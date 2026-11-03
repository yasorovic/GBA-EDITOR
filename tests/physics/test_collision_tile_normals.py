"""La normale de chaque type de tuile de collision : un seul calcul, lu par le dessin de l'éditeur."""
from __future__ import annotations

import math

import pytest

from core.models import collision_tiles as CT


def test_les_tuiles_vide_et_pleine_n_ont_pas_de_normale_propre():
    assert CT.surface_normal(CT.TILE_EMPTY) is None
    assert CT.surface_normal(CT.TILE_SOLID) is None


@pytest.mark.parametrize("tuile, attendu", [
    (CT.TILE_ONEWAY_UP, (4, 0, 0, -1)),
    (CT.TILE_ONEWAY_DOWN, (4, 8, 0, 1)),
    (CT.TILE_ONEWAY_LEFT, (0, 4, -1, 0)),
    (CT.TILE_ONEWAY_RIGHT, (8, 4, 1, 0)),
])
def test_une_face_a_sens_unique_a_sa_normale_au_centre_de_sa_face(tuile, attendu):
    assert CT.surface_normal(tuile) == attendu


@pytest.mark.parametrize("tuile", [t for t in range(CT.TILE_COUNT)
                                   if CT.kind_of(t) in (CT.KIND_FLOOR, CT.KIND_CEILING)])
def test_la_normale_d_une_pente_est_unitaire_perpendiculaire_et_sort_de_la_matiere(tuile):
    x, y, nx, ny = CT.surface_normal(tuile)
    assert math.isclose(math.hypot(nx, ny), 1.0)
    assert 0 <= x <= CT.COLLISION_TILE_SIZE and 0 <= y <= CT.COLLISION_TILE_SIZE
    y0, y1, kind = CT._GEOMETRY[tuile]
    assert math.isclose(nx * CT.COLLISION_TILE_SIZE + ny * (y1 - y0), 0.0, abs_tol=1e-9)     # perpendiculaire à la droite
    assert (ny < 0) if kind == CT.KIND_FLOOR else (ny > 0)                                    # un sol regarde en haut, un plafond en bas


def test_une_pente_de_45_degres_montante_regarde_en_haut_a_gauche():
    _x, _y, nx, ny = CT.surface_normal(CT.TILE_SLOPE_L)
    assert nx < 0 and ny < 0 and math.isclose(nx, ny)
