"""
engine_emulation/s3m_file.py — lecteur ScreamTracker 3 (`.s3m`).

Le plus proche du MOD : mêmes périodes Amiga, mêmes effets pour l'essentiel.
Trois différences comptent, et ce sont elles qui justifient un lecteur à part
plutôt qu'une variante du MOD :

  - **32 canaux possibles**, chacun avec son panoramique — plus de câblage
    Amiga en dur.
  - **un taux par échantillon** (`C2SPD`, le taux de la note C-4 en ST3, notre
    note 60), au lieu du 8363 Hz commun à tout le format ProTracker.
  - **les glissés fins vivent DANS le paramètre** : `DFx` est un slide fin,
    `Dxy` un slide ordinaire. C'est le lecteur qui démêle les deux, pour que le
    rendu n'ait qu'un effet « fin » clairement nommé à jouer.

Les patterns sont EMPAQUETÉS : un octet de masque par case, et seules les
colonnes présentes sont écrites. Une ligne vide ne coûte donc qu'un octet.
"""

from __future__ import annotations

import struct

import numpy as np

from .module_model import (
    Cell, Module, Sample, LOOP_FORWARD, LOOP_NONE, NOTE_NONE, NOTE_OFF,
    FX_NONE, FX_ARPEGGIO, FX_PORTA_UP, FX_PORTA_DOWN, FX_TONE_PORTA,
    FX_VIBRATO, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL, FX_TREMOLO, FX_SET_PAN,
    FX_SAMPLE_OFFSET, FX_VOLUME_SLIDE, FX_POSITION_JUMP, FX_SET_VOLUME,
    FX_PATTERN_BREAK, FX_SET_SPEED, FX_SET_TEMPO, FX_FINE_PORTA_UP,
    FX_FINE_PORTA_DOWN, FX_FINE_VOL_UP, FX_FINE_VOL_DOWN, FX_NOTE_CUT,
    FX_NOTE_DELAY, FX_PATTERN_DELAY, FX_RETRIGGER, FX_GLOBAL_VOLUME,
    FX_GLOBAL_VOL_SLIDE, FX_PAN_SLIDE, FX_TREMOR, FX_XFINE_PORTA_UP,
    FX_XFINE_PORTA_DOWN, FX_CHANNEL_VOLUME, FX_PATTERN_LOOP,
)

# ScreamTracker numérote ses commandes A..Z ; ici A = 1, comme dans le fichier.
_A, _B, _C, _D, _E, _F, _G, _H = 1, 2, 3, 4, 5, 6, 7, 8
_I, _J, _K, _L, _M, _N, _O, _P = 9, 10, 11, 12, 13, 14, 15, 16
_Q, _R, _S, _T, _U, _V, _W, _X = 17, 18, 19, 20, 21, 22, 23, 24


def _volume_slide(param: int) -> tuple[int, int]:
    """`Dxy` → (effet normalisé, paramètre).

    ST3 range les slides FINS dans le paramètre : un quartet à 0xF signale
    « fin », et lequel des deux dit le sens. Démêlé ici une fois pour toutes.
    """
    hi, lo = param >> 4, param & 0x0F
    if lo == 0x0F and hi:
        return FX_FINE_VOL_UP, hi
    if hi == 0x0F and lo:
        return FX_FINE_VOL_DOWN, lo
    return FX_VOLUME_SLIDE, param


def _porta(param: int, up: bool) -> tuple[int, int]:
    """`Exy` / `Fxy` → glissé ordinaire, fin (Fx) ou extra-fin (Ex)."""
    hi, lo = param >> 4, param & 0x0F
    if hi == 0x0F:
        return (FX_FINE_PORTA_UP if up else FX_FINE_PORTA_DOWN), lo
    if hi == 0x0E:
        return (FX_XFINE_PORTA_UP if up else FX_XFINE_PORTA_DOWN), lo
    return (FX_PORTA_UP if up else FX_PORTA_DOWN), param


