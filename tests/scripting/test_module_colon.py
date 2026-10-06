"""Un module du moteur est un récepteur singleton : `module:action(…)`, `module.état` —
ROADMAP v0.16, décision du 2026-09-26.

`sfx:play("Bip")`, `input:pressed("A")`, `save:write(0)`, `text:draw(…)`, `layer:get(0)` : l'action
d'un module s'écrit avec « : », comme celle d'une instance (`menu:hide()`), et son état avec un
point (`camera.bound`, `scene.frame`). Une seule exception, nommée : la bibliothèque sans état
`math`, qui garde le point (`math.abs(x)`).

Les clés du catalogue restent `module.fonction` : seule l'ÉCRITURE change, ce qui laisse
`RUNTIME_API`, le checker, le codegen et le renommage à leur forme unique. Le parseur ramène
`module:f(…)` à `ExprCall(module.f)` ; l'ancien point sur un module du moteur est refusé, avec la
forme à écrire.
"""

from __future__ import annotations

import pytest

from scripting.api import (
    MODULE_CALLS, STATELESS_MODULES, RUNTIME_API, RUNTIME_PROPS,
    module_call_form, canonical_key, modernize_message,
)


def _errors(body: str, **kw) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    return [e.message for e in check(parse(src), BuildContext(actor_name="Sc", **kw))
            if e.level == "error"]


def _c_body(body: str, **kw) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=["Bip"],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=["Foe"], owner_kind="scene", **kw)
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Sc_scene_on_update(void) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:] if ln.strip()]


# ── Le contrat : quels modules, quelle exception ───────────────────────────

def test_seule_la_bibliotheque_sans_etat_garde_le_point():
    assert STATELESS_MODULES == {"math"}
    modules_avec_fonctions = {k.split(".", 1)[0] for k in RUNTIME_API if "." in k}
    assert MODULE_CALLS == modules_avec_fonctions - STATELESS_MODULES
    assert {"input", "save", "text", "sfx", "scene", "layer", "interface"} <= MODULE_CALLS


def test_la_forme_ecrite_et_la_cle_du_catalogue_se_correspondent():
    for cle in RUNTIME_API:
        module = cle.split(".", 1)[0]
        if "." in cle and module in MODULE_CALLS:
            forme = module_call_form(cle)
            assert forme == cle.replace(".", ":", 1)
            assert canonical_key(forme) == cle, cle
    assert module_call_form("math.abs") == "math.abs"        # la bibliothèque
    assert module_call_form("sfx:stop") == "sfx:stop"        # une méthode de TYPE
    assert canonical_key("sfx:stop") == "sfx:stop"           # `sfx` : module ET type
    assert canonical_key("sfx:play") == "sfx.play"


# ── Ce qui se traduit ──────────────────────────────────────────────────────

def test_les_actions_de_module_se_traduisent_comme_avant():
    body = ('sfx:play("Bip")\n'
            'local pas = sfx:play("Bip")\npas:stop()\n'
            'if input:pressed("a") and input:held("b") then scene:switch("Sc") end\n'
            'text:draw(2, 3, "salut")\n'
            'local n = math.abs(-3)')
    kw = dict(text_keys=[], scene_names=["Sc"])
    assert _errors(body, sfx_names=["Bip"], scene_names=["Sc"], text_keys=[]) == []
    c = "\n".join(_c_body(body, text_keys=[], scene_names=["Sc"]))
    assert "sfx_play(SFX_BIP, 255, 0);" in c
    assert "mm_sfxhand pas = sfx_play(SFX_BIP, 255, 1);" in c
    assert "sfx_stop(pas);" in c
    assert "input_pressed(" in c and "input_held(" in c and "scene_switch(" in c
    assert "text_draw(2, 3," in c


def test_les_appels_se_chainent_sur_un_module():
    body = 'sfx:play("Bip"):set_volume(50)\nactor:get("Foe"):move_to(vec2(1, 2), 2)'
    assert _errors(body, sfx_names=["Bip"], actor_names=["Foe"]) == []
    c = _c_body(body)
    assert any(l.startswith("sfx_set_volume(sfx_play(SFX_BIP") for l in c), c
    assert any("actor_move_to(runtime_get_actor(ACTORNAME_FOE)" in l for l in c), c


