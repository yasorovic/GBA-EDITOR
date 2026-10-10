"""Créer et renommer un dossier de assets/ : la seule écriture de l'onglet Disk."""
from pathlib import Path

from core import disk_folders


def _assets(tmp_path: Path) -> Path:
    root = tmp_path / "assets"
    (root / "sfx").mkdir(parents=True)
    return root


def test_a_new_folder_takes_the_first_free_name(tmp_path: Path):
    root = _assets(tmp_path)
    names = [disk_folders.create_folder(root / "sfx", "New folder", root).name for _ in range(3)]
    assert names == ["New folder", "New folder_2", "New folder_3"]
    assert all((root / "sfx" / n).is_dir() for n in names)


def test_nothing_is_created_outside_assets(tmp_path: Path):
    root = _assets(tmp_path)
    assert disk_folders.create_folder(tmp_path, "x", root) is None                # le parent n'est pas dans assets/
    assert disk_folders.create_folder(root / "missing", "x", root) is None        # il n'existe pas
    assert disk_folders.create_folder(root / "sfx" / ".." / "..", "x", root) is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["assets"]


def test_rename_a_folder(tmp_path: Path):
    root = _assets(tmp_path)
    renamed = disk_folders.rename_folder(root / "sfx", "sounds", root)
    assert renamed == root / "sounds" and renamed.is_dir() and not (root / "sfx").exists()


def test_a_bad_or_taken_name_is_refused_and_nothing_moves(tmp_path: Path):
    root = _assets(tmp_path)
    (root / "music").mkdir()
    for bad in ("", "  ", ".", "..", "a/b", "a\b", "what?", "dots.", "music"):
        assert disk_folders.rename_folder(root / "sfx", bad, root) is None, bad
    assert (root / "sfx").is_dir() and (root / "music").is_dir()


def test_the_assets_folder_itself_cannot_be_renamed(tmp_path: Path):
    root = _assets(tmp_path)
    assert disk_folders.rename_folder(root, "other", root) is None
    assert root.is_dir()


def test_an_unchanged_name_is_a_no_op_and_a_case_change_is_allowed(tmp_path: Path):
    root = _assets(tmp_path)
    assert disk_folders.rename_folder(root / "sfx", "sfx", root) == root / "sfx"
    assert disk_folders.rename_folder(root / "sfx", "SFX", root) == root / "SFX"
    assert [p.name for p in root.iterdir()] == ["SFX"]
