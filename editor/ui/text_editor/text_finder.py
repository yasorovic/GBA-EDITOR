"""Finder des textes : l'arbre de rangement qui pilote la liste centrale."""
from __future__ import annotations
import json
from uuid import uuid4

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QPersistentModelIndex, QModelIndex
from PyQt6.QtGui import QFont, QShortcut, QKeySequence, QDrag, QPainter, QColor, QPen
from PyQt6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
                            QAbstractItemView, QMenu)

from core.models.text import moved_text_paths, SEP
from core.text_sequences import editor_rows, sequences, consumers

from ui.common import finder_fold_state as fold_state, icons
from ui.common.labels import label
from ui.common.theme import C, S, T, QSS
from ui.common.widgets import W


_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_IS_FOLDER = Qt.ItemDataRole.UserRole + 1
_ROLE_VIRTUAL = Qt.ItemDataRole.UserRole + 2
_TEXT_PATH_MIME = "application/x-gba-text-filing"


class _TextFinderTree(QTreeWidget):
    """Le drop demande une commande ; Qt ne déplace jamais ses items seul."""

    move_requested = pyqtSignal(object, object)

    def __init__(self, finder):
        super().__init__(finder)
        self._finder = finder
        self._drag_token = uuid4().hex
        self._drop_target = QPersistentModelIndex()
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAutoExpandDelay(500)

    def mimeTypes(self):
        return [_TEXT_PATH_MIME]

    def mimeData(self, items):
        data = QMimeData()
        if len(items) == 1 and not items[0].data(0, _ROLE_VIRTUAL):
            path = items[0].data(0, _ROLE_PATH)
            if path:
                data.setData(_TEXT_PATH_MIME, json.dumps(
                    {"token": self._drag_token, "path": list(path)}).encode('utf-8'))
        return data

    def startDrag(self, _actions):
        data = self.mimeData(self.selectedItems())
        if data.hasFormat(_TEXT_PATH_MIME):
            drag = QDrag(self)
            drag.setMimeData(data)
            try:
                drag.exec(Qt.DropAction.MoveAction)
            finally:
                self._set_drop_target(None)

    def _set_drop_target(self, item):
        target = (QPersistentModelIndex(self.indexFromItem(item)) if item is not None
                  else QPersistentModelIndex())
        if target != self._drop_target:
            self._drop_target = target
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_target.isValid():
            rect = self.visualRect(QModelIndex(self._drop_target)).adjusted(1, 1, -1, -1)
            painter = QPainter(self.viewport())
            tint = QColor(C.ACCENT)
            tint.setAlpha(32)
            painter.fillRect(rect, tint)
            painter.setPen(QPen(QColor(C.ACCENT)))
            painter.drawRect(rect)
            painter.end()

    def _drop_paths(self, data, item):
        if item is None or not item.data(0, _ROLE_IS_FOLDER):
            return None
        try:
            payload = json.loads(bytes(data.data(_TEXT_PATH_MIME)))
            source = payload['path']
            if (payload['token'] != self._drag_token or not isinstance(source, list)
                    or not all(isinstance(part, str) for part in source)):
                return None
        except (ValueError, KeyError, TypeError):
            return None
        destination = tuple(item.data(0, _ROLE_PATH) or ())
        if moved_text_paths(getattr(self._finder._project, 'texts', ()), source, destination):
            return tuple(source), destination
        return None

    def dragEnterEvent(self, event):
        try:
            payload = json.loads(bytes(event.mimeData().data(_TEXT_PATH_MIME)))
            valid = payload.get('token') == self._drag_token
        except (ValueError, TypeError, AttributeError):
            valid = False
        if valid:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if self._drop_paths(event.mimeData(), item) is not None:
            # Le traitement natif conserve le défilement et l'ouverture au
            # survol. Le repère de dépôt ne change pas la sélection, qui
            # pilote le filtre et les éditeurs de la colonne centrale.
            super().dragMoveEvent(event)
            self._set_drop_target(item)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            self._set_drop_target(None)
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_target(None)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drop_target(None)
        paths = self._drop_paths(event.mimeData(), self.itemAt(event.position().toPoint()))
        if paths is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        # La commande reconstruit le Finder après le retour de l'événement Qt.
        source, destination = paths
        QTimer.singleShot(0, lambda: self.move_requested.emit(source, destination))


