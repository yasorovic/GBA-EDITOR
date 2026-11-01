"""Les tuiles de collision à sens unique : le C réel de `resolve_actor_tiles`, compilé et exécuté.

Une face à sens unique n'arrête une boîte que si elle franchit la face CONTRE sa normale et qu'elle
était entièrement du côté ouvert à la frame précédente. Quatre normales (haut, bas, gauche, droite) :
la gravité a quatre sens, « le haut » n'est pas toujours l'axe Y négatif.
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
#include "gba_debug.h"
%(helpers)s

u8 *g_drop_through = 0;
/* 10 x 8 tuiles (80 x 64 px), vide hors des faces posées plus bas. */
static u8 carte[10 * 8];

static Actor mk(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    return a;
}
static void report(const char* nom, Actor* a){
    printf("%%s %%d %%d %%d %%d %%d\n", nom, a->x >> 8, a->y >> 8, a->vx, a->vy, a->collision.grounded);
}
static void frame(Actor* a){ a->x += a->vx; a->y += a->vy; resolve_actor_tiles(a, 1, 0); }

int main(void){
    /* haut : rangée 4 (face y = 32), colonnes 0 à 3 */
    for(int tx = 0; tx < 4; tx++) carte[4 * 10 + tx] = 22;
    /* bas : rangée 2 (face y = 24), colonnes 4 et 5 */
    carte[2 * 10 + 4] = 23; carte[2 * 10 + 5] = 23;
    /* gauche : colonne 6 (face x = 48), rangées 0 à 3 ; droite : colonne 8 (face x = 72) */
    for(int ty = 0; ty < 4; ty++){ carte[ty * 10 + 6] = 24; carte[ty * 10 + 8] = 25; }
    g_active_cmap = carte; g_cmap_w = 10; g_cmap_h = 8;
#ifdef AVEC_TABLES
    /* Les tables que le build émet : un bit (1 << sens) par rangée et par colonne qui porte une face. */
    static u8 rangees[8], colonnes[10];
    for(int ty = 0; ty < 8; ty++) for(int tx = 0; tx < 10; tx++){
        int sens = g_tile_oneway[carte[ty * 10 + tx]];
        if(sens){ rangees[ty] |= 1 << sens; colonnes[tx] |= 1 << sens; }
    }
    g_ow_rows = rangees; g_ow_cols = colonnes; g_ow_any = 0x1E;
#endif
    Actor a;

    a = mk(16, 16, 0, 1024);  frame(&a); report("haut_atterrit", &a);
    a = mk(16, 30, 0, -1024); frame(&a); report("haut_traverse_par_dessous", &a);
    a = mk(16, 17, 512, 64);  frame(&a); report("haut_marche_dessus", &a);
    a = mk(38, 10, 512, 0);   frame(&a); report("gauche_arrete", &a);
    a = mk(63, 10, -768, 0);  frame(&a); report("gauche_traverse_par_la_droite", &a);
    a = mk(79, 10, -512, 0);  frame(&a); report("droite_arrete", &a);
    a = mk(40, 19, 0, -2048); frame(&a); report("bas_arrete", &a);
    a = mk(40, 5, 0, 1024);   frame(&a); report("bas_traverse_par_dessus", &a);
    return 0;
}
"""


@pytest.fixture(scope="module", params=["lecture_de_la_carte", "tables_de_rangees"])
def resultats(tmp_path_factory, request):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines
    dossier = tmp_path_factory.mktemp("sens_unique")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(character_solver_lines(True))}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                *(["-DAVEC_TABLES"] if request.param == "tables_de_rangees" else []),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, y, vx, vy, au_sol).

def test_une_face_haut_porte_l_acteur_qui_tombe_dessus(resultats):
    assert resultats["haut_atterrit"] == (16, 17, 0, 0, 1)


def test_une_face_haut_se_traverse_par_en_dessous(resultats):
    assert resultats["haut_traverse_par_dessous"] == (16, 26, 0, -1024, 0)


def test_une_face_haut_porte_l_acteur_qui_marche_dessus(resultats):
    assert resultats["haut_marche_dessus"] == (18, 17, 512, 0, 1)


def test_une_face_gauche_arrete_l_acteur_venu_de_la_gauche(resultats):
    assert resultats["gauche_arrete"] == (38, 10, 0, 0, 0)


def test_une_face_gauche_se_traverse_par_la_droite(resultats):
    assert resultats["gauche_traverse_par_la_droite"] == (60, 10, -768, 0, 0)


def test_une_face_droite_arrete_l_acteur_venu_de_la_droite(resultats):
    assert resultats["droite_arrete"] == (79, 10, 0, 0, 0)


def test_une_face_bas_arrete_l_acteur_qui_monte_dessous(resultats):
    assert resultats["bas_arrete"] == (40, 13, 0, 0, 0)


def test_une_face_bas_se_traverse_par_dessus(resultats):
    assert resultats["bas_traverse_par_dessus"] == (40, 9, 0, 1024, 0)


def test_une_passe_n_est_emise_que_pour_un_sens_present_dans_les_cartes():
    from codegen.runtime_codegen.physics.character import character_solver_lines
    aucune = "\n".join(character_solver_lines())
    haut = "\n".join(character_solver_lines({1}))
    tout = "\n".join(character_solver_lines(True))
    assert "oneway_hit" not in aucune and "oneway_hit(1," in haut
    assert "oneway_hit(2," not in haut and "oneway_hit(3," not in haut and "oneway_hit(4," not in haut
    assert all(f"oneway_hit({n}," in tout for n in (1, 2, 3, 4))
