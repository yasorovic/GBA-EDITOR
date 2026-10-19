"""ui/common/import_folder.py — le dossier où naît un fichier importé depuis un écran.

Tous les boutons d'import (sprite, fond, remplacement d'image) posent le fichier dans le dossier que
l'onglet Disk affiche (cf. `core.asset_creation.import_folder`). La fenêtre branche l'onglet une fois ;
les écrans n'ont pas à le connaître.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core import asset_creation

_shown_folder: Callable[[], Optional[str]] = lambda: None


def set_shown_folder_provider(provider: Callable[[], Optional[str]]) -> None:
    global _shown_folder
    _shown_folder = provider


def import_folder(project) -> Path:
    """Le dossier d'accueil d'un import, créé s'il manque."""
    folder = asset_creation.import_folder(project, _shown_folder())
    folder.mkdir(parents=True, exist_ok=True)
    return folder
