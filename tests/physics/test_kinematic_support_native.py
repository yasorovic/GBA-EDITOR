"""Le transport d'une plateforme Kinematic suit le côté d'appui de la scène : le passager repose sur la face qui regarde la
gravité (dessus, dessous, ou un côté) et suit le déplacement réel de la plateforme, une seule fois."""
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
Actor g_actors[4];
u8 g_support_normal = 1;
int g_spool_start, g_actor_slot_end, g_scene_placed;
u32 g_alive_bits[1], g_alive_epoch;
%(helpers)s

static void mk(int i, int x, int y, int vx, int vy, int w, int h){
    Actor* a = &g_actors[i];
    *a = (Actor){0};
    a->active = 1; a->x = x << 8; a->y = y << 8; a->vx = vx; a->vy = vy;
    a->collision.box_count = 1;
    CollisionShape* b = &a->collision.boxes[0];
    b->w = w; b->h = h; b->solid = 1; b->active = 1;
}
/* La plateforme (acteur 0) était en (50, 50) et est maintenant en (px, py) ; le passager (acteur 1) est en (rx, ry). */
static void essai(const char* nom, int normale, int px, int py, int pw, int ph, int rx, int ry, int rvx, int rvy){
    int cx = 0, cy = 0; u8 carried = 0;
    mk(0, px, py, 0, 0, pw, ph);
    mk(1, rx, ry, rvx, rvy, 16, 16);
    kinematic_carry_n(&g_actors[0], &g_actors[1], 0, 0, 50 << 8, 50 << 8, &carried, &cx, &cy, normale);
    printf("%%s %%d %%d %%d\n", nom, g_actors[1].x >> 8, g_actors[1].y >> 8, carried);
}

int main(void){
    /* bas (1) : plateforme 16 x 4 qui glisse de 2 px vers la droite, passager posé dessus (bas = 50) */
    essai("bas_porte", 1, 52, 50, 16, 4, 50, 34, 0, 0);
    essai("bas_saute", 1, 52, 50, 16, 4, 50, 34, 0, -256);
    /* haut (2) : passager sous la plateforme (haut = 54 = bas de la plateforme) */
    essai("haut_porte", 2, 52, 50, 16, 4, 50, 54, 0, 0);
    essai("haut_s_eloigne", 2, 52, 50, 16, 4, 50, 54, 0, 256);
    /* droite (3) : barre 4 x 16 qui descend de 2 px, passager à sa gauche (bord droit = 50) */
    essai("droite_porte", 3, 50, 52, 4, 16, 34, 50, 0, 0);
    essai("droite_s_eloigne", 3, 50, 52, 4, 16, 34, 50, -256, 0);
    /* gauche (4) : passager à droite de la barre (bord gauche = 54) */
    essai("gauche_porte", 4, 50, 52, 4, 16, 54, 50, 0, 0);
    /* un passager posé sur le MAUVAIS côté n'est pas transporté */
    essai("bas_mauvais_cote", 1, 52, 50, 16, 4, 50, 54, 0, 0);
    essai("droite_mauvais_cote", 3, 50, 52, 4, 16, 54, 50, 0, 0);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le transport est vérifié en CI")
    from codegen.runtime_codegen.physics.kinematic import kinematic_helper_lines
    dossier = tmp_path_factory.mktemp("transport")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(kinematic_helper_lines())}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, y, transporté).

def test_le_passager_suit_la_face_qui_regarde_la_gravite(resultats):
    assert resultats["bas_porte"] == (52, 34, 1)
    assert resultats["haut_porte"] == (52, 54, 1)
    assert resultats["droite_porte"] == (34, 52, 1)
    assert resultats["gauche_porte"] == (54, 52, 1)


def test_un_passager_qui_s_eloigne_de_son_appui_n_est_pas_transporte(resultats):
    assert resultats["bas_saute"][2] == 0
    assert resultats["haut_s_eloigne"][2] == 0
    assert resultats["droite_s_eloigne"][2] == 0


def test_un_passager_du_mauvais_cote_n_est_pas_transporte(resultats):
    assert resultats["bas_mauvais_cote"] == (50, 54, 0)
    assert resultats["droite_mauvais_cote"] == (54, 50, 0)


@pytest.mark.parametrize("gravite, normale", [((0, 0.25), 1), ((0, -0.25), 2), ((0.25, 0), 3), ((-0.25, 0), 4)])
def test_le_build_emet_le_transport_du_cote_d_appui_de_la_scene(tmp_path, gravite, normale):
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.models.components import (CollisionShapeComponent, PhysicsBodyComponent, PHYSICS_BODY_CHARACTER,
                                        PHYSICS_BODY_KINEMATIC)
    from core.models.scene import Actor, Scene
    from core.project import Project
    plateforme, joueur = Actor(name="Plateforme"), Actor(name="Joueur")
    plateforme.components = [CollisionShapeComponent(id="b", response="block", solid=False),
                             PhysicsBodyComponent(mode=PHYSICS_BODY_KINEMATIC)]
    joueur.components = [CollisionShapeComponent(id="b", response="sensor", solid=True),
                         PhysicsBodyComponent(mode=PHYSICS_BODY_CHARACTER)]
    scene = Scene(name="S", actors=[plateforme, joueur], physics_enabled=True, physics_gravity_override=True,
                  physics_gravity_x=gravite[0], physics_gravity_y=gravite[1])
    p = Project(tmp_path)
    p.scenes.items = [scene]
    _before, after, _crush = kinematic_tick_parts(p, [(plateforme, None), (joueur, None)], scene)
    # Le côté d'appui de la scène est cuit dans l'appel, le dernier argument.
    appel = "\n".join(after)
    assert f"kinematic_carry_all(_kin_list,_kin_n,&_kin_run[0][0],1,_kin_riders,_kin_nr,_kin_pair,_kin_d,{normale});" in appel
