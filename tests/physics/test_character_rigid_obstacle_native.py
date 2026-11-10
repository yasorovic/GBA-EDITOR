"""Un CharacterBody s'arrête contre un RigidBody et ne le pousse pas, sur le C émis pour une vraie scène à carte.

Le défaut visé : au sol, la gravité du personnage l'enfonce d'un pixel dans le sol une image sur quelques-unes. Le
blocage le repoussait hors de la caisse, la garde `mover_in_wall` voyait le personnage dans le sol et annulait la
poussée : le personnage restait dans la caisse, et le solveur d'impulsions (masse inverse nulle du Character) écartait
la caisse. Le joueur poussait donc les Rigid, 2 px toutes les 4 images.

Les lignes C sont celles de `block_tick_lines`, `impulse_tick_lines` et `physics_tile_lines`, compilées avec les aides
réelles ; la sonde joue le script (gravité et marche, puis `apply_velocity`) et la gravité du Rigid.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
LARGEUR, HAUTEUR = 30, 20          # tuiles : sol en rangées 18 et 19 (y = 144)
FRAMES = 40

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS                                 /* hors GBA : mémoire ordinaire */
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
Actor g_actors[4];
int g_spool_start = 2, g_actor_slot_end = 2, g_scene_placed = 2;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@
ModelDesc g_model_desc_S[16];
static u8 carte[@W@ * @H@];

static Actor boite(int x, int y, int type){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, 8, 8, 1, 1, 0, 0};
    a.active = 1; a.alive = 1; a.type_id = type;
    return a;
}

int main(void){
    for(int i = 0; i < @W@ * @H@; i++) carte[i] = 0;
    for(int tx = 0; tx < @W@; tx++){ carte[(@H@ - 2) * @W@ + tx] = 1; carte[(@H@ - 1) * @W@ + tx] = 1; }
    g_active_cmap = carte; g_cmap_w = @W@; g_cmap_h = @H@;
    g_model_desc_S[@HERO@].body_mode = 1; g_model_desc_S[@HERO@].tile_mask = 1;
    g_model_desc_S[@CRATE@].body_mode = 3; g_model_desc_S[@CRATE@].tile_mask = 1;
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
    g_actors[0] = boite(40, 136, @HERO@); g_actors[0].slot_index = 0; alive_bit_set(0);
    g_actors[1] = boite(52, 136, @CRATE@); g_actors[1].slot_index = 1; alive_bit_set(1);
    int hero_max = 0;
    for(int f = 0; f < @FRAMES@; f++){
        Actor* h = &g_actors[0]; Actor* c = &g_actors[1];
        h->vy += 64; h->vx = 512; h->x += h->vx; h->y += h->vy;     /* le script : gravité, marche, apply_velocity */
        c->vy += 64; c->x += c->vx; c->y += c->vy;                  /* le Rigid : gravité */
@LINES@
        if((h->x >> 8) > hero_max) hero_max = h->x >> 8;
    }
    printf("%d %d %d %d\n", hero_max, g_actors[0].y >> 8, g_actors[1].x >> 8, g_actors[1].y >> 8);
    return 0;
}
"""


@pytest.fixture(scope="module")
def etat(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la physique est vérifiée en CI")
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.blocks import block_helper_lines, block_tick_lines
    from codegen.runtime_codegen.physics.character import character_solver_lines, physics_tile_lines
    from codegen.runtime_codegen.physics.impulses import impulse_helper_lines, impulse_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Scene
    from core.project import Project

    dossier = tmp_path_factory.mktemp("character_rigid")
    hero = Actor(name="Hero", components=[CollisionShapeComponent(solid=True, response="block", w=8, h=8),
                                          PhysicsBodyComponent(mode="CharacterBody")])
    caisse = Actor(name="Crate", components=[CollisionShapeComponent(solid=True, response="block", w=8, h=8),
                                             PhysicsBodyComponent(mode="RigidBody", mass=20.0)])
    scene = Scene(name="S", physics_enabled=True, actors=[hero, caisse])
    scene.collision_map = [[0] * LARGEUR for _ in range(HAUTEUR - 2)] + [[1] * LARGEUR for _ in range(2)]
    projet = Project(dossier)
    projet.scenes.items = [scene]
    pi = scene_pi(projet, scene)
    acteurs = [(a, None) for a in scene.actors]
    types = scene_oam_layout(projet, scene).placed_type_ids
    lignes = (block_tick_lines(projet, scene, acteurs, pi, resolve_initial_appearance)
              + impulse_tick_lines(projet, scene, acteurs, pi, resolve_initial_appearance)
              + physics_tile_lines(scene, acteurs, pi, kinematic=False))
    assert any("mover_in_wall" in ligne for ligne in lignes), "sans la garde de carte, la sonde ne vérifierait rien"
    assert any("rigid" in ligne.lower() for ligne in lignes), "sans solveur d'impulsions, la sonde ne vérifierait rien"

    source = (SONDE.replace("@HELPERS@", "\n".join(block_helper_lines() + impulse_helper_lines()
                                                    + character_solver_lines(False)))
              .replace("@LINES@", "\n".join(lignes)).replace("@W@", str(LARGEUR)).replace("@H@", str(HAUTEUR))
              .replace("@HERO@", str(types[0])).replace("@CRATE@", str(types[1])).replace("@FRAMES@", str(FRAMES)))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    return tuple(int(v) for v in sortie.stdout.split())


def test_le_character_au_sol_ne_pousse_pas_la_caisse(etat):
    """La caisse reste à x = 52 ; le personnage s'arrête contre elle (x = 44, bord droit sur son bord gauche)."""
    hero_max, _hero_y, caisse_x, _caisse_y = etat
    assert caisse_x == 52
    assert hero_max == 44


def test_les_deux_corps_restent_sur_le_sol(etat):
    """Ni le personnage ni la caisse ne s'enfoncent dans le sol (y = 144 - 8)."""
    _hero_max, hero_y, _caisse_x, caisse_y = etat
    assert hero_y == 136 and caisse_y == 136
