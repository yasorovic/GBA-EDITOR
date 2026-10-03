"""`;` et les instructions hors fonction (correctif du 2026-10-03).

Deux trous voisins, trouvés par un `; ADFZ` écrit en fin de ligne :

- `local vitesse = 2; ADFZ = 5` en tête de fichier, ou `end; ADFZ()` après le
  dernier handler : le parse réussissait, `convert_chunk` « ignorait les autres
  statements top-level », et le build passait sans un mot. Elles sont désormais
  PORTÉES (`LuaScript.stray_statements`) et refusées par le checker.
- `;` seul ne produisait aucun nœud connu : le checker le refusait avec le nom
  interne `SemiColon`, alors que `lua_subset` le déclare ACCEPTED. C'est un
  séparateur, il ne produit rien.

Et une faute de syntaxe donne toujours SA ligne, même quand antlr n'en rend pas.
"""
from __future__ import annotations

import pytest

from scripting.checker import BuildContext, check
from scripting.parser import LuaParseError, parse


def _errors(src: str) -> list[str]:
    ctx = BuildContext(actor_name="A", owner_kind="actor")
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


# ── `;` est un séparateur ─────────────────────────────────────────


@pytest.mark.parametrize("src", [
    "function on_update()\n  local a = 1;\nend\n",
    "function on_update()\n  local a = 1; local b = 2\nend\n",
    "function on_update()\n  ;\nend\n",
    "local vitesse = 2;\nfunction on_update()\nend;\n",
])
def test_un_point_virgule_ne_produit_rien(src):
    assert _errors(src) == []


def test_le_point_virgule_ne_laisse_pas_de_noeud_dans_le_corps():
    script = parse("function on_update()\n  local a = 1;\nend\n")
    assert len(script.functions[0].body) == 1


# ── Une instruction hors fonction ne passe plus sous silence ─────


@pytest.mark.parametrize("src, ligne", [
    ("local vitesse = 2; ADFZ = 5\nfunction on_update()\nend\n", 1),
    ("local vitesse = 2; ADFZ()\nfunction on_update()\nend\n", 1),
    ("function on_update()\nend; ADFZ = 1\n", 2),
    ("if true then ADFZ = 1 end\nfunction on_update()\nend\n", 1),
])
def test_une_instruction_de_tete_est_refusee_sur_sa_ligne(src, ligne):
    [err] = [e for e in check(parse(src), BuildContext(actor_name="A", owner_kind="actor"))
             if e.level == "error"]
    assert err.line == ligne                       # la ligne est un champ, pas un bout de texte
    assert "outside any function" in err.message


def test_les_formes_legitimes_de_tete_ne_sont_pas_refusees():
    """`local`, `exports = {…}`, les fonctions et le `return M` d'un module."""
    src = ("local vitesse = 2\n"
           "exports = { force = { default = 3, type = \"int\" } }\n"
           "function on_update()\nend\n")
    assert _errors(src) == []
    module = "local M = {}\nfunction M.f(a)\nend\nreturn M\n"
    assert parse(module).stray_statements == []


# ── Une faute de syntaxe dit toujours où ─────────────────────────


@pytest.mark.parametrize("src, ligne, jeton", [
    ("function on_update()\n  local x = 1; ADFZ\nend\n", 2, "ADFZ"),
    ("function on_update()\n  self:foo(); ADFZ\nend\n", 2, "ADFZ"),
    ("local vitesse = 2; ADFZ\nfunction on_update()\nend\n", 1, "ADFZ"),
    ("function on_update()\nend\nADFZ\n", 3, "ADFZ"),
])
def test_une_faute_de_syntaxe_donne_sa_ligne_et_son_jeton(src, ligne, jeton):
    with pytest.raises(LuaParseError) as exc:
        parse(src)
    assert exc.value.line == ligne
    assert jeton in str(exc.value)


def test_un_caractere_illegal_est_nomme():
    with pytest.raises(LuaParseError) as exc:
        parse("function on_update()\n  local x = 1 @\nend\n")
    assert exc.value.line == 2
    assert "@" in str(exc.value)
