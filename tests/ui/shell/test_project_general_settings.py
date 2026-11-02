from core.history import get_history
from core.project import Project
from ui.scene_manager.inspectors.project_settings_dialog import GeneralPanel, ProjectSettingsDialog


def test_general_is_the_first_project_settings_category(qapp, tmp_path):
    dialog = ProjectSettingsDialog(Project.create(tmp_path / "Game", "Game"))

    assert dialog._CATEGORIES[0] == "General"
    assert dialog._list.currentRow() == 0


def test_general_panel_renames_the_project(qapp, tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    panel = GeneralPanel(project)

    panel._ed_name.setText("Platformer")
    panel._ed_name.editingFinished.emit()

    assert project.settings.name == "Platformer"
    assert (project.root / "Platformer.project").exists()


def test_general_panel_puts_back_the_name_when_the_rename_is_refused(qapp, tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    panel = GeneralPanel(project)

    panel._ed_name.setText("a/b")
    panel._ed_name.editingFinished.emit()

    assert panel._ed_name.text() == "Game"
    assert project.settings.name == "Game"


def test_general_panel_edits_author_with_undo(qapp, tmp_path):
    history = get_history()
    history.clear()
    project = Project.create(tmp_path / "Game", "Game")
    panel = GeneralPanel(project)

    panel._ed_author.setText("Yasorovic")
    panel._ed_author.editingFinished.emit()
    assert project.settings.author == "Yasorovic"

    history.undo()
    assert project.settings.author == ""
    assert panel._ed_author.text() == ""
