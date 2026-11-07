"""Le transport par une plateforme Kinematic, sur le C émis pour une vraie scène.

La plateforme (KinematicBody) et son passager (CharacterBody) naissent dans le pool partagé ; un posé prend le même
chemin (`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont celles de `kinematic_tick_parts`, compilées avec l'aide
C réelle (`kinematic_carry_all`) ; à chaque image la plateforme avance de sa vitesse, puis le passager est porté. La
sonde rapporte la position du passager et le déplacement porté (celui que la résolution contre la carte ajoute à sa
vitesse). L'écrasement est dans `test_crush_scene_native.py`.
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

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define EWRAM_BSS
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
u8 g_support_normal = 1;
#define G_ACTOR_COUNT @SLOTS@
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
@HELPERS@

static void naitre(int slot, int x, int y, int vx, int vy, int w, int h, int model){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1; a.slot_index = slot; a.type_id = model;
    g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void joue(const char* nom, int kvx, int kvy, int x, int y, int vy){
    for(int i = 0; i < @SLOTS@; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; }
    g_actor_slot_end = @START@; g_alive_bits[0] = 0;
    int k = @START@, a = @START@ + 1;
    naitre(k, 40, 50, kvx, kvy, 24, 8, @TYPE_K@);
    naitre(a, x, y, 0, vy, 8, 8, @TYPE_A@);
    for(int f = 0; f < @FRAMES@; f++){
@BEFORE@
        g_actors[k].x += g_actors[k].vx; g_actors[k].y += g_actors[k].vy;
@AFTER@
        printf("%s %d %d %d %d\n", nom, g_actors[a].x, g_actors[a].y, _kin_d[a][0], _kin_d[a][1]);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _emissions(tmp_path) -> dict:
    """(avant, après, types) que le générateur émet pour une vraie scène où `Plateforme` et `Passager` sont spawnés."""
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project
    from oam_fixtures import faire_naitre

    plateforme = Prefab(name="Plateforme")
    plateforme.actor.components += [CollisionShapeComponent(solid=False, response="block"),
                                    PhysicsBodyComponent(mode="KinematicBody")]
    passager = Prefab(name="Passager")
    passager.actor.components += [CollisionShapeComponent(solid=True), PhysicsBodyComponent(mode="CharacterBody")]
    scene = Scene(name="S", physics_enabled=True, actors=[])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = [plateforme, passager]
    faire_naitre(tmp_path, scene, "Plateforme", "Passager")
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    before, after, _crush = kinematic_tick_parts(project, [], scene, pi, resolve_initial_appearance)
    spool = models["Plateforme"]["spool"]
    return {"before": before, "after": after, "k": models["Plateforme"]["root_type_id"],
            "a": models["Passager"]["root_type_id"], "start": spool["start"], "slots": spool["end"]}


@pytest.fixture(scope="module")
def etats(tmp_path_factory):
    """Par scénario, image par image : (x, y du passager en Q8, déplacement porté x, y)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le transport est vérifié en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines

    e = _emissions(tmp_path_factory.mktemp("transport_scene_projet"))
    assert any("kinematic_carry_all" in ligne for ligne in e["after"]), (
        "aucun transport émis : la sonde ne vérifierait rien")
    assert e["slots"] >= e["start"] + 2
    runs = "\n".join(f'    joue("{n}", {kvx}, {kvy}, {x}, {y}, {vy});' for n, kvx, kvy, x, y, vy in SCENARIOS)
    source = (SONDE.replace("@HELPERS@", "\n".join(kinematic_helper_lines()))
              .replace("@BEFORE@", "\n".join(e["before"])).replace("@AFTER@", "\n".join(e["after"]))
              .replace("@TYPE_K@", str(e["k"])).replace("@TYPE_A@", str(e["a"]))
              .replace("@START@", str(e["start"])).replace("@SLOTS@", str(e["slots"]))
              .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
    dossier = tmp_path_factory.mktemp("transport_scene")
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


def test_une_plateforme_qui_glisse_porte_son_passager_a_chaque_image(etats):
    glisse = etats["glisse_a_droite"]
    assert all(e[2:] == (512, 0) for e in glisse)
    assert glisse[-1][:2] == ((48 << 8) + FRAMES * 512, 42 << 8)


def test_une_plateforme_qui_monte_porte_son_passager_a_chaque_image(etats):
    monte = etats["monte"]
    assert all(e[2:] == (0, -256) for e in monte)
    assert monte[-1][:2] == (48 << 8, (42 << 8) - FRAMES * 256)


@pytest.mark.parametrize("nom", ["passager_qui_saute", "passager_hors_plateforme", "plateforme_immobile"])
def test_rien_n_est_porte_sans_appui_ou_sans_mouvement(etats, nom):
    x = 200 if nom == "passager_hors_plateforme" else 48
    assert all(e == (x << 8, 42 << 8, 0, 0) for e in etats[nom])
