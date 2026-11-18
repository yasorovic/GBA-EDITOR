"""Lire une grille de valeurs depuis un script : `data.grid.<Nom>`.

Tranche 3b du chantier des cartes de valeurs peintes. Deux accès, tous deux en
lecture seule : `:at(x, y)` en pixels monde, comme `collision.tile_at`, et
`[x][y]` en cases, la colonne puis la rangée, index à partir de 1 comme tout
tableau du sous-ensemble.

Le dernier test compile ensemble le `grids.h` émis, l'inline `grid_value_at` du
moteur et les expressions que le traducteur vient de produire : c'est le test de
comportement du C réellement émis que la règle de zone réclame.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from codegen.runtime_codegen.grids import scene_grid_access, write_grids
from core.models.grid import Grid, GridValue
from core.models.scene import Scene
from native_toolchain import compilateur_hote, environnement
from scripting.checker import BuildContext, check
from scripting.codegen import CodegenContext, generate
from scripting.parser import parse

REPO_DIR = Path(__file__).resolve().parents[2]
NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
MOTEUR_DIR = REPO_DIR / "runtime" / "include"

CASES = [[0, 1, 3, 3],
         [1, 1, 3, 0],
         [0, 2, 2, 1]]


def _scene() -> Scene:
    """La scène de référence : une grille de 4 x 3 cases de 16 px, avec sa légende."""
    return Scene(name="Arena", grids=[Grid(
        name="Terrain", step=16,
        values=[GridValue(value=1, name="HERBE"), GridValue(value=3, name="EAU")],
        cells=[list(row) for row in CASES])])


def _acces(scene=None) -> dict:
    return scene_grid_access(scene or _scene())


def _handler(corps: str) -> str:
    return f"function on_update()\n{corps}\nend\n"


def _erreurs(corps: str, acces=None) -> list[str]:
    ctx = BuildContext(actor_name="Ball", scene_label="Arena",
                       scene_grids=_acces() if acces is None else acces)
    return [e.message for e in check(parse(_handler(corps)), ctx) if e.level == "error"]


def _emis(corps: str) -> str:
    code, _globals, _consts = generate(parse(_handler(corps)), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=["Ball"],
        scene_sym="Arena", scene_grids=_acces()))
    return code


def _inline_du_moteur() -> str:
    """`grid_value_at`, extrait de `runtime_api_inline.h`.

    La sonde compile le VRAI code du moteur, sans l'en-tête entier : celui-ci réclame
    tout l'état du runtime (l'OAM, les sauvegardes, les palettes), alors que cette
    fonction ne prend qu'un pointeur et des entiers. Si elle est renommée ou déplacée,
    l'extraction échoue, et le test le dit."""
    source = (MOTEUR_DIR / "runtime_api_inline.h").read_text(encoding="utf-8")
    trouve = re.search(r"static inline int grid_value_at\(.*?\n\}\n", source, re.S)
    assert trouve, "grid_value_at est introuvable dans runtime_api_inline.h"
    return trouve.group(0)


def _expression(corps: str) -> str:
    """La seule expression émise par `local v = …`, sans son habillage."""
    (ligne,) = [L.strip() for L in _emis(corps).splitlines() if L.strip().startswith("int v =")]
    return ligne[len("int v ="):].strip().rstrip(";")


# ── Ce que le vérificateur accepte ────────────────────────────────

def test_les_deux_acces_passent():
    assert _erreurs("local v = data.grid.Terrain:at(32, 16)") == []
    assert _erreurs("local v = data.grid.Terrain[2][1]") == []
    assert _erreurs("local v = data.grid.Terrain[x][y]") == []


def test_hors_build_une_grille_n_est_pas_jugee():
    """Comme pour les tables : sans contexte de scène, on ne juge pas."""
    assert _erreurs("local v = data.grid.Terrain:at(0, 0)", acces=None) == []
    ctx = BuildContext(actor_name="Ball")
    assert [e for e in check(parse(_handler("local v = data.grid.Peu_importe:at(0, 0)")), ctx)
            if e.level == "error"] == []


# ── Ce qu'il refuse ───────────────────────────────────────────────

def test_une_grille_absente_de_la_scene_nomme_la_scene_et_les_grilles():
    (msg,) = _erreurs("local v = data.grid.Absente:at(0, 0)")
    assert "no painted grid of scene Arena by that name (Terrain)" in msg


def test_une_grille_citee_seule_n_est_pas_une_valeur():
    (msg,) = _erreurs("local v = data.grid.Terrain")
    assert "is a grid, not a value" in msg
    assert ":at(x, y)" in msg and "[x][y]" in msg


def test_la_seule_methode_est_at():
    (msg,) = _erreurs("local v = data.grid.Terrain:lire(1, 2)")
    assert "read-only, and its only method is :at(x, y)" in msg


