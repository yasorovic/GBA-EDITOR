"""ui/sound_mixer/order_range_bar.py — la barre qui coupe un jingle en MODULE : sa table d'ordres, deux poignées, le reste estompé.

Le pendant de `TrimBar` pour un module, dont la plus petite unité est l'ORDRE et non la milliseconde : une cellule par entrée de la
table brute (marqueurs « +++ » / « --- » compris : ce sont les positions que `mmGetPosition()` rend), et des poignées qui ne se posent
qu'ENTRE deux cellules. Elle ne connaît ni l'asset ni l'écran, seulement une table et une plage `(début, fin)` en positions d'ordre,
fin exclue — la convention de `core/module_trim.py`. Elle dit `moving` pendant le glisser et `changed` au relâchement ; c'est
l'éditeur qui écrit le modèle.

Le geste est celui de `TrimBar` : on saisit une poignée et on la glisse ; un double-clic remet le module entier. Une plage garde au
moins un ordre.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_model import is_pattern_order
from ui.common.theme import C, T

_HEIGHT = 46
_PAD = 8
_GRAB = 8
_HANDLE_W = 7
_GRIP_H = 18
_GAP = 2                  # l'espace entre deux cellules


class OrderRangeBar(QWidget):
    moving = pyqtSignal(int, int)        # (début, fin) en positions d'ordre, pendant le glisser
    changed = pyqtSignal(int, int)       # idem, au relâchement : c'est lui qu'on écrit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_HEIGHT)
        self.setMouseTracking(True)
        self._entries: list = []
        self._start = 0
        self._end = 0
        self._drag: str | None = None

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def load(self, entries: list, start: int, end: int) -> None:
        """La table brute d'ordres du module et la plage jouée, sans rien émettre."""
        self._entries = list(entries)
        self.set_window(start, end)

    def set_window(self, start: int, end: int) -> None:
        """Pose la plage jouée sans rien émettre. `end` à 0 ou au-delà de la table : jusqu'au bout."""
        count = len(self._entries)
        end = count if end <= 0 else min(int(end), count)
        start = max(0, min(int(start), max(0, end - 1)))
        self._start, self._end = start, end
        self.update()

    @property
    def window(self) -> tuple[int, int]:
        return self._start, self._end

    # ── Le dessin ─────────────────────────────────────────────────

    def _x_of(self, boundary: float) -> float:
        span = max(1, self.width() - 2 * _PAD)
        return _PAD + (boundary / len(self._entries) if self._entries else 0.0) * span

    def _boundary_of(self, x: float) -> int:
        span = max(1, self.width() - 2 * _PAD)
        return round(min(1.0, max(0.0, (x - _PAD) / span)) * len(self._entries))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        if self._entries:
            self._paint_cells(painter)
            left, right = self._x_of(self._start), self._x_of(self._end)
            shade = QColor(0, 0, 0, 150)                              # ce qui est coupé reste visible, mais en retrait
            painter.fillRect(QRectF(0, 0, left, self.height()), shade)
            painter.fillRect(QRectF(right, 0, self.width() - right, self.height()), shade)
            for x in (left, right):
                self._paint_handle(painter, x)
        painter.setPen(QPen(QColor(C.BORDER_MID), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()

    def _paint_cells(self, painter: QPainter) -> None:
        painter.setFont(QFont(T.MONO, T.SM))
        top, height = 8, self.height() - 16
        for index, entry in enumerate(self._entries):
            left, right = self._x_of(index) + _GAP / 2, self._x_of(index + 1) - _GAP / 2
            cell = QRectF(left, top, max(1.0, right - left), height)
            is_pattern = is_pattern_order(entry)
            painter.fillRect(cell, QColor(C.ACCENT) if is_pattern else QColor(C.BORDER_MID))
            if cell.width() >= 22:                                    # un numéro lisible, ou rien : jamais un nombre rogné
                painter.setPen(QPen(QColor(C.BG_DEEP) if is_pattern else QColor(C.TEXT_DIM)))
                painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, f"{index:02d}")

    def _paint_handle(self, painter: QPainter, x: float) -> None:
        painter.setPen(QPen(QColor(C.TEXT_HI), 1))
        painter.drawLine(QPointF(x, 1), QPointF(x, self.height() - 2))
        grip = QRectF(x - _HANDLE_W / 2, (self.height() - _GRIP_H) / 2, _HANDLE_W, _GRIP_H)
        painter.fillRect(grip, QColor(C.TEXT_NORM))
        painter.setPen(QPen(QColor(C.TEXT_HI), 1))
        painter.drawRect(grip)

    # ── Le geste ──────────────────────────────────────────────────

    def _handle_at(self, x: float) -> str | None:
        near = [(abs(x - self._x_of(boundary)), name) for name, boundary in (("start", self._start), ("end", self._end))
                if abs(x - self._x_of(boundary)) <= _GRAB]
        return min(near)[1] if near else None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._entries:
            self._drag = self._handle_at(event.position().x())
            if self._drag is not None:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._handle_at(x) else Qt.CursorShape.ArrowCursor)
            return
        boundary = self._boundary_of(x)
        before = (self._start, self._end)
        if self._drag == "start":
            self._start = max(0, min(boundary, self._end - 1))
        else:
            self._end = min(len(self._entries), max(boundary, self._start + 1))
        if (self._start, self._end) != before:                       # un glisser qui reste dans la même cellule n'émet rien
            self.update()
            self.moving.emit(self._start, self._end)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.changed.emit(self._start, self._end)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Un double-clic remet le module entier."""
        if self._entries:
            self._start, self._end = 0, len(self._entries)
            self.update()
            self.changed.emit(self._start, self._end)
