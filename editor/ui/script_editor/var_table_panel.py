"""ui/script_editor/var_table_panel.py — liste GLOBALS/CONSTANTS de la sidebar Script Editor."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QComboBox, QMenu,
    QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import C, T, S, QSS
from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.command_dispatcher import unique_name
from .colors import _C_GLOBAL, _C_CONST


_TYPES = ["int", "bool", "u8", "u16", "s8", "s16", "string"]
_STRING = "string"
_COMBO_WIDTH, _VALUE_WIDTH = 76, 64   # fixes : changer de type ne décale plus la ligne


def _type_tooltip(type_: str) -> str:
    """L'infobulle d'un type : son nom, sa portée, et ce que la string ne permet pas."""
    return tooltip(
        title=type_, body=label(f"vartbl.type_{type_}_tip"),
        note=label("vartbl.type_string_note") if type_ == _STRING else "",
    )

# Une ligne = un nom cliquable + son type + sa valeur, sans grille ni en-tête :
# le nom se lit comme les boutons des autres sections de la sidebar.
_ROW_SS = f"""
QPushButton#varName {{
    background:none; border:none; text-align:left; padding:2px 4px;
    font-family:{T.CODE}; font-size:{T.MD}px;
}}
QPushButton#varName:hover {{ background:{C.BG_PANEL}; color:{C.TEXT_HI}; }}
QLineEdit, QComboBox {{
    background:{C.BG_INPUT}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px; padding:0 3px;
}}
QComboBox QAbstractItemView {{
    background:{C.BG_RAISED}; color:{C.TEXT_HI};
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
}}
"""


class _VarRow(QWidget):
    """Une variable. Le clic sur le nom insère son accès ; le renommage passe
    par le clic droit (ou s'ouvre de lui-même sur une variable neuve) — un
    double-clic ne pouvait pas servir aux deux, l'insertion l'emportait."""

    name_clicked   = pyqtSignal(object)           # entry
    renamed        = pyqtSignal(object, str)      # entry, nouveau nom
    edited         = pyqtSignal()                 # type ou valeur modifiés
    menu_requested = pyqtSignal(object, QPoint)   # entry, position globale

    def __init__(self, entry, kind: str, color: str, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._kind = kind
        self.setStyleSheet(_ROW_SS)
        self.setFixedHeight(S.ROW)
        row = QHBoxLayout(self)
        row.setContentsMargins(S.LG, 0, S.SM, 0)
        row.setSpacing(4)

        self._name_btn = QPushButton(entry.name)
        self._name_btn.setObjectName("varName")
        self._name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_btn.setStyleSheet(f"QPushButton#varName{{color:{color};}}")
        self._name_btn.setToolTip(tooltip(title=label("vartbl.insert_title")))
        self._name_btn.clicked.connect(lambda: self.name_clicked.emit(self.entry))
        self._name_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._name_btn.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.entry, self._name_btn.mapToGlobal(pos)))
        self._name_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._name_btn, 1)

        self._name_edit = QLineEdit(entry.name)
        self._name_edit.setToolTip(tooltip(title=label("vartbl.rename"), body=label("vartbl.rename_tip")))
        self._name_edit.hide()
        self._renaming = False
        self._name_edit.editingFinished.connect(self._commit_rename)
        row.addWidget(self._name_edit, 1)

        self._combo = QComboBox()
        self._combo.addItems(_TYPES)
        for i, type_ in enumerate(_TYPES):
            self._combo.setItemData(i, _type_tooltip(type_), Qt.ItemDataRole.ToolTipRole)
        self._combo.setCurrentText(entry.type)
        self._combo.setFixedWidth(_COMBO_WIDTH)
        self._combo.currentTextChanged.connect(self._on_type)
        self._refresh_type_tip()
        row.addWidget(self._combo)

        self._value = QLineEdit()
        self._value.setFixedWidth(_VALUE_WIDTH)
        self._value.setToolTip(tooltip(title=label("vartbl.value_title")))
        self._value.editingFinished.connect(self._on_value)
        row.addWidget(self._value)
        self.refresh_value()

    # « Array » (ROADMAP v0.20) : une fois actif, la cellule ne montre plus le
    # défaut mais la TAILLE — couleur distincte pour ne pas la lire comme un
    # défaut ordinaire.
    def _is_array(self) -> bool:
        return self._kind == "global" and self.entry.count > 1

    def _is_string(self) -> bool:
        return self.entry.type == _STRING

    def _refresh_type_tip(self):
        """Le tooltip fermé du combo décrit le type COURANT ; ceux de la liste,
        chacun le sien."""
        self._combo.setToolTip(_type_tooltip(self.entry.type))

    def refresh_value(self):
        # Une string est un texte ; un tableau de strings garde sa taille dans la cellule.
        text_mode = self._is_string() and not self._is_array()
        if self._is_array():
            shown, color, tip = self.entry.count, C.ACCENT, tooltip(
                title=label("vartbl.array"), body=label("vartbl.array_tip"),
                note=label("vartbl.array_note"),
            )
        else:
            shown = self.entry.value if self._kind == "const" else self.entry.default
            color = C.SYNTAX_STRING if text_mode else C.SYNTAX_NUMBER
            tip = (tooltip(title=label("vartbl.value_title"),
                           body=label("vartbl.string_value_tip"))
                   if text_mode else tooltip(title=label("vartbl.value_title")))
        self._value.setText(str(shown))
        self._value.setToolTip(tip)
        self._value.setStyleSheet(f"color:{color};")

    def begin_rename(self):
        self._renaming = True
        self._name_btn.hide()
        self._name_edit.setText(self.entry.name)
        self._name_edit.show()
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _commit_rename(self):
        if not self._renaming:      # editingFinished tire aussi au masquage
            return
        self._renaming = False
        new = self._name_edit.text().strip()
        self._name_edit.hide()
        self._name_btn.show()
        if new and new != self.entry.name:
            self.renamed.emit(self.entry, new)
        self._name_btn.setText(self.entry.name)  # le nom réel : un refus le laisse intact

    def _on_type(self, text: str):
        was_string = self._is_string()
        self.entry.type = text
        if was_string != self._is_string():
            # Un nombre n'est pas un texte : la valeur repart de zéro / du vide
            # plutôt que de garder une chaîne là où le C attend un entier.
            reset = "" if self._is_string() else 0
            if self._kind == "const":
                self.entry.value = reset
            else:
                self.entry.default = reset
            if self._is_string() and self._kind == "global":
                self.entry.persist = False   # un index de texte ne se sauvegarde pas
            self.refresh_value()
        self._refresh_type_tip()
        self.edited.emit()

    def _on_value(self):
        if self._is_string() and not self._is_array():
            value = self._value.text()
        else:
            try:
                value = int(self._value.text() or "0")
            except ValueError:
                self.refresh_value()
                return
        if self._kind == "const":
            self.entry.value = value
        elif self.entry.count > 1:
            # Mode tableau (clic droit → Array) : la cellule édite la TAILLE ;
            # le défaut n'est pas touché tant qu'on reste en mode tableau.
            self.entry.count = max(1, value)
        else:
            self.entry.default = value
        self.refresh_value()
        self.edited.emit()


class VarTablePanel(QWidget):
    """
    Liste des GLOBALS ou CONSTANTS déclarées dans le projet : un nom, son type,
    sa valeur. Clic sur le nom → insère l'accès (`global.x`, `const.x`). Clic
    droit → accès, écriture (globals), Renommer, Array (la valeur devient une
    taille), Persist (SRAM) et Supprimer.

    Pas de header propre : posé via FinderSection.set_widget() pour la même
    apparence (flèche + titre coloré + boutons +/recherche) que les autres
    finders — le bouton "+" de la section appelle `_add_var()` directement.
    """
    snippet_requested = pyqtSignal(str)
    changed           = pyqtSignal()   # pour notifier le projet de sauvegarder

    def __init__(self, kind: str = "global", parent=None):
        super().__init__(parent)
        self._kind = kind   # "global" | "const"
        self._project = None
        self._color = _C_GLOBAL if kind == "global" else _C_CONST
        self._rows: list[_VarRow] = []

        # « Array » et « persist » n'ont pas de colonne : une constante ne change
        # jamais, et un global n'est qu'exceptionnellement un tableau ou
        # persistant. Le clic droit les porte, la cellule valeur en montre l'état.
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def _entries(self):
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def set_project(self, project):
        self._project = project
        self._reload()

    def _reload(self):
        for row in self._rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for entry in self._entries():
            self._append_row(entry)

    def _append_row(self, entry) -> _VarRow:
        row = _VarRow(entry, self._kind, self._color)
        row.name_clicked.connect(self._on_name_clicked)
        row.renamed.connect(self._rename)
        row.edited.connect(self._save)
        row.menu_requested.connect(self._ctx_menu)
        self._layout.addWidget(row)
        self._rows.append(row)
        return row

    def _add_var(self):
        """Pas de boîte de dialogue : un nom automatique, la ligne s'ouvre
        directement en renommage (cf. « inline plutôt que dialogues »)."""
        if not self._project:
            return
        base = "global" if self._kind == "global" else "const"
        name = unique_name(base, {e.name for e in self._entries()})
        entry = self._project.add_variable(self._kind, name)
        if entry is None:
            return   # le nom vient d'être garanti libre — ne devrait pas arriver
        row = self._append_row(entry)
        self.changed.emit()
        row.begin_rename()

    def _save(self):
        if self._project:
            self._project.save_variables()
            self.changed.emit()

    def _rename(self, entry, new: str):
        """Renomme via le projet, seul chemin qui suit les CITATIONS du nom.

        Écrire `entry.name` directement laisserait derrière chaque
        `global.ancien` et chaque `$ancien` d'un texte — le build échouerait
        bien plus tard sur un `g_ancien` indéfini, sans rien qui ramène au
        renommage. `Project.rename_variable` réécrit les deux et refuse un
        doublon.

        (L'id, lui, ne bouge pas : les fichiers de DONNÉES citent la variable
        par id justement pour ne pas dépendre de son nom.)"""
        if not self._project:
            return
        if self._project.rename_variable(self._kind, entry, new):
            self.changed.emit()
        elif self._project.variable_name_taken(self._kind, new, exclude=entry):
            QMessageBox.warning(self, label("common.duplicate"),
                                label("vartbl.dup_msg", name=new))

    def _row_of(self, entry) -> _VarRow | None:
        return next((r for r in self._rows if r.entry is entry), None)

    def _snippet_get(self, entry) -> str:
        # Accès pointé (chantier global/const) : nu pour un scalaire, indexé pour un
        # tableau — les deux compilent, il n'y a plus de forme à écarter.
        if self._kind == "const":
            return f'const.{entry.name}'
        return f'global.{entry.name}[1]' if entry.count > 1 else f'global.{entry.name}'

    def _on_name_clicked(self, entry):
        self.snippet_requested.emit(self._snippet_get(entry))

    def _ctx_menu(self, entry, global_pos: QPoint):
        is_array = self._kind == "global" and entry.count > 1
        write_snippet = f'global.{entry.name}[1] = ' if is_array else f'global.{entry.name} = '
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        a_get = menu.addAction(self._snippet_get(entry))
        a_set = (menu.addAction(write_snippet.rstrip(" ") + "...")
                 if self._kind == "global" else None)
        menu.addSeparator()
        a_rename = menu.addAction(label("vartbl.rename"))
        a_array = a_persist = None
        if self._kind == "global":
            a_array = menu.addAction(label("vartbl.array"))
            a_array.setCheckable(True)
            a_array.setChecked(is_array)
            a_persist = menu.addAction(label("vartbl.persist"))
            a_persist.setCheckable(True)
            a_persist.setChecked(entry.persist)
            a_persist.setEnabled(entry.type != _STRING)
        menu.addSeparator()
        a_del = menu.addAction(label("common.delete"))
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == a_get:
            self.snippet_requested.emit(self._snippet_get(entry))
        elif a_set is not None and action == a_set:
            self.snippet_requested.emit(write_snippet)
        elif action == a_rename:
            row = self._row_of(entry)
            if row:
                row.begin_rename()
        elif a_array is not None and action == a_array:
            self._toggle_array(entry)
        elif a_persist is not None and action == a_persist:
            entry.persist = not entry.persist
            self._save()
        elif action == a_del:
            self._delete(entry)

    def _toggle_array(self, entry):
        """Bascule une variable simple en tableau et inversement ; la cellule
        valeur change de sens en même temps (défaut ↔ taille)."""
        if entry.count > 1:
            entry.count = 1
            entry.default = "" if entry.type == _STRING else 0   # un défaut, pas une taille périmée
        else:
            entry.count = 8     # taille de départ ; l'auteur l'ajuste dans la cellule
        self._save()
        row = self._row_of(entry)
        if row:
            row.refresh_value()

    def _delete(self, entry):
        if not self._project:
            return
        entries = [e for e in self._entries() if e is not entry]
        if self._kind == "const":
            self._project.constants = entries
        else:
            self._project.globals = entries
        row = self._row_of(entry)
        if row:
            self._rows.remove(row)
            self._layout.removeWidget(row)
            row.deleteLater()
        self._save()
