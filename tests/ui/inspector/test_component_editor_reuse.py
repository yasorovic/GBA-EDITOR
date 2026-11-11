"""Un éditeur réutilisé suit la sélection, sans écrire sur son ancienne cible."""
import pytest
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit

from core.history import get_history
from core.models.components import CollisionShapeComponent, PhysicMaterialComponent, PhysicsBodyComponent
from core.models.scene import Actor
from core.models.settings import GlobalVar
from core.project import Project
from ui.common.labels import label
from ui.common.value_field import ValueField
from ui.common.widgets import PickerSlot
from ui.scene_manager.inspectors.actor_inspector import ActorInspector


@pytest.fixture
def inspector(qapp):
    history = get_history()
    history.clear()
    panel = ActorInspector()
    yield panel
    history.clear()
    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def _material(panel, name):
    return panel._editor_container.findChild(QDoubleSpinBox, name)


def test_changer_acteur_conserve_les_champs_et_ne_cree_pas_de_commande(inspector):
    first = Actor(name="First", components=[PhysicMaterialComponent(restitution=0.1)])
    second = Actor(name="Second", components=[PhysicMaterialComponent(restitution=0.8)])
    inspector.load(first, None, None)
    container = inspector._editor_container
    restitution = _material(inspector, "materialRestitution")

    for actor in (second, first, second):
        inspector.load(actor, None, None)
        assert inspector._editor_container is container
        assert _material(inspector, "materialRestitution") is restitution
        assert restitution.value() == actor.components[0].restitution

    restitution.setValue(0.6)
    assert first.components[0].restitution == 0.1
    assert second.components[0].restitution == 0.6
    get_history().undo()
    assert restitution.value() == 0.8
    assert not get_history().can_undo
    get_history().redo()
    assert restitution.value() == 0.6
    assert inspector._editor_container is container


def test_changer_composant_relie_aussi_id_et_active(inspector):
    first = PhysicMaterialComponent(id="First", restitution=0.1)
    second = PhysicMaterialComponent(id="Second", active=False, restitution=0.8)
    actor = Actor(name="Actor", components=[first, second])
    inspector.load(actor, None, None)
    container = inspector._editor_container
    name = container.findChild(QLineEdit)
    active = container.findChild(QCheckBox)

    inspector._comp_list.setCurrentRow(1)
    assert inspector._editor_container is container
    assert name.text() == "Second"
    assert not active.isChecked()
    assert not get_history().can_undo

    name.setText("Renamed")
    name.editingFinished.emit()
    active.setChecked(True)
    assert (first.id, first.active) == ("First", True)
    assert (second.id, second.active) == ("Renamed", True)
    get_history().undo()
    assert not active.isChecked()
    get_history().undo()
    assert name.text() == "Second"
    get_history().redo()
    get_history().redo()
    assert name.text() == "Renamed" and active.isChecked()


def test_annuler_sur_ancienne_cible_conserve_la_selection(inspector):
    first = PhysicMaterialComponent(id="First", friction=0.1)
    second = PhysicMaterialComponent(id="Second", friction=0.8)
    actor = Actor(name="Actor", components=[first, second])
    inspector.load(actor, None, None)
    friction = _material(inspector, "materialFriction")
    friction.setValue(0.3)
    inspector._comp_list.setCurrentRow(1)

    get_history().undo()
    assert first.friction == 0.1
    assert second.friction == 0.8
    assert inspector._current_comp is second
    assert _material(inspector, "materialFriction") is friction
    assert friction.value() == 0.8
    get_history().redo()
    assert first.friction == 0.3
    assert friction.value() == 0.8


def test_changer_de_type_et_revenir_reconstruit_sans_ancienne_cible(inspector, tmp_path):
    material = PhysicMaterialComponent(friction=0.2)
    actor = Actor(name="Actor", components=[material, CollisionShapeComponent()])
    inspector.load(actor, Project(tmp_path / "game"), None)
    container = inspector._editor_container
    inspector._comp_list.setCurrentRow(1)
    assert inspector._editor_container is not container
    inspector._comp_list.setCurrentRow(0)
    assert inspector._editor_container is not container
    _material(inspector, "materialFriction").setValue(0.5)
    assert material.friction == 0.5


