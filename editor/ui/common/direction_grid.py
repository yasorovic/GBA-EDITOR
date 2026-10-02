"""ui/common/direction_grid.py — grille 3×3 de directions, partagée Sprite Editor / inspecteurs.

Un seul widget de direction dans tout l'éditeur : mêmes icônes, mêmes couleurs,
même géométrie. Deux usages :
  - `DirectionGrid`      : grille brute, multi-sélection (Sprite Editor, AnimState)
  - `DirectionPicker`    : grille exclusive exposée en vecteur (dir_x, dir_y)
                           (Transform des Actors / Prefabs)

Les dir_id suivent la nomenclature du runtime (`runtime_api_inline.h`) :
    8 1 2
    7 0 3      0 = omni / aucune direction
    6 5 4
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from PyQt6.QtWidgets import QWidget, QGridLayout, QToolButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.common.theme import C, tint
from ui.common.icons import get as _ico

# (dir_id, icon_key, tooltip, row, col)
DIR_CELLS = [
    (8, "dir_nw", "NW", 0, 0), (1, "dir_n", "N",  0, 1), (2, "dir_ne", "NE", 0, 2),
    (7, "dir_w",  "W",  1, 0), (0, "dir_omni", 'dirgrid.omni_all_directions', 1, 1), (3, "dir_e", "E", 1, 2),
    (6, "dir_sw", "SW", 2, 0), (5, "dir_s", "S",  2, 1), (4, "dir_se", "SE", 2, 2),
]

# dir_id → (dir_x, dir_y) — identique au LUT du runtime
DIR_VECTORS: dict[int, tuple[int, int]] = {
    0: (0, 0),  1: (0, -1), 2: (1, -1), 3: (1, 0), 4: (1, 1),
    5: (0, 1),  6: (-1, 1), 7: (-1, 0), 8: (-1, -1),
}
VECTOR_DIRS: dict[tuple[int, int], int] = {v: k for k, v in DIR_VECTORS.items()}

DEFAULT_CELL = 44   # pixels, carré — taille utilisée par le Sprite Editor
DEFAULT_GAP = 4


def _styles(radius: int) -> tuple[str, str, str]:
    """(normal, mirrored, omni) — stylesheets paramétrés par le rayon des coins."""
    normal = (
        f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
        f"border:1px solid {C.BORDER};border-radius:{radius}px;padding:0;}}"
        f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};"
        f"border-color:{C.BORDER_MID};}}"
        f"QToolButton:checked{{color:{C.ACCENT};border:2px solid {C.ACCENT};"
        f"background:{C.BG_SEL};}}"
    )
    mirrored = (
        f"QToolButton{{color:{C.ACCENT_COOL};background:{tint(C.ACCENT_COOL, 0.08)};"
        f"border:1px dashed {tint(C.ACCENT_COOL, 0.45)};border-radius:{radius}px;padding:0;}}"
        f"QToolButton:checked{{color:{C.ACCENT_COOL};border:2px dashed {C.ACCENT_COOL};"
        f"background:{tint(C.ACCENT_COOL, 0.18)};}}"
    )
    omni = (
        f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_DEEP};"
        f"border:1px solid {C.BORDER_DARK};border-radius:{radius}px;padding:0;}}"
        f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        f"QToolButton:checked{{color:{C.ACCENT};border:2px solid {C.ACCENT};"
        f"background:{C.BG_SEL};}}"
    )
    return normal, mirrored, omni


class DirectionButton(QToolButton):
    """Bouton d'une cellule de la grille — icône flèche (ui/common/icons.py), carré fixe."""

    def __init__(self, dir_id: int, icon_key: str, tooltip: str,
                 cell: int = DEFAULT_CELL, icon_px: int | None = None, parent=None):
        super().__init__(parent)
        self.dir_id = dir_id
        self._icon_key = icon_key
        self._is_omni = (dir_id == 0)
        self._sty_normal, self._sty_mirrored, self._sty_omni = _styles(max(2, cell // 8))
        self.setCheckable(True)
        self.setFixedSize(cell, cell)
        px = icon_px if icon_px else max(10, int(cell * 0.45))
        self.setIconSize(QSize(px, px))
        self.setToolTip(tooltip)
        self.set_mirrored(False)

    def set_mirrored(self, mirrored: bool):
        if self._is_omni:
            self.setStyleSheet(self._sty_omni)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT))
        elif mirrored:
            self.setStyleSheet(self._sty_mirrored)
            self.setIcon(_ico(self._icon_key, tint(C.ACCENT_COOL, 0.6), C.ACCENT_COOL))
        else:
            self.setStyleSheet(self._sty_normal)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT))


