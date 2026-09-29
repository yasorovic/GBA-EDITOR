"""
engine_emulation/music_deck.py — La couche MODULE, telle que la ROM la pilote.

Pendant exact de `music_transition_tick()` (main.c) et des deux entrées
`music_fade_to` / `music_cut_to` (gba_engine.h). Le but n'est pas de faire
« quelque chose qui ressemble » : c'est de laisser régler une transition dans
l'éditeur et d'entendre CE QUE LA ROM FERA, sans build.

Ce que la ROM tient, et donc ce qui est reproduit ici :

    fondu traversant   le volume tombe à zéro en n/2 frames, l'autre module
                       DÉMARRE là — c'est le creux assumé —, puis remonte.
                       Il n'y a pas de fondu enchaîné : une seule couche.
    coupe à la position on attend la frontière de motif, puis on démarre
                       l'autre module au MÊME index d'ordre. Sans creux.

Ce qui n'est PAS reproduit, parce que la ROM ne le fait pas non plus :
`MusicState.intensity` et sa cible ne sont pas émis par le codegen (le C ne
pose que l'id, la boucle et le volume). Un aperçu qui les jouerait ferait
régler à l'oreille un effet que la ROM n'aura pas.

Sans Qt : cette classe dit quels échantillons sortent, pas comment les jouer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Une frame de VBlank. Le stepper du runtime tourne une fois par frame, et
# c'est cette horloge-là qui donne au fondu sa durée exacte.
FRAME_HZ = 60

# L'échelle de `mmSetModuleVolume` (cf. models/audio.volume_to_module).
MODULE_FULL = 1024


@dataclass
class Track:
    """Un module rendu, prêt à sonner, avec ses frontières de motif.

    Pas de `loop` ici : sur maxmod, la boucle est un paramètre de `mmStart`,
    pas une propriété du module. Le poser sur le Track — qui est mis en cache
    par fichier — ferait que deux états partageant une piste se marcheraient
    dessus.
    """
    pcm: np.ndarray                       # (n, 2) int16
    marks: dict = field(default_factory=dict)   # index d'ordre -> échantillon

    def order_at(self, pos: int) -> int:
        """L'index d'ordre joué à cet échantillon — ce que rend `mmGetPosition`."""
        best, best_off = 0, -1
        for order, off in self.marks.items():
            if best_off <= off <= pos:
                best, best_off = order, off
        return best

    def start_of(self, order: int) -> int:
        """L'échantillon où commence cet index d'ordre — `mmPosition(pat)`.

        Un ordre absent (l'autre module est plus court) retombe sur 0 : c'est
        ce que fait maxmod d'une position hors bornes, et mieux vaut le début
        du morceau qu'un silence inexpliqué.
        """
        return self.marks.get(order, 0)


class MusicDeck:
    """L'unique couche de module : ce qui joue, à quelle position, à quel volume.

    Le vocabulaire est celui du runtime — `play`, `fade_to`, `cut_to` — parce
    que c'est le même mécanisme. Un nom différent ici laisserait croire à un
    second chemin.
    """

    def __init__(self, mix_rate: int):
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
        self._ended = False              # module non bouclé arrivé au bout

        # L'état de transition — les `g_mtr_*` du runtime, mot pour mot.
        self._mode = 0                   # 0 rien, 1 fondu, 2 coupe
        self._to: Track | None = None
        self._to_vol = MODULE_FULL
        self._to_loop = True
        self._i = 0
        self._n = 1
        self._row_order = 0              # pour la coupe : l'ordre observé

    # ── Ce que la boîte demande ───────────────────────────────────

    @property
    def playing(self) -> bool:
        return self._track is not None and not self._ended

    @property
    def position(self) -> int:
        """Position de lecture actuelle, en échantillons stéréo."""
        return self._pos

    @property
    def duration(self) -> int:
        """Durée du module courant, en échantillons stéréo."""
        return 0 if self._track is None else int(self._track.pcm.shape[0])

    @property
    def looping(self) -> bool:
        return self._loop

    def set_looping(self, enabled: bool):
        """Change la boucle de la lecture en cours et de la transition pendante."""
        self._loop = bool(enabled)
        self._to_loop = bool(enabled)

    def play(self, track: Track, volume: int, loop: bool = True):
        """`music_play` : démarrage sec, sans transition."""
        self._track, self._pos, self._vol = track, 0, volume
        self._loop, self._ended = loop, False
        self._mode = 0

    def stop(self):
        self._track = None
        self._mode = 0

    def fade_to(self, track: Track, volume: int, frames: int,
                loop: bool = True):
        """`music_fade_to`. Sous deux frames, il n'y a pas de fondu à jouer."""
        if frames < 2 or not self.playing:
            self.play(track, volume, loop)
            return
        self._mode, self._to, self._to_vol = 1, track, volume
        self._to_loop = loop
        self._i, self._n = 0, frames

    def cut_to(self, track: Track, volume: int, loop: bool = True):
        """`music_cut_to`. Rien ne joue = aucune position à respecter."""
        if not self.playing:
            self.play(track, volume, loop)
            return
        self._mode, self._to, self._to_vol = 2, track, volume
        self._to_loop = loop
        self._row_order = self._track.order_at(self._pos)

    # ── L'horloge ─────────────────────────────────────────────────

    def _tick(self):
        """Une frame de `music_transition_tick()`."""
        if not self._mode:
            return
        if self._mode == 1:
            # Fondu traversant. La bascule tombe à la moitié, quand le volume
            # est à zéro : c'est là qu'un changement s'entend le moins.
            half = self._n // 2
            self._i += 1
            if self._i < half:
                self._vol = self._to_vol * (half - self._i) // max(1, half)
            elif self._i == half:
                self._track, self._pos = self._to, 0
                self._loop, self._ended = self._to_loop, False
                self._vol = 0
            elif self._i >= self._n:
                self._vol = self._to_vol
                self._mode = 0
            else:
                k, n = self._i - half, self._n - half
                self._vol = self._to_vol * k // max(1, n)
            return

        # Coupe à la position. Le runtime guette le retour en arrière de la
        # LIGNE ; ici on guette le changement d'index d'ordre, qui est la même
        # frontière et se lit directement sur les repères du rendu.
        order = self._track.order_at(self._pos)
        if order != self._row_order:
            self._track = self._to
            self._pos = self._to.start_of(order)
            self._loop, self._ended = self._to_loop, False
            self._vol = self._to_vol
            self._mode = 0
        else:
            self._row_order = order

    # ── La sortie ─────────────────────────────────────────────────

    def pull(self, n: int) -> np.ndarray:
        """Produit `n` échantillons stéréo, en faisant tourner l'horloge."""
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
        if track is None or self._ended or track.pcm.shape[0] == 0:
            return np.zeros((n, 2), dtype=np.int16)
        total = track.pcm.shape[0]
        parts, need = [], n
        while need > 0:
            if self._pos >= total:
                if not self._loop:
                    # Un module qui ne boucle pas s'arrête, comme MM_PLAY_ONCE.
                    self._ended = True
                    parts.append(np.zeros((need, 2), dtype=np.int16))
                    break
                self._pos = 0
            take = min(need, total - self._pos)
            parts.append(track.pcm[self._pos:self._pos + take])
            self._pos += take
            need -= take
        block = np.concatenate(parts) if len(parts) > 1 else parts[0]
        if self._vol >= MODULE_FULL:
            return block
        return (block.astype(np.int32) * self._vol // MODULE_FULL).astype(np.int16)
