"""Un récepteur CHAÎNÉ (`actor:get("Foe").velocity`, `interface:get("X"):show()`) se
traduit comme le même récepteur tenu dans un `local`.

Deux défauts que `test_checker_holes` ne voyait pas, parce qu'il ne juge que le
checker :

1. `interface:get("Cursor"):show()` passait le checker et disparaissait du C — un
   commentaire `/* invoke sur expression complexe ignoré */` à la place de l'appel.
   Aucun test ne lisait le C de cette forme.
2. Une PROPRIÉTÉ chaînée (`actor:get("Foe").velocity = …`) sautait les getters et
   setters : `resolve_prop` exigeait un nom, donc le codegen retombait sur un accès
   de champ brut (`runtime_get_actor(…).velocity`), que le checker acceptait et que
   gcc refuse sur une ligne que l'auteur n'a pas écrite.

Le contrat (ROADMAP v0.16, « Amendement du 2026-09-24 ») : la forme chaînée n'est pas
une forme de second rang. Elle donne le MÊME C que via un `local`, ou elle est
refusée par le checker — jamais ignorée, jamais du C invalide.
"""

from __future__ import annotations

import pytest


def _ctx_kw():
    return dict(actor_names=["Foe"], sfx_names=["Bip"], box_tag_names=["hb"],
                element_names=["Cursor"])


def _check(body: str, **kw):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    src = f"function on_update()\n{body}\nend\n"
    return check(parse(src), BuildContext(actor_name="Cam", **{**_ctx_kw(), **kw}))


def _errors(body: str, **kw) -> list[str]:
    return [e.message for e in _check(body, **kw) if e.level == "error"]


def _c_body(body: str) -> list[str]:
    """Les lignes C émises pour le corps de `on_update`."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext
    src = f"function on_update()\n{body}\nend\n"
    ctx = CodegenContext(actor_name="Cam", actor_sym="Cam", anim_names=[],
                         sfx_names=["Bip"], music_names=[], global_names=set(),
                         const_names=set(), all_actor_syms=["Foe"],
                         element_names=["Cursor"])
    code, _, _ = generate(parse(src), ctx)
    start = code.find("Cam_on_update(Actor* self) {")
    return [ln.strip() for ln in code[start:].split("\n}")[0].splitlines()[1:]
            if ln.strip()]


# (forme chaînée, forme via un local, le récepteur C que le local tient)
_FOE = "runtime_get_actor(ACTORNAME_FOE)"
_BOX = "actor_get_box(self, BOXTAG_HB)"

PARITY = [
    pytest.param('actor:get("Foe"):move_to(vec2(1, 2), 2)',
                 'local a = actor:get("Foe")\na:move_to(vec2(1, 2), 2)',
                 _FOE, "a", id="methode-acteur"),
    pytest.param('local p = actor:get("Foe").position',
                 'local a = actor:get("Foe")\nlocal p = a.position',
                 _FOE, "a", id="lecture-propriete-acteur"),
    pytest.param('actor:get("Foe").velocity = vec2(1, 0)',
                 'local a = actor:get("Foe")\na.velocity = vec2(1, 0)',
                 _FOE, "a", id="ecriture-propriete-acteur"),
    pytest.param('self:collision_box("hb").solid = false',
                 'local b = self:collision_box("hb")\nb.solid = false',
                 _BOX, "b", id="ecriture-propriete-boite"),
    pytest.param('local s = self:collision_box("hb").solid',
                 'local b = self:collision_box("hb")\nlocal s = b.solid',
                 _BOX, "b", id="lecture-propriete-boite"),
    pytest.param('interface:get("Cursor"):show()',
                 'local m = interface:get("Cursor")\nm:show()',
                 "UIELEM_CURSOR", "m", id="methode-element-interface"),
    pytest.param('interface:get("Cursor"):hide()',
                 'local m = interface:get("Cursor")\nm:hide()',
                 "UIELEM_CURSOR", "m", id="methode-element-interface-cacher"),
]


@pytest.mark.parametrize("chained, local, receiver_c, name", PARITY)
def test_la_forme_chainee_donne_le_meme_c_que_le_local(chained, local, receiver_c, name):
    """Le C de la forme chaînée est celui du `local`, le nom du local remplacé par
    l'expression qu'il tenait. Un seul chemin de traduction pour les deux formes."""
    via_local = _c_body(local)
    # La déclaration du local (`Actor* a = …;` / `int b = …;`) disparaît : c'est
    # elle que le chaînage supprime. Ce qui reste est l'usage, où le nom vaut son C.
    usage = [ln for ln in via_local if not ln.endswith(f" {name} = {receiver_c};")]
    expected = [ln.replace(f"({name}", f"({receiver_c}") for ln in usage]
    assert _c_body(chained) == expected


@pytest.mark.parametrize("chained, local, receiver_c, name", PARITY)
def test_une_forme_chainee_acceptee_n_est_jamais_ignoree_ni_du_c_brut(
        chained, local, receiver_c, name):
    """Le checker accepte : le C doit donc dire quelque chose. Ni commentaire
    « ignoré », ni accès de champ brut sur le récepteur (`….solid = 0`)."""
    assert _errors(chained) == []
    for ln in _c_body(chained):
        assert "/*" not in ln, ln
        assert f"{receiver_c}." not in ln, ln


def test_un_element_d_interface_chaine_emet_l_appel():
    """La régression d'origine, en clair : `interface:get("Cursor"):show()`."""
    assert _c_body('interface:get("Cursor"):show()') == ["ui_element_show(UIELEM_CURSOR, 1);"]


