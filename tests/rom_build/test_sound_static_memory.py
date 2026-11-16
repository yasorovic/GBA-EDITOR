"""Les tampons de maxmod sont dimensionnés au build, sans tas."""

from types import SimpleNamespace

from codegen.runtime_codegen.gen_main_loop import sound_init_lines, sound_memory_lines


def _project(channels=8):
    return SimpleNamespace(settings=SimpleNamespace(sound_channels=channels))


def test_les_tampons_sont_statiques_et_dimensionnes_par_canal():
    code = "\n".join(sound_memory_lines(_project(12), True))

    assert "g_mm_module_channels[MM_SIZEOF_MODCH * 12 / 4] EWRAM_BSS" in code
    assert "g_mm_active_channels[MM_SIZEOF_ACTCH * 12 / 4] EWRAM_BSS" in code
    assert "g_mm_mixing_channels[MM_SIZEOF_MIXCH * 12 / 4] EWRAM_BSS" in code
    assert "g_mm_wave_memory[MM_MIXLEN_16KHZ / 4] EWRAM_BSS" in code
    assert "g_mm_mixing_memory[MM_MIXLEN_16KHZ / 4];" in code


def test_l_initialisation_utilise_les_tampons_sans_mm_init_default():
    code = "\n".join(sound_init_lines(_project()))

    assert "MM_MIX_16KHZ, 8, 8" in code
    assert "mmInit(&mm_system);" in code
    assert "mmInitDefault" not in code


def test_un_projet_sans_son_ne_reserve_rien():
    assert sound_memory_lines(_project(), False) == []
