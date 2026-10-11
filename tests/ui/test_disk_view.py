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


def test_grid_cell_size_is_adjustable_only_in_grid_mode(qapp):
    view = DiskView()
    view.set_tree(_tree())
    default = view.grid_cell_width()
    view.set_grid_cell_width(default + 24)

    assert view.grid_cell_width() == default + 24
    assert view._list.gridSize().width() == default + 24
    assert not view._btn_grid_size.isHidden()

    view.set_layout_mode("list")
    assert view._btn_grid_size.isHidden()
    assert view._grid_size_slider.isHidden()


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


def test_the_vertical_tree_paints_its_rows_without_raising(qapp, monkeypatch):
    """Le délégué partagé lit le DiskNode sous le rôle de SA vue : l'arbre vertical ne range pas le nœud
    là où la vue à plat le range, et lire l'autre rôle y rendait une chaîne — un `paint` qui lève."""
    import sys
    from ui.common.disk_tree_view import DiskTreeView

    raised = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, tb: raised.append(error))
    view = DiskTreeView()
    view.resize(400, 300)
    view.set_tree(_tree())
    view.show()
    for _ in range(3):
        qapp.processEvents()

    assert raised == []


def test_rebuilding_the_breadcrumb_never_flashes_a_top_level_window(qapp):
    """Un maillon retiré du fil d'ariane devenait, un instant, une fenêtre de premier niveau (setParent(None)) :
    la petite fenêtre qui clignotait à chaque rafraîchissement de l'onglet Disk, donc à chaque Locate."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QWidget

    class Spy(QObject):
        def __init__(self):
            super().__init__()
            self.windows = []

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
                self.windows.append(type(watched).__name__)
            return False

    view = DiskView()
    view.resize(700, 300)
    view.show()
    qapp.processEvents()
    spy = Spy()
    qapp.installEventFilter(spy)
    try:
        for _ in range(3):
            view.set_tree(_tree())
            view.show_folder(Path("assets") / "sfx")            # chaque passage reconstruit le fil d'ariane
            qapp.processEvents()
            view.show_folder(Path("assets"))
            qapp.processEvents()
    finally:
        qapp.removeEventFilter(spy)

    assert spy.windows == []
