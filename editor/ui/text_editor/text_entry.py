"""Entrée sur deux lignes : identité et outils, puis source éditable."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLineEdit, QLabel, QToolButton,
    QTextEdit, QApplication, QSizePolicy, QPushButton,
)

from ui.common import icons
from ui.common.drag_grip import DragGrip
from ui.common.labels import label
from ui.text_editor.sequence_table_bar import SequenceTableBar
from ui.common.theme import C, T, QSS
from ui.common.widgets import BTN_ICON
from ui.text_editor.markup_toolbar import MarkupToolbar


class TextEntry(QFrame):
    activated = pyqtSignal()
    content_edited = pyqtSignal(str, str)
    key_edited = pyqtSignal(str)
    add_asked = pyqtSignal()
    remove_asked = pyqtSignal()
    geometry_changed = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, text, content: str, project, parent=None, *, number=None):
        super().__init__(parent)
        self._text = text
        self._baseline = content
        self._number = number
        self._selected = None
        self._drop = False
        self.setObjectName("textEntry")
        self.set_selected(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 8)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(6)
        # Poignée de réordonnancement : seulement pour une page de séquence.
        self.grip = DragGrip(self)   # parenté : un setVisible sur un widget orphelin ouvre une fenêtre
        self.grip.set_ghost_source(lambda: self)
        self.grip.setVisible(number is not None)
        header.addWidget(self.grip)
        self.collapse = QToolButton()
        self.collapse.setCheckable(True)
        self.collapse.setIcon(icons.arrow_icon('down', C.TEXT_DIM))
        self.collapse.setIconSize(QSize(14, 14))
        self.collapse.setFixedSize(22, 22)
        self.collapse.setStyleSheet(BTN_ICON)
        self.collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse.setToolTip(label('txtentry.collapse'))
        self.collapse.setAccessibleName(self.collapse.toolTip())
        self.collapse.toggled.connect(self._toggle_collapsed)
        header.addWidget(self.collapse)
        self.key = QLineEdit(text.key)
        self.key.setFont(QFont(T.CODE, T.SM))
        self.key.setStyleSheet(QSS.lineedit)
        self.key.setToolTip(label("txttbl.rename_key"))
        self.key.setMinimumWidth(100)
        self.key.editingFinished.connect(self._rename)
        self.key.installEventFilter(self)
        header.addWidget(self.key, 1)
        self.number = QLabel(f"#{number}" if number is not None else "")
        self.number.setFont(QFont(T.CODE, T.SM))
        self.number.setStyleSheet(f"color:{C.TEXT_DIM};")
        self.number.setToolTip(text.key)
        header.addWidget(self.number)
        if number is not None:
            self.key.hide()
            header.addStretch(1)
        else:
            self.number.hide()
        copy = QToolButton()
        copy.setIcon(icons.get("copy", C.TEXT_DIM))
        copy.setStyleSheet(BTN_ICON)
        copy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        copy.setToolTip(label("txtwb.key_title"))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text.key))
        header.addWidget(copy)
        self.used = QLabel()
        self.used.setTextFormat(Qt.TextFormat.PlainText)
        self.used.setStyleSheet(f"color:{C.TEXT_DIM};")
        self.used.setFont(QFont(T.UI, T.XS))
        header.addWidget(self.used)
        self.status = QLabel()
        self.status.setStyleSheet(f"color:{C.ACCENT_YLW};")
        header.addWidget(self.status)

        self.field = QFrame()
        self.field.setObjectName('textEntryField')
        self.field.setStyleSheet(f'QFrame#textEntryField{{background:{C.BG_INPUT};'
                                f'border:1px solid {C.BORDER_MID};border-radius:4px;}}')
        field_layout = QVBoxLayout(self.field)
        field_layout.setContentsMargins(6, 4, 6, 4)
        field_layout.setSpacing(0)
        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)
        self.edit.setFont(QFont(T.CODE, T.SM))
        self.edit.setStyleSheet(
            f"QTextEdit{{background:transparent; color:{C.TEXT_HI};"
            f"border:none; padding:0px;selection-background-color:{C.BG_SEL};}}")
        self.edit.setFixedHeight(64)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setTabChangesFocus(True)
        self.edit.setPlainText(content)
        self.edit.installEventFilter(self)
        # La barre existante sait déjà travailler avec un QTextEdit : mêmes
        # balises, menus de valeurs et remplacement de sélection que l'atelier.
        self.markup = MarkupToolbar(self.edit)
        self.markup.set_project(project)
        header.addWidget(self.markup)
        if number is not None:
            self.markup.hide()
        layout.addLayout(header)
        layout.addWidget(self.field)
        field_layout.addWidget(self.edit)
        controls = QHBoxLayout()
        controls.setSpacing(4)
        controls.addStretch()
        self.remove = QToolButton(self)
        self.remove.setIcon(icons.get('ev_destroy', C.TEXT_DIM))
        self.remove.setIconSize(QSize(14,14))
        self.remove.setFixedSize(22,22)
        self.remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove.setStyleSheet(BTN_ICON + 'QToolButton{padding:0px;margin:0px;}')
        self.remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.remove.setToolTip(label('txtseq.remove_entry'))
        self.remove.setAccessibleName(self.remove.toolTip())
        self.remove.clicked.connect(self.remove_asked.emit)
        header.addWidget(self.remove)
        self.add = QToolButton(self.field)
        self.add.setIcon(icons.get('add', C.TEXT_HI))
        self.add.setIconSize(QSize(14,14))
        self.add.setFixedSize(22,22)
        self.add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add.setStyleSheet(BTN_ICON + 'QToolButton{padding:0px;margin:0px;}')
        self.add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add.setToolTip(label('txtseq.add_after'))
        self.add.clicked.connect(self.add_asked.emit)
        controls.addWidget(self.add)
        field_layout.addLayout(controls)
        self.edit.document().documentLayout().documentSizeChanged.connect(self._fit_editor)
        self._fit_editor()
        self.edit.textChanged.connect(self._edited)

    def _toggle_collapsed(self, collapsed):
        self.field.setVisible(not collapsed)
        self.markup.setVisible(not collapsed and self._number is None)
        self.collapse.setIcon(icons.arrow_icon('right' if collapsed else 'down', C.TEXT_DIM))
        self.collapse.setToolTip(label('txtentry.expand' if collapsed else 'txtentry.collapse'))
        self.collapse.setAccessibleName(self.collapse.toolTip())
        self.layout().invalidate()
        self.updateGeometry()
        self.collapsed_changed.emit(collapsed)
        self.geometry_changed.emit()

    def eventFilter(self, watched, event):
        if watched is getattr(self, 'edit', None) and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            QTimer.singleShot(0, self._fit_editor)
        if event.type() == QEvent.Type.FocusIn:
            self.activated.emit()
        return super().eventFilter(watched, event)

    def _fit_editor(self, *_):
        import math
        height = max(64, min(180, math.ceil(self.edit.document().size().height()) + 4))
        if self.edit.height() != height:
            self.edit.setFixedHeight(height)
            self.field.layout().invalidate()
            self.layout().invalidate()
            self.updateGeometry()
            self.geometry_changed.emit()

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self._restyle()

    def set_drop_target(self, on: bool):
        """Repère visuel pendant qu'une poignée survole cette page."""
        if self._drop != on:
            self._drop = on
            self._restyle()

    def _restyle(self):
        self.setStyleSheet(
            f"QFrame#textEntry{{background:{C.BG_BASE};border:none;"
            f"border-top:2px solid {C.ACCENT if self._drop else 'transparent'};"
            f"border-left:2px solid {C.ACCENT if self._selected else 'transparent'};}}"
            f" QFrame#textEntry QLabel{{background:transparent;border:none;}}")

    def _edited(self):
        after = self.edit.toPlainText()
        before, self._baseline = self._baseline, after
        if before != after:
            self.content_edited.emit(before, after)

    def _rename(self):
        typed = self.key.text().strip()
        if typed and typed != self._text.key:
            self.key_edited.emit(typed)
        else:
            self.key.setText(self._text.key)
        if self._number is not None:
            self.key.hide()
            self.number.show()

    def begin_key_edit(self):
        self.number.hide()
        self.key.show()
        self.key.setFocus()
        self.key.selectAll()

    def set_content(self, content: str):
        if self.edit.toPlainText() != content:
            self.edit.blockSignals(True)
            self.edit.setPlainText(content)
            self.edit.blockSignals(False)
        self._baseline = content


