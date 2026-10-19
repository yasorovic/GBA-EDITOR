"""Les gestes de création hors finders passent tous par *Create blank* : un nœud Interface, un script d'acteur, une scène."""
from core import asset_creation
from core.history import CommandHistory
from core.models.scene import Scene
from core.project import Project


def _project(tmp_path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p.load_all_resources()
    return p


def test_an_interface_is_a_layout_plus_its_node_and_undoes_as_one(tmp_path):
    p = _project(tmp_path)
    scene = Scene(name="Level")
    folder = p.assets_dir / "UI"
    history, persisted = CommandHistory(), []

    gesture = asset_creation.create_interface(p, scene, folder, persist=lambda: persisted.append(1))
    history.push(gesture.command)

    layout = gesture.items[0]
    assert layout.name == "Level" and p.ui_layouts.get("Level") is layout
    assert (folder / "Level.layout").is_file()
    assert [n.layout_name for n in scene.ui_layouts] == ["Level"] and persisted

    history.undo()
    assert not scene.ui_layouts and p.ui_layouts.get("Level") is None
    history.redo()
    assert [n.layout_name for n in scene.ui_layouts] == ["Level"] and p.ui_layouts.get("Level") is layout


def test_an_actor_script_takes_the_wanted_name_and_a_taken_one_is_suffixed(tmp_path):
    p = _project(tmp_path)
    folder = p.assets_dir / "AI"
    history = CommandHistory()

    for expected in ("Hero", "Hero_2"):
        gesture = asset_creation.create_blank(p, "script", folder, name="Hero", template="actor")
        history.push(gesture.command)
        assert gesture.names == [expected] and (folder / f"{expected}.lua").is_file()

    history.undo()
    assert not (folder / "Hero_2.lua").exists() and (folder / "Hero.lua").is_file()


def test_a_blank_scene_is_born_in_the_given_folder_with_its_defaults(tmp_path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Levels"
    history = CommandHistory()

    gesture = asset_creation.create_blank(p, "scene", folder)
    history.push(gesture.command)

    scene = gesture.items[0]
    assert p.scenes.get(scene.name) is scene and scene.cameras
    assert (folder / f"{scene.name}.scene").is_file()
    history.undo()
    assert p.scenes.get(scene.name) is None
