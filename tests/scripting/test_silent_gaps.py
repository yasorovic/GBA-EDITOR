"""Six fautes que le checker laissait passer SANS un mot, et dont le C produit
était faux (relevé par un banc d'essai de scripts fautifs) :

  - `a, b = b, a` : la seconde cible disparaissait, l'échange devenait `a = b`
    (désormais traduit en affectations simples ; seul `a, b = 1` est refusé) ;
  - deux `function on_update()` : le second corps était ignoré ;
  - une chaîne comme opérande (`other_box == "x"`, `n + "a"`, `f | "A"`) : le C
    comparait ou additionnait un pointeur ;
  - `function on_updat()` : devenait une fonction privée que personne n'appelle ;
  - `for i = 1, 10, 0` : boucle infinie ;
  - un export `enum` sans étiquettes, avec un doublon ou un défaut absent.

Chaque cas a son contre-exemple VALIDE, pour que le refus ne déborde pas.
"""
from __future__ import annotations

import pytest


def _errors(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Ball", anim_names=["idle"]))
    return [e.message for e in errs if e.level == "error"]


def _in_handler(body: str, head: str = "local a = 1\nlocal b = 2\n") -> str:
    return f"{head}function on_update()\n  {body}\nend\n"


# ── Affectation multiple ─────────────────────────────────────────

def test_un_echange_a_b_egal_b_a_est_valide():
    assert _errors(_in_handler("a, b = b, a")) == []
    assert _errors(_in_handler("a, b = 0, b + 1")) == []


def test_un_echange_lit_les_valeurs_avant_d_affecter():
    """La seconde cible ne disparaît plus, et la valeur lue est l'ANCIENNE :
    `a, b = b, a` passe par un local caché, déclaré avant toute écriture."""
    from scripting.parser import parse, StmtAssign, StmtLocalAssign, ExprName
    body = parse(_in_handler("a, b = b, a")).functions[0].body
    assert [type(s) for s in body] == [StmtLocalAssign, StmtAssign, StmtAssign]
    tmp, first, second = body
    assert tmp.value == ExprName("a")
    assert (first.target, first.value) == (ExprName("a"), ExprName("b"))
    assert (second.target, second.value) == (ExprName("b"), ExprName(tmp.name))


def test_des_constantes_n_ont_pas_besoin_de_local_cache():
    from scripting.parser import parse, StmtAssign
    body = parse(_in_handler("a, b = 0, 1")).functions[0].body
    assert [type(s) for s in body] == [StmtAssign, StmtAssign]


def test_c_un_echange_emis_echange_vraiment(tmp_path):
    """Sonde native : le C réellement émis pour `on_update` est compilé et
    exécuté. Échange d'entiers, valeur calculée sur les ANCIENNES valeurs,
    échange de composantes d'un vec2."""
    import subprocess
    from native_toolchain import compilateur_hote, environnement
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    cc = compilateur_hote()
    if cc is None:
        pytest.skip("aucun compilateur C hôte")
    src = ("local a = 1\nlocal b = 2\nlocal c = 0\nlocal d = 0\nlocal p = vec2(3, 4)\n"
           "function on_update(self)\n"
           "  a, b = b, a\n"
           "  c, d = 10, c + a\n"
           "  p.x, p.y = p.y, p.x\n"
           "end\n")
    code, _, _ = generate(parse(src), CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    debut = code.index("static int a")
    fin = code.index("}", code.index("void Ball_on_update(Actor* self) {")) + 1
    sonde = ("#include <assert.h>\n#include <stddef.h>\n"
             "typedef struct { int x, y; } Vec2;\ntypedef struct Actor Actor;\n"
             + code[debut:fin] +
             "\nint main(void) {\n  Ball_on_update(NULL);\n"
             "  assert(a == 2 && b == 1);\n  assert(c == 10 && d == 2);\n"
             "  assert(p.x == 4 && p.y == 3);\n  return 0;\n}\n")
    (tmp_path / "probe.c").write_text(sonde, encoding="utf-8")
    binaire = tmp_path / "probe"
    build = subprocess.run([cc, "-std=gnu11", "-O0", "-o", str(binaire), str(tmp_path / "probe.c")],
                           capture_output=True, text=True, env=environnement(cc))
    assert build.returncode == 0, build.stderr + sonde
    run = subprocess.run([str(binaire)], capture_output=True, text=True, env=environnement(cc))
    assert run.returncode == 0, run.stderr + sonde


def test_un_nombre_de_valeurs_inegal_est_refuse():
    errs = _errors(_in_handler("a, b = 1"))
    assert any("multiple assignment" in e and "as many values" in e for e in errs), errs


def test_une_affectation_simple_et_un_local_multiple_restent_valides():
    assert _errors(_in_handler("a = b")) == []
    assert _errors(_in_handler("local x, y = 1, 2")) == []


# ── Fonctions en double ──────────────────────────────────────────

def test_deux_handlers_de_meme_nom_sont_refuses():
    errs = _errors("local a = 0\nfunction on_update()\n  a = 1\nend\n"
                   "function on_update()\n  a = 2\nend\n")
    assert any("defined twice" in e and "on_update" in e for e in errs), errs


def test_deux_fonctions_differentes_restent_valides():
    assert _errors("local a = 0\nfunction on_start()\n  a = 1\nend\n"
                   "function on_update()\n  a = 2\nend\n") == []


# ── Noms d'événement ─────────────────────────────────────────────

@pytest.mark.parametrize("name, suggestion", [
    ("on_updat",   "on_update"),
    ("onUpdate",   "on_update"),
    ("OnUpdate",   "on_update"),
    ("on_update_", "on_update"),
])
def test_un_nom_d_evenement_mal_ecrit_est_refuse_avec_la_correction(name, suggestion):
    errs = _errors(f"local a = 0\nfunction {name}()\n  a = 1\nend\n")
    assert any(f"`{suggestion}`" in e for e in errs), errs


def test_une_fonction_privee_ordinaire_et_une_sequence_restent_valides():
    assert _errors("local a = 0\nfunction compute(x)\n  return x\nend\n"
                   "function on_update()\n  a = compute(1)\nend\n") == []
    assert _errors("local a = 0\nfunction on_sequence_intro()\n  wait(10)\n  a = 1\nend\n"
                   "function on_update()\nend\n") == []


# ── Chaîne comme opérande ────────────────────────────────────────

@pytest.mark.parametrize("body", [
    'if a == "x" then a = 2 end',
    'a = a + "x"',
    'a = a | "A"',
    'if a ~= "x" then a = 2 end',
    'if a and "x" then a = 2 end',
])
def test_une_chaine_n_est_pas_un_operande(body):
    errs = _errors(_in_handler(body))
    assert any("string cannot be an operand" in e for e in errs), errs


def test_le_message_nomme_l_operateur_tel_qu_il_est_ecrit():
    errs = _errors(_in_handler('if a ~= "x" then a = 2 end'))
    assert any("operand of '~='" in e for e in errs), errs


def test_les_comparaisons_par_nom_restent_valides():
    # propriété à nom
    assert _errors(_in_handler('if self.direction == "west" then a = 2 end')) == []
    # étiquette d'enum
    head = ('exports = {\n  t = { type = "enum", default = "R", values = {"R", "B"} },\n}\n')
    assert _errors(_in_handler('if t == "R" then t = "B" end', head)) == []


# ── Pas de boucle nul ────────────────────────────────────────────

def test_un_pas_nul_est_refuse_et_les_pas_valides_non():
    assert any("never moves" in e for e in _errors(_in_handler("for i = 1, 10, 0 do a = i end")))
    assert _errors(_in_handler("for i = 1, 10, 2 do a = i end")) == []
    assert _errors(_in_handler("for i = 10, 1, -1 do a = i end")) == []


# ── Exports ──────────────────────────────────────────────────────

def _export(decl: str) -> str:
    return f"exports = {{\n  {decl},\n}}\nfunction on_update()\nend\n"


@pytest.mark.parametrize("decl, attendu", [
    ('e = { type = "enum", default = "A" }',                             "needs its labels"),
    ('e = { type = "enum", default = "A", values = {} }',                "needs its labels"),
    ('e = { type = "enum", default = "A", values = {"A", "A"} }',        "appears twice"),
    ('e = { type = "enum", default = "X", values = {"A", "B"} }',        "is not one of its labels"),
    ('e = { type = "int", default = "x" }',                             "takes a number"),
])
def test_un_export_incoherent_est_refuse(decl, attendu):
    errs = _errors(_export(decl))
    assert any(attendu in e for e in errs), errs


def test_des_exports_coherents_restent_valides():
    assert _errors(_export('e = { type = "enum", default = "A", values = {"A", "B"} }')) == []
    assert _errors(_export('n = { type = "int", default = 3 }')) == []
