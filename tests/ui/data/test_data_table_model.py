"""La grille Données lit le modèle du projet sans recopier ses cellules."""
from PyQt6.QtCore import Qt

from core.models.data_table import DataColumn, DataTable
from ui.data_editor.data_table_model import DataTableModel


def _table():
    return DataTable(
        name="Items",
        columns=[
            DataColumn("enabled", "bool"),
            DataColumn("score", "int"),
            DataColumn("caption", "text"),
        ],
        rows=[{"enabled": False, "score": 4, "caption": "hello"}],
    )


def test_le_modele_expose_schema_indices_et_valeurs(qapp):
    table = _table()
    model = DataTableModel(lambda *_: True, lambda key: f"preview:{key}")
    model.set_table(table)

    assert model.rowCount() == 1
    assert model.columnCount() == 3
    assert model.headerData(1, Qt.Orientation.Horizontal) == "score"
    assert model.headerData(0, Qt.Orientation.Vertical) == "1"
    assert model.data(model.index(0, 1)) == "4"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked


def test_le_modele_confie_les_ecritures_au_chemin_d_historique(qapp):
    table = _table()
    writes = []

    def write(row, column, value):
        writes.append((row, column, value))
        table.rows[row][table.columns[column].name] = value
        return True

    model = DataTableModel(write, lambda key: key)
    model.set_table(table)

    assert model.setData(model.index(0, 1), "12")
    assert model.setData(model.index(0, 0), Qt.CheckState.Checked,
                         Qt.ItemDataRole.CheckStateRole)
    assert writes == [(0, 1, 12), (0, 0, True)]
    assert table.rows[0]["score"] == 12
    assert table.rows[0]["enabled"] is True


def test_un_reset_relit_la_table_sans_items_intermediaires(qapp):
    table = _table()
    model = DataTableModel(lambda *_: True, lambda key: key)
    model.set_table(table)
    table.rows.append({"score": 8})
    model.set_table(table)

    assert model.rowCount() == 2
    assert model.data(model.index(1, 0), Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert model.data(model.index(1, 1)) == "8"

