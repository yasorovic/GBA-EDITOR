"""Parité posé / spawné : le C ÉMIS pour un acteur posé et pour le même modèle né dans le pool donne le même état.

Règle (`.claude/rules/lua-api.md`) : un acteur posé est un spawn fait au build. Le test prend les lignes que
le générateur émet vraiment pour chaque chemin, les compile dans une sonde native, fait vivre le même corps
posé puis spawné pendant N frames, et compare l'état image par image. Un chemin du pool qui diverge du posé
(ou qui manque) casse ici, pas en jouant.

Premier cas : la résolution contre la carte de collision. D'autres passes ajoutent leur scénario à `SCENARIOS`
et leurs lignes à `_emissions`; la sonde n'a pas à changer.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 6

# (nom, x, y, vx, vy) en pixels et Q8 : les cas de test_character_native, jouables sur plusieurs frames.
SCENARIOS = [
    ("atterrit_a_droite", 33, 22, 512, 1024),
    ("atterrit_a_gauche", 33, 22, -512, 1024),
    ("atterrit_lentement", 33, 24, 512, 300),
    ("mur_a_pied", 37, 25, 512, 0),
    ("mur_en_chutant", 37, 22, 512, 1024),
    ("immobile", 33, 25, 0, 0),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
@HELPERS@

u8 *g_drop_through = 0;
Actor g_actors[2];
int g_spool_start, g_spool_hw;
u32 g_alive_bits[1], g_alive_epoch;
/* 8 x 6 tuiles : un sol plein sur la rangée 5 (y = 40), un mur plein sur la colonne 6 (x = 48). */
static u8 carte[8 * 6];
#define N_FRAMES @FRAMES@

/* Le même corps pour les deux chemins : une boîte « pieds » solide de 17 x 4 en (-7, 11). */
static Actor corps(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void rapporte(const char* chemin, const char* nom, int frame, const Actor* a){
    printf("%s %s %d %d %d %d %d %d\n", chemin, nom, frame, a->x >> 8, a->y >> 8, a->vx, a->vy, a->collision.grounded);
}
/* Le tick d'un acteur posé : `actor:apply_velocity()` puis les lignes émises pour l'indice 0. */
static void joue_pose(const char* nom, int x, int y, int vx, int vy){
    g_actors[0] = corps(x, y, vx, vy); g_actors[0].inst = 0;
    for(int f = 0; f < N_FRAMES; f++){
        g_actors[0].x += g_actors[0].vx; g_actors[0].y += g_actors[0].vy;
@PLACED@
        rapporte("pose", nom, f, &g_actors[0]);
    }
}
/* Le même corps né dans le pool partagé : emplacement 1, modèle 1. */
static void joue_pool(const char* nom, int x, int y, int vx, int vy){
    g_actors[1] = corps(x, y, vx, vy); g_actors[1].inst = 1; g_actors[1].model = 1;
    g_spool_start = 1; g_spool_hw = 2;
    pool_bit_set(1);
    for(int f = 0; f < N_FRAMES; f++){
        g_actors[1].x += g_actors[1].vx; g_actors[1].y += g_actors[1].vy;
@POOL@
        rapporte("pool", nom, f, &g_actors[1]);
    }
}

int main(void){
    for(int tx = 0; tx < 8; tx++) carte[5 * 8 + tx] = 1;
    for(int ty = 0; ty < 6; ty++) carte[ty * 8 + 6] = 1;
    g_active_cmap = carte; g_cmap_w = 8; g_cmap_h = 6;
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path):
    """Les lignes C qu'émettent le chemin posé et le chemin du pool pour le même acteur."""
    from codegen.c_names import scene_actor_sym
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.gen_scene_tick import gen_scene_tick
    from codegen.runtime_codegen.physics.body import physics_collider_mask, uses_character_solver
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / "Parite", "Parite")
    scene = project.active_scene
    scene.collision_map = [[1 if (y == 5 or x == 6) else 0 for x in range(8)] for y in range(6)]
    hero = Actor(name="Hero", components=[CollisionShapeComponent(solid=True),
                                          PhysicsBodyComponent(mode="CharacterBody")])
    scene.actors = [hero]
    tick = gen_scene_tick(project, scene, 0, [], [(hero, None)], set(), [], {}, {}, [])
    placed = [line for line in tick if "resolve_actor_tiles(&g_actors[0]" in line]

    model = {"shared": True, "model_id": 1, "sym": scene_actor_sym(scene.name, hero.name), "prefab": hero}
    pool = shared_pool_gen.tile_lines(
        [model], lambda *_: False,
        lambda owner: (physics_collider_mask(owner, map_only=True) if uses_character_solver(owner) else 0))
    return placed, pool


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines

    dossier = tmp_path_factory.mktemp("parite")
    placed, pool = _emissions(dossier)
    assert placed, "le chemin posé n'émet aucune résolution de carte : la sonde ne comparerait rien"
    assert pool, "le chemin du pool n'émet aucune résolution de carte : la sonde ne comparerait rien"
    runs = "\n".join(f'    joue_pose("{n}", {x}, {y}, {vx}, {vy}); joue_pool("{n}", {x}, {y}, {vx}, {vy});'
                     for n, x, y, vx, vy in SCENARIOS)
    source = (SONDE.replace("@HELPERS@", "\n".join(character_solver_lines()))
              .replace("@FRAMES@", str(FRAMES)).replace("@PLACED@", "\n".join(placed))
              .replace("@POOL@", "\n".join(pool)).replace("@RUNS@", runs))
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
        chemin, nom, *valeurs = ligne.split()
        etats.setdefault((chemin, nom), []).append(tuple(int(v) for v in valeurs[1:]))
    return etats


@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_la_carte_de_collision_donne_le_meme_etat_pose_et_spawne(etats, nom):
    """(x, y, vx, vy, au_sol), image par image, identiques pour l'acteur posé et pour son jumeau du pool."""
    assert len(etats[("pose", nom)]) == FRAMES
    assert etats[("pool", nom)] == etats[("pose", nom)]
