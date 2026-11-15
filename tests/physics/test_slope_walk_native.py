"""Marcher sur une pente : le C réel de `resolve_actor_tiles`, compilé et exécuté.

Régression visée (2026-11-15, vue en jouant un projet d'auteur) : la passe X se
résout à la hauteur de la frame précédente, et cette hauteur était DEVINÉE
(`(y - vy) >> 8`). Deux erreurs dans cette soustraction : la gravité est ajoutée à
`vy` après le déplacement, donc elle retire une vitesse qui n'a pas bougé l'acteur,
et la fraction sous-pixel laissée par une chute décide de l'arrondi. Le résultat
tombait un pixel plus haut ou plus bas selon l'historique. Un pixel plus haut, la
montée d'une pente à 45° passait ; un pixel plus bas, la tuile pleine sous la pente
devenait un mur et l'acteur restait collé là pour toujours. D'où le symptôme :
la première montée passe, la deuxième (après une descente, qui laisse une fraction)
bloque.

La hauteur est maintenant LUE (`collision.last_y`, comme `last_x`), et la passe X
laisse à un acteur au sol de quoi monter de ce qu'il avance (la limite des 45°) :
sur une rampe, la matière de la colonne suivante commence un pixel au-dessus des
pieds, et la passe X tourne AVANT que le sol ne porte l'acteur.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

W, H = 32, 12   # tuiles

SONDE = r"""
#include <stdio.h>
typedef unsigned char u8; typedef signed char s8;
typedef unsigned short u16; typedef short s16; typedef unsigned int u32;
#include "actor_types_static.h"
#include "gba_debug.h"
%(helpers)s

u8 *g_drop_through = 0;
u8 g_support_normal = 1;
static u8 carte[%(w)d * %(h)d];

/* Un personnage de plateforme ordinaire : boîte 16 x 24 sous un cadre 32 x 32,
   donc des pieds à y + 32. */
static Actor mk(int x, int y){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8;
    a.collision.last_x = x; a.collision.last_y = y;   /* ce que pose actor_init_slot */
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){8, 8, 16, 24, 1, 1, 0, 0};
    return a;
}
static void report(const char* nom, Actor* a){
    printf("%%s %%d %%d %%d\n", nom, a->x >> 8, (a->y >> 8) + 32, a->collision.grounded);
}
/* L'ordre d'une frame : le script pose la vitesse et applique, le moteur ajoute la
   gravité de la scène (0,25 px/f²), puis la carte résout. */
static void frame(Actor* a, int vx){
    a->vx = vx;
    a->x += a->vx; a->y += a->vy;
    a->vy += 64; if(a->vy > 2048) a->vy = 2048;
    resolve_actor_tiles(a, 1, 0);
}
static void marche(Actor* a, int vx, int frames){ for(int f = 0; f < frames; f++) frame(a, vx); }

int main(void){
    /* Sol plat (rangées 10 et 11), rampe à 45° (colonnes 16 à 19) vers un plateau,
       puis une descente à 26° (colonnes 24 à 27) vers un sol plus bas. */
    for(int tx = 0; tx < %(w)d; tx++){ carte[10 * %(w)d + tx] = 1; carte[11 * %(w)d + tx] = 1; }
    for(int k = 0; k < 4; k++){
        int ty = 9 - k, tx = 16 + k;
        carte[ty * %(w)d + tx] = 2;                                   /* la pente */
        for(int x = tx + 1; x < %(w)d; x++) carte[ty * %(w)d + x] = 1; /* plein sous le plateau */
    }
    for(int ty = 8; ty <= 9; ty++) for(int tx = 18; tx < %(w)d; tx++) carte[ty * %(w)d + tx] = 1;
    carte[6 * %(w)d + 24] = 7; carte[6 * %(w)d + 25] = 6;             /* descente 26°, 1re marche */
    for(int tx = 26; tx < %(w)d; tx++) carte[6 * %(w)d + tx] = 0;
    carte[7 * %(w)d + 26] = 7; carte[7 * %(w)d + 27] = 6;             /* 2e marche */
    for(int tx = 28; tx < %(w)d; tx++) carte[7 * %(w)d + tx] = 0;
    g_active_cmap = carte; g_cmap_w = %(w)d; g_cmap_h = %(h)d;

    Actor a = mk(40, 48);            /* sur le plat, pieds à 80 */
    report("depart", &a);
    marche(&a, 512, 70);  report("montee_1", &a);
    marche(&a, -512, 70); report("retour", &a);
    marche(&a, 512, 70);  report("montee_2", &a);
    marche(&a, 512, 40);  report("descente", &a);
    return 0;
}
"""


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines
    dossier = tmp_path_factory.mktemp("pentes")
    (dossier / "probe.c").write_text(
        SONDE % {"helpers": "\n".join(character_solver_lines()), "w": W, "h": H},
        encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    lignes = subprocess.run([str(binaire)], capture_output=True, text=True,
                            env=environnement(compilateur)).stdout.strip().splitlines()
    return {ligne.split()[0]: tuple(int(v) for v in ligne.split()[1:]) for ligne in lignes}


# Les valeurs sont (x, pieds, au_sol).

def test_la_premiere_montee_atteint_le_plateau(resultats):
    assert resultats["depart"] == (40, 80, 0)
    x, pieds, sol = resultats["montee_1"]
    assert (pieds, sol) == (48, 1)     # le plateau, et toujours au sol
    assert x > 160                     # la rampe est franchie, pas seulement abordée


def test_la_deuxieme_montee_passe_comme_la_premiere(resultats):
    """Le cas qui bloquait : une descente laisse une fraction sous-pixel, et la
    hauteur devinée tombait alors sur la tuile pleine sous la pente."""
    assert resultats["retour"][1] == 80               # redescendu sur le plat
    x, pieds, sol = resultats["montee_2"]
    assert (pieds, sol) == (48, 1)                    # le plateau, pas la pente
    # Collé à la rampe, il restait vers x = 130 et des pieds entre 56 et 79.
    assert x >= resultats["montee_1"][0] - 2


def test_la_descente_a_26_degres_garde_le_contact(resultats):
    x, pieds, sol = resultats["descente"]
    assert (pieds, sol) == (64, 1)     # le sol plus bas, sans décollement
    assert x > 224
