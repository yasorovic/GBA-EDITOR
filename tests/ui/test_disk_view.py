"""DiskView : le contenu d'un dossier à plat, un fil d'ariane pour s'y repérer."""
from pathlib import Path

from PyQt6.QtWidgets import QPushButton, QWidget

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
    return [b.text() for b in view.findChildren(QPushButton) if b.isFlat()]


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


def test_the_rom_bar_is_hidden_on_the_disk_tab_only(qapp):
    from ui.common.build_panel import BuildPanel
    panel = BuildPanel()
    panel.show()
    tabs = panel._tabs
    for index in (0, 1, 2, 0):
        tabs.setCurrentIndex(index)
        assert panel.rom_bar.isVisible() is (tabs.widget(index) is not panel.disk), tabs.tabText(index)


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


def test_folders_are_full_and_only_the_dots_entry_is_outlined(qapp):
    from ui.common import icons
    view = DiskView()
    view.set_tree(_tree())
    _open(view, "sfx")
    full, outline = icons.folder_icon(False).pixmap(28, 28).toImage(), icons.folder_icon(True).pixmap(28, 28).toImage()
    assert full != outline                              # les deux dessins sont bien différents
    by_name = {view._list.item(i).text(): view._list.item(i) for i in range(view._list.count())}
    assert by_name["platformer"].icon().pixmap(28, 28).toImage() == full
    assert by_name["..."].icon().pixmap(28, 28).toImage() == outline

    view._go_to(0)                                       # à la racine, c'est un disque, ni plein ni en filet
    root_entry = view._list.item(0).icon().pixmap(28, 28).toImage()
    assert view._list.item(0).text() == "assets" and root_entry not in (full, outline)


def test_files_use_the_icon_of_their_family_then_of_their_format(qapp):
    from ui.common.disk_view import icon_key
    node = lambda name, family="": disk_tree.DiskNode(name, Path(name), disk_tree.FREE_SOURCE, family=family)
    assert icon_key(node("GOAL.json", "sfx")) == "sfx"            # un asset : sa famille, sans deviner
    assert icon_key(node("Ball.json", "sprites")) == "sprite"
    assert icon_key(node("Hero.lua", "scripts")) == "script_lua"
    assert icon_key(node("a.wav")) == "sfx"                       # une source libre : son format
    assert icon_key(node("a.xm")) == "music"
    assert icon_key(node("a.png")) == "sprite"
    assert icon_key(node("a.ttf")) == "font"
    assert icon_key(node("a.hex")) == "palette"
    assert icon_key(node("notes.txt")) == "script_file"           # inconnu : un fichier


def test_every_cell_has_the_same_size_whatever_its_name(qapp):
    view = DiskView()
    view.resize(900, 300)
    view.show()
    view.set_tree(_tree())
    _open(view, "sfx")
    qapp.processEvents()
    sizes = {(r.width(), r.height()) for r in (view._list.visualItemRect(view._list.item(i))
                                                for i in range(view._list.count()))}
    assert view._list.count() > 3
    assert len(sizes) == 1, sizes                        # « ... », un dossier, un fichier long : même boîte


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


def test_the_disk_tab_is_first_and_the_only_one_with_an_icon(qapp):
    from PyQt6.QtWidgets import QTabWidget
    from ui.common.build_panel import BuildPanel
    from ui.common.disk_view import add_disk_tab

    panel = BuildPanel()
    tabs = panel._tabs
    assert tabs.widget(0) is panel.disk and tabs.tabText(0) == "Disk"      # tout à gauche
    assert [tabs.tabText(i) for i in range(1, tabs.count())] == ["Console", "Diagnostics"]
    assert tabs.currentWidget() is not panel.disk                        # l'insérer ne change pas la sélection
    assert [not tabs.tabIcon(i).isNull() for i in range(tabs.count())] == [True, False, False]

    plain = QTabWidget()                                                 # le même geste dans la colonne de gauche
    first, second, disk = QWidget(), QWidget(), QWidget()
    plain.addTab(first, "Project viewer")
    add_disk_tab(plain, disk)
    assert plain.widget(0) is disk and plain.currentWidget() is first
    assert [not plain.tabIcon(i).isNull() for i in range(plain.count())] == [True, False]


def test_the_disk_icon_lights_up_with_its_tab(qapp):
    from PyQt6.QtWidgets import QTabWidget
    from ui.common.disk_view import add_disk_tab

    tabs = QTabWidget()
    other, disk = QWidget(), QWidget()
    tabs.addTab(other, "Other")
    add_disk_tab(tabs, disk)
    dim = tabs.tabIcon(0).pixmap(16, 16).toImage()                      # Disk n'est pas l'onglet courant
    tabs.setCurrentWidget(disk)
    lit = tabs.tabIcon(0).pixmap(16, 16).toImage()
    assert dim != lit
    tabs.setCurrentWidget(other)
    assert tabs.tabIcon(0).pixmap(16, 16).toImage() == dim
