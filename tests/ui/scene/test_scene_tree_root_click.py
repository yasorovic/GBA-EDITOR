"""Cliquer la ligne racine de l'arbre de scène montre l'inspecteur de la SCÈNE (et non celui du projet)."""
from __future__ import annotations

from types import SimpleNamespace

from core.models.scene import Scene
from ui.scene_manager import scene_tree_panel as module


class _Item:
    def __init__(self, kind):
        self._kind = kind

    def data(self, _column, role):
        return self._kind if role == module._ROLE_TYPE else None


def test_la_ligne_racine_publie_la_scene_sur_le_bus(qapp, monkeypatch):
    scene = Scene(name="Village")
    published = []
    monkeypatch.setattr(module, "get_bus", lambda: SimpleNamespace(select=published.append))

    module._ActiveSceneTree._on_click(SimpleNamespace(_scene=scene), _Item(module.T_SCENE), 0)

    assert published == [scene]
