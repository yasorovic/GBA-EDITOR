"""
core/wav_module.py — Un `.wav` déposé dans assets/music/, rendu en module XM.

maxmod ne sait jouer de la musique que sous forme de module. Plutôt que de
greffer un second chemin de lecture (un « moteur d'effets en boucle ») à tout ce
qui parle de musique — `MOD_*`, fondus, jingles, MusicBox, aperçu —, le WAV est
ENCAPSULÉ : un VRAI module, que tout ce qui est en aval voit comme un `.xm`.

  - la piste est découpée en SEGMENTS aux frontières des sections de la musique ;
    chaque segment est un échantillon XM (mono, 8 bits) joué par une note au début
    d'un pattern. Une section est donc une plage de positions d'ordre, exactement
    comme dans un module tracker : `music_info_row`, la table des sections, le tick
    de boucle, la coupe et `leave_loop` n'ont aucun cas particulier pour un WAV ;
  - les frontières tombent sur la GRILLE DES LIGNES : le module ne déclenche une
    note qu'au début d'une ligne, et un segment doit commencer pile à la fin du
    précédent. Une ligne dure 11,4155 ms (vitesse 1, 219 BPM = 180 échantillons du
    mixeur de maxmod, exactement : à 255 BPM maxmod tronque le tick et les lignes
    passent 0,4 % trop vite — mesuré sur ROM le 2026-10-11) ;
  - l'échantillon est rendu à `WAV_MUSIC_RATE` Hz (ou au taux choisi) : au-dessus,
    le mixeur de la console (16 kHz) ne le restituerait pas, et la ROM paierait pour
    rien ;
  - un segment plus long que ce qu'un échantillon peut porter est coupé en morceaux
    à une limite de ligne : la durée maximale est celle de la table d'ordres.

Le fichier de `assets/` n'est jamais réécrit : la sortie va dans le dossier de
build (`encode_music_for_build`) ou en mémoire (aperçu, validateur).
"""
from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from core.sfx_render import read_wav

# 8363 Hz est le C-4 d'un XM ; une octave plus haut (relative note +12), c'est
# 16 726 Hz — le plus proche du mixeur 16 kHz que le format sache exprimer sans
# finetune.
WAV_MUSIC_RATE = 16726
# Le plancher d'un taux choisi : en dessous, un morceau n'est plus qu'un grésillement,
# et le gain de place ne vaut plus la perte.
MUSIC_SAMPLE_RATE_MIN = 4000
_NOTE_C4 = 49

# Le mixeur « 16 kHz » de maxmod (celui que `mmInitDefault` choisit) tourne en vrai à
# 15 768 Hz. Un tick dure un NOMBRE ENTIER de ses échantillons : à 219 BPM,
# 15 768 × 2,5 / 219 = 180 pile, donc une ligne (vitesse 1) dure 180 échantillons et le
# module ne dérive pas par rapport au temps réel.
MIXER_RATE = 15768
_SPEED = 1
_BPM = 219
SAMPLES_PER_ROW = 180
assert MIXER_RATE * 5 * _SPEED == SAMPLES_PER_ROW * _BPM * 2, "the row length must be a whole number of mixer samples"
ROW_SECONDS = SAMPLES_PER_ROW / MIXER_RATE

ROWS_PER_PATTERN = 256
MAX_ORDERS = 256
MAX_INSTRUMENTS = 128
# Ce que la table d'ordres peut porter : des patterns pleins, bout à bout.
MAX_SECONDS = MAX_ORDERS * ROWS_PER_PATTERN * ROW_SECONDS
# Une coupe (`music.cut_to`) attend le retour de la LIGNE à zéro : pour un segment long,
# la fin de son pattern de 256 lignes, soit ~3 s au pire.
CUT_WAIT_SECONDS = ROWS_PER_PATTERN * ROW_SECONDS

# Le mixeur de maxmod range la longueur d'un échantillon décalée de 12 bits dans
# un mot de 32 (`longueur << 12`, relevé dans `mmMixerMix` de libmm) : un
# échantillon de 2^20 points ou plus déborde, et la piste se coupe au bout du
# reste — un titre de 75 s s'arrêtait après une douzaine de secondes. Un segment qui
# dépasse est donc coupé en plusieurs échantillons.
MAX_SAMPLE_FRAMES = (1 << 20) - 1


def effective_rate(sample_rate: int) -> int:
    """Le taux de build d'une musique : 0 (le défaut de `Music.sample_rate`) veut dire
    `WAV_MUSIC_RATE`."""
    return int(sample_rate) or WAV_MUSIC_RATE


def max_seconds() -> float:
    """Ce que dure, au plus, une piste : la borne est celle de la table d'ordres."""
    return MAX_SECONDS


