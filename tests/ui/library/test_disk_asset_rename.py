"""Renommer un asset depuis l'onglet Disk : le fichier de l'asset change de nom avec lui, annulable, refusé si pris."""
import wave
from pathlib import Path

from asset_fixtures import create
from core import disk_tree
from core.history import CommandHistory
from core.project import Project
from ui.common.asset_kinds import RenameAssetCmd


def _wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    return path


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p = Project.open(p.root)
    p.load_all_resources()
    return p


def test_an_asset_file_is_renamed_as_its_asset_and_undone(tmp_path: Path):
    p = _project(tmp_path)
    boom = create(p, "sfx", _wav(p.user_library_dir / "sfx" / "boom.wav"))
    before = p.sfx.path_of(boom)
    assert disk_tree.asset_at(p, before) == ("sfx", "boom")
    history = CommandHistory()

    command = RenameAssetCmd(p, "sfx", "boom", f"bang{p.sfx.suffix}")      # le nom du fichier, extension comprise
    history.push(command)
    assert command.applied == "bang" and boom.name == "bang"
    assert p.sfx.path_of(boom).is_file() and not before.exists()
    assert (p.user_library_dir / "sfx" / "boom.wav").is_file()               # la source ne bouge pas

    history.undo()
    assert boom.name == "boom" and before.is_file()


def test_a_taken_or_empty_name_is_refused(tmp_path: Path):
    p = _project(tmp_path)
    boom = create(p, "sfx", _wav(p.user_library_dir / "sfx" / "boom.wav"))
    create(p, "sfx", _wav(p.user_library_dir / "sfx" / "bang.wav"))

    for typed in ("bang", "  ", p.sfx.suffix):
        command = RenameAssetCmd(p, "sfx", "boom", typed)
        command.execute()
        assert command.applied is None and boom.name == "boom", typed


def test_a_source_or_a_project_table_is_not_an_asset_file(tmp_path: Path):
    p = _project(tmp_path)
    source = _wav(p.user_library_dir / "sfx" / "boom.wav")
    create(p, "sfx", source)
    assert disk_tree.asset_at(p, source) is None
    assert disk_tree.asset_at(p, p.texts_file) is None
