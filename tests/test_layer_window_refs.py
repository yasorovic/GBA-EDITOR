"""Un fond (layer) et une région de window sont des RÉFÉRENCES — ROADMAP v0.16, étape (c)/(d).

`layer:get(n)` rend le fond `n` (numéroté par le matériel, de 0 à 3) ;
`window:get("Nom")` rend une région du pochoir (nommée). Plus aucune fonction de module ne prend
« un fond » ou « une région » en premier argument : `layer.show(n, on)`, `layer.set_priority`,
`tilemap.set(n, …)`, `window.show(nom, on)`… sont devenus des verbes, des propriétés et des méthodes
de leur type. Les types ne portent pas le nom de leur module (`background_layer`, `window_region`) :
sinon `layer.priority` aurait deux lectures.
"""

from __future__ import annotations

from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def _errors(body: str, **kw) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    kw.setdefault("window_names", ["Panneau"])
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


# ── Un fond ─────────────────────────────────────────────────────────────────

def test_un_fond_se_traduit_terme_a_terme():
    body = ('layer:get(0):hide()\n'
            'layer:get(0):show()\n'
            'layer:get(1).priority = 0\n'
            'local p = layer:get(1).priority\n'
            'layer:get(2).scroll = vec2(0, 8)\n'
            'local s = layer:get(2).scroll.x\n'
            'layer:get(2):scroll_by(1, 0)\n'
            'layer:get(3).map = 5\n'
            'if layer:get(0).visible then layer:get(0):hide() end')
    assert _errors(body) == []
    assert _c_body(body) == [
        "layer_show(0, 0);", "layer_show(0, 1);",
        "layer_set_priority(1, 0);",
        "int p = layer_get_priority(1);",
        "layer_set_scroll_to(2, (Vec2){0, 8});",
        "int s = layer_get_scroll(2).x;",
        "layer_scroll_by(2, 1, 0);",
        "layer_set_map(3, 5);",
        "if (layer_is_visible(0)) {", "layer_show(0, 0);", "}",
    ]


def test_les_tuiles_d_un_fond_sont_ses_methodes():
    body = ('local fond = layer:get(1)\n'
            'fond:set_tile(2, 3, 4)\n'
            'local t = fond:get_tile(2, 3)\n'
            'fond:set_tile_palette(2, 3, 1)\n'
            'fond:set_tile_flip(2, 3, true, false)\n'
            'fond:fill(0, 0, 4, 4, 7)')
    assert _errors(body) == []
    assert _c_body(body) == [
        "int fond = 1;",
        "tilemap_set(fond, 2, 3, 4);",
        "int t = tilemap_get(fond, 2, 3);",
        "tilemap_set_palette(fond, 2, 3, 1);",
        "tilemap_set_flip(fond, 2, 3, 1, 0);",
        "tilemap_fill(fond, 0, 0, 4, 4, 7);",
    ]


def test_l_etat_d_un_fond_s_ecrit_par_ses_verbes_seulement():
    (msg,) = _errors("layer:get(0).visible = false")
    assert "lecture seule" in msg


def test_un_fond_refuse_ce_qui_n_est_pas_a_lui():
    (msg,) = _errors('layer:get(0):draw("x")')
    assert "background_layer" in msg and ":set_tile()" in msg and ":hide()" in msg


def test_le_numero_est_borne_par_les_fonds_de_la_scene():
    """Sans scène connue, les quatre fonds du mode 0 ; dans une scène, ceux que son mode a. Un
    numéro écrit en clair hors de cet ensemble est refusé, un numéro calculé n'est pas jugé
    (comme un index de tableau)."""
    from scripting.api import LAYERS_BY_MODE
    (msg,) = _errors("layer:get(4):hide()")
    assert "fond 4" in msg and "0, 1, 2, 3" in msg
    assert _errors("layer:get(0):hide()\nlayer:get(3):hide()") == []
    assert _errors("local i = 9\nlayer:get(i):hide()") == []
    # Un mode qui n'a que deux fonds réguliers (le troisième est affine) : le refus dit lesquels.
    (msg,) = _errors("layer:get(3):hide()", layer_numbers=LAYERS_BY_MODE[1])
    assert "fond 3" in msg and "0, 1" in msg
    assert _errors("layer:get(1):hide()", layer_numbers=LAYERS_BY_MODE[1]) == []
    (msg,) = _errors("layer:get(0):hide()", layer_numbers=LAYERS_BY_MODE[3])
    assert "aucun" in msg


