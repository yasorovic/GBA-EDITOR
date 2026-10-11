"""
engine_emulation/it_file.py — lecteur Impulse Tracker (`.it`).

Le format le plus riche des quatre, et celui qui demande le plus de travail au
lecteur pour deux raisons :

  - **les patterns sont empaquetés AVEC MÉMOIRE.** Un masque dit quelles
    colonnes sont écrites, et un second jeu de bits dit « reprends ce que ce
    canal avait la dernière fois ». Lire une case oblige donc à tenir l'état
    du canal, ligne après ligne — on ne peut pas sauter dans un pattern.
  - **les échantillons sont souvent COMPRESSÉS** (IT214/IT215), en delta sur
    des mots de largeur variable. C'est le format par défaut d'Impulse Tracker
    et d'OpenMPT : sans décompression, la moitié des fichiers livrés par un
    compositeur seraient muets.

Bonne nouvelle en revanche : la numérotation de notes du modèle EST celle d'IT
(60 = C-5), et sa table d'effets est celle de ScreamTracker à deux détails
près — d'où `s3m_file.translate_command`, partagée plutôt que recopiée.

Ce qui n'est PAS rendu, et qui ne l'est pas non plus par maxmod sur GBA : les
filtres résonants, les échantillons stéréo, et les NNA (New Note Actions)
au-delà de la coupure — une nouvelle note reprend son canal.
"""

from __future__ import annotations

import struct

import numpy as np

from .module_model import (
    Cell, Envelope, Instrument, Module, Sample,
    LOOP_FORWARD, LOOP_NONE, LOOP_PINGPONG, NOTE_NONE, NOTE_OFF,
    FX_NONE, FX_SET_VOLUME,
    VOL_NONE, VOL_SET, VOL_SLIDE_UP, VOL_SLIDE_DOWN, VOL_FINE_UP,
    VOL_FINE_DOWN, VOL_VIBRATO, VOL_PAN, VOL_TONE_PORTA,
)
from .s3m_file import translate_command


class _Bits:
    """Lecteur de bits, poids faibles d'abord — l'ordre d'IT."""

    def __init__(self, buf: bytes):
        self._buf = buf
        self._pos = 0
        self._acc = 0
        self._have = 0

    def read(self, n: int) -> int | None:
        while self._have < n:
            if self._pos >= len(self._buf):
                return None
            self._acc |= self._buf[self._pos] << self._have
            self._pos += 1
            self._have += 8
        v = self._acc & ((1 << n) - 1)
        self._acc >>= n
        self._have -= n
        return v


