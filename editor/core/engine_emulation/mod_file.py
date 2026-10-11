"""
engine_emulation/mod_file.py — lecteur ProTracker (`.mod`).

Format Amiga classique : 31 instruments, table d'ordre de 128 positions,
patterns de 64 lignes, quatre canaux (ou 6/8 selon le tag). Il produit un
`Module` (cf. module_model.py) — comme les trois autres lecteurs, pour que le
rendu ne connaisse pas les formats.

Deux traits du MOD qui n'existent nulle part ailleurs, et que la conversion
doit rendre :

  - **la hauteur est une PÉRIODE, écrite telle quelle dans la case.** Les
    autres formats écrivent un numéro de note. La période est retrouvée dans
    la table ProTracker pour en déduire la note, et `Module.amiga_table` dit
    au rendu de refaire le chemin inverse par la MÊME table : une période
    non standard (rare, écrite à la main) est alors ramenée à la note la plus
    proche, ce qui est aussi ce que fait un tracker quand il rouvre le fichier.
  - **le panoramique est câblé** : canaux 0 et 3 à gauche, 1 et 2 à droite,
    motif répété par groupe de quatre. C'est le branchement des sorties de
    l'Amiga, pas un réglage — il n'y a pas d'effet 8xx en ProTracker standard.

Le `finetune` des instruments est lu mais **pas appliqué** : ProTracker le
range par instrument et le combine à la table de périodes, et aucun des 105
modules de la démo ne s'en sert. Il est gardé dans le modèle pour le jour où
un fichier en aura besoin.
"""

from __future__ import annotations

import struct

import numpy as np

from .module_model import (
    Cell, Module, Sample, LOOP_FORWARD, LOOP_NONE, NOTE_NONE, effective_restart,
    FX_NONE, FX_ARPEGGIO, FX_PORTA_UP, FX_PORTA_DOWN, FX_TONE_PORTA,
    FX_VIBRATO, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL, FX_TREMOLO, FX_SET_PAN,
    FX_SAMPLE_OFFSET, FX_VOLUME_SLIDE, FX_POSITION_JUMP, FX_SET_VOLUME,
    FX_PATTERN_BREAK, FX_SET_SPEED, FX_SET_TEMPO, FX_FINE_PORTA_UP,
    FX_FINE_PORTA_DOWN, FX_FINE_VOL_UP, FX_FINE_VOL_DOWN, FX_NOTE_CUT,
    FX_NOTE_DELAY, FX_PATTERN_DELAY, FX_RETRIGGER, FX_PATTERN_LOOP,
)

# Tag 4 octets (offset 1080) -> nombre de canaux. Tag inconnu -> on suppose 4
# canaux (immense majorité des .mod en circulation).
_TAG_CHANNELS = {
    b"M.K.": 4, b"M!K!": 4, b"FLT4": 4, b"4CHN": 4, b"2CHN": 2,
    b"6CHN": 6,
    b"8CHN": 8, b"FLT8": 8, b"CD81": 8, b"OKTA": 8,
    b"16CN": 16, b"32CN": 32,
}

# La table ProTracker, finetune 0 : trois octaves, de C-4 à B-6 dans la
# numérotation du modèle (60 = C-5, la note qui sonne à 8363 Hz).
PT_PERIODS = (
    856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
    428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
    214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113,
)
PT_FIRST_NOTE = 48       # PT_PERIODS[0] = 856 = C-4


def period_to_note(period: int) -> int:
    """Période ProTracker → numéro de note du modèle.

    La plus proche, et non la seule exacte : un module écrit par un autre
    tracker peut porter une période intermédiaire, et l'arrondir vaut mieux
    que de rendre la case muette.
    """
    if period <= 0:
        return NOTE_NONE
    best = min(range(len(PT_PERIODS)), key=lambda i: abs(PT_PERIODS[i] - period))
    return PT_FIRST_NOTE + best


def note_to_period(note: int) -> float:
    """L'inverse, par la même table — d'où l'aller-retour exact."""
    idx = int(note) - PT_FIRST_NOTE
    if 0 <= idx < len(PT_PERIODS):
        return float(PT_PERIODS[idx])
    # Hors table : on prolonge par octaves, ce que fait la table elle-même.
    while idx < 0:
        idx += 12
    while idx >= len(PT_PERIODS):
        idx -= 12
    octaves = (note - PT_FIRST_NOTE - idx) // 12
    return PT_PERIODS[idx] / (2.0 ** octaves)


