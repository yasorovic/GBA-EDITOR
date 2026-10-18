"""Les éditeurs de la liste des textes ne sont construits que pour les lignes proches de l'écran."""
from core.project import Project
from ui.text_editor.text_table import COL_KEY, TextTable


def _table(tmp_path, count=150):
    project = Project(tmp_path / "game")
    texts = [project.new_text(content=f"line {i}", path=[f"Scene{i}", "Line"]) for i in range(count)]
    table = TextTable()
    table.resize(900, 600)
    table.show()
    table.load_project(project)
    return table, texts


def _built(table):
    return sum(1 for row in table._iter_rows() if table._tree.itemWidget(row, COL_KEY) is not None)


def test_seules_les_lignes_proches_de_l_ecran_ont_un_editeur(qapp, tmp_path):
    table, _texts = _table(tmp_path)

    assert 0 < _built(table) < 40
    table.close()


def test_defiler_construit_les_editeurs_qui_arrivent(qapp, tmp_path):
    table, _texts = _table(tmp_path)
    before = _built(table)

    bar = table._tree.verticalScrollBar()
    bar.setValue(bar.maximum())

    assert _built(table) > before
    table.close()


def test_une_ligne_non_construite_relit_le_modele_a_sa_construction(qapp, tmp_path):
    table, texts = _table(tmp_path)
    last = texts[-1]
    row = table._row_of(last)
    assert table._tree.itemWidget(row, COL_KEY) is None

    last.content = "changed elsewhere"
    table.sync_entry(last)

    assert table._tree.itemWidget(row, COL_KEY) is None
    assert table._entry_of(row).edit.toPlainText() == "changed elsewhere"
    table.close()


def test_focus_entry_construit_la_cible(qapp, tmp_path):
    table, texts = _table(tmp_path)

    table.focus_entry(texts[-1].id)

    assert table._tree.itemWidget(table._row_of(texts[-1]), COL_KEY) is not None
    table.close()
