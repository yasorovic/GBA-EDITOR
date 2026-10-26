"""Les temps d'accès de la ROM (`REG_WAITCNT`) : deux préréglages, des champs avancés, la SRAM toujours à 8 cycles.

Le moteur est compilé en Thumb et exécuté depuis la ROM : après le BIOS (ROM à 4/2, sans prefetch) il va presque deux
fois moins vite. La valeur du registre est calculée à la génération (`codegen/memory_timing.py`) et posée par
`memory_timing_init(valeur)` au début de `main()`."""
from __future__ import annotations

import re
from pathlib import Path

from codegen import memory_timing as mt

RUNTIME = Path(__file__).resolve().parents[2] / "runtime" / "include" / "gba_engine.h"


def test_le_prereglage_rapide_est_le_3_1_avec_prefetch_des_jeux_du_commerce():
    # WAITCNT : bits 0-1 SRAM (3 = 8 cycles) ; bits 2-3 WS0 N (01 = 3) ; bit 4 WS0 S (1 = 1) ; bit 14 prefetch.
    assert mt.waitcnt_value(*mt.PRESETS["fast"], cartridge_mib=4) == 0b11 | (0b01 << 2) | (1 << 4) | (1 << 14)


def test_le_prereglage_compatible_est_celui_du_bios_sans_prefetch():
    assert mt.waitcnt_value(*mt.PRESETS["compatible"], cartridge_mib=4) == 0b11   # N=4 (00), S=2 (0), pas de prefetch


def test_la_sram_reste_a_8_cycles_quel_que_soit_le_reglage():
    for first in mt.FIRST_ACCESS:
        for second in mt.second_choices(first):
            for prefetch in (False, True):
                assert mt.waitcnt_value(first, second, prefetch, 4) & 0b11 == 0b11


def test_au_dela_de_16_mio_ws1_reprend_ws0():
    petit = mt.waitcnt_value(3, 1, True, 16)
    grand = mt.waitcnt_value(3, 1, True, 32)
    assert petit & 0x00E0 == 0                       # ≤ 16 Mio : WS1 n'est pas touché
    assert (grand >> 5) & 0b11 == 0b01               # WS1 N = 3
    assert (grand >> 7) & 1 == 1                     # WS1 S = 1
    assert grand & ~0x00E0 == petit


def test_ws1_n_offre_pas_2_cycles_pour_s_alors_il_prend_4():
    assert (mt.waitcnt_value(4, 2, False, 32) >> 7) & 1 == 0     # code 0 = 4 cycles, plus lent donc sûr


def test_les_combinaisons_impossibles_sont_refusees():
    assert mt.is_valid(3, 1) and mt.is_valid(4, 2) and mt.is_valid(8, 2)
    assert not mt.is_valid(2, 2) and not mt.is_valid(3, 3) and not mt.is_valid(5, 1)
    assert mt.second_choices(2) == (1,)


def test_un_projet_abime_retombe_sur_le_prereglage_rapide():
    assert mt.normalised(2, 2, True) == mt.PRESETS["fast"]
    assert mt.normalised("x", None, True) == mt.PRESETS["fast"]
    assert mt.normalised(8, 1, False) == (8, 1, False)


def test_preset_of_reconnait_les_deux_prereglages():
    assert mt.preset_of(3, 1, True) == "fast"
    assert mt.preset_of(4, 2, False) == "compatible"
    assert mt.preset_of(3, 1, False) == mt.CUSTOM


def test_le_moteur_ecrit_seulement_sram_ws0_ws1_et_prefetch():
    texte = RUNTIME.read_text(encoding="utf-8")
    assert "#define WAITCNT_WRITE_MASK 0x40FF" in texte
    assert "REG_WAITCNT = (REG_WAITCNT & ~WAITCNT_WRITE_MASK) | waitcnt;" in texte
    assert mt.WRITE_MASK == 0x40FF
    assert "sram_init" not in texte


def test_toute_valeur_calculee_tient_dans_le_masque_d_ecriture():
    for mib in (4, 32):
        for first in mt.FIRST_ACCESS:
            for second in mt.second_choices(first):
                for prefetch in (False, True):
                    assert mt.waitcnt_value(first, second, prefetch, mib) & ~mt.WRITE_MASK == 0


def test_main_pose_les_temps_d_acces_calcules_avant_toute_lecture():
    from codegen.runtime_codegen import gen_main_loop
    source = Path(gen_main_loop.__file__).read_text(encoding="utf-8")
    assert "memory_timing_init(0x{waitcnt_value(" in source
    assert re.search(r"memory_timing_init\(0x\{", source)


def test_les_reglages_survivent_a_l_enregistrement_et_un_ancien_projet_prend_le_rapide(tmp_path):
    from core.project import Project
    p = Project(tmp_path)
    assert (p.settings.rom_wait_first, p.settings.rom_wait_second, p.settings.rom_prefetch) == (3, 1, True)
    p.settings.rom_wait_first, p.settings.rom_wait_second, p.settings.rom_prefetch = 8, 2, False
    p.save_settings()
    q = Project(tmp_path)
    q.load_settings()
    assert (q.settings.rom_wait_first, q.settings.rom_wait_second, q.settings.rom_prefetch) == (8, 2, False)
    # Un projet d'avant ce réglage n'a pas les clés : il prend le préréglage rapide.
    import json
    from core.project import find_manifest
    manifest = find_manifest(tmp_path)
    d = json.loads(manifest.read_text(encoding="utf-8"))
    for k in ("rom_wait_first", "rom_wait_second", "rom_prefetch"):
        d.pop(k, None)
    manifest.write_text(json.dumps(d), encoding="utf-8")
    r = Project(tmp_path)
    r.load_settings()
    assert (r.settings.rom_wait_first, r.settings.rom_wait_second, r.settings.rom_prefetch) == (3, 1, True)
