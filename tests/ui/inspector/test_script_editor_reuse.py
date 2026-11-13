"""La carte Script conserve ses champs et actualise la cible et les exports."""
from copy import deepcopy

import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSlider, QSpinBox

from core.history import get_history
from core.models.components import ScriptComponent
from core.models.scene import Actor, Area, Scene
from core.project import Project
from ui.common.widgets import PickerSlot
from ui.scene_manager.inspectors.actor_inspector import ActorInspector
from ui.scene_manager.inspectors.area_inspector import AreaInspector


@pytest.fixture(params=[AreaInspector, ActorInspector], ids=["area", "actor"])
def panel(request, qapp, monkeypatch):
    inspector = request.param()
    get_history().clear()
    saves = []
    monkeypatch.setattr(inspector, "_persist", lambda: saves.append(True))
    inspector.test_saves = saves
    yield inspector
    get_history().clear()
    inspector.close()
    inspector.deleteLater()
    qapp.processEvents()


def _editor(panel):
    return panel._script_editor if isinstance(panel, AreaInspector) else panel._component_editor


def _owner(panel, **kwargs):
    return (Area if isinstance(panel, AreaInspector) else Actor)(**kwargs)


def _script(project, text):
    path = project.root / "Script.lua"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return project.asset_rel(path), path


EXPORTS = '''exports = {
    enabled = { type = "bool", default = false },
    count = { type = "int", default = 2, min = 0, max = 10 },
    ratio = { type = "float", default = 0.25, min = 0, max = 1 },
    title = { type = "string", default = "Default" },
    position = { type = "vec2", default = {1, 2} },
    bounds = { type = "rect", default = {3, 4, 16, 24} },
    direction = { type = "enum", default = "left", values = {"left", "right"} },
    destination = { type = "scene_ref", default = "" },
    sound = { type = "sfx_ref", default = "" },
    target = { type = "actor_ref", default = "" },
}'''


def test_script_reutilise_tous_les_champs_et_ecrit_sur_la_nouvelle_cible(panel, tmp_path):
    project = Project(tmp_path / "game")
    rel, path = _script(project, EXPORTS)
    first = ScriptComponent(script=rel)
    values = {"enabled": True, "count": 8, "ratio": 0.75, "title": "Second",
              "position": [8, 9], "bounds": [10, 11, 32, 40], "direction": "right",
              "destination": "MissingScene", "sound": "MissingSound", "target": "MissingActor"}
    second = ScriptComponent(script=rel, exports_values=deepcopy(values))
    panel.load(_owner(panel, name="First", components=[first]), project, None)
    editor = _editor(panel)
    rows = dict(panel._export_rows)
    slot = editor._slot
    panel.load(_owner(panel, name="Second", components=[second]), project, None)
    assert _editor(panel) is editor and editor._slot is slot
    assert panel._export_rows == rows
    assert not panel.test_saves and not get_history().can_undo
    assert first.exports_values == {} and second.exports_values == values

    check = rows["enabled"].findChild(QCheckBox)
    count = rows["count"].findChild(QSpinBox)
    ratio = rows["ratio"].findChild(QDoubleSpinBox)
    title = rows["title"].findChild(QLineEdit)
    position = rows["position"].findChildren(QSpinBox)
    bounds = rows["bounds"].findChildren(QSpinBox)
    rect_fields = editor._exports_container.findChildren(QSpinBox)[-4:]
    direction = rows["direction"].findChild(QComboBox)
    assert check.isChecked() and count.value() == 8 and ratio.value() == 0.75
    assert rows["count"].findChild(QSlider).value() == 8
    assert rows["ratio"].findChild(QSlider).value() == 750
    assert title.text() == "Second" and [w.value() for w in position] == [8, 9]
    assert [w.value() for w in bounds] == [10, 11]  # largeur et hauteur sur la ligne suivante
    assert [w.value() for w in rect_fields] == [10, 11, 32, 40]
    assert direction.currentText() == "right"
    for name in ("destination", "sound", "target"):
        assert rows[name].findChild(PickerSlot).value() == values[name]

    check.setChecked(False)
    count.setValue(6)
    ratio.setValue(0.5)
    title.setText("Edited")
    title.editingFinished.emit()
    position[0].setValue(7)
    bounds[0].setValue(12)
    rect_fields[3].setValue(50)
    direction.setCurrentText("left")
    rows["target"].findChild(PickerSlot).pick("Chosen")
    assert first.exports_values == {}
    assert second.exports_values == dict(values, enabled=False, count=6, ratio=0.5, title="Edited",
                                         position=[7, 9], bounds=[12, 11, 32, 50], direction="left", target="Chosen")

    panel.load(_owner(panel, name="First", components=[first]), project, None)
    assert panel._export_rows == rows
    assert count.value() == 2 and ratio.value() == 0.25 and title.text() == "Default"
    assert direction.currentText() == "left" and not check.isChecked()


