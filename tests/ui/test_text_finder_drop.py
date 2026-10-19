"""Le drop du Finder passe par une commande et suit les références du texte."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QDragLeaveEvent
from PyQt6.QtWidgets import QApplication, QMenu

from core.history import get_history
from core.models.text import MAX_DEPTH, Text, moved_text_paths
from core.models.ui_region import UILayout, UIText
from core.project import Project
from ui.text_editor.text_finder import _ROLE_PATH
from ui.text_editor.text_editor_screen import TextEditorScreen
from ui.text_editor.text_panel import TextPanel
from ui.text_editor.text_table import COL_KEY
from ui.common.labels import label


def find_item(tree, path):
    def visit(item):
        if tuple(item.data(0, _ROLE_PATH) or ()) == tuple(path):
            return item
        for i in range(item.childCount()):
            match = visit(item.child(i))
            if match is not None:
                return match
        return None
    return visit(tree.topLevelItem(0))


def test_finder_uses_one_label_per_key_segment(qapp, tmp_path):
    project = Project(tmp_path / 'game')
    text = project.new_text(content='$score_cpu', path=['SCR_Arena', 'ScoreCpu'])
    screen = TextEditorScreen()
    screen.load_project(project)
    get_history().clear()
    try:
        old_key, old_path = text.key, list(text.path)
        screen._texts.rename_key(text, 'scr_arena_score_cpu')
        assert text.path == ['scr', 'arena', 'score', 'cpu']
        leaf = find_item(screen._text_finder._tree, text.path)
        assert leaf.text(0) == 'cpu  (1)'
        assert leaf.toolTip(0) == 'scr › arena › score › cpu'
        screen._text_finder._tree.setCurrentItem(leaf)
        assert not screen._texts._table._row_of(text).isHidden()
        get_history().undo()
        assert text.key == old_key
        assert text.path == old_path
        get_history().redo()
        assert text.path == ['scr', 'arena', 'score', 'cpu']
    finally:
        screen.close()
        get_history().clear()


def test_finder_context_menu_targets_clicked_text_and_folder(qapp, tmp_path, monkeypatch):
    project = Project(tmp_path / 'game')
    first = project.new_text(content='First', path=['Main', 'First'])
    second = project.new_text(content='Second', path=['Main', 'Second'])
    from ui.text_editor.text_finder import TextFinder
    finder = TextFinder()
    finder.load_project(project)
    finder.resize(300, 400)
    finder.show()
    finder._tree.expandAll()
    qapp.processEvents()
    created, duplicated, deleted = [], [], []
    finder.create_requested.connect(created.append)
    finder.duplicate_requested.connect(duplicated.append)
    finder.delete_requested.connect(deleted.append)

    wanted = ''
    def choose(menu, *_args):
        next(action for action in menu.actions() if action.text() == wanted).trigger()
    monkeypatch.setattr(QMenu, 'exec', choose)
    try:
        leaf = find_item(finder._tree, first.path)
        leaf_pos = finder._tree.visualItemRect(leaf).center()
        wanted = label('common.duplicate')
        finder._context_menu(leaf_pos)
        assert duplicated == [first]

        wanted = label('common.create')
        finder._context_menu(leaf_pos)
        assert created == [('Main',)]

        folder = find_item(finder._tree, ['Main'])
        wanted = label('common.delete')
        finder._context_menu(finder._tree.visualItemRect(folder).center())
        assert deleted == [[first, second]]
    finally:
        finder.close()




def test_hover_preserves_selection_filter_and_editors(qapp, tmp_path, monkeypatch):
    project = Project(tmp_path / 'game')
    source = project.new_text(content='Hello', path=['SceneA', 'Line'])
    target = project.new_text(content='Other', path=['SceneB', 'Existing'])
    screen = TextEditorScreen()
    screen.load_project(project)
    screen.resize(1200, 700)
    screen.show()
    panel, finder = screen._texts, screen._text_finder
    tree = finder._tree
    tree.expandAll()
    source_item = find_item(tree, source.path)
    tree.setCurrentItem(source_item)
    qapp.processEvents()
    card = panel._table._tree.itemWidget(panel._table._row_of(source), COL_KEY)
    calls = []
    original_refresh = panel._table.refresh
    def refresh(*args, **kwargs):
        calls.append(1)
        return original_refresh(*args, **kwargs)
    monkeypatch.setattr(panel._table, 'refresh', refresh)
    mime = tree.mimeData([source_item])
    folder = find_item(tree, ['SceneB'])
    pos = tree.visualItemRect(folder).center()
    try:
        enter = QDragEnterEvent(pos, Qt.DropAction.MoveAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), enter)
        for item in [folder, tree.topLevelItem(0)] * 3:
            move = QDragMoveEvent(tree.visualItemRect(item).center(), Qt.DropAction.MoveAction,
                                  mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(tree.viewport(), move)
            qapp.processEvents()
            assert move.isAccepted()
            assert tree._drop_target == tree.indexFromItem(item)
        assert finder.selected_path() == tuple(source.path)
        assert source_item.isSelected()
        assert panel._table._folder_filter == tuple(source.path)
        assert panel._table._tree.itemWidget(panel._table._row_of(source), COL_KEY) is card
        assert calls == []
        invalid = QDragMoveEvent(tree.visualItemRect(find_item(tree, target.path)).center(),
                                 Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), invalid)
        assert not invalid.isAccepted()
        assert not tree._drop_target.isValid()
        move = QDragMoveEvent(pos, Qt.DropAction.MoveAction, mime,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), move)
        assert tree._drop_target.isValid()
        QApplication.sendEvent(tree.viewport(), QDragLeaveEvent())
        assert not tree._drop_target.isValid()
        assert calls == []
        assert finder.selected_path() == tuple(source.path)
    finally:
        screen.close()


def test_trash_deletes_its_own_collapsed_text_and_syncs_finder_with_undo(qapp, tmp_path, monkeypatch):
    from ui.text_editor.text_panel import QMessageBox
    project = Project(tmp_path / 'game')
    first = project.new_text(content='First', path=['Main', 'First'])
    second = project.new_text(content='Second', path=['Main', 'Second'])
    project.rename_text_key(first, 'first')
    project.rename_text_key(second, 'second')
    screen = TextEditorScreen()
    screen.load_project(project)
    screen.show()
    qapp.processEvents()
    panel, finder = screen._texts, screen._text_finder
    get_history().clear()
    confirmations = []
    def confirm(*args):
        confirmations.append(args)
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, 'question', confirm)
    try:
        panel._table._tree.setCurrentItem(panel._table._row_of(first))
        assert panel._selection == [first]
        card = panel._table._tree.itemWidget(panel._table._row_of(second), COL_KEY)
        card.collapse.click()
        card.remove.click()
        qapp.processEvents()
        assert confirmations and 'second' in confirmations[0][2]
        assert project.texts == [first]
        assert find_item(finder._tree, second.path) is None
        get_history().undo()
        qapp.processEvents()
        assert project.texts == [first, second]
        assert find_item(finder._tree, second.path) is not None
        restored = panel._table._tree.itemWidget(panel._table._row_of(second), COL_KEY)
        assert restored.field.isHidden()
        get_history().redo()
        qapp.processEvents()
        assert project.texts == [first]
        assert find_item(finder._tree, second.path) is None
    finally:
        screen.close()
        get_history().clear()


@pytest.mark.parametrize('manual', [False, True])
def test_native_drop_rekeys_and_updates_links_then_undo_restores(qapp, tmp_path, manual):
    project = Project(tmp_path / 'game')
    project.project_dir.mkdir(parents=True)
    source = project.new_text(content='Hello', path=['SceneA', 'Line'])
    target = project.new_text(content='Other', path=['SceneB', 'Existing'])
    if manual:
        project.rename_text_key(source, 'custom_key')
    old_key, old_path = source.key, list(source.path)
    leaf = old_path[-1]            # le dernier niveau de la clé : « Line », ou « key » pour `custom_key`
    layout = UILayout(name='hud')
    zone = UIText(name='caption', text_key=old_key)
    layout.elements.append(zone)
    project.ui_layouts.append(layout)
    (project.assets_dir / "scripts").mkdir(parents=True, exist_ok=True)
    script = (project.assets_dir / "scripts") / 'main.lua'
    script.write_text(f'text:draw(0, 0, "{old_key}")\n', encoding='utf-8')
    screen = TextEditorScreen()
    screen.load_project(project)
    panel, finder = screen._texts, screen._text_finder
    screen.resize(1200, 700)
    screen.show()
    tree = finder._tree
    tree.expandAll()
    qapp.processEvents()
    get_history().clear()
    try:
        source_item = find_item(tree, source.path)
        folder = find_item(tree, ['SceneB'])
        mime = tree.mimeData([source_item])
        assert tree._drop_paths(mime, find_item(tree, target.path)) is None
        pos = tree.visualItemRect(folder).center()
        enter = QDragEnterEvent(pos, Qt.DropAction.MoveAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), enter)
        assert enter.isAccepted()
        move = QDragMoveEvent(pos, Qt.DropAction.MoveAction, mime,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), move)
        assert move.isAccepted()
        drop = QDropEvent(QPointF(pos), Qt.DropAction.MoveAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(), drop)
        assert drop.isAccepted()
        qapp.processEvents()
        assert source.path == ['SceneB', leaf]
        assert source.key == f'SceneB_{leaf}'
        assert source.content == 'Hello' and target.content == 'Other'
        assert zone.text_key == source.key
        assert source.key in script.read_text(encoding='utf-8')
        assert finder.selected_path() == ('SceneB', leaf)
        assert panel._table.selected_texts() == [source]
        get_history().undo()
        assert source.path == old_path
        assert source.key == old_key
        assert zone.text_key == old_key
        assert old_key in script.read_text(encoding='utf-8')
        assert finder.selected_path() == tuple(old_path)
        assert not get_history().can_undo
        get_history().redo()
        assert source.path == ['SceneB', leaf]
        assert zone.text_key == source.key == f'SceneB_{leaf}'
    finally:
        screen.close()
        get_history().clear()


def test_move_validation_rejects_leaf_cycles_same_parent_and_excess_depth():
    texts = [Text(key='A_Line'), Text(key='B_Other'), Text(key='_'.join(['Deep'] + [str(i) for i in range(2, MAX_DEPTH + 1)]))]
    assert not moved_text_paths(texts, [], ['B'])
    assert not moved_text_paths(texts, ['A'], ['A', 'Line'])
    assert not moved_text_paths(texts, ['A', 'Line'], ['A'])
    assert not moved_text_paths(texts, ['A', 'Line'], ['B', 'Other'])
    assert not moved_text_paths(texts, ['A'], ['Deep'] + [str(i) for i in range(2, MAX_DEPTH)])
    entries = moved_text_paths(texts, ['A', 'Line'], [])
    assert entries == [(texts[0], ['A', 'Line'], ['Line'])]


def test_moving_group_preserves_children_and_collision_never_overwrites(qapp, tmp_path):
    project = Project(tmp_path / 'game')
    first = project.new_text(content='One', path=['A', 'Group', '01'])
    second = project.new_text(content='Two', path=['A', 'Group', '02'])
    existing = project.new_text(content='Existing', path=['B', 'Group', '01'])
    panel = TextPanel()
    panel.load_project(project)
    get_history().clear()
    try:
        old = [(t.key, list(t.path)) for t in project.texts]
        panel.move_path(['A', 'Group'], ['B'])
        assert first.path == ['B', 'Group', '01', '2']
        assert second.path == ['B', 'Group', '02']
        assert len({t.key for t in project.texts}) == 3
        assert [t.content for t in project.texts] == ['One', 'Two', 'Existing']
        assert existing.key == old[2][0]
        get_history().undo()
        assert [(t.key, t.path) for t in project.texts] == old
    finally:
        panel.close()
        get_history().clear()


def test_a_folder_that_is_a_linked_sequence_gets_the_link_icon(qapp, tmp_path):
    from core.models.data_table import DataTable, DataColumn
    from core.text_table_link import LinkTableCmd
    project = Project(tmp_path / 'game')
    for n in (1, 2):
        project.new_text(content=str(n), path=['Arena', 'Box', f'Page{n:02}'])
    project.new_text(content='x', path=['Arena', 'Free', 'Page01'])
    project.new_text(content='y', path=['Arena', 'Free', 'Page02'])
    table = DataTable(name='Lines', columns=[DataColumn('line', 'text')])
    project.data_tables.append(table)
    LinkTableCmd(project, table, 'Arena_Box', 'line').execute()
    from ui.text_editor.text_finder import TextFinder
    finder = TextFinder()
    finder.load_project(project)
    try:
        tree = finder._tree
        linked, free = find_item(tree, ['Arena', 'Box']), find_item(tree, ['Arena', 'Free'])
        assert linked.icon(0).cacheKey() != free.icon(0).cacheKey()
        linked.setExpanded(not linked.isExpanded())          # replier/déplier garde l'icône
        qapp.processEvents()
        assert linked.icon(0).cacheKey() != free.icon(0).cacheKey()
        table2 = DataTable(name='More', columns=[DataColumn('line', 'text')])
        project.data_tables.append(table2)
        LinkTableCmd(project, table2, 'Arena_Free', 'line').execute()
        finder.refresh_links()                                # lier à chaud, sans reconstruire l'arbre
        assert free.icon(0).cacheKey() == linked.icon(0).cacheKey()
    finally:
        finder.close()
