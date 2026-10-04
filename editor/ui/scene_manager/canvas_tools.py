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

from abc import ABC
from typing import TYPE_CHECKING, Optional

from core.models.collision_tiles import TILE_EMPTY, TILE_SOLID
from core.collision_slopes import SLOPE_MODES, slope_tiles_for
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
            existing = {a.name for a in scene.actors}
            n = 0
            while f"Actor_{n}" in existing:
                n += 1
            name = f"Actor_{n}"
        else:
            name = "Actor_0"
        get_dispatcher().add_actor(name, x=sx, y=sy)
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
        from ui.scene_manager.canvas.canvas_items import SpriteItem

        items = self._view.scene().items(pos)
        for item in items:
            if isinstance(item, SpriteItem):
                get_dispatcher().delete_actor(item.scene_sprite)
                break
        return True  # toujours consommé — évite le rubber band


# ──────────────────────────────────────────────────────────────────
#  Collision — pinceau 8px, 16px, slope sol, slope plafond (inversé)
# ──────────────────────────────────────────────────────────────────

class CollisionTool(BaseTool):
    """
    mode : "collision_8" | "collision_16" | "collision_slope" | "collision_slope_inv"

    Clic droit = peindre / appliquer.
    Clic gauche = effacer (TILE_EMPTY).
    """

    def __init__(self, view: GBAView, mode: str):
        super().__init__(view)
        self._mode = mode
        self._paint_mode: bool = True  # True=peindre, False=effacer
        self._slope_start: Optional[tuple[int, int]] = None
        self._dirty = False
        self._stroke_delta: dict[tuple[int, int], tuple[int, int]] = {}

    # ── Cycle de vie ─────────────────────────────────────────────

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        ov = self._view.collision_overlay
        if ov:
            ov.setVisible(True)

    def deactivate(self):
        self._view.unsetCursor()
        ov = self._view.collision_overlay
        if ov:
            ov.set_preview(None)
            ov.set_hover(None)
            sc = self._view.scene()
            keep_visible = getattr(sc, "_collision_view", False)
            if not keep_visible:
                ov.setVisible(False)

    # ── Événements ───────────────────────────────────────────────

    def on_press(self, pos: QPointF, e) -> bool:
        self._stroke_delta = {}
        self._paint_mode = e.button() == Qt.MouseButton.LeftButton
        ov = self._view.collision_overlay
        if not ov:
            return True
        self._update_hover(pos)
        if self._mode in SLOPE_MODES:
            col, row = ov.scene_to_tile(pos.x(), pos.y())
            self._slope_start = (col, row)
            if self._paint_mode:
                ov.set_preview(self._slope_tiles_for(col, row, col, row))
        elif self._mode == "collision_8":
            self._paint_brush(pos, 1)
            self._dirty = True
        elif self._mode == "collision_16":
            self._paint_brush(pos, 2)
            self._dirty = True
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        ov = self._view.collision_overlay
        if not ov:
            return True
        self._update_hover(pos)
        # Brush : seulement si le bouton correspondant est enfoncé
        buttons = e.buttons()
        active = (self._paint_mode and buttons & Qt.MouseButton.LeftButton) or (
            not self._paint_mode and buttons & Qt.MouseButton.RightButton
        )
        if self._mode == "collision_8" and active:
            self._paint_brush(pos, 1)
        elif self._mode == "collision_16" and active:
            self._paint_brush(pos, 2)
        elif self._mode in SLOPE_MODES and self._slope_start and self._paint_mode:
            sc, sr = self._slope_start
            ec, er = ov.scene_to_tile(pos.x(), pos.y())
            ov.set_preview(self._slope_tiles_for(sc, sr, ec, er))
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        ov = self._view.collision_overlay
        if ov and self._mode in SLOPE_MODES and self._slope_start:
            sc, sr = self._slope_start
            ec, er = ov.scene_to_tile(pos.x(), pos.y())
            tiles = self._slope_tiles_for(sc, sr, ec, er)
            for col, row, t in tiles:
                old = ov.tile_at(col, row)
                new = t if self._paint_mode else TILE_EMPTY
                self._stroke_delta[(col, row)] = (old, new)
                ov.set_tile(col, row, new)
            ov.set_preview(None)
            self._slope_start = None
            self._dirty = True

        if self._stroke_delta:
            from core.history import CollisionPaintCmd, get_history

            cmd = CollisionPaintCmd(
                ov,
                dict(self._stroke_delta),
                persist_fn=lambda: self._view.collision_painted.emit(),
            )
            h = get_history()
            h._undo.append(cmd)
            h._redo.clear()
            h.changed.emit()
            self._stroke_delta = {}

        if self._dirty:
            self._view.collision_painted.emit()
            self._dirty = False
        return True

    def on_leave(self):
        ov = self._view.collision_overlay
        if ov:
            ov.set_hover(None)

    # ── Logique interne ───────────────────────────────────────────

    def _update_hover(self, scene_pos: QPointF):
        """Surligne la tuile (ou le bloc 2×2) que le pinceau va couvrir. Une pente
        en cours de tracé a déjà son aperçu : la surbrillance s'efface alors."""
        ov = self._view.collision_overlay
        if not ov:
            return
        if self._mode in SLOPE_MODES and self._slope_start:
            ov.set_hover(None)
            return
        size = 2 if self._mode == "collision_16" else 1
        col, row = ov.scene_to_tile(scene_pos.x(), scene_pos.y())
        ov.set_hover((col, row, size, size))

    def _paint_brush(self, scene_pos: QPointF, brush_tiles: int):
        ov = self._view.collision_overlay
        if not ov:
            return
        col, row = ov.scene_to_tile(scene_pos.x(), scene_pos.y())
        new_type = TILE_SOLID if self._paint_mode else TILE_EMPTY
        for dr in range(brush_tiles):
            for dc in range(brush_tiles):
                c, r = col + dc, row + dr
                old = ov.tile_at(c, r)
                ov.set_tile(c, r, new_type)
                if (c, r) not in self._stroke_delta:
                    self._stroke_delta[(c, r)] = (old, new_type)
                else:
                    self._stroke_delta[(c, r)] = (
                        self._stroke_delta[(c, r)][0],
                        new_type,
                    )

    # ── Slope : génération de tiles ──────────────────────────────
    # Algo (Bresenham + règles de pentes GBA) déporté dans core.collision_slopes
    # — pure géométrie, sans dépendance UI.

    def _slope_tiles_for(
        self,
        sc: int,
        sr: int,
        ec: int,
        er: int,
    ) -> list[tuple[int, int, int]]:
        return slope_tiles_for(self._mode, sc, sr, ec, er)


