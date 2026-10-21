"""editor/core/project_json.py — comment le projet écrit son JSON.

POINT DE VÉRITÉ UNIQUE de la MISE EN PAGE des fichiers de projet. Ce que contiennent ces fichiers appartient aux modèles ; la façon dont
ils se posent sur des lignes appartient ici, parce que c'est une seule règle
et qu'elle doit valoir partout de la même façon.

── Le problème que ça résout, et celui qu'il ne résout PAS ──────────────
`json.dumps(indent=2)` met UN scalaire par ligne. Une carte de collision de
30×20 devient donc 642 lignes, une police 2 242, un fond 684 — mesuré sur le
projet démo (14 444 lignes de JSON au total, ramenées à 3 679).

Ce que ça résout : **l'historique se relit**. Un diff montrait
« ligne 347 : 0 → 1 », ce dont personne ne peut rien tirer ; il montre
maintenant la rangée entière, à sa place dans la carte.

Ce que ça NE résout pas — et on avait supposé le contraire, mesure
à l'appui du contraire (2026-08-20) : **la fusion automatique n'y gagne rien,
elle y perd**. `git merge-file` travaille à la ligne, donc un scalaire par
ligne offrait la granularité MAXIMALE : deux modifications quelconques de la
même carte fusionnaient toujours proprement. Une rangée par ligne fait
conflit dès que deux personnes touchent la même rangée.

C'est un échange assumé, pas un oubli : deux personnes qui peignent la même
bande de carte se chevauchent réellement, et une fusion silencieuse leur
rendait une carte que ni l'une ni l'autre n'avait voulue. Le conflit est
désormais visible — et résoluble à l'œil, puisque la rangée se lit.

── La règle, en une phrase ──────────────────────────────────────────────
Les clés listées dans `ROW_KEYS` tiennent des RANGÉES : chacun de leurs
enfants directs est écrit sur exactement UNE ligne. Tout le reste garde la
mise en page standard.

Deux propriétés qui comptent plus que la compacité :

- **C'est du JSON ordinaire.** Aucune relecture à changer, aucun décodeur à
  écrire, aucun format à migrer : `json.loads` relit ces fichiers tels quels.
  Une rangée reste une liste de nombres, un glyphe reste un objet.
- **La mise en page est STABLE.** Elle ne dépend que du nom de la clé, jamais
  de la longueur ou du contenu des valeurs. Une règle « une ligne tant qu'elle
  fait moins de N caractères » ferait re-couler tout un fichier au premier
  changement de valeur — soit exactement le diff illisible qu'on cherche à
  supprimer.
"""
from __future__ import annotations
import json

# Les clés dont les enfants directs sont des RANGÉES — une par ligne.
#
# Y entrer demande une seule justification : « un enfant de cette liste se
# lit-il seul ? ». Une rangée de carte, un glyphe, une sous-palette : oui.
# C'est la LISIBILITÉ qui décide, pas la fusion — cf. l'en-tête : la fusion
# automatique perd à ce change, elle n'y gagne pas.
#
# `tileset` n'y est PAS : ses enfants sont déjà des chaînes, donc déjà une par
# ligne — c'est la partie du sidecar de fond qui se relisait le mieux, et
# c'est elle qui a servi de modèle à cette règle.
ROW_KEYS: frozenset[str] = frozenset({
    # Grilles de scène — une ligne par rangée de tuiles.
    "collision_map",
    # Fond tuilé — la tilemap est rangée en 2D depuis la v0.24, justement pour
    # avoir des rangées à donner à cette règle (cf. models/background.py).
    "tilemap",
    # Une police — un glyphe par ligne. Ce n'est pas une grille, mais c'est
    # bien une séquence d'enregistrements indépendants, et c'est le plus gros
    # poste de lignes de tout le projet (9 003 sur 14 444, mesuré).
    "glyphs",
    # Catalogues de couleurs — une sous-palette par ligne. Les couleurs sont
    # écrites en #RRGGBB (cf. gba_color.py) : seize d'entre elles tiennent
    # alors sur une ligne qui se lit.
    "palettes", "source_palettes",
})


# ── Une grille écrite en rangées ─────────────────────────────────────
# Une grille rangée À PLAT n'a aucune rangée à donner à la règle ci-dessus :
# elle sort à un nombre par ligne, ce qui ne vaut pas mieux qu'avant. Ces deux
# fonctions ne servent qu'à la FRONTIÈRE du fichier — en mémoire, la grille
# reste plate là où elle l'était (une tilemap s'indexe par cellule).
#
# `read_grid` accepte les deux formes pour toujours : une liste de rangées
# (depuis la v0.24) ou la liste plate d'avant.

def write_grid(flat, width: int) -> list:
    """Une liste plate → une liste de rangées de `width` éléments."""
    if width <= 0:
        return list(flat)
    return [list(flat[i:i + width]) for i in range(0, len(flat), width)]


def read_grid(value) -> list:
    """Une grille relue du disque, en rangées ou à plat, → une liste plate."""
    if value and isinstance(value[0], list):
        return [cell for row in value for cell in row]
    return list(value or [])


def dumps(value, indent: int = 2) -> str:
    """Le JSON du projet : `json.dumps(indent=…)`, sauf sous une clé de
    `ROW_KEYS` où chaque enfant direct tient sur une ligne."""
    return _render(value, 0, indent)


def _render(v, depth: int, indent: int) -> str:
    pad = " " * (depth * indent)
    inner = " " * ((depth + 1) * indent)
    if isinstance(v, dict):
        if not v:
            return "{}"
        parts = []
        for k, val in v.items():
            key = json.dumps(str(k), ensure_ascii=False)
            body = (_rows(val, depth + 1, indent)
                    if k in ROW_KEYS and isinstance(val, list) and val
                    else _render(val, depth + 1, indent))
            parts.append(f"{inner}{key}: {body}")
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        parts = [inner + _render(x, depth + 1, indent) for x in v]
        return "[\n" + ",\n".join(parts) + "\n" + pad + "]"
    return json.dumps(v, ensure_ascii=False)


def _rows(rows: list, depth: int, indent: int) -> str:
    """Une rangée par ligne, chacune compacte."""
    pad = " " * (depth * indent)
    inner = " " * ((depth + 1) * indent)
    parts = [inner + json.dumps(r, ensure_ascii=False, separators=(", ", ": "))
             for r in rows]
    return "[\n" + ",\n".join(parts) + "\n" + pad + "]"
