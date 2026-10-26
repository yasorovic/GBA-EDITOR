"""Le contrôle de l'EWRAM après le lien : la marge que le build garde libre pour le tas (maxmod) et pour ce que le jeu
ajoutera. La capacité du pool ne se calcule pas de la RAM libre (cf. `oam_alloc.OBJECT_CAPACITY`) : le build vérifie."""
from __future__ import annotations

from codegen.rom_report import EWRAM_MARGIN, RomReport, format_report


def _rapport(ewram: int) -> RomReport:
    return RomReport(rom_bytes=1024 * 100, cartridge_bytes=4 * 1024 * 1024, categories={}, ewram_bytes=ewram)


def test_la_memoire_libre_est_ce_que_les_donnees_statiques_laissent():
    assert _rapport(60 * 1024).ewram_free == 196 * 1024


def test_un_jeu_a_l_aise_n_est_pas_serre():
    assert not _rapport(72 * 1024).ewram_tight


def test_sous_la_marge_l_ewram_est_serree():
    assert _rapport(256 * 1024 - EWRAM_MARGIN + 1).ewram_tight
    assert not _rapport(256 * 1024 - EWRAM_MARGIN).ewram_tight


def test_une_mesure_absente_n_alerte_pas():
    assert not _rapport(0).ewram_tight


def test_le_journal_donne_l_ewram_utilisee_et_libre():
    lignes = format_report(_rapport(60 * 1024))
    assert any(l.startswith("  EWRAM — 60.0 KiB / 256 KiB, 196.0 KiB free") for l in lignes)
    assert not any("tight" in l for l in lignes)


def test_le_journal_dit_quand_l_ewram_est_serree():
    lignes = format_report(_rapport(250 * 1024))
    assert any("EWRAM is tight" in l and "16 KiB" in l for l in lignes)
