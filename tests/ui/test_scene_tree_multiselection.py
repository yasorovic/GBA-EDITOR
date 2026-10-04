from core.models.scene import Actor, Scene
from core.scene_tree_state import SceneTreeState
from PyQt6.QtCore import Qt


def test_priority_tree_highlights_multiple_mutable_actors(qapp):
    """La projection Priority accepte la même multi-sélection que Content."""
    from ui.scene_manager.scene_tree_panel import _PrioritySceneTree, _ROLE_OBJ

    actors = [Actor(name="First"), Actor(name="Second")]
    tree = _PrioritySceneTree(None)
    tree.populate(None, Scene(name="Test", actors=actors))

    tree.highlight_actors(actors)

    selected = [item.data(0, _ROLE_OBJ) for item in tree.selectedItems()]
    assert len(selected) == 2
    assert all(any(item is actor for item in selected) for actor in actors)


def test_content_tree_eye_masque_un_acteur_dans_le_sidecar(qapp, tmp_path):
    """L'œil ne modifie pas l'acteur : il ne change que l'état éditorial."""
    from types import SimpleNamespace
    from ui.scene_manager.scene_tree_panel import _ActiveSceneTree, _ROLE_OBJ, _ROLE_TYPE, T_ACTOR

    actor = Actor(name="Hero")
    scene = Scene(name="Test", actors=[actor])
    state = SceneTreeState(tmp_path)
    panel = SimpleNamespace(_content_state=state, refresh=lambda: None)
    tree = _ActiveSceneTree(panel)
    tree.populate(None, scene)
    item = next(item for item in tree.findItems("",  # tous les descendants
                                                 Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive, 0)
                if item.data(0, _ROLE_TYPE) == T_ACTOR and item.data(0, _ROLE_OBJ) is actor)

    tree.itemWidget(item, 1).click()

    assert not state.member_visible(scene.name, "actor:Hero")
    assert actor.visible is True


def test_selection_venue_du_canvas_pose_l_item_courant(qapp, tmp_path):
    """Sélectionnée depuis le canvas, la ligne est PRIMAIRE (courante : fond
    plein de la grammaire de sélection), pas un simple contour secondaire."""
    from ui.scene_manager.scene_tree_panel import _ActiveSceneTree, _ROLE_OBJ

    actors = [Actor(name="First"), Actor(name="Second")]
    from types import SimpleNamespace
    panel = SimpleNamespace(_content_state=SceneTreeState(tmp_path), refresh=lambda: None)
    tree = _ActiveSceneTree(panel)
    tree.populate(None, Scene(name="Test", actors=actors))

    tree.highlight_actors(actors, actors[1])

    assert tree.currentItem().data(0, _ROLE_OBJ) is actors[1]
    assert len(tree.selectedItems()) == 2
