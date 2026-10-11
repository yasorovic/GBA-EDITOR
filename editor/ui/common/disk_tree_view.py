"""DiskTreeView — l'onglet Disk du project viewer : l'arborescence de `assets/`.

L'arbre vertical de tout le dossier ; choisir un dossier le montre dans l'onglet Disk
du panneau du bas (`folder_selected`), qui en affiche le contenu à plat. Le « + » déroule le
menu de la vue à plat (importer, asset vierge, dossier) dans le dossier choisi ; un dossier neuf est
nommé d'office puis renommé EN PLACE (pas de fenêtre), comme tout dossier, source ou script (F2, ou « Rename » au clic droit) ; la loupe filtre l'arbre par nom. La vue ne connaît ni le projet ni le
disque : `window.py` lui donne l'arbre calculé par `core.disk_tree` et fait l'écriture
(`core.disk_folders`, `core.disk_move`). La marque d'un fichier (asset, source reliée, source
sans asset, non géré) se lit à sa couleur et à son infobulle ; la racine s'appelle
« Assets »."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from core import disk_tree
from ui.common import icons
from ui.common.disk_view import (
    DRAGGING_ROLE, MIME_DISK_PATHS, DiskCallbacks, DragDimDelegate, DropCheckMixin, add_asset_actions, add_folder_color_actions, bind_delete_key, disk_mime,
    dropped_paths, file_icon, mark_color, mark_text, openable, paint_drop_target, renamable, show_plus_menu, show_sort_menu, sort_nodes, SORT_MODES,
)
from ui.common.labels import label
from ui.common.panel_bar import bar_button, panel_bar
from ui.common.theme import C, QSS, S, T
from ui.common.tooltip import tooltip
from ui.common.widgets import W
from ui.common.disk_folder_colors import color_for as folder_color_for

_PATH_ROLE = Qt.ItemDataRole.UserRole
_IS_FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
_NODE_ROLE = Qt.ItemDataRole.UserRole + 2       # le DiskNode de la ligne


class _DiskTree(DropCheckMixin, QTreeWidget):
    """L'arbre : on y glisse des fichiers et des dossiers vers un dossier de l'arbre."""

    move_requested = pyqtSignal(list, str)           # (chemins, dossier de destination)
    drop_blocked = pyqtSignal(object)                # (chemin, motif) du premier élément qu'un survol refuse
    actor_dropped = pyqtSignal(str, str)             # (acteur du canvas, dossier de destination)
    files_dropped = pyqtSignal(list, str)            # (fichiers de l'explorateur, dossier de destination)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._verdicts: dict = {}
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)      # plusieurs entrées se glissent d'un coup
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)            # sans cela les événements de glisser n'atteignent jamais l'arbre
        self.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)       # jamais Move : un dépôt accepté AILLEURS (canvas) ferait retirer la ligne par Qt
        self._drop_hover: QTreeWidgetItem | None = None       # le dossier survolé par un glisser qui pourrait le recevoir

    def mimeTypes(self):
        return [MIME_DISK_PATHS]

    def mimeData(self, items):
        root = self.topLevelItem(0)
        items = [i for i in items if i is not root]                 # la racine « Assets » ne se glisse pas
        nodes = [n for n in (i.data(0, _NODE_ROLE) for i in items) if n is not None]
        return disk_mime((i.data(0, _PATH_ROLE) for i in items), nodes if len(nodes) == len(items) else ())

    def _target(self, event) -> str | None:
        item = self.itemAt(event.position().toPoint())
        if item is None or not item.data(0, _IS_FOLDER_ROLE):
            return None
        return item.data(0, _PATH_ROLE)

    def _import_item(self, event) -> QTreeWidgetItem | None:
        """Le dossier qui recevrait des fichiers de l'explorateur : celui sous la souris, le dossier d'un fichier
        survolé, sinon la racine."""
        item = self.itemAt(event.position().toPoint())
        if item is not None and not item.data(0, _IS_FOLDER_ROLE):
            item = item.parent()
        return item if item is not None else self.topLevelItem(0)

    def startDrag(self, actions):
        """Les lignes glissées passent à demi transparentes jusqu'au dépôt (ou à l'abandon)."""
        items = self.selectedItems()
        for item in items:
            item.setData(0, DRAGGING_ROLE, True)
        try:
            super().startDrag(Qt.DropAction.CopyAction)
        finally:
            for item in items:
                try:
                    item.setData(0, DRAGGING_ROLE, False)
                except RuntimeError:                      # la vue a été reconstruite par le déplacement
                    pass
            self.viewport().update()

    def dragEnterEvent(self, event):
        self._forget_verdicts()
        mime = event.mimeData()
        if dropped_paths(mime) or self._canvas_actor(mime) or self._external_files(mime):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        paths, target = dropped_paths(event.mimeData()), self._target(event)
        if self._external_files(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self._set_drop_hover(self._import_item(event))
        elif self._canvas_actor(event.mimeData()):          # un acteur du canvas : tout dossier le reçoit
            event.setDropAction(Qt.DropAction.CopyAction)
            if target:
                event.accept()
                self._set_drop_hover(self.itemAt(event.position().toPoint()))
            else:
                event.ignore()
                self._set_drop_hover(None)
        elif paths and target and self._allowed(paths, target):
            event.acceptProposedAction()
            self._set_drop_hover(self.itemAt(event.position().toPoint()))
        else:
            event.ignore()                                # le curseur « interdit » : pas de surimpression non plus
            self._set_drop_hover(None)

    def dragLeaveEvent(self, event):
        self._set_drop_hover(None)
        self._forget_verdicts()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        target = self._target(event)
        paths = dropped_paths(event.mimeData())
        actor = self._canvas_actor(event.mimeData())
        files = self._external_files(event.mimeData())
        folder = self._import_item(event) if files else None
        self._set_drop_hover(None)
        self._forget_verdicts()
        if files and folder is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.files_dropped.emit(files, folder.data(0, _PATH_ROLE))
            return
        if target and actor:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.actor_dropped.emit(actor, target)
            return
        if not (target and paths):
            event.ignore()
            return
        event.acceptProposedAction()
        self.clearSelection()                             # sinon Qt retirerait lui-même les lignes « déplacées »
        self.move_requested.emit(paths, target)

    def _set_drop_hover(self, item: QTreeWidgetItem | None) -> None:
        """Le dossier qui recevrait le dépôt, surligné tant que la souris le survole."""
        if item is not self._drop_hover:
            self._drop_hover = item
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_hover is not None:
            rect = self.visualItemRect(self._drop_hover)
            rect.setRight(self.viewport().width() - 1)          # la rangée entière, pas seulement son texte
            paint_drop_target(self.viewport(), rect)


class DiskTreeView(QWidget):
    refresh_requested = pyqtSignal()
    move_requested = pyqtSignal(list, str)          # (chemins, dossier de destination)
    drop_blocked = pyqtSignal(object)               # (chemin, motif) : un survol que le projet refuse
    asset_open_requested = pyqtSignal(str, str, str)  # (famille, nom, chemin) : double-clic sur un asset
    actor_dropped = pyqtSignal(str, str)            # (acteur du canvas, dossier) : un acteur glissé du canvas
    folder_selected = pyqtSignal(str)               # chemin du dossier choisi
    rename_requested = pyqtSignal(str, str)         # (chemin de l'entrée, nouveau nom)
    folder_color_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar, row = panel_bar()
        refresh = bar_button(label('build.refresh'))
        refresh.setToolTip(tooltip(title=label('disk.refresh_title'), body=label('disk.refresh_tip')))
        refresh.clicked.connect(lambda: self.refresh_requested.emit())
        row.addWidget(refresh)
        row.addStretch()
        self._btn_add = W.btn_add_menu(label('disk.add_folder_tip'))
        self._btn_add.clicked.connect(self._on_add)
        row.addWidget(self._btn_add)
        self._sort = SORT_MODES[0]
        self._root: disk_tree.DiskNode | None = None
        self._btn_sort = W.btn_sort(label('disk.sort_tip'))
        self._btn_sort.clicked.connect(
            lambda: show_sort_menu(self, self._btn_sort, self._sort, self._set_sort))
        row.addWidget(self._btn_sort)
        self._btn_search = W.btn_search(label('wdg.filter_by_name'))
        self._btn_search.setCheckable(True)
        self._btn_search.toggled.connect(self._on_search_toggled)
        row.addWidget(self._btn_search)
        v.addWidget(bar)

        # Champ de filtre : masqué tant que la loupe n'est pas enfoncée ; Échap le referme.
        self._search_box = W.search_box()
        self._search_box.textChanged.connect(self._apply_filter)
        close_on_escape = self._search_box.keyPressEvent
        self._search_box.keyPressEvent = lambda e: (
            self._btn_search.setChecked(False) if e.key() == Qt.Key.Key_Escape else close_on_escape(e))
        self._search_row = QWidget()
        self._search_row.setStyleSheet(f"background:{C.BG_BASE};")
        search_layout = QHBoxLayout(self._search_row)
        search_layout.setContentsMargins(S.GUTTER, S.SM, S.MD, S.SM)
        search_layout.addWidget(self._search_box)
        self._search_row.hide()
        v.addWidget(self._search_row)

        self._tree = _DiskTree()
        self._tree.move_requested.connect(self.move_requested)
        self._tree.drop_blocked.connect(self.drop_blocked)
        self._tree.actor_dropped.connect(self.actor_dropped)
        self._tree.files_dropped.connect(self._on_files_dropped)
        self._tree.setHeaderHidden(True)
        self._tree.setFont(QFont(T.UI, T.SM))
        self._tree.setUniformRowHeights(True)
        self._tree.setItemDelegate(DragDimDelegate(lines=1, parent=self._tree, node_role=_NODE_ROLE))
        # Un clic sur une ligne déjà choisie (ou F2) en édite le nom, comme dans les autres arbres ; seules les lignes
        # `renamable` portent le drapeau d'édition (cf. `_add`).
        self._tree.setEditTriggers(QTreeWidget.EditTrigger.SelectedClicked | QTreeWidget.EditTrigger.EditKeyPressed)
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_DEEP};border:none;padding:4px;outline:none;}}"
            f"QTreeWidget::item{{padding:2px 4px;border:1px solid transparent;border-radius:3px;}}"
            f"QTreeWidget::item:hover{{background:{C.BG_HOVER};}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL};border-color:{C.BORDER_MID};}}"
            f"QTreeWidget::item:selected:active{{border-color:{C.ACCENT};}}")
        self._tree.itemExpanded.connect(lambda item: self._set_folder_icon(item, True))
        self._tree.itemCollapsed.connect(lambda item: self._set_folder_icon(item, False))
        self._tree.itemClicked.connect(self._on_clicked)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)
        bind_delete_key(self._tree, self._selected_nodes, lambda: self._callbacks)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._callbacks: DiskCallbacks | None = None
        self._tree.itemChanged.connect(self._on_item_changed)
        v.addWidget(self._tree, 1)

        self._empty = QLabel("—")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED};")
        v.addWidget(self._empty)
        self._empty.hide()

    def set_drop_check(self, check) -> None:
        self._tree.set_drop_check(check)

    def set_callbacks(self, callbacks: DiskCallbacks) -> None:
        self._callbacks = callbacks

    def _on_files_dropped(self, files: list, folder: str) -> None:
        if self._callbacks is not None:
            self._callbacks.import_paths(files, folder)

    def _selected_nodes(self) -> list:
        return [n for n in (i.data(0, _NODE_ROLE) for i in self._tree.selectedItems()) if n is not None]

    def _on_context_menu(self, position) -> None:
        """Le clic droit sur une source libre (*Create*) ou un asset (*Delete*), comme dans la vue à plat."""
        if self._callbacks is None:
            return
        item = self._tree.itemAt(position)
        if item is not None and not item.isSelected():
            self._tree.clearSelection()
            item.setSelected(True)
        nodes = self._selected_nodes()
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        # « Assets », la racine, n'est pas un dossier qu'on renomme.
        rename = None if nodes and nodes[0] is self._root else self._begin_rename_node
        add_asset_actions(menu, nodes, self._callbacks, rename)
        if len(nodes) == 1:
            add_folder_color_actions(menu, nodes[0], self.folder_color_changed.emit)
        if not menu.isEmpty():
            menu.exec(self._tree.viewport().mapToGlobal(position))

    # ── Contenu ───────────────────────────────────────────────────

    def set_tree(self, root: disk_tree.DiskNode | None) -> None:
        """Remplace l'arbre. Les dossiers dépliés le restent, le dossier choisi aussi."""
        self._root = root
        opened = self._opened_paths()
        chosen = self._chosen_path()
        self._tree.blockSignals(True)       # reconstruire n'est pas un choix de l'auteur
        self._tree.clear()
        self._empty.setVisible(root is None)
        if root is not None:
            top = self._add(self._tree.invisibleRootItem(), root, label('disk.root'))
            self._restore(top, opened, chosen, is_root=True)
        self._tree.blockSignals(False)
        W.filter_tree(self._tree, self._search_box.text())     # un rafraîchissement garde le filtre

    def _add(self, parent: QTreeWidgetItem, node: disk_tree.DiskNode, text: str | None = None):
        item = QTreeWidgetItem(parent)
        item.setText(0, text if text is not None else node.name)
        item.setData(0, _PATH_ROLE, str(node.path))
        item.setData(0, _IS_FOLDER_ROLE, node.kind == disk_tree.FOLDER)
        item.setData(0, _NODE_ROLE, node)
        if renamable(node) and parent is not self._tree.invisibleRootItem():     # la racine « Assets » ne se renomme pas
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        if node.kind == disk_tree.FOLDER:
            item.setIcon(0, icons.folder_icon(False, folder_color_for(node.path) or icons.COLOR_FOLDER))
            item.setForeground(0, QColor(C.TEXT_HI))
            for child in sort_nodes(node.children, self._sort):
                self._add(item, child)
            return item
        item.setIcon(0, file_icon(node))
        item.setForeground(0, QColor(mark_color(node.kind)))
        item.setToolTip(0, mark_text(node))
        return item

    def _set_sort(self, mode: str) -> None:
        self._sort = mode
        self.set_tree(self._root)

    # ── Filtre ────────────────────────────────────────────────────

    def _on_search_toggled(self, shown: bool) -> None:
        self._search_row.setVisible(shown)
        if shown:
            self._search_box.setFocus()
        else:
            self._search_box.clear()                # remet tout l'arbre en vue

    def _apply_filter(self, text: str) -> None:
        W.filter_tree(self._tree, text)

    # ── Nouveau dossier, renommé en place ─────────────────────────

    def _target_folder(self) -> str | None:
        """Le dossier où le « + » crée : le dossier choisi (celui d'un fichier choisi, ou la racine à défaut)."""
        item = self._tree.currentItem()
        if item is not None and not item.data(0, _IS_FOLDER_ROLE):
            item = item.parent()
        if item is None:
            item = self._tree.topLevelItem(0)
        return item.data(0, _PATH_ROLE) if item is not None else None

    def _on_add(self) -> None:
        """Le « + » : le même menu que celui de la vue à plat (importer, créer un asset vierge, un dossier),
        dans le dossier choisi. Le filtre est levé : un dossier neuf ne le satisfait jamais."""
        self._btn_search.setChecked(False)
        show_plus_menu(self, self._btn_add, self._target_folder(), self._callbacks)

    def _begin_rename_node(self, node: disk_tree.DiskNode) -> None:
        if node is not self._root:
            self.begin_rename(str(node.path))

    def begin_rename(self, path: str) -> None:
        """L'entrée `path` (un dossier qui vient d'être créé, ou celle qu'on renomme) devient une ligne éditable."""
        item = self._find(path)
        if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
            return
        parent = item.parent()
        while parent is not None:                   # l'entrée doit se voir
            parent.setExpanded(True)
            parent = parent.parent()
        self._tree.setCurrentItem(item)
        # L'éditeur s'ouvre APRÈS la fin du clic sur « + » : à la fin d'un clic, le focus revient
        # au bouton, et un éditeur ouvert pendant ce temps se refermait aussitôt.
        QTimer.singleShot(0, lambda: self._tree.editItem(item, 0))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Le nom validé dans l'éditeur ; un nom inchangé (ou Échap) ne demande rien."""
        path = item.data(0, _PATH_ROLE)
        if (column == 0 and path and item.flags() & Qt.ItemFlag.ItemIsEditable      # pas la racine « Assets »
                and item.text(0) != Path(path).name):
            self.rename_requested.emit(path, item.text(0))

    def _find(self, path: str) -> QTreeWidgetItem | None:
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _PATH_ROLE) == path:
                return item
            stack.extend(item.child(i) for i in range(item.childCount()))
        return None

    def select_file(self, path: str) -> None:
        """Déplie les dossiers jusqu'à `path`, le sélectionne et l'amène en vue. Sans effet si l'arbre ne le contient pas.
        Le filtre est levé : il pourrait cacher la ligne."""
        self._btn_search.setChecked(False)
        item = self._find(str(path))
        if item is None:
            return
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self._tree.clearSelection()
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item)

    # ── Choix d'un dossier ────────────────────────────────────────

    def _on_clicked(self, item: QTreeWidgetItem) -> None:
        if item.data(0, _IS_FOLDER_ROLE):
            self.folder_selected.emit(item.data(0, _PATH_ROLE))

    def _on_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        node = item.data(0, _NODE_ROLE)
        target = openable(node) if node is not None else None
        if target is not None:
            self.asset_open_requested.emit(*target)

    def _chosen_path(self) -> str | None:
        item = self._tree.currentItem()
        return item.data(0, _PATH_ROLE) if item is not None else None

    # ── Dossiers dépliés ──────────────────────────────────────────

    def _opened_paths(self) -> set[str]:
        out: set[str] = set()
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.isExpanded():
                out.add(item.data(0, _PATH_ROLE))
            stack.extend(item.child(i) for i in range(item.childCount()))
        return out

    def _restore(self, item: QTreeWidgetItem, opened: set[str], chosen: str | None,
                 *, is_root: bool = False) -> None:
        # La racine s'ouvre d'elle-même la première fois ; ensuite on rend ce que
        # l'auteur avait ouvert.
        if item.childCount() and (item.data(0, _PATH_ROLE) in opened or (is_root and not opened)):
            item.setExpanded(True)
        if chosen is not None and item.data(0, _PATH_ROLE) == chosen:
            self._tree.setCurrentItem(item)
        for i in range(item.childCount()):
            self._restore(item.child(i), opened, chosen)

    @staticmethod
    def _set_folder_icon(item: QTreeWidgetItem, expanded: bool) -> None:
        item.setIcon(0, icons.folder_icon(expanded, folder_color_for(item.data(0, _PATH_ROLE)) or icons.COLOR_FOLDER))