class TextEntryGroup(QFrame):
    """En-tête d'une séquence de textes : préfixe, outils de balisage, état lié/libre.

    La séquence est dérivée des clés ; les mutations passent par des commandes."""

    prefix_edited = pyqtSignal(str)
    add_asked = pyqtSignal()
    delete_asked = pyqtSignal()

    def __init__(self, prefix, count, project, parent=None):
        super().__init__(parent)
        self._prefix = prefix
        self.setStyleSheet(
            f"TextEntryGroup{{background:{C.BG_RAISED};"
            f"border:none;}}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        layout = QHBoxLayout()
        outer.addLayout(layout)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)
        self.key = QLineEdit(prefix)
        self.key.setFont(QFont(T.CODE, T.SM, QFont.Weight.Bold))
        self.key.setStyleSheet(QSS.lineedit)
        self.key.setToolTip(label("txttbl.rename_group_key"))
        self.key.editingFinished.connect(self._rename_prefix)
        layout.addWidget(self.key, 1)
        count_label = QLabel(label("txttbl.text_count", n=count))
        count_label.setStyleSheet(f"color:{C.TEXT_DIM};")
        layout.addWidget(count_label)
        self.active = QLabel()
        self.active.setStyleSheet(f"color:{C.ACCENT};")
        layout.addWidget(self.active)
        self.markup = MarkupToolbar(None)
        self.markup.set_project(project)
        self.markup.setEnabled(False)
        layout.addWidget(self.markup)
        # Taille fixe : un bouton « + » à largeur libre se faisait rogner par la barre.
        self.add_first = QToolButton()
        self.add_first.setText('+')
        self.add_first.setStyleSheet(QSS.toolbutton_icon)
        self.add_first.setFixedSize(28, 28)
        self.add_first.setToolTip(label('txtseq.add_first'))
        self.add_first.clicked.connect(self.add_asked.emit)
        layout.addWidget(self.add_first)
        self.trash = QToolButton()
        self.trash.setIcon(icons.get("ev_destroy", C.TEXT_DIM))
        self.trash.setStyleSheet(QSS.toolbutton_icon)
        self.trash.setFixedSize(28, 28)
        self.trash.setToolTip(label('txtseq.delete_sequence_tip'))
        self.trash.clicked.connect(self.delete_asked.emit)
        layout.addWidget(self.trash)
        self.table_bar = SequenceTableBar()
        outer.addWidget(self.table_bar)

    def _rename_prefix(self):
        typed = self.key.text().strip()
        if typed and typed != self._prefix:
            self._prefix = typed
            self.prefix_edited.emit(typed)
        else:
            self.key.setText(self._prefix)

    def set_active_entry(self, entry):
        if entry is None:
            self.active.clear()
            self.markup.setEnabled(False)
            self.markup.set_editor(None)
            return
        self.active.setText(f"#{entry._number}")
        self.active.setToolTip(entry._text.key)
        self.markup.set_editor(entry.edit)
        self.markup.setEnabled(True)

    def set_selected(self, selected):
        pass  # Seuls les blocs portent la sélection, jamais le groupe entier.
