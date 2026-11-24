"""L'émission ROM des grilles de valeurs : `grids.h`, `grids.c`, et le C réel.

Tranche 2 du chantier des cartes de valeurs peintes. Le dernier test compile ce
que le build vient d'écrire et lit les cases à travers les macros émises : c'est
le test de comportement du C réellement émis que la règle de zone réclame.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from codegen.runtime_codegen.grids import (
    array_name, emitted_grids, generate_grids_c, generate_grids_h,
    project_has_ram_grid, scene_ram_grids, seed_name,
    step_macro, value_macro, width_macro, write_grids,
)
from core.models.grid import Grid, GridValue
from core.models.scene import Scene
from native_toolchain import compilateur_hote, environnement

NATIVE_DIR = Path(__file__).resolve().parents[1] / "native"
SONDE_C = NATIVE_DIR / "grid_probe.c"


class _Projet:
    """Le strict nécessaire : l'émetteur lit `scenes` par `getattr`."""

    def __init__(self, *scenes):
        self.scenes = list(scenes)


def _terrain() -> Grid:
    """Une grille de 4 x 3 cases de 16 px, avec sa légende."""
    return Grid(
        name="Terrain", step=16,
        values=[GridValue(value=1, name="HERBE", color="#00ff00"),
                GridValue(value=3, name="EAU", color="#0000ff")],
        cells=[[0, 1, 1, 3],
               [1, 1, 3, 3],
               [0, 0, 1, 0]],
    )


def _arena() -> Scene:
    return Scene(name="Arena", grids=[_terrain()])


# ── Ce que le build émet, et ce qu'il saute ───────────────────────

def test_une_grille_sans_case_n_est_pas_emise():
    """Jamais dimensionnée : aucun script ne peut en lire quoi que ce soit."""
    scene = Scene(name="Arena", grids=[Grid(name="Terrain")])
    assert emitted_grids(_Projet(scene)) == []


def test_une_grille_toute_a_zero_est_emise_quand_meme():
    """La différence avec la carte de collision : 0 est une valeur, pas une absence."""
    grid = Grid(name="Terrain", step=16)
    grid.ensure_size(64, 64)
    scene = Scene(name="Arena", grids=[grid])
    assert [g.name for _s, g in emitted_grids(_Projet(scene))] == ["Terrain"]


def test_le_symbole_est_qualifie_par_la_scene():
    """Deux scènes peuvent nommer leur grille « Terrain » sans se marcher dessus."""
    arena, cave = _arena(), Scene(name="Cave", grids=[_terrain()])
    assert array_name(arena, arena.grids[0]) == "g_grid_Arena_Terrain"
    assert array_name(cave, cave.grids[0]) == "g_grid_Cave_Terrain"
    assert width_macro(arena, arena.grids[0]) == "GRID_W_ARENA_TERRAIN"
    assert value_macro(cave, cave.grids[0], "EAU") == "GRID_VALUE_CAVE_TERRAIN_EAU"


def test_un_nom_d_auteur_traverse_la_frontiere_du_c():
    """Espaces et ponctuation : `c_sym` et `c_ident` sont les seules portes.

    Les accents, eux, PASSENT (`'û'.isalnum()` est vrai) : c'est le comportement
    de `c_names`, partagé par tous les symboles émis du projet, pas une décision
    de ce module. Ce test le constate pour qu'un changement s'y voie."""
    scene = Scene(name="Salle 2", grids=[Grid(name="Coût terrain", step=16, cells=[[0]])])
    grid = scene.grids[0]
    assert array_name(scene, grid) == "g_grid_Salle_2_Coût_terrain"
    assert step_macro(scene, grid) == "GRID_STEP_SALLE_2_COÛT_TERRAIN"


# ── L'en-tête ─────────────────────────────────────────────────────

def test_l_en_tete_declare_la_geometrie_et_la_legende():
    scene = _arena()
    h = generate_grids_h(emitted_grids(_Projet(scene)))
    assert "#define GRID_W_ARENA_TERRAIN 4" in h
    assert "#define GRID_H_ARENA_TERRAIN 3" in h
    assert "#define GRID_STEP_ARENA_TERRAIN 16" in h
    assert "#define GRID_VALUE_ARENA_TERRAIN_HERBE 1" in h
    assert "#define GRID_VALUE_ARENA_TERRAIN_EAU 3" in h
    assert "extern const unsigned char g_grid_Arena_Terrain[12];" in h


def test_une_valeur_de_legende_sans_nom_ne_donne_pas_de_macro():
    scene = Scene(name="Arena", grids=[Grid(name="Terrain", step=16,
                                            values=[GridValue(value=2, name="")],
                                            cells=[[0]])])
    assert "GRID_VALUE_ARENA_TERRAIN_" not in generate_grids_h(emitted_grids(_Projet(scene)))


def test_l_en_tete_existe_meme_sans_grille(tmp_path):
    """Une unité qui l'inclut n'a jamais à le faire sous condition."""
    assert write_grids(tmp_path, _Projet(Scene(name="Arena"))) == []
    assert "no value grid in this project" in (tmp_path / "grids.h").read_text(encoding="utf-8")
    assert not (tmp_path / "grids.c").exists()


def test_le_c_disparait_quand_la_derniere_grille_s_en_va(tmp_path):
    write_grids(tmp_path, _Projet(_arena()))
    assert (tmp_path / "grids.c").exists()
    write_grids(tmp_path, _Projet(Scene(name="Arena")))
    assert not (tmp_path / "grids.c").exists()


# ── Le C des cases ────────────────────────────────────────────────

def test_les_cases_sortent_a_plat_une_rangee_par_ligne():
    scene = _arena()
    c = generate_grids_c(emitted_grids(_Projet(scene)))
    assert "const unsigned char g_grid_Arena_Terrain[12] = {" in c
    assert "    0, 1, 1, 3," in c
    assert "    1, 1, 3, 3," in c
    assert "    0, 0, 1, 0," in c


