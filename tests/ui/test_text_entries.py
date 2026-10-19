"""L'édition intégrée garde le curseur, les balises et la bonne langue."""
import pytest
from PyQt6.QtGui import QTextCursor

from core.history import get_history
from core.project import Project
from core.models.settings import Language
from ui.text_editor.text_panel import TextPanel
from ui.text_editor.text_table import COL_KEY


@pytest.fixture
def entries(qapp, tmp_path):
    project = Project(tmp_path / 'game')
    project.project_dir.mkdir(parents=True)
    first = project.new_text(content='Hello', path=['Main'])
    second = project.new_text(content='World', path=['Main'])
    panel = TextPanel()
    panel.resize(1100, 550)
    panel.load_project(project)
    panel.show()
    qapp.processEvents()
    get_history().clear()
    yield panel, project, first, second
    panel.close()
    get_history().clear()


def put(text, *labels):
    """Pose une clé et ses libellés ensemble : la clé porte la structure."""
    from core.models.text import key_segment
    text.key = '_'.join(key_segment(label) for label in labels)


def adopt(project, *texts):
    """Les suites sont dérivées des clés : rien à enregistrer."""


def entry(panel, text):
    table = panel._table
    return table._tree.itemWidget(table._row_of(text), COL_KEY)


def test_folder_navigation_reuses_editors_and_updates_counts(entries, qapp):
    from ui.common.labels import label
    panel, project, first, second = entries
    put(second, 'Other')
    panel.refresh()
    card = entry(panel, first)
    card.edit.moveCursor(QTextCursor.MoveOperation.End)
    position = card.edit.textCursor().position()
    for path in (['Main'], ['Other'], [], ['Main']):
        panel.set_folder_filter(path)
        qapp.processEvents()
        assert entry(panel, first) is card
        assert card.edit.textCursor().position() == position
        assert panel._table._row_of(first).isHidden() == (path == ['Other'])
        assert panel._table._row_of(second).isHidden() == (path == ['Main'])
        if path:
            assert panel._table._crumb_count.text() == label('txttbl.text_count', n=1)
    card.edit.insertPlainText('!')
    assert first.content == 'Hello!'
    get_history().undo()
    assert card.edit.toPlainText() == 'Hello'


def test_selection_only_restyles_entries_that_change(entries, monkeypatch):
    from ui.common.theme import C
    panel, project, first, second = entries
    card = entry(panel, first)
    card.set_selected(True)
    assert f'background:{C.BG_BASE}' in card.styleSheet()
    assert f'border-left:2px solid {C.ACCENT}' in card.styleSheet()
    calls = []
    monkeypatch.setattr(card, 'setStyleSheet', calls.append)
    card.set_selected(True)
    assert not calls
    card.set_selected(False)
    assert len(calls) == 1


def test_editor_growth_updates_row_geometry(entries, qapp):
    panel, project, first, second = entries
    table = panel._table
    card = entry(panel, first)
    row = table._row_of(first)
    old_height = table._tree.visualItemRect(row).height()
    card.edit.insertPlainText('\n'.join(['Line'] * 8))
    for _ in range(3):
        qapp.processEvents()
    assert table._tree.visualItemRect(row).height() > old_height
    assert table._tree.visualItemRect(row).height() == row.sizeHint(COL_KEY).height()


@pytest.mark.parametrize('grouped', [False, True])
def test_text_field_collapse_preserves_content_cursor_and_refresh_state(entries, qapp, grouped):
    panel, project, first, second = entries
    if grouped:
        put(first, 'Dialogue', 'Page01')
        put(second, 'Dialogue', 'Page02')
        adopt(project, first, second)
        panel.refresh()
    table = panel._table
    card = entry(panel, first)
    card.edit.moveCursor(QTextCursor.MoveOperation.End)
    position = card.edit.textCursor().position()
    height = table._tree.visualItemRect(table._row_of(first)).height()
    card.collapse.click()
    qapp.processEvents()
    assert card.field.isHidden()
    assert card.remove.isVisible() and card.collapse.isVisible()
    assert card.markup.isHidden()
    assert table._tree.visualItemRect(table._row_of(first)).height() < height
    card.collapse.click()
    qapp.processEvents()
    assert card.field.isVisible()
    assert card.edit.toPlainText() == first.content == 'Hello'
    assert card.edit.textCursor().position() == position
    assert table._tree.visualItemRect(table._row_of(first)).height() == height
    card.collapse.click()
    panel.refresh()
    qapp.processEvents()
    assert entry(panel, first).field.isHidden()
    assert not get_history().can_undo
    table.focus_entry(first.id)
    qapp.processEvents()
    assert entry(panel, first).field.isVisible()
    assert not entry(panel, first).collapse.isChecked()










