"""ui/sound_mixer/section_colors.py — la couleur d'une section de boucle.

Une section porte sa couleur (`MusicSection.color`, « #RRGGBB »), choisie à sa création ; vide, elle
prend celle de son rang. Quatre composants la lisent — la forme d'onde, la bande des ordres, le
tableau et l'éditeur — d'où ce fichier plutôt qu'une copie dans chacun.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor

from ui.common.theme import C


def section_palette() -> list[str]:
    """Les couleurs proposées, dans l'ordre où on les attribue. Lues sur le thème À L'APPEL :
    le thème peut changer d'une session à l'autre, la couleur d'une section déjà écrite non."""
    return [C.ACCENT_COOL, C.AXIS_Z, C.ACCENT_WARM, C.SYNTAX_KEYWORD, C.ACCENT_RED, C.ACCENT_YLW]


def section_color(section, rank: int) -> QColor:
    """La couleur de cette section : la sienne, sinon celle de son RANG dans la musique."""
    if section.color:
        color = QColor(section.color)
        if color.isValid():
            return color
    palette = section_palette()
    return QColor(palette[rank % len(palette)])


def next_color(sections) -> str:
    """La couleur à donner à une section qu'on ajoute : la première de la palette que personne
    n'utilise, sinon on recommence le tour."""
    palette = section_palette()
    used = {s.color.lower() for s in sections if s.color}
    for color in palette:
        if color.lower() not in used:
            return color
    return palette[len(sections) % len(palette)]