def test_supprimer_et_annuler_relie_le_composant_restaure(inspector):
    first = PhysicMaterialComponent(id="First", friction=0.1)
    second = PhysicMaterialComponent(id="Second", friction=0.8)
    actor = Actor(name="Actor", components=[first, second])
    inspector.load(actor, None, None)
    friction = _material(inspector, "materialFriction")
    inspector._remove_selected_component()
    assert actor.components == [second]
    assert friction.value() == 0.8
    get_history().undo()
    assert actor.components[0] is first
    assert inspector._current_comp is first
    assert _material(inspector, "materialFriction") is friction
    friction.setValue(0.4)
    assert first.friction == 0.4
    assert second.friction == 0.8


def test_physics_body_reutilise_les_champs_et_les_colliders_de_la_nouvelle_cible(inspector):
    first = PhysicsBodyComponent(mode="RigidBody", mass=2.0, collider_id="body")
    second = PhysicsBodyComponent(mode="CharacterBody", mass=3.0, gravity_scale=0.5,
                                  use_scene_gravity=False, can_sleep=False, collider_id="body")
    first_actor = Actor(name="First", components=[first, CollisionShapeComponent(id="body", tag="First")])
    second_actor = Actor(name="Second", components=[second, CollisionShapeComponent(id="body", tag="Second"),
                                                   CollisionShapeComponent(id="feet")])
    inspector.load(first_actor, None, None)
    container = inspector._editor_container
    mass = container.findChild(QDoubleSpinBox, "physicsMass")
    mode = container.findChild(QComboBox)
    collider = container.findChild(PickerSlot)
    assert collider._lbl.text() == "body [First]"

    inspector.load(second_actor, None, None)

    assert inspector._editor_container is container
    assert container.findChild(QDoubleSpinBox, "physicsMass") is mass
    assert mass.value() == 3.0 and mass.parentWidget().isHidden()
    assert mode.currentData() == "CharacterBody"
    assert collider._lbl.text() == "body [Second]"
    assert {entry.value for entry in collider.popup_entries()} == {"body", "feet"}
    assert not get_history().can_undo
    mode.setCurrentIndex(mode.findData("RigidBody"))
    mass.setValue(4.0)
    collider.pick("feet")
    collider._btn_clear.click()
    assert (first.mode, first.mass, first.collider_id) == ("RigidBody", 2.0, "body")
    assert (second.mode, second.mass, second.collider_id) == ("RigidBody", 4.0, "")
    get_history().undo()
    assert second.collider_id == "body" and collider.value() == "body"
    get_history().redo()
    assert second.collider_id == "" and collider.value() == ""
    assert inspector._editor_container is container


def test_physics_body_annulation_retablit_mode_gravite_et_visibilite(inspector):
    body = PhysicsBodyComponent(mode="CharacterBody", use_scene_gravity=True)
    actor = Actor(name="Actor", components=[body])
    inspector.load(actor, None, None)
    container = inspector._editor_container
    mode = container.findChild(QComboBox)
    mass = container.findChild(QDoubleSpinBox, "physicsMass")
    gravity = container.findChild(QDoubleSpinBox, "physicsGravityScale")
    use_gravity = container.findChild(QCheckBox, "physicsUseSceneGravity")
    sleep = container.findChild(QCheckBox, "physicsCanSleep")
    for value in ("StaticBody", "KinematicBody", "RigidBody"):
        mode.setCurrentIndex(mode.findData(value))
        assert mass.parentWidget().isHidden() == (value != "RigidBody")
        assert sleep.parentWidget().isHidden() == (value != "RigidBody")
        assert use_gravity.parentWidget().isHidden() == (value in ("StaticBody", "RigidBody"))
        get_history().undo()
        assert mode.currentData() == body.mode == "CharacterBody"
        assert mass.parentWidget().isHidden() and sleep.parentWidget().isHidden()
        assert not use_gravity.parentWidget().isHidden() and not gravity.parentWidget().isHidden()
    use_gravity.setChecked(False)
    assert not body.use_scene_gravity and gravity.parentWidget().isHidden()
    get_history().undo()
    assert body.use_scene_gravity and use_gravity.isChecked()
    assert not gravity.parentWidget().isHidden()
    get_history().redo()
    assert gravity.parentWidget().isHidden()
    assert inspector._editor_container is container


