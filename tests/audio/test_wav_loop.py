"""Un WAV avec une section de boucle : l'échantillon boucle, le module ne finit plus.

Mesuré sur ROM le 2026-10-11 (ROADMAP « L'asset .music ») : il faut les DEUX pièces
— la boucle d'échantillon, sans quoi le son s'arrête à la fin de la piste alors que
le module continue ; le saut de position sur la dernière ligne, sans quoi le module
s'arrête et coupe l'échantillon. Ces tests tiennent la structure du module produit ;
la tenue du son lui-même, elle, ne se prouve que sur ROM.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))

from core import wav_module                                          # noqa: E402
from core.engine_emulation.module_model import FX_POSITION_JUMP      # noqa: E402
from core.engine_emulation.xm_file import parse_xm                   # noqa: E402


def _tone(freq: float, seconds: float, rate: int = 44100) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return np.sin(2 * np.pi * freq * t) * 0.6


def _write(path: Path, samples: np.ndarray, rate: int = 44100) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((samples * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def track(tmp_path) -> Path:
    """Intro 300 Hz (0,5 s), corps 800 Hz (1 s), final 1 200 Hz (1 s)."""
    return _write(tmp_path / "track.wav",
                  np.concatenate([_tone(300, 0.5), _tone(800, 1.0), _tone(1200, 1.0)]))


def _loop_module(track: Path, **kw):
    return parse_xm(wav_module.wav_to_xm(track, **kw))


# ── La structure du module ────────────────────────────────────────


def test_la_boucle_d_echantillon_est_posee_et_tronquee(track):
    mod = _loop_module(track, loop_ms=(500, 1500))
    sample = mod.samples[0]
    rate = wav_module.WAV_MUSIC_RATE
    assert sample.loops
    # Ce qui suit la fin de la boucle n'entre pas dans l'échantillon, donc pas en ROM.
    assert sample.data.size == sample.loop_end
    assert abs(sample.loop_start - 0.5 * rate) < 0.03 * rate
    assert abs(sample.loop_end - 1.5 * rate) < 0.03 * rate


def test_la_jointure_de_la_boucle_ne_fait_pas_de_marche(track):
    """Le dernier point joué (`loop_end - 1`) et le premier de la boucle sont tous
    deux au ras de zéro, le premier juste avant la montée : le saut de `end` vers
    `start` ne fait donc pas de marche, donc pas de clic."""
    sample = _loop_module(track, loop_ms=(500, 1500)).samples[0]
    last, first, before_first = (sample.data[sample.loop_end - 1], sample.data[sample.loop_start],
                                 sample.data[sample.loop_start - 1])
    assert before_first <= 0 < first            # `start` est un passage montant
    assert last <= 0                            # on arrive de dessous zéro
    # La marche n'est pas plus grande que le plus grand pas déjà présent dans le
    # signal : la jointure se confond avec deux échantillons consécutifs.
    assert abs(first - last) <= np.abs(np.diff(sample.data)).max() + 1e-6


def test_le_module_ne_finit_plus(track):
    """Deux ordres : la note, puis un pattern dont la dernière ligne saute sur lui-même."""
    mod = _loop_module(track, loop_ms=(500, 1500))
    assert mod.order == [0, 1]
    jumps = [(cell.effect, cell.param) for row in mod.patterns[1] for cell in row
             if cell.effect == FX_POSITION_JUMP]
    assert jumps == [(FX_POSITION_JUMP, 1)]


def test_sans_boucle_la_piste_joue_une_fois_comme_avant(track):
    mod = _loop_module(track)
    assert not mod.samples[0].loops
    assert all(cell.effect != FX_POSITION_JUMP for pat in mod.patterns for row in pat for cell in row)


def test_une_boucle_trop_courte_est_refusee(track):
    with pytest.raises(ValueError, match="too short"):
        wav_module.wav_to_xm(track, loop_ms=(500, 520))


def test_la_troncature_laisse_passer_une_piste_trop_longue_pour_un_echantillon(tmp_path):
    """Le plafond est celui de l'ÉCHANTILLON : ce qui suit la boucle n'y entre pas."""
    long = _write(tmp_path / "long.wav", _tone(300, 70, rate=2000), rate=2000)
    with pytest.raises(ValueError, match="too long"):
        wav_module.wav_to_xm(long)
    assert wav_module.wav_to_xm(long, loop_ms=(1000, 5000))


# ── Le taux de build ──────────────────────────────────────────────


def test_le_taux_par_defaut_ne_change_pas_la_hauteur_des_octets():
    """À 16 726 Hz — le double exact de 8 363 — c'est (12, 0), comme avant."""
    assert wav_module._tuning(wav_module.WAV_MUSIC_RATE) == (12, 0)
    assert wav_module._tuning(8363) == (0, 0)


def test_un_taux_plus_bas_accorde_l_echantillon_par_note_relative_et_finetune():
    relative, fine = wav_module._tuning(11025)
    # 12·log2(11025/8363) = 4,78 demi-tons → 5, et −0,22 demi-ton de finetune.
    assert (relative, fine) == (5, -28)


def test_un_taux_plus_bas_raccourcit_l_echantillon(tmp_path):
    src = _write(tmp_path / "a.wav", _tone(440, 2.0))
    hi = parse_xm(wav_module.wav_to_xm(src, 16726)).samples[0].data.size
    lo = parse_xm(wav_module.wav_to_xm(src, 11025)).samples[0].data.size
    assert lo < hi and abs(lo / hi - 11025 / 16726) < 0.01
