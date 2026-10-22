"""« Voir les utilisations » d'un script, dans le Script Editor : la colonne droite alterne bibliothèque / utilisations."""
from __future__ import annotations

import pytest

from core.project import Project
from ui.script_editor.script_editor import ScriptEditorScreen


@pytest.fixture
def project(tmp_path) -> Project:
    project = Project.create(tmp_path / "Game", "Game")
    (project.user_library_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (project.user_library_dir / "scripts" / "hero.lua").write_text("-- hero\n", encoding="utf-8")
    project.scenes[0].script = "assets/scripts/hero.lua"
    return project


def test_the_uses_view_lists_a_scene_script_and_a_click_names_its_target(qapp, project):
    screen = ScriptEditorScreen()
    screen.load_project(project)
    targets = []
    screen.script_user_requested.connect(targets.append)

    screen._show_script_uses(str(project.user_library_dir / "scripts" / "hero.lua"))
    assert screen._right_column.currentWidget() is screen._uses_panel

    layout = screen._uses_panel._list_layout
    leaves = [layout.itemAt(i).widget() for i in range(layout.count())
              if layout.itemAt(i).widget() is not None and layout.itemAt(i).widget().height() == 22]
    assert len(leaves) == 1
    leaves[0].mousePressEvent(None)
    assert targets == [project.scenes[0]]


def test_closing_the_uses_view_brings_back_the_library(qapp, project):
    screen = ScriptEditorScreen()
    screen.load_project(project)
    screen._show_script_uses(str(project.user_library_dir / "scripts" / "hero.lua"))

    screen._uses_panel.close_requested.emit()

    assert screen._right_column.currentWidget() is screen._file_tree
