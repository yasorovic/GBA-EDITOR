"""Le canvas transforme le sprite autour de son POINT DE PIVOT, pas autour du
centre du cadre ni de l'ancre : mesuré sur les pixels rendus, pas sur la matrice."""
from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QGraphicsScene

from core.models.scene import Actor


def _extent_x(qapp, *, scale_x: float, pivot_x: float) -> tuple[int, int]:
    """Colonnes (min, max) occupées par un sprite 32×32 posé en x=50."""
    from ui.scene_manager.canvas.canvas_items import SpriteItem

    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 255, 0))
    scene = QGraphicsScene(0, 0, 200, 100)
    actor = Actor(name="A")
    actor.x, actor.y = 50, 20
    scene.addItem(SpriteItem(pixmap, actor, 200, 100, scale_x=scale_x, pivot_x=pivot_x))
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 200, 100), QRectF(0, 0, 200, 100))
    painter.end()
    columns = [x for x in range(200) for y in range(100)
               if QColor.fromRgba(image.pixel(x, y)).alpha() > 200]
    return min(columns), max(columns)


def test_sans_pivot_l_echelle_part_du_centre_du_cadre(qapp):
    assert _extent_x(qapp, scale_x=2.0, pivot_x=0) == (34, 97)


def test_le_bord_gauche_reste_fixe_quand_le_pivot_est_a_gauche(qapp):
    assert _extent_x(qapp, scale_x=2.0, pivot_x=-16) == (50, 113)


def test_le_bord_droit_reste_fixe_quand_le_pivot_est_a_droite(qapp):
    assert _extent_x(qapp, scale_x=2.0, pivot_x=16) == (18, 81)


def test_une_echelle_negative_retourne_autour_du_pivot(qapp):
    # Pivot sur le bord gauche (x=50) : le sprite retourné occupe les colonnes 18..49.
    assert _extent_x(qapp, scale_x=-1.0, pivot_x=-16) == (18, 49)
