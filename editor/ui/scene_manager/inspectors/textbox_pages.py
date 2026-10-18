"""Pages d'une TextBox dans l'inspecteur : un bloc par texte de sa séquence, avec + et −.

Les blocs éditent directement les `Text` du projet ; la boîte ne stocke rien. Une boîte libre
montre un seul bloc (son texte, ou son contenu local) ; son + la transforme en séquence."""
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QToolButton, QLabel

from core.history import get_history, SetFieldCmd
from ui.common.drag_grip import DragGrip
from ui.common.labels import label
from ui.common.theme import C, T, QSS
from ui.text_editor.markup_highlighter import MarkupHighlighter

_PAGE_SELECTION = "#d62d79"


class PageEdit(QTextEdit):
    activated = pyqtSignal()
    deactivated = pyqtSignal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.activated.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.deactivated.emit()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self.deactivated.emit()
            get_history().undo()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.deactivated.emit()
            get_history().redo()
        else:
            super().keyPressEvent(event)


class TextboxPages(QWidget):
    changed = pyqtSignal()           # redessin du canvas, sans écriture disque
    persist_asked = pyqtSignal()     # une commande d'historique vient d'être poussée
    add_asked = pyqtSignal()
    remove_asked = pyqtSignal(int)   # rang de la page
    reorder_asked = pyqtSignal(int, int)   # rang de départ, rang d'arrivée

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = self._box = None
        self._active = 0
        self._entries = []
        self._pending = {}           # id(cible) -> (cible, champ, valeur d'avant la salve)
        self._drop = None            # page survolée pendant un glissement de poignée
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self.commit)
        # Le canvas, l'arbre et l'inspecteur se redessinent APRÈS une courte pause, pas à chaque touche.
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(150)
        self._redraw.timeout.connect(self.changed.emit)
        self._refreshing = False
        self.blocks = []
        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(5)

    def bind(self, project, box):
        if self._box is not box or self._project is not project:
            self.commit()
            self.clear_preview()
            self._active = 0
        self._project, self._box = project, box
        self.refresh()

    def clear_preview(self):
        if self._box is not None:
            self._box.__dict__.pop("_editor_page_id", None)

    def _entries_now(self):
        if getattr(self._box, "sequence_prefix", ""):
            return self._project.textbox_pages(self._box)
        return [self._project.region_text(self._box)]

    def refresh(self):
        if self._box is None or self._project is None:
            return
        self._refreshing = True
        try:
            self._entries = self._entries_now()
            self._active = min(self._active, len(self._entries) - 1)
            # Garder les widgets pendant la frappe : aucun focus ni curseur perdu.
            while len(self.blocks) > len(self._entries):
                block = self.blocks.pop()
                self._body.removeWidget(block)
                block.hide()
                block.deleteLater()
            while len(self.blocks) < len(self._entries):
                self._add_block(len(self.blocks))
            linked = bool(getattr(self._box, "sequence_prefix", ""))
            for index, (block, entry) in enumerate(zip(self.blocks, self._entries)):
                source = entry.content if entry is not None else ""
                if block.editor.toPlainText() != source:
                    block.editor.setPlainText(source)
                block.editor.setFixedHeight(min(180, max(44,
                    int(block.editor.document().size().height()) + 8)))
                block.editor.setPlaceholderText(label("uiinsp.text.content_placeholder"))
                block.remove.setVisible(linked and index > 0)
                block.grip.setVisible(linked and len(self._entries) > 1)
            self._preview()
        finally:
            self._refreshing = False

    def _add_block(self, index):
        block = QWidget()
        block.setObjectName("textboxPage")
        outer = QHBoxLayout(block)
        outer.setContentsMargins(2, 5, 5, 4)
        outer.setSpacing(2)
        block.grip = DragGrip()
        block.grip.set_ghost_source(lambda: block)
        block.grip.moved.connect(lambda y: self._drag_over(y))
        block.grip.released.connect(lambda y: self._drop_at(index, y))
        outer.addWidget(block.grip)
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)
        block.editor = PageEdit()
        block.editor.setAcceptRichText(False)
        block.editor.setUndoRedoEnabled(False)
        block.editor.setFont(QFont(T.MONO, T.MD))
        block.editor.setMinimumHeight(52)
        block.editor.setMaximumHeight(180)
        block.editor.setStyleSheet(f"QTextEdit{{background:transparent;color:{C.TEXT_NORM};border:none;}}")
        block.editor.document().documentLayout().documentSizeChanged.connect(
            lambda size: block.editor.setFixedHeight(min(180, max(44, int(size.height()) + 8))))
        block.highlighter = MarkupHighlighter(block.editor.document())
        block.editor.activated.connect(lambda: self.activate(index))
        block.editor.deactivated.connect(self.commit)
        block.editor.textChanged.connect(lambda: self._typed(index))
        body.addWidget(block.editor)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch()
        block.remove = QToolButton()
        block.add = QToolButton()
        for button, symbol, tip in ((block.remove, "−", "uiinsp.text.page_remove"),
                                    (block.add, "+", "uiinsp.text.page_add")):
            button.setText(symbol)
            button.setFixedSize(22, 22)
            button.setStyleSheet(QSS.toolbutton_icon)
            button.setToolTip(label(tip))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        block.add.clicked.connect(self.add_asked.emit)
        block.remove.clicked.connect(lambda: self.remove_asked.emit(index))
        body.addLayout(actions)
        self._body.insertWidget(len(self.blocks), block)
        self.blocks.append(block)

    def _preview(self):
        entry = self._entries[self._active] if self._entries else None
        if entry is not None and getattr(self._box, "sequence_prefix", ""):
            self._box._editor_page_id = entry.id
        else:
            self.clear_preview()
        for index, block in enumerate(self.blocks):
            color = (C.ACCENT if index == self._drop
                     else _PAGE_SELECTION if index == self._active else C.BORDER_MID)
            block.setStyleSheet(f"QWidget#textboxPage{{background:{C.BG_INPUT};"
                                f"border:2px solid {color};border-radius:4px;}}")

    def _page_at(self, global_y):
        """La page sous ce y (la première ou la dernière au-delà des bords)."""
        for index, block in enumerate(self.blocks):
            if global_y < block.mapToGlobal(QPoint(0, 0)).y() + block.height():
                return index
        return len(self.blocks) - 1

    def _drag_over(self, global_y):
        target = self._page_at(global_y)
        if target != self._drop:
            self._drop = target
            self._preview()

    def _drop_at(self, source, global_y):
        target = self._page_at(global_y)
        self._drop = None
        self._preview()
        if target != source:
            self.reorder_asked.emit(source, target)

    def activate(self, index):
        if self._refreshing or not 0 <= index < len(self.blocks):
            return
        self._active = index
        self._preview()
        self.changed.emit()

    def focus_page(self, index):
        if 0 <= index < len(self.blocks):
            self.activate(index)
            self.blocks[index].editor.setFocus()

    def _target(self, entry):
        """(objet, champ) que la frappe modifie : le texte du projet, sinon le contenu local de la boîte."""
        if entry is not None and any(entry is t for t in self._project.texts):
            return entry, "content"
        return self._box, "preview_text"

    def _typed(self, index):
        if self._refreshing or index >= len(self._entries):
            return
        if index != self._active:
            self._active = index
            self._preview()
        target, field = self._target(self._entries[index])
        key = (id(target), field)
        if key not in self._pending:
            self._pending[key] = (target, field, getattr(target, field))      # début de salve
        value = self.blocks[index].editor.toPlainText()
        setattr(target, field, value)
        if field == "preview_text":
            self._box.preview_is_literal = True
        self._redraw.start()
        self._timer.start()

    def commit(self):
        """Fin de salve : une entrée d'historique par champ modifié (la valeur est déjà dans le modèle)."""
        self._timer.stop()
        self._redraw.stop()
        pending, self._pending = self._pending, {}
        for target, field, old in pending.values():
            value = getattr(target, field)
            if value != old:
                get_history().push(SetFieldCmd(
                    target, field, old, value,
                    label=f"Edit text {getattr(target, 'key', 'local')}",
                    persist_fn=self.persist_asked.emit))
