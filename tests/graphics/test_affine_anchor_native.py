"""L'ancrage d'un sprite affine, mesuré sur le VRAI C émis par `affine_oam_lines_dynamic`.

Le cadre du sprite est un corps rigide accroché à l'actor : son centre vaut
`position + R(rotation)·S(scale)·(offset + demi-cadre)`. Avec l'offset posé au
cochage de la case Affine (-W/2, -H/2), le centre reste donc SUR la position de
l'actor, quelle que soit la rotation ou l'échelle de l'actor.

Régression : le C faisait tourner `offset` seul puis ajoutait le demi-cadre à plat ;
le centre décrivait alors un cercle autour de la position dès que l'actor tournait
(jusqu'à 22,6 px pour un cadre 16×16 à 180°), et glissait de même avec l'échelle."""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

from core.models.components import SpriteComponent
from core.models.scene import Actor
from codegen.runtime_codegen.gen_affine import affine_entry, affine_oam_lines_dynamic

RUNTIME = Path(__file__).resolve().parents[2] / "runtime" / "include" / "runtime_api_inline.h"
FRAME = 16
POS = (100, 80)      # position de l'actor, en pixels
TOLERANCE = 1.5      # px : table de sinus en Q8 et divisions entières


class _Forme:
    frame_w = frame_h = FRAME
    oam_shape, oam_size = 2, 1
    tiles_per_frame = 4


def _sinus_du_moteur() -> str:
    """`SIN_LUT`, `gba_sin` et `gba_cos` tels que le moteur les écrit."""
    texte = RUNTIME.read_text(encoding="utf-8")
    debut = texte.index("static const s16 SIN_LUT")
    fin = texte.index("static inline int gba_cos")
    fin = texte.index("\n", fin)
    return texte[debut:fin]


def _source_sonde() -> str:
    entree = affine_entry(Actor(name="A"), _sc(), 0)
    lignes = "\n".join(affine_oam_lines_dynamic(0, entree, _Forme(), bt=0, priority_expr="0"))
    return f"""
#include <stdio.h>
#include <stdlib.h>
typedef short s16; typedef unsigned short u16;
{_sinus_du_moteur()}
typedef struct {{ int x, y, rotation, scale_x, scale_y; }} A;
typedef struct {{ int rotation, scale_x, scale_y, flip_h, flip_v, offset_x, offset_y,
                  pivot_x, pivot_y, frame, obj_mode, priority, pal_bank; }} O;
typedef struct {{ u16 attr0, attr1, attr2, dummy; }} S;
A g_actors[1]; O g_oam_entries[1]; S shadow_oam[128]; int cam_x = 0, cam_y = 0;
int main(int c, char** v) {{
    g_actors[0].x = atoi(v[1]) << 8;  g_actors[0].y = atoi(v[2]) << 8;
    g_actors[0].rotation = atoi(v[3]); g_actors[0].scale_x = g_actors[0].scale_y = atoi(v[4]);
    g_oam_entries[0].offset_x = atoi(v[5]); g_oam_entries[0].offset_y = atoi(v[6]);
    g_oam_entries[0].pivot_x = atoi(v[7]);  g_oam_entries[0].pivot_y = atoi(v[8]);
    g_oam_entries[0].rotation = atoi(v[9]);
    g_oam_entries[0].scale_x = g_oam_entries[0].scale_y = 256;
    {{
{lignes}
        printf("%d %d\\n", sx + {FRAME}, sy + {FRAME});   /* centre de la texture */
    }}
    return 0;
}}
"""


def _sc() -> SpriteComponent:
    s = SpriteComponent()
    s.affine_transform = True
    return s


@pytest.fixture(scope="module")
def sonde(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) ; la CI le joue")
    env = environnement(compilateur)
    dossier = tmp_path_factory.mktemp("affine_anchor")
    source = dossier / "sonde.c"
    source.write_text(_source_sonde(), encoding="utf-8")
    binaire = dossier / "sonde"
    r = subprocess.run([compilateur, "-std=c11", "-O0", "-Wall", "-o", str(binaire), str(source)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr

    def mesurer(rotation=0, echelle=256, offset=(-FRAME // 2, -FRAME // 2), pivot=(0, 0), sprite_rot=0):
        args = [str(a) for a in (*POS, rotation, echelle, *offset, *pivot, sprite_rot)]
        sortie = subprocess.run([str(binaire), *args], capture_output=True, text=True, env=env, check=True)
        x, y = map(int, re.findall(r"-?\d+", sortie.stdout))
        return x, y

    return mesurer


def _proche(mesure, attendu):
    assert math.dist(mesure, attendu) <= TOLERANCE, f"mesuré {mesure}, attendu {attendu}"


@pytest.mark.parametrize("rotation", [0, 30, 45, 90, 135, 180, 270])
def test_le_centre_reste_sur_la_position_quand_l_actor_tourne(sonde, rotation):
    _proche(sonde(rotation=rotation), POS)


@pytest.mark.parametrize("echelle", [128, 256, 512])
def test_le_centre_reste_sur_la_position_quand_l_actor_change_d_echelle(sonde, echelle):
    _proche(sonde(rotation=60, echelle=echelle), POS)


@pytest.mark.parametrize("rotation", [0, 90, 180])
def test_un_offset_quelconque_tourne_avec_le_cadre(sonde, rotation):
    """Offset (0,0) : le centre est à (W/2, H/2) de la position, dans le repère de l'actor."""
    r = math.radians(rotation)
    demi = FRAME / 2
    attendu = (POS[0] + math.cos(r) * demi - math.sin(r) * demi,
               POS[1] + math.sin(r) * demi + math.cos(r) * demi)
    _proche(sonde(rotation=rotation, offset=(0, 0)), attendu)


def test_le_pivot_reste_fixe_quand_le_sprite_tourne(sonde):
    """P = centre + M·pivot ne bouge pas quand seule la rotation LOCALE du sprite change."""
    pivot = (6, 0)

    def point_fixe(sprite_rot):
        cx, cy = sonde(rotation=40, pivot=pivot, sprite_rot=sprite_rot)
        a = math.radians(40 + sprite_rot)
        return (cx + math.cos(a) * pivot[0] - math.sin(a) * pivot[1],
                cy + math.sin(a) * pivot[0] + math.cos(a) * pivot[1])

    _proche(point_fixe(0), point_fixe(90))
    _proche(point_fixe(0), point_fixe(200))
