"""Ordre des cartes repliables (CollapsibleCard) d'un panneau, retenu d'une session à l'autre.

Préférence d'affichage locale (comme `library_fold_state`) : elle suit l'auteur, pas le projet.
Un panneau est désigné par la classe Python qui contient ses cartes ; une carte, par son titre.
Une carte absente de l'ordre retenu garde sa place d'origine.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from core.app_info import APP_NAME


def _settings() -> QSettings:
    return QSettings(APP_NAME, "CardOrder")


def load(panel: str) -> list[str]:
    value = _settings().value(panel, [])
    if isinstance(value, str):      # QSettings rend une liste d'un élément comme une chaîne
        return [value]
    return list(value or [])


def save(panel: str, titles: list[str]) -> None:
    """Retient `titles` ; les titres déjà retenus d'un autre layout du même panneau suivent."""
    others = [t for t in load(panel) if t not in titles]
    _settings().setValue(panel, titles + others)
