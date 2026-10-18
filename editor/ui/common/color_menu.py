"""Pastilles de couleur partagées par les menus d'organisation."""
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QToolButton, QWidget, QWidgetAction

from ui.common.disk_folder_colors import COLORS
from ui.common.labels import label
from ui.common.theme import C


def add_color_actions(menu: QMenu, current: str | None,
                      selected: Callable[[str | None], None]) -> None:
    """Ajoute les cinq couleurs et la remise à zéro, puis ferme au choix."""
    if not menu.isEmpty():
        menu.addSeparator()
    row = QWidget(menu)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 4, 10, 4)
    layout.setSpacing(5)

    def choose(color):
        selected(color)
        menu.close()

    for key, color in [("none", None), *COLORS.items()]:
        dot = QToolButton(row)
        dot.setFixedSize(18, 18)
        dot.setCursor(Qt.CursorShape.PointingHandCursor)
        dot.setToolTip(label(f"disk.folder_color_{key}"))
        dot.setText("×" if color is None else "")
        fill = color or "transparent"
        border = C.TEXT_HI if (current or None) == color else (C.BORDER_MID if color is None else color)
        text = C.TEXT_DIM if color is None else C.BG_DEEP
        dot.setStyleSheet(
            f"QToolButton{{background:{fill};color:{text};border:2px solid {border};border-radius:9px;"
            f"padding:0;font-size:12px;font-weight:700;}}"
            f"QToolButton:hover{{border-color:{C.TEXT_HI};}}")
        dot.clicked.connect(lambda _=False, c=color: choose(c))
        layout.addWidget(dot)
    action = QWidgetAction(menu)
    action.setDefaultWidget(row)
    menu.addAction(action)
