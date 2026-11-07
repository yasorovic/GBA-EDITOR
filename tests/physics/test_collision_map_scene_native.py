"""La résolution d'un CharacterBody contre la carte de collision, sur le C émis pour une vraie scène.

Le prefab `Hero` (CharacterBody) naît dans le pool partagé ; un posé prend le même chemin (`SLOT_EACH`, type lu à
l'emplacement). Les lignes C sont la table du descripteur de modèle (`model_desc_lines`), le solveur
(`character_solver_lines`, qui porte `body_tile_step`) et la passe unique (`physics_tile_lines`). Les crochets
`on_tile_collide` et `on_crushed` sont lus au descripteur : la sonde compte leurs appels. Un déplacement porté par une
plateforme (`_kin_d`, cf. `physics.kinematic`) s'ajoute à la vitesse le temps de la résolution ; un transport que la
carte arrête écrase le Character. Les cas à une image, sans générateur, sont dans `test_character_native.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 6

# (nom, x, y, vx, vy, porté x, porté y) en pixels et Q8 : la carte a un sol plein sous y = 40 et un mur plein à x = 48.
# Le corps a une boîte « pieds » solide de 17 x 4 en (-7, 11).
SCENARIOS = [
    ("atterrit_a_droite", 33, 22, 512, 1024, 0, 0),
    ("atterrit_a_gauche", 33, 22, -512, 1024, 0, 0),
    ("mur_a_pied", 37, 25, 512, 0, 0, 0),
    ("mur_en_chutant", 37, 22, 512, 1024, 0, 0),
    ("immobile", 33, 25, 0, 0, 0, 0),
    ("porte_contre_le_mur", 37, 25, 0, 0, 512, 0),
    ("porte_libre", 20, 25, 0, 0, 256, 0),
]

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
@HELPERS@

u8 *g_drop_through = 0;
u8 g_support_normal = 1;
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end = @START@, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
static int _kin_d[@SLOTS@][3];
static int appels_carte, appels_ecrase;
void @SYM@_on_tile_collide(Actor* a, int nx, int ny){ appels_carte++; }
void @SYM@_on_crushed(Actor* a, Actor* obstacle){ appels_ecrase++; }
@TABLE@
/* 8 x 6 tuiles : un sol plein sur la rangée 5 (y = 40), un mur plein sur la colonne 6 (x = 48). */
static u8 carte[8 * 6];

static void tick(void){
@TILES@
}
static void joue(const char* nom, int x, int y, int vx, int vy, int cx, int cy){
    int s = @START@;
    for(int k = 0; k < @SLOTS@; k++){ g_actors[k] = (Actor){0}; g_actors[k].slot_index = k; }
    appels_carte = appels_ecrase = 0; g_alive_bits[0] = 0;
    Actor* a = &g_actors[s];
    a->x = x << 8; a->y = y << 8; a->vx = vx; a->vy = vy;
    a->collision.last_x = x;
    a->collision.box_count = 1;
    a->collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    a->active = 1; a->alive = 1; a->type_id = @TYPE@;
    alive_bit_set(s); g_actor_slot_end = s + 1;
    for(int f = 0; f < @FRAMES@; f++){
        /* `apply_velocity()`, puis le transport de la plateforme : il déplace le corps et retient ce qu'il a porté. */
        a->x += a->vx + cx; a->y += a->vy + cy;
        _kin_d[s][0] = cx; _kin_d[s][1] = cy; _kin_d[s][2] = 0;
        tick();
        printf("%s %d %d %d %d %d %d %d\n", nom, a->x >> 8, a->y >> 8, a->vx, a->vy,
               a->collision.grounded, appels_carte, appels_ecrase);
    }
}

int main(void){
    for(int tx = 0; tx < 8; tx++) carte[5 * 8 + tx] = 1;
    for(int ty = 0; ty < 6; ty++) carte[ty * 8 + 6] = 1;
    g_active_cmap = carte; g_cmap_w = 8; g_cmap_h = 6;
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path):
    """La table, le solveur et la passe de carte que le générateur émet pour la scène où `Hero` est spawné."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.character import character_solver_lines, physics_tile_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project

    hero = Prefab(name="Hero")
    hero.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    scene = Scene(name="S", actors=[])
    scene.collision_map = [[1 if (y == 5 or x == 6) else 0 for x in range(8)] for y in range(6)]
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [hero]
    faire_naitre(tmp_path, scene, "Hero")
    pi = scene_pi(p, scene)
    model = next(m for m in pi if m["shared"])
    return {
        "sym": model["sym"],
        "table": model_desc_lines(p, scene, [], pi, [], lambda _s, ev: ev in ("on_tile_collide", "on_crushed")),
        "helpers": character_solver_lines(),
        "tiles": physics_tile_lines(scene, [], pi, kinematic=False, carry=True),
        "type": model["root_type_id"], "start": model["spool"]["start"], "slots": model["spool"]["end"],
    }


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Par scénario, image par image : (x, y, vx, vy, au sol, appels de on_tile_collide, appels de on_crushed)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la carte de collision est vérifiée en CI")
    e = _emissions(tmp_path_factory.mktemp("carte_scene_projet"))
    assert e["table"] and e["tiles"], "rien d'émis : la sonde ne vérifierait rien"
    runs = "\n".join(f'    joue("{n}", {x}, {y}, {vx}, {vy}, {cx}, {cy});' for n, x, y, vx, vy, cx, cy in SCENARIOS)
    source = (SONDE.replace("@HELPERS@", "\n".join(e["helpers"])).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@TILES@", "\n".join(e["tiles"])).replace("@SYM@", e["sym"]).replace("@TYPE@", str(e["type"]))
              .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"]))
              .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
    dossier = tmp_path_factory.mktemp("carte_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[str, list[tuple[int, ...]]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        nom, *valeurs = ligne.split()
        etats.setdefault(nom, []).append(tuple(int(v) for v in valeurs))
    assert all(len(v) == FRAMES for v in etats.values())
    return etats


def test_le_mur_arrete_le_corps_et_appelle_le_crochet(etats):
    fin = etats["mur_a_pied"][-1]
    assert fin[0] == 38 and fin[2] == 0 and fin[5] > 0       # bord droit sur le mur (x = 48), vitesse annulée, crochet
    assert fin[6] == 0


def test_le_mur_arrete_aussi_un_corps_qui_chute(etats):
    fin = etats["mur_en_chutant"][-1]
    assert fin[0] == 38 and fin[2] == 0 and fin[5] > 0


@pytest.mark.parametrize("nom", ["atterrit_a_droite", "atterrit_a_gauche"])
def test_le_sol_arrete_la_chute(etats, nom):
    fin = etats[nom][-1]
    assert fin[1] == 25 and fin[3] == 0 and fin[4] == 1      # pieds (y + 11 .. y + 15) sur le sol (y = 40)


def test_un_corps_immobile_ne_bouge_pas_et_n_appelle_rien(etats):
    assert etats["immobile"][-1][:4] == (33, 25, 0, 0)
    assert etats["immobile"][-1][6] == 0


def test_un_transport_que_la_carte_arrete_ecrase_le_corps(etats):
    ecrase = etats["porte_contre_le_mur"]
    assert ecrase[0][6] == 1 and ecrase[-1][6] == FRAMES     # écrasé à chaque image où le mur arrête le transport
    assert ecrase[-1][2] == 0                                # la vitesse propre (nulle) est rendue


def test_un_transport_libre_porte_le_corps_sans_l_ecraser(etats):
    libre = etats["porte_libre"][-1]
    assert libre[0] == 20 + FRAMES and libre[6] == 0         # porté d'un pixel par image
