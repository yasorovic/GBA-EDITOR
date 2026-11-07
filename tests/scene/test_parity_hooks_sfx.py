"""Parité posé / spawné des crochets d'image (`on_update`, `on_late_update`) et du SoundFx déclenché par un bouton.

Une vraie scène : le prefab `Bell` (SoundFx sur le bouton A, script qui définit les deux crochets) est posé une fois ET
spawné par le script de scène. Les lignes C sont celles du générateur : la table du descripteur (`model_desc_lines`),
puis `hook_pass_lines` et `sfx_input_pass_lines`. Un seul emplacement vit à la fois ; la sonde compte les appels de
chaque crochet, lit la position vue par `on_late_update` (écrite par `on_update` : l'ordre compte) et les sons joués.

Voir `tests/physics/test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 5
APPUIS = (1, 3)        # les frames où A est pressé

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
#define SFX_DING 5
Actor g_actors[4];
int g_spool_start = 2, g_spool_hw = 2, g_scene_placed = 0;
u32 g_alive_bits[1], g_alive_epoch;
static int pressed, sfx_calls, last_sfx, last_volume, updates, lates, seen_x;
static int input_pressed(int mask){ return pressed && mask == BTN_A; }
static void sfx_play(int id, int volume, int unused){ sfx_calls++; last_sfx = id; last_volume = volume; }
void @SYM@_on_update(Actor* a){ updates++; a->x += 256; }
void @SYM@_on_late_update(Actor* a){ lates++; seen_x = a->x >> 8; }
@TABLE@
static void tick(void){
@UPDATE@
@SFX@
@LATE@
}
/* Un seul emplacement vivant : le posé (0) ou le né (2). */
static void joue(const char* chemin, int s, int type){
    for(int k = 0; k < 4; k++){ g_actors[k] = (Actor){0}; g_actors[k].inst = k; }
    g_alive_bits[0] = 0; g_spool_hw = 2; g_scene_placed = 2;   /* 0 et 1 : les posés */
    Actor* a = &g_actors[s];
    a->active = 1; a->alive = 1; a->model = type;
    alive_bit_set(s);
    if(s >= 2) g_spool_hw = s + 1;
    updates = lates = 0;
    for(int f = 0; f < @FRAMES@; f++){
        pressed = @PRESSED@;
        sfx_calls = 0; last_sfx = last_volume = -1;
        tick();
        printf("%s %d %d %d %d %d %d %d\n", chemin, f, sfx_calls, last_sfx, last_volume, updates, lates, seen_x);
    }
}
int main(void){
    joue("pose", 0, @TYPE_POSE@);
    joue("pool", 2, @TYPE_NE@);
    return 0;
}
"""


def _emissions(tmp_path):
    import copy
    from types import SimpleNamespace
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import hook_pass_lines, model_desc_lines, sfx_input_pass_lines
    from core.models.audio import Sfx
    from core.models.components import SoundFxComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project

    bell = Prefab(name="Bell")
    bell.actor.components.append(SoundFxComponent(sfx_name="Ding", trigger="a"))
    scene = Scene(name="S", actors=[Actor(name="BellPose", prefab_name="Bell",
                                          components=copy.deepcopy(bell.actor.components))])
    p = Project(tmp_path)
    p.sfx.append(Sfx(name="Ding", volume=50))
    p.scenes.items = [scene]
    p.prefabs.items = [bell]
    faire_naitre(tmp_path, scene, "Bell")
    pi = scene_pi(p, scene)
    model = next(m for m in pi if m["shared"])
    actors = [(a, None) for a in scene.actors]
    scripts = [model["sym"]]                     # le posé lié appelle le code de son modèle
    has = lambda _sym, event: event in ("on_update", "on_late_update")
    layout = SimpleNamespace(masks={})          # « a » n'est pas un accord déclaré : le bouton nu
    return {
        "sym": model["sym"],
        "table": model_desc_lines(p, scene, actors, pi, scripts, has, layout),
        "update": hook_pass_lines(scene, pi, scripts, has, "on_update"),
        "late": hook_pass_lines(scene, pi, scripts, has, "on_late_update"),
        "sfx": sfx_input_pass_lines(p, scene, actors, pi, layout),
        "type_pose": scene_oam_layout(p, scene).placed_model[0],
        "type_ne": model["model_id"],
    }


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    e = _emissions(tmp_path_factory.mktemp("parite_crochets_projet"))
    for nom in ("table", "update", "late", "sfx"):
        assert e[nom], f"{nom} : rien d'émis, la sonde ne comparerait rien"
    dossier = tmp_path_factory.mktemp("parite_crochets")
    pressed = "||".join(f"f=={f}" for f in APPUIS)
    source = (SONDE.replace("@SYM@", e["sym"]).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@UPDATE@", "\n".join(e["update"])).replace("@LATE@", "\n".join(e["late"]))
              .replace("@SFX@", "\n".join(e["sfx"])).replace("@FRAMES@", str(FRAMES))
              .replace("@PRESSED@", f"({pressed})")
              .replace("@TYPE_POSE@", str(e["type_pose"])).replace("@TYPE_NE@", str(e["type_ne"])))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[str, list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        chemin, _frame, *valeurs = ligne.split()
        etats.setdefault(chemin, []).append(tuple(int(v) for v in valeurs))
    return etats


def test_crochets_et_soundfx_donnent_le_meme_etat_pose_et_spawne(etats):
    """(sons joués, effet, volume, on_update, on_late_update, x vu par on_late_update), image par image."""
    assert len(etats["pose"]) == FRAMES
    assert etats["pool"] == etats["pose"]


def test_la_reference_pose_appelle_vraiment_les_crochets_et_joue_le_son(etats):
    """Sans cela, des états égaux mais inertes passeraient pour une parité."""
    from core.models.audio import volume_to_effect
    pose = etats["pose"]
    assert [row[0] for row in pose] == [1 if f in APPUIS else 0 for f in range(FRAMES)]
    assert pose[1][1:3] == (5, volume_to_effect(50))
    assert pose[-1][3:] == (FRAMES, FRAMES, FRAMES)          # un appel par image, et late voit le x écrit par update
