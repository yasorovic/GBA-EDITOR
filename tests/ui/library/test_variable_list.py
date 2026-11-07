"""Tri et gestes de la liste des constantes/globales, sans réordonner les données du projet."""
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMenu, QWidget

from core.project import Project
from ui.common.labels import label
from ui.common.widgets import HoverIconButton, W
from ui.script_editor.script_library_panel import ScriptLibraryPanel
from ui.script_editor.var_table_panel import VarTablePanel


@pytest.mark.parametrize("kind", ["const", "global"])
def test_tri_nom_type_preserve_les_donnees_et_les_champs(qapp, tmp_path, kind):
    project = Project.create(tmp_path / "Game", "Game")
    entries = [project.add_variable(kind, name) for name in ("Zulu", "alpha", "Beta")]
    for entry, type_ in zip(entries, ("int", "bool", "u8")):
        entry.type = type_
    panel = VarTablePanel(kind)
    panel.set_project(project)
    assert [row.entry.name for row in panel._rows] == ["alpha", "Beta", "Zulu"]
    rows = {row.entry.name: row for row in panel._rows}
    panel._set_sort("type")
    assert [panel._layout.itemAt(i).widget().entry.name for i in range(3)] == ["alpha", "Zulu", "Beta"]
    assert all(panel._row_of(entry) is rows[entry.name] for entry in entries)
    assert list(panel._entries()) == entries
    # Une édition de type relance le tri, sans remplacer la ligne en cours.
    rows["Beta"]._combo.setCurrentText("int")
    assert [row.entry.name for row in panel._rows] == ["alpha", "Beta", "Zulu"]
    panel._set_sort("name")
    panel._rename(entries[0], "Aardvark")
    assert panel._rows[0] is rows["Zulu"]
    assert list(panel._entries()) == entries


def test_boutons_des_deux_sections_reutilisent_le_menu_de_disk(qapp, tmp_path, monkeypatch):
    project = Project.create(tmp_path / "Game", "Game")
    library = ScriptLibraryPanel()
    library.set_project(project)
    buttons = [button for button in library.findChildren(HoverIconButton) if button._icon_name == "sort"]
    assert len(buttons) == 2
    menus = []

    def choose_type(menu, position):
        actions = menu.actions()
        menus.append(([action.text() for action in actions], [action.isChecked() for action in actions]))
        actions[1].trigger()
        return actions[1]

    monkeypatch.setattr(QMenu, "exec", choose_type)
    buttons[0].click()
    assert library._constants_panel._sort == "type"
    assert library._globals_panel._sort == "name"
    buttons[1].click()
    assert library._globals_panel._sort == "type"
    assert menus == [([label("disk.sort_name"), label("vartbl.sort_type")], [True, False])] * 2


def test_menu_disk_conserve_ses_trois_criteres(qapp, monkeypatch):
    from ui.common.disk_view import show_sort_menu
    parent = QWidget()
    button = W.btn_sort()
    captured = []
    picked = []

    def choose_status(menu, position):
        actions = menu.actions()
        captured.extend((action.text(), action.isChecked()) for action in actions)
        actions[2].trigger()
        return actions[2]

    monkeypatch.setattr(QMenu, "exec", choose_status)
    show_sort_menu(parent, button, "extension", picked.append)
    assert captured == [(label("disk.sort_name"), False), (label("disk.sort_extension"), True),
                        (label("disk.sort_status"), False)]
    assert picked == ["status"]


@pytest.mark.parametrize("kind,count,reference", [("const", 1, "const.Score"),
    ("global", 1, "global.Score"), ("global", 3, "global.Score[1]")])
def test_clic_gauche_renomme_clic_central_insere(qapp, tmp_path, monkeypatch, kind, count, reference):
    project = Project.create(tmp_path / "Game", "Game")
    entry = project.add_variable(kind, "Score")
    if kind == "global":
        entry.count = count
    panel = VarTablePanel(kind)
    panel.set_project(project)
    panel.resize(360, 80)
    panel.show()
    qapp.processEvents()
    snippets = []
    panel.snippet_requested.connect(snippets.append)
    row = panel._rows[0]
    QTest.mouseClick(row._name_btn, Qt.MouseButton.MiddleButton)
    assert snippets == [reference] and not row._renaming
    QTest.mouseClick(row._name_btn, Qt.MouseButton.LeftButton)
    assert row._renaming and row._name_edit.isVisible()
    assert snippets == [reference]
    row._name_edit.setText("Renamed")
    QTest.keyClick(row._name_edit, Qt.Key.Key_Return)
    assert entry.name == "Renamed" and not row._renaming
    assert row._name_btn.text() == ("[] Renamed" if count > 1 else "Renamed")
    # L'insertion reste accessible au clic droit, sans entrée d'affectation.
    def pick_reference(menu, position):
        assert not any("=" in action.text() for action in menu.actions())
        return menu.actions()[0]
    monkeypatch.setattr(QMenu, "exec", pick_reference)
    panel._ctx_menu(entry, QPoint())
    assert snippets[-1] == reference.replace("Score", "Renamed")


def test_reperes_persistant_et_tableau_suivent_les_reglages(qapp, tmp_path, monkeypatch):
    project = Project.create(tmp_path / "Game", "Game")
    entry = project.add_variable("global", "Score")
    entry.persist = True
    entry.count = 3
    panel = VarTablePanel("global")
    panel.set_project(project)
    row = panel._rows[0]
    assert not row._persist_dot.isHidden()
    assert row._name_btn.text() == "[] Score"
    def pick_persist(menu, position):
        return next(action for action in menu.actions() if action.text() == label("vartbl.persist"))
    monkeypatch.setattr(QMenu, "exec", pick_persist)
    panel._ctx_menu(entry, QPoint())
    assert not entry.persist and row._persist_dot.isHidden()
    panel._ctx_menu(entry, QPoint())
    assert entry.persist and not row._persist_dot.isHidden()
    row._combo.setCurrentText("string")
    assert not entry.persist and row._persist_dot.isHidden()
    row._value.setText("1")
    row._on_value()
    assert row._name_btn.text() == "Score"
    panel._toggle_array(entry)
    assert row._name_btn.text() == "[] Score"
