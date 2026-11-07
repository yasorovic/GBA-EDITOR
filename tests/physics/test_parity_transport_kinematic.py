"""Parité posé / spawné du transport par une plateforme Kinematic : quatre topologies, un seul résultat.

La plateforme (KinematicBody) et son passager (CharacterBody) sont chacun posé ou né dans le pool : posé/posé, posé/pool,
pool/posé, pool/pool. Les lignes C sont celles de `kinematic_tick_parts` pour une vraie scène où les deux prefabs sont
posés ET spawnés (un seul chemin), compilées avec l'aide C réelle (`kinematic_carry_all`) ; à chaque image la plateforme avance de sa vitesse, puis le passager est porté. Les quatre
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

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define EWRAM_BSS
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
u8 g_support_normal = 1;
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


def _emissions(tmp_path) -> dict:
    """(avant, après, types) que le générateur émet pour une vraie scène où les prefabs `Plateforme` et `Passager` sont
    posés (emplacements 0 et 1) ET spawnés : un seul chemin, chaque topologie ne choisit que ses emplacements vivants."""
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    plateforme = Prefab(name="Plateforme")
    plateforme.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                    PhysicsBodyComponent(mode="KinematicBody")]
    passager = Prefab(name="Passager")
    passager.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (plateforme, passager)])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = [plateforme, passager]
    faire_naitre(tmp_path, scene, "Plateforme", "Passager")
    pi = scene_pi(project, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    before, after, _crush = kinematic_tick_parts(project, [(a, None) for a in scene.actors], 0, scene, pi, shown)
    return {"before": before, "after": after, "k": ids["Plateforme"], "a": ids["Passager"]}


def _topologie_c(nom: str, plateforme_pose: bool, passager_pose: bool, e: dict) -> str:
    """La plateforme vit à l'emplacement 0 (posé) ou 2 (pool), le passager à 1 ou 3 ; posé ou né, le type de son
    prefab."""
    slot = {"k": 0 if plateforme_pose else 2, "a": 1 if passager_pose else 3}
    corps = {"k": "corps(40, 50, kvx, kvy, 24, 8)", "a": "corps(x, y, 0, vy, 8, 8)"}
    placement = []
    for k, pose in (("k", plateforme_pose), ("a", passager_pose)):
        if pose:
            placement.append(f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].inst = {slot[k]};"
                             f" g_actors[{slot[k]}].model = {e[k]};")
        else:
            placement.append(f"    pose_en_pool({slot[k]}, {corps[k]}, {e[k]});")
    k, a = slot["k"], slot["a"]
    dx, dy = f"_kin_d[{a}][0]", f"_kin_d[{a}][1]"      # une ligne par emplacement, posé ou né
    return (f"static void topo_{nom}(const char* nom, int kvx, int kvy, int x, int y, int vy){{\n    reinit();\n"
            + "\n".join(placement) + "\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            + "\n".join(e["before"]) + "\n"
            f"        g_actors[{k}].x += g_actors[{k}].vx; g_actors[{k}].y += g_actors[{k}].vy;\n"
            + "\n".join(e["after"]) + "\n"
            f"        rapporte(\"{nom}\", nom, f, &g_actors[{k}], &g_actors[{a}], {dx}, {dy});\n"
            "    }\n}\n")


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_transport_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines

    dossier = tmp_path_factory.mktemp("parite_transport")
    assert any("kinematic_carry_all" in ligne for ligne in emissions["after"]), (
        "aucun transport émis : la sonde ne comparerait rien")
    topologies = [_topologie_c(nom, plateforme_pose, passager_pose, emissions)
                  for nom, (plateforme_pose, passager_pose) in TOPOLOGIES.items()]
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
