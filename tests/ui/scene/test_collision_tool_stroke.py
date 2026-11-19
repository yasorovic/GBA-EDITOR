"""La surface Collision passe par les gestes communs ; la pente garde son geste propre."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from core.history import get_history
from core.models.collision_tiles import (
    TILE_EMPTY,
    TILE_ONEWAY_LEFT,
    TILE_ONEWAY_UP,
    TILE_SLOPE_L,
    TILE_SOLID,
)
from ui.scene_manager.canvas_tools import CollisionSlopeTool, GridPaintTool
from ui.scene_manager.grid_paint_surface import GridPaintSurface


class _Overlay:
    def __init__(self):
        self.tiles: dict = {}

    def scene_to_tile(self, x, y):
        return int(x // 8), int(y // 8)

    def tile_at(self, col, row):
        return self.tiles.get((col, row), TILE_EMPTY)

    def set_tile(self, col, row, tile):
        self.tiles[(col, row)] = tile

    def set_preview(self, _tiles):
        pass

    def update(self):
        pass

    def get_map(self):
        return [[self.tile_at(col, row) for col in range(16)] for row in range(4)]


class _Signal:
    def emit(self):
        pass


class _View:
    def __init__(self):
        self.collision_overlay = _Overlay()
        self.collision_painted = _Signal()


class _Event:
    def __init__(self, button=Qt.MouseButton.LeftButton, held=Qt.MouseButton.LeftButton):
        self._button, self._held = button, held

    def button(self):
        return self._button

    def buttons(self):
        return self._held


def _surface(view):
    overlay = view.collision_overlay
    return GridPaintSurface("Collision", 8, changed=overlay.update,
                            read=overlay.tile_at, write=overlay.set_tile)


def _solid(view):
    return {cell for cell, tile in view.collision_overlay.tiles.items() if tile == TILE_SOLID}


def test_un_glisser_rapide_ne_laisse_pas_de_trou(qapp):
    view = _View()
    tool = GridPaintTool(view, _surface(view), "brush", TILE_SOLID, None)

    tool.on_press(QPointF(1, 1), _Event())
    tool.on_move(QPointF(8 * 10 + 1, 1), _Event())
    tool.on_release(QPointF(8 * 10 + 1, 1), _Event())

    assert _solid(view) == {(col, 0) for col in range(11)}


def test_un_coup_de_pinceau_est_une_entree_d_historique_qui_s_annule_seule(qapp):
    view = _View()
    tool = GridPaintTool(view, _surface(view), "brush", TILE_SOLID, None)
    history = get_history()
    history.clear()

    for strokes in range(16):
        tool.on_press(QPointF(8 * strokes + 1, 1), _Event())
        tool.on_release(QPointF(8 * strokes + 1, 1), _Event())

    assert len(_solid(view)) == 16
    undone = 0
    while history.undo():
        undone += 1
    assert undone == 16
    assert _solid(view) == set()
    history.clear()


def test_effacer_toute_la_collision_est_une_entree_d_historique_qui_la_rend(qapp):
    from types import SimpleNamespace
    from ui.scene_manager.scene_canvas import SceneEditor

    view = _View()
    overlay = view.collision_overlay
    for cell in ((0, 0), (3, 1), (5, 3)):
        overlay.set_tile(*cell, TILE_SOLID)
    saved = []
    canvas = SimpleNamespace(_gba_scene=SimpleNamespace(collision_overlay=overlay),
                             _on_collision_painted=lambda: saved.append(True))
    history = get_history()
    history.clear()

    SceneEditor._on_clear_collision(canvas)

    assert _solid(view) == set() and saved
    history.undo()
    assert _solid(view) == {(0, 0), (3, 1), (5, 3)}
    history.clear()


def test_une_face_a_sens_unique_est_une_valeur_du_pinceau_commun(qapp):
    for tile in (TILE_ONEWAY_UP, TILE_ONEWAY_LEFT):
        view = _View()
        tool = GridPaintTool(view, _surface(view), "brush", tile, None)
        tool.on_press(QPointF(12, 4), _Event())
        tool.on_move(QPointF(28, 4), _Event())
        tool.on_release(QPointF(28, 4), _Event())

        assert {cell: value for cell, value in view.collision_overlay.tiles.items()} == {
            (1, 0): tile, (2, 0): tile, (3, 0): tile,
        }

        erase = Qt.MouseButton.RightButton
        tool.on_press(QPointF(12, 4), _Event(erase, erase))
        tool.on_release(QPointF(12, 4), _Event(erase, erase))
        assert view.collision_overlay.tile_at(1, 0) == TILE_EMPTY


def test_le_trait_de_pente_reste_un_geste_propre_a_la_collision(qapp):
    view = _View()
    tool = CollisionSlopeTool(view, "collision_slope")

    tool.on_press(QPointF(1, 2 * 8 + 1), _Event())
    tool.on_move(QPointF(2 * 8 + 1, 1), _Event())
    tool.on_release(QPointF(2 * 8 + 1, 1), _Event())

    assert view.collision_overlay.tiles == {
        (0, 2): TILE_SLOPE_L,
        (1, 1): TILE_SLOPE_L,
        (2, 0): TILE_SLOPE_L,
    }
