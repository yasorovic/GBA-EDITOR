"""Une clé n'est jamais à la fois une entrée et une séquence : le second texte promeut le premier."""
import pytest

from core.history import get_history
from core.project import Project
from ui.text_editor.text_panel import TextPanel


@pytest.fixture
def panel(qapp, tmp_path):
    project = Project(tmp_path / 'game')
    project.project_dir.mkdir(parents=True)
    panel = TextPanel()
    panel.load_project(project)
    get_history().clear()
    yield panel
    panel.close()
    get_history().clear()


def keys(panel):
    return sorted(t.key for t in panel._project.texts)


def test_add_promotes_the_lone_text_then_extends_the_sequence(panel):
    panel._add_text(['SCR'])
    assert keys(panel) == ['SCR_text']
    panel._add_text(['SCR'])
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2']
    panel._add_text(['SCR'])
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2', 'SCR_text_3']


def test_promotion_is_one_undo_step(panel):
    panel._add_text(['SCR'])
    panel._add_text(['SCR'])
    get_history().undo()
    assert keys(panel) == ['SCR_text']
    get_history().redo()
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2']


def test_plus_on_a_lone_entry_promotes_it(panel):
    panel._add_text(['SCR'])
    lone = panel._project.texts[0]
    panel._edit_sequence_entry(None, lone.id, 'add')
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2']


def test_duplicate_promotes_the_source(panel):
    panel._add_text(['SCR'])
    panel.duplicate_text(panel._project.texts[0])
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2']
    panel.duplicate_text(panel._project.texts[0])
    assert keys(panel) == ['SCR_text_1', 'SCR_text_2', 'SCR_text_3']