def test_l_etat_d_un_module_garde_le_point():
    body = 'local b = camera.bound\nlocal f = scene.frame\nlocal s = scene.size.x'
    assert _errors(body) == []


# ── Ce qui est refusé, avec la forme à écrire ──────────────────────────────

@pytest.mark.parametrize("cle", sorted(
    k for k in RUNTIME_API
    if "." in k and k.split(".", 1)[0] in MODULE_CALLS
    and not k.split(".", 1)[0] in {"interface", "layer", "window"}))
def test_l_ancien_point_est_refuse_pour_toute_fonction_de_module(cle):
    """Toute fonction de module, sans en nommer aucune ici : le catalogue dit lesquelles."""
    module, _, fonction = cle.partition(".")
    (msg, *_reste) = _errors(f"{module}.{fonction}()")
    assert f"{module}:{fonction}(" in msg and '":"' in msg, msg


def test_le_point_sur_interface_layer_window_est_refuse_aussi():
    for cle in ("interface.get", "layer.get", "window.get"):
        module, _, fonction = cle.partition(".")
        (msg, *_r) = _errors(f'{module}.{fonction}("x")')
        assert f"{module}:{fonction}(" in msg


def test_la_bibliotheque_math_refuse_les_deux_points():
    (msg,) = _errors("local x = math:abs(-1)")
    assert "library" in msg and "math.abs" in msg
    assert _errors("local x = math.abs(-1)") == []


def test_les_diagnostics_parlent_la_forme_ecrite():
    """Un message qui nomme `sfx.play` alors que l'auteur a écrit `sfx:play` l'enverrait
    chercher une forme qui n'existe plus."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = 'function on_update()\nsfx:play("Nawak")\nend\n'
    (msg,) = [e.message for e in check(parse(src), BuildContext(actor_name="Sc", sfx_names=["Bip"]))]
    assert "sfx:play('Nawak')" in msg, msg

    assert modernize_message("interface.get('X') et math.abs(1) et self:move()") == \
        "interface:get('X') et math.abs(1) et self:move()"


# ── Les outils lisent la forme écrite ──────────────────────────────────────

def test_le_renommage_suit_un_appel_de_module():
    from scripting.refactor import rename_in_text
    from scripting.api import DOMAIN_SCENE
    src = 'scene:switch("Arena")\nlocal x = scene:switch("Arena")\n'
    out, n = rename_in_text(src, DOMAIN_SCENE, "Arena", "Pit")
    assert n == 2 and out.count('scene:switch("Pit")') == 2


def test_les_paires_zone_texte_se_lisent_derriere_interface_deux_points():
    from scripting.refactor import iter_call_sites
    from scripting.api import DOMAIN_UI_ELEMENT, DOMAIN_TEXT
    src = 'interface:get("Box"):draw("hello")\nlocal b = interface:get("Box")\nb:draw("world")\n'
    paires = {(s.values[DOMAIN_UI_ELEMENT], s.values[DOMAIN_TEXT])
              for s in iter_call_sites(src, None, DOMAIN_UI_ELEMENT, DOMAIN_TEXT)}
    assert paires == {("Box", "hello"), ("Box", "world")}


def test_la_reservation_de_surface_reconnait_text_deux_points():
    from codegen.font_emit import _FREE_WRITE_RE
    assert _FREE_WRITE_RE.search('text:draw(1, 1, "a")')
    assert not _FREE_WRITE_RE.search('interface:get("Box"):draw("a")')


def test_la_reference_affiche_les_actions_avec_deux_points():
    from scripting import api_reference, api_snippets
    assert api_snippets.signature("input.pressed") == "input:pressed(btn)"
    assert api_snippets.bare("sfx.play") == "sfx:play()"
    labels = {e["label"].split("(")[0] for c in api_reference.get_categories()
              for e in c["entries"]}
    assert "input:pressed" in labels and "input.pressed" not in labels
    assert "math.abs" in labels                        # la bibliothèque
    assert api_reference.STALE == []


def test_aucune_propriete_de_module_ne_se_fait_appeler():
    """Une propriété (`camera.bound`) n'est jamais une fonction : elle ne peut pas porter de
    forme `module:x`, sans quoi `canonical_key` la confondrait avec une action."""
    for cle in RUNTIME_PROPS:
        module, dot, nom = cle.partition(".")
        if dot and module in MODULE_CALLS:
            assert f"{module}.{nom}" not in RUNTIME_API, cle
