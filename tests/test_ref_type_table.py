"""Un type de référence se déclare dans UNE table (`api.REF_TYPE_TABLE`) — ROADMAP v0.16,
amendement du 2026-09-24, critère 2.

Avant, ajouter un type touchait `REF_TYPES`, `C_REF_TYPES` (expr_types), la variable
des snippets (`_REF_VARIABLE`), un cas spécial du checker (`_is_ui_element`) et un autre du
codegen : trois mécanismes, écrits à la main aux mêmes endroits. `interface.get` en
était la preuve — son type `ui_element` était « déclaré comme type de retour mais
absent de `REF_TYPES` », donc jugé par une forme de code à part.

Ce fichier tient deux promesses :

1. **Un type factice, déclaré seulement dans la table et le catalogue, marche de bout
   en bout** — checker, codegen, snippets — sans qu'on ait touché à `checker.py` ni à
   `codegen.py`. C'est LE test : s'il échoue le jour où quelqu'un ajoute un cas spécial,
   la règle est rompue.
2. **La table et le catalogue ne se contredisent pas** : pas de type sans fabrique, pas
   de clé `<type>:méthode` d'un type inconnu (une faute de frappe qui laisserait ses
   méthodes injoignables).
"""

from __future__ import annotations

import pytest

from scripting import api
from scripting.api import (
    ApiFunc, ApiProp, Param, RefType, PARAM_INT, RUNTIME_API, RUNTIME_PROPS,
    REF_TYPE_TABLE, REF_TYPES,
)


# ── Le type factice : trois lignes de déclaration, aucun code de traduction ──

@pytest.fixture
def gizmo(monkeypatch):
    """Un type `gizmo` déclaré comme le ferait quiconque en ajoute un vrai. La
    fabrique vit dans un module EXISTANT (`scene`) : ce test juge les types, pas
    la déclaration d'un nouveau module."""
    monkeypatch.setitem(REF_TYPE_TABLE, "gizmo", RefType(
        c_type="gizmo_t", variable="g", hint="Un gizmo se règle par `speed`."))
    monkeypatch.setitem(RUNTIME_API, "scene.make_gizmo", ApiFunc(
        lua_name="scene.make_gizmo", c_func="gizmo_make", ret="gizmo"))
    monkeypatch.setitem(RUNTIME_API, "gizmo:spin", ApiFunc(
        lua_name="gizmo:spin", c_func="gizmo_spin", self_first=True,
        params=[Param("turns", PARAM_INT)]))
    monkeypatch.setitem(RUNTIME_PROPS, "gizmo.speed", ApiProp(
        lua_name="gizmo.speed", c_getter="gizmo_get_speed",
        c_setter="gizmo_set_speed", self_first=True))
    monkeypatch.setitem(RUNTIME_PROPS, "gizmo.id", ApiProp(
        lua_name="gizmo.id", c_getter="gizmo_get_id", self_first=True, read_only=True))


def _errors(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    return [e.message for e in check(parse(src), BuildContext(actor_name="Cam"))
            if e.level == "error"]


def _c_body(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Cam", actor_sym="Cam", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=[])
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Cam_on_update(Actor* self) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:]
            if ln.strip()]


def test_un_type_declare_dans_la_table_se_traduit_de_bout_en_bout(gizmo):
    body = ("local g = scene:make_gizmo()\n"
            "g:spin(3)\n"
            "g.speed = 2\n"
            "local s = g.speed")
    assert _errors(body) == []
    assert _c_body(body) == [
        "gizmo_t g = gizmo_make();",       # le type C vient de la TABLE
        "gizmo_spin(g, 3);",               # la méthode, de `gizmo:spin`
        "gizmo_set_speed(g, 2);",          # la propriété, de `gizmo.speed`
        "int s = gizmo_get_speed(g);",
    ]


def test_un_type_declare_se_chaine_sans_local(gizmo):
    """Le chaînage est le même chemin que via un `local` (cf. test_chained_receivers)."""
    body = "scene:make_gizmo():spin(3)\nscene:make_gizmo().speed = 4"
    assert _errors(body) == []
    assert _c_body(body) == ["gizmo_spin(gizmo_make(), 3);",
                             "gizmo_set_speed(gizmo_make(), 4);"]


def test_les_fautes_d_un_type_declare_sont_refusees_avec_son_indice(gizmo):
    """Méthode ou champ inconnu : l'erreur nomme le type, liste ses membres et
    ajoute l'`hint` DÉCLARÉ avec lui — aucune phrase écrite dans le checker."""
    for body in ("local g = scene:make_gizmo()\ng:bogus()",
                 "scene:make_gizmo():bogus()"):
        (msg,) = _errors(body)
        assert "gizmo" in msg and ":spin()" in msg and "Un gizmo se règle par" in msg, msg
    for body in ("local g = scene:make_gizmo()\nlocal x = g.bogus",
                 "local x = scene:make_gizmo().bogus"):
        (msg,) = _errors(body)
        assert "speed" in msg and "Un gizmo se règle par" in msg, msg


