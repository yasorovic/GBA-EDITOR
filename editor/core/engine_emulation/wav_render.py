"""
core/engine_emulation/wav_render.py — Une piste `.wav` rendue comme la ROM la jouera.

C'est ce que `module_render` fait pour un module : produire du PCM stéréo
int16 à `GBA_MIX_RATE`, directement jouable par le `MusicDeck`. Une piste n'a pas
de repères de motif, donc le `Track` rendu n'a pas de `marks`.

Elle passe par le MÊME chemin que le build (`core/wav_module`) : le taux choisi
(`Music.sample_rate`), la quantification à 8 bits, et la boucle d'échantillon calée
sur un passage par zéro. L'aperçu ne joue pas la source, il joue ce que la ROM
contiendra — avec la même perte, sinon un taux trop bas ne s'entendrait qu'après
un build.
"""
from __future__ import annotations

import numpy as np

from core import wav_module
from core.engine_emulation.module_render import GBA_MIX_RATE
from core.engine_emulation.music_deck import Track


def render_wav(path, mix_rate: int = GBA_MIX_RATE, sample_rate: int = 0,
               loop_ms: tuple[int, int] | None = None) -> Track:
    """Lit un WAV PCM 8/16 bits et le rend en stéréo à `mix_rate`.

    `sample_rate` est celui de `Music.sample_rate` (0 = le défaut) et `loop_ms` la
    section de boucle, en millisecondes : avec elle, le `Track` porte une boucle
    d'échantillon et ne contient que ce que la ROM garde (intro + boucle).

    Lève `ValueError` pour une profondeur que mmutil ne convertit pas non plus, ou
    pour une boucle trop courte.
    """
    rate = wav_module.effective_rate(sample_rate)
    built = wav_module.render_at_rate(path, rate)       # mono 8 bits, comme dans le module
    if built.size == 0:
        return Track(pcm=np.zeros((0, 2), dtype=np.int16))

    loop = None
    if loop_ms is not None:
        start, end = wav_module.loop_frames(built, rate, loop_ms)
        built = built[:end]
        loop = (start, end)

    # Le mixeur de la console ne lisse pas : chaque échantillon est tenu jusqu'au
    # suivant (rendu « sans interpolation », comme `module_render`).
    n_out = max(1, round(built.size * mix_rate / rate))
    index = np.minimum((np.arange(n_out) * rate) // mix_rate, built.size - 1)
    mono = (built[index].astype(np.float32) / 127.0 * 32767.0).astype(np.int16)
    sample_loop = None
    if loop is not None:
        sample_loop = (min(n_out - 1, round(loop[0] * mix_rate / rate)), n_out)
    return Track(pcm=np.stack([mono, mono], axis=1), sample_loop=sample_loop)
