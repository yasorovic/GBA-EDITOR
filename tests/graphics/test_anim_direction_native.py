"""Le choix de la direction d'animation, exécuté en C (le vrai bloc émis par `anim_tick_lines`).

Un sprite qui ne dessine que Est et Ouest (le platformer) ne doit jamais afficher la frame 0
du sheet — celle d'un AUTRE état — quand `auto_dir` lui demande Nord (un saut droit). Le repli,
dans l'état courant : la direction exacte, puis l'omni, puis le côté REGARDÉ (`face_x`, le dernier
`dir_x` non nul), puis la première direction de l'état."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

DEMO = Path(__file__).resolve().parents[2] / "Project Demo" / "Platformer"

# Platformer/Player : Idle = W (frame 0, miroir) + E (1) ; Moving = 2..13 ; Jumping = W (14) + E (15).
JUMPING, W_JUMP, E_JUMP = 2, 14, 15

SONDE = """
#include <stdio.h>
typedef signed char s8; typedef unsigned char u8; typedef short s16;
typedef struct { int vx, vy; s8 dir_x, dir_y; } A;
typedef struct { u8 auto_dir, anim_state, anim_loop, anim_finished, anim_speed, anim_length;
                 s8 face_x; int frame, timer; } O;
A g_actors[1]; O g_oam_entries[1];
%(tables)s
int main(void) {
    int vx, vy, dx, dy, face, state;
    while (scanf("%%d %%d %%d %%d %%d %%d", &state, &vx, &vy, &dx, &dy, &face) == 6) {
        g_actors[0].vx = vx; g_actors[0].vy = vy; g_actors[0].dir_x = dx; g_actors[0].dir_y = dy;
        g_oam_entries[0].auto_dir = 1; g_oam_entries[0].anim_state = state;
        g_oam_entries[0].frame = 0;  g_oam_entries[0].face_x = face;
        {
%(tick)s
        }
        printf("%%d %%d\\n", g_oam_entries[0].frame, g_oam_entries[0].face_x);
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def sonde(tmp_path_factory):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; le choix de direction est vérifié en CI")
    if not DEMO.is_dir():
        pytest.skip("projet de démo absent")
    from core.project import Project
    from codegen.runtime_codegen.gen_sprite import anim_tables_for, anim_tick_lines
    dossier = tmp_path_factory.mktemp("anim_direction")
    copie = dossier / "Platformer"
    shutil.copytree(DEMO, copie, ignore=shutil.ignore_patterns("build"))
    p = Project.open(copie)
    source = SONDE % {"tables": "\n".join(anim_tables_for(p, p.get_sprite("Player"))),
                      "tick": "\n".join(anim_tick_lines(0, "sprite_Player"))}
    (dossier / "probe.c").write_text(source, encoding="utf-8")
    binaire = dossier / "probe"
    resultat = subprocess.run([compilateur, "-std=gnu11", "-O0", "-w", "-o", str(binaire),
                               str(dossier / "probe.c")],
                              capture_output=True, text=True, env=environnement(compilateur))
    assert resultat.returncode == 0, resultat.stderr

    def lancer(state, vx, vy, dx, dy, face):
        sortie = subprocess.run([str(binaire)], input=f"{state} {vx} {vy} {dx} {dy} {face}",
                                capture_output=True, text=True,
                                env=environnement(compilateur)).stdout.split()
        return int(sortie[0]), int(sortie[1])      # (frame affichée, côté regardé)

    return lancer


def test_un_saut_lateral_garde_la_frame_du_cote_du_mouvement(sonde):
    assert sonde(JUMPING, 256, -900, 0, 0, 0) == (E_JUMP, 1)
    assert sonde(JUMPING, -256, -900, 0, 0, 0) == (W_JUMP, -1)


def test_un_saut_droit_garde_le_cote_regarde(sonde):
    """`auto_dir` met dir_x à 0 : le côté regardé est retenu à part, jamais la frame 0."""
    assert sonde(JUMPING, 0, -900, 0, 0, 1) == (E_JUMP, 1)
    assert sonde(JUMPING, 0, -900, 0, 0, -1) == (W_JUMP, -1)


def test_sans_cote_connu_la_premiere_direction_de_l_etat_est_choisie(sonde):
    """Jamais la frame 0 du sheet : celle-ci est l'état Idle, pas Jumping."""
    frame, _ = sonde(JUMPING, 0, -900, 0, 0, 0)
    assert frame in (W_JUMP, E_JUMP)


def test_la_direction_exacte_reste_prioritaire(sonde):
    assert sonde(JUMPING, 0, 0, 1, 0, -1) == (E_JUMP, 1)     # le script regarde à l'est
