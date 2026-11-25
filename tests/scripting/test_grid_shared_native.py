"""Preuve de comportement du C émis : une grille RAM de scène PARTAGÉE entre
scripts.

C'est le test de comportement que la règle de zone réclame pour ce chantier. Il
compile le VRAI `grids.c` émis (le tampon RAM `g_grid_Arena_Flow` et son germe
ROM) avec trois unités de traduction distinctes : un « script de scène » qui
ÉCRIT la grille (`data.grid.Flow:fill_rect`), un « script d'acteur » qui la LIT
(`data.grid.Flow:at` et `[x][y]`), et un main qui la germe comme `gen_scene_init`.
Les trois ne voient le tampon que par l'`extern` de `grids.h` : si le lecteur
retrouve ce que l'écrivain a posé, le partage inter-scripts tient au niveau du C.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from codegen.runtime_codegen.grids import scene_grid_access, write_grids
from core.models.grid import Grid
from core.models.scene import Scene
from native_toolchain import compilateur_hote, environnement
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"


class _Projet:
    def __init__(self, *scenes):
        self.scenes = list(scenes)


def _scene() -> Scene:
    """Une scène « Arena » avec une grille RAM `Flow` de 4 x 3 cases, germée :
    la case (1,1) vaut 5 et la case (4,3) vaut 3 (base 1)."""
    flow = Grid(name="Flow", step=16, ram=True,
                cells=[[5, 0, 0, 0],
                       [0, 0, 0, 0],
                       [0, 0, 0, 3]])
    return Scene(name="Arena", grids=[flow])


def _acces() -> dict:
    return scene_grid_access(_scene())


def _emis(corps: str) -> str:
    code, _g, _c = generate(parse(f"function on_update()\n{corps}\nend\n"), CodegenContext(
        actor_name="Chaser", actor_sym="Chaser", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Chaser"],
        scene_sym="Arena", scene_grids=_acces()))
    return code


def _ligne(corps: str, motif: str) -> str:
    ligne = next(L.strip() for L in _emis(corps).splitlines() if motif in L)
    return ligne[ligne.index(motif):].rstrip(";")


def _expression(corps: str) -> str:
    (ligne,) = [L.strip() for L in _emis(corps).splitlines() if L.strip().startswith("int v =")]
    return ligne[len("int v ="):].strip().rstrip(";")


def _inline_du_moteur() -> str:
    source = (MOTEUR_DIR / "runtime_api_inline.h").read_text(encoding="utf-8")
    morceaux = []
    for signature in (r"static inline int grid_value_at\(.*?\n\}\n",
                      r"static inline void grid_fill_rect\(.*?\n\}\n"):
        trouve = re.search(signature, source, re.S)
        assert trouve, f"inline introuvable dans runtime_api_inline.h : {signature}"
        morceaux.append(trouve.group(0))
    return "\n".join(morceaux)


def test_un_script_ecrit_la_grille_ram_de_scene_un_autre_la_relit(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "le partage de grille RAM n'est PAS vérifié sur le C émis")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")

    # Le C émis du build : grids.h (externs + macros) et grids.c (le tampon RAM
    # avec EWRAM_BSS et le germe ROM).
    write_grids(tmp_path, _Projet(_scene()))
    # EWRAM_BSS vient de libgba au build ; pour l'hôte, un en-tête neutre le vide.
    (tmp_path / "gba_engine.h").write_text("#define EWRAM_BSS\n", encoding="utf-8")
    (tmp_path / "grid_inline.h").write_text(_inline_du_moteur(), encoding="utf-8")

    write_rect = _ligne("data.grid.Flow:fill_rect(x, y, w, h, v)", "grid_fill_rect(")
    read_at = _expression("local v = data.grid.Flow:value_at(px, py)")
    cell = _expression("local v = data.grid.Flow[x][y]")
    # Les symboles émis doivent bien viser le tampon partagé, qualifié par la scène.
    assert "g_grid_Arena_Flow" in write_rect
    assert "g_grid_Arena_Flow" in read_at and "g_grid_Arena_Flow" in cell
    (tmp_path / "grid_shared_expr.h").write_text(
        "#define GRID_WRITE_RECT(x, y, w, h, v) " + write_rect + "\n"
        "#define GRID_READ_AT(px, py) " + read_at + "\n"
        "#define GRID_CELL(x, y) " + cell + "\n", encoding="utf-8")

    binaire = tmp_path / "grid_shared_probe"
    env = environnement(compilateur)
    compile = subprocess.run(
        [compilateur, "-std=c11", "-Wall", "-Werror", "-O0", "-I", str(tmp_path),
         str(tmp_path / "grids.c"),
         str(NATIVE_DIR / "grid_shared_writer.c"),
         str(NATIVE_DIR / "grid_shared_reader.c"),
         str(NATIVE_DIR / "grid_shared_main.c"),
         "-o", str(binaire)],
        capture_output=True, text=True, env=env)
    assert compile.returncode == 0, f"le C émis ne compile pas :\n{compile.stderr}"

    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    lignes = dict(L.split(" ", 1) for L in run.stdout.strip().splitlines())

    assert lignes["SEED"] == "5 3"       # le germe peint est bien copié en RAM
    assert lignes["WRITTEN"] == "9 9"    # ce que la scène a écrit, l'acteur le lit
    assert lignes["KEPT"] == "5"         # hors du rectangle, le germe tient
    assert lignes["AT"] == "9"           # lecture par pixel : même tampon
