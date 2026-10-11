"""Quatre diagnostics qui envoyaient l'auteur chercher la mauvaise faute :

  - « missing `end` » répondait à TOUT ce qui ne pouvait pas suivre `return`
    (le code après un `return`) et à une annotation de type (`local x: int`) ;
    antlr attend `end` à chaque endroit où seul `end` suit, mais ce n'est un
    `end` oublié que lorsque le jeton fautif est la fin du fichier ;
  - une récursion directe était dite deux fois ;
  - `team == RED` suggérait `local RED = 0` pour une étiquette d'`enum` ;
  - un type d'export inconnu répondait « not applied at build yet ».
"""
from __future__ import annotations

import pytest


def _syntax_error(src: str):
    from scripting.parser import parse
    with pytest.raises(Exception) as caught:
        parse(src)
    return caught.value


def _errors(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Ball", anim_names=["idle"]))
    return [e.message for e in errs if e.level == "error"]


def _in_handler(body: str) -> str:
    return f"function on_update()\n{body}\nend\n"


# ── « missing end » n'est dit que pour une fin de fichier ─────────

def test_un_end_vraiment_oublie_garde_son_message():
    exc = _syntax_error("function on_update()\n  if true then\nend\n")
    assert "missing `end`" in str(exc)


def test_le_code_apres_un_return_est_nomme_et_situe_sur_le_return():
    exc = _syntax_error(_in_handler("  return\n  local a = 1"))
    assert "`return` must be the last statement" in str(exc)
    assert "missing `end`" not in str(exc)
    assert exc.line == 2


def test_un_return_avec_valeur_suivi_de_code_est_traite_de_meme():
    exc = _syntax_error(_in_handler("  return 5\n\n  local a = 1"))
    assert "`return` must be the last statement" in str(exc)


def test_un_jeton_inattendu_dans_un_bloc_est_nomme():
    exc = _syntax_error(_in_handler("  if true then\n  )\n  end"))
    assert "unexpected `)`" in str(exc)
    assert "missing `end`" not in str(exc)


def test_une_annotation_de_type_est_expliquee():
    exc = _syntax_error(_in_handler("  local x: int = 3"))
    assert "no type annotations" in str(exc) and "local x = 3" in str(exc)
    assert "missing `end`" not in str(exc)


def test_un_return_en_fin_de_bloc_et_un_appel_de_methode_restent_valides():
    from scripting.parser import parse
    parse(_in_handler("  local a = 1\n  return"))
    parse(_in_handler("  if true then return end\n  local p = self:collision_box(\"b\")"))


# ── Récursion ────────────────────────────────────────────────────

def test_une_recursion_directe_n_est_dite_qu_une_fois():
    src = ("local c = 0\nfunction f(n)\n  if n > 0 then f(n - 1) end\nend\n"
           "function on_update()\n  f(3)\nend\n")
    errs = [e for e in _errors(src) if "Recursion" in e]
    assert len(errs) == 1, errs


def test_une_recursion_mutuelle_montre_son_chemin():
    src = ("local c = 0\nfunction f(n)\n  g(n)\nend\nfunction g(n)\n  f(n)\nend\n"
           "function on_update()\n  f(3)\nend\n")
    errs = [e for e in _errors(src) if "Recursion" in e]
    assert len(errs) == 1 and "f → g → f" in errs[0], errs


def test_deux_fonctions_qui_s_appellent_sans_cycle_restent_valides():
    src = ("local c = 0\nfunction f(n)\n  return g(n)\nend\nfunction g(n)\n  return n\nend\n"
           "function on_update()\n  c = f(3)\nend\n")
    assert [e for e in _errors(src) if "Recursion" in e] == []


# ── Étiquette d'enum nue ─────────────────────────────────────────

ENUM = 'exports = {\n  team = { type = "enum", default = "RED", values = {"RED", "BLUE"} },\n}\n'


def test_une_etiquette_d_enum_sans_guillemets_dit_comment_l_ecrire():
    errs = _errors(ENUM + _in_handler("  if team == RED then end"))
    assert any('label of the enum export "team"' in e and 'team == "RED"' in e for e in errs), errs
    assert not any("local RED" in e for e in errs), errs


def test_un_nom_inconnu_ordinaire_garde_son_avertissement():
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    diags = check(parse(_in_handler("  ghost = 1")), BuildContext(actor_name="Ball"))
    assert any(d.level == "warning" and "refers to nothing" in d.message for d in diags)


# ── Type d'export inconnu ────────────────────────────────────────

def test_un_type_d_export_inconnu_est_une_erreur_avec_la_correction():
    errs = _errors('exports = {\n  a = { type = "integer", default = 1 },\n}\n' + _in_handler(""))
    assert any("unknown type 'integer'" in e and "Did you mean 'int'" in e for e in errs), errs
    assert not any("not applied at build yet" in e for e in errs), errs


def test_les_types_connus_restent_valides():
    for typ, default in (("int", "1"), ("bool", "false"), ("float", "1")):
        assert _errors(f'exports = {{\n  a = {{ type = "{typ}", default = {default} }},\n}}\n'
                       + _in_handler("")) == []
