"""editor/ui/common/palette_swatch.py — Icône QIcon générée depuis une PaletteBank.

Partagé entre l'écran Palette Editor et les widgets de sélection de palette
(ScriptSlot/AssetPickerPopup réutilisés en picker de palette).
"""
from __future__ import annotations

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPolygon
from PyQt6.QtCore import Qt, QPoint

from ui.common.theme import C
from core.models.palette import PaletteBank
from core.models.gba_color import bgr555_to_rgb888


def _qcolor(v: int) -> QColor:
    r, g, b = bgr555_to_rgb888(v)
    return QColor(r, g, b)


def _sample_stops(colors) -> list | None:
    """4 échantillons (clair -> sombre) d'une liste de couleurs BGR555, index 0
    exclu (toujours réservé/transparent). None si rien d'affichable."""
    editable = colors[1:] if len(colors) > 1 else colors
    if not editable:
        return None
    n = len(editable)
    return [editable[min(i * (n - 1) // 3, n - 1)] for i in range(4)]


def _grey(qc: QColor, amount: float = 0.62) -> QColor:
    """Mélange une couleur vers un gris moyen (signale « non éditable »)."""
    g = QColor(96, 102, 110)
    inv = 1.0 - amount
    return QColor(
        int(qc.red()   * inv + g.red()   * amount),
        int(qc.green() * inv + g.green() * amount),
        int(qc.blue()  * inv + g.blue()  * amount),
    )


def swatch_icon(colors, size: int = 16, *, greyed: bool = False,
                override: bool = False, marker_color: str = C.ACCENT) -> QIcon:
    """Icône 2x2 échantillonnant 4 couleurs d'une liste BGR555 brute.

    - `greyed`   : couleurs atténuées vers le gris (palette propre d'asset,
      non éditable).
    - `override` : dessine un petit chevron d'angle (marker_color) signalant
      que cet asset pointe vers une palette de scène (pointeur, pas sa palette
      d'origine)."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    half = size // 2
    stops = _sample_stops(colors)
    if stops:
        quads = [(0, 0), (half, 0), (0, half), (half, half)]
        for (x, y), c in zip(quads, stops):
            qc = _qcolor(c)
            if greyed:
                qc = _grey(qc)
            painter.fillRect(x, y, half, half, qc)
    else:
        painter.fillRect(0, 0, size, size, QColor(C.BG_INPUT))
        painter.setPen(QColor(C.BORDER_MID))
        painter.drawRect(0, 0, size - 1, size - 1)
    if override:
        # Petit triangle plein dans le coin supérieur droit = marqueur "lien".
        s = max(5, size // 3)
        tri = QPolygon([QPoint(size - s, 0), QPoint(size, 0), QPoint(size, s)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(marker_color))
        painter.drawPolygon(tri)
    painter.end()
    return QIcon(px)


def plus_icon(size: int = 16, color: str = C.ACCENT) -> QIcon:
    """Icône « + » peinte (indépendante de la police) pour le bouton d'ajout."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    t = max(2, size // 8)              # épaisseur des barres
    m = size // 4                      # marge
    painter.fillRect(m, (size - t) // 2, size - 2 * m, t, QColor(color))   # barre horizontale
    painter.fillRect((size - t) // 2, m, t, size - 2 * m, QColor(color))   # barre verticale
    painter.end()
    return QIcon(px)


def bank_icon(bank: PaletteBank, size: int = 16) -> QIcon:
    """Icone 2x2 échantillonnant 4 couleurs de la banque (claire -> sombre).
    Grisée si la banque n'a pas encore de couleurs (slot réservé). L'index 0
    (toujours réservé/transparent) est exclu de l'échantillonnage — sinon un
    quadrant afficherait la même couleur pour toutes les banques du catalogue."""
    return swatch_icon(list(bank.colors), size)
