"""Les noms canoniques des modes dans l'éditeur PhysicsBody."""
from types import SimpleNamespace

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QVBoxLayout, QWidget

from core.models.components import CollisionBoxComponent, PhysicsBodyComponent
from core.models.scene import Actor
from ui.common.notice import NoteLine
from ui.common.widgets import ScriptSlot, W
from ui.scene_manager.inspectors.component_editors.physics_body import PhysicsBodyEditor


def test_l_editeur_affiche_et_ecrit_les_quatre_noms_canoniques(qapp):
    written = []
    comp = PhysicsBodyComponent(collider_id="feet")
    actor = Actor(name="Hero", components=[
        CollisionBoxComponent(id="body", tag="Body"),
        CollisionBoxComponent(id="feet", tag="Feet"),
        comp,
    ])

    def set_comp(component, field, value):
        written.append((field, value))
        setattr(component, field, value)

    inspector = SimpleNamespace(_set_comp=set_comp, _field_syncers={}, _actor=actor)
    host = QWidget()
    layout = QVBoxLayout(host)
    PhysicsBodyEditor(inspector).build(comp, lambda lab, w: W.row(lab, w, layout), layout)
    combo = host.findChild(QComboBox)
    notes = host.findChildren(NoteLine)
    static_note = next(note for note in notes if note.key == "physics.static_body")
    character_note = next(note for note in notes if note.key == "physics.character_body")
    kinematic_note = next(note for note in notes if note.key == "physics.kinematic_body")
    mass = host.findChild(QDoubleSpinBox, "physicsMass")
    gravity_scale = host.findChild(QDoubleSpinBox, "physicsGravityScale")
    can_sleep = host.findChild(QCheckBox, "physicsCanSleep")
    collider = host.findChild(ScriptSlot)

    expected = ["StaticBody", "CharacterBody", "KinematicBody", "RigidBody"]
    assert [combo.itemText(i) for i in range(combo.count())] == expected
    assert [combo.itemData(i) for i in range(combo.count())] == expected
    assert static_note.isHidden()
    assert character_note.isVisibleTo(host)
    assert "apply_velocity" in character_note.text()
    assert kinematic_note.isHidden()
    assert mass.parentWidget().isHidden()
    assert gravity_scale.parentWidget().isHidden()
    assert can_sleep.parentWidget().isHidden()
    assert collider._lbl.text() == "feet [Feet]"

    collider._click_clear()
    assert comp.collider_id == ""
    assert "Automatic" in collider._lbl.text()

    combo.setCurrentIndex(combo.findData("StaticBody"))
    assert static_note.isVisibleTo(host)
    assert character_note.isHidden()
    assert kinematic_note.isHidden()
    assert "position" in static_note.text().lower()

    combo.setCurrentIndex(combo.findData("KinematicBody"))
    assert static_note.isHidden()
    assert character_note.isHidden()
    assert kinematic_note.isVisibleTo(host)
    assert "velocity" in kinematic_note.text().lower()

    combo.setCurrentIndex(combo.findData("RigidBody"))
    assert static_note.isHidden()
    assert character_note.isHidden()
    assert kinematic_note.isHidden()
    assert not mass.parentWidget().isHidden()
    assert not gravity_scale.parentWidget().isHidden()
    assert not can_sleep.parentWidget().isHidden()
    assert written[-1] == ("mode", "RigidBody")
    assert comp.mode == "RigidBody"

    mass.setValue(2.5)
    gravity_scale.setValue(0.5)
    can_sleep.setChecked(False)
    assert (comp.mass, comp.gravity_scale, comp.can_sleep) == (2.5, 0.5, False)
    assert written[-3:] == [("mass", 2.5), ("gravity_scale", 0.5), ("can_sleep", False)]
