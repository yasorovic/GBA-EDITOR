"""L'arbre Disk : le disque tel qu'il est, chaque fichier marqué par sa place dans le projet."""
import json
from pathlib import Path

from core import disk_tree
from core.project import Project


def _project(tmp_path: Path) -> Project:
    project = Project(tmp_path)
    project.save_settings()   # le manifeste : sans lui, le dossier n'est pas un projet
    return project


def _by_name(root: disk_tree.DiskNode) -> dict:
    return {node.path.relative_to(root.path).as_posix(): node for node in root.walk() if node is not root}


def test_every_file_gets_one_mark(tmp_path: Path):
    _project(tmp_path)
    sfx = tmp_path / "assets" / "sfx"
    (sfx / "deep" / "er").mkdir(parents=True)
    (sfx / "Blip.wav").write_bytes(b"")
    (sfx / "Blip.sfx").write_text(json.dumps(
        {"name": "Blip", "asset": "assets/sfx/Blip.wav", "volume": 100, "sample_rate": 0}), encoding="utf-8")
    (sfx / "deep" / "Loose.wav").write_bytes(b"")           # une source que rien ne cite (le scan est plat : un sous-dossier ne devient pas asset)
    (sfx / "deep" / "er" / "Echo.wav").write_bytes(b"")     # idem, dans un sous-dossier
    (sfx / "notes.txt").write_text("x", encoding="utf-8")
    (sfx / "song.ogg").write_bytes(b"")                     # format que la chaîne ne sait pas construire
    scripts = tmp_path / "assets" / "scripts"
    scripts.mkdir()
    (scripts / "Ball.lua").write_text("", encoding="utf-8")

    project = Project.open(tmp_path)
    project.load_all_resources()
    nodes = _by_name(disk_tree.build_disk_tree(project))

    assert nodes["sfx"].kind == disk_tree.FOLDER and nodes["sfx/deep/er"].kind == disk_tree.FOLDER
    assert (nodes["sfx/Blip.sfx"].kind, nodes["sfx/Blip.sfx"].owner) == (disk_tree.ASSET, "Blip")
    assert (nodes["sfx/Blip.wav"].kind, nodes["sfx/Blip.wav"].owner) == (disk_tree.LINKED_SOURCE, "Blip")
    assert nodes["sfx/deep/Loose.wav"].kind == disk_tree.FREE_SOURCE
    assert nodes["sfx/deep/er/Echo.wav"].kind == disk_tree.FREE_SOURCE
    assert nodes["sfx/notes.txt"].kind == disk_tree.UNSUPPORTED
    assert nodes["sfx/song.ogg"].kind == disk_tree.UNSUPPORTED
    assert (nodes["scripts/Ball.lua"].kind, nodes["scripts/Ball.lua"].owner) == (disk_tree.ASSET, "Ball")
    # La famille suit l'asset (son sidecar comme sa source) ; une source libre n'en a pas.
    assert nodes["sfx/Blip.sfx"].family == nodes["sfx/Blip.wav"].family == "sfx"
    assert nodes["scripts/Ball.lua"].family == "scripts"
    assert nodes["sfx/deep/Loose.wav"].family == "" and nodes["sfx/notes.txt"].family == ""
    assert nodes["sfx/Blip.sfx"].status == nodes["sfx/Blip.wav"].status == disk_tree.STATUS_OK
    assert nodes["sfx/deep/Loose.wav"].status == disk_tree.STATUS_ORPHAN_SOURCE
    assert nodes["sfx/notes.txt"].status == disk_tree.STATUS_NEUTRAL


def test_an_asset_with_a_missing_source_is_marked_for_repair(tmp_path: Path):
    _project(tmp_path)
    sfx = tmp_path / "assets" / "sfx"
    sfx.mkdir(parents=True)
    (sfx / "Lost.sfx").write_text(json.dumps(
        {"name": "Lost", "asset": "assets/sfx/gone.wav", "volume": 100, "sample_rate": 0}), encoding="utf-8")

    project = Project.open(tmp_path)
    project.load_all_resources()
    node = _by_name(disk_tree.build_disk_tree(project))["sfx/Lost.sfx"]

    assert node.kind == disk_tree.ASSET
    assert node.status == disk_tree.STATUS_MISSING_SOURCE


def test_the_tree_shows_the_disk_and_adds_nothing(tmp_path: Path):
    _project(tmp_path)
    folder = tmp_path / "assets" / "sprites" / "empty"
    folder.mkdir(parents=True)
    (tmp_path / "assets" / "sprites" / "z.txt").write_bytes(b"")
    (tmp_path / "assets" / "sprites" / "A.txt").write_bytes(b"")

    project = Project.open(tmp_path)
    project.load_all_resources()
    root = disk_tree.build_disk_tree(project)

    on_disk = {p.relative_to(root.path).as_posix() for p in root.path.rglob("*")}
    assert set(_by_name(root)) == on_disk
    sprites = _by_name(root)["sprites"]
    # dossiers d'abord, puis les fichiers par ordre alphabétique sans tenir compte de la casse
    assert [child.name for child in sprites.children] == ["empty", "A.txt", "z.txt"]


def test_a_palette_is_matched_with_its_hex_source(tmp_path: Path):
    from core.models.palette import PaletteBank
    project = _project(tmp_path)
    project.palettes.save(PaletteBank(name="Night", colors=[0x0000, 0x7FFF]))

    reopened = Project.open(tmp_path)
    reopened.load_all_resources()
    nodes = _by_name(disk_tree.build_disk_tree(reopened))

    assert (nodes["Night.hex"].kind, nodes["Night.hex"].owner) == (disk_tree.LINKED_SOURCE, "Night")
    assert nodes["Night.palette"].kind == disk_tree.ASSET


def test_a_missing_assets_folder_gives_an_empty_root(tmp_path: Path):
    project = _project(tmp_path)
    root = disk_tree.build_disk_tree(project)
    assert root.kind == disk_tree.FOLDER and root.children == []
