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
    QWidget, QVBoxLayout, QTableView, QHeaderView,
    QAbstractItemView, QMenu, QLineEdit, QStyledItemDelegate,
    QSpinBox, QHBoxLayout, QLabel, QPushButton, QStyle,
    QStyleOptionViewItem,
)
from ui.common.popup import MessageBox as QMessageBox
from PyQt6.QtGui import QColor, QBrush, QPen, QPalette
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QModelIndex, QPersistentModelIndex, QSize, QEvent, QTimer

from ui.common.theme import C, T, S, QSS, ui_font
from ui.common.widgets import W, AssetPickerPopup
from ui.common.palette_swatch import bank_icon
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common import icons
from ui.common.color_menu import add_color_actions
from ui.common.asset_kinds import CREATABLE_REFERENCES, create_referenced_asset
from ui.common.deferred_writes import schedule_unwatched

from core.models.unique_name import unique_name
from core.models.text import key_from_path
from core.models.data_table import (DataTable, DataColumn, COLUMN_CHOICES,
                                    COLUMN_REFERENCES)
from core.history import get_history, RemoveListItemCmd, SetFieldCmd, AddListItemCmd, MacroCmd
from core.text_sequences import sequences
from core.text_table_link import (link_state, key_column,
                                  row_changes, LinkTableCmd, UnlinkTableCmd)
from core.project import Project

from .data_commands import (SetCellCmd, InsertRowCmd, AddColumnCmd,
                            RemoveColumnCmd, SetColumnTypeCmd)
from .data_table_model import DataTableModel


_TBL_SS = f"""
QTableView {{
    background:{C.BG_BASE}; alternate-background-color:{C.BG_PANEL}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER}; border-radius:0;
    gridline-color:{C.BORDER};
    font-family:{T.CODE}; font-size:{T.LG}px;
    outline:none;
    selection-background-color:{C.BG_SEL}; selection-color:{C.TEXT_HI};
}}
QHeaderView::section {{
    background:{C.BG_PANEL}; color:{C.TEXT_DIM};
    border:none; border-bottom:1px solid {C.BORDER_DARK};
    border-right:1px solid {C.BORDER_DARK};
    font-family:{T.CODE}; font-size:{T.SM}px;
    font-weight:400;
    padding:0;
}}
QHeaderView::section:checked {{
    background:{C.BG_SEL}; color:{C.ACCENT};
}}
QTableCornerButton::section {{
    background:{C.BG_RAISED}; border:none;
    border-bottom:1px solid {C.BORDER_DARK};
    border-right:1px solid {C.BORDER_DARK};
}}
QTableView::item {{ padding:3px 14px; }}
QTableView::item:hover {{ background:{C.BG_HOVER}; }}
"""


