"""Un éditeur réutilisé suit la sélection, sans écrire sur son ancienne cible."""
import pytest
from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QLineEdit

from core.history import get_history
from core.models.components import CollisionShapeComponent, PhysicMaterialComponent
from core.models.scene import Actor
from core.project import Project
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
