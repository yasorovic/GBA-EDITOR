"""ui/text_editor/value_completion.py — l'autocomplétion de `$nom` dans les champs de texte.

Taper `$` ouvre la liste des globals et constantes du projet ; chaque lettre
suivante la filtre. Les noms viennent de la même source que le bouton `$name` de
la barre de balisage (`value_names`) : une seule liste, deux gestes.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, QEvent, QObject, QStringListModel
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QCompleter

from ui.common.theme import C

# `$` suivi du début d'un nom, curseur juste après. `$$` est un `$` littéral, et
# `!3` (limite) n'est pas un nom : le popup se referme dès le `!`.
_OPEN_VALUE = re.compile(r"(?<!\$)\$([A-Za-z_]\w*)?$")


def value_names(project) -> list[str]:
    """Ce qu'un `$nom` peut désigner : les globals et les constantes."""
    if not project:
        return []
    return sorted({v.name for v in project.globals}
                  | {c.name for c in project.constants})


def attach_value_completion(edit, project_of) -> QCompleter:
    """Branche l'autocomplétion de `$` sur un `QTextEdit`. `project_of()` rend le
    projet courant (il change sans que le champ soit recréé)."""
    completer = QCompleter(QStringListModel(edit), edit)
    completer.setWidget(edit)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.popup().setStyleSheet(
        f"QListView{{background:{C.BG_RAISED};color:{C.TEXT_HI};"
        f"border:1px solid {C.BORDER_MID};outline:none;padding:2px;}}"
        f"QListView::item{{padding:2px 6px;}}"
        f"QListView::item:selected{{background:{C.ACCENT};color:{C.ON_ACCENT};}}")
    inserting = [False]

    def refresh():
        if inserting[0] or not edit.hasFocus():
            return
        cursor = edit.textCursor()
        before = cursor.block().text()[:cursor.positionInBlock()]
        match = _OPEN_VALUE.search(before)
        prefix = (match.group(1) or "") if match else ""
        names = value_names(project_of()) if match else []
        found = [n for n in names if n.lower().startswith(prefix.lower())]
        # Rien à proposer, ou un nom déjà tapé en entier.
        if not found or [n.lower() for n in found] == [prefix.lower()]:
            completer.popup().hide()
            return
        completer.model().setStringList(names)
        completer.setCompletionPrefix(prefix)
        completer.popup().setCurrentIndex(completer.completionModel().index(0, 0))
        rect = edit.cursorRect()
        rect.setWidth(completer.popup().sizeHintForColumn(0)
                      + completer.popup().verticalScrollBar().sizeHint().width() + 24)
        completer.complete(rect)

    def insert(name: str):
        cursor = edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Left,
                            QTextCursor.MoveMode.KeepAnchor,
                            len(completer.completionPrefix()))
        inserting[0] = True
        try:
            cursor.insertText(name)
        finally:
            inserting[0] = False
        edit.setTextCursor(cursor)

    class _PopupKeys(QObject):
        """Tab et Entrée valident la ligne courante, Échap ferme : tenu à la main,
        comme le popup du script editor, plutôt que laissé au tri de QCompleter."""
        def eventFilter(self, obj, event):
            if event.type() != QEvent.Type.KeyPress:
                return False
            key = event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                index = completer.popup().currentIndex()
                if index.isValid():
                    insert(index.data())
                completer.popup().hide()
                return True
            if key == Qt.Key.Key_Escape:
                completer.popup().hide()
                return True
            return False

    keys = _PopupKeys(completer)
    completer.popup().installEventFilter(keys)
    edit.textChanged.connect(refresh)
    return completer
