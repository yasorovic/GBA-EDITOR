"""Les opérateurs bit à bit de Lua 5.3 (`& | ~ << >> ~a`) se traduisent terme à
terme en C. Leur piège est la PRÉCÉDENCE : `a & 1 == 0` se lit `a & (1 == 0)` en
Lua mais `(a & 1) == 0` en C. Le codegen parenthèse chaque opération, donc le C
émis garde le sens de la source Lua.
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


def _handler(body: str) -> str:
    return f"local flags = 0\nfunction on_update()\n  {body}\nend\n"


@pytest.mark.parametrize("body, attendu", [
    ("flags = flags | 2",        "flags = (flags | 2);"),
    ("flags = flags & 6",        "flags = (flags & 6);"),
    ("flags = flags ~ 1",        "flags = (flags ^ 1);"),
    ("flags = flags << 2",       "flags = bits_shl(flags, 2);"),
    ("flags = flags >> 1",       "flags = bits_shr(flags, 1);"),
    ("flags = ~flags",           "flags = (~flags);"),
    ("flags = flags & ~4",       "flags = (flags & (~4));"),
])
def test_un_operateur_binaire_se_traduit_en_c(body, attendu):
    errs, code = _lua(_handler(body))
    assert errs == []
    assert attendu in code


def test_le_xor_n_est_pas_confondu_avec_different_de():
    errs, code = _lua(_handler("if flags ~= 1 then flags = flags ~ 1 end"))
    assert errs == []
    assert "(flags != 1)" in code and "(flags ^ 1)" in code


def test_la_precedence_de_lua_est_gardee_dans_le_c():
    """`flags & 1 ~= 0` : en Lua 5.3 les comparaisons lient plus bas que `&`, donc
    c'est `(flags & 1) ~= 0` — et le C parenthésé doit dire la même chose. Un C
    non parenthésé lirait `flags & (1 != 0)`."""
    errs, code = _lua(_handler("if flags & 1 ~= 0 then flags = 0 end"))
    assert errs == []
    assert "((flags & 1) != 0)" in code


def test_un_decalage_se_compose_avec_l_addition_comme_en_lua():
    """En Lua, `+` lie plus fort que `<<` : `1 << 2 + 1` vaut `1 << 3`."""
    errs, code = _lua(_handler("flags = 1 << 2 + 1"))
    assert errs == []
    assert "bits_shl(1, (2 + 1))" in code


def test_un_vecteur_n_est_pas_un_operande_binaire():
    errs, _ = _lua("function on_update()\n  local v = vec2(1, 2)\n  local r = v & 1\nend\n")
    assert errs, "un vec2 ne se combine pas bit à bit"


# ── Calé sur l'ARM : un entier a 32 bits ─────────────────────────

@pytest.mark.parametrize("count", ["32", "40", "-1"])
def test_un_decalage_litteral_hors_de_0_a_31_est_refuse(count):
    errs, _ = _lua(_handler(f"flags = flags << {count}"))
    assert any("32 bits" in e for e in errs), errs
    errs, _ = _lua(_handler(f"flags = flags >> {count}"))
    assert any("32 bits" in e for e in errs), errs


@pytest.mark.parametrize("count", ["0", "1", "31"])
def test_un_decalage_litteral_de_0_a_31_est_accepte(count):
    errs, _ = _lua(_handler(f"flags = flags << {count}"))
    assert errs == []


def test_un_decalage_a_compte_variable_passe_par_les_fonctions_definies():
    """Un compte inconnu au build ne peut pas être jugé : c'est le runtime qui
    le rend sûr (0 au-delà de 31), pas un `<<` nu indéfini en C."""
    errs, code = _lua("local n = 3\nlocal flags = 0\n"
                      "function on_update()\n  flags = flags >> n\nend\n")
    assert errs == []
    assert "bits_shr(flags, n)" in code


def test_les_helpers_de_decalage_existent_dans_le_runtime_et_sont_logiques():
    from pathlib import Path
    header = (Path(__file__).resolve().parents[2] / "runtime" / "include"
              / "runtime_api_inline.h").read_text(encoding="utf-8")
    assert "static inline int bits_shl" in header
    # `>>` logique : passe par unsigned, sinon le C propage le signe.
    assert "(int)((unsigned)a >> n)" in header
