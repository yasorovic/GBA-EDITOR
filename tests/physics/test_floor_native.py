"""Le contact final CharacterBody/floor exécuté dans le C généré : le premier appui qui porte est retenu."""
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
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
Actor g_actors[3];
u16 floor_store[3];
u16 *g_actor_floor=floor_store;
u8 *g_drop_through=0;
u8 g_support_normal=1;
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
%(helper)s
/* Le corps est du type 1, les deux appuis du type 2 (rang compact 0) : un seul couple de boîtes (0, 0). */
static const u8 si[3]={255,255,0};
static const PairRun runs[1]={{0,1}};
static const FloorPair pairs[1]={{0,0,0,0}};

static void box(Actor* a,int x,int y,int w,int h){
    a->active=1; a->alive=1; a->collision.box_count=1;
    a->collision.boxes[0]=(CollisionShape){x,y,w,h,1,1,0,0};
}
int main(void){
    for(int i=0;i<3;i++) g_actors[i].slot_index=i;
    box(&g_actors[0],0,0,8,8); box(&g_actors[1],0,0,16,8); box(&g_actors[2],0,0,16,8);
    g_actors[0].x=4<<8; g_actors[0].y=8<<8;
    g_actors[1].x=0; g_actors[1].y=16<<8;
    g_actors[2].x=0; g_actors[2].y=16<<8;
    g_actors[0].type_id=1; g_actors[1].type_id=2; g_actors[2].type_id=2;
    g_scene_placed=3; g_actor_slot_end=3; for(int i=0;i<3;i++) alive_bit_set(i);
    FloorSupport list[3]; int n=floor_supports(si,list);   /* le corps n'est pas un appui : deux entrées */
    actors_floor(&g_actors[0],1,runs,list,n,pairs,1);
    printf("%%u ",floor_store[0]);
    g_actors[0].x=20<<8;                      /* hors des appuis : la passe remet le sol à zéro */
    actors_floor(&g_actors[0],1,runs,list,n,pairs,1);
    printf("%%u",floor_store[0]);
    return 0;
}
"""


def test_le_premier_floor_exact_est_retenu(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hote")
    from codegen.runtime_codegen.physics.floor import floor_helper_lines

    source = tmp_path / "floor.c"
    source.write_text(SONDE % {"helper": "\n".join(floor_helper_lines())}, encoding="utf-8")
    binary = tmp_path / "floor"
    built = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                            "-o", str(binary), str(source)],
                           capture_output=True, text=True, env=environnement(compilateur))
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            env=environnement(compilateur))
    assert result.stdout == "2 0"
