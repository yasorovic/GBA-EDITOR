"""Parité posé / spawné des contacts (`on_collision_enter`, `on_collide`, `on_collision_exit`) : quatre topologies.

Une vraie scène où les prefabs `Joueur` (son script répond aux trois crochets) et `Piece` (seulement à enter) sont posés
ET spawnés. Les lignes C sont le descripteur de modèle et la passe de contacts que le générateur émet ; chaque
topologie ne choisit que ses emplacements vivants : posé/posé, posé/pool, pool/posé et pool/pool (ce dernier n'avait
aucun chemin avant la passe par type). La pièce traverse le joueur : enter, collide tant qu'elles se recouvrent, exit.
Le test des boîtes est le vrai (`actors_overlap_mask`, repris de `runtime_api_inline.h`).

Voir `test_parity_posed_spawned.py` pour la règle.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 16

# topologie -> (joueur posé ?, pièce posée ?)
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
#define EWRAM_BSS
Actor g_actors[4];
int g_spool_start = 2, g_actor_slot_end = 2, g_scene_placed = 0;
u32 g_alive_bits[1], g_alive_epoch;
@OVERLAP@
static int ev[4][3];
void @J@_on_collision_enter(Actor* s, Actor* o, u8 m, u8 t){ ev[s->slot_index][0]++; }
void @J@_on_collide(Actor* s, Actor* o, u8 m, u8 t){ ev[s->slot_index][1]++; }
void @J@_on_collision_exit(Actor* s, Actor* o, u8 m, u8 t){ ev[s->slot_index][2]++; }
void @P@_on_collision_enter(Actor* s, Actor* o, u8 m, u8 t){ ev[s->slot_index][0]++; }
@HELPERS@
@TABLE@

static Actor corps(int x, int vx){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = 10 << 8; a.vx = vx;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, 8, 8, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void place(int slot, Actor a, int model){
    a.slot_index = slot; a.type_id = model; g_actors[slot] = a;
    if(slot >= g_spool_start && slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void tick(void){
@LINES@
}
static void joue(const char* topo, int jp, int pp){
    for(int i = 0; i < 4; i++){ g_actors[i] = (Actor){0}; g_actors[i].slot_index = i; ev[i][0] = ev[i][1] = ev[i][2] = 0; }
    g_actor_slot_end = 2; g_alive_bits[0] = 0; g_scene_placed = 2;   /* 0 et 1 : les posés */
    int j = jp ? 0 : 2, p = pp ? 1 : 3;
    place(j, corps(10, 0), @TYPE_J@);          /* le joueur : x 10..18 */
    place(p, corps(30, -512), @TYPE_P@);       /* la pièce arrive de la droite, 2 px par image, et le traverse */
    for(int f = 0; f < @FRAMES@; f++){
        g_actors[p].x += g_actors[p].vx;
        tick();
        printf("%s %d %d %d %d %d\n", topo, f, ev[j][0], ev[j][1], ev[j][2], ev[p][0]);
    }
}

int main(void){
@RUNS@
    return 0;
}
"""


def _overlap_source() -> str:
    """Le texte de `box_overlap`, `_box_canonical` et `actors_overlap_mask`, tel que `runtime_api_inline.h` l'écrit."""
    lines = (INCLUDE / "runtime_api_inline.h").read_text(encoding="utf-8").splitlines()

    def block(name: str) -> list[str]:
        i = next(k for k, line in enumerate(lines) if line.startswith("static") and f" {name}(" in line)
        j = next(k for k in range(i, len(lines)) if lines[k] == "}")
        return lines[i:j + 1]

    return "\n".join(block("box_overlap") + block("_box_canonical") + ["BS_ATTR_IWRAM"] + block("actors_overlap_mask"))


def _emissions(tmp_path) -> dict:
    import copy
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.contacts import contact_tick_lines
    from core.models.components import CollisionShapeComponent
    from core.models.scene import Actor, Prefab, Scene
    from core.project import Project

    joueur = Prefab(name="Joueur")
    joueur.actor.components += [CollisionShapeComponent(w=8, h=8)]
    piece = Prefab(name="Piece")
    piece.actor.components += [CollisionShapeComponent(w=8, h=8)]
    scene = Scene(name="S", actors=[
        Actor(name=f"{pf.name}Pose", prefab_name=pf.name, components=copy.deepcopy(pf.actor.components))
        for pf in (joueur, piece)])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = [joueur, piece]
    faire_naitre(tmp_path, scene, "Joueur", "Piece")
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    sj, sp = models["Joueur"]["sym"], models["Piece"]["sym"]
    events = {sj: {"on_collision_enter", "on_collide", "on_collision_exit"}, sp: {"on_collision_enter"}}
    has_event = lambda s, ev: ev in events.get(s, set())
    actors = [(a, None) for a in scene.actors]
    return {"j": sj, "p": sp, "table": model_desc_lines(project, scene, actors, pi, [sj, sp], has_event),
            "lines": contact_tick_lines(project, scene, actors, pi, resolve_initial_appearance, [sj, sp], has_event),
            "types": (models["Joueur"]["root_type_id"], models["Piece"]["root_type_id"])}


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("parite_contacts_projet"))


@pytest.fixture(scope="module")
def etats(tmp_path_factory, emissions):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la parité est vérifiée en CI")
    from codegen.runtime_codegen.physics.contacts import contact_helper_lines

    e = emissions
    assert any("contacts_run" in ligne for ligne in e["lines"]), "aucun contact émis : la sonde ne comparerait rien"
    tj, tp = e["types"]
    runs = "\n".join(f'    joue("{nom}", {int(j)}, {int(p)});' for nom, (j, p) in TOPOLOGIES.items())
    source = (SONDE.replace("@OVERLAP@", _overlap_source()).replace("@HELPERS@", "\n".join(contact_helper_lines()))
              .replace("@TABLE@", "\n".join(e["table"])).replace("@LINES@", "\n".join(e["lines"]))
              .replace("@J@", e["j"]).replace("@P@", e["p"]).replace("@TYPE_J@", str(tj)).replace("@TYPE_P@", str(tp))
              .replace("@FRAMES@", str(FRAMES)).replace("@RUNS@", runs))
    dossier = tmp_path_factory.mktemp("parite_contacts")
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
        topo, _frame, *valeurs = ligne.split()
        etats.setdefault(topo, []).append(tuple(int(v) for v in valeurs))
    return etats


def test_les_copies_posees_prennent_le_type_du_modele_ne(emissions):
    assert len(set(emissions["types"])) == 2


@pytest.mark.parametrize("topologie", [t for t in TOPOLOGIES if t != "pose_pose"])
def test_les_contacts_donnent_les_memes_evenements_pose_et_spawne(etats, topologie):
    """(enter, collide, exit du joueur ; enter de la pièce), image par image, identiques au cas posé/posé."""
    assert len(etats["pose_pose"]) == FRAMES
    assert etats[topologie] == etats["pose_pose"]


def test_la_reference_vit_vraiment_un_contact(etats):
    """Sans cela, des compteurs égaux mais nuls passeraient pour une parité."""
    fin = etats["pose_pose"][-1]
    assert fin[0] == 1 and fin[3] == 1           # un seul enter, de chaque côté
    assert fin[1] > 1                            # collide à chaque image de recouvrement
    assert fin[2] == 1                           # puis un exit, une fois la pièce passée
