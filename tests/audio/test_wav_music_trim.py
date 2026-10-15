"""Rogner une musique ou un jingle WAV : la plage gardée, ses sections, les fondus cuits d'un jingle.

Le fichier n'est jamais réécrit : `wav_to_xm` rogne le signal AVANT le plan, donc la coupe est à l'échantillon près et le
module qu'on entend à l'aperçu est EXACTEMENT celui que le build écrit. Les sections d'une musique WAV sont dans le temps de
la plage gardée (celui de l'onde) et glissent avec le son quand la plage bouge (`music_structure.retrim`).
"""
from __future__ import annotations

import wave

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                    # noqa: E402
from core import music_structure, wav_module
from core.engine_emulation.xm_file import parse_xm
from core.models.audio import Jingle, Music, UNIT_MS, UNIT_ORDER

RATE = 8000


def _ramp_wav(path, seconds: float = 4.0):
    """Un WAV dont la valeur dit où l'on est : une rampe de -0,9 à +0,9 (donc une coupe se lit sur le premier échantillon)."""
    frames = int(RATE * seconds)
    ramp = np.linspace(-0.9, 0.9, frames)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((ramp * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def src(tmp_path):
    return _ramp_wav(tmp_path / "long.wav")


def _first_sample(xm: bytes) -> float:
    """La première valeur du premier échantillon, normalisée dans [-1, 1]."""
    return float(parse_xm(xm).samples[0].data[0])


def test_the_kept_part_of_a_wav_is_shorter_by_exactly_what_the_trim_cuts(src):
    assert wav_module.wav_kept_seconds(src) == pytest.approx(4.0)
    assert wav_module.wav_kept_seconds(src, (1000, 3000)) == pytest.approx(2.0)
    assert wav_module.wav_kept_seconds(src, (1000, 0)) == pytest.approx(3.0)           # fin à 0 : jusqu'au bout
    assert wav_module.wav_kept_seconds(src, (0, 9000)) == pytest.approx(4.0)           # une fin trop loin est bornée


def test_a_trim_that_leaves_nothing_is_refused_with_its_reason(src):
    with pytest.raises(ValueError, match="trim leaves nothing"):
        wav_module.wav_kept_seconds(src, (5000, 0))
    with pytest.raises(ValueError, match="trim leaves nothing"):
        wav_module.wav_to_xm(src, trim=(5000, 0))


def test_the_module_carries_only_the_kept_part_and_starts_on_the_cut_sample(src):
    whole = wav_module.wav_to_xm(src, 8000)
    cut = wav_module.wav_to_xm(src, 8000, trim=(2000, 0))                              # la moitié : de 2 s à 4 s

    assert len(cut) < len(whole) * 0.6                                                 # la ROM suit
    assert _first_sample(whole) < -0.8                                                 # le début du fichier : le bas de la rampe
    assert abs(_first_sample(cut)) < 0.05                                              # le milieu de la rampe : ~0, à l'échantillon près


def test_sections_are_in_the_time_of_the_kept_part(src):
    # Une section de 0,5 s à 1,5 s DE LA PLAGE GARDÉE : le plan coupe à ces instants-là, quel que soit le début du fichier.
    plan = wav_module.plan_wav(wav_module.wav_kept_seconds(src, (2000, 0)), 8000, [500, 1500])

    assert plan.order_at(500) is not None and plan.order_at(1500) is not None
    assert plan.total_rows == wav_module.plan_wav(2.0, 8000).total_rows                # la piste dure 2 s, pas 4


def test_the_build_writes_the_same_module_the_preview_plays(src, tmp_path):
    dst = tmp_path / "out.xm"
    trim, fades = (500, 3500), (0, 0)

    size = wav_module.encode_music_for_build(src, dst, 8000, [800, 2000], trim, fades)

    assert dst.read_bytes() == wav_module.wav_to_xm(src, 8000, [800, 2000], trim=trim, fades=fades)
    assert size == dst.stat().st_size


def test_a_jingle_bakes_its_fades_a_music_leaves_them_to_the_console():
    jingle = Jingle(name="j", asset="assets/jingles/j.wav", fade_in=6, fade_out=12, trim_start=100, trim_end=900)
    music = Music(name="m", asset="assets/music/m.wav", fade_in=6, fade_out=12)

    assert music_structure.wav_cut(jingle) == ((100, 900), (6, 12))
    assert music_structure.wav_cut(music) == ((0, 0), (0, 0))                          # la console les applique : pas deux fois


def test_the_baked_fades_of_a_jingle_start_and_end_on_an_exact_zero(tmp_path):
    flat = tmp_path / "flat.wav"
    with wave.open(str(flat), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(np.full(RATE * 2, 20000, dtype="<i2").tobytes())

    plain = parse_xm(wav_module.wav_to_xm(flat, 8000)).samples[0].data
    faded = parse_xm(wav_module.wav_to_xm(flat, 8000, fades=(6, 6))).samples[0].data

    assert plain[0] > 0.4 and plain[-1] > 0.4                                          # un signal plein, qui claquerait à la coupe
    assert faded[0] == 0 and faded[-1] == 0
    assert faded[len(faded) // 2] == pytest.approx(plain[len(plain) // 2], abs=0.02)   # le milieu n'est pas touché


def test_a_jingle_wav_applies_its_fades_a_jingle_module_does_not():
    assert "fades" not in music_structure.jingle_ignored_settings(Jingle(name="j", asset="a.wav", fade_in=5))
    assert "fades" in music_structure.jingle_ignored_settings(Jingle(name="j", asset="a.xm", fade_in=5))
    assert "trim" in music_structure.jingle_ignored_settings(Jingle(name="j", asset="a.xm", trim_start=100))


# ── retrim : les sections suivent le son ──────────────────────────────

def _music_with_sections():
    music = Music(name="m", asset="assets/music/m.wav", unit=UNIT_MS)
    music.add_section(1000, 2000, "Intro")
    music.add_section(2500, 3500, "Loop")
    music.loop_section = "Loop"
    return music


def test_trimming_the_start_slides_the_sections_with_the_sound():
    music = _music_with_sections()

    gone = music_structure.retrim(music, 500, 0, 4000)

    assert gone == [] and (music.trim_start, music.trim_end) == (500, 0)
    assert [(s.name, s.start, s.end) for s in music.sections] == [("Intro", 500, 1500), ("Loop", 2000, 3000)]


def test_a_section_the_trim_leaves_outside_goes_and_takes_its_loop_with_it():
    music = _music_with_sections()

    gone = music_structure.retrim(music, 0, 3000, 4000)                                # la fin à 3 s : « Loop » finit à 3,5 s

    assert gone == []                                                                  # coupée, pas écartée : 2,5–3 s reste
    assert music.section("Loop").end == 3000

    gone = music_structure.retrim(music, 2980, 3000, 4000)                             # il ne reste que 20 ms : plus rien n'y tient
    assert sorted(gone) == ["Intro", "Loop"] and music.loop_section != "Loop" and music.sections == []


def test_a_window_that_covers_the_whole_file_is_written_as_no_trim():
    music = _music_with_sections()
    music_structure.retrim(music, 500, 0, 4000)

    music_structure.retrim(music, 0, 4000, 4000)

    assert (music.trim_start, music.trim_end) == (0, 0)
    assert [(s.start, s.end) for s in music.sections] == [(1000, 2000), (2500, 3500)]  # revenues à leur place : le son n'a pas bougé


def test_a_section_cut_short_by_the_end_of_the_window_stays_short_when_the_window_widens_again():
    """Le prix du temps « de la plage gardée » : ce qui dépasse la fin est écrêté, et ne revient pas (une section DANS la
    plage, elle, suit le son dans les deux sens)."""
    music = _music_with_sections()
    music_structure.retrim(music, 0, 3000, 4000)                                       # « Loop » (2,5–3,5 s) est écrêtée à 3 s

    music_structure.retrim(music, 0, 4000, 4000)

    assert music.section("Loop").end == 3000


# ── Le validateur ─────────────────────────────────────────────────────

def test_a_trim_that_keeps_nothing_is_an_error(src):
    music = Music(name="m", asset="assets/music/long.wav", unit=UNIT_MS, trim_start=5000)

    problems = music_structure.music_problems(music, src)

    assert any(level == music_structure.ERROR and "past the end" in text for level, text in problems)


def test_a_module_ignores_a_trim_and_says_so(tmp_path):
    module = tmp_path / "song.it"
    module.write_bytes(F.make_it(orders=[0] * 4))
    music = Music(name="m", asset="assets/music/song.it", unit=UNIT_ORDER, trim_start=100)

    problems = music_structure.music_problems(music, module)

    assert any(level == music_structure.WARNING and "only applies to a WAV" in text for level, text in problems)


def test_sections_are_judged_against_the_kept_part_not_the_whole_file(src):
    music = Music(name="m", asset="assets/music/long.wav", unit=UNIT_MS, trim_start=1000, trim_end=3000)   # 2 s gardées
    music.add_section(0, 1900, "Fits")

    assert music_structure.music_problems(music, src) == []

    music.add_section(0, 2600, "TooLong")                                              # dépasse la plage gardée (2 s), pas le fichier (4 s)
    assert any("TooLong" in text for _level, text in music_structure.music_problems(music, src))


def test_the_rom_weight_follows_the_trim(src):
    whole = music_structure.wav_rom_bytes(Music(name="m", asset="a.wav", unit=UNIT_MS), src)
    cut = music_structure.wav_rom_bytes(Music(name="m", asset="a.wav", unit=UNIT_MS, trim_start=1000, trim_end=2000), src)

    assert cut < whole * 0.4
