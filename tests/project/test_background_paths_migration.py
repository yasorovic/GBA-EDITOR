"""Un fond cite son image par un chemin relatif au projet ; l'outil migre un projet d'avant."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_background_paths", ROOT / "tools" / "migrate_background_paths.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _background(root: Path, folder: str, name: str, asset: str) -> Path:
    path = root / "assets" / folder / f"{name}.background"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, "id": "0123456789ab", "asset": asset, "mode": "tiled"}, indent=2),
                    encoding="utf-8")
    return path


def test_a_bare_file_name_becomes_a_project_relative_path_and_nothing_else_changes(tmp_path: Path):
    sky = _background(tmp_path, "backgrounds", "sky", "sky.png")
    moved = _background(tmp_path, "Levels", "cave", "cave.png")                  # le sidecar peut déjà être ailleurs
    before = json.loads(sky.read_text())

    assert _migration().migrate(tmp_path, dry_run=False) == 2

    after = json.loads(sky.read_text())
    assert after["asset"] == "assets/backgrounds/sky.png"
    assert {k: v for k, v in after.items() if k != "asset"} == {k: v for k, v in before.items() if k != "asset"}
    assert json.loads(moved.read_text())["asset"] == "assets/backgrounds/cave.png"


def test_it_is_idempotent_and_leaves_a_path_alone(tmp_path: Path):
    _background(tmp_path, "backgrounds", "sky", "assets/Art/sky.png")
    assert _migration().migrate(tmp_path, dry_run=False) == 0
    assert json.loads((tmp_path / "assets" / "backgrounds" / "sky.background").read_text())["asset"] == "assets/Art/sky.png"


def test_dry_run_writes_nothing(tmp_path: Path):
    sky = _background(tmp_path, "backgrounds", "sky", "sky.png")
    assert _migration().migrate(tmp_path, dry_run=True) == 1
    assert json.loads(sky.read_text())["asset"] == "sky.png"


def test_a_folder_without_assets_is_refused(tmp_path: Path):
    with pytest.raises(SystemExit, match="no assets/ folder"):
        _migration().migrate(tmp_path, dry_run=False)
