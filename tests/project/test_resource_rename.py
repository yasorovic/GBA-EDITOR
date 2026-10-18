import json
from pathlib import Path

import pytest

from core.models.palette import PaletteBank
from core.models.scene import Scene
from core.resources.palette_store import PaletteStore
from core.resources.resource_store import ResourceStore


@pytest.fixture(params=["scene", "palette"])
def asset(tmp_path, request):
    if request.param == "palette":
        store = PaletteStore(tmp_path)
        item = PaletteBank(name="Original", colors=[0x001F] * 16)
    else:
        store = ResourceStore(tmp_path, Scene)
        item = Scene(name="Original")
    store.append(item)
    store.save(item)
    return store, item


@pytest.mark.parametrize("failure", ["write", "replace", "delete"])
def test_failed_rename_preserves_original_and_can_be_retried(asset, monkeypatch, failure):
    store, item = asset
    old_path = store.path_of(item)
    original = old_path.read_bytes()
    new_path = old_path.with_name("Renamed" + store.suffix)
    method = {"write": "write_text", "replace": "replace", "delete": "unlink"}[failure]
    real = getattr(Path, method)
    failure_path = old_path if failure == "delete" else new_path.with_suffix(new_path.suffix + ".tmp")

    def fail(self, *args, **kwargs):
        if self == failure_path:
            raise OSError("simulated disk failure")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, fail)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.rename(item, "Renamed")

    assert old_path.read_bytes() == original
    assert item.name == "Original"
    assert store.index.path_for("Original") == old_path
    assert store.index.path_for("Renamed") is None
    assert not new_path.exists()
    monkeypatch.undo()

    store.rename(item, "Renamed")
    assert not old_path.exists()
    assert store.index.path_for("Original") is None
    assert store.path_of(item) == new_path
    assert json.loads(new_path.read_text(encoding="utf-8"))["name"] == "Renamed"


def test_rename_to_same_filename_keeps_the_asset(asset):
    store, item = asset
    store.rename(item, "Original ")

    assert store.path_of(item).is_file()
    assert store.index.path_for(item.name) == store.path_of(item)
    assert json.loads(store.path_of(item).read_text(encoding="utf-8"))["name"] == "Original "


def test_rename_refuses_to_overwrite_another_file(asset):
    store, item = asset
    old_path = store.path_of(item)
    original = old_path.read_bytes()
    target = old_path.with_name("Renamed" + store.suffix)
    target.write_text("another asset", encoding="utf-8")

    with pytest.raises(FileExistsError):
        store.rename(item, "Renamed")

    assert item.name == "Original"
    assert old_path.read_bytes() == original
    assert target.read_text(encoding="utf-8") == "another asset"


def test_case_only_rename_keeps_the_new_name_on_disk(asset):
    store, item = asset
    store.rename(item, "original")

    assert store.index.names() == ("original",)
    assert [path.name for path in store.root.glob("*" + store.suffix)] == ["original" + store.suffix]
    store.load()
    assert [item.name for item in store] == ["original"]
