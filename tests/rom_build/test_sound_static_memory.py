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


def test_le_taux_de_mixage_dimensionne_les_tampons_et_regle_le_mixeur():
    """Deux macros pour un seul choix : `MM_MIX_<taux>` règle le mixeur, `MM_MIXLEN_<taux>` dimensionne ses tampons. Un
    taux changé dans un seul des deux endroits compilerait, et le mixeur écrirait au-delà d'un tampon trop court."""
    from codegen.runtime_codegen.gen_main_loop import MIXING_RATE, MM_MIX_MODE, MM_MIXLEN

    assert (MM_MIX_MODE, MM_MIXLEN) == (f"MM_MIX_{MIXING_RATE}", f"MM_MIXLEN_{MIXING_RATE}")

    memoire = "\n".join(sound_memory_lines(_project(), True))
    init = "\n".join(sound_init_lines(_project()))
    assert memoire.count(MM_MIXLEN) == 2 and MM_MIX_MODE not in memoire     # les deux tampons, et rien d'autre
    assert MM_MIX_MODE in init and MM_MIXLEN not in init
