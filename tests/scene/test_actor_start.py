"""Le démarrage d'une scène garde l'identité de chaque acteur du lot."""
from pathlib import Path
import subprocess

import pytest

from codegen.runtime_codegen.gen_appearance import appearance_layout
from codegen.runtime_codegen.gen_pool import scene_pi, section_spawn
from codegen.runtime_codegen.gen_scene_init import _placed_actor_lines, _start_lines
from core.models.components import ScriptComponent
from core.models.scene import Actor, Prefab, Scene
from core.project import Project
from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre


SONDE = r"""
#include <assert.h>
#include <stddef.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32; typedef int s32;
#include "actor_types_static.h"
Actor g_actors[3];
OamEntry g_oam_entries[1];
SlotLink g_slot_link[3];
int g_slot_depth, g_scene_placed = 2;
int g_spool_start = 2, g_spool_end = 3, g_actor_slot_end = 2, g_spool_free = 2, g_spool_entry = -1;
u16 *g_actor_floor;
u8 *g_drop_through;
int g_rigid_rest[3][2];
u32 g_alive_bits[1], g_alive_epoch;
#define EASE_IN 0
#define EASE_OUT 1
#define EASE_IN_OUT 2
void window_set(int id, int x, int y, int w, int h);
void window_show(int id, int on);
#include "runtime_api_inline.h"
#define ACTOR_S_FIRST 0
#define ACTOR_S_BELLPLACED 1
#define ACTOR_S_BELL 2

@SPAWN@

static int step, mode, hp[3];

void S_Bell_init_script_state(Actor* a) { hp[a->slot_index] = 5; }
void S_Bell_set_hp(Actor* a, int value) { hp[a->slot_index] = value; }

void S_First_on_start(Actor* first) {
    Actor* bell = &g_actors[1];
    assert(first->alive && !first->active);
    assert(bell->alive && bell->x == 10 * 256 && hp[1] == 12);
    assert(step == 0);
    step = 1;
    if (mode) actor_destroy_internal(bell);
    if (mode >= 2) {
        if (mode == 2) {
            assert(spawn_S_Bell(20, 0) == bell);
        } else {
            assert(actor_spawn_init_S_Bell(20, 0) == bell);
            assert(step == 1);
            S_Bell_set_hp(bell, 12);
            actor_spawn_start_S_Bell(bell);
        }
        assert(step == 2);
    }
}

void S_Bell_on_start(Actor* bell) {
    assert(step == 1);
    assert(bell == &g_actors[1]);
    assert(bell->x == (mode >= 2 ? 20 : 10) * 256);
    assert(hp[bell->slot_index] == (mode == 2 ? 5 : 12));
    step = 2;
}

void S_scene_on_start(void) {
    assert(step == (mode == 1 ? 1 : 2));
    step = 3;
}

static void scene_init(void) {
@PLACED@
@START@
}

int main(void) {
    for (mode = 0; mode < 4; mode++) {
        step = 0;
        scene_init();
        assert(step == 3);
    }
    return 0;
}
"""


def test_le_lot_demarre_les_acteurs_initiaux_et_le_spawn_demarre_immediatement(tmp_path):
    cc = compilateur_hote()
    if cc is None:
        pytest.skip("aucun compilateur C hôte")

    p = Project(tmp_path)
    bell = Prefab(name="Bell")
    bell.actor.components = [ScriptComponent(script="assets/bell.lua")]
    scene = Scene(name="S", actors=[
        Actor(name="First", visible=False),
        Actor(name="BellPlaced", prefab_name="Bell", x=10,
              components=[ScriptComponent(script="assets/bell.lua", exports_values={"hp": 12})]),
    ])
    p.scenes.items = [scene]
    p.prefabs.items = [bell]
    faire_naitre(tmp_path, scene, "Bell")
    (tmp_path / "assets" / "bell.lua").write_text(
        'exports = { hp = { type = "int", default = 5 } }\nfunction on_start()\nend\n',
        encoding="utf-8",
    )
    actors = [(a, None) for a in scene.actors]
    pi = scene_pi(p, scene)
    events = {"S_First": {"on_start"}, "S_Bell": {"on_start"}}
    spawn = section_spawn(pi, p, None, actor_defined_events=events)
    placed = _placed_actor_lines(p, scene, actors, 0, None, appearance_layout(p, actors, pi, None), {})
    starts = _start_lines(p, scene, "S", actors, 0, {0, 1}, pi, False, None, events)
    source = SONDE.replace("@SPAWN@", "\n".join(spawn)).replace("@PLACED@", "\n".join(placed))
    source = source.replace("@START@", "\n".join(starts))
    (tmp_path / "probe.c").write_text(source, encoding="utf-8")
    (tmp_path / "obj_state.h").write_text("#define OBJ_STATE_STRIDE 1\n", encoding="utf-8")

    include = Path(__file__).resolve().parents[2] / "runtime" / "include"
    binary = tmp_path / "probe"
    build = subprocess.run([cc, "-std=gnu11", "-O0", "-w", "-I", str(tmp_path), "-I", str(include),
                            "-o", str(binary), str(tmp_path / "probe.c")],
                           capture_output=True, text=True, env=environnement(cc))
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True, env=environnement(cc))
    assert run.returncode == 0, run.stderr
