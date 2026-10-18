"""Le lien est un état de la table ; une ligne est identifiée par sa clé."""
from core.project import Project
from core.models.data_table import DataTable, DataColumn
from core.models.ids import new_id
from core.text_sequences import sequences, group_keys
from core.text_table_link import LinkTableCmd, UnlinkTableCmd, link_state


def _setup(tmp_path):
    p = Project(tmp_path / 'game')
    texts = [p.new_text(content=str(n), path=['Arena', 'Dialogue', f'Page{n:02}']) for n in (1, 2, 3)]
    table = DataTable(name='Dialogue', columns=[DataColumn('line', 'text'), DataColumn('portrait', 'int')])
    table.id = new_id(set())
    table.rows = [{'line': texts[0].key, 'portrait': 10}, {'line': 'manual_key', 'portrait': 99}]
    p.data_tables.append(table)
    prefix = texts[0].key.rsplit('_Page', 1)[0]
    return p, table, texts, prefix


def test_link_projects_rows_by_key_and_unlink_keeps_them(tmp_path):
    p, table, texts, prefix = _setup(tmp_path)
    assert list(sequences(p)) == [prefix] and link_state(p, table) is None
    first_row = table.rows[0]
    LinkTableCmd(p, table, prefix, 'line').execute()
    assert [r['line'] for r in table.rows] == [t.key for t in texts]
    assert table.rows[0] is first_row and first_row['portrait'] == 10
    assert link_state(p, table) == 'current'
    assert DataTable.from_dict(table.to_dict()).text_link == table.text_link
    UnlinkTableCmd(p, table).execute()
    assert link_state(p, table) is None and len(table.rows) == 3


def test_page_removed_is_out_of_sync_then_updated_and_undone(tmp_path):
    p, table, texts, prefix = _setup(tmp_path)
    LinkTableCmd(p, table, prefix, 'line').execute()
    table.rows[2]['portrait'] = 33
    p.texts.remove(texts[1])
    assert group_keys(p, prefix) == [texts[0].key, texts[2].key]
    assert link_state(p, table) == 'different'
    cmd = LinkTableCmd(p, table, prefix, 'line')
    cmd.execute()
    assert [r['portrait'] for r in table.rows] == [10, 33] and link_state(p, table) == 'current'
    cmd.undo()
    assert len(table.rows) == 3 and table.rows[2]['portrait'] == 33


def test_sequences_are_derived_from_any_numeric_suffix(tmp_path):
    from core.text_sequences import sequence_of, consumers
    assert sequence_of('A_1') == ('A', 1) and sequence_of('A_B_Page07') == ('A_B', 7)
    assert sequence_of('A_Page') is None and sequence_of('Page01') is None
    p, table, texts, prefix = _setup(tmp_path)
    p.new_text(content='x', path=['Solo', 'Intro_1'])
    p.new_text(content='y', path=['Shop', 'Item_2'])
    p.new_text(content='z', path=['Shop', 'Item_10'])
    assert set(sequences(p)) == {prefix, 'Shop_Item'} and consumers(p, prefix) == []
    LinkTableCmd(p, table, prefix, 'line').execute()
    assert consumers(p, prefix) == [table]


def test_linked_table_follows_text_changes_through_history(tmp_path):
    from core.history import CommandHistory, Command
    from core.text_table_link import TableSync

    class RemoveText(Command):
        def __init__(self, p, t): self.p, self.t = p, t
        def execute(self): self.p.texts.remove(self.t)
        def undo(self): self.p.texts.append(self.t)

    p, table, texts, prefix = _setup(tmp_path)
    LinkTableCmd(p, table, prefix, 'line').execute()
    table.rows[1]['portrait'] = 33
    h = CommandHistory()
    h.after_execute = TableSync(p)
    h.push(RemoveText(p, texts[1]))
    assert [r['line'] for r in table.rows] == [texts[0].key, texts[2].key]
    h.undo()
    assert link_state(p, table) == 'current' and table.rows[1]['portrait'] == 33
    h.redo()
    assert len(table.rows) == 2


def test_create_linked_table_is_one_undoable_step(tmp_path):
    from core.history import CommandHistory
    from core.text_sequences import consumers
    from core.text_table_link import create_linked_table, free_tables
    p, table, texts, prefix = _setup(tmp_path)
    assert free_tables(p) == [table]
    h = CommandHistory()
    h.push(create_linked_table(p, prefix))
    [made] = consumers(p, prefix)
    assert [r['line'] for r in made.rows] == [t.key for t in texts]
    h.undo()
    assert consumers(p, prefix) == [] and made not in list(p.data_tables)


def test_unrelated_command_never_touches_table_rows(tmp_path):
    from core.history import CommandHistory, Command
    from core.text_table_link import TableSync

    class Noop(Command):
        def execute(self): pass
        def undo(self): pass

    p, table, texts, prefix = _setup(tmp_path)
    LinkTableCmd(p, table, prefix, 'line').execute()
    p.texts.remove(texts[1])          # changed outside the history: table is now stale
    h = CommandHistory()
    h.after_execute = TableSync(p)
    h.push(Noop())
    assert len(table.rows) == 3


def test_command_that_changed_texts_before_being_pushed_still_syncs(tmp_path):
    from core.history import CommandHistory, Command
    from core.text_table_link import TableSync

    class Noop(Command):
        def execute(self): pass
        def undo(self): pass

    p, table, texts, prefix = _setup(tmp_path)
    LinkTableCmd(p, table, prefix, 'line').execute()
    h = CommandHistory()
    h.after_execute = TableSync(p)
    new = p.new_text(content='4', path=['Arena', 'Dialogue', 'Page04'])   # applied BEFORE the push, as the Text screen does
    h.push(Noop())
    assert [r['line'] for r in table.rows][-1] == new.key
