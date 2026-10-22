"""Un argument du mauvais type est refusé, et le message dit ce que la fonction attend.

Le trou : `music_box:trigger(vec2)` passait le build. `_check_args` ne jugeait un paramètre à
domaine que si l'argument était une CHAÎNE littérale ; tout le reste (un nom nu, un nombre, un
vec2) « ne se lisait pas dans le source » et traversait sans un mot. Le C émis visait alors
une constante qui n'existe pas, ou pire, compilait.

Le contrôle est maintenant général : chaque type de paramètre du catalogue (`int`, `bool`,
`str`, `str_literal`, `actor`, `vec2`) a une règle, et le test de complétude parcourt le
catalogue entier pour qu'un nouveau type de paramètre ne puisse pas arriver sans règle.

La moitié qui compte autant : ce qui reste ACCEPTÉ. On n'accuse que ce qui est écrit en clair —
une variable, un appel, un calcul passent sans un mot.
"""
from __future__ import annotations

import pytest

from scripting.api import RUNTIME_API, module_call_form
from scripting.parser import parse
from scripting.checker import check, BuildContext, _PARAM_TYPE_RULES
from scripting.expr_types import VEC_CONSTRUCTORS


def _errors(body: str, **kw) -> list[str]:
    kw.setdefault("music_box_trigger_names", ["to_title"])
    kw.setdefault("actor_names", ["paddle"])
    src = f"local n = 0\nfunction on_start()\n    {body}\nend\n"
    return [m.message for m in check(parse(src), BuildContext(actor_name="T", **kw))
            if m.level == "error"]


# ── Le cas d'origine ────────────────────────────────────────────────────────

def test_constructeur_nu_en_argument_est_refuse():
    msgs = _errors("music_box:trigger(vec2)")
    assert any("`vec2` is a constructor" in m and "vec2(x, y)" in m for m in msgs), msgs


def test_constructeur_nu_ne_declenche_pas_deux_erreurs_pour_une_faute():
    assert len(_errors("music_box:trigger(vec2)")) == 1
    assert len(_errors("self:move(vec2, 3)")) == 1


@pytest.mark.parametrize("name", ["vec2", "vec3", "rect"])
def test_constructeur_nu_hors_appel_est_refuse(name):
    assert any(f"`{name}` is a constructor" in m for m in _errors(f"local v = {name}"))


def test_fonction_de_langage_nue_est_refusee():
    assert any("`dot` is a function" in m for m in _errors("local d = dot"))


def test_un_appel_de_constructeur_reste_valide():
    assert _errors("self:move(vec2(1, 2), 3)") == []


@pytest.mark.parametrize("arg", ["2", "n + 1"])
def test_actor_get_accepte_un_index(arg):
    assert _errors(f"local a = actor:get({arg})") == []


def test_un_local_peut_masquer_le_nom_du_constructeur():
    assert _errors("local vec2 = 3\n    self:move(self.position, vec2)") == []


# ── Un cas par type de paramètre ────────────────────────────────────────────

@pytest.mark.parametrize("call, expected, received", [
    ('music_box:trigger(5)',          'argument "trigger" expects a string',  "a number"),
    ('music_box:trigger(true)',       'expects a string',                     "a boolean"),
    ('music_box:trigger(nil)',        'expects a string',                     "nil"),
    ('music_box:trigger(vec2(1, 2))', 'expects a string',                     "a vec2"),
    ('music_box:trigger({1, 2})',     'expects a string',                     "a table"),
    ('self:move(5, "fast")',          'argument "speed" expects a number',    "a string"),
    ('self:move(vec2(1, 0), true)',   'argument "speed" expects a number',    "a boolean"),
    ('self:move(vec2(1, 0), nil)',    'argument "speed" expects a number',    "nil"),
    ('self:move(vec2(1, 0), vec2(1, 2))', 'argument "speed" expects a number', "a vec2"),
    ('self:move(vec2(1, 0), n > 2)',  'argument "speed" expects a number',    "a boolean"),
    ('self:move(5, 3)',               'argument "dir" expects a vec2',        "a number"),
    ('local hb = self:collision_box("body")\n    hb:overlaps(5)',
     'argument "other" expects an actor (or a collision box)',               "a number"),
    ('local hb = self:collision_box("body")\n    hb:overlaps("paddle")',
     'argument "other" expects an actor',                                    "a string"),
])
def test_message_dit_ce_que_la_fonction_attend(call, expected, received):
    msgs = _errors(call)
    assert any(expected in m and f"received {received}" in m for m in msgs), msgs


