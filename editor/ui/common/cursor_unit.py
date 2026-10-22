"""ui/common/cursor_unit.py : l'unité de la position du curseur, commune à tous les canvas (scène, fond, sprite).

Un clic sur l'affichage de la position bascule pixels <-> tuiles, partout à la fois, et le choix survit au redémarrage.
Une tuile fait 8 px. Le canvas donne toujours des pixels : la conversion se fait ici, au dernier moment.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QToolButton

from core import interface_preferences
from ui.common.labels import label
from ui.common.theme import C
from ui.common.tooltip import tooltip

TILE_PX = 8


class _CursorUnit(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._unit = interface_preferences.cursor_unit()

    @property
    def is_tile(self) -> bool:
        return self._unit == "tile"

    def toggle(self) -> None:
        self._unit = "px" if self.is_tile else "tile"
        interface_preferences.set_cursor_unit(self._unit)
        self.changed.emit()

    def text(self, x: int | None, y: int | None) -> str:
        """La position affichée : « x:12 y:34 » ou « tile 1,4 » ; « x:— y:— » hors du canvas."""
        if x is None or y is None:
            return "tile —" if self.is_tile else "x:— y:—"
        if self.is_tile:
            return label("sprframe.coord", c=x // TILE_PX, r=y // TILE_PX)
        return f"x:{x} y:{y}"


_UNIT = _CursorUnit()


def cursor_unit() -> _CursorUnit:
    return _UNIT


class CursorUnitButton(QToolButton):
    """L'affichage de la position du curseur : un bouton dont le clic bascule pixels <-> tuiles dans tous les canvas.
    `set_position(x, y)` prend des PIXELS du canvas, ou (None, None) hors du canvas."""

    def __init__(self, font, dim: str = C.TEXT_DIM, normal: str = C.TEXT_NORM, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setFont(font)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip(title=label("cvtop.cursor_unit_title"), body=label("cvtop.cursor_unit_tip")))
        self._colors = (dim, normal)
        self._position: tuple = (None, None)
        self.clicked.connect(_UNIT.toggle)
        _UNIT.changed.connect(self._render)
        self._render()

    def set_position(self, x: int | None, y: int | None) -> None:
        self._position = (x, y)
        self._render()

    def _render(self) -> None:
        x, y = self._position
        self.setText(_UNIT.text(x, y))
        self.setStyleSheet(f"QToolButton{{color:{self._colors[0] if x is None or y is None else self._colors[1]};"
                           "border:none;background:transparent;}")
        self.adjustSize()
