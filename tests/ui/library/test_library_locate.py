"""LOCATE (onglet Disk) et REVEAL (explorateur) depuis une library : l'icône à droite de chaque asset,
le menu contextuel, et le canal qui mène à la fenêtre."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from ui.common import reveal
from ui.common.locate_bus import get_locate_bus


def _library(qapp, tmp_path):
    from core.models.scene import Scene
    from core.project import Project
    from ui.common.asset_library import AssetLibrary
    from ui.common.asset_kinds import SCENES

    project = Project(tmp_path / "jeu")
    scene = Scene(name="Title")
    scene.id = "0123456789ab"
    project.scenes.append(scene)
    library = AssetLibrary("Library", [SCENES])
    library.resize(320, 240)
    library.load_project(project)
    library.show()
    qapp.processEvents()
    return library, project, scene


def _row(library):
    tree = library._trees["Scenes"]
    return tree, tree.topLevelItem(0)


def _cell_center(tree, item, column) -> QPoint:
    return tree.visualRect(tree.indexFromItem(item, column)).center()


def test_the_locate_icon_sits_in_its_own_column_and_asks_the_bus_for_the_file(qapp, tmp_path):
    library, project, scene = _library(qapp, tmp_path)
    tree, item = _row(library)
    heard = []
    get_locate_bus().requested.connect(lambda path, name: heard.append((path, name)))

    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=_cell_center(tree, item, 2))

    assert heard == [(project.scenes.path_of(scene), "Title")]
    assert not item.isSelected()                # le clic sur l'icône n'active pas la scène


def test_a_click_on_the_name_still_selects_and_does_not_locate(qapp, tmp_path):
    library, _project, _scene = _library(qapp, tmp_path)
    tree, item = _row(library)
    heard = []
    get_locate_bus().requested.connect(lambda path, name: heard.append(name))

    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=_cell_center(tree, item, 0))

    assert heard == [] and item.isSelected()


def test_reveal_of_an_asset_shows_its_file_in_the_file_manager(qapp, tmp_path, monkeypatch):
    library, project, scene = _library(qapp, tmp_path)
    tree, _item = _row(library)
    shown = []
    monkeypatch.setattr("ui.common.asset_library.reveal_in_file_manager", shown.append)

    tree._reveal_asset(scene)

    assert shown == [project.scenes.path_of(scene)]


def test_every_family_of_a_library_can_be_located():
    from ui.common import asset_kinds
    from ui.common.asset_library import AssetKind

    kinds = [k for k in vars(asset_kinds).values() if isinstance(k, AssetKind)]
    assert kinds and all(kind.file_of is not None for kind in kinds)


def test_reveal_selects_a_file_where_the_system_knows_how(tmp_path, monkeypatch):
    target = tmp_path / "hero.sprite"
    target.write_text("{}")
    launched = []
    monkeypatch.setattr(reveal.subprocess, "Popen", lambda args: launched.append(args))
    monkeypatch.setattr(reveal.sys, "platform", "win32")

    reveal.reveal_in_file_manager(target)

    assert launched == [["explorer", "/select,", str(target)]]


def test_reveal_opens_a_folder_and_ignores_what_does_not_exist(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(reveal.QDesktopServices, "openUrl", lambda url: opened.append(Path(url.toLocalFile())))

    reveal.reveal_in_file_manager(tmp_path)
    reveal.reveal_in_file_manager(tmp_path / "absent" / "nothing.txt")
    reveal.reveal_in_file_manager(None)

    assert opened == [tmp_path]


def test_a_locate_reads_the_disk_once_not_once_per_tab_switch(monkeypatch):
    """Changer d'onglet Disk déclenche un rafraîchissement ; `_locate_file` les suspend le temps des bascules
    puis relit une seule fois. La garde : suspendu, `_refresh_disk` ne touche ni au projet ni à l'arbre."""
    from types import SimpleNamespace
    from window import MainWindow

    touched = []
    monkeypatch.setattr("core.disk_tree.build_disk_tree", lambda project: touched.append("build") or "tree")
    project = SimpleNamespace(load_all_resources=lambda: touched.append("load"))

    def window(suspended):
        return SimpleNamespace(project=project, _disk_refresh_suspended=suspended,
                               _show_disk=lambda tree: touched.append(f"show {tree}"))

    MainWindow._refresh_disk(window(True))
    assert touched == []                                                    # suspendu : rien n'est relu

    MainWindow._refresh_disk(window(False))
    assert touched == ["load", "build", "show tree"]                        # libéré : la relecture a lieu
    assert MainWindow._disk_refresh_suspended is False                      # rien ne reste suspendu par défaut


