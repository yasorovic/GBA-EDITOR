"""Le contact au sol (`physics_body.floor`) sur le C émis pour une vraie scène.

Le corps (Character ou Rigid) et son appui (Static, Kinematic ou Rigid) naissent dans le pool partagé ; un posé prend le
même chemin (`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont celles de `floor_tick_lines`, compilées avec les
aides C réelles ; la sonde rapporte QUEL acteur la table `g_actor_floor` désigne. Les cas sans générateur sont dans
`test_floor_native.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# nom -> ((x, y, vy du corps en Q8), verdict attendu : 1 porté par l'appui, 0 aucun sol, 2 un autre acteur).
# L'appui occupe (40,50)-(64,58), le corps est une boîte de 8 x 8.
SCENARIOS = {
    "pose_dessus": ((48, 42, 0), 1),
    "pose_dessus_en_tombant": ((48, 42, 256), 1),
    "monte": ((48, 42, -256), 0),                  # il s'éloigne de son appui
    "a_un_pixel_au_dessus": ((48, 41, 0), 0),
    "enfonce_d_un_pixel": ((48, 43, 0), 0),        # le contact est exact, pas approché
    "hors_de_l_appui": ((100, 42, 0), 0),
}

# (mode du corps, mode de l'appui)
COUPLES = [("CharacterBody", "StaticBody"), ("CharacterBody", "KinematicBody"), ("RigidBody", "RigidBody"),
           ("RigidBody", "StaticBody")]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS                                 /* hors GBA : mémoire ordinaire */
Actor g_actors[@SLOTS@];
u16 floor_store[@SLOTS@];
u16 *g_actor_floor = floor_store;
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
int g_spool_start = @START@, g_actor_slot_end, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static void naitre(int slot, int x, int y, int vy, int w, int h, int model){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1; a.slot_index = slot; a.type_id = model;
    g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void joue(const char* nom, int x, int y, int vy){
    for(int i = 0; i < @SLOTS@; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; floor_store[i] = 0; }
    g_actor_slot_end = @START@; g_alive_bits[0] = 0;
    int c = @START@, a = @START@ + 1;
    naitre(c, x, y, vy, 8, 8, @TYPE_C@);
    naitre(a, 40, 50, 0, 24, 8, @TYPE_A@);
@LINES@
    int ref = floor_store[c];
    printf("%s %d\n", nom, ref == 0 ? 0 : ref == a + 1 ? 1 : 2);
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path, couple) -> dict:
    """Les lignes émises pour une vraie scène où les prefabs `Corps` et `Appui` sont spawnés."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.floor import floor_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    mode_corps, mode_appui = couple
    dossier = tmp_path / f"Sol_{mode_corps}_{mode_appui}"
    corps = Prefab(name="Corps")
    corps.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode=mode_corps)]
    appui = Prefab(name="Appui")
    appui.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                               PhysicsBodyComponent(mode=mode_appui)]
    scene = Scene(name="S", physics_enabled=True, actors=[])
    project = Project(dossier)
    project.scenes.items = [scene]
    project.prefabs.items = [corps, appui]
    faire_naitre(dossier, scene, "Corps", "Appui")
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    spool = models["Corps"]["spool"]
    return {"lines": floor_tick_lines(project, [], scene, pi, resolve_initial_appearance),
            "c": models["Corps"]["root_type_id"], "a": models["Appui"]["root_type_id"],
            "start": spool["start"], "slots": spool["end"]}


@pytest.fixture(scope="module")
def verdicts(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le sol est vérifié en CI")
    from codegen.runtime_codegen.physics.floor import floor_helper_lines

    dossier = tmp_path_factory.mktemp("sol_scene")
    resultats: dict[tuple[str, str], int] = {}
    runs = "\n".join(f'    joue("{n}", {x}, {y}, {vy});' for n, ((x, y, vy), _v) in SCENARIOS.items())
    for couple in COUPLES:
        e = _emissions(dossier, couple)
        assert any("actors_floor" in ligne for ligne in e["lines"]), (
            f"{couple} n'émet aucun test de sol : la sonde ne vérifierait rien")
        assert e["slots"] >= e["start"] + 2
        source = (SONDE.replace("@HELPERS@", "\n".join(floor_helper_lines())).replace("@LINES@", "\n".join(e["lines"]))
                  .replace("@TYPE_C@", str(e["c"])).replace("@TYPE_A@", str(e["a"]))
                  .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"])).replace("@RUNS@", runs))
        dossier_couple = dossier / "_".join(couple)
        dossier_couple.mkdir()
        (dossier_couple / "probe.c").write_text(source, encoding="utf-8")
        binaire = dossier_couple / "probe"
        construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                    "-o", str(binaire), str(dossier_couple / "probe.c")],
                                   capture_output=True, text=True, env=environnement(compilateur))
        assert construit.returncode == 0, construit.stderr
        sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
        assert sortie.returncode == 0, sortie.stderr
        for ligne in sortie.stdout.strip().splitlines():
            nom, verdict = ligne.split()
            resultats[("_".join(couple), nom)] = int(verdict)
    return resultats


@pytest.mark.parametrize("nom", list(SCENARIOS))
@pytest.mark.parametrize("couple", ["_".join(c) for c in COUPLES])
def test_le_sol_designe_l_appui_seulement_au_contact_exact(verdicts, couple, nom):
    assert verdicts[(couple, nom)] == SCENARIOS[nom][1]
