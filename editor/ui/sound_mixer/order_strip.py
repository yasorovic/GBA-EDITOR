"""ui/sound_mixer/order_strip.py — la table d'ordres d'un module, avec ses sections.

Une cellule par POSITION de la table BRUTE — celle que la ROM numérote (cf.
engine_emulation/module_model.ORDER_SKIP) — et non par pattern : une section vise une position, et
c'est ce numéro-là que l'auteur lit ici et qui sort au build. Un séparateur ou une fin (`254` / `255`)
occupe sa cellule, grisée, et ne se sélectionne pas.

On y glisse pour choisir une plage ; un clic sur le nom d'une section la sélectionne en entier.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_model import is_pattern_order
from ui.common.theme import C, T
from ui.sound_mixer.section_colors import section_color

_RULER = 16
_BAND = 20
_CELL = 28


class OrderStrip(QWidget):
    selection_changed = pyqtSignal(int, int)     # [début, fin) ; (0, 0) = rien
    section_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_RULER + _BAND + _CELL + 8)
        self._table: list = []
        self._sections: list = []
        self._playhead = -1
        self._selection = (0, 0)
        self._anchor: int | None = None

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def set_orders(self, table: list) -> None:
        self._table = list(table)
        self._selection = (0, 0)
        self.update()

    def set_sections(self, sections: list) -> None:
        self._sections = list(sections)
        self.update()

    def set_playhead_order(self, order: int) -> None:
        if order != self._playhead:
            self._playhead = order
            self.update()

    def selection(self) -> tuple:
        return self._selection

    def clear_selection(self) -> None:
        self._set_selection(0, 0)

    def _set_selection(self, start: int, end: int) -> None:
        if (start, end) != self._selection:
            self._selection = (start, end)
            self.selection_changed.emit(start, end)
            self.update()

    # ── Géométrie ─────────────────────────────────────────────────

    def _cell_width(self) -> float:
        return (self.width() - 2) / len(self._table) if self._table else 0.0

    def _index_at(self, x: float) -> int:
        n = len(self._table)
        return max(0, min(n - 1, int((x - 1) / self._cell_width()))) if n else -1

    def _cell_rect(self, i: int) -> QRectF:
        cw = self._cell_width()
        return QRectF(1 + i * cw, _RULER + _BAND + 2, cw, _CELL)

    # ── La souris ─────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self._table:
            return
        i = self._index_at(e.position().x())
        if e.position().y() < _RULER + _BAND:                     # la bande des noms
            hit = next((s for s in reversed(self._sections) if s.start <= i < s.end), None)
            if hit is not None:
                self._set_selection(hit.start, min(hit.end, len(self._table)))
                self.section_clicked.emit(hit.name)
            return
        if not is_pattern_order(self._table[i]):
            return
        self._anchor = i
        self._set_selection(i, i + 1)

    def mouseMoveEvent(self, e):
        if self._anchor is None or not self._table:
            return
        i = self._index_at(e.position().x())
        lo, hi = min(self._anchor, i), max(self._anchor, i)
        self._set_selection(lo, hi + 1)

    def mouseReleaseEvent(self, _e):
        self._anchor = None

    # ── Le dessin ─────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        n = len(self._table)
        if not n:
            return
        cw = self._cell_width()
        p.setFont(QFont(T.MONO, T.XS))
        every = max(1, int(26 / cw) + (1 if cw < 26 else 0))      # une étiquette tous les `every`
        for i, entry in enumerate(self._table):
            rect = self._cell_rect(i)
            if i % every == 0:
                p.setPen(QPen(QColor(C.TEXT_DIM)))
                p.drawText(QPointF(rect.left() + 3, _RULER - 4), f"{i:02d}")
            self._paint_cell(p, rect, is_pattern_order(entry))
        for rank, section in enumerate(self._sections):
            self._paint_section(p, rank, section, n, cw)
        self._paint_selection_and_playhead(p)

    def _paint_cell(self, p: QPainter, rect: QRectF, is_pattern: bool) -> None:
        p.fillRect(rect.adjusted(0, 0, -1, 0), QColor(C.BG_INPUT if is_pattern else C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(rect.adjusted(0, 0, -1, 0))
        if not is_pattern:                                         # marqueur : hachuré
            p.drawLine(rect.bottomLeft(), rect.topRight())

    def _paint_section(self, p: QPainter, rank: int, section, n: int, cw: float) -> None:
        start, end = max(0, section.start), min(n, section.end)
        if end <= start:
            return
        color = section_color(section, rank)
        fill = QColor(color); fill.setAlpha(80)
        for i in range(start, end):
            p.fillRect(self._cell_rect(i).adjusted(1, 1, -2, -1), fill)
        band = QRectF(1 + start * cw, _RULER, (end - start) * cw - 1, _BAND - 2)
        solid = QColor(color); solid.setAlpha(60)
        p.fillRect(band, solid)
        p.setPen(QPen(color, 1))
        p.drawRect(band)
        p.setPen(QPen(QColor(C.TEXT_HI)))
        p.drawText(band.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(section.name, Qt.TextElideMode.ElideRight,
                                              max(0, int(band.width()) - 8)))

    def _paint_selection_and_playhead(self, p: QPainter) -> None:
        lo, hi = self._selection
        if hi > lo:
            first, last = self._cell_rect(lo), self._cell_rect(hi - 1)
            p.setPen(QPen(QColor(C.ACCENT), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(first.left(), first.top(), last.right() - first.left() - 1, _CELL))
        if 0 <= self._playhead < len(self._table):
            r = self._cell_rect(self._playhead)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 2))
            p.drawRect(r.adjusted(1, 1, -2, -1))
