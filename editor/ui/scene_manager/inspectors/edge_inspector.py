"""Inspecteur compact d'une transition du graphe de scènes."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

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
        self._path.write_text(text, encoding="utf-8")
        self._changed()

    def execute(self):
        self._apply(self._after)

    def undo(self):
        self._apply(self._before)


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
        line = QFrame(); line.setCursor(Qt.CursorShape.PointingHandCursor)
        line.setStyleSheet(f"QFrame{{background:{C.BG_RAISED};border:1px solid {C.BORDER};}} QFrame:hover{{background:{C.BG_HOVER};}}")
        row = QHBoxLayout(line); row.setContentsMargins(9, 7, 7, 7); row.setSpacing(8)
        marker = QLabel("•"); marker.setStyleSheet(f"color:{C.ACCENT};")
        prefix = QLabel(f"{ref.path.name} : {ref.line}")
        prefix.setFont(QFont(T.CODE, T.SM)); prefix.setStyleSheet(f"color:{C.TEXT_DIM};")
        text = QLineEdit(source)
        text.setFont(QFont(T.CODE, T.SM)); text.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};padding:3px 5px;}}"
            f"QLineEdit:focus{{border-color:{C.ACCENT};}}")
        text.editingFinished.connect(lambda r=ref, field=text: self._save_source_line(r, field))
        open_btn = QPushButton(label("common.open")); open_btn.setStyleSheet(f"color:{C.ACCENT};background:transparent;border:none;")
        open_btn.clicked.connect(lambda: self.open_ref.emit(ref))
        row.addWidget(marker); row.addWidget(prefix); row.addWidget(text, 1); row.addWidget(open_btn)
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
