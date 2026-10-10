"""Un sidecar peut vivre dans un sous-dossier du dossier de sa famille : l'inventaire le trouve et
chaque opération le traite là où il est."""
import json
from pathlib import Path

import pytest

from core import disk_tree
from core.models.audio import Sfx
from core.project import Project
from core.resources.resource_index import ResourceIndex
from core.resources.resource_store import ResourceStore


def _sfx(folder: Path, name: str, **extra) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.sfx"
    path.write_text(json.dumps({"name": name, "asset": f"assets/sfx/{name}.wav", "volume": 100,
                                "sample_rate": 0, **extra}), encoding="utf-8")
    return path


def _store(directory: Path) -> ResourceStore:
    store = ResourceStore(directory, Sfx)
    store.load()
    return store


def test_the_index_finds_sidecars_at_every_depth(tmp_path: Path):
    (tmp_path / "a.sfx").write_text("{}", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.sfx").write_text("{}", encoding="utf-8")
    (tmp_path / "sub" / "deep").mkdir()
    (tmp_path / "sub" / "deep" / "c.sfx").write_text("{}", encoding="utf-8")
    (tmp_path / "sub" / "c.sfx.corrupt").write_text("x", encoding="utf-8")        # une copie : pas un sidecar

    index = ResourceIndex(tmp_path, ".sfx")
    index.scan()

    assert index.names() == ("a", "b", "c")
    assert index.path_for("c") == tmp_path / "sub" / "deep" / "c.sfx"
    assert index.duplicates == {}


def test_the_shallowest_homonym_wins_and_the_others_are_kept_aside(tmp_path: Path):
    (tmp_path / "coin.sfx").write_text("{}", encoding="utf-8")
    for folder in ("b", "a"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "coin.sfx").write_text("{}", encoding="utf-8")

    index = ResourceIndex(tmp_path, ".sfx")
    index.scan()

    assert index.path_for("coin") == tmp_path / "coin.sfx"                      # le moins profond
    assert [p.relative_to(tmp_path).as_posix() for p in index.duplicates["coin"]] == ["a/coin.sfx", "b/coin.sfx"]


def test_a_nested_sidecar_is_read_saved_renamed_and_deleted_where_it_lives(tmp_path: Path):
    nested = _sfx(tmp_path / "platformer" / "wav", "coin")
    store = _store(tmp_path)
    coin = store.get("coin")
    assert coin is not None and store.path_of(coin) == nested

    coin.volume = 40
    store.save(coin)                                                              # reste là où il est
    assert json.loads(nested.read_text())["volume"] == 40
    assert not (tmp_path / "coin.sfx").exists()

    store.rename(coin, "coin_big")                                                # le fichier reste dans son dossier
    assert (tmp_path / "platformer" / "wav" / "coin_big.sfx").is_file() and not nested.exists()
    assert not (tmp_path / "coin_big.sfx").exists()

    store.delete(coin)
    assert not (tmp_path / "platformer" / "wav" / "coin_big.sfx").exists()


def test_a_soft_deleted_nested_sidecar_is_erased_from_its_own_folder(tmp_path: Path):
    nested = _sfx(tmp_path / "deep", "zap")
    store = _store(tmp_path)
    zap = store.get("zap")

    store.soft_delete(zap)
    assert nested.exists()                                                        # différé jusqu'à la fermeture
    store.commit_deletes()
    assert not nested.exists()


def test_a_new_asset_can_be_placed_in_a_folder_but_never_outside_the_collection(tmp_path: Path):
    store = _store(tmp_path / "sfx")
    store.dir.mkdir(parents=True, exist_ok=True)
    folder = store.dir / "platformer" / "wav"

    store.save(Sfx(name="jump"), folder)
    assert (folder / "jump.sfx").is_file() and not (store.dir / "jump.sfx").exists()
    placed = store.get("jump")
    assert placed is not None and store.path_of(placed) == folder / "jump.sfx"

    store.save(Sfx(name="plain"))                                                 # sans dossier : la racine, comme avant
    assert (store.dir / "plain.sfx").is_file()

    with pytest.raises(ValueError):
        store.save(Sfx(name="intruder"), tmp_path / "elsewhere")
    assert not (tmp_path / "elsewhere").exists()


def test_two_files_with_the_same_name_are_reported_and_the_second_is_never_touched(tmp_path: Path):
    project = Project(tmp_path)
    project.save_settings()
    _sfx(tmp_path / "assets" / "sfx", "coin", volume=100)
    ignored = _sfx(tmp_path / "assets" / "sfx" / "old", "coin", volume=7)
    before = ignored.read_text()

    reopened = Project.open(tmp_path)
    reopened.load_all_resources()

    assert reopened.sfx.get("coin").volume == 100                                 # celui de la racine
    assert [name for name, _ in reopened.ignored_duplicate_files()] == ["sfx/old/coin.sfx"]
    assert any("old/coin.sfx" in w and "ignored" in w for w in reopened.load_warnings)
    from core.validator import validate_project
    warnings, errors = validate_project(reopened)
    assert any("old/coin.sfx" in str(w) and "ignored" in str(w) for w in warnings)
    reopened.sfx.save_all()
    assert ignored.read_text() == before                                          # ni lu, ni réécrit


def test_the_disk_tab_marks_a_nested_sidecar_as_an_asset(tmp_path: Path):
    project = Project(tmp_path)
    project.save_settings()
    folder = tmp_path / "assets" / "sfx" / "platformer" / "wav"
    folder.mkdir(parents=True)
    (folder / "coin.wav").write_bytes(b"")
    _sfx(folder, "coin", asset="assets/sfx/platformer/wav/coin.wav")              # la source est à côté de son sidecar

    reopened = Project.open(tmp_path)
    reopened.load_all_resources()
    nodes = {n.path.relative_to(reopened.assets_dir).as_posix(): n
             for n in disk_tree.build_disk_tree(reopened).walk() if n.path != reopened.assets_dir}

    assert (nodes["sfx/platformer/wav/coin.sfx"].kind, nodes["sfx/platformer/wav/coin.sfx"].family) == (disk_tree.ASSET, "sfx")
    assert (nodes["sfx/platformer/wav/coin.wav"].kind, nodes["sfx/platformer/wav/coin.wav"].owner) == (disk_tree.LINKED_SOURCE, "coin")
