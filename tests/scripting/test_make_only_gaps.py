"""Fautes que le checker laissait passer et que seul le `make` découvrait, sur une
ligne de C GÉNÉRÉ plutôt que sur la ligne du script :

  - un `vec2` / `rect` comme condition, `-v`, `~v` : le C refuse une struct ;
  - un composite dans un entier (ou l'inverse), un tableau comme valeur ;
  - `break` hors d'une boucle, `return 5` dans un handler `void` ;
  - `on_update(dt)` : `dt` n'existe pas dans le C.

Chaque cas a son contre-exemple VALIDE.
"""
from __future__ import annotations

import pytest


def _errors(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Ball", anim_names=["idle"]))
    return [e.message for e in errs if e.level == "error"]


HEAD = "local count = 0\nlocal pos = vec2(0, 0)\n"


def _in_handler(body: str, head: str = HEAD) -> str:
    return f"{head}function on_update()\n  {body}\nend\n"


# ── Composite utilisé comme un nombre ────────────────────────────

@pytest.mark.parametrize("body, attendu", [
    ("local v = vec2(1, 2)\n  if v then count = 1 end",            "is not a condition"),
    ("local v = vec2(1, 2)\n  if not v then count = 1 end",        "is not a condition"),
    ("local v = vec2(1, 2)\n  while v do count = 1 end",           "is not a condition"),
    ("local r = rect(0, 0, 1, 1)\n  if r then count = 1 end",      "a rect is not a condition"),
    ("local v = vec2(1, 2)\n  local r = -v",                       "cannot be negated"),
    ("local v = vec2(1, 2)\n  local r = ~v",                       "only works on integers"),
])
def test_un_composite_n_est_ni_une_condition_ni_un_operande_unaire(body, attendu):
    errs = _errors(_in_handler(body))
    assert any(attendu in e for e in errs), errs


def test_un_composite_se_teste_par_un_champ():
    assert _errors(_in_handler("local v = vec2(1, 2)\n  if v.x ~= 0 then count = 1 end")) == []
    assert _errors(_in_handler("if count then count = 0 end")) == []


# ── Composite et entier mélangés à l'affectation ─────────────────

def test_un_composite_dans_un_entier_est_refuse():
    errs = _errors(_in_handler("count = vec2(1, 2)"))
    assert any("`count` holds an integer" in e for e in errs), errs
    errs = _errors(_in_handler("count = pos"))
    assert any("`count` holds an integer" in e for e in errs), errs


def test_un_entier_litteral_dans_un_composite_est_refuse():
    errs = _errors(_in_handler("pos = 5"))
    assert any("`pos` holds a vec2" in e for e in errs), errs


def test_un_composite_d_un_autre_type_est_refuse():
    errs = _errors(_in_handler("pos = vec3(1, 2, 3)"))
    assert any("`pos` holds a vec2" in e and "vec3" in e for e in errs), errs


def test_les_affectations_de_meme_nature_restent_valides():
    assert _errors(_in_handler("count = count + 1")) == []
    assert _errors(_in_handler("pos = vec2(3, 4)")) == []
    assert _errors(_in_handler("pos = self.position")) == []
    assert _errors(_in_handler("pos = pos + vec2(1, 1)")) == []
    assert _errors(_in_handler("count = pos.x")) == []


def test_un_nom_de_local_reutilise_avec_un_autre_type_n_est_pas_juge():
    """`v` est un entier dans un handler et un vec2 dans l'autre : le nom ne dit
    rien de sûr, et le checker ne conclut pas."""
    src = ("function on_start()\n  local v = 1\n  v = 2\nend\n"
           "function on_update()\n  local v = vec2(1, 2)\n  v = vec2(3, 4)\nend\n")
    assert _errors(src) == []


# ── Tableau ──────────────────────────────────────────────────────

def test_un_tableau_n_est_pas_une_valeur():
    errs = _errors(_in_handler("local t = {1, 2}\n  count = t"))
    assert any("is an array" in e and "t[i]" in e for e in errs), errs
    errs = _errors(_in_handler("local t = {1, 2}\n  t = 5"))
    assert any("is an array" in e for e in errs), errs


def test_un_element_de_tableau_reste_valide():
    assert _errors(_in_handler("local t = {1, 2}\n  count = t[1]\n  t[2] = count")) == []


# ── break / return ───────────────────────────────────────────────

def test_break_hors_boucle_est_refuse_et_dans_une_boucle_non():
    assert any("only valid inside a loop" in e for e in _errors(_in_handler("break")))
    assert any("only valid inside a loop" in e
               for e in _errors(_in_handler("if count > 0 then break end")))
    assert _errors(_in_handler("while count < 3 do count = count + 1 break end")) == []
    assert _errors(_in_handler("for i = 1, 3 do if i == 2 then break end end")) == []


def test_un_break_apres_une_boucle_est_refuse():
    errs = _errors(_in_handler("for i = 1, 3 do count = i end\n  break"))
    assert any("only valid inside a loop" in e for e in errs), errs


def test_return_avec_valeur_dans_un_handler_est_refuse():
    errs = _errors(_in_handler("return 5"))
    assert any("returns nothing" in e for e in errs), errs
    assert _errors(_in_handler("if count > 0 then return end")) == []


def test_return_avec_valeur_dans_une_fonction_privee_reste_valide():
    src = ("local count = 0\nfunction twice(n)\n  return n * 2\nend\n"
           "function on_update()\n  count = twice(2)\nend\n")
    assert _errors(src) == []


# ── Paramètres de handler ────────────────────────────────────────

@pytest.mark.parametrize("signature, mot", [
    ("on_update(dt)",                         "dt"),
    ("on_start(x)",                           "x"),
    ("on_collision_enter(a, b, c, d, e)",     "other, my_box, other_box"),
])
def test_un_parametre_que_le_moteur_ne_passe_pas_est_refuse(signature, mot):
    name = signature.split("(")[0]
    src = f"local count = 0\nfunction {signature}\n  count = 1\nend\n"
    errs = _errors(src)
    assert any("the engine does not pass" in e and mot in e for e in errs), (name, errs)


@pytest.mark.parametrize("signature", [
    "on_update()",
    "on_update(self)",
    "on_collision_enter(other)",
    "on_collision_enter(other, my_box, other_box)",
    "on_tile_collide(normal_x, normal_y)",
])
def test_les_parametres_offerts_restent_valides(signature):
    src = f"local count = 0\nfunction {signature}\n  count = 1\nend\n"
    assert _errors(src) == []