def test_physics_body_relit_les_colliders_et_garde_une_reference_absente(inspector):
    body = PhysicsBodyComponent(collider_id="feet")
    shape = CollisionShapeComponent(id="feet", tag="Feet")
    actor = Actor(name="Actor", components=[body, shape])
    inspector.load(actor, None, None)
    container = inspector._editor_container
    collider = container.findChild(PickerSlot)
    actor.components.remove(shape)
    inspector.load(actor, None, None)

    assert inspector._editor_container is container
    assert collider.value() == body.collider_id == "feet"
    assert collider.popup_entries()[0].missing
    actor.components.append(CollisionShapeComponent(id="new"))
    assert {entry.value for entry in collider.popup_entries()} == {"new", "feet"}
    get_history().clear()
    collider.pick("new")
    get_history().undo()
    assert body.collider_id == collider.value() == "feet"
    assert next(entry for entry in collider.popup_entries() if entry.value == "feet").missing
    get_history().redo()
    assert body.collider_id == collider.value() == "new"


def test_collision_reutilise_les_champs_entre_formes_et_acteurs(inspector, tmp_path):
    project = Project(tmp_path / "game")
    first = CollisionShapeComponent(id="first", x=1, tag="First", material_id="rubber")
    second = CollisionShapeComponent(id="second", x=8, solid=False, response="block", one_way="down")
    third = CollisionShapeComponent(id="third", x=12, material_id="metal")
    first_actor = Actor(name="First", components=[first, second, PhysicMaterialComponent(id="rubber")])
    second_actor = Actor(name="Second", components=[third, PhysicMaterialComponent(id="metal")])
    inspector.load(first_actor, project, None)
    container = inspector._editor_container
    x = container.findChildren(ValueField)[0]
    solid = next(check for check in container.findChildren(QCheckBox) if not check.text())
    blocks = next(check for check in container.findChildren(QCheckBox)
                  if check.text() == label("comped.collision_blocks"))
    one_way = container.findChild(QComboBox)
    tag, material = container.findChildren(PickerSlot)

    inspector._comp_list.setCurrentRow(1)
    assert inspector._editor_container is container
    assert x.raw() == 8 and not solid.isChecked() and blocks.isChecked()
    assert one_way.currentData() == "down"
    x._spin.setValue(10)
    assert first.x == 1 and second.x == 10
    get_history().undo()
    assert second.x == x.raw() == 8
    assert not get_history().can_undo

    inspector.load(second_actor, project, None)
    assert inspector._editor_container is container
    assert container.findChildren(ValueField)[0] is x
    assert x.raw() == 12 and solid.isChecked() and not blocks.isChecked()
    assert {entry.value for entry in material.popup_entries()} == {"metal"}
    assert material.value() == "metal"
    x._spin.setValue(22)
    solid.setChecked(False)
    blocks.setChecked(True)
    one_way.setCurrentIndex(one_way.findData("up"))
    tag.pick("NewTag")
    material._btn_clear.click()
    assert (third.x, third.solid, third.response, third.one_way, third.tag, third.material_id) == (
        22, False, "block", "up", "NewTag", "")
    assert (first.x, first.solid, first.response, first.one_way, first.tag, first.material_id) == (
        1, True, "sensor", "off", "First", "rubber")
    get_history().undo()
    assert third.material_id == material.value() == "metal"