def test_script_actualise_les_references_et_le_projet(panel, tmp_path):
    project = Project(tmp_path / "first")
    rel, path = _script(project, EXPORTS)
    first = _owner(panel, name="First", components=[ScriptComponent(script=rel)])
    second = _owner(panel, name="Second", components=[ScriptComponent(script=rel)])
    scene = Scene(name="Scene", actors=[Actor(name="Visible")])
    if isinstance(panel, ActorInspector):
        scene.actors.extend([first, second])
    panel.load(first, project, scene)
    editor = _editor(panel)
    rows = dict(panel._export_rows)
    target = rows["target"].findChild(PickerSlot)
    assert "Visible" in [entry.value for entry in target.popup_entries()]
    scene.actors.append(Actor(name="Fresh"))
    panel.load(second, project, scene)
    assert panel._export_rows == rows
    choices = [entry.value for entry in target.popup_entries()]
    assert "Fresh" in choices
    if isinstance(panel, ActorInspector):
        assert "First" in choices and "Second" not in choices

    other = Project(tmp_path / "second")
    _script(other, EXPORTS)
    panel.load(second, other, Scene(actors=[Actor(name="Other")]))
    assert _editor(panel) is editor and panel._export_rows != rows
    target = panel._export_rows["target"].findChild(PickerSlot)
    assert [entry.value for entry in target.popup_entries()] == ["", "Other"]
    assert not panel.test_saves and not get_history().can_undo


def test_script_rafraichi_conserve_une_saisie_non_validee(panel, tmp_path):
    project = Project(tmp_path / "game")
    rel, path = _script(project, EXPORTS)
    comp = ScriptComponent(script=rel)
    owner = _owner(panel, components=[comp])
    panel.load(owner, project, None)
    title = panel._export_rows["title"].findChild(QLineEdit)
    title.setText("Draft")
    panel._export_rows["count"].findChild(QSpinBox).setValue(5)
    panel.load(owner, project, None)
    assert title.text() == "Draft" and "title" not in comp.exports_values
    title.editingFinished.emit()
    assert comp.exports_values == {"count": 5, "title": "Draft"}


def test_script_reconstruit_uniquement_les_exports_si_le_fichier_change(panel, tmp_path, qapp):
    project = Project(tmp_path / "game")
    rel, path = _script(project, EXPORTS)
    comp = ScriptComponent(script=rel, exports_values={"count": 7})
    owner = _owner(panel, components=[comp])
    panel.load(owner, project, None)
    editor = _editor(panel)
    slot, old = editor._slot, editor._exports_container
    path.write_text('exports = { count = { type = "int", default = 1, max = 4 }, new = { type = "bool" } }', encoding="utf-8")
    panel.load(owner, project, None)
    assert _editor(panel) is editor and editor._slot is slot
    assert editor._exports_container is not old and set(panel._export_rows) == {"count", "new"}
    assert panel._export_rows["count"].findChild(QSpinBox).maximum() == 4
    assert comp.exports_values == {"count": 7} and not panel.test_saves
    panel.focus_script_export("new")
    qapp.processEvents()
    path.unlink()
    panel.load(owner, project, None)
    assert not panel._export_rows and comp.script == rel
    assert slot.value() == rel and not panel.test_saves


def test_script_choix_et_effacement_suivent_la_cible_courante(panel, tmp_path):
    project = Project(tmp_path / "game")
    rel, path = _script(project, EXPORTS)
    first, second = ScriptComponent(), ScriptComponent()
    panel.load(_owner(panel, components=[first]), project, None)
    editor = _editor(panel)
    panel.load(_owner(panel, components=[second]), project, None)
    editor._slot.pick(rel)
    assert second.script == rel and first.script is None
    assert "count" in panel._export_rows
    editor._clear_script(editor.comp)
    assert second.script is None and second.exports_values == {} and not panel._export_rows


def test_area_sans_script_ajout_annulation_et_retablissement(tmp_path, qapp, monkeypatch):
    panel = AreaInspector()
    monkeypatch.setattr(panel, "_persist", lambda: None)
    get_history().clear()
    project = Project(tmp_path / "game")
    rel, path = _script(project, EXPORTS)
    area = Area()
    try:
        panel.load(area, project, None)
        editor = panel._script_editor
        assert area.get_component("script") is None
        editor._slot.pick(rel)
        comp = area.get_component("script")
        assert comp is editor.comp and comp.script == rel
        get_history().undo()
        panel.refresh()
        assert area.get_component("script") is None and editor._slot.value() is None
        assert not panel._export_rows
        get_history().redo()
        panel.refresh()
        assert area.get_component("script") is comp and editor.comp is comp
        assert editor._slot.value() == rel and "count" in panel._export_rows
    finally:
        get_history().clear()
        panel.deleteLater()
        qapp.processEvents()
