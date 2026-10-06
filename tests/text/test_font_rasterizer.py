"""Contrats purs de FontRasterizer, sans exiger une fonte installée."""

import pytest

from core.font_rasterizer import (RasterGlyph, _asset_source_names, display_coverage,
                                  resolved_pixel_fit)
from core.models.font_asset import FontAsset, FontFace


def test_raster_glyph_conserve_la_couverture_et_les_metriques():
    glyph = RasterGlyph("A", 2, 2, bytes((0, 64, 128, 255)), 5, -1, 7, "regular")

    assert glyph.coverage_at(1, 1) == 255
    assert glyph.coverage_at(-1, 0) == 0
    assert glyph.advance == 5
    assert glyph.bearing_y == 7


def test_raster_glyph_refuse_une_grille_incoherente():
    with pytest.raises(ValueError):
        RasterGlyph("A", 2, 2, b"\x00", 0, 0, 0)


def test_sortie_binary_et_coverage_respectent_le_seuil():
    assert display_coverage(127, 0, 0, raster_mode="binary", threshold=128,
                            dither_pattern="none") == 0
    assert display_coverage(128, 0, 0, raster_mode="binary", threshold=128,
                            dither_pattern="none") == 255
    assert display_coverage(87, 0, 0, raster_mode="coverage", threshold=128,
                            dither_pattern="none") == 87


def test_dither_modifie_localement_le_seuil_sans_changer_la_couverture():
    pixels = {display_coverage(128, x, y, raster_mode="dither", threshold=128,
                               dither_pattern="bayer_2x2")
              for y in range(2) for x in range(2)}

    assert pixels == {0, 255}


def test_le_poids_natif_choisit_sa_face_et_non_la_chaine_regular():
    asset = FontAsset(
        sources={"regular": ["Comic-Regular"]},
        faces=[FontFace("Comic-Regular", 400), FontFace("Comic-Bold", 700)],
    )

    assert _asset_source_names(asset, "regular", 400) == ["Comic-Regular"]
    assert _asset_source_names(asset, "regular", 700) == ["Comic-Bold"]


def test_light_italic_est_distingue_de_light():
    asset = FontAsset(faces=[FontFace("Light", 300), FontFace("LightItalic", 300, True)])

    assert _asset_source_names(asset, "regular", 300, False) == ["Light"]
    assert _asset_source_names(asset, "regular", 300, True) == ["LightItalic"]


def test_pixel_fit_auto_privilegie_la_strike_puis_la_grille_a_cinq_pixels():
    assert resolved_pixel_fit("auto", 5, has_bitmap_strike=True) == "bitmap_strike"
    assert resolved_pixel_fit("auto", 5, has_bitmap_strike=False) == "grid_fit"
    assert resolved_pixel_fit("auto", 8, has_bitmap_strike=False) == "native"


def test_pixel_fit_strike_absente_retombe_sur_une_recette_fiable():
    assert resolved_pixel_fit("bitmap_strike", 5, has_bitmap_strike=False) == "native"
