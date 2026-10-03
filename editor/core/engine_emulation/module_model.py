"""
engine_emulation/module_model.py — le modèle commun aux quatre formats de
module que maxmod sait jouer : ProTracker (`.mod`), ScreamTracker 3 (`.s3m`),
FastTracker II (`.xm`) et Impulse Tracker (`.it`).

Un fichier de module est lu par le lecteur de SON format (`mod_file.py`,
`s3m_file.py`, `xm_file.py`, `it_file.py`) et devient un `Module` : à partir
de là, `module_render.py` n'en connaît plus le format. C'est ce qui évite
quatre lecteurs audio, donc quatre façons de rendre le même vibrato.

── Ce que les quatre formats ont en commun, et où ils divergent ────────────

Tous décrivent la même chose : des ÉCHANTILLONS, une grille de PATTERNS
(lignes × canaux), et une table d'ORDRE qui dit dans quel ordre les jouer.
Trois divergences seulement comptent pour le rendu, et le modèle les porte
explicitement plutôt que de les cacher :

  - **la hauteur.** MOD et S3M raisonnent en PÉRIODES Amiga (plus la période
    est petite, plus le son est aigu) ; XM et IT peuvent utiliser une échelle
    LINÉAIRE en fractions de demi-ton. La différence ne s'entend pas sur une
    note tenue — elle s'entend sur les GLISSÉS, qui avancent d'un pas constant
    dans l'une ou l'autre unité. D'où `Module.linear_freq`, et un canal qui
    garde toujours une `period` dont le sens dépend de ce drapeau.
  - **les instruments.** MOD et S3M jouent un échantillon directement ; XM et
    IT interposent un INSTRUMENT, qui choisit l'échantillon selon la note et
    porte les enveloppes. `Module.instruments` vide = le premier cas.
  - **les effets.** Chaque format a sa propre numérotation (0-F en MOD, des
    lettres en S3M/IT). Les lecteurs les traduisent tous vers les constantes
    `FX_*` ci-dessous — sinon le lecteur audio porterait quatre tables de
    correspondance, et un effet corrigé dans l'une resterait faux dans les
    trois autres.

── Ce que ce modèle NE porte pas ───────────────────────────────────────────

Les filtres résonants d'IT, les échantillons stéréo, et les NNA (New Note
Actions) au-delà de la coupure : maxmod ne les rend pas non plus sur GBA, et
l'aperçu vise ce que la console jouera, pas ce qu'un lecteur de bureau
jouerait. Cf. ROADMAP v0.8.8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# ── Effets, normalisés ────────────────────────────────────────────────
# Un seul jeu de constantes pour les quatre formats. Les valeurs n'ont aucun
# sens en dehors de ce module : ce sont les lecteurs qui traduisent, et le
# lecteur audio qui compare.

FX_NONE            = 0
FX_ARPEGGIO        = 1
FX_PORTA_UP        = 2
FX_PORTA_DOWN      = 3
FX_TONE_PORTA      = 4    # glissé VERS la note jouée
FX_VIBRATO         = 5
FX_TONE_PORTA_VOL  = 6    # glissé + slide de volume, sans reprendre le paramètre
FX_VIBRATO_VOL     = 7
FX_TREMOLO         = 8
FX_SET_PAN         = 9
FX_SAMPLE_OFFSET   = 10
FX_VOLUME_SLIDE    = 11
FX_POSITION_JUMP   = 12
FX_SET_VOLUME      = 13
FX_PATTERN_BREAK   = 14
FX_SET_SPEED       = 15   # ticks par ligne
FX_SET_TEMPO       = 16   # BPM
FX_FINE_PORTA_UP   = 17
FX_FINE_PORTA_DOWN = 18
FX_FINE_VOL_UP     = 19
FX_FINE_VOL_DOWN   = 20
FX_NOTE_CUT        = 21
FX_NOTE_DELAY      = 22
FX_PATTERN_DELAY   = 23
FX_RETRIGGER       = 24
FX_GLOBAL_VOLUME   = 25
FX_GLOBAL_VOL_SLIDE = 26
FX_PAN_SLIDE       = 27
FX_TREMOR          = 28
FX_XFINE_PORTA_UP  = 29
FX_XFINE_PORTA_DOWN = 30
FX_KEY_OFF         = 31
FX_CHANNEL_VOLUME  = 32
FX_PATTERN_LOOP    = 33

# ── Colonne de volume (XM/IT) ─────────────────────────────────────────
# MOD et S3M n'en ont pas ; elle vaut alors toujours VOL_NONE. Ce n'est pas
# un effet ordinaire : elle se joue EN PLUS de la colonne d'effet, et une
# valeur y est un réglage, pas une commande.

VOL_NONE      = 0
VOL_SET       = 1    # poser le volume (0..64)
VOL_SLIDE_UP  = 2
VOL_SLIDE_DOWN = 3
VOL_FINE_UP   = 4
VOL_FINE_DOWN = 5
VOL_VIBRATO   = 6    # profondeur de vibrato
VOL_PAN       = 7    # poser le panoramique
VOL_TONE_PORTA = 8

# ── Bouclage d'un échantillon ─────────────────────────────────────────
LOOP_NONE     = 0
LOOP_FORWARD  = 1
LOOP_PINGPONG = 2

# Notes. La numérotation est celle d'IT — **60 = C-5**, la note qui sonne au
# `c5_speed` de l'échantillon. Les autres formats s'y ramènent à la lecture,
# pour que le lecteur audio n'ait qu'une convention à connaître.
NOTE_NONE = 0
NOTE_OFF  = 255       # relâche (XM/IT) : déclenche le fadeout, pas la coupure
NOTE_C5   = 60

# Période Amiga de C-5 au taux d'origine (8363 Hz) — le 428 de ProTracker.
PERIOD_C5 = 428.0
AMIGA_C5_RATE = 8363.0


@dataclass
class Envelope:
    """Enveloppe de volume ou de panoramique (XM/IT).

    `points` est une liste de (tick, valeur). Le tick est l'horloge de
    l'enveloppe, qui avance d'une unité par tick de lecture — c'est-à-dire
    plus vite quand le morceau est rapide, exactement comme dans les trackers.
    """
    points: list = field(default_factory=list)   # list[tuple[int, int]]
    sustain: int = -1        # index du point de maintien, -1 = aucun
    loop_start: int = -1
    loop_end: int = -1

    @property
    def active(self) -> bool:
        return len(self.points) >= 2

    def value_at(self, tick: int, default: float) -> float:
        """Interpolation linéaire entre les deux points qui encadrent `tick`."""
        if not self.points:
            return default
        if tick <= self.points[0][0]:
            return float(self.points[0][1])
        for (t0, v0), (t1, v1) in zip(self.points, self.points[1:]):
            if tick <= t1:
                if t1 == t0:
                    return float(v1)
                f = (tick - t0) / (t1 - t0)
                return v0 + (v1 - v0) * f
        return float(self.points[-1][1])


@dataclass
class Sample:
    """Un échantillon, ramené à un tableau float32 dans −1..+1.

    Les sources sont en 8 ou 16 bits, signées ou non selon le format ; les
    normaliser À LA LECTURE évite que le lecteur audio ait à savoir d'où vient
    la donnée, et c'est la seule normalisation qu'on s'autorise (le mixeur du
    GBA, lui, travaille bien en 8 bits — d'où le rendu sans interpolation).
    """
    name: str = ""
    data: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    loop_start: int = 0
    loop_end: int = 0          # exclu
    loop_kind: int = LOOP_NONE
    volume: int = 64           # 0..64
    global_volume: int = 64    # 0..64 — IT/S3M, multiplie le précédent
    default_pan: int = -1      # 0..255, -1 = l'échantillon n'a pas d'avis
    c5_speed: int = int(AMIGA_C5_RATE)   # Hz de la note C-5
    relative_note: int = 0     # XM — décalage en demi-tons
    finetune: int = 0          # XM — −128..127, en 1/128 de demi-ton

    @property
    def loops(self) -> bool:
        return self.loop_kind != LOOP_NONE and self.loop_end > self.loop_start


@dataclass
class Instrument:
    """La couche que XM et IT posent entre une note et un échantillon."""
    name: str = ""
    # note (0..119) → index d'échantillon dans Module.samples, -1 = aucun
    sample_of_note: list = field(default_factory=lambda: [-1] * 120)
    vol_env: Envelope = field(default_factory=Envelope)
    pan_env: Envelope = field(default_factory=Envelope)
    fadeout: int = 0           # 0 = pas de fadeout (la note tient jusqu'à la fin)
    global_volume: int = 128   # IT — 0..128


@dataclass
class Cell:
    """Une case de pattern : ce qu'UN canal fait sur UNE ligne."""
    note: int = NOTE_NONE          # 0 = rien, 1..119 = note, NOTE_OFF = relâche
    instrument: int = 0            # 1..N, 0 = inchangé
    vol_fx: int = VOL_NONE
    vol_param: int = 0
    effect: int = FX_NONE
    param: int = 0


