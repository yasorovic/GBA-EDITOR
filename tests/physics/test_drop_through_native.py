"""`physics_body:drop_through(n)` fait vraiment descendre un joueur immobile posé sur une face à sens unique.

Le script du joueur n'applique la gravité que lorsqu'il n'est pas `grounded`, et la résolution contre la carte laisse un
acteur à vitesse nulle où il est (`grounded` garde sa valeur : un acteur au repos est encore au repos). Un joueur qui ne
bouge pas, posé sur une face haute, appelait donc `drop_through` sans que rien ne change : il restait au sol. L'appel doit
lui retirer le contact au sol, pour que la frame suivante applique la gravité et que le compteur fasse le reste.

Le C réel est compilé et exécuté : `actor_drop_through` de `runtime_api_inline.h` et `resolve_actor_tiles`, avec la boucle
du script (gravité quand on n'est pas au sol, `drop_through` sur B).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
%(helpers)s
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
Actor g_actors[1];
u16 floor_store[1];
u16 *g_actor_floor = floor_store;
u8 drop_store[1];
u8 *g_drop_through = drop_store;
u8 g_drop_live = 0;
u8 g_support_normal = 1;
#include "runtime_api_inline.h"
/* 10 x 12 tuiles : face haute (22) sur la rangée 4 (surface y = 32), sol plein sur les rangées 9 à 11 (surface y = 72). */
static u8 carte[10 * 12];

static void frame(Actor* a, int vx, int appui_b){
    int vy = a->vy;
    if(!a->collision.grounded) vy += 64;                    /* le script du joueur */
    if(a->collision.grounded && appui_b) actor_drop_through(a, 10);
    a->vx = vx; a->vy = vy; a->x += a->vx; a->y += a->vy; resolve_actor_tiles(a, 1, 0);
    if(g_drop_through[a->slot_index] && --g_drop_through[a->slot_index]) g_drop_live = 1;   /* le décompte de la phase physique */
}

int main(void){
    for(int tx = 0; tx < 4; tx++) carte[4 * 10 + tx] = 22;
    for(int ty = 9; ty < 12; ty++) for(int tx = 0; tx < 10; tx++) carte[ty * 10 + tx] = 1;
    g_active_cmap = carte; g_cmap_w = 10; g_cmap_h = 12;
    static u8 rangees[12], colonnes[10];
    for(int ty = 0; ty < 12; ty++) for(int tx = 0; tx < 10; tx++){
        int sens = g_tile_oneway[carte[ty * 10 + tx]];
        if(sens){ rangees[ty] |= 1 << sens; colonnes[tx] |= 1 << sens; }
    }
    g_ow_rows = rangees; g_ow_cols = colonnes; g_ow_any = 0x1E;
    for(int vx = 0; vx <= 512; vx += 512){
        g_actors[0] = (Actor){0}; Actor* a = &g_actors[0];
        a->active = 1; a->alive = 1; a->slot_index = 0; a->x = 16 << 8; a->y = (32 - 15) << 8; a->collision.last_x = 16;
        a->collision.box_count = 1; a->collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
        floor_store[0] = 0; drop_store[0] = 0;
        for(int f = 0; f < 6; f++) frame(a, 0, 0);          /* se pose sur la face haute */
        printf("pose %%d %%d\n", a->y >> 8, a->collision.grounded);
        for(int f = 0; f < 40; f++) frame(a, vx, f == 0);   /* B à la première frame, puis il tombe jusqu'au sol plein */
        printf("apres_b vx=%%d %%d %%d\n", vx, a->y >> 8, a->collision.grounded);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines
    dossier = tmp_path_factory.mktemp("drop_through")
    (dossier / "obj_state.h").write_text("#define OBJ_STATE_STRIDE 1\n", encoding="utf-8")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(character_solver_lines(True))}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(dossier), "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    return subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout.splitlines()


def test_le_joueur_pose_sur_la_face_haute_est_bien_au_sol_au_depart(sortie):
    assert [l for l in sortie if l.startswith("pose")] == ["pose 17 1", "pose 17 1"]


@pytest.mark.parametrize("vx", [0, 512])
def test_drop_through_fait_descendre_le_joueur_au_sol_plein_immobile_ou_en_marche(sortie, vx):
    ligne = next(l for l in sortie if l.startswith(f"apres_b vx={vx} "))
    y, au_sol = (int(v) for v in ligne.split()[2:])
    assert (y, au_sol) == (72 - 15, 1), ligne      # traversé la face haute, posé sur le sol plein (y + 15 = 72)