def test_le_message_nomme_la_fonction():
    msg = next(m for m in _errors("music_box:trigger(5)") if "expects" in m)
    assert msg.startswith("music_box:trigger(): "), msg


def test_parametre_bool_refuse_un_nombre():
    """`0` est VRAI en Lua : `set_tile_flip(0)` ne ferait pas ce qu'il laisse croire."""
    key = next(k for k, a in RUNTIME_API.items()
               if any(p.ptype == "bool" for p in a.params) and "." in k)
    module, fn = key.split(".")
    params = RUNTIME_API[key].params
    args = ", ".join("0" if p.ptype == "bool" else "1" for p in params)
    assert any("expects a boolean" in m for m in _errors(f"{module}:{fn}({args})"))


# ── Ce qui reste accepté ────────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    'music_box:trigger("to_title")',
    'self:move(vec2(1, 0), 3)',
    'self:move(vec2(1, 0), n)',                  # une variable : valeur inconnue du source
    'self:move(vec2(1, 0), n + 1)',              # un calcul
    'self:move(vec2(1, 0), math.abs(n))',        # un appel
    'self:move(self.position, 3)',               # une propriété vec2
    'local hb = self:collision_box("body")\n    hb:overlaps(self)',
    'local hb = self:collision_box("body")\n    hb:overlaps(paddle)',
    'local hb = self:collision_box("body")\n    hb:overlaps(actor:get("paddle"))',
])
def test_un_argument_bien_type_ou_inconnu_passe(call):
    assert _errors(call) == [], _errors(call)


# ── Complétude : tout le catalogue ──────────────────────────────────────────

_WRONG = {"int": '"x"', "bool": "7", "str": "5", "str_literal": "5", "actor": "5",
          "vec2": "5", "vec3": "5", "rect": "5"}


def test_chaque_type_de_parametre_du_catalogue_a_une_regle():
    """Un type de paramètre nouveau doit arriver avec sa règle, sinon il passerait tout."""
    used = {p.ptype for api in RUNTIME_API.values() for p in api.params}
    assert used <= set(_PARAM_TYPE_RULES) | set(VEC_CONSTRUCTORS), \
        used - set(_PARAM_TYPE_RULES) - set(VEC_CONSTRUCTORS)


def _judges(message: str, name: str) -> bool:
    """Le message vise ce paramètre : type attendu, ou — pour une énumération matérielle,
    qui a son message plus précis — « s'écrit par son nom »."""
    return (f'argument "{name}" expects' in message
            or f'argument "{name}" is written by its name' in message)


def _module_cases():
    for key, api in RUNTIME_API.items():
        if "." not in key or ":" in key or key == "actor.get":   # actor.get accepte aussi un index
            continue
        for i, p in enumerate(api.params):
            yield pytest.param(key, i, id=f"{key}[{p.name}:{p.ptype}]")


@pytest.mark.parametrize("key, index", list(_module_cases()))
def test_chaque_parametre_de_chaque_fonction_de_module_est_juge(key, index):
    api = RUNTIME_API[key]
    args = ["1"] * len(api.params)
    args[index] = _WRONG[api.params[index].ptype]
    msgs = _errors(f"{module_call_form(key)}({', '.join(args)})")
    name = api.params[index].name
    assert any(_judges(m, name) for m in msgs), (key, msgs)


def _method_cases():
    for key, api in RUNTIME_API.items():
        if not key.startswith("actor:"):
            continue
        for i, p in enumerate(api.params):
            yield pytest.param(key, i, id=f"{key}[{p.name}:{p.ptype}]")


@pytest.mark.parametrize("key, index", list(_method_cases()))
def test_chaque_parametre_de_chaque_methode_d_acteur_est_juge(key, index):
    api = RUNTIME_API[key]
    args = ["1"] * len(api.params)
    args[index] = _WRONG[api.params[index].ptype]
    msgs = _errors(f"self:{key.split(':', 1)[1]}({', '.join(args)})")
    name = api.params[index].name
    assert any(_judges(m, name) for m in msgs), (key, msgs)
