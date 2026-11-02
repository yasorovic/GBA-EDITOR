"""`grounded` suit la gravité : le contact qui le produit est celui du côté d'appui de la scène, pas forcément le bas.

Le C réel de `resolve_actor_tiles` est compilé et exécuté avec chaque côté d'appui (1 bas, 2 haut, 3 droite,
4 gauche). Le bas reste le comportement d'avant : une scène sans gravité l'utilise aussi.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
u8 *g_drop_through = 0;
u8 g_support_normal = 1;
%(helpers)s

/* 8 x 6 tuiles : sol plein sur la rangée 5 (y = 40), mur plein sur la colonne 6 (x = 48), plafond plein sur la
   rangée 1 pour les colonnes 0 à 3 (y = 8 à 15). */
static u8 carte[8 * 6];

static Actor mk(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    return a;
}
static void frame(Actor* a){ a->x += a->vx; a->y += a->vy; resolve_actor_tiles(a, 1, 0); }
static void essai(const char* nom, int normale, int x, int y, int vx, int vy){
    g_support_normal = normale;
    Actor a = mk(x, y, vx, vy); frame(&a);
    printf("%%s %%d %%d %%d\n", nom, a.x >> 8, a.y >> 8, a.collision.grounded);
}

int main(void){
    for(int tx = 0; tx < 8; tx++) carte[5 * 8 + tx] = 1;
    for(int ty = 0; ty < 6; ty++) carte[ty * 8 + 6] = 1;
    for(int tx = 0; tx < 4; tx++) carte[1 * 8 + tx] = 1;
    g_active_cmap = carte; g_cmap_w = 8; g_cmap_h = 6;
    /* Atterrir sur le sol : le bas porte seulement si la gravité tire vers le bas. */
    essai("sol_normale_bas", 1, 33, 22, 0, 1024);
    essai("sol_normale_haut", 2, 33, 22, 0, 1024);
    essai("sol_normale_droite", 3, 33, 22, 0, 1024);
    /* Se cogner le crâne au plafond (haut de la boîte à y + 11 = 16 : la boîte est posée dessous). */
    essai("plafond_normale_haut", 2, 16, 5, 0, -256);
    essai("plafond_normale_bas", 1, 16, 5, 0, -256);
    /* Pousser contre un mur : celui de la colonne 6 par la gauche, puis le bloc des colonnes 0 à 3 par la droite. */
    essai("mur_droit_normale_droite", 3, 37, 10, 512, 0);
    essai("mur_droit_normale_bas", 1, 37, 10, 512, 0);
    essai("mur_gauche_normale_gauche", 4, 40, 0, -768, 0);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines
    dossier = tmp_path_factory.mktemp("appui")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(character_solver_lines())}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, y, au_sol).

def test_le_sol_ne_porte_que_sous_une_gravite_vers_le_bas(resultats):
    assert resultats["sol_normale_bas"][2] == 1
    assert resultats["sol_normale_haut"][2] == 0
    assert resultats["sol_normale_droite"][2] == 0
    # Le sol arrête le corps dans tous les cas : seul le drapeau change.
    assert resultats["sol_normale_bas"][1] == resultats["sol_normale_haut"][1] == 25


def test_le_plafond_porte_sous_une_gravite_vers_le_haut(resultats):
    assert resultats["plafond_normale_haut"][2] == 1
    assert resultats["plafond_normale_bas"][2] == 0


def test_le_mur_porte_sous_une_gravite_laterale(resultats):
    assert resultats["mur_droit_normale_droite"] == (38, 10, 1)
    assert resultats["mur_droit_normale_bas"][2] == 0
    assert resultats["mur_gauche_normale_gauche"][2] == 1


@pytest.mark.parametrize("gravite, attendu", [
    ((0, 0.25), 1), ((0, -0.25), 2), ((0.25, 0), 3), ((-0.25, 0), 4),
    ((0, 0), 1),    # sans gravité déclarée : le bas, comme avant (un Character écrit sa propre gravité)
])
def test_le_cote_d_appui_vient_de_la_gravite_de_la_scene(gravite, attendu):
    from codegen.runtime_codegen.physics.body import support_normal
    scene = SimpleNamespace(effective_physics_gravity=lambda _settings: gravite)
    assert support_normal(scene, None) == attendu
