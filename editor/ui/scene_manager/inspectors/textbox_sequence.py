"""Ligne « séquence de textes » d'une TextBox : liée à un préfixe, ou libre.

Liée, la boîte lit la séquence entière (cf. `Project.textbox_pages`) et la suit d'elle-même.
Le widget ne modifie rien : il annonce le préfixe choisi (`prefix_chosen`, "" pour délier)."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu

from core.text_sequences import sequences
from ui.common.labels import label
from ui.common.theme import C, QSS


class TextboxSequenceRow(QWidget):
    prefix_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = self._box = None
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._state = QLabel()
        self._state.setStyleSheet(f"color:{C.TEXT_DIM};")
        row.addWidget(self._state, 1)
        self._link = QPushButton(label("uiinsp.text.sequence_link"))
        self._unlink = QPushButton(label("uiinsp.text.sequence_unlink"))
        for button in (self._link, self._unlink):
            button.setStyleSheet(QSS.button_ghost)
            row.addWidget(button)
        self._link.clicked.connect(self._menu)
        self._unlink.clicked.connect(lambda: self.prefix_chosen.emit(""))

    def bind(self, project, box):
        self._project, self._box = project, box
        prefix = getattr(box, "sequence_prefix", "")
        if prefix:
            self._state.setText(label("uiinsp.text.sequence_linked", prefix=prefix,
                                      n=len(project.textbox_pages(box))))
        else:
            self._state.setText(label("uiinsp.text.sequence_free"))
        self._link.setVisible(not prefix)
        self._unlink.setVisible(bool(prefix))

    def _menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        found = list(sequences(self._project))
        for prefix in found:
            menu.addAction(prefix).setData(prefix)
        if not found:
            menu.addAction(label("uiinsp.text.no_sequence")).setEnabled(False)
        action = menu.exec(self._link.mapToGlobal(self._link.rect().bottomLeft()))
        if action is not None and action.data():
            self.prefix_chosen.emit(action.data())
