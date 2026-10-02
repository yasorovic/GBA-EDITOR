"""
tools/check_architecture.py — les règles d'architecture, rendues exécutables.

    python tools/check_architecture.py

Une règle écrite dans un document ne se vérifie que si quelqu'un la relit. Les
six contrôles ci-dessous sont les mêmes règles, mais qui répondent tout seuls.
Sortie non nulle en cas d'échec, pour qu'ils puissent garder une CI.

Chacun vient d'un défaut RÉEL trouvé dans ce dépôt, et le commentaire de chaque
contrôle dit lequel — c'est ce qui distingue un garde-fou d'une coquetterie.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import importlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDITOR = ROOT / "editor"

# ── Les couches, de la plus haute à la plus basse ─────────────────
#
#   ui           l'interface
#   core         la logique éditeur et le projet ouvert
#   core.models  les données du projet, et le format binaire qu'elles décrivent
#   codegen      la génération du C, qui consomme le modèle
#   scripting    la compilation Lua -> C
#
# Une couche ne dépend jamais de ce qui est au-dessus d'elle. UNE EXCEPTION,
# déclarée et assumée : la génération lit les données du projet — c'est sa
# raison d'être — donc `codegen` et `scripting` ont le droit d'importer `core`.
# Ce qu'ils n'ont pas le droit de faire, c'est de toucher à l'interface.
INTERDITS = {
    "core":        ("ui",),
    "core.models": ("ui", "core", "codegen", "scripting"),
    "codegen":     ("ui",),
    "scripting":   ("ui",),
}

# ── Ce qui n'a pas d'appelant mais doit vivre quand même ──────────
# Une exemption se justifie par écrit, sinon c'est une liste qui grossit.
VIVANTS_SANS_APPELANT = {
    "all_editors": "surface d'extension des plugins — documentée dans "
                   "component_editors/__init__.py, appelée depuis un plugin tiers",
}

# Décorateurs qui TRANSFORMENT sans référencer — leur présence ne prouve pas
# qu'un symbole sert encore.
DECORATEURS_INERTES = {
    "dataclass", "property", "staticmethod", "classmethod", "contextmanager",
    "cached_property", "abstractmethod", "override", "wraps",
}


def _nom_decorateur(node: ast.AST) -> str:
    """`@register("x")` -> "register" ; `@dataclasses.dataclass` -> "dataclass"."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    return getattr(node, "id", "")


# ── Boucles connues, assumées, datées ─────────────────────────────
# Un contrôle rouge en permanence est un contrôle que plus personne ne lance.
# Ces deux-là sont donc ACCEPTÉES, pas ignorées : elles apparaissent dans le
# rapport avec leur raison, et toute boucle NOUVELLE fait échouer la commande.
# Retirer une ligne d'ici le jour où la boucle est cassée.
BOUCLES_ACCEPTEES: dict = {
    # 2026-09-07 — la boucle canvas_tools ↔ scene_canvas est DÉNOUÉE par la
    # découpe (A3) : `GBAView` vit dans canvas_view et n'est plus importée par
    # canvas_tools qu'en TYPE_CHECKING ; `SpriteItem` vient de canvas_items. Plus
    # aucune boucle acceptée. Ajouter une entrée ici seulement pour une boucle
    # documentée et inévitable.
}


def module_name(path: Path) -> str:
    parts = list(path.relative_to(EDITOR).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def layer_of(mod: str) -> str | None:
    if mod.startswith("core.models"):
        return "core.models"
    for couche in ("ui", "core", "codegen", "scripting"):
        if mod == couche or mod.startswith(couche + "."):
            return couche
    return None


def lignes_type_checking(tree: ast.AST) -> set[int]:
    """Lignes d'un bloc `if TYPE_CHECKING:` — elles ne s'exécutent jamais, donc
    elles ne peuvent pas fabriquer de boucle réelle."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            t = node.test
            nom = (t.id if isinstance(t, ast.Name)
                   else t.attr if isinstance(t, ast.Attribute) else "")
            if nom == "TYPE_CHECKING":
                for b in node.body:
                    for sub in ast.walk(b):
                        if hasattr(sub, "lineno"):
                            out.add(sub.lineno)
    return out


class Rapport:
    def __init__(self) -> None:
        self.echecs: list[str] = []
        self.sections: list[tuple[str, int]] = []

    def section(self, titre: str, echecs: list[str]) -> None:
        etat = "OK" if not echecs else f"{len(echecs)} PROBLEME(S)"
        print(f"\n=== {titre} : {etat}")
        for e in echecs:
            print(f"    {e}")
        self.echecs += echecs
        self.sections.append((titre, len(echecs)))


def _import_isole(mod: str) -> tuple[str, str]:
    """Importe `mod` SEUL dans un interpréteur neuf. Rend (mod, erreur|"")."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '.'); import {mod}"],
        cwd=EDITOR, capture_output=True, text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    if r.returncode == 0:
        return mod, ""
    derniere = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
    return mod, (derniere[-1] if derniere else "échec sans message")