@dataclass
class Module:
    """Un module, quel que soit le format d'où il vient."""
    kind: str = "mod"              # mod | s3m | xm | it — pour l'affichage
    name: str = ""
    num_channels: int = 4
    speed: int = 6                 # ticks par ligne
    bpm: int = 125
    global_volume: int = 64        # 0..64
    linear_freq: bool = False      # XM/IT en mode linéaire
    amiga_table: bool = False      # MOD : périodes prises dans la table ProTracker
    # Deux traits qui séparent ProTracker de tous les autres, et qu'il vaut
    # mieux porter que deviner dans le lecteur :
    #   - `slide_scale` : ProTracker glisse d'UNE unité de période par point de
    #     paramètre ; S3M, XM et IT comptent en QUARTS d'unité. Sans ça, un
    #     portamento sonne quatre fois trop vite ou quatre fois trop lent.
    #   - `effect_memory` : un paramètre nul REPREND le précédent en S3M/XM/IT.
    #     En ProTracker, « A00 » ne fait rien du tout.
    slide_scale: float = 1.0
    effect_memory: bool = False
    order: list = field(default_factory=list)          # list[int]
    patterns: list = field(default_factory=list)       # list[list[list[Cell]]]
    samples: list = field(default_factory=list)        # list[Sample]
    instruments: list = field(default_factory=list)    # list[Instrument], vide si aucun
    channel_pan: list = field(default_factory=list)    # 0..255 par canal
    channel_volume: list = field(default_factory=list) # 0..64 par canal

    def rows(self, pattern_idx: int) -> int:
        """Le nombre de lignes de ce pattern — 64 en MOD, variable ailleurs."""
        return len(self.patterns[pattern_idx]) if 0 <= pattern_idx < len(self.patterns) else 0


