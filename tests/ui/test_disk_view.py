"""DiskView : le contenu d'un dossier à plat, un fil d'ariane pour s'y repérer."""
from pathlib import Path

from PyQt6.QtWidgets import QPushButton

from core import disk_tree
from ui.common.disk_view import DiskView


def _tree() -> disk_tree.DiskNode:
    base = Path("assets")
    deep = disk_tree.DiskNode("platformer", base / "sfx" / "platformer", disk_tree.FOLDER, children=[
        disk_tree.DiskNode("jump.wav", base / "sfx" / "platformer" / "jump.wav", disk_tree.FREE_SOURCE)])
    sfx = disk_tree.DiskNode("sfx", base / "sfx", disk_tree.FOLDER, children=[
        deep,
        disk_tree.DiskNode("GOAL.json", base / "sfx" / "GOAL.json", disk_tree.ASSET, "GOAL"),
        disk_tree.DiskNode("GOAL.wav", base / "sfx" / "GOAL.wav", disk_tree.LINKED_SOURCE, "GOAL")])
    return disk_tree.DiskNode("assets", base, disk_tree.FOLDER, children=[sfx])


def _names(view: DiskView) -> list[str]:
    return [view._list.item(i).text() for i in range(view._list.count())]


def _open(view: DiskView, name: str) -> None:
    """Le double-clic sur l'entrée `name`."""
    item = next(view._list.item(i) for i in range(view._list.count()) if view._list.item(i).text() == name)
    view._enter(item)


def _crumbs(view: DiskView) -> list[str]:
    return [b.text() for b in view.findChildren(QPushButton) if b.isFlat() and not b.isHidden()]


def test_shows_one_folder_flat_with_the_root_in_the_breadcrumb(qapp):
    view = DiskView()
    view.set_tree(_tree())
    assert _names(view) == ["assets", "sfx"]
    assert _crumbs(view) == ["Assets"]


def test_double_click_enters_a_folder_and_the_breadcrumb_goes_back(qapp):
    view = DiskView()
    view.set_tree(_tree())
    _open(view, "sfx")
    assert _names(view) == ["...", "platformer", "GOAL.json", "GOAL.wav"]
    assert _crumbs(view) == ["Assets", "sfx"]

    _open(view, "platformer")
    assert _names(view) == ["...", "jump.wav"] and _crumbs(view) == ["Assets", "sfx", "platformer"]

    _open(view, "jump.wav")                             # un fichier : rien ne se passe
    assert _names(view) == ["...", "jump.wav"]

    view._go_to(1)                                      # clic sur « sfx »
    assert _crumbs(view) == ["Assets", "sfx"] and "GOAL.json" in _names(view)
    view._go_to(0)
    assert _names(view) == ["assets", "sfx"]


def test_refresh_keeps_the_folder_and_falls_back_when_it_is_gone(qapp):
    view = DiskView()
    view.set_tree(_tree())
    _open(view, "sfx")
    view.set_tree(_tree())                              # Refresh : on reste dans sfx
    assert _crumbs(view) == ["Assets", "sfx"]

    view.set_tree(disk_tree.DiskNode("assets", Path("assets"), disk_tree.FOLDER))   # le dossier a disparu
    assert _crumbs(view) == ["Assets"] and _names(view) == ["assets"]

    view.set_tree(None)
    assert _crumbs(view) == [] and _names(view) == []


def test_the_dots_entry_is_first_outside_the_root_and_goes_up(qapp):
    view = DiskView()
    view.set_tree(_tree())
    assert "..." not in _names(view) and _names(view)[0] == "assets"     # à la racine, rien au-dessus

    _open(view, "sfx")
    _open(view, "platformer")
    assert _names(view)[0] == "..."
    _open(view, "...")                                  # remonte d'un seul niveau
    assert _crumbs(view) == ["Assets", "sfx"] and _names(view)[0] == "..."
    _open(view, "...")
    assert _crumbs(view) == ["Assets"] and _names(view)[0] == "assets"


def test_the_root_entry_opens_the_assets_folder_and_the_dots_entry_never_does(qapp, monkeypatch):
    opened: list = []
    monkeypatch.setattr("ui.common.disk_view.reveal_in_file_manager", opened.append)
    view = DiskView()
    view.set_tree(_tree())

    assert _names(view)[0] == "assets"
    _open(view, "assets")                                # à la racine : ouvre le dossier lui-même
    assert opened == [Path("assets")] and _crumbs(view) == ["Assets"]

    _open(view, "sfx")
    assert "assets" not in _names(view)                  # plus bas, « ... » prend sa place
    _open(view, "...")
    assert opened == [Path("assets")]                    # remonter n'ouvre rien


def test_select_file_opens_its_folder_and_selects_the_row(qapp):
    view = DiskView()
    view.set_tree(_tree())
    view.select_file(Path("assets") / "sfx" / "GOAL.json")
    assert _crumbs(view) == ["Assets", "sfx"]
    assert view._list.currentItem().text() == "GOAL.json"


def test_build_start_brings_the_console_tab_forward_not_disk(qapp):
    from ui.common.build_panel import BuildPanel
    panel = BuildPanel()
    panel.show_disk_tab()
    panel.show_console_tab()
    assert panel._tabs.currentWidget() is panel._console_tab and not panel.tab_is_disk()


def test_tab_sets_are_reorderable_and_the_console_stays_found(qapp):
    from ui.common.build_panel import BuildPanel
    panel = BuildPanel()
    assert panel._tabs.isMovable()
    panel._tabs.tabBar().moveTab(panel._tabs.indexOf(panel._console_tab), 0)     # la Console passe devant Disk
    panel.show_disk_tab()
    panel.show_console_tab()
    assert panel._tabs.currentWidget() is panel._console_tab


def test_tab_order_round_trips_and_tolerates_stale_settings(qapp):
    from ui.common.build_panel import BuildPanel
    panel = BuildPanel()
    default = panel.tab_order()
    assert default == ["disk", "console", "diagnostics"]
    panel.restore_tab_order(["diagnostics", "disk", "console"])
    assert panel.tab_order() == ["diagnostics", "disk", "console"]
    panel.restore_tab_order(["console", "ghost"])            # clé inconnue ignorée, les absents suivent dans l'ordre déclaré
    assert panel.tab_order() == ["console", "diagnostics", "disk"]
    panel.restore_tab_order(None)                            # rien d'enregistré : ordre déclaré
    assert panel.tab_order() == ["console", "diagnostics", "disk"]
    panel.restore_tab_order("disk")                          # QSettings : liste d'un élément = chaîne
    assert panel.tab_order()[0] == "disk"


