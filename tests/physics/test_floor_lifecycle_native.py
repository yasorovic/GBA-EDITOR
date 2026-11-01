"""La lecture du sol ne conserve pas un acteur disparu ou désactivé."""
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
Actor g_actors[2];
u16 floor_store[2];
u16 *g_actor_floor=floor_store;
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id,int x,int y,int w,int h);
void window_show(int id,int on);
#include "runtime_api_inline.h"

int main(void){
    g_actors[0].inst=0; g_actors[0].alive=1; g_actors[0].active=1;
    g_actors[1].inst=1; g_actors[1].alive=1; g_actors[1].active=1;
    floor_store[0]=2;
    printf("%d ", actor_get_floor(&g_actors[0]) == &g_actors[1]);
    g_actors[1].active=0;
    printf("%d ", actor_get_floor(&g_actors[0]) == 0);
    g_actors[1].alive=0;
    printf("%d", actor_get_floor(&g_actors[0]) == 0);
    return 0;
}
"""


def test_un_sol_desactive_ou_detruit_est_immediatement_invisible(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hote")

    source = tmp_path / "floor_lifecycle.c"
    (tmp_path / "obj_state.h").write_text("#define OBJ_STATE_STRIDE 1\n", encoding="utf-8")
    source.write_text(SONDE, encoding="utf-8")
    binary = tmp_path / "floor_lifecycle"
    built = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(tmp_path), "-I", str(INCLUDE),
                            "-o", str(binary), str(source)],
                           capture_output=True, text=True, env=environnement(compilateur))
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            env=environnement(compilateur))
    assert result.stdout == "1 1 1"
