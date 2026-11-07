"""Parité posé / spawné : le C ÉMIS pour un acteur posé et pour le même modèle né dans le pool donne le même état.

Règle (`.claude/rules/lua-api.md`) : un acteur posé est un spawn fait au build. Le test prend les lignes que
le générateur émet vraiment pour chaque chemin, les compile dans une sonde native, fait vivre le même corps
posé puis spawné pendant N frames, et compare l'état image par image. Un chemin du pool qui diverge du posé
(ou qui manque) casse ici, pas en jouant.

Ici : la résolution contre la carte de collision. Une vraie scène où le prefab `Hero` (CharacterBody) est posé une fois
ET spawné par le script de scène ; les lignes C sont la table du descripteur de modèle (`model_desc_lines`), le solveur
(`character_solver_lines`, qui porte `body_tile_step`) et la passe unique (`physics_tile_lines`). Les crochets
`on_tile_collide` et `on_crushed` sont lus au descripteur : la sonde compte leurs appels. Un déplacement porté par une
plateforme (`_kin_d`, cf. `physics.kinematic`) s'ajoute à la vitesse le temps de la résolution ; un transport que la
carte arrête écrase le Character.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 6

# (nom, x, y, vx, vy, porté x, porté y) en pixels et Q8 : les cas de test_character_native, jouables sur plusieurs
# frames, puis deux transports par une plateforme (contre le mur : écrasé ; en terrain libre : rien).
SCENARIOS = [
    ("atterrit_a_droite", 33, 22, 512, 1024, 0, 0),
    ("atterrit_a_gauche", 33, 22, -512, 1024, 0, 0),
    ("atterrit_lentement", 33, 24, 512, 300, 0, 0),
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
Actor g_actors[2];
int g_spool_start = 1, g_spool_hw = 1;
u32 g_alive_bits[1], g_alive_epoch;
static int _kin_d[2][3];
static int appels_carte[2], appels_ecrase[2];
void @SYM@_on_tile_collide(Actor* a, int nx, int ny){ appels_carte[a->inst]++; }
void @SYM@_on_crushed(Actor* a, Actor* obstacle){ appels_ecrase[a->inst]++; }
@TABLE@
/* 8 x 6 tuiles : un sol plein sur la rangée 5 (y = 40), un mur plein sur la colonne 6 (x = 48). */
static u8 carte[8 * 6];

static void tick(void){
@TILES@
}
/* Le même corps pour les deux chemins : une boîte « pieds » solide de 17 x 4 en (-7, 11). Un seul emplacement vivant :
   le posé (0, son type de posé) ou le né (1, le `model_id` du prefab). */
static void joue(const char* chemin, const char* nom, int x, int y, int vx, int vy, int cx, int cy){
    for(int k = 0; k < 2; k++){ g_actors[k] = (Actor){0}; g_actors[k].inst = k; appels_carte[k] = appels_ecrase[k] = 0; }
    g_alive_bits[0] = 0; g_spool_hw = 1;
    int s = chemin[1] == 'o' && chemin[2] == 's' ? 0 : 1;   /* "pose" ou "pool" */
    Actor* a = &g_actors[s];
    a->x = x << 8; a->y = y << 8; a->vx = vx; a->vy = vy;
    a->collision.last_x = x;
    a->collision.box_count = 1;
    a->collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    a->active = 1; a->alive = 1;
    if(s == 0) a->model = @TYPE_POSE@;
    else { a->model = @TYPE_NE@; pool_bit_set(1); g_spool_hw = 2; }
    for(int f = 0; f < @FRAMES@; f++){
        /* `apply_velocity()`, puis le transport de la plateforme : il déplace le corps et retient ce qu'il a porté. */
        a->x += a->vx + cx; a->y += a->vy + cy;
        _kin_d[s][0] = cx; _kin_d[s][1] = cy; _kin_d[s][2] = 0;
        tick();
        printf("%s %s %d %d %d %d %d %d %d %d\n", chemin, nom, f, a->x >> 8, a->y >> 8, a->vx, a->vy,
               a->collision.grounded, appels_carte[s], appels_ecrase[s]);
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
    """La table, le solveur et la passe de carte que le générateur émet pour la scène où `Hero` est posé et spawné."""
    import copy
    from codegen.oam_alloc import scene_oam_layout
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.character import character_solver_lines, physics_tile_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project

    hero = Prefab(name="Hero")
    hero.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    scene = Scene(name="S", actors=[Actor(name="HeroPose", prefab_name="Hero",
                                          components=copy.deepcopy(hero.actor.components))])
    scene.collision_map = [[1 if (y == 5 or x == 6) else 0 for x in range(8)] for y in range(6)]
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [hero]
    faire_naitre(tmp_path, scene, "Hero")
    pi = scene_pi(p, scene)
    model = next(m for m in pi if m["shared"])
    actors = [(a, None) for a in scene.actors]
    return {
        "sym": model["sym"],
        # Le posé et le né appellent le même code : les deux crochets existent, la table les cite pour l'un et l'autre.
        "table": model_desc_lines(p, scene, actors, pi, [model["sym"]],
                                  lambda _s, ev: ev in ("on_tile_collide", "on_crushed")),
        "helpers": character_solver_lines(),
        "tiles": physics_tile_lines(scene, actors, 0, pi, kinematic=False, carry=True),
        "type_pose": scene_oam_layout(p, scene).placed_model[0],
        "type_ne": model["model_id"],
    }


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_carte_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    e = emissions
    assert e["table"] and e["tiles"], "rien d'émis : la sonde ne comparerait rien"
    dossier = tmp_path_factory.mktemp("parite")
    runs = "\n".join(f'    joue("pose", "{n}", {x}, {y}, {vx}, {vy}, {cx}, {cy}); '
                     f'joue("pool", "{n}", {x}, {y}, {vx}, {vy}, {cx}, {cy});'
                     for n, x, y, vx, vy, cx, cy in SCENARIOS)
    source = (SONDE.replace("@HELPERS@", "\n".join(e["helpers"])).replace("@TABLE@", "\n".join(e["table"]))
              .replace("@TILES@", "\n".join(e["tiles"])).replace("@SYM@", e["sym"])
              .replace("@TYPE_POSE@", str(e["type_pose"])).replace("@TYPE_NE@", str(e["type_ne"]))
              .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
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
        chemin, nom, *valeurs = ligne.split()
        etats.setdefault((chemin, nom), []).append(tuple(int(v) for v in valeurs[1:]))
    return etats


def test_un_pose_et_un_ne_ont_chacun_leur_type(emissions):
    """Sans cela, la sonde lirait la même ligne de table pour les deux chemins et ne comparerait rien."""
    assert emissions["type_pose"] != emissions["type_ne"]


@pytest.mark.parametrize("nom", [s[0] for s in SCENARIOS])
def test_la_carte_de_collision_donne_le_meme_etat_pose_et_spawne(etats, nom):
    """(x, y, vx, vy, au_sol, appels de on_tile_collide, appels de on_crushed), image par image, identiques pour
    l'acteur posé et pour son jumeau du pool."""
    assert len(etats[("pose", nom)]) == FRAMES
    assert etats[("pool", nom)] == etats[("pose", nom)]


def test_la_reference_pose_heurte_vraiment_la_carte(etats):
    """Sans cela, des états égaux mais sans collision passeraient pour une parité."""
    mur = etats[("pose", "mur_a_pied")][-1]
    assert mur[0] == 38 and mur[2] == 0 and mur[5] > 0          # bord droit sur le mur (x = 48), vitesse annulée, crochet
    assert etats[("pose", "atterrit_a_droite")][-1][4] == 1      # posé sur le sol
    ecrase = etats[("pose", "porte_contre_le_mur")]
    assert ecrase[0][6] == 1 and ecrase[-1][6] == FRAMES          # écrasé à chaque image où le mur arrête le transport
    assert ecrase[-1][2] == 0                                     # la vitesse propre (nulle) est rendue
    libre = etats[("pose", "porte_libre")][-1]
    assert libre[0] == 20 + FRAMES and libre[6] == 0              # porté d'un pixel par image, sans écrasement
