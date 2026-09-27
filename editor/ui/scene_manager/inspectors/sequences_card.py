"""
ui/scene_manager/inspectors/sequences_card.py — la carte « Séquences » de la
fenêtre Project Settings (catégorie Input, ROADMAP « Les inputs
personnalisés »).

Une séquence nommée (quart de cercle, demi-cercle, dragon punch, ou une
composition) reconnue par `input:get_sequence("nom")`. Barre d'expression
éditable dans le mini-langage complet (`+` accord, `-` pas suivant, `(a|b)`
alternative, mouvements), avec en dessous l'aperçu de ce que le parseur a
compris. Rôle distinct d'InputsCard (accords simples, cases à cocher) —
décision de Victor du 2026-09-27 : les deux ne partagent plus ni écran ni
appel Lua.

Comme LanguagesCard, la carte ne mute rien : elle SIGNALE un geste, et
l'appelant (SequencesPanel) en fait une commande annulable.
"""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QCompleter,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal, Qt

from core.models.settings import InputSequence, BUTTON_NAMES
from core.models.input_expression import (
    InputExpressionError, BUILTIN_MOVEMENTS, parse_input_expression,
)
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard, W


# ── L'aperçu : mêmes glyphes que le ROADMAP ("↓ ↘ → ➜ Ⓐ") ─────────────
_ARROWS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
_DIAGONALS = {
    frozenset({"up", "right"}): "↗", frozenset({"up", "left"}): "↖",
    frozenset({"down", "right"}): "↘", frozenset({"down", "left"}): "↙",
}
_CIRCLED = {"a": "Ⓐ", "b": "Ⓑ", "l": "Ⓛ", "r": "Ⓡ"}


def _step_glyph(buttons: frozenset) -> str:
    if buttons in _DIAGONALS:
        return _DIAGONALS[buttons]
    dirs = [_ARROWS[b] for b in ("up", "down", "left", "right") if b in buttons]
    others = [_CIRCLED.get(b, b.capitalize())
             for b in ("a", "b", "l", "r", "start", "select") if b in buttons]
    parts = dirs + others
    return "+".join(parts) if parts else "?"


def render_preview(expr) -> str:
    return " ➜ ".join(_step_glyph(s.buttons) for s in expr.steps)


def _completion_words(custom_movements: dict) -> list:
    return sorted(set(BUTTON_NAMES) | set(BUILTIN_MOVEMENTS) | set(custom_movements))