def test_les_fonds_par_mode_couvrent_les_six_modes_du_modele():
    from scripting.api import LAYERS_BY_MODE, LAYER_NUMBERS
    assert sorted(LAYERS_BY_MODE) == [0, 1, 2, 3, 4, 5]
    assert all(0 <= n <= 3 for nums in LAYERS_BY_MODE.values() for n in nums)
    assert LAYER_NUMBERS == LAYERS_BY_MODE[0]


def test_le_build_derive_les_numeros_du_mode_de_la_scene():
    """`lua_compiler` lit `Scene.render_mode` : c'est CETTE scène qui borne `layer:get`."""
    src = (REPO_DIR / "editor" / "codegen" / "runtime_codegen" / "lua_compiler.py"
           ).read_text(encoding="utf-8")
    assert "LAYERS_BY_MODE.get(" in src and "layer_numbers = layer_numbers" in src


def test_ce_que_l_auteur_lit_ne_parle_pas_de_mode_video():
    """L'anticipation est INTERNE : les modes affine et bitmap ne sont pas offerts à l'auteur,
    donc rien de ce qu'il lit — la doc, l'indice d'erreur, les messages du checker, y compris
    quand un mode restreint les fonds — ne doit les évoquer."""
    from scripting.api import (RUNTIME_API, RUNTIME_PROPS, REF_TYPE_TABLE, REF_LAYER,
                               LAYERS_BY_MODE)
    textes = [REF_TYPE_TABLE[REF_LAYER].hint]
    textes += [f.doc for k, f in RUNTIME_API.items() if k.startswith(("layer.", f"{REF_LAYER}:"))]
    textes += [p.doc for k, p in RUNTIME_PROPS.items() if k.startswith(f"{REF_LAYER}.")]
    textes += _errors("layer:get(4):hide()")
    textes += _errors("layer:get(3):hide()", layer_numbers=LAYERS_BY_MODE[1])
    textes += _errors("layer:get(0):hide()", layer_numbers=LAYERS_BY_MODE[3])
    for texte in textes:
        assert "mode" not in texte.lower() and "affine" not in texte.lower(), texte


# ── Une région de window ───────────────────────────────────────────────────

def test_une_region_de_window_se_traduit_terme_a_terme():
    body = ('window:get("Panneau"):show()\n'
            'window:get("Panneau"):hide()\n'
            'window:get("Panneau"):set(8, 8, 64, 32)\n'
            'window:get("Panneau"):set_layer(1, true)\n'
            'local w = window:get("Panneau")\n'
            'w:set_obj(false)\n'
            'w:set_blend(true)\n'
            'if w.visible then local a = w:get_layer(2) end')
    assert _errors(body) == []
    assert _c_body(body) == [
        "window_show(WIN_PANNEAU, 1);", "window_show(WIN_PANNEAU, 0);",
        "window_set(WIN_PANNEAU, 8, 8, 64, 32);",
        "window_set_layer(WIN_PANNEAU, 1, 1);",
        "int w = WIN_PANNEAU;",
        "window_set_obj(w, 0);", "window_set_blend(w, 1);",
        "if (window_is_visible(w)) {", "int a = window_get_layer(w, 2);", "}",
    ]


def test_une_region_inconnue_est_refusee_sur_son_nom():
    (msg,) = _errors('window:get("Nawak"):show()')
    assert "Nawak" in msg


def test_l_etat_d_une_region_s_ecrit_par_ses_verbes_seulement():
    (msg,) = _errors('window:get("Panneau").visible = true')
    assert "lecture seule" in msg


# ── Le C ───────────────────────────────────────────────────────────────────

def test_les_conversions_de_vecteur_vivent_dans_la_facade():
    facade = (REPO_DIR / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    for morceau in ("Vec2 layer_get_scroll(int bg)", "void layer_set_scroll_to(int bg, Vec2 v)",
                    "void layer_set_scroll(int bg, int x, int y)"):
        assert morceau in facade, morceau


def test_les_fonctions_c_des_fonds_et_des_windows_sont_dans_le_moteur():
    from scripting.api import RUNTIME_API, RUNTIME_PROPS
    moteur = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(encoding="utf-8")
    facade = (REPO_DIR / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    noms = set()
    for cle, f in RUNTIME_API.items():
        if cle.startswith(("background_layer:", "window_region:")) and not f.c_func.startswith("_"):
            noms.add(f.c_func)
    for cle, p in RUNTIME_PROPS.items():
        if cle.startswith(("background_layer.", "window_region.")):
            noms |= {fn for fn in (p.c_getter, p.c_setter) if fn}
    import re
    manque = {n for n in noms if not re.search(rf"\b{n}\s*\(", moteur + facade)}

    assert manque == set(), manque
