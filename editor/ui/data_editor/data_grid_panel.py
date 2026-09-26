"""ui/data_editor/data_grid_panel.py — panneau central : la grille d'une table.

Deux objets d'édition dans un seul widget, et c'est le point délicat de cet
écran : les COLONNES (le schéma) et les LIGNES (les données). Ils se
distinguent par le geste — l'en-tête pour le schéma, les cellules pour les
valeurs — et non par un mode à basculer.

Le rang d'une ligne EST ce qu'un script indexe (`data.Objets[3]`) : l'en-tête
vertical le montre, numéroté À PARTIR DE 1 comme en Lua, et insérer au milieu
décale ce qui suit. C'est le comportement voulu, pas un défaut à masquer par
une identité de ligne que le script ne pourrait pas nommer.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QLineEdit, QStyledItemDelegate, QComboBox,
    QSpinBox, QMessageBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import C, T, S, QSS
from ui.common.widgets import W
from ui.common.labels import label

from core.models.data_table import (DataTable, DataColumn, COLUMN_TYPES,
                                    COLUMN_REFERENCES)
from core.history import get_history, RemoveListItemCmd
from core.project import Project

from .data_commands import (SetCellCmd, InsertRowCmd, AddColumnCmd,
                            RemoveColumnCmd, SetColumnTypeCmd)


_TBL_SS = f"""
QTableWidget {{
    background:{C.BG_BASE}; color:{C.TEXT_HI};
    border:none; gridline-color:{C.BORDER_DARK};
    font-family:{T.CODE}; font-size:{T.MD}px;
    outline:none;
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
}}
QHeaderView::section {{
    background:transparent; color:{C.TEXT_MUTED};
    border:none; border-bottom:1px solid {C.BORDER_DARK};
    border-right:1px solid {C.BORDER_DARK};
    font-family:{T.UI_STACK}; font-size:{T.XS}px;
    font-weight:700; letter-spacing:1px;
    padding:3px 6px;
}}
QTableWidget::item {{ padding:1px 4px; }}
QTableWidget::item:hover {{ background:{C.BG_PANEL}; }}
"""


class _ColumnHeader(QHeaderView):
    """En-tête horizontal dont une section se renomme EN PLACE.

    Double-clic → un champ de saisie posé sur la section. `QHeaderView` n'a pas
    d'édition native ; un dialogue « nouveau nom » ferait sortir l'utilisateur
    de la grille pour changer un mot qu'il a sous les yeux."""

    rename_requested = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsClickable(True)
        self._editor: Optional[QLineEdit] = None
        self._section = -1
        self.sectionDoubleClicked.connect(self._edit_section)

    def _edit_section(self, index: int):
        self._close_editor()
        self._section = index
        rect = self.sectionViewportPosition(index)
        editor = QLineEdit(self)
        editor.setStyleSheet(QSS.lineedit)
        editor.setGeometry(rect, 0, self.sectionSize(index), self.height())
        editor.setText(self.model().headerData(index, Qt.Orientation.Horizontal) or "")
        editor.selectAll()
        editor.show()
        editor.setFocus()
        editor.editingFinished.connect(self._commit)
        self._editor = editor

    def _commit(self):
        if self._editor is None:
            return
        text, section = self._editor.text().strip(), self._section
        self._close_editor()
        if text:
            self.rename_requested.emit(section, text)

    def _close_editor(self):
        if self._editor is not None:
            editor, self._editor = self._editor, None
            editor.blockSignals(True)
            editor.deleteLater()


