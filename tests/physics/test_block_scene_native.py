"""Le blocage entre acteurs sur le C émis pour une vraie scène.

Le mobile (CharacterBody) et le bloqueur (StaticBody, réponse `block`) naissent tous deux dans le pool partagé ; un posé
prend le même chemin (`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont celles de `block_tick_lines`, compilées avec
les aides C réelles ; le mobile fait un pas puis le blocage le repousse. Les cas à la main (tables écrites par le test,
masse, impulsions, transport) sont dans `tests/scene/test_block_native.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

# nom -> ((x, y, vx, vy) du mobile avant son pas, en pixels et Q8 ; (x, y, vx, vy) attendus après le blocage).
# Le bloqueur occupe (40,40)-(56,56) ; le mobile est une boîte de 8 x 8.
SCENARIOS = {
    "mur_par_la_gauche": ((30, 44, 2048, 0), (32, 44, 0, 0)),          # repoussé de 6 px, vitesse annulée
    "sol_par_le_haut": ((44, 30, 0, 2560), (44, 32, 0, 0)),            # posé sur le dessus, axe vertical
    "diagonale": ((33, 33, 1536, 1536), (32, 39, 0, 1536)),            # égalité : l'horizontale, il glisse
    "sans_contact": ((0, 0, 256, 256), (1, 1, 256, 256)),
    "immobile_dans_le_bloqueur": ((44, 44, 0, 0), (44, 44, 0, 0)),     # sans vitesse, rien ne le pousse
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
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static void naitre(int slot, Actor a, int model){
    a.slot_index = slot; a.type_id = model; a.active = 1; a.alive = 1; g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void joue(const char* nom, int x, int y, int vx, int vy){
    for(int i = 0; i < @SLOTS@; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
    g_actor_slot_end = @START@; g_alive_bits[0] = 0;
    int m = @START@, b = @START@ + 1;
    Actor mobile = (Actor){0};
    mobile.x = x << 8; mobile.y = y << 8; mobile.vx = vx; mobile.vy = vy;
    mobile.collision.box_count = 1;
    mobile.collision.boxes[0] = (CollisionShape){0, 0, 8, 8, 1, 1, 0, 0};
    naitre(m, mobile, @TYPE_M@);
    Actor bloqueur = (Actor){0};
    bloqueur.x = 40 << 8; bloqueur.y = 40 << 8;
    bloqueur.collision.box_count = 1;
    bloqueur.collision.boxes[0] = (CollisionShape){0, 0, 16, 16, 0, 1, 0, 0};
    naitre(b, bloqueur, @TYPE_B@);
    g_actors[m].x += g_actors[m].vx; g_actors[m].y += g_actors[m].vy;
@LINES@
    const Actor* a = &g_actors[m];
    printf("%s %d %d %d %d\n", nom, a->x >> 8, a->y >> 8, a->vx, a->vy);
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path) -> dict:
    """Les lignes que le générateur émet pour une vraie scène où les prefabs `Mobile` et `Bloqueur` sont spawnés."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    mobile = Prefab(name="Mobile")
    mobile.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    bloqueur = Prefab(name="Bloqueur")
    bloqueur.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                  PhysicsBodyComponent(mode="StaticBody")]
    scene = Scene(name="S", physics_enabled=True, actors=[])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    p.prefabs.items = [mobile, bloqueur]
    faire_naitre(tmp_path, scene, "Mobile", "Bloqueur")
    pi = scene_pi(p, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    spool = models["Mobile"]["spool"]
    return {"lines": block_tick_lines(p, scene, [], pi, resolve_initial_appearance),
            "start": spool["start"], "slots": spool["end"],
            "mobile": models["Mobile"]["root_type_id"], "bloqueur": models["Bloqueur"]["root_type_id"]}


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le blocage est vérifié en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines

    e = _emissions(tmp_path_factory.mktemp("blocage_scene_projet"))
    assert any("actors_resolve_blocks" in ligne for ligne in e["lines"]), (
        "aucun blocage émis : la sonde ne vérifierait rien")
    assert e["slots"] >= e["start"] + 2
    runs = "\n".join(f'    joue("{nom}", {x}, {y}, {vx}, {vy});' for nom, ((x, y, vx, vy), _) in SCENARIOS.items())
    source = (SONDE.replace("@HELPERS@", "\n".join(block_helper_lines())).replace("@LINES@", "\n".join(e["lines"]))
              .replace("@TYPE_M@", str(e["mobile"])).replace("@TYPE_B@", str(e["bloqueur"]))
              .replace("@SLOTS@", str(e["slots"])).replace("@START@", str(e["start"])).replace("@RUNS@", runs))
    dossier = tmp_path_factory.mktemp("blocage_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    etats: dict[str, tuple[int, ...]] = {}
    for ligne in sortie.stdout.strip().splitlines():
        nom, *valeurs = ligne.split()
        etats[nom] = tuple(int(v) for v in valeurs)
    return etats


@pytest.mark.parametrize("nom", list(SCENARIOS))
def test_le_blocage_donne_la_position_et_la_vitesse_attendues(etats, nom):
    """(x, y, vx, vy) du mobile après le blocage."""
    assert etats[nom] == SCENARIOS[nom][1]
