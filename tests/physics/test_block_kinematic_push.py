"""Une plateforme Kinematic qui glisse sur un Character immobile le pousse de côté, jamais dans le sol.

Le mobile (CharacterBody) est une boîte de pieds de 17 x 4 posée sur le sol (y = 177, bas à 192). Le bloqueur est une
boîte de 32 x 32 posée à plat sur ce sol (haut 160, bas 192) qui avance de 1 px par image vers lui. Avant la correction, un
mobile immobile n'était pas poussé : le recouvrement dépassait la hauteur de ses pieds, puis l'axe vertical l'emportait
et le poussait de 4 px vers le bas. Un bloqueur immobile (Static) ou un Rigid ne pousse toujours que ce qui bouge.

Les lignes C sont celles de `block_tick_lines`, pour le bloqueur posé puis né dans le pool.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 40

# (nom du cas, mode du bloqueur, vitesse du bloqueur en Q8, vitesse du mobile en Q8)
CAS = [
    ("kinematic_sur_joueur_immobile", "KinematicBody", -256, 0),
    ("kinematic_sur_joueur_qui_avance", "KinematicBody", -256, 512),
    ("static_ne_pousse_pas_un_immobile", "StaticBody", 0, 0),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
u8 *g_drop_through = 0;
Actor g_actors[4];
int g_spool_start, g_spool_hw;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static Actor boite(int x, int y, int vx, int w, int h, int ox, int oy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){ox, oy, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
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


def _lignes(tmp_path, mode: str, bloqueur_pose: bool) -> list[str]:
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / f"Pousse_{mode}", "Pousse")
    scene = project.active_scene
    joueur = Actor(name="Joueur", components=[CollisionShapeComponent(solid=True),
                                              PhysicsBodyComponent(mode="CharacterBody")])
    bloqueur = Actor(name="Bloqueur", components=[CollisionShapeComponent(solid=False, response="block"),
                                                  PhysicsBodyComponent(mode=mode)])
    posés = [joueur] + ([bloqueur] if bloqueur_pose else [])
    pool = [] if bloqueur_pose else [{"shared": True, "model_id": 2, "sym": "bloqueur", "prefab": bloqueur}]
    return block_tick_lines(project, scene, [(a, None) for a in posés], 0, pool, shown)


def _topologie_c(nom: str, bloqueur_pose: bool, lignes: list[str]) -> str:
    slot = 1 if bloqueur_pose else 2
    placement = (f"    g_actors[{slot}] = boite(bx, 160, bvx, 32, 32, 0, 0); g_actors[{slot}].inst = {slot};"
                 if bloqueur_pose else f"    pose_en_pool({slot}, boite(bx, 160, bvx, 32, 32, 0, 0), 2);")
    return (f"static void topo_{nom}(const char* cas, int bvx, int mvx){{\n    int bx = 90;\n    reinit();\n"
            "    g_actors[0] = boite(60, 177, mvx, 17, 4, -7, 11); g_actors[0].inst = 0;\n"
            f"{placement}\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            f"        g_actors[{slot}].x += g_actors[{slot}].vx; g_actors[0].x += g_actors[0].vx;\n"
            + "\n".join(lignes) + "\n"
            f"        printf(\"{nom} %s %d %d %d\\n\", cas, f, g_actors[0].x >> 8, g_actors[0].y >> 8);\n"
            "    }\n}\n")


@pytest.fixture(scope="module")
def trajets(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines

    dossier = tmp_path_factory.mktemp("pousse_kinematic")
    resultats: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for cas, mode, bvx, mvx in CAS:
        topologies = []
        for nom, pose in (("pose", True), ("pool", False)):
            lignes = _lignes(dossier, mode, pose)
            assert any("actors_resolve_blocks" in ligne for ligne in lignes)
            topologies.append(_topologie_c(nom, pose, lignes))
        runs = "\n".join(f'    topo_{nom}("{cas}", {bvx}, {mvx});' for nom in ("pose", "pool"))
        source = (SONDE.replace("@HELPERS@", "\n".join(block_helper_lines()))
                  .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
        dossier_cas = dossier / cas
        dossier_cas.mkdir()
        (dossier_cas / "probe.c").write_text(source, encoding="utf-8")
        binaire = dossier_cas / "probe"
        construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                    "-o", str(binaire), str(dossier_cas / "probe.c")],
                                   capture_output=True, text=True, env=environnement(compilateur))
        assert construit.returncode == 0, construit.stderr
        sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
        for ligne in sortie.stdout.strip().splitlines():
            topologie, nom, _frame, x, y = ligne.split()
            resultats.setdefault((nom, topologie), []).append((int(x), int(y)))
    return resultats


@pytest.mark.parametrize("topologie", ["pose", "pool"])
@pytest.mark.parametrize("cas", ["kinematic_sur_joueur_immobile", "kinematic_sur_joueur_qui_avance"])
def test_une_plateforme_kinematic_pousse_de_cote_sans_enfoncer_le_joueur_dans_le_sol(trajets, cas, topologie):
    trajet = trajets[(cas, topologie)]
    assert all(y == 177 for _, y in trajet), "le joueur est resté sur le sol, jamais poussé vers le bas"
    assert trajet[-1][0] < 60, "la plateforme a poussé le joueur vers la gauche"


def test_un_bloqueur_static_ne_pousse_pas_un_acteur_immobile(trajets):
    for topologie in ("pose", "pool"):
        assert set(trajets[("static_ne_pousse_pas_un_immobile", topologie)]) == {(60, 177)}


def test_le_pool_et_le_pose_donnent_les_memes_trajets(trajets):
    for cas, _mode, _bvx, _mvx in CAS:
        assert trajets[(cas, "pose")] == trajets[(cas, "pool")]
