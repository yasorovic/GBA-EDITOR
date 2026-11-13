"""Scene et UI rafraîchissent la sélection sans refaire les contrôles valides."""
import pytest

from core.history import get_history
from core.models.background import BackgroundLayer
from core.models.palette import PaletteBank
from core.models.scene import Scene
from core.models.ui_region import UILayout, UIText, UIContainer
from core.project import Project
from ui.scene_manager.inspectors import DynamicInspector


@pytest.fixture
def inspector(qapp):
    get_history().clear()
    panel = DynamicInspector()
    yield panel
    if panel._ui_insp is not None:
        panel._ui_insp._commit_content()
    get_history().clear()
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def _project(tmp_path):
    project = Project(tmp_path)
    scene = Scene(name="First")
    project.scenes.append(scene)
    return project, scene


def test_scene_refresh_conserve_les_lignes_et_actualise_les_valeurs(inspector, tmp_path, monkeypatch):
    project, scene = _project(tmp_path)
    inspector.set_project(project)
    inspector.show_scene(scene, project)
    panel = inspector._scene_insp
    monkeypatch.setattr(panel, "_persist_scene", lambda: None)
    rows = list(panel._bg_layer_rows)
    bank, font = panel._ui_pal_slot, panel._font_slot
    scene.background_layers[0].scroll_speed = 2.5
    scene.background_layers[0].background_name = "Missing"
    project.settings.transition_kind = "fade_black"
    panel._notes_edit.setPlainText("Draft")
    monkeypatch.setattr(panel, "load", lambda *_: pytest.fail("refresh doit conserver la sélection"))
    inspector.refresh_current()
    assert panel._bg_layer_rows == rows
    assert panel._ui_pal_slot is bank and panel._font_slot is font
    assert rows[0]._speed.value() == 2.5 and not rows[0]._btn_clear.isHidden()
    assert panel._combo_trans.currentData() == "fade_black"
    assert panel._notes_edit.toPlainText() == "Draft" and not get_history().can_undo
    scene.background_layers[0].background_name = ""
    inspector.refresh_current()
    assert rows[0]._btn_clear.isHidden()
    for _ in range(3):
        inspector.refresh_current()
    rows[0]._speed.setValue(3.0)
    assert scene.background_layers[0].scroll_speed == 3.0
    get_history().undo()
    inspector.refresh_current()
    assert rows[0]._speed.value() == 2.5 and not get_history().can_undo


def test_scene_reconnecte_apres_remplacement_scene_et_mode(inspector, tmp_path, monkeypatch):
    project, first = _project(tmp_path)
    inspector.set_project(project)
    inspector.show_scene(first, project)
    panel = inspector._scene_insp
    monkeypatch.setattr(panel, "_persist_scene", lambda: None)
    previous = panel._bg_layer_rows[0]
    second = Scene(name="Second")
    project.scenes.append(second)
    inspector.show_scene(second, project)
    row = panel._bg_layer_rows[0]
    assert row is not previous
    row._speed.setValue(2.0)
    assert second.background_layers[0].scroll_speed == 2.0
    assert first.background_layers[0].scroll_speed == 1.0
    replacement = BackgroundLayer(bg_slot=0, scroll_speed=0.5)
    second.background_layers[0] = replacement
    inspector.refresh_current()
    assert panel._bg_layer_rows[0] is not row
    panel._bg_layer_rows[0]._speed.setValue(0.75)
    assert replacement.scroll_speed == 0.75
    second.render_mode = 3
    inspector.refresh_current()
    assert not panel._bg_layer_rows
    second.render_mode = 0
    inspector.refresh_current()
    assert len(panel._bg_layer_rows) == 4
    assert panel._bg_layer_rows[0]._speed.value() == 0.75


def test_ui_refresh_garde_la_salve_et_le_curseur_jusqu_au_commit(inspector, tmp_path, monkeypatch):
    project, scene = _project(tmp_path)
    element = UIText(name="Text", preview_text="Hello")
    layout = UILayout(name="HUD", elements=[element])
    inspector.set_project(project)
    inspector.show_ui_element(layout, element, project)
    panel = inspector._ui_insp
    monkeypatch.setattr(panel, "_persist", lambda: None)
    monkeypatch.setattr(panel, "load", lambda *_: pytest.fail("refresh ne doit pas commiter la frappe"))
    bank = panel._ui_pal_slot
    panel._content.moveCursor(panel._content.textCursor().MoveOperation.End)
    for char in "abc":
        panel._content.insertPlainText(char)
        inspector.refresh_current()
    assert element.preview_text == "Helloabc"
    assert panel._content.textCursor().position() == len("Helloabc")
    assert panel._content_baseline == "Hello" and not get_history().can_undo
    assert panel._ui_pal_slot is bank
    panel._commit_content()
    get_history().undo()
    inspector.refresh_current()
    assert element.preview_text == panel._content.toPlainText() == "Hello"
    get_history().redo()
    inspector.refresh_current()
    assert panel._content.toPlainText() == "Helloabc"


def test_ui_palettes_conservees_puis_actualisees_et_nouvelle_cible(inspector, tmp_path, monkeypatch):
    project, scene = _project(tmp_path)
    project.palettes.append(PaletteBank(name="A", colors=[0, 31]))
    project.palettes.append(PaletteBank(name="B", colors=[0, 992]))
    scene.active_bg_palettes = ["A"]
    first = UIContainer(name="First", fill_palette="A")
    second = UIContainer(name="Second", fill_palette="A")
    layout = UILayout(name="HUD", elements=[first, second])
    inspector.set_project(project)
    inspector.show_ui_element(layout, first, project)
    panel = inspector._ui_insp
    monkeypatch.setattr(panel, "_persist", lambda: None)
    slot = panel._fill_pal_slot
    inspector.refresh_current()
    assert panel._fill_pal_slot is slot
    inspector.show_ui_element(layout, second, project)
    assert panel._fill_pal_slot is slot
    scene.active_bg_palettes.append("B")
    inspector.refresh_current()
    assert panel._fill_pal_slot is not slot
    assert "B" in [entry.value for entry in panel._fill_pal_slot.popup_entries()]
    panel._fill_pal_slot.pick("B")
    assert first.fill_palette == "A" and second.fill_palette == "B"
    get_history().undo()
    inspector.refresh_current()
    assert second.fill_palette == panel._fill_pal_slot.value() == "A"
