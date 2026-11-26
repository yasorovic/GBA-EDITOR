"""ui/script_editor/lua_editor.py : coloration syntaxique Lua + widget d'édition."""
import re

from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
from PyQt6.QtGui import (QColor, QFont, QPainter, QPolygon, QSyntaxHighlighter,
                         QTextCharFormat, QTextCursor, QTextFormat)
from PyQt6.QtCore import Qt, QPoint, QRect, QRegularExpression, QSize

from scripting import completion
from ui.common.theme import C, T
from .completer import ScriptCompleter

class LuaHighlighter(QSyntaxHighlighter):

    # Mots-clés et modules ne sont plus tenus à la main : ils DÉRIVENT du même
    # catalogue que l'autocomplétion (`scripting.completion`). L'ancienne liste
    # colorait encore `display`/`send`, disparus de l'API, et ignorait la moitié
    # des modules vivants — la source unique supprime la dérive. `self` s'y ajoute : c'est le récepteur, pas un module du catalogue.
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

    # Le début d'un commentaire : `--`, suivi ou non d'un crochet long
    # (`--[[`, `--[=[`, `--[==[`…). Le groupe capturé dit lequel des deux :
    # vide, le commentaire s'arrête en fin de ligne ; plein, il court jusqu'au
    # crochet fermant de MÊME niveau, des lignes plus bas s'il le faut.
    _LONG_COMMENT_OPEN = re.compile(r"--\[(=*)\[")

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        self._highlight_long_comment(text)

    def _highlight_long_comment(self, text: str):
        """Les commentaires `--[[ ]]`, qui traversent les lignes.

        Une règle d'expression régulière ne suffit pas : elle ne voit qu'une
        ligne à la fois. L'état du bloc porte donc le niveau du crochet ouvert
        (0 pour `--[[`, 1 pour `--[=[`…), et -1 quand rien ne reste ouvert ;
        une ligne qui commence dans un commentaire ouvert reprend l'état de la
        précédente. Le format s'applique APRÈS les règles ordinaires : dans un
        commentaire, un mot-clé ou un nombre n'est plus que du texte."""
        niveau = self.previousBlockState()
        self.setCurrentBlockState(-1)
        depart = 0
        while True:
            if niveau < 0:
                comment = self._comment_start(text, depart)
                if comment is None:
                    return
                depart, niveau, apres = comment
                if niveau is None:
                    self.setFormat(depart, len(text) - depart, self._cmt_fmt)
                    return
            else:
                apres = depart
            ferme = QRegularExpression(r"\]" + "=" * niveau + r"\]").match(text, apres)
            if not ferme.hasMatch():
                self.setFormat(depart, len(text) - depart, self._cmt_fmt)
                self.setCurrentBlockState(niveau)
                return
            self.setFormat(depart, ferme.capturedEnd() - depart, self._cmt_fmt)
            depart = ferme.capturedEnd()
            niveau = -1

    @classmethod
    def _comment_start(cls, text: str, start: int) -> tuple[int, int | None, int] | None:
        """Renvoie le premier commentaire Lua hors d'une chaîne citée."""
        quote = ""
        escaped = False
        index = start
        while index < len(text):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                index += 1
                continue
            if char in "\"'":
                quote = char
                index += 1
                continue
            if text.startswith("--", index):
                match = cls._LONG_COMMENT_OPEN.match(text, index)
                if match:
                    return index, len(match.group(1)), match.end()
                return index, None, len(text)
            index += 1
        return None


# ─── Marge des numéros de ligne ───────────────────────────────────────

