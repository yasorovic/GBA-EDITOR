"""ui/data_editor/data_inspector_panel.py — panneau droit : la sélection.

Deux sujets, dans cet ordre : la COLONNE de la cellule sélectionnée (son nom,
son type) et ce que la CELLULE désigne quand sa colonne est une référence.

C'est ici, et pas dans la grille, que se lit la désignation : une colonne qui
afficherait le contenu du texte à côté de sa clé écraserait la grille sur deux
cents lignes, et ferait dire à l'éditeur autre chose que ce que la donnée
contient. La grille montre la valeur, l'inspecteur montre ce qu'elle vise.

L'ÉCRITURE reste côté grille — ce panneau émet, il ne modifie rien. Même
répartition que le Palette Editor : un seul chemin d'écriture, donc un seul
endroit qui pousse dans l'historique.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T, S, QSS
from ui.common.widgets import W, CollapsibleCard
from ui.common.notice import note
from ui.common.labels import label
from ui.common.tooltip import tooltip

from core.models.data_table import DataColumn, COLUMN_TYPES, COLUMN_REFERENCES
from core.project import Project


class DataInspectorPanel(QWidget):
    """Colonne sélectionnée + ce que la cellule désigne."""

    type_changed = pyqtSignal(object, str)   # (colonne, nouveau type)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._column:  Optional[DataColumn] = None
        self._updating = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self.setMinimumWidth(260)
        self.setMaximumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(S.MD, S.MD, S.MD, S.MD)
        root.setSpacing(S.SM)

        column_card = CollapsibleCard(label("datainsp.column"))
        self._name = QLabel("—")
        self._name.setStyleSheet(f"color:{C.ACCENT}; font-family:{T.CODE}; "
                                 f"font-size:{T.MD}px;")
        W.row(label("datainsp.name"), self._name, column_card.body_layout)

        self._type = QComboBox()
        self._type.addItems(COLUMN_TYPES)
        self._type.setStyleSheet(QSS.combobox)
        self._type.setToolTip(tooltip(
            title=label("datainsp.type_title"), body=label("datainsp.type_tip"),
        ))
        self._type.currentTextChanged.connect(self._on_type_changed)
        W.row(label("datainsp.type"), self._type, column_card.body_layout)

        note(column_card.body_layout, "data.column_rename").show_text()
        root.addWidget(column_card)

        cell_card = CollapsibleCard(label("datainsp.cell"))
        self._value = QLabel("—")
        self._value.setStyleSheet(f"color:{C.TEXT_HI}; font-family:{T.CODE}; "
                                  f"font-size:{T.MD}px;")
        self._value.setWordWrap(True)
        W.row(label("datainsp.value"), self._value, cell_card.body_layout)

        self._target = QLabel("")
        self._target.setStyleSheet(f"color:{C.TEXT_DIM}; font-size:{T.SM}px;")
        self._target.setWordWrap(True)
        cell_card.body_layout.addWidget(self._target)
        root.addWidget(cell_card)

        root.addStretch(1)
        self.set_selection(None, None)

    def load_project(self, project: Project):
        self._project = project

    # ── Sélection ─────────────────────────────────────────────────

    def set_selection(self, column: Optional[DataColumn], value):
        self._column = column
        self._updating = True
        if column is None:
            self._name.setText("—")
            self._type.setEnabled(False)
            self._value.setText("—")
            self._target.setText("")
        else:
            self._name.setText(column.name)
            self._type.setEnabled(True)
            self._type.setCurrentText(column.type)
            self._value.setText("—" if value is None else str(value))
            self._target.setText(self._describe(column, value))
        self._updating = False

    def _describe(self, column: DataColumn, value) -> str:
        """Ce que la valeur DÉSIGNE — factuel, jamais un commentaire sur la
        donnée. Une référence vide est une valeur légitime, pas une faute : le
        build l'émet en 0."""
        if column.type not in COLUMN_REFERENCES:
            return ""
        name = str(value or "").strip()
        if not name:
            return label("datainsp.no_ref")
        if self._project is None:
            return ""
        if name not in self._project.data_column_choices(column.type):
            return label("datainsp.no_named", type=column.type, name=name)
        if column.type == "text":
            entry = next((t for t in self._project.texts if t.key == name), None)
            return label("datainsp.text_content", content=entry.content) if entry else ""
        if column.type == "palette":
            bank = self._project.palettes.get(name)
            return label("datainsp.pal_colors", n=bank.size) if bank else ""
        return label("datainsp.of_project", type=column.type)

    # ── Type ──────────────────────────────────────────────────────

    def _on_type_changed(self, new_type: str):
        if self._updating or self._column is None:
            return
        if new_type != self._column.type:
            self.type_changed.emit(self._column, new_type)