class DirectionGrid(QWidget):
    """
    Grille 3×3 de `DirectionButton`, taille fixe (vrai carré).

    `exclusive=True` → une seule direction active à la fois, impossible de
    tout désélectionner (comportement d'un radio group).
    """

    dir_toggled = pyqtSignal(int, bool)   # dir_id, checked

    def __init__(self, cell: int = DEFAULT_CELL, gap: int = DEFAULT_GAP,
                 icon_px: int | None = None, exclusive: bool = False, parent=None):
        super().__init__(parent)
        self._exclusive = exclusive
        self._blocking = False

        side = cell * 3 + gap * 2
        self.setFixedSize(side, side)
        self.setStyleSheet("background:transparent;")

        grid = QGridLayout(self)
        grid.setSpacing(gap)
        grid.setContentsMargins(0, 0, 0, 0)
        for i in range(3):
            grid.setColumnMinimumWidth(i, cell)
            grid.setRowMinimumHeight(i, cell)

        self.buttons: dict[int, DirectionButton] = {}
        for dir_id, icon_key, tip, row, col in DIR_CELLS:
            btn = DirectionButton(dir_id, icon_key, label(tip), cell=cell, icon_px=icon_px)
            btn.toggled.connect(lambda checked, d=dir_id: self._on_toggled(d, checked))
            grid.addWidget(btn, row, col)
            self.buttons[dir_id] = btn

    # ── état ──────────────────────────────────────────────────────
    def checked_dirs(self) -> list[int]:
        return [d for d, b in self.buttons.items() if b.isChecked()]

    def set_checked_dirs(self, dirs, *, silent: bool = True):
        """Coche exactement `dirs` (sans émettre par défaut)."""
        prev, self._blocking = self._blocking, (self._blocking or silent)
        wanted = set(dirs)
        for d, b in self.buttons.items():
            b.setChecked(d in wanted)
        self._blocking = prev

    def set_mirrored_dirs(self, dirs):
        mirrored = set(dirs)
        for d, b in self.buttons.items():
            b.set_mirrored(d in mirrored)

    # ── interne ───────────────────────────────────────────────────
    def _on_toggled(self, dir_id: int, checked: bool):
        if self._blocking:
            return
        if self._exclusive:
            if not checked:
                # pas de désélection : on rétablit
                self._blocking = True
                self.buttons[dir_id].setChecked(True)
                self._blocking = False
                return
            self._blocking = True
            for d, b in self.buttons.items():
                if d != dir_id:
                    b.setChecked(False)
            self._blocking = False
        self.dir_toggled.emit(dir_id, checked)


class DirectionPicker(QWidget):
    """
    Sélecteur d'une direction unique, exposée en vecteur (dir_x, dir_y) ∈ {-1,0,1}².

    Utilisé par le panneau Transform des Actors / Prefabs — (0,0) = omni.
    """

    changed = pyqtSignal(int, int)   # dir_x, dir_y

    def __init__(self, cell: int = 24, gap: int = 3, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout

        self._grid = DirectionGrid(cell=cell, gap=gap, exclusive=True)
        self._grid.buttons[0].setToolTip(
            tooltip(title=label('dirgrid.omni_no_initial_direction')))
        self._grid.dir_toggled.connect(self._on_dir)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._grid, alignment=Qt.AlignmentFlag.AlignLeft)
        self.setFixedSize(self._grid.width(), self._grid.height())

        self.set_direction(0, 0)

    def set_direction(self, dx: int, dy: int):
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        self._grid.set_checked_dirs([VECTOR_DIRS[(dx, dy)]])

    def direction(self) -> tuple[int, int]:
        checked = self._grid.checked_dirs()
        return DIR_VECTORS[checked[0]] if checked else (0, 0)

    def _on_dir(self, dir_id: int, checked: bool):
        if not checked:
            return
        dx, dy = DIR_VECTORS[dir_id]
        self.changed.emit(dx, dy)
