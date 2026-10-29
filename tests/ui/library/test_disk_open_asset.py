"""Double-clic dans l'onglet Disk : ce qui s'ouvre dans son écran, et ce qui reste fermé."""
from pathlib import Path

from core import disk_tree
from ui.common.disk_view import openable


def _node(kind, owner="", family=""):
    return disk_tree.DiskNode("x", Path("x"), kind, owner, family)


def test_an_asset_file_opens_with_its_family_and_name():
    assert openable(_node(disk_tree.ASSET, "Hero", "sprites")) == ("sprites", "Hero", str(Path("x")))


def test_a_source_opens_only_when_one_asset_cites_it():
    assert openable(_node(disk_tree.LINKED_SOURCE, "Hero", "sprites")) is not None
    assert openable(_node(disk_tree.LINKED_SOURCE, "Hero, Tree", "sprites")) is None     # lequel ouvrir ?


def test_folders_and_free_files_do_not_open():
    assert openable(_node(disk_tree.FOLDER)) is None
    assert openable(_node(disk_tree.FREE_SOURCE)) is None
    assert openable(_node(disk_tree.UNSUPPORTED)) is None
