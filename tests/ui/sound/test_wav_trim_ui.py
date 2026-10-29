"""Rogner un WAV à l'écran : la barre à deux poignées, le bouton « Rogner », les sections qui suivent le son.

La barre (`TrimBar`) est la même pour les trois familles de WAV ; ici on la tient seule, puis dans l'éditeur d'une musique
et d'un jingle. Rogner n'écrit que `trim_start` / `trim_end` : le fichier n'est jamais touché.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                           # noqa: E402
from asset_fixtures import create                                     # noqa: E402
from core.models.audio import Jingle, UNIT_MS                         # noqa: E402
from core.project import Project                                      # noqa: E402
from core.wav_edit import MIN_TRIM_MS                                 # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer                     # noqa: E402
from ui.sound_mixer.music_editor import MusicEditor                   # noqa: E402
from ui.sound_mixer.trim_bar import TrimBar                           # noqa: E402
from ui.sound_mixer.waveform_view import peak_envelope                # noqa: E402


# ── La barre, seule ───────────────────────────────────────────────────

@pytest.fixture
def bar(qapp):
    widget = TrimBar()
    widget.resize(700, 46)
    mono = (np.sin(np.linspace(0, 80, 8000)) * 12000).astype(np.int16)
    peaks, _seconds = peak_envelope(np.stack([mono, mono], axis=1), 8000)
    widget.load(peaks, 10000, 0, 0)                                     # 10 s, rien de coupé
    widget.show()
    return widget


def _drag(widget, x_from: float, x_to: float):
    y = widget.height() // 2
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(round(x_from), y))
    QTest.mouseMove(widget, QPoint(round(x_to), y))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(round(x_to), y))


def test_an_untrimmed_file_shows_its_whole_length(bar):
    assert bar.window == (0, 10000)


def test_dragging_the_start_handle_keeps_the_rest_and_writes_on_release(bar):
    moving, changed = [], []
    bar.moving.connect(lambda a, b: moving.append((a, b)))
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(0), bar._x_of(2500))

    assert len(changed) == 1 and abs(changed[0][0] - 2500) <= 20 and changed[0][1] == 10000
    assert moving                                                        # le glisser a prévenu, le relâchement a écrit une fois


def test_dragging_the_end_handle_left_cuts_the_tail(bar):
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(10000), bar._x_of(6000))

    assert len(changed) == 1 and changed[0][0] == 0 and abs(changed[0][1] - 6000) <= 20


def test_the_two_handles_cannot_cross_nor_get_closer_than_the_shortest_trim(bar):
    bar.set_window(4000, 6000)

    _drag(bar, bar._x_of(6000), bar._x_of(1000))                         # la fin glissée bien avant le début

    start, end = bar.window
    assert end - start == MIN_TRIM_MS and start == 4000


def test_a_drag_that_does_not_start_on_a_handle_changes_nothing(bar):
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    _drag(bar, bar._x_of(5000), bar._x_of(8000))

    assert changed == [] and bar.window == (0, 10000)


def test_a_double_click_keeps_the_whole_file_again(bar):
    bar.set_window(2000, 7000)
    changed = []
    bar.changed.connect(lambda a, b: changed.append((a, b)))

    QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(bar.width() // 2, bar.height() // 2))

    assert changed == [(0, 10000)] and bar.window == (0, 10000)


def test_the_bar_draws_itself(bar):
    pixmap = bar.grab()

    assert not pixmap.isNull() and pixmap.width() == 700
    image = pixmap.toImage()
    assert len({image.pixel(x, 23) for x in range(0, 700, 7)}) > 3       # une enveloppe et des poignées, pas un aplat


# ── Dans l'éditeur d'une musique et d'un jingle ───────────────────────

RATE = 8000


def _wav(project, name: str, seconds: float = 4.0, family: str = "music"):
    folder = project.user_library_dir / ("jingles" if family == "jingles" else "music")
    folder.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(RATE * seconds)) / RATE
    with wave.open(str(folder / f"{name}.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    return create(project, family, folder / f"{name}.wav")


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


def test_the_trim_button_is_there_for_a_wav_and_not_for_a_module(editor, project):
    music = _wav(project, "Ambient")
    editor.load(project, music)
    assert not editor._trim_zone.isHidden() and not editor._trim_btn.isChecked() and editor._trim_bar.isHidden()

    folder = project.user_library_dir / "music"
    (folder / "Theme.it").write_bytes(F.make_it(orders=[0] * 4))
    module = create(project, "music", folder / "Theme.it")
    editor.load(project, module)

    assert editor._trim_zone.isHidden()


def test_checking_the_button_shows_the_bar_under_the_wave(editor, project):
    editor.load(project, _wav(project, "Ambient"))

    editor._trim_btn.setChecked(True)
    assert not editor._trim_bar.isHidden() and editor._trim_bar.window == (0, 4000)

    editor._trim_btn.setChecked(False)
    assert editor._trim_bar.isHidden()


def test_an_already_trimmed_asset_opens_with_its_bar_shown(editor, project):
    music = _wav(project, "Ambient")
    music.trim_start, music.trim_end = 1000, 3000

    editor.load(project, music)

    assert editor._trim_btn.isChecked() and not editor._trim_bar.isHidden()
    assert editor._trim_bar.window == (1000, 3000)
    assert editor._duration_ms == 2000                                    # l'axe de l'onde est celui de la plage gardée


def test_releasing_a_handle_writes_the_trim_slides_the_sections_and_rerenders(editor, project):
    music = _wav(project, "Ambient")
    music.unit = UNIT_MS
    music.add_section(1000, 2000, "Intro")
    music.add_section(2500, 3500, "Loop")
    editor.load(project, music)
    whole_pcm = editor._track.pcm.shape[0]
    saved = []
    editor.changed.connect(lambda: saved.append(1))

    editor._trim_bar.changed.emit(500, 4000)                              # la poignée de début lâchée à 0,5 s

    assert (music.trim_start, music.trim_end) == (500, 0) and saved == [1]
    assert [(s.name, s.start, s.end) for s in music.sections] == [("Intro", 500, 1500), ("Loop", 2000, 3000)]
    assert editor._duration_ms == 3500 and editor._track.pcm.shape[0] < whole_pcm * 0.95
    assert "0.5 s" in editor._trim_note.text() and "3.5 s" in editor._trim_note.text()


def test_a_section_left_outside_is_removed_and_said(editor, project):
    music = _wav(project, "Ambient")
    music.unit = UNIT_MS
    music.add_section(100, 400, "Short")
    music.add_section(2500, 3500, "Loop")
    editor.load(project, music)

    editor._trim_bar.changed.emit(1000, 4000)

    assert [s.name for s in music.sections] == ["Loop"]
    assert "Short" in editor._trim_note.text()


def test_the_rom_weight_follows_the_trim(editor, project):
    music = _wav(project, "Ambient")
    editor.load(project, music)
    before = editor._weight.text()

    editor._trim_bar.changed.emit(0, 2000)

    assert editor._weight.text() != before


def test_a_jingle_wav_gets_its_fades_a_jingle_module_does_not(editor, project):
    jingle = _wav(project, "Fanfare", family="jingles")
    assert isinstance(jingle, Jingle)
    editor.load(project, jingle, sections=False)
    assert editor._baked_fades and all(f.isEnabled() for f in editor._faders._fades.values())

    folder = project.user_library_dir / "jingles"
    (folder / "Tune.it").write_bytes(F.make_it(orders=[0] * 4))
    module = create(project, "jingles", folder / "Tune.it")
    editor.load(project, module, sections=False)

    assert not editor._baked_fades and not any(f.isEnabled() for f in editor._faders._fades.values())


def test_moving_a_jingle_fade_rerenders_the_wave_after_a_silence(editor, project):
    jingle = _wav(project, "Fanfare", family="jingles")
    editor.load(project, jingle, sections=False)

    editor._faders.fade("fade_out").setValue(30)

    assert jingle.fade_out == 30 and editor._rerender_timer.isActive()


def test_a_music_fade_does_not_rerender_the_wave(editor, project):
    music = _wav(project, "Ambient")
    editor.load(project, music)

    editor._faders.fade("fade_out").setValue(30)

    assert music.fade_out == 30 and not editor._rerender_timer.isActive()   # la console l'applique : rien à refaire
