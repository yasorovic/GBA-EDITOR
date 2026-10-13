"""
engine_emulation/module_stream.py — un module joué EN DIRECT, tick par tick.

`render_module_marked` rend un morceau entier d'avance : bon pour dessiner l'onde et pour les boîtes, mais un
tempo ou une hauteur qu'on change pendant l'écoute obligerait à tout refaire. Ici le rendu suit la carte son :
`StreamTrack` ne produit un tick que quand le deck en a besoin, et lit le tempo et la hauteur AU MOMENT de le
produire (cf. `TickState`) — un curseur qui bouge s'entend au tick suivant, sans rendu en arrière-plan ni saut.

C'est un `Track` pour le deck : mêmes champs de réglages (section de boucle, fondus), mêmes questions
(`order_at`, `start_of`, `restart_at`), donc la boucle, la section, les fondus et le volume restent ceux de
`MusicDeck` — un seul endroit où la ROM est rejouée. Ce qui change est la nature du PCM :

  - il se remplit à la demande (`ensure`) et se lit par tranches ; les échantillons trop anciens sont oubliés ;
  - une position d'ordre n'est plus un décalage dans un rendu fini : `start_of(ordre)` DEMANDE le saut au rendu
    (`mmPosition`) et rend l'endroit où le nouveau son commencera. Les canaux gardent ce qu'ils jouaient — le
    saut ne réinitialise rien, comme sur la console.
"""
from __future__ import annotations

from bisect import bisect_right
from typing import Optional

import numpy as np

from .module_model import ORDER_END, ORDER_SKIP, Module
from .module_render import GBA_MIX_RATE, TickState, iter_module_ticks, to_stereo16
from .music_deck import Track

# Combien de temps de son déjà produit on garde derrière la tête de lecture.
_KEEP_SECONDS = 3.0


class _LazyPCM:
    """Ce que le deck prend pour `track.pcm` : une longueur et des tranches, remplies par le rendu."""

    def __init__(self, owner: "StreamTrack"):
        self._owner = owner

    @property
    def shape(self) -> tuple:
        return (self._owner.rendered, 2)

    def __getitem__(self, key: slice) -> np.ndarray:
        return self._owner.slice(key.start or 0, key.stop)


