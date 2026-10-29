"""La table clavier du popup d'autocomplétion (v0.27) — un comportement décidé,
donc verrouillé :

    ↑ / ↓    sélectionnent (la première flèche active le premier item)
    Tab      valide — la sélection active, ou le PREMIER item si aucune (passive)
    Entrée   valide la sélection ACTIVE ; sinon insère une nouvelle ligne
    Échap    ferme le popup

Et pas de popup automatique en début de ligne — `Tab` y indente alors, faute de
popup à qui la touche revienne.
"""
from __future__ import annotations

from PyQt6.QtGui import QTextCursor, QKeyEvent
from PyQt6.QtCore import Qt, QEvent


def _at_end(ed):
    cur = ed.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    ed.setTextCursor(cur)


def _armed(qapp, text: str):
    """Un éditeur avec son popup ouvert — sans sélection active (état réel à
    l'ouverture, cf. `_nav_active`)."""
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.set_completion_context("actor")
    ed.setPlainText(text)
    _at_end(ed)
    ed._completer.maybe_complete(force=True)
    return ed, ed._completer


def _press(comp, key):
    ev = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    return comp.eventFilter(comp._qc.popup(), ev)


def test_pas_de_popup_auto_en_debut_de_ligne(qapp):
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.set_completion_context("actor")
    ed.setPlainText("function f()\n")          # nouvelle ligne, rien de tapé
    _at_end(ed)
    ed._completer.maybe_complete(force=False)  # frappe normale, pas Ctrl+Espace
    # Aucun popup : la touche `Tab` revient à l'éditeur, qui l'utilise pour
    # indenter (comportement natif de QPlainTextEdit).
    assert not ed._completer.popup_visible()


def test_entree_sans_navigation_insere_une_ligne(qapp):
    ed, comp = _armed(qapp, "function on_update()\n    self:pl")
    assert _press(comp, Qt.Key.Key_Return) is True
    assert not comp.popup_visible()
    # Rien accepté ; nouvelle ligne qui conserve l'indentation (quatre espaces).
    assert ed.toPlainText() == "function on_update()\n    self:pl\n    "


def test_entree_conserve_lindentation_popup_ferme(qapp):
    from PyQt6.QtGui import QKeyEvent
    from ui.script_editor.lua_editor import LuaEditor
    ed = LuaEditor()
    ed.set_completion_context("actor")
    ed.setPlainText("function f()\n    local x = 1")
    _at_end(ed)
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                               Qt.KeyboardModifier.NoModifier))
    assert ed.toPlainText() == "function f()\n    local x = 1\n    "


def test_fleche_puis_entree_valide_la_selection(qapp):
    ed, comp = _armed(qapp, "function on_update()\n    self:pl")
    _press(comp, Qt.Key.Key_Down)             # active le premier item
    assert comp._nav_active
    assert _press(comp, Qt.Key.Key_Return) is True
    assert not comp.popup_visible()
    assert ed.toPlainText().splitlines()[-1] == "    self:play_anim"


def test_tab_valide_le_premier_item_sans_navigation(qapp):
    # Popup ouvert, aucune flèche : `Tab` valide passivement le premier item.
    ed, comp = _armed(qapp, "function on_update()\n    self:pl")
    assert _press(comp, Qt.Key.Key_Tab) is True
    assert not comp.popup_visible()
    assert ed.toPlainText().splitlines()[-1] == "    self:play_anim"


def test_tab_valide_la_selection_active(qapp):
    # Après une flèche (premier item activé), `Tab` valide cet item.
    ed, comp = _armed(qapp, "function on_update()\n    self:pl")
    _press(comp, Qt.Key.Key_Down)
    assert comp._nav_active
    assert _press(comp, Qt.Key.Key_Tab) is True
    assert ed.toPlainText().splitlines()[-1] == "    self:play_anim"


def test_echap_ferme_sans_changer(qapp):
    ed, comp = _armed(qapp, "function on_update()\n    self:pl")
    before = ed.toPlainText()
    assert _press(comp, Qt.Key.Key_Escape) is True
    assert not comp.popup_visible()
    assert ed.toPlainText() == before