def controle_ordre_d_import(mods: dict) -> list[str]:
    """Chaque module tient-il debout SEUL, premier chargé ?

    Le contrôle des boucles lit le code ; celui-ci l'exécute. Il existe parce
    qu'aucun des autres n'a vu ceci : `scripting.api` importait `codegen.c_names`
    — sept lignes sans dépendance — mais importer un module d'un paquet exécute
    d'abord son `__init__.py`, et celui de `codegen` tirait toute la chaîne de
    build jusqu'à `core.project`, déjà en cours d'initialisation. Boucle.

    Charger tous les modules d'affilée ne le montre pas : le premier import
    réussi amorce le cache, et l'ordre alphabétique masque le problème. Il faut
    un interpréteur NEUF par module — d'où le coût, d'où l'option."""
    from concurrent.futures import ThreadPoolExecutor
    echecs = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for mod, err in pool.map(_import_isole, sorted(mods)):
            if err:
                echecs.append(f"{mod} seul : {err}")
    return echecs


#  Les fonctions qui CITENT une clé de notice, et la position de la clé dans
#  leurs arguments. `note(layout, clé)` a la sienne en second : c'est le seul
#  niveau dont la clé peut changer d'un rafraîchissement à l'autre, d'où la
#  signature qui met le lieu d'abord (cf. ui/common/notice.py).
CITATIONS_NOTICES = {"note": 1, "notice": 0, "tip": 0, "text": 0, "show_text": 0}
#  Les libellés n'ont qu'un accès, `label(clé)` (cf. ui/common/labels.py).
CITATIONS_LABELS = {"label": 0}


def controle_catalogue(trees: dict, nom_catalogue: str, citations: dict) -> list:
    """Toute clé citée existe dans le catalogue, toute entrée est citée. Vaut
    pour les deux catalogues d'interface (notices, libellés) : même fichier
    `<nom>/<nom>.json`, même grammaire, seule change la table des citations."""
    catalogue = json.loads(
        (EDITOR / "ui" / "common" / nom_catalogue / f"{nom_catalogue}.json")
        .read_text(encoding="utf-8")
    )[nom_catalogue]
    citees: dict[str, str] = {}     # clé littérale EN POSITION D'APPEL
    littérales: set[str] = set()    # n'importe quelle chaîne du code
    familles: list[re.Pattern] = []  # clés construites : f"win.{k}_note"
    for m, t in trees.items():
        for node in ast.walk(t):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                littérales.add(node.value)
            if isinstance(node, ast.JoinedStr):
                famille = _famille_de_cles(node)
                if famille is not None:
                    familles.append(famille)
            elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                  and isinstance(node.left, ast.Constant)
                  and isinstance(node.left.value, str)
                  and re.match(r"^[a-z][a-z0-9_]*\.", node.left.value)
                  and not isinstance(node.right, ast.Constant)):
                # `"win.iwram_part" + sec` : la clé s'achève à l'exécution.
                familles.append(re.compile(re.escape(node.left.value) + r"[a-z0-9_.]*"))
            if not isinstance(node, ast.Call):
                continue
            nom = (node.func.attr if isinstance(node.func, ast.Attribute)
                   else getattr(node.func, "id", ""))
            pos = citations.get(nom)
            if pos is None or len(node.args) <= pos:
                continue
            arg = node.args[pos]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                citees.setdefault(arg.value, f"{m}:{node.lineno}")
    # Le sens « orpheline » se contente d'une chaîne trouvée n'importe où :
    # une clé rangée dans un tuple ou une table de correspondance est citée
    # pour de bon, elle ne passe simplement pas par l'argument d'un appel. Une clé
    # CONSTRUITE (`label(f"win.{key}_note")`) l'est aussi : elle n'existe jamais
    # entière dans le code, mais sa famille — `win.<quelque chose>_note` — oui.
    return ([f"{clé} citée en {où} — absente du catalogue"
             for clé, où in sorted(citees.items()) if clé not in catalogue]
            + [f"{clé} — dans le catalogue, citée nulle part"
               for clé in sorted(catalogue)
               if clé not in littérales
               and not any(f.fullmatch(clé) for f in familles)])


