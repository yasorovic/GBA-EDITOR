"""Inspecteur de TextBox : un bloc par page, frappe sans saut de curseur, + et −."""
import pytest

from core.history import get_history
from core.models.ui_region import UILayout, UITextbox
from core.project import Project
from ui.scene_manager.inspectors.ui_inspector import UIInspector


@pytest.fixture
def inspector(qapp, tmp_path):
    project = Project(tmp_path / "game")
    project.root.mkdir()
    box = UITextbox(name="Dialog", preview_text="Hello", preview_is_literal=True)
    layout = UILayout(name="HUD", elements=[box])
    project.ui_layouts.append(layout)
    insp = UIInspector()
    insp.show()
    insp.load(layout, box, project, project.active_scene)
    get_history().clear()
    yield insp, project, box, layout
    insp.close()
    get_history().clear()


def test_typing_keeps_the_cursor_through_an_inspector_reload(inspector, qapp):
    insp, project, box, layout = inspector
    editor = insp._pages.blocks[0].editor
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    for char in "abc":
        editor.insertPlainText(char)
        insp.load(layout, box, project, project.active_scene)      # ce que fait `refresh_current`
    assert editor.toPlainText() == "Helloabc"
    assert editor.textCursor().position() == len("Helloabc")


def test_plus_makes_a_sequence_then_minus_removes_the_page(inspector, qapp, monkeypatch):
    insp, project, box, layout = inspector
    insp._on_page_add()
    qapp.processEvents()
    assert box.sequence_prefix and len(insp._pages.blocks) == 2
    assert [b.editor.toPlainText() for b in insp._pages.blocks] == ["Hello", ""]

    monkeypatch.setattr("ui.common.popup.MessageBox.question",
                        lambda *a, **k: __import__("ui.common.popup", fromlist=["MessageBox"])
                        .MessageBox.StandardButton.Yes)
    insp._on_page_remove(1)
    qapp.processEvents()
    assert len(insp._pages.blocks) == 1 and len(project.textbox_pages(box)) == 1
    get_history().undo()
    qapp.processEvents()
    assert len(project.textbox_pages(box)) == 2


def test_reordering_pages_swaps_key_numbers_and_the_table_follows(inspector, qapp):
    from core.models.data_table import DataTable, DataColumn
    from core.text_table_link import LinkTableCmd
    insp, project, box, layout = inspector
    insp._on_page_add()
    insp._on_page_add()
    qapp.processEvents()
    prefix = box.sequence_prefix
    pages = project.textbox_pages(box)
    for page, content in zip(pages, ("first", "second", "third")):
        page.content = content
    table = DataTable(name="Lines", columns=[DataColumn("line", "text"), DataColumn("portrait", "int")])
    project.data_tables.append(table)
    LinkTableCmd(project, table, prefix, "line").execute()
    for n, row in enumerate(table.rows):
        row["portrait"] = (n + 1) * 10
    insp.load(layout, box, project, project.active_scene)
    get_history().clear()
    from core.text_table_link import TableSync
    get_history().after_execute = TableSync(project)   # ce que le dispatcher branche dans l'éditeur
    try:
        _reorder_and_undo(insp, project, box, table, prefix, qapp)
    finally:
        get_history().after_execute = None


def _reorder_and_undo(insp, project, box, table, prefix, qapp):
    insp._on_page_reorder(2, 0)                       # « third » passe en tête
    qapp.processEvents()
    assert [t.content for t in project.textbox_pages(box)] == ["third", "first", "second"]
    assert [b.editor.toPlainText() for b in insp._pages.blocks] == ["third", "first", "second"]
    assert [(r["line"], r["portrait"]) for r in table.rows] == [
        (f"{prefix}_Page01", 30), (f"{prefix}_Page02", 10), (f"{prefix}_Page03", 20)]

    get_history().undo()
    qapp.processEvents()
    assert [t.content for t in project.textbox_pages(box)] == ["first", "second", "third"]
    assert [r["portrait"] for r in table.rows] == [10, 20, 30]