_BG_TILE = 8


class SceneInpaintingTool(BaseTool):
    """Peinture par palette d'un layer BG (réassignation SE_PALBANK par tuile).

    mode : "inpaint_brush" (pinceau 8×8) | "inpaint_rect" (sélection rectangulaire).
    Clic gauche = peindre la banque active ; clic droit = effacer l'override.
    L'état (layer actif, banque de peinture, raster) vit dans
    `view.inpainting_controller`.
    """

    _PREVIEW_FILL = QColor(120, 180, 255, 60)
    _PREVIEW_BORDER = QColor(120, 180, 255, 220)

    def __init__(self, view: GBAView, mode: str):
        super().__init__(view)
        self._mode = mode
        self._erase = False
        self._anchor: Optional[tuple[int, int]] = None  # (col,row) pour le rect
        self._preview: QGraphicsRectItem | None = None

    # ── Cycle de vie ─────────────────────────────────────────────
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        if self._mode == "inpaint_rect":
            self._preview = QGraphicsRectItem(0, 0, 0, 0)
            self._preview.setBrush(QBrush(self._PREVIEW_FILL))
            self._preview.setPen(QPen(self._PREVIEW_BORDER, 0))
            self._preview.setZValue(60)
            self._preview.setVisible(False)
            self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    # ── Helpers ──────────────────────────────────────────────────
    def _ctrl(self):
        return getattr(self._view, "inpainting_controller", None)

    @staticmethod
    def _tile(pos: QPointF) -> tuple[int, int]:
        return int(pos.x() // _BG_TILE), int(pos.y() // _BG_TILE)

    # ── Événements ───────────────────────────────────────────────
    def on_press(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True  # consommé (évite le rubber band) même si rien à peindre
        self._erase = e.button() == Qt.MouseButton.RightButton
        ctrl.begin_stroke()
        col, row = self._tile(pos)
        if self._mode == "inpaint_rect":
            self._anchor = (col, row)
            self._update_preview(col, row)
        else:
            ctrl.inpaint_tile(col, row, erase=self._erase)
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True
        buttons = e.buttons()
        pressing = buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        col, row = self._tile(pos)
        if self._mode == "inpaint_rect" and self._anchor is not None:
            self._update_preview(col, row)
        elif self._mode == "inpaint_brush" and pressing:
            ctrl.inpaint_tile(col, row, erase=self._erase)
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True
        if self._mode == "inpaint_rect" and self._anchor is not None:
            ac, ar = self._anchor
            ec, er = self._tile(pos)
            for r in range(min(ar, er), max(ar, er) + 1):
                for c in range(min(ac, ec), max(ac, ec) + 1):
                    ctrl.inpaint_tile(c, r, erase=self._erase)
            self._anchor = None
            if self._preview:
                self._preview.setVisible(False)
        ctrl.end_stroke()
        return True

    def _update_preview(self, col: int, row: int):
        if not self._preview or self._anchor is None:
            return
        ac, ar = self._anchor
        x0, y0 = min(ac, col) * _BG_TILE, min(ar, row) * _BG_TILE
        w = (abs(col - ac) + 1) * _BG_TILE
        h = (abs(row - ar) + 1) * _BG_TILE
        self._preview.setRect(x0, y0, w, h)
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

    Le geste est celui de `SceneInpaintingTool` en mode rect — ancre au press,
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
        "text":  (128, 32),    # une boîte de dialogue basse plausible
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

    @staticmethod
    def _snap(pos: QPointF) -> tuple[int, int]:
        return (int(pos.x()) // _BG_TILE) * _BG_TILE, (int(pos.y()) // _BG_TILE) * _BG_TILE

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
        if w <= _BG_TILE and h <= _BG_TILE:      # simple clic
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
            self._preview.setRect(x, y, w, h)
            self._preview.setVisible(True)

    def on_leave(self):
        if self._preview and self._anchor is None:
            self._preview.setVisible(False)
