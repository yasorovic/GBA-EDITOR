"""Les émetteurs sonores d'Area : le modèle, le C émis, et le pas C réel (compilé et exécuté avec des `sfx_*` factices)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.models.audio import Sfx
from core.models.components import AudioEmitterComponent, components_from_list, components_to_list
from core.models.scene import Area, Scene
from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"


class _Projet:
    """Ce que le générateur lit d'un projet : les effets, les scènes."""
    def __init__(self, scene, *sfx):
        self.sfx = list(sfx)
        self.scenes = [scene]


def _scene(**fields):
    area = Area(name="Wind", x=100, y=50)
    area.components.append(AudioEmitterComponent(**fields))
    return Scene(name="S", areas=[area])


@pytest.mark.parametrize("field, value", [("volume", 101), ("volume", -1), ("falloff", 256), ("falloff", -1)])
def test_les_bornes_de_l_emetteur(field, value):
    with pytest.raises(ValueError):
        AudioEmitterComponent(**{field: value})


def test_l_emetteur_fait_l_aller_retour_dans_une_area():
    scene = _scene(sfx_name="Wind", volume=60, falloff=32, panning=True)
    again = Area.from_dict(scene.areas[0].to_dict())
    comp = again.effect(AudioEmitterComponent)
    assert (comp.sfx_name, comp.volume, comp.falloff, comp.panning) == ("Wind", 60, 32, True)
    assert components_from_list(components_to_list(again.components)) == again.components


def test_la_table_et_la_boucle_de_la_scene():
    from codegen.runtime_codegen.physics.audio_emitters import emitter_tick_lines, scene_emitters
    scene = _scene(sfx_name="Wind", volume=50, falloff=40, panning=True)
    projet = _Projet(scene, Sfx(name="Wind", volume=100))
    assert [i for i, *_ in scene_emitters(projet, scene)] == [0]
    text = "\n".join(emitter_tick_lines(projet, scene))
    assert "static const AudioEmitter _snd[1]={" in text
    assert "{&g_areas[0],SFX_WIND," in text and ",40,1}," in text
    assert "audio_emitter_step(&_snd[_k],&g_snd_h[_k]);" in text


def test_un_emetteur_sans_effet_valide_ou_sans_forme_n_est_pas_emis():
    from codegen.runtime_codegen.physics.audio_emitters import emitter_tick_lines, project_has_emitters
    projet = _Projet(_scene(sfx_name="Missing"), Sfx(name="Wind"))
    assert emitter_tick_lines(projet, projet.scenes[0]) == [] and not project_has_emitters(projet)
    scene = _scene(sfx_name="Wind")
    scene.areas[0].components = [c for c in scene.areas[0].components if isinstance(c, AudioEmitterComponent)]
    assert not project_has_emitters(_Projet(scene, Sfx(name="Wind")))
    assert emitter_tick_lines(_Projet(Scene(name="Empty"), Sfx(name="Wind")), Scene(name="Empty")) == []


def test_le_validateur_signale_un_effet_inconnu_et_trop_d_emetteurs():
    from core.validator import _check_audio_emitters
    messages = []

    class Ctx:
        def __init__(self, scene, channels):
            self.project = _Projet(scene, Sfx(name="Wind"))
            self.project.settings = type("S", (), {"sound_channels": channels})()

        def warn(self, _owner, message):
            messages.append(message)

    scene = _scene(sfx_name="Missing")
    _check_audio_emitters(Ctx(scene, 1), scene)
    assert any("no valid sound effect" in m and "Missing" in m for m in messages)
    messages.clear()
    scene = Scene(name="S", areas=[Area(name=f"A{i}") for i in range(3)])
    for area in scene.areas:
        area.components.append(AudioEmitterComponent(sfx_name="Wind"))
    _check_audio_emitters(Ctx(scene, 2), scene)
    assert any("3 audio emitters" in m for m in messages)


SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
int cam_x = 0, cam_y = 0;
static int played = 0, volume = 0, stopped = 0, panning = -1, playing = 0, next_handle = 1;
static int sfx_play(int id, int vol, int hold){ played++; volume = vol; playing = 1; return next_handle; }
static void sfx_set_volume(int h, int vol){ volume = vol; }
static void sfx_set_panning(int h, int p){ panning = p; }
static void sfx_stop(int h){ stopped++; playing = 0; }
static int sfx_is_playing(int h){ return playing; }
%(fonction)s
static void etape(const AudioEmitter* e, int* h, const char* nom){
    audio_emitter_step(e, h);
    printf("%%s %%d %%d %%d %%d %%d\n", nom, played, volume, stopped, *h != 0, panning);
}
int main(void){
    /* Zone (100,50) taille 40x30, marge 40, volume 200 ; l'écouteur est cam + (120,80). */
    Area zone = { 100 << 8, 50 << 8, (CollisionShape){ 0, 0, 40, 30, 0, 1, 0 }, 1, 0, 0 };
    AudioEmitter e = { &zone, 3, 200, 40, 0 };
    AudioEmitter p = { &zone, 3, 200, 40, 1 };
    int h = 0, hp = 0;
    cam_x = 0; cam_y = 0;       /* écouteur (120, 80) : dans la zone (100..140, 50..80) */
    etape(&e, &h, "dedans");
    etape(&e, &h, "dure");                       /* l'effet joue encore : seulement le volume, pas de relance */
    playing = 0; etape(&e, &h, "fini_relance");  /* fini : il repart */
    cam_x = 40;                                  /* écouteur (160, 80) : à 20 px de la forme */
    etape(&e, &h, "bord");
    cam_x = 60;                                  /* écouteur (180, 80) : pile à la marge, silence */
    etape(&e, &h, "dehors");
    etape(&e, &h, "dehors_encore");
    zone.active = 0; cam_x = 0; played = 0;
    etape(&e, &h, "zone_eteinte");
    zone.active = 1;
    etape(&e, &h, "rallumee");
    zone.held = 1; etape(&e, &h, "tenue");
    zone.held = 0; cam_x = -40;                  /* écouteur (80, 80) : à 20 px à gauche */
    etape(&p, &hp, "pan_gauche");
    cam_x = 40; etape(&p, &hp, "pan_droite");
    return 0;
}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; l'émetteur sonore est vérifié en CI")
    from codegen.runtime_codegen.physics.audio_emitters import emitter_function_lines
    dossier = tmp_path_factory.mktemp("emetteur")
    (dossier / "probe.c").write_text(SONDE % {"fonction": "\n".join(emitter_function_lines())}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE), "-o", str(binaire),
                                str(dossier / "probe.c")], capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    return {l.split()[0]: [int(v) for v in l.split()[1:]] for l in run.stdout.splitlines()}


# colonnes : lancés, volume, coupés, a une référence, panoramique
def test_c_dans_la_zone_il_joue_au_plein_volume_et_ne_se_relance_pas(sortie):
    assert sortie["dedans"] == [1, 200, 0, 1, -1]
    assert sortie["dure"] == [1, 200, 0, 1, -1]
    assert sortie["fini_relance"] == [2, 200, 0, 1, -1]


def test_c_le_volume_decroit_lineairement_puis_il_se_coupe(sortie):
    assert sortie["bord"][1] == 100                          # à 20 px sur 40 : la moitié de 200
    assert sortie["dehors"][2:4] == [1, 0]                   # coupé, plus de référence
    assert sortie["dehors_encore"][2] == 1                   # rien à couper de plus


def test_c_une_zone_eteinte_ou_tenue_se_tait(sortie):
    assert sortie["zone_eteinte"][0] == 0                    # rien n'est lancé
    assert sortie["rallumee"][0] == 1
    assert sortie["tenue"][3] == 0                           # le parent est tenu : coupé


def test_c_le_panoramique_suit_la_position_de_la_zone(sortie):
    assert sortie["pan_gauche"][4] > 128 and sortie["pan_droite"][4] < 128      # la zone est à droite, puis à gauche
