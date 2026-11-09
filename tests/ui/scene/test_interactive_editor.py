"""L'éditeur du composant Interactive dans l'inspecteur d'acteur, et le tag réservé dans la matrice."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QComboBox, QSpinBox, QVBoxLayout, QWidget

from core.models.components import CollisionShapeComponent, InteractiveComponent
from ui.common.widgets import PickerSlot, W
from ui.common.unit_spin import UnitSpin
from ui.scene_manager.inspectors.component_editors.interactive import InteractiveEditor


def _build(comp, boxes=()):
    """L'éditeur monté dans un faux inspecteur ; rend (hôte, champs écrits)."""
    written = []
    actor = SimpleNamespace(components=[comp, *boxes])

    def set_comp(c, field, value):
        written.append((field, value))
        setattr(c, field, value)

    insp = SimpleNamespace(_actor=actor, _project=None, _set_comp=set_comp, _field_syncers={})
    host = QWidget()
    layout = QVBoxLayout(host)
    InteractiveEditor(insp).build(comp, lambda lab, w: W.row(lab, w, layout), layout)
    host.show()
    return host, written


def _combos(host):
    return host.findChildren(QComboBox)


def test_soundfx_propose_et_conserve_le_declencheur_interaction(qapp):
    from core.models.components import SoundFxComponent
    from ui.scene_manager.inspectors.component_editors.sfx import SfxEditor
    comp = SoundFxComponent(trigger="on_interact")
    written = []
    insp = SimpleNamespace(_project=None, _set_comp=lambda c, field, value: written.append((field, value)))
    host = QWidget()
    layout = QVBoxLayout(host)
    SfxEditor(insp).build(comp, lambda lab, widget: W.row(lab, widget, layout), layout)
    trigger = _combos(host)[0]
    assert trigger.currentData() == "on_interact"
    trigger.setCurrentIndex(trigger.findData("manual"))
    trigger.setCurrentIndex(trigger.findData("on_interact"))
    assert written[-1] == ("trigger", "on_interact")


def test_l_editeur_propose_les_deux_selecteurs_et_la_zone(qapp):
    host, _ = _build(InteractiveComponent(), boxes=[CollisionShapeComponent(tag="reach")])
    saisie, interaction = _combos(host)
    zone = host.findChild(PickerSlot)
    assert [saisie.itemData(i) for i in range(saisie.count())] == ["pressed", "hold", "released"]
    assert [interaction.itemData(i) for i in range(interaction.count())] == ["hover", "facing"]
    assert [e.value for e in zone.popup_entries()] == ["", "reach"]     # sa propre boîte, puis l'existante


def test_choisir_un_mode_ecrit_le_champ(qapp):
    comp = InteractiveComponent()
    host, written = _build(comp)
    saisie, interaction = _combos(host)
    saisie.setCurrentIndex(saisie.findData("hold"))
    interaction.setCurrentIndex(interaction.findData("facing"))
    assert ("input_mode", "hold") in written and ("interaction", "facing") in written
    assert (comp.input_mode, comp.interaction) == ("hold", "facing")


def test_le_maintien_n_apparait_que_pour_hold(qapp):
    comp = InteractiveComponent()
    host, _ = _build(comp)
    saisie = _combos(host)[0]
    maintien = host.findChildren(UnitSpin)[0]
    assert maintien.parentWidget().isHidden()
    saisie.setCurrentIndex(saisie.findData("hold"))
    assert not maintien.parentWidget().isHidden()


def test_la_taille_n_apparait_que_pour_la_boite_propre(qapp):
    comp = InteractiveComponent()
    host, _ = _build(comp, boxes=[CollisionShapeComponent(tag="reach")])
    zone = host.findChild(PickerSlot)
    largeur = host.findChildren(QSpinBox)[1]
    assert not largeur.isHidden()
    zone.pick("reach")
    assert comp.box_tag == "reach"
    assert largeur.isHidden() or not largeur.isVisibleTo(host)


# ── Collision : la case « Bloque les acteurs » ──

def test_la_boite_de_collision_a_sa_case_de_blocage(qapp):
    from PyQt6.QtWidgets import QCheckBox
    from ui.scene_manager.inspectors.component_editors.collision import CollisionEditor

    class _Inspecteur(QWidget):
        pass

    insp = _Inspecteur()
    insp._project = SimpleNamespace(collision_tags=lambda: ["body"], settings=SimpleNamespace(collision_tags=[]),
                                    save_settings=lambda: None, globals=[], constants=[])
    insp._field_syncers = {}
    written = []

    def set_comp(c, field, value):
        written.append((field, value))
        setattr(c, field, value)

    insp._set_comp = set_comp
    comp = CollisionShapeComponent()
    host = QWidget()
    layout = QVBoxLayout(host)
    CollisionEditor(insp).build(comp, lambda lab, w: W.row(lab, w, layout), layout)

    case = next(c for c in host.findChildren(QCheckBox) if c.text() == "Block")
    assert not case.isChecked()                    # jamais par défaut
    case.setChecked(True)
    assert ("response", "block") in written and comp.response == "block"
    insp._field_syncers["response"]("sensor")
    assert not case.isChecked()                    # le syncer repeuple sans écrire


def test_le_materiau_physique_ecrit_son_rebond_et_son_frottement(qapp):
    from PyQt6.QtWidgets import QDoubleSpinBox
    from core.models.components import PhysicMaterialComponent
    from ui.scene_manager.inspectors.component_editors.physic_material import PhysicMaterialEditor

    insp = QWidget()
    insp._project = SimpleNamespace(globals=[], constants=[])
    insp._field_syncers = {}
    written = []
    insp._set_comp = lambda c, field, value: (written.append((field, value)), setattr(c, field, value))
    comp = PhysicMaterialComponent()
    host = QWidget()
    layout = QVBoxLayout(host)
    PhysicMaterialEditor(insp).build(comp, lambda lab, w: W.row(lab, w, layout), layout)

    host.findChild(QDoubleSpinBox, "materialRestitution").setValue(0.75)
    host.findChild(QDoubleSpinBox, "materialFriction").setValue(0.25)
    assert ("restitution", 0.75) in written and ("friction", 0.25) in written


def test_soundfx_garde_un_effet_disparu_visible_au_lieu_du_premier(qapp):
    from core.models.components import SoundFxComponent
    from ui.common.widgets import PickerSlot
    from ui.scene_manager.inspectors.component_editors.sfx import SfxEditor
    comp = SoundFxComponent(sfx_name="Gone")
    written = []
    proj = SimpleNamespace(load_audio=lambda: None, sfx=SimpleNamespace(items=[SimpleNamespace(name="Jump")]),
                           settings=SimpleNamespace(inputs=[]))
    insp = SimpleNamespace(_project=proj, _set_comp=lambda c, field, value: written.append((field, value)))
    host = QWidget()
    layout = QVBoxLayout(host)
    SfxEditor(insp).build(comp, lambda lab, widget: W.row(lab, widget, layout), layout)
    sfx = host.findChild(PickerSlot)
    assert sfx.value() == "Gone" and sfx.popup_entries()[-1].missing and written == []
    sfx.pick("Jump")
    assert written == [("sfx_name", "Jump")]
