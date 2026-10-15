"""ui/sound_mixer/channel_meters.py — une barre verticale par canal, qui se remplit quand le canal sonne.

Les barres lisent le pic de chaque canal au tick où se trouve la tête de lecture (cf. `ChannelLevels`) : arrêtée,
la jauge est vide ; en lecture, elle monte d'un coup et retombe doucement, comme un vumètre.

Le pic du rendu n'a pas le volume de la musique : le lecteur l'applique en jouant, comme `mmSetModuleVolume`. Les
barres le multiplient (`set_gain`), pour montrer ce que chaque canal fait réellement entendre.

Il y a une barre par canal de la SOURCE (un module à 4 voies en montre 4, un effet — une seule voix — en montre une) ;
le plafond du projet (`mmInitDefault(bank, n)`) ne fait pas ajouter de barres, il fait peindre en rouge celles qui le
dépassent — ces voix-là n'ont nulle part où sonner. La place qui reste est dite par la courbe de polyphonie.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.engine_emulation.module_render import ChannelLevels
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip

_BAR = 24               # largeur d'une barre (px)
_GAP = 6                # espace entre deux barres (px)
_PAD = 6                # marge autour des barres (px)
_NAME = 16              # hauteur (px) de la ligne où le numéro du canal est écrit sous sa barre
_FULL = 0.8             # le pic d'un canal à plein volume : la barre est pleine à ce niveau
_FALL = 0.82            # ce qui reste de la hauteur à chaque mise à jour quand le canal se tait
_PEAK_FALL = 0.94       # le repère de crête reste brièvement visible


class ChannelMeters(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip(tooltip(title=label("sndedit.meters_title"), body=label("sndedit.meters_tip")))
        self._levels: ChannelLevels | None = None
        self._mix_rate = 1
        self._ceiling = 0
        self._shown = np.zeros(0, dtype=np.float32)      # la hauteur affichée de chaque barre, 0..1
        self._peaks = np.zeros(0, dtype=np.float32)       # crête retenue, pour lire les attaques très courtes
        self._count = 0
        self._gain = 1.0                                  # le volume de la musique, 0..1
        self._apply_width()

    def set_gain(self, gain: float) -> None:
        """Le volume de la musique change : les barres suivent à la prochaine position de la tête de lecture."""
        self._gain = max(0.0, min(1.0, float(gain)))

    def set_levels(self, levels: ChannelLevels | None, mix_rate: int, ceiling: int) -> None:
        self._levels, self._mix_rate, self._ceiling = levels, max(1, int(mix_rate)), int(ceiling)
        self._count = 0 if levels is None else levels.channel_count
        self._shown = np.zeros(self._count, dtype=np.float32)
        self._peaks = np.zeros(self._count, dtype=np.float32)
        self._apply_width()
        self.update()

    def set_playhead(self, seconds: float) -> None:
        """La tête de lecture a bougé : chaque barre prend le pic de son canal à ce tick, ou retombe."""
        target = np.zeros(self._count, dtype=np.float32)
        levels = self._levels
        if levels is not None and seconds >= 0 and levels.starts.size:
            tick = int(np.searchsorted(levels.starts, int(seconds * self._mix_rate), side="right")) - 1
            if 0 <= tick < levels.starts.size:
                target[:levels.channel_count] = np.minimum(1.0, levels.peaks[tick] * self._gain / _FULL)
        self._shown = np.where(target >= self._shown, target, self._shown * _FALL).astype(np.float32)
        self._peaks = np.maximum(target, self._peaks * _PEAK_FALL).astype(np.float32)
        self.update()

    def _apply_width(self) -> None:
        self.setFixedWidth(2 * _PAD + max(1, self._count) * _BAR + max(0, self._count - 1) * _GAP)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top, bottom = _PAD, self.height() - _PAD - _NAME
        span = max(1, bottom - top)
        p.setFont(QFont(T.MONO, T.XS))
        for index in range(self._count):
            x = _PAD + index * (_BAR + _GAP)
            cell = QRectF(x, top, _BAR, span)
            beyond = bool(self._ceiling) and index >= self._ceiling
            border = QColor(C.ACCENT_RED if beyond else C.BORDER_MID)
            rail = cell.adjusted(1, 1, -1, -1)
            p.setPen(QPen(border, 1))
            p.setBrush(QColor(C.BG_DEEP))
            p.drawRoundedRect(rail, 2, 2)

            # Trois repères rendent le niveau lisible sans ajouter d'échelle
            # ou de texte : bas, moitié et proche de la saturation.
            tick = QColor(C.ACCENT_RED if beyond else C.BORDER)
            for fraction in (0.25, 0.5, 0.75):
                y = bottom - fraction * span
                p.setPen(QPen(tick, 1))
                p.drawLine(int(rail.left() + 3), int(y), int(rail.right() - 3), int(y))

            height = float(self._shown[index]) * span
            if height >= 1.0:
                fill_rect = QRectF(rail.left() + 2, bottom - height + 1, rail.width() - 3, height - 2)
                gradient = QLinearGradient(fill_rect.bottomLeft(), fill_rect.topLeft())
                if beyond:
                    gradient.setColorAt(0.0, QColor(C.ACCENT_RED))
                    gradient.setColorAt(1.0, QColor(C.ACCENT_WARM))
                else:
                    gradient.setColorAt(0.0, QColor(C.ACCENT_COOL))
                    gradient.setColorAt(1.0, QColor(C.ACCENT))
                p.fillRect(fill_rect, QBrush(gradient))

            # Une fine crête, même après une attaque qui a déjà commencé à
            # retomber : c'est elle qui rend les barres exploitables en lecture.
            peak = float(self._peaks[index]) * span
            if peak >= 1.0:
                y = bottom - peak
                p.setPen(QPen(QColor(C.ACCENT_RED if beyond else C.TEXT_HI), 1.5))
                p.drawLine(int(rail.left() + 2), int(y), int(rail.right() - 2), int(y))

            # Un module ne porte pas de nom de canal : le numéro est ce que le tracker affiche en tête de colonne.
            p.setPen(QColor(C.ACCENT_RED if beyond else C.TEXT_NORM))
            p.drawText(QRectF(x - _GAP / 2, bottom + 2, _BAR + _GAP, _NAME), Qt.AlignmentFlag.AlignCenter, str(index + 1))
