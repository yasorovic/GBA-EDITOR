"""Starters de projet locaux, intégrés ou fournis par l'utilisateur.

Un starter est une arborescence qui ne contient que ``assets/`` et ``project/``.
Il peut donc être édité comme un projet normal sans emporter son manifeste,
ses réglages d'identité ou un build obsolète dans le projet créé.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from core.app_info import APP_NAME


USER_STARTERS_DIR = Path.home() / f".{APP_NAME.lower()}" / "project_starters"
BUILTIN_STARTERS_DIR = Path(__file__).resolve().parent.parent / "project_starters"


@dataclass(frozen=True)
class ProjectStarter:
    id: str
    display_name: str
    path: Path
    builtin: bool = False


def available_starters() -> list[ProjectStarter]:
    """Retourne Basic puis les presets déposés dans le dossier utilisateur."""
    starters: list[ProjectStarter] = []
    for directory, builtin in ((BUILTIN_STARTERS_DIR, True), (USER_STARTERS_DIR, False)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda candidate: candidate.name.casefold()):
            if path.is_dir() and (path / "project").is_dir():
                identifier = path.name if builtin else f"user:{path.name}"
                starters.append(ProjectStarter(identifier, path.name, path, builtin))
    return starters


def get_starter(identifier: str = "Basic") -> ProjectStarter:
    for starter in available_starters():
        if starter.id == identifier:
            return starter
    raise ValueError(f"Starter de projet introuvable : {identifier}")


def copy_starter(starter: ProjectStarter, destination: Path) -> None:
    """Copie seulement le contenu versionnable d'un starter vers le projet."""
    for name in ("assets", "project"):
        source = starter.path / name
        if source.is_dir():
            shutil.copytree(source, destination / name, dirs_exist_ok=True)
