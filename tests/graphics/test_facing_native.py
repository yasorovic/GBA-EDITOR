"""Le regard (`facing`) face à la trajectoire (`dir`), exécutés en C (le vrai bloc émis par
`direction_lines`) : `dir_x/dir_y` retombent à 0 à l'arrêt, `facing_x/facing_y` gardent la dernière
direction non nulle, en VECTEUR entier."""
from __future__ import annotations

import subprocess

import pytest

from native_toolchain import compilateur_hote, environnement

SONDE = """
#include <stdio.h>
typedef signed char s8; typedef unsigned char u8; typedef short s16;
typedef struct { int vx, vy; s8 dir_x, dir_y, facing_x, facing_y; } A;
typedef struct { u8 facing_auto; s8 face_x; } O;
A g_actors[1]; O g_oam_entries[1];
int main(void) {
    int vx, vy, auto_on;
    while (scanf("%%d %%d %%d", &vx, &vy, &auto_on) == 3) {
        g_actors[0].vx = vx; g_actors[0].vy = vy;
        g_oam_entries[0].facing_auto = auto_on;
%(direction)s
        printf("%%d %%d %%d %%d\\n", g_actors[0].dir_x, g_actors[0].dir_y,
               g_actors[0].facing_x, g_actors[0].facing_y);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def pas(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le regard est vérifié en CI")
    from codegen.runtime_codegen.gen_sprite import direction_lines
    dossier = tmp_path_factory.mktemp("facing")
    (dossier / "probe.c").write_text(SONDE % {"direction": "\n".join(direction_lines(0, 0))},
                                     encoding="utf-8")
    binaire = dossier / "probe"
    resultat = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-o", str(binaire),
                               str(dossier / "probe.c")],
                              capture_output=True, text=True, env=environnement(compilateur))
    assert resultat.returncode == 0, resultat.stderr

    def lancer(*frames):
        """Chaque frame = (vx, vy, facing_auto) ; rend (dir_x, dir_y, facing_x, facing_y) de la
        dernière, l'état de l'acteur se conservant d'une frame à l'autre."""
        entree = "\n".join(f"{vx} {vy} {a}" for vx, vy, a in frames)
        # Un processus par séquence : l'état C (g_actors) persiste le long de l'entrée.
        sortie = subprocess.run([str(binaire)], input=entree, capture_output=True, text=True,
                                env=environnement(compilateur)).stdout.strip().splitlines()
        return tuple(int(v) for v in sortie[-1].split())

    return lancer


def test_la_trajectoire_retombe_a_zero_et_le_regard_reste(pas):
    assert pas((256, 0, 1), (0, 0, 1)) == (0, 0, 1, 0)


def test_le_regard_est_un_vecteur_pas_un_cote_par_axe(pas):
    """Un pas à droite puis un pas vers le haut : on regarde en haut, pas en haut à droite."""
    assert pas((256, 0, 1), (0, -256, 1)) == (0, -1, 0, -1)
    assert pas((256, 0, 1), (0, -256, 1), (0, 0, 1)) == (0, 0, 0, -1)


def test_une_diagonale_se_regarde_en_diagonale(pas):
    assert pas((-256, 256, 1), (0, 0, 1)) == (0, 0, -1, 1)


def test_sans_facing_auto_le_regard_ne_suit_pas_mais_la_trajectoire_oui(pas):
    assert pas((256, 0, 0)) == (1, 0, 0, 0)