def translate_command(cmd: int, param: int, *, bcd_break: bool = True,
                      pan_full: bool = False) -> tuple[int, int]:
    """Commande lettrée (A..Z) → effet normalisé.

    Impulse Tracker a repris la table de ScreamTracker et n'en a changé que
    deux détails, passés ici en paramètres plutôt qu'en deuxième table :
    la ligne visée par « C » (décimale en ST3, hexadécimale en IT) et
    l'échelle de « X » (0..128 en ST3, 0..255 en IT).
    """
    if cmd == _A:
        return FX_SET_SPEED, param
    if cmd == _B:
        return FX_POSITION_JUMP, param
    if cmd == _C:
        if bcd_break:
            # Comme en MOD, la ligne visée est écrite en décimal codé binaire.
            return FX_PATTERN_BREAK, (param >> 4) * 10 + (param & 0x0F)
        return FX_PATTERN_BREAK, param
    if cmd == _D:
        return _volume_slide(param)
    if cmd == _E:
        return _porta(param, up=False)
    if cmd == _F:
        return _porta(param, up=True)
    if cmd == _G:
        return FX_TONE_PORTA, param
    if cmd in (_H, _U):          # U = vibrato fin — même onde, amplitude /4
        return FX_VIBRATO, param
    if cmd == _I:
        return FX_TREMOR, param
    if cmd == _J:
        return FX_ARPEGGIO, param
    if cmd == _K:
        return FX_VIBRATO_VOL, param
    if cmd == _L:
        return FX_TONE_PORTA_VOL, param
    if cmd == _M:
        return FX_CHANNEL_VOLUME, param
    if cmd == _N:
        return FX_VOLUME_SLIDE, param
    if cmd == _O:
        return FX_SAMPLE_OFFSET, param
    if cmd == _P:
        return FX_PAN_SLIDE, param
    if cmd == _Q:
        return FX_RETRIGGER, param & 0x0F
    if cmd == _R:
        return FX_TREMOLO, param
    if cmd == _S:
        sub, val = param >> 4, param & 0x0F
        if sub == 0x8:
            return FX_SET_PAN, val * 17          # 0..15 → 0..255
        if sub == 0xB:
            return FX_PATTERN_LOOP, val
        if sub == 0xC:
            return FX_NOTE_CUT, val
        if sub == 0xD:
            return FX_NOTE_DELAY, val
        if sub == 0xE:
            return FX_PATTERN_DELAY, val
        return FX_NONE, 0
    if cmd == _T:
        return FX_SET_TEMPO, param
    if cmd == _V:
        return FX_GLOBAL_VOLUME, param
    if cmd == _W:
        return FX_GLOBAL_VOL_SLIDE, param
    if cmd == _X:
        return FX_SET_PAN, param if pan_full else min(255, param * 2)
    return FX_NONE, 0


