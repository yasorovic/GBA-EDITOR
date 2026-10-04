"""ui/script_editor/lua_editor.py — coloration syntaxique Lua + widget d'édition."""
from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt, QRegularExpression

from scripting import completion
from ui.common.theme import C, T
from .completer import ScriptCompleter

class LuaHighlighter(QSyntaxHighlighter):

    # Mots-clés et modules ne sont plus tenus à la main : ils DÉRIVENT du même
    # catalogue que l'autocomplétion (`scripting.completion`). L'ancienne liste
    # colorait encore `display`/`send`, disparus de l'API, et ignorait la moitié
    # des modules vivants — la source unique supprime la dérive (cf. ROADMAP
    # v0.27). `self` s'y ajoute : c'est le récepteur, pas un module du catalogue.
    _KEYWORDS = completion.KEYWORDS
    _API_MODULES = ("self", *completion.MODULES)

    def __init__(self, doc):
        super().__init__(doc)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        def fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:   f.setFontWeight(700)
            if italic: f.setFontItalic(True)
            return f

        kw_fmt = fmt(C.SYNTAX_KEYWORD, bold=True)
        for word in self._KEYWORDS:
            self._rules.append((QRegularExpression(rf"\b{word}\b"), kw_fmt))

        api_fmt = fmt(C.SYNTAX_API)
        for word in self._API_MODULES:
            self._rules.append((QRegularExpression(rf"\b{word}\b"), api_fmt))

        self._rules.append((QRegularExpression(r"\b0x[0-9a-fA-F]+\b|\b\d+\.?\d*\b"),
                            fmt(C.SYNTAX_NUMBER)))
        self._str_fmt = fmt(C.SYNTAX_STRING)
        self._rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), self._str_fmt))
        self._rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), self._str_fmt))
        self._cmt_fmt = fmt(C.SYNTAX_COMMENT, italic=True)
        self._rules.append((QRegularExpression(r"--[^\n]*"), self._cmt_fmt))

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ─── Éditeur de code ──────────────────────────────────────────────────

