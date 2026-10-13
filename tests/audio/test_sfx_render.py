"""La découpe d'un effet (début, fin en ms) et le nom sous lequel il part à mmutil.

Le fichier de `assets/` n'est jamais touché ; le build rend la plage gardée, au taux visé, dans `build/sfx/<nom de l'asset>.wav`.
"""
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from codegen.sfx_encode import encode_sfx_for_build
from core import sfx_render
from core.models.audio import Sfx


def _wav(path: Path, frames: int = 8000, rate: int = 8000, ramp: bool = True) -> Path:
    """Un son de `frames` frames dont la valeur MONTE avec le temps : on lit où l'on a coupé dans les échantillons."""
    path.parent.mkdir(parents=True, exist_ok=True)
    values = (np.linspace(-0.9, 0.9, frames) if ramp else np.zeros(frames)) * 32767
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(values.astype("<i2").tobytes())
    return path


def _project(tmp_path: Path, sfx_rate: int = 0):
    return SimpleNamespace(build_dir=tmp_path / "build", settings=SimpleNamespace(sfx_sample_rate=sfx_rate))


def _frames(path: Path) -> tuple[int, int]:
    with wave.open(str(path)) as w:
        return w.getnframes(), w.getframerate()


def test_a_sidecar_from_before_the_trim_keeps_the_whole_effect():
    sfx = Sfx.from_dict({"name": "coin", "asset": "assets/coin.wav", "volume": 80})
    assert (sfx.trim_start, sfx.trim_end) == (0, 0) and not sfx_render.is_trimmed(sfx)


def test_the_kept_range_is_in_frames_and_end_zero_means_the_end_of_the_file():
    sfx = Sfx(name="coin", trim_start=250, trim_end=750)
    assert sfx_render.kept_range(sfx, 8000, 8000) == (2000, 6000)
    assert sfx_render.kept_range(Sfx(name="x", trim_start=500), 8000, 8000) == (4000, 8000)
    assert sfx_render.kept_range(Sfx(name="x"), 8000, 8000) == (0, 8000)
    assert sfx_render.kept_range(Sfx(name="x", trim_end=99999), 8000, 8000) == (0, 8000)     # une fin trop loin est bornée
    assert sfx_render.kept_range(Sfx(name="x", trim_start=2000), 8000, 8000) is None          # rien après la fin


def test_the_window_the_screen_draws_is_the_same_clamped_range():
    assert sfx_render.trim_window(Sfx(name="x"), 1000) == (0, 1000)
    assert sfx_render.trim_window(Sfx(name="x", trim_start=100, trim_end=400), 1000) == (100, 400)
    assert sfx_render.trim_window(Sfx(name="x", trim_start=100, trim_end=5000), 1000) == (100, 1000)


def test_a_trim_that_keeps_nothing_is_a_problem_and_a_sane_one_is_not():
    assert sfx_render.trim_problem(Sfx(name="x"), 1000) is None
    assert sfx_render.trim_problem(Sfx(name="x", trim_start=100, trim_end=400), 1000) is None
    assert "past the end" in sfx_render.trim_problem(Sfx(name="x", trim_start=1500), 1000)
    assert "shortest" in sfx_render.trim_problem(Sfx(name="x", trim_start=100, trim_end=105), 1000)


def test_the_planned_weight_follows_the_trim_and_the_rate():
    sfx = Sfx(name="x", trim_start=0, trim_end=500)
    assert sfx_render.planned_frames(sfx, 8000, 8000, 0) == 4000                  # un octet par frame gardée
    assert sfx_render.planned_frames(sfx, 8000, 8000, 4000) == 2000               # puis au taux visé
    assert sfx_render.planned_frames(Sfx(name="x", trim_start=2000), 8000, 8000, 0) == 0