def _translate_effect(effect: int, param: int) -> tuple[int, int]:
    """Effet ProTracker → effet normalisé du modèle."""
    if effect == 0x0:
        return (FX_ARPEGGIO, param) if param else (FX_NONE, 0)
    simple = {
        0x1: FX_PORTA_UP, 0x2: FX_PORTA_DOWN, 0x3: FX_TONE_PORTA,
        0x4: FX_VIBRATO, 0x5: FX_TONE_PORTA_VOL, 0x6: FX_VIBRATO_VOL,
        0x7: FX_TREMOLO, 0x8: FX_SET_PAN, 0x9: FX_SAMPLE_OFFSET,
        0xA: FX_VOLUME_SLIDE, 0xB: FX_POSITION_JUMP, 0xC: FX_SET_VOLUME,
    }
    if effect in simple:
        return simple[effect], param
    if effect == 0xD:
        # Le paramètre est en DÉCIMAL codé binaire : D16 saute à la ligne 16.
        return FX_PATTERN_BREAK, (param >> 4) * 10 + (param & 0x0F)
    if effect == 0xF:
        return (FX_SET_SPEED, param) if param < 32 else (FX_SET_TEMPO, param)
    if effect == 0xE:
        sub, val = param >> 4, param & 0x0F
        ext = {
            0x1: FX_FINE_PORTA_UP, 0x2: FX_FINE_PORTA_DOWN,
            0x6: FX_PATTERN_LOOP, 0x9: FX_RETRIGGER,
            0xA: FX_FINE_VOL_UP, 0xB: FX_FINE_VOL_DOWN,
            0xC: FX_NOTE_CUT, 0xD: FX_NOTE_DELAY, 0xE: FX_PATTERN_DELAY,
        }
        if sub in ext:
            return ext[sub], val
    return FX_NONE, 0


def parse_mod(data: bytes) -> Module:
    name = data[0:20].rstrip(b"\x00").decode("latin-1", "ignore")

    headers = []
    off = 20
    for _ in range(31):
        s_name      = data[off:off + 22].rstrip(b"\x00").decode("latin-1", "ignore")
        length      = struct.unpack(">H", data[off + 22:off + 24])[0] * 2
        raw_ft      = data[off + 24] & 0x0F
        finetune    = raw_ft - 16 if raw_ft >= 8 else raw_ft
        volume      = min(data[off + 25], 64)
        loop_start  = struct.unpack(">H", data[off + 26:off + 28])[0] * 2
        loop_length = struct.unpack(">H", data[off + 28:off + 30])[0] * 2
        headers.append((s_name, length, finetune, volume, loop_start, loop_length))
        off += 30

    song_length = data[off]; off += 1
    restart = data[off]; off += 1
    order = list(data[off:off + 128])[:song_length]
    off += 128

    tag = bytes(data[off:off + 4])
    num_channels = _TAG_CHANNELS.get(tag, 4)
    off += 4

    num_patterns = (max(order) + 1) if order else 0
    patterns: list = []
    for _p in range(num_patterns):
        pattern = []
        for _row in range(64):
            row = []
            for _ch in range(num_channels):
                b0, b1, b2, b3 = data[off], data[off + 1], data[off + 2], data[off + 3]
                off += 4
                period = ((b0 & 0x0F) << 8) | b1
                fx, par = _translate_effect(b2 & 0x0F, b3)
                row.append(Cell(
                    note=period_to_note(period),
                    instrument=(b0 & 0xF0) | (b2 >> 4),
                    effect=fx, param=par,
                ))
            pattern.append(row)
        patterns.append(pattern)

    samples: list = []
    for s_name, length, finetune, volume, loop_start, loop_length in headers:
        raw = data[off:off + length]
        off += length
        arr = np.frombuffer(raw, dtype=np.int8).copy() if raw else np.zeros(0, dtype=np.int8)
        if arr.size < length:
            # Fichier tronqué / sample coupé : compléter par du silence plutôt
            # que planter — un module amputé s'écoute, il ne se refuse pas.
            arr = np.pad(arr, (0, length - arr.size))
        loops = loop_length > 2
        samples.append(Sample(
            name=s_name,
            data=arr.astype(np.float32) / 128.0,
            loop_start=loop_start if loops else 0,
            loop_end=(loop_start + loop_length) if loops else 0,
            loop_kind=LOOP_FORWARD if loops else LOOP_NONE,
            volume=volume,
            finetune=finetune * 16,     # −8..7 → l'échelle 1/128 de demi-ton
        ))

    # Panoramique câblé de l'Amiga : 0 et 3 à gauche, 1 et 2 à droite.
    pan = [0 if (i % 4) in (0, 3) else 255 for i in range(num_channels)]

    return Module(
        kind="mod", name=name, num_channels=num_channels,
        amiga_table=True, linear_freq=False,
        slide_scale=1.0, effect_memory=False,
        order=order, restart=effective_restart(restart, len(order)),
        patterns=patterns, samples=samples,
        channel_pan=pan, channel_volume=[64] * num_channels,
    )
