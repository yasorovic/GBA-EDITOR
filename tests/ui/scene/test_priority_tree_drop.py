"""La projection Priorité : l'arbre garde l'ouverture que l'auteur lui a donnée d'un geste à l'autre (seul le récepteur d'un
dépôt s'ouvre), et refuse dès le survol ce qui ne se range pas (un acteur sous un Background)."""
from __future__ import annotations

from types import SimpleNamespace

from core.models.background import BackgroundLayer
from core.models.scene import Actor, Scene
from ui.scene_manager.scene_tree_panel import (
    _PrioritySceneTree, T_PRIORITY_GROUP, T_ACTOR, _ROLE_TYPE, _ROLE_PATH,
)


def _tree(qapp):
    scene = Scene(name="S", background_layers=[BackgroundLayer(background_name="sky", bg_slot=1)])
    hero = Actor(name="Hero"); hero.priority = 1
    scene.actors.append(hero)
    tree = _PrioritySceneTree(SimpleNamespace())
    tree._populate(None, scene)
    return tree, scene


def _group(tree, kind, slot):
    return next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                if tuple(tree.topLevelItem(i).data(0, _ROLE_PATH)) == (kind, slot))


def test_a_collapsed_node_stays_collapsed_after_the_tree_is_rebuilt(qapp):
    tree, scene = _tree(qapp)
    assert _group(tree, "bg", 1).isExpanded()                       # défaut : un Background est ouvert
    _group(tree, "bg", 1).setExpanded(False)                        # l'auteur le referme
    _group(tree, "obj", 1).setExpanded(True)                        # et ouvre un OBJ
    tree._populate(None, scene)                                     # chaque geste reconstruit l'arbre
    assert not _group(tree, "bg", 1).isExpanded()
    assert _group(tree, "obj", 1).isExpanded()
    assert not _group(tree, "obj", 2).isExpanded()                  # le reste n'a pas bougé


def test_an_actor_only_lands_under_an_obj_group(qapp):
    tree, _scene = _tree(qapp)
    hero = _group(tree, "obj", 1).child(0)
    assert hero.data(0, _ROLE_TYPE) == T_ACTOR
    assert tree._drop_host(hero, _group(tree, "bg", 1)) is None     # dans un Background : interdit
    assert tree._drop_host(hero, _group(tree, "obj", 3)) is not None
    host, kind, slot = tree._drop_host(hero, hero)                  # sur un frère : son groupe
    assert (kind, slot) == ("obj", 1)
    assert host.data(0, _ROLE_TYPE) == T_PRIORITY_GROUP
    assert tree._drop_host(hero, None) is None
