"""Les gestes de l'onglet Disk sont annulables et refaisables : importer, déplacer, créer un dossier, créer un asset vierge."""
import wave
from pathlib import Path

from asset_fixtures import create
from core import blank_assets
from core.disk_commands import CreateFileCmd, CreateFolderCmd, ImportFilesCmd, MoveFilesCmd, RenameFolderCmd
from core.history import CommandHistory, CreateAssetCmd
from core.project import Project


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


def test_a_move_is_undone_and_redone_and_the_asset_keeps_pointing_at_its_source(tmp_path: Path):
    p = _project(tmp_path)
    source = _wav(p.sfx_dir / "boom.wav")
    boom = create(p, "sfx", source)
    target = p.assets_dir / "Audio"
    target.mkdir()
    history = CommandHistory()

    history.push(MoveFilesCmd(p, [source], target))
    assert (target / "boom.wav").is_file() and boom.asset == "assets/Audio/boom.wav"

    history.undo()
    assert source.is_file() and not (target / "boom.wav").exists()
    assert boom.asset == "assets/sfx/boom.wav"                                    # la référence est revenue avec le fichier

    history.redo()
    assert (target / "boom.wav").is_file() and boom.asset == "assets/Audio/boom.wav"


def test_moving_a_folder_and_undoing_puts_everything_back(tmp_path: Path):
    p = _project(tmp_path)
    pack = p.assets_dir / "Pack"
    source = _wav(pack / "boom.wav")
    create(p, "sfx", source)
    target = p.assets_dir / "Archive"
    target.mkdir()
    history = CommandHistory()

    history.push(MoveFilesCmd(p, [pack], target))
    assert (target / "Pack" / "boom.sfx").is_file() and not pack.exists()

    history.undo()
    assert (pack / "boom.sfx").is_file() and (pack / "boom.wav").is_file() and not (target / "Pack").exists()


def test_an_import_copies_files_in_and_undoing_removes_only_the_copies(tmp_path: Path):
    p = _project(tmp_path)
    outside = _wav(tmp_path / "Downloads" / "coin.wav")
    copy = p.assets_dir / "Audio" / "coin.wav"
    history = CommandHistory()

    history.push(ImportFilesCmd([(outside, copy)]))
    assert copy.is_file()

    history.undo()
    assert not copy.exists() and outside.is_file()                                # l'original n'est jamais touché

    history.redo()
    assert copy.is_file()


def test_a_new_folder_is_undone_if_still_empty_and_kept_if_something_was_put_in_it(tmp_path: Path):
    p = _project(tmp_path)
    history = CommandHistory()
    first = CreateFolderCmd(p.assets_dir, "New folder", p.assets_dir)

    history.push(first)
    assert first.created is not None and first.created.is_dir()
    history.undo()
    assert not first.created.exists()

    second = CreateFolderCmd(p.assets_dir, "Keep", p.assets_dir)
    history.push(second)
    (second.created / "note.txt").write_text("x", encoding="utf-8")
    history.undo()
    assert second.created.is_dir()                                                # on ne détruit pas ce qu'on y a rangé


def test_renaming_a_folder_is_undoable(tmp_path: Path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Old"
    folder.mkdir()
    history = CommandHistory()

    history.push(RenameFolderCmd(folder, "New", p.assets_dir))
    assert (p.assets_dir / "New").is_dir() and not folder.exists()
    history.undo()
    assert folder.is_dir() and not (p.assets_dir / "New").exists()


def test_every_blank_kind_builds_a_named_asset_that_is_created_in_the_folder_and_undone(tmp_path: Path):
    p = _project(tmp_path)
    folder = p.assets_dir / "Anywhere"
    folder.mkdir()
    history = CommandHistory()

    for kind, family, _base in blank_assets.BLANK_KINDS:
        store, item = blank_assets.build_blank(p, kind)
        assert item not in store.items                                            # construit, pas rangé
        history.push(CreateAssetCmd(store, item, folder))
        assert store.get(item.name) is item and store.path_of(item).parent == folder, kind
        history.undo()
        assert store.get(item.name) is None, kind


def test_a_second_blank_asset_gets_a_unique_name(tmp_path: Path):
    p = _project(tmp_path)
    store, first = blank_assets.build_blank(p, "prefab")
    store.append(first)
    _, second = blank_assets.build_blank(p, "prefab")
    assert (first.name, second.name) == ("Prefab", "Prefab_2")


def test_a_new_script_and_a_new_behavior_are_files_that_come_and_go_with_undo(tmp_path: Path):
    from core import lua_scripts
    p = _project(tmp_path)
    history = CommandHistory()
    script = p.assets_dir / "Levels" / "Hero.lua"
    behavior = p.assets_dir / "Levels" / "ai.lua"

    history.push(CreateFileCmd(script, blank_assets.script_source("script", "Hero").encode()))
    history.push(CreateFileCmd(behavior, blank_assets.script_source("behavior", "ai").encode()))
    assert script.is_file() and lua_scripts.is_behavior(behavior) and not lua_scripts.is_behavior(script)

    history.undo()
    history.undo()
    assert not script.exists() and not behavior.exists()
    history.redo()
    assert script.is_file()
