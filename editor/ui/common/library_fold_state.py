"""Repli des sections et des dossiers des libraries, retenu d'une session à l'autre.

Préférence d'affichage locale (comme `disk_folder_colors`) : elle suit l'auteur,
pas le projet. Tout est replié tant que l'auteur n'a rien déplié.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from core.app_info import APP_NAME


def _settings() -> QSettings:
    return QSettings(APP_NAME, "LibraryFold")


# Les clés dépliées, lues UNE fois : `QSettings` est un accès registre par appel sous Windows, et une library
# interroge chaque dossier à chaque repeuplement (≈0,2 ms × des centaines).
_expanded: "set[str] | None" = None


def _loaded() -> "set[str]":
    global _expanded
    if _expanded is None:
        settings = _settings()
        _expanded = {key for key in settings.allKeys() if settings.value(key, False, type=bool)}
    return _expanded


def is_expanded(key: str) -> bool:
    return key in _loaded()


def set_expanded(key: str, expanded: bool) -> None:
    settings = _settings()
    if expanded:
        settings.setValue(key, True)
        _loaded().add(key)
    else:
        settings.remove(key)        # replié = défaut : rien à retenir
        _loaded().discard(key)
