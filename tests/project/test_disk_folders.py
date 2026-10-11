"""Créer un dossier de assets/."""
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