# ── Reconnaissance du format : par le CONTENU, jamais par l'extension ──
#
# La v0.8.1 l'a mesuré : le tri par extension laisse passer un fichier
# renommé et refuse un fichier valide mal nommé. Les quatre signatures sont à
# des offsets fixes, et un module trop court pour les porter n'en est pas un.

_SIGNATURES = (
    (0x00, b"Extended Module: ", "xm"),
    (0x00, b"IMPM", "it"),
    (0x2C, b"SCRM", "s3m"),
)

# Tags ProTracker à l'offset 1080. Le MOD n'a pas de signature en tête : c'est
# le dernier essayé, et c'est pourquoi il est reconnu par sa liste de tags.
_MOD_TAGS = frozenset({
    b"M.K.", b"M!K!", b"FLT4", b"4CHN", b"6CHN", b"8CHN", b"FLT8", b"CD81",
    b"OKTA", b"16CN", b"32CN", b"2CHN",
})


def detect_format(data: bytes) -> str | None:
    """« mod » / « s3m » / « xm » / « it », ou None si ce n'en est aucun."""
    for offset, magic, kind in _SIGNATURES:
        if data[offset:offset + len(magic)] == magic:
            return kind
    if len(data) >= 1084 and data[1080:1084] in _MOD_TAGS:
        return "mod"
    return None


def load_module(path) -> Module:
    """Lit un module, quel que soit son format. Lève ValueError si ce n'en est pas un.

    Le dispatch se fait sur la SIGNATURE du fichier, jamais sur son extension,
    et les quatre lecteurs sont importés à la demande : ouvrir un projet ne
    doit pas charger le lecteur d'un format que personne n'emploie.
    """
    path = Path(path)
    data = path.read_bytes()
    kind = detect_format(data)
    if kind is None:
        raise ValueError("unrecognised module format (neither MOD, S3M, XM nor IT)")
    if kind == "mod":
        from .mod_file import parse_mod
        return parse_mod(data)
    if kind == "s3m":
        from .s3m_file import parse_s3m
        return parse_s3m(data)
    if kind == "xm":
        from .xm_file import parse_xm
        return parse_xm(data)
    from .it_file import parse_it
    return parse_it(data)
