"""Parité posé / spawné de l'animation et de l'écriture OAM, matrices affines comprises.

Une copie de la démo Platformer (le vrai sprite `Player`, ses états et ses tables) : le prefab `Hero` affiche `Player`
en affine. La sonde le construit avec les deux vrais chemins générés, puis exécute `anim_oam_pass_lines`
(une boucle sur les emplacements, le cas du type de chacun), avec les vraies tables d'animation et la vraie
trigonométrie du moteur. Un seul emplacement vit à la fois ; la sonde compare, image par image, la frame d'animation,
les trois attributs OAM, la matrice écrite et le nombre de matrices prises. Puis les deux vivent ensemble : une
rotation égale reprend la même matrice, une rotation différente en prend une seconde.

Voir `tests/physics/test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

DEMO = Path(__file__).resolve().parents[2] / "Project Demo" / "Platformer"
INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 12
MOVING = 1          # l'état « Moving » du sprite Player

SONDE = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
typedef struct { u16 attr0, attr1, attr2, dummy; } OBJATTR;
OBJATTR shadow_oam[128];
int cam_x = 0, cam_y = 0, g_oam_dropped = 0, g_affine_dropped = 0;
Actor g_actors[2]; OamEntry g_oam_entries[2];
int g_spool_start = 1, g_spool_end = 2, g_spool_hw = 1, g_spool_free = 1, g_spool_entry = 1, g_scene_placed = 0;
const u8 *g_spool_part = 0;
SlotLink g_slot_link[2]; int g_slot_depth = 0;
u16 *g_actor_floor;
u8 *g_drop_through;
int g_rigid_rest[2][2];
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"
#define ACTOR_S_HEROPOSE 0
#define ACTOR_S_HERO 1
#define BOXTAG_BODY 1
u32 g_alive_bits[1], g_alive_epoch;
s16 g_sound_box_action[256]; u8 g_sound_box_action_vol[256];
static void sfx_play(int id, int volume, int unused){ (void)id; (void)volume; (void)unused; }
@SPAWN@
AffCache g_aff_cache[2];
@TABLES@

static int rendre(void){
    int _oamn = 0;
    memset(shadow_oam, 0, sizeof shadow_oam);
@PASS@
    return _affn;
}
static void place(void){
@PLACED@
}
static void seul(const char* chemin, int s){
    g_alive_bits[0] = 0;
    g_spool_hw = g_spool_free = 1;
    g_actors[1].alive = g_actors[1].active = 0;
    memset(g_aff_cache, 0, sizeof g_aff_cache);
    place();
    if(s){
        assert(spawn_S_Hero(40, 60) == &g_actors[1]);
        g_actors[0].active = 0;
    }
    assert(g_actors[s].x == 40 * 256 && g_actors[s].y == 60 * 256);
    assert(g_actors[s].collision.box_count == 1 && g_actors[s].collision.boxes[0].w == 10);
    assert(g_oam_entries[s].anim_state == @MOVING@ && g_oam_entries[s].affine_slot == 0);
    g_actors[s].vx = 256;
    for(int f = 0; f < @FRAMES@; f++){
        g_actors[s].rotation = f * 7; g_actors[s].x += g_actors[s].vx;
        int n = rendre();
        printf("%s %d %d %d %d %d %d %d %d %d %d\n", chemin, f, g_oam_entries[s].frame, shadow_oam[0].attr0,
               shadow_oam[0].attr1, shadow_oam[0].attr2, shadow_oam[0].dummy, shadow_oam[1].dummy,
               shadow_oam[2].dummy, shadow_oam[3].dummy, n);
    }
}
int main(void){
    memset(g_sound_box_action, 0xff, sizeof g_sound_box_action);
    seul("pose", 0);
    seul("pool", 1);
    /* les deux ensemble : même rotation, puis rotations différentes */
    memset(g_aff_cache, 0, sizeof g_aff_cache);
    place();
    g_actors[1].x = 120 * 256;
    g_actors[0].rotation = g_actors[1].rotation = 30;
    int n = rendre();
    printf("ensemble_egal %d %d %d\n", n, g_oam_entries[0].affine_slot, g_oam_entries[1].affine_slot);
    g_actors[1].rotation = 45;
    n = rendre();
    printf("ensemble_different %d %d %d\n", n, g_oam_entries[0].affine_slot, g_oam_entries[1].affine_slot);

    actor_destroy_internal(&g_actors[0]);
    u16 generation = g_actors[0].gen;
    g_actors[0].vx = 1024;
    g_oam_entries[0].timer = 7;
    g_rigid_rest[0][0] = 123;
    Actor* reused = spawn_S_Hero(-5, 60);
    assert(reused == &g_actors[0] && reused->name == ACTOR_S_HEROPOSE);
    assert(reused->gen != generation && reused->x == -5 * 256 && reused->vx == 0);
    assert(g_oam_entries[0].timer == 0 && g_rigid_rest[0][0] == 0);
    assert((g_alive_bits[0] & 1) && (g_alive_bits[0] & 2));   /* posés comme nés : le bit de vivant de chaque emplacement */
    return 0;
}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    if not DEMO.is_dir():
        pytest.skip("projet de démo absent")
    import copy
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_affine import compute_affine_info
    from codegen.palette_alloc import scene_bank_layout
    from codegen.runtime_codegen.gen_appearance import appearance_layout
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    from codegen.runtime_codegen.gen_scene_init import _placed_actor_lines
    from codegen.runtime_codegen.gen_sprite import anim_oam_pass_lines, anim_tables_for
    from core.models.components import CollisionShapeComponent, SpriteComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    dossier = tmp_path_factory.mktemp("parite_anim")
    copie = dossier / "Platformer"
    shutil.copytree(DEMO, copie, ignore=shutil.ignore_patterns("build"))
    p = Project.open(copie)
    hero = Prefab(name="Hero")
    hero.actor.components = [
        SpriteComponent(sprite_name="Player", affine_transform=True, initial_state="Moving"),
        CollisionShapeComponent(w=10, h=12, solid=True),
    ]
    scene = Scene(name="S", actors=[Actor(name="HeroPose", prefab_name="Hero", x=40, y=60,
                                          components=copy.deepcopy(hero.actor.components))])
    p.scenes.items = [scene]
    p.prefabs.items = [hero]
    faire_naitre(copie, scene, "Hero")
    pi = scene_pi(p, scene)
    lay = scene_oam_layout(p, scene)
    (ne,) = [m for m in pi if m["shared"]]
    assert lay.placed_model == [ne["model_id"]], "la copie posée doit porter le type du modèle né"
    actors = [(a, None) for a in scene.actors]
    passe = anim_oam_pass_lines(p, actors, 0, pi, lay, [ne["sym"]], set(compute_affine_info(0, actors)), {})
    assert passe, "rien d'émis : la sonde ne comparerait rien"
    layout = scene_bank_layout(p, scene, "obj")
    placed = _placed_actor_lines(p, scene, actors, 0, layout, appearance_layout(p, actors, pi, layout),
                                 compute_affine_info(0, actors))
    source = (SONDE.replace("@SPAWN@", "\n".join(section_spawn(pi, p, layout, actor_defined_events={})))
              .replace("@PLACED@", "\n".join(placed))
              .replace("@TABLES@", "\n".join(anim_tables_for(p, p.get_sprite("Player"))))
              .replace("@PASS@", "\n".join(passe))
              .replace("@MOVING@", str(MOVING)).replace("@FRAMES@", str(FRAMES)))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    shim = INCLUDE.parents[1] / "tests" / "native" / "libgba_shim"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE), "-I", str(shim),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert run.returncode == 0, run.stderr
    out: dict = {}
    for ligne in run.stdout.strip().splitlines():
        nom, *valeurs = ligne.split()
        out.setdefault(nom, []).append(tuple(int(v) for v in valeurs))
    return out


def test_l_animation_et_l_oam_donnent_le_meme_etat_pose_et_spawne(sortie):
    """(frame, attr0, attr1, attr2, matrice, matrices prises), image par image."""
    assert len(sortie["pose"]) == FRAMES
    assert sortie["pool"] == sortie["pose"]


def test_la_reference_pose_anime_et_tourne_vraiment(sortie):
    """Sans cela, des états égaux mais inertes passeraient pour une parité."""
    pose = sortie["pose"]
    assert len({row[1] for row in pose}) > 1                        # la frame avance
    assert all(row[2] & (1 << 8) for row in pose)                   # attr0 : sprite affine
    assert len({row[5:9] for row in pose}) > 1                      # la matrice suit la rotation
    assert all(row[9] == 1 for row in pose)                         # une matrice par image


def test_une_matrice_identique_est_reprise(sortie):
    """Deux sprites de même transform partagent une matrice (le boss qui tourne d'un bloc) ; un transform différent
    en prend une seconde."""
    assert sortie["ensemble_egal"] == [(1, 0, 0)]
    assert sortie["ensemble_different"] == [(2, 0, 1)]
