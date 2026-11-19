"""Les grilles de valeurs d'une scène : le modèle, ses défauts et sa sérialisation.

Tranche 1 du chantier des cartes de valeurs peintes. Rien ici ne touche au
codegen ni à l'interface : seulement ce que la scène garde et relit.
"""
import json

from core.models.grid import (
    GRID_STEP_DEFAULT, GRID_STEPS, GRID_VALUE_MAX, Grid, GridValue, make_cells,
)
from core.models.scene import Scene
from core.project import Project


def _scene_json(project, scene):
    return json.loads(project.scenes.path_of(scene).read_text(encoding="utf-8"))


def _saved(tmp_path, scene):
    """La scène écrite puis relue par le projet, comme à la réouverture."""
    p = Project.create(tmp_path / "Game", "Game")
    p.scenes.append(scene)
    p.scenes.save_all()
    return p, _scene_json(p, scene)


# ── Les défauts ───────────────────────────────────────────────────

def test_une_grille_neuve_est_au_pas_de_seize_pixels():
    """Le pas par défaut est verrouillé : 16 px, la maille des jeux visés."""
    assert Grid().step == 16 == GRID_STEP_DEFAULT


def test_un_pas_qui_n_est_pas_une_puissance_de_deux_retombe_sur_le_defaut():
    """La GBA n'a pas d'instruction de division : le pas reste 8, 16 ou 32."""
    assert Grid(step=12).step == GRID_STEP_DEFAULT
    assert Grid.from_dict({"step": 20}).step == GRID_STEP_DEFAULT
    for step in GRID_STEPS:
        assert Grid(step=step).step == step


def test_les_cases_se_comptent_au_pas_de_la_grille():
    assert len(make_cells(240, 160, 16)) == 10              # rangées
    assert len(make_cells(240, 160, 16)[0]) == 15           # colonnes
    assert len(make_cells(240, 160, 8)[0]) == 30
    assert len(make_cells(240, 160, 32)[0]) == 8


def test_une_scene_plus_petite_qu_une_case_en_garde_une():
    assert make_cells(4, 4, 16) == [[0]]


# ── L'agrandissement, jamais le rognage ───────────────────────────

def test_une_grille_declaree_sans_cases_les_recoit_a_la_taille_de_la_scene():
    scene = Scene(name="Arena", grids=[Grid(name="Terrain", step=16)])
    scene.ensure_grid_sizes(240, 160)
    assert (scene.grid("Terrain").cols, scene.grid("Terrain").rows) == (15, 10)


def test_agrandir_la_scene_agrandit_la_grille_sans_rien_perdre():
    grid = Grid(name="Terrain", step=16, cells=[[3, 4], [5, 6]])
    grid.ensure_size(240, 160)
    assert grid.cells[0][:2] == [3, 4] and grid.cells[1][:2] == [5, 6]
    assert (grid.cols, grid.rows) == (15, 10)
    assert grid.cells[9][14] == 0


def test_reduire_la_scene_ne_detruit_pas_ce_qui_est_peint():
    """Le contrat de la carte de collision : réduire un fond ne rogne pas."""
    grid = Grid(name="Terrain", step=16)
    grid.ensure_size(240, 160)
    grid.cells[9][14] = 7
    grid.ensure_size(64, 64)
    assert (grid.cols, grid.rows) == (15, 10)
    assert grid.cells[9][14] == 7


def test_changer_le_pas_conserve_les_regions_dans_l_espace_monde():
    grid = Grid(name="Terrain", step=16, cells=[[1, 2], [3, 4]])

    cells = grid.cells_at_step(32, 32, 8)

    assert cells == [
        [1, 1, 2, 2],
        [1, 1, 2, 2],
        [3, 3, 4, 4],
        [3, 3, 4, 4],
    ]


def test_ensure_grid_sizes_ne_cree_aucune_grille():
    """C'est l'auteur qui déclare une grille, pas le chargement d'une scène."""
    scene = Scene(name="Arena")
    scene.ensure_grid_sizes(240, 160)
    assert scene.grids == []


# ── Les lectures ──────────────────────────────────────────────────

def test_la_scene_retrouve_une_grille_par_son_nom():
    scene = Scene(name="Arena", grids=[Grid(name="Terrain"), Grid(name="Danger")])
    assert scene.grid("Danger").name == "Danger"
    assert scene.grid("Absente") is None


def test_la_legende_se_lit_par_le_nom_de_la_valeur():
    grid = Grid(name="Terrain", values=[GridValue(value=3, name="EAU", color="#0000ff")])
    assert grid.value_named("EAU").value == 3
    assert grid.value_named("LAVE") is None


def test_un_dict_passe_au_constructeur_devient_une_grille():
    """L'invariant de `__post_init__`, comme pour les nœuds d'interface."""
    scene = Scene(name="Arena", grids=[{"name": "Terrain", "step": 32}])
    assert isinstance(scene.grids[0], Grid)
    assert scene.grids[0].step == 32
    assert isinstance(Grid(values=[{"value": 2, "name": "MUR"}]).values[0], GridValue)


# ── La sérialisation ──────────────────────────────────────────────

def test_une_scene_sans_grille_ne_gagne_pas_la_cle(tmp_path):
    """Même règle que le mélange et la musique : le défaut ne s'écrit pas."""
    _, written = _saved(tmp_path, Scene(name="Arena"))
    assert "grids" not in written


def test_une_grille_fait_l_aller_retour_par_le_json(tmp_path):
    grid = Grid(name="Terrain", step=16,
                values=[GridValue(value=1, name="HERBE", color="#00ff00"),
                        GridValue(value=2, name="EAU", color="#0000ff")],
                cells=[[0, 1], [2, 0]])
    _, written = _saved(tmp_path, Scene(name="Arena", grids=[grid]))

    assert written["grids"] == [{
        "name": "Terrain", "step": 16,
        "values": [{"value": 1, "name": "HERBE", "color": "#00ff00"},
                   {"value": 2, "name": "EAU", "color": "#0000ff"}],
        "cells": [[0, 1], [2, 0]],
    }]

    relue = Scene.from_dict(written).grid("Terrain")
    assert relue.step == 16
    assert [v.name for v in relue.values] == ["HERBE", "EAU"]
    # Les cases ont grandi à la scène par défaut, et gardent ce qui est peint.
    assert relue.cells[0][:2] == [0, 1] and relue.cells[1][:2] == [2, 0]


def test_les_rangees_d_une_grille_tiennent_une_ligne_chacune(tmp_path):
    """Sans cette règle, une grille au pas de 8 ajoute 600 lignes au fichier."""
    grid = Grid(name="Terrain", step=16)
    grid.ensure_size(240, 160)
    scene = Scene(name="Arena", grids=[grid])
    p = Project.create(tmp_path / "Game", "Game")
    p.scenes.append(scene)
    p.scenes.save_all()

    lignes = [L.strip() for L in p.scenes.path_of(scene).read_text(encoding="utf-8").splitlines()]
    assert lignes.count("[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],") == 9


def test_une_valeur_hors_de_l_octet_est_bornee_a_la_lecture():
    """Une case est un octet : c'est ce que le build émet."""
    grid = Grid.from_dict({"name": "Terrain", "cells": [[-4, 999]]})
    assert grid.cells == [[0, GRID_VALUE_MAX]]
    assert GridValue.from_dict({"value": 300}).value == GRID_VALUE_MAX


def test_une_entree_de_legende_qui_n_est_pas_un_objet_est_ignoree():
    assert Grid.from_dict({"values": ["EAU", 3, None]}).values == []
