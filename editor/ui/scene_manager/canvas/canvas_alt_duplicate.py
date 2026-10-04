"""ui/scene_manager/canvas/canvas_alt_duplicate.py — le geste Alt+glisser.

Trois temps, rien d'autre :
  1. Alt+clic sur un item  → le geste prend la main (la vue ne délègue RIEN à Qt :
     ni sélection par glisser, ni déplacement d'item, ni rectangle) ;
  2. glisser               → des FANTÔMES (le sprite, ou un cadre à défaut) suivent la souris ; les objets
     réels ne bougent pas, aucun modèle n'est touché ;
  3. relâcher              → le décalage final est rendu à l'appelant, qui crée
     les copies en UNE fois. Sous le seuil, c'est un simple clic : rien n'est créé.

La vue ne conserve que `gesture.active` ; tout l'état du geste vit ici.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem

from ui.scene_manager.canvas.canvas_items import SpriteItem

from ui.common.theme import C

# En deçà (px scène) c'est un clic Alt, pas un glisser.
_THRESHOLD = 2
_SNAP = 8
_GHOST_Z = 10_000
_GHOST_OPACITY = 0.6


class AltDuplicateGesture:
    def __init__(self, view):
        self._view = view
        self._press: Optional[QPointF] = None
        self._ghosts: list[tuple[QGraphicsItem, QPointF]] = []   # (fantôme, pos de départ)
        self._snap = False

    @property
    def active(self) -> bool:
        return self._press is not None

    def begin(self, scene_pos: QPointF) -> bool:
        """Arme le geste si un item éligible est sous le clic. Un item hors
        sélection la remplace (comme un clic ordinaire) ; sinon toute la
        sélection est dupliquée."""
        item = self._view._selectable_item_at(scene_pos)
        if item is None:
            return False
        scene = self._view.scene()
        if not item.isSelected():
            scene.clearSelection()
            item.setSelected(True)
            scene.set_active_item(item)
        items = scene.selectable_items()
        self._snap = any(getattr(it, "snap", False) for it in items)
        self._press = QPointF(scene_pos)
        for it in items:
            ghost = self._make_ghost(it)
            ghost.setZValue(_GHOST_Z)
            ghost.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            scene.addItem(ghost)
            self._ghosts.append((ghost, ghost.pos()))
        return True

    def move(self, scene_pos: QPointF) -> None:
        dx, dy = self._delta(scene_pos)
        for ghost, start in self._ghosts:
            ghost.setPos(start.x() + dx, start.y() + dy)

    def finish(self, scene_pos: QPointF) -> Optional[tuple[int, int]]:
        """Fin du geste : le décalage à appliquer, ou None (simple clic Alt)."""
        dx, dy = self._delta(scene_pos)
        self.cancel()
        if abs(dx) < _THRESHOLD and abs(dy) < _THRESHOLD:
            return None
        return dx, dy

    def cancel(self) -> None:
        scene = self._view.scene()
        for ghost, _start in self._ghosts:
            if scene is not None and ghost.scene() is scene:
                scene.removeItem(ghost)
        self._ghosts = []
        self._press = None

    @staticmethod
    def _make_ghost(item) -> QGraphicsItem:
        """Le sprite lui-même (même cadrage, même transform) s'il en a un ;
        sinon — zone d'interface, acteur sans image — un cadre en pointillés."""
        if isinstance(item, SpriteItem) and not item._placeholder:
            ghost = QGraphicsPixmapItem(item.pixmap())
            ghost.setOffset(item.offset())
            ghost.setTransform(item.transform())
            ghost.setPos(item.pos())
            ghost.setOpacity(_GHOST_OPACITY)
            return ghost
        frame = QGraphicsRectItem(item.sceneBoundingRect())
        pen = QPen(QColor(C.ACCENT), 0)
        pen.setStyle(Qt.PenStyle.DashLine)
        frame.setPen(pen)
        fill = QColor(C.ACCENT)
        fill.setAlpha(50)
        frame.setBrush(QBrush(fill))
        return frame

    def _delta(self, scene_pos: QPointF) -> tuple[int, int]:
        dx = round(scene_pos.x() - self._press.x())
        dy = round(scene_pos.y() - self._press.y())
        if self._snap:
            dx = round(dx / _SNAP) * _SNAP
            dy = round(dy / _SNAP) * _SNAP
        return dx, dy
