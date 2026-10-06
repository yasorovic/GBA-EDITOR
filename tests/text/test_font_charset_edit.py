"""Édition en bloc du charset — `SetCharsetCmd`.

Le charset n'est pas stocké (cf. `core.models.font`) : l'éditer d'un bloc est
une assignation POSITIONNELLE reversée sur les `Glyph.char`. Ces cas verrouillent
la règle « une case = un caractère » et l'annulation, y compris quand une
ligature est aplatie.
"""
from __future__ import annotations

from core.models.font import Font, Glyph
from ui.text_editor.text_commands import SetCharsetCmd


def _font(chars):
    return Font(glyphs=[Glyph(char=c) for c in chars])


def test_positional_assignment_and_flattens_ligature():
    f = _font(["A", "B", "...", "D"])   # la 3e case est une ligature
    SetCharsetCmd(f, "XYZ").execute()
    # caractère i → case i ; la ligature devient un seul caractère ; la case
    # au-delà de la chaîne garde le sien.
    assert [g.char for g in f.glyphs] == ["X", "Y", "Z", "D"]


def test_extra_characters_are_ignored():
    f = _font(["A", "B", "C"])
    SetCharsetCmd(f, "PQRSTUV").execute()   # plus de caractères que de cases
    assert f.charset == "PQR"


def test_undo_restores_including_ligature():
    f = _font(["A", "B", "...", "D"])
    cmd = SetCharsetCmd(f, "XYZ")
    cmd.execute()
    cmd.undo()
    assert [g.char for g in f.glyphs] == ["A", "B", "...", "D"]


def test_persist_fn_runs_on_execute_and_undo():
    f = _font(["A", "B"])
    calls = []
    cmd = SetCharsetCmd(f, "CD", persist_fn=lambda: calls.append(1))
    cmd.execute()
    cmd.undo()
    assert len(calls) == 2
