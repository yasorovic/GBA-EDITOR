"""Le cuiseur : un fond tuilé 4bpp sort en PNG indexé « par banques » et se relit à l'identique, banques comprises."""
from __future__ import annotations

from PIL import Image

from core.bg_bake import render_indexed, render_rgba, save_indexed_png
from core.bg_import import encode_background, render_bg_preview
from core.blank_assets import _build


def _painted():
    """Un fond vierge de deux palettes, peint dans les DEUX banques, avec une surcharge de palette."""
    ba = _build(None, "background", "Background")
    ba.palettes[0][1:4] = [0x7FFF, 0x001F, 0x03E0]
    ba.added_palettes = ["P0"]                       # la peinture ne se pose que sur des palettes AJOUTÉES (références)
    ba.add_palette_ref("P1", [0, 0x7C00, 0x7FE0, 0x4210] + [0] * 12)
    ba.tile_paint = {(0, 0): (1, 0), (1, 0): (2, 0), (2, 0): (1, 1), (3, 0): (3, 1), (4, 0): (0, 0)}
    ba.tileset.append("0" * 63 + "2")                            # une tuile de l'image, repeinte en banque 1
    ba.tilemap[5] = (1 & 0x3FF)
    ba.tile_palette_overrides = {(5, 0): 1}
    return ba


def _reread(tmp_path, ba):
    path = tmp_path / "baked.png"
    save_indexed_png(ba, path)
    encoded = encode_background(path)
    again = render_bg_preview({"tiles_w": encoded["tiles_w"], "tiles_h": encoded["tiles_h"],
                               "tileset": encoded["tileset"], "palettes": encoded["palettes"],
                               "tilemap": encoded["tilemap"], "bpp": 4})
    return path, encoded, again


def test_the_baked_png_is_indexed_with_one_palette_entry_per_bank_color(tmp_path):
    ba = _painted()
    path, _encoded, _again = _reread(tmp_path, ba)

    image = Image.open(path)

    assert image.mode == "P" and image.size == (240, 160)
    palette = image.getpalette()
    assert tuple(palette[16 * 3 + 3:16 * 3 + 6]) == (0, 0, 248)      # banque 1, couleur 1 (0x7C00 = bleu)
    assert image.info.get("transparency") is not None


def test_a_baked_background_reads_back_pixel_for_pixel_and_keeps_its_banks(tmp_path):
    ba = _painted()
    before = render_rgba(ba)

    _path, encoded, after = _reread(tmp_path, ba)

    assert before.tobytes() == after.tobytes()
    assert len(encoded["palettes"]) == 2                              # les deux banques, la 2ᵉ comprise
    assert encoded["palettes"][1][1:4] == ba.palettes[1][1:4]


def test_a_declared_bank_that_nothing_paints_survives_the_file(tmp_path):
    ba = _painted()
    ba.tile_paint = {(0, 0): (1, 0)}                                  # plus rien en banque 1
    ba.tile_palette_overrides = {}

    _path, encoded, _after = _reread(tmp_path, ba)

    assert len(encoded["palettes"]) == 2


def test_only_a_tiled_4bpp_background_can_be_baked(tmp_path):
    import pytest
    ba = _painted()
    ba.bpp = 8
    with pytest.raises(ValueError):
        render_indexed(ba)


def test_a_plain_indexed_png_with_a_full_256_entry_palette_still_gives_one_bank(tmp_path):
    image = Image.new("P", (16, 16), 0)
    image.putpalette([c for i in range(256) for c in (i, 255 - i, 0)])
    image.putpixel((3, 3), 5)
    path = tmp_path / "plain.png"
    image.save(path)

    assert len(encode_background(path)["palettes"]) == 1


def test_an_indexed_png_whose_tile_straddles_two_banks_falls_back_to_the_deduced_packing(tmp_path):
    image = Image.new("P", (8, 8), 0)
    image.putpalette([c for i in range(256) for c in (i, 0, 255 - i)])
    image.putpixel((0, 0), 1)                                         # banque 0
    image.putpixel((1, 0), 17)                                        # banque 1, dans la MÊME tuile
    path = tmp_path / "straddle.png"
    image.save(path)

    encoded = encode_background(path)

    assert encoded["diagnostics"].get("src_indexed") is not True      # pas une lecture par banques : packing déduit


def test_a_baked_png_dropped_into_another_project_is_imported_as_4bpp_with_its_banks(tmp_path):
    from core.bg_import import detect_import_mode, encode_by_mode
    ba = _painted()
    path = tmp_path / "baked.png"
    save_indexed_png(ba, path)

    detected = detect_import_mode(path)
    encoded = encode_by_mode(path, detected["token"])

    assert detected["indexed"] and detected["token"] == "tiled4" and detected["warning"] is None
    assert len(encoded["palettes"]) == 2 and encoded["bpp"] == 4


def test_a_sixteen_bank_png_is_still_imported_as_4bpp_with_sixteen_banks(tmp_path):
    from core.bg_import import detect_import_mode, encode_by_mode
    ba = _build(None, "background", "Background")
    ba.added_palettes = ["P0"]
    for bank in range(1, 16):
        ba.add_palette_ref(f"P{bank}", [0] + [(bank * 2 + k) & 0x7FFF for k in range(1, 16)])
    ba.palettes[0][1:16] = list(range(1, 16))
    ba.tile_paint = {(bank, 0): (1 + bank % 15, bank) for bank in range(16)}
    path = tmp_path / "full.png"
    save_indexed_png(ba, path)

    detected = detect_import_mode(path)
    encoded = encode_by_mode(path, detected["token"])

    assert detected["token"] == "tiled4" and len(encoded["palettes"]) == 16
    assert render_rgba(ba).tobytes() == render_bg_preview({
        "tiles_w": encoded["tiles_w"], "tiles_h": encoded["tiles_h"], "tileset": encoded["tileset"],
        "palettes": encoded["palettes"], "tilemap": encoded["tilemap"], "bpp": 4}).tobytes()
