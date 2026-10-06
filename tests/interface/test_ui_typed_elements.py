"""`interface:get("Nom")` rend le type RÉEL de l'élément — ROADMAP v0.16, étape (c), tranche 2.

Un élément d'interface est une liste, une image, une zone de texte ou un conteneur : sa
NATURE, lue dans la mise en page au build, décide de ses membres (`menu.index`, `heart.state`,
`box:draw(...)`) et de la constante C qu'`interface.get` émet. Ce fichier tient ce qui n'est pas
déjà juré ailleurs : la lecture de la nature, la chaîne `menu:row(n):draw(...)`, les paires
(zone, texte) que le build mesure, et le refus d'un membre qui n'est pas celui du type.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.models.ui_region import KIND_CONTAINER, KIND_IMAGE, KIND_LIST, KIND_TEXT

KINDS = {"Menu": "list", "Heart": "image", "Box": "text_region", "Hud": "ui_element"}


def _errors(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    ctx = BuildContext(actor_name="Sc", element_names=list(KINDS), ref_kinds=KINDS,
                       text_keys=["hello"], image_states={"Heart": ["full", "empty"]})
    src = f"function on_update()\n{body}\nend\n"
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def _c_body(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=[], owner_kind="scene", text_keys=["hello"],
                         element_names=list(KINDS), ref_kinds=KINDS)
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Sc_scene_on_update(void) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:] if ln.strip()]


# ── La nature se lit dans la mise en page ──────────────────────────────────

def test_la_nature_d_un_element_vient_de_la_mise_en_page():
    from scripting.project_names import ui_ref_kinds
    layout = object()
    elements = [(layout, SimpleNamespace(name=n, kind=k)) for n, k in
                (("Menu", KIND_LIST), ("Heart", KIND_IMAGE), ("Box", KIND_TEXT),
                 ("Hud", KIND_CONTAINER), ("Autre", "kind_inconnu"))]
    project = SimpleNamespace(all_elements=lambda: elements)
    # Un `kind` que la table ne connaît pas retombe sur le type de base : il garde au moins
    # son cycle de vie, il ne disparaît pas.
    assert ui_ref_kinds(project) == {**KINDS, "Autre": "ui_element"}


def test_la_constante_emise_suit_la_nature():
    assert _c_body('interface:get("Menu"):activate()\n'
                   'interface:get("Heart"):play()\n'
                   'interface:get("Box"):clear()\n'
                   'interface:get("Hud"):hide()') == [
        "ui_list_set_active(UILIST_MENU, 1);",
        "ui_image_play(IMAGE_HEART, 1);",
        "text_clear_in(REGION_BOX);",
        "ui_element_show(UIELEM_HUD, 0);",
    ]


# ── Les rangées d'une liste sont des zones de texte ────────────────────────

def test_une_rangee_de_liste_s_ecrit_par_chainage():
    body = 'interface:get("Menu"):row(1):draw("hello")\nlocal r = interface:get("Menu"):row(2)\nr:clear()'
    assert _errors(body) == []
    assert _c_body(body) == [
        "text_draw_in(ui_list_row(UILIST_MENU, 1), TEXT_HELLO);",
        "int r = ui_list_row(UILIST_MENU, 2);",
        "text_clear_in(r);",
    ]


# ── Les membres d'un type ne sont pas ceux d'un autre ──────────────────────

def test_un_membre_d_un_autre_type_est_refuse_en_nommant_ceux_du_type():
    (msg,) = _errors('local i = interface:get("Heart").index')
    assert "image" in msg and "state" in msg and "offset" in msg
    assert "visible" in msg                       # l'héritage se lit dans la liste des champs
    (msg,) = _errors('interface:get("Menu"):draw("hello")')
    assert "list" in msg and ":row()" in msg and ":hide()" in msg


def test_les_etats_d_image_se_jugent_dans_le_sprite_de_l_image():
    assert _errors('interface:get("Heart").state = "empty"') == []
    (msg,) = _errors('interface:get("Heart").state = "broken"')
    assert "full, empty" in msg


def test_une_zone_de_texte_se_lit_et_se_saute():
    body = 'if interface:get("Box").reading then interface:get("Box"):skip() end'
    assert _errors(body) == []
    assert "text_reading(REGION_BOX)" in "\n".join(_c_body(body))


# ── Ce que le build mesure : la paire (zone, texte) ────────────────────────

def test_une_ecriture_dans_une_zone_donne_la_paire_zone_texte():
    """`box:draw("hello")` pose la MÊME paire que `draw_text("box", "hello")` : sans elle, le
    débordement d'un texte hors de sa zone ne serait plus signalé par le build."""
    from scripting.refactor import iter_call_sites
    from scripting.api import DOMAIN_UI_ELEMENT, DOMAIN_TEXT
    src = ('interface:get("Box"):draw("hello")\n'
           'local b = interface:get("Box")\n'
           'b:draw("world")\n'
           'local m = interface:get("Menu")\nm.index = 2\n'
           'interface:get("Menu"):draw("nul")\n')
    paires = [(s.values[DOMAIN_UI_ELEMENT], s.values[DOMAIN_TEXT])
              for s in iter_call_sites(src, None, DOMAIN_UI_ELEMENT, DOMAIN_TEXT)]
    assert ("Box", "hello") in paires and ("Box", "world") in paires


