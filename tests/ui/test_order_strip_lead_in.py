"""L'amorce de tempo d'un module converti : un ordre 0 muet que la bande réduit, et que les sections évitent.

`tools/convert_uge_to_mod.py` pose le tempo dans un premier ordre sans note et fait reboucler le fichier à l'ordre 1.
La reconnaissance est stricte (ordre 0 muet ET restart qui le saute) ; ce qu'elle change est de la présentation :
la table d'ordres reste brute, les numéros restent ceux de la ROM.
"""
from __future__ import annotations

import pytest

from core.engine_emulation.module_model import Cell, Module, lead_in_orders
from core.models.audio import Music
from ui.sound_mixer.order_strip import OrderStrip
from ui.sound_mixer.section_table import SectionTable


def _module(*, restart: int, first_has_note: bool = False) -> Module:
    silent = [[Cell() for _ in range(4)] for _ in range(4)]
    played = [[Cell() for _ in range(4)] for _ in range(4)]
    played[0][0] = Cell(note=60, instrument=1)
    first = played if first_has_note else silent
    return Module(order=[0, 1, 2, 3], restart=restart, patterns=[first, played, played, played])


def test_amorce_reconnue():
    assert lead_in_orders(_module(restart=1)) == 1


def test_ordre_zero_joue_pas_une_amorce():
    assert lead_in_orders(_module(restart=1, first_has_note=True)) == 0


def test_restart_zero_pas_une_amorce():
    """Un ordre 0 muet que le morceau rejoue à chaque boucle est un vrai silence voulu."""
    assert lead_in_orders(_module(restart=0)) == 0


def test_sans_ordre_ni_pattern():
    assert lead_in_orders(Module()) == 0


@pytest.fixture
def strip(qapp):
    widget = OrderStrip()
    widget.resize(400, 80)
    widget.set_orders([0, 1, 2, 3], lead_in=1)
    return widget


def test_case_d_amorce_reduite_et_ordres_alignes(strip):
    assert strip._cell_rect(0).width() < strip._cell_rect(1).width()
    assert strip._cell_rect(3).right() == pytest.approx(strip.width() - 1)
    for order in range(4):                                  # le clic retombe sur la case dessinée
        assert strip._index_at(strip._cell_rect(order).center().x()) == order
    assert strip._boundary_at(strip._x(1)) == 1


def test_amorce_ni_reperable_ni_selectionnable(strip):
    assert strip._cue_position_at(strip._cell_rect(0).center().x()) is None
    assert strip._cue_position_at(strip._cell_rect(1).center().x()) == 1


def test_bande_sans_amorce_inchangee(qapp):
    widget = OrderStrip()
    widget.resize(400, 80)
    widget.set_orders([0, 1, 2, 3])
    assert widget._cell_rect(0).width() == pytest.approx(widget._cell_rect(1).width())


def test_amorce_se_dessine(strip):
    assert not strip.grab().isNull()


def test_nouvelle_section_commence_apres_l_amorce(qapp):
    music = Music(name="m", asset="assets/music/m.mod")
    table = SectionTable()
    table.load(music, 4, lead_in=1)
    assert table._default_range() == (1, 4)
