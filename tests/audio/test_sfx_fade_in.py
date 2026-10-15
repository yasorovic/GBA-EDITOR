"""Le fondu d'entrée d'un effet : le pendant du fondu de sortie, cuit dans l'échantillon par le même code que le build."""
from __future__ import annotations

import wave
from types import SimpleNamespace

import numpy as np
import pytest

from core import sfx_render
from core.models.audio import Sfx


def _wav(path, frames: int = 8000, rate: int = 8000, level: int = 20000):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(np.full(frames, level, dtype="<i2").tobytes())
    return path


def test_the_effect_rises_linearly_from_an_exact_zero(tmp_path):
    src = _wav(tmp_path / "a.wav")

    data, rate = sfx_render.render_sfx(src, Sfx(name="x", fade_in=6), 0)          # 6 images = 0,1 s = 800 échantillons à 8 kHz

    assert rate == 8000 and data.size == 8000
    assert data[0] == 0.0                                                         # c'est ce zéro qui supprime le clic
    assert data[799] == pytest.approx(20000 / 32768, abs=1e-4)                    # arrivé au niveau du fichier
    assert np.all(np.diff(data[:800]) > 0)                                        # monotone : une rampe, pas un escalier
    assert data[800:] == pytest.approx(np.full(7200, 20000 / 32768), abs=1e-4)    # le reste n'est pas touché


def test_a_fade_in_longer_than_the_effect_covers_all_of_it(tmp_path):
    src = _wav(tmp_path / "a.wav", frames=400)

    data, _rate = sfx_render.render_sfx(src, Sfx(name="x", fade_in=600), 0)

    assert data.size == 400 and data[0] == 0.0 and np.all(np.diff(data) > 0)


def test_the_two_fades_apply_together(tmp_path):
    src = _wav(tmp_path / "a.wav", frames=1600)

    data, _rate = sfx_render.render_sfx(src, Sfx(name="x", fade_in=6, fade_out=6), 0)

    assert data[0] == 0.0 and data[-1] == 0.0
    assert data[800] == pytest.approx(20000 / 32768, abs=1e-4)                    # plein niveau entre les deux rampes


def test_the_fade_follows_the_trim_not_the_file(tmp_path):
    """Le fondu d'entrée est posé sur le début de la plage GARDÉE, pas sur celui du fichier."""
    src = _wav(tmp_path / "a.wav", frames=8000)

    data, _rate = sfx_render.render_sfx(src, Sfx(name="x", trim_start=500, fade_in=3), 0)

    assert data[0] == 0.0 and data.size == 4000


def test_a_fade_in_alone_is_an_edit_and_gets_its_own_preview_file(tmp_path):
    src = _wav(tmp_path / "a.wav")
    settings = SimpleNamespace(sfx_sample_rate=0)

    assert sfx_render.is_edited(Sfx(name="x", fade_in=1)) and not sfx_render.is_edited(Sfx(name="x"))
    plain = sfx_render.preview_file(src, Sfx(name="x"), settings)
    faded_in = sfx_render.preview_file(src, Sfx(name="x", fade_in=5), settings)
    faded_out = sfx_render.preview_file(src, Sfx(name="x", fade_out=5), settings)

    assert plain is src and faded_in != src and faded_in != faded_out             # deux réglages, deux fichiers


def test_the_fade_in_survives_the_sidecar():
    assert Sfx.from_dict(Sfx(name="x", fade_in=12).to_dict()).fade_in == 12
    assert Sfx.from_dict({"name": "old"}).fade_in == 0                            # un sidecar d'avant le champ
