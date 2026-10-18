"""Source audio inspection and explicit playback for Disk, without asset writes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import wave
import struct

import numpy as np
from PyQt6.QtCore import QTimer, QUrl, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from core import disk_tree
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS, Music
from ui.common.labels import label
from ui.common.theme import C


def supports_audio(node):
    return node.family in ('sfx', 'music', 'jingles') or node.path.suffix.lower() in (MUSIC_FILE_EXTS | SFX_FILE_EXTS)


def _waveform(reader):
    """Sample small windows across the entire WAV, with bounded memory and I/O."""
    width, height = 768, 200
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(C.BG_DEEP))
    peaks = []
    frames, size = reader.getnframes(), reader.getsampwidth()
    for x in range(width):
        if not frames:
            break
        reader.setpos(min(frames - 1, x * frames // width))
        raw = reader.readframes(min(64, max(1, frames // width)))
        if size == 1:
            values = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
        elif size in (2, 4):
            values = np.frombuffer(raw, dtype='<i2' if size == 2 else '<i4').astype(np.float64) / (2 ** (size * 8 - 1))
        elif size == 3:
            packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            values = ((packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)) << 8) / 2147483648.0
        else:
            break
        if values.size:
            low, high = float(values.min()), float(values.max())
            peaks.append((x, round(height / 2 - high * (height / 2 - 4)),
                          round(height / 2 - low * (height / 2 - 4))))
    painter = QPainter(image)
    painter.setPen(QColor(C.ACCENT_COOL))
    for x, top, bottom in peaks:
        painter.drawLine(x, top, x, bottom)
    painter.end()
    return image


def read_audio_preview(project, node, result, render):
    asset = None
    path = node.path
    rows = []

    def add(key, value):
        if isinstance(value, bool):
            value = label('disk.meta_yes' if value else 'disk.meta_no')
        rows.append((label(key), str(value)))

    if node.kind == disk_tree.ASSET and node.family in ('sfx', 'music', 'jingles'):
        asset = getattr(project, node.family).get(node.owner) if project is not None else None
        path = project.asset_abs(asset.asset) if asset and asset.asset else None
        if path is None:
            result.note = label('disk.preview_missing_source')
            return
        add('disk.meta_source', path)
        for field, key, unit in (
            ('volume', 'disk.audio_volume', ' %'), ('sample_rate', 'disk.audio_target_rate', ' Hz'),
            ('pitch', 'disk.audio_pitch', ' %'), ('tempo', 'disk.audio_tempo', ' %'),
            ('panning', 'disk.audio_pan', ''), ('trim_start', 'disk.audio_trim_start', ' ms'),
            ('trim_end', 'disk.audio_trim_end', ' ms'),
            ('fade_in', 'disk.audio_fade_in', ' frames'), ('fade_out', 'disk.audio_fade_out', ' frames'),
            ('loop', 'disk.meta_loop', ''), ('loop_section', 'disk.audio_loop_section', ''),
            ('protected', 'disk.audio_protected', ''), ('pitch_variation', 'disk.audio_variation', ' %'),
            ('order_start', 'disk.audio_order_start', ''), ('order_end', 'disk.audio_order_end', ''),
            ('music_policy', 'disk.audio_music_policy', ''), ('duck_level', 'disk.audio_duck', ' %'),
        ):
            if hasattr(asset, field):
                value = getattr(asset, field)
                if field == 'sample_rate' and value == 0:
                    value, unit = label('disk.audio_default_rate'), ''
                elif field == 'trim_end' and value == 0:
                    value, unit = label('disk.audio_file_end'), ''
                if isinstance(value, bool):
                    add(key, value)
                elif value != '':
                    add(key, f'{value}{unit}')
        for section in getattr(asset, 'sections', []):
            rows.append((section.name, f'{section.start} → {section.end} ({asset.unit})'))
        if hasattr(asset, 'cues'):
            add('disk.audio_cues', len(asset.cues))
    try:
        path = Path(path)
        add('disk.meta_source_bytes', f'{path.stat().st_size:,} B')
        if path.suffix.lower() == '.wav':
            with wave.open(str(path), 'rb') as reader:
                channels, rate, bits, count = (reader.getnchannels(), reader.getframerate(),
                                               reader.getsampwidth() * 8, reader.getnframes())
                result.lines.extend(['WAV', label('disk.audio_wav', seconds=f'{count / max(1, rate):.3f}',
                                                  rate=rate, channels=channels, bits=bits)])
                add('disk.audio_samples', count)
                add('disk.audio_codec', reader.getcomptype())
                if render:
                    result.image = _waveform(reader)
                result.note = label('disk.audio_sampled_waveform')
        else:
            # Module parsers load sample data too. Keep inspection bounded for oversized files.
            if path.stat().st_size > 32 * 1024 * 1024:
                result.note = label('disk.audio_too_large')
                return
            from core.engine_emulation.module_model import load_module
            mod = load_module(path)
            result.lines.extend([mod.kind.upper(), label('disk.audio_module', channels=mod.num_channels,
                                                          orders=len(mod.order), patterns=len(mod.patterns))])
            for key, value in [('disk.meta_name', mod.name), ('disk.audio_bpm', mod.bpm),
                               ('disk.audio_speed', mod.speed), ('disk.audio_instruments', len(mod.instruments)),
                               ('disk.audio_sample_count', len(mod.samples)), ('disk.audio_restart', mod.restart)]:
                add(key, value)
            result.note = label('disk.audio_module_duration')
        if render:
            result.audio_path = path
    except (OSError, ValueError, EOFError, wave.Error, struct.error, IndexError, KeyError, TypeError, OverflowError):
        result.note = label('disk.preview_unavailable')
    finally:
        if render:
            result.metadata.extend(rows)


class DiskAudioPlayer(QWidget):
    """No device is opened until Play. Hiding or changing selection stops sound."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = None
        self._media = self._output = self._box = None
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._update_time)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self._play = QPushButton(label('disk.audio_play'))
        self._stop = QPushButton(label('disk.audio_stop'))
        self._play.clicked.connect(self.play)
        self._stop.clicked.connect(self.stop)
        row.addWidget(self._play)
        row.addWidget(self._stop)
        layout.addLayout(row)
        self._status = QLabel(label('disk.audio_source_listening'))
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setToolTip(label('disk.audio_listening_volume'))
        self._volume.valueChanged.connect(self._set_volume)
        layout.addWidget(self._volume)

    def set_path(self, path):
        self.stop()
        self._path = path
        self._play.setEnabled(path is not None)
        self._status.setText(label('disk.audio_source_listening'))

    def play(self):
        if self._path is None:
            return
        self.stop()
        try:
            if self._path.suffix.lower() == '.wav':
                self._start_wav()
            else:
                self._start_module()
            self._timer.start()
        except (OSError, ValueError, RuntimeError) as error:
            self.stop()
            self._status.setText(label('disk.audio_play_error', reason=str(error)))

    def _start_wav(self):
        if self._media is None:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            self._output = QAudioOutput(self)
            self._media = QMediaPlayer(self)
            self._media.setAudioOutput(self._output)
            self._media.errorOccurred.connect(self._media_error)
        self._output.setVolume(self._volume.value() / 100)
        self._media.setSource(QUrl.fromLocalFile(str(self._path)))
        self._media.play()

    def _media_error(self, error, message):
        self.stop()
        self._status.setText(label('disk.audio_play_error', reason=message))

    def _start_module(self):
        if self._box is None:
            from PyQt6.QtMultimedia import QMediaDevices
            if QMediaDevices.defaultAudioOutput().isNull():
                raise RuntimeError(label('disk.audio_no_device'))
            from ui.sound_mixer.box_playback import BoxPlayer
            self._box = BoxPlayer(self)
            self._box.message.connect(self._status.setText)
        asset = Music(name=self._path.stem, asset=str(self._path), loop=False)
        project = SimpleNamespace(asset_abs=lambda _: self._path)
        self._box.set_volume(self._volume.value() / 100)
        if not self._box.preview(project, asset):
            raise ValueError(label('disk.preview_unavailable'))

    def _set_volume(self, value):
        if self._output is not None:
            self._output.setVolume(value / 100)
        if self._box is not None:
            self._box.set_volume(value / 100)

    def _update_time(self):
        if self._media is not None and self._path.suffix.lower() == '.wav':
            seconds = self._media.position() / 1000
        elif self._box is not None:
            seconds = self._box.position_seconds()
        else:
            return
        self._status.setText(label('disk.audio_position', seconds=f'{seconds:.1f}'))

    def stop(self):
        self._timer.stop()
        if self._media is not None:
            self._media.stop()
            self._media.setSource(QUrl())
        if self._box is not None:
            self._box.shutdown()
        self._status.setText(label('disk.audio_source_listening'))

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)
