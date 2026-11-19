"""
editor/canvas_tools.py — Outils du canvas (pattern Strategy).

Chaque outil gère ses propres événements souris et son état.
GBAView délègue on_press/on_move/on_release à l'outil actif.

Cycle de vie :
    view.set_tool(tool)
        → ancien_tool.deactivate()   (curseur, drag mode)
        → nouveau_tool.activate()
    mouse events → tool.on_press / on_move / on_release
        → retourne True si l'event est consommé (évite super() dans View)
"""

from __future__ import annotations

from core.models.unique_name import unique_name
from abc import ABC
from typing import TYPE_CHECKING, Optional

from core.models.collision_tiles import TILE_EMPTY
from core.collision_slopes import slope_tiles_for
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsView

if TYPE_CHECKING:
    from ui.scene_manager.canvas.canvas_view import GBAView


# ──────────────────────────────────────────────────────────────────
#  Base
# ──────────────────────────────────────────────────────────────────


class BaseTool(ABC):
    def __init__(self, view: GBAView):
        self._view = view

    def activate(self):
        """Appelé à l'activation : curseur, drag mode, overlays."""

    def deactivate(self):
        """Appelé avant le changement d'outil : nettoyage."""

    def on_press(self, pos: QPointF, e) -> bool:
        """Retourne True si l'event est consommé."""
        return False

    def on_move(self, pos: QPointF, e) -> bool:
        return False

    def on_release(self, pos: QPointF, e) -> bool:
        return False

    def on_leave(self):
        """Appelé quand la souris quitte le viewport."""


# ──────────────────────────────────────────────────────────────────
#  Ajout d'actor — snap 8px + surbrillance de cellule
# ──────────────────────────────────────────────────────────────────


