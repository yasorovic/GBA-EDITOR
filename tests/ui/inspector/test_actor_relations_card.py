"""La carte Relations : toujours là, ses sections Parent et Enfants seulement s'il existe une relation ; elle édite les parties d'un prefab sans le poser dans une scène."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QTreeWidgetItemIterator

from core import command_dispatcher as dispatcher_module
from core.history import get_history
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from core.selection_bus import SelectionBus
from ui.scene_manager.inspectors import actor_inspector as inspector_module
from ui.scene_manager.inspectors.actor_inspector import ActorInspector


def _setup(tmp_path):
    project = Project(tmp_path / "jeu")
    project.root.mkdir(parents=True, exist_ok=True)
    scene = Scene(name="Arena")
    parent = Actor(name="Boss", x=0, y=0)
    child = Actor(name="Arm", x=8, y=8, parent="Boss")
    alone = Actor(name="Ball", x=0, y=0)
    scene.actors.extend([parent, child, alone])
    project.scenes.append(scene)
    return project, scene, parent, child, alone


def test_the_sections_only_show_for_an_actor_with_a_relation(qapp, tmp_path):
    project, scene, parent, child, alone = _setup(tmp_path)
    inspector = ActorInspector()

    inspector.load(alone, project, scene)
    assert not inspector._rel_card.isHidden()                         # le « + » crée le premier enfant
    assert inspector._rel_parent_host.isHidden() and inspector._rel_children_host.isHidden()

    inspector.load(parent, project, scene)
    assert not inspector._rel_card.isHidden()
    assert not inspector._rel_children_host.isHidden() and inspector._rel_parent_host.isHidden()
    assert inspector._children_tree.topLevelItemCount() == 1

    inspector.load(child, project, scene)
    assert not inspector._rel_card.isHidden()
    assert not inspector._rel_parent_host.isHidden() and inspector._rel_parent_btn.text() == "Boss"
    assert inspector._rel_children_host.isHidden()


def test_a_prefab_root_adds_a_part_without_being_placed_in_a_scene(qapp, tmp_path):
    project, scene, *_ = _setup(tmp_path)
    prefab = Prefab(name="Dragon", actor=Actor(name="Dragon"))
    inspector = ActorInspector()
    inspector.load_prefab(prefab, project, None)
    assert not inspector._rel_card.isHidden() and not inspector._rel_add.isHidden()

    inspector._persist = lambda: None
    inspector._rel_add.click()

    assert [pt.name for pt in prefab.children] == ["Part"]
    assert inspector._children_tree.topLevelItemCount() == 1


@pytest.fixture
def relations(qapp, tmp_path, monkeypatch):
    project, scene, parent, child, alone = _setup(tmp_path)
    dispatcher = dispatcher_module.CommandDispatcher()
    dispatcher._project = project
    bus = SelectionBus()
    monkeypatch.setattr(dispatcher_module, "get_bus", lambda: bus)
    monkeypatch.setattr(inspector_module, "get_bus", lambda: bus)
    monkeypatch.setattr(inspector_module, "get_dispatcher", lambda: dispatcher)
    inspector = ActorInspector()
    bus.changed.connect(lambda actor: inspector.load(actor, project, scene))
    get_history().clear()
    yield inspector, dispatcher, bus, project, scene, parent, child, alone
    get_history().clear()
    inspector.close()
    inspector.deleteLater()


def test_ajout_enfant_definit_le_parent_avant_notification_et_selection(relations):
    inspector, dispatcher, bus, project, scene, parent, _, _ = relations
    bus.select(parent)
    notifications = []
    dispatcher.on("actors_list_changed", lambda: notifications.append(
        [(actor.name, actor.parent) for actor in scene.actors]))

    inspector._rel_add.click()

    child = scene.actors[-1]
    assert child.parent == parent.name
    assert bus.current is child and inspector._actor is child
    assert notifications == [[(actor.name, actor.parent) for actor in scene.actors]]
    assert (child.x, child.y) == (parent.x, parent.y)

    from ui.scene_manager import scene_tree_panel as tree_module
    panel = tree_module.SceneTreePanel()
    panel.load_project(project)
    iterator = QTreeWidgetItemIterator(panel._tree)
    child_item = None
    while iterator.value():
        item = iterator.value()
        if item.data(0, tree_module._ROLE_OBJ) is child:
            child_item = item
            break
        iterator += 1
    assert child_item is not None
    assert child_item.parent().data(0, tree_module._ROLE_OBJ) is parent
    get_history().undo()
    assert all(actor is not child for actor in scene.actors)
    get_history().redo()
    assert scene.actors[-1] is child and child.parent == parent.name
    panel.close()
    panel.deleteLater()


def test_moins_detache_sans_supprimer_et_annulation_restaure_le_lien(relations):
    inspector, dispatcher, bus, _, scene, parent, child, _ = relations
    grandchild = Actor(name="Hand", parent=child.name)
    scene.actors.append(grandchild)
    bus.select(parent)
    actors = tuple(scene.actors)
    assert not inspector._rel_del.isHidden()
    assert not inspector._rel_del.isEnabled()
    inspector._children_tree.select_part(child)
    assert inspector._rel_del.isEnabled()

    inspector._rel_del.click()

    assert child.parent is None
    assert len(scene.actors) == len(actors)
    assert all(actual is expected for actual, expected in zip(scene.actors, actors))
    assert grandchild.parent == child.name
    assert inspector._children_tree.topLevelItemCount() == 0
    assert not inspector._rel_del.isEnabled()
    assert bus.current is parent
    get_history().undo()
    assert child.parent == parent.name
    assert inspector._children_tree.topLevelItemCount() == 1
    get_history().redo()
    assert child.parent is None
    assert inspector._children_tree.topLevelItemCount() == 0


def test_plus_repete_cree_une_chaine_sans_cycle(relations):
    inspector, _, bus, _, scene, parent, _, _ = relations
    bus.select(parent)
    inspector._rel_add.click()
    child = bus.current
    inspector._rel_add.click()
    grandchild = bus.current
    assert child.parent == parent.name
    assert grandchild.parent == child.name
    assert grandchild.name != child.name
    assert (grandchild.x, grandchild.y) == (parent.x, parent.y)
    get_history().undo()
    assert all(actor is not grandchild for actor in scene.actors)
    get_history().undo()
    assert all(actor is not child for actor in scene.actors)
