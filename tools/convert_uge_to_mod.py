"""Convertit des morceaux hUGETracker (``.uge``) en modules ProTracker (``.mod``) à 4 canaux.

    python tools/convert_uge_to_mod.py <fichier.uge | dossier> [--output DOSSIER]

Sans ``--output``, les ``.mod`` sont écrits dans un sous-dossier ``mod`` à côté des sources, qui ne sont
jamais modifiées. Sert à obtenir des modules réalistes pour essayer l'écran Son et le build audio quand on
n'en a pas sous la main : le résultat est jouable et fidèle aux notes, pas au son d'une Game Boy.

Un ``.uge`` ne contient aucun échantillon : ses quatre canaux sont du matériel (deux carrés, une onde
programmable, un bruit). On synthétise donc un échantillon par instrument UTILISÉ et par moitié de tessiture,
puis on traduit les notes et les effets qui existent aussi en MOD.

Repris : les notes, les instruments (rapport cyclique, onde, bruit 7 ou 15 bits), le volume initial,
l'enveloppe de volume (approchée par des glissés ``A``), le compteur de longueur (coupe ``EC``), les effets
``0`` arpège, ``1`` ``2`` ``3`` portamento, ``7`` délai, ``A`` ``B`` ``C`` ``D`` ``E`` ``F``, et le tempo.
Non repris : le balayage de fréquence, les sous-motifs (v6), le panoramique (``8xx``), le timbre (``9xx``),
l'appel de routine (``6xy``) et le volume maître (``5xx``).

Le format ``.uge`` (versions 5 et 6) est celui du manuel de hUGETracker, « uge-format.md ». La hauteur de la
note 0 (65,406 Hz) et la durée d'un tick (1 / 59,7275 s) ont été vérifiées sur les rendus audio que
hUGETracker produit : la note 12 sonne à 130 Hz, et la durée simulée d'un morceau tombe à 2 % de celle de son
rendu.

Un MOD n'a pas d'en-tête de tempo : on ajoute un pattern d'AMORCE d'un ordre, qui pose 149 BPM (un tick MOD
vaut alors un tick Game Boy) et la vitesse du morceau. Le fichier reboucle à l'ordre suivant, pour ne pas la
rejouer ; les positions d'ordre (``Bxx``) sont décalées d'un cran en conséquence.
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

NO_NOTE = 90                    # une case de pattern sans note

GB_BASE_HZ = 65.406             # la note 0 de hUGETracker
MOD_C2_HZ = 8363.0              # ce que mmutil et maxmod jouent pour la période 428 (C-2)
GB_TICK_HZ = 59.7275            # une frame Game Boy
MOD_BPM = 149                   # 2,5 / 149 s ≈ 1 / 59,7275 s
PERIODS = [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
           428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
           214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113]    # C-1 … B-3, finetune 0
GROUP = {0: 0, 1: 0, 2: 15, 3: 30}      # canal → décalage dans les 45 instruments (15 carrés, 15 ondes, 15 bruits)
LOW, HIGH = 0, 1                        # deux moitiés de 36 notes : un MOD n'en couvre que trois octaves


# ══════════════════════════════════════════════════════════════════
#  Lecture d'un .uge
# ══════════════════════════════════════════════════════════════════

class _Reader:
    def __init__(self, data: bytes):
        self.data, self.position = data, 0

    def u8(self) -> int:
        value = self.data[self.position]
        self.position += 1
        return value

    def i8(self) -> int:
        value = struct.unpack_from("<b", self.data, self.position)[0]
        self.position += 1
        return value

    def u32(self) -> int:
        value = struct.unpack_from("<I", self.data, self.position)[0]
        self.position += 4
        return value

    def boolean(self) -> bool:
        return bool(self.u8())

    def shortstring(self) -> str:
        """Un octet de longueur, puis 255 caractères dont seuls les premiers comptent."""
        length = self.u8()
        raw = self.data[self.position:self.position + 255]
        self.position += 255
        return raw[:length].decode("latin-1")


@dataclass
class Instrument:
    kind: int = 0                   # 0 carré, 1 onde, 2 bruit
    name: str = ""
    length: int = 0
    length_enabled: bool = False
    volume: int = 15                # carré / bruit : volume initial 0-15 ; onde : bits de NR32 (1 = 100 %)
    sweep_down: bool = True
    sweep_change: int = 0           # 0 = pas d'enveloppe
    duty: int = 2
    wave_index: int = 0
    noise_7bit: bool = False


@dataclass
class Cell:
    note: int = NO_NOTE
    instrument: int = 0
    effect: int = 0
    param: int = 0


@dataclass
class Song:
    version: int = 0
    name: str = ""
    instruments: list = field(default_factory=list)     # 45
    waves: list = field(default_factory=list)           # 16 × 32 quartets
    ticks_per_row: int = 6
    patterns: dict = field(default_factory=dict)        # identifiant → 64 `Cell`
    orders: list = field(default_factory=list)          # 4 listes d'identifiants de pattern


def _skip_subpattern(reader: _Reader, version: int) -> None:
    """Le sous-motif d'un instrument (v6) : lu pour avancer, jamais traduit."""
    if version < 6:
        return
    reader.boolean()
    for _ in range(64):
        reader.u32(); reader.u32(); reader.u32(); reader.u32(); reader.u8()


