"""Séquences dérivées des clés : détection, boîtes qui les suivent, suppression."""
from core.models.scene import Scene
from core.models.ui_region import UILayout, UITextbox
from core.project import Project
from core.text_sequences import editor_rows, next_key, consumers, sequences
from ui.text_editor.text_commands import DeleteTextsCmd


def _project(tmp_path):
    project = Project(tmp_path / "game")
    project.root.mkdir()
    return project


def test_ordinary_key_collisions_do_not_create_a_group(tmp_path):
    project = _project(tmp_path)
    first = project.new_text(path=["Dialogue"])
    second = project.new_text(path=["Dialogue"])

    assert (first.key, second.key) == ("Dialogue", "Dialogue_2")
    assert sequences(project) == {}
    assert all(prefix is None for _text, _path, prefix in editor_rows(project))


def test_next_key_keeps_the_width_of_the_last_number(tmp_path):
    project = _project(tmp_path)
    assert next_key(project, "Solo") == "Solo_1"
    for n in (1, 2):
        project.new_text(path=["Intro", f"Page{n:02}"])
    assert next_key(project, "Intro") == "Intro_Page03"


def test_textbox_follows_its_sequence_and_is_a_consumer(tmp_path):
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Box", f"Page{n:02}"]) for n in (1, 2, 3)]
    box = UITextbox(name="box", sequence_prefix="Arena_Box")
    project.ui_layouts.append(UILayout(name="HUD", elements=[box]))

    assert project.textbox_pages(box) == texts
    assert project.region_text(box) is texts[0] and project.region_texts(box) == texts
    assert consumers(project, "Arena_Box") == [box]

    project.texts.remove(texts[0])
    assert project.region_text(box) is texts[1]


def test_prefix_rename_carries_the_box(tmp_path):
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Box", f"Page{n:02}"]) for n in (1, 2)]
    box = UITextbox(name="box", sequence_prefix="Arena_Box")
    project.ui_layouts.append(UILayout(name="HUD", elements=[box]))

    project.rename_text_keys([(t, t.key.replace("Arena_Box", "Arena_Talk")) for t in texts])
    assert box.sequence_prefix == "Arena_Talk"
    assert project.textbox_pages(box) == texts


def test_text_deletion_clears_text_key_and_translation_and_undoes(tmp_path):
    project = _project(tmp_path)
    first = project.new_text("First", path=["Arena", "box"])
    box = UITextbox(name="box", text_key=first.key)
    project.ui_layouts.append(UILayout(name="HUD", elements=[box]))
    project.scenes.append(Scene(name="Arena"))
    project.translations = {"fr": {first.id: "Premier"}}

    command = DeleteTextsCmd(project, [first])
    command.execute()
    assert project.texts == [] and box.text_key == "" and project.translations["fr"] == {}

    command.undo()
    assert project.texts == [first] and box.text_key == first.key
    assert project.translations["fr"] == {first.id: "Premier"}


def test_legacy_page_ids_become_a_sequence_or_the_first_page(tmp_path):
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Box", f"Page{n:02}"]) for n in (1, 2)]
    other = project.new_text("Solo", path=["Elsewhere"])
    whole = UITextbox.from_dict({"kind": "textbox", "name": "whole", "page_ids": [t.id for t in texts]})
    partial = UITextbox.from_dict({"kind": "textbox", "name": "partial", "page_ids": [texts[1].id, other.id]})
    project.ui_layouts.append(UILayout(name="HUD", elements=[whole, partial]))

    project.migrate_legacy_pages()

    assert whole.sequence_prefix == "Arena_Box"
    assert partial.sequence_prefix == "" and partial.text_key == texts[1].key


