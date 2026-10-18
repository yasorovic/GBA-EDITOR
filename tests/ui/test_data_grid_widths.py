"""Les largeurs de colonnes tirées par l'auteur survivent aux rechargements de la grille."""
from core.models.data_table import DataColumn, DataTable
from core.project import Project
from ui.data_editor import data_grid_panel


def _panel(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    table = DataTable(name="Items", columns=[DataColumn("price", "int"), DataColumn("rare", "bool")],
                      rows=[{"price": 12}, {"price": 30}])
    project.data_tables.append(table)
    panel = data_grid_panel.DataGridPanel()
    panel.resize(900, 500)
    panel.load_project(project)
    panel.show_table(table.name)
    panel.show()
    return panel, table


def test_une_largeur_tiree_survit_a_un_rechargement_et_a_un_redimensionnement(qapp, tmp_path):
    panel, _table = _panel(tmp_path)
    panel._tbl.setColumnWidth(0, 333)            # le geste de l'auteur

    panel.reload()
    panel.resize(1100, 500)

    assert panel._tbl.columnWidth(0) == 333
    panel.close()


def test_sans_geste_les_colonnes_remplissent_la_largeur(qapp, tmp_path):
    panel, _table = _panel(tmp_path)
    before = panel._tbl.columnWidth(0)

    panel.resize(1400, 500)

    assert panel._tbl.columnWidth(0) > before
    panel.close()


def test_une_autre_table_repart_de_la_largeur_pleine(qapp, tmp_path):
    panel, table = _panel(tmp_path)
    panel._tbl.setColumnWidth(0, 333)
    other = DataTable(name="Other", columns=[DataColumn("a", "int"), DataColumn("b", "int")], rows=[{}])
    panel._project.data_tables.append(other)

    panel.show_table(other.name)

    assert panel._tbl.columnWidth(0) != 333
    panel.close()
