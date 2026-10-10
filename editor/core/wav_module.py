"""
core/wav_module.py — Un `.wav` déposé dans assets/music/, rendu en module XM.

maxmod ne sait jouer de la musique que sous forme de module. Plutôt que de
greffer un second chemin de lecture (un « moteur d'effets en boucle ») à tout ce
qui parle de musique — `MOD_*`, fondus, jingles, MusicBox, aperçu —, le WAV est
ENCAPSULÉ : un module d'un seul instrument, dont l'échantillon est la piste
entière, mono 8 bits. Tout ce qui est en aval le voit comme un `.xm`.

  - l'échantillon est rendu à `WAV_MUSIC_RATE` Hz : au-dessus, le mixeur de la
    console (16 kHz) ne le restituerait pas, et la ROM paierait pour rien ;
  - le module dure autant que la piste : un `loop` rejoue donc le morceau, et
    un `once` s'arrête avec lui. La ligne dure ~20 ms, ce qui borne l'écart à
    la jointure ;
  - pas de boucle d'échantillon : c'est le module qui boucle, pas le matériel.

Le fichier de `assets/` n'est jamais réécrit : la sortie va dans le dossier de
build (`encode_music_for_build`) ou en mémoire (aperçu, validateur).
"""
from __future__ import annotations

import math
import struct
import wave

import numpy as np

# 8363 Hz est le C-4 d'un XM ; une octave plus haut (relative note +12), c'est
# 16 726 Hz — le plus proche du mixeur 16 kHz que le format sache exprimer sans
# finetune.
WAV_MUSIC_RATE = 16726
_RELATIVE_NOTE = 12
_NOTE_C4 = 49

_ROWS_PER_PATTERN = 256
_MAX_ORDERS = 256
_SPEED = 2
_BPM = 255
_ROW_SECONDS = _SPEED * 2.5 / _BPM
# Ce que la table d'ordre peut porter : un pattern plein tient 256 lignes.
_PATTERN_SECONDS = _MAX_ORDERS * _ROWS_PER_PATTERN * _ROW_SECONDS

# Le mixeur de maxmod range la longueur d'un échantillon décalée de 12 bits dans
# un mot de 32 (`longueur << 12`, relevé dans `mmMixerMix` de libmm) : un
# échantillon de 2^20 points ou plus déborde, et la piste se coupe au bout du
# reste — un titre de 75 s s'arrêtait après une douzaine de secondes. La borne est
# donc celle de l'ÉCHANTILLON, bien avant celle de la table d'ordre.
MAX_SAMPLE_FRAMES = (1 << 20) - 1
MAX_SECONDS = min(_PATTERN_SECONDS, MAX_SAMPLE_FRAMES / WAV_MUSIC_RATE)


