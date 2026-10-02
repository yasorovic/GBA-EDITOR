"""Le .hex est l'asset palette ; le JSON ne doit jamais en devenir la copie."""
from __future__ import annotations

import json

from core.models.gba_color import bgr555_to_hex, rgb888_to_bgr555
from core.models.palette import PaletteBank
from core.resources.palette_store import PaletteStore
from core.project import Project
from core import project_starters


def test_basic_starter_copies_hex_and_creates_metadata_sidecars(tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")
    palette_dir = project.palettes_dir

    sources = sorted(palette_dir.glob("*.hex"))
    sidecars = sorted(palette_dir.glob("*.json"))
    assert len(sources) == 10
    assert {path.stem for path in sources} == {path.stem for path in sidecars}
    assert len(project.palettes) == len(sources)
    for sidecar in sidecars:
        assert "colors" not in json.loads(sidecar.read_text(encoding="utf-8"))


def test_hex_dropped_by_user_creates_sidecar_on_open(tmp_path):
    palette_dir = tmp_path / "assets" / "palettes"
    palette_dir.mkdir(parents=True)
    (palette_dir / "Forest.hex").write_text("#000000\n#4EA832\n", encoding="utf-8")

    store = PaletteStore(palette_dir)
    store.load()

    assert store.get("Forest").colors == [0, rgb888_to_bgr555(0x4E, 0xA8, 0x32)]
    assert json.loads((palette_dir / "Forest.json").read_text(encoding="utf-8")) == {
        "name": "Forest", "size": 16,
    }


def test_palette_bank_owns_the_canonical_hex_format():
    bank = PaletteBank.from_hex("Forest", "#000000\n#4EA832\n", {"size": 16})

    assert bank.to_hex() == "#000000\n#48A830\n"
    assert bank.to_metadata_dict() == {"name": "Forest", "size": 16}


def test_deleted_hex_is_never_recreated_from_its_sidecar(tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")
    source = project.palettes_dir / "_PICO-8.hex"
    source.unlink()

    reopened = Project.open(project.root)

    assert reopened.palettes.get("_PICO-8") is None
    assert not source.exists()


def test_legacy_json_palette_migrates_once_to_hex(tmp_path):
    palette_dir = tmp_path / "assets" / "palettes"
    palette_dir.mkdir(parents=True)
    legacy_colors = [0, rgb888_to_bgr555(0x11, 0x22, 0x33)]
    (palette_dir / "Legacy.json").write_text(
        json.dumps({"name": "Legacy", "size": 16,
                    "colors": [bgr555_to_hex(color) for color in legacy_colors]}),
        encoding="utf-8",
    )

    store = PaletteStore(palette_dir)
    store.load()

    assert (palette_dir / "Legacy.hex").read_text(encoding="utf-8") == "#000000\n#102030\n"
    assert json.loads((palette_dir / "Legacy.json").read_text(encoding="utf-8")) == {
        "name": "Legacy", "size": 16,
    }


def test_saving_palette_writes_hex_before_metadata(tmp_path):
    store = PaletteStore(tmp_path / "palettes")
    bank = PaletteBank(name="Sky", colors=[0, rgb888_to_bgr555(0x4F, 0xA9, 0xFF)])
    store.append(bank)
    store.save(bank)
    store.load()

    assert (tmp_path / "palettes" / "Sky.hex").read_text(encoding="utf-8") == "#000000\n#48A8F8\n"
    assert store.get("Sky").colors == bank.colors


def test_personal_starter_is_discovered_and_copies_only_project_content(tmp_path, monkeypatch):
    personal_root = tmp_path / "starters"
    starter = personal_root / "My setup"
    (starter / "project" / "palettes").mkdir(parents=True)
    (starter / "project" / "palettes" / "Warm.hex").write_text("#000000\n#F8A000\n")
    (starter / "Old.project").write_text("must not be copied")
    monkeypatch.setattr(project_starters, "USER_STARTERS_DIR", personal_root)

    discovered = project_starters.get_starter("user:My setup")
    destination = tmp_path / "new-game"
    project_starters.copy_starter(discovered, destination)

    assert (destination / "project" / "palettes" / "Warm.hex").exists()
    assert not (destination / "Old.project").exists()