def test_un_local_reaffecte_a_un_autre_element_ne_conclut_rien():
    from scripting.refactor import iter_call_sites
    from scripting.api import DOMAIN_UI_ELEMENT, DOMAIN_TEXT
    src = ('local b = interface:get("Box")\n'
           'b = interface:get("Menu")\n'
           'b:draw("hello")\n')
    assert list(iter_call_sites(src, None, DOMAIN_UI_ELEMENT, DOMAIN_TEXT)) == []


def test_renommer_une_zone_reecrit_son_nom_dans_interface_get():
    from scripting.refactor import rename_in_text
    from scripting.api import DOMAIN_UI_ELEMENT
    src = 'local b = interface:get("Box")\nb:draw("hello")\ninterface:get("Box"):clear()\n'
    out, n = rename_in_text(src, DOMAIN_UI_ELEMENT, "Box", "Dialog")
    assert n == 2 and out.count('interface:get("Dialog")') == 2


# ── Le C : un élément typé se convertit vers son parent ────────────────────

def test_les_conversions_vers_l_element_de_base_existent_dans_le_moteur():
    from pathlib import Path
    from scripting.api import REF_TYPE_TABLE
    moteur = (Path(__file__).resolve().parents[2] / "runtime" / "include"
              / "gba_engine.h").read_text(encoding="utf-8")
    for decl in REF_TYPE_TABLE.values():
        if decl.to_base:
            assert f"int {decl.to_base}(" in moteur.replace("int  ", "int "), decl.to_base


# ── Une colonne de données `region` / `image` porte le handle d'un type ────────
# Le build range dans une telle colonne l'INDEX de la zone ou de l'image : c'est exactement la
# valeur du type. `data.Dialogue[i].boite:draw("…")` se juge donc comme `interface:get(…):draw`,
# sans nom d'élément à citer — la porte d'usage qui manquait depuis la migration des fonctions
# de module.

DATA = {"Dialogue": (["boite", "icone", "n"], 3)}


def _kinds_data():
    from scripting.expr_types import data_column_key
    return {data_column_key("Dialogue", "boite"): "text_region",
            data_column_key("Dialogue", "icone"): "image"}


def _data_errors(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = BuildContext(actor_name="Sc", data_tables=DATA, ref_kinds=_kinds_data(),
                       text_keys=["hello"], image_states={})
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def _data_c(body: str) -> list[str]:
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[],
                         music_names=[], global_names=set(), const_names=set(),
                         all_actor_syms=[], owner_kind="scene", text_keys=["hello"],
                         data_tables=DATA, ref_kinds=_kinds_data())
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Sc_scene_on_update(void) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:] if ln.strip()]


def test_une_cellule_de_colonne_region_ou_image_est_une_reference_typee():
    body = ('data.Dialogue[2].boite:draw("hello")\n'
            'local z = data.Dialogue[1].boite\n'
            'z:clear()\n'
            'if data.Dialogue[1].boite.reading then z:skip() end\n'
            'data.Dialogue[1].icone.offset = vec2(0, 4)\n'
            'data.Dialogue[1].icone:pause()\n'
            'local n = data.Dialogue[1].n')
    assert _data_errors(body) == []
    assert _data_c(body) == [
        "text_draw_in(g_data_Dialogue[1].boite, TEXT_HELLO);",
        "int z = g_data_Dialogue[0].boite;",
        "text_clear_in(z);",
        "if (text_reading(g_data_Dialogue[0].boite)) {", "text_skip(z);", "}",
        "ui_image_set_offset(g_data_Dialogue[0].icone, (Vec2){0, 4});",
        "ui_image_play(g_data_Dialogue[0].icone, 0);",
        "int n = g_data_Dialogue[0].n;",
    ]


def test_la_cellule_garde_sa_nature_de_donnee_constante():
    """Le handle se lit ; la CELLULE ne s'écrit toujours pas (la table est en ROM). Seule une
    propriété de l'élément désigné s'écrit."""
    (msg,) = _data_errors("data.Dialogue[1].boite = 2")
    assert "constant" in msg
    assert _data_errors("data.Dialogue[1].icone.offset = vec2(0, 1)") == []


def test_un_membre_d_un_autre_type_est_refuse_sur_une_cellule():
    (msg,) = _data_errors("local i = data.Dialogue[1].boite.offset")
    assert "text_region" in msg and "data.Dialogue[…].boite" in msg
    (msg,) = _data_errors('data.Dialogue[1].boite:play()')
    assert "text_region" in msg


def test_l_etat_d_image_par_nom_exige_une_image_connue_au_build():
    """Une cellule désigne une image que le build ne sait pas nommer : deviner la constante
    écrirait l'état d'une autre. Le message dit quoi écrire."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    ctx = BuildContext(actor_name="Sc", data_tables=DATA, ref_kinds=_kinds_data(),
                       image_states={"Heart": ["full"]})
    src = 'function on_update()\ndata.Dialogue[1].icone.state = "full"\nend\n'
    (msg,) = [e.message for e in check(parse(src), ctx) if e.level == "error"]
    assert "does not know which image" in msg


def test_le_build_type_les_colonnes_de_reference_du_projet():
    from types import SimpleNamespace
    from scripting.project_names import data_column_kinds
    from scripting.expr_types import data_column_key
    col = lambda n, t: SimpleNamespace(name=n, type=t)
    project = SimpleNamespace(data_tables=[
        SimpleNamespace(name="Dialogue",
                        columns=[col("boite", "region"), col("icone", "image"),
                                 col("texte", "text"), col("n", "int")])])
    assert data_column_kinds(project) == {
        data_column_key("Dialogue", "boite"): "text_region",
        data_column_key("Dialogue", "icone"): "image"}
