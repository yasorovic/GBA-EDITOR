"""Raccord FontAsset → tables GBA : pas de planche intermédiaire sur disque."""

from codegen.font_build import build_font_asset
from codegen.font_emit import TEXT_SURF_TILES, encode_font, font_palette, font_vram_tiles
from core.font_rasterizer import RasterGlyph
from core.models.font import Font, Glyph
from core.models.font_asset import FontAsset


def test_un_font_asset_rasterise_alimente_encodage_et_budget(monkeypatch):
    glyph = RasterGlyph("A", 3, 5, bytes([255]) * 15, 4, 0, 5, "source")
    monkeypatch.setattr("codegen.font_build.rasterize_asset_glyph",
                        lambda _project, _asset, char, faces=None: glyph if char == "A"
                        else (_ for _ in ()).throw(RuntimeError("absent")))

    font = build_font_asset(object(), FontAsset(
        name="Dialogue", sources={"regular": ["source"]},
        pixel_height=8, line_height=8), {"A"})
    encoded = encode_font(font)

    assert encoded["codepoints"] == [ord("A")]
    assert encoded["n_tiles"] == 1
    # Chasse 4 px : le même Font temporaire choisit la composition et son
    # budget est bien celui de la surface, pas celui d'une planche source.
    assert font_vram_tiles(font, {ord("A")}) == TEXT_SURF_TILES


def test_bitmap_materialise_conserve_sa_couleur_et_l_index_d_encre():
    """Le chemin FontAsset ne doit pas transformer une planche indexée en
    rampe grise : les banques de scène attendent l'encre au slot 1."""
    glyph = RasterGlyph(
        "A", 2, 1, bytes((255, 0)), 2, 0, 1, "bitmap",
        # Noir, puis une couleur de fond qui est transparente via coverage.
        colors=bytes((8, 16, 8, 224, 248, 207)),
    )
    font = Font(name="Bitmap", cell_w=8, cell_h=8, line_height=8,
                glyphs=[Glyph(char="A", w=2, h=8, advance=2)])
    font.raster_glyphs = {"A": glyph}
    font.raster_mode = "binary"
    font.coverage_threshold = 128
    font.dither_pattern = "none"

    encoded = encode_font(font)

    assert encoded["palette"][1] != 0
    assert set((word >> (4 * bit)) & 0xF
               for word in encoded["tiles"] for bit in range(8)) == {0, 1}
    assert font_palette(font, None) == encoded["palette"]
