"""ActorInspector — les champs liés par `FieldBinder` reflètent le modèle, et une
édition les y réécrit.

Ces tests couvrent le contrat que l'inspecteur promet à l'utilisateur : ce qu'il
affiche EST l'état de l'acteur sélectionné (jamais celui d'un acteur précédent),
et éditer un champ mute l'acteur : aucun champ ne garde la valeur d'un acteur précédent.
"""
from __future__ import annotations

import pytest

from core.models.scene import Actor
from ui.scene_manager.inspectors.actor_inspector import ActorInspector

# Les champs 1:1 confiés au binder, avec deux jeux de valeurs distincts.
_A = dict(x=48, y=96,
          priority=2, obj_mode=2, screen_space=True, visible=False)
_B = dict(x=8, y=8,
          priority=0, obj_mode=0, screen_space=False, visible=True)


def _widget_state(insp: ActorInspector) -> dict:
    return dict(
        x=insp._tx.raw(), y=insp._ty.raw(),
        priority=insp._tpriority.raw(),
        obj_mode=[0, 2][insp._tobj_mode.currentIndex()],
        screen_space=insp._tscreen.isChecked(),
        visible=insp._tvisible.isChecked(),
    )


def test_load_reflete_le_modele(qapp):
    insp = ActorInspector()
    insp.load(Actor(name="Hero", **_A), project=None, scene=None)
    st = _widget_state(insp)
    for k, v in _A.items():
        assert st[k] == pytest.approx(v), f"{k}: widget {st[k]} != modèle {v}"


def test_changer_dacteur_repeuple_tout(qapp):
    """Après un second `load`, aucun champ ne doit garder la valeur du premier acteur."""
    insp = ActorInspector()
    insp.load(Actor(name="Hero", **_A), project=None, scene=None)
    insp.load(Actor(name="Coin", **_B), project=None, scene=None)
    st = _widget_state(insp)
    for k, v in _B.items():
        assert st[k] == pytest.approx(v), f"{k}: widget {st[k]} != modèle {v}"


def test_edition_ecrit_dans_le_modele(qapp):
    insp = ActorInspector()
    a = Actor(name="Hero", **_B)
    insp.load(a, project=None, scene=None)

    insp._tvisible.setChecked(False)
    insp._tpriority._spin.setValue(3)

    assert a.visible is False
    assert a.priority == 3


# ── Le tag Joueur : une case visible d'emblée, pas cachée dans une carte repliée ──

def test_la_case_joueur_est_visible_sans_rien_deplier(qapp):
    insp = ActorInspector()
    insp.resize(380, 900)
    insp.show()
    insp.load(Actor(name="Hero"), project=None, scene=None)
    qapp.processEvents()
    assert insp._tplayer.isVisible()


def test_la_case_joueur_reflete_et_ecrit_le_modele(qapp):
    insp = ActorInspector()
    a = Actor(name="Hero", is_player=True)
    insp.load(a, project=None, scene=None)
    assert insp._tplayer.isChecked()

    insp._tplayer.setChecked(False)
    assert a.is_player is False

    insp.load(Actor(name="Coin"), project=None, scene=None)
    assert not insp._tplayer.isChecked()


def _origine(widget, parent):
    p = widget.mapTo(parent, widget.rect().topLeft())
    return p.x(), p.y()


def test_actif_et_joueur_sont_cote_a_cote_quand_la_place_le_permet(qapp):
    insp = ActorInspector()
    insp.resize(600, 900)
    insp.show()
    insp.load(Actor(name="Hero"), project=None, scene=None)
    qapp.processEvents()
    qapp.processEvents()
    (ax, ay), (px, py) = _origine(insp._active, insp), _origine(insp._tplayer, insp)
    assert ay == py and px > ax


def test_joueur_passe_sous_actif_quand_la_fenetre_est_etroite(qapp):
    insp = ActorInspector()
    insp.resize(200, 900)
    insp.show()
    insp.load(Actor(name="Hero"), project=None, scene=None)
    qapp.processEvents()
    qapp.processEvents()
    (ax, ay), (px, py) = _origine(insp._active, insp), _origine(insp._tplayer, insp)
    assert py > ay and px == ax


# ── Un prefab peut être le joueur ──

