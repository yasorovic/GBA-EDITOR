"""Les deux lectures de la jauge ROM gardent les mêmes données, mais pas la
même échelle : capacité de cartouche ou total des consommateurs."""

from ui.common.rom_budget_bar import _Gauge, RomBudgetBar


def test_gauge_fill_mode_leaves_unused_cartridge_empty(qapp):
    gauge = _Gauge()
    gauge.resize(100, 14)
    gauge.set_data({"Audio": 25, "Sprites": 25}, rom_bytes=50, cartridge_bytes=100)

    assert gauge._segment_at(10) == ("Audio", 25)
    assert gauge._segment_at(35) == ("Sprites", 25)
    assert gauge._segment_at(75) is None


def test_gauge_breakdown_mode_fills_whole_width(qapp):
    gauge = _Gauge()
    gauge.resize(100, 14)
    gauge.set_data({"Audio": 25, "Sprites": 25}, rom_bytes=50, cartridge_bytes=100)
    gauge.set_mode("breakdown")

    assert gauge._segment_at(25) == ("Audio", 25)
    assert gauge._segment_at(75) == ("Sprites", 25)
    assert gauge._segment_at(99) == ("Sprites", 25)


def test_rom_bar_starts_in_fill_mode_and_switches_view(qapp):
    bar = RomBudgetBar()

    assert bar._mode == "fill"
    assert bar._mode_button.text().endswith("▾")
    bar._set_mode("breakdown")
    assert bar._gauge._mode == "breakdown"