def test_the_written_file_holds_exactly_the_kept_range_and_the_source_is_untouched(tmp_path: Path):
    src = _wav(tmp_path / "coin.wav")
    before = src.read_bytes()
    dst = tmp_path / "out" / "coin.wav"

    n = sfx_render.write_sfx(src, dst, Sfx(name="coin", trim_start=250, trim_end=750), 0)

    assert n == 4000 and _frames(dst) == (4000, 8000)
    with wave.open(str(dst)) as w:
        kept = np.frombuffer(w.readframes(4000), dtype="<i2")
    assert kept[0] > -0.9 * 32767 * 0.6 and kept[-1] < 0.9 * 32767 * 0.6          # le milieu de la rampe, pas ses bouts
    assert src.read_bytes() == before


def test_a_trim_and_a_lower_rate_compose(tmp_path: Path):
    src = _wav(tmp_path / "coin.wav", frames=16000, rate=16000)
    n = sfx_render.write_sfx(src, tmp_path / "coin_out.wav", Sfx(name="coin", trim_end=500), 8000)
    assert n == 4000 and _frames(tmp_path / "coin_out.wav") == (4000, 8000)       # 8000 frames gardées à 16 kHz → 4000 à 8 kHz


def test_the_build_renders_only_what_changes_and_leaves_the_others_untouched(tmp_path: Path):
    project = _project(tmp_path)
    plain = _wav(tmp_path / "assets" / "plain.wav")
    cut = _wav(tmp_path / "assets" / "cut.wav")
    items = [(Sfx(name="plain"), plain), (Sfx(name="cut", trim_end=500), cut)]

    encoded = encode_sfx_for_build(project, items)

    assert set(encoded) == {"cut"}                                                # `plain` part tel quel : aucune copie
    assert encoded["cut"] == project.build_dir / "sfx" / "cut.wav" and _frames(encoded["cut"])[0] == 4000


def test_two_effects_on_the_same_source_render_to_two_files_named_after_the_assets(tmp_path: Path):
    project = _project(tmp_path)
    src = _wav(tmp_path / "assets" / "coin.wav")
    items = [(Sfx(name="coin"), src), (Sfx(name="coin_2", trim_end=500), src), (Sfx(name="coin_3", trim_end=250), src)]

    encoded = encode_sfx_for_build(project, items)

    assert set(encoded) == {"coin_2", "coin_3"}
    assert _frames(encoded["coin_2"])[0] == 4000 and _frames(encoded["coin_3"])[0] == 2000   # pas le même fichier : pas de collision


def test_an_empty_trim_falls_back_to_the_whole_effect_and_says_so(tmp_path: Path):
    project = _project(tmp_path)
    src = _wav(tmp_path / "assets" / "coin.wav")
    sent = []

    encoded = encode_sfx_for_build(project, [(Sfx(name="coin", trim_start=60000), src)], lambda kind, msg: sent.append(kind))

    assert encoded == {} and "diagnostic" in sent                                  # le fichier d'origine part entier


def test_the_preview_plays_the_file_itself_unless_the_build_would_change_it(tmp_path: Path):
    src = _wav(tmp_path / "coin.wav")
    settings = SimpleNamespace(sfx_sample_rate=0)

    assert sfx_render.preview_file(src, Sfx(name="coin"), settings) is src
    cut = sfx_render.preview_file(src, Sfx(name="coin", trim_end=500), settings)
    assert cut != src and _frames(cut) == (4000, 8000)                                    # ce que le build écrirait
    assert sfx_render.preview_file(src, Sfx(name="coin", trim_end=500), settings) == cut   # même réglage, même fichier
    other = sfx_render.preview_file(src, Sfx(name="coin", trim_end=400), settings)
    assert other != cut and _frames(other) == (3200, 8000)                                # un autre réglage, un autre fichier
    rated = sfx_render.preview_file(src, Sfx(name="coin"), SimpleNamespace(sfx_sample_rate=4000))
    assert _frames(rated) == (4000, 4000)                                                 # le taux du PROJET s'entend aussi
    assert sfx_render.preview_file(src, Sfx(name="coin", trim_start=60000), settings) is src   # découpe vide : l'effet entier


