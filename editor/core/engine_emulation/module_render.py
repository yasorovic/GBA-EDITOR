"""
engine_emulation/module_render.py — rejoue un `Module` en PCM, façon mixeur
logiciel maxmod GBA.

Il s'appelait `mod_render.py` tant qu'il ne savait jouer que du ProTracker.
Depuis la v0.8.8 il joue les quatre formats que maxmod accepte, parce qu'ils
arrivent tous ici sous la même forme (cf. module_model.py) : un lecteur audio,
pas quatre — sinon le vibrato existerait en quatre versions, et trois d'entre
elles seraient fausses.

Objectif inchangé : un aperçu qui SONNE comme le rendu en jeu, pas un lecteur
de bureau haute fidélité. Deux choix le pilotent :

  - taux de mixage réduit (GBA_MIX_RATE) au lieu de 44,1 kHz ;
  - lecture des échantillons au plus proche voisin, sans interpolation — le
    mixeur logiciel du GBA n'interpole pas non plus.

Ce qui est rendu : notes, instruments, enveloppes de volume et de panoramique,
fadeout, arpège, portamentos (dont fins et extra-fins), vibrato, trémolo,
slides de volume et de panoramique, offset d'échantillon, retrigger, tremor,
coupure et retard de note, volume global, sauts et ruptures de pattern, boucle
et retard de pattern, colonne de volume, et le bouclage aller-retour.

Ce qui ne l'est pas, et qui ne l'est pas non plus sur la console : les filtres
résonants d'IT, les échantillons stéréo, et les NNA au-delà de la coupure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .module_model import (
    Envelope, Instrument, Module, Sample, ORDER_END,
    LOOP_NONE, LOOP_PINGPONG, NOTE_NONE, NOTE_OFF, NOTE_C5,
    PERIOD_C5, AMIGA_C5_RATE,
    FX_NONE, FX_ARPEGGIO, FX_PORTA_UP, FX_PORTA_DOWN, FX_TONE_PORTA,
    FX_VIBRATO, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL, FX_TREMOLO, FX_SET_PAN,
    FX_SAMPLE_OFFSET, FX_VOLUME_SLIDE, FX_POSITION_JUMP, FX_SET_VOLUME,
    FX_PATTERN_BREAK, FX_SET_SPEED, FX_SET_TEMPO, FX_FINE_PORTA_UP,
    FX_FINE_PORTA_DOWN, FX_FINE_VOL_UP, FX_FINE_VOL_DOWN, FX_NOTE_CUT,
    FX_NOTE_DELAY, FX_PATTERN_DELAY, FX_RETRIGGER, FX_GLOBAL_VOLUME,
    FX_GLOBAL_VOL_SLIDE, FX_PAN_SLIDE, FX_TREMOR, FX_XFINE_PORTA_UP,
    FX_XFINE_PORTA_DOWN, FX_KEY_OFF, FX_CHANNEL_VOLUME, FX_PATTERN_LOOP,
    VOL_NONE, VOL_SET, VOL_SLIDE_UP, VOL_SLIDE_DOWN, VOL_FINE_UP,
    VOL_FINE_DOWN, VOL_VIBRATO, VOL_PAN, VOL_TONE_PORTA,
)
from .mod_file import note_to_period

GBA_MIX_RATE = 13379          # Hz — taux « qualité standard » des presets maxmod GBA
AMIGA_PAL_CLOCK = 7093789.2   # Hz — horloge de référence période → fréquence
_MAX_VISITED = 4096           # anti-boucle infinie sur des patterns qui se rebouclent

# Table sinusoïdale des trackers : un quart de période sur 32 pas, en 0..255.
# La même sert au vibrato et au trémolo, comme dans ProTracker.
_SINE = tuple(int(round(255 * math.sin(math.pi * 2 * i / 64))) for i in range(64))

# Bornes de période en mode Amiga. Larges à dessein : elles n'existent que
# pour empêcher un glissé qui s'emballe de produire une fréquence absurde.
_PERIOD_MIN, _PERIOD_MAX = 20.0, 6848.0
_LINEAR_MIN, _LINEAR_MAX = 0.0, 7680.0


@dataclass
class _Channel:
    sample: Sample | None = None
    instrument: Instrument | None = None
    note: int = 0
    period: float = 0.0
    porta_target: float = 0.0
    porta_speed: int = 0
    volume: float = 0.0          # 0..64
    pan: int = 128               # 0..255
    pos: float = 0.0
    direction: int = 1           # +1 / −1, pour le bouclage aller-retour
    playing: bool = False

    vib_pos: int = 0
    vib_speed: int = 0
    vib_depth: int = 0
    trem_pos: int = 0
    trem_speed: int = 0
    trem_depth: int = 0

    # Mémoire des paramètres : un effet écrit sans paramètre reprend le
    # dernier — c'est la règle dans les quatre formats, et l'oublier fait
    # taire un glissé sur deux.
    mem_porta: int = 0
    mem_tone: int = 0
    mem_volslide: int = 0
    mem_offset: int = 0

    delay_ticks: int = -1        # note retardée (EDx) — le tick où elle tombe
    cut_tick: int = -1
    retrig_every: int = 0
    tremor_on: int = 0
    tremor_off: int = 0
    tremor_count: int = 0
    tremor_mute: bool = False

    # Enveloppes et extinction (XM/IT)
    env_vol_tick: int = 0
    env_pan_tick: int = 0
    keyed_off: bool = False
    fade: float = 1.0

    pending: object = None       # la Cell à déclencher, quand elle est retardée


def _sine(pos: int) -> float:
    """Onde de vibrato/trémolo, −255..+255."""
    v = _SINE[pos & 63]
    return float(v)


def _period_of(mod: Module, note: int, samp: Sample | None) -> float:
    """La période d'une note, dans l'unité du module.

    Amiga : une vraie période, d'autant plus petite que la note est haute.
    Linéaire : l'échelle de FastTracker, 64 unités par demi-ton, dans le même
    sens (plus petite = plus aigu). Les deux partagent donc tous les glissés.
    """
    if mod.linear_freq:
        rel = samp.relative_note if samp else 0
        fine = samp.finetune if samp else 0
        return (120 - (note + rel)) * 64.0 - fine / 2.0
    if mod.amiga_table:
        return note_to_period(note)
    c5 = (samp.c5_speed if samp and samp.c5_speed else AMIGA_C5_RATE)
    return PERIOD_C5 * (AMIGA_C5_RATE / c5) * (2.0 ** ((NOTE_C5 - note) / 12.0))


def _step(mod: Module, period: float, samp: Sample | None, mix_rate: int) -> float:
    """Période → avance de lecture, en échantillons source par échantillon de sortie."""
    if period <= 0:
        return 0.0
    if mod.linear_freq:
        c5 = (samp.c5_speed if samp and samp.c5_speed else AMIGA_C5_RATE)
        freq = c5 * (2.0 ** ((3840.0 - period) / 768.0))
    else:
        freq = AMIGA_PAL_CLOCK / (period * 2.0)
    return freq / mix_rate


def _clamp_period(mod: Module, period: float) -> float:
    if mod.linear_freq:
        return max(_LINEAR_MIN, min(_LINEAR_MAX, period))
    return max(_PERIOD_MIN, min(_PERIOD_MAX, period))


def _memo(mod: Module, param: int, memory: int) -> int:
    """Le paramètre à appliquer : celui de la case, ou le dernier retenu.

    ProTracker n'a PAS de mémoire d'effet — un « A00 » n'y glisse rien —, les
    trois autres formats si. Une seule règle ici plutôt qu'un `if kind ==` là
    où l'effet se joue."""
    if param:
        return param
    return memory if mod.effect_memory else 0


