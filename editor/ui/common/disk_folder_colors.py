"""Couleurs d'organisation des dossiers de l'onglet Disk.

Ce sont des préférences d'affichage locales : elles aident l'auteur à se
repérer dans SON éditeur sans modifier les fichiers du projet ni créer un
bruit de versionnement pour le reste de l'équipe.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings

from core.app_info import APP_NAME


COLORS = {
    "blue": "#82aaff",
    "violet": "#b392f0",
    "green": "#79c99e",
    "orange": "#d9a65a",
    "rose": "#df8eb9",
}


def _key(path) -> str:
    return str(Path(path).resolve())


def color_for(path) -> str | None:
    value = QSettings(APP_NAME, "DiskFolderColors").value(_key(path), "")
    return value if value in COLORS.values() else None


def set_color(path, color: str | None) -> None:
    settings = QSettings(APP_NAME, "DiskFolderColors")
    key = _key(path)
    if color in COLORS.values():
        settings.setValue(key, color)
    else:
        settings.remove(key)