class _CellDelegate(QStyledItemDelegate):
    """L'éditeur d'une cellule dépend du TYPE de sa colonne.

    C'est ce qui justifie l'écran contre l'édition du JSON à la main : une
    colonne de référence n'offre que des noms qui existent, là où un nom tapé
    au clavier ne se voyait qu'au build."""

    def __init__(self, panel: "DataGridPanel"):
        super().__init__(panel)
        self._panel = panel

    def createEditor(self, parent, option, index):
        col = self._panel.column_at(index.column())
        if col is None:
            return None
        if col.type in COLUMN_REFERENCES:
            combo = QComboBox(parent)
            combo.setStyleSheet(QSS.combobox)
            # Une entrée vide en tête : « aucune référence » est une valeur
            # légitime, et le build l'émet en 0.
            combo.addItem("")
            combo.addItems(self._panel.choices_for(col))
            return combo
        if col.type == "int":
            spin = QSpinBox(parent)
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(-2_147_483_648, 2_147_483_647)
            return spin
        return None

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole) or ""
        if isinstance(editor, QComboBox):
            pos = editor.findText(str(value))
            editor.setCurrentIndex(max(0, pos))
        elif isinstance(editor, QSpinBox):
            try:
                editor.setValue(int(value or 0))
            except (TypeError, ValueError):
                editor.setValue(0)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QSpinBox):
            model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)