def test_collision_actualise_tags_et_materiaux_sans_reconstruction(inspector, tmp_path):
    project = Project(tmp_path / "game")
    project.root.mkdir()
    shape = CollisionShapeComponent(material_id="rubber")
    rubber = PhysicMaterialComponent(id="rubber")
    actor = Actor(name="Actor", components=[shape, rubber])
    inspector.load(actor, project, None)
    container = inspector._editor_container
    tag, material = container.findChildren(PickerSlot)
    project.settings.collision_tags.append("Player")
    assert "Player" in {entry.value for entry in tag.popup_entries()}
    tag._created("player")
    assert shape.tag == tag.value() == "Player"
    assert "player" not in project.settings.collision_tags
    get_history().clear()
    tag._created("NewTag")
    assert shape.tag == "NewTag" and "NewTag" in project.settings.collision_tags
    get_history().undo()
    assert shape.tag == tag.value() == "Player"
    get_history().undo()
    assert "NewTag" not in project.settings.collision_tags
    get_history().redo()
    get_history().redo()
    assert shape.tag == tag.value() == "NewTag"

    actor.components.remove(rubber)
    inspector.load(actor, project, None)
    assert inspector._editor_container is container
    assert shape.material_id == material.value() == "rubber"
    assert material.popup_entries()[0].missing
    actor.components.append(PhysicMaterialComponent(id="metal"))
    assert {entry.value for entry in material.popup_entries()} == {"metal", "rubber"}
    material.pick("metal")
    get_history().undo()
    assert shape.material_id == material.value() == "rubber"
    assert next(entry for entry in material.popup_entries() if entry.value == "rubber").missing
    get_history().redo()
    assert shape.material_id == material.value() == "metal"


def test_collision_relit_les_variables_sans_changer_leur_reference(inspector, tmp_path):
    project = Project(tmp_path / "game")
    variable = GlobalVar(name="Before", id="123456789abc")
    project.globals.append(variable)
    raw = {"var": variable.id, "src": "global"}
    shape = CollisionShapeComponent(x=raw)
    actor = Actor(name="Actor", components=[shape])
    inspector.load(actor, project, None)
    container = inspector._editor_container
    x = container.findChildren(ValueField)[0]
    variable.name = "After"
    inspector.load(actor, project, None)
    assert inspector._editor_container is container
    assert x.raw() == shape.x == raw
    assert "After" in x._chip.text() and "Before" not in x._chip.text()
    assert not get_history().can_undo


def test_collision_reconstruit_si_physique_ou_projet_change(inspector, tmp_path):
    from core.models.scene import Scene

    project = Project(tmp_path / "first")
    project.root.mkdir()
    shape = CollisionShapeComponent(one_way="up", material_id="missing")
    actor = Actor(name="Actor", components=[shape])
    scene = Scene(name="Scene", physics_enabled=True)
    inspector.load(actor, project, scene)
    container = inspector._editor_container
    scene.physics_enabled = False
    inspector.load(actor, project, scene)
    assert inspector._editor_container is not container
    assert not inspector._editor_container.findChildren(QComboBox)
    assert len(inspector._editor_container.findChildren(PickerSlot)) == 1
    assert shape.one_way == "up" and shape.material_id == "missing"
    container = inspector._editor_container
    scene.physics_enabled = True
    inspector.load(actor, project, scene)
    assert inspector._editor_container is not container
    assert inspector._editor_container.findChild(QComboBox).currentData() == "up"
    container = inspector._editor_container
    other_project = Project(tmp_path / "second")
    other_project.root.mkdir()
    inspector.load(actor, other_project, scene)
    assert inspector._editor_container is not container
    tag = inspector._editor_container.findChildren(PickerSlot)[0]
    tag._created("OtherProjectTag")
    assert "OtherProjectTag" in other_project.settings.collision_tags
    assert "OtherProjectTag" not in project.settings.collision_tags
