"""
core/launch_target.py — ce que l'éditeur ouvre quand on lui passe un fichier au lancement.

Trois formes, la première venue gagne :

- `<Nom>.project`, le manifeste (double-clic dans l'explorateur) : on ouvre son dossier ;
- un fichier d'asset (`Hero.sprite`, `Level.scene`…) ou un script `.lua` d'un projet : on ouvre le
  projet qui le contient (le premier dossier parent qui porte un manifeste) et on y montre le fichier,
  comme un double-clic dans l'onglet Disk ;
- tout le reste est ignoré.

Seul le manifeste `.project` est associé au système (installateur, MIME) : les extensions d'asset
(`.font`, `.table`, `.scene`…) sont trop génériques pour qu'on les réclame à l'utilisateur. Un asset passé
en argument vient d'un terminal, d'un raccourci ou d'un autre outil.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.models.asset_extensions import ALL_EXTENSIONS
from core.project_paths import PROJECT_EXT, ProjectManifestError, find_manifest

_OPENABLE_SUFFIXES = ALL_EXTENSIONS | {".lua"}


@dataclass(frozen=True)
class LaunchTarget:
    project_root: Path
    asset: Path | None = None       # le fichier à montrer une fois le projet ouvert


def find_project_root(path: Path) -> Path | None:
    """Le dossier projet qui contient `path` (son premier parent portant un manifeste), ou None.
    Un dossier à plusieurs manifestes est rendu tel quel : c'est à l'ouverture de le refuser, avec son message."""
    for folder in path.resolve().parents:
        try:
            if find_manifest(folder) is not None:
                return folder
        except ProjectManifestError:
            return folder
    return None


def parse_launch_arguments(args: list[str]) -> LaunchTarget | None:
    for arg in args:
        path = Path(arg)
        if arg.endswith(PROJECT_EXT):
            return LaunchTarget(path.parent if path.is_file() else path)
        if path.suffix in _OPENABLE_SUFFIXES and path.is_file():
            root = find_project_root(path)
            if root is not None:
                return LaunchTarget(root, path.resolve())
    return None
