"""Resolve display tables at construction, preserving stable selection values."""
import pytest
from PyQt6.QtWidgets import QLabel, QPushButton

from ui.common import catalog, labels
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SCENES
from ui.common.widgets import W, ScriptPickerPopup
from ui.scene_manager.inspectors.bg_layer_row import BgLayerRow
from ui.scene_manager.inspectors.camera_inspector import CameraInspector
from ui.scene_manager.inspectors.project_settings_dialog import ProjectSettingsDialog
from core.project import Project


@pytest.fixture
def marked_language(monkeypatch):
    # Modules above are already imported: strings must not have been frozen there.
    catalog.set_language("")
    master = labels._CAT._catalog()
    monkeypatch.setattr(labels._CAT, "_side", {
        key: {form: "§ " + text for form, text in entry.items()}
        for key, entry in master.items()
    })
    yield
    catalog.set_language("")


def test_asset_title_is_translated_but_selection_id_is_stable(qapp, marked_language):
    finder = AssetFinder("", [SCENES])
    assert SCENES.label == "Scenes"
    assert "Scenes" in finder._trees
    assert "§ Scenes" in {w.text() for w in finder.findChildren(QLabel)}
    assert finder._sections["Scenes"]._btn_add.toolTip() == "<b>§ New scene</b>"


def test_camera_modes_and_blend_tables_resolve_after_import(qapp, marked_language):
    camera = CameraInspector()
    assert camera._mode_combo.itemText(0) == "§ Fixed"
    row = BgLayerRow(0)
    row.set_blend_role("top")
    row.set_blend_ui("toggle")
    assert row._blend_btn.toolTip().startswith("<b>§ Translucent layer</b>")


def test_default_widget_text_resolves_at_construction(qapp, marked_language):
    assert W.btn_add().toolTip() == "§ Add"
    popup = ScriptPickerPopup([], "#888888")
    assert "§ ＋  New script" in {w.text() for w in popup.findChildren(QPushButton)}


def test_project_navigation_keeps_ids_while_translating(qapp, marked_language, tmp_path):
    dialog = ProjectSettingsDialog(Project(tmp_path), initial_category="Visual")
    assert dialog._list.currentRow() == 1
    assert dialog._list.item(1).text() == "§ Visual"
