"""Audio inspection does not play, rewrite, or render complete tracks."""
from pathlib import Path
import runpy
from types import SimpleNamespace
import wave

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog

from core import disk_tree
from core.models.audio import Sfx
from ui.common.disk_audio_preview import DiskAudioPlayer
from ui.common.disk_preview import DiskPreviewPanel, resource_preview


def _wav(path, width=2, channels=1):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(8000)
        handle.writeframes(b'\x10' * (800 * width * channels))


def _node(path, family='', kind=disk_tree.FREE_SOURCE):
    return disk_tree.DiskNode(path.name, path, kind, path.stem, family)


@pytest.mark.parametrize('width,channels', [(1, 1), (2, 2), (3, 1), (4, 1)])
def test_wav_metadata_and_bounded_waveform(qapp, tmp_path, width, channels):
    path = tmp_path / 'beep.wav'
    _wav(path, width, channels)
    original = path.read_bytes()
    hover = resource_preview(None, _node(path), False)
    assert any('8000 Hz' in line and f'{width * 8}' in line for line in hover.lines)
    assert hover.image.isNull() and hover.audio_path is None
    preview = resource_preview(None, _node(path), True)
    assert preview.audio_path == path
    assert preview.image.width() == 768
    assert preview.image.height() == 200
    assert path.read_bytes() == original


@pytest.mark.parametrize('kind', ['mod', 'xm', 's3m', 'it'])
def test_tracker_structure_without_rendering_audio(qapp, tmp_path, kind):
    fixtures = runpy.run_path(str(Path(__file__).parents[2] / 'audio' / 'module_fixtures.py'))
    path = tmp_path / f'track.{kind}'
    path.write_bytes(fixtures[f'make_{kind}']())
    result = resource_preview(None, _node(path), True)
    assert result.lines[0] == kind.upper()
    assert result.audio_path == path
    assert result.image.isNull()
    assert any(value == '125' for _, value in result.metadata)


def test_asset_settings_are_separate_from_source_listening(qapp, tmp_path):
    path = tmp_path / 'beep.wav'
    _wav(path)
    asset = Sfx(name='Beep', asset=str(path), volume=50, pitch=125, trim_start=20)
    project = SimpleNamespace(sfx=SimpleNamespace(get=lambda _: asset), asset_abs=lambda _: path)
    result = resource_preview(project, _node(tmp_path / 'Beep.sfx', 'sfx', disk_tree.ASSET), True)
    assert result.audio_path == path
    assert any(value == '50 %' for _, value in result.metadata)
    assert any(value == '125 %' for _, value in result.metadata)
    assert any(value == '20 ms' for _, value in result.metadata)
    path.unlink()
    missing = resource_preview(project, _node(tmp_path / 'Beep.sfx', 'sfx', disk_tree.ASSET), True)
    assert missing.audio_path is None and missing.note


def test_bad_audio_does_not_crash(qapp, tmp_path):
    for suffix in ['wav', 'mod', 'xm', 'it', 's3m']:
        path = tmp_path / f'bad.{suffix}'
        path.write_bytes(b'not an audio file')
        result = resource_preview(None, _node(path), True)
        assert result.audio_path is None and result.note


def test_wav_playback_is_explicit_and_selection_stops_it(qapp, tmp_path, monkeypatch):
    from PyQt6 import QtMultimedia
    calls = []

    class FakeMedia:
        def __init__(self, parent):
            self.errorOccurred = SimpleNamespace(connect=lambda callback: None)
        def setAudioOutput(self, output): pass
        def setSource(self, url): calls.append(('source', url.toLocalFile()))
        def play(self): calls.append(('play',))
        def stop(self): calls.append(('stop',))
        def position(self): return 0

    monkeypatch.setattr(QtMultimedia, 'QMediaPlayer', FakeMedia)
    monkeypatch.setattr(QtMultimedia, 'QAudioOutput', lambda parent: SimpleNamespace(setVolume=lambda value: calls.append(('volume', value))))
    player = DiskAudioPlayer()
    path = tmp_path / 'beep.wav'
    player.set_path(path)
    assert not calls
    player._play.click()
    assert ('play',) in calls
    assert any(call[0] == 'source' and Path(call[1]) == path for call in calls)
    assert player._timer.isActive()
    player.set_path(None)
    assert not player._timer.isActive()
    assert ('stop',) in calls
    assert not player._play.isEnabled()
    player.close()


def test_tracker_player_uses_unmodified_source_and_shuts_down(qapp, tmp_path):
    calls = []
    player = DiskAudioPlayer()
    player._box = SimpleNamespace(shutdown=lambda: calls.append('stop'),
        set_volume=lambda value: None,
        preview=lambda project, asset: calls.append(asset) or True)
    player.set_path(tmp_path / 'track.mod')
    player.play()
    asset = next(value for value in calls if not isinstance(value, str))
    assert asset.asset.endswith('track.mod') and not asset.loop
    player.show()
    player.hide()
    assert calls[-1] == 'stop'
    assert not player._timer.isActive()
    player.close()


def test_existing_module_engine_accepts_source_preview_project(qapp, tmp_path, monkeypatch):
    from core.models.audio import Music
    from ui.sound_mixer.box_playback import BoxPlayer
    fixtures = runpy.run_path(str(Path(__file__).parents[2] / 'audio' / 'module_fixtures.py'))
    path = tmp_path / 'track.mod'
    path.write_bytes(fixtures['make_mod']())
    player = BoxPlayer()
    monkeypatch.setattr(player, '_open_sink', lambda: None)
    assert player.preview(SimpleNamespace(asset_abs=lambda _: path), Music(asset=str(path), loop=False))
    assert player.sounding
    player.stop()
    assert not player.sounding


def test_enlarged_wav_and_tracker_previews_do_not_autoplay(qapp, tmp_path):
    path = tmp_path / 'beep.wav'
    _wav(path)
    fixtures = runpy.run_path(str(Path(__file__).parents[2] / 'audio' / 'module_fixtures.py'))
    module = tmp_path / 'track.mod'
    module.write_bytes(fixtures['make_mod']())
    panel = DiskPreviewPanel()
    observations = []
    for source in [path, module]:
        panel.show_preview(source.name, resource_preview(None, _node(source), True))
        assert panel._audio._media is None and panel._audio._box is None

        def inspect():
            dialogs = [dialog for dialog in panel.findChildren(QDialog) if dialog.isVisible()]
            dialog = dialogs[0]
            audio = dialog.findChild(DiskAudioPlayer)
            observations.append(audio is not None and audio._media is None and audio._box is None)
            dialog.accept()

        QTimer.singleShot(0, inspect)
        panel._enlarge.click()
    assert observations == [True, True]
    panel.close()
