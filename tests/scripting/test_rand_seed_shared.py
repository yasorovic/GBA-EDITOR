"""La graine de `math_rand` est UNE pour le jeu : définie dans main.c, `extern` dans le header.

`static` dans le header donnait à chaque unité de script sa propre copie, donc la
même suite de tirages partout."""
import re

from core.app_paths import RUNTIME_DIR, APP_DIR


def test_seed_is_extern_in_header():
    header = (RUNTIME_DIR / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    assert re.search(r"^extern u32 _g_rand_seed;", header, re.M)
    assert not re.search(r"^\s*static\s+u32\s+\w*seed", header, re.M)


def test_seed_is_defined_in_main_c_generator():
    src = (APP_DIR / "editor" / "codegen" / "runtime_codegen" / "main_gen.py").read_text(encoding="utf-8")
    assert '"u32   _g_rand_seed' in src


def test_seed_is_stirred_once_at_first_button_press():
    src = (APP_DIR / "editor" / "codegen" / "runtime_codegen" / "main_gen.py").read_text(encoding="utf-8")
    assert "u32   _g_rand_ticks" in src and "int   _g_rand_seeded" in src
    assert "if(!_g_rand_seeded && _g_keys_pressed)" in src
