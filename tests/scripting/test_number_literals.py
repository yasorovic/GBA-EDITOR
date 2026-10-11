"""Les littéraux numériques, jugés à l'écriture plutôt qu'au `make` ou jamais :

  - hors de 32 bits : gcc le tronquait (au mieux un avertissement) ;
  - à virgule (`1.5`) : tronqué vers zéro sans un mot ;
  - diviseur nul (`x / 0`, `x % 0`) : sur GBA la division est une fonction de
    libgcc qui NE s'arrête PAS — elle rend INT_MAX / INT_MIN, un nombre faux.
    (Mesuré sur `__divsi3` / `__modsi3` de devkitARM : `cmp r1, #0` puis un
    retour de 0x7fffffff / 0x80000000 selon le signe du dividende, jamais de
    boucle ni de BIOS.)
"""
from __future__ import annotations

import pytest


def _diags(src: str):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    return check(parse(src), BuildContext(actor_name="Ball", anim_names=["idle"]))


def _errors(src):
    return [d.message for d in _diags(src) if d.level == "error"]


def _warnings(src):
    return [d.message for d in _diags(src) if d.level == "warning"]


def _in_handler(body: str, head: str = "local count = 0\nlocal d = 3\n") -> str:
    return f"{head}function on_update()\n  {body}\nend\n"


# ── Hors de 32 bits ──────────────────────────────────────────────

@pytest.mark.parametrize("literal", ["99999999999", "2147483648", "-2147483649", "-99999999999"])
def test_un_litteral_hors_de_32_bits_est_refuse(literal):
    errs = _errors(_in_handler(f"count = {literal}"))
    assert any("does not fit in an integer" in e for e in errs), errs


@pytest.mark.parametrize("literal", ["2147483647", "-2147483648", "0", "-1", "0x7fffffff"])
def test_les_bornes_de_32_bits_restent_valides(literal):
    assert _errors(_in_handler(f"count = {literal}")) == []


def test_un_litteral_hors_bornes_dans_un_tableau_ou_en_tete_est_refuse():
    assert any("does not fit" in e for e in _errors(_in_handler("count = 1", "local big = 99999999999\n")))
    assert any("does not fit" in e for e in _errors(_in_handler("count = 1", "local t = {1, 99999999999}\n")))


# ── À virgule ────────────────────────────────────────────────────

def test_un_litteral_a_virgule_avertit_de_sa_troncature():
    warns = _warnings(_in_handler("count = 1.5"))
    assert any("1.5 is truncated to 1" in w for w in warns), warns
    assert _errors(_in_handler("count = 1.5")) == []


def test_la_troncature_se_fait_vers_zero_pour_un_negatif():
    warns = _warnings(_in_handler("count = -1.5"))
    assert any("-1.5 is truncated to -1" in w for w in warns), warns


def test_un_litteral_a_virgule_dans_un_tableau_ou_en_tete_avertit():
    assert any("truncated" in w for w in _warnings(_in_handler("count = 1", "local t = {1.5, 2}\n")))
    assert any("truncated" in w for w in _warnings(_in_handler("count = 1", "local x = 2.5\n")))


@pytest.mark.parametrize("literal", ["1.0", "1e3", "0x10", "100", "2.0"])
def test_un_litteral_entier_sous_une_autre_forme_n_avertit_pas(literal):
    assert _warnings(_in_handler(f"count = {literal}")) == []


# ── Diviseur nul ─────────────────────────────────────────────────

@pytest.mark.parametrize("body, mot", [
    ("count = d / 0",    "division by zero"),
    ("count = d % 0",    "modulo by zero"),
    ("count = 7 / 0",    "division by zero"),
    ("count = d / 0.5",  "division by zero"),     # 0.5 est tronqué à 0
])
def test_un_diviseur_nul_ecrit_en_clair_est_refuse(body, mot):
    errs = _errors(_in_handler(body))
    assert any(mot in e for e in errs), errs


def test_le_message_dit_ce_que_fait_vraiment_la_console():
    errs = _errors(_in_handler("count = d / 0"))
    assert any("does not stop" in e for e in errs), errs
    assert not any("BIOS" in e or "freeze" in e for e in errs), errs


@pytest.mark.parametrize("body", [
    "count = d / 2",
    "count = d % 3",
    "count = d / count",         # diviseur calculé : non jugé
    "count = 0 / d",             # dividende nul : valide
])
def test_une_division_ordinaire_reste_valide(body):
    assert _errors(_in_handler(body)) == []
