"""Un `.wav` dans assets/music/ : encapsulé en module XM, jouable comme les autres."""
import struct
import tempfile
import wave
from pathlib import Path

from core.engine_emulation.module_model import load_module
from core.resources.asset_reconciliation import check_audio_file
from core.wav_module import ROW_SECONDS, WAV_MUSIC_RATE, wav_to_xm


def _write_wav(path: Path, seconds: float, rate: int = 44100, channels: int = 2, width: int = 2):
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes((struct.pack("<h", 1000) if width == 2 else b"\xa0") * (n * channels))


def _music_dir() -> Path:
    d = Path(tempfile.mkdtemp()) / "music"
    d.mkdir()
    return d


def test_wav_becomes_a_module_as_long_as_the_track():
    wav = _music_dir() / "theme.wav"
    _write_wav(wav, 3.0)
    mod = load_module(wav)
    assert mod.samples[0].data.size == round(3.0 * WAV_MUSIC_RATE)
    rows = sum(mod.rows(i) for i in mod.order)
    assert abs(rows * ROW_SECONDS - 3.0) < ROW_SECONDS      # au plus une ligne de plus que la piste


def test_wav_in_music_folder_is_accepted_and_xm_roundtrips():
    wav = _music_dir() / "theme.wav"
    _write_wav(wav, 1.0, width=1)
    assert check_audio_file(wav) is None
    assert wav_to_xm(wav)[:17] == b"Extended Module: "


def test_too_long_track_is_refused_in_music_folder_only():
    d = _music_dir()
    long_wav = d / "long.wav"
    _write_wav(long_wav, 1300.0, rate=100, channels=1)   # peu d'octets, grande durée
    assert "limited" in check_audio_file(long_wav)
    sfx = d.parent / "sfx" / "long.wav"
    sfx.parent.mkdir()
    sfx.write_bytes(long_wav.read_bytes())
    assert check_audio_file(sfx) is None
