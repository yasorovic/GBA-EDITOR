"""Les « + » de l'asset library sont les deux gestes : *Create from source* (sons) et *Create blank* (le reste), dans le dossier affiché."""
import wave

from PyQt6.QtWidgets import QFileDialog

from core.history import CommandHistory
from core.project import Project
from ui.common import asset_kinds, import_folder


def _wav(path):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    return path


def _project(tmp_path, monkeypatch, history):
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p.load_all_resources()
    folder = p.user_library_dir / "Audio"
    folder.mkdir()
    monkeypatch.setattr(import_folder, "_shown_folder", lambda: str(folder))
    monkeypatch.setattr(asset_kinds, "get_history", lambda: history)
    monkeypatch.setattr("core.history.get_history", lambda: history)
    return p, folder


def test_the_plus_of_a_sound_family_imports_a_file_as_one_undoable_gesture(tmp_path, monkeypatch):
    history = CommandHistory()
    p, folder = _project(tmp_path, monkeypatch, history)
    outside = _wav(tmp_path / "coin.wav")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(outside)], ""))

    sfx = asset_kinds.SFX.add(p)

    assert sfx.name == "coin" and (folder / "coin.wav").is_file() and p.sfx.path_of(sfx).parent == folder
    history.undo()
    assert p.sfx.get("coin") is None and not (folder / "coin.wav").exists()
    history.redo()
    assert p.sfx.get("coin") is not None and (folder / "coin.wav").is_file()


def test_the_plus_of_the_blank_families_creates_in_the_shown_folder(tmp_path, monkeypatch):
    history = CommandHistory()
    p, folder = _project(tmp_path, monkeypatch, history)

    table = asset_kinds.DATA_TABLES.add(p)
    big = asset_kinds._create_blank(p, "palette", size=256)
    font_asset = asset_kinds.FONT_ASSETS.add(p)

    assert p.data_tables.path_of(table).parent == folder
    assert big.size == 256 and p.palettes.hex_path(big).parent == folder
    assert p.font_assets.path_of(font_asset).parent == folder