class SequencesCard(CollapsibleCard):
    """Déclaration des séquences d'input du projet."""

    sequence_added = pyqtSignal()
    sequence_removed = pyqtSignal(object)                     # InputSequence
    sequence_field_changed = pyqtSignal(object, str, object)  # (InputSequence, champ, valeur)

    def __init__(self, parent=None):
        super().__init__(label('inputs.sequences'), expanded=False, parent=parent)
        self._project = None
        self._blocking = False
        inner = self.body_layout

        hint = QLabel(label('inputs.sequences_hint'))
        hint.setFont(QFont(T.UI, T.XS))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hint.setWordWrap(True)
        inner.addWidget(hint)

        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 6, 0, 0)
        self._rows.setSpacing(8)
        inner.addWidget(self._rows_host)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 4, 0, 0)
        self._btn_add = W.btn_add(label('inputs.declare_a_sequence'))
        self._btn_add.clicked.connect(lambda: self.sequence_added.emit())
        add_row.addWidget(self._btn_add)
        self._count = QLabel("")
        self._count.setFont(QFont(T.UI, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        add_row.addWidget(self._count, 1)
        inner.addLayout(add_row)

    # ── Chargement ────────────────────────────────────────────────

    def load(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        self._blocking = True
        try:
            p = self._project
            self._btn_add.setEnabled(p is not None)
            self._rebuild_rows()
            n = len(p.settings.sequences) if p else 0
            self._count.setText("" if not n else label('inputs.sequences_count', n=n))
        finally:
            self._blocking = False

    def _clear_rows(self):
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _custom_movements(self) -> dict:
        return {m.name: m.steps for m in (self._project.settings.movements or [])
                if m.name and m.steps}

    def _rebuild_rows(self):
        self._clear_rows()
        if not self._project:
            return
        sequences = self._project.settings.sequences
        # Un doublon d'expression n'empêche rien, mais un avertissement évite
        # qu'il passe inaperçu.
        seen: dict = {}
        for s in sequences:
            expr = s.expression.strip()
            if expr:
                seen.setdefault(expr, []).append(s.name)
        for i, seq in enumerate(sequences):
            dup = seen.get(seq.expression.strip(), [])
            other = next((n for n in dup if n != seq.name), None)
            self._rows.addWidget(self._build_row(i, seq, other))

    def _build_row(self, index: int, seq: InputSequence, dup_with: str | None) -> QWidget:
        movements = self._custom_movements()
        words = _completion_words(movements)

        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)

        name = QLineEdit(seq.name)
        name.setFont(QFont(T.UI, T.SM))
        name.setStyleSheet(QSS.lineedit)
        name.setPlaceholderText(label('inputs.sequence_name_placeholder'))
        name.setFixedWidth(110)
        name.editingFinished.connect(
            lambda _i=index, _e=name: self._commit_name(_i, _e.text()))
        top.addWidget(name)

        expr = QLineEdit(seq.expression)
        expr.setFont(QFont(T.MONO, T.SM))
        expr.setPlaceholderText(label('inputs.expression_placeholder'))
        completer = QCompleter(words, expr)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        expr.setCompleter(completer)
        top.addWidget(expr, 1)

        window = QSpinBox()
        window.setFont(QFont(T.UI, T.SM))
        window.setStyleSheet(QSS.spinbox)
        window.setRange(1, 255)
        window.setValue(seq.window)
        window.setPrefix(label('inputs.window_prefix'))
        window.setToolTip(label('inputs.window_tip'))
        window.valueChanged.connect(
            lambda v, _i=index: self._commit_window(_i, v))
        top.addWidget(window)

        rm = W.btn_danger(label('inputs.remove_this_sequence'))
        rm.clicked.connect(lambda _c=False, _i=index: self._remove(_i))
        top.addWidget(rm)
        col.addLayout(top)

        preview = QLabel()
        preview.setFont(QFont(T.MONO, T.XS))
        preview.setWordWrap(True)
        col.addWidget(preview)

        def _reparse(text: str):
            try:
                alternatives = parse_input_expression(text, movements) if text.strip() else []
                if not alternatives:
                    preview.setText(label('inputs.expression_empty'))
                    preview.setStyleSheet(f"color:{C.TEXT_MUTED};")
                else:
                    txt = "  |  ".join(render_preview(e) for e in alternatives)
                    if dup_with:
                        txt += "   " + label('inputs.duplicate_expression', other=dup_with)
                    preview.setText(txt)
                    preview.setStyleSheet(
                        f"color:{C.ACCENT_YLW if dup_with else C.TEXT_MUTED};")
                expr.setStyleSheet(QSS.lineedit)
            except InputExpressionError as ex:
                preview.setText(f"{label('inputs.expression_error')} : {ex.message}")
                preview.setStyleSheet(f"color:{C.ACCENT_RED};")
                expr.setStyleSheet(QSS.lineedit + (
                    f"QLineEdit {{ border: 1px solid {C.ACCENT_RED}; }}"))

        _reparse(seq.expression)
        expr.textEdited.connect(_reparse)
        expr.editingFinished.connect(
            lambda _i=index, _e=expr: self._commit_expression(_i, _e.text()))
        return host

    # ── Mutations — la carte PROPOSE, l'appelant décide ────────────

    def _seq_at(self, index: int):
        items = self._project.settings.sequences if self._project else []
        return items[index] if 0 <= index < len(items) else None

    def _commit_name(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        seq = self._seq_at(index)
        name = raw.strip()
        if seq is not None and seq.name != name:
            self.sequence_field_changed.emit(seq, "name", name)

    def _commit_expression(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        seq = self._seq_at(index)
        text = raw.strip()
        if seq is not None and seq.expression != text:
            self.sequence_field_changed.emit(seq, "expression", text)

    def _commit_window(self, index: int, value: int):
        if self._blocking or not self._project:
            return
        seq = self._seq_at(index)
        if seq is not None and seq.window != value:
            self.sequence_field_changed.emit(seq, "window", value)

    def _remove(self, index: int):
        seq = self._seq_at(index)
        if seq is not None:
            self.sequence_removed.emit(seq)

    def free_name(self) -> str:
        taken = {s.name for s in self._project.settings.sequences}
        n = 1
        while f"sequence{n}" in taken:
            n += 1
        return f"sequence{n}"
