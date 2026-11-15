"""La vue « index de tuile » : l'index de chaque tuile de collision non vide s'écrit sur l'overlay, et la carte reste visible."""
from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from core.models.collision_tiles import (
    TILE_EMPTY, TILE_ONEWAY_UP, TILE_SLOPE_L_HI, TILE_SLOPE_L_LO, TILE_SOLID,
)
from ui.scene_manager.canvas.canvas_items import CollisionOverlay
from ui.scene_manager.canvas.canvas_scene import GBAScene


def _rendu(scene, w=32, h=16):
    image = QImage(w * 8, h * 8, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    scene.render(painter)
    painter.end()
    return image


def test_les_indices_ajoutent_du_texte_sur_les_tuiles_non_vides(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    scene = QGraphicsScene(0, 0, 32, 16)      # la scène possède l'item : elle doit survivre au rendu
    overlay = CollisionOverlay()
    scene.addItem(overlay)
    overlay.load([[TILE_SOLID, 0, TILE_ONEWAY_UP, 0]] + [[0] * 4 for _ in range(1)])
    overlay.setVisible(True)
    sans = _rendu(scene)
    overlay.set_show_indices(True)
    avec = _rendu(scene)
    assert sans != avec


def test_les_tuiles_voisines_forment_des_masses_continues_sur_un_voile_sombre(qapp):
    overlay = CollisionOverlay()
    overlay.load([[TILE_SOLID, TILE_SOLID]])
    image = QImage(16, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    option = QStyleOptionGraphicsItem()
    option.exposedRect = QRectF(0, 0, 16, 8)
    overlay.paint(painter, option)
    painter.end()

    # Pas de bordure au joint x=7/8, mais un contour sur le bord extérieur.
    assert image.pixelColor(7, 4) == image.pixelColor(8, 4)
    assert image.pixelColor(0, 4) != image.pixelColor(7, 4)
    # Même fusion pour deux index qui composent une pente douce continue.
    overlay.load([[TILE_SLOPE_L_LO, TILE_SLOPE_L_HI]])
    slope = QImage(16, 8, QImage.Format.Format_ARGB32)
    slope.fill(QColor("white"))
    painter = QPainter(slope)
    overlay.paint(painter, option)
    painter.end()
    assert slope.pixelColor(7, 6) == slope.pixelColor(8, 6)
    # Une zone vide reste assombrie par le mode collision.
    overlay.load([[TILE_EMPTY]])
    empty = QImage(8, 8, QImage.Format.Format_ARGB32)
    empty.fill(QColor("white"))
    painter = QPainter(empty)
    overlay.paint(painter, option)
    painter.end()
    assert empty.pixelColor(4, 4).red() < 200


def test_la_vue_index_rend_la_carte_visible_puis_la_rend_a_son_etat(qapp):
    scene = GBAScene()
    assert not scene._collision_overlay.isVisible()
    scene.set_collision_index_view(True)
    assert scene._collision_overlay.isVisible()
    scene.set_collision_index_view(False)
    assert not scene._collision_overlay.isVisible()
    scene.set_collision_view(True)
    scene.set_collision_index_view(True)
    scene.set_collision_index_view(False)
    assert scene._collision_overlay.isVisible()


def test_les_normales_ajoutent_des_traits_sur_les_pentes_les_blocs_et_les_faces_a_sens_unique(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from core.models.collision_tiles import TILE_SLOPE_L
    scene = QGraphicsScene(0, 0, 32, 16)
    overlay = CollisionOverlay()
    scene.addItem(overlay)
    overlay.load([[TILE_SOLID, TILE_SOLID, TILE_SLOPE_L, TILE_ONEWAY_UP]] + [[0] * 4])
    overlay.setVisible(True)
    sans = _rendu(scene)
    overlay.set_show_normals(True)
    assert sans != _rendu(scene)


def test_la_carte_reste_visible_tant_qu_une_des_trois_vues_la_demande(qapp):
    scene = GBAScene()
    scene.set_collision_normals_view(True)
    scene.set_collision_index_view(True)
    scene.set_collision_index_view(False)
    assert scene._collision_overlay.isVisible()
    scene.set_collision_normals_view(False)
    assert not scene._collision_overlay.isVisible()