class StreamTrack(Track):
    def __init__(self, mod: Module, mix_rate: int = GBA_MIX_RATE, *, tempo: float = 1.0, pitch: float = 1.0,
                 loop_orders: Optional[tuple] = None, fade_in: int = 0, fade_out: int = 0,
                 reference: Optional[Track] = None):
        self._mod, self._mix = mod, mix_rate
        self._state = TickState(tempo=tempo, pitch=pitch)
        self._gen = iter_module_ticks(mod, mix_rate, self._state, guard=False)
        self._chunks: list = []          # int16 (n, 2), un par tick
        self._starts: list = []          # décalage absolu du début de chaque tick
        self._ticks: list = []           # (ordre, ligne) de chaque tick
        self._end = 0                    # décalage absolu de la fin de ce qui est produit
        self._finished = False           # le morceau est arrivé au bout : il attend un saut
        self.reference = reference       # le rendu entier (onde, repères) : la frise sur laquelle on situe la tête
        super().__init__(pcm=_LazyPCM(self), marks={}, restart=mod.restart, order_count=len(mod.order),
                         loop_orders=loop_orders, fade_in=fade_in, fade_out=fade_out)

    # ── Ce que l'écran règle pendant qu'on écoute ─────────────────

    def set_tuning(self, tempo: float, pitch: float) -> None:
        """Pris au tick suivant : le tick en cours est déjà produit."""
        self._state.tempo, self._state.pitch = tempo, pitch

    # ── Le PCM à la demande ───────────────────────────────────────

    @property
    def rendered(self) -> int:
        return self._end

    def ensure(self, upto: int) -> None:
        """Produit des ticks jusqu'à ce que `upto` soit couvert, ou que le morceau soit fini."""
        while not self._finished and self._end < upto:
            order, row, rendered = next(self._gen)
            if order is None:
                self._finished = True
                return
            if rendered is None:
                continue
            stereo = to_stereo16(rendered[0], rendered[1])
            self._starts.append(self._end)
            self._ticks.append((order, row))
            self._chunks.append(stereo)
            self._end += stereo.shape[0]

    def slice(self, start: int, stop: int) -> np.ndarray:
        stop = self._end if stop is None else min(stop, self._end)
        start = max(0, start)
        self._forget(start)
        if stop <= start or not self._chunks:
            return np.zeros((0, 2), dtype=np.int16)
        first = max(0, bisect_right(self._starts, start) - 1)
        parts = []
        for index in range(first, len(self._chunks)):
            offset = self._starts[index]
            if offset >= stop:
                break
            chunk = self._chunks[index]
            parts.append(chunk[max(0, start - offset):max(0, stop - offset)])
        out = np.concatenate(parts) if parts else np.zeros((0, 2), dtype=np.int16)
        if start < self._starts[0]:                      # déjà oublié : du silence plutôt qu'une erreur
            out = np.concatenate([np.zeros((min(self._starts[0], stop) - start, 2), dtype=np.int16), out])
        return out

    def _forget(self, position: int) -> None:
        """Oublie ce qui est loin derrière la tête de lecture : un morceau en boucle ne doit pas grossir sans fin."""
        horizon = position - round(self._mix * _KEEP_SECONDS)
        drop = bisect_right(self._starts, horizon) - 1
        if drop > 0:
            del self._chunks[:drop], self._starts[:drop], self._ticks[:drop]

    # ── Les questions du deck ─────────────────────────────────────

    def order_at(self, pos: int) -> int:
        """L'ordre joué à cet échantillon — ce que rend `mmGetPosition`. Lu sur les ticks réellement produits :
        un ordre rejoué par une boucle est le BON ordre, pas le premier rendu."""
        index = bisect_right(self._starts, pos) - 1
        return self._ticks[index][0] if 0 <= index < len(self._ticks) else 0

    def tick_info(self, pos: int) -> tuple[int, int]:
        """(ordre, ligne) du tick joué à cet échantillon."""
        index = bisect_right(self._starts, pos) - 1
        return self._ticks[index] if 0 <= index < len(self._ticks) else (0, 0)

    def _landing(self, order: int) -> Optional[int]:
        """Où tombe `mmPosition(order)` : un séparateur (254) tombe sur le pattern SUIVANT, un 255 ou une
        position hors table n'a pas de musique (mesuré sur ROM le 2026-10-11)."""
        table = self._mod.order
        if order < 0:
            return None
        while order < len(table) and table[order] == ORDER_SKIP:
            order += 1
        if order >= len(table) or table[order] == ORDER_END:
            return None
        return order

    def _seek(self, order: int, row: int = 0) -> int:
        """Demande le saut au rendu et rend l'endroit où le nouveau son commencera."""
        self._state.jump_to, self._state.jump_row = order, row
        self._finished = False
        return self._end

    def start_of(self, order: int, row: int = 0) -> Optional[int]:
        landing = self._landing(order)
        if landing is None:
            return None
        return self._seek(landing, row if landing == order else 0)   # un séparateur sauté : le début du suivant

    def locate(self, seconds: float, mix_rate: int) -> Optional[tuple[int, int]]:
        """L'inverse de `song_seconds` : (ordre, ligne) à cet instant de la frise, ou None sans frise."""
        ref = self.reference
        if ref is None or not ref.marks:
            return None
        pos = int(seconds * mix_rate)
        order = ref.order_at(pos)
        start = ref.marks.get(order, 0)
        later = [offset for offset in ref.marks.values() if offset > start]
        end = min(later) if later else int(ref.pcm.shape[0])
        pattern = self._mod.order[order] if order < len(self._mod.order) else None
        if pattern is None or pattern >= len(self._mod.patterns):
            return order, 0
        rows = len(self._mod.patterns[pattern])
        return order, max(0, min(rows - 1, int((pos - start) / max(1, end - start) * rows)))

    @property
    def restart_at(self) -> int:
        landing = self._landing(self.restart)
        return self._seek(landing if landing is not None else 0)

    def rewind(self) -> int:
        return self.restart_at

    # ── Où en est la lecture, sur la frise de l'écran ─────────────

    def song_seconds(self, pos: int, mix_rate: int) -> float:
        """La position du morceau (pas du flux : celui-ci grandit à chaque tour de boucle), située sur le rendu entier
        qui sert à dessiner l'onde — par l'ordre et la ligne de la tête de lecture."""
        ref = self.reference
        if ref is None or not ref.marks:
            return 0.0
        order, row = self.tick_info(pos)
        if order not in ref.marks:
            return 0.0
        start = ref.marks[order]
        later = [offset for offset in ref.marks.values() if offset > start]
        end = min(later) if later else int(ref.pcm.shape[0])
        pattern = self._mod.order[order]
        rows = len(self._mod.patterns[pattern]) if pattern < len(self._mod.patterns) else 1
        return (start + (row / max(1, rows)) * (end - start)) / mix_rate

    def total_seconds(self, mix_rate: int) -> float:
        return 0.0 if self.reference is None else int(self.reference.pcm.shape[0]) / mix_rate