class DataGridPanel(QWidget):
    """La grille : colonnes en en-tête, lignes en dessous."""

    # (colonne, valeur de la cellule) — l'inspecteur détaille la sélection.
    cell_selected  = pyqtSignal(object, object)
    # Le schéma ou le nombre de lignes a changé : le finder réaffiche « n × m ».
    table_changed  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._table:   Optional[DataTable] = None
        self._updating = False
        self.setStyleSheet(f"background:{C.BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._bar = W.section_bar(label("datagrid.table_bar"), C.ACCENT)
        hl = self._bar.layout()
        self._btn_row = W.btn_add(label("datagrid.add_row"), icon="add_row")
        self._btn_row.clicked.connect(lambda: self._insert_row(len(self._table.rows)
                                                               if self._table else 0))
        hl.addWidget(self._btn_row)
        self._btn_col = W.btn_add(label("datagrid.add_column"), icon="add_column")
        self._btn_col.clicked.connect(self._add_column)
        hl.addWidget(self._btn_col)
        root.addWidget(self._bar)

        self._tbl = QTableWidget(0, 0)
        self._tbl.setStyleSheet(_TBL_SS)
        self._header = _ColumnHeader(self._tbl)
        self._tbl.setHorizontalHeader(self._header)
        self._header.rename_requested.connect(self._rename_column)
        self._header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._header.customContextMenuRequested.connect(self._column_menu)
        self._tbl.setItemDelegate(_CellDelegate(self))
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                  | QAbstractItemView.EditTrigger.EditKeyPressed)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._row_menu)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.currentCellChanged.connect(self._on_current_cell)
        root.addWidget(self._tbl, 1)

        self._empty = W.empty_state(label("datagrid.empty"))
        root.addWidget(self._empty)
        self._show_empty(True)

    # ── Ce que la grille sait de sa table ─────────────────────────

    def column_at(self, index: int) -> Optional[DataColumn]:
        if self._table and 0 <= index < len(self._table.columns):
            return self._table.columns[index]
        return None

    def choices_for(self, column: DataColumn) -> list[str]:
        return (self._project.data_column_choices(column.type)
                if self._project else [])

    @property
    def table_name(self) -> str:
        return self._table.name if self._table else ""

    def _persist(self):
        if self._project and self._table:
            self._project.data_tables.save(self._table)

    def _show_empty(self, empty: bool):
        self._empty.setVisible(empty)
        self._tbl.setVisible(not empty)
        self._bar.setVisible(not empty)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._table = None
        self._show_empty(True)

    def show_table(self, name: str):
        self._table = self._project.get_data_table(name) if self._project else None
        self._show_empty(self._table is None)
        self.reload()

    def on_table_deleted(self):
        self._table = None
        self._show_empty(True)

    def reload(self):
        if not self._table:
            return
        self._updating = True
        self._tbl.clear()
        self._tbl.setColumnCount(len(self._table.columns))
        self._tbl.setRowCount(len(self._table.rows))
        self._tbl.setHorizontalHeaderLabels([c.name for c in self._table.columns])
        # Les lignes sont numérotées À PARTIR DE 1 : c'est l'index qu'un script
        # écrit, et l'afficher à partir de 0 obligerait à traduire de tête.
        self._tbl.setVerticalHeaderLabels([str(i + 1)
                                           for i in range(len(self._table.rows))])
        for c in range(len(self._table.columns)):
            self._tbl.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.Interactive)
            self._tbl.setColumnWidth(c, 120)
        for r, row in enumerate(self._table.rows):
            self._tbl.setRowHeight(r, S.ROW)
            for c, col in enumerate(self._table.columns):
                self._tbl.setItem(r, c, self._make_item(row, col))
        self._updating = False

    def _make_item(self, row: dict, col: DataColumn) -> QTableWidgetItem:
        value = self._table.value(row, col)
        item = QTableWidgetItem()
        if col.type == "bool":
            # Une case à cocher, sans texte : la colonne dit déjà ce qu'elle coche.
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                          | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked if value
                               else Qt.CheckState.Unchecked)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            item.setText(str(value))
            if col.type in COLUMN_REFERENCES:
                item.setForeground(QColor(C.ACCENT if value else C.TEXT_DIM))
                # Une colonne de textes montre une CLÉ, qui ne dit pas ce que
                # le joueur lira (ROADMAP v0.21). Le contenu vient donc en
                # infobulle : la cellule garde sa clé — c'est elle que
                # `_read_item` relit — et l'auteur voit sa réplique sans
                # ouvrir l'écran Texte.
                if col.type == "text" and value:
                    item.setToolTip(self._text_preview(str(value)))
            else:
                item.setForeground(QColor(C.SYNTAX_NUMBER))
        return item

    def _text_preview(self, key: str) -> str:
        """La réplique que cette clé désigne, telle que le joueur la lira —
        balisage résolu, constantes cuites, comme à l'aperçu de l'écran Texte."""
        if not self._project:
            return key
        entry = next((x for x in getattr(self._project, "texts", [])
                      if x.key == key), None)
        if entry is None:
            return label("datagrid.text_not_found", key=key)
        try:
            from core.text_markup import parse, resolve
            consts = {c.name: c.value for c in getattr(self._project, "constants", [])}
            body = resolve(parse(entry.content or ""), consts)
        except Exception:
            body = entry.content or ""
        body = body.replace(chr(10), " ")
        if len(body) > 160:
            body = body[:157] + "…"
        return label("datagrid.text_preview", key=key, body=body)

    # ── Écriture d'une cellule ────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating or not self._table:
            return
        col = self.column_at(item.column())
        if col is None or item.row() >= len(self._table.rows):
            return
        row = self._table.rows[item.row()]
        old = self._table.value(row, col)
        new = self._read_item(item, col)
        if new == old:
            return
        get_history().push(SetCellCmd(self._table, row, col.name, old, new,
                                      self._persist))
        self._refresh_cell(item.row(), item.column())
        self.cell_selected.emit(col, new)

    def _read_item(self, item: QTableWidgetItem, col: DataColumn):
        if col.type == "bool":
            return item.checkState() == Qt.CheckState.Checked
        if col.type == "int":
            try:
                return int(item.text().strip() or 0)
            except ValueError:
                return 0
        return item.text().strip()

    def _refresh_cell(self, r: int, c: int):
        """Réaffiche une cellule depuis la donnée — une saisie invalide dans une
        colonne d'entiers ne doit pas rester à l'écran sous sa forme tapée."""
        if not self._table:
            return
        self._updating = True
        self._tbl.setItem(r, c, self._make_item(self._table.rows[r],
                                                self._table.columns[c]))
        self._updating = False

    def _on_current_cell(self, r: int, c: int, _pr, _pc):
        col = self.column_at(c)
        if col is None or not self._table or not (0 <= r < len(self._table.rows)):
            self.cell_selected.emit(col, None)
            return
        self.cell_selected.emit(col, self._table.value(self._table.rows[r], col))

    # ── Lignes ────────────────────────────────────────────────────

    def _insert_row(self, index: int):
        if not self._table:
            return
        if not self._table.columns:
            QMessageBox.information(self, label("datagrid.no_column_title"),
                                    label("datagrid.no_column_text"))
            return
        get_history().push(InsertRowCmd(self._table, index, {}, self._after_change))

    def _delete_row(self, index: int):
        if not self._table or not (0 <= index < len(self._table.rows)):
            return
        get_history().push(RemoveListItemCmd(
            self._table.rows, self._table.rows[index], self._after_change,
            label=f"Ligne {index + 1}"))

    def _row_menu(self, pos: QPoint):
        if not self._table:
            return
        r = self._tbl.rowAt(pos.y())
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        a_above = menu.addAction(label("datagrid.row_above")) if r >= 0 else None
        a_below = menu.addAction(label("datagrid.row_below")) if r >= 0 else None
        a_end   = menu.addAction(label("datagrid.row_end"))
        menu.addSeparator()
        a_del   = menu.addAction(label("datagrid.row_delete")) if r >= 0 else None
        act = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if act is None:
            return
        if act == a_above:
            self._insert_row(r)
        elif act == a_below:
            self._insert_row(r + 1)
        elif act == a_end:
            self._insert_row(len(self._table.rows))
        elif act == a_del:
            self._delete_row(r)

    # ── Colonnes ──────────────────────────────────────────────────

    def _unique_column(self, base: str) -> str:
        if self._table and not self._table.column(base):
            return base
        i = 2
        while self._table.column(f"{base}_{i}"):
            i += 1
        return f"{base}_{i}"

    def _add_column(self):
        if not self._table:
            return
        col = DataColumn(name=self._unique_column("column"), type="int")
        get_history().push(AddColumnCmd(self._table, col, self._after_change))

    def _rename_column(self, index: int, new_name: str):
        col = self.column_at(index)
        if col is None or not self._project:
            return
        if self._project.rename_data_column(self._table, col, new_name):
            self._after_change()
            return
        self.reload()
        if new_name != col.name:
            QMessageBox.warning(
                self, label("datagrid.rename_title"),
                label("datagrid.rename_text", name=new_name,
                      table=self._table.name, col=col.name))

    def set_column_type(self, column: DataColumn, new_type: str):
        """Appelé par l'inspecteur : c'est la grille qui écrit et qui pousse
        dans l'historique, jamais le panneau qui affiche."""
        if self._table and column in self._table.columns and new_type != column.type:
            get_history().push(SetColumnTypeCmd(self._table, column, new_type,
                                                self._after_change))

    def _column_menu(self, pos: QPoint):
        if not self._table:
            return
        index = self._header.logicalIndexAt(pos)
        col = self.column_at(index)
        if col is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        type_menu = menu.addMenu(label("datagrid.type"))
        actions = {}
        for t in COLUMN_TYPES:
            a = type_menu.addAction(t)
            a.setCheckable(True)
            a.setChecked(t == col.type)
            actions[a] = t
        menu.addSeparator()
        a_add = menu.addAction(label("datagrid.add_column_menu"))
        a_del = menu.addAction(label("datagrid.delete_column"))
        act = menu.exec(self._header.mapToGlobal(pos))
        if act is None:
            return
        if act in actions:
            if actions[act] != col.type:
                get_history().push(SetColumnTypeCmd(self._table, col, actions[act],
                                                    self._after_change))
        elif act == a_add:
            self._add_column()
        elif act == a_del:
            get_history().push(RemoveColumnCmd(self._table, col, self._after_change))

    # ── Après toute écriture de structure ─────────────────────────

    def _after_change(self):
        self._persist()
        self.reload()
        self.table_changed.emit()
