"""Parité posé / spawné du blocage entre acteurs : quatre topologies, un seul résultat.

Le mobile (CharacterBody) et le bloqueur (StaticBody, réponse `block`) sont chacun posé ou né dans le pool :
posé/posé, posé/pool, pool/posé, pool/pool. Les lignes C sont celles de `block_tick_lines` pour une vraie scène où les
deux prefabs sont posés ET spawnés (un seul chemin : chaque topologie ne choisit que ses emplacements vivants),
compilées avec les aides C réelles ; le mobile fait un pas puis le blocage le repousse. Les quatre topologies
doivent donner exactement le même état que posé/posé, qui sert de référence.

Voir `test_parity_posed_spawned.py` pour la règle et pour la première passe (carte de collision).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# (nom, x, y, vx, vy) du mobile avant son pas, en pixels et Q8. Le bloqueur occupe (40,40)-(56,56); le mobile
# est une boîte de 8 x 8.
SCENARIOS = [
    ("mur_par_la_gauche", 30, 44, 2048, 0),
    ("sol_par_le_haut", 44, 30, 0, 2560),
    ("diagonale", 33, 33, 1536, 1536),
    ("sans_contact", 0, 0, 256, 256),
    ("immobile_dans_le_bloqueur", 44, 44, 0, 0),
]

# topologie -> (mobile posé ?, bloqueur posé ?)
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
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS                                 /* hors GBA : mémoire ordinaire */
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
Actor g_actors[4];
int g_spool_start, g_spool_hw, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static Actor mobile(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, 8, 8, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static Actor bloqueur(void){
    Actor a = (Actor){0};
    a.x = 40 << 8; a.y = 40 << 8;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, 16, 16, 0, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void rapporte(const char* topo, const char* nom, const Actor* a){
    printf("%s %s %d %d %d %d\n", topo, nom, a->x >> 8, a->y >> 8, a->vx, a->vy);
}
/* Les emplacements 0 et 1 sont posés, 2 et 3 sont le pool partagé (g_spool_start = 2). */
static void reinit(void){
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].inst = i; }
    g_spool_start = 2; g_spool_hw = 2; g_alive_bits[0] = 0; g_scene_placed = 2;   /* 0 et 1 : les posés */
}
static void pose_en_pool(int slot, Actor a, int model){
    a.inst = slot; a.model = model; g_actors[slot] = a;
    if(slot + 1 > g_spool_hw) g_spool_hw = slot + 1;
    alive_bit_set(slot);
}
@TOPOLOGIES@

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path) -> dict:
    """Les lignes que le générateur émet pour une vraie scène où les prefabs `Mobile` et `Bloqueur` sont chacun posé
    (emplacements 0 et 1) ET spawnés (pool partagé). Une seule émission pour les quatre topologies : le chemin est
    unique, chaque topologie ne choisit que les emplacements vivants."""
    import copy
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    mobile = Prefab(name="Mobile")
    mobile.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    bloqueur = Prefab(name="Bloqueur")
    bloqueur.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                  PhysicsBodyComponent(mode="StaticBody")]
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (mobile, bloqueur)])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [mobile, bloqueur]
    faire_naitre(tmp_path, scene, "Mobile", "Bloqueur")
    pi = scene_pi(p, scene)
    ids = {m["prefab"].name: m["model_id"] for m in pi if m["shared"]}
    return {"lines": block_tick_lines(p, scene, [(a, None) for a in scene.actors], pi, shown),
            "placed": scene_oam_layout(p, scene).placed_model, "mobile": ids["Mobile"], "bloqueur": ids["Bloqueur"]}


def _topologie_c(nom: str, mobile_pose: bool, bloqueur_pose: bool, e: dict) -> str:
    """Le mobile vit à l'emplacement 0 (posé) ou 2 (pool), le bloqueur à 1 ou 3 ; l'autre emplacement de chacun reste
    vide. Posé ou né, un emplacement porte le type de son prefab."""
    slot = {"m": 0 if mobile_pose else 2, "b": 1 if bloqueur_pose else 3}
    placement = []
    for k, pose in (("m", mobile_pose), ("b", bloqueur_pose)):
        model = e["mobile"] if k == "m" else e["bloqueur"]
        acteur = "mobile(x, y, vx, vy)" if k == "m" else "bloqueur()"
        if pose:
            placement.append(f"    g_actors[{slot[k]}] = {acteur}; g_actors[{slot[k]}].inst = {slot[k]}; alive_bit_set({slot[k]});"
                             f" g_actors[{slot[k]}].model = {model};")
        else:
            placement.append(f"    pose_en_pool({slot[k]}, {acteur}, {model});")
    m = slot["m"]
    body = "\n".join(e["lines"])
    return (f"static void topo_{nom}(const char* nom, int x, int y, int vx, int vy){{\n    reinit();\n"
            + "\n".join(placement)
            + f"\n    g_actors[{m}].x += g_actors[{m}].vx; g_actors[{m}].y += g_actors[{m}].vy;\n{body}\n"
            f"    rapporte(\"{nom}\", nom, &g_actors[{m}]);\n}}\n")


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_blocage_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines

    dossier = tmp_path_factory.mktemp("parite_blocage")
    assert any("actors_resolve_blocks" in ligne for ligne in emissions["lines"]), (
        "aucun blocage émis : la sonde ne comparerait rien")
    topologies = [_topologie_c(nom, mobile_pose, bloqueur_pose, emissions)
                  for nom, (mobile_pose, bloqueur_pose) in TOPOLOGIES.items()]
    runs = "\n".join(f'    topo_{nom}("{n}", {x}, {y}, {vx}, {vy});'
                     for n, x, y, vx, vy in SCENARIOS for nom in TOPOLOGIES)
    source = (SONDE.replace("@HELPERS@", "\n".join(block_helper_lines()))
              .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[tuple[str, str], tuple[int, ...]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        topologie, nom, *valeurs = ligne.split()
        etats[(topologie, nom)] = tuple(int(v) for v in valeurs)
    return etats


def test_le_pose_et_le_ne_d_un_prefab_ont_le_meme_type(emissions):
    """Les copies posées identiques au prefab prennent son `model_id` : posé ou né, la même ligne des tables."""
    assert emissions["placed"] == [emissions["mobile"], emissions["bloqueur"]]


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "pose_pose"])
@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_le_blocage_donne_le_meme_etat_quelle_que_soit_l_origine_des_deux_acteurs(etats, nom, topologie):
    """(x, y, vx, vy) du mobile après le blocage, identiques à ceux du cas posé/posé."""
    assert etats[("pose_pose", nom)] == etats[(topologie, nom)]


def test_la_reference_pose_pose_bloque_vraiment(etats):
    """Sans cela, quatre états égaux mais sans blocage passeraient pour une parité."""
    assert etats[("pose_pose", "mur_par_la_gauche")] == (32, 44, 0, 0)       # repoussé de 6 px, vitesse annulée
    assert etats[("pose_pose", "sol_par_le_haut")] == (44, 32, 0, 0)         # posé sur le dessus, axe vertical
    assert etats[("pose_pose", "diagonale")] == (32, 39, 0, 1536)            # égalité : l'horizontale, il glisse
    assert etats[("pose_pose", "sans_contact")] == (1, 1, 256, 256)
    assert etats[("pose_pose", "immobile_dans_le_bloqueur")] == (44, 44, 0, 0)
