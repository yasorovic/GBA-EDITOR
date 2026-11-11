"""Une banque de palette est une RÉFÉRENCE : `palette:bg_bank(n)` et `palette:obj_bank(n)` la rendent, ses méthodes
lisent et changent ses couleurs. `palette:rgb(r, g, b)` construit une couleur en 0-31 par canal, la précision du GBA.
Le comportement du C (copie en RAM, reset) est jugé par la sonde native, `tests/graphics/test_palette_copy_native.py`."""
from __future__ import annotations


def _errors(body: str, **kw) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    kw.setdefault("palette_names", ["Night"])
    src = f"function on_update()\n{body}\nend\n"
    return [e.message for e in check(parse(src), BuildContext(actor_name="Sc", **kw))
            if e.level == "error"]


def _c_body(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=[], owner_kind="scene")
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Sc_scene_on_update(void) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:] if ln.strip()]


def test_une_banque_se_traduit_terme_a_terme():
    body = ('local ciel = palette:bg_bank(3)\n'
            'ciel:set_color(5, palette:rgb(31, 0, 0))\n'
            'local c = ciel:get_color(5)\n'
            'ciel:replace("Night")\n'
            'palette:obj_bank(1):reset()')
    assert _errors(body) == []
    assert _c_body(body) == [
        "int ciel = palette_bg_bank(3);",
        "palette_bank_set_color(ciel, 5, palette_rgb(31, 0, 0));",
        "int c = palette_bank_get_color(ciel, 5);",
        "palette_bank_replace(ciel, PAL_NIGHT);",
        "palette_bank_reset(palette_obj_bank(1));",
    ]


def test_une_banque_ecrite_en_clair_hors_de_0_15_est_refusee():
    assert any("palette:bg_bank(…): 16 is outside 0-15" in m for m in _errors("palette:bg_bank(16):reset()"))
    assert _errors("local n = 16\npalette:bg_bank(n):reset()") == []      # un nombre calculé n'est pas jugé


def test_une_couleur_ecrite_en_0_255_est_refusee():
    erreurs = _errors("palette:bg_bank(0):set_color(1, palette:rgb(255, 0, 0))")
    assert any("palette:rgb(…): 255 is outside 0-31, the range of a colour channel" in m for m in erreurs)


def test_une_palette_inconnue_est_refusee_par_replace():
    assert any("Nope" in m for m in _errors('palette:bg_bank(0):replace("Nope")'))


# ── Les effets de palette ────────────────────────────────────────────────────

def test_les_effets_se_traduisent_sur_une_banque_et_sur_un_pool():
    body = ('local ciel = palette:bg_bank(3)\n'
            'ciel:fade(palette:rgb(31, 31, 31), 8)\n'
            'ciel:grayscale(16)\n'
            'ciel:invert(0)\n'
            'local ecran = palette:bg_pool()\n'
            'ecran:fade(palette:rgb(0, 0, 0), 16)\n'
            'palette:obj_pool():grayscale(4)\n'
            'palette:obj_pool():invert(2)')
    assert _errors(body) == []
    assert _c_body(body) == [
        "int ciel = palette_bg_bank(3);",
        "palette_bank_fade(ciel, palette_rgb(31, 31, 31), 8);",
        "palette_bank_grayscale(ciel, 16);",
        "palette_bank_invert(ciel, 0);",
        "int ecran = palette_bg_pool();",
        "palette_pool_fade(ecran, palette_rgb(0, 0, 0), 16);",
        "palette_pool_grayscale(palette_obj_pool(), 4);",
        "palette_pool_invert(palette_obj_pool(), 2);",
    ]


def test_une_intensite_ecrite_en_clair_hors_de_0_16_est_refusee():
    erreurs = _errors("palette:bg_pool():fade(palette:rgb(0, 0, 0), 255)")
    assert any("palette_pool:fade(…): 255 is outside 0-16" in m for m in erreurs)
    erreurs = _errors("local b = palette:obj_bank(2)\nb:grayscale(17)")
    assert any("palette_bank:grayscale(…): 17 is outside 0-16" in m for m in erreurs)
    assert _errors("local n = 40\npalette:bg_pool():invert(n)") == []     # un nombre calculé n'est pas jugé


def test_un_pool_n_a_pas_les_methodes_d_une_banque():
    assert _errors("palette:bg_pool():set_color(1, 0)") != []


# ── La rotation d'une plage ──────────────────────────────────────────────────

def test_la_rotation_se_traduit_terme_a_terme():
    body = 'local n = 3\npalette:bg_bank(2):rotate(1, 4, n)'
    assert _errors(body) == []
    assert _c_body(body)[-1] == "palette_bank_rotate(palette_bg_bank(2), 1, 4, n);"


def test_une_plage_de_rotation_ecrite_en_clair_hors_de_1_15_est_refusee():
    assert any("starts at 0, outside 1-15" in m for m in _errors("palette:bg_bank(2):rotate(0, 4, 1)"))
    assert any("4 colours from index 13 go past index 15" in m
               for m in _errors("palette:bg_bank(2):rotate(13, 4, 1)"))
    assert _errors("palette:bg_bank(2):rotate(12, 4, -1)") == []
