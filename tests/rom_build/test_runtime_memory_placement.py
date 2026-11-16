"""Placement des réserves mesurées du runtime hors de l'IWRAM."""

from pathlib import Path


MOTEUR = (Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h")


def test_les_tampons_de_recomposition_sont_en_ewram():
    source = MOTEUR.read_text(encoding="utf-8")

    assert "g_mat_cp[TEXT_MAT_MAX] EWRAM_BSS;" in source
    assert "g_mat_ev[TEXT_EV_MAX] EWRAM_BSS;" in source
    assert "g_mat_map[TEXT_MAT_MAX + 1] EWRAM_BSS;" in source
    assert "g_ui_img_under[UI_IMAGE_MAX][UI_IMAGE_UNDER_MAX] EWRAM_BSS;" in source


def test_les_etats_texte_et_ui_mesures_sont_en_ewram():
    source = MOTEUR.read_text(encoding="utf-8")

    for symbol in ("g_cap_x", "g_cap_y", "g_cap_gi", "g_cap_fx", "g_cap_i", "g_cap_ink"):
        assert f"{symbol}[TEXT_ANIM_MAX] EWRAM_BSS;" in source
    assert "g_region_surf[TEXT_REGION_SURF_MAX] EWRAM_BSS;" in source
    assert "g_region_fill[TEXT_REGION_FILL_MAX] EWRAM_BSS;" in source
    assert "g_reads[TEXT_READ_MAX] EWRAM_BSS;" in source
    assert "g_region_layer[UI_REGION_MAX] EWRAM_BSS;" in source
    assert "g_region_active[UI_REGION_MAX] EWRAM_BSS;" in source
    assert "g_ui_img[UI_IMAGE_MAX] EWRAM_BSS;" in source
    assert "g_image_layer[UI_IMAGE_MAX] EWRAM_BSS;" in source
    assert "g_image_active[UI_IMAGE_MAX] EWRAM_BSS;" in source