def test_la_racine_d_un_prefab_peut_etre_cochee_joueur(qapp):
    from core.models.scene import Prefab
    insp = ActorInspector()
    insp.resize(600, 900)
    insp.show()
    prefab = Prefab(name="Hero")
    insp.load_prefab(prefab, project=None, scene=None)
    qapp.processEvents()
    assert insp._tplayer.isVisible() and not insp._tplayer.isChecked()

    insp._tplayer.setChecked(True)
    assert prefab.actor.is_player is True and prefab.is_player is True


def test_la_case_joueur_reflete_un_prefab_deja_joueur(qapp):
    from core.models.scene import Actor, Prefab
    insp = ActorInspector()
    insp.load_prefab(Prefab(name="Hero", actor=Actor(name="Hero", is_player=True)),
                     project=None, scene=None)
    assert insp._tplayer.isChecked()


def test_une_partie_de_prefab_n_a_pas_la_case_joueur(qapp):
    from core.models.scene import Prefab
    insp = ActorInspector()
    insp.resize(600, 900)
    insp.show()
    prefab = Prefab(name="Boss")
    part = Actor(name="Arm")
    prefab.children.append(part)
    insp.load_child(part, prefab, project=None, scene=None)
    qapp.processEvents()
    assert not insp._tplayer.isVisible()


@pytest.mark.parametrize("mode", ["actor", "instance", "prefab", "part"])
def test_note_et_identite_restent_fixes_pendant_le_defilement(qapp, monkeypatch, mode):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QWidget
    from core.models.scene import Prefab
    from ui.common import card_order
    from ui.common.labels import label
    from ui.common.widgets import CollapsibleCard

    monkeypatch.setattr(card_order, "load", lambda panel: [
        label("actorinsp.card.components"), label("common.note"),
        label("actorinsp.card.transform"), label("actorinsp.card.relations"),
    ])
    monkeypatch.setattr(card_order, "save", lambda *args: None)
    insp = ActorInspector()
    actor = Actor(name="Hero", notes="Une note")
    prefab = Prefab(name="Hero", actor=actor)
    if mode == "prefab":
        insp.load_prefab(prefab, project=None)
    elif mode == "part":
        prefab.children.append(actor := Actor(name="Part", notes="Une note"))
        insp.load_child(actor, prefab, project=None)
    else:
        if mode == "instance":
            actor.prefab_name = "Hero"
        insp.load(actor, project=None)
    insp.resize(400, 450)
    insp.show()
    insp._transform_group.set_expanded(True)
    insp._comp_card.set_expanded(True)
    insp._comp_card.body_layout.addWidget(spacer := QWidget())
    spacer.setMinimumHeight(900)
    qapp.processEvents()
    header = insp._sprite_preview.parentWidget()
    assert header.isAncestorOf(insp._active)
    assert header.isAncestorOf(insp._tplayer)
    widgets = [insp._notes_edit, insp._sprite_preview, insp._tag_lbl, insp._active]
    if mode != "part":
        widgets.append(insp._tplayer)
    if mode == "actor":
        widgets.append(insp._expose_row)
    elif mode == "instance":
        widgets.append(insp._prefab_badge)
    assert all(not insp._scroll.isAncestorOf(w) for w in widgets)
    before = [w.mapTo(insp, QPoint()) for w in widgets]
    assert insp._notes_edit.toPlainText() == "Une note"
    assert not insp._scroll.isAncestorOf(insp._notes_edit)
    assert all(c._title_lbl.text() != label("common.note")
               for c in insp.findChildren(CollapsibleCard))
    insp._comp_card._drop_at(0)
    qapp.processEvents()
    bar = insp._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert [w.mapTo(insp, QPoint()) for w in widgets] == before
    assert all(w.isVisible() for w in widgets)
    insp.load(None, project=None)
    assert all(not w.isVisible() for w in widgets)
    insp.close()


def test_identite_avant_note_et_aucun_vide_avant_les_cartes(qapp):
    from PyQt6.QtCore import QPoint

    insp = ActorInspector()
    insp.resize(450, 900)
    insp.load(Actor(name="Hero"), project=None)
    insp.show()
    qapp.processEvents()
    qapp.processEvents()
    assert insp._sprite_preview.mapTo(insp, QPoint()).y() < insp._notes_edit.y()
    assert insp._flags_row.height() == insp._flags_flow.heightForWidth(insp._flags_row.width())
    cards = [insp._transform_group, insp._comp_card, insp._rel_card]
    first = min((c for c in cards if c.isVisible()), key=lambda c: c.y())
    assert first.y() == 0
    insp.close()
