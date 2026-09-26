"""ui/script_editor/var_table_panel.py — table GLOBALS/CONSTANTS de la sidebar Script Editor."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
    QComboBox, QAbstractItemView, QMenu, QMessageBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import C, T, S, QSS
from ui.common.labels import label
from core.models.settings import Constant, GlobalVar
from core.command_dispatcher import unique_name
from .colors import _C_GLOBAL, _C_CONST


# Même grammaire que les autres viewers : fond du panneau, retrait de contenu,
# sélection périwinkle, en-tête de colonnes en intertitre discret.
_TBL_SS = f"""
QTableWidget {{
    background:{C.BG_BASE}; color:{C.TEXT_HI};
    border:none; gridline-color:transparent;
    font-family:{T.CODE}; font-size:{T.MD}px;
    outline:none;
    padding-left:{S.LG}px; padding-right:{S.SM}px;
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
}}
QHeaderView::section {{
    background:transparent; color:{C.TEXT_MUTED};
    border:none; border-bottom:1px solid {C.BORDER_DARK};
    font-family:{T.UI_STACK}; font-size:{T.XS}px;
    font-weight:700; letter-spacing:1px;
    padding:3px 4px;
}}
QTableWidget::item {{ padding:1px 4px; }}
QTableWidget::item:hover {{ background:{C.BG_PANEL}; }}
QComboBox {{
    background:{C.BG_INPUT}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
}}
QComboBox QAbstractItemView {{
    background:{C.BG_RAISED}; color:{C.TEXT_HI};
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
}}
"""


class VarTablePanel(QWidget):
    """
    Tableau nom/type/valeur pour GLOBALS ou CONSTANTS, déclarées dans le
    projet. Double-clic sur une ligne → insère un snippet get (et set pour
    les globals) au curseur. Clic droit → même menu + Supprimer, et pour les
    globals, Array (la cellule Value devient une taille) et Persist (SRAM).

    Pas de header propre : posé via FinderSection.set_widget() pour la même
    apparence (flèche + titre coloré + boutons +/recherche) que les autres
    finders — le bouton "+" de la section appelle add_var() directement.
    """
    snippet_requested = pyqtSignal(str)
    changed           = pyqtSignal()   # pour notifier le projet de sauvegarder

    def __init__(self, kind: str = "global", parent=None):
        super().__init__(parent)
        self._kind = kind   # "global" | "const"
        self._project = None
        self._updating = False
        self._label = label("vartbl.globals") if kind == "global" else label("vartbl.constants")
        self._color = _C_GLOBAL if kind == "global" else _C_CONST
        value_col = "default" if kind == "global" else "value"
        # Name | Type | Value, pour les deux tables — le format d'origine.
        # « Array » (nombre de cases, ROADMAP v0.20) et « persist » (SRAM,
        # v0.5) ne sont pas des colonnes : une constante ne change jamais, et
        # un global n'est qu'exceptionnellement un tableau ou persistant.
        # Deux propriétés d'exception qui réclameraient leur propre colonne
        # sur TOUTES les lignes pour ne dire quelque chose que sur quelques-
        # unes — le clic droit les porte, la cellule Value en montrant l'état
        # (cf. `_append_row`).
        self._cols = ["name", "type", value_col]
        self._col_value = self._cols.index(value_col)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Table : nom / type / défaut ou valeur.
        self._tbl = QTableWidget(0, len(self._cols))
        self._tbl.setStyleSheet(_TBL_SS)
        self._tbl.setHorizontalHeaderLabels(self._cols)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(self._cols)):
            self._tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self._tbl.setColumnWidth(1, 46)
        self._tbl.setColumnWidth(self._col_value, 46)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._ctx_menu)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.cellDoubleClicked.connect(self._on_double_click)
        self._tbl.setMaximumHeight(self._MAX_H)
        # Hauteur réglée sur le contenu (cf. `_fit`) et politique NON extensible :
        # la section se cale alors dessus au lieu de réclamer de la place, et la
        # suivante vient se ferrer juste en dessous. Sans ça, la table garde son
        # sizeHint de QTableWidget — bien plus haut que deux lignes — et creuse
        # un vide sous elle.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        root.addWidget(self._tbl)
        self._fit()

    # Une table vide montre quand même son en-tête ; au-delà de _MAX_H elle
    # défile plutôt que de repousser les sections voisines hors de l'écran.
    _MAX_H = 240

    def _fit(self):
        header = self._tbl.horizontalHeader().height()
        rows = sum(self._tbl.rowHeight(r) for r in range(self._tbl.rowCount()))
        self._tbl.setFixedHeight(min(header + rows + 4, self._MAX_H))

    def _entries(self):
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def set_project(self, project):
        self._project = project
        self._reload()

    def _reload(self):
        self._updating = True
        self._tbl.setRowCount(0)
        for e in self._entries():
            self._append_row(e.name, e.type, entry=e)
        self._updating = False
        self._fit()

    def _append_row(self, name="var", typ="int", entry=None):
        row = self._tbl.rowCount()
        self._tbl.insertRow(row)
        self._tbl.setRowHeight(row, S.ROW)

        name_item = QTableWidgetItem(name)
        name_item.setForeground(QColor(self._color))
        # La ligne retient l'entrée dont elle vient, et non son rang : supprimer
        # une ligne décale toutes les suivantes, et un rang décalé ferait écrire
        # les valeurs d'une variable dans une autre.
        name_item.setData(Qt.ItemDataRole.UserRole, entry)
        self._tbl.setItem(row, 0, name_item)

        combo = QComboBox()
        combo.addItems(["int", "bool", "u8", "u16", "s8", "s16"])
        combo.setCurrentText(typ)
        combo.setStyleSheet(_TBL_SS)
        combo.currentTextChanged.connect(lambda _, r=row: self._sync_to_project())
        self._tbl.setCellWidget(row, 1, combo)

        # « Array » (ROADMAP v0.20) n'a plus sa propre colonne — clic droit →
        # Array pour l'activer. Une fois active, cette cellule ne montre plus
        # le défaut mais la TAILLE, et se tape directement à l'écran ("value
        # défini sa taille") ; couleur distincte pour ne pas la lire comme un
        # défaut ordinaire.
        is_array = self._kind == "global" and entry is not None and entry.count > 1
        if is_array:
            shown = entry.count
        elif self._kind == "global":
            shown = entry.default if entry is not None else 0
        else:
            shown = entry.value if entry is not None else 0
        value_item = QTableWidgetItem(str(shown))
        value_item.setForeground(QColor(C.ACCENT) if is_array else QColor(C.SYNTAX_NUMBER))
        if is_array:
            value_item.setToolTip(label("vartbl.array_tip"))
        self._tbl.setItem(row, self._col_value, value_item)

    def _add_var(self):
        """Pas de boîte de dialogue : un nom automatique, la ligne s'ouvre
        directement en édition (cf. « inline plutôt que dialogues »)."""
        if not self._project:
            return
        base = "global" if self._kind == "global" else "const"
        name = unique_name(base, {e.name for e in self._entries()})
        entry = self._project.add_variable(self._kind, name)
        if entry is None:
            return   # le nom vient d'être garanti libre — ne devrait pas arriver
        self._updating = True
        self._append_row(entry.name, entry.type, entry=entry)
        self._updating = False
        self.changed.emit()
        row = self._tbl.rowCount() - 1
        self._tbl.editItem(self._tbl.item(row, 0))

    def _on_item_changed(self, item):
        if self._updating:
            return
        # Le NOM ne se recopie pas, il se renomme : c'est la seule colonne dont
        # la valeur est citée ailleurs (appels Lua, `$nom` dans un texte).
        if item.column() == 0:
            self._rename_from_cell(item)
            return
        self._sync_to_project()

    def _rename_from_cell(self, item):
        """Renomme via le projet, seul chemin qui suit les CITATIONS du nom.

        Écrire `entry.name` directement laisserait derrière chaque
        `global.ancien` et chaque `$ancien` d'un texte — le build échouerait
        bien plus tard sur un `g_ancien` indéfini, sans rien qui ramène au
        renommage. `Project.rename_variable` réécrit les deux, refuse un
        doublon et dit combien de références il a touchées.

        (L'id, lui, ne bouge pas : les fichiers de DONNÉES citent la variable
        par id justement pour ne pas dépendre de son nom, cf. `_sync_to_project`.)"""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            # Ligne neuve, pas encore adossée à une entrée : rien à renommer.
            self._sync_to_project()
            return
        old, new = entry.name, item.text().strip()
        if new == old:
            return
        if self._project and self._project.rename_variable(self._kind, entry, new):
            self._updating = True
            item.setText(entry.name)   # normalisé par le projet (espaces retirés)
            self._updating = False
            self.changed.emit()
            return
        # Refusé : la cellule doit revenir au nom réel, sinon la table affiche
        # une variable qui n'existe sous ce nom nulle part.
        self._updating = True
        item.setText(old)
        self._updating = False
        if new and self._project and self._project.variable_name_taken(
                self._kind, new, exclude=entry):
            QMessageBox.warning(self, label("common.duplicate"),
                                label("vartbl.dup_msg", name=new))

    def _sync_to_project(self):
        """Reporte la table dans le projet, en MODIFIANT les entrées existantes.

        Reconstruire des `GlobalVar` neufs à chaque édition perdrait tout ce que
        la table n'affiche pas — `id` en tête. Or l'id est l'identité opaque que
        citent les références de champ et les fichiers de sauvegarde : le
        régénérer à la volée casserait le lien de chaque référence stockée, sans
        rien qui le signale. Chaque ligne porte l'entrée dont elle vient ; une
        ligne qui n'en a pas est une ligne neuve."""
        if not self._project or self._updating:
            return
        from core.models.settings import Constant, GlobalVar
        entries = []
        for row in range(self._tbl.rowCount()):
            name_item = self._tbl.item(row, 0)
            combo     = self._tbl.cellWidget(row, 1)
            val_item  = self._tbl.item(row, self._col_value)
            if name_item is None:
                continue
            name  = name_item.text().strip()
            typ   = combo.currentText() if combo else "int"
            value = int(val_item.text() or "0") if val_item else 0
            if not name:
                continue
            entry = name_item.data(Qt.ItemDataRole.UserRole)
            if entry is None:
                entry = (Constant(name=name) if self._kind == "const"
                         else GlobalVar(name=name))
                name_item.setData(Qt.ItemDataRole.UserRole, entry)
            # Le nom n'est PAS recopié ici : il appartient à `_rename_from_cell`,
            # qui seul sait réécrire ce qui le cite. Une entrée neuve, elle, l'a
            # déjà reçu de son constructeur.
            entry.type = typ
            if self._kind == "const":
                entry.value = value
            elif entry.count > 1:
                # Mode tableau (clic droit → Array, cf. `_ctx_menu`) : cette
                # cellule montre et édite la TAILLE, pas le défaut — celui-ci
                # n'est pas touché tant qu'on reste en mode tableau.
                entry.count = max(1, value)
            else:
                entry.default = value
            # `persist` ne vient plus d'une cellule : `_ctx_menu` le pose
            # directement sur l'entrée, ce tour de table ne doit pas l'écraser.
            entries.append(entry)
        if self._kind == "const":
            self._project.constants = entries
        else:
            self._project.globals = entries
        self._project.save_variables()
        self.changed.emit()

    def _snippet_get(self, name: str, count: int = 1) -> str:
        # Accès pointé (chantier global/const) : nu pour un scalaire, indexé pour un
        # tableau — les deux compilent, il n'y a plus de forme à écarter.
        if self._kind == "const":
            return f'const.{name}'
        return f'global.{name}[1]' if count > 1 else f'global.{name}'

    def _row_count_cells(self, row) -> int:
        name_item = self._tbl.item(row, 0)
        entry = name_item.data(Qt.ItemDataRole.UserRole) if name_item else None
        return max(1, getattr(entry, "count", 1)) if entry is not None else 1

    def _on_double_click(self, row, col):
        name_item = self._tbl.item(row, 0)
        if name_item:
            self.snippet_requested.emit(
                self._snippet_get(name_item.text(), self._row_count_cells(row)))

    def _ctx_menu(self, pos: QPoint):
        row = self._tbl.rowAt(pos.y())
        if row < 0:
            return
        name_item = self._tbl.item(row, 0)
        if not name_item:
            return
        name = name_item.text()
        entry = name_item.data(Qt.ItemDataRole.UserRole)
        n = self._row_count_cells(row)
        write_snippet = f'global.{name}[1] = ' if n > 1 else f'global.{name} = '
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        a_get = menu.addAction(self._snippet_get(name, n))
        a_set = (menu.addAction(write_snippet.rstrip(" ") + "...")
                 if self._kind == "global" else None)
        # Array et Persist n'ont pas de colonne (cf. `__init__`) : deux cases
        # à cocher ici, plutôt que deux colonnes vides sur presque toutes les
        # lignes.
        a_array = a_persist = None
        if self._kind == "global" and entry is not None:
            menu.addSeparator()
            a_array = menu.addAction(label("vartbl.array"))
            a_array.setCheckable(True)
            a_array.setChecked(entry.count > 1)
            a_persist = menu.addAction(label("vartbl.persist"))
            a_persist.setCheckable(True)
            a_persist.setChecked(entry.persist)
        menu.addSeparator()
        a_del = menu.addAction(label("common.delete"))
        action = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if action == a_get:
            self.snippet_requested.emit(self._snippet_get(name, n))
        elif a_set is not None and action == a_set:
            self.snippet_requested.emit(write_snippet)
        elif a_array is not None and action == a_array:
            self._toggle_array(entry)
        elif a_persist is not None and action == a_persist:
            entry.persist = not entry.persist
            self._project.save_variables()
            self.changed.emit()
        elif action == a_del:
            self._delete_row(row)

    def _toggle_array(self, entry):
        """Bascule une variable simple en tableau et inversement.

        La cellule Value change de sens en même temps (défaut ↔ taille,
        cf. `_append_row`) : un `_reload()` complet est le plus sûr moyen de
        ne pas laisser l'ancien sens affiché sur la nouvelle cellule."""
        if entry.count > 1:
            entry.count = 1
            entry.default = 0   # la case redevient un défaut, pas une taille périmée
        else:
            entry.count = 8     # taille de départ ; l'auteur l'ajuste dans la cellule
        self._project.save_variables()
        self.changed.emit()
        self._reload()

    def _delete_row(self, row):
        self._tbl.removeRow(row)
        self._sync_to_project()
