"""
engine_emulation/music_deck.py — La couche MODULE, telle que la ROM la pilote.

Pendant exact de `music_transition_tick()` / `music_loop_tick()` (main.c) et des
entrées `music_play` / `music_stop` / `music_fade_to` / `music_cut_to`
(gba_engine.h). Le but n'est pas de faire « quelque chose qui ressemble » : c'est de
laisser régler une transition, une section de boucle ou un fondu dans l'éditeur et
d'entendre CE QUE LA ROM FERA, sans build.

Ce que la ROM tient, et donc ce qui est reproduit ici :

    fondu traversant   le volume tombe à zéro en n/2 frames, l'autre module
                       DÉMARRE là — c'est le creux assumé —, puis remonte.
                       Il n'y a pas de fondu enchaîné : une seule couche.
    coupe à la position on attend la frontière de motif, puis on démarre
                       l'autre module au MÊME index d'ordre. Sans creux.
    fondu d'entrée     `Music.fade_in` : le volume monte de zéro à `music_play`.
    fondu de sortie    `Music.fade_out` : à `music_stop`, le volume tombe à zéro
                       puis le module s'arrête. Ce sont deux MODES (3 et 4) du même
                       pas par frame que les transitions : un seul point d'écriture
                       du volume, comme dans le C.
    section de boucle  `Music.loop_section` : chaque frame, si la position d'ordre
                       a atteint la fin de la section, on revient à son début ; une
                       sortie par l'arrière (le module qui rebouclait seul) est
                       renvoyée au début. Un module à section boucle QUEL QUE SOIT son
                       drapeau : sans la section il s'arrêterait (`music_mode`).
    boucle d'échantillon  un WAV à section : l'échantillon boucle lui-même, le module
                       ne finit plus (cf. `core/wav_module`).

Ce qui n'est PAS reproduit, parce que la ROM ne le fait pas non plus :
`MusicState.intensity` et sa cible ne sont pas émis par le codegen (le C ne
pose que l'id, la boucle et le volume). Un aperçu qui les jouerait ferait
régler à l'oreille un effet que la ROM n'aura pas.

Sans Qt : cette classe dit quels échantillons sortent, pas comment les jouer.
"""
from __future__ import annotations

import functools
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .module_render import ChannelLevels

# Une frame de VBlank. Le stepper du runtime tourne une fois par frame, et
# c'est cette horloge-là qui donne au fondu sa durée exacte.
FRAME_HZ = 60

# L'échelle de `mmSetModuleVolume` (cf. models/audio.volume_to_module).
MODULE_FULL = 1024

# Le scrub : la vitesse de lecture suit le geste, bornée en multiples de la vitesse normale ; et la part de
# l'écart restant à la cible que chaque paquet rattrape (plus c'est grand, plus le son colle au pointeur).
_SCRUB_MAX_RATE = 6.0
_SCRUB_FOLLOW = 0.8

# Les modes du pas par frame — les mêmes nombres que `g_mtr_mode` dans main.c.
_NONE, _CROSSFADE, _CUT, _FADE_IN, _FADE_OUT = 0, 1, 2, 3, 4


