"""Le dossier virtuel d'un asset (le rangement de l'asset library) ne dépend pas de l'endroit où son fichier vit."""
import json
import shutil
from pathlib import Path

from core.asset_folder_store import AssetFolderStore
from core.project import Project


def _scene(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name}), encoding="utf-8")


def test_an_asset_keeps_its_virtual_folder_when_its_file_is_moved_on_disk(tmp_path: Path):
    Project(tmp_path).save_settings()
    _scene(tmp_path / "assets" / "scenes" / "Intro.scene", "Intro")
    _scene(tmp_path / "assets" / "scenes" / "Boss.scene", "Boss")

    opened = Project.open(tmp_path)
    folders = AssetFolderStore(tmp_path)
    levels = folders.create_folder("scenes", "Levels")
    intro_id = opened.scenes.id_of("Intro")
    folders.move_member("scenes", intro_id, levels.id)                               # le rangement tient l'ID, pas le nom

    (tmp_path / "assets" / "Story").mkdir()                                         # l'auteur range son disque comme il veut
    shutil.move(tmp_path / "assets" / "scenes" / "Intro.scene", tmp_path / "assets" / "Story" / "Intro.scene")

    reopened = Project.open(tmp_path)
    reopened_folders = AssetFolderStore(tmp_path)
    reopened_folders.prune("scenes", {scene.id for scene in reopened.scenes})        # ce que fait la fenêtre à l'ouverture

    assert {scene.name for scene in reopened.scenes} == {"Intro", "Boss"}            # l'asset est retrouvé là où il est
    assert reopened.scenes.id_of("Intro") == intro_id                                # avec la même identité
    assert reopened_folders.folder_of("scenes", intro_id) == levels.id               # et toujours rangé dans « Levels »
    assert reopened_folders.folder_of("scenes", reopened.scenes.id_of("Boss")) is None


def test_an_asset_keeps_its_virtual_folder_when_it_is_renamed(tmp_path: Path):
    Project(tmp_path).save_settings()
    _scene(tmp_path / "assets" / "scenes" / "Intro.scene", "Intro")

    project = Project.open(tmp_path)
    folders = AssetFolderStore(tmp_path)
    levels = folders.create_folder("scenes", "Levels")
    intro = project.scenes.get("Intro")
    folders.move_member("scenes", intro.id, levels.id)

    project.rename_scene(intro, "Prologue")

    assert folders.folder_of("scenes", project.scenes.id_of("Prologue")) == levels.id


def test_the_virtual_folders_of_two_families_do_not_see_each_other(tmp_path: Path):
    folders = AssetFolderStore(tmp_path)
    scenes_folder = folders.create_folder("scenes", "Levels")
    sprites_folder = folders.create_folder("sprites", "Enemies")
    folders.move_member("scenes", "coin", scenes_folder.id)
    folders.move_member("sprites", "coin", sprites_folder.id)                        # même nom, autre famille

    assert folders.folder_of("scenes", "coin") == scenes_folder.id
    assert folders.folder_of("sprites", "coin") == sprites_folder.id
    assert [f.name for f in folders.folders("scenes")] == ["Levels"]
    assert [f.name for f in folders.folders("sprites")] == ["Enemies"]
