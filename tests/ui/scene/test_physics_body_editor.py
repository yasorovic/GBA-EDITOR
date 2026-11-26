"""Les noms canoniques des modes dans l'éditeur PhysicsBody."""
from types import SimpleNamespace

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QVBoxLayout, QWidget

from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
from core.models.scene import Actor
from ui.common.notice import NoteLine
from ui.common.widgets import PickerSlot, W
from ui.scene_manager.inspectors.component_editors.physics_body import PhysicsBodyEditor


def test_l_editeur_affiche_et_ecrit_les_quatre_noms_canoniques(qapp):
    written = []
    comp = PhysicsBodyComponent(collider_id="feet")
    actor = Actor(name="Hero", components=[
        CollisionShapeComponent(id="body", tag="Body"),
        CollisionShapeComponent(id="feet", tag="Feet"),
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
    use_gravity = host.findChild(QCheckBox, "physicsUseSceneGravity")
    collider = host.findChild(PickerSlot)

    expected = ["StaticBody", "CharacterBody", "KinematicBody", "RigidBody"]
    assert [combo.itemText(i) for i in range(combo.count())] == expected
    assert [combo.itemData(i) for i in range(combo.count())] == expected
    assert static_note.isHidden()
    assert character_note.isVisibleTo(host)
    assert "apply_velocity" in character_note.text()
    assert kinematic_note.isHidden()
    assert mass.parentWidget().isHidden()
    assert not gravity_scale.parentWidget().isHidden()      # actif par défaut pour un Character
    assert not use_gravity.parentWidget().isHidden()
    use_gravity.setChecked(False)
    assert comp.use_scene_gravity is False
    assert gravity_scale.parentWidget().isHidden()
    use_gravity.setChecked(True)
    assert can_sleep.parentWidget().isHidden()
    assert collider._lbl.text() == "feet [Feet]"

    collider._click_clear()
    assert comp.collider_id == ""
    assert collider._lbl.text() == "Auto"

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
    assert use_gravity.parentWidget().isHidden()
    assert written[-1] == ("mode", "RigidBody")
    assert comp.mode == "RigidBody"

    mass.setValue(2.5)
    gravity_scale.setValue(0.5)
    can_sleep.setChecked(False)
    assert (comp.mass, comp.gravity_scale, comp.can_sleep) == (2.5, 0.5, False)
    assert written[-3:] == [("mass", 2.5), ("gravity_scale", 0.5), ("can_sleep", False)]


def test_meta_inline_donne_le_mode_pour_la_barre(qapp):
    """L'éditeur propose le Mode comme champ inline (à loger à la place de l'id) :
    un combo des quatre noms canoniques, qui écrit `mode`."""
    written = []
    comp = PhysicsBodyComponent()
    actor = Actor(name="Hero", components=[comp])
    inspector = SimpleNamespace(
        _set_comp=lambda c, f, v: (written.append((f, v)), setattr(c, f, v)),
        _field_syncers={}, _actor=actor)

    inline = PhysicsBodyEditor(inspector).meta_inline(comp)
    assert inline is not None
    lab, combo = inline
    assert isinstance(combo, QComboBox)
    assert [combo.itemData(i) for i in range(combo.count())] == \
        ["StaticBody", "CharacterBody", "KinematicBody", "RigidBody"]
    combo.setCurrentIndex(combo.findData("KinematicBody"))
    assert comp.mode == "KinematicBody" and written[-1] == ("mode", "KinematicBody")


def test_meta_bar_loge_le_champ_inline_a_la_place_de_l_id(qapp):
    """`meta_bar(show_id=False, inline=(label, widget))` pose le champ dans l'espace
    de l'id, à côté d'Active, sans champ id."""
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit

    host = QWidget()
    layout = QVBoxLayout(host)
    comp = SimpleNamespace(id="", active=True)
    probe = QComboBox()
    W.meta_bar(comp, {}, lambda *a: None, layout,
               show_id=False, inline=("Mode", probe))

    meta = probe.parentWidget()
    assert meta.findChild(QCheckBox) is not None     # Active est dans la même barre
    assert meta.findChild(QLineEdit) is None          # pas de champ id
    assert host.findChild(QComboBox) is probe
