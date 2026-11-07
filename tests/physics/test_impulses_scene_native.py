"""Le solveur d'impulsions, sur le C émis pour une vraie scène.

Un Rigid et son partenaire (StaticBody ou autre Rigid) naissent dans le pool partagé ; un posé prend le même chemin
(`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont celles d'`impulse_tick_lines`, compilées avec les aides C
réelles ; à chaque image le Rigid reçoit la gravité puis avance, et le solveur résout le contact. Masse, restitution et
friction, sur des tables écrites à la main, sont dans `tests/scene/test_block_native.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 30

# (nom, mode du partenaire, x, y, vx, vy du Rigid mobile) : pixels et Q8. Le Rigid est une boîte de 8 x 8 ; le partenaire
# occupe (30,30)-(70,60) (Static) ou (36,50)-(44,58) (Rigid). La gravité de la sonde est de 64 par image, pour les Rigid.
SCENARIOS = [
    ("chute_sur_static", "StaticBody", 40, 5, 0, 512),
    ("choc_lateral_sur_static", "StaticBody", 10, 40, 1536, 0),
    ("chute_sur_rigid", "RigidBody", 38, 20, 0, 512),
    ("rigid_contre_rigid", "RigidBody", 20, 52, 1024, 0),
    ("sans_contact", "StaticBody", 0, 0, 256, 0),
]
PARTENAIRE = {"StaticBody": (30, 30, 40, 30), "RigidBody": (36, 50, 8, 8)}

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
#define BS_ATTR_IWRAM
#define EWRAM_BSS
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static void naitre(int slot, int x, int y, int vx, int vy, int w, int h, int model){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1; a.slot_index = slot; a.type_id = model;
    g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void joue(const char* nom, int x, int y, int vx, int vy, int px, int py, int pw, int ph, int partenaire_rigid){
    for(int i = 0; i < @SLOTS@; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
    g_actor_slot_end = @START@; g_alive_bits[0] = 0;
    int m = @START@, p = @START@ + 1;
    naitre(m, x, y, vx, vy, 8, 8, @TYPE_M@);
    naitre(p, px, py, 0, 0, pw, ph, @TYPE_P@);
    for(int f = 0; f < @FRAMES@; f++){
        g_actors[m].vy += 64; g_actors[m].x += g_actors[m].vx; g_actors[m].y += g_actors[m].vy;
        if(partenaire_rigid){ g_actors[p].vy += 64; g_actors[p].x += g_actors[p].vx; g_actors[p].y += g_actors[p].vy; }
@LINES@
        const Actor* a = &g_actors[m]; const Actor* b = &g_actors[p];
        printf("%s %d %d %d %d %d %d %d %d\n", nom, a->x, a->y, a->vx, a->vy, b->x, b->y, b->vx, b->vy);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path, partenaire_mode: str) -> dict:
    """Les lignes émises pour une vraie scène où `Mobile` (Rigid) et `Partenaire` (Static ou Rigid) sont spawnés."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    dossier = tmp_path / f"Impulsions_{partenaire_mode}"
    mobile = Prefab(name="Mobile")
    mobile.actor.components += [CollisionShapeComponent(solid=True, response="block"),
                                PhysicsBodyComponent(mode="RigidBody")]
    partenaire = Prefab(name="Partenaire")
    partenaire.actor.components += [CollisionShapeComponent(solid=True, response="block"),
                                    PhysicsBodyComponent(mode=partenaire_mode)]
    scene = Scene(name="S", physics_enabled=True, actors=[])
    project = Project(dossier)
    project.scenes.items = [scene]
    project.prefabs.items = [mobile, partenaire]
    faire_naitre(dossier, scene, "Mobile", "Partenaire")
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    spool = models["Mobile"]["spool"]
    return {"lines": impulse_tick_lines(project, scene, [], pi, resolve_initial_appearance),
            "m": models["Mobile"]["root_type_id"], "p": models["Partenaire"]["root_type_id"],
            "start": spool["start"], "slots": spool["end"]}


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Par scénario, image par image : (x, y, vx, vy) du mobile puis du partenaire, en Q8."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; les impulsions sont vérifiées en CI")
    from codegen.runtime_codegen.physics.impulses import impulse_helper_lines

    dossier = tmp_path_factory.mktemp("impulsions_scene")
    etats: dict[str, list[tuple[int, ...]]] = {}
    for mode in ("StaticBody", "RigidBody"):
        e = _emissions(dossier, mode)
        assert any("rigid_solve" in ligne for ligne in e["lines"]), (
            f"{mode} n'émet aucune impulsion : la sonde ne vérifierait rien")
        assert e["slots"] >= e["start"] + 2
        px, py, pw, ph = PARTENAIRE[mode]
        runs = "\n".join(f'    joue("{n}", {x}, {y}, {vx}, {vy}, {px}, {py}, {pw}, {ph}, {int(mode == "RigidBody")});'
                         for n, scenario_mode, x, y, vx, vy in SCENARIOS if scenario_mode == mode)
        source = (SONDE.replace("@HELPERS@", "\n".join(impulse_helper_lines())).replace("@LINES@", "\n".join(e["lines"]))
                  .replace("@TYPE_M@", str(e["m"])).replace("@TYPE_P@", str(e["p"]))
                  .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"]))
                  .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
        dossier_mode = dossier / mode
        dossier_mode.mkdir()
        (dossier_mode / "probe.c").write_text(source, encoding="utf-8")
        binaire = dossier_mode / "probe"
        construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                    "-o", str(binaire), str(dossier_mode / "probe.c")],
                                   capture_output=True, text=True, env=environnement(compilateur))
        assert construit.returncode == 0, construit.stderr
        sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
        assert sortie.returncode == 0, sortie.stderr
        for ligne in sortie.stdout.strip().splitlines():
            nom, *valeurs = ligne.split()
            etats.setdefault(nom, []).append(tuple(int(v) for v in valeurs))
    assert all(len(v) == FRAMES for v in etats.values())
    return etats


def test_un_rigid_qui_tombe_s_arrete_sur_le_static(etats):
    fin = etats["chute_sur_static"][-1]
    assert fin[1] >> 8 <= 22 and fin[3] < 64 * 4             # il ne traverse pas le Static (y <= 30 - 8)
    assert fin[4:] == (30 << 8, 30 << 8, 0, 0)               # le Static ne bouge pas


def test_un_choc_lateral_s_arrete_avant_le_static(etats):
    fin = etats["choc_lateral_sur_static"][-1]
    assert fin[0] >> 8 < 30
    assert fin[4:] == (30 << 8, 30 << 8, 0, 0)


def test_un_rigid_transmet_son_impulsion_a_un_autre_rigid(etats):
    choc = etats["rigid_contre_rigid"]
    assert max(e[6] for e in choc) > 0                       # le second Rigid est poussé dans le sens du choc
    assert min(e[2] for e in choc) < 1024                    # et le premier y perd de sa vitesse


def test_un_rigid_qui_tombe_sur_un_rigid_ne_le_traverse_pas(etats):
    fin = etats["chute_sur_rigid"][-1]
    assert fin[1] + (8 << 8) <= fin[5] + 256                 # bas du mobile au plus à un pixel sous le haut du second


def test_sans_contact_la_vitesse_horizontale_se_conserve(etats):
    libre = etats["sans_contact"]
    assert all(e[2] == 256 for e in libre)
    assert libre[-1][0] == 256 * FRAMES
