"""
core/lua_scripts.py — quels `.lua` sont des scripts, quels sont des behaviors, et où ils sont.

Un script Lua se range où l'auteur veut sous `assets/`. Son RÔLE ne vient donc pas de son dossier mais de
son contenu : un behavior (un module que d'autres scripts importent) commence par la ligne
`-- @behavior`. Tout autre `.lua` est un script, qu'on attache à un acteur, une scène ou une caméra.

`require("Nom")` désigne une bibliothèque par son nom logique. Le dossier ne fait pas partie de cette
référence : déplacer le fichier ne change donc pas ses importeurs. Les Behaviors et les modules privés partagent
un même espace de noms, car l'import ne doit pas dépendre de leur nature. Deux bibliothèques de même nom sont une
erreur de build (`core.validator`).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

BEHAVIOR_MARKER = "-- @behavior"
MODULE_MARKER = "-- @module"


def is_behavior(path) -> bool:
    """La première ligne du fichier est-elle le marqueur ? Un fichier illisible n'en est pas un."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.readline().strip() == BEHAVIOR_MARKER
    except (OSError, UnicodeDecodeError):
        return False


def is_private_module(path) -> bool:
    """La premiere ligne marque-t-elle un module prive importable ?"""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.readline().strip() == MODULE_MARKER
    except (OSError, UnicodeDecodeError):
        return False


def lua_files(project) -> list[Path]:
    """Tous les `.lua` de `assets/`, à toute profondeur.

    Dans `lua_files_cached`, le parcours (plusieurs centaines de ms sur un gros `assets/`) n'est fait qu'une fois."""
    memo = getattr(project, "_lua_files_memo", None)
    if memo is not None:
        if memo["files"] is None:
            memo["files"] = _scan(project)
        return list(memo["files"])
    return _scan(project)


def _scan(project) -> list[Path]:
    assets = project.user_library_dir
    return sorted(assets.rglob("*.lua")) if assets.is_dir() else []


@contextmanager
def lua_files_cached(project):
    """Le temps d'une opération qui ne crée ni ne supprime de script (renommage par lot, rafraîchissement qui suit),
    `lua_files` ne parcourt `assets/` qu'une fois. Imbriqué, c'est le plus extérieur qui compte."""
    if getattr(project, "_lua_files_memo", None) is not None:
        yield
        return
    project._lua_files_memo = {"files": None}
    try:
        yield
    finally:
        project._lua_files_memo = None


def behavior_files(project) -> list[Path]:
    return [path for path in lua_files(project) if is_behavior(path)]


def private_module_files(project) -> list[Path]:
    return [path for path in lua_files(project) if is_private_module(path)]


def script_files(project) -> list[Path]:
    """Les scripts qu'on peut attacher, distincts des bibliotheques importables."""
    return [path for path in lua_files(project)
            if not is_behavior(path) and not is_private_module(path)]


def behaviors_by_name(project) -> dict[str, list[Path]]:
    """`{nom: [fichiers]}` ; plus d'un fichier pour un nom = ambigu."""
    found: dict[str, list[Path]] = {}
    for path in behavior_files(project):
        found.setdefault(path.stem, []).append(path)
    return found


def behavior_paths(project) -> dict[str, Path]:
    """`{nom: fichier}` pour la résolution des `require` ; un nom ambigu prend le premier (le build s'arrête
    de toute façon sur l'erreur de doublon)."""
    return {name: paths[0] for name, paths in behaviors_by_name(project).items()}


def private_modules_by_name(project) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for path in private_module_files(project):
        found.setdefault(path.stem, []).append(path)
    return found


def library_paths(project) -> dict[str, Path]:
    """Nom logique de bibliothèque -> fichier, toutes natures confondues."""
    found: dict[str, Path] = {}
    for name, paths in behaviors_by_name(project).items():
        found[name] = paths[0]
    for name, paths in private_modules_by_name(project).items():
        found.setdefault(name, paths[0])
    return found


def require_name(target: str) -> str:
    """Un import est un nom logique, jamais un chemin ou un espace de noms."""
    return target if target and "/" not in target and "\\" not in target else ""