@pytest.mark.parametrize('grouped', [False, True])
def test_retired_editor_focus_is_ignored_after_refresh(entries, grouped):
    from PyQt6 import sip
    panel, project, first, second = entries
    if grouped:
        put(first, 'Dialogue', 'Page01')
        put(second, 'Dialogue', 'Page02')
        adopt(project, first, second)
        panel.refresh()
    table = panel._table
    old_entry = entry(panel, first)
    old_row = table._row_of(first)
    old_header = table._number_groups[0][1] if grouped else None
    table._signature_shown = None     # une structure inchangée se met à jour en place : on force la reconstruction
    panel.refresh()
    assert sip.isdeleted(old_row)
    # Qt garde encore l'ancien widget en vie jusqu'au DeferredDelete.
    assert not sip.isdeleted(old_entry)
    if old_header is not None:
        sip.delete(old_header)
    table.select_by_ids([second.id])
    current_card = entry(panel, second)
    old_entry.activated.emit()
    assert table.selected_texts() == [second]
    assert entry(panel, second) is current_card
    if grouped:
        _, header = table._number_groups[0]
        current_card.activated.emit()
        assert header.markup._edit is current_card.edit


def test_focus_activation_survives_selection_refresh(entries):
    panel, project, first, second = entries
    put(first, 'Dialogue', 'Page01')
    put(second, 'Dialogue', 'Page02')
    adopt(project, first, second)
    panel.refresh()
    table = panel._table
    table.clear_selection()
    old_entry = entry(panel, first)
    def refresh_on_selection(texts):
        table.selection_changed.disconnect(refresh_on_selection)
        table.refresh()
    table.selection_changed.connect(refresh_on_selection)
    old_entry.activated.emit()
    assert table._row_of(first) is not None








def test_inline_edit_keeps_cursor_and_other_entry_and_can_undo(entries, qapp):
    panel, project, first, second = entries
    card = entry(panel, first)
    assert panel._bench.isHidden()
    assert not panel._bench.isEnabled()
    card.edit.setFocus()
    card.edit.moveCursor(QTextCursor.MoveOperation.End)
    card.edit.insertPlainText('!\nNext')
    assert first.content == 'Hello!\nNext'
    assert second.content == 'World'
    assert entry(panel, first) is card
    assert card.edit.textCursor().position() == len(first.content)
    get_history().undo()
    assert first.content == 'Hello'
    assert card.edit.toPlainText() == 'Hello'
    get_history().redo()
    assert card.edit.toPlainText() == 'Hello!\nNext'


def test_existing_markup_toolbar_edits_selected_source(entries):
    panel, project, first, second = entries
    card = entry(panel, first)
    card.edit.selectAll()
    card.markup._insert('wave', None, preselect=False)
    assert first.content == '[wave]Hello[/wave]'
    assert second.content == 'World'
    card.markup._insert('wave', None, preselect=False)
    assert first.content == 'Hello'


def test_translation_starts_empty_and_never_overwrites_source(entries, qapp):
    panel, project, first, second = entries
    put(first, 'PressStart', 'Page0')
    put(second, 'PressStart', 'Page2')
    adopt(project, first, second)
    project.settings.source_lang = Language(code='en', name='English')
    project.settings.languages = [Language(code='fr', name='French')]
    panel.refresh()
    panel._bench._lang_tabs.picked.emit('fr')
    assert len(panel._table._number_groups) == 1
    card = entry(panel, first)
    assert card.edit.toPlainText() == ''
    card.edit.insertPlainText('Bonjour')
    assert project.translations['fr'][first.id] == 'Bonjour'
    assert first.content == 'Hello'
    get_history().undo()
    assert card.edit.toPlainText() == ''




