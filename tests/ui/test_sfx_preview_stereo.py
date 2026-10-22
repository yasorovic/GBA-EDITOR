"""L'aperçu d'un effet se place dans le champ stéréo et tire sa hauteur comme la console.

La console est stéréo (`mmMixerMix` règle un volume gauche et un droit par voix) : le panoramique de l'effet doit s'entendre
à l'aperçu, et la variation de hauteur aussi — un tirage par lecture, comme `sfx_play`.
"""
from __future__ import annotations

import random
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from asset_fixtures import create
from core import sfx_render, wav_module
from core.engine_emulation.xm_file import parse_xm
from core.models.audio import PAN_CENTER, Sfx, panning_to_hardware
from core.project import Project
from ui.sound_mixer.box_playback import BoxPlayer


def _wav(path, frames: int = 4000, rate: int = 8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.sin(np.linspace(0, 120, frames)) * 20000).astype("<i2").tobytes())
    return path


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def coin(project) -> Sfx:
    return create(project, "sfx", _wav(project.user_library_dir / "coin.wav"))


def _side_energy(track) -> tuple[float, float]:
    pcm = track.pcm.astype(np.float64)
    return float(np.abs(pcm[:, 0]).sum()), float(np.abs(pcm[:, 1]).sum())


def test_the_module_carries_the_panning_the_build_never_gives(tmp_path):
    src = _wav(tmp_path / "a.wav")

    assert parse_xm(wav_module.wav_to_xm(src)).samples[0].default_pan == PAN_CENTER          # le build : toujours au centre
    assert parse_xm(wav_module.wav_to_xm(src, pan=0)).samples[0].default_pan == 0
    assert parse_xm(wav_module.wav_to_xm(src, pan=255)).samples[0].default_pan == 255


def test_the_preview_of_an_effect_is_heard_on_the_side_it_is_panned_to(qapp, project, coin):
    player = BoxPlayer()

    centre = _side_energy(player.track_for(project, coin))
    coin.panning = -100
    left = _side_energy(player.track_for(project, coin))
    coin.panning = 100
    right = _side_energy(player.track_for(project, coin))

    assert centre[0] == pytest.approx(centre[1], rel=0.05)                                   # centré : les deux côtés pareils
    assert left[0] > 20 * max(left[1], 1.0) and right[1] > 20 * max(right[0], 1.0)           # tout à gauche, tout à droite
    assert left[0] > centre[0] and right[1] > centre[1]


def test_the_panning_of_the_effect_is_the_one_the_console_receives(qapp, project, coin):
    player = BoxPlayer()
    coin.panning = -40

    _path, _key, params, _info = player._prepare(project, coin, coin.name)

    assert params["pan"] == panning_to_hardware(-40)


def test_two_panned_renders_do_not_share_a_cache_entry(qapp, project, coin):
    player = BoxPlayer()
    first = player.track_for(project, coin)
    coin.panning = 60

    assert player.track_for(project, coin) is not first and len(player._tracks) == 2


def test_the_variation_draws_inside_its_range_at_the_tenth_of_a_percent():
    sfx = SimpleNamespace(pitch=150, pitch_variation=10)
    rng = random.Random(7)

    drawn = [sfx_render.varied_pitch(sfx, rng) for _ in range(2000)]

    assert min(drawn) >= 150 * 0.9 and max(drawn) <= 150 * 1.1
    assert min(drawn) < 150 * 0.91 and max(drawn) > 150 * 1.09                                # explore toute la marge
    assert all(round(value * 1000 / 150) == pytest.approx(value * 1000 / 150, abs=1e-6) for value in drawn)   # au dixième de %


def test_no_variation_draws_the_pitch_itself():
    assert sfx_render.varied_pitch(SimpleNamespace(pitch=120, pitch_variation=0)) == 120


def test_each_preview_of_a_varied_effect_plays_a_fresh_draw(qapp, project, coin, monkeypatch):
    player = BoxPlayer()
    coin.pitch, coin.pitch_variation = 100, 20
    played = []
    monkeypatch.setattr(player, "_live_track", lambda _project, asset: played.append(asset.pitch))   # rien à jouer : on lit le tirage
    monkeypatch.setattr(sfx_render.random, "randint", lambda low, high: high)

    player.preview(project, coin)
    monkeypatch.setattr(sfx_render.random, "randint", lambda low, high: low)
    player.preview(project, coin)

    assert played == [pytest.approx(120.0), pytest.approx(80.0)]
    assert coin.pitch == 100                                                                  # l'asset garde sa hauteur de départ


def test_a_fractional_pitch_gets_its_own_preview_file(tmp_path):
    src = _wav(tmp_path / "a.wav")
    settings = SimpleNamespace(sfx_sample_rate=0)

    a = sfx_render.preview_file(src, Sfx(name="x", pitch=100), settings)
    b = sfx_render.preview_file(src, Sfx(name="x", pitch=104.3), settings)
    c = sfx_render.preview_file(src, Sfx(name="x", pitch=104.3), settings)

    assert a is src and b != src and b == c
