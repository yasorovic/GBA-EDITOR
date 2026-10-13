"""Repli des sections et des dossiers des finders, retenu d'une session à l'autre.

Préférence d'affichage locale (comme `disk_folder_colors`) : elle suit l'auteur,
pas le projet. Tout est replié tant que l'auteur n'a rien déplié.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from core.app_info import APP_NAME


def _settings() -> QSettings:
    return QSettings(APP_NAME, "FinderFold")


def is_expanded(key: str) -> bool:
    return _settings().value(key, False, type=bool)


def set_expanded(key: str, expanded: bool) -> None:
    settings = _settings()
    if expanded:
        settings.setValue(key, True)
    else:
        settings.remove(key)        # replié = défaut : rien à retenir
