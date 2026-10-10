"""
core/engine_emulation/wav_render.py — Un effet `.wav` rendu au taux du mixeur.

C'est ce que `module_render` fait pour un module : produire du PCM stéréo
int16 à `GBA_MIX_RATE`, directement jouable par le `MusicDeck`. Les effets
n'ont pas de repères de motif, donc le `Track` rendu n'a pas de `marks`.
"""
from __future__ import annotations

import wave

import numpy as np

from core.engine_emulation.module_render import GBA_MIX_RATE
from core.engine_emulation.music_deck import Track


def render_wav(path, mix_rate: int = GBA_MIX_RATE) -> Track:
    """Lit un WAV PCM 8/16 bits et le rend en stéréo à `mix_rate`.

    Lève `ValueError` pour une profondeur que mmutil ne convertit pas non plus.
    """
    with wave.open(str(path)) as w:
        rate, channels, width, frames = (
            w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes())
        raw = w.readframes(frames)
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise ValueError(f"unsupported WAV bit depth: {width * 8}")

    mono = data[: (data.size // channels) * channels].reshape(-1, channels).mean(axis=1)
    if mono.size == 0:
        return Track(pcm=np.zeros((0, 2), dtype=np.int16))

    target_len = max(1, round(mono.size * mix_rate / rate))
    positions = np.linspace(0, mono.size - 1, target_len)
    resampled = np.interp(positions, np.arange(mono.size), mono)
    pcm = np.clip(resampled * 32767.0, -32768, 32767).astype(np.int16)
    return Track(pcm=np.stack([pcm, pcm], axis=1))
