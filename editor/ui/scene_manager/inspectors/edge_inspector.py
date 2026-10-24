"""Inspecteur compact d'une transition du graphe de scènes."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from core.scene_graph_state import SceneGraphState
from core.history import Command, get_history
from ui.common.labels import label
from ui.scene_manager.scene_graph_commands import EdgePresentationCmd
from ui.common.theme import C, T
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import CollapsibleCard, NotesEdit, W


def _source_line(ref) -> str:
    try:
        lines = ref.path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return lines[ref.line - 1].strip() if 1 <= ref.line <= len(lines) else ""


class _ScriptTextCmd(Command):
    """Réécriture atomique d'un script, annulable via l'historique partagé."""

    def __init__(self, path, before: str, after: str, changed):
        self._path, self._before, self._after, self._changed = path, before, after, changed
        self.label = f"Modifier {path.name}"

    def _apply(self, text: str) -> None:
        self._path.write_text(text, encoding="utf-8", newline="\n")
        self._changed()

    def execute(self):
        self._apply(self._after)

    def undo(self):
        self._apply(self._before)


class _StartAlignedLineEdit(QLineEdit):
    """Champ dont le début reste visible tant qu'il n'est pas en cours d'édition.

    Qt laisse sinon le curseur (donc la vue) à la fin du texte, et un texte plus long que le
    champ apparaît coupé à gauche."""

    def _show_start(self) -> None:
        if not self.hasFocus():
            self.setCursorPosition(0)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._show_start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._show_start()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._show_start()


class _CallRow(QFrame):
    """Une ligne d'appel : repère, `fichier : ligne`, champ Lua éditable, bouton Ouvrir.

    Le nom du fichier est coupé par « ... » (le style de l'application) ; quand la place manque
    pour un champ lisible, le champ passe seul sur une seconde ligne."""

    _MIN_FIELD_WIDTH = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("callRow")
        self.setStyleSheet(
            f"QFrame#callRow{{background:{C.BG_RAISED};border:1px solid {C.BORDER};}}")
        self.marker = QLabel("•")
        self.marker.setStyleSheet(f"color:{C.ACCENT};border:none;background:transparent;")
        self.prefix = QLabel()
        self.prefix.setFont(QFont(T.CODE, T.SM))
        self.prefix.setStyleSheet(
            f"QLabel{{color:{C.TEXT_DIM};background:{C.BG_RAISED};border:1px solid {C.BORDER_MID};padding:3px 5px;}}"
            f"QLabel:hover{{background:{C.BG_HOVER};border-color:{C.ACCENT};}}")
        # Minimum nul : le libellé peut rétrécir sous sa largeur naturelle, le style l'abrège.
        self.prefix.setMinimumWidth(0)
        self.text = _StartAlignedLineEdit()
        self.text.setFont(QFont(T.CODE, T.SM))
        self.text.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};padding:3px 5px;}}"
            f"QLineEdit:hover{{background:{C.BG_HOVER};border-color:{C.ACCENT};}}"
            f"QLineEdit:focus{{background:{C.BG_INPUT};border-color:{C.ACCENT};}}")
        self.open_btn = QPushButton(label("common.open"))
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};padding:3px 10px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};border-color:{C.ACCENT};}}"
            f"QPushButton:pressed{{color:{C.BG_DEEP};background:{C.ACCENT};}}")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(9, 7, 7, 7)
        self._grid.setHorizontalSpacing(8); self._grid.setVerticalSpacing(6)
        self._wrapped = None
        self._arrange(False)

    def _arrange(self, wrapped: bool) -> None:
        if wrapped == self._wrapped:
            return
        self._wrapped = wrapped
        for widget in (self.marker, self.prefix, self.text, self.open_btn):
            self._grid.removeWidget(widget)
        for column in range(4):
            self._grid.setColumnStretch(column, 0)
        self._grid.addWidget(self.marker, 0, 0)
        self._grid.addWidget(self.prefix, 0, 1)
        if wrapped:
            self._grid.addWidget(self.open_btn, 0, 2)
            self._grid.addWidget(self.text, 1, 0, 1, 3)
            self._grid.setColumnStretch(1, 1)
        else:
            self._grid.addWidget(self.text, 0, 2)
            self._grid.addWidget(self.open_btn, 0, 3)
            self._grid.setColumnStretch(2, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        spacing = self._grid.horizontalSpacing()
        margins = self._grid.contentsMargins()
        needed = (self.marker.sizeHint().width() + self.prefix.fontMetrics().horizontalAdvance(self.prefix.text())
                  + self._MIN_FIELD_WIDTH + self.open_btn.sizeHint().width()
                  + 3 * spacing + margins.left() + margins.right())
        self._arrange(self.width() < needed)


class EdgeInspector(QWidget):
    """Présentation éditoriale d'une transition, sans second bandeau d'asset."""

    open_ref = pyqtSignal(object)
    style_changed = pyqtSignal(object)
    script_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edge = None
        self._edges = []
        self._state: SceneGraphState | None = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = InspectorScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer.addWidget(scroll)
        content = QWidget(); content.setStyleSheet(f"background:{C.BG_PANEL};")
        self._content = QVBoxLayout(content)
        self._content.setContentsMargins(10, 10, 10, 12); self._content.setSpacing(8)
        scroll.setWidget(content)

        note_title = QLabel(label("common.note")); note_title.setFont(QFont(T.UI, T.SM))
        note_title.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._content.addWidget(note_title)
        self._note = NotesEdit(); self._note.committed.connect(self._save_note)
        self._content.addWidget(self._note)

        self._appearance = CollapsibleCard(label("edgeinsp.appearance"))
        self._style_buttons = {}
        toggle = QWidget(); row = QHBoxLayout(toggle)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)
        for style, text in (("straight", label("edgeinsp.path_straight")),
                            ("curve", label("edgeinsp.path_curve"))):
            btn = QPushButton(text); btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=style: self._set_style(s))
            btn.setStyleSheet(
                f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};padding:4px 10px;}}"
                f"QPushButton:checked{{color:{C.BG_DEEP};background:{C.ACCENT};border-color:{C.ACCENT};}}")
            row.addWidget(btn); self._style_buttons[style] = btn
        W.row(label("edgeinsp.path"), toggle, self._appearance.body_layout)
        self._content.addWidget(self._appearance)

        self._calls = CollapsibleCard(label("edgeinsp.script_calls"))
        self._calls.body_layout.setContentsMargins(0, 4, 0, 4)
        self._list = QVBoxLayout(); self._list.setSpacing(2)
        self._list_layout = self._list
        self._calls.body_layout.addLayout(self._list)
        self._content.addWidget(self._calls)
        self._content.addStretch(1)

    def set_graph_state(self, state: SceneGraphState | None) -> None:
        self._state = state

    def load(self, edge, project) -> None:
        """Charge une transition ou une sélection de transitions."""
        self._edges = list(edge) if isinstance(edge, (list, tuple)) else [edge]
        self._edges = [value for value in self._edges if value is not None]
        self._edge = self._edges[0] if self._edges else None
        if self._edge is None:
            return
        # Le titre de la transition est posé par le header du DynamicInspector
        # (`show_edge`), source unique : l'inspecteur ne le recalcule pas.
        if self._state is None and project is not None:
            self._state = SceneGraphState(project.root)
        notes = ([self._state.edge_note(value.source, value.target) for value in self._edges]
                 if self._state else [])
        same_note = notes[0] if notes and all(note == notes[0] for note in notes) else ""
        self._note.set_text_silent(same_note)
        self._note.setPlaceholderText(
            label("wdg.notes") if len(self._edges) == 1
            else label("edgeinsp.notes_multi_placeholder"))
        self._sync_style_buttons()
        self._clear_calls()
        for value in self._edges:
            for ref in value.refs:
                self._add_call(ref, _source_line(ref))
        if not any(value.refs for value in self._edges):
            self._add_message(label("edgeinsp.target_missing", target=self._edge.target))

    def _set_style(self, style: str) -> None:
        if not self._edges or self._state is None:
            return
        before = [self._state.edge_style(edge.source, edge.target) for edge in self._edges]
        after = [style] * len(self._edges)
        if before != after:
            get_history().push(EdgePresentationCmd(
                self._state, self._edges, "style", before, after, self._metadata_applied))
        else:
            # Les boutons sont cochables (et non exclusifs) pour représenter
            # l'état mixte : un second clic ne doit pas laisser « aucun style ».
            self._sync_style_buttons()

    def _save_note(self, text: str) -> None:
        if not self._edges or self._state is None:
            return
        before = [self._state.edge_note(edge.source, edge.target) for edge in self._edges]
        after = [text] * len(self._edges)
        if before != after:
            get_history().push(EdgePresentationCmd(
                self._state, self._edges, "note", before, after, self._metadata_applied))

    def _sync_style_buttons(self) -> None:
        styles = ([self._state.edge_style(edge.source, edge.target) for edge in self._edges]
                  if self._state else ["auto"])
        shared = styles[0] if styles and all(style == styles[0] for style in styles) else None
        self._style_buttons["straight"].setChecked(shared == "straight")
        self._style_buttons["curve"].setChecked(shared == "curve")

    def _metadata_applied(self, edges, field: str) -> None:
        """Rafraîchit la vue et le panneau si cette sélection est toujours active."""
        if field == "style":
            self.style_changed.emit(list(edges))
        if tuple(self._edges) != tuple(edges) or self._state is None:
            return
        if field == "style":
            self._sync_style_buttons()
        else:
            notes = [self._state.edge_note(edge.source, edge.target) for edge in self._edges]
            self._note.set_text_silent(notes[0] if notes and all(note == notes[0] for note in notes) else "")

    def _clear_calls(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if (widget := item.widget()) is not None:
                widget.deleteLater()

    def _add_call(self, ref, source: str) -> None:
        line = _CallRow()
        marker, prefix, text, open_btn = line.marker, line.prefix, line.text, line.open_btn
        prefix.setText(f"{ref.path.name} : {ref.line}")
        text.setText(source)
        text.editingFinished.connect(lambda r=ref, field=text: self._save_source_line(r, field))
        open_btn.clicked.connect(lambda: self.open_ref.emit(ref))
        # Le champ central possède son propre clic et son focus ; seul le bouton
        # explicite « Ouvrir » déclenche la navigation vers le Script Editor.
        self._list.addWidget(line)

    def _save_source_line(self, ref, field: QLineEdit) -> None:
        """Réécrit seulement la ligne référencée, sans toucher au reste du Lua."""
        try:
            text = ref.path.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            if not 1 <= ref.line <= len(lines):
                return
            ending = "\r\n" if lines[ref.line - 1].endswith("\r\n") else "\n" if lines[ref.line - 1].endswith("\n") else ""
            if lines[ref.line - 1].rstrip("\r\n") == field.text():
                return
            lines[ref.line - 1] = field.text() + ending
            updated = "".join(lines)
        except OSError:
            return
        get_history().push(_ScriptTextCmd(ref.path, text, updated, self.script_changed.emit))

    def _add_message(self, text: str) -> None:
        message = QLabel(text); message.setStyleSheet(f"color:{C.TEXT_DIM}; padding:8px;")
        self._list.addWidget(message)
