"""
core/wav_edit.py — ce qu'on fait à un WAV avant qu'il devienne de la ROM : le rogner, et fondre ses bords.

Un effet, une musique WAV et un jingle WAV partent du même geste — garder une plage du fichier, sans jamais le réécrire,
et le fondre aux deux bouts pour que la coupe ne claque pas. Ce module est cet unique endroit : `core/sfx_render.py` (un
effet) et `core/wav_module.py` (une piste WAV encapsulée en module) en dépendent tous deux, donc le build, l'aperçu et
l'écran voient la même plage. Un module tracker ne se rogne pas : ses plages sont des sections en positions d'ordre.

Les champs d'un asset sont lus par DUCK TYPING (`trim_start`, `trim_end`, `fade_in`, `fade_out`) : un `Sfx`, une `Music` ou un
`Jingle` conviennent, un objet qui n'a pas le champ vaut « rien ».

Convention de la découpe : millisecondes depuis le début du FICHIER ; la fin à 0 veut dire « jusqu'au bout » ; les deux à 0, « le
fichier entier » — ce que lit aussi un sidecar d'avant ces champs.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# Une découpe plus courte ne laisse pas un son : l'écran la refuse à la souris, le validateur la signale.
MIN_TRIM_MS = 10

FRAMES_PER_SECOND = 60             # l'unité des fondus de l'éditeur : la frame de la console


# ── Les fondus ────────────────────────────────────────────────────────

def fade_out_of(asset) -> int:
    """Le fondu de sortie de l'asset, en frames (1/60 s) : 0 = aucun."""
    return max(0, int(getattr(asset, "fade_out", 0) or 0))


def fade_in_of(asset) -> int:
    """Le fondu d'entrée de l'asset, en frames (1/60 s) : 0 = aucun."""
    return max(0, int(getattr(asset, "fade_in", 0) or 0))


def apply_fades(data: np.ndarray, rate: float, fade_in: int, fade_out: int) -> np.ndarray:
    """Les fondus (en frames) cuits dans les premiers et les derniers échantillons de `data` (mono, flottant), à `rate` Hz.

    Rampe linéaire, depuis un zéro EXACT sur le premier échantillon et jusqu'à un zéro EXACT sur le dernier : c'est ce zéro qui
    supprime le clic d'une coupe en plein signal. Plus long que le signal, un fondu le couvre en entier. Rend `data` tel quel
    s'il n'y a rien à fondre, une copie sinon."""
    ramp_in = min(int(data.size), round(max(0, fade_in) * rate / FRAMES_PER_SECOND))
    ramp_out = min(int(data.size), round(max(0, fade_out) * rate / FRAMES_PER_SECOND))
    if ramp_in <= 0 and ramp_out <= 0:
        return data
    data = data.copy()
    if ramp_in > 0:
        data[:ramp_in] *= np.linspace(0.0, 1.0, ramp_in, dtype=np.float32)
    if ramp_out > 0:
        data[-ramp_out:] *= np.linspace(1.0, 0.0, ramp_out, dtype=np.float32)
    return data


# ── La découpe ────────────────────────────────────────────────────────

def trim_of(asset) -> tuple[int, int]:
    """`(début, fin)` en ms depuis le début du fichier, tels que l'asset les porte. Fin à 0 : jusqu'à la fin du fichier."""
    return max(0, int(getattr(asset, "trim_start", 0) or 0)), max(0, int(getattr(asset, "trim_end", 0) or 0))


def is_trimmed(asset) -> bool:
    start, end = trim_of(asset)
    return start > 0 or end > 0


def trim_window(asset, total_ms: float) -> tuple[int, int]:
    """La plage gardée, en ms, bornée au fichier : `(début, fin)` avec `fin` jamais à 0. Ce que l'écran dessine."""
    start, end = trim_of(asset)
    total = max(0, round(total_ms))
    end = total if end == 0 else min(end, total)
    return min(start, end), end


def trim_problem(asset, total_ms: float) -> Optional[str]:
    """Pourquoi cette découpe ne donne pas un son, ou None : la plage est vide, ou plus courte que `MIN_TRIM_MS`."""
    start, end = trim_of(asset)
    if start == 0 and end == 0:
        return None
    total = round(total_ms)
    if start >= total:
        return f"the trim starts at {start} ms, past the end of the file ({total} ms)."
    kept = (total if end == 0 else min(end, total)) - start
    if kept < MIN_TRIM_MS:
        return f"the trim keeps {max(0, kept)} ms of the file ; the shortest it can keep is {MIN_TRIM_MS} ms."
    return None


def kept_range(asset, frames: int, rate: int) -> Optional[tuple[int, int]]:
    """`(première, dernière + 1)` frame gardées d'un fichier de `frames` frames à `rate` Hz, ou None si la découpe ne
    laisse rien. Les ms se convertissent À LA FRAME : l'arrondi se fait une fois, ici."""
    start, end = trim_of(asset)
    return kept_frames(start, end, frames, rate)


def kept_frames(start_ms: int, end_ms: int, frames: int, rate: int) -> Optional[tuple[int, int]]:
    """`kept_range` pour une plage donnée en ms (`end_ms` à 0 : jusqu'au bout) plutôt que par un asset."""
    first = min(frames, round(max(0, start_ms) * rate / 1000))
    last = frames if end_ms <= 0 else min(frames, round(end_ms * rate / 1000))
    return (first, last) if last > first else None
