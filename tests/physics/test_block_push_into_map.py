"""Un bloqueur qui pousse un mobile contre la carte ne le fait pas traverser le mur, le sol ou le plafond.

Le mobile (CharacterBody, boîte de 16 x 16) est immobile, collé à un mur, au sol ou au plafond ; une plateforme Kinematic
de 32 x 32 avance de 1 px par image vers lui, dans les quatre sens. La résolution contre la carte ne bouge un acteur que
d'après sa vitesse (à vitesse nulle, elle le prend pour un téléport), et le blocage annule la vitesse sur l'axe qu'il
repousse : sans garde, le mobile était emporté à travers le mur et hors du niveau ; un déplacement qui l'y ferait entrer est refusé.

Les lignes C sont celles de `block_tick_lines` (avec la carte), le C du solveur est le vrai, la plateforme et le mobile sont
posés ou nés dans le pool.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 160
LARGEUR, HAUTEUR = 30, 20      # tuiles : murs en colonnes 0 et 29, plafond en rangées 0 et 1, sol en rangées 18 et 19

# (nom, x, y du mobile, x, y de la plateforme, vitesse de la plateforme en Q8) : mobile 16 x 16, plateforme 32 x 32.
# Murs : x = 8 et x = 232 ; sol : y = 144 ; plafond : y = 16.
SENS = [
    ("vers_le_mur_gauche", 8, 128, 70, 112, (-256, 0)),
    ("vers_le_mur_droit", 216, 128, 150, 112, (256, 0)),
    ("vers_le_sol", 100, 128, 92, 60, (0, 256)),
    ("vers_le_plafond", 100, 16, 92, 80, (0, -256)),
]
# Les positions que le mobile ne doit jamais quitter : (x min, x max, y min, y max), les boîtes entières dans le niveau.
LIMITES = (8, 216, 16, 128)

TOPOLOGIES = {"pose_pose": (True, True), "plateforme_pool": (True, False), "mobile_pool": (False, True)}

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
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
@BLOCKS@
@SOLVER@
static u8 carte[@W@ * @H@];

static Actor boite(int x, int y, int vx, int vy, int w, int h){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy; a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void reinit(void){
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
    g_spool_start = 2; g_actor_slot_end = 2; g_alive_bits[0] = 0; g_scene_placed = 2;   /* 0 et 1 : les posés */
    for(int i = 0; i < @W@ * @H@; i++) carte[i] = 0;
    for(int tx = 0; tx < @W@; tx++){ carte[(@H@ - 2) * @W@ + tx] = 1; carte[(@H@ - 1) * @W@ + tx] = 1; carte[tx] = 1; carte[@W@ + tx] = 1; }
    for(int ty = 0; ty < @H@; ty++){ carte[ty * @W@] = 1; carte[ty * @W@ + @W@ - 1] = 1; }
    g_active_cmap = carte; g_cmap_w = @W@; g_cmap_h = @H@;
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


def _emissions(tmp_path) -> dict:
    """Les lignes émises pour une vraie scène à carte où les prefabs `Mobile` et `Plateforme` sont posés ET spawnés : un
    seul chemin, chaque topologie ne choisit que les emplacements vivants. Rend aussi le type de chacun."""
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    mobile = Prefab(name="Mobile")
    mobile.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    plateforme = Prefab(name="Plateforme")
    plateforme.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                    PhysicsBodyComponent(mode="KinematicBody")]
    scene = Scene(name="S", physics_enabled=True, actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (mobile, plateforme)])
    scene.collision_map = [[1] * LARGEUR] + [[0] * LARGEUR for _ in range(HAUTEUR - 1)]
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = [mobile, plateforme]
    faire_naitre(tmp_path, scene, "Mobile", "Plateforme")
    pi = scene_pi(project, scene)
    ids = {m["prefab"].name: m["root_type_id"] for m in pi if m["shared"]}
    return {"lines": block_tick_lines(project, scene, [(a, None) for a in scene.actors], pi, resolve_initial_appearance),
            "m": ids["Mobile"], "p": ids["Plateforme"]}


def _topologie_c(nom: str, mobile_pose: bool, plateforme_pose: bool, e: dict) -> str:
    """Le mobile vit à l'emplacement 0 (posé) ou 2 (pool), la plateforme à 1 ou 3."""
    slot = {"m": 0 if mobile_pose else 2, "p": 1 if plateforme_pose else 3}
    corps = {"m": "boite(mx, my, 0, 0, 16, 16)", "p": "boite(px, py, pvx, pvy, 32, 32)"}
    placement = []
    for k, pose in (("m", mobile_pose), ("p", plateforme_pose)):
        if pose:
            placement.append(f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].slot_index = {slot[k]}; alive_bit_set({slot[k]});"
                             f" g_actors[{slot[k]}].type_id = {e[k]};")
        else:
            placement.append(f"    pose_en_pool({slot[k]}, {corps[k]}, {e[k]});")
    m, p = slot["m"], slot["p"]
    return (f"static void topo_{nom}(const char* cas, int mx, int my, int px, int py, int pvx, int pvy){{\n    reinit();\n"
            + "\n".join(placement) + "\n"
            f"    int xmin = 99999, xmax = -99999, ymin = 99999, ymax = -99999;\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            f"        g_actors[{p}].x += g_actors[{p}].vx; g_actors[{p}].y += g_actors[{p}].vy;\n"
            + "\n".join(e["lines"]) + "\n"
            f"        int x = g_actors[{m}].x >> 8, y = g_actors[{m}].y >> 8;\n"
            "        if(x < xmin) xmin = x; if(x > xmax) xmax = x; if(y < ymin) ymin = y; if(y > ymax) ymax = y;\n"
            "    }\n"
            f"    printf(\"{nom} %s %d %d %d %d %d %d\\n\", cas, xmin, xmax, ymin, ymax, g_actors[{m}].x >> 8, g_actors[{m}].y >> 8);\n"
            "}\n")


