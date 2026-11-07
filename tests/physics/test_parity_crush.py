"""Parité posé / spawné de l'écrasement contre un StaticBody : une plateforme porte un Character dans un mur.

Une vraie scène où les prefabs `Plateforme` (Kinematic), `Passager` (Character dont le script définit `on_crushed`) et
`Mur` (Static) sont posés ET spawnés. Les lignes C sont le descripteur de modèle, le transport et l'écrasement que le
générateur émet ; chaque topologie ne choisit que ses emplacements vivants. Le crochet est lu au descripteur : un
Character né est écrasé comme un posé (avant, seul le posé l'était).

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 8

# topologie -> (plateforme posée ?, passager posé ?, mur posé ?)
TOPOLOGIES = {
    "tout_pose": (True, True, True),
    "passager_ne": (True, False, True),
    "mur_ne": (True, True, False),
    "tout_ne": (False, False, False),
}

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define EWRAM_BSS
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define G_ACTOR_COUNT 6
Actor g_actors[6];
u8 g_support_normal = 1;
int g_spool_start = 3, g_spool_hw = 3;
u32 g_alive_bits[1], g_alive_epoch;
static int appels[6], obstacle[6];
void @SYM@_on_crushed(Actor* a, Actor* o){ appels[a->inst]++; obstacle[a->inst] = o->inst; }
@HELPERS@
@TABLE@

static Actor corps(int x, int y, int vx, int w, int h){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
/* Posés : plateforme 0, passager 1, mur 2. Pool partagé : 3, 4, 5. */
static void place(int slot, Actor a, int model){
    a.inst = slot; a.model = model; g_actors[slot] = a;
    if(slot >= g_spool_start){ if(slot + 1 > g_spool_hw) g_spool_hw = slot + 1; pool_bit_set(slot); }
}
static void joue(const char* topo, int kp, int ap, int wp){
    for(int i = 0; i < 6; i++){ g_actors[i] = (Actor){0}; g_actors[i].inst = i; appels[i] = 0; obstacle[i] = -1; }
    g_spool_hw = 3; g_alive_bits[0] = 0;
    int k = kp ? 0 : 3, a = ap ? 1 : 4, w = wp ? 2 : 5;
    place(k, corps(40, 50, 512, 24, 8), @TYPE_K@);       /* la plateforme avance de 2 px par image */
    place(a, corps(48, 42, 0, 8, 8), @TYPE_A@);          /* le passager posé dessus (bas = 50) */
    place(w, corps(60, 20, 0, 8, 30), @TYPE_W@);         /* le mur : x 60..68, y 20..50 */
    for(int f = 0; f < @FRAMES@; f++){
@BEFORE@
        g_actors[k].x += g_actors[k].vx;
@AFTER@
@CRUSH@
        printf("%s %d %d %d %d\n", topo, f, g_actors[a].x >> 8, appels[a], obstacle[a] == w ? 1 : obstacle[a] < 0 ? 0 : 2);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path) -> dict:
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
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
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in prefabs])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = list(prefabs)
    faire_naitre(tmp_path, scene, *(pf.name for pf in prefabs))
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    sym = models["Passager"]["sym"]
    actors = [(a, None) for a in scene.actors]
    # Le passager posé et le né appellent le même code : son script définit `on_crushed`.
    table = model_desc_lines(project, scene, actors, pi, [None, sym, None], lambda s, ev: s == sym and ev == "on_crushed")
    before, after, crush = kinematic_tick_parts(project, actors, 0, scene, pi, shown)
    return {"sym": sym, "table": table, "before": before, "after": after, "crush": crush,
            "types": [models[pf.name]["model_id"] for pf in prefabs]}


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_ecrasement_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines

    e = emissions
    assert e["crush"], "aucun écrasement émis : la sonde ne comparerait rien"
    tk, ta, tw = e["types"]
    runs = "\n".join(f'    joue("{nom}", {int(k)}, {int(a)}, {int(w)});' for nom, (k, a, w) in TOPOLOGIES.items())
    source = (SONDE.replace("@HELPERS@", "\n".join(kinematic_helper_lines())).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@BEFORE@", "\n".join(e["before"])).replace("@AFTER@", "\n".join(e["after"]))
              .replace("@CRUSH@", "\n".join(e["crush"])).replace("@SYM@", e["sym"])
              .replace("@TYPE_K@", str(tk)).replace("@TYPE_A@", str(ta)).replace("@TYPE_W@", str(tw))
              .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
    dossier = tmp_path_factory.mktemp("parite_ecrasement")
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
        topo, _frame, *valeurs = ligne.split()
        etats.setdefault(topo, []).append(tuple(int(v) for v in valeurs))
    return etats


def test_les_copies_posees_prennent_le_type_du_modele_ne(emissions):
    assert len(set(emissions["types"])) == 3


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "tout_pose"])
def test_l_ecrasement_donne_le_meme_etat_pose_et_spawne(etats, topologie):
    """(x du passager, appels de on_crushed, obstacle désigné), image par image, identiques au cas tout posé."""
    assert len(etats["tout_pose"]) == FRAMES
    assert etats[topologie] == etats["tout_pose"]


def test_la_reference_ecrase_vraiment(etats):
    """Sans cela, des états égaux mais sans écrasement passeraient pour une parité."""
    debut, fin = etats["tout_pose"][0], etats["tout_pose"][-1]
    assert debut[1] == 0                         # loin du mur : rien
    assert fin[1] > 0 and fin[2] == 1            # dans le mur : écrasé, une fois par image, contre le mur
    assert fin[0] == 48 + 2 * FRAMES             # le transport ne bloque pas : il signale