def test_the_disk_refresh_rescans_the_disk_before_reading_the_tree():
    """Le bouton Refresh (et l'ouverture de l'onglet) rattrape d'abord ce qui a changé hors de l'éditeur, puis relit
    l'arbre ; suspendu (Locate), il ne fait ni l'un ni l'autre."""
    from types import SimpleNamespace
    from window import MainWindow

    calls = []

    def window(project, suspended=False):
        return SimpleNamespace(project=project, _disk_refresh_suspended=suspended,
                               _watcher=SimpleNamespace(rescan=lambda: calls.append("rescan")),
                               _refresh_disk=lambda: calls.append("refresh"))

    MainWindow._rescan_and_refresh_disk(window(object()))
    assert calls == ["rescan", "refresh"]

    calls.clear()
    MainWindow._rescan_and_refresh_disk(window(object(), suspended=True))
    MainWindow._rescan_and_refresh_disk(window(None))
    assert calls == []


def test_switching_screen_rescans_the_disk_once_a_project_is_open():
    """Changer d'écran rattrape d'abord les fichiers modifiés hors de l'éditeur, avant que l'écran d'arrivée se
    peuple ou se rafraîchisse ; sans projet, rien n'est rescanné."""
    from types import SimpleNamespace
    from window import MainWindow

    calls = []

    def window(project):
        w = SimpleNamespace(project=project,
                            _watcher=SimpleNamespace(rescan=lambda: calls.append("rescan")),
                            _ensure_screen=lambda i: calls.append("ensure"))
        # On s'arrête à `_ensure_screen` : le reste de `_show_screen` a ses propres tests.
        w._ensure_screen = lambda i: (calls.append("ensure"), (_ for _ in ()).throw(_Stop()))[0]
        return w

    class _Stop(Exception):
        pass

    for project in (object(), None):
        try:
            MainWindow._show_screen(window(project), 0)
        except _Stop:
            pass
        calls.append("|")
    assert calls == ["rescan", "ensure", "|", "ensure", "|"]


def test_the_pointer_returning_rescans_unless_busy_or_too_soon(monkeypatch):
    """Le survol de la fenêtre rattrape les changements externes, une fois par seconde au plus, et jamais pendant
    qu'une modification attend d'être écrite (le rescan lèverait la suppression du watcher)."""
    from types import SimpleNamespace
    from window import MainWindow

    now = [100.0]
    monkeypatch.setattr("window.time.monotonic", lambda: now[0])
    calls = []
    w = SimpleNamespace(project=object(), _has_pending_changes=lambda: False, _last_enter_rescan=0.0,
                        _RESCAN_ON_ENTER_MIN_S=MainWindow._RESCAN_ON_ENTER_MIN_S,
                        _watcher=SimpleNamespace(rescan=lambda: calls.append("rescan")))

    MainWindow._rescan_on_pointer_return(w)
    now[0] += 0.5
    MainWindow._rescan_on_pointer_return(w)          # trop tôt
    assert calls == ["rescan"]

    now[0] += 1.0
    w._has_pending_changes = lambda: True
    MainWindow._rescan_on_pointer_return(w)          # écriture en attente
    assert calls == ["rescan"]

    w._has_pending_changes = lambda: False
    MainWindow._rescan_on_pointer_return(w)
    w.project = None
    now[0] += 2.0
    MainWindow._rescan_on_pointer_return(w)          # pas de projet
    assert calls == ["rescan", "rescan"]

