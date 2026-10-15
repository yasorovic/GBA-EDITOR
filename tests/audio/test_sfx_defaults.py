"""Hauteur, panoramique et variation de hauteur PAR DÉFAUT d'un effet : ce qu'il porte, ce que le build émet, ce que la console lit.

La règle du volume : la ressource propose, l'API surcharge. `Sfx.pitch` (100 = le fichier tel quel), `Sfx.panning`
(−100..+100) et `Sfx.pitch_variation` (± %) ne changent rien aux octets de la ROM : trois tables, une case par effet dans
l'ordre du soundbank, que `sfx_play` lit au lancement. Le C est compilé et lu en vrai par les builds lents ; ici ce qui se
vérifie sans console — dont le C de `sfx_play` lui-même, compilé sur l'hôte avec un `mmEffectEx` factice.
"""
import os
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from codegen.runtime_codegen import headers, sound_emit
from core import sfx_render
from core.models.audio import PANNING_MAX, SFX_PITCH_MAX, SFX_PITCH_MIN, Sfx
from core.project import Project


def test_an_effect_starts_at_the_pitch_of_its_file_in_the_centre_and_without_variation():
    fresh = Sfx(name="x")
    assert (fresh.pitch, fresh.panning, fresh.pitch_variation, fresh.fade_out) == (100, 0, 0, 0)
    old = Sfx.from_dict({"name": "coin", "asset": "assets/coin.wav", "volume": 80, "sample_rate": 11025})
    assert (old.pitch, old.panning, old.pitch_variation, old.fade_out) == (100, 0, 0, 0)    # un sidecar d'avant relit les défauts


def test_the_tables_hold_the_hardware_values_one_entry_per_effect_in_soundbank_order():
    sounds = {"sfx": [(Sfx(name="plain"), Path("a.wav")),
                      (Sfx(name="high", pitch=200, panning=100), Path("b.wav")),
                      (Sfx(name="low_left", pitch=50, panning=-100, pitch_variation=12, protected=True), Path("c.wav"))],
              "music": []}

    assert sound_emit.sfx_default_tables(sounds) == [
        "const mm_hword g_sfx_default_rate[3] = {1024,2048,512};",
        "const mm_byte  g_sfx_default_pan[3] = {128,255,1};",
        "const mm_byte  g_sfx_default_spread[3] = {0,0,12};",
        "const mm_byte  g_sfx_default_protected[3] = {0,0,1};",
        "mm_word g_sfx_seed = 1013904223u;", ""]


def test_the_extremes_of_the_range_stay_inside_what_the_mixer_accepts():
    rows = sound_emit.sfx_default_tables({"sfx": [(Sfx(name="lo", pitch=SFX_PITCH_MIN, panning=-PANNING_MAX), Path("a.wav")),
                                                  (Sfx(name="hi", pitch=SFX_PITCH_MAX, panning=PANNING_MAX), Path("b.wav"))]})
    assert rows[0] == "const mm_hword g_sfx_default_rate[2] = {256,4096};"
    assert rows[1] == "const mm_byte  g_sfx_default_pan[2] = {1,255};"
    over = sound_emit.sfx_default_tables({"sfx": [(Sfx(name="wild", pitch_variation=900), Path("a.wav"))]})
    assert over[2] == "const mm_byte  g_sfx_default_spread[1] = {50};"                # bornée à la plage de l'éditeur


def test_a_project_with_music_only_still_gets_tables_the_header_can_name():
    assert sound_emit.sfx_default_tables({"sfx": [], "music": [object()]})[:3] == [
        "const mm_hword g_sfx_default_rate[1] = {1024};", "const mm_byte  g_sfx_default_pan[1] = {128};",
        "const mm_byte  g_sfx_default_spread[1] = {0};"]
    assert sound_emit.sfx_default_tables(None)[0].endswith("{1024};")


def _sfx_play_c(tmp_path: Path):
    project = Project.create(tmp_path / "Jeu", "Jeu")
    headers.generate_runtime_api(project, [], [], True, [])
    text = (project.src_dir / "runtime_api.h").read_text(encoding="utf-8")
    start = text.index("static inline mm_sfxhand sfx_play")
    return text, text[start:text.index("static inline void sfx_set_volume")]


def test_sfx_play_starts_from_the_tables_and_remembers_the_pitch_it_started_with(tmp_path: Path):
    text, play = _sfx_play_c(tmp_path)

    assert "extern const mm_hword g_sfx_default_rate[];" in text and "extern const mm_byte  g_sfx_default_pan[];" in text
    assert "extern const mm_byte  g_sfx_default_spread[];" in text and "extern mm_word g_sfx_seed;" in text
    assert "ex.rate = g_sfx_default_rate[id];" in play and "ex.panning = g_sfx_default_pan[id];" in play
    assert "g_sfx_rate[s] = ex.rate;" in play      # `sfx_set_pitch` raisonne sur la hauteur COURANTE : celle de départ, pas 1024
    assert "ex.rate = (mm_hword)1024" not in text
    assert "math_rand" not in play                 # un effet qui varie ne consomme jamais le hasard du jeu


