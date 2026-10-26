"""Le calcul de la matrice affine, en C réel : le nouveau code (réduction d'angle sans division, inverse des échelles
calculé une fois) doit rendre ce que rendait l'ancien — `gba_sin`/`gba_cos` à l'identique, la matrice à 1 près
(la troncature se fait après l'inverse, plus avant)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

RUNTIME = Path(__file__).resolve().parents[2] / "runtime" / "include" / "runtime_api_inline.h"

SONDE = r"""
#include <stdio.h>
typedef short s16; typedef signed char s8; typedef unsigned char u8;
%(moteur)s

/* L'ancien calcul, tel qu'il était écrit. */
static int old_sin(int deg) {
    deg = ((deg %% 360) + 360) %% 360;
    int neg = deg >= 180;
    if (neg) deg -= 180;
    if (deg > 90) deg = 180 - deg;
    return neg ? -SIN_LUT[deg] : SIN_LUT[deg];
}
static int old_cos(int deg) { return old_sin(deg + 90); }

int main(void) {
    long bad_sin = 0, bad_cos = 0, bad_sc = 0, n = 0;
    for (int d = -120000; d <= 120000; d++) {
        int s, c;
        gba_sincos(d, &s, &c);
        n++;
        if (gba_sin(d) != old_sin(d)) bad_sin++;
        if (gba_cos(d) != old_cos(d)) bad_cos++;
        if (s != old_sin(d) || c != old_cos(d)) bad_sc++;
    }
    printf("angles %%ld %%ld %%ld %%ld\n", n, bad_sin, bad_cos, bad_sc);

    int scales[] = {1, 2, 3, 16, 64, 100, 128, 200, 255, 256, 257, 300, 512, 1000, 2047, 2048, -256, -128, 0};
    int ns = (int)(sizeof scales / sizeof scales[0]);
    long worst = 0, cells = 0;
    for (int a = 0; a < 360; a += 5) {
        int sinA = old_sin(a), cosA = old_cos(a);
        for (int i = 0; i < ns; i++)
            for (int j = 0; j < ns; j++) {
                int sx = scales[i], sy = scales[j];
                int pa, pb, pc, pd;
                gba_affine_matrix(cosA, sinA, sx, sy, &pa, &pb, &pc, &pd);
                int opa = sx ? cosA * 256 / sx : 0, opb = sx ? sinA * 256 / sx : 0;
                int opc = sy ? -sinA * 256 / sy : 0, opd = sy ? cosA * 256 / sy : 0;
                if (!opa && !opb) opa = 1;
                if (!opc && !opd) opd = 1;
                int diffs[4] = {pa - opa, pb - opb, pc - opc, pd - opd};
                for (int k = 0; k < 4; k++) {
                    long dk = diffs[k] < 0 ? -diffs[k] : diffs[k];
                    /* hors de la plage 16 bits de la matrice, la valeur est tronquée au rangement : on la compare telle quelle */
                    long ref = (k == 0 ? opa : k == 1 ? opb : k == 2 ? opc : opd);
                    long mag = ref < 0 ? -ref : ref;
                    long allowed = 1 + mag / 4096;     /* l'inverse est arrondi à 2^-14 près en relatif */
                    if (dk > allowed && dk - allowed > worst) worst = dk - allowed;
                }
                cells++;
            }
    }
    printf("matrice %%ld %%ld\n", cells, worst);
    return 0;
}
"""


def _moteur() -> str:
    texte = RUNTIME.read_text(encoding="utf-8")
    debut = texte.index("static const s16 SIN_LUT")
    fin = texte.index("/* fin de la trigonométrie du moteur */")
    return texte[debut:fin]


@pytest.fixture(scope="module")
def sortie(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la matrice affine est vérifiée en CI")
    dossier = tmp_path_factory.mktemp("affine_math")
    (dossier / "sonde.c").write_text(SONDE % {"moteur": _moteur()}, encoding="utf-8")
    binaire = dossier / "sonde"
    construit = subprocess.run([compilateur, "-std=gnu11", "-O1", "-w", "-o", str(binaire), str(dossier / "sonde.c")],
                               capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    brut = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur)).stdout
    return {ligne.split()[0]: [int(v) for v in ligne.split()[1:]] for ligne in brut.strip().splitlines()}


def test_sinus_et_cosinus_sont_ceux_de_l_ancien_calcul_sur_toute_la_plage(sortie):
    n, mauvais_sin, mauvais_cos, mauvais_sincos = sortie["angles"]
    assert n == 240001
    assert (mauvais_sin, mauvais_cos, mauvais_sincos) == (0, 0, 0)       # négatifs et très grands angles compris


def test_la_matrice_est_celle_de_l_ancien_calcul_a_la_troncature_pres(sortie):
    cellules, pire = sortie["matrice"]
    assert cellules > 5000
    assert pire == 0
