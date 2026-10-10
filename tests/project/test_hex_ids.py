"""Les ids opaques : 12 chiffres hexadécimaux, partout, et la migration qui y mène."""
import importlib.util
import json
from pathlib import Path

from codegen.runtime_codegen.gen_save import save_id32
from core.asset_folder_store import AssetFolderStore
from core.models.field_value import FieldValue
from core.models.ids import ID_HEX_LENGTH, is_id, new_id
from core.scene_tree_state import SceneTreeState

ROOT = Path(__file__).resolve().parents[2]


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_ids_to_hex", ROOT / "tools" / "migrate_ids_to_hex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_id_has_the_hex_shape_and_avoids_taken():
    taken: set[str] = set()
    for _ in range(200):
        value = new_id(taken)
        assert is_id(value) and len(value) == ID_HEX_LENGTH
        assert value not in taken
        taken.add(value)


def test_is_id_separates_ids_from_names():
    assert is_id("0123456789ab")
    assert not is_id("score_player")
    assert not is_id("0123456789AB")         # majuscules : c'est un nom
    assert not is_id("0123456789a")          # 11 chiffres
    assert not is_id(123456789012)           # un entier n'est pas un id


def test_field_value_reads_both_id_and_name_references():
    vid = "0123456789ab"
    by_id = FieldValue.parse({"var": vid, "src": "global"}, {("global", vid): "score"})
    assert by_id.var_id == vid and by_id.var_name == "score"
    assert by_id.to_raw() == {"var": vid, "src": "global"}

    by_name = FieldValue.parse({"var": "score", "src": "global"})
    assert by_name.var_id == "" and by_name.var_name == "score"


def test_save_id_keeps_the_last_eight_digits():
    assert save_id32("0123456789ab") == 0x456789AB


def test_folder_stores_draw_hex_ids(tmp_path):
    folder = AssetFolderStore(tmp_path).create_folder("scenes", "Village")
    assert is_id(folder.id)
    assert is_id(SceneTreeState(tmp_path).create_folder("Scene_01", "Group").id)


def test_migration_rewrites_ids_once_and_keeps_layout(tmp_path):
    migrate = _load_migration()
    project = tmp_path / "project"
    (project / "editor").mkdir(parents=True)
    old_uuid = "64a0d785468c46f78434885dcb2b5283"
    files = {
        "variables.json": '{\r\n  "globals": [\r\n    {"id": 176276980874, "name": "score"}\r\n  ],\r\n  "constants": []\r\n}',
        "texts.json": '{\r\n  "texts": [\r\n    {"id": 999615648992, "key": "a"}\r\n  ]\r\n}',
        "texts_de.json": '{\r\n  "lang": "de",\r\n  "texts": [\r\n    {"id": 999615648992, "content": "x"}\r\n  ]\r\n}',
        "scene.json": '{\r\n  "x": {"var": 176276980874, "src": "global"}\r\n}',
        "editor/scene-tree.json": f'{{\r\n  "scenes": {{"S": {{"folders": [{{"id": "{old_uuid}"}}], "hidden_folders": ["{old_uuid}"]}}}}\r\n}}',
    }
    for name, text in files.items():
        (project / name).write_bytes(text.encode("utf-8"))

    assert migrate.migrate(tmp_path, dry_run=True) == 5
    assert (project / "variables.json").read_bytes().decode().count("176276980874") == 1

    assert migrate.migrate(tmp_path, dry_run=False) == 5
    assert migrate.migrate(tmp_path, dry_run=False) == 0        # idempotent

    variable_id = migrate.derived_id("176276980874")
    text_id = migrate.derived_id("999615648992")
    folder_id = migrate.derived_id(old_uuid)
    assert json.loads((project / "variables.json").read_text())["globals"][0]["id"] == variable_id
    assert json.loads((project / "texts.json").read_text())["texts"][0]["id"] == text_id
    assert json.loads((project / "texts_de.json").read_text())["texts"][0]["id"] == text_id
    assert json.loads((project / "scene.json").read_text())["x"]["var"] == variable_id
    tree = json.loads((project / "editor" / "scene-tree.json").read_text())["scenes"]["S"]
    assert tree["folders"][0]["id"] == folder_id and tree["hidden_folders"] == [folder_id]
    assert all(is_id(value) for value in (variable_id, text_id, folder_id))
    assert b"\r\n" in (project / "variables.json").read_bytes()
    assert b"\n" not in (project / "variables.json").read_bytes().replace(b"\r\n", b"")
