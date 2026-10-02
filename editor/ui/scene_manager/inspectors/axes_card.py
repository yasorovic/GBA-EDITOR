"""
ui/scene_manager/inspectors/axes_card.py — la carte « Axes » de la fenêtre
Project Settings (catégorie Input, ROADMAP « Les inputs personnalisés »).

Un axe scalaire remappe la croix ou pilote un axe avec d'autres boutons/
actions, sans toucher au script (`input:get_axis("nom")`). "horizontal" et
"vertical" sont TOUJOURS présents (la croix) et n'apparaissent jamais dans
cette liste — ce sont les seuls noms qu'un axe déclaré ne peut pas prendre.

Même contrat que InputsCard : la carte SIGNALE un geste, l'appelant
(AxesPanel) en fait une commande annulable.
"""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox
from PyQt6.QtGui import QFont

from PyQt6.QtCore import pyqtSignal

from core.models.settings import InputAxis, BUTTON_NAMES
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard, W

RESERVED_AXIS_NAMES = frozenset({"horizontal", "vertical"})


class AxesCard(CollapsibleCard):
    """Déclaration des axes personnalisés du projet."""

    axis_added = pyqtSignal()
    axis_removed = pyqtSignal(object)                    # InputAxis
    axis_field_changed = pyqtSignal(object, str, object)  # (InputAxis, champ, valeur)

    def __init__(self, parent=None):
        super().__init__(label('inputs.axes'), expanded=False, parent=parent)
        self._project = None
        self._blocking = False
        inner = self.body_layout

        hint = QLabel(label('inputs.axes_hint'))
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
        self._btn_add = W.btn_add(label('inputs.declare_an_axis'))
        self._btn_add.clicked.connect(lambda: self.axis_added.emit())
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
            n = len(p.settings.axes) if p else 0
            self._count.setText("" if not n else label('inputs.axes_count', n=n))
        finally:
            self._blocking = False

    def _clear_rows(self):
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _side_choices(self) -> list:
        """Bouton ou accord (`InputBinding`) — jamais une séquence, qui n'a
        pas de masque simple (décision de l'auteur, 2026-09-27)."""
        names = list(BUTTON_NAMES)
        if self._project:
            names += [b.name for b in self._project.settings.inputs
                     if b.name and b.buttons]
        return names

    def _rebuild_rows(self):
        self._clear_rows()
        if not self._project:
            return
        for i, axis in enumerate(self._project.settings.axes):
            self._rows.addWidget(self._build_row(i, axis))

    def _build_row(self, index: int, axis: InputAxis) -> QWidget:
        choices = self._side_choices()
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        name = QLineEdit(axis.name)
        name.setFont(QFont(T.UI, T.SM))
        name.setStyleSheet(QSS.lineedit)
        name.setPlaceholderText(label('inputs.axis_name_placeholder'))
        name.setFixedWidth(110)
        name.editingFinished.connect(
            lambda _i=index, _e=name: self._commit_name(_i, _e.text()))
        row.addWidget(name)

        row.addWidget(QLabel(label('inputs.axis_negative')))
        neg = QComboBox()
        neg.setFont(QFont(T.UI, T.SM))
        neg.setStyleSheet(QSS.combobox)
        neg.addItems(choices)
        if axis.negative in choices:
            neg.setCurrentText(axis.negative)
        neg.currentTextChanged.connect(
            lambda v, _i=index: self._commit_field(_i, "negative", v))
        row.addWidget(neg)

        row.addWidget(QLabel(label('inputs.axis_positive')))
        pos = QComboBox()
        pos.setFont(QFont(T.UI, T.SM))
        pos.setStyleSheet(QSS.combobox)
        pos.addItems(choices)
        if axis.positive in choices:
            pos.setCurrentText(axis.positive)
        pos.currentTextChanged.connect(
            lambda v, _i=index: self._commit_field(_i, "positive", v))
        row.addWidget(pos)

        row.addStretch(1)
        rm = W.btn_danger(label('inputs.remove_this_axis'))
        rm.clicked.connect(lambda _c=False, _i=index: self._remove(_i))
        row.addWidget(rm)
        return host

    # ── Mutations — la carte PROPOSE, l'appelant décide ────────────

    def _axis_at(self, index: int):
        items = self._project.settings.axes if self._project else []
        return items[index] if 0 <= index < len(items) else None

    def _commit_name(self, index: int, raw: str):
        if self._blocking or not self._project:
            return
        axis = self._axis_at(index)
        name = raw.strip()
        if axis is None or axis.name == name:
            return
        others = {a.name for a in self._project.settings.axes if a is not axis}
        if name in RESERVED_AXIS_NAMES or name in others:
            self.refresh()   # nom refusé : la ligne revient à sa valeur précédente
            return
        self.axis_field_changed.emit(axis, "name", name)

    def _commit_field(self, index: int, field: str, value: str):
        if self._blocking or not self._project:
            return
        axis = self._axis_at(index)
        if axis is not None and getattr(axis, field) != value:
            self.axis_field_changed.emit(axis, field, value)

    def _remove(self, index: int):
        axis = self._axis_at(index)
        if axis is not None:
            self.axis_removed.emit(axis)

    def free_name(self) -> str:
        taken = {a.name for a in self._project.settings.axes} | RESERVED_AXIS_NAMES
        n = 1
        while f"axis{n}" in taken:
            n += 1
        return f"axis{n}"
