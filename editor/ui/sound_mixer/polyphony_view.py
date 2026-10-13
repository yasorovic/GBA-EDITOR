"""ui/sound_mixer/polyphony_view.py — combien de canaux sonnent, à chaque instant du morceau.

Une courbe en escalier sous la forme d'onde, sur le MÊME axe de temps (les deux widgets prennent toute la largeur
de la colonne et partent du même PCM). Une ligne en pointillé marque le nombre de canaux logiciels du projet
(`mmInitDefault(bank, n)`) : ce qui dépasse est peint en rouge, car ces voix-là n'ont nulle part où sonner.

C'est le nombre de canaux QUI SONNENT dans l'émulation — un canal dont le volume est tombé à zéro compte pour
rien. La console, elle, garde une voie tant que son échantillon n'est pas fini : la courbe est un plancher, pas
une simulation du vol de voix de maxmod.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_render import ChannelLevels
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip

_HEIGHT = 60
_LABEL_BAND = 18         # hauteur (px) du bandeau du texte, en haut : les barres n'y montent pas


class PolyphonyView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_HEIGHT)
        self.setToolTip(tooltip(title=label("sndedit.poly_title"), body=label("sndedit.poly_tip")))
        self._runs: list = []              # (début, fin, canaux) en échantillons — un par palier de l'escalier
        self._total = 0                    # la longueur du PCM en échantillons
        self._mix_rate = 1
        self._ceiling = 0
        self._peak = 0
        self._playhead = -1.0

    def set_levels(self, levels: ChannelLevels | None, total: int, mix_rate: int, ceiling: int) -> None:
        """`total` : la longueur du PCM en échantillons ; `ceiling` : les canaux dont le projet dispose."""
        self._total, self._mix_rate, self._ceiling = int(total), max(1, int(mix_rate)), int(ceiling)
        self._runs, self._peak = [], 0
        if levels is not None and levels.starts.size and self._total > 0:
            counts = levels.active_counts()
            edges = np.flatnonzero(np.diff(counts)) + 1                  # là où le nombre de canaux change
            firsts = np.concatenate(([0], edges))
            lasts = np.concatenate((edges, [counts.size]))
            self._runs = [(int(levels.starts[a]), int(levels.starts[b]) if b < counts.size else self._total, int(counts[a]))
                          for a, b in zip(firsts, lasts)]
            self._peak = int(counts.max())
        self.update()

    def set_playhead(self, seconds: float) -> None:
        old, self._playhead = self._playhead, float(seconds)
        for value in (old, self._playhead):
            if value >= 0 and self._total:
                x = int(value * self._mix_rate / self._total * self.width())
                self.update(QRect(x - 3, 0, 7, self.height()))

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        if not self._runs:
            return
        scale = max(self._ceiling, self._peak, 1)
        unit = (h - _LABEL_BAND - 3) / scale                             # px par canal ; sous le bandeau du texte, 3 px de marge en bas
        base = h - 3.0
        ok, over = QColor(C.ACCENT), QColor(C.ACCENT_RED)
        ok.setAlpha(150); over.setAlpha(200)
        for start, end, count in self._runs:
            if count <= 0:
                continue
            x0, x1 = start / self._total * w, end / self._total * w
            within = min(count, self._ceiling) if self._ceiling else count
            p.fillRect(QRectF(x0, base - within * unit, max(1.0, x1 - x0), within * unit), ok)
            if count > within:
                p.fillRect(QRectF(x0, base - count * unit, max(1.0, x1 - x0), (count - within) * unit), over)
        if self._ceiling:
            y = base - self._ceiling * unit
            p.setPen(QPen(QColor(C.ACCENT_WARM), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, int(y), w, int(y))
        p.setFont(QFont(T.MONO, T.XS))
        p.setPen(QColor(C.TEXT_DIM))
        p.drawText(QRectF(8, 2, w - 16, _LABEL_BAND - 4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   label("sndedit.poly_peak", peak=self._peak, ceiling=self._ceiling))
        if self._playhead >= 0:
            x = self._playhead * self._mix_rate / self._total * w
            p.setPen(QPen(QColor(C.ACCENT_WARM), 1.5))
            p.drawLine(int(x), 0, int(x), h)
