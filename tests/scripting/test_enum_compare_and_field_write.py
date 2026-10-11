"""Deux écritures qui n'avaient pas de forme correcte jusqu'ici :

  - un export `enum` se compare et s'affecte par son ÉTIQUETTE
    (`team == "RED"`). Le C recevait la chaîne : la comparaison d'un entier à
    un pointeur, donc toujours fausse, sans un mot du checker ;
  - un champ d'une propriété composée s'écrit (`self.position.x = 5`), le
    codegen lisant la valeur, changeant la composante, puis la réécrivant.
"""
from __future__ import annotations

import pytest


def _lua(src: str):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"]))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    return [e.message for e in errors if e.level == "error"], code


ENUM = ('exports = {\n'
        '  team = { type = "enum", default = "RED", values = {"RED", "BLUE", "GREEN"} },\n'
        '}\n')


def _enum_script(body: str) -> str:
    return ENUM + f"function on_update()\n  {body}\nend\n"


# ── Comparaison et affectation d'un enum ─────────────────────────

@pytest.mark.parametrize("body, attendu", [
    ('if team == "RED" then self:show() end',    "(team == 0)"),
    ('if team == "GREEN" then self:show() end',  "(team == 2)"),
    ('if team ~= "BLUE" then self:show() end',   "(team != 1)"),
    ('if "BLUE" == team then self:show() end',   "(team == 1)"),
])
def test_un_enum_se_compare_par_son_etiquette(body, attendu):
    errs, code = _lua(_enum_script(body))
    assert errs == []
    assert attendu in code
    assert '"RED"' not in code and '"BLUE"' not in code, "l'étiquette ne doit plus partir en C"


def test_un_enum_s_affecte_par_son_etiquette():
    errs, code = _lua(_enum_script('team = "BLUE"'))
    assert errs == []
    assert "team = 1;" in code


def test_une_etiquette_inconnue_est_refusee_et_les_valides_sont_nommees():
    errs, _ = _lua(_enum_script('if team == "PURPLE" then self:show() end'))
    assert any("PURPLE" in e and "RED, BLUE, GREEN" in e for e in errs), errs
    errs, _ = _lua(_enum_script('team = "PURPLE"'))
    assert any("PURPLE" in e for e in errs), errs


def test_un_enum_se_compare_toujours_par_son_index():
    errs, code = _lua(_enum_script('if team == 1 then self:show() end'))
    assert errs == []
    assert "(team == 1)" in code


# ── Écriture d'un champ de propriété composée ────────────────────

def test_un_champ_de_position_s_ecrit():
    errs, code = _lua("function on_update()\n  self.position.x = 5\nend\n")
    assert errs == []
    assert "_field.x = 5;" in code
    assert "actor_set_position(self, _field)" in code


def test_un_champ_s_ecrit_depuis_sa_propre_valeur():
    errs, code = _lua("function on_update()\n"
                      "  self.position.y = self.position.y + 1\nend\n")
    assert errs == []
    assert "_field.y = " in code


def test_un_champ_inconnu_reste_refuse():
    errs, _ = _lua("function on_update()\n  self.position.z = 5\nend\n")
    assert any("no field 'z'" in e for e in errs), errs


def test_un_champ_d_une_propriete_en_lecture_seule_reste_refuse():
    errs, _ = _lua("function on_update()\n  scene.size.x = 5\nend\n")
    assert any("read-only" in e for e in errs), errs


def test_un_champ_de_rect_s_ecrit_avec_w_et_h():
    errs, code = _lua("function on_update()\n"
                      "  camera.bound.w = 200\n  camera.bound.h = 120\nend\n")
    assert errs == []
    assert "_field.w = 200;" in code and "_field.h = 120;" in code
    assert "camera_set_bounds(_field)" in code


@pytest.mark.parametrize("body, attendu", [
    ('self.position.x = "a"',        "assign it an integer"),
    ("self.position.x = vec2(1, 2)", "assign it an integer"),
    ("self.position.x.y = 3",        "is a number"),
])
def test_un_champ_de_composante_n_accepte_qu_un_entier(body, attendu):
    errs, _ = _lua(f"function on_update()\n  {body}\nend\n")
    assert any(attendu in e for e in errs), errs
