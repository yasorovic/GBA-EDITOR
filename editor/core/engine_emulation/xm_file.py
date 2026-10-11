"""
engine_emulation/xm_file.py — lecteur FastTracker II (`.xm`).

C'est le format que livre le plus souvent un compositeur, et il apporte trois
choses que ni le MOD ni le S3M n'ont :

  - **des INSTRUMENTS** : une note ne désigne plus un échantillon mais un
    instrument, qui choisit l'échantillon selon la note jouée et porte ses
    ENVELOPPES de volume et de panoramique. C'est ce qui permet un piano dont
    les graves et les aigus sont deux enregistrements.
  - **une colonne de VOLUME** à côté de la colonne d'effet : deux commandes par
    case au lieu d'une.
  - **des fréquences LINÉAIRES** (au choix du morceau) : un glissé y avance
    d'un pas constant en demi-tons, là où une période Amiga accélère vers les
    aigus. Le drapeau vit dans l'en-tête, et le modèle le porte tel quel.

Deux pièges du format, que le lecteur doit connaître :

  - les données d'échantillon sont **encodées en delta** — chaque octet est un
    écart au précédent, pas une valeur ;
  - les tailles d'en-tête sont **déclarées dans le fichier** et servent de pas
    de déplacement. Les recalculer ferait dérailler la lecture sur tout fichier
    écrit par un tracker un peu différent.
"""

from __future__ import annotations

import struct

import numpy as np

from .module_model import (
    Cell, Envelope, Instrument, Module, Sample, effective_restart,
    LOOP_FORWARD, LOOP_NONE, LOOP_PINGPONG, NOTE_NONE, NOTE_OFF,
    FX_NONE, FX_ARPEGGIO, FX_PORTA_UP, FX_PORTA_DOWN, FX_TONE_PORTA,
    FX_VIBRATO, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL, FX_TREMOLO, FX_SET_PAN,
    FX_SAMPLE_OFFSET, FX_VOLUME_SLIDE, FX_POSITION_JUMP, FX_SET_VOLUME,
    FX_PATTERN_BREAK, FX_SET_SPEED, FX_SET_TEMPO, FX_FINE_PORTA_UP,
    FX_FINE_PORTA_DOWN, FX_FINE_VOL_UP, FX_FINE_VOL_DOWN, FX_NOTE_CUT,
    FX_NOTE_DELAY, FX_PATTERN_DELAY, FX_RETRIGGER, FX_GLOBAL_VOLUME,
    FX_GLOBAL_VOL_SLIDE, FX_PAN_SLIDE, FX_TREMOR, FX_XFINE_PORTA_UP,
    FX_XFINE_PORTA_DOWN, FX_KEY_OFF, FX_PATTERN_LOOP,
    VOL_NONE, VOL_SET, VOL_SLIDE_UP, VOL_SLIDE_DOWN, VOL_FINE_UP,
    VOL_FINE_DOWN, VOL_VIBRATO, VOL_PAN, VOL_TONE_PORTA,
)

# La note 1 du XM est un C-0, et sa note 49 (C-4) sonne à 8363 Hz — le C-5 du
# modèle. D'où le décalage, appliqué une fois à la lecture.
_NOTE_OFFSET = 11
_XM_KEY_OFF = 97


def _translate(effect: int, param: int) -> tuple[int, int]:
    """Effet XM → effet normalisé. Les seize premiers sont ceux du MOD."""
    if effect == 0x0:
        return (FX_ARPEGGIO, param) if param else (FX_NONE, 0)
    simple = {
        0x1: FX_PORTA_UP, 0x2: FX_PORTA_DOWN, 0x3: FX_TONE_PORTA,
        0x4: FX_VIBRATO, 0x5: FX_TONE_PORTA_VOL, 0x6: FX_VIBRATO_VOL,
        0x7: FX_TREMOLO, 0x8: FX_SET_PAN, 0x9: FX_SAMPLE_OFFSET,
        0xA: FX_VOLUME_SLIDE, 0xB: FX_POSITION_JUMP, 0xC: FX_SET_VOLUME,
        0x10: FX_GLOBAL_VOLUME, 0x11: FX_GLOBAL_VOL_SLIDE,
        0x14: FX_KEY_OFF, 0x19: FX_PAN_SLIDE, 0x1D: FX_TREMOR,
    }
    if effect in simple:
        return simple[effect], param
    if effect == 0xD:
        return FX_PATTERN_BREAK, (param >> 4) * 10 + (param & 0x0F)
    if effect == 0xF:
        return (FX_SET_SPEED, param) if param < 32 else (FX_SET_TEMPO, param)
    if effect == 0x1B:                       # R — retrigger avec slide
        return FX_RETRIGGER, param & 0x0F
    if effect == 0x21:                       # X — glissés extra-fins
        sub, val = param >> 4, param & 0x0F
        if sub == 1:
            return FX_XFINE_PORTA_UP, val
        if sub == 2:
            return FX_XFINE_PORTA_DOWN, val
        return FX_NONE, 0
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


