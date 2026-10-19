"""Un sidecar peut vivre dans un sous-dossier du dossier de sa famille : l'inventaire le trouve et
chaque opération le traite là où il est."""
import json
from pathlib import Path

import pytest

from core.models.audio import Sfx
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
    store.root.mkdir(parents=True, exist_ok=True)
    folder = store.root / "platformer" / "wav"

    store.save(Sfx(name="jump"), folder)
    assert (folder / "jump.sfx").is_file() and not (store.root / "jump.sfx").exists()
    placed = store.get("jump")
    assert placed is not None and store.path_of(placed) == folder / "jump.sfx"

    store.save(Sfx(name="plain"))                                                 # sans dossier : la racine, comme avant
    assert (store.root / "plain.sfx").is_file()

    with pytest.raises(ValueError):
        store.save(Sfx(name="intruder"), tmp_path / "elsewhere")
    assert not (tmp_path / "elsewhere").exists()


