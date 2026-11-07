"""Parité posé / spawné de l'animation et de l'écriture OAM, matrices affines comprises.

Une copie de la démo Platformer (le vrai sprite `Player`, ses états et ses tables) : le prefab `Hero` affiche `Player`
en affine, il est posé une fois ET spawné par le script de scène. Les lignes C sont celles de `anim_oam_pass_lines`
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
#include <stdio.h>
#include <string.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
typedef struct { u16 attr0, attr1, attr2, dummy; } OBJATTR;
OBJATTR shadow_oam[128];
int cam_x = 0, cam_y = 0, g_oam_dropped = 0, g_affine_dropped = 0;
Actor g_actors[2]; OamEntry g_oam_entries[2];
int g_spool_start = 1, g_spool_hw = 1;
u32 g_alive_bits[1], g_alive_epoch;
s16 g_sound_box_action[256]; u8 g_sound_box_action_vol[256];
static void sfx_play(int id, int volume, int unused){ (void)id; (void)volume; (void)unused; }
@TRIG@
AffCache g_aff_cache[2];
@TABLES@

static int rendre(void){
    int _oamn = 0;
    memset(shadow_oam, 0, sizeof shadow_oam);
@PASS@
    return _affn;
}
static void place(int s, int type, int x){
    Actor* a = &g_actors[s]; OamEntry* e = &g_oam_entries[s];
    *a = (Actor){0}; *e = (OamEntry){0};
    a->active = 1; a->alive = 1; a->inst = s; a->model = type; a->oam_entry = s;
    a->x = x << 8; a->y = 60 << 8; a->vx = 256; a->scale_x = a->scale_y = 256;
    e->visible = 1; e->affine_slot = 0; e->scale_x = e->scale_y = 256; e->anim_state = @MOVING@; e->facing_auto = 1;
    if(s >= g_spool_start){ pool_bit_set(s); g_spool_hw = s + 1; }
}
static void seul(const char* chemin, int s, int type){
    g_alive_bits[0] = 0; g_spool_hw = 1; g_actors[0] = g_actors[1] = (Actor){0};
    memset(g_aff_cache, 0, sizeof g_aff_cache);
    place(s, type, 40);
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
    seul("pose", 0, @TYPE@);
    seul("pool", 1, @TYPE@);
    /* les deux ensemble : même rotation, puis rotations différentes */
    g_alive_bits[0] = 0; g_spool_hw = 1; memset(g_aff_cache, 0, sizeof g_aff_cache);
    place(0, @TYPE@, 40); place(1, @TYPE@, 120);
    g_actors[0].rotation = g_actors[1].rotation = 30;
    int n = rendre();
    printf("ensemble_egal %d %d %d\n", n, g_oam_entries[0].affine_slot, g_oam_entries[1].affine_slot);
    g_actors[1].rotation = 45;
    n = rendre();
    printf("ensemble_different %d %d %d\n", n, g_oam_entries[0].affine_slot, g_oam_entries[1].affine_slot);
    return 0;
}
"""


def _trigonometrie() -> str:
    texte = (INCLUDE / "runtime_api_inline.h").read_text(encoding="utf-8")
    return texte[texte.index("static const s16 SIN_LUT"):texte.index("/* fin de la trigonométrie du moteur */")]


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
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import anim_oam_pass_lines, anim_tables_for
    from core.models.components import SpriteComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    dossier = tmp_path_factory.mktemp("parite_anim")
    copie = dossier / "Platformer"
    shutil.copytree(DEMO, copie, ignore=shutil.ignore_patterns("build"))
    p = Project.open(copie)
    hero = Prefab(name="Hero")
    hero.actor.components.append(SpriteComponent(sprite_name="Player", affine_transform=True))
    scene = Scene(name="S", actors=[Actor(name="HeroPose", prefab_name="Hero",
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
    source = (SONDE.replace("@TRIG@", _trigonometrie())
              .replace("@TABLES@", "\n".join(anim_tables_for(p, p.get_sprite("Player"))))
              .replace("@PASS@", "\n".join(passe)).replace("@TYPE@", str(ne["model_id"]))
              .replace("@MOVING@", str(MOVING)).replace("@FRAMES@", str(FRAMES)))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
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