def _translate_volume(v: int) -> tuple[int, int]:
    """La colonne de volume du XM : un octet, huit commandes."""
    if v == 0:
        return VOL_NONE, 0
    if 0x10 <= v <= 0x50:
        return VOL_SET, v - 0x10
    if 0x60 <= v <= 0x6F:
        return VOL_SLIDE_DOWN, v & 0x0F
    if 0x70 <= v <= 0x7F:
        return VOL_SLIDE_UP, v & 0x0F
    if 0x80 <= v <= 0x8F:
        return VOL_FINE_DOWN, v & 0x0F
    if 0x90 <= v <= 0x9F:
        return VOL_FINE_UP, v & 0x0F
    if 0xB0 <= v <= 0xBF:
        return VOL_VIBRATO, v & 0x0F
    if 0xC0 <= v <= 0xCF:
        return VOL_PAN, (v & 0x0F) * 4
    if 0xF0 <= v <= 0xFF:
        return VOL_TONE_PORTA, v & 0x0F
    return VOL_NONE, 0


def _envelope(raw: bytes, count: int, sustain: int,
              loop_start: int, loop_end: int, typ: int) -> Envelope:
    """Les 12 points d'une enveloppe XM (x, y en mots), et ses trois drapeaux."""
    if not (typ & 0x01) or count < 2:
        return Envelope()
    pts = []
    for i in range(min(count, 12)):
        x, y = struct.unpack_from("<HH", raw, i * 4)
        pts.append((int(x), int(y)))
    return Envelope(
        points=pts,
        sustain=sustain if (typ & 0x02) and sustain < len(pts) else -1,
        loop_start=loop_start if (typ & 0x04) and loop_start < len(pts) else -1,
        loop_end=loop_end if (typ & 0x04) and loop_end < len(pts) else -1,
    )


