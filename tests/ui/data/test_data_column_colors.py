"""Coloration depuis le menu partagé, sauvegarde et annulation."""
import json

from PyQt6.QtWidgets import QMenu, QToolButton

from core.history import CommandHistory
from core.models.data_table import DataColumn, DataTable
from core.project import Project
from ui.common.color_menu import add_color_actions
from ui.common.disk_folder_colors import COLORS
from ui.data_editor import data_grid_panel


def test_le_menu_partage_propose_les_couleurs_et_la_remise_a_zero(qapp):
    picked = []
    menu = QMenu()
    add_color_actions(menu, None, picked.append)
    dots = menu.actions()[-1].defaultWidget().findChildren(QToolButton)
    assert len(dots) == len(COLORS) + 1
    for dot in dots:
        dot.click()
    assert picked == [None, *COLORS.values()]
    menu.close()


def test_la_couleur_survit_a_la_reouverture_et_s_annule(qapp, tmp_path, monkeypatch):
    history = CommandHistory()
    monkeypatch.setattr(data_grid_panel, "get_history", lambda: history)
    project = Project.create(tmp_path / "Game", "Game")
    table = DataTable(name="Items", columns=[DataColumn("price", "int")],
                      rows=[{"price": 12}])
    project.data_tables.append(table)
    panel = data_grid_panel.DataGridPanel()
    panel.load_project(project)
    panel.show_table(table.name)
    column = table.columns[0]
    color = COLORS["blue"]
    panel._set_column_color(column, color)
    saved = DataTable.from_dict(json.loads(
        project.data_tables._path(table.name).read_text(encoding="utf-8")))
    assert saved.columns[0].color == color
    assert saved.rows == [{"price": 12}]
    history.undo()
    assert column.color == ""
    history.redo()
    assert column.color == color
    panel._set_column_color(column, None)
    assert column.color == ""
    assert DataTable.from_dict({"columns": [{"name": "old", "type": "int"}]}).columns[0].color == ""
    panel.close()
