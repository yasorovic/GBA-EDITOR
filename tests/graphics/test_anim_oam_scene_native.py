"""L'animation et l'écriture OAM, matrices affines comprises, sur le C émis pour une vraie scène.

Une copie de la démo Platformer (le vrai sprite `Player`, ses états et ses tables) : le prefab `Hero` affiche `Player`
en affine et naît dans le pool partagé ; un posé prend le même chemin (`SLOT_EACH`, type lu à l'emplacement). La sonde
le crée par le spawn généré, puis exécute `anim_oam_pass_lines` avec les vraies tables d'animation et la vraie
trigonométrie du moteur : la frame d'animation avance, les attributs OAM et la matrice suivent la rotation. Puis deux
Hero vivent ensemble : une rotation égale reprend la même matrice, une rotation différente en prend une seconde. Enfin
un emplacement détruit puis repris repart de zéro (génération, vitesse, minuteur d'animation, table de repos).

La reprise d'un emplacement posé par un spawn, et l'ordre de `on_start`, sont dans `tests/scene/test_actor_start.py`.
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
Actor g_actors[@SLOTS@]; OamEntry g_oam_entries[@SLOTS@];
int g_spool_start = @START@, g_spool_end = @SLOTS@, g_actor_slot_end = @START@, g_spool_free = @START@;
int g_spool_entry = @ENTRY@, g_scene_placed = @START@;
const u8 *g_spool_part = 0;
SlotLink g_slot_link[@SLOTS@]; int g_slot_depth = 0;
u16 *g_actor_floor;
u8 *g_drop_through;
int g_rigid_rest[@SLOTS@][2];
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"
#define ACTOR_S_HERO 0
#define BOXTAG_BODY 1
u32 g_alive_bits[(@SLOTS@ + 31) / 32], g_alive_epoch;
s16 g_sound_box_action[256]; u8 g_sound_box_action_vol[256];
static void sfx_play(int id, int volume, int unused){ (void)id; (void)volume; (void)unused; }
@SPAWN@
AffCache g_aff_cache[32];
@TABLES@

static int rendre(void){
    int _oamn = 0;
    memset(shadow_oam, 0, sizeof shadow_oam);
@PASS@
    return _affn;
}
int main(void){
    memset(g_sound_box_action, 0xff, sizeof g_sound_box_action);
    Actor* a = spawn_S_Hero(40, 60);
    int s = a->slot_index;
    assert(a->x == 40 * 256 && a->y == 60 * 256);
    assert(a->collision.box_count == 1 && a->collision.boxes[0].w == 10);
    assert(g_oam_entries[s].anim_state == @MOVING@ && g_oam_entries[s].affine_slot == 0);
    a->vx = 256;
    for(int f = 0; f < @FRAMES@; f++){
        a->rotation = f * 7; a->x += a->vx;
        int n = rendre();
        printf("seul %d %d %d %d %d %d %d %d %d %d\n", f, g_oam_entries[s].frame, shadow_oam[0].attr0,
               shadow_oam[0].attr1, shadow_oam[0].attr2, shadow_oam[0].dummy, shadow_oam[1].dummy,
               shadow_oam[2].dummy, shadow_oam[3].dummy, n);
    }
    /* deux Hero ensemble : même rotation, puis rotations différentes */
    memset(g_aff_cache, 0, sizeof g_aff_cache);
    Actor* b = spawn_S_Hero(120, 60);
    int t = b->slot_index;
    a->rotation = b->rotation = 30;
    int n = rendre();
    printf("ensemble_egal %d %d %d\n", n, g_oam_entries[s].affine_slot, g_oam_entries[t].affine_slot);
    b->rotation = 45;
    n = rendre();
    printf("ensemble_different %d %d %d\n", n, g_oam_entries[s].affine_slot, g_oam_entries[t].affine_slot);

    /* un emplacement rendu puis repris : le constructeur repart de zéro */
    actor_destroy_internal(a);
    u16 generation = a->gen;
    a->vx = 1024; g_oam_entries[s].timer = 7; g_rigid_rest[s][0] = 123;
    Actor* r = spawn_S_Hero(-5, 60);
    printf("repris %d %d %d %d %d %d\n", r == a, r->gen != generation, r->x == -5 * 256, r->vx,
           g_oam_entries[s].timer, g_rigid_rest[s][0]);
    return 0;
}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; l'animation est vérifiée en CI")
    if not DEMO.is_dir():
        pytest.skip("projet de démo absent")
    from codegen.oam_alloc import scene_oam_layout
    from codegen.palette_alloc import scene_bank_layout
    from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
    from codegen.runtime_codegen.gen_sprite import anim_oam_pass_lines, anim_tables_for
    from core.models.components import CollisionShapeComponent, SpriteComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    dossier = tmp_path_factory.mktemp("anim_scene")
    copie = dossier / "Platformer"
    shutil.copytree(DEMO, copie, ignore=shutil.ignore_patterns("build"))
    p = Project.open(copie)
    hero = Prefab(name="Hero")
    hero.actor.components = [
        SpriteComponent(sprite_name="Player", affine_transform=True, initial_state="Moving"),
        CollisionShapeComponent(w=10, h=12, solid=True),
    ]
    scene = Scene(name="S", actors=[])
    p.scenes.items = [scene]
    p.prefabs.items = [hero]
    faire_naitre(copie, scene, "Hero")
    pi = scene_pi(p, scene)
    (ne,) = [m for m in pi if m["shared"]]
    passe = anim_oam_pass_lines(p, [], 0, pi, scene_oam_layout(p, scene), [], set(), {})
    assert passe, "rien d'émis : la sonde ne vérifierait rien"
    layout = scene_bank_layout(p, scene, "obj")
    spool = ne["spool"]
    source = (SONDE.replace("@SPAWN@", "\n".join(section_spawn(pi, p, layout, actor_defined_events={})))
              .replace("@TABLES@", "\n".join(anim_tables_for(p, p.get_sprite("Player"))))
              .replace("@PASS@", "\n".join(passe))
              .replace("@START@", str(spool["start"])).replace("@SLOTS@", str(spool["end"]))
              .replace("@ENTRY@", str(spool["entry_start"]))
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
    assert len(out["seul"]) == FRAMES
    return out


def test_la_frame_d_animation_avance(sortie):
    assert len({row[1] for row in sortie["seul"]}) > 1


def test_l_oam_ecrit_un_sprite_affine_a_la_position_de_l_acteur(sortie):
    seul = sortie["seul"]
    assert all(row[2] & (1 << 8) for row in seul)                   # attr0 : sprite affine
    assert len({row[3] & 0x1FF for row in seul}) == FRAMES           # attr1 : x suit l'acteur, un pixel par image


def test_la_matrice_suit_la_rotation(sortie):
    seul = sortie["seul"]
    assert len({row[5:9] for row in seul}) > 1
    assert all(row[9] == 1 for row in seul)                         # une matrice par image


def test_une_matrice_identique_est_reprise(sortie):
    """Deux sprites de même transform partagent une matrice (le boss qui tourne d'un bloc) ; un transform différent
    en prend une seconde."""
    assert sortie["ensemble_egal"] == [(1, 0, 0)]
    assert sortie["ensemble_different"] == [(2, 0, 1)]


def test_un_emplacement_repris_repart_de_zero(sortie):
    """(même emplacement, génération nouvelle, position du spawn, vx, minuteur d'animation, table de repos)."""
    assert sortie["repris"] == [(1, 1, 1, 0, 0, 0)]
