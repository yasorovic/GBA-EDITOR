"""Le contact final CharacterBody/support execute dans le C genere."""
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
Actor g_actors[3];
u16 support_store[3];
u16 *g_actor_support=support_store;
%(helper)s

static void box(Actor* a,int x,int y,int w,int h){
    a->active=1; a->alive=1; a->collision.box_count=1;
    a->collision.boxes[0]=(CollisionBox){x,y,w,h,1,1,0,0};
}
int main(void){
    for(int i=0;i<3;i++) g_actors[i].inst=i;
    box(&g_actors[0],0,0,8,8); box(&g_actors[1],0,0,16,8); box(&g_actors[2],0,0,16,8);
    g_actors[0].x=4<<8; g_actors[0].y=8<<8;
    g_actors[1].x=0; g_actors[1].y=16<<8;
    g_actors[2].x=0; g_actors[2].y=16<<8;
    actor_support_test(&g_actors[0],0,&g_actors[1],0);
    actor_support_test(&g_actors[0],0,&g_actors[2],0);
    printf("%%u ",support_store[0]);
    support_store[0]=0; g_actors[0].x=20<<8;
    actor_support_test(&g_actors[0],0,&g_actors[1],0);
    printf("%%u",support_store[0]);
    return 0;
}
"""


def test_le_premier_support_exact_est_retenu(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hote")
    from codegen.runtime_codegen.physics.support import support_helper_lines

    source = tmp_path / "support.c"
    source.write_text(SONDE % {"helper": "\n".join(support_helper_lines())}, encoding="utf-8")
    binary = tmp_path / "support"
    built = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                            "-o", str(binary), str(source)],
                           capture_output=True, text=True, env=environnement(compilateur))
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            env=environnement(compilateur))
    assert result.stdout == "2 0"