def _decode_delta(raw: bytes, wide: bool) -> np.ndarray:
    """Les échantillons XM sont écrits en DELTA : on intègre pour les relire."""
    if not raw:
        return np.zeros(0, dtype=np.float32)
    if wide:
        d = np.frombuffer(raw[:len(raw) // 2 * 2], dtype="<i2").astype(np.int32)
        acc = np.cumsum(d).astype(np.int32)
        acc = ((acc + 32768) & 0xFFFF) - 32768
        return acc.astype(np.float32) / 32768.0
    d = np.frombuffer(raw, dtype=np.int8).astype(np.int32)
    acc = np.cumsum(d).astype(np.int32)
    acc = ((acc + 128) & 0xFF) - 128
    return acc.astype(np.float32) / 128.0


def parse_xm(data: bytes) -> Module:
    name = data[17:37].rstrip(b" \x00").decode("latin-1", "ignore")
    header_size = struct.unpack_from("<I", data, 0x3C)[0]
    (song_len, restart, n_channels, n_patterns, n_instruments,
     flags, speed, bpm) = struct.unpack_from("<HHHHHHHH", data, 0x40)
    n_channels = max(1, min(64, n_channels))
    order = list(data[0x50:0x50 + song_len])

    off = 0x3C + header_size

    # ── Patterns ──────────────────────────────────────────────────
    patterns: list = []
    for _p in range(n_patterns):
        if off + 9 > len(data):
            break
        pat_header, _packing, rows, packed = struct.unpack_from("<IBHH", data, off)
        rows = max(1, rows)
        body = off + pat_header
        off = body + packed
        grid = [[Cell() for _ in range(n_channels)] for _ in range(rows)]
        if packed == 0:
            patterns.append(grid)
            continue
        i = body
        row = col = 0
        while i < min(body + packed, len(data)) and row < rows:
            b = data[i]; i += 1
            note = inst = vol = fx = par = 0
            if b & 0x80:
                if b & 0x01: note = data[i]; i += 1
                if b & 0x02: inst = data[i]; i += 1
                if b & 0x04: vol = data[i]; i += 1
                if b & 0x08: fx = data[i]; i += 1
                if b & 0x10: par = data[i]; i += 1
            else:
                note = b
                inst, vol, fx, par = data[i], data[i + 1], data[i + 2], data[i + 3]
                i += 4
            if col < n_channels:
                cell = grid[row][col]
                if note == _XM_KEY_OFF:
                    cell.note = NOTE_OFF
                elif note:
                    cell.note = note + _NOTE_OFFSET
                cell.instrument = inst
                cell.vol_fx, cell.vol_param = _translate_volume(vol)
                cell.effect, cell.param = _translate(fx, par)
            col += 1
            if col >= n_channels:
                col = 0
                row += 1
        patterns.append(grid)

    # ── Instruments et échantillons ───────────────────────────────
    samples: list = []
    instruments: list = []
    for _i in range(n_instruments):
        if off + 4 > len(data):
            break
        inst_size = struct.unpack_from("<I", data, off)[0] or 29
        i_name = data[off + 4:off + 26].rstrip(b" \x00").decode("latin-1", "ignore")
        n_samples = struct.unpack_from("<H", data, off + 27)[0] if off + 29 <= len(data) else 0
        inst = Instrument(name=i_name)

        if n_samples:
            samp_header_size = struct.unpack_from("<I", data, off + 29)[0] or 40
            base = off + 33
            note_map = list(data[base:base + 96])
            vol_pts = data[base + 96:base + 144]
            pan_pts = data[base + 144:base + 192]
            (n_vol, n_pan, vol_sus, vol_ls, vol_le,
             pan_sus, pan_ls, pan_le, vol_type, pan_type) = data[base + 192:base + 202]
            fadeout = struct.unpack_from("<H", data, base + 214)[0]
            inst.vol_env = _envelope(vol_pts, n_vol, vol_sus, vol_ls, vol_le, vol_type)
            inst.pan_env = _envelope(pan_pts, n_pan, pan_sus, pan_ls, pan_le, pan_type)
            # Le fadeout du XM se retire de 65536 par tick, et l'échelle du
            # modèle est déjà celle-là : rien à convertir.
            inst.fadeout = fadeout * 2

            # Les en-têtes d'échantillon, puis TOUTES leurs données à la suite.
            hdr = off + inst_size
            heads = []
            for _s in range(n_samples):
                if hdr + 40 > len(data):
                    break
                length, loop_start, loop_len = struct.unpack_from("<III", data, hdr)
                volume = data[hdr + 12]
                finetune = struct.unpack_from("<b", data, hdr + 13)[0]
                s_type = data[hdr + 14]
                panning = data[hdr + 15]
                rel_note = struct.unpack_from("<b", data, hdr + 16)[0]
                s_name = data[hdr + 18:hdr + 40].rstrip(b" \x00").decode("latin-1", "ignore")
                heads.append((length, loop_start, loop_len, volume, finetune,
                              s_type, panning, rel_note, s_name))
                hdr += samp_header_size

            first_index = len(samples)
            pos = hdr
            for (length, loop_start, loop_len, volume, finetune,
                 s_type, panning, rel_note, s_name) in heads:
                wide = bool(s_type & 0x10)
                raw = data[pos:pos + length]
                pos += length
                arr = _decode_delta(raw, wide)
                loop_bits = s_type & 0x03
                if wide:
                    loop_start //= 2
                    loop_len //= 2
                loops = loop_bits and loop_len > 0
                samples.append(Sample(
                    name=s_name, data=arr,
                    loop_start=loop_start if loops else 0,
                    loop_end=(loop_start + loop_len) if loops else 0,
                    loop_kind=(LOOP_PINGPONG if loop_bits == 2 else LOOP_FORWARD)
                    if loops else LOOP_NONE,
                    volume=min(64, volume),
                    default_pan=panning,
                    relative_note=rel_note,
                    finetune=finetune,
                ))
            off = pos

            for n in range(min(96, len(note_map))):
                idx = note_map[n]
                target = first_index + idx if idx < n_samples else -1
                # Le décalage de note du modèle s'applique aussi à la carte.
                if 0 <= n + _NOTE_OFFSET + 1 < 120:
                    inst.sample_of_note[n + _NOTE_OFFSET + 1] = target
        else:
            off += inst_size
        instruments.append(inst)

    return Module(
        kind="xm", name=name, num_channels=n_channels,
        speed=max(1, speed), bpm=max(32, bpm),
        linear_freq=bool(flags & 0x01), amiga_table=False,
        slide_scale=4.0, effect_memory=True,
        order=order, restart=effective_restart(restart, len(order)),
        patterns=patterns, samples=samples, instruments=instruments,
        channel_pan=[128] * n_channels, channel_volume=[64] * n_channels,
    )
