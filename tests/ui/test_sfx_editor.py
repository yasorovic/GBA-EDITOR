"""La découpe d'un effet à l'écran : l'onde, deux poignées, deux champs, le poids ROM — et ce qui s'écrit dans l'asset."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from asset_fixtures import create
from core.project import Project
from ui.sound_mixer.sfx_editor import SfxEditor


def _wav(path: Path, frames: int = 8000, rate: int = 8000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.sin(np.linspace(0, 200, frames)) * 20000).astype("<i2").tobytes())
    return path


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def editor(qapp, project):
    sfx = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    widget = SfxEditor()
    widget.resize(700, 300)
    widget.load(project, sfx)
    widget.changed_count = 0
    widget.changed.connect(lambda: setattr(widget, "changed_count", widget.changed_count + 1))
    widget.sfx = sfx
    return widget


def _saved(project, name="coin"):
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    return reopened.sfx.get(name)


def test_an_untouched_effect_shows_its_whole_file(editor):
    assert (editor._start.value(), editor._end.value()) == (0, 1000)
    assert not editor._reset.isEnabled()
    assert "Whole file" in editor._summary.text() and "7.8 KiB" in editor._summary.text()    # 8000 frames, un octet chacune


def test_dragging_a_handle_writes_the_trim_only_when_the_hand_lets_go(editor, project):
    editor._wave.loop_moving.emit(250, 750)
    assert editor.sfx.trim_start == 0 and editor.sfx.trim_end == 0                          # en cours : rien n'est écrit
    assert (editor._start.value(), editor._end.value()) == (250, 750) and "3.9 KiB" in editor._summary.text()

    editor._wave.loop_changed.emit(250, 750)

    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (250, 750) and editor.changed_count == 1
    saved = _saved(project)
    assert (saved.trim_start, saved.trim_end) == (250, 750)
    assert editor._reset.isEnabled() and "instead of 7.8 KiB" in editor._summary.text()


def test_the_two_fields_write_the_same_trim(editor, project):
    editor._start.setValue(100)
    editor._end.setValue(600)
    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (100, 600)
    assert (_saved(project).trim_start, _saved(project).trim_end) == (100, 600)


def test_a_range_that_covers_the_whole_file_is_written_as_no_trim(editor):
    editor._wave.loop_changed.emit(250, 750)
    editor._wave.loop_changed.emit(0, 1000)

    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (0, 0)                           # la fin à 0 suit un fichier remplacé
    assert not editor._reset.isEnabled()


def test_the_end_cannot_cross_the_start_nor_leave_less_than_the_shortest_trim(editor):
    editor._wave.loop_changed.emit(900, 905)

    assert editor.sfx.trim_end - editor.sfx.trim_start >= 10


def test_reset_keeps_the_whole_file_again(editor, project):
    editor._wave.loop_changed.emit(250, 750)
    editor._reset.click()

    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (0, 0)
    assert (_saved(project).trim_start, _saved(project).trim_end) == (0, 0)


def test_a_lower_sample_rate_lightens_the_announced_weight(editor, project):
    editor.sfx.sample_rate = 4000
    editor.refresh()

    assert "3.9 KiB" in editor._summary.text()                                              # 8000 frames à 8 kHz → 4000 à 4 kHz


def test_an_effect_without_a_readable_file_has_nothing_to_set(qapp, project):
    sfx = create(project, "sfx", _wav(project.assets_dir / "gone.wav"))
    (project.assets_dir / "gone.wav").unlink()
    widget = SfxEditor()
    widget.load(project, sfx)

    assert not widget._start.isEnabled() and not widget._end.isEnabled() and not widget._reset.isEnabled()
    widget.load(project, None)
    assert widget._summary.text() == ""


def test_the_fade_out_field_writes_frames_and_draws_the_ramp_inside_the_kept_part(editor, project):
    editor._wave.loop_changed.emit(100, 600)
    editor._fade.setValue(12)                                                        # 12 fr = 200 ms

    assert editor.sfx.fade_out == 12 and _saved(project).fade_out == 12
    assert editor._wave._ramp == (400, 600)                                          # sur la fin de la plage GARDÉE, pas du fichier
    assert editor.changed_count >= 1


def test_a_fade_longer_than_the_kept_part_is_drawn_no_longer_than_it(editor):
    editor._wave.loop_changed.emit(100, 200)
    editor._fade.setValue(60)                                                        # une seconde de fondu sur 100 ms gardées

    assert editor._wave._ramp == (100, 200)


def test_reset_trim_leaves_the_fade_alone_and_no_fade_draws_no_ramp(editor):
    editor._wave.loop_changed.emit(100, 600)
    editor._fade.setValue(12)
    editor._reset.click()

    assert editor.sfx.fade_out == 12 and editor._wave._ramp == (800, 1000)
    editor._fade.setValue(0)
    assert editor._wave._ramp is None