@pytest.fixture(scope="module")
def trajets(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines
    from codegen.runtime_codegen.physics.character import character_solver_lines

    dossier = tmp_path_factory.mktemp("pousse_carte")
    emis = _emissions(dossier)
    assert any("mover_in_wall" in ligne for ligne in emis["lines"]), (
        "le blocage ne garde pas la carte : le mobile poussé traverserait le mur")
    topologies = []
    for nom, (mobile_pose, plateforme_pose) in TOPOLOGIES.items():
        topologies.append(_topologie_c(nom, mobile_pose, plateforme_pose, emis))
    runs = "\n".join(f'    topo_{nom}("{cas}", {mx}, {my}, {px}, {py}, {vx}, {vy});'
                     for cas, mx, my, px, py, (vx, vy) in SENS for nom in TOPOLOGIES)
    source = (SONDE.replace("@BLOCKS@", "\n".join(block_helper_lines()))
              .replace("@SOLVER@", "\n".join(character_solver_lines(False)))
              .replace("@W@", str(LARGEUR)).replace("@H@", str(HAUTEUR))
              .replace("@TOPOLOGIES@", "\n".join(topologies)).replace("@RUNS@", runs))
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    resultats: dict[tuple[str, str], tuple[int, ...]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        topologie, cas, *valeurs = ligne.split()
        resultats[(cas, topologie)] = tuple(int(v) for v in valeurs)
    return resultats


@pytest.mark.parametrize("topologie", list(TOPOLOGIES))
@pytest.mark.parametrize("cas", [s[0] for s in SENS])
def test_le_mobile_pousse_reste_dans_le_niveau_dans_les_quatre_sens(trajets, cas, topologie):
    """(x min, x max, y min, y max) sur toute la durée : jamais dans le mur, le sol ni le plafond."""
    xmin, xmax, ymin, ymax, _x, _y = trajets[(cas, topologie)]
    x_min, x_max, y_min, y_max = LIMITES
    assert x_min <= xmin and xmax <= x_max and y_min <= ymin and ymax <= y_max, (xmin, xmax, ymin, ymax)
