"""DiskTreeView : l'arbre vertical de assets/, et le dossier choisi qui pilote la vue du bas."""
from pathlib import Path

from PyQt6.QtCore import Qt

from PyQt6.QtWidgets import QPushButton

from core import disk_tree
from ui.common.disk_tree_view import DiskTreeView
from ui.common.disk_view import DiskView, renamable


def _tree() -> disk_tree.DiskNode:
    base = Path("assets")
    deep = disk_tree.DiskNode("platformer", base / "sfx" / "platformer", disk_tree.FOLDER, children=[
        disk_tree.DiskNode("jump.wav", base / "sfx" / "platformer" / "jump.wav", disk_tree.FREE_SOURCE)])
    sfx = disk_tree.DiskNode("sfx", base / "sfx", disk_tree.FOLDER, children=[
        deep, disk_tree.DiskNode("GOAL.json", base / "sfx" / "GOAL.json", disk_tree.ASSET, "GOAL")])
    return disk_tree.DiskNode("assets", base, disk_tree.FOLDER, children=[sfx])


def _find(view: DiskTreeView, path: Path):
    stack = [view._tree.topLevelItem(0)]
    while stack:
        item = stack.pop()
        if item.data(0, 256) == str(path):
            return item
        stack.extend(item.child(i) for i in range(item.childCount()))
    return None


def test_root_is_called_assets_and_opens_once(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())
    top = view._tree.topLevelItem(0)
    assert top.text(0) == "Assets" and top.isExpanded()
    assert not _find(view, Path("assets") / "sfx").isExpanded()


def test_choosing_a_folder_emits_it_but_a_file_does_not(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())
    got: list[str] = []
    view.folder_selected.connect(got.append)

    view._on_clicked(_find(view, Path("assets") / "sfx"))
    view._on_clicked(_find(view, Path("assets") / "sfx" / "GOAL.json"))
    assert got == [str(Path("assets") / "sfx")]


def test_refresh_keeps_opened_folders_and_the_chosen_one_without_emitting(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())
    sfx = _find(view, Path("assets") / "sfx")
    sfx.setExpanded(True)
    view._tree.setCurrentItem(sfx)
    got: list[str] = []
    view.folder_selected.connect(got.append)

    view.set_tree(_tree())
    assert _find(view, Path("assets") / "sfx").isExpanded()
    assert view._chosen_path() == str(Path("assets") / "sfx")
    assert got == []                                   # reconstruire n'est pas un choix

    view.set_tree(None)
    assert view._tree.topLevelItemCount() == 0


def test_the_flat_view_shows_the_folder_chosen_in_the_tree(qapp):
    flat = DiskView()
    flat.set_tree(_tree())
    flat.show_folder(Path("assets") / "sfx" / "platformer")
    names = [flat._list.item(i).text() for i in range(flat._list.count())]
    crumbs = [b.text() for b in flat.findChildren(QPushButton) if b.isFlat() and not b.isHidden()]
    assert names == ["...", "jump.wav"] and crumbs == ["Assets", "sfx", "platformer"]

    flat.show_folder(Path("elsewhere") / "x")           # hors de la racine : ignoré
    assert crumbs == [b.text() for b in flat.findChildren(QPushButton) if b.isFlat() and not b.isHidden()]
    flat.show_folder(Path("assets") / "gone")           # dossier disparu : on reste à la racine
    assert [b.text() for b in flat.findChildren(QPushButton) if b.isFlat() and not b.isHidden()] == ["Assets"]


def _emitted(signal) -> list:
    got: list = []
    signal.connect(lambda *args: got.append(args))
    return got


def test_the_plus_targets_the_chosen_folder_or_beside_a_chosen_file_or_the_root(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())

    view._tree.setCurrentItem(_find(view, Path("assets") / "sfx"))
    assert view._target_folder() == str(Path("assets") / "sfx")
    view._tree.setCurrentItem(_find(view, Path("assets") / "sfx" / "GOAL.json"))
    assert view._target_folder() == str(Path("assets") / "sfx")        # un fichier : son dossier
    view._tree.setCurrentItem(None)
    assert view._target_folder() == str(Path("assets"))                # rien : la racine


def test_a_folder_or_a_file_is_renamed_in_place_and_only_a_real_change_is_reported(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())
    asked = _emitted(view.rename_requested)
    folder = Path("assets") / "sfx" / "platformer"
    jump = folder / "jump.wav"

    view.begin_rename(str(folder))
    item = _find(view, folder)
    assert item.parent().isExpanded()                   # le dossier neuf se voit
    assert item.flags() & Qt.ItemFlag.ItemIsEditable

    item.setText(0, "platformer")                       # l'éditeur se ferme sans changement (ou Échap)
    assert asked == []
    item.setText(0, "jumps")
    assert asked == [(str(folder), "jumps")]
    _find(view, jump).setText(0, "hop.wav")             # un fichier source aussi
    assert asked[-1] == (str(jump), "hop.wav")


def test_the_root_and_an_asset_are_not_editable_and_never_ask_for_a_rename(qapp):
    view = DiskTreeView()
    view.set_tree(_tree())
    asked = _emitted(view.rename_requested)
    root = view._tree.topLevelItem(0)
    goal = _find(view, Path("assets") / "sfx" / "GOAL.json")

    assert not root.flags() & Qt.ItemFlag.ItemIsEditable and not goal.flags() & Qt.ItemFlag.ItemIsEditable
    root.setExpanded(False)                             # le changement d'icône émet `itemChanged` : pas une demande
    root.setText(0, "x")
    assert asked == []
    view.begin_rename(str(Path("assets") / "sfx" / "GOAL.json"))      # sans effet sur un asset
    assert view._tree.state() != view._tree.State.EditingState


def test_only_folders_sources_and_scripts_are_renamable():
    folder = disk_tree.DiskNode("a", Path("a"), disk_tree.FOLDER)
    source = disk_tree.DiskNode("a.wav", Path("a.wav"), disk_tree.FREE_SOURCE)
    script = disk_tree.DiskNode("a.lua", Path("a.lua"), disk_tree.ASSET, "a", "scripts")
    asset = disk_tree.DiskNode("a.sfx", Path("a.sfx"), disk_tree.ASSET, "a", "sfx")
    assert [renamable(n) for n in (folder, source, script, asset)] == [True, True, True, False]


