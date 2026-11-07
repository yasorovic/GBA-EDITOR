"""Parité posé / spawné du contact au sol (`physics_body.floor`) : quatre topologies, un seul résultat.

Le corps (Character ou Rigid) et son appui (Static, Kinematic ou Rigid) sont chacun posé ou né dans le pool : posé/posé,
posé/pool, pool/posé, pool/pool. Les lignes C sont celles de `floor_tick_lines` pour une vraie scène où les deux prefabs
sont posés ET spawnés (un seul chemin, chaque topologie ne choisit que ses emplacements vivants), compilées avec les
aides C réelles ; la sonde rapporte QUEL acteur la table `g_actor_floor` désigne (le corps porté ou non, l'appui ou
un autre). Les quatre topologies doivent donner le même verdict que posé/posé, qui sert de référence.

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# (nom, x, y, vy du corps en Q8) : l'appui occupe (40,50)-(64,58), le corps est une boîte de 8 x 8.
SCENARIOS = [
    ("pose_dessus", 48, 42, 0),
    ("pose_dessus_en_tombant", 48, 42, 256),
    ("monte", 48, 42, -256),
    ("a_un_pixel_au_dessus", 48, 41, 0),
    ("enfonce_d_un_pixel", 48, 43, 0),
    ("hors_de_l_appui", 100, 42, 0),
]

# (mode du corps, mode de l'appui)
COUPLES = [("CharacterBody", "StaticBody"), ("CharacterBody", "KinematicBody"), ("RigidBody", "RigidBody"),
           ("RigidBody", "StaticBody")]

TOPOLOGIES = {
    "pose_pose": (True, True),
    "pose_pool": (True, False),
    "pool_pose": (False, True),
    "pool_pool": (False, False),
}

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS                                 /* hors GBA : mémoire ordinaire */
Actor g_actors[4];
u16 floor_store[4];
u16 *g_actor_floor = floor_store;
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static Actor boite(int x, int y, int vy, int w, int h){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
/* Les emplacements 0 et 1 sont posés, 2 et 3 sont le pool partagé (g_spool_start = 2). */
static void reinit(void){
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; floor_store[i] = 0; }
    g_spool_start = 2; g_actor_slot_end = 2; g_alive_bits[0] = 0; g_scene_placed = 2;   /* 0 et 1 : les posés */
}
static void pose_en_pool(int slot, Actor a, int model){
    a.slot_index = slot; a.type_id = model; g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
@TOPOLOGIES@

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path, couple) -> dict:
    """Les lignes émises pour une vraie scène où les prefabs `Corps` et `Appui` sont posés (emplacements 0 et 1) ET
    spawnés : un seul chemin, chaque topologie ne choisit que les emplacements vivants. Rend aussi le type de chacun."""
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.floor import floor_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    mode_corps, mode_appui = couple
    dossier = tmp_path / f"Sol_{mode_corps}_{mode_appui}"
    corps = Prefab(name="Corps")
    corps.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode=mode_corps)]
    appui = Prefab(name="Appui")
    appui.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                               PhysicsBodyComponent(mode=mode_appui)]
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (corps, appui)])
    project = Project(dossier)
    project.scenes.items = [scene]
    project.prefabs.items = [corps, appui]
    faire_naitre(dossier, scene, "Corps", "Appui")
    pi = scene_pi(project, scene)
    ids = {m["prefab"].name: m["root_type_id"] for m in pi if m["shared"]}
    return {"lines": floor_tick_lines(project, [(a, None) for a in scene.actors], scene, pi, resolve_initial_appearance),
            "c": ids["Corps"], "a": ids["Appui"]}


def _topologie_c(nom: str, corps_pose: bool, appui_pose: bool, e: dict) -> str:
    """Le corps vit à l'emplacement 0 (posé) ou 2 (pool), l'appui à 1 ou 3 ; posé ou né, le type de son prefab."""
    slot = {"c": 0 if corps_pose else 2, "a": 1 if appui_pose else 3}
    boites = {"c": "boite(x, y, vy, 8, 8)", "a": "boite(40, 50, 0, 24, 8)"}
    placement = []
    for k, pose in (("c", corps_pose), ("a", appui_pose)):
        if pose:
            placement.append(f"    g_actors[{slot[k]}] = {boites[k]}; g_actors[{slot[k]}].slot_index = {slot[k]}; alive_bit_set({slot[k]});"
                             f" g_actors[{slot[k]}].type_id = {e[k]};")
        else:
            placement.append(f"    pose_en_pool({slot[k]}, {boites[k]}, {e[k]});")
    c, a = slot["c"], slot["a"]
    return (f"static void topo_{nom}(const char* nom, int x, int y, int vy){{\n    reinit();\n"
            + "\n".join(placement) + "\n"
            + "\n".join(e["lines"]) + "\n"
            # 1 : le corps est porté par l'appui, 0 : aucun sol, 2 : porté par un autre acteur que l'appui
            f"    int ref = floor_store[{c}];\n"
            f"    printf(\"{nom} %s %d\\n\", nom, ref == 0 ? 0 : ref == {a} + 1 ? 1 : 2);\n"
            "}\n")


@pytest.fixture(scope="module")
def verdicts(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.floor import floor_helper_lines

    dossier = tmp_path_factory.mktemp("parite_sol")
    resultats: dict[tuple[str, str, str], int] = {}
    for couple in COUPLES:
        emis = _emissions(dossier, couple)
        assert any("actors_floor" in ligne for ligne in emis["lines"]), (
            f"{couple} n'émet aucun test de sol : la sonde ne comparerait rien")
        topologies = [_topologie_c(nom, corps_pose, appui_pose, emis)
                      for nom, (corps_pose, appui_pose) in TOPOLOGIES.items()]
        runs = "\n".join(f'    topo_{nom}("{n}", {x}, {y}, {vy});' for n, x, y, vy in SCENARIOS for nom in TOPOLOGIES)
        source = (SONDE.replace("@HELPERS@", "\n".join(floor_helper_lines()))
                  .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
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
            topologie, nom, verdict = ligne.split()
            resultats[("_".join(couple), topologie, nom)] = int(verdict)
    return resultats


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "pose_pose"])
@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
@pytest.mark.parametrize("couple", ["_".join(c) for c in COUPLES])
def test_le_sol_donne_le_meme_verdict_quelle_que_soit_l_origine_des_deux_acteurs(verdicts, couple, nom, topologie):
    assert verdicts[(couple, "pose_pose", nom)] == verdicts[(couple, topologie, nom)]


@pytest.mark.parametrize("couple", ["_".join(c) for c in COUPLES])
def test_la_reference_pose_pose_distingue_vraiment_les_cas(verdicts, couple):
    """Sans cela, des verdicts égaux mais tous nuls passeraient pour une parité."""
    assert verdicts[(couple, "pose_pose", "pose_dessus")] == 1
    assert verdicts[(couple, "pose_pose", "pose_dessus_en_tombant")] == 1
    assert verdicts[(couple, "pose_pose", "monte")] == 0                  # il s'éloigne de son appui
    assert verdicts[(couple, "pose_pose", "a_un_pixel_au_dessus")] == 0
    assert verdicts[(couple, "pose_pose", "enfonce_d_un_pixel")] == 0     # le contact est exact, pas approché
    assert verdicts[(couple, "pose_pose", "hors_de_l_appui")] == 0
