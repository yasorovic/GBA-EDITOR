"""Une chute rapide ne traverse pas le sol : la boîte de pieds (4 px) peut franchir la surface de plus que sa hauteur en une image.

Le sol est l'ancien défaut : la surface était écartée comme une saillie « sous laquelle on passe » dès qu'elle se retrouvait au
dessus du haut de la boîte, donc une boîte de 4 px qui tombait de plus de 4 px par image s'enfonçait dans un sol plein. Le
C réel de `resolve_actor_tiles` est compilé et exécuté ; chaque vitesse de chute et chaque décalage d'arrivée sont essayés.
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
u8 g_support_normal = 1;
/* 10 x 12 tuiles : sol plein sur les rangées 8 à 11 (surface y = 64), saillie pleine sur la rangée 3 pour les colonnes 6 à 9. */
static u8 carte[10 * 12];

static Actor mk(int x, int y, int vx, int vy){
    Actor a = (Actor){0};
    a.x = x << 8; a.y = y << 8; a.vx = vx; a.vy = vy; a.collision.last_x = x;
    a.collision.box_count = 1;
    a.collision.boxes[0] = (CollisionShape){-7, 11, 17, 4, 1, 1, 0, 0};
    return a;
}

int main(void){
    for(int ty = 8; ty < 12; ty++) for(int tx = 0; tx < 10; tx++) carte[ty * 10 + tx] = 1;
    for(int tx = 6; tx < 10; tx++) carte[3 * 10 + tx] = 1;
    g_active_cmap = carte; g_cmap_w = 10; g_cmap_h = 12;
    /* tombe à chaque vitesse de 1 à 15 px par image, avec chaque décalage d'arrivée sur 8 px */
    for(int v = 256; v <= 15 * 256; v += 128){
        for(int dy = 0; dy < 8; dy++){
            Actor a = mk(24, 64 - 15 - dy - (v >> 8) , 0, v);
            for(int f = 0; f < 8; f++){ a.x += a.vx; a.y += a.vy; resolve_actor_tiles(&a, 1, 0); }
            printf("chute %%d %%d %%d %%d\n", v, dy, a.y >> 8, a.collision.grounded);
        }
    }
    /* marcher sous la saillie (colonnes 6 à 9, surface basse y = 32) sans être soulevé : le haut de la boîte est à y+11 = 38 */
    Actor a = mk(48, 27, 512, 0);
    for(int f = 0; f < 30; f++){ a.x += a.vx; a.y += a.vy; resolve_actor_tiles(&a, 1, 0); }
    printf("sous_la_saillie %%d %%d\n", a.x >> 8, a.y >> 8);
    return 0;
}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision est vérifiée en CI")
    from codegen.runtime_codegen.physics.character import character_solver_lines
    dossier = tmp_path_factory.mktemp("chute_rapide")
    (dossier / "probe.c").write_text(SONDE % {"helpers": "\n".join(character_solver_lines())}, encoding="utf-8")
    binaire = dossier / "probe"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-I", str(INCLUDE),
                                "-o", str(binaire), str(dossier / "probe.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    return subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout.splitlines()


def test_la_boite_de_pieds_se_pose_sur_le_sol_a_toutes_les_vitesses_de_chute(sortie):
    chutes = [tuple(int(v) for v in ligne.split()[1:]) for ligne in sortie if ligne.startswith("chute")]
    assert len(chutes) > 100
    # Posée : les pieds (y + 11 .. y + 14) finissent juste au-dessus de la surface (y = 64), donc y = 64 - 15 = 49.
    mauvais = [c for c in chutes if c[2] != 49 or not c[3]]
    assert not mauvais, f"{len(mauvais)} chutes finissent hors du sol, par exemple (vitesse Q8, décalage, y, au sol) = {mauvais[:3]}"


def test_marcher_sous_une_saillie_ne_souleve_pas_l_acteur(sortie):
    """La borne de rejet recule jusqu'au haut de l'image précédente : une saillie au dessus d'un acteur qui ne tombe pas
    reste écartée (même haut avant et après)."""
    ligne = next(l for l in sortie if l.startswith("sous_la_saillie"))
    assert int(ligne.split()[2]) == 27, ligne      # x s'arrête au bord de la carte ; y n'a pas bougé
