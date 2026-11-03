"""Parité posé / spawné du solveur d'impulsions : quatre topologies, un seul résultat.

Un Rigid et son partenaire (StaticBody ou autre Rigid) sont chacun posé ou né dans le pool : posé/posé, posé/pool,
pool/posé, pool/pool. Les lignes C sont celles d'`impulse_tick_lines` pour chaque topologie, compilées avec les aides C
réelles ; à chaque image le Rigid reçoit la gravité puis avance, et le solveur résout le contact. Les quatre
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

MOBILE_MODEL, PARTENAIRE_MODEL = 1, 2

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
#define BS_ATTR_IWRAM
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


def _tick_lines(tmp_path, partenaire_mode: str, mobile_pose: bool, partenaire_pose: bool) -> list[str]:
    """Les lignes que le générateur émet pour cette topologie (mobile = Rigid, partenaire = Static ou Rigid)."""
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / f"Impulsions_{partenaire_mode}", "Impulsions")
    scene = project.active_scene
    mobile = Actor(name="Mobile", components=[CollisionShapeComponent(solid=True, response="block"),
                                              PhysicsBodyComponent(mode="RigidBody")])
    partenaire = Actor(name="Partenaire", components=[CollisionShapeComponent(solid=True, response="block"),
                                                      PhysicsBodyComponent(mode=partenaire_mode)])
    posés = [a for a, pose in ((mobile, mobile_pose), (partenaire, partenaire_pose)) if pose]
    pool = [{"shared": True, "model_id": model, "sym": a.name.lower(), "prefab": a}
            for a, pose, model in ((mobile, mobile_pose, MOBILE_MODEL), (partenaire, partenaire_pose, PARTENAIRE_MODEL))
            if not pose]
    return impulse_tick_lines(project, scene, [(a, None) for a in posés], 0, pool, shown)


def _topologie_c(nom: str, mobile_pose: bool, partenaire_pose: bool, lines: list[str]) -> str:
    # Les posés prennent les emplacements 0, 1 dans l'ordre mobile, partenaire; ceux du pool, 2 puis 3.
    cles = (("m", mobile_pose), ("p", partenaire_pose))
    poses = [k for k, pose in cles if pose]
    pool = [k for k, pose in cles if not pose]
    slot = {k: i for i, k in enumerate(poses)} | {k: 2 + i for i, k in enumerate(pool)}
    corps = {"m": "corps(x, y, vx, vy, 8, 8)", "p": "corps(px, py, 0, 0, pw, ph)"}
    placement = []
    for k in poses:
        placement.append(f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].inst = {slot[k]};")
    for k in pool:
        placement.append(f"    pose_en_pool({slot[k]}, {corps[k]}, {MOBILE_MODEL if k == 'm' else PARTENAIRE_MODEL});")
    m, p = slot["m"], slot["p"]
    body = "\n".join(lines)
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
        topologies = []
        for nom, (mobile_pose, partenaire_pose) in TOPOLOGIES.items():
            lignes = _tick_lines(dossier, mode, mobile_pose, partenaire_pose)
            assert any("rigid_pairs_scan" in ligne or "rigid_pool_pass" in ligne for ligne in lignes), (
                f"la topologie {nom} n'émet aucune impulsion : la sonde ne comparerait rien")
            topologies.append(_topologie_c(nom, mobile_pose, partenaire_pose, lignes))
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
