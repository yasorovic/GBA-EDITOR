"""Déplacer une image d'interface depuis un script (ROADMAP v0.22, 2026-09-02 ; reprise en
propriété typée par l'étape c de la v0.16, 2026-09-26).

Le jalon s'appelle « Menus, listes et CURSEUR » et ne savait pas déplacer un
curseur : la navigation livrée surligne la rangée choisie, mais aucune API ne
donnait accès à la position d'une image. Écrit d'instinct,
`interface:get("Cursor").y = 40` traversait le checker sans un mot et produisait
`UIELEM_CURSOR.y` — `.y` sur un entier, refusé par gcc sur un fichier que
l'auteur n'a pas écrit.

Depuis l'étape c, `interface:get("Curseur")` rend une IMAGE, et son décalage est sa
propriété `offset` (un vec2, relatif à la position authorée). Ce que ces tests protègent :

- la forme passe par les chemins GÉNÉRIQUES des propriétés, sans une ligne de checker ni de
  codegen écrite pour l'occasion — c'est justement ce qu'un test doit surveiller : si quelqu'un
  ajoute plus tard un chemin dédié, c'est que la forme a dérivé ;
- le nom résout en `IMAGE_*` (index dans `g_ui_images`) et jamais en `UIELEM_*`
  (index dans `g_ui_elements`, la table de VISIBILITÉ qui couvre tous les types) — la confusion
  qui rendait le premier réflexe incompilable. C'est la NATURE de l'élément, lue dans la mise en
  page, qui choisit la constante ;
- un nom d'élément inconnu est refusé au build, en nommant les éléments du projet ;
- les fonctions sont vues des DEUX contextes de compilation — `gba_engine.h` pour `main.c`, et le
  prototype GÉNÉRÉ dans `runtime_api.h` (ou la façade) pour les unités de scène/acteur.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent


def _lua(src: str, images=("Curseur",), lists=("Menu",)):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    elements = list(images) + list(lists)
    kinds = {**{n: "image" for n in images}, **{n: "list" for n in lists}}
    errors = [e.message for e in check(script, BuildContext(
        actor_name="Sc", element_names=elements, ref_kinds=kinds,
    )) if e.level == "error"]
    code, _w, _s = generate(script, CodegenContext(
        actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=[],
        owner_kind="scene", image_names=list(images), ui_list_names=list(lists),
        element_names=elements, ref_kinds=kinds))
    return errors, code


def _body(*lines: str) -> str:
    return "function on_update()\n" + "".join(f"    {l}\n" for l in lines) + "end\n"


# ── La forme, et ce en quoi elle compile ──────────────────────────


def test_le_deplacement_compile_en_ecriture_de_propriete():
    errors, code = _lua(_body('interface:get("Curseur").offset = vec2(0, 16)'))
    assert errors == []
    assert "ui_image_set_offset(IMAGE_CURSEUR, (Vec2){0, 16})" in code


def test_le_nom_resout_en_index_dimage_pas_en_index_delement():
    """`UIELEM_*` indexe `g_ui_elements` (la VISIBILITÉ, tous types confondus), `IMAGE_*`
    indexe `g_ui_images`. Confondre les deux est ce qui rendait `interface:get("Cursor").y`
    incompilable ; la nature de l'élément, lue dans la mise en page, évite la question."""
    _errors, code = _lua(_body('interface:get("Curseur").offset = vec2(4, 8)'))
    corps = code[code.find("Sc_scene_on_update"):]      # le `#define UIELEM_*` d'en-tête existe
    assert "IMAGE_CURSEUR" in corps
    assert "UIELEM_CURSEUR" not in corps


def test_la_lecture_est_symetrique_de_lecriture():
    errors, code = _lua(_body('local o = interface:get("Curseur").offset',
                              'local x = o.x',
                              'local y = interface:get("Curseur").offset.y'))
    assert errors == []
    assert "Vec2 o = ui_image_offset(IMAGE_CURSEUR);" in code
    assert "ui_image_offset(IMAGE_CURSEUR).y" in code


def test_le_decalage_se_compose_avec_une_expression():
    """Le cas qui a motivé le chantier : un curseur qui suit l'item choisi."""
    errors, code = _lua(_body(
        'interface:get("Curseur").offset = vec2(0, 16 * interface:get("Menu").index)'))
    assert errors == []
    assert "ui_image_set_offset(IMAGE_CURSEUR, (Vec2){0, (16 * ui_list_index(UILIST_MENU))})" in code


def test_un_local_tient_l_image_comme_la_forme_chainee():
    errors, code = _lua(_body('local c = interface:get("Curseur")',
                              'c.offset = vec2(0, 8)', 'c:pause()', 'c:play()'))
    assert errors == []
    assert "int c = IMAGE_CURSEUR;" in code
    assert "ui_image_set_offset(c, (Vec2){0, 8});" in code
    assert "ui_image_play(c, 0);" in code and "ui_image_play(c, 1);" in code


