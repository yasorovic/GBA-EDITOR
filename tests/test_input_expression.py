"""Le parseur pur du mini-langage d'input (ROADMAP : « Les inputs personnalisés »).

Une seule grammaire, une seule table de mouvements : ces tests couvrent
l'accord (`+`), la séquence (`-`), les mouvements built-in et leur expansion,
les mouvements personnalisés (sans cycle possible), l'alternance bornée
`(a|b)`, et les erreurs situées par colonne — jamais un silence.
"""
from __future__ import annotations

import pytest

from core.models.input_expression import (
    InputExpressionError,
    compile_movement,
    parse_input_expression,
)


def _steps(text, custom_movements=None):
    exprs = parse_input_expression(text, custom_movements)
    assert len(exprs) == 1, exprs
    return [set(s.buttons) for s in exprs[0].steps]


def _alternatives(text, custom_movements=None):
    exprs = parse_input_expression(text, custom_movements)
    return [[set(s.buttons) for s in e.steps] for e in exprs]


# ── Grammaire de base ────────────────────────────────────────────────

def test_bouton_seul():
    assert _steps("a") == [{"a"}]


def test_accord():
    assert _steps("down + a") == [{"down", "a"}]
    assert _steps("down+a") == [{"down", "a"}]  # espaces libres


def test_sequence_double_appui():
    exprs = parse_input_expression("right - right")
    assert len(exprs) == 1
    expr = exprs[0]
    assert expr.is_sequence
    assert [set(s.buttons) for s in expr.steps] == [{"right"}, {"right"}]


def test_accord_ne_tient_pas_de_second_pas():
    expr = parse_input_expression("down + a")[0]
    assert not expr.is_sequence


# ── Mouvements built-in ──────────────────────────────────────────────

def test_quarter_circle_right():
    assert _steps("quarter_circle_right") == [{"down"}, {"down", "right"}, {"right"}]


def test_quarter_circle_left_est_le_miroir():
    assert _steps("quarter_circle_left") == [{"down"}, {"down", "left"}, {"left"}]


def test_half_circle_right():
    assert _steps("half_circle_right") == [
        {"left"}, {"down", "left"}, {"down"}, {"down", "right"}, {"right"},
    ]


def test_dragon_punch_right():
    assert _steps("dragon_punch_right") == [{"right"}, {"down"}, {"down", "right"}]


def test_mouvement_plus_bouton_rejoint_le_dernier_pas():
    assert _steps("quarter_circle_right + a") == [
        {"down"}, {"down", "right"}, {"right", "a"},
    ]


def test_mouvement_doit_etre_en_tete():
    with pytest.raises(InputExpressionError) as exc:
        parse_input_expression("a + quarter_circle_right")
    assert "premier atome" in exc.value.message


def test_mouvement_au_milieu_dune_sequence_refuse():
    with pytest.raises(InputExpressionError):
        parse_input_expression("a - quarter_circle_right")


# ── Mouvements personnalisés ─────────────────────────────────────────

def test_mouvement_personnalise():
    custom = {"my_move": "down - right"}
    assert _steps("my_move + a", custom) == [{"down"}, {"right", "a"}]


def test_mouvement_personnalise_ne_peut_pas_referencer_un_mouvement():
    with pytest.raises(InputExpressionError):
        compile_movement("broken", "quarter_circle_right - a")


def test_mouvement_personnalise_ne_peut_pas_ecraser_un_built_in():
    with pytest.raises(InputExpressionError):
        parse_input_expression("a", {"quarter_circle_right": "down - right"})


def test_mouvement_personnalise_refuse_alternance():
    with pytest.raises(InputExpressionError):
        compile_movement("broken", "(a|b) - down")


# ── Alternance bornée ────────────────────────────────────────────────

def test_alternance_simple():
    alts = _alternatives("(a|b) + down")
    assert alts == [[{"a", "down"}], [{"b", "down"}]]


def test_alternance_dans_une_sequence():
    alts = _alternatives("(a|b) - down")
    assert alts == [[{"a"}, {"down"}], [{"b"}, {"down"}]]


def test_alternance_bornee_a_quatre_branches():
    with pytest.raises(InputExpressionError):
        parse_input_expression("(a|b|l|r|start)")


def test_alternance_imbriquee_refusee():
    with pytest.raises(InputExpressionError):
        parse_input_expression("((a|b)|l)")


def test_trop_dalternatives_au_total_refuse():
    with pytest.raises(InputExpressionError):
        parse_input_expression("(a|b) + (l|r) + (start|select)")


# ── Erreurs situées ──────────────────────────────────────────────────

def test_nom_inconnu_situe_la_colonne():
    with pytest.raises(InputExpressionError) as exc:
        parse_input_expression("down + xyzzy")
    assert exc.value.column == "down + ".__len__() + 1


def test_caractere_inattendu():
    with pytest.raises(InputExpressionError):
        parse_input_expression("a ? b")


def test_jeton_final_inattendu():
    with pytest.raises(InputExpressionError):
        parse_input_expression("a +")


def test_parenthese_non_fermee():
    with pytest.raises(InputExpressionError):
        parse_input_expression("(a|b")