def _tuning(rate: int) -> tuple[int, int]:
    """(note relative, finetune) qui font sonner un échantillon à `rate` Hz sur un C-4.

    Un C-4 d'XM joue à 8 363 Hz ; la note relative décale en demi-tons, le finetune
    en 128es de demi-ton. À `WAV_MUSIC_RATE` (le double exact) c'est (12, 0)."""
    semitones = 12.0 * math.log2(rate / 8363.0)
    relative = int(round(semitones))
    fine = int(round((semitones - relative) * 128))
    return max(-96, min(95, relative)), max(-128, min(127, fine))


def played_rate(rate: int) -> float:
    """Le taux auquel l'échantillon sonnera RÉELLEMENT : `_tuning` arrondit à 1/128 de demi-ton, soit
    jusqu'à 0,27 % d'écart. On rend la piste à ce taux-là, pas à celui demandé : sinon un segment durerait
    un peu plus ou un peu moins que ses lignes, et le suivant arriverait trop tôt ou trop tard."""
    relative, fine = _tuning(rate)
    return 8363.0 * 2.0 ** ((relative + fine / 128.0) / 12.0)


def _read_mono(path) -> tuple[np.ndarray, int]:
    """(échantillons float32 mono dans [-1, 1], taux). ValueError si illisible."""
    try:
        got = read_wav(Path(path))
    except wave.Error as e:
        raise ValueError(f"WAV not recognised ({e})") from e
    if got is None:
        raise ValueError("WAV depth not read: only 8, 16, 24 and 32 bits PCM")
    data, rate, channels = got
    data = data[: (data.size // channels) * channels].reshape(-1, channels).mean(axis=1)
    if data.size == 0:
        raise ValueError("WAV without any sample")
    return data, rate


def wav_seconds(path) -> float:
    """La durée d'un WAV, lue dans son en-tête. ValueError s'il est illisible."""
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / max(1, w.getframerate())
    except wave.Error as e:
        raise ValueError(f"WAV not recognised ({e})") from e


def _resample(data: np.ndarray, rate: float, target: float) -> np.ndarray:
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


# ── Le plan : où tombent les segments ─────────────────────────────────────────

@dataclass(frozen=True)
class WavPlan:
    """Comment une piste se découpe en échantillons et en positions d'ordre.

    `chunks[k]` est la plage de LIGNES [début, fin) du k-ième échantillon ; `first_order[k]` est
    la position d'ordre où il démarre. Les deux se lisent aussi bien pour le build (qui écrit le module)
    que pour la table des sections (qui traduit des millisecondes en positions d'ordre)."""
    play_rate: float
    total_rows: int
    chunks: tuple
    first_order: tuple
    order_count: int

    def order_at(self, ms: float) -> int:
        """La position d'ordre où démarre le segment qui commence à `ms` (arrondie à la ligne), ou la
        longueur de la table si `ms` est la fin de la piste. ValueError si aucun segment n'y commence —
        la frontière doit avoir été donnée à `plan_wav`."""
        row = min(self.total_rows, max(0, round(ms / 1000.0 / ROW_SECONDS)))
        if row >= self.total_rows:
            return self.order_count
        for (start, _end), order in zip(self.chunks, self.first_order):
            if start == row:
                return order
        raise ValueError(f"no segment starts at {ms} ms")


def plan_wav(seconds: float, rate: int, boundaries_ms: Iterable[float] = ()) -> WavPlan:
    """Le plan d'une piste de `seconds`, rendue à `rate`, coupée aux frontières `boundaries_ms`.

    ValueError si la piste ne tient pas dans un module (table d'ordres, nombre d'instruments)."""
    total_rows = max(1, math.ceil(seconds / ROW_SECONDS - 1e-9))
    cuts = {0, total_rows}
    for ms in boundaries_ms:
        cuts.add(min(total_rows, max(0, round(ms / 1000.0 / ROW_SECONDS))))
    cuts = sorted(cuts)
    play_rate = played_rate(rate)
    # Des morceaux d'un nombre ENTIER de patterns : un morceau qui s'arrête au milieu d'un pattern
    # gaspillerait le reste de sa position d'ordre, et la table n'en a que 256.
    max_rows = max(ROWS_PER_PATTERN, int(MAX_SAMPLE_FRAMES / (play_rate * ROW_SECONDS)) // ROWS_PER_PATTERN
                   * ROWS_PER_PATTERN)

    chunks, first_order, order = [], [], 0
    for a, b in zip(cuts, cuts[1:]):
        start = a
        while start < b:
            end = min(b, start + max_rows)
            chunks.append((start, end))
            first_order.append(order)
            order += math.ceil((end - start) / ROWS_PER_PATTERN)
            start = end
    if order > MAX_ORDERS:
        raise ValueError(f"track too long ({seconds:.0f} s): a module holds {MAX_SECONDS:.0f} s at most")
    if len(chunks) > MAX_INSTRUMENTS:
        raise ValueError(f"too many segments ({len(chunks)}): a module holds {MAX_INSTRUMENTS} samples")
    return WavPlan(play_rate=play_rate, total_rows=total_rows, chunks=tuple(chunks),
                   first_order=tuple(first_order), order_count=order)


# ── Le module ─────────────────────────────────────────────────────────────────

def _pattern(rows: int, instrument: int = 0) -> bytes:
    """Un pattern à 2 canaux (le minimum du format) ; seule la 1re case sonne, et seulement si
    `instrument` désigne un instrument (1…) : sinon le pattern est vide."""
    packed = bytearray()
    if instrument:
        packed += bytes([0x80 | 0x01 | 0x02, _NOTE_C4, instrument])   # canal 0 : note + instrument
    else:
        packed += bytes([0x80])
    packed += bytes([0x80])                                           # canal 1 : vide
    packed += bytes([0x80]) * (2 * (rows - 1))
    return struct.pack("<IBHH", 9, 0, rows, len(packed)) + bytes(packed)


def _instrument(index: int, pcm: np.ndarray, rate: int) -> bytes:
    name = f"wav{index}".encode("ascii").ljust(22, b"\x00")
    out = bytearray()
    out += struct.pack("<I", 263) + name + bytes([0])
    out += struct.pack("<H", 1) + struct.pack("<I", 40)
    out += bytes(96) + bytes(48) + bytes(48)             # carte, enveloppes
    out += bytes(2) + bytes(6) + bytes(2) + bytes(4)     # compteurs, boucles, types, vibrato
    out += struct.pack("<H", 0) + bytes(22)              # fondu, réservé
    delta = np.diff(pcm.astype(np.int16), prepend=np.int16(0)).astype(np.int8)
    relative, fine = _tuning(rate)
    out += struct.pack("<IIIBbBBbB", pcm.size, 0, 0, 64, fine, 0, 128, relative, 0)
    out += name
    out += delta.tobytes()
    return bytes(out)


def wav_to_xm(path, rate: int = WAV_MUSIC_RATE, boundaries_ms: Iterable[float] = ()) -> bytes:
    """Le module XM qui joue ce WAV. ValueError si le WAV n'est pas convertible.

    Chaque frontière de `boundaries_ms` (arrondie à la ligne) ouvre un nouveau segment : un échantillon, une
    position d'ordre. Sans frontière la piste est un seul segment, qui joue une fois : le module dure autant
    qu'elle, un `loop` la rejoue et un `once` s'arrête avec elle."""
    data, src_rate = _read_mono(path)
    plan = plan_wav(data.size / src_rate, rate, boundaries_ms)
    pcm = np.clip(np.round(_resample(data, src_rate, plan.play_rate) * 127.0), -128, 127).astype(np.int8)

    frames_per_row = plan.play_rate * ROW_SECONDS
    samples = []
    for k, (a, b) in enumerate(plan.chunks):
        lo = min(pcm.size - 1, round(a * frames_per_row))
        hi = pcm.size if b >= plan.total_rows else min(pcm.size, round(b * frames_per_row))
        samples.append(pcm[lo:max(hi, lo + 1)])

    patterns, index_of, orders = [], {}, []

    def pattern(rows: int, instrument: int = 0) -> int:
        key = (rows, instrument)
        if key not in index_of:
            index_of[key] = len(patterns)
            patterns.append(_pattern(rows, instrument))
        return index_of[key]

    for k, (a, b) in enumerate(plan.chunks):
        rows = b - a
        first = min(ROWS_PER_PATTERN, rows)
        orders.append(pattern(first, k + 1))
        rest = rows - first
        while rest > 0:
            n = min(ROWS_PER_PATTERN, rest)
            orders.append(pattern(n))
            rest -= n
    assert len(orders) == plan.order_count

    out = bytearray()
    out += b"Extended Module: " + b"wav".ljust(20, b" ") + bytes([0x1A])
    out += b"Backstage".ljust(20, b" ") + struct.pack("<H", 0x0104)
    out += struct.pack("<I", 20 + 256)
    # longueur, restart, canaux, patterns, instruments, flags (fréquences
    # linéaires), vitesse, tempo
    out += struct.pack("<HHHHHHHH", len(orders), 0, 2, len(patterns), len(samples), 1, _SPEED, _BPM)
    out += bytes(orders).ljust(256, b"\x00")
    for p in patterns:
        out += p
    for k, chunk in enumerate(samples):
        out += _instrument(k, chunk, rate)
    return bytes(out)


def encode_music_for_build(src, dst, sample_rate: int = 0,
                           boundaries_ms: Iterable[float] = ()) -> int:
    """Écrit le module de `src` dans `dst` ; rend sa taille en octets.

    `sample_rate` est celui de `Music.sample_rate` (0 = le défaut), `boundaries_ms` les frontières des
    sections de la musique, en millisecondes (cf. `wav_to_xm`)."""
    from pathlib import Path
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = wav_to_xm(src, effective_rate(sample_rate), boundaries_ms)
    dst.write_bytes(data)
    return len(data)