def test_a_protected_effect_always_asks_for_a_custom_channel_so_maxmod_cannot_steal_it(tmp_path: Path):
    text, play = _sfx_play_c(tmp_path)

    assert "extern const mm_byte  g_sfx_default_protected[];" in text
    assert "ex.handle = (mm_hword)((hold || g_sfx_default_protected[id]) ? 0 : 255);" in play
    assert Sfx.from_dict({"name": "old"}).protected is False                          # un sidecar d'avant relit « volable »
    assert Sfx.from_dict(Sfx(name="boss", protected=True).to_dict()).protected is True


# ── Le C généré, compilé et exécuté sur l'hôte ────────────────────────

_HARNESS = r"""
#include <stdio.h>
#include <stdint.h>
typedef uint32_t mm_word; typedef uint16_t mm_hword; typedef uint8_t mm_byte; typedef mm_hword mm_sfxhand;
typedef struct { mm_word id; mm_hword rate; mm_hword handle; mm_byte volume; mm_byte panning; } mm_sound_effect;
static mm_hword g_last_rate;
static mm_sfxhand mmEffectEx(mm_sound_effect *e){ g_last_rate = e->rate; return 0; }
mm_hword g_sfx_rate[16];
const mm_hword g_sfx_default_rate[3] = {1024, 2048, 1024};
const mm_byte  g_sfx_default_pan[3] = {128, 128, 128};
const mm_byte  g_sfx_default_spread[3] = {0, 10, 50};
const mm_byte  g_sfx_default_protected[3] = {0, 0, 0};
mm_word g_sfx_seed = 1013904223u;
static inline int sfx_slot(mm_sfxhand h){return (int)(h & 0xFF) - 1;}
@@PLAY@@
int main(void){
    for(int id = 0; id < 3; id++){
        mm_hword lo = 65535, hi = 0;
        for(int i = 0; i < 2000; i++){ sfx_play(id, 255, 0); if(g_last_rate < lo) lo = g_last_rate; if(g_last_rate > hi) hi = g_last_rate; }
        printf("%d %d %d\n", id, (int)lo, (int)hi);
    }
    return 0;
}
"""


def _host_gcc():
    for candidate in (shutil.which("gcc"), "C:/msys64/ucrt64/bin/gcc.exe"):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


@pytest.mark.skipif(_host_gcc() is None, reason="gcc hôte absent")
def test_the_generated_sfx_play_draws_inside_the_spread_and_never_outside(tmp_path: Path):
    _text, play = _sfx_play_c(tmp_path)
    source = tmp_path / "harness.c"
    source.write_text(_HARNESS.replace("@@PLAY@@", play), encoding="utf-8")
    exe = tmp_path / "harness.exe"
    # Le dossier du compilateur en tête du PATH : sous Windows, gcc échoue sans un mot s'il ne retrouve pas ses DLL.
    env = {**os.environ, "PATH": str(Path(_host_gcc()).parent) + os.pathsep + os.environ.get("PATH", "")}
    subprocess.run([_host_gcc(), "-std=c99", "-O1", "-o", str(exe), str(source)], check=True, capture_output=True, env=env)

    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True, env=env).stdout.split("\n")
    rows = {int(a): (int(b), int(c)) for a, b, c in (line.split() for line in out if line)}

    assert rows[0] == (1024, 1024)                                                   # écart nul : toujours la hauteur de départ
    assert 2048 * 900 // 1000 <= rows[1][0] < 2048 * 920 // 1000                      # ± 10 % de 2048, et toute la marge est explorée
    assert 2048 * 1080 // 1000 < rows[1][1] <= 2048 * 1100 // 1000
    assert 1024 // 2 <= rows[2][0] < 1024 * 55 // 100                                 # ± 50 % de 1024
    assert 1024 * 145 // 100 < rows[2][1] <= 1024 * 3 // 2


def _wav(path: Path, frames: int = 8000, rate: int = 8000) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.sin(np.linspace(0, 200, frames)) * 20000).astype("<i2").tobytes())
    return path


def test_the_preview_plays_the_default_pitch_by_declaring_a_faster_or_slower_rate(tmp_path: Path):
    src = _wav(tmp_path / "coin.wav")
    settings = SimpleNamespace(sfx_sample_rate=0)

    assert sfx_render.preview_file(src, Sfx(name="coin"), settings) is src          # 100 % : le fichier lui-même
    octave = sfx_render.preview_file(src, Sfx(name="coin", pitch=200), settings)
    with wave.open(str(octave)) as w:
        assert (w.getframerate(), w.getnframes()) == (16000, 8000)                  # mêmes échantillons, joués deux fois plus vite
    deep = sfx_render.preview_file(src, Sfx(name="coin", pitch=50), settings)
    with wave.open(str(deep)) as w:
        assert w.getframerate() == 4000 and deep != octave