# ── Le fondu de sortie ────────────────────────────────────────────────

def _samples(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.int32)


def _loud(path: Path, frames: int = 8000, rate: int = 8000) -> Path:
    """Un signal constant et fort : tout ce qui change dans le rendu vient du fondu."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.full(frames, 20000)).astype("<i2").tobytes())
    return path


def test_the_fade_out_ramps_the_last_frames_linearly_down_to_exact_silence(tmp_path: Path):
    src = _loud(tmp_path / "loud.wav")                                           # 1 s à 8 kHz
    sfx_render.write_sfx(src, tmp_path / "out.wav", Sfx(name="x", fade_out=30), 0)  # 30 frames = 0,5 s

    out = _samples(tmp_path / "out.wav")

    assert len(out) == 8000                                                      # la durée ne change pas : le son fond, il ne raccourcit pas
    assert (abs(out[:4000] - 20000) <= 1).all()                                  # avant la rampe, rien n'a bougé (au bit de quantification près)
    assert out[-1] == 0                                                          # le zéro exact qui supprime le clic
    assert (np.diff(out[4000:]) <= 0).all() and out[6000] == pytest.approx(10000, abs=200)   # descente régulière : à mi-rampe, la moitié


def test_the_fade_follows_the_end_of_the_kept_part_not_the_end_of_the_file(tmp_path: Path):
    src = _loud(tmp_path / "loud.wav")
    sfx_render.write_sfx(src, tmp_path / "out.wav", Sfx(name="x", trim_end=500, fade_out=6), 0)   # 6 fr = 100 ms = 800 échantillons

    out = _samples(tmp_path / "out.wav")

    assert len(out) == 4000 and out[-1] == 0 and (abs(out[:3200] - 20000) <= 1).all()


def test_a_fade_longer_than_the_effect_covers_all_of_it_and_a_missing_one_changes_nothing(tmp_path: Path):
    src = _loud(tmp_path / "loud.wav", frames=800)                               # 100 ms
    sfx_render.write_sfx(src, tmp_path / "long.wav", Sfx(name="x", fade_out=600), 0)
    sfx_render.write_sfx(src, tmp_path / "none.wav", Sfx(name="x"), 0)

    long, none = _samples(tmp_path / "long.wav"), _samples(tmp_path / "none.wav")
    assert len(long) == 800 and abs(long[0] - 20000) <= 1 and long[-1] == 0      # tout l'effet descend, sans dépasser
    assert (abs(none - 20000) <= 1).all()


def test_the_fade_is_in_frames_so_it_lasts_the_same_whatever_the_sample_rate(tmp_path: Path):
    src = _loud(tmp_path / "loud.wav", frames=16000, rate=16000)
    sfx_render.write_sfx(src, tmp_path / "out.wav", Sfx(name="x", fade_out=30), 8000)

    out = _samples(tmp_path / "out.wav")

    assert len(out) == 8000 and abs(out[3999] - 20000) <= 1 and out[-1] == 0     # 0,5 s sur 1 s, au taux de sortie


def test_a_fade_alone_makes_the_build_render_the_effect(tmp_path: Path):
    project = _project(tmp_path)
    src = _wav(tmp_path / "assets" / "coin.wav")

    encoded = encode_sfx_for_build(project, [(Sfx(name="plain"), src), (Sfx(name="soft", fade_out=12), src)])

    assert set(encoded) == {"soft"} and _frames(encoded["soft"])[0] == 8000          # même durée : seul le fondu a demandé le rendu


def test_the_preview_plays_the_fade_and_the_weight_does_not_change(tmp_path: Path):
    src = _loud(tmp_path / "loud.wav")
    settings = SimpleNamespace(sfx_sample_rate=0)

    soft = sfx_render.preview_file(src, Sfx(name="x", fade_out=30), settings)

    assert soft != src and _samples(soft)[-1] == 0
    assert sfx_render.planned_frames(Sfx(name="x", fade_out=30), 8000, 8000, 0) == 8000   # un fondu ne pèse rien de plus
