"""L'éditeur du composant Interactive dans l'inspecteur d'acteur, et le tag réservé dans la matrice."""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtWidgets import QComboBox, QSpinBox, QVBoxLayout, QWidget

from core.models.components import CollisionBoxComponent, InteractiveComponent
from ui.common.widgets import W
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


def test_l_editeur_propose_les_deux_selecteurs_et_la_zone(qapp):
    host, _ = _build(InteractiveComponent(), boxes=[CollisionBoxComponent(tag="reach")])
    saisie, interaction, zone = _combos(host)
    assert [saisie.itemData(i) for i in range(saisie.count())] == ["pressed", "hold", "released"]
    assert [interaction.itemData(i) for i in range(interaction.count())] == ["hover", "facing"]
    assert [zone.itemData(i) for i in range(zone.count())] == ["", "reach"]     # sa propre boîte, puis l'existante


def test_choisir_un_mode_ecrit_le_champ(qapp):
    comp = InteractiveComponent()
    host, written = _build(comp)
    saisie, interaction, _ = _combos(host)
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
    host, _ = _build(comp, boxes=[CollisionBoxComponent(tag="reach")])
    zone = _combos(host)[2]
    largeur = host.findChildren(QSpinBox)[1]
    assert not largeur.isHidden()
    zone.setCurrentIndex(zone.findData("reach"))
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
    comp = CollisionBoxComponent()
    host = QWidget()
    layout = QVBoxLayout(host)
    CollisionEditor(insp).build(comp, lambda lab, w: W.row(lab, w, layout), layout)

    case = next(c for c in host.findChildren(QCheckBox) if c.text() == "Blocks actors")
    assert not case.isChecked()                    # jamais par défaut
    case.setChecked(True)
    assert ("blocks_actors", True) in written and comp.blocks_actors is True
    insp._field_syncers["blocks_actors"](False)
    assert not case.isChecked()                    # le syncer repeuple sans écrire