def parse_uge(data: bytes) -> Song:
    reader = _Reader(data)
    song = Song(version=reader.u32())
    version = song.version
    if version not in (5, 6):
        raise ValueError(f"version {version} non gérée (5 et 6 seulement)")
    song.name = reader.shortstring()
    reader.shortstring(); reader.shortstring()          # artiste, commentaire

    for kind in (0, 1, 2):
        for _ in range(15):
            ins = Instrument(kind=reader.u32(), name=reader.shortstring())
            ins.length, ins.length_enabled = reader.u32(), reader.boolean()
            if kind == 0:
                ins.volume = reader.u8()
                ins.sweep_down = reader.u32() == 1
                ins.sweep_change = reader.u8()
                reader.u32(); reader.u32(); reader.u32()         # balayage de fréquence : temps, activé, décalage
                ins.duty = reader.u8()
                reader.u32(); reader.u32()
                if version < 6:
                    reader.u32()
                reader.u32()
            elif kind == 1:
                reader.u8(); reader.u32(); reader.u8(); reader.u32(); reader.u32(); reader.u32(); reader.u8()
                ins.volume = reader.u32()
                ins.wave_index = reader.u32()
                if version < 6:
                    reader.u32()
                reader.u32()
            else:
                ins.volume = reader.u8()
                ins.sweep_down = reader.u32() == 1
                ins.sweep_change = reader.u8()
                reader.u32(); reader.u32(); reader.u32(); reader.u8(); reader.u32(); reader.u32()
                if version < 6:
                    reader.u32()
                ins.noise_7bit = reader.u32() == 1
            if version < 6:
                reader.u32()
            _skip_subpattern(reader, version)
            if 4 <= version < 6:
                for _ in range(6):
                    reader.i8()
            song.instruments.append(ins)

    for _ in range(16):
        song.waves.append([reader.u8() for _ in range(32)])

    song.ticks_per_row = reader.u32()
    if version >= 6:
        reader.boolean(); reader.u32()
    for _ in range(reader.u32()):
        identifier = reader.u32()
        rows = []
        for _ in range(64):
            note, instrument = reader.u32(), reader.u32()
            if version >= 6:
                reader.u32()
            rows.append(Cell(note, instrument, reader.u32(), reader.u8()))
        song.patterns[identifier] = rows

    for _ in range(4):
        count = reader.u32()
        # Le format écrit « longueur + 1 » entrées : la dernière est un remplissage (le bug « off by one »).
        song.orders.append([reader.u32() for _ in range(count)][:-1])
    return song


# ══════════════════════════════════════════════════════════════════
#  Les échantillons
# ══════════════════════════════════════════════════════════════════

def gb_frequency(note: int) -> float:
    return GB_BASE_HZ * 2 ** (note / 12)


def variant_of(channel: int, note: int) -> int:
    if channel == 3:
        return LOW
    return LOW if note < 36 else HIGH