def test_une_rangee_plus_courte_est_completee_a_la_largeur():
    """Le C ne peut pas avoir de rangée trouée : la mise à plat la comble."""
    scene = Scene(name="Arena", grids=[Grid(name="Terrain", step=16,
                                            cells=[[1, 2, 3], [4]])])
    c = generate_grids_c(emitted_grids(_Projet(scene)))
    assert "    1, 2, 3," in c and "    4, 0, 0," in c


def test_le_rapport_rom_classe_les_grilles_dans_leur_poste():
    from codegen.rom_report import CATEGORY_ORDER, _SYMBOL_RULES
    categorie = next(c for c, motif in _SYMBOL_RULES if motif.search("g_grid_Arena_Terrain"))
    assert categorie == "Grilles"
    assert "Grilles" in CATEGORY_ORDER
    # La carte de collision garde son propre poste.
    assert next(c for c, motif in _SYMBOL_RULES if motif.search("g_cmap_Arena")) == "Collision"


# ── Les grilles RAM (partagées, inscriptibles au runtime) ─────────

def _flow_peinte() -> Grid:
    """Une grille RAM 2 x 2 avec un germe peint."""
    return Grid(name="Flow", step=16, ram=True, cells=[[0, 5], [0, 0]])


def test_l_en_tete_d_une_grille_ram_declare_un_tampon_non_const_et_son_germe():
    scene = Scene(name="Arena", grids=[_flow_peinte()])
    h = generate_grids_h(emitted_grids(_Projet(scene)))
    assert "extern unsigned char g_grid_Arena_Flow[4];" in h
    assert "extern const unsigned char g_grid_Arena_Flow_seed[4];" in h
    assert "RAM, runtime-writable" in h


def test_une_grille_ram_vide_n_a_pas_de_germe():
    """Rien de peint : le tampon part de zéro, aucun germe ROM n'est émis."""
    grid = Grid(name="Flow", step=16, ram=True)
    grid.ensure_size(32, 32)
    h = generate_grids_h(emitted_grids(_Projet(Scene(name="Arena", grids=[grid]))))
    assert "extern unsigned char g_grid_Arena_Flow[" in h
    assert "_seed" not in h


def test_le_c_d_une_grille_ram_est_un_tampon_ewram_plus_son_germe():
    scene = Scene(name="Arena", grids=[_flow_peinte()])
    c = generate_grids_c(emitted_grids(_Projet(scene)))
    assert '#include "gba_engine.h"' in c            # pour EWRAM_BSS
    assert "unsigned char g_grid_Arena_Flow[4] EWRAM_BSS;" in c
    assert "const unsigned char g_grid_Arena_Flow_seed[4] = {" in c
    assert "    0, 5," in c and "    0, 0," in c
    # Le tampon n'est jamais émis `const` : les scripts l'écrivent.
    assert "const unsigned char g_grid_Arena_Flow[" not in c


def test_grids_c_reste_sans_dependance_libgba_quand_tout_est_rom():
    """gba_engine.h n'est inclus que si une grille RAM l'exige."""
    c = generate_grids_c(emitted_grids(_Projet(_arena())))
    assert "gba_engine.h" not in c


def test_la_scene_liste_ses_grilles_ram_a_germer():
    scene = Scene(name="Arena", grids=[_flow_peinte(),
                                       Grid(name="Cost", step=16, ram=True, cells=[[0]]),
                                       _terrain()])  # ROM : pas germée
    inits = scene_ram_grids(scene)
    assert [g.sym for g in inits] == ["g_grid_Arena_Flow", "g_grid_Arena_Cost"]
    # Flow a un germe (contenu peint), Cost non (toute à zéro).
    assert inits[0].seed == seed_name(scene, scene.grids[0])
    assert inits[1].seed is None


def test_le_projet_sait_s_il_a_une_grille_ram():
    assert project_has_ram_grid(_Projet(_arena())) is False
    assert project_has_ram_grid(_Projet(Scene(name="Arena", grids=[_flow_peinte()]))) is True


# ── Le C réellement émis, compilé et exécuté ──────────────────────

def test_la_sonde_lit_dans_le_c_emis_ce_que_l_editeur_a_peint(tmp_path):
    """Compile `grids.h` + `grids.c` tels que le build les écrit, et compare."""
    compilateur = compilateur_hote()
    if compilateur is None:
        message = ("aucun compilateur C hôte (cc/gcc/clang, ou CC=...) — "
                   "le C émis des grilles n'est PAS vérifié")
        if os.environ.get("GBA_TESTS_REQUIRE_NATIVE"):
            pytest.fail(message)
        pytest.skip(message + " ; il l'est en CI")

    scene = _arena()
    write_grids(tmp_path, _Projet(scene))

    binaire = tmp_path / "grid_probe"
    env = environnement(compilateur)
    compile = subprocess.run(
        [compilateur, "-std=c11", "-O0", "-Wall", "-Werror",
         "-o", str(binaire), str(SONDE_C), str(tmp_path / "grids.c"),
         "-I", str(tmp_path)],
        capture_output=True, text=True, env=env,
    )
    assert compile.returncode == 0, f"le C émis ne compile pas :\n{compile.stderr}"

    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    lignes = dict(L.split(" ", 1) for L in run.stdout.strip().splitlines())

    assert lignes["W"] == "4" and lignes["H"] == "3" and lignes["STEP"] == "16"
    assert lignes["EAU"] == "3"
    attendu = [str(v) for row in scene.grids[0].cells for v in row]
    assert lignes["CELLS"].split() == attendu
    assert lignes["OUT"] == "0 0"
