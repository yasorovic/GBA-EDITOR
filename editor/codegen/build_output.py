"""editor/codegen/build_output.py — ce que le build ÉCRIT, et quand.

POINT DE VÉRITÉ UNIQUE de la règle « ne pas réécrire un fichier identique »
(ROADMAP v0.24). Tout ce que le build dépose dans `build/` passe par ici.

── Le problème, mesuré (2026-08-20, projet Pong) ────────────────────────
Un rebuild où RIEN n'a changé coûtait 9,09 s contre 10,08 s à froid : presque
rien de gagné. `make` reprenait 3,5 s pour recompiler du code identique.

La cause n'est pas dans `make`, qui fait exactement son travail : sur
40 fichiers générés, 36 avaient un contenu IDENTIQUE au build précédent, mais
32 voyaient leur date de modification réécrite. `make` compare des dates ; il
recompilait donc 32 fichiers pour rien, à chaque itération.

── La règle ─────────────────────────────────────────────────────────────
On n'écrit un fichier que si son CONTENU diffère. Sinon on n'y touche pas —
sa date reste celle de la dernière vraie modification, et `make` le saute.

C'est la décision verrouillée du chantier (« sur l'EMPREINTE de la source et
des options, pas sur la date ») appliquée un cran plus haut : plutôt que de
construire un cache à côté du compilateur, on rend au compilateur le seul
signal dont il a besoin pour utiliser le sien.

── Le cas grit ──────────────────────────────────────────────────────────
`grit` estampille l'heure d'export dans un commentaire de ses .c/.h :

    //	Time-stamp: 2026-08-20, 21:36:58

Ce seul commentaire suffit à rendre le fichier « différent » à chaque build,
donc à le faire recompiler — et à le faire apparaître modifié dans `git
status` alors que pas un octet de donnée n'a bougé. `strip_volatile_stamp`
neutralise la ligne. Ce n'est pas de la cosmétique : sans elle, la règle
ci-dessus n'a aucun effet sur la sortie de grit.

(Troisième défaut de grit relevé par ce projet, après `-fa` multi-fichier et
`-pn` ignoré sous `-pS`.)
"""
from __future__ import annotations
import re
from pathlib import Path

# La ligne d'horodatage de grit, remplacée par une mention stable. On la garde
# VISIBLE plutôt que supprimée : un lecteur du fichier généré doit comprendre
# pourquoi l'heure d'export n'y est pas, sans avoir à retrouver ce module.
_GRIT_STAMP = re.compile(r"^(//\s*)Time-stamp:.*$", re.MULTILINE)
_GRIT_STAMP_REPLACEMENT = r"\1Time-stamp: (neutralised — see codegen/build_output.py)"

# Ce que le build en cours a produit, et ce qu'il a laissé tel quel. Remis à
# zéro par `begin_build()`.
written = 0
skipped = 0
_emitted: set[Path] = set()


def begin_build() -> None:
    global written, skipped
    written = skipped = 0
    _emitted.clear()


def claim(path: Path) -> None:
    """Déclare un fichier produit par un outil EXTERNE (grit, mmutil, bin2s).

    `sweep` ne peut pas deviner qu'il est légitime : il n'est pas passé par
    `write`. Sans cette déclaration, il serait pris pour un reste périmé."""
    _emitted.add(Path(path).resolve())


def sweep(dirs, suffixes=(".c", ".h", ".s")) -> list[Path]:
    """Supprime, dans `dirs`, les fichiers que CE build n'a pas produits.

    Remplace le `rmtree` que `Project.prepare_build` faisait en tête de build.
    Le rmtree répondait à un vrai risque — le Makefile ramasse `src/*.c` au
    glob, donc un sprite retiré du projet laissait derrière lui un `.c` qui
    continuait d'être compilé et lié. Mais il effaçait AUSSI les 32 fichiers
    identiques d'un build à l'autre, et c'est ce qui rendait chaque itération
    aussi chère qu'une compilation complète.

    Balayer à la FIN répond au même risque sans le prix : ce qui n'a pas été
    produit cette fois-ci n'a plus lieu d'être. Volontairement restreint aux
    extensions compilées et aux répertoires GÉNÉRÉS — on ne supprime jamais un
    fichier qu'on ne sait pas reproduire."""
    removed = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix in suffixes and f.resolve() not in _emitted:
                f.unlink()
                removed.append(f)
    return removed


def strip_volatile_stamp(text: str) -> str:
    """Neutralise l'horodatage que grit met dans ses fichiers générés."""
    return _GRIT_STAMP.sub(_GRIT_STAMP_REPLACEMENT, text)


def write(path: Path, text: str, encoding: str = "utf-8") -> bool:
    """Écrit `text` dans `path` SEULEMENT s'il diffère de ce qui s'y trouve.

    Rend True si le fichier a été réécrit. La comparaison porte sur le texte
    décodé et non sur les octets : un fichier relu avec le même encodage que
    celui d'écriture donne le même texte, et c'est le contenu qui décide."""
    global written, skipped
    text = strip_volatile_stamp(text)
    _emitted.add(Path(path).resolve())
    try:
        if path.read_text(encoding=encoding) == text:
            skipped += 1
            return False
    except (OSError, UnicodeDecodeError):
        pass          # absent, illisible, ou d'un autre encodage : on écrit
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    written += 1
    return True


def copy(src: Path, dst: Path, encoding: str = "utf-8") -> bool:
    """Le pendant de `write` pour un fichier recopié tel quel (les en-têtes
    statiques du runtime). `shutil.copy2` préserverait la date de la SOURCE,
    ce qui suffirait presque — mais la source change de date à chaque `git
    checkout`, exactement le cas que la décision verrouillée écarte."""
    return write(dst, src.read_text(encoding=encoding), encoding=encoding)
