"""Un asset vit où l'auteur l'a rangé sous `assets/` : l'extension de son fichier dit son type, pas son dossier."""
import json
from pathlib import Path

import pytest

from core import disk_tree
from core.models.audio import Music, Sfx
from core.project import Project
from core.validator import validate_project


def _sidecar(path: Path, name: str, **fields) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **fields}), encoding="utf-8")
    return path


def _project(tmp_path: Path) -> Project:
    project = Project(tmp_path)
    project.save_settings()
    return project


def _reopen(root: Path) -> Project:
    project = Project.open(root)
    project.load_all_resources()
    return project


def test_an_asset_outside_its_family_folder_is_found_by_its_extension(tmp_path: Path):
    _project(tmp_path)
    _sidecar(tmp_path / "assets" / "Characters" / "Hero.sprite", "Hero")
    _sidecar(tmp_path / "assets" / "Levels" / "Act1" / "Intro.scene", "Intro")
    _sidecar(tmp_path / "assets" / "Misc" / "Table.table", "Table")

    project = _reopen(tmp_path)

    assert project.sprites.get("Hero") is not None
    assert project.scenes.get("Intro") is not None
    assert project.data_tables.get("Table") is not None


def test_one_folder_can_hold_every_type_and_each_family_takes_only_its_own(tmp_path: Path):
    _project(tmp_path)
    folder = tmp_path / "assets" / "Everything"
    for extension, name in ((".sfx", "boom"), (".music", "theme"), (".jingle", "win"), (".prefab", "Crate")):
        _sidecar(folder / f"{name}{extension}", name, asset=f"assets/Everything/{name}.wav")

    project = _reopen(tmp_path)

    assert [s.name for s in project.sfx] == ["boom"]
    assert [m.name for m in project.music] == ["theme"]
    assert [j.name for j in project.jingles] == ["win"]
    assert [p.name for p in project.prefabs] == ["Crate"]


def test_the_same_name_in_two_types_is_not_a_conflict(tmp_path: Path):
    _project(tmp_path)
    _sidecar(tmp_path / "assets" / "a" / "coin.sfx", "coin", asset="assets/a/coin.wav")
    _sidecar(tmp_path / "assets" / "b" / "coin.music", "coin", asset="assets/b/coin.wav")

    project = _reopen(tmp_path)

    assert project.sfx.get("coin") is not None and project.music.get("coin") is not None
    assert project.sfx.ignored_duplicates() == {} and project.music.ignored_duplicates() == {}


def test_an_asset_is_saved_renamed_and_deleted_where_it_lives(tmp_path: Path):
    _project(tmp_path)
    where = _sidecar(tmp_path / "assets" / "Sounds" / "FX" / "boom.sfx", "boom",
                     asset="assets/Sounds/FX/boom.wav", volume=100, sample_rate=0)
    project = _reopen(tmp_path)
    boom = project.sfx.get("boom")

    boom.volume = 55
    project.sfx.save(boom)
    assert json.loads(where.read_text())["volume"] == 55
    assert not ((project.user_library_dir / "sfx") / "boom.sfx").exists()                      # il n'a pas été ramené dans assets/sfx

    project.sfx.rename(boom, "bang")
    assert (where.parent / "bang.sfx").is_file() and not where.exists()

    project.sfx.delete(boom)
    assert not (where.parent / "bang.sfx").exists()


def test_a_new_asset_is_born_at_the_root_of_assets_and_may_be_placed_anywhere_under_it(tmp_path: Path):
    project = _project(tmp_path)
    project.sfx.save(Sfx(name="plain"))
    assert (project.user_library_dir / "plain.sfx").is_file()

    elsewhere = tmp_path / "assets" / "My sounds"
    project.music.save(Music(name="tune"), elsewhere)
    assert (elsewhere / "tune.music").is_file()
    assert project.music.path_of(project.music.get("tune")) == elsewhere / "tune.music"

    with pytest.raises(ValueError):
        project.sfx.save(Sfx(name="intruder"), tmp_path / "outside")         # hors de assets/


def test_the_same_asset_name_in_two_folders_keeps_the_shallowest_and_reports_the_other(tmp_path: Path):
    _project(tmp_path)
    kept = _sidecar(tmp_path / "assets" / "Hero.sprite", "Hero")
    ignored = _sidecar(tmp_path / "assets" / "old" / "backup" / "Hero.sprite", "Hero")
    before = ignored.read_text()

    project = _reopen(tmp_path)

    assert project.sprites.index.path_for("Hero") == kept
    assert list(project.sprites.ignored_duplicates()) == ["old/backup/Hero.sprite"]
    project.sprites.save_all()
    assert ignored.read_text() == before                                     # ni lu, ni réécrit
    warnings, _ = validate_project(project)
    assert any("old/backup/Hero.sprite" in str(w) and "ignored" in str(w) for w in warnings)


def test_the_disk_tab_marks_a_misplaced_asset_as_an_asset(tmp_path: Path):
    _project(tmp_path)
    _sidecar(tmp_path / "assets" / "Anywhere" / "Hero.sprite", "Hero")
    project = _reopen(tmp_path)

    nodes = {n.path.relative_to(project.user_library_dir).as_posix(): n
             for n in disk_tree.build_disk_tree(project).walk() if n.path != project.user_library_dir}

    node = nodes["Anywhere/Hero.sprite"]
    assert (node.kind, node.family, node.owner) == (disk_tree.ASSET, "sprites", "Hero")


def test_palettes_stay_in_their_own_folder(tmp_path: Path):
    project = _project(tmp_path)
    _sidecar(tmp_path / "assets" / "Elsewhere" / "Night.palette", "Night")

    reopened = _reopen(tmp_path)

    assert reopened.palettes.get("Night") is None                           # le .hex vit dans assets/palettes, avec son sidecar
