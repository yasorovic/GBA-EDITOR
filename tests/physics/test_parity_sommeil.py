"""Parité posé / spawné du mouvement et du sommeil Rigid.

Les lignes C sont celles de `physics_motion_lines` et `physics_sleep_lines` pour un RigidBody posé (indice 0) et
pour le même modèle né dans le pool (emplacement 1). Gravité nulle : seule la vitesse du scénario déplace le
corps, ce qui isole le sommeil (ancre `g_rigid_rest` par emplacement, compteur `physics_sleep`).

Les tables par emplacement hors d'Actor sont remises à zéro par la destruction (`actor_slot_tables_clear`), vérifié
par la sonde native `actor_box_probe.c` : ici, un emplacement neuf suffit. Voir `test_parity_posed_spawned.py`
pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 40

# (nom, x, y, vx, vy) : pixels et Q8. Le sommeil par défaut : 30 images, seuil 0,05 px.
SCENARIOS = [
    ("repos", 10, 10, 0, 0),
    ("derive_rapide", 10, 10, 256, 0),
    ("derive_lente", 10, 10, 3, 0),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
Actor g_actors[2];
s32 g_rigid_rest[2][2];
int g_spool_start, g_spool_hw;
u32 g_alive_bits[1], g_alive_epoch;
static inline void actor_apply_velocity(Actor* s) { s->x+=s->vx; s->y+=s->vy; }

static Actor rigid(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.active = 1; a.alive = 1;
    return a;
}
static void rapporte(const char* chemin, const char* nom, int f, const Actor* a){
    printf("%s %s %d %d %d %d %d %d\n", chemin, nom, f, a->x, a->y, a->vx, a->vy, a->physics_sleep);
}
static void joue_pose(const char* nom, int x, int y, int vx, int vy){
    g_actors[0] = rigid(x, y, vx, vy); g_actors[0].inst = 0;
    g_rigid_rest[0][0] = 0; g_rigid_rest[0][1] = 0; g_rigid_rest[1][0] = 0; g_rigid_rest[1][1] = 0;   /* scene_init */
    for(int f = 0; f < @FRAMES@; f++){
@PLACED_MOTION@
@PLACED_SLEEP@
        rapporte("pose", nom, f, &g_actors[0]);
    }
}
static void joue_pool(const char* nom, int x, int y, int vx, int vy){
    g_actors[1] = rigid(x, y, vx, vy); g_actors[1].inst = 1; g_actors[1].model = 1;
    g_spool_start = 1; g_spool_hw = 2;
    pool_bit_set(1);
    for(int f = 0; f < @FRAMES@; f++){
@POOL_MOTION@
@POOL_SLEEP@
        rapporte("pool", nom, f, &g_actors[1]);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""

def _emissions(tmp_path):
    """(posé, pool) : mouvement puis sommeil, tels que le générateur les émet pour ce RigidBody."""
    from codegen.c_names import scene_actor_sym
    from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / "Sommeil", "Sommeil")
    scene = project.active_scene
    rigid = Actor(name="Rigid", components=[CollisionShapeComponent(solid=True),
                                            PhysicsBodyComponent(mode="RigidBody", gravity_scale=0.0)])
    model = {"shared": True, "model_id": 1, "sym": scene_actor_sym(scene.name, rigid.name), "prefab": rigid}
    posé = ([(rigid, None)], [])
    pool = ([], [model])
    return tuple((physics_motion_lines(scene, project.settings, actors, 0, pi),
                  physics_sleep_lines(scene, project.settings, actors, 0, pi))
                 for actors, pi in (posé, pool))

@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    dossier = tmp_path_factory.mktemp("parite_sommeil")
    (pose_motion, pose_sleep), (pool_motion, pool_sleep) = _emissions(dossier)
    for nom, lignes in (("posé/mouvement", pose_motion), ("posé/sommeil", pose_sleep),
                        ("pool/mouvement", pool_motion), ("pool/sommeil", pool_sleep)):
        assert lignes, f"{nom} n'émet rien : la sonde ne comparerait rien"
    runs = "\n".join(f'    joue_pose("{n}", {x}, {y}, {vx}, {vy}); joue_pool("{n}", {x}, {y}, {vx}, {vy});'
                     for n, x, y, vx, vy in SCENARIOS)
    source = (SONDE.replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs)
              .replace("@PLACED_MOTION@", "\n".join(pose_motion)).replace("@PLACED_SLEEP@", "\n".join(pose_sleep))
              .replace("@POOL_MOTION@", "\n".join(pool_motion)).replace("@POOL_SLEEP@", "\n".join(pool_sleep)))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str], list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        chemin, nom, _frame, *valeurs = ligne.split()
        etats.setdefault((chemin, nom), []).append(tuple(int(v) for v in valeurs))
    return etats

@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_le_mouvement_et_le_sommeil_donnent_le_meme_etat_pose_et_spawne(etats, nom):
    """(x, y, vx, vy, compteur de sommeil), image par image."""
    assert len(etats[("pose", nom)]) == FRAMES
    assert etats[("pool", nom)] == etats[("pose", nom)]

def test_la_reference_pose_s_endort_ou_derive_vraiment(etats):
    """Sans cela, des états égaux mais inertes passeraient pour une parité."""
    assert etats[("pose", "repos")][-1][4] == 30                      # le compteur atteint le délai et s'y tient
    rapide = etats[("pose", "derive_rapide")][-1]
    assert rapide[4] <= 1 and rapide[2] == 256                        # jamais endormi : la vitesse reste
    assert rapide[0] == (10 << 8) + 256 * FRAMES
    lente = etats[("pose", "derive_lente")]
    assert lente[-1][2] == 0 and lente[-1][4] == 30                   # endormi : la vitesse est remise à zéro
