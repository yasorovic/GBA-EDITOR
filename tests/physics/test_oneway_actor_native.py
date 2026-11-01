"""Les faces à sens unique d'un acteur : le C réel de `actors_resolve_blocks_ow`, compilé et exécuté, puis le sens
cuit par le build selon la gravité de la scène.

Une face n'arrête un mobile que s'il était ENTIÈREMENT du côté de sa normale avant le déplacement de la frame
(le sien comme celui du porteur), et elle le repousse le long de la normale seule.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.models.components import CollisionShapeComponent
from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
Actor g_actors[8];
int g_spool_start = 0, g_spool_hw = 0;
u32 g_alive_bits[1];
u32 g_alive_epoch;
PoolCursor g_nth;
static u8 drop_store[8];
u8 *g_drop_through = drop_store;
%(helpers)s

static void mk(int i, int x, int y, int vx, int vy, int w, int h){
    Actor* a = &g_actors[i];
    *a = (Actor){0};
    a->active = 1; a->inst = i; a->x = x << 8; a->y = y << 8; a->vx = vx; a->vy = vy;
    a->collision.box_count = 1;
    CollisionShape* b = &a->collision.boxes[0];
    b->w = w; b->h = h; b->solid = 1; b->active = 1;
}
static void run(const char* nom, int dir){
    const u16 idx[] = {1}; const u8 box[] = {0}; const u8 ow[] = {dir};
    actors_resolve_blocks_ow(&g_actors[0], 1, idx, box, ow, 1);
    printf("%%s %%d %%d %%d %%d\n", nom, g_actors[0].x >> 8, g_actors[0].y >> 8, g_actors[0].vx, g_actors[0].vy);
}

int main(void){
    /* Face haut : une plateforme 16 x 4 en (50, 50). Le mobile 16 x 16 tombe de 8 px par frame (positions APRÈS le pas). */
    mk(1, 50, 50, 0, 0, 16, 4);
    mk(0, 50, 38, 0, 2048, 16, 16); run("haut_atterrit", 1);
    mk(0, 50, 40, 0, -2048, 16, 16); run("haut_traverse_par_dessous", 1);
    drop_store[0] = 3;
    mk(0, 50, 38, 0, 2048, 16, 16); run("haut_ignore_pendant_drop", 1);
    drop_store[0] = 0;
    /* Plateforme qui MONTE d'1 px par frame, mobile posé dessus (son bas à 50, vitesse nulle) : il est porté. */
    mk(1, 50, 49, 0, -256, 16, 4);
    mk(0, 50, 34, 0, 0, 16, 16); g_actors[0].vx = 1; run("haut_porte_par_plateforme_qui_monte", 1);
    /* Face bas : le mobile monte de dessous (haut 54 -> 46) contre la face du bas (bas à 54). */
    mk(1, 50, 50, 0, 0, 16, 4);
    mk(0, 50, 46, 0, -2048, 16, 16); run("bas_arrete", 2);
    mk(0, 50, 38, 0, 2048, 16, 16); run("bas_traverse_par_dessus", 2);
    /* Faces gauche et droite : une barre 4 x 16 en (50, 50). */
    mk(1, 50, 50, 0, 0, 4, 16);
    mk(0, 42, 50, 2048, 0, 16, 16); run("gauche_arrete", 3);
    mk(0, 46, 50, -2048, 0, 16, 16); run("gauche_traverse_par_la_droite", 3);
    mk(0, 46, 50, -2048, 0, 16, 16); run("droite_arrete", 4);
    mk(0, 42, 50, 2048, 0, 16, 16); run("droite_traverse_par_la_gauche", 4);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le blocage est vérifié en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines
    dossier = tmp_path_factory.mktemp("sens_unique_acteur")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(block_helper_lines(one_way=True))}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, y, vx, vy).

def test_une_face_haut_pose_le_mobile_qui_tombe_dessus(resultats):
    assert resultats["haut_atterrit"] == (50, 34, 0, 0)


def test_une_face_haut_se_traverse_par_en_dessous(resultats):
    assert resultats["haut_traverse_par_dessous"] == (50, 40, 0, -2048)


def test_drop_through_fait_ignorer_la_face(resultats):
    assert resultats["haut_ignore_pendant_drop"] == (50, 38, 0, 2048)


def test_une_plateforme_qui_monte_porte_le_mobile_pose_dessus(resultats):
    assert resultats["haut_porte_par_plateforme_qui_monte"][:2] == (50, 33)


def test_une_face_bas_arrete_par_en_dessous_et_se_traverse_par_dessus(resultats):
    assert resultats["bas_arrete"] == (50, 54, 0, 0)
    assert resultats["bas_traverse_par_dessus"] == (50, 38, 0, 2048)


def test_les_faces_gauche_et_droite_n_arretent_que_de_leur_cote(resultats):
    assert resultats["gauche_arrete"] == (34, 50, 0, 0)
    assert resultats["gauche_traverse_par_la_droite"] == (46, 50, -2048, 0)
    assert resultats["droite_arrete"] == (54, 50, 0, 0)
    assert resultats["droite_traverse_par_la_gauche"] == (42, 50, 2048, 0)


def _scene(gx, gy):
    return SimpleNamespace(effective_physics_gravity=lambda _settings: (gx, gy))


@pytest.mark.parametrize("gravite, mode, attendu", [
    ((0, 0.25), "off", 0),
    ((0, 0.25), "gravity", 1),      # gravité vers le bas : la face qui porte est celle du haut
    ((0, -0.25), "gravity", 2),     # gravité vers le haut : celle du bas
    ((0.25, 0), "gravity", 3),      # gravité vers la droite : celle de gauche
    ((-0.25, 0), "gravity", 4),
    ((0, 0), "gravity", 1),         # sans gravité : le haut
    ((0, 0.25), "left", 3),         # une normale fixée ignore la gravité
])
def test_le_sens_cuit_suit_la_gravite_de_la_scene(gravite, mode, attendu):
    from codegen.runtime_codegen.physics.body import shape_one_way_dir
    assert shape_one_way_dir(CollisionShapeComponent(one_way=mode), _scene(*gravite), None) == attendu


def test_un_mode_inconnu_est_refuse():
    with pytest.raises(ValueError):
        CollisionShapeComponent(one_way="diagonal")


def _acteur(nom, **boite):
    from core.models.scene import Actor
    a = Actor(name=nom)
    a.components = [CollisionShapeComponent(id="b", **boite)]
    return a


def _lignes(*acteurs, gravite=(0, 0.25)):
    from codegen.runtime_codegen.physics.blocks import block_tick_lines
    p = SimpleNamespace(settings=SimpleNamespace(collision_disabled_pairs=[], collision_tags=[]))
    return "\n".join(block_tick_lines(p, _scene(*gravite), [(a, None) for a in acteurs], 0, [], lambda _p, _o: (None, None)))


def test_le_build_cuit_le_sens_de_la_face_dans_la_table_du_mobile():
    hero = _acteur("Hero", tag="Player")
    plateforme = _acteur("Plateforme", tag="body", response="block", solid=False, one_way="gravity")
    lignes = _lignes(hero, plateforme)
    assert "static const u8 _bk_ow[]={1};" in lignes
    assert "actors_resolve_blocks_ow(&g_actors[0],1,_bk_idx,_bk_box,_bk_ow,1);" in lignes
    assert "static const u8 _bk_ow[]={2};" in _lignes(hero, plateforme, gravite=(0, -0.25))


def test_sans_face_a_sens_unique_le_build_emet_l_appel_historique():
    hero = _acteur("Hero", tag="Player")
    coffre = _acteur("Chest", tag="body", response="block", solid=False)
    lignes = _lignes(hero, coffre)
    assert "actors_resolve_blocks(&g_actors[0],1,_bk_idx,_bk_box,1);" in lignes
    assert "_ow" not in lignes


def test_la_carte_et_les_acteurs_partagent_une_seule_condition_de_traversee(tmp_path):
    """Les deux émetteurs écrivent `oneway_common_lines()` dans le même fichier : la garde de macro n'en laisse qu'une
    définition, sans quoi le fichier ne compile pas."""
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le blocage est vérifié en CI")
    from codegen.runtime_codegen.physics.blocks import block_helper_lines
    from codegen.runtime_codegen.physics.character import character_solver_lines
    probe = SONDE.split("%(helpers)s")[0] + "\n".join(character_solver_lines() + block_helper_lines(one_way=True))
    probe += "\nint main(void){ return oneway_open(1, 4, 4) && !oneway_open(1, 5, 4) && oneway_open(2, 5, 4) ? 0 : 1; }\n"
    (tmp_path / "probe.c").write_text(probe, encoding="utf-8")
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(tmp_path / "probe"), str(tmp_path / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    assert subprocess.run([str(tmp_path / "probe")], env=environnement(compilateur)).returncode == 0
