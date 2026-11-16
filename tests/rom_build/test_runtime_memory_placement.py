"""Placement des grosses réserves froides du runtime hors de l'IWRAM."""

from pathlib import Path


MOTEUR = (Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h")


def test_les_tampons_de_recomposition_sont_en_ewram():
    source = MOTEUR.read_text(encoding="utf-8")

    assert "g_mat_cp[TEXT_MAT_MAX] EWRAM_BSS;" in source
    assert "g_mat_ev[TEXT_EV_MAX] EWRAM_BSS;" in source
    assert "g_mat_map[TEXT_MAT_MAX + 1] EWRAM_BSS;" in source
    assert "g_ui_img_under[UI_IMAGE_MAX][UI_IMAGE_UNDER_MAX] EWRAM_BSS;" in source
