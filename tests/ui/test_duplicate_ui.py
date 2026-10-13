"""*Duplicate* dans les finders (menu, Ctrl+D, dossier d'auteur conservé) et dans l'onglet Disk (menu, tout ou rien)."""
from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMenu

from asset_fixtures import create
from core import disk_tree
from core.asset_folder_store import AssetFolderStore
from core.history import get_history
from core.project import Project
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import ALL_KINDS, JINGLES, MUSIC, SFX
from ui.common.disk_view import DiskCallbacks, add_asset_actions


def _wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(bytes(800))
    return path


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def finder(qapp, project) -> AssetFinder:
    finder = AssetFinder("Sound finder", [SFX, MUSIC, JINGLES])
    finder.set_folder_store(AssetFolderStore(project.root))
    finder.load_project(project)
    return finder


def test_every_family_a_finder_shows_can_be_duplicated():
    assert [kind.label for kind in ALL_KINDS if kind.duplicate is None] == []


def test_the_single_menu_offers_duplicate_with_the_shortcut_and_the_batch_menu_counts(finder, project, monkeypatch):
    first = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    second = create(project, "sfx", _wav(project.assets_dir / "boom.wav"))
    finder.refresh()
    tree = finder._trees[SFX.label]
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *a, **k: shown.append([a.text() for a in menu.actions() if not a.isSeparator()]))

    tree._single_menu(first, tree.viewport().rect().center())
    tree._multi_menu([first, second], tree.viewport().rect().center())

    assert "Duplicate" in shown[0] and shown[0].index("Rename…") < shown[0].index("Duplicate")
    assert "Duplicate 2 items" in shown[1]


def test_duplicating_in_a_finder_is_one_undoable_entry_and_keeps_the_author_folder(finder, project):
    original = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    finder.refresh()
    scheme = finder.folder_scheme(SFX.label)
    scheme.move(original, scheme.create("Pickups", None).id)
    tree = finder._trees[SFX.label]

    tree._duplicate([original])

    copy = project.sfx.get("coin_2")
    assert copy is not None and copy.asset == original.asset
    assert scheme.folder_of(copy) == scheme.folder_of(original)               # la copie reste dans le dossier de l'original
    get_history().undo()
    assert project.sfx.get("coin_2") is None and project.sfx.get("coin") is original


def test_ctrl_d_duplicates_the_selection(finder, project):
    original = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    finder.refresh()
    tree = finder._trees[SFX.label]
    tree.select_obj(original)

    tree._duplicate_shortcut.activated.emit()

    assert [s.name for s in project.sfx] == ["coin", "coin_2"]


# ── L'onglet Disk ─────────────────────────────────────────────────────

def _disk_nodes():
    base = Path("assets")
    return {n.name: n for n in disk_tree.DiskNode("assets", base, disk_tree.FOLDER, children=[
        disk_tree.DiskNode("hero.sprite", base / "hero.sprite", disk_tree.ASSET, "hero", "sprites"),
        disk_tree.DiskNode("Level.scene", base / "Level.scene", disk_tree.ASSET, "Level", "scenes"),
        disk_tree.DiskNode("texts.json", base / "texts.json", disk_tree.ASSET, "texts", "texts"),
        disk_tree.DiskNode("hero.png", base / "hero.png", disk_tree.LINKED_SOURCE, "hero", "sprites"),
        disk_tree.DiskNode("boom.wav", base / "boom.wav", disk_tree.FREE_SOURCE),
        disk_tree.DiskNode("notes.txt", base / "notes.txt", disk_tree.UNSUPPORTED),
        disk_tree.DiskNode("Art", base / "Art", disk_tree.FOLDER),
    ]).walk()}


def _callbacks(duplicated: list) -> DiskCallbacks:
    return DiskCallbacks(
        create_options=lambda path: [], create_from_sources=lambda paths, family: None,
        delete_items=lambda nodes: None, deletable=lambda node: True,
        import_files=lambda folder: None, import_paths=lambda files, folder: None,
        create_blank=lambda kind, folder: None, new_folder=lambda parent: None,
        duplicate_items=lambda nodes: duplicated.append([n.name for n in nodes]),
        # La règle de la fenêtre (`_disk_duplicable`) : un asset (sauf textes et variables) ou une source.
        duplicable=lambda node: (node.kind in (disk_tree.FREE_SOURCE, disk_tree.LINKED_SOURCE)
                                 or (node.kind == disk_tree.ASSET and node.family not in ("texts", "variables"))))


def _texts(menu: QMenu) -> list[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_the_disk_menu_duplicates_assets_and_sources_all_or_nothing(qapp):
    duplicated, nodes = [], _disk_nodes()
    cb = _callbacks(duplicated)

    one = QMenu()
    add_asset_actions(one, [nodes["hero.sprite"]], cb)
    assert _texts(one)[0] == "Duplicate"
    one.actions()[0].trigger()
    assert duplicated == [["hero.sprite"]]

    many = QMenu()
    add_asset_actions(many, [nodes["hero.sprite"], nodes["Level.scene"]], cb)
    assert _texts(many)[0] == "Duplicate 2 items"

    sources = QMenu()
    add_asset_actions(sources, [nodes["hero.png"], nodes["boom.wav"], nodes["hero.sprite"]], cb)   # sources et assets, ensemble
    assert "Duplicate 3 items" in _texts(sources)

    for refused in ([nodes["texts.json"]],                                      # un fichier pour tout le projet
                    [nodes["notes.txt"]],                                       # un fichier que l'éditeur ne lit pas
                    [nodes["Art"]],                                             # un dossier
                    [nodes["hero.sprite"], nodes["Art"]]):                      # tout ou rien
        menu = QMenu()
        add_asset_actions(menu, refused, cb)
        assert not any(text.startswith("Duplicate") for text in _texts(menu))


def test_a_disk_without_the_duplicate_callbacks_offers_nothing(qapp):
    menu = QMenu()
    callbacks = _callbacks([])
    callbacks.duplicate_items = None
    add_asset_actions(menu, [_disk_nodes()["hero.sprite"]], callbacks)
    assert not any(text.startswith("Duplicate") for text in _texts(menu))
