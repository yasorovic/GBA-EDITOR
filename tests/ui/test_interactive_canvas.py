"""La boîte propre d'un composant Interactive est dessinée au canvas, à la taille et au tag que le build
émet (même fonction `owner_effective_boxes`), dans sa teinte à part."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

from core.models.components import CollisionBoxComponent, InteractiveComponent
from core.models.scene import Actor
from ui.scene_manager.canvas.canvas_items import ActorBoxOverlay


def _rendu(actor, sprites=None) -> QImage:
    scene = QGraphicsScene(0, 0, 64, 64)
    overlay = ActorBoxOverlay(64, 64)
    scene.addItem(overlay)
    overlay.set_actors([actor], {}, sprites)
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, 64, 64), QRectF(0, 0, 64, 64))
    painter.end()
    return image


def _ambre(image, x, y) -> bool:
    c = QColor.fromRgba(image.pixel(x, y))
    return c.alpha() > 0 and c.red() > 200 and c.green() > 150 and c.blue() < 130


def _vide(image, x, y) -> bool:
    return QColor.fromRgba(image.pixel(x, y)).alpha() == 0


def test_la_boite_propre_est_dessinee_16_par_16_sans_sprite(qapp):
    acteur = Actor(name="Chest", x=10, y=10)
    acteur.components = [InteractiveComponent()]
    image = _rendu(acteur)
    assert _ambre(image, 18, 18)               # le centre de la zone 10..26
    assert _vide(image, 30, 18) and _vide(image, 5, 18)


def test_la_boite_propre_prend_le_cadre_du_sprite(qapp):
    acteur = Actor(name="Chest", x=10, y=10)
    acteur.components = [InteractiveComponent()]
    sprite = SimpleNamespace(frame_w=32, frame_h=8)
    image = _rendu(acteur, {id(acteur): sprite})
    assert _ambre(image, 38, 14)               # jusqu'à x = 42
    assert _vide(image, 18, 24)                # 8 px de haut seulement


def test_une_boite_designee_n_en_ajoute_pas(qapp):
    acteur = Actor(name="Sign", x=10, y=10)
    acteur.components = [CollisionBoxComponent(tag="reach", solid=False, w=8, h=8),
                         InteractiveComponent(box_tag="reach")]
    image = _rendu(acteur)
    assert not _ambre(image, 14, 14)           # la boîte « reach » garde sa teinte de capteur
    assert not _vide(image, 14, 14)
    assert _vide(image, 24, 24)                # rien d'ajouté en 16×16
