"""La carte Relations : toujours là, ses sections Parent et Enfants seulement s'il existe une relation ; elle édite les parties d'un prefab sans le poser dans une scène."""
from __future__ import annotations

from core.models.scene import Actor, Prefab, Scene
from core.project import Project
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
    inspector._add_child()

    assert [pt.name for pt in prefab.children] == ["Part"]
    assert inspector._children_tree.topLevelItemCount() == 1