def parse_s3m(data: bytes) -> Module:
    name = data[0:28].rstrip(b"\x00").decode("latin-1", "ignore")
    ord_num, ins_num, pat_num = struct.unpack_from("<HHH", data, 0x20)
    _flags, _cwtv, ffv = struct.unpack_from("<HHH", data, 0x26)
    global_vol = min(64, data[0x30])
    speed = data[0x31] or 6
    tempo = data[0x32] or 125
    master = data[0x33]
    stereo = bool(master & 0x80)
    default_pan_present = data[0x35] == 252
    chan_settings = list(data[0x40:0x60])

    off = 0x60
    # La table BRUTE, marqueurs compris (cf. module_model.ORDER_SKIP) : même
    # convention qu'IT dans le format, non vérifiée sous `mmutil` pour le S3M.
    order = list(data[off:off + ord_num])
    off += ord_num
    ins_ptr = list(struct.unpack_from(f"<{ins_num}H", data, off)); off += ins_num * 2
    pat_ptr = list(struct.unpack_from(f"<{pat_num}H", data, off)); off += pat_num * 2

    pan_table = list(data[off:off + 32]) if default_pan_present else []

    # Les canaux ACTIFS, dans l'ordre : un canal désactivé (0xFF) n'occupe pas
    # de colonne dans les patterns, mais son rang y reste — d'où une table de
    # correspondance plutôt qu'un simple compte.
    active = [i for i, cs in enumerate(chan_settings) if cs < 16]
    num_channels = max(1, len(active))
    col_of = {c: i for i, c in enumerate(active)}

    pan = []
    for c in active:
        if default_pan_present and c < len(pan_table) and (pan_table[c] & 0x20):
            pan.append(min(255, (pan_table[c] & 0x0F) * 17))
        elif not stereo:
            pan.append(128)
        else:
            pan.append(48 if chan_settings[c] < 8 else 207)

    # ── Instruments ───────────────────────────────────────────────
    samples: list = []
    for p in ins_ptr:
        base = p * 16
        if base <= 0 or base + 0x50 > len(data) or data[base] != 1:
            samples.append(Sample())
            continue
        mem_hi = data[base + 0x0D]
        mem_lo = struct.unpack_from("<H", data, base + 0x0E)[0]
        sdata = ((mem_hi << 16) | mem_lo) * 16
        length, loop_beg, loop_end = struct.unpack_from("<III", data, base + 0x10)
        volume = min(64, data[base + 0x1C])
        pack = data[base + 0x1E]
        sflags = data[base + 0x1F]
        c2spd = struct.unpack_from("<I", data, base + 0x20)[0] or 8363
        s_name = data[base + 0x30:base + 0x4C].rstrip(b"\x00").decode("latin-1", "ignore")

        wide = bool(sflags & 0x04)
        raw = data[sdata:sdata + length * (2 if wide else 1)]
        if pack:
            # ADPCM : ST3 ne l'a jamais écrit, et personne ne le lit. Un
            # échantillon vide vaut mieux qu'un bruit inventé.
            arr = np.zeros(0, dtype=np.float32)
        elif wide:
            a = np.frombuffer(raw, dtype="<u2").astype(np.float32)
            arr = (a - 32768.0) / 32768.0 if ffv != 1 else \
                np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        else:
            a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            arr = (a - 128.0) / 128.0 if ffv != 1 else \
                np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 128.0

        loops = bool(sflags & 0x01) and loop_end > loop_beg
        samples.append(Sample(
            name=s_name, data=arr,
            loop_start=loop_beg if loops else 0,
            loop_end=loop_end if loops else 0,
            loop_kind=LOOP_FORWARD if loops else LOOP_NONE,
            volume=volume, c5_speed=c2spd,
        ))

    # ── Patterns ──────────────────────────────────────────────────
    patterns: list = []
    for p in pat_ptr:
        base = p * 16
        rows = [[Cell() for _ in range(num_channels)] for _ in range(64)]
        if base <= 0 or base + 2 > len(data):
            patterns.append(rows)
            continue
        end = base + 2 + struct.unpack_from("<H", data, base)[0]
        i = base + 2
        row = 0
        while i < min(end, len(data)) and row < 64:
            b = data[i]; i += 1
            if b == 0:
                row += 1
                continue
            chan = b & 31
            note = inst = vol = cmd = par = None
            if b & 32:
                note, inst = data[i], data[i + 1]; i += 2
            if b & 64:
                vol = data[i]; i += 1
            if b & 128:
                cmd, par = data[i], data[i + 1]; i += 2
            col = col_of.get(chan)
            if col is None:
                continue
            cell = rows[row][col]
            if note is not None:
                if note == 255:
                    cell.note = NOTE_NONE
                elif note == 254:
                    cell.note = NOTE_OFF
                else:
                    # ST3 : quartet haut = octave, quartet bas = demi-ton, et
                    # C-4 (0x40) est la note qui sonne au C2SPD — notre 60.
                    cell.note = (note >> 4) * 12 + (note & 0x0F) + 12
                cell.instrument = inst
            if vol is not None and vol <= 64:
                cell.effect, cell.param = FX_SET_VOLUME, vol
            if cmd:
                fx, pr = translate_command(cmd, par or 0)
                if fx != FX_NONE:
                    cell.effect, cell.param = fx, pr
        patterns.append(rows)

    return Module(
        kind="s3m", name=name, num_channels=num_channels,
        speed=speed, bpm=tempo, global_volume=global_vol,
        linear_freq=False, amiga_table=False,
        # ST3 compte ses périodes QUATRE FOIS plus fin que ProTracker (1712
        # pour le C-4 là où l'Amiga écrit 428) : un point de paramètre y
        # déplace donc quatre fois moins la hauteur.
        slide_scale=0.25, effect_memory=True,
        order=order, patterns=patterns, samples=samples,
        channel_pan=pan, channel_volume=[64] * num_channels,
    )
