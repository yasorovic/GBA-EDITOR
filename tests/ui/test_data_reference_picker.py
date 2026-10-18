"""Le sélecteur filtrable écrit une référence seulement au choix explicite."""
import pytest
from PyQt6.QtWidgets import QPushButton

from core.history import CommandHistory
from core.models.data_table import DataColumn, DataTable
from core.project import Project
from ui.common.widgets import ScriptPickerPopup
from ui.data_editor import data_grid_panel


@pytest.fixture
def grid(qapp, tmp_path, monkeypatch):
    history = CommandHistory()
    monkeypatch.setattr(data_grid_panel, "get_history", lambda: history)
    project = Project.create(tmp_path / "Game", "Game")
    table = DataTable(name="Items", columns=[DataColumn("visual", "sprite")],
                      rows=[{"visual": "Missing"}])
    project.data_tables.append(table)
    panel = data_grid_panel.DataGridPanel()
    panel.load_project(project)
    panel.show_table(table.name)
    monkeypatch.setattr(panel, "choices_for", lambda _: ["Hero", "Enemy"])
    panel.resize(800, 400)
    panel.show()
    qapp.processEvents()
    yield panel, table, history
    panel.close()


def _open(panel, qapp):
    panel._tbl.edit(panel._model.index(0, 0))
    qapp.processEvents()
    popup = panel._tbl.findChild(ScriptPickerPopup)
    assert popup is not None and popup.isVisible()
    return popup


def test_filtrer_et_choisir_passe_par_l_historique(grid, qapp):
    panel, table, history = grid
    popup = _open(panel, qapp)
    assert popup._search.hasFocus()
    popup._search.setText("ene")
    qapp.processEvents()
    matches = [popup._list_layout.itemAt(i).widget()
               for i in range(popup._list_layout.count())]
    buttons = [w for w in matches if isinstance(w, QPushButton)]
    assert [b.text() for b in buttons] == ["Enemy"]
    buttons[0].click()
    assert table.rows[0]["visual"] == "Enemy"
    history.undo()
    assert table.rows[0]["visual"] == "Missing"


def test_fermer_preserve_une_reference_absente(grid, qapp):
    panel, table, _ = grid
    popup = _open(panel, qapp)
    popup.close()
    qapp.processEvents()
    assert table.rows[0]["visual"] == "Missing"


def test_le_choix_vide_efface_la_reference(grid, qapp):
    panel, table, _ = grid
    popup = _open(panel, qapp)
    popup._on_pick("")
    assert table.rows[0]["visual"] == ""


def test_un_popup_obsolete_n_ecrit_pas_apres_rechargement(grid, qapp):
    panel, table, _ = grid
    popup = _open(panel, qapp)
    panel.reload()
    popup._on_pick("Enemy")
    assert table.rows[0]["visual"] == "Missing"
