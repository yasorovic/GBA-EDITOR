"""Un renommage Content conserve le groupe malgré le rafraîchissement synchrone."""
import pytest

from core.models.scene import Actor
from core.project import Project
from core.scene_tree_state import SceneTreeState
from ui.scene_manager.scene_tree_panel import SceneTreePanel, _ROLE_OBJ


@pytest.mark.parametrize("collision", [False, True])
def test_renommer_acteur_conserve_groupe_et_visibilite(qapp, tmp_path, collision):
    project = Project.create(tmp_path / "Game", "Game")
    scene = project.scenes[0]
    actor = Actor(name="Collectible")
    other = Actor(name="Door")
    scene.actors.extend([actor, other])
    project.set_active_scene(0)
    panel = SceneTreePanel()
    panel.load_project(project)
    state = panel._content_state
    folder = state.create_folder(scene.name, "Collectibles")
    state.move_member(scene.name, "actor:Collectible", folder.id)
    state.set_member_visible(scene.name, "actor:Collectible", False)
    other_folder = state.create_folder(scene.name, "Doors")
    state.move_member(scene.name, "actor:Door", other_folder.id)
    panel.refresh()
    tree = panel._tree

    # La notification du projet reconstruit réellement l'arbre AVANT le retour du renommage.
    project.events.on("renamed", lambda *args: panel.refresh())
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
    iterator = QTreeWidgetItemIterator(tree)
    while iterator.value().data(0, _ROLE_OBJ) is not actor:
        iterator += 1
    item = iterator.value()
    tree.blockSignals(True)
    item.setText(0, "Door" if collision else "Coin")
    tree.blockSignals(False)
    tree._commit_rename_actor(item)

    expected = "Collectible" if collision else "Coin"
    assert actor.name == expected
    assert state.folder_of(scene.name, f"actor:{expected}") == folder.id
    assert not state.member_visible(scene.name, f"actor:{expected}")
    assert state.folder_of(scene.name, "actor:Door") == other_folder.id
    reopened = SceneTreeState(project.root)
    assert reopened.folder_of(scene.name, f"actor:{expected}") == folder.id


@pytest.mark.parametrize("kind", ["camera", "ui_element"])
def test_renommer_camera_ou_texte_conserve_groupe(qapp, tmp_path, kind):
    from core.models.camera import Camera
    from core.models.ui_region import UILayout, UIText, InterfaceNode
    from PyQt6.QtWidgets import QTreeWidgetItemIterator

    project = Project.create(tmp_path / "Game", "Game")
    scene = project.scenes[0]
    if kind == "camera":
        obj = Camera(name="ExtraView")
        scene.cameras.append(obj)
        old_key, new_key = "camera:ExtraView", "camera:Renamed"
    else:
        obj = UIText(name="Caption")
        layout = UILayout(name="HUD", elements=[obj])
        project.ui_layouts.append(layout)
        scene.ui_layouts.append(InterfaceNode(layout_name=layout.name))
        old_key, new_key = "ui_element:HUD:Caption", "ui_element:HUD:Renamed"
    project.set_active_scene(0)
    panel = SceneTreePanel()
    panel.load_project(project)
    state = panel._content_state
    folder = state.create_folder(scene.name, "Content")
    state.move_member(scene.name, old_key, folder.id)
    state.set_member_visible(scene.name, old_key, False)
    panel.refresh()
    project.events.on("renamed", lambda *args: panel.refresh())
    tree = panel._tree
    iterator = QTreeWidgetItemIterator(tree)
    while iterator.value() and iterator.value().data(0, _ROLE_OBJ) is not obj:
        iterator += 1
    item = iterator.value()
    assert item is not None
    tree.blockSignals(True)
    item.setText(0, "Renamed")
    tree.blockSignals(False)
    if kind == "camera":
        tree._commit_rename_camera(item)
    else:
        tree._commit_rename_ui_elem(item)
    assert obj.name == "Renamed"
    assert state.folder_of(scene.name, new_key) == folder.id
    assert not state.member_visible(scene.name, new_key)
