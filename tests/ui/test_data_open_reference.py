"""Une cellule de référence mène à l'élément qu'elle cite : bouton de l'inspecteur Données, `select_text` de l'écran Texte."""
import pytest

from core.history import get_history
from core.models.data_table import DataColumn
from core.project import Project
from ui.data_editor.data_inspector_panel import DataInspectorPanel
from ui.text_editor.text_panel import TextPanel
from ui.text_editor.text_table import COL_KEY


@pytest.fixture
def project(tmp_path):
    project = Project(tmp_path / 'game')
    project.project_dir.mkdir(parents=True)
    return project


def test_text_panel_shows_a_text_hidden_by_the_filters(qapp, project):
    first = project.new_text(content='Hello', path=['Main'])
    second = project.new_text(content='World', path=['Other'])
    panel = TextPanel()
    panel.resize(1100, 550)
    panel.load_project(project)
    panel.show()
    panel.set_folder_filter(['Main'])
    qapp.processEvents()
    assert panel._table._row_of(second).isHidden()
    panel.show_text(second)
    qapp.processEvents()
    assert not panel._table._row_of(second).isHidden()
    assert panel._table.selected_texts() == [second]
    assert panel._selection == [second]
    assert not panel._table._tree.itemWidget(panel._table._row_of(second), COL_KEY).edit.hasFocus()
    panel.close()
    get_history().clear()


def test_inspector_offers_to_open_only_an_existing_target(qapp, project):
    project.new_text(content='Hello', path=['Main'])
    key = project.texts[0].key
    inspector = DataInspectorPanel()
    inspector.load_project(project)
    asked = []
    inspector.open_requested.connect(lambda family, name: asked.append((family, name)))
    text_column = DataColumn(name='line', type='text')

    inspector.set_selection(text_column, key)
    assert inspector._open_target == ('texts', key)
    inspector._open.click()
    assert asked == [('texts', key)]

    for column, value in ((text_column, ''), (text_column, 'unknown_key'),
                          (DataColumn(name='hp', type='int'), 3), (None, None)):
        inspector.set_selection(column, value)
        assert inspector._open_target is None