class _ColumnHeader(QHeaderView):
    """En-tête horizontal dont une section se renomme EN PLACE.

    Double-clic → un champ de saisie posé sur la section. `QHeaderView` n'a pas
    d'édition native ; un dialogue « nouveau nom » ferait sortir l'utilisateur
    de la grille pour changer un mot qu'il a sous les yeux."""

    rename_requested = pyqtSignal(int, str)

    def __init__(self, type_for_section, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._type_for_section = type_for_section
        self.setSectionsClickable(True)
        self.setFixedHeight(58)
        self.setMinimumSectionSize(120)
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

    def paintSection(self, painter, rect, logical_index):
        """Un nom et son type dans le même en-tête, sans ajouter une colonne
        de métadonnées à la grille. Le schéma reste lisible avant les valeurs."""
        if rect.width() <= 0:
            return
        name = str(self.model().headerData(logical_index, Qt.Orientation.Horizontal) or "")
        column = self._type_for_section(logical_index)
        type_name = column.type if column is not None else ""

        painter.save()
        painter.setClipRect(rect)
        painter.fillRect(rect, QColor(C.BG_RAISED))
        column_color = QColor(column.color) if column and column.color else QColor()
        if column_color.isValid():
            fill = QColor(column_color)
            fill.setAlpha(22)
            painter.fillRect(rect, fill)
            painter.fillRect(rect.x(), rect.y(), rect.width(), 3, column_color)
        painter.setPen(QColor(C.BORDER))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.setPen(QColor(C.BORDER_DARK))
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.setPen(column_color if column_color.isValid() else QColor(C.TEXT_HI))
        font = ui_font(T.LG, bold=True)
        painter.setFont(font)
        name_rect = rect.adjusted(14, 7, -14, -29)
        name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight,
                                               max(0, name_rect.width()))
        painter.drawText(name_rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         name)
        if type_name:
            color = QColor({"int": C.SYNTAX_NUMBER, "bool": C.SYNTAX_KEYWORD,
                            "text": C.SYNTAX_STRING}.get(type_name, C.ACCENT_COOL))
            painter.setFont(ui_font(T.SM, family=T.CODE))
            badge = rect.adjusted(14, 32, -14, -8)
            badge.setWidth(min(badge.width(), painter.fontMetrics().horizontalAdvance(type_name) + 16))
            fill = QColor(color)
            fill.setAlpha(20)
            painter.setBrush(fill)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge.adjusted(0, 0, -1, -1), 3, 3)
            painter.setPen(color)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, type_name)
        painter.restore()

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

    def paint(self, painter, option, index):
        """Peint la sélection comme UNE rangée continue, comme dans la
        maquette, tout en laissant Qt dessiner texte et cases à cocher."""
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        if selected:
            styled.state &= ~QStyle.StateFlag.State_Selected
            styled.state &= ~QStyle.StateFlag.State_MouseOver
            styled.state &= ~QStyle.StateFlag.State_HasFocus
            styled.backgroundBrush = QBrush(QColor(C.BG_SEL))
            styled.palette.setColor(QPalette.ColorRole.Text, QColor(C.TEXT_HI))
        super().paint(painter, styled, index)

        painter.save()
        painter.setPen(QPen(QColor(C.BORDER_DARK), 1))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        if selected and index.column() == 0:
            painter.fillRect(option.rect.x(), option.rect.y(), 3,
                             option.rect.height(), QColor(C.ACCENT))
        if selected and option.state & QStyle.StateFlag.State_HasFocus:
            edge = QColor(C.ACCENT)
            edge.setAlpha(100)
            painter.setPen(QPen(edge, 1))
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
        painter.restore()

    def createEditor(self, parent, option, index):
        col = self._panel.column_at(index.column())
        if col is None or self._panel.is_key_cell(col):
            return None
        if col.type in COLUMN_REFERENCES:
            self._pick_reference(parent, option, index, col)
            return None
        if col.type == "int":
            spin = QSpinBox(parent)
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(-2_147_483_648, 2_147_483_647)
            return spin
        return None

    def _pick_reference(self, parent, option, index, column):
        # Le popup écrit seulement au choix explicite. Le fermer (Échap ou
        # clic ailleurs) ne remplace donc jamais une référence manquante.
        target = QPersistentModelIndex(index)
        entries = [(label("common.none_paren"), "", None)]
        project = self._panel._project
        icon = (icons.get(column.type, C.TEXT_DIM) if column.type in
                {"sprite", "background", "prefab", "palette", "scene", "camera", "font", "sfx", "music"}
                else None)
        for name in self._panel.choices_for(column):
            entry_icon = icon
            if column.type == "palette" and project:
                bank = project.palettes.get(name)
                if bank:
                    entry_icon = bank_icon(bank)
            entries.append((name, name, entry_icon))
        creatable = column.type == "text" or column.type in CREATABLE_REFERENCES
        popup = AssetPickerPopup(entries, C.ACCENT, parent=parent,
                                  new_label=label("datagrid.create_reference") if creatable else None)
        popup.setFixedWidth(max(260, min(420, option.rect.width())))
        popup.new_requested.connect(lambda: self._panel.create_reference(target, column))

        def picked(value):
            # Un rechargement de la table invalide l'index : un ancien popup
            # ne doit pas écrire dans la nouvelle sélection.
            if target.isValid():
                target.model().setData(QModelIndex(target), value, Qt.ItemDataRole.EditRole)

        popup.picked.connect(picked)
        anchor = QWidget(parent)
        anchor.setGeometry(option.rect)
        popup.show_below(anchor)
        anchor.deleteLater()

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole) or ""
        if isinstance(editor, QSpinBox):
            try:
                editor.setValue(int(value or 0))
            except (TypeError, ValueError):
                editor.setValue(0)

    def setModelData(self, editor, model, index):
        if isinstance(editor, QSpinBox):
            model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)