def _slide_toward(period: float, target: float, step: float) -> float:
    if period < target:
        return min(target, period + step)
    if period > target:
        return max(target, period - step)
    return period


def render_module(mod: Module, mix_rate: int = GBA_MIX_RATE,
                  tempo: float = 1.0, pitch: float = 1.0) -> np.ndarray:
    """Retourne un tableau int16 stéréo entrelacé (frames, 2)."""
    return render_module_marked(mod, mix_rate, tempo, pitch)[0]


def render_module_marked(mod: Module, mix_rate: int = GBA_MIX_RATE,
                         tempo: float = 1.0, pitch: float = 1.0) -> tuple[np.ndarray, dict]:
    """Le rendu, PLUS l'offset où commence chaque position d'ordre.

    `marks[i]` = l'échantillon où débute la position d'ordre `i`, la première
    fois qu'elle est jouée. C'est la frontière de motif que la « coupe à la
    position » guette (`mmGetPosition` / `mmPosition` dans le runtime) : sans
    ces repères, l'aperçu ne saurait ni quand couper, ni où reprendre l'autre
    module. Un seul parcours produit les deux — un rendu et une table de
    positions calculés séparément finiraient par diverger.

    `tempo` et `pitch` sont les facteurs de `mmSetModuleTempo` / `mmSetModulePitch`
    (1,0 = le fichier tel qu'il est ; la ROM les borne à 0,5–2,0). Le tempo raccourcit
    ou allonge le TICK — les lignes passent plus vite, les échantillons gardent leur
    hauteur — ; la hauteur multiplie la vitesse de lecture de chaque échantillon, donc sa
    durée change avec elle. Mesuré sur ROM le 2026-10-11 : les deux prennent effet
    appliqués juste après `mmStart`, et le facteur de tempo SE MULTIPLIE avec un
    changement de tempo du morceau lui-même (`Fxx` à 250 bpm : ×2 ; facteur 200 % : ×2 ;
    les deux : ×4) — d'où le facteur appliqué à chaque tick, quel que soit le tempo courant.
    """
    n_ch = max(1, mod.num_channels)
    channels = [_Channel() for _ in range(n_ch)]
    for ci, ch in enumerate(channels):
        ch.pan = mod.channel_pan[ci] if ci < len(mod.channel_pan) else 128

    speed = max(1, mod.speed)
    bpm = max(32, mod.bpm)
    global_vol = mod.global_volume
    order_pos = 0
    row = 0
    visited: set = set()

    out_l: list = []
    out_r: list = []
    marks: dict = {}
    written = 0        # échantillons déjà produits — l'horloge des repères

    def sample_of(cell_instrument: int, note: int) -> tuple[Sample | None, Instrument | None, int]:
        """(échantillon, instrument, index) pour ce couple instrument/note.

        C'est ici que la couche d'instrument de XM et IT se résout — et son
        absence en MOD et S3M, où l'« instrument » EST l'échantillon."""
        if cell_instrument <= 0:
            return None, None, -1
        if mod.instruments:
            if cell_instrument > len(mod.instruments):
                return None, None, -1
            inst = mod.instruments[cell_instrument - 1]
            n = note if note not in (NOTE_NONE, NOTE_OFF) else NOTE_C5
            idx = inst.sample_of_note[n] if 0 <= n < len(inst.sample_of_note) else -1
            if idx < 0 or idx >= len(mod.samples):
                return None, inst, -1
            return mod.samples[idx], inst, idx
        idx = cell_instrument - 1
        if idx >= len(mod.samples):
            return None, None, -1
        return mod.samples[idx], None, idx

    def start_note(ch: _Channel, cell, keep_position: bool = False):
        """Déclenche la note d'une case sur ce canal."""
        samp, inst, _idx = sample_of(cell.instrument, cell.note)
        if samp is not None:
            ch.sample = samp
            ch.instrument = inst
            ch.volume = float(samp.volume)
            if samp.default_pan >= 0:
                ch.pan = samp.default_pan
        elif inst is not None:
            ch.instrument = inst

        if cell.note not in (NOTE_NONE, NOTE_OFF):
            ch.note = cell.note
            ch.period = _period_of(mod, cell.note, ch.sample)
            if not keep_position:
                ch.pos = 0.0
                ch.direction = 1
                ch.playing = ch.sample is not None
            ch.keyed_off = False
            ch.fade = 1.0
            ch.env_vol_tick = 0
            ch.env_pan_tick = 0

    def key_off(ch: _Channel):
        """Relâche : le fadeout commence, et l'enveloppe quitte son maintien.

        Sans enveloppe de volume ni fadeout — le cas de MOD et S3M —, il n'y a
        rien à relâcher : la note s'arrête net, comme sur la console."""
        ch.keyed_off = True
        inst = ch.instrument
        if inst is None or (not inst.vol_env.active and not inst.fadeout):
            ch.playing = False
            ch.volume = 0.0

    def env_value(env: Envelope, tick: int, default: float) -> float:
        return env.value_at(tick, default) if env.active else default

    def advance_env(env: Envelope, tick: int, keyed_off: bool) -> int:
        """Fait avancer l'horloge d'une enveloppe d'un tick, boucle comprise."""
        if not env.active:
            return tick
        tick += 1
        if env.loop_end >= 0 and env.loop_start >= 0 and env.loop_end < len(env.points):
            if tick >= env.points[env.loop_end][0]:
                tick = env.points[env.loop_start][0]
                return tick
        if (not keyed_off) and 0 <= env.sustain < len(env.points):
            if tick > env.points[env.sustain][0]:
                tick = env.points[env.sustain][0]
        return tick

    def render_tick():
        """Mixe un tick — la plus petite tranche de temps d'un tracker."""
        nonlocal written
        n = round(mix_rate * 2.5 / (bpm * tempo))
        if n <= 0:
            return
        left = np.zeros(n, dtype=np.float32)
        right = np.zeros(n, dtype=np.float32)
        for ch in channels:
            samp = ch.sample
            if not ch.playing or samp is None or samp.data.size == 0:
                continue
            step = _step(mod, ch.period + _vib_delta(ch), samp, mix_rate) * pitch
            if step <= 0:
                continue
            vol = ch.volume + _trem_delta(ch)
            vol = max(0.0, min(64.0, vol))
            if ch.tremor_mute:
                vol = 0.0
            gain = (vol / 64.0) * ch.fade * (global_vol / 64.0)
            gain *= (samp.global_volume / 64.0)
            if ch.instrument is not None:
                gain *= (ch.instrument.global_volume / 128.0)
                gain *= env_value(ch.instrument.vol_env, ch.env_vol_tick, 64.0) / 64.0
            if gain <= 0.0:
                _advance_position(ch, step, n)
                continue

            pan = ch.pan
            if ch.instrument is not None and ch.instrument.pan_env.active:
                # L'enveloppe de panoramique DÉVIE autour du centre, elle ne
                # remplace pas le réglage du canal (règle XM/IT).
                dev = env_value(ch.instrument.pan_env, ch.env_pan_tick, 32.0) - 32.0
                pan = int(max(0, min(255, pan + dev * 4)))

            vals = _read_samples(ch, samp, step, n)
            left += vals * (gain * (255 - pan) / 255.0)
            right += vals * (gain * pan / 255.0)
        out_l.append(left)
        out_r.append(right)
        written += n

    def _vib_delta(ch: _Channel) -> float:
        if not ch.vib_depth:
            return 0.0
        amp = _sine(ch.vib_pos) * ch.vib_depth / 128.0
        return amp * mod.slide_scale

    def _trem_delta(ch: _Channel) -> float:
        if not ch.trem_depth:
            return 0.0
        return _sine(ch.trem_pos) * ch.trem_depth / 64.0 / 4.0

    def _read_samples(ch: _Channel, samp: Sample, step: float, n: int) -> np.ndarray:
        """Les `n` échantillons de ce canal pour ce tick, bouclage compris.

        Le cas courant — pas de boucle, ou boucle simple — est vectorisé ;
        l'aller-retour, rare, avance échantillon par échantillon. Une preview
        qui rame n'est pas une preview, mais un aller-retour mal rendu
        s'entend, alors on paie le prix là où il se pose.
        """
        data = samp.data
        if samp.loops and samp.loop_kind == LOOP_PINGPONG:
            out = np.empty(n, dtype=np.float32)
            pos, d = ch.pos, ch.direction
            ls, le = samp.loop_start, samp.loop_end
            for i in range(n):
                if pos >= le:
                    pos = le - (pos - le) - 1
                    d = -1
                elif pos < ls and d < 0:
                    pos = ls + (ls - pos)
                    d = 1
                idx = int(pos)
                out[i] = data[idx] if 0 <= idx < data.size else 0.0
                pos += step * d
            ch.pos, ch.direction = pos, d
            return out

        positions = ch.pos + step * np.arange(n, dtype=np.float64)
        if samp.loops:
            ls, le = samp.loop_start, samp.loop_end
            span = max(1, le - ls)
            over = positions >= le
            positions = np.where(over, ls + np.mod(positions - ls, span), positions)
        valid = positions < data.size
        idx = np.clip(positions.astype(np.int64), 0, max(data.size - 1, 0))
        vals = data[idx].astype(np.float32)
        vals[~valid] = 0.0
        last = ch.pos + step * n
        if samp.loops:
            ls, le = samp.loop_start, samp.loop_end
            if last >= le:
                last = ls + math.fmod(last - ls, max(1, le - ls))
        elif last >= data.size:
            ch.playing = False
        ch.pos = last
        return vals

    def _advance_position(ch: _Channel, step: float, n: int):
        """Avancer sans mixer — un canal muet continue de se dérouler."""
        last = ch.pos + step * n
        samp = ch.sample
        if samp is not None and samp.loops:
            ls, le = samp.loop_start, samp.loop_end
            if last >= le:
                last = ls + math.fmod(last - ls, max(1, le - ls))
        elif samp is not None and last >= samp.data.size:
            ch.playing = False
        ch.pos = last

    # ── Le parcours du morceau ────────────────────────────────────
    pattern_loop_row = [0] * n_ch
    pattern_loop_count = [0] * n_ch

    while 0 <= order_pos < len(mod.order):
        pattern_idx = mod.order[order_pos]
        if pattern_idx == ORDER_END:
            break            # fin du morceau : ce qui suit n'est jamais joué (ROM comprise)
        if pattern_idx >= len(mod.patterns):    # ORDER_SKIP compris : sauté
            order_pos += 1
            row = 0
            continue
        pattern = mod.patterns[pattern_idx]
        n_rows = len(pattern)
        looped_out = False
        marks.setdefault(order_pos, written)

        while row < n_rows:
            key = (order_pos, row)
            if key in visited or len(visited) > _MAX_VISITED:
                looped_out = True
                break
            visited.add(key)

            cells = pattern[row]
            next_order_jump = None
            next_row_break = None
            row_repeat = 0        # EEx : le nombre de fois où la ligne est REJOUÉE
            loop_jump = None

            # ── Tick 0 : déclenchements et effets immédiats ───────
            for ci in range(n_ch):
                if ci >= len(cells):
                    continue
                cell = cells[ci]
                ch = channels[ci]
                ch.cut_tick = -1
                ch.delay_ticks = -1
                ch.retrig_every = 0
                ch.tremor_mute = False
                fx, par = cell.effect, cell.param

                tone_porta = fx in (FX_TONE_PORTA, FX_TONE_PORTA_VOL) or cell.vol_fx == VOL_TONE_PORTA

                if fx == FX_NOTE_DELAY and par > 0:
                    ch.delay_ticks = par
                    ch.pending = cell
                elif cell.note == NOTE_OFF:
                    key_off(ch)
                elif tone_porta and cell.note not in (NOTE_NONE, NOTE_OFF):
                    # Un glissé VERS une note ne la déclenche pas : il pose la
                    # cible et laisse le son en cours y aller.
                    samp, inst, _i = sample_of(cell.instrument, cell.note)
                    if samp is not None and ch.sample is None:
                        ch.sample, ch.instrument = samp, inst
                        ch.volume = float(samp.volume)
                    ch.porta_target = _period_of(mod, cell.note, ch.sample)
                    ch.note = cell.note
                    if ch.sample is not None and not ch.playing:
                        ch.playing = True
                elif cell.note != NOTE_NONE or cell.instrument:
                    start_note(ch, cell)

                # Colonne de volume — un réglage, pas une commande.
                if cell.vol_fx == VOL_SET:
                    ch.volume = float(min(64, cell.vol_param))
                elif cell.vol_fx == VOL_PAN:
                    ch.pan = min(255, cell.vol_param * 4)
                elif cell.vol_fx == VOL_VIBRATO:
                    ch.vib_depth = cell.vol_param
                elif cell.vol_fx == VOL_FINE_UP:
                    ch.volume = min(64.0, ch.volume + cell.vol_param)
                elif cell.vol_fx == VOL_FINE_DOWN:
                    ch.volume = max(0.0, ch.volume - cell.vol_param)
                elif cell.vol_fx == VOL_TONE_PORTA and cell.vol_param:
                    ch.porta_speed = cell.vol_param * 16

                if fx == FX_SET_VOLUME:
                    ch.volume = float(min(64, par))
                elif fx == FX_SET_PAN:
                    ch.pan = par
                elif fx == FX_SAMPLE_OFFSET:
                    ch.mem_offset = par or ch.mem_offset
                    if cell.note not in (NOTE_NONE, NOTE_OFF):
                        ch.pos = float(ch.mem_offset) * 256.0
                elif fx == FX_POSITION_JUMP:
                    next_order_jump = par
                elif fx == FX_PATTERN_BREAK:
                    next_row_break = par
                elif fx == FX_SET_SPEED:
                    if par:
                        speed = par
                elif fx == FX_SET_TEMPO:
                    if par:
                        bpm = par
                elif fx == FX_GLOBAL_VOLUME:
                    global_vol = min(64, par)
                elif fx == FX_CHANNEL_VOLUME:
                    ch.volume = float(min(64, par))
                elif fx in (FX_TONE_PORTA, FX_TONE_PORTA_VOL):
                    if fx == FX_TONE_PORTA and par:
                        ch.mem_tone = par
                    ch.porta_speed = (ch.mem_tone or par) * mod.slide_scale
                elif fx in (FX_PORTA_UP, FX_PORTA_DOWN):
                    if par:
                        ch.mem_porta = par
                elif fx in (FX_VIBRATO, FX_VIBRATO_VOL):
                    if fx == FX_VIBRATO:
                        if par >> 4:
                            ch.vib_speed = par >> 4
                        if par & 0x0F:
                            ch.vib_depth = par & 0x0F
                elif fx == FX_TREMOLO:
                    if par >> 4:
                        ch.trem_speed = par >> 4
                    if par & 0x0F:
                        ch.trem_depth = par & 0x0F
                elif fx == FX_FINE_PORTA_UP:
                    ch.period = _clamp_period(mod, ch.period - par * mod.slide_scale)
                elif fx == FX_FINE_PORTA_DOWN:
                    ch.period = _clamp_period(mod, ch.period + par * mod.slide_scale)
                elif fx == FX_XFINE_PORTA_UP:
                    ch.period = _clamp_period(mod, ch.period - par * mod.slide_scale / 4.0)
                elif fx == FX_XFINE_PORTA_DOWN:
                    ch.period = _clamp_period(mod, ch.period + par * mod.slide_scale / 4.0)
                elif fx == FX_FINE_VOL_UP:
                    ch.volume = min(64.0, ch.volume + par)
                elif fx == FX_FINE_VOL_DOWN:
                    ch.volume = max(0.0, ch.volume - par)
                elif fx == FX_NOTE_CUT:
                    ch.cut_tick = par
                    if par == 0:
                        ch.volume = 0.0
                elif fx == FX_RETRIGGER:
                    ch.retrig_every = par
                elif fx == FX_TREMOR:
                    ch.tremor_on = (par >> 4) + 1
                    ch.tremor_off = (par & 0x0F) + 1
                    ch.tremor_count = 0
                elif fx == FX_KEY_OFF:
                    key_off(ch)
                elif fx == FX_PATTERN_DELAY:
                    row_repeat = max(row_repeat, par)
                elif fx == FX_PATTERN_LOOP:
                    if par == 0:
                        pattern_loop_row[ci] = row
                    elif pattern_loop_count[ci] < par:
                        pattern_loop_count[ci] += 1
                        loop_jump = pattern_loop_row[ci]
                    else:
                        pattern_loop_count[ci] = 0

                if fx in (FX_VOLUME_SLIDE, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL) and par:
                    ch.mem_volslide = par

            # ── Les ticks de la ligne ─────────────────────────────
            for repeat in range(row_repeat + 1):
                for tick in range(speed):
                    if tick > 0:
                        for ci in range(n_ch):
                            if ci >= len(cells):
                                continue
                            cell = cells[ci]
                            ch = channels[ci]
                            fx, par = cell.effect, cell.param

                            if ch.delay_ticks == tick and ch.pending is not None:
                                start_note(ch, ch.pending)
                                ch.pending = None

                            if fx == FX_PORTA_UP:
                                amount = _memo(mod, par, ch.mem_porta)
                                ch.period = _clamp_period(mod, ch.period - amount * mod.slide_scale)
                            elif fx == FX_PORTA_DOWN:
                                amount = _memo(mod, par, ch.mem_porta)
                                ch.period = _clamp_period(mod, ch.period + amount * mod.slide_scale)
                            elif fx in (FX_TONE_PORTA, FX_TONE_PORTA_VOL) or cell.vol_fx == VOL_TONE_PORTA:
                                if ch.porta_target:
                                    ch.period = _slide_toward(ch.period, ch.porta_target,
                                                              ch.porta_speed)

                            if fx in (FX_VOLUME_SLIDE, FX_TONE_PORTA_VOL, FX_VIBRATO_VOL):
                                p = _memo(mod, par if fx == FX_VOLUME_SLIDE else 0,
                                          ch.mem_volslide)
                                up, down = p >> 4, p & 0x0F
                                if up:
                                    ch.volume = min(64.0, ch.volume + up)
                                elif down:
                                    ch.volume = max(0.0, ch.volume - down)
                            elif cell.vol_fx == VOL_SLIDE_UP:
                                ch.volume = min(64.0, ch.volume + cell.vol_param)
                            elif cell.vol_fx == VOL_SLIDE_DOWN:
                                ch.volume = max(0.0, ch.volume - cell.vol_param)

                            if fx == FX_GLOBAL_VOL_SLIDE:
                                up, down = par >> 4, par & 0x0F
                                if up:
                                    global_vol = min(64, global_vol + up)
                                elif down:
                                    global_vol = max(0, global_vol - down)
                            elif fx == FX_PAN_SLIDE:
                                up, down = par >> 4, par & 0x0F
                                ch.pan = max(0, min(255, ch.pan + (up - down) * 4))

                            if fx in (FX_VIBRATO, FX_VIBRATO_VOL) or cell.vol_fx == VOL_VIBRATO:
                                ch.vib_pos = (ch.vib_pos + ch.vib_speed) & 63
                            if fx == FX_TREMOLO:
                                ch.trem_pos = (ch.trem_pos + ch.trem_speed) & 63

                            if fx == FX_NOTE_CUT and ch.cut_tick == tick:
                                ch.volume = 0.0
                            if ch.retrig_every and tick % ch.retrig_every == 0:
                                ch.pos = 0.0
                                ch.direction = 1
                                ch.playing = ch.sample is not None
                            if ch.tremor_on:
                                cycle = ch.tremor_on + ch.tremor_off
                                ch.tremor_mute = (tick % cycle) >= ch.tremor_on

                    # L'arpège change la hauteur SANS toucher à l'état du canal :
                    # il se lit sur le tick, il ne se mémorise pas.
                    saved = []
                    for ci in range(min(n_ch, len(cells))):
                        cell, ch = cells[ci], channels[ci]
                        if cell.effect == FX_ARPEGGIO and cell.param and ch.period:
                            semis = 0
                            if tick % 3 == 1:
                                semis = cell.param >> 4
                            elif tick % 3 == 2:
                                semis = cell.param & 0x0F
                            if semis:
                                saved.append((ch, ch.period))
                                if mod.linear_freq:
                                    ch.period -= semis * 64
                                else:
                                    ch.period /= 2.0 ** (semis / 12.0)

                    render_tick()

                    for ch, period in saved:
                        ch.period = period

                    # Enveloppes et extinction : une horloge par tick joué.
                    for ch in channels:
                        inst = ch.instrument
                        if inst is None:
                            continue
                        ch.env_vol_tick = advance_env(inst.vol_env, ch.env_vol_tick, ch.keyed_off)
                        ch.env_pan_tick = advance_env(inst.pan_env, ch.env_pan_tick, ch.keyed_off)
                        if ch.keyed_off and inst.fadeout:
                            ch.fade -= inst.fadeout / 65536.0
                            if ch.fade <= 0.0:
                                ch.fade = 0.0
                                ch.playing = False

            if loop_jump is not None:
                row = loop_jump
                continue
            if next_row_break is not None or next_order_jump is not None:
                order_pos = next_order_jump if next_order_jump is not None else order_pos + 1
                row = next_row_break if next_row_break is not None else 0
                break
            row += 1
        else:
            order_pos += 1
            row = 0
            continue

        if looped_out:
            break

    if not out_l:
        return np.zeros((0, 2), dtype=np.int16), {}

    left = np.concatenate(out_l)
    right = np.concatenate(out_r)
    # Gain global : les échantillons sont normalisés en −1..+1 et pondérés par
    # volume/64 ; on remet à l'échelle int16 avec de la marge pour limiter
    # l'écrêtage quand plusieurs canaux forts se superposent (comportement
    # « authentique » GBA : ça peut quand même saturer, comme sur la console).
    scale = 190.0 * 128.0
    left = np.clip(left * scale, -32768, 32767).astype(np.int16)
    right = np.clip(right * scale, -32768, 32767).astype(np.int16)
    stereo = np.empty((left.size, 2), dtype=np.int16)
    stereo[:, 0] = left
    stereo[:, 1] = right
    return stereo, marks
