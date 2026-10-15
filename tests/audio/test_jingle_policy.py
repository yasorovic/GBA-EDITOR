"""La politique d'un jingle envers la musique : « mix », « duck », « pause ».

Trois choses se tiennent ici : le modèle (champs, bornes, sidecar d'avant), ce que le script émet
(`music.jingle` porte la politique de l'ASSET), et le C lui-même — le VRAI C généré, compilé sur l'hôte contre
un maxmod simulé, parce que ce qui compte (la musique descend, remonte, attend) ne se lit pas dans une chaîne.
Ce que la console fait de `mmPause` sur la seule couche principale est lu dans `libmm.a` (le 2026-10-14) : la
couche jingle n'est pas touchée, et `mmActiveSub` dit quand elle finit.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(REPO_DIR / "tests"))

from codegen.runtime_codegen import sound_emit                      # noqa: E402
from core.models import audio                                        # noqa: E402
from core.models.audio import Jingle, Music                          # noqa: E402
from native_toolchain import compilateur_hote, environnement         # noqa: E402


# ── Le modèle ─────────────────────────────────────────────────────


def test_un_jingle_sans_reglage_garde_l_ancien_comportement():
    jingle = Jingle(name="Fanfare")
    assert jingle.music_policy == audio.JINGLE_MIX
    assert jingle.runtime_policy() == (0, 1024, 0)


def test_un_sidecar_d_avant_relit_le_defaut():
    old = Jingle.from_dict({"name": "Fanfare", "asset": "assets/jingles/Fanfare.it", "volume": 80})
    assert (old.music_policy, old.duck_level, old.duck_release) == ("mix", 30, 30)


def test_une_politique_inconnue_ou_hors_borne_est_ramenee_sans_planter():
    jingle = Jingle.from_dict({"name": "J", "music_policy": "fade", "duck_level": 400, "duck_release": -5})
    assert jingle.music_policy == "mix" and jingle.duck_level == 100 and jingle.duck_release == 0


def test_le_duck_emet_son_niveau_sur_l_echelle_du_module_et_sa_remontee():
    jingle = Jingle(name="J", music_policy="duck", duck_level=30, duck_release=45)
    assert jingle.runtime_policy() == (1, audio.volume_to_module(30), 45)
    assert audio.volume_to_module(30) == 307


def test_les_autres_politiques_n_emettent_ni_niveau_ni_remontee():
    for policy, code in (("mix", 0), ("pause", 2)):
        jingle = Jingle(name="J", music_policy=policy, duck_level=10, duck_release=99)
        assert jingle.runtime_policy() == (code, 1024, 0)


def test_la_politique_survit_a_la_serialisation():
    jingle = Jingle(name="J", music_policy="pause", duck_level=55)
    assert Jingle.from_dict(jingle.to_dict()).music_policy == "pause"
    assert not hasattr(Music(name="M"), "music_policy")        # une musique n'a pas de politique : elle EST la musique


# ── Ce que le script émet ─────────────────────────────────────────


def test_music_jingle_porte_la_politique_de_l_asset():
    from scripting.codegen import CodeGen
    from scripting.parser import ExprString
    emit = CodeGen._emit_music_jingle

    class _Ctx:
        music_info = {"Fanfare": (False, 80)}
        jingle_policy = {"Fanfare": Jingle(name="Fanfare", music_policy="duck", duck_level=30,
                                           duck_release=30).runtime_policy()}

    class _Gen:
        ctx = _Ctx()

    line = emit(_Gen(), [ExprString("Fanfare")])
    assert line == "music_jingle(MUSIC_FANFARE, 819, 1, 307, 30)"


# ── Le C émis, contre un maxmod simulé ────────────────────────────

_MOCK = r'''
#include <stdio.h>
typedef unsigned int mm_word;
typedef int mm_pmode;
typedef signed char s8; typedef unsigned char u8; typedef short s16; typedef unsigned short u16;
typedef int s32; typedef unsigned int u32;
#define MM_PLAY_LOOP 0
#define MM_PLAY_ONCE 1
#define MSL_NSONGS 3

/* Les deux couches de maxmod : `active` = un module est chargé, `playing` = il avance. */
static int main_active = 0, main_playing = 0, sub_playing = 0, pos = 0;
static int module_volume = -1, jingle_volume = -1, pause_calls = 0, resume_calls = 0;
int g_mtr_mode = 0, g_mtr_id = 0, g_mtr_loop = 1, g_mtr_vol = 255, g_mtr_i = 0, g_mtr_n = 1, g_mtr_row = 0;

void mmSetModuleVolume(mm_word v){ module_volume = (int)v; }
void mmSetJingleVolume(mm_word v){ jingle_volume = (int)v; }
void mmSetModuleTempo(mm_word v){ (void)v; }
void mmSetModulePitch(mm_word v){ (void)v; }
void mmStart(mm_word id, mm_pmode m){ (void)id; (void)m; main_active = 1; main_playing = 1; }
void mmStop(void){ main_active = 0; main_playing = 0; }
void mmPause(void){ pause_calls++; if(main_active) main_playing = 0; }     /* la couche principale SEULE */
void mmResume(void){ resume_calls++; if(main_active) main_playing = 1; }
int  mmActive(void){ return main_playing; }
int  mmActiveSub(void){ return sub_playing; }
void mmJingle(mm_word id){ (void)id; sub_playing = 1; }
mm_word mmGetPosition(void){ return (mm_word)pos; }
void mmPosition(mm_word p){ pos = (int)p; }
'''

_SCENARIOS = r'''
static void report(const char *name){
    printf("%s vol=%d playing=%d active=%d jvol=%d\n", name, module_volume, main_playing, main_active, jingle_volume);
}
static void reset(void){
    main_active = main_playing = sub_playing = 0; module_volume = jingle_volume = -1;
    pause_calls = resume_calls = 0; g_mtr_mode = 0;
    g_duck = g_duck_to = 1024; g_jingle_watch = g_jingle_paused = 0; g_music_vol = 0;
}
static void end_jingle(void){ sub_playing = 0; }

int main(void){
    int i;

    /* duck : tombe d'un coup, tient tant que le jingle sonne, remonte en `release` frames */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 1, 307, 30);                 report("duck_in");
    for(i = 0; i < 100; i++) music_jingle_tick();     report("duck_held");
    end_jingle(); music_jingle_tick();                report("duck_first_step");
    for(i = 0; i < 28; i++) music_jingle_tick();      report("duck_before_end");
    music_jingle_tick();                              report("duck_end");

    /* le volume demandé pendant le duck est mis à l'échelle du duck, pas écrasé par lui */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 1, 307, 30);
    music_set_volume(512);                            report("duck_set_volume");
    end_jingle(); for(i = 0; i < 40; i++) music_jingle_tick();   report("duck_set_volume_after");

    /* un fondu en cours écrit lui-même, avec le duck du moment : le tick du jingle ne le recouvre pas */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 1, 512, 30);
    g_mtr_mode = 4; g_mtr_vol = 1024; module_volume = -2;
    music_jingle_tick();                              report("duck_during_fade");

    /* pause : la musique attend, et reprend là où elle était */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 2, 1024, 0);                 report("pause_in");
    for(i = 0; i < 100; i++) music_jingle_tick();     report("pause_held");
    end_jingle(); music_jingle_tick();                report("pause_end");

    /* une nouvelle musique pendant la pause attend aussi */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 2, 1024, 0);
    music_play(1, 1, 1024);                           report("pause_new_music");
    end_jingle(); music_jingle_tick();                report("pause_new_music_end");

    /* une musique arrêtée pendant la pause n'est pas ressuscitée par la fin du jingle */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 2, 1024, 0);
    music_stop();
    end_jingle(); music_jingle_tick();                report("pause_stopped");

    /* mix : rien ne touche à la musique */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 0, 1024, 0);
    for(i = 0; i < 10; i++) music_jingle_tick();
    end_jingle(); music_jingle_tick();                report("mix");
    printf("mix_calls pause=%d resume=%d\n", pause_calls, resume_calls);

    /* un jingle qui en remplace un autre prend SA politique : le duck d'avant remonte */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 1, 307, 0);
    music_jingle(2, 900, 0, 1024, 0);                 report("replaced_by_mix");

    /* une pause remplacée par un autre jingle rend la musique */
    reset(); music_play(0, 1, 1024);
    music_jingle(1, 900, 2, 1024, 0);
    music_jingle(2, 900, 0, 1024, 0);                 report("pause_replaced_by_mix");

    /* un id absent (module disparu) ne fait rien */
    reset(); music_play(0, 1, 1024);
    music_jingle(-1, 900, 1, 307, 30);                report("missing_id");
    return 0;
}
'''


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    cc = compilateur_hote()
    if cc is None:
        pytest.skip("pas de compilateur C sur l'hôte")
    work = tmp_path_factory.mktemp("jingle_policy")
    music = Music(name="Theme", asset="assets/music/Theme.it")
    body = "\n".join(sound_emit.music_runtime_lines(None, {"music": [(music, None)]}))
    source = work / "probe.c"
    source.write_text(_MOCK + body + "\n" + _SCENARIOS, encoding="utf-8")
    exe = work / "probe.exe"
    done = subprocess.run([cc, "-std=gnu99", "-O1", "-o", str(exe), str(source)],
                          capture_output=True, text=True, env=environnement(cc))
    assert done.returncode == 0, done.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, env=environnement(cc), check=True)
    return {name: dict(pair.split("=") for pair in pairs.split())
            for name, pairs in (line.split(" ", 1) for line in run.stdout.strip().splitlines())}


def _vol(probe, name) -> int:
    return int(probe[name]["vol"])


def test_le_duck_tombe_d_un_coup_et_tient_tant_que_le_jingle_sonne(probe):
    assert _vol(probe, "duck_in") == 307 and _vol(probe, "duck_held") == 307


def test_le_duck_remonte_en_release_frames_sans_depasser(probe):
    first, before_end, end = (_vol(probe, k) for k in ("duck_first_step", "duck_before_end", "duck_end"))
    assert 307 < first < before_end < end == 1024


def test_un_volume_demande_pendant_le_duck_est_mis_a_l_echelle(probe):
    assert _vol(probe, "duck_set_volume") == 512 * 307 // 1024
    assert _vol(probe, "duck_set_volume_after") == 512             # le duck est fini : le volume demandé, tel quel


def test_un_fondu_en_cours_n_est_pas_recouvert_par_le_tick_du_jingle(probe):
    assert _vol(probe, "duck_during_fade") == -2                    # le fondu écrit seul, le tick du jingle n'a pas touché


def test_la_pause_suspend_la_musique_jusqu_a_la_fin_du_jingle(probe):
    assert probe["pause_in"]["playing"] == "0" and probe["pause_held"]["playing"] == "0"
    assert probe["pause_end"]["playing"] == "1"


def test_une_musique_lancee_pendant_la_pause_attend_aussi(probe):
    assert probe["pause_new_music"]["playing"] == "0"
    assert probe["pause_new_music_end"]["playing"] == "1"


def test_une_musique_arretee_pendant_la_pause_n_est_pas_ressuscitee(probe):
    assert probe["pause_stopped"]["active"] == "0" and probe["pause_stopped"]["playing"] == "0"


def test_mix_ne_touche_pas_a_la_musique(probe):
    assert _vol(probe, "mix") == 1024 and probe["mix"]["playing"] == "1"
    assert probe["mix_calls"] == {"pause": "0", "resume": "0"}


def test_un_jingle_qui_en_remplace_un_autre_prend_sa_politique(probe):
    assert _vol(probe, "replaced_by_mix") == 1024
    assert probe["pause_replaced_by_mix"]["playing"] == "1"


def test_un_id_absent_ne_fait_rien(probe):
    assert _vol(probe, "missing_id") == 1024


def test_aucune_ecriture_directe_du_volume_de_module_hors_de_la_fonction_unique():
    """Le duck n'est un multiplicateur honnête que si tout passe par `music_write_volume`."""
    from codegen.runtime_codegen import main_gen
    body = "\n".join(sound_emit.music_runtime_lines(None, {"music": []}))
    direct = [line for line in body.splitlines() if "mmSetModuleVolume(" in line]
    assert len(direct) == 1 and "g_duck" in direct[0]
    assert "mmSetModuleVolume(" not in Path(main_gen.__file__).read_text(encoding="utf-8")
