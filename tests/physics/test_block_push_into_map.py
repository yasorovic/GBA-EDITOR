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
MOBILE_MODEL, PLATEFORME_MODEL = 1, 2

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
Actor g_actors[4];
int g_spool_start, g_spool_hw;
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
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].inst = i; }
    g_spool_start = 2; g_spool_hw = 2; g_alive_bits[0] = 0;
    for(int i = 0; i < @W@ * @H@; i++) carte[i] = 0;
    for(int tx = 0; tx < @W@; tx++){ carte[(@H@ - 2) * @W@ + tx] = 1; carte[(@H@ - 1) * @W@ + tx] = 1; carte[tx] = 1; carte[@W@ + tx] = 1; }
    for(int ty = 0; ty < @H@; ty++){ carte[ty * @W@] = 1; carte[ty * @W@ + @W@ - 1] = 1; }
    g_active_cmap = carte; g_cmap_w = @W@; g_cmap_h = @H@;
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


def _lignes(tmp_path, mobile_pose: bool, plateforme_pose: bool) -> list[str]:
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor
    from core.project import Project

    project = Project.create(tmp_path / "PousseCarte", "PousseCarte")
    scene = project.active_scene
    scene.collision_map = [[1] * LARGEUR] + [[0] * LARGEUR for _ in range(HAUTEUR - 1)]
    mobile = Actor(name="Mobile", components=[CollisionShapeComponent(solid=True),
                                              PhysicsBodyComponent(mode="CharacterBody")])
    plateforme = Actor(name="Plateforme", components=[CollisionShapeComponent(solid=False, response="block"),
                                                      PhysicsBodyComponent(mode="KinematicBody")])
    posés = [a for a, pose in ((mobile, mobile_pose), (plateforme, plateforme_pose)) if pose]
    pool = [{"shared": True, "model_id": model, "sym": a.name.lower(), "prefab": a}
            for a, pose, model in ((mobile, mobile_pose, MOBILE_MODEL), (plateforme, plateforme_pose, PLATEFORME_MODEL))
            if not pose]
    return block_tick_lines(project, scene, [(a, None) for a in posés], 0, pool, shown)


def _topologie_c(nom: str, mobile_pose: bool, plateforme_pose: bool, lignes: list[str]) -> str:
    cles = (("m", mobile_pose), ("p", plateforme_pose))
    poses = [k for k, pose in cles if pose]
    pool = [k for k, pose in cles if not pose]
    slot = {k: i for i, k in enumerate(poses)} | {k: 2 + i for i, k in enumerate(pool)}
    corps = {"m": "boite(mx, my, 0, 0, 16, 16)", "p": "boite(px, py, pvx, pvy, 32, 32)"}
    placement = [f"    g_actors[{slot[k]}] = {corps[k]}; g_actors[{slot[k]}].inst = {slot[k]};" for k in poses]
    placement += [f"    pose_en_pool({slot[k]}, {corps[k]}, {MOBILE_MODEL if k == 'm' else PLATEFORME_MODEL});"
                  for k in pool]
    m, p = slot["m"], slot["p"]
    return (f"static void topo_{nom}(const char* cas, int mx, int my, int px, int py, int pvx, int pvy){{\n    reinit();\n"
            + "\n".join(placement) + "\n"
            f"    int xmin = 99999, xmax = -99999, ymin = 99999, ymax = -99999;\n"
            f"    for(int f = 0; f < {FRAMES}; f++){{\n"
            f"        g_actors[{p}].x += g_actors[{p}].vx; g_actors[{p}].y += g_actors[{p}].vy;\n"
            + "\n".join(lignes) + "\n"
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
    topologies = []
    for nom, (mobile_pose, plateforme_pose) in TOPOLOGIES.items():
        lignes = _lignes(dossier, mobile_pose, plateforme_pose)
        assert any("mover_in_wall" in ligne for ligne in lignes), (
            f"{nom} ne garde pas la carte après le blocage : le mobile poussé traverserait le mur")
        topologies.append(_topologie_c(nom, mobile_pose, plateforme_pose, lignes))
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
