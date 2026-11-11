"""Le sélecteur filtrable écrit une référence seulement au choix explicite."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from core.history import CommandHistory
from core.models.data_table import DataColumn, DataTable
from core.project import Project
from ui.common.widgets import PickerPopup
from ui.data_editor import data_table_panel


@pytest.fixture
def table_panel(qapp, tmp_path, monkeypatch):
    history = CommandHistory()
    monkeypatch.setattr(data_table_panel, "get_history", lambda: history)
    project = Project.create(tmp_path / "Game", "Game")
    table = DataTable(name="Items", columns=[DataColumn("visual", "sprite")],
                      rows=[{"visual": "Missing"}])
    project.data_tables.append(table)
    panel = data_table_panel.DataTablePanel()
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
    popup = panel._tbl.findChild(PickerPopup)
    assert popup is not None and popup.isVisible()
    return popup


def _pick(popup, value):
    """Un clic sur la ligne qui porte `value`."""
    row = [e.value for e in popup._entries].index(value)
    popup._list.itemClicked.emit(popup._list.item(row))


def test_filtrer_et_choisir_passe_par_l_historique(table_panel, qapp):
    panel, table, history = table_panel
    popup = _open(panel, qapp)
    assert popup._search.hasFocus()
    popup._search.setText("ene")
    qapp.processEvents()
    assert [e.label for e in popup.visible_entries()] == ["Enemy"]
    _pick(popup, "Enemy")
    assert table.rows[0]["visual"] == "Enemy"
    history.undo()
    assert table.rows[0]["visual"] == "Missing"


def test_fermer_preserve_une_reference_absente(table_panel, qapp):
    panel, table, _ = table_panel
    popup = _open(panel, qapp)
    popup.close()
    qapp.processEvents()
    assert table.rows[0]["visual"] == "Missing"


def test_le_choix_vide_efface_la_reference(table_panel, qapp):
    panel, table, _ = table_panel
    popup = _open(panel, qapp)
    _pick(popup, "")
    assert table.rows[0]["visual"] == ""


def test_un_popup_obsolete_n_ecrit_pas_apres_rechargement(table_panel, qapp):
    panel, table, _ = table_panel
    popup = _open(panel, qapp)
    panel.reload()
    _pick(popup, "Enemy")
    assert table.rows[0]["visual"] == "Missing"


def _create_button(popup):
    return next(b for b in popup.findChildren(QPushButton) if b is popup._btn_new)


def test_creer_un_texte_depuis_la_cellule_en_un_seul_pas(table_panel, qapp):
    panel, table, history = table_panel
    table.columns[0].type = "text"
    panel.reload()
    popup = _open(panel, qapp)
    _create_button(popup).click()
    qapp.processEvents()
    project = panel._project
    assert table.rows[0]["visual"] == "text_Items_01"
    assert project.get_text("text_Items_01") is not None
    history.undo()
    assert table.rows[0]["visual"] == "Missing"
    assert project.get_text("text_Items_01") is None
    history.redo()
    assert table.rows[0]["visual"] == "text_Items_01" and project.get_text("text_Items_01") is not None


def test_creer_un_asset_cite_le_nom_cree(table_panel, qapp, monkeypatch):
    panel, table, history = table_panel
    table.columns[0].type = "palette"
    panel.reload()
    monkeypatch.setattr(data_table_panel, "create_referenced_asset", lambda project, kind: "NewPalette")
    popup = _open(panel, qapp)
    _create_button(popup).click()
    qapp.processEvents()
    assert table.rows[0]["visual"] == "NewPalette"


def test_pas_de_creation_pour_un_sprite(table_panel, qapp):
    panel, _table, _history = table_panel
    assert _open(panel, qapp)._btn_new is None


def _click(panel, qapp, row=0, column=0):
    from PyQt6.QtTest import QTest
    index = panel._model.index(row, column)
    QTest.mouseClick(panel._tbl.viewport(), Qt.MouseButton.LeftButton,
                     pos=panel._tbl.visualRect(index).center())
    qapp.processEvents()


def test_premier_clic_selectionne_second_clic_edite(table_panel, qapp):
    panel, _table, _history = table_panel
    _click(panel, qapp)
    assert panel._tbl.currentIndex().row() == 0 and panel._tbl.findChild(PickerPopup) is None
    _click(panel, qapp)
    popup = panel._tbl.findChild(PickerPopup)
    assert popup is not None and popup.isVisible()


def test_double_clic_ouvre_un_seul_selecteur(table_panel, qapp):
    """La suite réelle d'un double clic : appui, relâchement, double-clic, relâchement."""
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent
    panel, _table, _history = table_panel
    viewport = panel._tbl.viewport()
    position = QPointF(panel._tbl.visualRect(panel._model.index(0, 0)).center())
    left, none = Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    for kind, buttons in ((QEvent.Type.MouseButtonPress, left), (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
                          (QEvent.Type.MouseButtonDblClick, left), (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        qapp.sendEvent(viewport, QMouseEvent(kind, position, viewport.mapToGlobal(position), left, buttons, none))
        qapp.processEvents()
    assert len(panel._tbl.findChildren(PickerPopup)) == 1