def test_une_propriete_en_lecture_seule_d_un_type_declare_est_refusee(gizmo):
    assert any("read-only" in m for m in _errors(
        "local g = scene:make_gizmo()\ng.id = 3"))


def test_la_variable_des_snippets_vient_de_la_table(gizmo):
    from scripting import api_snippets
    assert api_snippets._on_variable("gizmo:spin") == "g:spin"
    assert api_snippets._on_variable("gizmo.speed") == "g.speed"


def test_le_type_c_de_chaque_type_reel_vient_de_la_table():
    """Les trois types existants, avec leur représentation C d'avant la table."""
    assert {n: t.c_type for n, t in REF_TYPE_TABLE.items()} == {
        "sfx": "mm_sfxhand", "collision_box": "int", "ui_element": "int",
        "list": "int", "image": "int", "text_region": "int",
        "background_layer": "int", "window_region": "int", "actor": "Actor*"}



def test_un_element_d_interface_est_un_type_comme_un_autre():
    """`ui_element` n'est plus un cas spécial : ses verbes vivent sous SA clé, et ceux
    de l'acteur sous `self:` — chacun est une entrée du catalogue, pas un partage de clé."""
    assert "ui_element:show" in RUNTIME_API and "ui_element:hide" in RUNTIME_API
    assert RUNTIME_API["ui_element:show"].c_func == RUNTIME_API["ui_element:hide"].c_func
    assert RUNTIME_API["actor:show"].c_func == "actor_set_visible"
    assert RUNTIME_API["interface.get"].ret == "ui_element"


def test_absent_se_dit_nil_pour_toute_reference_de_pool():
    """Les « trois façons de dire absent » (`nil` pour un acteur, `0` pour un effet ou
    une boîte) n'en sont qu'UNE dans le C émis : `nil` vaut 0, et une référence
    absente vaut 0. `if p ~= nil` marche donc sur les trois — ce que la table
    n'a pas à déclarer, seulement à ne pas casser."""
    cas = {
        "sfx": ('local p = sfx:play("Bip")\nif p ~= nil then p:stop() end', "(p != 0)"),
        "collision_box": ('local hb = self:collision_box("hb")\nif hb == nil then self:destroy() end',
                          "(hb == 0)"),
        "actor": ('local a = actor:get("Foe")\nif a ~= nil then a:destroy() end', "(a != 0)"),
    }
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    for type_, (body, attendu) in cas.items():
        src = f"function on_update()\n{body}\nend\n"
        ctx = CodegenContext(actor_name="Cam", actor_sym="Cam", anim_names=[],
                             sfx_names=["Bip"], music_names=[], global_names=set(),
                             const_names=set(), all_actor_syms=["Foe"])
        code, _, _ = generate(parse(src), ctx)
        assert f"if ({attendu})" in code, (type_, code[-400:])


# ── La table et le catalogue s'accordent ──────────────────────────────────

def test_les_types_de_reference_sont_une_vue_vivante_de_la_table():
    assert list(REF_TYPES) == list(REF_TYPE_TABLE)


def test_tout_type_declare_a_une_fabrique():
    """Un type que rien ne rend est un type mort : ses méthodes seraient injoignables.
    (`collision_box` est rendu par `self:collision_box`, une acquisition dérivée.)"""
    rendus = {f.ret for f in RUNTIME_API.values()}
    # `interface.get` rend le type de la NATURE de l'élément (`ret_by_name`) : tout type
    # d'élément d'interface a donc pour fabrique cette seule fonction.
    if any(f.ret_by_name for f in RUNTIME_API.values()):
        rendus |= {n for n, t in REF_TYPE_TABLE.items() if t.ui_kind}
    assert set(REF_TYPE_TABLE) <= rendus, set(REF_TYPE_TABLE) - rendus


def test_tout_ret_de_reference_est_declare():
    """Un `ret` que ni le langage ni la table ne connaît ne se traduit nulle part :
    c'était l'état de `ui_element`, jugé par une forme de code à part."""
    simples = {"void", "int", "bool", "actor", "vec2", "vec3", "rect"}
    inconnus = {f.ret for f in RUNTIME_API.values()} - simples - set(REF_TYPE_TABLE)
    assert not inconnus, inconnus


def test_toute_cle_de_methode_ou_de_propriete_designe_un_type_connu():
    """`collison_box:overlaps` (faute de frappe) laisserait ses méthodes sans porteur,
    sans qu'aucun test de fonction ne l'atteigne."""
    connus = set(REF_TYPE_TABLE) | {"self"}
    for cle in RUNTIME_API:
        if ":" in cle:
            assert cle.split(":")[0] in connus, cle
    proprietes = connus | {"blend", "camera", "input", "scene"}
    for cle in RUNTIME_PROPS:
        assert cle.split(".")[0] in proprietes, cle


# ── L'héritage : `list` reprend `ui_element` (ROADMAP v0.16, étape c) ──────

