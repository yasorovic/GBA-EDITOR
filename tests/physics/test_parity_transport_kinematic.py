"""Parité posé / spawné du transport par une plateforme Kinematic : quatre topologies, un seul résultat.

La plateforme (KinematicBody) et son passager (CharacterBody) sont chacun posé ou né dans le pool : posé/posé, posé/pool,
pool/posé, pool/pool. Les lignes C sont celles de `kinematic_tick_parts` pour chaque topologie, compilées avec l'aide C
réelle (`kinematic_carry`) ; à chaque image la plateforme avance de sa vitesse, puis le passager est porté. Les quatre
topologies doivent donner exactement le même état, image par image, que posé/posé, qui sert de référence : position du
passager et déplacement porté (celui que la résolution contre la carte ajoute à sa vitesse).

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 20

# (nom, vx, vy de la plateforme en Q8, x, y, vy du passager en pixels et Q8) : la plateforme occupe (40,50)-(64,58) au
# départ, le passager est une boîte de 8 x 8 posée dessus (bas = 50) sauf mention contraire.
SCENARIOS = [
    ("glisse_a_droite", 512, 0, 48, 42, 0),
    ("monte", 0, -256, 48, 42, 0),
    ("passager_qui_saute", 512, 0, 48, 42, -256),
    ("passager_hors_plateforme", 512, 0, 200, 42, 0),
    ("plateforme_immobile", 0, 0, 48, 42, 0),
]

TOPOLOGIES = {
    "pose_pose": (True, True),
    "pose_pool": (True, False),
    "pool_pose": (False, True),
    "pool_pool": (False, False),
}

PLATEFORME_MODEL, PASSAGER_MODEL = 1, 2

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define EWRAM_BSS
#define G_ACTOR_COUNT 4
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
static void rapporte(const char* topo, const char* nom, int f, const Actor* k, const Actor* a, int dx, int dy){
    printf("%s %s %d %d %d %d %d %d %d\n", topo, nom, f, k->x, k->y, a->x, a->y, dx, dy);
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


def _parts(tmp_path, plateforme_pose: bool, passager_pose: bool):
    """(avant, après, passagers posés) que le générateur émet pour cette topologie (plateforme et passager)."""
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / "Transport", "Transport")
    scene = project.active_scene
    plateforme = Actor(name="Plateforme", components=[CollisionShapeComponent(solid=False, response="block"),
                                                      PhysicsBodyComponent(mode="KinematicBody")])
    passager = Actor(name="Passager", components=[CollisionShapeComponent(solid=True),
                                                  PhysicsBodyComponent(mode="CharacterBody")])
    posés = [a for a, pose in ((plateforme, plateforme_pose), (passager, passager_pose)) if pose]
    pool = [{"shared": True, "model_id": model, "sym": a.name.lower(), "prefab": a,
             "spool": {"start": 2, "end": 4}}
            for a, pose, model in ((plateforme, plateforme_pose, PLATEFORME_MODEL),
                                   (passager, passager_pose, PASSAGER_MODEL)) if not pose]
    return kinematic_tick_parts(project, [(a, None) for a in posés], 0, scene, pool, shown)


def _topologie_c(nom: str, plateforme_pose: bool, passager_pose: bool, before, after) -> str:
    cles = (("k", plateforme_pose), ("a", passager_pose))
    poses = [k for k, pose in cles if pose]
    pool = [k for k, pose in cles if not pose]
    slot = {k: i for i, k in enumerate(poses)} | {k: 2 + i for i, k in enumerate(pool)}
    corps = {"k": "corps(40, 50, kvx, kvy, 24, 8)", "a": "corps(x, y, 0, vy, 8, 8)"}
    placement = []
    for k in poses:
        placement.append(f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].inst = {slot[k]};")
    for k in pool:
        placement.append(f"    pose_en_pool({slot[k]}, {corps[k]}, {PLATEFORME_MODEL if k == 'k' else PASSAGER_MODEL});")
    k, a = slot["k"], slot["a"]
    dx, dy = f"_kin_d[{a}][0]", f"_kin_d[{a}][1]"      # une ligne par emplacement, posé ou né
    return (f"static void topo_{nom}(const char* nom, int kvx, int kvy, int x, int y, int vy){{\n    reinit();\n"
            + "\n".join(placement) + "\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            + "\n".join(before) + "\n"
            f"        g_actors[{k}].x += g_actors[{k}].vx; g_actors[{k}].y += g_actors[{k}].vy;\n"
            + "\n".join(after) + "\n"
            f"        rapporte(\"{nom}\", nom, f, &g_actors[{k}], &g_actors[{a}], {dx}, {dy});\n"
            "    }\n}\n")


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines

    dossier = tmp_path_factory.mktemp("parite_transport")
    topologies = []
    for nom, (plateforme_pose, passager_pose) in TOPOLOGIES.items():
        before, after, _carried = _parts(dossier, plateforme_pose, passager_pose)
        assert any("kinematic_carry" in ligne for ligne in after), (
            f"la topologie {nom} n'émet aucun transport : la sonde ne comparerait rien")
        topologies.append(_topologie_c(nom, plateforme_pose, passager_pose, before, after))
    runs = "\n".join(f'    topo_{nom}("{n}", {kvx}, {kvy}, {x}, {y}, {vy});'
                     for n, kvx, kvy, x, y, vy in SCENARIOS for nom in TOPOLOGIES)
    source = (SONDE.replace("@HELPERS@", "\n".join(kinematic_helper_lines()))
              .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str], list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        topologie, nom, _frame, *valeurs = ligne.split()
        etats.setdefault((topologie, nom), []).append(tuple(int(v) for v in valeurs))
    return etats


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "pose_pose"])
@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_le_transport_donne_le_meme_etat_quelle_que_soit_l_origine_des_deux_acteurs(etats, nom, topologie):
    """(x, y de la plateforme, x, y du passager, déplacement porté), image par image, identiques à posé/posé."""
    assert len(etats[("pose_pose", nom)]) == FRAMES
    assert etats[("pose_pose", nom)] == etats[(topologie, nom)]


def test_la_reference_pose_pose_porte_vraiment(etats):
    """Sans cela, des états égaux mais sans transport passeraient pour une parité."""
    glisse = etats[("pose_pose", "glisse_a_droite")][-1]
    assert glisse[2] - (48 << 8) == FRAMES * 512                         # le passager a suivi la plateforme, une fois par image
    monte = etats[("pose_pose", "monte")][-1]
    assert monte[3] - (42 << 8) == -FRAMES * 256
    assert etats[("pose_pose", "passager_qui_saute")][-1][2] == 48 << 8   # il s'éloigne : pas porté
    assert etats[("pose_pose", "passager_hors_plateforme")][-1][2] == 200 << 8
