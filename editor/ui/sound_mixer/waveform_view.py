"""ui/sound_mixer/waveform_view.py — la forme d'onde d'une musique, telle que le deck la jouera.

On dessine le PCM du `Track` (cf. box_playback.track_for), pas le fichier source : un WAV y paraît
mono, au taux et à la quantification que la ROM portera, un module tel que le rend l'émulation. Ce
qu'on voit est ce qu'on entend.

Deux usages, un seul dessin :
  - un module : des BANDES colorées (les sections, en secondes) posées derrière l'onde, en lecture
    seule — c'est la bande des ordres qui se règle ;
  - un WAV : la boucle, à deux POIGNÉES qu'on glisse. Les valeurs sont des millisecondes, l'unité
    d'un WAV dans le sidecar (cf. models/audio.UNIT_MS).
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ui.common.theme import C, T

_BINS = 1600            # crêtes gardées : au-delà, un écran n'a pas de pixel de plus
_RULER = 20             # hauteur de la règle des temps
_GRAB = 7               # distance (px) à laquelle une poignée se saisit
_MIN_LOOP_MS = 50       # la boucle d'un WAV ne peut pas être plus courte (cf. wav_module)
_STEPS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600)


class WaveformView(QWidget):
    loop_moving = pyqtSignal(int, int)      # (début, fin) en ms, pendant le glisser
    loop_changed = pyqtSignal(int, int)     # idem, au relâchement : c'est lui qui écrit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(118)
        self.setMouseTracking(True)
        self._peaks = np.zeros((0, 2), dtype=np.float32)    # (min, max) par colonne
        self._seconds = 0.0
        self._bands: list = []                              # (début s, fin s, QColor)
        self._loop: tuple | None = None                     # (début ms, fin ms)
        self._editable = False
        self._playhead = -1.0
        self._drag: str | None = None

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def set_track(self, pcm: np.ndarray, mix_rate: int) -> None:
        """Garde les crêtes de `pcm` (stéréo int16) : un (min, max) par colonne de `_BINS`."""
        n = int(pcm.shape[0]) if pcm.ndim else 0
        if n == 0 or mix_rate <= 0:
            self._peaks, self._seconds = np.zeros((0, 2), dtype=np.float32), 0.0
            self.update()
            return
        mono = pcm.astype(np.float32).mean(axis=1) / 32768.0
        bins = min(_BINS, n)
        edges = np.linspace(0, n, bins + 1).astype(int)[:-1]
        self._peaks = np.stack([np.minimum.reduceat(mono, edges),
                                np.maximum.reduceat(mono, edges)], axis=1)
        self._seconds = n / mix_rate
        self.update()

    def set_bands(self, bands: list) -> None:
        self._bands = list(bands)
        self.update()

    def set_loop_ms(self, loop: tuple | None) -> None:
        self._loop = None if loop is None else (int(loop[0]), int(loop[1]))
        self.update()

    def set_editable(self, editable: bool) -> None:
        self._editable = bool(editable)
        self.update()

    def set_playhead(self, seconds: float) -> None:
        self._playhead = float(seconds)
        self.update()

    @property
    def seconds(self) -> float:
        return self._seconds

    # ── Géométrie ─────────────────────────────────────────────────

    def _x_of(self, seconds: float) -> float:
        return seconds / self._seconds * self.width() if self._seconds > 0 else 0.0

    def _seconds_of(self, x: float) -> float:
        return max(0.0, min(self._seconds, x / max(1, self.width()) * self._seconds))

    def _handle_at(self, x: float) -> str | None:
        if not (self._editable and self._loop and self._seconds > 0):
            return None
        start_x, end_x = (self._x_of(ms / 1000) for ms in self._loop)
        if abs(x - start_x) <= _GRAB and abs(x - start_x) <= abs(x - end_x):
            return "start"
        return "end" if abs(x - end_x) <= _GRAB else None

    # ── La souris ─────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = self._handle_at(e.position().x())

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._handle_at(x)
                           else Qt.CursorShape.ArrowCursor)
            return
        ms = round(self._seconds_of(x) * 1000)
        start, end = self._loop
        if self._drag == "start":
            start = max(0, min(ms, end - _MIN_LOOP_MS))
        else:
            end = min(round(self._seconds * 1000), max(ms, start + _MIN_LOOP_MS))
        self._loop = (start, end)
        self.loop_moving.emit(start, end)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.loop_changed.emit(*self._loop)

    # ── Le dessin ─────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        w, h = self.width(), self.height()
        plot = QRectF(0, _RULER, w, h - _RULER)
        self._paint_ruler(p, w)
        if self._seconds <= 0 or not len(self._peaks):
            return
        for start, end, color in self._bands:
            band = QColor(color); band.setAlpha(46)
            p.fillRect(QRectF(self._x_of(start), plot.top(), self._x_of(end) - self._x_of(start),
                              plot.height()), band)
        if self._loop:
            region = QColor(C.ACCENT_COOL); region.setAlpha(34)
            lo, hi = (self._x_of(ms / 1000) for ms in self._loop)
            p.fillRect(QRectF(lo, plot.top(), hi - lo, plot.height()), region)
        self._paint_wave(p, plot)
        if self._loop:
            self._paint_loop(p, plot)
        if self._playhead >= 0:
            x = self._x_of(self._playhead)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 1.5))
            p.drawLine(QPointF(x, 0), QPointF(x, h))

    def _paint_ruler(self, p: QPainter, w: int) -> None:
        p.setPen(QPen(QColor(C.BORDER)))
        p.drawLine(0, _RULER - 1, w, _RULER - 1)
        if self._seconds <= 0:
            return
        step = next((s for s in _STEPS if self._x_of(s) >= 78), _STEPS[-1])
        p.setFont(QFont(T.MONO, T.XS))
        t = 0
        while t <= self._seconds:
            x = self._x_of(t)
            p.setPen(QPen(QColor(C.BORDER_MID)))
            p.drawLine(QPointF(x, _RULER - 6), QPointF(x, _RULER - 1))
            p.setPen(QPen(QColor(C.TEXT_DIM)))
            p.drawText(QPointF(x + 4, _RULER - 7), f"{t // 60}:{t % 60:02d}")
            t += step

    def _paint_wave(self, p: QPainter, plot: QRectF) -> None:
        mid = plot.center().y()
        half = plot.height() / 2 - 3
        inside = QColor(C.ACCENT_COOL)
        outside = QColor(C.ACCENT_COOL); outside.setAlpha(120 if self._loop else 255)
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawLine(QPointF(0, mid), QPointF(plot.width(), mid))
        n, w = len(self._peaks), plot.width()
        lo, hi = ((self._x_of(ms / 1000) for ms in self._loop) if self._loop else (0, 0))
        for x in range(int(w)):
            lo_v, hi_v = self._peaks[min(n - 1, int(x / w * n))]
            p.setPen(QPen(inside if lo <= x <= hi else outside))
            p.drawLine(QPointF(x, mid - hi_v * half), QPointF(x, mid - lo_v * half - 1))

    def _paint_loop(self, p: QPainter, plot: QRectF) -> None:
        for ms in self._loop:
            x = self._x_of(ms / 1000)
            p.setPen(QPen(QColor(C.ACCENT_COOL), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if self._editable:
                p.fillRect(QRectF(x - 4, plot.top(), 8, 8), QColor(C.ACCENT_COOL))