class LineNumberArea(QWidget):
    """La marge gauche de l'éditeur. Elle ne sait rien : l'éditeur la mesure et
    la peint, car lui seul connaît la géométrie de ses blocs."""

    def __init__(self, editor: "LuaEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)

    def mousePressEvent(self, event):
        """La marge porte le repli : un clic sur la ligne d'une flèche ouvre ou
        ferme le bloc qu'elle commande. Une ligne qui n'ouvre rien ignore le clic."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._editor.gutter_clicked(int(event.position().y()))


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
            f"  background:{C.BG_INPUT}; color:{C.TEXT_HI};"
            f"  border:none; padding:4px;"
            f"}}"
        )
        self.setTabStopDistance(32)
        self._hl = LuaHighlighter(self.document())
        self._completer = ScriptCompleter(self)

        # La marge suit le nombre de lignes (sa largeur), le défilement (son
        # contenu) et le curseur (la ligne mise en avant).
        self._line_numbers = LineNumberArea(self)
        self.blockCountChanged.connect(self._reserve_line_number_width)
        self.updateRequest.connect(self._repaint_line_numbers)
        self.cursorPositionChanged.connect(self._line_numbers.update)
        self._reserve_line_number_width()

        # Replis ouverts (ancrés sur un curseur, donc suivant leur ligne quand
        # l'auteur écrit au-dessus) et ligne désignée par le journal de build.
        self._folds: list[QTextCursor] = []
        self._error_line: int | None = None
        self.textChanged.connect(self._on_document_edited)

    def set_completion_context(self, context: str):
        """Le type de script (actor/scene/behavior/camera) — ce qui filtre les
        handlers proposés. Posé par l'écran à l'ouverture d'un fichier."""
        self._completer.set_context(context)

    def set_completion_project_names(self, names):
        """{domaine → noms du projet} pour la complétion des arguments chaîne.
        Posé par l'écran quand le projet est chargé."""
        self._completer.set_project_names(names)

    # ── Marge des numéros de ligne ─────────────────────────────────
    _GUTTER_PAD = 8      # le blanc de part et d'autre des chiffres
    _FOLD_WIDTH = 14     # la colonne des flèches de repli, collée au code

    def line_number_width(self) -> int:
        """La largeur de la marge : le plus grand numéro affichable, plus la
        colonne des flèches de repli."""
        chiffres = len(str(max(1, self.blockCount())))
        return (2 * self._GUTTER_PAD + self._FOLD_WIDTH
                + self.fontMetrics().horizontalAdvance("9") * chiffres)

    def _reserve_line_number_width(self, _count: int = 0):
        """Le texte commence après la marge : c'est la marge du viewport qui la
        lui réserve, sans quoi les chiffres se peindraient par-dessus le code."""
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _repaint_line_numbers(self, rect, dy):
        if dy:
            self._line_numbers.scroll(0, dy)
        else:
            self._line_numbers.update(0, rect.y(), self._line_numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._reserve_line_number_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Posée sur la HAUTEUR DU VIEWPORT, pas sur celle du widget : la feuille
        # de style donne au cadre un rembourrage, et un numéro décalé de ces
        # quelques pixels ne désignerait plus sa ligne.
        viewport = self.viewport().geometry()
        self._line_numbers.setGeometry(QRect(self.contentsRect().left(), viewport.top(),
                                             self.line_number_width(), viewport.height()))

    def paint_line_numbers(self, event):
        """Les numéros des blocs visibles, alignés à droite. La ligne du curseur
        est la seule en clair : l'auteur retrouve où il est sans compter."""
        painter = QPainter(self._line_numbers)
        painter.fillRect(event.rect(), QColor(C.BG_PANEL))
        painter.setFont(self.font())
        courante = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        haut = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid() and haut <= event.rect().bottom():
            hauteur = self.blockBoundingRect(block).height()
            if block.isVisible() and haut + hauteur >= event.rect().top():
                painter.setPen(QColor(C.TEXT_NORM if block.blockNumber() == courante
                                      else C.TEXT_MUTED))
                painter.drawText(0, int(haut),
                                 self._line_numbers.width() - self._GUTTER_PAD - self._FOLD_WIDTH,
                                 int(hauteur),
                                 int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                                 str(block.blockNumber() + 1))
                if self.fold_end(block.blockNumber()) is not None:
                    self._paint_fold_marker(painter, haut, hauteur,
                                            self.is_folded(block.blockNumber()))
            block = block.next()
            haut += hauteur

    def _paint_fold_marker(self, painter: QPainter, haut: float, hauteur: float, ferme: bool):
        """Le triangle de la colonne de repli : vers le bas quand le bloc est
        ouvert, vers la droite quand il est fermé. Fermé, il est en clair :
        c'est le seul signe que du code manque à l'écran."""
        cote = 7
        cx = self._line_numbers.width() - self._FOLD_WIDTH / 2 - 2
        cy = haut + hauteur / 2
        if ferme:
            pts = [QPoint(int(cx - cote / 3), int(cy - cote / 2)),
                   QPoint(int(cx - cote / 3), int(cy + cote / 2)),
                   QPoint(int(cx + cote / 2), int(cy))]
        else:
            pts = [QPoint(int(cx - cote / 2), int(cy - cote / 3)),
                   QPoint(int(cx + cote / 2), int(cy - cote / 3)),
                   QPoint(int(cx), int(cy + cote / 2))]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C.TEXT_HI if ferme else C.TEXT_MUTED))
        painter.drawPolygon(QPolygon(pts))
        painter.restore()

    # ── Repli des blocs indentés ───────────────────────────────────
    # Un bloc est ce qu'OUVRE une ligne : les lignes suivantes plus indentées
    # qu'elle. Rien n'analyse la syntaxe Lua, l'indentation suffit, et elle vaut
    # pour `function`, `if`, `for` comme pour une table écrite sur plusieurs
    # lignes. La ligne d'en-tête reste visible, son corps disparaît.

    def _indent_of(self, text: str) -> int | None:
        """La profondeur d'indentation en colonnes, None pour une ligne blanche :
        une ligne vide au milieu d'un bloc n'en marque pas la fin."""
        if not text.strip():
            return None
        blanc = text[:len(text) - len(text.lstrip(" \t"))]
        return len(blanc.replace("\t", " " * self._TAB_WIDTH))

    def fold_end(self, line: int) -> int | None:
        """Le dernier bloc (0-indexé) du repli qu'ouvre `line`, ou None quand
        cette ligne n'ouvre rien. Les lignes blanches de la fin n'en font pas
        partie : replier ne doit pas avaler la respiration avant la suite."""
        doc = self.document()
        bloc = doc.findBlockByNumber(line)
        if not bloc.isValid():
            return None
        commentaire = self._long_comment_end(line)
        if commentaire is not None:
            return commentaire
        base = self._indent_of(bloc.text())
        if base is None:
            return None
        dernier, n = line, line + 1
        while n < doc.blockCount():
            indent = self._indent_of(doc.findBlockByNumber(n).text())
            if indent is None:
                n += 1
                continue
            if indent <= base:
                break
            dernier = n
            n += 1
        return dernier if dernier > line else None

    # `--`, suivi ou non d'un crochet long. Le même motif que le colorateur :
    # un `--` simple commente sa ligne, un `--[[` ouvre un bloc.
    def _long_comment_end(self, line: int) -> int | None:
        """Le dernier bloc d'un commentaire `--[[ ]]` ouvert par `line`, ou None.

        Un commentaire de plusieurs lignes se replie comme un bloc, alors qu'il
        n'indente rien : c'est souvent la plus longue chose à passer dans un
        fichier. Sans fermeture, la coloration reste ouverte pendant la frappe,
        mais il n'y a pas de bloc valide à replier."""
        doc = self.document()
        comment = LuaHighlighter._comment_start(doc.findBlockByNumber(line).text(), 0)
        if comment is None or comment[1] is None:
            return None
        _, niveau, apres = comment
        ferme = "]" + "=" * niveau + "]"
        if ferme in doc.findBlockByNumber(line).text()[apres:]:
            return None                     # ouvert et refermé sur sa ligne
        for n in range(line + 1, doc.blockCount()):
            if ferme in doc.findBlockByNumber(n).text():
                return n
        return None

    def folded_lines(self) -> set[int]:
        return {c.blockNumber() for c in self._folds}

    def is_folded(self, line: int) -> bool:
        return line in self.folded_lines()

    def toggle_fold(self, line: int) -> bool:
        return self.unfold(line) if self.is_folded(line) else self.fold(line)

    def fold(self, line: int) -> bool:
        fin = self.fold_end(line)
        if fin is None or self.is_folded(line):
            return False
        doc = self.document()
        for n in range(line + 1, fin + 1):
            doc.findBlockByNumber(n).setVisible(False)
        self._folds.append(QTextCursor(doc.findBlockByNumber(line)))
        # Le curseur ne reste pas dans ce qui vient de disparaître : il remonte
        # sur l'en-tête, sans quoi la frappe suivante écrirait à l'aveugle.
        if line < self.textCursor().blockNumber() <= fin:
            self.setTextCursor(QTextCursor(doc.findBlockByNumber(line)))
        self._after_fold_change(line, fin)
        return True

    def unfold(self, line: int) -> bool:
        if not self.is_folded(line):
            return False
        doc = self.document()
        fin = self.fold_end(line) or line
        self._folds = [c for c in self._folds if c.blockNumber() != line]
        n = line + 1
        while n <= fin:
            doc.findBlockByNumber(n).setVisible(True)
            # Un repli imbriqué garde le sien : rouvrir le parent ne rouvre pas
            # les enfants que l'auteur avait fermés.
            if self.is_folded(n):
                n = (self.fold_end(n) or n) + 1
            else:
                n += 1
        self._after_fold_change(line, fin)
        return True

    def unfold_all(self):
        doc = self.document()
        block = doc.firstBlock()
        while block.isValid():
            block.setVisible(True)
            block = block.next()
        self._folds.clear()
        self._after_fold_change(0, max(0, doc.blockCount() - 1))

    def reveal_line(self, line: int):
        """Ouvre ce qu'il faut pour que `line` se voie : un saut depuis le
        journal ne doit pas se perdre dans un repli."""
        doc = self.document()
        while doc.findBlockByNumber(line).isValid() \
                and not doc.findBlockByNumber(line).isVisible():
            parents = [n for n in self.folded_lines()
                       if n < line and (self.fold_end(n) or n) >= line]
            if not parents:
                self.unfold_all()    # caché sans repli connu : tout rouvrir
                return
            self.unfold(max(parents))

    def _after_fold_change(self, line: int, fin: int):
        doc = self.document()
        debut = doc.findBlockByNumber(line).position()
        bloc_fin = doc.findBlockByNumber(fin)
        doc.markContentsDirty(debut, bloc_fin.position() + bloc_fin.length() - debut)
        doc.documentLayout().requestUpdate()
        self.viewport().update()
        self._line_numbers.update()

    def _on_document_edited(self):
        """Le surlignage du journal désigne un état du texte : la première
        frappe l'invalide. Un repli dont le corps a disparu sous l'édition
        laisserait des lignes cachées sans flèche pour les rendre : tout
        rouvrir est la seule sortie sûre."""
        self.clear_error_line()
        if any(self.fold_end(line) is None for line in self.folded_lines()):
            self.unfold_all()

    def setPlainText(self, text: str):
        self._folds.clear()
        self._error_line = None
        super().setPlainText(text)

    def gutter_clicked(self, y: int):
        line = self._line_at(y)
        if line is not None:
            self.toggle_fold(line)

    def _line_at(self, y: int) -> int | None:
        """Le numéro du bloc peint à cette ordonnée du viewport, ou None."""
        block = self.firstVisibleBlock()
        haut = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid() and haut <= self.viewport().height():
            hauteur = self.blockBoundingRect(block).height()
            if block.isVisible() and haut <= y < haut + hauteur:
                return block.blockNumber()
            block = block.next()
            haut += hauteur
        return None

    # ── Ligne désignée par le journal de build ─────────────────────

    def highlight_error_line(self, line: int):
        """Surligne la ligne entière (0-indexée) que désigne le journal : le
        curseur dit où est le code, la bande dit laquelle des lignes à l'écran
        est en cause. Elle s'efface à la première frappe."""
        bloc = self.document().findBlockByNumber(line)
        if not bloc.isValid():
            return
        couleur = QColor(C.ACCENT_RED)
        couleur.setAlpha(48)
        fmt = QTextCharFormat()
        fmt.setBackground(couleur)
        fmt.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection = QTextEdit.ExtraSelection()
        selection.format = fmt
        curseur = QTextCursor(bloc)
        curseur.clearSelection()
        selection.cursor = curseur
        self._error_line = line
        self.setExtraSelections([selection])

    def clear_error_line(self):
        if self._error_line is None:
            return
        self._error_line = None
        self.setExtraSelections([])

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

    _BLOCK_OPEN = re.compile(
        r"^(?:(?:local\s+)?function\b(?!.*\bend\b).*|"
        r"(?:if|elseif)\b.*\bthen(?!.*\bend\b).*|"
        r"(?:for|while)\b.*\bdo(?!.*\bend\b).*|else|do)\s*$"
    )

    def insert_newline_keeping_indent(self):
        """Retour à la ligne avec l'indentation que la structure appelle.

        Le blanc de tête est conservé dans le cas courant. Après un ouvreur Lua
        (`then`, `do`, `function`, `else`), l'éditeur ajoute un niveau pour que
        l'auteur écrive directement le corps. Entrée n'ajoute pas de `end` :
        elle ne doit pas modifier une structure encore incomplète.

        Le point unique du retour à la ligne : l'éditeur l'appelle quand le popup
        est fermé, le completer quand il est ouvert sans sélection — pour que les
        deux indentent pareil."""
        cur = self.textCursor()
        line = cur.block().text()
        indent = line[:len(line) - len(line.lstrip(" \t"))]
        prefix = line[:cur.positionInBlock()]
        comment = LuaHighlighter._comment_start(prefix, 0)
        code = (prefix if comment is None else prefix[:comment[0]]).strip()
        if self._BLOCK_OPEN.search(code):
            indent += " " * self._TAB_WIDTH
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
        """Place le curseur au DÉBUT DU CODE de la ligne `line` (1-indexée) et
        la centre.

        Sert au saut depuis le journal de build (`fichier.lua:ligne` cliqué).
        La ligne entière est surlignée : c'est elle que le message désigne, et
        une bande de couleur se retrouve d'un coup d'œil là où un curseur se
        confond avec le reste. Un repli qui la cachait s'ouvre.
        Le curseur se pose sur le premier caractère non blanc, pas en fin de
        ligne : c'est là que commence ce que le message désigne, et l'auteur
        n'a rien à retraverser. Une ligne hors plage retombe sur la dernière —
        un message peut citer une ligne au-delà de la fin sur un fichier
        tronqué."""
        doc = self.document()
        block = doc.findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            block = doc.lastBlock()
        self.reveal_line(block.blockNumber())
        texte = block.text()
        # Une ligne entièrement blanche n'a pas de début de code : le curseur
        # s'y pose au début plutôt qu'au bout de son indentation.
        debut = len(texte) - len(texte.lstrip(" \t")) if texte.strip() else 0
        cur = QTextCursor(block)
        cur.setPosition(block.position() + debut)
        self.setTextCursor(cur)
        self.centerCursor()
        self.highlight_error_line(block.blockNumber())
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
