"""La résolution d'un acteur contre la carte de collision : le C réel de `resolve_actor_tiles`, compilé et exécuté.

Régression visée : `apply_velocity` déplace x ET y d'un coup, puis la résolution traitait l'axe X à la
nouvelle hauteur. Un acteur qui atterrit vite a déjà les pieds dans le sol à ce moment-là : le sol passait
pour un MUR et repoussait l'acteur de côté, parfois dans une paroi (vu en jouant la démo Platformer).
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
%(helpers)s

/* 8 x 6 tuiles : un sol plein sur la dernière rangée (y = 40), un mur plein sur la colonne 6 (x = 48). */
static u8 carte[8 * 6];

/* Le joueur de la démo : une boîte « pieds » solide de 17 x 4 en (-7, 11). */
static Actor mk(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy;
    a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionBox){-7, 11, 17, 4, 1, 1, 0, 0};
    return a;
}
static void report(const char* nom, Actor* a){
    printf("%%s %%d %%d %%d %%d %%d\n", nom, a->x >> 8, a->y >> 8, a->vx, a->vy, a->collision.grounded);
}
/* Ce que fait `actor:apply_velocity()` puis le tick. */
static void frame(Actor* a){ a->x += a->vx; a->y += a->vy; resolve_actor_tiles(a, 0); }

int main(void){
    for(int tx = 0; tx < 8; tx++) carte[5 * 8 + tx] = 1;
    for(int ty = 0; ty < 6; ty++) carte[ty * 8 + 6] = 1;
    g_active_cmap = carte; g_cmap_w = 8; g_cmap_h = 6;
    Actor a;

    /* Atterrissage vite (4 px/frame) en avançant de 2 px : les pieds finissent 1 px dans le sol. */
    a = mk(33, 22, 512, 1024); frame(&a); report("atterrit_a_droite", &a);
    a = mk(33, 22, -512, 1024); frame(&a); report("atterrit_a_gauche", &a);
    /* Atterrissage lent (1 px/frame) : les pieds arrivent pile sur le sol, sans enfoncement. */
    a = mk(33, 24, 512, 300); frame(&a); report("atterrit_lentement", &a);
    /* Le mur arrête toujours : à pied, puis en chutant. */
    a = mk(37, 25, 512, 0); frame(&a); report("mur_a_pied", &a);
    a = mk(37, 22, 512, 1024); frame(&a); report("mur_en_chutant", &a);
    /* Au sol, immobile : laissé tel quel. */
    a = mk(33, 25, 0, 0); frame(&a); report("immobile", &a);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.gen_tile_collision import gen_tile_helpers
    dossier = tmp_path_factory.mktemp("tuiles")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(gen_tile_helpers())}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, y, vx, vy, au_sol).

def test_un_atterrissage_rapide_ne_repousse_pas_l_acteur_de_cote(resultats):
    """Le sol, où les pieds sont déjà enfoncés, n'est pas un mur : x avance de 2 px, comme prévu."""
    assert resultats["atterrit_a_droite"] == (35, 25, 512, 0, 1)
    assert resultats["atterrit_a_gauche"] == (31, 25, -512, 0, 1)


def test_un_atterrissage_lent_pose_l_acteur_sans_le_deplacer_de_cote(resultats):
    assert resultats["atterrit_lentement"] == (35, 25, 512, 0, 1)


def test_un_mur_arrete_toujours_l_acteur_a_pied_comme_en_chutant(resultats):
    assert resultats["mur_a_pied"] == (38, 25, 0, 0, 1)         # le bord droit des pieds touche x = 48
    assert resultats["mur_en_chutant"][0] == 38 and resultats["mur_en_chutant"][2] == 0


def test_un_acteur_immobile_est_laisse_tel_quel(resultats):
    assert resultats["immobile"][:2] == (33, 25)