class LuaEditor(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont(T.CODE, T.LG)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            f"QPlainTextEdit{{"
            f"  background:{C.BG_RAISED}; color:{C.TEXT_HI};"
            f"  border:none; padding:4px;"
            f"}}"
        )
        self.setTabStopDistance(32)
        self._hl = LuaHighlighter(self.document())
        self._completer = ScriptCompleter(self)

    def set_completion_context(self, context: str):
        """Le type de script (actor/scene/behavior/camera) — ce qui filtre les
        handlers proposés. Posé par l'écran à l'ouverture d'un fichier."""
        self._completer.set_context(context)

    def set_completion_project_names(self, names):
        """{domaine → noms du projet} pour la complétion des arguments chaîne.
        Posé par l'écran quand le projet est chargé."""
        self._completer.set_project_names(names)

    _TAB_WIDTH = 4   # largeur d'un niveau d'indentation écrit en espaces

    def _selected_lines(self) -> tuple[int, int]:
        """(première, dernière) ligne touchées par la sélection, ou la ligne du curseur.
        Une sélection qui se termine au tout début d'une ligne ne touche pas cette ligne."""
        cur = self.textCursor()
        doc = self.document()
        first = doc.findBlock(cur.selectionStart()).blockNumber()
        last_block = doc.findBlock(cur.selectionEnd())
        if cur.hasSelection() and cur.selectionEnd() == last_block.position()                 and last_block.blockNumber() > first:
            last_block = last_block.previous()
        return first, last_block.blockNumber()

    def indent_selection(self) -> bool:
        """`Tab` sur une sélection de PLUSIEURS lignes : ajoute une tabulation en tête de
        chacune, la sélection est conservée. Rend False (rien fait) quand la sélection
        tient sur une ligne ou n'existe pas : `Tab` y insère une tabulation, comme d'habitude."""
        first, last = self._selected_lines()
        if not self.textCursor().hasSelection() or first == last:
            return False
        cur = self.textCursor()
        doc = self.document()
        cur.beginEditBlock()
        for n in range(first, last + 1):
            if doc.findBlockByNumber(n).text():       # une ligne vide reste vide
                QTextCursor(doc.findBlockByNumber(n)).insertText("	")
        cur.endEditBlock()
        return True

    def unindent_selection(self):
        """`Maj+Tab` : retire UN niveau d'indentation de la ligne du curseur, ou de
        chaque ligne touchée par la sélection. Un niveau est une tabulation, ou à
        défaut jusqu'à `_TAB_WIDTH` espaces de tête ; une ligne sans indentation
        reste telle quelle. Un seul geste d'annulation pour l'ensemble."""
        cur = self.textCursor()
        doc = self.document()
        first, last = self._selected_lines()
        cur.beginEditBlock()
        for n in range(first, last + 1):
            block = doc.findBlockByNumber(n)
            text = block.text()
            if text.startswith("	"):
                removed = 1
            else:
                removed = min(len(text) - len(text.lstrip(" ")), self._TAB_WIDTH)
            if removed:
                edit = QTextCursor(block)
                edit.movePosition(QTextCursor.MoveOperation.Right,
                                  QTextCursor.MoveMode.KeepAnchor, removed)
                edit.removeSelectedText()
        cur.endEditBlock()

    def insert_newline_keeping_indent(self):
        """Retour à la ligne qui CONSERVE l'indentation de la ligne courante —
        sans ça, `Entrée` ramène le curseur tout à gauche. Reproduit le blanc de
        tête (espaces/tabulations) de la ligne, rien de plus : garder
        l'indentation courante, pas en ajouter un niveau après `then`/`do`.

        Le point unique du retour à la ligne : l'éditeur l'appelle quand le popup
        est fermé, le completer quand il est ouvert sans sélection — pour que les
        deux indentent pareil."""
        cur = self.textCursor()
        line = cur.block().text()
        indent = line[:len(line) - len(line.lstrip(" \t"))]
        cur.insertText("\n" + indent)
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    # ── Autocomplétion ─────────────────────────────────────────────
    # Les touches du popup OUVERT (Tab, Entrée, Échap, ↑/↓) sont tenues par le
    # filtre du completer sur sa liste — le popup capte le clavier quand il est
    # visible, donc elles n'arrivent pas ici. Cette méthode ne gère que
    # l'ouverture à la demande et le re-déclenchement au fil de la frappe.
    def keyPressEvent(self, event):
        comp = self._completer
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) \
                and event.key() == Qt.Key.Key_Space:
            comp.maybe_complete(force=True)      # Ctrl+Espace
            return

        # `Tab` sur plusieurs lignes sélectionnées : indente chacune (popup fermé).
        if event.key() == Qt.Key.Key_Tab and not (event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier))                 and self.indent_selection():
            comp.hide()
            return

        # `Maj+Tab` (popup fermé — ouvert, c'est le filtre du completer qui l'a) :
        # désindente. Qt le livre comme `Key_Backtab`.
        if event.key() == Qt.Key.Key_Backtab:
            self.unindent_selection()
            comp.hide()
            return

        # `Entrée` (popup fermé — ouvert, c'est le filtre du completer qui l'a) :
        # retour à la ligne en conservant l'indentation courante.
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return) \
                and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                              | Qt.KeyboardModifier.AltModifier)):
            self.insert_newline_keeping_indent()
            comp.hide()
            return

        super().keyPressEvent(event)
        # Un déplacement pur ferme le popup et ne le relance pas.
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                           Qt.Key.Key_Home, Qt.Key.Key_End,
                           Qt.Key.Key_Up, Qt.Key.Key_Down):
            comp.hide()
            return
        comp.maybe_complete()

    def jump_to_function(self, func_name: str):
        doc = self.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            if f"function {func_name}" in block.text():
                cur = QTextCursor(block)
                cur.movePosition(QTextCursor.MoveOperation.NextBlock)
                cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cur)
                self.ensureCursorVisible()
                return

    def goto_line(self, line: int):
        """Place le curseur sur la ligne `line` (1-indexée) et la centre.

        Sert au saut depuis le journal de build (`fichier.lua:ligne` cliqué).
        Une ligne hors plage retombe sur la dernière — un message peut citer une
        ligne au-delà de la fin sur un fichier tronqué."""
        doc = self.document()
        block = doc.findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            block = doc.lastBlock()
        cur = QTextCursor(block)
        cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
        self.setTextCursor(cur)
        self.centerCursor()
        self.setFocus()

    def insert_at_cursor(self, text: str):
        """Insère text à la position courante du curseur."""
        cur = self.textCursor()
        cur.insertText(text)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        self.setFocus()

    def insert_stub(self, stub: str):
        """Insère un stub en fin de document, saute au corps."""
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if not self.toPlainText().endswith("\n"):
            cur.insertText("\n")
        cur.insertText("\n" + stub)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