def test_un_champ_compose_se_lit_sur_une_propriete_chainee():
    """`.x` se compose sur le résultat du getter, comme sur un nom."""
    assert _c_body('local px = actor:get("Foe").position.x') == [
        f"int px = actor_get_position({_FOE}).x;"]


def test_une_comparaison_de_domaine_sur_recepteur_chaine():
    """`actor:get("Foe").direction == "west"` passe par la porte NOMMÉE du getter,
    comme `self.direction == "west"` — pas par un Vec2 comparé à une chaîne."""
    (ligne,) = _c_body('if actor:get("Foe").direction == "west" then\n'
                       '    self:destroy()\nend')[:1]
    assert f"actor_get_dir({_FOE})" in ligne and "DIR_WEST" in ligne


# ── Ce que le checker refuse, au lieu de le laisser traverser ─────────────

def test_ecrire_une_propriete_chainee_en_lecture_seule_est_refuse():
    assert any("read-only" in m for m in _errors('self:collision_box("hb").tag = "x"'))


def test_une_propriete_chainee_recoit_le_type_de_sa_valeur():
    """`velocity` est un vec2 : lui donner un scalaire est jugé comme sur un nom."""
    assert any("vec2" in m for m in _errors('actor:get("Foe").velocity = 3'))


def test_un_champ_inconnu_sur_une_reference_chainee_est_refuse():
    (msg,) = _errors('local x = self:collision_box("hb").bogus')
    assert "bogus" in msg and "collision_box" in msg


def test_un_recepteur_chaine_de_type_inconnu_est_refuse():
    """`math.abs(1):foo()` : le codegen n'a rien à émettre. Refusé, pas ignoré."""
    assert any("cannot be called" in m for m in _errors("math.abs(1):foo()"))


def test_une_methode_inconnue_sur_un_acteur_chaine_est_refusee():
    assert any("Unknown method" in m for m in _errors('actor:get("Foe"):bogus()'))


def test_une_methode_inconnue_sur_une_reference_chainee_est_refusee():
    assert any("Unknown method" in m for m in _errors('sfx:play("Bip"):bogus()'))


def test_l_enfant_d_un_prefab_reste_un_recepteur_valide():
    """`self.bras:play_anim(...)` — le récepteur que la v0.23 a livré ne doit pas
    tomber sous le refus des récepteurs chaînés."""
    assert _errors('self.bras:destroy()', child_names=["bras"]) == []
