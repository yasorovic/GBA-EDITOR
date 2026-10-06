"""Poignées de recadrage / redimensionnement du Background Editor (item Qt).

La géométrie pure est testée dans tests/graphics/test_bg_prepare.py ; ici, ce que l'item en
fait : quelles poignées il offre, et quel bord reste en place quand on tire.
"""
from __future__ import annotations

from ui.background_editor.bg_prepare_overlay import PrepareOverlay


def test_poignees_de_redimensionnement_sur_les_huit_points(qapp):
    ov = PrepareOverlay()
    ov.start_resize((100, 50))
    assert set(ov._handles()) == {"nw", "n", "ne", "w", "e", "sw", "s", "se"}


def test_tirer_la_gauche_garde_le_bord_droit_fixe(qapp):
    ov = PrepareOverlay()
    ov.start_resize((100, 50))
    assert ov.begin(0, 25)                     # poignée « w »
    ov.drag(-30, 25, False, False)             # vers l'extérieur
    assert ov._rect == (-30, 0, 100, 50) and ov.size() == (130, 50)


def test_tirer_le_haut_garde_le_bord_bas_fixe(qapp):
    ov = PrepareOverlay()
    ov.start_resize((100, 50))
    assert ov.begin(50, 0)                     # poignée « n »
    ov.drag(50, -20, False, False)
    assert ov._rect == (0, -20, 100, 50) and ov.size() == (100, 70)