def mod_note(channel: int, note: int) -> int:
    """L'index MOD (0 = C-1 … 35 = B-3) joué pour une note Game Boy. Le bruit n'a pas de hauteur : on
    garde l'ORDRE des notes (une percussion plus aiguë reste plus aiguë) en comprimant la tessiture."""
    if channel == 3:
        return min(35, max(0, note // 2))
    return note - 36 * variant_of(channel, note)


def cycle_length(variant: int) -> tuple[int, int]:
    """(N, finetune) : le nombre d'échantillons d'une période pour cette moitié de tessiture, et le finetune
    qui rattrape l'arrondi. À la note MOD m, un cycle de N points sonne à 8363 · 2^((m-12)/12) / N Hz."""
    ideal = MOD_C2_HZ / 2 / (GB_BASE_HZ * 2 ** (36 * variant / 12))
    n = max(4, round(ideal))
    residual = 12 * math.log2(ideal / n)                 # l'écart de hauteur restant, en demi-tons
    return n, max(-8, min(7, round(residual * 8)))       # le finetune d'un MOD est en 1/8 de demi-ton


def _cycle(instrument: Instrument, waves: list, points: int) -> np.ndarray:
    """Une période de l'instrument, échantillonnée sur `points` points, de -1 à +1."""
    phase = (np.arange(points) + 0.5) / points
    if instrument.kind == 0:
        duty = (0.125, 0.25, 0.5, 0.75)[instrument.duty & 3]
        return np.where(phase < duty, 1.0, -1.0)
    table = np.array(waves[instrument.wave_index & 15], dtype=float)
    return (table[(phase * 32).astype(int) % 32] - 7.5) / 7.5


def _noise(instrument: Instrument) -> tuple[np.ndarray, bool]:
    """(échantillon, boucle ?). Un bruit qui décroît est cuit en un coup ; un bruit tenu boucle."""
    width = 7 if instrument.noise_7bit else 15
    register, bits = (1 << width) - 1, []
    for _ in range(127 if instrument.noise_7bit else 8192):
        feedback = (register ^ (register >> 1)) & 1
        register = (register >> 1) | (feedback << (width - 1))
        bits.append(1.0 if register & 1 else -1.0)
    noise = np.array(bits)
    decays = instrument.sweep_down and instrument.sweep_change > 0 and instrument.volume > 0
    seconds = instrument.volume * instrument.sweep_change / 64.0 if decays else None
    if instrument.length_enabled:
        cut = (64 - instrument.length) / 256.0
        seconds = cut if seconds is None else min(seconds, cut)
    if seconds is None:
        return noise, True
    frames = max(64, int(seconds * MOD_C2_HZ))
    shaped = np.resize(noise, frames)
    if decays:
        shaped = shaped * np.clip(1 - np.arange(frames) / MOD_C2_HZ / seconds, 0, 1)
    return shaped, False


class _Sample:
    def __init__(self, name: str, data: np.ndarray, volume: int, finetune: int, loops: bool):
        self.name, self.finetune, self.loops = name[:22], finetune, loops
        self.volume = max(0, min(64, volume))
        pcm = np.clip(np.round(data * 100), -127, 127).astype(np.int8)
        if len(pcm) % 2:                                  # une longueur de MOD se compte en mots
            pcm = np.append(pcm, pcm[-1:] if loops else np.zeros(1, dtype=np.int8))
        self.pcm = pcm


def _build_sample(song: Song, index: int, variant: int) -> _Sample:
    instrument = song.instruments[index]
    name = (instrument.name.strip() or f"instr {index}")[:18] + f" {'LH'[variant]}"
    if instrument.kind == 2:
        data, loops = _noise(instrument)
        return _Sample(name, data, round(64 * instrument.volume / 15), 0, loops)
    points, finetune = cycle_length(variant)
    data = np.tile(_cycle(instrument, song.waves, points), max(1, 64 // points))   # ≥ ~64 points bouclés
    if instrument.kind == 0:
        volume = round(64 * instrument.volume / 15)
    else:
        volume = round(64 * {0: 0.0, 1: 1.0, 2: 0.5, 3: 0.25}.get(instrument.volume, 1.0))
    return _Sample(name, data, volume, finetune, True)


# ══════════════════════════════════════════════════════════════════
#  Les patterns
# ══════════════════════════════════════════════════════════════════

def _to_bcd(row: int) -> int:
    """La rangée d'un saut `Dxx` : ProTracker l'écrit en décimal codé (D14 = ligne 14)."""
    return ((row // 10) << 4) | (row % 10)


def _cell(period: int, sample: int, effect: int, param: int) -> bytes:
    return bytes([((sample >> 4) & 0x0F) | ((period >> 8) & 0x0F), period & 0xFF,
                  ((sample & 0x0F) << 4) | (effect & 0x0F), param & 0xFF])


def convert(song: Song) -> tuple[bytes, dict]:
    """(le fichier MOD, ce qu'il contient). ValueError si le morceau ne tient pas dans un MOD."""
    orders = song.orders
    length = len(orders[0])
    if length + 1 > 128:
        raise ValueError(f"{length} ordres : un MOD n'en tient que 128, dont un d'amorce")

    # 1. Quels (instrument, moitié de tessiture) servent ? Un premier passage sur les notes.
    needed: set = set()
    for channel in range(4):
        current = GROUP[channel]
        for position in range(length):
            for cell in song.patterns[orders[channel][position]]:
                if cell.instrument:
                    current = GROUP[channel] + cell.instrument - 1
                if cell.note != NO_NOTE:
                    needed.add((current, variant_of(channel, cell.note)))
    if len(needed) > 31:
        raise ValueError(f"{len(needed)} échantillons nécessaires : un MOD en tient 31")
    slots = {key: i + 1 for i, key in enumerate(sorted(needed))}
    samples = {slots[key]: _build_sample(song, *key) for key in slots}

    # 2. Un pattern par position d'ordre, l'état de chaque canal passant d'une position à la suivante.
    speed = song.ticks_per_row
    state = [dict(instrument=GROUP[ch], variant=None, mod_note=0, slide=0, frequency=65.0) for ch in range(4)]
    patterns = []
    for position in range(length):
        grid = [[None] * 4 for _ in range(64)]
        for channel in range(4):
            st = state[channel]
            for row, cell in enumerate(song.patterns[orders[channel][position]]):
                period = sample = effect = param = 0
                if cell.instrument:
                    st["instrument"] = GROUP[channel] + cell.instrument - 1
                if cell.note != NO_NOTE:
                    variant = variant_of(channel, cell.note)
                    index = mod_note(channel, cell.note)
                    period = PERIODS[max(0, min(35, index))]
                    # Sans numéro d'échantillon, un MOD garde le volume courant : exactement une note Game Boy
                    # sans instrument, qui ne relance pas l'enveloppe. Un changement de moitié l'impose.
                    if cell.instrument or variant != st["variant"]:
                        sample = slots.get((st["instrument"], variant), 0)
                    st["variant"], st["mod_note"], st["frequency"] = variant, index, gb_frequency(cell.note)
                    instrument = song.instruments[st["instrument"]]
                    # L'enveloppe : -1 sur 15 toutes les `change`/64 s, soit ~4,6/change unités MOD par tick.
                    st["slide"] = 0
                    if channel != 3 and instrument.kind == 0 and instrument.sweep_down and instrument.sweep_change > 0:
                        per_tick = 4.57 / instrument.sweep_change * speed / max(1, speed - 1)
                        st["slide"] = max(1, min(15, round(per_tick)))
                if cell.effect or cell.param:
                    effect, param = _translate_effect(cell, st, speed)
                    if effect == 0xF:
                        speed = param
                    elif effect == 0xC:
                        st["slide"] = 0
                if effect == 0 and param == 0 and st["slide"]:
                    effect, param = 0xA, st["slide"]           # le glissé se poursuit tant qu'aucun effet ne le remplace
                grid[row][channel] = _cell(period, sample, effect, param)
        patterns.append(grid)

    # L'AMORCE : le tempo et la vitesse. Un MOD démarre à 125 BPM, vitesse 6, et n'a pas d'en-tête pour ça ;
    # chercher une cellule libre à la ligne 0 échouait quand les quatre canaux y jouaient.
    empty = bytes(4)
    preamble = [[empty] * 4 for _ in range(64)]
    preamble[0][0] = _cell(0, 0, 0xF, 1)                        # vitesse 1 : l'amorce ne dure presque rien
    preamble[0][1] = _cell(0, 0, 0xF, MOD_BPM)
    preamble[1][0] = _cell(0, 0, 0xF, song.ticks_per_row)       # la vitesse du morceau
    preamble[1][1] = _cell(0, 0, 0xD, 0)                        # puis le premier ordre
    patterns.insert(0, preamble)
    length += 1

    # 3. Le fichier.
    out = bytearray(song.name.encode("latin-1", "replace")[:20].ljust(20, b"\x00"))
    for number in range(1, 32):
        sample = samples.get(number)
        if sample is None:
            out += bytes(22) + struct.pack(">HBBHH", 0, 0, 0, 0, 1)
            continue
        words = len(sample.pcm) // 2
        out += sample.name.encode("latin-1", "replace").ljust(22, b"\x00")
        out += struct.pack(">HBBHH", words, sample.finetune & 0x0F, sample.volume, 0,
                           words if sample.loops else 1)
    # Reboucle à l'ordre 1 : l'amorce ne se rejoue pas.
    out += bytes([length, 1]) + bytes(range(length)).ljust(128, b"\x00") + b"M.K."
    for grid in patterns:
        for row in grid:
            out += b"".join(row)
    for number in sorted(samples):
        out += samples[number].pcm.tobytes()
    return bytes(out), dict(orders=length, samples=len(samples), size=len(out))


def _translate_effect(cell: Cell, st: dict, speed: int) -> tuple[int, int]:
    """(effet, paramètre) MOD d'un effet Game Boy ; (0, 0) quand il n'a pas d'équivalent."""
    code, value = cell.effect, cell.param
    if code == 0x0:
        return 0x0, value                                       # arpège
    if code in (0x1, 0x2, 0x3):
        # Une unité de registre de fréquence Game Boy vaut plus ou moins de unités de période MOD selon la
        # hauteur : f · période / 131072.
        factor = st["frequency"] * PERIODS[st["mod_note"]] / 131072
        return code, max(1, min(255, round(value * factor)))
    if code == 0x7 and value <= 15:
        return 0xE, 0xD0 | value                                # note retardée
    if code == 0xA:
        return 0xA, (min(15, round((value >> 4) * 4)) << 4) | min(15, round((value & 15) * 4))
    if code == 0xB:
        return 0xB, value + 1                                   # + l'amorce
    if code == 0xC:
        return 0xC, round(64 * (value & 15) / 15)
    if code == 0xD:
        return 0xD, _to_bcd(min(63, value))
    if code == 0xE and value < speed:                           # sinon la note n'est pas coupée
        return 0xE, 0xC0 | min(15, value)
    if code == 0xF and 0 < value < 32:
        return 0xF, value
    return 0, 0


# ══════════════════════════════════════════════════════════════════
#  En ligne de commande
# ══════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", type=Path, help="un fichier .uge, ou un dossier qui en contient")
    parser.add_argument("--output", type=Path, help="dossier des .mod (défaut : « mod » à côté des sources)")
    args = parser.parse_args(argv)

    sources = [args.source] if args.source.is_file() else sorted(args.source.glob("*.uge"))
    if not sources:
        print(f"aucun .uge dans {args.source}", file=sys.stderr)
        return 1
    folder = args.output or (args.source.parent if args.source.is_file() else args.source) / "mod"
    folder.mkdir(parents=True, exist_ok=True)

    failures = 0
    for path in sources:
        try:
            data, info = convert(parse_uge(path.read_bytes()))
        except (ValueError, IndexError, struct.error) as exc:
            print(f"{path.name} : refusé — {exc}", file=sys.stderr)
            failures += 1
            continue
        (folder / f"{path.stem}.mod").write_bytes(data)
        print(f"{path.stem}.mod : {info['orders']} ordres, {info['samples']} échantillons, {info['size'] // 1024} Ko")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