def _locked(method):
    """Le deck est produit par le thread audio (`pull`) et piloté par celui de l'interface : une seule main à la fois."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


@dataclass
class _Scrub:
    """Le son qui suit la main : le rendu entier lu à la position `pos` (en échantillons, fractionnaire), qui court
    vers `target`."""
    pcm: np.ndarray
    pos: float
    target: float


@dataclass
class Track:
    """Un module rendu, prêt à sonner, avec ses frontières de motif.

    Pas de `loop` ici : sur maxmod, la boucle est un paramètre de `mmStart`,
    pas une propriété du module. Le poser sur le Track — qui est mis en cache
    par fichier — ferait que deux états partageant une piste se marcheraient
    dessus.

    Les champs qui suivent `order_count` sont les RÉGLAGES de l'asset, tels que la
    ROM les lit (`core/music_structure.music_info_row`) : ils ne changent pas ce que
    le fichier rend, seulement comment le deck le joue.
    """
    pcm: np.ndarray                       # (n, 2) int16
    marks: dict = field(default_factory=dict)   # index d'ordre -> échantillon
    restart: int = 0                      # index d'ordre où `MM_PLAY_LOOP` reboucle
    order_count: int = 0                  # longueur de la table BRUTE ; 0 = sans structure
    loop_orders: Optional[tuple] = None   # section de boucle : positions d'ordre [début, fin)
    fade_in: int = 0                      # frames
    fade_out: int = 0                     # frames
    levels: Optional[ChannelLevels] = None   # le pic de chaque canal par tick ; None pour un rendu en direct

    @property
    def forces_loop(self) -> bool:
        """Une section de boucle fait boucler le module quel que soit son drapeau."""
        return self.loop_orders is not None

    @property
    def restart_at(self) -> int:
        """L'échantillon où la boucle reprend : le début de l'ordre de restart.

        C'est ce que la ROM fait de la position de restart du fichier ; reboucler
        à 0 aurait rejoué une intro que la console ne rejoue pas."""
        return self.marks.get(self.restart, 0)

    def order_at(self, pos: int) -> int:
        """L'index d'ordre joué à cet échantillon — ce que rend `mmGetPosition`."""
        best, best_off = 0, -1
        for order, off in self.marks.items():
            if best_off <= off <= pos:
                best, best_off = order, off
        return best

    def rewind(self) -> int:
        """Où le deck reprend quand un module qui boucle arrive à sa fin : son ordre de restart."""
        return min(self.restart_at, max(0, int(self.pcm.shape[0]) - 1))

    def song_seconds(self, pos: int, mix_rate: int) -> float:
        """La position DANS LE MORCEAU, en secondes (un rendu en direct la situe sur une frise, cf. module_stream)."""
        return pos / mix_rate

    def total_seconds(self, mix_rate: int) -> float:
        return int(self.pcm.shape[0]) / mix_rate

    def start_of(self, order: int, row: int = 0) -> Optional[int]:
        """L'échantillon où commence cet index d'ordre — `mmPosition(pat)` — ou None
        si la piste n'a PAS de musique à cette position.

        Mesuré sur ROM le 2026-10-11 : un séparateur (254) tombe sur le pattern
        SUIVANT ; une position hors table, ou un 255, n'a pas de musique — c'est
        à l'appelant de dire ce qui suit, car cela dépend du mode de lecture. Une
        piste sans repères (un WAV) n'a pas de structure à violer : le début.

        `row` n'a de sens que pour un rendu en direct (cf. module_stream) : un rendu fini se lit à l'ordre.
        """
        if not self.marks:
            return 0
        if order in self.marks:
            return self.marks[order]
        if order < self.order_count:
            later = [k for k in self.marks if k > order]
            if later:
                return self.marks[min(later)]
        return None


class MusicDeck:
    """L'unique couche de module : ce qui joue, à quelle position, à quel volume.

    Le vocabulaire est celui du runtime — `play`, `music_stop`, `fade_to`, `cut_to` —
    parce que c'est le même mécanisme. Un nom différent ici laisserait croire à un
    second chemin. `stop()` est l'arrêt SEC du lecteur (le bouton Stop) ; `music_stop()`
    est l'appel du jeu, qui passe par le fondu de sortie.
    """

    def __init__(self, mix_rate: int):
        # Réentrant : un appel verrouillé en fait d'autres (`play` → `_start`). Quiconque lit l'intérieur d'un
        # `Track` en direct pendant que le thread audio le remplit (cf. `StreamTrack`) le prend aussi.
        self.lock = threading.RLock()
        self._mix = mix_rate
        # Échantillons par frame. Le volume et la bascule ne bougent QU'ICI,
        # comme la ROM ne les touche qu'au VBlank : un fondu de 30 frames dure
        # exactement une demi-seconde, pas « à peu près ».
        self._frame_len = max(1, round(mix_rate / FRAME_HZ))
        self._until_tick = self._frame_len

        self._track: Track | None = None
        self._loop = True
        self._pos = 0
        self._vol = MODULE_FULL          # volume courant, échelle maxmod
        self._music_vol = MODULE_FULL    # `g_music_vol` : le dernier niveau DEMANDÉ
        self._ended = False              # module non bouclé arrivé au bout
        self._loop_in = False            # `g_mloop_in` : on est entré dans la section

        # L'état de transition — les `g_mtr_*` du runtime, mot pour mot.
        self._mode = _NONE
        self._to: Track | None = None
        self._to_vol = MODULE_FULL
        self._to_loop = True
        self._i = 0
        self._n = 1
        self._row_order = 0              # pour la coupe : l'ordre observé
        self._scrub: Optional[_Scrub] = None

    # ── Ce que la boîte demande ───────────────────────────────────

    @property
    def playing(self) -> bool:
        return self._track is not None and not self._ended

    @property
    def position(self) -> int:
        """Position de lecture actuelle, en échantillons stéréo."""
        return self._pos

    @property
    def track(self) -> Optional[Track]:
        return self._track

    @property
    def duration(self) -> int:
        """Durée du module courant, en échantillons stéréo."""
        return 0 if self._track is None else int(self._track.pcm.shape[0])

    @property
    def looping(self) -> bool:
        return self._loop

    @_locked
    def set_looping(self, enabled: bool):
        """Change la boucle de la lecture en cours et de la transition pendante.

        Un module à section de boucle ne peut pas cesser de boucler : la ROM le
        démarre toujours en `MM_PLAY_LOOP`."""
        forced = self._track is not None and self._track.forces_loop
        self._loop = bool(enabled) or forced
        self._to_loop = bool(enabled)

    @_locked
    def set_volume(self, volume: int):
        """`music_set_volume` : le niveau demandé change, et se fait entendre tout de suite — sauf pendant un
        fondu, où le pas de la frame suivante reprend la rampe vers le nouveau niveau."""
        self._music_vol = volume
        if self._mode == _FADE_IN:
            self._to_vol = volume
        elif self._mode == _NONE:
            self._vol = volume

    @_locked
    def play(self, track: Track, volume: int, loop: bool = True, start_at: int = 0):
        """`music_play` : démarrage sec, sans transition — mais avec le fondu d'entrée.

        `start_at` (en échantillons) n'existe pas dans la ROM : c'est l'aperçu d'une section, qui
        commence à SON début. Un `mmStart` suivi d'un `mmPosition` donnerait la même chose."""
        self._start(track, loop)
        self._pos = max(0, min(int(start_at), max(0, track.pcm.shape[0] - 1)))
        self._music_vol = volume
        if track.fade_in > 1:
            # Le volume part de zéro et monte : c'est le mode 3 du pas par frame.
            self._vol = 0
            self._mode, self._to_vol, self._i, self._n = _FADE_IN, volume, 0, track.fade_in
        else:
            self._vol = volume

    @_locked
    def stop(self):
        """L'arrêt sec : le bouton Stop du lecteur, pas l'appel du jeu."""
        self._scrub = None
        self._track = None
        self._mode = _NONE

    @_locked
    def music_stop(self):
        """`music_stop()` : avec un fondu de sortie, la musique s'éteint puis s'arrête."""
        if self._mode == _FADE_OUT:
            return                                   # déjà en train de s'éteindre
        track = self._track
        if track is not None and track.fade_out > 1 and self.playing:
            self._mode, self._to_vol = _FADE_OUT, self._music_vol
            self._i, self._n = 0, track.fade_out
            return
        self.stop()

    @_locked
    def fade_to(self, track: Track, volume: int, frames: int,
                loop: bool = True):
        """`music_fade_to`. Sous deux frames, il n'y a pas de fondu à jouer."""
        if frames < 2 or not self.playing:
            self.play(track, volume, loop)
            return
        self._mode, self._to, self._to_vol = _CROSSFADE, track, volume
        self._to_loop = loop
        self._i, self._n = 0, frames

    @_locked
    def cut_to(self, track: Track, volume: int, loop: bool = True):
        """`music_cut_to`. Rien ne joue = aucune position à respecter."""
        if not self.playing:
            self.play(track, volume, loop)
            return
        self._mode, self._to, self._to_vol = _CUT, track, volume
        self._to_loop = loop
        self._row_order = self._track.order_at(self._pos)

    def _start(self, track: Track, loop: bool):
        """`mmStart` suivi de `music_apply` : le module démarre, ses réglages s'appliquent."""
        self._track, self._pos = track, 0
        self._scrub = None
        self._loop = loop or track.forces_loop
        self._ended = False
        self._loop_in = False
        self._mode = _NONE

    # ── L'horloge ─────────────────────────────────────────────────

    def _tick(self):
        """Une frame : `music_transition_tick()` puis `music_loop_tick()`."""
        self._transition_tick()
        self._loop_tick()

    def _transition_tick(self):
        if self._mode == _NONE:
            return
        if self._mode == _FADE_IN:
            self._i += 1
            if self._i >= self._n:
                self._vol = self._to_vol
                self._mode = _NONE
            else:
                self._vol = self._to_vol * self._i // self._n
            return
        if self._mode == _FADE_OUT:
            self._i += 1
            if self._i >= self._n:
                self.stop()
            else:
                self._vol = self._to_vol * (self._n - self._i) // self._n
            return
        if self._mode == _CROSSFADE:
            # Fondu traversant. La bascule tombe à la moitié, quand le volume
            # est à zéro : c'est là qu'un changement s'entend le moins.
            half = self._n // 2
            self._i += 1
            if self._i < half:
                self._vol = self._to_vol * (half - self._i) // max(1, half)
            elif self._i == half:
                self._start(self._to, self._to_loop)
                self._mode = _CROSSFADE              # `_start` l'a remis à zéro
                self._vol = 0
            elif self._i >= self._n:
                self._vol = self._to_vol
                self._music_vol = self._to_vol
                self._mode = _NONE
            else:
                k, n = self._i - half, self._n - half
                self._vol = self._to_vol * k // max(1, n)
            return

        # Coupe à la position. Le runtime guette le retour en arrière de la
        # LIGNE ; ici on guette le changement d'index d'ordre, qui est la même
        # frontière et se lit directement sur les repères du rendu.
        order = self._track.order_at(self._pos)
        if order != self._row_order:
            target = self._to
            land = target.start_of(order)
            self._start(target, self._to_loop)
            if land is None and self._loop:
                # Mesuré : sans musique à cette position, MM_PLAY_LOOP redémarre la
                # cible à son restart…
                land = target.restart_at
            self._pos = land or 0
            # …et MM_PLAY_ONCE l'arrête.
            self._ended = land is None
            self._vol = self._to_vol
            self._music_vol = self._to_vol
        else:
            self._row_order = order

    def _loop_tick(self):
        """`music_loop_tick()` : tenir la position dans la section de boucle."""
        track = self._track
        if track is None or self._ended or track.loop_orders is None:
            return
        start, end = track.loop_orders
        order = track.order_at(self._pos)
        if order >= end:
            self._jump_to_order(start)
            self._loop_in = True
        elif order >= start:
            self._loop_in = True
        elif self._loop_in:
            # Une sortie par l'ARRIÈRE : le module a rebouclé tout seul (une boucle qui
            # va jusqu'à la fin du morceau, ou un saut), et on le renvoie au début.
            self._jump_to_order(start)

    @_locked
    def seek_to_order(self, order: int):
        """Pose la tête de lecture au début de cet ordre — le saut `mmPosition`, à l'ordre près : la console
        ne sait pas repartir d'une ligne. Quitter la section de boucle par l'arrière n'est pas une boucle qui
        déborde : on le dit au deck, qui ne ramène donc pas la lecture au début de la section."""
        if self._track is not None and not self._ended:
            self._jump_to_order(order)
            self._loop_in = False

    @property
    def scrubbing(self) -> bool:
        return self._scrub is not None

    @property
    def scrub_position(self) -> float:
        """Où le scrub lit le rendu entier, en échantillons."""
        return 0.0 if self._scrub is None else self._scrub.pos

    @property
    def scrub_target(self) -> float:
        """Où la main tient la tête de lecture, en échantillons : c'est là qu'on la dessine, le son la rattrape."""
        return 0.0 if self._scrub is None else self._scrub.target

    @_locked
    def scrub_to(self, pcm: np.ndarray, target: float, start: float):
        """La main tient la tête de lecture : la lecture automatique se met en pause et le son court vers `target`
        (en échantillons du rendu entier `pcm`) à la vitesse du geste — vers l'arrière aussi — puis se tait quand la
        main s'arrête. `start` : d'où le son part au premier appel."""
        if self._scrub is None:
            self._scrub = _Scrub(pcm, float(start), float(target))
        self._scrub.target = float(target)

    @_locked
    def scrub_end(self):
        """La main lâche : la lecture reprend où l'appelant la repose (cf. `seek_to_row`)."""
        self._scrub = None

    def _scrub_chunk(self, n: int) -> np.ndarray:
        s = self._scrub
        total = int(s.pcm.shape[0])
        step = max(-_SCRUB_MAX_RATE * n, min(_SCRUB_MAX_RATE * n, (s.target - s.pos) * _SCRUB_FOLLOW))
        if total == 0 or abs(step) < 0.02 * n:                     # la main est arrêtée : silence
            return np.zeros((n, 2), dtype=np.int16)
        where = np.clip(s.pos + np.arange(n) * (step / n), 0, total - 1)
        low = where.astype(np.int64)
        high = np.minimum(low + 1, total - 1)
        frac = (where - low)[:, None]
        block = s.pcm[low] * (1.0 - frac) + s.pcm[high] * frac
        s.pos = float(np.clip(s.pos + step, 0, total - 1))
        return (block * min(1.0, self._vol / MODULE_FULL)).astype(np.int16)

    @_locked
    def seek_to_row(self, order: int, row: int):
        """Comme `seek_to_order`, mais à une ligne du motif : ce que ne sait pas la console, et que l'aperçu
        s'autorise pour qu'on puisse poser la tête de lecture où l'on veut."""
        if self._track is not None and not self._ended:
            self._jump_to_order(order, row)
            self._loop_in = False

    def _jump_to_order(self, order: int, row: int = 0):
        """`mmPosition(order)`."""
        land = self._track.start_of(order, row)
        if land is not None:
            self._pos = land

    # ── La sortie ─────────────────────────────────────────────────

    @_locked
    def pull(self, n: int) -> np.ndarray:
        """Produit `n` échantillons stéréo, en faisant tourner l'horloge."""
        if self._scrub is not None:
            return self._scrub_chunk(n)
        out = np.zeros((n, 2), dtype=np.int16)
        done = 0
        while done < n:
            if self._until_tick == 0:
                self._tick()
                self._until_tick = self._frame_len
            step = min(n - done, self._until_tick)
            out[done:done + step] = self._chunk(step)
            done += step
            self._until_tick -= step
        return out

    def _chunk(self, n: int) -> np.ndarray:
        """`n` échantillons du module courant, bouclés et mis au volume."""
        track = self._track
        if track is None or self._ended:
            return np.zeros((n, 2), dtype=np.int16)
        ensure = getattr(track, "ensure", None)          # un rendu en direct produit ce qu'on lui demande
        if ensure is None and track.pcm.shape[0] == 0:
            return np.zeros((n, 2), dtype=np.int16)
        parts, need, rewinds = [], n, 0
        while need > 0:
            if ensure is not None:
                ensure(self._pos + need)
            total = track.pcm.shape[0]
            if self._pos >= total:
                if not self._loop or rewinds >= 2:
                    # Un module qui ne boucle pas s'arrête, comme MM_PLAY_ONCE.
                    self._ended = True
                    parts.append(np.zeros((need, 2), dtype=np.int16))
                    break
                rewinds += 1
                self._pos = track.rewind()
                continue
            take = min(need, total - self._pos)
            parts.append(track.pcm[self._pos:self._pos + take])
            self._pos += take
            need -= take
        block = np.concatenate(parts) if len(parts) > 1 else parts[0]
        if self._vol >= MODULE_FULL:
            return block
        return (block.astype(np.int32) * self._vol // MODULE_FULL).astype(np.int16)
