"""Couper un jingle en module aux ordres à l'écran : la barre d'ordres, le bouton « Rogner », le rendu qui suit.

La barre (`OrderRangeBar`) est tenue seule, puis dans l'éditeur d'un jingle. Couper n'écrit que `order_start` / `order_end` :
le fichier n'est jamais touché."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                           # noqa: E402
from asset_fixtures import create                                     # noqa: E402
from core.models.audio import Jingle                                  # noqa: E402
from core.project import Project                                      # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer                     # noqa: E402
from ui.sound_mixer.music_editor import MusicEditor                   # noqa: E402
from ui.sound_mixer.order_range_bar import OrderRangeBar              # noqa: E402


@pytest.fixture
def bar(qapp):
    widget = OrderRangeBar()
    widget.resize(700, 46)
    widget.load([0, 0, 0, 0, 254, 0, 0, 255], 0, 0)                      # huit entrées, marqueurs compris
    widget.show()
    return widget


def _drag(widget, x_from: float, x_to: float):
    y = widget.height() // 2
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(round(x_from), y))
    QTest.mouseMove(widget, QPoint(round(x_to), y))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(round(x_to), y))


def test_an_uncut_module_shows_its_whole_table(bar):
    assert bar.window == (0, 8)


def test_dragging_the_start_handle_snaps_between_two_orders_and_writes_on_release(bar):
    moving, changed = [], []
    bar.moving.connect(lambda a, b: moving.append((a, b)))
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(0), bar._x_of(2) + 3)                            # près de la frontière 2

    assert changed == [(2, 8)] and moving and moving[-1] == (2, 8)


def test_dragging_the_end_handle_left_cuts_the_tail(bar):
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(8), bar._x_of(5))

    assert changed == [(0, 5)]


def test_the_handles_keep_at_least_one_order(bar):
    bar.set_window(3, 5)

    _drag(bar, bar._x_of(5), bar._x_of(0))                                # la fin glissée bien avant le début

    assert bar.window == (3, 4)


def test_double_click_plays_the_whole_module_again(bar):
    bar.set_window(2, 5)
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(100, 20))

    assert bar.window == (0, 8) and changed == [(0, 8)]


def test_a_drag_that_does_not_start_on_a_handle_changes_nothing(bar):
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(4), bar._x_of(6))

    assert changed == [] and bar.window == (0, 8)


# ── Dans l'éditeur d'un jingle ────────────────────────────────────────


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def editor(qapp, project):
    player = BoxPlayer()
    widget = MusicEditor(player.track_for)
    widget.resize(900, 760)
    widget._project = project
    return widget


def _jingle(project, name="Tune", orders=(0, 0, 0, 0)) -> Jingle:
    folder = project.user_library_dir / "jingles"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.it").write_bytes(F.make_it(orders=list(orders)))
    return create(project, "jingles", folder / f"{name}.it")


def test_a_jingle_module_has_the_trim_button_and_a_music_module_does_not(editor, project):
    editor.load(project, _jingle(project), sections=False)
    assert not editor._trim_zone.isHidden() and not editor._trim_btn.isChecked() and editor._order_bar.isHidden()

    folder = project.user_library_dir / "music"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Theme.it").write_bytes(F.make_it(orders=[0] * 4))
    editor.load(project, create(project, "music", folder / "Theme.it"))
    assert editor._trim_zone.isHidden()


def test_checking_the_button_shows_the_order_bar_and_not_the_ms_bar(editor, project):
    editor.load(project, _jingle(project), sections=False)

    editor._trim_btn.setChecked(True)
    assert not editor._order_bar.isHidden() and editor._trim_bar.isHidden()
    assert editor._order_bar.window == (0, 4)

    editor._trim_btn.setChecked(False)
    assert editor._order_bar.isHidden()


def test_an_already_cut_jingle_opens_with_its_bar_shown(editor, project):
    jingle = _jingle(project)
    jingle.order_start, jingle.order_end = 1, 3

    editor.load(project, jingle, sections=False)

    assert editor._trim_btn.isChecked() and not editor._order_bar.isHidden()
    assert editor._order_bar.window == (1, 3)
    assert "01–02" in editor._trim_note.text() and "2 of 4" in editor._trim_note.text()


def test_releasing_a_handle_writes_the_range_and_rerenders_the_shorter_module(editor, project):
    jingle = _jingle(project, orders=(0, 0, 0, 0, 0, 0))
    editor.load(project, jingle, sections=False)
    whole = editor._track.pcm.shape[0]
    saved = []
    editor.changed.connect(lambda: saved.append(1))

    editor._order_bar.changed.emit(0, 3)

    assert (jingle.order_start, jingle.order_end) == (0, 3) and saved == [1]
    assert editor._track.pcm.shape[0] < whole * 0.7                       # la moitié des ordres : un rendu plus court
    assert editor._order_bar.window == (0, 3)                             # la barre garde la table ENTIÈRE à l'écran


def test_the_whole_table_is_written_as_no_cut(editor, project):
    jingle = _jingle(project)
    jingle.order_start, jingle.order_end = 1, 3
    editor.load(project, jingle, sections=False)

    editor._order_bar.changed.emit(0, 4)

    assert (jingle.order_start, jingle.order_end) == (0, 0)


def test_a_cut_that_reaches_the_end_is_written_with_the_end_at_zero(editor, project):
    jingle = _jingle(project)
    editor.load(project, jingle, sections=False)

    editor._order_bar.changed.emit(2, 4)

    assert (jingle.order_start, jingle.order_end) == (2, 0)


def test_the_note_follows_the_drag_before_anything_is_written(editor, project):
    jingle = _jingle(project)
    editor.load(project, jingle, sections=False)

    editor._order_bar.moving.emit(1, 3)

    assert "01–02" in editor._trim_note.text()
    assert (jingle.order_start, jingle.order_end) == (0, 0)