def test_l_heritage_se_declare_avec_sa_conversion_de_reference():
    """Un type qui a un parent dit AUSSI comment passer à son index : sans `to_base`,
    `menu:hide()` émettrait `ui_element_show(<index de liste>, 0)` — l'index d'un autre
    espace, qui cacherait un autre élément sans une erreur."""
    for nom, decl in REF_TYPE_TABLE.items():
        if decl.base:
            assert decl.base in REF_TYPE_TABLE, (nom, decl.base)
            assert decl.to_base, f"{nom} hérite de {decl.base} sans dire comment le convertir"
        else:
            assert not decl.to_base, nom
    from scripting.api import ref_lineage, ref_member, ref_upcast
    assert ref_lineage("list") == ["list", "ui_element"]
    assert ref_member("list", "hide", ":")[0] == "ui_element"
    assert ref_member("list", "index", ".")[0] == "list"
    assert ref_member("image", "index", ".") is None        # `menu.index`, pas `heart.index`
    assert ref_upcast("list", "ui_element", "m") == "ui_list_element(m)"
    assert ref_upcast("list", "list", "m") == "m"


def test_les_natures_d_element_sont_celles_de_la_mise_en_page():
    """`RefType.ui_kind` cite les `kind` de la mise en page en toutes lettres : ce test les
    tient d'accord avec le modèle, qui reste leur source."""
    from core.models import ui_region
    kinds = {t.ui_kind for t in REF_TYPE_TABLE.values() if t.ui_kind}
    assert kinds == {ui_region.KIND_CONTAINER, ui_region.KIND_LIST,
                     ui_region.KIND_IMAGE, ui_region.KIND_TEXT}
    assert len({t.constant for t in REF_TYPE_TABLE.values() if t.ui_kind}) == 4


def test_un_membre_herite_se_verifie_et_se_traduit_sur_le_type_reel():
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext
    src = ("function on_update()\n"
           '  local menu = interface:get("Menu")\n'
           "  menu.index = 2\n"
           "  menu:hide()\n"
           "  if menu.visible and menu.active then menu:activate() end\n"
           '  interface:get("Menu"):show()\n'
           "end\n")
    kinds = {"Menu": "list"}
    errs = [e.message for e in check(parse(src), BuildContext(
        actor_name="Cam", element_names=["Menu"], ref_kinds=kinds)) if e.level == "error"]
    assert errs == []
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Cam", actor_sym="Cam", anim_names=[], sfx_names=[], music_names=[],
        global_names=set(), const_names=set(), all_actor_syms=[],
        element_names=["Menu"], ref_kinds=kinds))
    corps = code[code.find("Cam_on_update(Actor* self) {"):]
    assert "int menu = UILIST_MENU;" in corps           # la référence porte l'index de LISTE
    assert "ui_list_set_index(menu, 2);" in corps       # ...que ses propriétés attendent
    assert "ui_element_show(ui_list_element(menu), 0);" in corps   # ...et le parent, converti
    assert "ui_element_is_visible(ui_list_element(menu))" in corps
    assert "ui_list_active(menu)" in corps
    assert "ui_list_set_active(menu, 1);" in corps
    assert "ui_element_show(ui_list_element(UILIST_MENU), 1);" in corps


# ── L'acteur est un type comme un autre (ROADMAP v0.16, étape e) ───────────────
# Ses méthodes sont `actor:<m>`, ses propriétés `actor.<champ>` ; à l'écriture c'est `self:` (l'instance
# qui exécute le script), `other:`, ou une variable qui tient `actor:get(…)`.

def test_le_catalogue_ne_garde_aucune_cle_self():
    """`self` n'est pas un type, c'est un récepteur : le catalogue dit `actor`."""
    assert not [k for k in RUNTIME_API if k.startswith(("self:", "self."))]
    assert not [k for k in RUNTIME_PROPS if k.startswith(("self:", "self."))]
    assert REF_TYPE_TABLE["actor"].c_type == "Actor*"
    assert REF_TYPE_TABLE["actor"].variable == "self"


def _actor_errors(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    return [e.message for e in check(parse(src), BuildContext(
        actor_name="Cam", actor_names=["Foe"])) if e.level == "error"]


def test_un_acteur_tenu_par_une_variable_a_les_membres_du_type_actor():
    body = ('local boss = actor:get("Foe")\n'
            'boss:move_to(vec2(1, 2), 2)\n'
            'boss.position = vec2(3, 4)\n'
            'local p = boss.position.x\n'
            'boss:deactivate()')
    assert _actor_errors(body) == []
    (msg,) = _actor_errors('local boss = actor:get("Foe")\nlocal x = boss.nawak')
    assert "actor" in msg and "position" in msg


def test_le_module_actor_n_a_pas_les_champs_du_type_actor():
    """`actor.position` : `actor` est ici le MODULE (`actor:get`, `actor:spawn`). Le type et le
    module partagent leur nom, jamais leurs membres."""
    (msg,) = _actor_errors("local p = actor.position")
    assert "module" in msg and "count" in msg and "self.position" in msg
    assert _actor_errors("local p = self.position\nother.velocity = vec2(0, 0)") == []


def test_la_variable_des_snippets_d_un_acteur_est_self():
    from scripting import api_snippets
    assert api_snippets.bare("actor:move_to") == "self:move_to()"
    assert api_snippets.bare("actor.position") == "self.position"
    assert api_snippets.signature("actor:play_anim").startswith("self:play_anim(")
