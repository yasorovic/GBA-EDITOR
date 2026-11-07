"""Les contacts entre acteurs (`on_collision_enter`, `on_collide`, `on_collision_exit`) sur le C émis pour une vraie scène.

Les prefabs `Joueur` (tag `hero`, son script répond aux trois crochets) et `Piece` (tag `coin`, seulement à enter) naissent
tous deux dans le pool partagé : deux acteurs spawnés, le cas qui n'avait aucun chemin avant la passe par type. Un posé
prend le même chemin (`SLOT_EACH`, type lu à l'emplacement). Les lignes C sont le descripteur de modèle et la passe de
contacts que le générateur émet ; le test des boîtes est le vrai (`actors_overlap_mask`, repris de `runtime_api_inline.h`).

La pièce traverse le joueur de droite à gauche, 2 px par image : enter, collide tant qu'elles se recouvrent, exit. Chaque
crochet reçoit son propre acteur, l'autre, puis son tag et celui de l'autre.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement
from oam_fixtures import faire_naitre

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"
FRAMES = 16

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
#define EWRAM_BSS
Actor g_actors[@SLOTS@];
int g_spool_start = @START@, g_actor_slot_end = @START@, g_scene_placed = @START@;
u32 g_alive_bits[1], g_alive_epoch;
@OVERLAP@
static int frame;
static void note(const char* ev, Actor* s, Actor* o, u8 ts, u8 to){
    printf("%d %s %d %d %d %d\n", frame, ev, s->slot_index, o->slot_index, ts, to);
}
void @J@_on_collision_enter(Actor* s, Actor* o, u8 m, u8 t){ note("joueur_enter", s, o, m, t); }
void @J@_on_collide(Actor* s, Actor* o, u8 m, u8 t){ note("joueur_collide", s, o, m, t); }
void @J@_on_collision_exit(Actor* s, Actor* o, u8 m, u8 t){ note("joueur_exit", s, o, m, t); }
void @P@_on_collision_enter(Actor* s, Actor* o, u8 m, u8 t){ note("piece_enter", s, o, m, t); }
@HELPERS@
@TABLE@

static void naitre(int slot, int x, int vx, int model, int tag){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = 10 << 8; a.vx = vx;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, 8, 8, 1, 1, 0, 0};
    a.collision.boxes[0].tag = tag;
    a.active = 1; a.alive = 1; a.slot_index = slot; a.type_id = model;
    g_actors[slot] = a;
    if(slot + 1 > g_actor_slot_end) g_actor_slot_end = slot + 1;
    alive_bit_set(slot);
}
static void tick(void){
@LINES@
}

int main(void){
    int j = @START@, p = @START@ + 1;
    naitre(j, 10, 0, @TYPE_J@, @TAG_J@);       /* le joueur : x 10..18 */
    naitre(p, 30, -512, @TYPE_P@, @TAG_P@);    /* la pièce arrive de la droite, 2 px par image, et le traverse */
    for(frame = 0; frame < @FRAMES@; frame++){
        g_actors[p].x += g_actors[p].vx;
        tick();
    }
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
    from codegen.runtime_codegen.gen_pool import scene_pi
    from codegen.runtime_codegen.gen_sprite import resolve_initial_appearance
    from codegen.runtime_codegen.model_desc import model_desc_lines
    from codegen.runtime_codegen.physics.contacts import contact_tick_lines
    from core.models.components import CollisionShapeComponent
    from core.models.scene import Prefab, Scene
    from core.project import Project

    joueur = Prefab(name="Joueur")
    joueur.actor.components += [CollisionShapeComponent(w=8, h=8, tag="hero")]
    piece = Prefab(name="Piece")
    piece.actor.components += [CollisionShapeComponent(w=8, h=8, tag="coin")]
    scene = Scene(name="S", actors=[])
    project = Project(tmp_path)
    project.scenes.items = [scene]
    project.prefabs.items = [joueur, piece]
    faire_naitre(tmp_path, scene, "Joueur", "Piece")
    pi = scene_pi(project, scene)
    models = {m["prefab"].name: m for m in pi if m["shared"]}
    sj, sp = models["Joueur"]["sym"], models["Piece"]["sym"]
    events = {sj: {"on_collision_enter", "on_collide", "on_collision_exit"}, sp: {"on_collision_enter"}}
    has_event = lambda s, ev: ev in events.get(s, set())
    tags = list(project.collision_tags())
    spool = models["Joueur"]["spool"]
    return {"j": sj, "p": sp, "start": spool["start"], "slots": spool["end"],
            "table": model_desc_lines(project, scene, [], pi, [], has_event),
            "lines": contact_tick_lines(project, scene, [], pi, resolve_initial_appearance, [], has_event),
            "types": (models["Joueur"]["root_type_id"], models["Piece"]["root_type_id"]),
            "tags": (tags.index("hero"), tags.index("coin"))}


@pytest.fixture(scope="module")
def emissions(tmp_path_factory):
    return _emissions(tmp_path_factory.mktemp("contacts_scene_projet"))


@pytest.fixture(scope="module")
def evenements(tmp_path_factory, emissions):
    """Les crochets appelés, dans l'ordre : (image, crochet, emplacement propre, emplacement de l'autre, tag propre,
    tag de l'autre)."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; les contacts sont vérifiés en CI")
    from codegen.runtime_codegen.physics.contacts import contact_helper_lines

    e = emissions
    assert any("contacts_run" in ligne for ligne in e["lines"]), "aucun contact émis : la sonde ne vérifierait rien"
    assert e["slots"] >= e["start"] + 2
    (tj, tp), (gj, gp) = e["types"], e["tags"]
    source = (SONDE.replace("@OVERLAP@", _overlap_source()).replace("@HELPERS@", "\n".join(contact_helper_lines()))
              .replace("@TABLE@", "\n".join(e["table"])).replace("@LINES@", "\n".join(e["lines"]))
              .replace("@J@", e["j"]).replace("@P@", e["p"]).replace("@TYPE_J@", str(tj)).replace("@TYPE_P@", str(tp))
              .replace("@TAG_J@", str(gj)).replace("@TAG_P@", str(gp)).replace("@SLOTS@", str(e["slots"]))
              .replace("@START@", str(e["start"])).replace("@FRAMES@", str(FRAMES)))
    dossier = tmp_path_factory.mktemp("contacts_scene")
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert sortie.returncode == 0, sortie.stderr
    lignes = [ligne.split() for ligne in sortie.stdout.strip().splitlines()]
    return [(int(f), ev, *(int(v) for v in reste)) for f, ev, *reste in lignes]


