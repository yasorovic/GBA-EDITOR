"""Ligne d'état d'une séquence de textes : liée (ses tables) ou libre (les relier, en créer une).

L'état est calculé, jamais stocké : une séquence est liée dès qu'une table la cite.
Les actions poussent une commande ; la synchronisation suit d'elle-même (cf. `sync_linked_tables`).
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu

from core.history import get_history
from core.command_dispatcher import get_dispatcher
from core.text_sequences import consumers
from core.text_table_link import free_tables, link_free_table, create_linked_table
from ui.common.labels import label
from ui.common.theme import C, QSS


class SequenceTableBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 10, 4)
        self._state = QLabel()
        self._state.setStyleSheet(f"color:{C.TEXT_DIM};")
        row.addWidget(self._state, 1)
        self._link = QPushButton(label("txtseq.link_table"))
        self._create = QPushButton(label("txtseq.create_table_action"))
        for button in (self._link, self._create):
            button.setStyleSheet(QSS.button_ghost)
            row.addWidget(button)
        self._link.clicked.connect(self._link_menu)
        self._create.clicked.connect(self._create_table)
        self._project = self._prefix = None

    def refresh(self, project, prefix):
        self._project, self._prefix = project, prefix
        # Seules les tables comptent ici : une TextBox qui lit la séquence ne la « lie » pas à une table.
        tables = [c for c in consumers(project, prefix) if hasattr(c, "text_link")]
        self._state.setText(label("txtseq.linked_to", tables=", ".join(t.name for t in tables))
                            if tables else label("txtseq.free"))
        self._link.setVisible(not tables)
        self._create.setVisible(not tables)

    def _push(self, cmd):
        get_history().push(cmd)

    def _notify(self):
        get_dispatcher().notify_data_tables_changed()

    def _link_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        tables = free_tables(self._project)
        for table in tables:
            menu.addAction(table.name).setData(table)
        if not tables:
            menu.addAction(label("txtseq.no_free_table")).setEnabled(False)
        action = menu.exec(self._link.mapToGlobal(self._link.rect().bottomLeft()))
        if action is not None and action.data() is not None:
            self._push(link_free_table(self._project, action.data(), self._prefix, self._notify))

    def _create_table(self):
        self._push(create_linked_table(self._project, self._prefix, self._notify))
