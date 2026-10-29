"""Le pinceau de collision : trait continu, pinceau 16 aligné sur sa grille, un coup de pinceau = une entrée d'historique."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from core.history import get_history
from core.models.collision_tiles import TILE_EMPTY, TILE_SOLID
from ui.scene_manager.canvas_tools import CollisionTool


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

    def set_hover(self, _hover):
        pass


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


def _solid(view):
    return {cell for cell, tile in view.collision_overlay.tiles.items() if tile == TILE_SOLID}


def test_le_pinceau_16_se_pose_sur_la_grille_de_16(qapp):
    view = _View()
    tool = CollisionTool(view, "collision_16")

    tool.on_press(QPointF(8 * 3 + 1, 8 * 5 + 1), _Event())
    tool.on_release(QPointF(8 * 3 + 1, 8 * 5 + 1), _Event())

    assert _solid(view) == {(2, 4), (3, 4), (2, 5), (3, 5)}


def test_un_glisser_rapide_ne_laisse_pas_de_trou(qapp):
    view = _View()
    tool = CollisionTool(view, "collision_8")

    tool.on_press(QPointF(1, 1), _Event())
    tool.on_move(QPointF(8 * 10 + 1, 1), _Event())        # un seul événement qui saute dix tuiles
    tool.on_release(QPointF(8 * 10 + 1, 1), _Event())

    assert _solid(view) == {(col, 0) for col in range(11)}


def test_un_coup_de_pinceau_est_une_entree_d_historique_qui_s_annule_seule(qapp):
    view = _View()
    tool = CollisionTool(view, "collision_8")
    history = get_history()
    history.clear()

    for strokes in range(16):
        tool.on_press(QPointF(8 * strokes + 1, 1), _Event())
        tool.on_release(QPointF(8 * strokes + 1, 1), _Event())
    assert len(_solid(view)) == 16

    undone = 0
    while history.undo():
        undone += 1

    assert undone == 16 and _solid(view) == set()
    history.clear()


def test_effacer_toute_la_collision_est_une_entree_d_historique_qui_la_rend(qapp):
    from types import SimpleNamespace
    from ui.scene_manager.scene_canvas import SceneEditor

    view = _View()
    overlay = view.collision_overlay
    overlay.get_map = lambda: [[overlay.tile_at(col, row) for col in range(6)] for row in range(4)]
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
