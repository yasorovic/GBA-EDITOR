"""Le décodage d'un WAV, profondeur par profondeur : 8, 16, 24 et 32 bits entiers.

mmutil ne lit que le 8 et le 16 bits. L'éditeur décode les autres lui-même (`sfx_render.read_wav`) et réécrit un 16 bits mono
que mmutil reçoit — un effet 24 bits n'est donc plus refusé à l'import. Rien ne couvrait ce décodage hors d'un essai manuel :
une valeur lue de travers (signe, échelle, ordre des octets) rendrait l'effet muet ou saturé sans qu'un message le dise.
"""
from __future__ import annotations

import wave

import numpy as np
import pytest

from core import sfx_render
from core.models.audio import Sfx


def _write(path, frames: bytes, width: int, channels: int = 1, rate: int = 8000):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(frames)
    return path


def _pack24(values) -> bytes:
    """Trois octets little-endian par échantillon, signé."""
    return b"".join(int(v).to_bytes(3, "little", signed=True) for v in values)


def test_8_bits_is_unsigned_and_centred_on_128(tmp_path):
    path = _write(tmp_path / "a.wav", bytes([128, 255, 0, 192]), 1)

    data, rate, channels = sfx_render.read_wav(path)

    assert (rate, channels) == (8000, 1)
    assert data == pytest.approx([0.0, 127 / 128, -1.0, 0.5])


def test_16_bits_is_signed_over_32768(tmp_path):
    path = _write(tmp_path / "a.wav", np.array([0, 16384, -16384, 32767, -32768], dtype="<i2").tobytes(), 2)

    data, _rate, _channels = sfx_render.read_wav(path)

    assert data == pytest.approx([0.0, 0.5, -0.5, 32767 / 32768, -1.0])


def test_24_bits_reads_the_sign_the_scale_and_the_byte_order(tmp_path):
    path = _write(tmp_path / "a.wav", _pack24([0, 4194304, -4194304, 8388607, -8388608, 1]), 3)

    data, _rate, _channels = sfx_render.read_wav(path)

    assert data == pytest.approx([0.0, 0.5, -0.5, 8388607 / 8388608, -1.0, 1 / 8388608])


def test_32_bits_integer_reads_the_sign_and_the_scale(tmp_path):
    path = _write(tmp_path / "a.wav", np.array([0, 2 ** 30, -(2 ** 30), 2 ** 31 - 1, -(2 ** 31)], dtype="<i4").tobytes(), 4)

    data, _rate, _channels = sfx_render.read_wav(path)

    assert data == pytest.approx([0.0, 0.5, -0.5, 1.0, -1.0])


def test_the_same_signal_reads_the_same_whatever_the_depth(tmp_path):
    """Une même onde écrite en 16, 24 et 32 bits se lit pareil (à la précision du plus court)."""
    wave_ = np.sin(np.linspace(0, 30, 600)) * 0.7
    paths = {
        16: _write(tmp_path / "w16.wav", (wave_ * 32767).astype("<i2").tobytes(), 2),
        24: _write(tmp_path / "w24.wav", _pack24(np.round(wave_ * 8388607)), 3),
        32: _write(tmp_path / "w32.wav", np.round(wave_ * 2147483647).astype("<i4").tobytes(), 4),
    }

    read = {bits: sfx_render.read_wav(path)[0] for bits, path in paths.items()}

    assert read[24] == pytest.approx(read[32], abs=1e-6)
    assert read[16] == pytest.approx(read[32], abs=1e-4)


def test_a_float_wav_is_not_decoded_the_import_refuses_it(tmp_path):
    """Le WAV flottant (format 3) n'est pas du PCM : `wave` ne le lit pas, et l'import (`check_audio_file`) le refuse."""
    header = (b"RIFF" + (36 + 8).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
              + (3).to_bytes(2, "little") + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little")
              + (32000).to_bytes(4, "little") + (4).to_bytes(2, "little") + (32).to_bytes(2, "little")
              + b"data" + (8).to_bytes(4, "little") + bytes(8))
    path = tmp_path / "float.wav"
    path.write_bytes(header)

    with pytest.raises(Exception):
        sfx_render.read_wav(path)


def test_stereo_is_mixed_to_mono_when_the_effect_is_rendered(tmp_path):
    left_right = np.array([[20000, -20000], [10000, 10000]] * 50, dtype="<i2")
    path = _write(tmp_path / "s.wav", left_right.tobytes(), 2, channels=2)

    data, rate = sfx_render.render_sfx(path, Sfx(name="x"), 0)

    assert rate == 8000 and data.size == 100
    assert data[0::2] == pytest.approx(np.zeros(50), abs=1e-4)                 # gauche + droite opposées : silence
    assert data[1::2] == pytest.approx(np.full(50, 10000 / 32768), abs=1e-4)   # identiques : inchangé


def test_a_24_bit_effect_is_rewritten_as_16_bit_mono_for_mmutil_even_untouched(tmp_path):
    from types import SimpleNamespace
    settings = SimpleNamespace(sfx_sample_rate=0)
    src = _write(tmp_path / "deep.wav", _pack24(np.round(np.sin(np.linspace(0, 40, 800)) * 6000000)), 3)

    out = sfx_render.preview_file(src, Sfx(name="x"), settings)
    written = sfx_render.write_sfx(src, tmp_path / "out.wav", Sfx(name="x"), 0)

    assert out != src                                                          # rien d'édité, mais mmutil ne lit pas du 24 bits
    with wave.open(str(out)) as w:
        assert (w.getsampwidth(), w.getnchannels(), w.getframerate()) == (2, 1, 8000)
    assert written == 800
    decoded = sfx_render.read_wav(tmp_path / "out.wav")[0]
    assert decoded == pytest.approx(np.sin(np.linspace(0, 40, 800)) * 6000000 / 8388608, abs=2e-4)   # le signal survit


def test_a_16_bit_effect_nobody_touched_is_played_as_the_file_itself(tmp_path):
    from types import SimpleNamespace
    src = _write(tmp_path / "ok.wav", np.zeros(400, dtype="<i2").tobytes(), 2)

    assert sfx_render.preview_file(src, Sfx(name="x"), SimpleNamespace(sfx_sample_rate=0)) is src
