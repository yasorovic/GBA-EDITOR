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
  - pas de boucle d'échantillon : c'est le module qui boucle, pas le matériel —
    SAUF quand la musique porte une section de boucle (`loop_ms`, ci-dessous) :
    l'échantillon boucle alors lui-même, à l'échantillon près, et le module ne finit
    plus (cf. `wav_to_xm`). Mesuré sur ROM le 2026-10-11 : sans l'une ou l'autre des
    deux pièces, le son s'arrête ou le module s'éteint.

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
# Le plancher d'un taux choisi : en dessous, un morceau n'est plus qu'un grésillement,
# et le gain de place (une piste plus longue dans un échantillon) ne vaut plus la perte.
MUSIC_SAMPLE_RATE_MIN = 4000
_NOTE_C4 = 49

_ROWS_PER_PATTERN = 256
_MAX_ORDERS = 256
_SPEED = 2
_BPM = 255
_ROW_SECONDS = _SPEED * 2.5 / _BPM
# Ce que la table d'ordre peut porter : un pattern plein tient 256 lignes.
_PATTERN_SECONDS = _MAX_ORDERS * _ROWS_PER_PATTERN * _ROW_SECONDS
# Une coupe (`music.cut_to`) attend le retour de la LIGNE à zéro : pour une piste WAV,
# la fin de son pattern de 256 lignes, soit ~5 s au pire.
CUT_WAIT_SECONDS = _ROWS_PER_PATTERN * _ROW_SECONDS

# Le mixeur de maxmod range la longueur d'un échantillon décalée de 12 bits dans
# un mot de 32 (`longueur << 12`, relevé dans `mmMixerMix` de libmm) : un
# échantillon de 2^20 points ou plus déborde, et la piste se coupe au bout du
# reste — un titre de 75 s s'arrêtait après une douzaine de secondes. La borne est
# donc celle de l'ÉCHANTILLON, bien avant celle de la table d'ordre.
MAX_SAMPLE_FRAMES = (1 << 20) - 1
MAX_SECONDS = min(_PATTERN_SECONDS, MAX_SAMPLE_FRAMES / WAV_MUSIC_RATE)


def effective_rate(sample_rate: int) -> int:
    """Le taux de build d'une musique : 0 (le défaut de `Music.sample_rate`) veut dire
    `WAV_MUSIC_RATE`."""
    return int(sample_rate) or WAV_MUSIC_RATE


def max_seconds(rate: int = WAV_MUSIC_RATE) -> float:
    """Ce que dure, au plus, une piste à ce taux : la borne est celle de l'ÉCHANTILLON
    (`MAX_SAMPLE_FRAMES`), donc plus le taux baisse, plus la piste peut être longue —
    à 13 kHz, ~78 s tiennent là où 16,7 kHz en refuse 62."""
    return min(_PATTERN_SECONDS, MAX_SAMPLE_FRAMES / max(1, rate))


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


def _pattern(rows: int, trigger: bool, jump_to: int | None = None) -> bytes:
    """Un pattern à 2 canaux (le minimum du format) ; seule la 1re case sonne.

    `jump_to` pose un saut de position (`Bxx`) sur le canal 1 de la DERNIÈRE ligne :
    le module retourne à cet ordre au lieu de finir. Le canal 0, lui, n'est pas touché
    — il continue de jouer son échantillon."""
    packed = bytearray()
    if trigger:
        packed += bytes([0x80 | 0x01 | 0x02, _NOTE_C4, 1])   # canal 0 : note + instrument
    else:
        packed += bytes([0x80])
    packed += bytes([0x80])                                   # canal 1 : vide
    packed += bytes([0x80]) * (2 * (rows - 1))
    if jump_to is not None:
        # Le canal 1 de la dernière ligne est le dernier octet du pattern.
        packed = packed[:-1] + bytes([0x80 | 0x08 | 0x10, 0x0B, jump_to])
    return struct.pack("<IBHH", 9, 0, rows, len(packed)) + bytes(packed)


def _tuning(rate: int) -> tuple[int, int]:
    """(note relative, finetune) qui font sonner un échantillon à `rate` Hz sur un C-4.

    Un C-4 d'XM joue à 8 363 Hz ; la note relative décale en demi-tons, le finetune
    en 128es de demi-ton. À `WAV_MUSIC_RATE` (le double exact) c'est (12, 0) : la
    sortie du taux par défaut ne change pas d'un octet."""
    semitones = 12.0 * math.log2(rate / 8363.0)
    relative = int(round(semitones))
    fine = int(round((semitones - relative) * 128))
    return max(-96, min(95, relative)), max(-128, min(127, fine))


def _snap_to_zero_crossing(pcm: np.ndarray, index: int, window: int) -> int:
    """L'indice le plus proche de `index` où le signal PASSE de négatif à positif.

    Une boucle d'échantillon saute de `end` à `start` : si les deux sont des
    passages par zéro montants, la jointure ne fait pas de marche, donc pas de
    clic. Dans `window` échantillons ; sans passage, on garde `index`."""
    lo, hi = max(1, index - window), min(pcm.size - 1, index + window)
    best = None
    for i in range(lo, hi + 1):
        if pcm[i - 1] <= 0 < pcm[i] and (best is None or abs(i - index) < abs(best - index)):
            best = i
    return index if best is None else best


# Un morceau qui boucle sur moins que ça n'est plus une boucle, c'est un bourdonnement.
_MIN_LOOP_SECONDS = 0.05
# Jusqu'où la jointure peut se déplacer pour tomber sur un passage par zéro.
_SNAP_SECONDS = 0.02


