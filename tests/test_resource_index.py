from pathlib import Path

from core.resources.resource_index import ResourceIndex, safe_filename
from core.resources.resource_store import ResourceStore
from core.models.scene import Actor, Scene
from core.models.components import SpriteComponent
from core.models.sprite import SpriteAsset
from core.models.background import BackgroundAsset, BackgroundLayer
from core.models.audio import Sfx, Music
from core.project import Project


def test_index_lists_json_sidecars_without_reading_them(tmp_path: Path):
    (tmp_path / "Hero.json").write_text("not json", encoding="utf-8")
    (tmp_path / "Arena.json").write_text("{", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("x", encoding="utf-8")

    index = ResourceIndex(tmp_path)
    index.scan()

    assert index.names() == ("Arena", "Hero")
    assert index.path_for("Hero") == tmp_path / "Hero.json"
    assert "Arena" in index


def test_index_uses_the_same_safe_filename_as_the_store(tmp_path: Path):
    (tmp_path / "Boss_1.json").write_text("{}", encoding="utf-8")

    index = ResourceIndex(tmp_path)
    index.scan()

    assert safe_filename("Boss:1") == "Boss_1"
    assert index.path_for("Boss:1") == tmp_path / "Boss_1.json"


def test_store_can_load_one_indexed_resource_without_loading_the_collection(tmp_path: Path):
    store = ResourceStore(tmp_path, Scene)
    scene = Scene(name="Arena")
    store.save(scene)

    assert store.known_names() == ("Arena",)
    assert list(store) == []
    assert store.ensure_loaded("Arena").name == "Arena"
    assert [scene.name for scene in store] == ["Arena"]


def test_project_indexes_heavy_asset_families_until_their_screen_needs_them(tmp_path: Path):
    writer = Project(tmp_path)
    writer.sprites.save(SpriteAsset(name="Hero"))
    writer.backgrounds.save(BackgroundAsset(name="Sky"))
    writer.sfx.save(Sfx(name="Blip"))
    writer.music.save(Music(name="Theme"))
    writer.save_settings()   # le manifeste : sans lui, le dossier n'est pas un projet

    project = Project.open(tmp_path)

    assert project.sprites.known_names() == ("Hero",)
    assert project.backgrounds.known_names() == ("Sky",)
    assert project.sfx.known_names() == ("Blip",)
    assert project.music.known_names() == ("Theme",)
    assert not list(project.sprites)
    assert project.get_sprite("Hero").name == "Hero"

    project.load_all_resources()

    assert [asset.name for asset in project.backgrounds] == ["Sky"]
    assert [asset.name for asset in project.sfx] == ["Blip"]
    assert [asset.name for asset in project.music] == ["Theme"]


def test_project_preloads_only_the_active_scene_assets(tmp_path: Path):
    writer = Project(tmp_path)
    writer.sprites.save(SpriteAsset(name="Hero"))
    writer.sprites.save(SpriteAsset(name="Unused sprite"))
    writer.backgrounds.save(BackgroundAsset(name="Sky"))
    writer.backgrounds.save(BackgroundAsset(name="Unused background"))
    writer.scenes.save(Scene(
        name="Arena",
        background_layers=[BackgroundLayer(background_name="Sky")],
        actors=[Actor(components=[SpriteComponent(sprite_name="Hero")])],
    ))
    writer.save_settings()

    project = Project.open(tmp_path)

    assert [asset.name for asset in project.backgrounds] == ["Sky"]
    assert [asset.name for asset in project.sprites] == ["Hero"]
    assert "Unused background" in project.backgrounds.known_names()
    assert "Unused sprite" in project.sprites.known_names()
