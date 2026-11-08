"""L'ancrage d'un sprite affine, mesuré sur le VRAI C émis par `affine_oam_lines` et sur la fonction du moteur qu'il
appelle (`oam_write_affine`).

Un acteur n'a ni rotation ni échelle : le centre du cadre vaut `position + offset + demi-cadre`, et le sprite tourne
et change d'échelle autour de son pivot. Avec l'offset posé au cochage de la case Affine (-W/2, -H/2), le centre reste
donc SUR la position de l'actor, quelle que soit la rotation ou l'échelle du sprite."""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

from core.models.components import SpriteComponent
from core.models.scene import Actor
from codegen.runtime_codegen.gen_affine import affine_oam_lines

RUNTIME = Path(__file__).resolve().parents[2] / "runtime" / "include" / "runtime_api_inline.h"
FRAME = 16
POS = (100, 80)      # position de l'actor, en pixels
TOLERANCE = 1.5      # px : table de sinus en Q8 et divisions entières


class _Forme:
    frame_w = frame_h = FRAME
    oam_shape, oam_size = 2, 1
    tiles_per_frame = 4


def _sinus_du_moteur() -> str:
    """`SIN_LUT`, la réduction d'angle, `gba_sin`/`gba_cos`/`gba_sincos` et la matrice, tels que le moteur les écrit."""
    texte = RUNTIME.read_text(encoding="utf-8")
    debut = texte.index("static const s16 SIN_LUT")
    fin = texte.index("/* fin de la trigonométrie du moteur */")
    return texte[debut:fin]


def _ecriture_affine_du_moteur() -> str:
    """`oam_write_affine` telle que le moteur l'écrit (le C émis l'appelle), à compiler contre les structures de la sonde."""
    texte = RUNTIME.read_text(encoding="utf-8")
    debut = texte.index("BS_ATTR_IWRAM\nstatic int __attribute__((unused)) oam_write_affine(")
    fin = texte.index("\n}\n", debut) + 3
    return texte[debut:fin]


# Les structures réduites des sondes, sous les noms du moteur, et ce que `oam_write_affine` lit autour d'elles.
STRUCTURES = """
typedef struct { int x, y; } A;
typedef struct { int rotation, scale_x, scale_y, flip_h, flip_v, offset_x, offset_y,
                 pivot_x, pivot_y, frame, obj_mode, priority, pal_bank, affine_slot; } O;
typedef struct { u16 attr0, attr1, attr2, dummy; } S;
typedef A Actor; typedef O OamEntry;
A g_actors[1]; O g_oam_entries[1]; S shadow_oam[128]; int cam_x = 0, cam_y = 0; AffCache g_aff_cache[1];
int g_oam_dropped = 0;
#define BS_ATTR_IWRAM
"""


def _source_sonde() -> str:
    lignes = "\n".join(affine_oam_lines(0, _Forme(), bt=0))
    return f"""
#include <stdio.h>
#include <stdlib.h>
typedef short s16; typedef unsigned short u16; typedef signed char s8; typedef unsigned char u8;
{_sinus_du_moteur()}
{STRUCTURES}
{_ecriture_affine_du_moteur()}
int main(int c, char** v) {{
    int _oamn = 0, _affn = 0;
    g_actors[0].x = atoi(v[1]) << 8;  g_actors[0].y = atoi(v[2]) << 8;
    g_oam_entries[0].rotation = atoi(v[3]); g_oam_entries[0].scale_x = g_oam_entries[0].scale_y = atoi(v[4]);
    g_oam_entries[0].offset_x = atoi(v[5]); g_oam_entries[0].offset_y = atoi(v[6]);
    g_oam_entries[0].pivot_x = atoi(v[7]);  g_oam_entries[0].pivot_y = atoi(v[8]);
    {{
{lignes}
        int sx = (int)((unsigned)shadow_oam[0].attr1 << 23) >> 23, sy = (signed char)shadow_oam[0].attr0;   /* coin de la boîte */
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

    def mesurer(rotation=0, echelle=256, offset=(-FRAME // 2, -FRAME // 2), pivot=(0, 0)):
        args = [str(a) for a in (*POS, rotation, echelle, *offset, *pivot)]
        sortie = subprocess.run([str(binaire), *args], capture_output=True, text=True, env=env, check=True)
        x, y = map(int, re.findall(r"-?\d+", sortie.stdout))
        return x, y

    return mesurer


def _proche(mesure, attendu):
    assert math.dist(mesure, attendu) <= TOLERANCE, f"mesuré {mesure}, attendu {attendu}"


@pytest.mark.parametrize("rotation", [0, 30, 45, 90, 135, 180, 270])
def test_le_centre_reste_sur_la_position_quand_le_sprite_tourne(sonde, rotation):
    _proche(sonde(rotation=rotation), POS)


@pytest.mark.parametrize("echelle", [128, 256, 512])
def test_le_centre_reste_sur_la_position_quand_le_sprite_change_d_echelle(sonde, echelle):
    _proche(sonde(rotation=60, echelle=echelle), POS)


@pytest.mark.parametrize("rotation", [0, 90, 180])
def test_l_offset_ne_tourne_pas_avec_le_sprite(sonde, rotation):
    """Offset (0,0) : le centre est à (W/2, H/2) de la position, quelle que soit la rotation du sprite (un acteur n'a
    pas de rotation qui ferait tourner le cadre)."""
    demi = FRAME / 2
    _proche(sonde(rotation=rotation, offset=(0, 0)), (POS[0] + demi, POS[1] + demi))


def test_le_pivot_reste_fixe_quand_le_sprite_tourne(sonde):
    """P = centre + M·pivot ne bouge pas quand la rotation du sprite change."""
    pivot = (6, 0)

    def point_fixe(sprite_rot):
        cx, cy = sonde(rotation=sprite_rot, pivot=pivot)
        a = math.radians(sprite_rot)
        return (cx + math.cos(a) * pivot[0] - math.sin(a) * pivot[1],
                cy + math.sin(a) * pivot[0] + math.cos(a) * pivot[1])

    _proche(point_fixe(0), point_fixe(90))
    _proche(point_fixe(0), point_fixe(200))
