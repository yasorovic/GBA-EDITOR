"""La position du curseur se lit en pixels ou en tuiles, d'un clic, dans tous les canvas."""
from __future__ import annotations

import pytest

from core import interface_preferences


@pytest.fixture
def unit(qapp, monkeypatch):
    from ui.common import cursor_unit as module
    monkeypatch.setattr(interface_preferences, "_save", lambda: None)
    monkeypatch.setattr(module._UNIT, "_unit", "px")
    return module._UNIT


def test_les_pixels_se_convertissent_en_tuiles_de_8(unit):
    assert unit.text(17, 40) == "x:17 y:40"
    unit.toggle()
    assert unit.text(17, 40) == "tile 2,5"
    unit.toggle()
    assert unit.text(17, 40) == "x:17 y:40"


def test_hors_du_canvas_le_texte_dit_rien(unit):
    assert unit.text(None, None) == "x:— y:—"
    unit.toggle()
    assert unit.text(None, None) == "tile —"


def test_un_clic_bascule_tous_les_affichages(unit):
    from PyQt6.QtGui import QFont
    from ui.common.cursor_unit import CursorUnitButton
    first, second = CursorUnitButton(QFont()), CursorUnitButton(QFont())
    first.set_position(16, 8)
    second.set_position(24, 0)

    first.click()

    assert first.text() == "tile 2,1" and second.text() == "tile 3,0"