class DataGridPanel(QWidget):
    """La grille : colonnes en en-tête, lignes en dessous."""

    # (colonne, valeur de la cellule) — l'inspecteur détaille la sélection.
    cell_selected  = pyqtSignal(object, object)
    # Le schéma ou le nombre de lignes a changé : la library réaffiche « n × m ».
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

        self._bar = QWidget()
        self._bar.setObjectName("dataToolbar")
        self._bar.setStyleSheet(f"""
            QWidget#dataToolbar {{ background:{C.BG_BASE}; border-bottom:1px solid {C.BORDER_DARK}; }}
            QLabel {{ background:transparent; border:none; }}
        """)
        self._bar.setMinimumHeight(76)
        bar_layout = QHBoxLayout(self._bar)
        bar_layout.setContentsMargins(S.XL, S.MD, S.XL, S.MD)
        bar_layout.setSpacing(S.MD)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(S.SM)
        self._table_title = QLabel(label("datagrid.table_bar"))
        self._table_title.setStyleSheet(
            f"color:{C.TEXT_HI}; font-family:{T.UI_STACK}; font-size:{T.XXL}px; font-weight:600;")
        self._table_meta = QLabel("")
        self._table_meta.setStyleSheet(
            f"color:{C.TEXT_DIM}; font-family:{T.UI_STACK}; font-size:{T.SM}px;")
        heading.addWidget(self._table_title)
        heading.addWidget(self._table_meta)
        self._link_label = QLabel("")
        self._link_label.setStyleSheet(
            f"color:{C.ACCENT}; font-family:{T.UI_STACK}; font-size:{T.SM}px;")
        heading.addWidget(self._link_label)
        bar_layout.addLayout(heading, 1)

        self._btn_row = QPushButton(label("datagrid.add_row_action"))
        self._btn_row.setStyleSheet(QSS.button_primary)
        self._btn_row.setMinimumHeight(32)
        self._btn_row.setIcon(icons.get("add", C.BTN_PRIMARY_TEXT))
        self._btn_row.setIconSize(QSize(15, 15))
        self._btn_row.setToolTip(tooltip(title=label("datagrid.add_row")))
        self._btn_row.clicked.connect(lambda: self._insert_row(len(self._table.rows)
                                                               if self._table else 0))
        bar_layout.addWidget(self._btn_row)
        self._btn_duplicate = QPushButton(label("datagrid.duplicate_row"))
        secondary_style = QSS.button_ghost + f"QPushButton {{ font-size:{T.MD}px; padding:4px 10px; }}"
        self._btn_duplicate.setStyleSheet(secondary_style)
        self._btn_duplicate.setMinimumHeight(32)
        self._btn_duplicate.setIcon(icons.get("copy", C.TEXT_DIM))
        self._btn_duplicate.setIconSize(QSize(15, 15))
        self._btn_duplicate.clicked.connect(self._duplicate_selected_row)
        bar_layout.addWidget(self._btn_duplicate)
        self._btn_delete = QPushButton(label("datagrid.delete_row"))
        self._btn_delete.setStyleSheet(secondary_style + f"QPushButton:hover {{ color:{C.ACCENT_RED}; }}")
        self._btn_delete.setMinimumHeight(32)
        self._btn_delete.setIcon(icons.get("clear", C.TEXT_DIM))
        self._btn_delete.setIconSize(QSize(15, 15))
        self._btn_delete.clicked.connect(self._delete_selected_row)
        bar_layout.addWidget(self._btn_delete)
        self._btn_link = QPushButton(label("datagrid.link_action"))
        self._btn_unlink = QPushButton(label("datagrid.unlink_action"))
        for button, handler in ((self._btn_link, self._link_menu), (self._btn_unlink, self._unlink)):
            button.setStyleSheet(secondary_style)
            button.setMinimumHeight(32)
            button.clicked.connect(handler)
            bar_layout.addWidget(button)
        separator = QWidget()
        separator.setFixedSize(1, 20)
        separator.setStyleSheet(f"background:{C.BORDER};")
        bar_layout.addWidget(separator)
        self._btn_col = QPushButton(label("datagrid.add_column_action"))
        self._btn_col.setStyleSheet(secondary_style)
        self._btn_col.setMinimumHeight(32)
        self._btn_col.setIcon(icons.get("add", C.TEXT_DIM))
        self._btn_col.setIconSize(QSize(15, 15))
        self._btn_col.setToolTip(tooltip(title=label("datagrid.add_column"), body=label("datagrid.add_column_tip")))
        self._btn_col.clicked.connect(self._add_column)
        bar_layout.addWidget(self._btn_col)
        root.addWidget(self._bar)

        self._tbl = QTableView()
        self._tbl.setStyleSheet(_TBL_SS)
        self._tbl.setShowGrid(False)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setMouseTracking(True)
        self._tbl.setWordWrap(False)
        self._tbl.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._tbl.verticalHeader().setFixedWidth(44)
        self._tbl.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tbl.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._tbl.verticalHeader().setDefaultSectionSize(36)
        self._model = DataTableModel(self._write_cell, self._text_preview, self._tbl)
        self._tbl.setModel(self._model)
        self._header = _ColumnHeader(self.column_at, self._tbl)
        self._tbl.setHorizontalHeader(self._header)
        self._header.rename_requested.connect(self._rename_column)
        self._header.setToolTip(tooltip(
            title=label("datagrid.column_title"), body=label("datagrid.column_tip"),
        ))
        self._header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._header.customContextMenuRequested.connect(self._column_menu)
        self._fit_key = None            # (table, nombre de colonnes) dont les largeurs sont posées
        self._fitting = False
        self._user_widths = False       # l'auteur a tiré une colonne : plus rien ne les remplace
        self._header.sectionResized.connect(self._on_section_resized)
        self._tbl.setItemDelegate(_CellDelegate(self))
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Un premier clic sélectionne la case, un clic sur la case déjà courante l'édite (`eventFilter`) : Qt n'offre que
        # `SelectedClicked`, qui compte la LIGNE sélectionnée, pas la case.
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self._pressed_current = None    # (index persistant, était la case courante) du dernier appui gauche
        self._tbl.viewport().installEventFilter(self)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._row_menu)
        self._tbl.selectionModel().currentChanged.connect(self._on_current_index)
        self._grid_host = QWidget()
        self._grid_host.setStyleSheet(f"background:{C.BG_BASE};")
        grid_layout = QVBoxLayout(self._grid_host)
        grid_layout.setContentsMargins(S.XL, S.XL, S.XL, S.XL)
        grid_layout.setSpacing(0)
        grid_layout.addWidget(self._tbl, 1)
        root.addWidget(self._grid_host, 1)

        self._empty = W.empty_state(label("datagrid.empty"))
        root.addWidget(self._empty)
        self._show_empty(True)

    def eventFilter(self, watched, event):
        if watched is self._tbl.viewport() and self._table is not None:
            kind = event.type()
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)                     and event.button() == Qt.MouseButton.LeftButton:
                index = self._tbl.indexAt(event.position().toPoint())
                # Avant que la vue ne déplace la case courante : c'est ce qui distingue « sélectionner » de « éditer ».
                self._pressed_current = (QPersistentModelIndex(index),
                                         index.isValid() and index == self._tbl.currentIndex())
            elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton                     and self._pressed_current is not None:
                pressed, was_current = self._pressed_current
                self._pressed_current = None
                index = self._tbl.indexAt(event.position().toPoint())
                if (was_current and event.modifiers() == Qt.KeyboardModifier.NoModifier
                        and pressed.isValid() and index.isValid() and index == QModelIndex(pressed)):
                    QTimer.singleShot(0, lambda: pressed.isValid() and self._tbl.edit(QModelIndex(pressed)))
        return super().eventFilter(watched, event)

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

    def create_reference(self, target: QPersistentModelIndex, column: DataColumn):
        """« Create new » du sélecteur d'une cellule : l'élément naît comme depuis sa library, puis la cellule le cite."""
        if self._project is None or self._table is None or not target.isValid():
            return
        if column.type == "text":
            self._create_text_for(target.row(), column)
            return
        name = create_referenced_asset(self._project, column.type)
        if name and target.isValid():
            target.model().setData(QModelIndex(target), name, Qt.ItemDataRole.EditRole)

    def _create_text_for(self, row_index: int, column: DataColumn):
        """Un texte rangé sous le dossier `text` puis le nom de la table (`text_<table>_01`…), cité par la cellule, en UN pas d'historique.
        La clé est proposée par le rangement, jamais tapée ; le contenu s'écrit ensuite dans l'écran Texte."""
        project, table = self._project, self._table
        taken = project.text_keys()
        number = 1
        while key_from_path(["text", table.name, f"{number:02d}"], taken=set()) in taken:
            number += 1
        text = project.new_text(path=["text", table.name, f"{number:02d}"])
        row = table.rows[row_index]

        def persist_texts():
            schedule_unwatched("save_texts", project.save_texts)
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().notify_texts_changed()

        add = AddListItemCmd(project.texts, text, persist_fn=persist_texts, label=f"New text {text.key}")
        write = SetCellCmd(table, row, column.name, table.value(row, column), text.key, self._persist)
        get_history().push(MacroCmd([add, write], f"{table.name}.{column.name}"))
        self._after_change()

    def _persist(self):
        if self._project and self._table:
            self._project.data_tables.save(self._table)

    def _show_empty(self, empty: bool):
        self._empty.setVisible(empty)
        self._grid_host.setVisible(not empty)
        self._bar.setVisible(not empty)

    def _update_table_header(self):
        if not self._table:
            return
        self._table_title.setText(self._table.name)
        self._table_meta.setText(label("datagrid.table_summary",
                                       rows=len(self._table.rows),
                                       columns=len(self._table.columns)))
        self._sync_link_ui()
        self._sync_row_actions()

    def _sync_row_actions(self):
        has_row = self._tbl.currentIndex().row() >= 0
        locked = self._is_linked()
        self._btn_row.setEnabled(not locked)
        self._btn_duplicate.setEnabled(has_row and not locked)
        self._btn_delete.setEnabled(has_row and not locked)

    # ── Lien avec un groupe de textes ─────────────────────────────

    def _is_linked(self) -> bool:
        return bool(self._table and self._table.text_link)

    def is_key_cell(self, column: DataColumn) -> bool:
        return self._is_linked() and key_column(self._table) is column

    def _sync_link_ui(self):
        state = link_state(self._project, self._table) if self._is_linked() else None
        self._link_label.setVisible(state is not None)
        if state:
            self._link_label.setText(label("datagrid.link_" + state,
                                           group=self._table.text_link["prefix"]))
        self._link_label.setToolTip(label("datagrid.link_locked"))
        self._btn_link.setVisible(state is None)
        self._btn_unlink.setVisible(state is not None)

    def _text_column(self):
        return next((c for c in self._table.columns if c.type == "text"), None)

    def _link_menu(self):
        if not self._table:
            return
        column = self._text_column()
        if column is None:
            QMessageBox.information(self, label("datagrid.link_title"), label("datagrid.link_no_text_column"))
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        groups = list(sequences(self._project))
        for prefix in groups:
            menu.addAction(prefix).setData(prefix)
        if not groups:
            menu.addAction(label("datagrid.link_no_group")).setEnabled(False)
        action = menu.exec(self._btn_link.mapToGlobal(QPoint(0, self._btn_link.height())))
        if action is not None and action.data() is not None:
            self._apply_link(action.data(), column.name)

    def _confirm_link(self, prefix, added, lost) -> bool:
        return QMessageBox.question(
            self, label("datagrid.link_title"),
            label("datagrid.link_confirm", group=prefix, added=added, lost=lost),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _apply_link(self, prefix, column_name):
        column = self._table.column(column_name)
        added, lost = row_changes(self._project, self._table, prefix, column)
        if (added or lost) and not self._confirm_link(prefix, added, lost):
            return
        get_history().push(LinkTableCmd(self._project, self._table, prefix, column_name,
                                        self._after_change))

    def _unlink(self):
        if self._is_linked():
            get_history().push(UnlinkTableCmd(self._project, self._table, self._after_change))

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._table = None
        self._model.set_table(None)
        self._show_empty(True)

    def show_table(self, name: str):
        self._table = self._project.get_data_table(name) if self._project else None
        self._show_empty(self._table is None)
        if self._table is None:
            self._model.set_table(None)
            self.cell_selected.emit(None, None)
        self.reload()

    def on_table_deleted(self):
        self._table = None
        self._model.set_table(None)
        self.cell_selected.emit(None, None)
        self._show_empty(True)

    def reload(self):
        if not self._table:
            return
        # Une réinitialisation du modèle efface les largeurs de l'en-tête : celles de l'auteur sont reposées après.
        kept = None
        if self._user_widths and self._fit_key == (id(self._table), len(self._table.columns)):
            kept = [self._tbl.columnWidth(c) for c in range(self._model.columnCount())]
        self._updating = True
        self._model.set_table(self._table)
        # Les lignes sont numérotées À PARTIR DE 1 : c'est l'index qu'un script
        # écrit, et le modèle les expose donc à partir de 1.
        for c in range(len(self._table.columns)):
            self._tbl.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.Interactive)
        self._updating = False
        self._fit_columns(kept)
        self._update_table_header()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_columns()

    def _on_section_resized(self, *_):
        if not self._fitting and not self._updating:
            self._user_widths = True

    def _fit_columns(self, kept=None):
        """La grille est un plan de travail, pas une petite table collée au
        coin : ses colonnes initiales occupent la largeur disponible. Dès que
        l'auteur tire une colonne, ses largeurs ne sont plus jamais remplacées
        (`kept` : celles à reposer après un rechargement de la même table)."""
        count = self._model.columnCount()
        if not count:
            return
        key = (id(self._table), count)
        if key != self._fit_key:
            self._fit_key, self._user_widths, kept = key, False, None
        if self._user_widths and not kept:
            return
        self._fitting = True
        try:
            width = max(120, self._tbl.viewport().width() // count)
            for column in range(count):
                self._tbl.setColumnWidth(column, kept[column] if kept else width)
        finally:
            self._fitting = False

    def _text_preview(self, key: str) -> str:
        """La réplique que cette clé désigne, telle que le joueur la lira —
        balisage résolu, constantes cuites, comme à l'aperçu de l'écran Texte."""
        if not self._project:
            return key
        entry = next((x for x in getattr(self._project, "texts", [])
                      if x.key == key), None)
        if entry is None:
            return label("datagrid.text_not_found", name=key)
        try:
            from core.text_markup import parse, resolve
            consts = {c.name: c.value for c in getattr(self._project, "constants", [])}
            body = resolve(parse(entry.content or ""), consts)
        except Exception:
            body = entry.content or ""
        body = body.replace(chr(10), " ")
        if len(body) > 160:
            body = body[:157] + "…"
        return label("datagrid.text_preview", name=key, body=body)

    # ── Écriture d'une cellule ────────────────────────────────────

    def _write_cell(self, row_index: int, column_index: int, new) -> bool:
        """Seul chemin d'écriture du modèle vers la donnée et l'historique."""
        if self._updating or not self._table:
            return False
        col = self.column_at(column_index)
        if col is None or self.is_key_cell(col) or not (0 <= row_index < len(self._table.rows)):
            return False
        row = self._table.rows[row_index]
        old = self._table.value(row, col)
        if new == old:
            return True
        get_history().push(SetCellCmd(self._table, row, col.name, old, new,
                                      self._persist))
        self.cell_selected.emit(col, new)
        return True

    def _on_current_index(self, current: QModelIndex, _previous: QModelIndex):
        self._sync_row_actions()
        r, c = current.row(), current.column()
        col = self.column_at(c)
        if col is None or not self._table or not (0 <= r < len(self._table.rows)):
            self.cell_selected.emit(col, None)
            return
        self.cell_selected.emit(col, self._table.value(self._table.rows[r], col))

    # ── Lignes ────────────────────────────────────────────────────

    def _insert_row(self, index: int):
        if not self._table or self._is_linked():
            return
        if not self._table.columns:
            QMessageBox.information(self, label("datagrid.no_column_title"),
                                    label("datagrid.no_column_text"))
            return
        if not self._confirm_index_shift(index, inserting=True):
            return
        get_history().push(InsertRowCmd(self._table, index, {}, self._after_change))

    def _delete_row(self, index: int):
        if not self._table or self._is_linked() or not (0 <= index < len(self._table.rows)):
            return
        if not self._confirm_index_shift(index, inserting=False):
            return
        get_history().push(RemoveListItemCmd(
            self._table.rows, self._table.rows[index], self._after_change,
            label=f"Ligne {index + 1}"))

    def _duplicate_selected_row(self):
        if not self._table or self._is_linked():
            return
        row = self._tbl.currentIndex().row()
        if 0 <= row < len(self._table.rows):
            if not self._confirm_index_shift(row + 1, inserting=True):
                return
            copied = dict(self._table.rows[row])
            get_history().push(InsertRowCmd(
                self._table, row + 1, copied, self._after_change))

    def _delete_selected_row(self):
        self._delete_row(self._tbl.currentIndex().row())

    def _confirm_index_shift(self, index: int, *, inserting: bool) -> bool:
        """L'ordre affiché est celui que Lua indexe. Ajouter en fin ou retirer
        la dernière ligne ne décale rien ; tous les autres gestes le disent
        avant d'écrire (la roadmap interdit de masquer cette conséquence)."""
        if not self._table:
            return False
        shifts = index < len(self._table.rows) if inserting else index < len(self._table.rows) - 1
        if not shifts:
            return True
        message = label("datagrid.insert_shifts_indices" if inserting
                        else "datagrid.delete_shifts_indices", index=index + 1)
        return QMessageBox.question(
            self, label("datagrid.index_shift_title"), message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _row_menu(self, pos: QPoint):
        if not self._table or self._is_linked():
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
        return unique_name(base, [c.name for c in self._table.columns] if self._table else [])

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
        for t in COLUMN_CHOICES:
            a = type_menu.addAction(t)
            a.setCheckable(True)
            a.setChecked(t == col.type)
            actions[a] = t
        menu.addSeparator()
        a_add = menu.addAction(label("datagrid.add_column_menu"))
        a_del = menu.addAction(label("datagrid.delete_column"))
        add_color_actions(menu, col.color,
                          lambda color: self._set_column_color(col, color))
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

    def _set_column_color(self, column: DataColumn, color: str | None):
        color = color or ""
        if self._table and column in self._table.columns and column.color != color:
            get_history().push(SetFieldCmd(column, "color", column.color, color,
                                           label=column.name, persist_fn=self._after_change))

    # ── Après toute écriture de structure ─────────────────────────

    def _after_change(self):
        self._persist()
        self.reload()
        self.table_changed.emit()
