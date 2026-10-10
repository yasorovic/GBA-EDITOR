"""DiskTreeView — l'onglet Disk du project viewer : l'arborescence de `assets/`.

L'arbre vertical de tout le dossier ; choisir un dossier le montre dans l'onglet Disk
du panneau du bas (`folder_selected`), qui en affiche le contenu à plat. Le « + » déroule le
menu de la vue à plat (importer, asset vierge, dossier) dans le dossier choisi ; un dossier neuf est
nommé d'office puis renommé EN PLACE (pas de fenêtre) ; la loupe filtre l'arbre par nom. La vue ne connaît ni le projet ni le
disque : `window.py` lui donne l'arbre calculé par `core.disk_tree` et fait l'écriture
(`core.disk_folders`). La marque d'un fichier (asset, source reliée, source
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
    DRAGGING_ROLE, MIME_DISK_PATHS, DiskCallbacks, DragDimDelegate, DropCheckMixin, add_asset_actions, bind_delete_key, disk_mime,
    dropped_paths, file_icon, mark_color, mark_text, openable, paint_drop_target, show_plus_menu, show_sort_menu, sort_nodes, SORT_MODES,
)
from ui.common.labels import label
from ui.common.panel_bar import bar_button, panel_bar
from ui.common.theme import C, QSS, S, T
from ui.common.tooltip import tooltip
from ui.common.widgets import W

_PATH_ROLE = Qt.ItemDataRole.UserRole
_IS_FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
_NODE_ROLE = Qt.ItemDataRole.UserRole + 2       # le DiskNode de la ligne


class _DiskTree(DropCheckMixin, QTreeWidget):
    """L'arbre : on y glisse des fichiers et des dossiers vers un dossier de l'arbre."""

    move_requested = pyqtSignal(list, str)           # (chemins, dossier de destination)
    drop_blocked = pyqtSignal(object)                # (chemin, motif) du premier élément qu'un survol refuse
    actor_dropped = pyqtSignal(str, str)             # (acteur du canvas, dossier de destination)

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
        if dropped_paths(event.mimeData()) or self._canvas_actor(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        paths, target = dropped_paths(event.mimeData()), self._target(event)
        if self._canvas_actor(event.mimeData()):          # un acteur du canvas : tout dossier le reçoit
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
        self._set_drop_hover(None)
        self._forget_verdicts()
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
    folder_rename_requested = pyqtSignal(str, str)  # (chemin du dossier, nouveau nom)

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
        self._tree.setHeaderHidden(True)
        self._tree.setFont(QFont(T.UI, T.SM))
        self._tree.setUniformRowHeights(True)
        self._tree.setItemDelegate(DragDimDelegate(lines=1, parent=self._tree))
        self._tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_DEEP};border:none;padding:2px;}}"
            f"QTreeWidget::item{{padding:2px 4px;}}"
            f"QTreeWidget::item:hover{{background:{C.BG_HOVER};}}"
            f"QTreeWidget::item:selected{{background:{C.BG_HOVER};}}")
        self._tree.itemExpanded.connect(lambda item: self._set_folder_icon(item, True))
        self._tree.itemCollapsed.connect(lambda item: self._set_folder_icon(item, False))
        self._tree.itemClicked.connect(self._on_clicked)
        self._tree.itemDoubleClicked.connect(self._on_double_clicked)
        bind_delete_key(self._tree, self._selected_nodes, lambda: self._callbacks)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._callbacks: DiskCallbacks | None = None
        self._tree.itemChanged.connect(self._on_item_changed)
        self._renaming: str | None = None           # le dossier dont le nom s'édite en ce moment
        # L'éditeur se referme à la validation comme à Échap, qu'il y ait eu changement ou non :
        # c'est là qu'on rend la ligne non éditable.
        self._tree.itemDelegate().closeEditor.connect(self._end_rename)
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
        add_asset_actions(menu, nodes, self._callbacks)
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
        if node.kind == disk_tree.FOLDER:
            item.setIcon(0, icons.folder_icon(False))
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

    def begin_rename(self, path: str) -> None:
        """Le dossier `path` (qui vient d'être créé) devient une ligne éditable."""
        item = self._find(path)
        if item is None:
            return
        parent = item.parent()
        while parent is not None:                   # le dossier neuf doit se voir
            parent.setExpanded(True)
            parent = parent.parent()
        self._set_editable(item, True)
        self._renaming = path
        self._tree.setCurrentItem(item)
        # L'éditeur s'ouvre APRÈS la fin du clic sur « + » : à la fin d'un clic, le focus revient
        # au bouton, et un éditeur ouvert pendant ce temps se refermait aussitôt.
        QTimer.singleShot(0, lambda: self._start_edit(path))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, _PATH_ROLE)
        if column != 0 or path != self._renaming:
            return
        self._end_rename()
        if item.text(0) != Path(path).name:
            self.folder_rename_requested.emit(path, item.text(0))

    def _start_edit(self, path: str) -> None:
        item = self._find(path) if self._renaming == path else None
        if item is not None:
            self._tree.editItem(item, 0)

    def _end_rename(self, *_ignored) -> None:
        item = self._find(self._renaming) if self._renaming else None
        self._renaming = None
        if item is not None:
            self._set_editable(item, False)

    def _set_editable(self, item: QTreeWidgetItem, editable: bool) -> None:
        """Changer les drapeaux d'un élément émet `itemChanged` : sans le bloquer, le
        gestionnaire verrait ce changement comme une validation du nom."""
        self._tree.blockSignals(True)
        flags = item.flags()
        item.setFlags(flags | Qt.ItemFlag.ItemIsEditable if editable
                      else flags & ~Qt.ItemFlag.ItemIsEditable)
        self._tree.blockSignals(False)

    def _find(self, path: str) -> QTreeWidgetItem | None:
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _PATH_ROLE) == path:
                return item
            stack.extend(item.child(i) for i in range(item.childCount()))
        return None

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
        item.setIcon(0, icons.folder_icon(expanded))
