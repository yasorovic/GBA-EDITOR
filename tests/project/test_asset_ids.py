"""Tous les assets portent un id, écrit et relu par le magasin : jamais renuméroté, nouveau pour une copie."""
import copy
import json
import wave
from pathlib import Path

from core.models.audio import Sfx
from core.models.data_table import DataTable
from core.models.ids import is_id
from core.models.scene import Scene
from core.project import Project
from core import asset_creation
from core.resources.resource_store import ResourceStore


def _project(tmp_path: Path) -> Project:
    project = Project(tmp_path)
    project.save_settings()   # le manifeste : sans lui, le dossier n'est pas un projet
    return project


def _write(folder: Path, name: str, **fields) -> Path:
    """Un sidecar de SFX."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.sfx"
    path.write_text(json.dumps({"name": name, **fields}), encoding="utf-8")
    return path


def _sfx_fields(name: str) -> dict:
    return {"asset": f"assets/sfx/{name}.wav", "volume": 100, "sample_rate": 0}


def test_no_stored_model_has_its_own_top_level_id_field(tmp_path: Path):
    """Le magasin place l'id dans le JSON : un modèle qui aurait un champ `id` le verrait écrasé."""
    from dataclasses import fields
    project = Project(tmp_path)
    for store in project._resource_stores():
        assert "id" not in {f.name for f in fields(store.cls)}, store.cls.__name__


def test_a_saved_sidecar_starts_with_its_name_then_its_id_whatever_the_model(tmp_path: Path):
    for name, item in (("Blip", Sfx(name="Blip")), ("Level", Scene(name="Level")),
                       ("Items", DataTable(name="Items"))):
        store = ResourceStore(tmp_path / name, type(item))
        store.save(item)
        data = json.loads((tmp_path / name / f"{name}{type(item).sidecar_extension}").read_text(encoding="utf-8"))
        assert list(data)[:2] == ["name", "id"] and is_id(data["id"]) and data["id"] == item.id


def test_an_asset_gets_its_id_the_first_time_it_is_saved(tmp_path: Path):
    store = ResourceStore(tmp_path, Sfx)
    sfx = Sfx(name="Zap")
    assert sfx.id == ""
    store.save(sfx)
    assert is_id(sfx.id)
    first = sfx.id
    store.save(sfx)
    assert sfx.id == first                                                      # jamais renuméroté


def test_an_asset_from_before_the_ids_gets_one_at_load_and_keeps_it(tmp_path: Path):
    _write(tmp_path, "Blip", **_sfx_fields("Blip"))
    first = ResourceStore(tmp_path, Sfx)
    first.load()
    given = first.get("Blip").id
    assert is_id(given)
    assert json.loads((tmp_path / "Blip.sfx").read_text())["id"] == given        # écrit sur le disque

    again = ResourceStore(tmp_path, Sfx)
    again.load()
    assert again.get("Blip").id == given


def test_a_copy_of_a_file_gets_a_new_id_and_the_original_keeps_its_own(tmp_path: Path):
    _write(tmp_path, "Blip", id="0123456789ab", **_sfx_fields("Blip"))
    _write(tmp_path / "copy", "Blip_copy", id="0123456789ab", **_sfx_fields("Blip"))   # copié dans l'Explorateur

    store = ResourceStore(tmp_path, Sfx)
    store.load()

    ids = {s.name: s.id for s in store}
    assert ids["Blip"] == "0123456789ab"                                         # le premier dans l'ordre des noms
    assert is_id(ids["Blip_copy"]) and ids["Blip_copy"] != "0123456789ab"
    assert json.loads((tmp_path / "copy" / "Blip_copy.sfx").read_text())["id"] == ids["Blip_copy"]


def test_an_id_of_the_wrong_shape_is_replaced(tmp_path: Path):
    _write(tmp_path, "Blip", id="not-an-id", **_sfx_fields("Blip"))
    store = ResourceStore(tmp_path, Sfx)
    store.load()
    assert is_id(store.get("Blip").id)


def test_an_in_memory_duplicate_that_kept_its_original_id_is_given_a_new_one_when_saved(tmp_path: Path):
    store = ResourceStore(tmp_path, Scene)
    original = Scene(name="Level")
    store.append(original)
    store.save(original)

    duplicate = copy.deepcopy(original)                                          # même id, comme `duplicate_scene`
    duplicate.name = "Level_2"
    store.append(duplicate)
    store.save(duplicate)

    assert duplicate.id != original.id and is_id(duplicate.id)
    assert json.loads((tmp_path / "Level.scene").read_text())["id"] == original.id


def test_a_lazily_read_asset_without_id_gets_one_on_the_spot(tmp_path: Path):
    _write(tmp_path, "Blip", **_sfx_fields("Blip"))
    store = ResourceStore(tmp_path, Sfx)
    store.scan_index()                                                           # rien n'est lu : chargement paresseux
    sfx = store.get("Blip")
    assert is_id(sfx.id) and json.loads((tmp_path / "Blip.sfx").read_text())["id"] == sfx.id


def test_a_new_audio_file_gets_an_id_when_its_sidecar_is_created(tmp_path: Path):
    project = _project(tmp_path)
    folder = tmp_path / "assets" / "sfx"
    folder.mkdir(parents=True)
    path = folder / "Zap.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(b"\x80" * 80)

    sfx = asset_creation.create_from_source(project, "sfx", path).item

    assert is_id(sfx.id) and json.loads((folder / "Zap.sfx").read_text())["id"] == sfx.id
