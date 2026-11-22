"""Le socle de la collision modifiable, sur le C réellement émis.

Une scène `collision_mutable` copie sa carte peinte (ROM) dans un buffer RAM
partagé à l'entrée de scène ; la carte active pointe dessus et devient écrivable
par `g_active_cmap_w`. La sonde compile les DONNÉES (`scene_data_lines`) et la
dispatch d'init (`_scene_state_lines`) réellement émises, vérifie que la copie RAM
reflète la carte peinte, puis qu'une écriture par l'alias change la lecture SANS
toucher la source ROM. Renommé ou déplacé, l'un des symboles émis, l'extraction
ou la compilation échoue.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from native_toolchain import compilateur_hote, environnement

INCLUDE = Path(__file__).resolve().parents[2] / "runtime" / "include"

SONDE = r"""
#include <stdio.h>
#include <stddef.h>
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

/* Les globals de la carte active, du même type que `character.py` les déclare. */
const u8 *g_active_cmap = NULL;
u8 *g_active_cmap_w = NULL;
int g_cmap_w = 0, g_cmap_h = 0;
u8 g_ow_any = 0;
const u8 *g_ow_rows = NULL, *g_ow_cols = NULL;

@DATA@

int main(void){
@INIT@
    /* La copie RAM reflète la carte peinte : un mur en case (1, 1), rien ailleurs. */
    printf("MAP");
    for(int ty = 0; ty < g_cmap_h; ty++)
        for(int tx = 0; tx < g_cmap_w; tx++)
            printf(" %d", g_active_cmap[ty * g_cmap_w + tx]);
    printf("\n");
    /* Une écriture par l'alias change la lecture, sans toucher la source ROM. */
    g_active_cmap_w[0 * g_cmap_w + 2] = 1;
    printf("AFTER %d %d\n", g_active_cmap[2], g_cmap_Arena[2]);
    return 0;
}
"""


def _data_et_init() -> tuple[list[str], list[str]]:
    from codegen.runtime_codegen.gen_scene_data import c_sym, scene_data_lines
    from codegen.runtime_codegen.gen_scene_init import _scene_state_lines
    from core.models.scene import Scene
    from core.project import Project

    scene = Scene(name="Arena")
    scene.ensure_collision_map(32, 24)   # 4 x 3 tuiles de 8 px
    scene.collision_mutable = True
    scene.collision_map[1][1] = 1        # un mur en case (1, 1)
    p = Project(tempfile.mkdtemp())
    p.scenes.items = [scene]
    data = scene_data_lines(p, [{"scene": scene}])
    init = [L for L in _scene_state_lines(scene, c_sym(scene.name), 0)
            if any(k in L for k in ("g_cmap_w =", "g_cmap_ram", "g_active_cmap", "g_ow_"))]
    assert any("g_cmap_ram[" in L for L in data), "le buffer RAM n'est pas émis"
    assert any("g_cmap_ram[_i] = g_cmap_Arena" in L for L in init), "la copie ROM vers RAM n'est pas émise"
    return data, init


def test_le_socle_copie_la_carte_puis_la_laisse_ecrire(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision modifiable est vérifiée en CI")
    data, init = _data_et_init()
    source = SONDE.replace("@DATA@", "\n".join(data)).replace("@INIT@", "\n".join(init))
    (tmp_path / "probe.c").write_text(source, encoding="utf-8")
    binaire = tmp_path / "probe"
    construit = subprocess.run(
        [compilateur, "-std=gnu11", "-Wall", "-Werror", "-O0", "-I", str(INCLUDE),
         "-o", str(binaire), str(tmp_path / "probe.c")],
        capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert run.returncode == 0, run.stderr
    sortie = {L.split(" ", 1)[0]: L.split(" ", 1)[1] for L in run.stdout.strip().splitlines()}

    # La RAM est la copie exacte de la carte peinte : seul le mur (1, 1) = index 5.
    assert sortie["MAP"] == "0 0 0 0 0 1 0 0 0 0 0 0"
    # Après écriture de la case (2, 0) : la lecture voit 1, la source ROM reste 0.
    assert sortie["AFTER"] == "1 0"


ECRITURE = r"""
#include <stdio.h>
#include <stddef.h>
typedef unsigned char u8;
#define TILE_SIZE 8

