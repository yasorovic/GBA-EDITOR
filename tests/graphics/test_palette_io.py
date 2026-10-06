"""Formats externes de palette : importés dans le domaine, pas dans l'UI."""
from __future__ import annotations

from PIL import Image

from core.palette_io import import_palette, parse_palette_file


def test_parse_gpl_and_hex_files(tmp_path):
    gpl = tmp_path / "colors.gpl"
    gpl.write_text("GIMP Palette\nName: Test\n# note\n255 0 0 red\n0 255 0 green\n")
    hex_file = tmp_path / "colors.hex"
    hex_file.write_text("#112233 #445566\n")

    assert parse_palette_file(gpl) == [(255, 0, 0), (0, 255, 0)]
    assert parse_palette_file(hex_file) == [(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)]


def test_import_png_extracts_opaque_colors_into_a_palette(tmp_path):
    path = tmp_path / "pixels.png"
    image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.save(path)

    bank = import_palette(path)

    assert bank.name == "pixels"
    assert bank.size == 16
    assert bank.colors[0] == 0
    assert len(bank.colors) == 16
    assert any(color != 0 for color in bank.colors[1:])
