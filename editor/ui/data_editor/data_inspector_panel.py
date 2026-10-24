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

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T, S, QSS
from ui.common.widgets import W, CollapsibleCard
from ui.common.notice import note
from ui.common.labels import label
from ui.common.tooltip import tooltip

from .data_cell_preview import CellPreview
from core.models.data_table import DataColumn, COLUMN_CHOICES, COLUMN_REFERENCES
from core.project import Project


# Type de colonne -> famille d'asset que `Window.open_element` sait ouvrir. Une caméra ou une région
# n'a pas d'écran propre : leur cellule se décrit, sans bouton.
OPENABLE_FAMILY = {
    "text": "texts", "sprite": "sprites", "background": "backgrounds", "prefab": "prefabs", "sfx": "sfx",
    "music": "music", "scene": "scenes", "font": "fonts", "palette": "palettes",
}


class DataInspectorPanel(QWidget):
    """Colonne sélectionnée + ce que la cellule désigne."""

    type_changed = pyqtSignal(object, str)   # (colonne, nouveau type)
    open_requested = pyqtSignal(str, str)    # (famille, nom) de l'élément cité par la cellule
    text_edited = pyqtSignal(object, str, str)   # (Text, avant, après) : le contenu du texte cité, corrigé ici

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
        self._type.addItems(COLUMN_CHOICES)
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

        self._preview = CellPreview()
        self._preview.text_edited.connect(self.text_edited)
        cell_card.body_layout.addWidget(self._preview)

        self._open = QPushButton(label("datainsp.open_target"))
        self._open.setStyleSheet(QSS.button_ghost + f"QPushButton {{ font-size:{T.MD}px; padding:4px 10px; }}")
        self._open.clicked.connect(self._on_open)
        cell_card.body_layout.addWidget(self._open)
        self._open_target: Optional[tuple[str, str]] = None
        root.addWidget(cell_card)

        root.addStretch(1)
        self.set_selection(None, None)

    def load_project(self, project: Project):
        self._project = project

    # ── Sélection ─────────────────────────────────────────────────

    def set_selection(self, column: Optional[DataColumn], value):
        self._column = column
        self._updating = True
        self._open_target = self._openable(column, value)
        self._open.setVisible(self._open_target is not None)
        if column is None:
            self._name.setText("—")
            self._type.setEnabled(False)
            self._value.setText("—")
            self._target.setText("")
        else:
            self._name.setText(column.name)
            self._type.setEnabled(True)
            # Un ancien type reste affiché sans redevenir un choix de création.
            self._type.setPlaceholderText(column.type)
            self._type.setCurrentIndex(self._type.findText(column.type))
            self._value.setText("—" if value is None else str(value))
            self._target.setText(self._describe(column, value))
        self._preview.show_for(self._project, column, value)
        self._updating = False

    def refresh_text(self):
        """Le contenu d'un texte a changé hors de cet écran."""
        self._preview.refresh_text()

    def _openable(self, column: Optional[DataColumn], value) -> Optional[tuple[str, str]]:
        """(famille, nom) quand la cellule cite un élément qui existe ; sinon rien à ouvrir."""
        family = OPENABLE_FAMILY.get(column.type) if column is not None else None
        name = str(value or "").strip()
        if family is None or not name or self._project is None:
            return None
        if name not in self._project.data_column_choices(column.type):
            return None
        return family, name

    def _on_open(self):
        if self._open_target is not None:
            self.open_requested.emit(*self._open_target)

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
            return ""      # le contenu s'affiche, et se corrige, dans l'aperçu
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