def _famille_de_cles(noeud: ast.JoinedStr):
    """Le motif d'une clé de catalogue CONSTRUITE par f-string, ou None.

    `f"win.{key}_note"` → `win\\.[a-z0-9_.]+_note`. Seule une f-string dont le
    premier morceau LIT comme un début de clé (`écran.`) compte : un message
    ordinaire ou un chemin, qui ne ressemble pas à `préfixe.suite`, n'excuse
    aucune entrée du catalogue."""
    morceaux = noeud.values
    if not morceaux or not isinstance(morceaux[0], ast.Constant):
        return None
    if not re.match(r"^[a-z][a-z0-9_]*\.", str(morceaux[0].value)):
        return None
    if not any(isinstance(m, ast.FormattedValue) for m in morceaux):
        return None
    motif = "".join(
        re.escape(str(m.value)) if isinstance(m, ast.Constant) else r"[a-z0-9_.]+"
        for m in morceaux)
    return re.compile(motif)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fresh", action="store_true",
                    help="importe chaque module SEUL dans un interpréteur neuf "
                         "(seul moyen de voir une boucle qui dépend de l'ordre ; "
                         "compter une vingtaine de secondes)")
    args = ap.parse_args()
    os.chdir(EDITOR)
    sys.path.insert(0, str(EDITOR))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
    except Exception:
        pass   # les contrôles purement statiques n'en ont pas besoin

    fichiers = [p for p in sorted(EDITOR.rglob("*.py")) if ".ruff_cache" not in str(p)]
    mods: dict[str, Path] = {}
    trees: dict[str, ast.AST] = {}
    sources: dict[str, str] = {}
    erreurs_syntaxe = []
    for p in fichiers:
        m = module_name(p)
        src = p.read_text(encoding="utf-8")
        mods[m], sources[m] = p, src
        try:
            trees[m] = ast.parse(src)
        except SyntaxError as e:
            erreurs_syntaxe.append(f"{p.relative_to(ROOT)} : {e}")

    r = Rapport()
    r.section("Syntaxe", erreurs_syntaxe)
    if erreurs_syntaxe:
        return 1

    # ── graphe d'imports internes (TYPE_CHECKING exclu) ──────────
    graphe: dict[str, set[str]] = defaultdict(set)
    differes: dict[str, set[str]] = defaultdict(set)
    for m, t in trees.items():
        sautees = lignes_type_checking(t)
        au_sommet = {id(n) for n in t.body}
        for node in ast.walk(t):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.lineno in sautees:
                continue
            noms = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else ([node.module] if node.module and not node.level else []))
            for n in noms:
                parts = n.split(".")
                for i in range(len(parts), 0, -1):
                    cible = ".".join(parts[:i])
                    if cible in mods and cible != m:
                        graphe[m].add(cible)
                        if id(node) not in au_sommet:
                            differes[m].add(cible)
                        break

    # ── 1. Boucles d'import ──────────────────────────────────────
    # Trouvé ainsi : dix modules mutuellement dépendants, invisibles parce que
    # contournés par des imports posés au fond des fonctions. Python ne proteste
    # jamais ; sans ce contrôle, personne ne le voit.
    index, low, sur_pile, pile, boucles, compteur = {}, {}, {}, [], [], [0]

    def tarjan(v: str) -> None:
        index[v] = low[v] = compteur[0]
        compteur[0] += 1
        pile.append(v)
        sur_pile[v] = True
        for w in sorted(graphe.get(v, ())):
            if w not in index:
                tarjan(w)
                low[v] = min(low[v], low[w])
            elif sur_pile.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = pile.pop()
                sur_pile[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                boucles.append(sorted(comp))

    sys.setrecursionlimit(10000)
    for m in sorted(trees):
        if m not in index:
            tarjan(m)
    nouvelles, acceptees = [], []
    for c in sorted(boucles, key=len, reverse=True):
        raison = BOUCLES_ACCEPTEES.get(frozenset(c))
        (acceptees if raison else nouvelles).append(
            f"{len(c)} modules : " + " <-> ".join(c) + (f"\n        assumee : {raison}" if raison else ""))
    for a in acceptees:
        print(f"    [assumee] {a}")
    r.section("Boucles d'import", nouvelles)

    # ── 2. Sens des dépendances ──────────────────────────────────
    # Trouvé ainsi : `core/asset_manager.py`, un fichier d'INTERFACE rangé dans
    # `core/`, qui faisait dépendre la logique éditeur de l'UI.
    violations = []
    for src, cibles in sorted(graphe.items()):
        ls = layer_of(src)
        if ls is None:
            continue
        for d in sorted(cibles):
            ld = layer_of(d)
            if ld and ld in INTERDITS.get(ls, ()):
                violations.append(f"{src} ({ls}) importe {d} ({ld})")
    r.section("Sens des dépendances", violations)

    # ── 3. Les imports désignent-ils des noms qui existent ? ─────
    # Trouvé ainsi : six imports DIFFÉRÉS cassés par un déplacement de symbole.
    # Charger tous les modules ne les exécute pas — ils n'auraient échoué que le
    # jour où l'utilisateur emprunte ce chemin-là.
    interne = ("core", "ui", "codegen", "scripting", "plugins", "window")
    irresolus = []
    for m, t in trees.items():
        for node in ast.walk(t):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if node.module.split(".")[0] not in interne:
                continue
            try:
                cible = importlib.import_module(node.module)
            except Exception as e:
                irresolus.append(f"{m}:{node.lineno} module {node.module} : {type(e).__name__}")
                continue
            for a in node.names:
                if a.name == "*" or hasattr(cible, a.name):
                    continue
                try:            # un sous-module n'est un attribut qu'une fois importé
                    importlib.import_module(f"{node.module}.{a.name}")
                except Exception:
                    irresolus.append(f"{m}:{node.lineno} {node.module} n'expose pas `{a.name}`")
    r.section("Imports résolus", irresolus)

    # ── 4. Noms utilisés, liés nulle part ────────────────────────
    # Trouvé ainsi : une fonction dupliquée supprimée d'un module... qui
    # continuait de l'appeler, sans que l'import soit posé. Aucun des contrôles
    # précédents ne le voit : il n'y a pas d'import fautif, il n'y en a PAS.
    # Approximation volontairement large (tout nom lié quelque part dans le
    # module compte comme lié) : ça rate des cas, ça n'en invente pas.
    connus_partout = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "self", "cls"}
    orphelins = []
    for m, t in trees.items():
        lies = set()
        for node in ast.walk(t):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    lies.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                   ast.Lambda)):
                if not isinstance(node, ast.Lambda):
                    lies.add(node.name)
                # Les paramètres, y compris ceux d'une lambda : `lambda p: p.name`
                # lie bien `p`, et l'oublier faisait crier ce contrôle sur des
                # dizaines de connexions de signaux Qt.
                # `parametres` et non `args` : ce dernier est déjà la ligne de
                # commande, plus haut dans la même fonction — le réutiliser ici
                # l'écrasait, et `--fresh` disparaissait. Le piège que ce
                # fichier signale à propos de `sym`, tendu à moi-même.
                parametres = getattr(node, "args", None)
                if parametres:
                    for a in (parametres.args + parametres.posonlyargs
                              + parametres.kwonlyargs):
                        lies.add(a.arg)
                    for a in (parametres.vararg, parametres.kwarg):
                        if a:
                            lies.add(a.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                lies.add(node.id)
            elif isinstance(node, (ast.ExceptHandler,)) and node.name:
                lies.add(node.name)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                lies.add(node.name)          # `case d if d == X:` lie bien `d`
            elif isinstance(node, ast.MatchMapping) and node.rest:
                lies.add(node.rest)
            elif isinstance(node, ast.Global):
                lies |= set(node.names)
        for node in ast.walk(t):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in lies and node.id not in connus_partout:
                    orphelins.append(f"{m}:{node.lineno} `{node.id}` n'est lié nulle part")
    r.section("Noms résolus", sorted(set(orphelins)))

    # ── 5. Symboles de module sans aucun appelant ────────────────
    # Une ancienne implémentation qu'on a oublié de retirer ne se signale
    # jamais : elle compile, elle s'importe, elle ne sert plus.
    morts = []
    for m, t in trees.items():
        for node in t.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            nom = node.name
            if nom.startswith("__") or nom in VIVANTS_SANS_APPELANT:
                continue
            # Un décorateur qui INSCRIT compte comme un usage : `@register(...)`
            # range la classe dans un registre, et plus rien ne la cite ensuite
            # par son nom. Sans cette règle, tout le système de plugins passait
            # pour mort. Les décorateurs INERTES (`@dataclass`, `@property`…) ne
            # comptent pas : ils transforment l'objet, ils ne le référencent nulle
            # part — sans quoi toute dataclass inutilisée deviendrait invisible.
            if any(d for d in node.decorator_list
                   if _nom_decorateur(d) not in DECORATEURS_INERTES):
                continue
            if any(o.count(nom) for om, o in sources.items() if om != m):
                continue
            if sources[m].count(nom) > 1:
                continue
            morts.append(f"{m}.{nom} (l.{node.lineno}) n'est cité nulle part")
    r.section("Code mort", morts)

    # ── 6. Symboles privés qui traversent un module ──────────────
    # Le tiret bas dit « ne m'appelle pas de dehors ». Vingt et un endroits le
    # faisaient : le code contredisait son propre signal, et un lecteur ne
    # savait plus lequel croire.
    prives = []
    for m, t in trees.items():
        for node in ast.walk(t):
            if isinstance(node, ast.ImportFrom) and node.module and \
               node.module.split(".")[0] in interne:
                for a in node.names:
                    if a.name.startswith("_") and not a.name.startswith("__"):
                        prives.append(f"{m}:{node.lineno} importe `{a.name}` de {node.module}")
    r.section("Frontières respectées", prives)

    # ── 7. Catalogue de notices ↔ code ───────────────────────────
    # Trouvé ainsi : quatre infobulles d'inspecteur qui citaient une clé absente
    # de leur propre dictionnaire, et n'affichaient donc RIEN depuis toujours.
    # Une clé mal tapée donne un message vide, et un message vide ne se plaint
    # jamais — c'est le seul défaut de ce chantier qu'aucun test ne verrait.
    # Le contrôle vaut dans les DEUX sens : une entrée que plus personne ne cite
    # est du texte à traduire pour rien.
    r.section("Catalogue de notices",
              controle_catalogue(trees, "notices", CITATIONS_NOTICES))

    # ── 8. Catalogue de libellés ↔ code ──────────────────────────
    # Même contrôle, catalogue frère (ROADMAP v0.11) : les libellés d'interface
    # extraits vers labels.json. Une clé mal tapée afficherait la clé brute ;
    # une entrée que plus personne ne cite est du texte à traduire pour rien.
    r.section("Catalogue de libellés",
              controle_catalogue(trees, "labels", CITATIONS_LABELS))

    from check_ui_text import check as check_ui_text
    r.section("Textes d'interface : structure, paramètres et extraction",
              check_ui_text(ROOT))

    if args.fresh:
        r.section("Ordre d'import (interpréteur neuf par module)",
                  controle_ordre_d_import(mods))
    else:
        print("\n=== Ordre d'import : NON TESTE (relancer avec --fresh)")

    print("\n" + "-" * 60)
    for titre, n in r.sections:
        print(f"  {'OK ' if not n else 'KO '} {titre}" + (f" ({n})" if n else ""))
    if r.echecs:
        print(f"\n{len(r.echecs)} probleme(s). Voir ARCHITECTURE.md, section "
              f"« Sens des dependances ».")
        return 1
    print("\nTout est conforme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
