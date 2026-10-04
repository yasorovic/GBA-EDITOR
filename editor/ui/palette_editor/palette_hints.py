"""ui/palette_editor/palette_hints.py — contenu de la table des raccourcis de la
grille de palette. Pas d'outil : une seule table (la grille de couleurs).
Seuls les gestes propres à la grille s'affichent ; les raccourcis communs
(copier, vider, ajuster, zoom) vivent dans Réglages → Shortcuts."""
from __future__ import annotations

from ui.common.shortcut_hints import Hints, combo, key_icon, mouse


def palette_grid_hints(_context: str) -> Hints:
    return "hints.palette.title", [
        (mouse("left_click"), "hints.palette.select"),
        (mouse("left_drag"), "hints.palette.select_rect"),
        (combo("Shift", mouse("left_drag")), "hints.palette.select_range"),
        (mouse("right_click"), "hints.palette.menu"),
        (key_icon("dir_omni"), "hints.palette.move"),
        (combo("Shift", key_icon("dir_omni")), "hints.palette.extend"),
        ("Enter", "hints.palette.edit_hex"),
    ]
