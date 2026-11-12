"""Les formes des Areas gardent leurs widgets et suivent la zone courante."""
import pytest

from core.history import get_history
from core.models.components import CollisionShapeComponent
from core.models.scene import Area
from core.models.settings import GlobalVar
from core.project import Project
from ui.common.value_field import ValueField
from ui.common.widgets import PickerSlot
from ui.scene_manager.inspectors.area_inspector import AreaInspector


@pytest.fixture
def inspector(qapp):
    get_history().clear()
    panel = AreaInspector()
    yield panel
    get_history().clear()
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_area_reutilise_la_forme_et_annule_sur_la_bonne_cible(inspector, tmp_path):
    project = Project(tmp_path / "game")
    first = Area(name="First", components=[CollisionShapeComponent(w=24, tag="First")])
    second = Area(name="Second", components=[CollisionShapeComponent(w=48, tag="Second")])
    inspector.load(first, project, None)
    container = inspector._shape_container
    x, y, width, height = container.findChildren(ValueField)
    tag = container.findChild(PickerSlot)
    inspector._shape_card.set_expanded(True)

    width.changed.emit(32)
    assert first.shape().w == 32
    inspector.load(second, project, None)
    assert inspector._shape_container is container
    assert container.findChildren(ValueField) == [x, y, width, height]
    assert width.raw() == 48 and tag.value() == "Second"
    assert inspector._shape_card.is_expanded()
    assert len(get_history()._undo) == 1

    get_history().undo()
    inspector.refresh()
    assert first.shape().w == 24 and width.raw() == 48
    width.changed.emit(64)
    tag.pick("Other")
    assert second.shape().w == 64 and second.shape().tag == "Other"
    assert first.shape().w == 24 and first.shape().tag == "First"
    get_history().undo()
    get_history().undo()
    inspector.refresh()
    assert width.raw() == 48 and tag.value() == "Second"
    get_history().redo()
    inspector.refresh()
    assert width.raw() == 64 and inspector._shape_container is container
    assert not {"solid", "response", "one_way", "material_id"} & inspector._field_syncers.keys()


def test_area_actualise_variables_et_tags_puis_reconstruit_pour_un_autre_projet(inspector, tmp_path):
    project = Project(tmp_path / "first")
    var = GlobalVar(name="Before", id="123456789abc")
    project.globals.append(var)
    raw = {"var": var.id, "src": "global"}
    area = Area(components=[CollisionShapeComponent(x=raw)])
    inspector.load(area, project, None)
    container = inspector._shape_container
    x = container.findChildren(ValueField)[0]
    var.name = "After"
    project.settings.collision_tags.append("Fresh")
    inspector.refresh()
    assert inspector._shape_container is container and x.raw() == raw
    assert "After" in x._chip.text()
    assert "Fresh" in [entry.value for entry in container.findChild(PickerSlot).popup_entries()]
    assert not get_history().can_undo

    other = Project(tmp_path / "second")
    other.settings.collision_tags.append("Other")
    inspector.load(area, other, None)
    assert inspector._shape_container is not container
    assert "Other" in [entry.value for entry in inspector._shape_container.findChild(PickerSlot).popup_entries()]
    assert area.shape().x == raw and not get_history().can_undo


def test_area_sans_forme_puis_avec_une_forme_ne_garde_pas_une_ancienne_cible(inspector, tmp_path):
    project = Project(tmp_path / "game")
    area = Area()
    inspector.load(area, project, None)
    previous = inspector._shape_container
    area.components.clear()
    inspector.refresh()
    empty = inspector._shape_container
    assert empty is not previous and not inspector._field_syncers
    assert inspector._shape_editor is None and not empty.findChildren(ValueField)
    inspector.load(area, project, None)
    assert inspector._shape_container is empty

    shape = CollisionShapeComponent(w=72)
    area.components.append(shape)
    inspector.refresh()
    assert inspector._shape_container is not empty
    width = inspector._shape_container.findChildren(ValueField)[2]
    assert width.raw() == 72
    width.changed.emit(80)
    assert shape.w == 80
