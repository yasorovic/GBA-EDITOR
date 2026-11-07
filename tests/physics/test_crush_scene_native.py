"""L'écrasement contre un StaticBody, sur le C émis pour une vraie scène : une plateforme porte un Character dans un mur.

Les prefabs `Plateforme` (Kinematic), `Passager` (Character dont le script définit `on_crushed`) et `Mur` (Static)
naissent dans le pool partagé ; un posé prend le même chemin (`SLOT_EACH`, type lu à l'emplacement). Le Character est
spawné exprès : avant l'unification, seul le posé était écrasé. Les lignes C sont le descripteur de modèle, le transport
et l'écrasement que le générateur émet ; le crochet est lu au descripteur.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 8

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define EWRAM_BSS
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define G_ACTOR_COUNT @SLOTS@
Actor g_actors[@SLOTS@];
u8 g_support_normal = 1;
int g_spool_start = @START@, g_actor_slot_end = @START@, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
static int appels, ecrase, obstacle = -1;
void @SYM@_on_crushed(Actor* a, Actor* o){ appels++; ecrase = a->slot_index; obstacle = o->slot_index; }
@HELPERS@
@TABLE@

static void naitre(int slot, int x, int y, int vx, int w, int h, int model){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1; a.slot_index = slot; a.type_id = model;
    g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}

int main(void){
    int k = @START@, a = @START@ + 1, w = @START@ + 2;
    naitre(k, 40, 50, 512, 24, 8, @TYPE_K@);       /* la plateforme avance de 2 px par image */
    naitre(a, 48, 42, 0, 8, 8, @TYPE_A@);          /* le passager posé dessus (bas = 50) */
    naitre(w, 60, 20, 0, 8, 30, @TYPE_W@);         /* le mur : x 60..68, y 20..50 */
    for(int f = 0; f < @FRAMES@; f++){
@BEFORE@
        g_actors[k].x += g_actors[k].vx;
@AFTER@
@CRUSH@
        printf("%d %d %d %d\n", g_actors[a].x >> 8, appels, appels ? ecrase == a : 0, obstacle == w ? 1 : obstacle < 0 ? 0 : 2);
    }
    return 0;
}
"""


def _emissions(tmp_path) -> dict:
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project

    plateforme = Prefab(name="Plateforme")
    plateforme.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                    PhysicsBodyComponent(mode="KinematicBody")]
    passager = Prefab(name="Passager")
    passager.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    mur = Prefab(name="Mur")
    mur.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                             PhysicsBodyComponent(mode="StaticBody")]
    prefabs = (plateforme, passager, mur)
    scene = Scene(name="S", physics_enabled=True, actors=[])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = list(prefabs)
    faire_naitre(tmp_path, scene, *(pf.name for pf in prefabs))
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    sym = models["Passager"]["sym"]
    table = model_desc_lines(project, scene, [], pi, [], lambda s, ev: s == sym and ev == "on_crushed")
    before, after, crush = kinematic_tick_parts(project, [], scene, pi, resolve_initial_appearance)
    spool = models["Passager"]["spool"]
    return {"sym": sym, "table": table, "before": before, "after": after, "crush": crush,
            "types": [models[pf.name]["root_type_id"] for pf in prefabs],
            "start": spool["start"], "slots": spool["end"]}


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Image par image : (x du passager, appels de on_crushed, le passager est l'écrasé, l'obstacle désigné : 1 le mur,
    0 aucun, 2 un autre)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; l'écrasement est vérifié en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines

    e = _emissions(tmp_path_factory.mktemp("ecrasement_scene_projet"))
    assert e["crush"], "aucun écrasement émis : la sonde ne vérifierait rien"
    assert e["slots"] >= e["start"] + 3
    tk, ta, tw = e["types"]
    source = (SONDE.replace("@HELPERS@", "\n".join(kinematic_helper_lines())).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@BEFORE@", "\n".join(e["before"])).replace("@AFTER@", "\n".join(e["after"]))
              .replace("@CRUSH@", "\n".join(e["crush"])).replace("@SYM@", e["sym"])
              .replace("@TYPE_K@", str(tk)).replace("@TYPE_A@", str(ta)).replace("@TYPE_W@", str(tw))
              .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"]))
              .replace("@FRAMES@", str(FRAMES)))
    dossier = tmp_path_factory.mktemp("ecrasement_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats = [tuple(int(v) for v in ligne.split()) for ligne in sortie.stdout.strip().splitlines()]
    assert len(etats) == FRAMES
    return etats


def test_loin_du_mur_rien_n_est_ecrase(etats):
    assert etats[0][1] == 0 and etats[0][3] == 0


def test_dans_le_mur_le_passager_ne_est_ecrase_contre_le_mur(etats):
    fin = etats[-1]
    assert fin[1] > 0 and fin[2] == 1 and fin[3] == 1


def test_l_ecrasement_est_signale_a_chaque_image_sans_bloquer_le_transport(etats):
    premiere = next(f for f, e in enumerate(etats) if e[1])
    assert [e[1] for e in etats[premiere:]] == list(range(1, FRAMES - premiere + 1))
    assert etats[-1][0] == 48 + 2 * FRAMES                   # le transport ne bloque pas : il signale