def test_group_toolbar_targets_focused_block_and_filtered_block(entries, qapp):
    panel, project, first, second = entries
    put(first, 'PressStart', 'Page0')
    put(second, 'PressStart', 'Page2')
    adopt(project, first, second)
    panel.refresh()
    table = panel._table
    row, header = table._number_groups[0]
    card = entry(panel, second)
    card.edit.setFocus()
    qapp.processEvents()
    card.edit.selectAll()
    header.markup._insert('wave', None, preselect=False)
    assert second.content == '[wave]World[/wave]'
    assert first.content == 'Hello'
    assert header.active.text() == '#02'
    get_history().undo()
    assert card.edit.toPlainText() == 'World'
    table._search.setText('PressStart_Page0')
    assert table._row_of(second).isHidden()
    assert not row.isHidden()
    assert header.markup._edit is entry(panel, first).edit
    table._search.setText('no_match')
    assert row.isHidden()
    assert not header.markup.isEnabled()


def test_renaming_member_ungroups_and_undo_regroups(entries):
    panel, project, first, second = entries
    put(first, 'PressStart', 'Page0')
    put(second, 'PressStart', 'Page2')
    adopt(project, first, second)
    panel.refresh()
    panel.rename_key(second, 'other_text')
    assert second.key == 'other_text'
    assert second.content == 'World'
    get_history().undo()
    assert second.key == 'PressStart_Page2'
    assert len(panel._table._number_groups) == 1


def test_numbered_page_paths_share_header_but_keep_folder_filter(entries):
    panel, project, first, second = entries
    put(first, 'SCRArena', 'textbox2', 'Page01')
    put(second, 'SCRArena', 'textbox2', 'Page02')
    third = project.new_text(content='Third', path=['SCRArena'])
    put(third, 'SCRArena', 'textbox2', 'Page03')
    adopt(project, first, second, third)
    panel.refresh()
    table = panel._table
    assert len(table._number_groups) == 1
    row, header = table._number_groups[0]
    assert row.childCount() == 3
    assert [table._tree.itemWidget(row.child(i), COL_KEY).number.text()
            for i in range(3)] == ['#01', '#02', '#03']
    table.set_folder_filter(['SCRArena', 'textbox2'])
    row, header = table._number_groups[0]
    assert all(not row.child(i).isHidden() for i in range(3))
    table.set_folder_filter(first.path)
    row, header = table._number_groups[0]
    assert not row.isHidden()
    assert not table._row_of(first).isHidden()
    assert table._row_of(second).isHidden()
    assert table._row_of(third).isHidden()
    assert header.markup._edit is entry(panel, first).edit
    assert first.path == ['SCRArena', 'textbox2', 'Page01']
    assert second.path == ['SCRArena', 'textbox2', 'Page02']


def test_group_prefix_rename_updates_references_and_undoes_once(entries, qapp):
    from core.models.ui_region import UILayout, UIText
    panel, project, first, second = entries
    put(first, 'PressStart', 'Page01')
    put(second, 'PressStart', 'Page02')
    adopt(project, first, second)
    layout = UILayout(name='hud')
    zones = [UIText(name=f'text_{i}', text_key=text.key)
             for i, text in enumerate((first, second))]
    layout.elements.extend(zones)
    project.ui_layouts.append(layout)
    (project.assets_dir / "scripts").mkdir(parents=True, exist_ok=True)
    script = (project.assets_dir / "scripts") / 'main.lua'
    script.write_text('text:draw(0, 0, "PressStart_Page01")\ntext:draw(0, 8, "PressStart_Page02")\n', encoding='utf-8')
    panel.refresh()
    _, header = panel._table._number_groups[0]
    header.key.setText('start_prompt')
    header.key.editingFinished.emit()
    qapp.processEvents()
    assert [first.key, second.key] == ['start_prompt_Page01', 'start_prompt_Page02']
    assert [zone.text_key for zone in zones] == [first.key, second.key]
    assert 'PressStart_' not in script.read_text(encoding='utf-8')
    get_history().undo()
    assert [first.key, second.key] == ['PressStart_Page01', 'PressStart_Page02']
    assert [zone.text_key for zone in zones] == [first.key, second.key]
    assert 'start_prompt_' not in script.read_text(encoding='utf-8')
    assert not get_history().can_undo
    get_history().redo()
    assert [first.key, second.key] == ['start_prompt_Page01', 'start_prompt_Page02']






