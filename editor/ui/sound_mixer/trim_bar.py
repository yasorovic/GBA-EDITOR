"""ui/sound_mixer/trim_bar.py — la barre qui rogne un WAV : le FICHIER entier en vignette, deux poignées, le reste estompé.

Une seule barre pour les trois familles de WAV (un effet, une musique, un jingle) : elle ne connaît ni l'asset ni l'écran,
seulement une durée, une enveloppe et une plage `(début, fin)` en millisecondes depuis le début du fichier — la convention de
`core/wav_edit.py`. Elle dit `moving` pendant le glisser et `changed` au relâchement ; c'est l'éditeur qui écrit le modèle.

Le geste : on saisit une poignée et on la glisse ; un double-clic remet le fichier entier. Une plage ne peut pas devenir plus
courte que `MIN_TRIM_MS`.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.wav_edit import MIN_TRIM_MS
from ui.common.theme import C

_HEIGHT = 38
_PAD = 8                  # la marge de chaque côté : une poignée à 0 ou à la fin reste entière à l'écran
_GRAB = 8                 # la distance (px) à laquelle une poignée se saisit
_HANDLE_W = 7
_GRIP_H = 18


class TrimBar(QWidget):
    moving = pyqtSignal(int, int)        # (début, fin) en ms, pendant le glisser
    changed = pyqtSignal(int, int)       # idem, au relâchement : c'est lui qu'on écrit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_HEIGHT)
        self.setMouseTracking(True)
        self._peaks = np.zeros((0, 2), dtype=np.float32)
        self._total = 0
        self._start = 0
        self._end = 0
        self._drag: str | None = None                  # « start » | « end » tant qu'une poignée est tenue

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def load(self, peaks: np.ndarray, total_ms: int, start: int, end: int) -> None:
        """Le fichier entier (`peaks` : crêtes min/max, cf. `waveform_view.peak_envelope`, `total_ms` : sa durée) et la plage
        gardée, sans rien émettre."""
        self._peaks, self._total = peaks, max(0, int(total_ms))
        self.set_window(start, end)

    def set_window(self, start: int, end: int) -> None:
        """Pose la plage gardée sans rien émettre. `end` à 0 ou au-delà du fichier : jusqu'au bout."""
        end = self._total if end <= 0 else min(int(end), self._total)
        start = max(0, min(int(start), max(0, end - MIN_TRIM_MS)))
        self._start, self._end = start, end
        self.update()

    @property
    def window(self) -> tuple[int, int]:
        return self._start, self._end

    # ── Le dessin ─────────────────────────────────────────────────

    def _x_of(self, ms: float) -> float:
        span = max(1, self.width() - 2 * _PAD)
        return _PAD + (ms / self._total if self._total else 0.0) * span

    def _ms_of(self, x: float) -> int:
        span = max(1, self.width() - 2 * _PAD)
        return round(min(1.0, max(0.0, (x - _PAD) / span)) * self._total)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        mid = self.height() / 2
        if self._total > 0 and len(self._peaks):
            self._paint_envelope(painter, mid)
            left, right = self._x_of(self._start), self._x_of(self._end)
            shade = QColor(0, 0, 0, 150)                              # ce qui est coupé reste visible, mais en retrait
            painter.fillRect(QRectF(0, 0, left, self.height()), shade)
            painter.fillRect(QRectF(right, 0, self.width() - right, self.height()), shade)
            for x in (left, right):
                self._paint_handle(painter, x)
        painter.setPen(QPen(QColor(C.BORDER_MID), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()

    def _paint_envelope(self, painter: QPainter, mid: float) -> None:
        width = max(1, self.width() - 2 * _PAD)
        bins = len(self._peaks)
        painter.setPen(QPen(QColor(C.ACCENT), 1))
        half = mid - 6
        for column in range(width):
            low, high = self._peaks[column * bins // width]
            painter.drawLine(QPointF(_PAD + column, mid - float(high) * half), QPointF(_PAD + column, mid - float(low) * half))

    def _paint_handle(self, painter: QPainter, x: float) -> None:
        painter.setPen(QPen(QColor(C.TEXT_HI), 1))
        painter.drawLine(QPointF(x, 1), QPointF(x, self.height() - 2))
        grip = QRectF(x - _HANDLE_W / 2, (self.height() - _GRIP_H) / 2, _HANDLE_W, _GRIP_H)
        painter.fillRect(grip, QColor(C.TEXT_NORM))
        painter.setPen(QPen(QColor(C.TEXT_HI), 1))
        painter.drawRect(grip)

    # ── Le geste ──────────────────────────────────────────────────

    def _handle_at(self, x: float) -> str | None:
        """La poignée sous `x`, la plus proche si les deux se chevauchent (plage très courte)."""
        near = [(abs(x - self._x_of(ms)), name) for name, ms in (("start", self._start), ("end", self._end))
                if abs(x - self._x_of(ms)) <= _GRAB]
        return min(near)[1] if near else None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._total > 0:
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
        ms = self._ms_of(x)
        if self._drag == "start":
            self._start = max(0, min(ms, self._end - MIN_TRIM_MS))
        else:
            self._end = min(self._total, max(ms, self._start + MIN_TRIM_MS))
        self.update()
        self.moving.emit(self._start, self._end)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.changed.emit(self._start, self._end)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Un double-clic remet le fichier entier."""
        if self._total > 0:
            self._start, self._end = 0, self._total
            self.update()
            self.changed.emit(self._start, self._end)