def _read_mono(path) -> tuple[np.ndarray, int]:
    """(échantillons float32 mono dans [-1, 1], taux). ValueError si illisible."""
    try:
        with wave.open(str(path)) as w:
            rate, channels, width, frames = (
                w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes())
            raw = w.readframes(frames)
    except wave.Error as e:
        raise ValueError(f"WAV not recognised ({e})") from e
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise ValueError(f"WAV {width * 8} bits: only 8 and 16 bits are converted")
    data = data[: (data.size // channels) * channels].reshape(-1, channels).mean(axis=1)
    if data.size == 0:
        raise ValueError("WAV without any sample")
    return data, rate


def _resample(data: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Moyenne glissante puis interpolation : même filtre que `sfx_encode`.

    Sans le filtre, ce qui dépasse la moitié du nouveau taux se replie en
    sifflements. La moyenne est une somme cumulée : la piste fait des millions
    d'échantillons, une convolution y coûterait des secondes.
    """
    if rate == target:
        return data
    ratio = target / rate
    if ratio < 1.0:
        k = max(1, int(round(1 / ratio)))
        csum = np.concatenate(([0.0], np.cumsum(data, dtype=np.float64)))
        lo = np.clip(np.arange(data.size) - k // 2, 0, data.size)
        hi = np.clip(np.arange(data.size) - k // 2 + k, 0, data.size)
        data = ((csum[hi] - csum[lo]) / np.maximum(hi - lo, 1)).astype(np.float32)
    n_out = max(1, int(round(data.size * ratio)))
    pos = np.linspace(0, data.size - 1, n_out)
    return np.interp(pos, np.arange(data.size), data).astype(np.float32)


def _pattern(rows: int, trigger: bool) -> bytes:
    """Un pattern à 2 canaux (le minimum du format) ; seule la 1re case sonne."""
    packed = bytearray()
    if trigger:
        packed += bytes([0x80 | 0x01 | 0x02, _NOTE_C4, 1])   # canal 0 : note + instrument
    else:
        packed += bytes([0x80])
    packed += bytes([0x80])                                   # canal 1 : vide
    packed += bytes([0x80]) * (2 * (rows - 1))
    return struct.pack("<IBHH", 9, 0, rows, len(packed)) + bytes(packed)


def wav_to_xm(path, rate: int = WAV_MUSIC_RATE) -> bytes:
    """Le module XM qui joue ce WAV une fois. ValueError si le WAV n'est pas convertible."""
    data, src_rate = _read_mono(path)
    data = _resample(data, src_rate, rate)
    pcm = np.clip(np.round(data * 127.0), -128, 127).astype(np.int8)
    if pcm.size > MAX_SAMPLE_FRAMES:
        raise ValueError(
            f"track too long ({pcm.size / rate:.0f} s): the console's mixer plays "
            f"{MAX_SECONDS:.0f} s of one sample at most")

    # Ce qu'il faut de lignes pour couvrir la piste : un pattern plein qui
    # porte la note, des patterns vides partagés, et un dernier tronqué.
    total_rows = max(1, math.ceil(pcm.size / rate / _ROW_SECONDS))
    first = min(_ROWS_PER_PATTERN, total_rows)
    rest = total_rows - first
    full, tail = divmod(rest, _ROWS_PER_PATTERN)
    orders = [0] + [1] * full + ([2] if tail else [])
    if len(orders) > _MAX_ORDERS:
        raise ValueError(
            f"track too long ({pcm.size / rate:.0f} s): a module holds "
            f"{MAX_SECONDS:.0f} s at most")

    out = bytearray()
    out += b"Extended Module: " + b"wav".ljust(20, b" ") + bytes([0x1A])
    out += b"Backstage".ljust(20, b" ") + struct.pack("<H", 0x0104)
    out += struct.pack("<I", 20 + 256)
    # longueur, restart, canaux, patterns, instruments, flags (fréquences
    # linéaires), vitesse, tempo
    out += struct.pack("<HHHHHHHH", len(orders), 0, 2, 3, 1, 1, _SPEED, _BPM)
    out += bytes(orders).ljust(256, b"\x00")

    out += _pattern(first, trigger=True)
    out += _pattern(_ROWS_PER_PATTERN, trigger=False)
    out += _pattern(tail or 1, trigger=False)

    out += struct.pack("<I", 263) + b"wav".ljust(22, b"\x00") + bytes([0])
    out += struct.pack("<H", 1) + struct.pack("<I", 40)
    out += bytes(96) + bytes(48) + bytes(48)             # carte, enveloppes
    out += bytes(2) + bytes(6) + bytes(2) + bytes(4)     # compteurs, boucles, types, vibrato
    out += struct.pack("<H", 0) + bytes(22)              # fondu, réservé

    delta = np.diff(pcm.astype(np.int16), prepend=np.int16(0)).astype(np.int8)
    out += struct.pack("<IIIBbBBbB", pcm.size, 0, 0, 64, 0, 0, 128, _RELATIVE_NOTE, 0)
    out += b"wav".ljust(22, b"\x00")
    out += delta.tobytes()
    return bytes(out)


def encode_music_for_build(src, dst) -> int:
    """Écrit le module de `src` dans `dst` ; rend sa taille en octets."""
    from pathlib import Path
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = wav_to_xm(src)
    dst.write_bytes(data)
    return len(data)
