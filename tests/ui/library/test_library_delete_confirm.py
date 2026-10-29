"""Supprimer depuis une library : pas de fenêtre pour un asset que rien ne cite (annulable) ; une question quand il est encore utilisé."""
from __future__ import annotations

import pytest
from ui.common.popup import MessageBox as QMessageBox

from core.history import get_history


@pytest.fixture
def panel(qapp, tmp_path):
    from core.models.scene import Scene
    from core.project import Project
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel

    project = Project(tmp_path / "jeu")
    for name in ("Title", "Shop", "Arena"):
        project.scenes.append(Scene(name=name))
    panel = SceneLibraryPanel()
    panel.load_project(project)
    get_history().clear()
    yield panel, project
    get_history().clear()


def _tree(panel):
    from ui.common.asset_kinds import SCENES
    return panel._library._trees[SCENES.label]


def _spy(monkeypatch, answer):
    asked = []

    def question(parent, title, text, *rest):
        asked.append(text)
        return answer
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def test_an_unused_scene_is_deleted_without_a_window(panel, monkeypatch):
    panel, project = panel
    asked = _spy(monkeypatch, QMessageBox.StandardButton.No)                     # même si on répondait non, rien n'est demandé

    _tree(panel)._delete(project.scenes.get("Shop"))

    assert asked == [] and project.scenes.get("Shop") is None
    get_history().undo()
    assert project.scenes.get("Shop") is not None                                # et Ctrl+Z la rend


def test_a_scene_still_in_use_asks_once_and_says_why(panel, monkeypatch):
    panel, project = panel
    project.settings.start_scene = "Arena"
    asked = _spy(monkeypatch, QMessageBox.StandardButton.No)

    _tree(panel)._delete(project.scenes.get("Arena"))

    assert len(asked) == 1 and "start scene" in asked[0]
    assert project.scenes.get("Arena") is not None                                # refusé : elle est toujours là


def test_confirming_deletes_a_scene_in_use(panel, monkeypatch):
    panel, project = panel
    project.settings.start_scene = "Arena"
    _spy(monkeypatch, QMessageBox.StandardButton.Yes)

    _tree(panel)._delete(project.scenes.get("Arena"))

    assert project.scenes.get("Arena") is None


def test_a_batch_asks_only_if_one_of_them_is_in_use(panel, monkeypatch):
    panel, project = panel
    asked = _spy(monkeypatch, QMessageBox.StandardButton.Yes)

    _tree(panel)._delete_many([project.scenes.get("Title"), project.scenes.get("Shop")])
    assert asked == [] and [s.name for s in project.scenes] == ["Arena"]

    get_history().undo()                                                          # un seul Ctrl+Z pour tout le lot
    assert sorted(s.name for s in project.scenes) == ["Arena", "Shop", "Title"]

    project.settings.start_scene = "Title"
    _tree(panel)._delete_many([project.scenes.get("Title"), project.scenes.get("Shop")])
    assert len(asked) == 1 and "Title" in asked[0]


def test_deleting_says_in_the_status_bar_that_ctrl_z_undoes(panel, monkeypatch):
    from core.command_dispatcher import get_dispatcher
    panel, project = panel
    messages = []
    get_dispatcher().on("status_message", messages.append)
    _spy(monkeypatch, QMessageBox.StandardButton.Yes)

    _tree(panel)._delete(project.scenes.get("Shop"))
    _tree(panel)._delete_many([project.scenes.get("Title"), project.scenes.get("Arena")])

    assert messages == ["Deleted 1 item. Ctrl+Z undoes.", "Deleted 2 items. Ctrl+Z undoes."]
