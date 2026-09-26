"""ui/sprite_editor/direction_widget.py — sélecteur de directions 3×3 pour une AnimState."""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QToolButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.common.theme import C, T, tint
from ui.common.direction_grid import DirectionGrid
from core.models.sprite import AnimState
from core.models.sprite import resolve_direction_mirrors


class DirectionWidget(QWidget):
    """
    Grille 3×3 de directions + boutons H-Mirror / V-Mirror.
    Émet directions_changed(active_dirs, h_mirror, v_mirror).
    """

    directions_changed = pyqtSignal(list, bool, bool)  # [dir_id], h_mirror, v_mirror

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocking = False
        self._h_mirror = False
        self._v_mirror = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Grille 3×3 partagée (ui/common/direction_grid.py)
        self._grid = DirectionGrid()
        self._grid.dir_toggled.connect(self._on_dir_toggled)
        self._dir_btns = self._grid.buttons
        root.addWidget(self._grid, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Boutons H / V mirror
        _MIRROR_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;"
            f"font-family:{T.UI_STACK};font-size:{T.XS}px;padding:4px 8px;}}"
            f"QToolButton:checked{{color:{C.ACCENT_COOL};border-color:{C.ACCENT_COOL};"
            f"background:{tint(C.ACCENT_COOL, 0.18)};}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )

        mirror_row = QHBoxLayout()
        mirror_row.setSpacing(4)
        mirror_row.setContentsMargins(0, 0, 0, 0)

        from ui.common.icons import get as _ico

        self._btn_h = QToolButton(); self._btn_h.setText(label('dirwidget.h_mirror'))
        self._btn_h.setIcon(_ico("mirror_h", C.TEXT_DIM, C.ACCENT_COOL))
        self._btn_h.setIconSize(QSize(16, 16))
        self._btn_h.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_h.setCheckable(True); self._btn_h.setStyleSheet(_MIRROR_BTN)
        self._btn_h.setFixedHeight(28)
        self._btn_h.setToolTip(label('dirwidget.mirror_h_tip'))
        self._btn_h.toggled.connect(self._on_h_mirror)

        self._btn_v = QToolButton(); self._btn_v.setText(label('dirwidget.v_mirror'))
        self._btn_v.setIcon(_ico("mirror_v", C.TEXT_DIM, C.ACCENT_COOL))
        self._btn_v.setIconSize(QSize(16, 16))
        self._btn_v.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_v.setCheckable(True); self._btn_v.setStyleSheet(_MIRROR_BTN)
        self._btn_v.setFixedHeight(28)
        self._btn_v.setToolTip(label('dirwidget.mirror_v_tip'))
        self._btn_v.toggled.connect(self._on_v_mirror)

        mirror_row.addWidget(self._btn_h, 1)
        mirror_row.addWidget(self._btn_v, 1)
        root.addLayout(mirror_row)

    def load(self, state: AnimState):
        """Charge la configuration de directions depuis un AnimState."""
        self._blocking = True
        active = {sd.dir for sd in state.directions}
        mirrored = {sd.dir for sd in state.directions if sd.mirror_of is not None}
        h_mirror = any(sd.mirror_of is not None and sd.flip_h for sd in state.directions)
        v_mirror = any(sd.mirror_of is not None and sd.flip_v for sd in state.directions)

        for dir_id, btn in self._dir_btns.items():
            btn.setChecked(dir_id in active)
            btn.set_mirrored(dir_id in mirrored)

        self._btn_h.setChecked(h_mirror)
        self._btn_v.setChecked(v_mirror)
        self._h_mirror = h_mirror
        self._v_mirror = v_mirror
        self._blocking = False

    def _on_dir_toggled(self, dir_id: int, checked: bool):
        if self._blocking:
            return
        self._update_mirrors()
        self._emit()

    def _on_h_mirror(self, checked: bool):
        if self._blocking:
            return
        self._h_mirror = checked
        self._update_mirrors()
        self._emit()

    def _on_v_mirror(self, checked: bool):
        if self._blocking:
            return
        self._v_mirror = checked
        self._update_mirrors()
        self._emit()

    def _update_mirrors(self):
        """Met à jour l'apparence des boutons miroirs selon l'état H/V."""
        self._blocking = True
        active = {d for d, btn in self._dir_btns.items() if btn.isChecked()}
        mirrors = resolve_direction_mirrors(active, self._h_mirror, self._v_mirror)

        for dst in mirrors:
            self._dir_btns[dst].setChecked(True)
        for dir_id, btn in self._dir_btns.items():
            btn.set_mirrored(dir_id in mirrors)

        self._blocking = False

    def _emit(self):
        active = [d for d, btn in self._dir_btns.items() if btn.isChecked()]
        self.directions_changed.emit(active, self._h_mirror, self._v_mirror)


