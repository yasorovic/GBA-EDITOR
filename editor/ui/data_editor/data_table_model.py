"""Modèle Qt de la grille de données.

La table du projet reste l'unique source de vérité. Contrairement à un
``QTableWidget``, ce modèle ne fabrique pas un ``QTableWidgetItem`` par case :
il expose directement les lignes et colonnes de ``DataTable`` à la vue. Le
rendu et les éditeurs peuvent donc suivre la maquette sans recopier l'état.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from core.models.data_table import DataColumn, DataTable, COLUMN_REFERENCES
from ui.common.labels import label
from ui.common.theme import C
from ui.common.tooltip import tooltip


class DataTableModel(QAbstractTableModel):
    """Adaptateur léger entre ``DataTable`` et la grille peinte par Qt."""

    def __init__(self, write_value: Callable[[int, int, object], bool],
                 text_preview: Callable[[str], str], parent=None):
        super().__init__(parent)
        self._table: Optional[DataTable] = None
        self._write_value = write_value
        self._text_preview = text_preview

    def set_table(self, table: Optional[DataTable]) -> None:
        self.beginResetModel()
        self._table = table
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() or self._table is None else len(self._table.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() or self._table is None else len(self._table.columns)

    def column_at(self, section: int) -> Optional[DataColumn]:
        if self._table is not None and 0 <= section < len(self._table.columns):
            return self._table.columns[section]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or self._table is None:
            return None
        if orientation == Qt.Orientation.Horizontal:
            column = self.column_at(section)
            return column.name if column is not None else None
        return str(section + 1) if 0 <= section < len(self._table.rows) else None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._table is None:
            return None
        column = self.column_at(index.column())
        if column is None or not (0 <= index.row() < len(self._table.rows)):
            return None
        value = self._table.value(self._table.rows[index.row()], column)

        if role == Qt.ItemDataRole.DisplayRole:
            return "" if column.type == "bool" else str(value)
        if role == Qt.ItemDataRole.EditRole:
            return value
        if role == Qt.ItemDataRole.CheckStateRole and column.type == "bool":
            return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.TextAlignmentRole and column.type == "bool":
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.ForegroundRole:
            if column.type in COLUMN_REFERENCES:
                return QColor(C.ACCENT if value else C.TEXT_DIM)
            return QColor(C.SYNTAX_NUMBER)
        if (role == Qt.ItemDataRole.ToolTipRole and column.type == "text"
                and value):
            return tooltip(title=label("datagrid.text_preview_title"),
                           body=self._text_preview(str(value)))
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        column = self.column_at(index.column())
        base = (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if column is None:
            return base
        if column.type == "bool":
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base | Qt.ItemFlag.ItemIsEditable

    def setData(self, index: QModelIndex, value,
                role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or self._table is None:
            return False
        column = self.column_at(index.column())
        if column is None:
            return False
        if role == Qt.ItemDataRole.CheckStateRole and column.type == "bool":
            new_value = value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked
        elif role == Qt.ItemDataRole.EditRole:
            if column.type == "int":
                try:
                    new_value = int(value or 0)
                except (TypeError, ValueError):
                    new_value = 0
            else:
                new_value = str(value or "").strip()
        else:
            return False
        if not self._write_value(index.row(), index.column(), new_value):
            return False
        self.dataChanged.emit(index, index, [
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.CheckStateRole,
            Qt.ItemDataRole.ForegroundRole,
            Qt.ItemDataRole.ToolTipRole,
        ])
        return True

