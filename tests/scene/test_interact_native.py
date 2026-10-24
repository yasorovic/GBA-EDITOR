"""Le C réel de la détection Interactive (`interact_helper_lines`), compilé et exécuté : le recouvrement
(hover), la visée dans le regard (facing), l'arrêt par les murs, et le plus proche qui l'emporte."""
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
Actor g_actors[8];
OamEntry g_oam_entries[8];
static int g_wall_x0 = 0, g_wall_x1 = -1;       /* un mur vertical : x dans [x0, x1], tout y */
static int tile_wall_at(int px, int py){ (void)py; return px >= g_wall_x0 && px <= g_wall_x1; }
%(helpers)s

/* Un acteur actif en (x, y), une seule boîte (bx, by, w, h) active. */
static void mk(int i, int x, int y, int bx, int by, int w, int h, int solid){
    Actor* a = &g_actors[i];
    *a = (Actor){0};
    a->active = 1; a->x = x << 8; a->y = y << 8; a->oam_entry = -1;
    a->collision.box_count = 1;
    CollisionBox* b = &a->collision.boxes[0];
    b->x = bx; b->y = by; b->w = w; b->h = h; b->solid = solid; b->active = 1;
}

int main(void){
    const u16 idx[] = {1, 2};
    const u8 box[] = {0, 0};
    const u8 hover[] = {0, 0}, aim[] = {1, 1};
    int r;
    /* 0 = le joueur (16x16 en 0,0), 1 = une zone 16x16 en x=10 (recouvre le joueur) */
    mk(0, 0, 0, 0, 0, 16, 16, 1); mk(1, 10, 0, 0, 0, 16, 16, 0); mk(2, 100, 100, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, hover, 2, 4);  printf("hover_recouvre %%d\n", r);
    mk(1, 30, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, hover, 2, 4);  printf("hover_loin %%d\n", r);

    /* facing : zone collée à droite (x=16..32), le joueur regarde à droite, portée 4 */
    mk(1, 16, 0, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = 1;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_colle %%d\n", r);
    mk(1, 19, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_a_portee %%d\n", r);
    mk(1, 20, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_trop_loin %%d\n", r);
    mk(1, 20, 0, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = -1;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_dos_tourne %%d\n", r);
    g_actors[0].facing_x = 0;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_nul %%d\n", r);

    /* facing vers le bas */
    mk(1, 0, 18, 0, 0, 16, 16, 0);
    g_actors[0].facing_x = 0; g_actors[0].facing_y = 1;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_bas %%d\n", r);

    /* un mur entre les deux */
    mk(1, 20, 0, 0, 0, 16, 16, 0); g_actors[0].facing_x = 1; g_actors[0].facing_y = 0;
    mk(1, 19, 0, 0, 0, 16, 16, 0);
    g_wall_x0 = 17; g_wall_x1 = 18;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("facing_mur %%d\n", r);
    mk(1, 10, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, hover, 2, 4);  printf("hover_ignore_le_mur %%d\n", r);
    g_wall_x0 = 0; g_wall_x1 = -1;

    /* le plus proche l'emporte */
    mk(1, 19, 0, 0, 0, 16, 16, 0); mk(2, 17, 0, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("plus_proche %%d\n", r);
    mk(2, 17, 0, 0, 0, 16, 16, 0); g_actors[2].active = 0;
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("inactif_ignore %%d\n", r);
    g_actors[2].active = 1;
    const u8 hors[] = {0, 3};
    r = interact_pick(&g_actors[0], idx, hors, aim, 2, 4);   printf("zone_absente %%d\n", r);

    /* sans boite de collision : la boite du joueur est le cadre du sprite (16x16 par defaut) */
    mk(0, 0, 0, 0, 0, 16, 16, 1); g_actors[0].collision.box_count = 0; g_actors[0].facing_x = 1;
    mk(1, 18, 0, 0, 0, 16, 16, 0); mk(2, 100, 100, 0, 0, 16, 16, 0);
    r = interact_pick(&g_actors[0], idx, box, aim, 2, 4);    printf("sans_boite %%d\n", r);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la détection est vérifiée en CI")
    from codegen.runtime_codegen.interact_gen import interact_helper_lines
    dossier = tmp_path_factory.mktemp("interact")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(interact_helper_lines())},
                                     encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    sortie = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.split()
    return {nom: int(valeur) for nom, valeur in zip(sortie[::2], sortie[1::2])}


def test_hover_recouvre_la_zone(resultats):
    assert resultats["hover_recouvre"] == 0          # le consommateur 0 (acteur 1)
    assert resultats["hover_loin"] == -1


def test_facing_atteint_la_zone_dans_le_regard_a_portee(resultats):
    assert resultats["facing_colle"] == 0            # collée : sans marge sur la zone
    assert resultats["facing_a_portee"] == 0         # 3 px d'écart : la bande de 4 px la touche
    assert resultats["facing_trop_loin"] == -1       # 4 px d'écart : les bords ne se recouvrent pas
    assert resultats["facing_bas"] == 0


def test_facing_n_atteint_rien_dans_le_dos_ou_sans_regard(resultats):
    assert resultats["facing_dos_tourne"] == -1
    assert resultats["facing_nul"] == -1


def test_un_mur_arrete_la_visee_mais_pas_le_recouvrement(resultats):
    assert resultats["facing_mur"] == -1
    assert resultats["hover_ignore_le_mur"] == 0


def test_le_plus_proche_l_emporte_et_l_inactif_est_ignore(resultats):
    assert resultats["plus_proche"] == 1             # l'acteur 2 (x=17) bat l'acteur 1 (x=19)
    assert resultats["inactif_ignore"] == 0
    assert resultats["zone_absente"] == 0            # le rang 3 n'existe pas : ce consommateur est écarté


def test_sans_boite_de_collision_la_visee_part_du_cadre(resultats):
    assert resultats["sans_boite"] == 0
