"""La découpe d'un effet à l'écran : l'onde, la barre de découpe, deux champs, le poids ROM — et ce qui s'écrit dans l'asset."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from asset_fixtures import create
from core.project import Project
from ui.common.deferred_writes import get_deferred_writes
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
    get_deferred_writes().flush()                  # le sidecar s'écrit après un silence : on relit ce que la file a posé
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    return reopened.sfx.get(name)


def test_an_untouched_effect_shows_its_whole_file(editor):
    assert (editor._start.value(), editor._end.value()) == (0, 1000)
    assert not editor._reset.isEnabled()
    assert "Whole file" in editor._summary.text() and "7.8 KiB" in editor._summary.text()    # 8000 frames, un octet chacune


def test_dragging_a_trim_handle_writes_the_trim_only_when_the_hand_lets_go(editor, project):
    editor._trim_bar.moving.emit(250, 750)
    assert editor.sfx.trim_start == 0 and editor.sfx.trim_end == 0                          # en cours : rien n'est écrit
    assert (editor._start.value(), editor._end.value()) == (250, 750) and "3.9 KiB" in editor._summary.text()

    editor._trim_bar.changed.emit(250, 750)

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
    editor._trim_bar.changed.emit(250, 750)
    editor._trim_bar.changed.emit(0, 1000)

    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (0, 0)                           # la fin à 0 suit un fichier remplacé
    assert not editor._reset.isEnabled()


def test_the_end_cannot_cross_the_start_nor_leave_less_than_the_shortest_trim(editor):
    editor._trim_bar.changed.emit(900, 905)

    assert editor.sfx.trim_end - editor.sfx.trim_start >= 10


def test_reset_keeps_the_whole_file_again(editor, project):
    editor._trim_bar.changed.emit(250, 750)
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
    editor._trim_bar.changed.emit(100, 600)
    editor._mix.fade("fade_out").setValue(12)                                                        # 12 fr = 200 ms

    assert editor.sfx.fade_out == 12 and _saved(project).fade_out == 12
    assert editor._wave._ramp == (400, 600)                                          # sur la fin de la plage GARDÉE, pas du fichier
    assert editor.changed_count >= 1


def test_a_fade_longer_than_the_kept_part_is_drawn_no_longer_than_it(editor):
    editor._trim_bar.changed.emit(100, 200)
    editor._mix.fade("fade_out").setValue(60)                                                        # une seconde de fondu sur 100 ms gardées

    assert editor._wave._ramp == (100, 200)


def test_reset_trim_leaves_the_fade_alone_and_no_fade_draws_no_ramp(editor):
    editor._trim_bar.changed.emit(100, 600)
    editor._mix.fade("fade_out").setValue(12)
    editor._reset.click()

    assert editor.sfx.fade_out == 12 and editor._wave._ramp == (800, 1000)
    editor._mix.fade("fade_out").setValue(0)
    assert editor._wave._ramp is None


# ── La poignée du fondu, le canal, l'oscilloscope ─────────────────────

def _drag(wave, x_from: float, x_to: float):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    y = wave.height() - 9                                                            # la bande du bas, où vivent les poignées de fondu
    QTest.mousePress(wave, Qt.MouseButton.LeftButton, pos=QPoint(round(x_from), y))
    QTest.mouseMove(wave, QPoint(round(x_to), y))
    QTest.mouseRelease(wave, Qt.MouseButton.LeftButton, pos=QPoint(round(x_to), y))


def test_dragging_the_fade_handle_left_sets_the_fade_in_frames_and_writes_it_on_release(editor, project):
    editor.show()
    wave = editor._wave
    width = wave.width()

    _drag(wave, width - 1, width * 0.75)                                             # un quart de seconde = 15 frames

    assert editor.sfx.fade_out == 15 and _saved(project).fade_out == 15
    assert editor._mix.fade("fade_out").value() == 15 and wave._ramp == (750, 1000)
    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (0, 0)                    # la poignée du fondu n'a pas pris celle de la plage


def test_the_fade_handle_sits_on_the_end_of_the_kept_part_and_follows_the_trim(editor):
    editor.show()
    editor._trim_bar.changed.emit(100, 600)
    editor._mix.fade("fade_out").setValue(6)                                                         # 100 ms

    assert editor._wave._ramp == (500, 600)
    assert abs(editor._wave._ramp_x() - editor._wave._x_of(0.5)) < 1


def test_the_fade_handle_cannot_go_past_the_start_of_the_kept_part(editor):
    editor.show()
    editor._trim_bar.changed.emit(500, 1000)                                        # 500 ms gardées = 30 frames
    wave = editor._wave

    _drag(wave, wave._ramp_x() - 1 + 0, 2)                                           # jusqu'au bord gauche de l'onde

    assert editor.sfx.fade_out == 30


def test_without_a_track_provider_there_is_no_channel_bar_and_no_scope_switch(editor):
    assert editor._track is None and not editor._meters.isVisible()
    assert not editor._wave._mode_buttons["osc"].isVisible()


@pytest.fixture
def full_editor(qapp, project):
    from ui.sound_mixer.box_playback import BoxPlayer
    player = BoxPlayer()
    sfx = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    widget = SfxEditor(player.track_for)
    widget.resize(800, 320)
    widget.set_live_source(lambda frames: None)
    widget.load(project, sfx)
    widget.show()
    widget.sfx = sfx
    yield widget
    # Un widget encore affiché à sa destruction reçoit son `hideEvent` quand l'objet Python est déjà vidé (ramasse-miettes) :
    # l'exception dans ce slot fait avorter tout le processus. On le cache tant qu'il est entier.
    widget.hide()


def test_the_channel_bars_show_only_the_voices_of_the_source(full_editor, project):
    meters = full_editor._meters
    assert meters.isVisible() and full_editor._track is not None
    assert meters._count == full_editor._track.levels.channel_count        # pas les 8 canaux du projet : un effet en a une
    assert meters._count < project.settings.sound_channels


def test_the_bars_beyond_the_project_ceiling_are_not_added_but_kept_red(qapp):
    from core.engine_emulation.module_render import ChannelLevels
    from ui.sound_mixer.channel_meters import ChannelMeters
    levels = ChannelLevels(np.array([0], dtype=np.int64), np.zeros((1, 6), dtype=np.float32))
    meters = ChannelMeters()
    meters.set_levels(levels, 100, 4)
    assert meters._count == 6 and meters._ceiling == 4
    meters.set_levels(ChannelLevels(np.array([0], dtype=np.int64), np.zeros((1, 2), dtype=np.float32)), 100, 8)
    assert meters._count == 2                                              # un module à 2 voies : 2 barres, malgré 8 canaux


def test_the_scope_switch_appears_and_shows_the_start_of_the_rendered_effect(full_editor):
    from PyQt6.QtWidgets import QApplication
    wave = full_editor._wave
    assert wave._mode_buttons["osc"].isVisible()

    wave._mode_buttons["osc"].click()
    QApplication.processEvents()
    window, live = wave._osc_samples()

    assert not live and window is not None and len(window) == 800 and float(np.abs(window).max()) > 0.05
    wave._mode_buttons["wave"].click()


def _after_silence(editor) -> None:
    """Le rendu de l'aperçu part après un court silence (`refresh_soon`) : on déclenche le minuteur armé au lieu de
    l'attendre — même chemin, sans boucle d'évènements ni horloge."""
    assert editor._track_timer.isActive()
    editor._track_timer.stop()
    editor._track_timer.timeout.emit()


def test_the_channel_bar_and_the_scope_follow_a_trim_and_a_fade(full_editor, project):
    before = full_editor._track.pcm.shape[0]
    full_editor._trim_bar.changed.emit(0, 500)
    _after_silence(full_editor)

    assert full_editor._track.pcm.shape[0] < before * 0.6                           # le rendu est celui de la plage gardée
    full_editor._mix.fade("fade_out").setValue(15)
    _after_silence(full_editor)
    assert full_editor._track is not None and abs(int(full_editor._track.pcm[-1].max())) < 400   # ... et fondu jusqu'au silence


def test_turning_a_field_renders_the_preview_once_after_the_hand_stops(full_editor):
    renders = []
    provider = full_editor._track_provider
    full_editor._track_provider = lambda project, sfx: (renders.append(1), provider(project, sfx))[1]

    for frames in range(1, 11):
        full_editor._mix.fade("fade_out").setValue(frames)
    assert renders == []                                                             # le geste continue : rien n'est rendu

    _after_silence(full_editor)
    assert renders == [1]                                                            # un seul rendu, pour la dernière valeur


def test_the_playhead_is_placed_on_the_file_not_on_the_trimmed_render(full_editor):
    full_editor._trim_bar.changed.emit(400, 800)
    full_editor.sfx.pitch = 200
    full_editor.set_playhead_seconds(0.1)

    assert full_editor._wave._playhead == pytest.approx(0.4 + 0.1 * 2)               # début de la plage + durée de rendu × hauteur
    full_editor.set_playhead_seconds(-1.0)
    assert full_editor._wave._playhead == -1.0


# ── Fondu d'entrée et écoute A/B du taux ──────────────────────────────

def test_the_fade_in_field_writes_the_effect_and_survives_reopening(editor, project):
    editor._mix.fade("fade_in").setValue(12)

    assert editor.sfx.fade_in == 12 and editor.changed_count == 1
    assert _saved(project).fade_in == 12
    assert editor._summary.text()                                                  # le poids annoncé est toujours là


def test_an_untouched_effect_shows_no_fade_in(editor):
    assert editor._mix.fade("fade_in").value() == 0 and editor._mix.fade("fade_in").isEnabled()


def test_the_ab_button_needs_two_different_rates(editor, project):
    assert not editor._ab.isEnabled()                                              # rien à comparer : ni taux d'effet ni de projet

    project.settings.sfx_sample_rate = 4000                                        # le fichier est à 8 000 Hz
    editor.refresh()

    assert editor._ab.isEnabled()
    editor.sfx.sample_rate = 8000                                                  # l'effet impose le taux de son fichier
    editor.refresh()
    assert not editor._ab.isEnabled()


def test_the_summary_shows_the_weight_at_the_files_rate_when_the_rom_resamples(editor, project):
    plain = editor._summary.text()
    project.settings.sfx_sample_rate = 4000

    editor.refresh()

    text = editor._summary.text()
    assert "8000 Hz" in text and "KiB at the file's rate" in text and "KiB at the file's rate" not in plain


def test_toggling_the_ab_button_tells_the_player_and_loading_another_effect_resets_it(editor, project):
    project.settings.sfx_sample_rate = 4000
    editor.refresh()
    heard = []
    editor.original_rate_toggled.connect(heard.append)

    editor._ab.setChecked(True)
    editor.load(project, editor.sfx)                                               # on rouvre un effet : retour au son de la ROM

    assert heard == [True, False] and not editor._ab.isChecked()


def test_the_player_plays_the_file_at_its_own_rate_in_the_ab_mode(qapp, project):
    from ui.sound_mixer.box_playback import BoxPlayer
    sfx = create(project, "sfx", _wav(project.assets_dir / "ab.wav"))
    sfx.sample_rate = 4000
    player = BoxPlayer()

    built = player._prepare(project, sfx, sfx.name)[0]
    player.set_original_rate(True)
    original = player._prepare(project, sfx, sfx.name)[0]
    player.set_original_rate(False)

    assert built != original                                                       # deux fichiers : rééchantillonné / tel quel
    assert original == project.asset_abs(sfx.asset)                                # le fichier lui-même, au taux qu'il a
    assert player._prepare(project, sfx, sfx.name)[0] == built                     # et la bascule retombe sur le son de la ROM


# ── La table de mixage : volume, hauteur, variation, deux fondus ───────

def test_the_mix_table_shows_the_effects_values_and_the_ranges_of_its_fields(editor):
    from core.models.audio import FADE_MAX_FRAMES, SFX_PITCH_MAX, SFX_PITCH_MIN, SFX_PITCH_VARIATION_MAX
    mix = editor._mix

    assert (mix.fader("volume").value(), mix.fader("pitch").value(), mix.fader("pitch_variation").value()) == (100, 100, 0)
    assert (mix.fader("pitch").minimum(), mix.fader("pitch").maximum()) == (SFX_PITCH_MIN, SFX_PITCH_MAX)
    assert mix.fader("pitch_variation").maximum() == SFX_PITCH_VARIATION_MAX
    assert (mix.fade("fade_in").maximum(), mix.fade("fade_out").maximum()) == (FADE_MAX_FRAMES, FADE_MAX_FRAMES)


def test_a_fader_writes_the_effect_once_after_the_gesture_and_it_survives_reopening(editor, project):
    for value in (120, 130, 140, 150):
        editor._mix.fader("pitch").setValue(value)
    editor._mix.fader("volume").setValue(60)
    editor._mix.fader("pitch_variation").setValue(12)

    assert (editor.sfx.pitch, editor.sfx.volume, editor.sfx.pitch_variation) == (150, 60, 12)
    assert get_deferred_writes().has_pending()
    saved = _saved(project)
    assert (saved.pitch, saved.volume, saved.pitch_variation) == (150, 60, 12)


def test_the_volume_and_the_variation_do_not_wake_the_explorer_or_render_the_preview(editor):
    renders = []
    provider = editor._track_provider = lambda project, sfx: renders.append(1)

    editor._mix.fader("volume").setValue(40)
    editor._mix.fader("pitch_variation").setValue(20)

    assert editor.changed_count == 0 and renders == [] and not editor._track_timer.isActive()


def test_the_pitch_renders_the_preview_once_after_the_hand_stops(editor):
    editor._mix.fader("pitch").setValue(150)
    editor._mix.fader("pitch").setValue(160)

    assert editor._track_timer.isActive() and editor.changed_count == 0                 # un rendu à venir, pas à chaque cran


def test_the_fade_faders_redraw_the_ramp_and_tell_the_explorer(editor):
    editor._mix.fade("fade_out").setValue(30)

    assert editor._wave._ramp == (500, 1000) and editor.changed_count == 1


def test_the_fade_handle_on_the_wave_moves_the_fade_out_fader(editor, project):
    editor.show()
    wave = editor._wave

    _drag(wave, wave.width() - 1, wave.width() * 0.75)

    assert editor._mix.fade("fade_out").value() == 15 and editor.sfx.fade_out == 15
    assert _saved(project).fade_out == 15


def test_double_click_resets_a_fader_to_its_neutral_value(editor):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    editor._mix.fader("pitch").setValue(250)
    editor._mix.fader("pitch_variation").setValue(30)

    for name in ("pitch", "pitch_variation"):
        fader = editor._mix.fader(name)
        QTest.mouseDClick(fader, Qt.MouseButton.LeftButton, pos=QPoint(fader.width() // 2, fader.height() // 2))

    assert (editor.sfx.pitch, editor.sfx.pitch_variation) == (100, 0)                    # la variation revient à zéro, pas à 100


def test_the_mix_table_is_off_without_an_effect_and_its_fades_need_a_readable_file(qapp, project):
    widget = SfxEditor()
    widget.load(project, None)
    assert not widget.mix_panel.isEnabled()

    sfx = create(project, "sfx", _wav(project.assets_dir / "gone.wav"))
    (project.assets_dir / "gone.wav").unlink()
    widget.load(project, sfx)
    mix = widget._mix

    assert widget.mix_panel.isEnabled() and mix.fader("pitch").isEnabled()               # le volume et la hauteur n'ont pas besoin du fichier
    assert not mix.fade("fade_in").isEnabled() and not mix.fade("fade_out").isEnabled()  # un fondu coupe un fichier : il n'y en a pas


# ── La barre de découpe : la même que celle d'une musique ou d'un jingle WAV ──


def test_the_trim_bar_shows_the_whole_file_and_the_kept_range(editor):
    assert not editor._trim_bar.isHidden()
    assert editor._trim_bar.window == (0, 1000)
    editor._commit(250, 750)
    assert editor._trim_bar.window == (250, 750)


def test_dragging_a_bar_handle_moves_the_wave_and_fields_and_writes_on_release(editor, project):
    editor._trim_bar.moving.emit(250, 750)
    assert editor.sfx.trim_start == 0 and editor.sfx.trim_end == 0                          # en cours : rien n'est écrit
    assert (editor._start.value(), editor._end.value()) == (250, 750)

    editor._trim_bar.changed.emit(250, 750)

    assert (editor.sfx.trim_start, editor.sfx.trim_end) == (250, 750)
    assert (_saved(project).trim_start, _saved(project).trim_end) == (250, 750)


def test_the_trim_bar_follows_the_fields(editor):
    editor._start.setValue(300)
    assert editor._trim_bar.window[0] == 300


def test_the_wave_has_no_trim_handle_any_more_but_still_shows_the_kept_range(editor):
    """La barre règle la plage ; l'onde la montre (la part claire) et garde la poignée du fondu de sortie."""
    editor._commit(250, 750)
    wave = editor._wave
    assert wave._editable is False and wave._loop == (250, 750)
    assert wave._handle_at(wave._x_of(0.25), wave.height() / 2) is None          # une borne de plage ne se saisit plus sur l'onde


def test_an_effect_without_a_readable_file_has_no_trim_bar(qapp, project):
    sfx = create(project, "sfx", _wav(project.assets_dir / "coin.wav"))
    (project.assets_dir / "coin.wav").write_bytes(b"not a wav")
    widget = SfxEditor()
    widget.load(project, sfx)
    assert widget._trim_bar.isHidden()
