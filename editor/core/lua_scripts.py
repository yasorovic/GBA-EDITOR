"""
core/lua_scripts.py — quels `.lua` sont des scripts, quels sont des behaviors, et où ils sont.

Un script Lua se range où l'auteur veut sous `assets/`. Son RÔLE ne vient donc pas de son dossier mais de
son contenu : un behavior (un module que d'autres scripts importent) commence par la ligne
`-- @behavior`. Tout autre `.lua` est un script, qu'on attache à un acteur, une scène ou une caméra.

`require("behaviors/<nom>")` reste l'appel écrit : `behaviors/` y est un espace de noms, plus un dossier, et
`<nom>` se résout PAR NOM parmi les behaviors du projet, où qu'ils soient. Deux behaviors de même nom ne se
départagent pas : c'est une erreur de build (`core.validator`).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

BEHAVIOR_MARKER = "-- @behavior"
_NAMESPACE = "behaviors"


def is_behavior(path) -> bool:
    """La première ligne du fichier est-elle le marqueur ? Un fichier illisible n'en est pas un."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.readline().strip() == BEHAVIOR_MARKER
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
    assets = project.assets_dir
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


def script_files(project) -> list[Path]:
    """Les scripts qu'on peut attacher : les `.lua` qui ne sont pas des behaviors."""
    return [path for path in lua_files(project) if not is_behavior(path)]


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


def require_name(target: str) -> str:
    """`"behaviors/paddle_ai"` → `"paddle_ai"`."""
    prefix = f"{_NAMESPACE}/"
    return target[len(prefix):] if target.startswith(prefix) else Path(target).stem