def render_at_rate(path, rate: int) -> np.ndarray:
    """La piste telle que le module la portera : mono, `rate` Hz, 8 bits signés.

    Lue par le build ET par l'aperçu — ce qu'on entend est ce que la ROM contiendra,
    avec la même perte (taux choisi, quantification à 8 bits), pas la source."""
    data, src_rate = _read_mono(path)
    data = _resample(data, src_rate, rate)
    return np.clip(np.round(data * 127.0), -128, 127).astype(np.int8)


def loop_frames(pcm: np.ndarray, rate: int, loop_ms: tuple[int, int]) -> tuple[int, int]:
    """(début, fin) de la boucle d'échantillon, en échantillons de `pcm`, ramenés au
    passage par zéro montant le plus proche. ValueError si ce n'est plus une boucle.

    Un seul calcul pour le build (`wav_to_xm`) et pour l'aperçu."""
    window = max(1, int(rate * _SNAP_SECONDS))
    start = _snap_to_zero_crossing(pcm, int(round(loop_ms[0] * rate / 1000)), window)
    end = _snap_to_zero_crossing(pcm, min(pcm.size, int(round(loop_ms[1] * rate / 1000))), window)
    if end <= start or (end - start) < rate * _MIN_LOOP_SECONDS:
        raise ValueError(f"loop of {loop_ms[0]}-{loop_ms[1]} ms is too short or empty "
                         f"(at least {int(_MIN_LOOP_SECONDS * 1000)} ms)")
    return start, end


def wav_to_xm(path, rate: int = WAV_MUSIC_RATE, loop_ms: tuple[int, int] | None = None) -> bytes:
    """Le module XM qui joue ce WAV. ValueError si le WAV n'est pas convertible.

    Sans `loop_ms`, la piste joue UNE fois : le module dure autant qu'elle.

    Avec `loop_ms = (début, fin)` en millisecondes, la piste est intro puis boucle :
    l'ÉCHANTILLON boucle entre ces deux points (ramenés au passage par zéro montant
    le plus proche, pour que la jointure ne claque pas), et le module ne finit plus —
    sa dernière ligne saute sur elle-même. Il faut les DEUX : sans la boucle
    d'échantillon, le son s'arrête à la fin de la piste alors que le module continue ;
    sans le saut, le module s'arrête et coupe l'échantillon (mesuré sur ROM le
    2026-10-11). Ce qui suit la fin de la boucle n'est jamais joué : il n'entre pas
    dans l'échantillon, donc pas dans la ROM.
    """
    pcm = render_at_rate(path, rate)

    loop = None
    if loop_ms is not None:
        start, end = loop_frames(pcm, rate, loop_ms)
        pcm = pcm[:end]
        loop = (start, end - start)

    if pcm.size > MAX_SAMPLE_FRAMES:
        raise ValueError(
            f"track too long ({pcm.size / rate:.0f} s): the console's mixer plays "
            f"{max_seconds(rate):.0f} s of one sample at most")

    if loop is not None:
        # Un pattern d'une ligne qui porte la note, un autre qui saute sur lui-même.
        patterns = [_pattern(1, trigger=True), _pattern(1, trigger=False, jump_to=1)]
        orders = [0, 1]
    else:
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
                f"{max_seconds(rate):.0f} s at most")
        patterns = [_pattern(first, trigger=True),
                    _pattern(_ROWS_PER_PATTERN, trigger=False),
                    _pattern(tail or 1, trigger=False)]

    out = bytearray()
    out += b"Extended Module: " + b"wav".ljust(20, b" ") + bytes([0x1A])
    out += b"Backstage".ljust(20, b" ") + struct.pack("<H", 0x0104)
    out += struct.pack("<I", 20 + 256)
    # longueur, restart, canaux, patterns, instruments, flags (fréquences
    # linéaires), vitesse, tempo
    out += struct.pack("<HHHHHHHH", len(orders), 0, 2, len(patterns), 1, 1, _SPEED, _BPM)
    out += bytes(orders).ljust(256, b"\x00")

    for pattern in patterns:
        out += pattern

    out += struct.pack("<I", 263) + b"wav".ljust(22, b"\x00") + bytes([0])
    out += struct.pack("<H", 1) + struct.pack("<I", 40)
    out += bytes(96) + bytes(48) + bytes(48)             # carte, enveloppes
    out += bytes(2) + bytes(6) + bytes(2) + bytes(4)     # compteurs, boucles, types, vibrato
    out += struct.pack("<H", 0) + bytes(22)              # fondu, réservé

    delta = np.diff(pcm.astype(np.int16), prepend=np.int16(0)).astype(np.int8)
    relative, fine = _tuning(rate)
    loop_start, loop_length = loop if loop is not None else (0, 0)
    out += struct.pack("<IIIBbBBbB", pcm.size, loop_start, loop_length, 64, fine,
                       1 if loop is not None else 0, 128, relative, 0)
    out += b"wav".ljust(22, b"\x00")
    out += delta.tobytes()
    return bytes(out)


def encode_music_for_build(src, dst, sample_rate: int = 0,
                           loop_ms: tuple[int, int] | None = None) -> int:
    """Écrit le module de `src` dans `dst` ; rend sa taille en octets.

    `sample_rate` est celui de `Music.sample_rate` (0 = le défaut), `loop_ms` la
    section de boucle de la musique, en millisecondes (cf. `wav_to_xm`)."""
    from pathlib import Path
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = wav_to_xm(src, effective_rate(sample_rate), loop_ms)
    dst.write_bytes(data)
    return len(data)
