"""`Maj+Tab` dans l'éditeur de script : retire un niveau d'indentation."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor

from ui.script_editor.lua_editor import LuaEditor


def _shift_tab(editor: LuaEditor):
    editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backtab,
                                   Qt.KeyboardModifier.ShiftModifier))


def test_maj_tab_retire_un_niveau_sur_la_ligne_du_curseur(qapp):
    e = LuaEditor()
    e.setPlainText("a\n\tb\n    c\n")
    cur = e.textCursor()
    cur.setPosition(3)                       # sur la ligne `\tb`
    e.setTextCursor(cur)
    _shift_tab(e)
    assert e.toPlainText() == "a\nb\n    c\n"


def test_maj_tab_desindente_toute_la_selection_en_un_geste_annulable(qapp):
    e = LuaEditor()
    e.setPlainText("a\n\tb\n    c\n  d\n\t\te\n")
    cur = e.textCursor()
    cur.setPosition(0)
    cur.setPosition(len(e.toPlainText()), QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(cur)
    _shift_tab(e)
    assert e.toPlainText() == "a\nb\nc\nd\n\te\n"   # un niveau seulement : `\t\te` garde un `\t`
    e.undo()
    assert e.toPlainText() == "a\n\tb\n    c\n  d\n\t\te\n"


def _tab(editor: LuaEditor):
    editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab,
                                   Qt.KeyboardModifier.NoModifier, "	"))   # une vraie frappe porte son texte


def test_tab_sur_plusieurs_lignes_indente_chacune_et_garde_la_selection(qapp):
    e = LuaEditor()
    e.setPlainText("a\n\nb\nc\n")
    cur = e.textCursor()
    cur.setPosition(0)
    cur.setPosition(4, QTextCursor.MoveMode.KeepAnchor)      # de `a` jusqu'à `b` inclus
    e.setTextCursor(cur)
    _tab(e)
    assert e.toPlainText() == "\ta\n\n\tb\nc\n"              # la ligne vide reste vide
    assert e.textCursor().hasSelection()
    _shift_tab(e)
    assert e.toPlainText() == "a\n\nb\nc\n"                  # Tab puis Maj+Tab : aller-retour


def test_tab_sans_selection_multiligne_insere_une_tabulation(qapp):
    e = LuaEditor()
    e.setPlainText("ab")
    cur = e.textCursor()
    cur.setPosition(1)
    e.setTextCursor(cur)
    _tab(e)
    assert e.toPlainText() == "a\tb"