def test_at_prend_deux_arguments():
    (msg,) = _erreurs("local v = data.grid.Terrain:at(1)")
    assert "takes two arguments, x and y in world pixels (1 given)" in msg


def test_une_case_hors_bornes_est_refusee_quand_elle_est_ecrite_en_clair():
    (msg,) = _erreurs("local v = data.grid.Terrain[9][1]")
    assert "out of bounds on x" in msg and "from 1 to 4" in msg
    (msg,) = _erreurs("local v = data.grid.Terrain[1][7]")
    assert "out of bounds on y" in msg and "from 1 to 3" in msg


def test_une_seule_dimension_ne_designe_pas_une_case():
    (msg,) = _erreurs("local v = data.grid.Terrain[1]")
    assert "has two dimensions" in msg


def test_une_grille_ne_s_ecrit_pas():
    (msg,) = _erreurs("data.grid.Terrain[1][1] = 4")
    assert "cannot be written" in msg and "constant, baked into the ROM" in msg


def test_une_faute_ne_donne_qu_un_message():
    """La marche des expressions redescend dans le récepteur : sans la marque des
    nœuds déjà lus, chaque faute en produirait deux."""
    for corps in ("local v = data.grid.Absente:at(0, 0)",
                  "local v = data.grid.Terrain:at(1)",
                  "local v = data.grid.Terrain[9][1]",
                  "data.grid.Terrain[1][1] = 4"):
        assert len(_erreurs(corps)) == 1, corps


# ── Ce que le traducteur émet ─────────────────────────────────────

def test_l_acces_par_pixel_passe_par_l_inline_du_moteur():
    assert _expression("local v = data.grid.Terrain:at(32, 16)") == (
        "grid_value_at(g_grid_Arena_Terrain, GRID_W_ARENA_TERRAIN, "
        "GRID_H_ARENA_TERRAIN, GRID_SHIFT_ARENA_TERRAIN, 32, 16)")


def test_l_acces_par_case_indexe_le_tableau_mis_a_plat():
    """La grille est émise en une dimension : la chaîne `[x][y]` ne se compose pas
    toute seule comme celle d'une table, le build calcule l'indice."""
    assert _expression("local v = data.grid.Terrain[2][1]") == (
        "g_grid_Arena_Terrain[(0) * GRID_W_ARENA_TERRAIN + (1)]")
    assert _expression("local v = data.grid.Terrain[x][y]") == (
        "g_grid_Arena_Terrain[((y) - 1) * GRID_W_ARENA_TERRAIN + ((x) - 1)]")


def test_l_unite_inclut_l_en_tete_des_grilles():
    assert '#include "grids.h"' in _emis("local v = data.grid.Terrain:at(0, 0)")


# ── Le C réellement émis, compilé et exécuté ──────────────────────

def test_la_sonde_lit_dans_le_c_emis_ce_que_l_editeur_a_peint(tmp_path):
    compilateur = compilateur_hote()
    if compilateur is None:
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "la lecture d'une grille n'est PAS vérifiée sur le C émis")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; elle l'est en CI")

    class _Projet:
        scenes = [_scene()]

    write_grids(tmp_path, _Projet())
    (tmp_path / "grid_inline.h").write_text(_inline_du_moteur(), encoding="utf-8")

    # Les deux expressions du traducteur, paramétrées par leurs coordonnées : le
    # littéral écrit dans le script est remplacé par le paramètre de la macro.
    at = _expression("local v = data.grid.Terrain:at(111, 222)")
    at = at.replace("111", "(px)").replace("222", "(py)")
    cell = _expression("local v = data.grid.Terrain[x][y]")
    (tmp_path / "grid_expr.h").write_text(
        "#define GRID_EXPR_AT(px, py) " + at + "\n"
        "#define GRID_EXPR_CELL(x, y) " + cell + "\n", encoding="utf-8")

    binaire = tmp_path / "grid_read_probe"
    env = environnement(compilateur)
    compile = subprocess.run(
        [compilateur, "-std=c11", "-Wall", "-Werror", "-O0",
         "-I", str(tmp_path),
         str(NATIVE_DIR / "grid_read_probe.c"), str(tmp_path / "grids.c"), "-o", str(binaire)],
        capture_output=True, text=True, env=env)
    assert compile.returncode == 0, f"le C émis ne compile pas :\n{compile.stderr}"

    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    sortie = dict(re.match(r"(\w+) (.*)", L).groups() for L in run.stdout.strip().splitlines())

    attendu = [str(v) for row in CASES for v in row]
    assert sortie["AT"].split() == attendu      # par pixel, au centre de chaque case
    assert sortie["CELL"].split() == attendu    # par case, même ordre
    assert sortie["OUT"] == "0 0"               # hors grille vaut 0
    assert sortie["EAU"] == "3"
