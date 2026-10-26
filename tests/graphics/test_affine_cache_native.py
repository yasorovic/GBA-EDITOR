"""Le cache du calcul affine, en C réel : le C émis, joué deux images de suite, rend EXACTEMENT la même chose avec le
cache (relecture) que sans (calcul complet) ; et dès qu'une des entrées de la clé change, il recalcule.

Le cache est une optimisation : la seule propriété qu'il doit garder est qu'il ne rende jamais un résultat périmé."""
from __future__ import annotations

import subprocess

import pytest

from codegen.runtime_codegen.gen_affine import affine_entry, affine_oam_lines_dynamic
from core.models.components import SpriteComponent
from core.models.scene import Actor
from native_toolchain import compilateur_hote, environnement
from test_affine_anchor_native import _Forme, _sinus_du_moteur


def _source() -> str:
    sc = SpriteComponent()
    sc.affine_transform = True
    entree = affine_entry(Actor(name="A"), sc, 0)
    lignes = "\n".join(affine_oam_lines_dynamic(0, entree, _Forme(), bt=0, priority_expr="0"))
    return f"""
#include <stdio.h>
#include <string.h>
typedef short s16; typedef unsigned short u16; typedef signed char s8; typedef unsigned char u8;
{_sinus_du_moteur()}
typedef struct {{ int x, y, rotation, scale_x, scale_y; }} A;
typedef struct {{ int rotation, scale_x, scale_y, flip_h, flip_v, offset_x, offset_y,
                  pivot_x, pivot_y, frame, obj_mode, priority, pal_bank; }} O;
typedef struct {{ u16 attr0, attr1, attr2, dummy; }} S;
A g_actors[1]; O g_oam_entries[1]; S shadow_oam[128]; int cam_x = 0, cam_y = 0; AffCache g_aff_cache[1];
int g_oam_dropped = 0;

/* Les entrées de la clé, dans l'ordre : rotation, rotation locale, échelles (acteur x y, sprite x y), décalage x y,
   pivot x y, flips h v. */
static void regler(const int p[12]) {{
    g_actors[0].x = 100 << 8; g_actors[0].y = 80 << 8;
    g_actors[0].rotation = p[0]; g_oam_entries[0].rotation = p[1];
    g_actors[0].scale_x = p[2]; g_actors[0].scale_y = p[3];
    g_oam_entries[0].scale_x = p[4]; g_oam_entries[0].scale_y = p[5];
    g_oam_entries[0].offset_x = p[6]; g_oam_entries[0].offset_y = p[7];
    g_oam_entries[0].pivot_x = p[8]; g_oam_entries[0].pivot_y = p[9];
    g_oam_entries[0].flip_h = p[10]; g_oam_entries[0].flip_v = p[11];
}}

static void rendre(unsigned out[7]) {{
    int _oamn = 0;
    memset(shadow_oam, 0, sizeof shadow_oam);
    {{
{lignes}
    }}
    out[0] = shadow_oam[0].dummy; out[1] = shadow_oam[1].dummy; out[2] = shadow_oam[2].dummy;
    out[3] = shadow_oam[3].dummy; out[4] = shadow_oam[0].attr0; out[5] = shadow_oam[0].attr1; out[6] = shadow_oam[0].attr2;
}}

int main(void) {{
    const int base[12] = {{37, 11, 256, 256, 256, 256, 20, 30, 3, 5, 0, 0}};
    /* une perturbation par entrée de la clé, plus deux paires dont la somme des champs ne bouge pas */
    int pert[16][12] = {{{{0}}}};
    int delta[16][12] = {{
        {{1,0,0,0,0,0,0,0,0,0,0,0}}, {{0,7,0,0,0,0,0,0,0,0,0,0}}, {{0,0,16,0,0,0,0,0,0,0,0,0}}, {{0,0,0,16,0,0,0,0,0,0,0,0}},
        {{0,0,0,0,16,0,0,0,0,0,0,0}}, {{0,0,0,0,0,16,0,0,0,0,0,0}}, {{0,0,0,0,0,0,8,0,0,0,0,0}}, {{0,0,0,0,0,0,0,8,0,0,0,0}},
        {{0,0,0,0,0,0,0,0,8,0,0,0}}, {{0,0,0,0,0,0,0,0,0,8,0,0}}, {{0,0,0,0,0,0,0,0,0,0,1,0}}, {{0,0,0,0,0,0,0,0,0,0,0,1}},
        {{0,0,0,0,0,0,8,0,-8,0,0,0}},      /* décalage +8, pivot -8 : `lx` ne change pas, `px` oui */
        {{0,0,0,0,0,0,0,8,0,-8,0,0}},      /* idem en y */
        {{0,0,16,0,-16,0,0,0,0,0,0,0}},    /* échelle acteur +16, échelle sprite -16 */
        {{360,0,0,0,0,0,0,0,0,0,0,0}},     /* un tour de plus : même angle, autre champ */
    }};
    long mauvais = 0, essais = 0, attendus_hits = 0;
    unsigned a[7], b[7], c[7];
    for (int k = -1; k < 16; k++) {{
        int p[12];
        for (int i = 0; i < 12; i++) p[i] = base[i] + (k >= 0 ? delta[k][i] : 0);
        /* le cache chaud sur la base (deux images : la deuxième range) ... */
        regler(base); memset(g_aff_cache, 0, sizeof g_aff_cache); rendre(c); rendre(c);
        /* ...la référence : les entrées perturbées sans cache ... */
        regler(p); memset(g_aff_cache, 0, sizeof g_aff_cache); rendre(b);
        /* ...puis les mêmes entrées perturbées SUR le cache chaud, trois images de suite : la première change la clé, la
           deuxième range, la troisième relit — chacune doit rendre la référence. */
        regler(base); memset(g_aff_cache, 0, sizeof g_aff_cache); rendre(c); rendre(c);
        regler(p);
        for (int image = 0; image < 3; image++) {{
            rendre(a);
            essais++;
            if (memcmp(a, b, sizeof a)) mauvais++;
        }}
    }}
    printf("essais %ld mauvais %ld\\n", essais, mauvais);
    return 0;
}}
"""


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le cache affine est vérifié en CI")
    dossier = tmp_path_factory.mktemp("affine_cache")
    (dossier / "sonde.c").write_text(_source(), encoding="utf-8")
    binaire = dossier / "sonde"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O1", "-w", "-o", str(binaire), str(dossier / "sonde.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    brut = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout
    valeurs = brut.split()
    return {"essais": int(valeurs[1]), "mauvais": int(valeurs[3])}


def test_le_cache_ne_rend_jamais_un_resultat_perime(sortie):
    assert sortie["essais"] == 51            # la base et seize perturbations de la clé, trois images chacune
    assert sortie["mauvais"] == 0