def test_finder_uses_folder_for_multiple_texts_even_without_subfolders(entries):
    from ui.text_editor.text_finder import TextFinder, _ROLE_IS_FOLDER
    panel, project, first, second = entries
    finder = TextFinder()
    finder.load_project(project)
    root = finder._tree.topLevelItem(0)
    shared = root.child(0)
    assert shared.data(0, _ROLE_IS_FOLDER) is True
    assert shared.childCount() == 1
    put(first, 'Main', 'Page01')
    put(second, 'Main', 'Page02')
    finder.refresh()
    shared = finder._tree.topLevelItem(0).child(0)
    assert shared.data(0, _ROLE_IS_FOLDER) is True
    assert shared.childCount() == 2
    assert shared.child(0).data(0, _ROLE_IS_FOLDER) is False
    finder.close()


def test_page_keys_form_a_group_without_registering_a_suite(entries):
    panel, project, first, second = entries
    third = project.new_text(content='Third', path=['Main'])
    put(first, 'Textbox', 'Page01')
    put(second, 'Textbox', 'Page05')
    put(third, 'Textbox', 'Page02')
    panel.refresh()
    table = panel._table
    assert len(table._number_groups) == 1
    row, header = table._number_groups[0]
    assert [row.child(i).text(COL_KEY) for i in range(row.childCount())] == [
        'Textbox_Page01', 'Textbox_Page02', 'Textbox_Page05']


def test_dragging_a_page_grip_reorders_pages_by_renaming_their_keys(entries, qapp):
    panel, project, first, second = entries
    third = project.new_text(content='Third', path=['Main'])
    put(first, 'Main', 'Page01')
    put(second, 'Main', 'Page02')
    put(third, 'Main', 'Page03')
    panel.refresh()
    qapp.processEvents()
    table = panel._table
    assert entry(panel, first).grip.isVisible() or not entry(panel, first).grip.isHidden()

    target_entry = entry(panel, first)
    y = target_entry.mapToGlobal(target_entry.rect().center()).y()
    table._entry_drop('Main', third.id, y)               # « Page03 » lâchée sur « Page01 »
    qapp.processEvents()

    assert (third.key, first.key, second.key) == ('Main_Page01', 'Main_Page02', 'Main_Page03')
    get_history().undo()
    qapp.processEvents()
    assert (first.key, second.key, third.key) == ('Main_Page01', 'Main_Page02', 'Main_Page03')


def test_reordering_pages_keeps_the_widgets_and_swaps_their_entries(entries):
    panel, project, first, second = entries
    put(first, 'Dialogue', 'Page01')
    put(second, 'Dialogue', 'Page02')
    adopt(project, first, second)
    panel.refresh()
    table = panel._table
    group = table._number_groups[0][0]
    rows = [group.child(i) for i in range(group.childCount())]
    widgets = [table._entry_of(row) for row in rows]
    from core.text_sequences import group_texts, reordered_keys
    pages = group_texts(project, table._number_groups[0][1].prefix)
    project.rename_text_keys(reordered_keys(pages, 0, 1))
    panel.refresh()
    # mêmes lignes, mêmes widgets, entrées échangées
    assert [group.child(i) for i in range(2)] == rows
    assert [table._entry_of(row) for row in rows] == widgets
    now = [row.data(0, 256) for row in rows]
    assert now == group_texts(project, table._number_groups[0][1].prefix)
    assert [w._text for w in widgets] == now
    assert [w.edit.toPlainText() for w in widgets] == [t.content for t in now]
