"""`hw_layer_z` — l'ordre de composition du canvas doit REPRODUIRE celui du
hardware GBA, jamais un empilement choisi pour le confort de l'édition.

Avant ce correctif, un acteur (OBJ) avait un zValue fixe (10) et une zone
d'interface un zValue fixe (120) : l'acteur passait donc TOUJOURS sous
l'interface dans le canvas, quelle que soit la priorité réelle — le contraire
de ce que montre la ROM dès que l'UI vit sur un BG ≠ 0 (cf. `_gen_scene_init`,
« Priorité GBA = bg_slot directement », et la règle documentée du hardware :
à priorité ÉGALE, l'OBJ passe devant le BG).
"""
from __future__ import annotations

import sys

import pytest


def _z():
    sys.path.insert(0, "editor")
    from ui.scene_manager.canvas.canvas_items import hw_layer_z
    return hw_layer_z


def test_priorite_0_est_devant_priorite_3():
    z = _z()
    assert z(0, is_obj=False) > z(3, is_obj=False)
    assert z(0, is_obj=True) > z(3, is_obj=True)


def test_a_priorite_egale_obj_passe_devant_bg():
    z = _z()
    for p in range(4):
        assert z(p, is_obj=True) > z(p, is_obj=False)


def test_obj_prioritaire_reste_derriere_bg_plus_prioritaire():
    """Un acteur de priorité 2 (arrière-plan) ne doit jamais passer devant un
    BG de priorité 0 (premier plan) — l'échelle est UNE seule, pas deux
    échelles indépendantes qui se recouperaient mal."""
    z = _z()
    assert z(2, is_obj=True) < z(0, is_obj=False)


def test_le_cas_reel_de_la_demo_fonts_and_texts():
    """Selector (Actor.priority par défaut = 0) doit passer DEVANT
    Selection_box (panneau dont le nœud Interface est sur BG1) — c'est le bug
    exact signalé en relisant le canvas contre la ROM compilée."""
    z = _z()
    z_panel = z(1, is_obj=False)     # Selection_box, nœud Interface sur BG1
    z_selector = z(0, is_obj=True)   # Selector, priority par défaut
    assert z_selector > z_panel


def test_bornes_hors_plage_sont_pincees():
    z = _z()
    assert z(-1, is_obj=False) == z(0, is_obj=False)
    assert z(9, is_obj=True) == z(3, is_obj=True)
