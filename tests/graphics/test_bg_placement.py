"""Géométrie de l'image posée dans le canvas d'un fond : déplacer, mettre à l'échelle, et les trois aides au placement."""
from __future__ import annotations

from ui.background_editor.bg_placement_geometry import (
    fill_rect, fit_rect, move_rect, normalize, one_to_one_rect, rect_of, scale_rect)


# ── Valeurs de sidecar ────────────────────────────────────────────────────────

def test_sans_valeur_l_image_est_a_la_taille_du_fichier_en_0_0():
    assert rect_of(None, None, None, (64, 48)) == (0, 0, 64, 48)


def test_les_valeurs_du_sidecar_donnent_le_rectangle_pose():
    assert rect_of((32, 32), (-8, 4), (128, 96), (64, 48)) == (-8, 4, 128, 96)


def test_normaliser_n_ecrit_que_ce_qui_differe_du_defaut():
    assert normalize((64, 48), (0, 0, 64, 48), (64, 48)) == (None, None, None)
    assert normalize((32, 32), (0, 0, 64, 48), (64, 48)) == ((32, 32), None, None)
    assert normalize((32, 32), (-8, 4, 128, 96), (64, 48)) == ((32, 32), (-8, 4), (128, 96))


# ── Déplacer ──────────────────────────────────────────────────────────────────

def test_deplacer_ajoute_le_decalage():
    assert move_rect((10, 10, 50, 40), 5, -3, False) == (15, 7, 50, 40)


def test_deplacer_avec_ctrl_accroche_le_coin_a_la_grille():
    assert move_rect((10, 10, 50, 40), 3, 3, True) == (16, 16, 50, 40)


def test_deplacer_ne_borne_pas_l_image_au_canvas():
    assert move_rect((0, 0, 50, 40), -500, 900, False) == (-500, 900, 50, 40)


# ── Mettre à l'échelle ────────────────────────────────────────────────────────

def test_tirer_le_coin_bas_droit_garde_le_coin_haut_gauche():
    assert scale_rect((10, 10, 100, 50), "se", 20, -10, False, False) == (10, 10, 120, 40)


def test_tirer_le_bord_gauche_garde_le_bord_droit():
    # Vers l'extérieur (dx négatif) : l'image grandit vers la gauche, son bord droit ne bouge pas.
    assert scale_rect((10, 10, 100, 50), "w", -20, 0, False, False) == (-10, 10, 120, 50)
    assert scale_rect((10, 10, 100, 50), "w", 30, 0, False, False) == (40, 10, 70, 50)


def test_tirer_le_bord_haut_garde_le_bord_bas():
    assert scale_rect((10, 10, 100, 50), "n", 0, -10, False, False) == (10, 0, 100, 60)


def test_maj_a_un_coin_garde_les_proportions():
    x, y, w, h = scale_rect((0, 0, 100, 50), "se", 50, 0, True, False)
    assert (x, y) == (0, 0) and (w, h) == (150, 75)


def test_maj_a_un_coin_haut_gauche_garde_le_coin_bas_droit():
    x, y, w, h = scale_rect((100, 100, 100, 50), "nw", -100, 0, True, False)
    assert (x + w, y + h) == (200, 150) and w / h == 2.0


def test_maj_a_un_bord_fait_suivre_l_autre_dimension_centree():
    x, y, w, h = scale_rect((0, 0, 100, 50), "e", 100, 0, True, False)
    assert (w, h) == (200, 100) and y == -25                       # la hauteur grandit autour du milieu


def test_ctrl_accroche_le_cote_tire_a_la_grille():
    x, y, w, h = scale_rect((0, 0, 100, 50), "se", 3, 3, False, True)
    assert (x + w, y + h) == (104, 56)


def test_une_image_ne_descend_pas_sous_un_pixel_ni_ne_se_retourne():
    assert scale_rect((10, 10, 100, 50), "se", -500, -500, False, False) == (10, 10, 1, 1)
    assert scale_rect((10, 10, 100, 50), "w", 500, 0, False, False) == (109, 10, 1, 50)


# ── Les aides au placement ────────────────────────────────────────────────────

def test_ajuster_met_toute_l_image_dans_le_canvas_centree():
    assert fit_rect((1000, 500), (240, 160)) == (0, 20, 240, 120)


def test_remplir_couvre_le_canvas_et_rogne_le_surplus():
    x, y, w, h = fill_rect((1000, 500), (240, 160))
    assert (w, h) == (320, 160) and x == -40 and y == 0


def test_un_pour_un_garde_la_taille_du_fichier_centree():
    assert one_to_one_rect((100, 60), (240, 160)) == (70, 50, 100, 60)
