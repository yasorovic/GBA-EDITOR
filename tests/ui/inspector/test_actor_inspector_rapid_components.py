"""Enchaîner les ajouts de composants sans pause ne perd rien : chaque ajout est entier avant le suivant."""
from __future__ import annotations

from PyQt6.QtWidgets import QMenu

from core.history import get_history
from core.models.scene import Actor, Scene
from core.project import Project
from ui.scene_manager.inspectors.actor_inspector import ActorInspector
from ui.common.labels import label


def test_menu_ajout_masque_la_physique_desactivee(qapp, tmp_path, monkeypatch):
    project = Project(tmp_path / "jeu")
    actor = Actor(name="Hero")
    scene = Scene(name="Village", actors=[actor], physics_enabled=False)
    insp = ActorInspector()
    insp.load(actor, project=project, scene=scene)
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *args: menus.append(
        {action.text(): action.isEnabled() for action in menu.actions()}))

    for enabled in (False, True, False):
        scene.physics_enabled = enabled
        insp._show_add_menu()
        entries = menus[-1]
        for key in ("actorinsp.comp.physics_body", "actorinsp.comp.physic_material"):
            assert (label(key) in entries) == enabled
            if enabled:
                assert entries[label(key)]
        assert label("actorinsp.comp.collision_shape") in entries

    insp.close()
    insp.deleteLater()


def test_des_ajouts_enchaines_sans_pause_sont_tous_pris(qapp, tmp_path):
    project = Project(tmp_path / "jeu")
    actor = Actor(name="Hero")
    scene = Scene(name="Village", actors=[actor])
    project.scenes.append(scene)
    insp = ActorInspector()
    insp.load(actor, project=project, scene=scene)
    get_history().clear()
    before = len(actor.components)

    for type_name in ("sprite", "collision_shape", "sprite", "collision_shape"):
        insp._add_component(type_name)

    kinds = [type(c).__name__ for c in actor.components[before:]]
    assert len(kinds) == 4
    assert insp._comp_list.count() == len(actor.components)
    assert insp._comp_list.currentRow() == len(actor.components) - 1     # le dernier ajouté est celui que l'inspecteur montre


def test_ajouter_un_composant_fait_defiler_jusqu_a_la_carte_components(qapp, tmp_path):
    project = Project(tmp_path / "jeu")
    actor = Actor(name="Hero")
    scene = Scene(name="Village", actors=[actor])
    project.scenes.append(scene)
    insp = ActorInspector()
    insp.resize(320, 260)                       # un panneau bas : les cartes du haut cachent celle des composants
    insp.show()
    insp.load(actor, project=project, scene=scene)
    qapp.processEvents()
    bar = insp._scroll.verticalScrollBar()
    assert bar.value() == 0 and bar.maximum() > 0

    insp._add_component("sprite")
    qapp.processEvents()
    qapp.processEvents()

    assert bar.value() > 0