class AddActorTool(BaseTool):
    """
    Snap obligatoire à la grille 8px.
    La cellule survolée est mise en surbrillance.
    Clic → crée un actor nommé Actor_X_Y aux coordonnées snappées.
    """

    _CELL = 16
    _FILL = QColor(100, 255, 120, 70)
    _BORDER = QColor(100, 255, 120, 220)

    def __init__(self, view):
        super().__init__(view)
        self._preview: QGraphicsRectItem | None = None

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._preview = QGraphicsRectItem(0, 0, self._CELL, self._CELL)
        self._preview.setBrush(QBrush(self._FILL))
        self._preview.setPen(QPen(self._BORDER, 0))
        self._preview.setZValue(50)
        self._preview.setVisible(False)
        self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    def on_move(self, pos: QPointF, e) -> bool:
        sx = int(pos.x() // self._CELL) * self._CELL
        sy = int(pos.y() // self._CELL) * self._CELL
        self._preview.setPos(sx, sy)
        self._preview.setVisible(True)
        return True

    def on_press(self, pos: QPointF, e) -> bool:
        sx = int(pos.x() // self._CELL) * self._CELL
        sy = int(pos.y() // self._CELL) * self._CELL
        from core.command_dispatcher import get_dispatcher

        proj = get_dispatcher().project
        scene = proj.active_scene if proj else None
        if scene:
            name = unique_name("Actor", {a.name for a in scene.actors})
        else:
            name = "Actor"
        get_dispatcher().add_actor(name, x=sx, y=sy)
        self._view.placement_done.emit()
        return True

    def on_leave(self):
        if self._preview:
            self._preview.setVisible(False)


# ──────────────────────────────────────────────────────────────────
#  Ajout d'Area — grille 8px, aperçu de la taille d'une Area neuve
# ──────────────────────────────────────────────────────────────────


class AddAreaTool(BaseTool):
    """Clic → crée une Area neuve (forme capteur 32×32) centrée sur le point cliqué, aimanté à la grille de 8 px.
    L'aperçu montre la zone que le clic poserait."""

    _STEP = 8
    _FILL = QColor(110, 150, 255, 70)
    _BORDER = QColor(140, 175, 255, 220)

    def __init__(self, view):
        super().__init__(view)
        from core.models.scene import AREA_DEFAULT_SIZE
        self._size = AREA_DEFAULT_SIZE
        self._preview: QGraphicsRectItem | None = None

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._preview = QGraphicsRectItem(0, 0, self._size, self._size)
        self._preview.setBrush(QBrush(self._FILL))
        self._preview.setPen(QPen(self._BORDER, 0))
        self._preview.setZValue(50)
        self._preview.setVisible(False)
        self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    def _centre(self, pos: QPointF) -> tuple[int, int]:
        """Le point cliqué, aimanté : c'est le CENTRE de l'Area (cf. `CommandDispatcher.add_area`)."""
        return (round(pos.x() / self._STEP) * self._STEP, round(pos.y() / self._STEP) * self._STEP)

    def on_move(self, pos: QPointF, e) -> bool:
        cx, cy = self._centre(pos)
        self._preview.setPos(cx - self._size // 2, cy - self._size // 2)
        self._preview.setVisible(True)
        return True

    def on_press(self, pos: QPointF, e) -> bool:
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().add_area(*self._centre(pos))
        self._view.placement_done.emit()
        return True

    def on_leave(self):
        if self._preview:
            self._preview.setVisible(False)


# ──────────────────────────────────────────────────────────────────
#  Sélection / déplacement (comportement Qt par défaut)
# ──────────────────────────────────────────────────────────────────


class SelectTool(BaseTool):
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.unsetCursor()

    # Aucun on_press/on_move/on_release : Qt gère rubber band + item drag.


# ──────────────────────────────────────────────────────────────────
#  Gomme — supprime l'actor cliqué
# ──────────────────────────────────────────────────────────────────


class EraseTool(BaseTool):
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.ForbiddenCursor)

    def deactivate(self):
        self._view.unsetCursor()

    def on_press(self, pos: QPointF, e) -> bool:
        from core.command_dispatcher import get_dispatcher
        from ui.scene_manager.canvas.canvas_items import AreaItem, SpriteItem

        items = self._view.scene().items(pos)
        for item in items:
            if isinstance(item, SpriteItem):
                get_dispatcher().delete_actor(item.scene_sprite)
                break
            if isinstance(item, AreaItem):
                get_dispatcher().delete_areas([item.area])
                break
        return True  # toujours consommé — évite le rubber band


# ──────────────────────────────────────────────────────────────────
#  Collision — pinceau 8px, 16px, slope sol, slope plafond (inversé)
# ──────────────────────────────────────────────────────────────────

class CollisionSlopeTool(BaseTool):
    """Trait de pente de la surface Collision.

    Le mode choisit le côté plein (sol ou plafond). Les autres gestes passent
    par GridPaintTool, comme pour une grille ou un fond.
    """

    def __init__(self, view: GBAView, mode: str):
        super().__init__(view)
        self._mode = mode
        self._paint = True
        self._start: Optional[tuple[int, int]] = None

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        if self._view.collision_overlay:
            self._view.collision_overlay.setVisible(True)

    def deactivate(self):
        self._view.unsetCursor()
        overlay = self._view.collision_overlay
        if not overlay:
            return
        overlay.set_preview(None)
        scene = self._view.scene()
        if not (getattr(scene, "_collision_view", False)
                or getattr(scene, "_collision_index_view", False)
                or getattr(scene, "_collision_normals_view", False)):
            overlay.setVisible(False)

    def on_press(self, pos: QPointF, e) -> bool:
        overlay = self._view.collision_overlay
        if not overlay:
            return True
        self._paint = e.button() == Qt.MouseButton.LeftButton
        self._start = overlay.scene_to_tile(pos.x(), pos.y())
        if self._paint:
            col, row = self._start
            overlay.set_preview(slope_tiles_for(self._mode, col, row, col, row))
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        overlay = self._view.collision_overlay
        if overlay and self._start and self._paint:
            col, row = overlay.scene_to_tile(pos.x(), pos.y())
            overlay.set_preview(slope_tiles_for(self._mode, *self._start, col, row))
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        overlay = self._view.collision_overlay
        if not overlay or self._start is None:
            return True
        col, row = overlay.scene_to_tile(pos.x(), pos.y())
        delta = {}
        for cell_col, cell_row, tile in slope_tiles_for(self._mode, *self._start, col, row):
            old = overlay.tile_at(cell_col, cell_row)
            new = tile if self._paint else TILE_EMPTY
            if old != new:
                delta[(cell_col, cell_row)] = (old, new)
                overlay.set_tile(cell_col, cell_row, new)
        overlay.set_preview(None)
        self._start = None
        if delta:
            from core.history import GridPaintCmd, get_history
            from ui.scene_manager.grid_paint_surface import GridPaintSurface

            get_history().push_executed(GridPaintCmd(
                GridPaintSurface("Collision", 8, changed=overlay.update,
                                 read=overlay.tile_at, write=overlay.set_tile),
                delta, persist_fn=lambda: self._view.collision_painted.emit(),
                label="Peinture collision",
            ))
            self._view.collision_painted.emit()
        return True
_BG_TILE = 8


class GridPaintTool(BaseTool):
    """Pinceau, rectangle ou remplissage d'une surface de valeurs."""

    def __init__(self, view: GBAView, surface, mode: str, value: int, persist):
        super().__init__(view)
        self._surface, self._mode, self._value, self._persist = surface, mode, value, persist
        self._erase = False
        self._anchor = None
        self._delta = {}
        self._last_cell = None
        self._preview = None

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        if self._mode == 'rect':
            self._preview = QGraphicsRectItem(0, 0, 0, 0)
            self._preview.setBrush(QBrush(QColor(120, 180, 255, 60)))
            self._preview.setPen(QPen(QColor(120, 180, 255, 220), 0))
            self._preview.setZValue(300)
            self._preview.setVisible(False)
            self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    def _paint(self, col, row, *, notify: bool = False) -> bool:
        old = self._surface.value_at(col, row)
        new = self._surface.empty_value if self._erase else self._value
        if old != new and self._surface.set_value(col, row, new, notify=notify):
            self._delta[(col, row)] = (self._delta.get((col, row), (old, new))[0], new)
            return True
        return False

    @staticmethod
    def _cells_between(start: tuple[int, int], end: tuple[int, int]):
        (c0, r0), (c1, r1) = start, end
        dc, dr = abs(c1 - c0), -abs(r1 - r0)
        step_c, step_r = (1 if c0 < c1 else -1), (1 if r0 < r1 else -1)
        error = dc + dr
        while True:
            yield c0, r0
            if (c0, r0) == (c1, r1):
                return
            doubled = 2 * error
            if doubled >= dr:
                error += dr
                c0 += step_c
            if doubled <= dc:
                error += dc
                r0 += step_r

    def _paint_to(self, col: int, row: int):
        start = self._last_cell if self._last_cell is not None else (col, row)
        changed = False
        for cell in self._cells_between(start, (col, row)):
            changed = self._paint(*cell) or changed
        if changed:
            self._surface.notify_changed()
        self._last_cell = (col, row)

    def on_press(self, pos: QPointF, e) -> bool:
        self._erase, self._delta, self._last_cell = e.button() == Qt.MouseButton.RightButton, {}, None
        col, row = self._surface.scene_to_cell(pos.x(), pos.y())
        if self._mode == 'rect':
            self._anchor = (col, row)
            self._update_preview(col, row)
        elif self._mode == 'fill':
            self._fill(col, row)
        else:
            self._paint_to(col, row)
        return True

    def _fill(self, col: int, row: int):
        """Remplit uniquement la zone contiguë de la valeur sous le clic."""
        source = self._surface.value_at(col, row)
        target = self._surface.empty_value if self._erase else self._value
        if source == target or not self._surface.contains(col, row):
            return
        pending, seen = [(col, row)], set()
        changed = False
        while pending:
            c, r = pending.pop()
            if (c, r) in seen or not self._surface.contains(c, r) or self._surface.value_at(c, r) != source:
                continue
            seen.add((c, r))
            changed = self._paint(c, r) or changed
            pending.extend(((c - 1, r), (c + 1, r), (c, r - 1), (c, r + 1)))
        if changed:
            self._surface.notify_changed()

    def on_move(self, pos: QPointF, e) -> bool:
        col, row = self._surface.scene_to_cell(pos.x(), pos.y())
        if self._mode == 'rect' and self._anchor is not None:
            self._update_preview(col, row)
            return True
        held = Qt.MouseButton.RightButton if self._erase else Qt.MouseButton.LeftButton
        if self._mode == 'brush' and e.buttons() & held:
            self._paint_to(col, row)
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        if self._anchor is not None:
            c0, r0 = self._anchor
            c1, r1 = self._surface.scene_to_cell(pos.x(), pos.y())
            changed = False
            for row in range(min(r0, r1), max(r0, r1) + 1):
                for col in range(min(c0, c1), max(c0, c1) + 1):
                    changed = self._paint(col, row) or changed
            if changed:
                self._surface.notify_changed()
            self._anchor = None
            if self._preview:
                self._preview.setVisible(False)
        if self._delta:
            from core.history import GridPaintCmd, get_history
            get_history().push_executed(GridPaintCmd(self._surface, dict(self._delta), self._persist))
            if self._persist:
                self._persist()
        self._last_cell = None
        return True

    def _update_preview(self, col: int, row: int):
        if not self._preview or self._anchor is None:
            return
        c0, r0 = self._anchor
        size = self._surface.cell_size
        self._preview.setRect(min(c0, col) * size, min(r0, row) * size,
                              (abs(col - c0) + 1) * size, (abs(row - r0) + 1) * size)
        self._preview.setVisible(True)

    def on_leave(self):
        if self._preview and self._anchor is None:
            self._preview.setVisible(False)


# ──────────────────────────────────────────────────────────────────
#  Zone de texte — tracé rectangulaire
# ──────────────────────────────────────────────────────────────────


class UIWidgetTool(BaseTool):
    """Dessine un élément d'UI (texte, conteneur ou image) au rectangle — UN
    outil paramétré par `kind`, choisi dans le dropdown de la toolbar (même
    modèle que collision et inpainting).

    Le geste est celui de `GridPaintTool` en mode rect — ancre au press,
    aperçu au move, création au release — parce que c'est déjà le geste
    « délimiter une surface » du canvas, et qu'en inventer un second pour la
    même intention rendrait l'outil étranger au reste.

    Snap à la tuile PENDANT le tracé et pas seulement au moment d'écrire : un
    élément en cible BG ne peut pas commencer entre deux tuiles, et l'aperçu
    doit montrer ce qui sera réellement posé. Un rectangle qui rétrécirait au
    relâchement ferait douter du clic.

    Clic sans glisser = taille par défaut du type : c'est le geste de qui sait
    déjà où il le veut et le redimensionnera dans l'inspecteur."""

    # Palette locale de l'outil Interface : elle rend le geste lisible dans le
    # canvas ; le type précis se lit à l'icône de la toolbar, pas à une
    # couleur globale dédiée.
    _FILL   = QColor(79, 143, 247, 50)
    _BORDER = QColor(79, 143, 247, 230)
    # Taille au simple clic, par type — multiples de 8.
    _DEFAULTS = {
        "text":  (96, 16),     # un libellé d'une ligne
        "textbox": (128, 32),  # une boîte de dialogue basse plausible
        "container": (96, 48),  # un cadre de menu
        "image": (16, 16),     # une icône de HUD ; le sprite choisi la recalera
    }

    def __init__(self, view: GBAView, kind: str = "text"):
        super().__init__(view)
        self._kind = kind
        self._anchor: Optional[tuple[int, int]] = None   # (x, y) px snappés
        self._preview: QGraphicsRectItem | None = None

    # ── Cycle de vie ─────────────────────────────────────────────
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._preview = QGraphicsRectItem(0, 0, 0, 0)
        self._preview.setBrush(QBrush(self._FILL))
        self._preview.setPen(QPen(self._BORDER, 0))
        self._preview.setZValue(70)      # au-dessus de l'aperçu d'inpainting
        self._preview.setVisible(False)
        self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None
        self._anchor = None

    # ── Helpers ──────────────────────────────────────────────────
    def _ctrl(self):
        return getattr(self._view, "ui_region_controller", None)

    def _offset(self) -> tuple[int, int]:
        """Position de la caméra de démarrage si le widget sera ancré à l'écran :
        le clic est en coordonnées de scène, le modèle en coordonnées d'écran."""
        from core.models.ui_region import ANCHOR_SCREEN
        ctrl, sc = self._ctrl(), self._view.scene()
        if ctrl is None or not hasattr(sc, "camera_pos"):
            return 0, 0
        return sc.camera_pos() if ctrl.receiving_anchor() == ANCHOR_SCREEN else (0, 0)

    def _snap(self, pos: QPointF) -> tuple[int, int]:
        """Case de tuile sous `pos`, en repère écran quand le widget y sera ancré."""
        ox, oy = self._offset()
        return ((int(pos.x()) - ox) // _BG_TILE) * _BG_TILE, ((int(pos.y()) - oy) // _BG_TILE) * _BG_TILE

    def _rect(self, pos: QPointF) -> tuple[int, int, int, int]:
        """(x, y, w, h) en pixels, bornes snappées, largeur/hauteur >= 1 tuile.
        La tuile SOUS le curseur est incluse — sans le `+ _BG_TILE`, glisser
        d'une tuile produirait une zone vide."""
        ax, ay = self._anchor
        cx, cy = self._snap(pos)
        x0, y0 = min(ax, cx), min(ay, cy)
        x1, y1 = max(ax, cx) + _BG_TILE, max(ay, cy) + _BG_TILE
        return x0, y0, x1 - x0, y1 - y0

    # ── Événements ───────────────────────────────────────────────
    def on_press(self, pos: QPointF, e) -> bool:
        if e.button() != Qt.MouseButton.LeftButton:
            return True
        self._anchor = self._snap(pos)
        if self._kind == "text":
            # Une chaîne se pose, elle ne se dessine pas : pas de rectangle.
            return self.on_release(pos, e)
        self._apply_preview(*self._rect(pos))
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        if self._anchor is None:
            return True
        self._apply_preview(*self._rect(pos))
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        if self._anchor is None:
            return True
        x, y, w, h = self._rect(pos)
        if self._kind == "text" or (w <= _BG_TILE and h <= _BG_TILE):   # simple clic
            w, h = self._DEFAULTS.get(self._kind, self._DEFAULTS["text"])
        self._anchor = None
        if self._preview:
            self._preview.setVisible(False)
        ctrl = self._ctrl()
        if ctrl is not None:
            ctrl.create_element(self._kind, x, y, w, h)
            self._view.placement_done.emit()
        return True

    def _apply_preview(self, x, y, w, h):
        if self._preview:
            ox, oy = self._offset()
            self._preview.setRect(x + ox, y + oy, w, h)
            self._preview.setVisible(True)

    def on_leave(self):
        if self._preview and self._anchor is None:
            self._preview.setVisible(False)
