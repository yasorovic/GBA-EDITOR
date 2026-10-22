"""Glisser un élément d'interface dans une AUTRE interface est refusé à voix haute, et l'arbre est reconstruit depuis le modèle."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import QTimer

from ui.scene_manager import scene_tree_panel as module


class _Item:
    def __init__(self, roles):
        self._roles = roles

    def data(self, _column, role):
        return self._roles.get(role)


def test_un_depot_dans_une_autre_interface_dit_non_et_rafraichit_l_arbre(qapp, monkeypatch):
    told, refreshed = [], []
    monkeypatch.setattr(module, "get_dispatcher", lambda: SimpleNamespace(status=told.append))
    monkeypatch.setattr(QTimer, "singleShot", staticmethod(lambda _ms, fn: fn()))
    hud, shop = object(), object()
    element = SimpleNamespace(name="slot1")
    dragged = _Item({module._ROLE_OBJ: element, module._ROLE_PATH: hud})
    target = _Item({module._ROLE_TYPE: module.T_UI_LAYOUT, module._ROLE_OBJ: shop})
    tree = SimpleNamespace(_panel=SimpleNamespace(refresh=lambda: refreshed.append(True)))

    module._ActiveSceneTree._handle_ui_drop(tree, dragged, target, QAbstractItemView.DropIndicatorPosition.OnItem)

    assert len(told) == 1 and refreshed == [True]
