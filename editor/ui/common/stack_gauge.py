"""
ui/common/stack_gauge.py — jauge en forme de pile, pour l'IWRAM.

Une pile de tranches couchée sur le côté, qui se remplit depuis la gauche ;
chaque tranche garde SA couleur selon son rang, du vert (gauche) au rouge
(droite), comme un vumètre. L'image est celle de la mémoire : les données
statiques montent depuis le bas de l'IWRAM, la pile du programme descend depuis le
haut — la tranche rouge est la zone où elles se rejoignent.

Les teintes sont propres à ce widget (même exception que `rom_budget_bar` : ici
la teinte est la SEULE chose qui distingue une tranche de sa voisine, et le thème
n'a plus de vert d'état — le vert POWER est réservé aux signaux « live »).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCore import Qt

from ui.common.theme import C

_SLABS = 6
_SLAB_W = 6
_GAP = 1
_HEIGHT = 10

_GREEN = "#2e8b3e" if C.IS_LIGHT else "#5fbf6a"


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t))


def slab_color(index: int) -> QColor:
    """Couleur de la tranche `index` (0 = gauche) : vert → jaune → rouge."""
    t = index / max(1, _SLABS - 1)
    if t < 0.5:
        return _mix(_GREEN, C.ACCENT_YLW, t * 2)
    return _mix(C.ACCENT_YLW, C.ACCENT_RED, (t - 0.5) * 2)


class StackGauge(QWidget):
    """`set_ratio(None)` = inconnu : toutes les tranches éteintes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_SLABS * _SLAB_W + (_SLABS - 1) * _GAP, _HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._ratio: float | None = None

    def lit_slabs(self) -> int:
        """Tranches allumées : toute fraction entamée en allume une, pour qu'un
        remplissage non nul ne s'affiche jamais comme une pile vide."""
        if self._ratio is None or self._ratio <= 0:
            return 0
        return min(_SLABS, int(self._ratio * _SLABS) + 1)

    def set_ratio(self, ratio: float | None):
        self._ratio = ratio
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        lit = self.lit_slabs()
        for i in range(_SLABS):
            x = i * (_SLAB_W + _GAP)
            p.setBrush(slab_color(i) if i < lit else QColor(C.BORDER_MID))
            p.drawRect(x, 0, _SLAB_W, self.height())
        p.end()
