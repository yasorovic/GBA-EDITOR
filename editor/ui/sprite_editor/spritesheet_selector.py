"""ui/sprite_editor/spritesheet_selector.py — le spritesheet : sélecteur de tuiles sur le PNG source."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu,
)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPixmap, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint

from ui.common.theme import C, T, QSS, ui_font
from ui.common.labels import label
from ui.common.cursor_unit import CursorUnitButton
from ui.common.tooltip import tooltip
from ui.common import external_editor

# ── Viewer du spritesheet source (tile picker) ─────────────────────────────────

class SpritesheetCanvas(QWidget):
    """Canvas interne du picker — grille 8×8, sélection multi-tiles, zoom, pan.

    Remplit toute la zone (comme SpriteCanvas) : zoom molette et pan clic molette
    marchent partout, y compris dans le vide autour de la planche.
    """

    selection_changed = pyqtSignal(list)
    hover_changed      = pyqtSignal(object)  # (col, row) survolé, ou None
    cursor_px_changed  = pyqtSignal(object)  # (x, y) en pixels de la planche survolée, ou None

    MAX_ZOOM = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap:    Optional[QPixmap]       = None
        self._zoom:      int                     = 2
        self._pan:       QPoint                  = QPoint(0, 0)
        self._drag_start: Optional[tuple]        = None
        self._drag_end:   Optional[tuple]        = None
        self._selection:  list[tuple[int, int]]  = []
        self._mid_drag:   Optional[tuple]        = None   # pan (start_pos, start_pan)
        self._hover:      Optional[tuple]        = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Focus au clic — même raison que SpriteCanvas : permet à Shift+X/Y
        # (portés par SpriteCenterPanel) de marcher après une sélection ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def load(self, path: Optional[Path]):
        self._pixmap = QPixmap(str(path)) if path and path.exists() else None
        self._selection = []
        self._drag_start = self._drag_end = None
        self._pan = QPoint(0, 0)
        self.update()

    def clear_selection(self):
        self._selection = []
        self._drag_start = self._drag_end = None
        self.update()
        self.selection_changed.emit([])

    def _origin(self) -> QPoint:
        """Coin haut-gauche de la planche dans le widget (centrée + pan)."""
        if not self._pixmap:
            return QPoint(0, 0)
        pw = self._pixmap.width()  * self._zoom
        ph = self._pixmap.height() * self._zoom
        return QPoint((self.width() - pw) // 2, (self.height() - ph) // 2) + self._pan

    def _tile_at(self, pos) -> tuple[int, int]:
        tpx = 8 * self._zoom
        o = self._origin()
        col = int((pos.x() - o.x()) // tpx)
        row = int((pos.y() - o.y()) // tpx)
        if self._pixmap:
            col = max(0, min(col, self._pixmap.width()  // 8 - 1))
            row = max(0, min(row, self._pixmap.height() // 8 - 1))
        return col, row

    def _pixel_at(self, pos) -> tuple[int, int]:
        o = self._origin()
        x = int((pos.x() - o.x()) // self._zoom)
        y = int((pos.y() - o.y()) // self._zoom)
        return max(0, min(x, self._pixmap.width() - 1)), max(0, min(y, self._pixmap.height() - 1))

    def _adjust_zoom(self, delta: int):
        self._zoom = max(1, min(self.MAX_ZOOM, self._zoom + delta))
        self.update()

    # ── Événements ────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = (e.pos(), QPoint(self._pan))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._pixmap or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_start = self._tile_at(e.position())
        self._drag_end = self._drag_start
        self._recompute_selection()

    def mouseMoveEvent(self, e):
        if self._mid_drag:
            start, pan0 = self._mid_drag
            self._pan = pan0 + (e.pos() - start)
            self.update()
            return
        if self._pixmap:
            cell = self._tile_at(e.position())
            if cell != self._hover:
                self._hover = cell
                self.hover_changed.emit(cell)
            self.cursor_px_changed.emit(self._pixel_at(e.position()))
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        self._drag_end = self._tile_at(e.position())
        self._recompute_selection()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if e.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_end = self._tile_at(e.position())
            self._recompute_selection()
            self._drag_start = None

    def leaveEvent(self, e):
        self.cursor_px_changed.emit(None)
        if self._hover is not None:
            self._hover = None
            self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._adjust_zoom(1 if delta > 0 else -1)
        e.accept()

    def _recompute_selection(self):
        if self._drag_start is None or self._drag_end is None:
            return
        c0, r0 = self._drag_start
        c1, r1 = self._drag_end
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        self._selection = [(c, r) for r in range(rmin, rmax + 1)
                           for c in range(cmin, cmax + 1)]
        self.update()
        self.selection_changed.emit(self._selection)

    @staticmethod
    def _checker_pattern(cs: int = 8) -> QPixmap:
        pm = QPixmap(cs * 2, cs * 2)
        pm.fill(QColor(C.CHECKER_A))
        p = QPainter(pm)
        p.fillRect(cs, 0, cs, cs, QColor(C.CHECKER_B))
        p.fillRect(0, cs, cs, cs, QColor(C.CHECKER_B))
        p.end()
        return pm

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor(C.TEXT_MUTED))
            painter.setFont(ui_font(T.LG))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             label("sprsheet.no_png"))
            painter.end()
            return

        pw = self._pixmap.width()  * self._zoom
        ph = self._pixmap.height() * self._zoom
        painter.translate(self._origin())
        # Damier sous la planche : sans lui, les pixels transparents se
        # confondent avec le fond du panneau.
        painter.fillRect(QRect(0, 0, pw, ph), QBrush(self._checker_pattern()))
        painter.drawPixmap(QRect(0, 0, pw, ph), self._pixmap)

        tpx = 8 * self._zoom
        painter.setPen(QPen(QColor(0, 200, 100, 60), 1))
        x = 0
        while x <= pw:
            painter.drawLine(x, 0, x, ph); x += tpx
        y = 0
        while y <= ph:
            painter.drawLine(0, y, pw, y); y += tpx

        for col, row in self._selection:
            r = QRect(col * tpx, row * tpx, tpx, tpx)
            painter.fillRect(r, QColor(155, 140, 255, 80))
            painter.setPen(QPen(QColor(C.ACCENT), 1))
            painter.drawRect(r)

        painter.end()


class SpritesheetSelector(QWidget):
    """Zone basse — spritesheet, picker multi-tiles, zoom, indicateur brosse."""

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header : titre + indicateur brosse + zoom
        hdr_w = QWidget()
        hdr_w.setFixedHeight(22)
        hdr_w.setStyleSheet(
            f"background:{C.BG_RAISED};border-bottom:1px solid {C.BORDER_DARK};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(8, 0, 4, 0)
        hdr_lay.setSpacing(4)

        lbl_title = QLabel(label("sprsheet.title"))
        lbl_title.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        lbl_title.setStyleSheet(QSS.title_panel)
        hdr_lay.addWidget(lbl_title)

        hdr_lay.addStretch()

        self._brush_lbl = QLabel(label("sprsheet.no_brush"))
        self._brush_lbl.setFont(QFont(T.UI, T.XS))
        self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._brush_lbl)

        hdr_lay.addSpacing(12)

        self._coord_lbl = CursorUnitButton(QFont(T.MONO, T.XS), dim=C.TEXT_MUTED, normal=C.TEXT_MUTED)
        hdr_lay.addWidget(self._coord_lbl)

        root.addWidget(hdr_w)

        self._canvas = SpritesheetCanvas()
        self._canvas.selection_changed.connect(self.selection_changed)
        self._canvas.cursor_px_changed.connect(self._on_cursor_px)
        root.addWidget(self._canvas, 1)

        # Éditer le PNG source dans un logiciel externe — bouton texte en
        # surimpression du canvas (cf. ui/common/external_editor.py) : ce
        # viewer sert au découpage/à la sélection de tuiles, pas au dessin.
        self._path: Optional[Path] = None
        self._btn_edit = QPushButton(label("sprsheet.edit"), self)
        self._btn_edit.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_DIM};background:{C.BG_RAISED};"
            f"border:1px solid {C.BORDER_DARK};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED};}}"
        )
        self._btn_edit.setToolTip(tooltip(
            title=label("sprsheet.edit"), body=label("sprsheet.edit_tip")
        ))
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit_image)
        self._btn_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_edit.customContextMenuRequested.connect(self._on_edit_menu)
        self._btn_edit.adjustSize()
        self._btn_edit.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._btn_edit.move((self.width() - self._btn_edit.width()) // 2, 22 + 8)
        self._btn_edit.raise_()

    def _on_cursor_px(self, px):
        self._coord_lbl.set_position(*(px or (None, None)))

    def load(self, path: Optional[Path]):
        self._path = path
        self._btn_edit.setEnabled(bool(path and path.exists()))
        self._canvas.load(path)

    def _on_edit_image(self):
        if self._path is not None:
            external_editor.open_image(self._path, self)

    def _on_edit_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        cur = external_editor.get_configured_editor()
        act_choose = menu.addAction(label("common.choose_editor"))
        act_default = menu.addAction(label("common.use_default"))
        act_default.setEnabled(bool(cur))
        chosen = menu.exec(self._btn_edit.mapToGlobal(pos))
        if chosen == act_choose:
            external_editor.choose_editor(self)
        elif chosen == act_default:
            external_editor.use_system_default()

    def clear_selection(self):
        self._canvas.clear_selection()
        self.set_brush_label(0)

    def set_brush_label(self, n: int):
        if n == 0:
            self._brush_lbl.setText(label("sprsheet.no_brush"))
            self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        else:
            self._brush_lbl.setText(label("sprsheet.brush", n=n))
            self._brush_lbl.setStyleSheet(f"color:{C.ACCENT};background:transparent;")