const u8 *g_active_cmap = NULL;
u8 *g_active_cmap_w = NULL;
int g_cmap_w = 0, g_cmap_h = 0;

@FUNCS@

static u8 carte[4 * 3];

int main(void){
    for(int i = 0; i < 4 * 3; i++) carte[i] = 0;
    g_cmap_w = 4; g_cmap_h = 3; g_active_cmap = carte; g_active_cmap_w = carte;

    collision_fill_rect(1, 1, 2, 2, 1);   /* bloc 2x2 en haut-gauche */
    collision_set_tile(4, 3, 7);          /* une case en bas-droite */
    collision_fill_rect(3, 1, 5, 2, 2);   /* déborde la carte : écrêté */
    printf("MAP");
    for(int ty = 0; ty < 3; ty++)
        for(int tx = 0; tx < 4; tx++)
            printf(" %d", collision_map_tile(tx * 8 + 4, ty * 8 + 4));
    printf("\n");

    /* Scène en ROM (alias à NULL) : l'écriture est sans effet. */
    g_active_cmap_w = NULL;
    collision_set_tile(1, 1, 9);
    printf("GUARD %d\n", collision_map_tile(4, 4));
    return 0;
}
"""


def _trois_fonctions() -> str:
    from codegen.runtime_codegen.physics.character import character_solver_lines
    src = "\n".join(character_solver_lines())
    out = []
    for sig in (r"int collision_map_tile\(.*?\n\}",
                r"void collision_set_tile\(.*?\n\}",
                r"void collision_fill_rect\(.*?\n\}"):
        m = re.search(sig, src, re.S)
        assert m, f"fonction introuvable dans character.py : {sig}"
        out.append(m.group(0))
    return "\n".join(out)


def test_l_ecriture_par_le_c_emis(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        pytest.skip("aucun compilateur C hôte ; la collision modifiable est vérifiée en CI")
    source = ECRITURE.replace("@FUNCS@", _trois_fonctions())
    (tmp_path / "probe.c").write_text(source, encoding="utf-8")
    binaire = tmp_path / "probe"
    construit = subprocess.run(
        [compilateur, "-std=gnu11", "-Wall", "-Werror", "-O0", "-I", str(INCLUDE),
         "-o", str(binaire), str(tmp_path / "probe.c")],
        capture_output=True, text=True, env=environnement(compilateur))
    assert construit.returncode == 0, construit.stderr
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(compilateur))
    assert run.returncode == 0, run.stderr
    sortie = {L.split(" ", 1)[0]: L.split(" ", 1)[1] for L in run.stdout.strip().splitlines()}

    # fill_rect base 1 -> 0, set_tile une case, fill_rect débordant écrêté à la carte.
    assert sortie["MAP"] == "1 1 2 2 1 1 2 2 0 0 0 7"
    # Sur une scène en ROM (alias NULL), l'écriture n'a rien changé.
    assert sortie["GUARD"] == "1"


def test_une_scene_non_modifiable_garde_le_chemin_rom():
    """Sans le drapeau, l'init pointe la carte ROM et laisse l'alias écrivable à NULL."""
    from codegen.runtime_codegen.gen_scene_init import _scene_state_lines
    from core.models.scene import Scene

    scene = Scene(name="Rom")
    scene.ensure_collision_map(32, 24)
    scene.collision_map[1][1] = 1
    lignes = "\n".join(_scene_state_lines(scene, "Rom", 0))
    assert "g_active_cmap = g_cmap_Rom;" in lignes
    assert "g_active_cmap_w = NULL;" in lignes
    assert "g_cmap_ram" not in lignes
