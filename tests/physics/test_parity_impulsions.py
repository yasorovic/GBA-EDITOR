"""Parité posé / spawné du solveur d'impulsions : quatre topologies, un seul résultat.

Un Rigid et son partenaire (StaticBody ou autre Rigid) sont chacun posé ou né dans le pool : posé/posé, posé/pool,
pool/posé, pool/pool. Les lignes C sont celles d'`impulse_tick_lines` pour une vraie scène où les deux prefabs sont
posés ET spawnés (un seul chemin), compilées avec les aides C réelles ; à chaque image le Rigid reçoit la gravité puis avance, et le solveur résout le contact. Les quatre
topologies doivent donner exactement le même état, image par image, que posé/posé, qui sert de référence.

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 30

# (nom, mode du partenaire, x, y, vx, vy du Rigid mobile) : pixels et Q8. Le Rigid est une boîte de 8 x 8 ; le partenaire
# occupe (30,30)-(70,60) (Static) ou (36,50)-(44,58) (Rigid).
SCENARIOS = [
    ("chute_sur_static", "StaticBody", 40, 5, 0, 512),
    ("choc_lateral_sur_static", "StaticBody", 10, 40, 1536, 0),
    ("chute_sur_rigid", "RigidBody", 38, 20, 0, 512),
    ("rigid_contre_rigid", "RigidBody", 20, 52, 1024, 0),
    ("sans_contact", "StaticBody", 0, 0, 256, 0),
]

# topologie -> (mobile posé ?, partenaire posé ?)
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
#include "gba_debug.h"
#define BS_ATTR_IWRAM
#define EWRAM_BSS
Actor g_actors[4];
int g_spool_start, g_spool_hw;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static Actor corps(int x, int y, int vx, int vy, int w, int h){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void rapporte(const char* topo, const char* nom, int f, const Actor* a, const Actor* b){
    printf("%s %s %d %d %d %d %d %d %d %d %d\n", topo, nom, f, a->x, a->y, a->vx, a->vy, b->x, b->y, b->vx, b->vy);
}
/* Les emplacements 0 et 1 sont posés, 2 et 3 sont le pool partagé (g_spool_start = 2). */
static void reinit(void){
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].inst = i; }
    g_spool_start = 2; g_spool_hw = 2; g_alive_bits[0] = 0;
}
static void pose_en_pool(int slot, Actor a, int model){
    a.inst = slot; a.model = model; g_actors[slot] = a;
    if(slot + 1 > g_spool_hw) g_spool_hw = slot + 1;
    pool_bit_set(slot);
}
@TOPOLOGIES@

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path, partenaire_mode: str) -> dict:
    """Les lignes émises pour une vraie scène où les prefabs `Mobile` (Rigid) et `Partenaire` (Static ou Rigid) sont
    posés (emplacements 0 et 1) ET spawnés : un seul chemin, chaque topologie ne choisit que ses emplacements vivants."""
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    dossier = tmp_path / f"Impulsions_{partenaire_mode}"
    mobile = Prefab(name="Mobile")
    mobile.actor.components += [CollisionShapeComponent(solid=True, response="block"),
                                PhysicsBodyComponent(mode="RigidBody")]
    partenaire = Prefab(name="Partenaire")
    partenaire.actor.components += [CollisionShapeComponent(solid=True, response="block"),
                                    PhysicsBodyComponent(mode=partenaire_mode)]
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (mobile, partenaire)])
    project = Project(dossier)
    project.scenes.items = [scene]
    project.prefabs.items = [mobile, partenaire]
    faire_naitre(dossier, scene, "Mobile", "Partenaire")
    pi = scene_pi(project, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    return {"lines": impulse_tick_lines(project, scene, [(a, None) for a in scene.actors], 0, pi, shown),
            "m": ids["Mobile"], "p": ids["Partenaire"]}


def _topologie_c(nom: str, mobile_pose: bool, partenaire_pose: bool, e: dict) -> str:
    """Le mobile vit à l'emplacement 0 (posé) ou 2 (pool), le partenaire à 1 ou 3 ; posé ou né, le type de son prefab."""
    slot = {"m": 0 if mobile_pose else 2, "p": 1 if partenaire_pose else 3}
    corps = {"m": "corps(x, y, vx, vy, 8, 8)", "p": "corps(px, py, 0, 0, pw, ph)"}
    placement = []
    for k, pose in (("m", mobile_pose), ("p", partenaire_pose)):
        if pose:
            placement.append(f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].inst = {slot[k]};"
                             f" g_actors[{slot[k]}].model = {e[k]};")
        else:
            placement.append(f"    pose_en_pool({slot[k]}, {corps[k]}, {e[k]});")
    m, p = slot["m"], slot["p"]
    body = "\n".join(e["lines"])
    return (f"static void topo_{nom}(const char* nom, int x, int y, int vx, int vy, int px, int py, int pw, int ph, int partenaire_rigid){{\n"
            "    reinit();\n" + "\n".join(placement) + "\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            f"        g_actors[{m}].vy += 64; g_actors[{m}].x += g_actors[{m}].vx; g_actors[{m}].y += g_actors[{m}].vy;\n"
            f"        if(partenaire_rigid){{ g_actors[{p}].vy += 64; g_actors[{p}].x += g_actors[{p}].vx; g_actors[{p}].y += g_actors[{p}].vy; }}\n"
            f"{body}\n"
            f"        rapporte(\"{nom}\", nom, f, &g_actors[{m}], &g_actors[{p}]);\n"
            "    }\n}\n")


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.impulses import impulse_helper_lines

    dossier = tmp_path_factory.mktemp("parite_impulsions")
    etats: dict[tuple[str, str], list[tuple[int, ...]]] = {}
    for mode in ("StaticBody", "RigidBody"):
        emis = _emissions(dossier, mode)
        assert any("rigid_solve" in ligne for ligne in emis["lines"]), (
            f"{mode} n'émet aucune impulsion : la sonde ne comparerait rien")
        topologies = [_topologie_c(nom, mobile_pose, partenaire_pose, emis)
                      for nom, (mobile_pose, partenaire_pose) in TOPOLOGIES.items()]
        runs = "\n".join(
            f'    topo_{nom}("{n}", {x}, {y}, {vx}, {vy}, '
            f'{30 if mode == "StaticBody" else 36}, {30 if mode == "StaticBody" else 50}, {40 if mode == "StaticBody" else 8}, '
            f'{30 if mode == "StaticBody" else 8}, {int(mode == "RigidBody")});'
            for n, scenario_mode, x, y, vx, vy in SCENARIOS if scenario_mode == mode for nom in TOPOLOGIES)
        source = (SONDE.replace("@HELPERS@", "\n".join(impulse_helper_lines()))
                  .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
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
            topologie, nom, _frame, *valeurs = ligne.split()
            etats.setdefault((topologie, nom), []).append(tuple(int(v) for v in valeurs))
    return etats


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "pose_pose"])
@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_le_solveur_donne_le_meme_etat_quelle_que_soit_l_origine_des_deux_acteurs(etats, nom, topologie):
    """(x, y, vx, vy) du mobile puis du partenaire, image par image, identiques à ceux du cas posé/posé."""
    assert len(etats[("pose_pose", nom)]) == FRAMES
    assert etats[("pose_pose", nom)] == etats[(topologie, nom)]


def test_la_reference_pose_pose_resout_vraiment_les_contacts(etats):
    """Sans cela, des états égaux mais sans contact résolu passeraient pour une parité."""
    chute = etats[("pose_pose", "chute_sur_static")]
    assert chute[-1][1] >> 8 <= 22 and chute[-1][3] < 64 * 4             # le Rigid ne traverse pas le Static (y <= 30 - 8)
    lateral = etats[("pose_pose", "choc_lateral_sur_static")]
    assert lateral[-1][0] >> 8 < 30                                      # arrêté avant le Static, il ne le traverse pas
    entre_rigid = etats[("pose_pose", "rigid_contre_rigid")]
    assert entre_rigid[-1][6] != 36 << 8 or entre_rigid[-1][7] != 50 << 8   # le second Rigid a reçu de l'impulsion
    libre = etats[("pose_pose", "sans_contact")]
    assert libre[-1][2] == 256                                            # aucun contact : la vitesse horizontale reste