class TextFinder(QWidget):
    """Présente le rangement des textes sans dupliquer leur édition.

    Les entrées restent dans la table centrale ; le Finder ne choisit que le
    dossier dont on souhaite examiner le contenu.
    """

    path_selected = pyqtSignal(object)  # tuple[str, ...]
    folder_renamed = pyqtSignal(object, str)  # (path, nouveau segment)
    move_requested = pyqtSignal(object, object)
    create_requested = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    duplicate_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._blocking = False
        self._linked_paths: set = set()
        self._editing_path: tuple[str, ...] | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(W.finder_bar(label("common.texts")))

        self._tree = _TextFinderTree(self)
        self._tree.move_requested.connect(self.move_requested.emit)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.UI_STACK}; font-size:{T.MD}px; outline:none;}}"
            f"QTreeWidget::item{{height:{S.ROW}px; padding:2px 4px;}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{C.TEXT_HI};}}"
            f"QTreeWidget::item:hover:!selected{{background:{C.BG_PANEL};}}")
        self._tree.itemSelectionChanged.connect(self._on_selection)
        self._tree.itemDoubleClicked.connect(self._begin_rename)
        self._tree.itemChanged.connect(self._commit_rename)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self._tree,
                  activated=self._rename_current,
                  context=Qt.ShortcutContext.WidgetShortcut)
        self._tree.itemExpanded.connect(lambda it: self._refresh_folder_icon(it, True))
        self._tree.itemCollapsed.connect(lambda it: self._refresh_folder_icon(it, False))
        self._tree.itemExpanded.connect(lambda it: self._remember_fold(it, True))
        self._tree.itemCollapsed.connect(lambda it: self._remember_fold(it, False))
        root.addWidget(self._tree, 1)

    @staticmethod
    def _fold_key(path: tuple[str, ...]) -> str:
        return "/".join(["text_folder", *path])

    def _remember_fold(self, item: QTreeWidgetItem, expanded: bool) -> None:
        # `refresh` pose les états sous `_blocking` : seuls les clics de l'auteur sont retenus.
        if not self._blocking:
            fold_state.set_expanded(self._fold_key(tuple(item.data(0, _ROLE_PATH) or ())), expanded)

    def load_project(self, project):
        self._tree._drag_token = uuid4().hex
        self._project = project
        self.refresh()

    def refresh(self):
        selected = self.selected_path()
        display_rows = editor_rows(self._project) if self._project else []
        self._blocking = True
        self._tree.clear()
        root = QTreeWidgetItem(self._tree, [label("txttbl.text_count",
                                                  n=len(display_rows))])
        root.setData(0, _ROLE_PATH, ())
        root.setData(0, _ROLE_IS_FOLDER, True)
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        root.setExpanded(fold_state.is_expanded(self._fold_key(())))
        root.setIcon(0, icons.folder_icon(root.isExpanded(), icons.COLOR_FOLDER))
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {(): root}
        counts: dict[tuple[str, ...], int] = {(): 0}
        paths = [(path, path != tuple(text.path), 1) for text, path, _prefix in display_rows]
        # Un dossier qui EST une séquence lue par une table ou une boîte porte l'icône « lié ».
        self._linked_paths = self._compute_linked_paths()
        for display_path, virtual, weight in paths:
            parent = root
            for depth, segment in enumerate(display_path):
                path = tuple(display_path[:depth + 1])
                item = nodes.get(path)
                if item is None:
                    item = QTreeWidgetItem(parent, [segment])
                    item.setData(0, _ROLE_PATH, path)
                    nodes[path] = item
                    counts[path] = 0
                counts[path] += weight
                if virtual and depth == len(display_path)-1:
                    item.setData(0, _ROLE_VIRTUAL, True)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
                parent = item
        parents = {path[:-1] for path in nodes if len(path) > 1}      # les nœuds sont clos par préfixe : parent direct suffit
        for path, item in nodes.items():
            if path:
                item.setText(0, f"{path[-1]}  ({counts[path]})")
                item.setToolTip(0, SEP.join(path))
                # Un dernier niveau peut encore contenir plusieurs textes :
                # l'icône texte est réservée à une entrée seule.
                has_child = path in parents
                is_folder = has_child or counts[path] > 1
                item.setData(0, _ROLE_IS_FOLDER, is_folder)
                if not is_folder:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
                if not is_folder:
                    item.setIcon(0, icons.get("ui_text", C.TEXT_DIM))
                else:
                    expanded = fold_state.is_expanded(self._fold_key(path))
                    item.setExpanded(expanded)
                    self._refresh_folder_icon(item, expanded)
        target = nodes.get(selected, root)
        target.setSelected(True)
        self._tree.setCurrentItem(target)
        self._blocking = False

    def select_path(self, path):
        """Suit une entrée déplacée, en ouvrant ses nouveaux ancêtres."""
        path = tuple(path)
        def find(item):
            if tuple(item.data(0, _ROLE_PATH) or ()) == path:
                return item
            for i in range(item.childCount()):
                match = find(item.child(i))
                if match is not None:
                    return match
            return None
        item = find(self._tree.topLevelItem(0))
        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self._tree.setCurrentItem(item)
            self._tree.scrollToItem(item)

    def _compute_linked_paths(self) -> set:
        if not self._project:
            return set()
        return {tuple(prefix.split("_")) for prefix in sequences(self._project)
                if consumers(self._project, prefix)}

    def refresh_links(self) -> None:
        """Une séquence vient d'être liée ou déliée : on change les icônes, sans reconstruire l'arbre."""
        self._linked_paths = self._compute_linked_paths()
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _ROLE_IS_FOLDER):
                self._refresh_folder_icon(item, item.isExpanded())
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _refresh_folder_icon(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if not item.data(0, _ROLE_IS_FOLDER):
            return
        if tuple(item.data(0, _ROLE_PATH) or ()) in self._linked_paths:
            item.setIcon(0, icons.get("data_table_linked", C.ACCENT))
        else:
            item.setIcon(0, icons.folder_icon(expanded, icons.COLOR_FOLDER))

    def selected_path(self) -> tuple[str, ...]:
        item = self._tree.currentItem()
        return tuple(item.data(0, _ROLE_PATH) or ()) if item else ()

    def _on_selection(self):
        if not self._blocking:
            self.path_selected.emit(self.selected_path())

    def _context_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is None:
            return
        if not item.isSelected():
            self._tree.setCurrentItem(item)
        path = tuple(item.data(0, _ROLE_PATH) or ())
        folder = bool(item.data(0, _ROLE_IS_FOLDER))
        rows = editor_rows(self._project) if self._project else []
        texts = list({text.id: text for text, shown, _prefix in rows
                      if tuple(shown) == path or (folder and tuple(shown[:len(path)]) == path)}.values())

        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.addAction(label("common.create"),
                       lambda: self.create_requested.emit(path if folder else path[:-1]))
        duplicate = menu.addAction(label("common.duplicate"))
        duplicate.setEnabled(not folder and len(texts) == 1)
        if duplicate.isEnabled():
            duplicate.triggered.connect(lambda: self.duplicate_requested.emit(texts[0]))
        delete = menu.addAction(label("common.delete"))
        delete.setEnabled(bool(texts))
        if delete.isEnabled():
            delete.triggered.connect(lambda: self.delete_requested.emit(texts))
        menu.exec(self._tree.viewport().mapToGlobal(position))

    def _rename_current(self) -> None:
        item = self._tree.currentItem()
        if item is not None:
            self._begin_rename(item, 0)

    def _begin_rename(self, item, _column) -> None:
        """Même renommage en place que les autres finders, jamais une modale."""
        if item.data(0, _ROLE_VIRTUAL):
            return
        path = tuple(item.data(0, _ROLE_PATH) or ())
        if not path:
            return
        self._editing_path = path
        self._blocking = True
        item.setText(0, path[-1])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._blocking = False
        QTimer.singleShot(0, lambda: self._tree.editItem(item, 0))

    def _commit_rename(self, item, _column) -> None:
        if self._blocking or self._editing_path is None:
            return
        path, self._editing_path = self._editing_path, None
        typed = item.text(0).strip()
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if typed and typed != path[-1]:
            self.folder_renamed.emit(path, typed)
        else:
            self.refresh()
