"""Glisser des fichiers et des dossiers de l'onglet Disk vers un dossier : la vue demande le déplacement, rien de plus."""
from pathlib import Path

from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from core import disk_tree
from ui.common.disk_tree_view import DiskTreeView
from ui.common.disk_view import DiskView, _DiskList, disk_mime, dropped_paths

BASE = Path("assets")


def _tree() -> disk_tree.DiskNode:
    deep = disk_tree.DiskNode("platformer", BASE / "sfx" / "platformer", disk_tree.FOLDER)
    sfx = disk_tree.DiskNode("sfx", BASE / "sfx", disk_tree.FOLDER, children=[
        deep,
        disk_tree.DiskNode("GOAL.sfx", BASE / "sfx" / "GOAL.sfx", disk_tree.ASSET, "GOAL"),
        disk_tree.DiskNode("GOAL.wav", BASE / "sfx" / "GOAL.wav", disk_tree.LINKED_SOURCE, "GOAL")])
    return disk_tree.DiskNode("assets", BASE, disk_tree.FOLDER, children=[sfx])


def _drop(widget, point, mime) -> None:
    """Un glisser-déposer COMPLET (entrée, survol, dépôt) envoyé au viewport, comme le fait le système : si
    le viewport n'accepte pas les dépôts, rien n'atteint les gestionnaires de la liste."""
    from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent
    from PyQt6.QtWidgets import QApplication
    point = QPointF(point).toPoint()
    args = (Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    viewport = widget.viewport()
    QApplication.sendEvent(viewport, QDragEnterEvent(point, *args))
    over = QDragMoveEvent(point, *args)
    QApplication.sendEvent(viewport, over)
    if over.isAccepted():
        QApplication.sendEvent(viewport, QDropEvent(QPointF(point), *args))


def _row(view: DiskView, text: str):
    return next(view._list.item(i) for i in range(view._list.count()) if view._list.item(i).text() == text)


def _centre(view: DiskView, text: str):
    return view._list.visualItemRect(_row(view, text)).center()


def _flat_view_in_sfx(qapp) -> DiskView:
    view = DiskView()
    view.resize(600, 300)
    view.set_tree(_tree())
    view.show()
    view._enter(_row(view, "sfx"))
    return view


def test_the_paths_travel_in_one_format_and_a_foreign_drag_carries_none():
    assert dropped_paths(disk_mime([Path("a/b.wav"), Path("a/c")])) == [str(Path("a/b.wav")), str(Path("a/c"))]
    foreign = QMimeData()
    foreign.setText("not ours")
    assert dropped_paths(foreign) == []


def test_dropping_on_a_folder_entry_asks_to_move_there(qapp):
    view = _flat_view_in_sfx(qapp)
    asked = []
    view.move_requested.connect(lambda paths, target: asked.append((paths, target)))

    _drop(view._list, _centre(view, "platformer"), disk_mime([BASE / "sfx" / "GOAL.wav"]))

    assert asked == [([str(BASE / "sfx" / "GOAL.wav")], str(BASE / "sfx" / "platformer"))]


def test_dropping_on_the_up_entry_moves_one_level_up(qapp):
    view = _flat_view_in_sfx(qapp)
    asked = []
    view.move_requested.connect(lambda paths, target: asked.append(target))

    _drop(view._list, _centre(view, "..."), disk_mime([BASE / "sfx" / "GOAL.sfx"]))

    assert asked == [str(BASE)]


def test_dropping_on_a_file_or_on_nothing_asks_nothing(qapp):
    view = _flat_view_in_sfx(qapp)
    asked = []
    view.move_requested.connect(lambda *args: asked.append(args))

    _drop(view._list, _centre(view, "GOAL.sfx"), disk_mime([BASE / "sfx" / "GOAL.wav"]))
    _drop(view._list, QPointF(590, 290).toPoint(), disk_mime([BASE / "sfx" / "GOAL.wav"]))
    foreign = QMimeData()
    foreign.setText("x")
    _drop(view._list, _centre(view, "platformer"), foreign)

    assert asked == []


def test_what_is_dragged_from_the_flat_view_is_the_selected_entries_only(qapp):
    view = _flat_view_in_sfx(qapp)
    _row(view, "GOAL.sfx").setSelected(True)
    _row(view, "GOAL.wav").setSelected(True)

    paths = dropped_paths(view._list.mimeData(view._list.selectedItems()))

    assert sorted(paths) == sorted([str(BASE / "sfx" / "GOAL.sfx"), str(BASE / "sfx" / "GOAL.wav")])
    assert not (_row(view, "...").flags() & Qt.ItemFlag.ItemIsDragEnabled)       # « ... » ne se glisse pas


def _find(view: DiskTreeView, path: Path):
    stack = [view._tree.topLevelItem(0)]
    while stack:
        item = stack.pop()
        if item.data(0, Qt.ItemDataRole.UserRole) == str(path):
            return item
        stack.extend(item.child(i) for i in range(item.childCount()))
    return None


def _tree_view(qapp) -> DiskTreeView:
    view = DiskTreeView()
    view.resize(400, 400)
    view.set_tree(_tree())
    view.show()
    view._tree.expandAll()
    return view


def test_dropping_on_a_folder_of_the_tree_asks_to_move_there(qapp):
    view = _tree_view(qapp)
    asked = []
    view.move_requested.connect(lambda paths, target: asked.append((paths, target)))
    centre = view._tree.visualItemRect(_find(view, BASE / "sfx" / "platformer")).center()

    _drop(view._tree, centre, disk_mime([BASE / "sfx" / "GOAL.sfx"]))

    assert asked == [([str(BASE / "sfx" / "GOAL.sfx")], str(BASE / "sfx" / "platformer"))]


def test_the_root_of_the_tree_cannot_be_dragged(qapp):
    view = _tree_view(qapp)
    root = view._tree.topLevelItem(0)
    goal = _find(view, BASE / "sfx" / "GOAL.sfx")

    paths = dropped_paths(view._tree.mimeData([root, goal]))

    assert paths == [str(BASE / "sfx" / "GOAL.sfx")]


def _mouse(widget, kind, point, buttons):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    event = QMouseEvent(kind, QPointF(point), QPointF(widget.mapToGlobal(point)), Qt.MouseButton.LeftButton,
                        buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget.viewport(), event)


def test_pressing_on_an_entry_and_moving_drags_it_instead_of_drawing_a_rectangle(qapp, monkeypatch):
    from PyQt6.QtCore import QEvent
    view = _flat_view_in_sfx(qapp)
    started = []
    monkeypatch.setattr(_DiskList, "startDrag", lambda self, actions: started.append(sorted(i.text() for i in self.selectedItems())))
    start = _centre(view, "GOAL.sfx")

    _mouse(view._list, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    _mouse(view._list, QEvent.Type.MouseMove, start + QPointF(40, 0).toPoint(), Qt.MouseButton.LeftButton)
    _mouse(view._list, QEvent.Type.MouseButtonRelease, start + QPointF(40, 0).toPoint(), Qt.MouseButton.NoButton)

    assert started == [["GOAL.sfx"]]                                           # le glisser a démarré sur l'entrée pressée


def test_pressing_on_a_selected_entry_drags_the_whole_selection(qapp, monkeypatch):
    from PyQt6.QtCore import QEvent
    view = _flat_view_in_sfx(qapp)
    _row(view, "GOAL.sfx").setSelected(True)
    _row(view, "GOAL.wav").setSelected(True)
    started = []
    monkeypatch.setattr(_DiskList, "startDrag", lambda self, actions: started.append(sorted(i.text() for i in self.selectedItems())))
    start = _centre(view, "GOAL.wav")

    _mouse(view._list, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    _mouse(view._list, QEvent.Type.MouseMove, start + QPointF(40, 0).toPoint(), Qt.MouseButton.LeftButton)

    assert started == [["GOAL.sfx", "GOAL.wav"]]


def test_a_folder_that_cannot_receive_is_neither_highlighted_nor_accepted_and_says_why_once(qapp):
    from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent
    from PyQt6.QtWidgets import QApplication
    view = _flat_view_in_sfx(qapp)
    asked, said = [], []
    view.set_drop_check(lambda paths, target: (asked.append(target) or False, (Path("texts.json"), "protected")))
    view.drop_blocked.connect(said.append)
    mime = disk_mime([BASE / "texts.json"])
    point = _centre(view, "platformer")
    args = (Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    QApplication.sendEvent(view._list.viewport(), QDragEnterEvent(point, *args))
    moves = [QDragMoveEvent(point, *args) for _ in range(3)]                    # la souris bouge sur le même dossier
    for move in moves:
        QApplication.sendEvent(view._list.viewport(), move)

    assert not any(move.isAccepted() for move in moves)                         # curseur « interdit »
    assert view._list._drop_hover is None                                       # aucune surimpression
    assert len(asked) == 1 and said == [(Path("texts.json"), "protected")]      # question et message : une seule fois


def test_a_lone_prefab_or_layout_also_travels_in_the_format_the_canvas_reads():
    from core.models.resource import MIME_PREFAB_TEMPLATE, MIME_UI_LAYOUT
    prefab = disk_tree.DiskNode("Player.prefab", BASE / "Player.prefab", disk_tree.ASSET, "Player", "prefabs")
    layout = disk_tree.DiskNode("Hud.layout", BASE / "Hud.layout", disk_tree.ASSET, "Hud", "ui_layouts")
    sound = disk_tree.DiskNode("GOAL.sfx", BASE / "GOAL.sfx", disk_tree.ASSET, "GOAL", "sfx")
    assert bytes(disk_mime([prefab.path], [prefab]).data(MIME_PREFAB_TEMPLATE)) == b"Player"
    assert bytes(disk_mime([layout.path], [layout]).data(MIME_UI_LAYOUT)) == b"Hud"
    for nodes in ([sound], [prefab, layout]):                 # ni un autre asset, ni une sélection multiple
        mime = disk_mime([n.path for n in nodes], nodes)
        assert not mime.hasFormat(MIME_PREFAB_TEMPLATE) and not mime.hasFormat(MIME_UI_LAYOUT)


def test_the_canvas_view_turns_a_dropped_layout_into_a_signal(qapp):
    from PyQt6.QtGui import QDragEnterEvent
    from core.models.resource import MIME_UI_LAYOUT
    from ui.scene_manager.canvas.canvas_view import GBAView
    from ui.scene_manager.canvas.canvas_scene import GBAScene
    view, names = GBAView(GBAScene()), []
    view.ui_layout_dropped.connect(names.append)
    mime = QMimeData()
    mime.setData(MIME_UI_LAYOUT, b"Hud")
    point = QPointF(5, 5).toPoint()
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    view.dragEnterEvent(QDragEnterEvent(point, *args))
    view.dropEvent(QDropEvent(QPointF(point), *args))
    assert names == ["Hud"]