# ── Ce que le build refuse tout seul ──────────────────────────────


def test_une_image_inconnue_est_refusee_en_nommant_les_autres():
    errors, _code = _lua(_body('interface:get("Cusor").offset = vec2(0, 8)'))
    assert len(errors) == 1
    assert "Cusor" in errors[0] and "Curseur" in errors[0]


def test_un_scalaire_n_est_pas_un_decalage():
    errors, _code = _lua(_body('interface:get("Curseur").offset = 8'))
    assert errors and "vec2" in errors[0]


def test_une_liste_n_a_pas_de_decalage():
    """`offset` est une propriété d'IMAGE : la liste garde ses propres membres."""
    errors, _code = _lua(_body('interface:get("Menu").offset = vec2(0, 8)'))
    assert len(errors) == 1 and "list" in errors[0]


# ── La forme n'a demandé aucun chemin dédié ───────────────────────


def test_aucun_emetteur_dedie_pour_le_decalage_ni_les_verbes_d_image():
    """Une propriété se traduit par le getter/setter du catalogue, un verbe d'image par
    `fixed_args`. Si l'un d'eux apparaît un jour dans `_INVOKE_CUSTOM`, c'est que la forme
    a dérivé vers un cas particulier — et c'est le moment de se demander pourquoi."""
    from scripting import codegen
    for nom in ("image:play", "image:pause", "image.offset", "list:activate",
                "list:deactivate", "list:row"):
        assert nom not in codegen._INVOKE_CUSTOM


def test_le_domaine_porte_le_renommage():
    """Le NOM d'un élément ne se cite que dans `interface.get` : c'est son domaine qui fait
    suivre un renommage dans les scripts (`refactor.iter_refs`), sans liste de fonctions codée
    en dur — et qui vaut pour toute nature d'élément, un conteneur compris."""
    from scripting.refactor import iter_refs
    from scripting.api import DOMAIN_UI_ELEMENT
    src = _body('interface:get("Curseur").offset = vec2(0, 8)',
                'local m = interface:get("Menu")')
    refs = list(iter_refs(src, domain=DOMAIN_UI_ELEMENT))
    assert [r.value for r in refs] == ["Curseur", "Menu"]


# ── Les deux contextes de compilation ─────────────────────────────


@pytest.mark.parametrize("fn", ["ui_image_set_state", "ui_image_state", "ui_image_play",
                                "ui_list_element", "ui_image_element", "ui_region_element"])
def test_la_fonction_est_vue_des_deux_contextes(fn):
    """`main.c` voit `gba_engine.h` ; une unité d'acteur ou de scène voit le prototype GÉNÉRÉ dans
    `runtime_api.h` (A2, « 4e lecteur »). Ce qui est dans le moteur et exposé est extrait et émis
    automatiquement — y compris les conversions d'élément (`RefType.to_base`), qu'aucune entrée
    du catalogue ne nomme."""
    from codegen.runtime_codegen.api_prototypes import (
        build_prototype_block, exposed_engine_names,
    )
    moteur = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(encoding="utf-8")
    assert fn in moteur
    decls, _ = build_prototype_block(moteur, exposed_engine_names())
    assert any(f"extern " in d and f" {fn}(" in d for d in decls), \
        f"{fn} n'est pas repris par la génération de prototypes"


@pytest.mark.parametrize("fn", ["ui_image_move", "ui_image_dx", "ui_image_dy"])
def test_le_decalage_vec2_est_construit_dans_la_facade(fn):
    """Le moteur tient le décalage en deux entiers ; `Vec2` n'existe que côté scripts. La
    conversion vit dans `runtime_api_inline.h`, avec les trois prototypes dont elle dépend —
    plus aucune entrée du catalogue ne les nomme, donc la génération ne les émet plus."""
    facade = (REPO_DIR / "runtime" / "include" / "runtime_api_inline.h").read_text(encoding="utf-8")
    assert f" {fn}(" in facade
    assert "Vec2 ui_image_offset(int img)" in facade
    assert "void ui_image_set_offset(int img, Vec2 v)" in facade


def test_le_decalage_est_remis_a_zero_entre_deux_scenes():
    """`ui_images_reset` ferme les images de la scène précédente. Sans les deux
    champs, revenir dans un menu retrouverait le curseur là où on l'avait
    laissé, alors que tout le reste de la scène repart de sa mise en page."""
    moteur = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(encoding="utf-8")
    debut = moteur.index("void ui_images_reset(void)")
    corps = moteur[debut: moteur.index("\n}", debut)]
    assert "dx" in corps and "dy" in corps