def _sign_extend(v: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (v ^ sign) - sign


def _decompress(data: bytes, offset: int, count: int,
                wide: bool, it215: bool) -> tuple[np.ndarray, int]:
    """Décompresse `count` échantillons IT214/IT215 à partir de `offset`.

    L'algorithme d'origine : des blocs de 32 Kio de sortie, chacun encodé en
    largeur de mot VARIABLE. Une valeur particulière ne code pas un échantillon
    mais un changement de largeur — c'est ce qui permet à un passage calme de
    coûter trois bits par échantillon.
    """
    out = np.zeros(count, dtype=np.int32)
    pos = offset
    written = 0
    max_width = 17 if wide else 9
    block_max = 0x4000 if wide else 0x8000
    bits_per = 16 if wide else 8
    mask = (1 << bits_per) - 1

    while written < count and pos + 2 <= len(data):
        block = min(block_max, count - written)
        comp_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        bits = _Bits(data[pos:pos + comp_len])
        pos += comp_len
        width = max_width
        d1 = d2 = 0
        n = 0
        while n < block:
            v = bits.read(width)
            if v is None:
                break
            change = False
            if width < 7:
                if v == (1 << (width - 1)):
                    nw = bits.read(4 if wide else 3)
                    if nw is None:
                        break
                    nw += 1
                    width = nw if nw < width else nw + 1
                    change = True
            elif width < max_width:
                border = ((0xFFFF if wide else 0xFF) >> (max_width - width)) - (8 if wide else 4)
                if border < v <= border + (16 if wide else 8):
                    v -= border
                    width = v if v < width else v + 1
                    change = True
            elif width == max_width:
                top = 0x10000 if wide else 0x100
                if v & top:
                    width = (v + 1) & 0xFF
                    change = True
            else:
                break
            if change:
                # Une largeur hors bornes ne peut venir que d'un fichier
                # corrompu — et c'est une VRAIE porte d'entrée, puisque le
                # fichier arrive de l'extérieur. On abandonne le bloc au lieu
                # de laisser un décalage négatif faire tomber l'éditeur.
                if not (1 <= width <= max_width):
                    break
                continue

            delta = _sign_extend(v, width) if width < (16 if wide else 8) else _sign_extend(
                v, 16 if wide else 8)
            # Les deux accumulateurs sont des REGISTRES : ils débordent et
            # repartent, ils ne grandissent pas. Sans ce repli, une onde qui
            # descend sous −128 remonte à +156 au lieu de revenir à −100.
            d1 = _sign_extend((d1 + delta) & mask, bits_per)
            d2 = _sign_extend((d2 + d1) & mask, bits_per)
            out[written + n] = d2 if it215 else d1
            n += 1
        written += block

    scale = 32768.0 if wide else 128.0
    return (out.astype(np.float32) / scale), pos


def _envelope(raw: bytes, base: int) -> tuple[Envelope, int]:
    """Une enveloppe IT : 82 octets — drapeaux, points, boucles.

    Les valeurs de volume y vont de 0 à 64, celles de panoramique de −32 à
    +32 : les secondes sont décalées pour que le rendu n'ait qu'une convention
    (0..64, centre à 32), la même que le XM.
    """
    flags = raw[base]
    num = raw[base + 1]
    loop_start, loop_end = raw[base + 2], raw[base + 3]
    sus_start, sus_end = raw[base + 4], raw[base + 5]
    pts = []
    for i in range(min(num, 25)):
        y = struct.unpack_from("<b", raw, base + 6 + i * 3)[0]
        x = struct.unpack_from("<H", raw, base + 7 + i * 3)[0]
        pts.append((int(x), int(y)))
    env = Envelope()
    if (flags & 0x01) and len(pts) >= 2:
        env.points = pts
        if flags & 0x02:
            env.loop_start, env.loop_end = loop_start, loop_end
        if flags & 0x04:
            env.sustain = sus_start
        # Un maintien qui n'est pas un point valide ne maintient rien.
        if env.sustain >= len(pts):
            env.sustain = -1
        if env.loop_end >= len(pts):
            env.loop_start = env.loop_end = -1
        _ = sus_end
    return env, base + 82


def _translate_volume(v: int) -> tuple[int, int]:
    """La colonne de volume d'IT : une seule plage 0..212, dix commandes."""
    if v <= 64:
        return VOL_SET, v
    if 65 <= v <= 74:
        return VOL_FINE_UP, v - 65
    if 75 <= v <= 84:
        return VOL_FINE_DOWN, v - 75
    if 85 <= v <= 94:
        return VOL_SLIDE_UP, v - 85
    if 95 <= v <= 104:
        return VOL_SLIDE_DOWN, v - 95
    if 128 <= v <= 192:
        return VOL_PAN, int((v - 128) * 255 / 64)
    if 193 <= v <= 202:
        return VOL_TONE_PORTA, v - 193
    if 203 <= v <= 212:
        return VOL_VIBRATO, v - 203
    return VOL_NONE, 0


def parse_it(data: bytes) -> Module:
    name = data[4:30].rstrip(b"\x00").decode("latin-1", "ignore")
    ord_num, ins_num, smp_num, pat_num = struct.unpack_from("<HHHH", data, 0x20)
    _cwtv, cmwt, flags, special = struct.unpack_from("<HHHH", data, 0x28)
    global_vol = min(128, data[0x30])
    _mix_vol = data[0x31]
    speed = data[0x32] or 6
    tempo = data[0x33] or 125
    chan_pan = list(data[0x40:0x80])
    chan_vol = list(data[0x80:0xC0])

    off = 0xC0
    # La table BRUTE, marqueurs compris : c'est l'index que la ROM rendra
    # (cf. module_model.ORDER_SKIP). L'IT n'a pas de position de restart.
    order = list(data[off:off + ord_num])
    off += ord_num
    ins_off = list(struct.unpack_from(f"<{ins_num}I", data, off)); off += ins_num * 4
    smp_off = list(struct.unpack_from(f"<{smp_num}I", data, off)); off += smp_num * 4
    pat_off = list(struct.unpack_from(f"<{pat_num}I", data, off)); off += pat_num * 4

    linear = bool(flags & 0x08)
    use_instruments = bool(flags & 0x04)
    it215 = cmwt >= 0x215

    # Les canaux réellement employés : IT en déclare 64, un morceau en emploie
    # rarement plus de 16, et un canal vide coûterait un mixage pour rien.
    used = 0
    for p in pat_off:
        if 0 < p < len(data):
            used = max(used, 0)
    num_channels = 64

    # ── Échantillons ──────────────────────────────────────────────
    samples: list = []
    for p in smp_off:
        if not (0 < p and p + 0x50 <= len(data)) or data[p:p + 4] != b"IMPS":
            samples.append(Sample())
            continue
        gvl = data[p + 0x11]
        sflags = data[p + 0x12]
        vol = data[p + 0x13]
        s_name = data[p + 0x14:p + 0x2E].rstrip(b"\x00").decode("latin-1", "ignore")
        cvt = data[p + 0x2E]
        dfp = data[p + 0x2F]
        length, loop_beg, loop_end, c5 = struct.unpack_from("<IIII", data, p + 0x30)
        sample_ptr = struct.unpack_from("<I", data, p + 0x48)[0]

        wide = bool(sflags & 0x02)
        has_data = bool(sflags & 0x01) and length and sample_ptr
        if not has_data:
            samples.append(Sample(name=s_name))
            continue
        if sflags & 0x08:
            arr, _end = _decompress(data, sample_ptr, length, wide, it215)
        else:
            n_bytes = length * (2 if wide else 1)
            raw = data[sample_ptr:sample_ptr + n_bytes]
            signed = bool(cvt & 0x01)
            if wide:
                a = np.frombuffer(raw[:len(raw) // 2 * 2],
                                  dtype="<i2" if signed else "<u2").astype(np.float32)
                arr = a / 32768.0 if signed else (a - 32768.0) / 32768.0
            else:
                a = np.frombuffer(raw, dtype=np.int8 if signed else np.uint8).astype(np.float32)
                arr = a / 128.0 if signed else (a - 128.0) / 128.0

        loops = bool(sflags & 0x10) and loop_end > loop_beg
        ping = bool(sflags & 0x40)
        samples.append(Sample(
            name=s_name, data=arr,
            loop_start=loop_beg if loops else 0,
            loop_end=loop_end if loops else 0,
            loop_kind=(LOOP_PINGPONG if ping else LOOP_FORWARD) if loops else LOOP_NONE,
            volume=min(64, vol),
            global_volume=min(64, gvl),
            default_pan=(dfp & 0x7F) * 2 if (dfp & 0x80) else -1,
            c5_speed=c5 or 8363,
        ))

    # ── Instruments ───────────────────────────────────────────────
    instruments: list = []
    if use_instruments:
        for p in ins_off:
            if not (0 < p and p + 0x230 <= len(data)) or data[p:p + 4] != b"IMPI":
                instruments.append(Instrument())
                continue
            fadeout = struct.unpack_from("<H", data, p + 0x14)[0]
            gbv = data[p + 0x18]
            i_name = data[p + 0x20:p + 0x3A].rstrip(b"\x00").decode("latin-1", "ignore")
            inst = Instrument(name=i_name)
            # IT retire `fadeout × 2` d'un volume sur 1024 à chaque tick ;
            # l'échelle du modèle est sur 65536, d'où le facteur.
            inst.fadeout = fadeout * 128
            inst.global_volume = max(1, gbv)
            for n in range(120):
                smp = data[p + 0x40 + n * 2 + 1]
                inst.sample_of_note[n] = smp - 1 if 0 < smp <= len(samples) else -1
            vol_env, nxt = _envelope(data, p + 0x130)
            pan_env, _ = _envelope(data, nxt)
            # L'enveloppe de panoramique d'IT va de −32 à +32 : on la ramène
            # sur la même graduation que le volume (0..64, centre 32).
            pan_env.points = [(x, y + 32) for x, y in pan_env.points]
            inst.vol_env, inst.pan_env = vol_env, pan_env
            instruments.append(inst)

    # ── Patterns ──────────────────────────────────────────────────
    patterns: list = []
    for p in pat_off:
        if not (0 < p and p + 8 <= len(data)):
            patterns.append([[Cell() for _ in range(num_channels)] for _ in range(64)])
            continue
        packed, rows = struct.unpack_from("<HH", data, p)
        rows = max(1, rows)
        grid = [[Cell() for _ in range(num_channels)] for _ in range(rows)]
        i = p + 8
        end = i + packed
        row = 0
        mask = [0] * num_channels
        last_note = [0] * num_channels
        last_inst = [0] * num_channels
        last_vol = [0] * num_channels
        last_cmd = [0] * num_channels
        last_par = [0] * num_channels
        while i < min(end, len(data)) and row < rows:
            cv = data[i]; i += 1
            if cv == 0:
                row += 1
                continue
            chan = (cv - 1) & 63
            if cv & 0x80:
                mask[chan] = data[i]; i += 1
            m = mask[chan]
            note = inst = vol = cmd = par = None
            if m & 0x01:
                last_note[chan] = data[i]; i += 1
                note = last_note[chan]
            if m & 0x02:
                last_inst[chan] = data[i]; i += 1
                inst = last_inst[chan]
            if m & 0x04:
                last_vol[chan] = data[i]; i += 1
                vol = last_vol[chan]
            if m & 0x08:
                last_cmd[chan], last_par[chan] = data[i], data[i + 1]; i += 2
                cmd, par = last_cmd[chan], last_par[chan]
            if m & 0x10:
                note = last_note[chan]
            if m & 0x20:
                inst = last_inst[chan]
            if m & 0x40:
                vol = last_vol[chan]
            if m & 0x80:
                cmd, par = last_cmd[chan], last_par[chan]

            cell = grid[row][chan]
            if note is not None:
                if note >= 254:
                    cell.note = NOTE_OFF
                elif note < 120:
                    cell.note = note
                else:
                    cell.note = NOTE_NONE
            if inst is not None:
                cell.instrument = inst
            if vol is not None:
                cell.vol_fx, cell.vol_param = _translate_volume(vol)
            if cmd:
                fx, pr = translate_command(cmd, par or 0, bcd_break=False, pan_full=True)
                if fx != FX_NONE:
                    cell.effect, cell.param = fx, pr
        patterns.append(grid)

    # Les canaux au-delà du dernier employé ne servent à rien : les couper ici
    # épargne 48 mixages par tick sur un morceau qui n'en utilise que 16.
    last_used = 0
    for grid in patterns:
        for r in grid:
            for c in range(num_channels - 1, last_used - 1, -1):
                cell = r[c]
                if cell.note or cell.instrument or cell.effect or cell.vol_fx:
                    last_used = max(last_used, c + 1)
                    break
    num_channels = max(1, last_used)
    patterns = [[row[:num_channels] for row in grid] for grid in patterns]

    pan = []
    vols = []
    for c in range(num_channels):
        raw_pan = chan_pan[c] if c < len(chan_pan) else 32
        surround = raw_pan == 100
        base = 32 if (surround or raw_pan > 64) else raw_pan
        pan.append(min(255, int(base * 255 / 64)))
        vols.append(min(64, chan_vol[c] if c < len(chan_vol) else 64))

    _ = special, used
    return Module(
        kind="it", name=name, num_channels=num_channels,
        speed=speed, bpm=tempo, global_volume=min(64, global_vol // 2),
        linear_freq=linear, amiga_table=False,
        slide_scale=4.0 if linear else 0.25, effect_memory=True,
        order=order, patterns=patterns, samples=samples,
        instruments=instruments,
        channel_pan=pan, channel_volume=vols,
    )
