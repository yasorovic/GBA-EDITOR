"""
ui/common/action_list_popup.py — la liste des actions de l'écran affiché, dans une fenêtre flottante et défilante.

Une seule ligne du temps : le geste le plus récent en haut, ce que Annuler peut défaire dessous, ce que Rétablir peut
rejouer au-dessus (grisé). Cliquer une ligne défait, ou rejoue, tout jusqu'à elle comprise. Le widget ne touche pas à
l'historique : il dit combien de pas la ligne représente (`picked`, négatif pour annuler, positif pour rétablir) et la
fenêtre principale les joue.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QFrame, QListWidget, QListWidgetItem, QVBoxLayout

from ui.common.labels import label
from ui.common.theme import C, QSS, T

_WIDTH = 300
_ROW_HEIGHT = 26
_MAX_HEIGHT = 320
_STEPS = Qt.ItemDataRole.UserRole


class ActionListPopup(QFrame):
    picked = pyqtSignal(int)     # pas à jouer : -3 = défaire les 3 dernières, +2 = rejouer les 2 prochaines

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setStyleSheet(f"ActionListPopup{{background:{C.BG_RAISED};border:1px solid {C.SPLITTER};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self._list = QListWidget()
        self._list.setStyleSheet(QSS.list_widget)
        self._list.setFont(QFont(T.UI, T.MD))
        self._list.itemClicked.connect(self._on_clicked)
        lay.addWidget(self._list)

    def set_entries(self, undo_labels: list[str], redo_labels: list[str]) -> None:
        """`undo_labels` : la plus récente d'abord. `redo_labels` : la prochaine à rejouer d'abord."""
        self._list.clear()
        # Du plus lointain dans le futur au plus proche, puis le passé : une seule ligne du temps, lue de haut en bas.
        for i in reversed(range(len(redo_labels))):
            self._add(redo_labels[i], i + 1, dim=True)
        for i, text in enumerate(undo_labels):
            self._add(text, -(i + 1), dim=False)
        if not undo_labels and not redo_labels:
            item = QListWidgetItem(label("win.undo_none"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        rows = max(1, self._list.count())
        self.setFixedSize(_WIDTH, min(_MAX_HEIGHT, rows * _ROW_HEIGHT + 12))

    def _add(self, text: str, steps: int, dim: bool) -> None:
        item = QListWidgetItem(text)
        item.setData(_STEPS, steps)
        item.setSizeHint(QSize(0, _ROW_HEIGHT))
        if dim:
            item.setForeground(QColor(C.TEXT_MUTED))
        self._list.addItem(item)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        steps = item.data(_STEPS)
        self.close()
        if steps:
            self.picked.emit(int(steps))