def test_add_page_turns_a_free_box_into_a_sequence_then_extends_it(tmp_path):
    from core.history import CommandHistory
    from core.textbox_sequence_commands import AddTextboxPageCmd
    project = _project(tmp_path)
    box = UITextbox(name="Dialog", preview_text="Hello", preview_is_literal=True)
    project.ui_layouts.append(UILayout(name="HUD", elements=[box]))
    history = CommandHistory()

    history.push(AddTextboxPageCmd(project, box, "Arena"))
    pages = project.textbox_pages(box)
    assert box.sequence_prefix and [t.content for t in pages] == ["Hello", ""]
    assert [t.key for t in pages] == [f"{box.sequence_prefix}_Page01", f"{box.sequence_prefix}_Page02"]

    history.push(AddTextboxPageCmd(project, box, "Arena"))
    assert [t.key for t in project.textbox_pages(box)][-1] == f"{box.sequence_prefix}_Page03"

    history.undo()
    history.undo()
    assert box.sequence_prefix == "" and box.preview_text == "Hello" and project.texts == []


def test_deleting_a_page_of_a_linked_sequence_renumbers_the_rest_and_undoes(tmp_path):
    from core.models.data_table import DataTable, DataColumn
    from core.text_table_link import LinkTableCmd
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Dialogue", f"Page{n:02}"]) for n in range(1, 6)]
    table = DataTable(name="Lines", columns=[DataColumn("line", "text"), DataColumn("portrait", "int")])
    project.data_tables.append(table)
    LinkTableCmd(project, table, "Arena_Dialogue", "line").execute()
    for n, row in enumerate(table.rows):
        row["portrait"] = (n + 1) * 10
    keys = [t.key for t in texts]

    command = DeleteTextsCmd(project, [texts[1]])
    command.execute()

    assert [t.key for t in texts if t in project.texts] == [
        "Arena_Dialogue_Page01", "Arena_Dialogue_Page02", "Arena_Dialogue_Page03", "Arena_Dialogue_Page04"]
    assert [(r["line"], r["portrait"]) for r in table.rows] == [
        ("Arena_Dialogue_Page01", 10), ("Arena_Dialogue_Page02", 30),
        ("Arena_Dialogue_Page03", 40), ("Arena_Dialogue_Page04", 50)]

    assert [t.path[-1] for t in texts if t in project.texts] == ["Page01", "Page02", "Page03", "Page04"]

    command.undo()
    assert [t.key for t in texts] == keys
    assert [t.path[-1] for t in texts] == ["Page01", "Page02", "Page03", "Page04", "Page05"]
    assert [(r["line"], r["portrait"]) for r in table.rows] == list(zip(keys, (10, 20, 30, 40, 50)))


def test_deleting_a_page_of_a_free_sequence_keeps_the_numbers(tmp_path):
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Dialogue", f"Page{n:02}"]) for n in range(1, 4)]
    DeleteTextsCmd(project, [texts[0]]).execute()
    assert [t.key for t in texts[1:]] == ["Arena_Dialogue_Page02", "Arena_Dialogue_Page03"]


def test_delete_sequence_removes_texts_empties_the_table_and_unlinks_the_box(tmp_path):
    from core.models.data_table import DataTable, DataColumn
    from core.text_table_link import LinkTableCmd
    from ui.text_editor.text_commands import DeleteSequenceCmd
    project = _project(tmp_path)
    texts = [project.new_text(f"T{n}", path=["Arena", "Dialogue", f"Page{n:02}"]) for n in (1, 2, 3)]
    other = project.new_text("keep", path=["Arena", "Other"])
    table = DataTable(name="Lines", columns=[DataColumn("line", "text"), DataColumn("portrait", "int")])
    project.data_tables.append(table)
    LinkTableCmd(project, table, "Arena_Dialogue", "line").execute()
    box = UITextbox(name="box", sequence_prefix="Arena_Dialogue")
    project.ui_layouts.append(UILayout(name="HUD", elements=[box]))

    command = DeleteSequenceCmd(project, "Arena_Dialogue")
    command.execute()
    assert project.texts == [other] and table.rows == [] and box.sequence_prefix == ""
    assert table.text_link                                  # la table reste liée, simplement vide

    command.undo()
    assert [t.key for t in project.texts if t in texts] == [t.key for t in texts]
    assert [r["line"] for r in table.rows] == [t.key for t in texts]
    assert box.sequence_prefix == "Arena_Dialogue" and len(project.textbox_pages(box)) == 3