def _de(evenements, crochet):
    return [e for e in evenements if e[1] == crochet]


def test_les_deux_tags_sont_distincts(emissions):
    """Sans cela, un tag inversé passerait inaperçu."""
    assert emissions["tags"][0] != emissions["tags"][1]


def test_enter_puis_collide_a_chaque_image_puis_exit(evenements):
    # La pièce (x = 28 - 2f) recouvre le joueur (10..18) des images 6 à 12 et le quitte à l'image 13.
    assert [e[0] for e in _de(evenements, "joueur_enter")] == [6]
    assert [e[0] for e in _de(evenements, "joueur_collide")] == list(range(7, 13))
    assert [e[0] for e in _de(evenements, "joueur_exit")] == [13]
    assert [e[0] for e in _de(evenements, "piece_enter")] == [6]


def test_chaque_crochet_recoit_son_acteur_puis_l_autre(emissions, evenements):
    j, p = emissions["start"], emissions["start"] + 1
    for e in evenements:
        attendu = (p, j) if e[1] == "piece_enter" else (j, p)
        assert e[2:4] == attendu, e


def test_chaque_crochet_recoit_son_tag_puis_celui_de_l_autre(emissions, evenements):
    hero, coin = emissions["tags"]
    for e in evenements:
        attendu = (coin, hero) if e[1] == "piece_enter" else (hero, coin)
        assert e[4:6] == attendu, e


def test_le_crochet_d_un_prefab_qui_ne_le_definit_pas_n_est_pas_appele(evenements):
    assert {e[1] for e in evenements} == {"joueur_enter", "joueur_collide", "joueur_exit", "piece_enter"}
