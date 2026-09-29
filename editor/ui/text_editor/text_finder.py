"""Finder des textes : l'arbre de rangement qui pilote la liste centrale."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ui.common import icons
from ui.common.labels import label
from ui.common.theme import C, S, T
from ui.common.widgets import W


_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_IS_FOLDER = Qt.ItemDataRole.UserRole + 1


class TextFinder(QWidget):
    """Présente le rangement des textes sans dupliquer leur édition.

    Les entrées restent dans la table centrale ; le Finder ne choisit que le
    dossier dont on souhaite examiner le contenu.
    """

    path_selected = pyqtSignal(object)  # tuple[str, ...]
    folder_renamed = pyqtSignal(object, str)  # (path, nouveau segment)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._blocking = False
        self._editing_path: tuple[str, ...] | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(W.finder_bar(label("common.texts")))

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.UI_STACK}; font-size:{T.MD}px; outline:none;}}"
            f"QTreeWidget::item{{height:{S.ROW}px; padding:2px 4px;}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{C.TEXT_HI};}}"
            f"QTreeWidget::item:hover:!selected{{background:{C.BG_PANEL};}}")
        self._tree.itemSelectionChanged.connect(self._on_selection)
        self._tree.itemDoubleClicked.connect(self._begin_rename)
        self._tree.itemChanged.connect(self._commit_rename)
        self._tree.itemExpanded.connect(lambda it: self._refresh_folder_icon(it, True))
        self._tree.itemCollapsed.connect(lambda it: self._refresh_folder_icon(it, False))
        root.addWidget(self._tree, 1)

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        selected = self.selected_path()
        self._blocking = True
        self._tree.clear()
        root = QTreeWidgetItem(self._tree, [label("txttbl.text_count",
                                                  n=len(self._project.texts) if self._project else 0)])
        root.setData(0, _ROLE_PATH, ())
        root.setData(0, _ROLE_IS_FOLDER, True)
        root.setIcon(0, icons.folder_icon(root.isExpanded(), icons.COLOR_FOLDER))
        nodes: dict[tuple[str, ...], QTreeWidgetItem] = {(): root}
        counts: dict[tuple[str, ...], int] = {(): 0}
        for text in getattr(self._project, "texts", ()):
            parent = root
            for depth, segment in enumerate(text.path):
                path = tuple(text.path[:depth + 1])
                item = nodes.get(path)
                if item is None:
                    item = QTreeWidgetItem(parent, [segment])
                    item.setData(0, _ROLE_PATH, path)
                    nodes[path] = item
                    counts[path] = 0
                counts[path] += 1
                parent = item
        for path, item in nodes.items():
            if path:
                item.setText(0, f"{path[-1]}  ({counts[path]})")
                # Le dernier niveau désigne une string : sa forme diffère du
                # dossier afin que la hiérarchie se lise d'un seul regard.
                has_child = any(other[:len(path)] == path and len(other) > len(path)
                                for other in nodes)
                item.setData(0, _ROLE_IS_FOLDER, has_child)
                if not has_child:
                    item.setIcon(0, icons.get("ui_text", C.TEXT_DIM))
                else:
                    # À l'ouverture, les grands dossiers restent lisibles mais
                    # leurs descendants ne déroulent pas toute l'arborescence.
                    expanded = len(path) == 1
                    item.setExpanded(expanded)
                    item.setIcon(0, icons.folder_icon(expanded, icons.COLOR_FOLDER))
        target = nodes.get(selected, root)
        target.setSelected(True)
        self._tree.setCurrentItem(target)
        self._blocking = False

    @staticmethod
    def _refresh_folder_icon(item: QTreeWidgetItem, expanded: bool) -> None:
        if item.data(0, _ROLE_IS_FOLDER):
            item.setIcon(0, icons.folder_icon(expanded, icons.COLOR_FOLDER))

    def selected_path(self) -> tuple[str, ...]:
        item = self._tree.currentItem()
        return tuple(item.data(0, _ROLE_PATH) or ()) if item else ()

    def _on_selection(self):
        if not self._blocking:
            self.path_selected.emit(self.selected_path())

    def _begin_rename(self, item, _column) -> None:
        """Même renommage en place que les autres finders, jamais une modale."""
        path = tuple(item.data(0, _ROLE_PATH) or ())
        if not path:
            return
        self._editing_path = path
        self._blocking = True
        item.setText(0, path[-1])       # ne jamais faire éditer le compteur
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
