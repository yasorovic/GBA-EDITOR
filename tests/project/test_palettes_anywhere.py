"""Une palette est un asset `.palette` qui POINTE son `.hex` : l'un comme l'autre se rangent où l'on veut sous `assets/`."""
import json
from pathlib import Path

from asset_fixtures import create_now
from core import asset_creation, asset_relink, disk_move
from core.models.palette import PaletteBank
from core.project import Project
from core.validator import validate_project

NIGHT = "#000000\n#102030\n#405060\n"
DAWN = "#000000\n#ff8800\n"


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    hex_file = (p.assets_dir / "palettes") / "Night.hex"
    hex_file.write_text(NIGHT, encoding="utf-8")
    assert create_now(p, "palettes", hex_file).error is None     # le geste de l'auteur
    return Project.open(p.root)


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _errors(root: Path) -> list[str]:
    project = Project.open(root)
    project.load_all_resources()
    return [str(m) for m in validate_project(project)[1]]


def test_a_hex_dropped_by_hand_is_a_free_source_until_the_author_creates_the_palette(tmp_path: Path):
    p = _project(tmp_path)
    ((p.assets_dir / "palettes") / "Loose.hex").write_text(DAWN, encoding="utf-8")

    reopened = Project.open(p.root)

    assert reopened.palettes.get("Loose") is None and not ((p.assets_dir / "palettes") / "Loose.palette").exists()


def test_a_palette_created_from_a_hex_cites_it(tmp_path: Path):
    p = _project(tmp_path)
    night = p.palettes.get("Night")
    assert night is not None and night.asset == "assets/palettes/Night.hex"
    sidecar = json.loads(((p.assets_dir / "palettes") / "Night.palette").read_text())
    assert sidecar == {"name": "Night", "size": 16, "asset": "assets/palettes/Night.hex"}   # les couleurs restent dans le .hex


def test_a_palette_and_its_hex_can_live_in_different_folders(tmp_path: Path):
    p = _project(tmp_path)
    colours = _mkdir(p.assets_dir / "Colours")
    art = _mkdir(p.assets_dir / "Art" / "Raw")
    (art / "dusk.hex").write_text(DAWN, encoding="utf-8")
    (colours / "Dusk.palette").write_text(
        json.dumps({"name": "Dusk", "size": 16, "asset": "assets/Art/Raw/dusk.hex"}), encoding="utf-8")

    reopened = Project.open(p.root)

    dusk = reopened.palettes.get("Dusk")
    assert dusk is not None and len(dusk.colors) == 2
    assert reopened.palettes.hex_path(dusk) == (art / "dusk.hex").resolve()
    assert reopened.palettes.path_of(dusk) == colours / "Dusk.palette"
    assert not any("source file not found" in e for e in _errors(p.root))


def test_saving_writes_the_colours_to_the_cited_hex_and_the_metadata_where_the_palette_is(tmp_path: Path):
    p = _project(tmp_path)
    colours = _mkdir(p.assets_dir / "Colours")
    disk_move.move_to_folder(p, [p.palettes.path_of(p.palettes.get("Night"))], colours)
    night = p.palettes.get("Night")
    night.colors[1] = 0x7FFF

    p.palettes.save(night)

    assert (colours / "Night.palette").is_file() and not ((p.assets_dir / "palettes") / "Night.palette").exists()
    assert "#F8F8F8" in ((p.assets_dir / "palettes") / "Night.hex").read_text().upper()          # le .hex n'a pas bougé, il est réécrit sur place


def test_moving_the_hex_rewrites_the_path_the_palette_cites(tmp_path: Path):
    p = _project(tmp_path)
    night = p.palettes.get("Night")
    target = _mkdir(p.assets_dir / "Colours")

    result = disk_move.move_to_folder(p, [(p.assets_dir / "palettes") / "Night.hex"], target)

    assert result.refused == [] and night.asset == "assets/Colours/Night.hex"
    reopened = Project.open(p.root)
    assert reopened.palettes.get("Night").asset == "assets/Colours/Night.hex"
    assert len(reopened.palettes.get("Night").colors) == 3
    assert not any("source file not found" in e for e in _errors(p.root))


def test_moving_the_whole_palettes_folder_takes_everything_with_it(tmp_path: Path):
    p = _project(tmp_path)
    target = _mkdir(p.assets_dir / "Archive")

    result = disk_move.move_to_folder(p, [(p.assets_dir / "palettes")], target)

    assert result.refused == []
    assert p.palettes.get("Night").asset == "assets/Archive/palettes/Night.hex"
    reopened = Project.open(p.root)
    assert reopened.palettes.get("Night") is not None
    assert not any("source file not found" in e for e in _errors(p.root))


def test_renaming_a_palette_does_not_rename_its_hex(tmp_path: Path):
    p = _project(tmp_path)
    night = p.palettes.get("Night")

    p.rename_palette(night, "Midnight")

    assert ((p.assets_dir / "palettes") / "Night.hex").is_file() and night.asset == "assets/palettes/Night.hex"
    assert ((p.assets_dir / "palettes") / "Midnight.palette").is_file() and not ((p.assets_dir / "palettes") / "Night.palette").exists()
    reopened = Project.open(p.root)
    assert reopened.palettes.get("Midnight") is not None and reopened.palettes.get("Night") is None


def test_a_palette_whose_hex_is_missing_is_not_loaded_and_its_sidecar_is_kept(tmp_path: Path):
    p = _project(tmp_path)
    ((p.assets_dir / "palettes") / "Night.hex").unlink()
    sidecar = (p.assets_dir / "palettes") / "Night.palette"
    before = sidecar.read_text()

    reopened = Project.open(p.root)

    assert reopened.palettes.get("Night") is None
    assert sidecar.read_text() == before                                          # supprimer le .hex est une intention


def test_relinking_a_palette_to_another_hex_takes_its_colours(tmp_path: Path):
    p = _project(tmp_path)
    night = p.palettes.get("Night")
    other = _mkdir(p.assets_dir / "Elsewhere") / "dawn.hex"
    other.write_text(DAWN, encoding="utf-8")

    slot = asset_relink.relink_source(p, "palettes", night, other)

    assert slot == "asset" and night.asset == "assets/Elsewhere/dawn.hex"
    assert len(night.colors) == 2                                                 # les couleurs viennent du NOUVEAU fichier
    reopened = Project.open(p.root)
    assert reopened.palettes.get("Night").asset == "assets/Elsewhere/dawn.hex"


def test_a_new_palette_gets_its_hex_next_to_its_sidecar_wherever_it_is_born(tmp_path: Path):
    p = _project(tmp_path)
    folder = _mkdir(p.assets_dir / "Colours")
    bank = PaletteBank(name="Fresh", colors=[0, 0x1234])

    p.palettes.append(bank)
    p.palettes.save(bank, folder)

    assert bank.asset == "assets/Colours/Fresh.hex"
    assert (folder / "Fresh.hex").is_file() and (folder / "Fresh.palette").is_file()
    assert not ((p.assets_dir / "palettes") / "Fresh.hex").exists()


def test_a_new_palette_without_a_folder_is_born_at_the_root_of_assets(tmp_path: Path):
    p = _project(tmp_path)
    bank = PaletteBank(name="Fresh", colors=[0, 0x1234])

    p.palettes.append(bank)
    p.palettes.save(bank)

    assert bank.asset == "assets/Fresh.hex"
    assert (p.assets_dir / "Fresh.hex").is_file() and (p.assets_dir / "Fresh.palette").is_file()
