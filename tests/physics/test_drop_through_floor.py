"""Un corps qui descend à travers les faces à sens unique (`drop_through`) n'y repose plus : `floor` et `grounded` la lâchent.

Le contact au sol d'un acteur sur un acteur est relu à chaque image, contact exact (pieds sur la face). Sans cette garde, un
joueur qui appelle `drop_through` sur une plateforme d'acteur à sens unique y restait désigné comme posé (`grounded` vrai), donc
le script n'appliquait pas la gravité et il ne tombait jamais. Une face pleine (sans sens unique) le porte toujours.

Les lignes C sont celles de `floor_tick_lines`, compilées avec les aides C réelles.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#define BS_ATTR_IWRAM __attribute__((noinline))   /* hors GBA : fonction ordinaire (cf. runtime_api_inline.h) */
u8 g_support_normal = 1;
Actor g_actors[2];
u16 floor_store[2];
u16 *g_actor_floor = floor_store;
u8 drop_store[2];
u8 *g_drop_through = drop_store;
int g_spool_start, g_spool_hw, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
%(helpers)s

static Actor boite(int x, int y, int w, int h){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){0, 0, w, h, 1, 1, 0, 0};
    a.active = 1; a.alive = 1;
    return a;
}
static void essai(const char* nom, int drop){
    g_actors[0] = boite(48, 42, 8, 8); g_actors[0].inst = 0; g_actors[0].model = %(type_corps)s;   /* le corps : bas = 50 */
    g_actors[1] = boite(40, 50, 24, 8); g_actors[1].inst = 1; g_actors[1].model = %(type_appui)s;  /* l'appui : haut = 50 */
    floor_store[0] = floor_store[1] = 0; drop_store[0] = drop; drop_store[1] = 0;
    g_scene_placed = 2; g_spool_hw = 2; g_alive_bits[0] = 0; alive_bit_set(0); alive_bit_set(1);   /* deux posés */
%(lines)s
    printf("%%s %%d\n", nom, floor_store[0] == 2);
}
int main(void){ essai("sans_drop", 0); essai("avec_drop", 10); return 0; }
"""


def _resultats(tmp_path, one_way: str) -> dict[str, int]:
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le contact au sol est vérifié en CI")
    from codegen.runtime_codegen.gen_sprite import shown
    from codegen.runtime_codegen.physics.floor import floor_helper_lines, floor_tick_lines
    from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
    from codegen.oam_alloc import scene_oam_layout
    from core.models.scene import Actor, Scene
    from core.project import Project

    corps = Actor(name="Corps", components=[CollisionShapeComponent(solid=True),
                                            PhysicsBodyComponent(mode="CharacterBody")])
    appui = Actor(name="Appui", components=[CollisionShapeComponent(solid=False, response="block", one_way=one_way),
                                            PhysicsBodyComponent(mode="StaticBody")])
    scene = Scene(name="S", actors=[corps, appui], physics_enabled=True)
    project = Project(tmp_path / f"Drop_{one_way}")
    project.scenes.items = [scene]
    lignes = floor_tick_lines(project, [(corps, None), (appui, None)], scene, [], shown)
    assert any("actors_floor" in ligne for ligne in lignes)
    type_corps, type_appui = scene_oam_layout(project, scene).placed_model
    source = SONDE % {"helpers": "\n".join(floor_helper_lines()), "lines": "\n".join(lignes),
                      "type_corps": type_corps, "type_appui": type_appui}
    dossier = tmp_path / one_way
    dossier.mkdir()
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout
    return {ligne.split()[0]: int(ligne.split()[1]) for ligne in sortie.splitlines()}


def test_une_face_a_sens_unique_porte_sauf_pour_un_corps_qui_descend_a_travers(tmp_path):
    assert _resultats(tmp_path, "gravity") == {"sans_drop": 1, "avec_drop": 0}


def test_une_face_pleine_porte_toujours_meme_pendant_un_drop_through(tmp_path):
    assert _resultats(tmp_path, "off") == {"sans_drop": 1, "avec_drop": 1}
