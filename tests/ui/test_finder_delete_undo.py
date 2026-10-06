"""Supprimer depuis le finder, puis Ctrl+Z : l'arbre doit suivre le modèle.

Le finder se rafraîchissait après SA suppression, mais Ctrl+Z passe par
l'historique, qui ne le connaît pas : la ressource revenait dans le projet et
jamais dans la liste affichée.
"""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QMessageBox

from core.history import get_history


def _names(tree) -> list[str]:
    out: list[str] = []
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop(0)
        out.append(it.text(0).split()[0])
        stack.extend(it.child(n) for n in range(it.childCount()))
    return sorted(out)


@pytest.fixture
def panel(qapp, tmp_path, monkeypatch):
    from core.models.scene import Scene
    from core.project import Project
    from ui.scene_manager.assets_finder_panel import AssetsFinderPanel

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    project = Project(tmp_path / "jeu")
    for name in ("Title", "Shop", "Arena"):
        project.scenes.append(Scene(name=name))
    panel = AssetsFinderPanel()
    panel.load_project(project)
    get_history().clear()
    yield panel, project
    get_history().clear()


def _tree(panel):
    from ui.common.asset_kinds import SCENES
    return panel._finder._trees[SCENES.label]


def test_supprimer_puis_annuler_remet_la_scene_dans_l_arbre(panel):
    panel, project = panel
    tree = _tree(panel)
    shop = project.scenes.get("Shop")

    tree._delete(shop)
    assert _names(tree) == ["Arena", "Title"]

    get_history().undo()
    assert _names(tree) == ["Arena", "Shop", "Title"]


def test_refaire_retire_a_nouveau_la_scene_de_l_arbre(panel):
    panel, project = panel
    tree = _tree(panel)
    tree._delete(project.scenes.get("Shop"))
    get_history().undo()
    get_history().redo()
    assert _names(tree) == ["Arena", "Title"]


def test_suppression_en_lot_s_annule_d_un_seul_geste(panel):
    panel, project = panel
    tree = _tree(panel)
    tree._delete_many([project.scenes.get("Shop"), project.scenes.get("Arena")])
    assert _names(tree) == ["Title"]

    get_history().undo()
    assert _names(tree) == ["Arena", "Shop", "Title"]
