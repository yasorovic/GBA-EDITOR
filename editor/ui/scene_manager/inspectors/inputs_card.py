"""
ui/scene_manager/inspectors/inputs_card.py — la carte « Inputs » de la
fenêtre Project Settings (catégorie Input).

Nommer une action et lui associer un ou plusieurs boutons physiques du GBA
pressés ENSEMBLE — un combo à un seul bouton est le cas courant, à plusieurs
il en fait un vrai combo. Le nom est utilisable depuis Lua via
`input:held("nom")` et `input:pressed("nom")`.

Comme LanguagesCard, la carte ne mute rien : elle SIGNALE un geste — « ajoute »,
« retire », « ce champ vaut ça » — et l'appelant (InputsPanel) en fait une
commande annulable.
"""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.models.settings import InputBinding, BUTTON_NAMES
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard, W


# Libellés courts affichés sur chaque case — dans l'ordre du boîtier GBA,
# même ordre que BUTTON_NAMES.
_BUTTON_LABELS: tuple[tuple[str, str], ...] = tuple(zip(
    BUTTON_NAMES,
    ("↑", "↓", "←", "→", "A", "B", "L", "R", "Start", "Select"),
))


class InputsCard(CollapsibleCard):
    """Déclaration des actions d'input du projet."""

    input_added = pyqtSignal()
    input_removed = pyqtSignal(object)                     # InputBinding
    input_field_changed = pyqtSignal(object, str, object)  # (InputBinding, champ, valeur)

    def __init__(self, parent=None):
        super().__init__(label('inputs.inputs'), expanded=True, parent=parent)
        self._project = None
        self._blocking = False
        inner = self.body_layout

        hint = QLabel(
            label('inputs.hint'))
        hint.setFont(QFont(T.UI, T.XS))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hint.setWordWrap(True)
        inner.addWidget(hint)

        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 6, 0, 0)
        self._rows.setSpacing(3)
        inner.addWidget(self._rows_host)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 4, 0, 0)
        self._btn_add = W.btn_add(label('inputs.declare_an_input'))
        self._btn_add.clicked.connect(lambda: self.input_added.emit())
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
            n = len(p.settings.inputs) if p else 0
            self._count.setText("" if not n else label('inputs.count', n=n))
        finally:
            self._blocking = False

    def _clear_rows(self):
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_rows(self):
        self._clear_rows()
        if not self._project:
            return
        for i, binding in enumerate(self._project.settings.inputs):
            self._rows.addWidget(self._build_row(i, binding))

    def _build_row(self, index: int, binding: InputBinding) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        name = QLineEdit(binding.name)
        name.setFont(QFont(T.UI, T.SM))
        name.setStyleSheet(QSS.lineedit)
        name.setPlaceholderText(label('inputs.jump'))
        name.setFixedWidth(110)
        name.editingFinished.connect(
            lambda _i=index, _e=name: self._commit_name(_i, _e.text()))
        row.addWidget(name)

        for key, btn_name in _BUTTON_LABELS:
            box = QCheckBox(btn_name)
            box.setFont(QFont(T.UI, T.XS))
            box.setStyleSheet(QSS.checkbox)
            box.setChecked(key in binding.buttons)
            box.toggled.connect(
                lambda on, _i=index, _k=key: self._commit_button(_i, _k, on))
            row.addWidget(box)

        row.addStretch(1)
        rm = W.btn_danger(label('inputs.remove_this_input'))
        rm.clicked.connect(lambda _c=False, _i=index: self._remove(_i))
        row.addWidget(rm)
        return host

    # ── Mutations — la carte PROPOSE, l'appelant décide ────────────

    def _binding_at(self, index: int):
        items = self._project.settings.inputs if self._project else []
        return items[index] if 0 <= index < len(items) else None

    def _commit_name(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        binding = self._binding_at(index)
        name = raw.strip()
        if binding is not None and binding.name != name:
            self.input_field_changed.emit(binding, "name", name)

    def _commit_button(self, index: int, key: str, on: bool):
        if self._blocking or not self._project:
            return
        binding = self._binding_at(index)
        if binding is None:
            return
        buttons = set(binding.buttons)
        if on:
            buttons.add(key)
        else:
            buttons.discard(key)
        # Ordre canonique du boîtier, pas l'ordre de clic.
        ordered = [k for k in BUTTON_NAMES if k in buttons]
        if ordered != binding.buttons:
            self.input_field_changed.emit(binding, "buttons", ordered)

    def _remove(self, index: int):
        binding = self._binding_at(index)
        if binding is not None:
            self.input_removed.emit(binding)

    def free_name(self) -> str:
        """Un nom encore libre, pour un input qu'on vient d'ajouter — il doit
        pouvoir être distingué des autres avant même d'être renommé."""
        taken = {b.name for b in self._project.settings.inputs}
        n = 1
        while f"input{n}" in taken:
            n += 1
        return f"input{n}"
