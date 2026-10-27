"""ui/common/copy_button.py — le bouton « copier dans le presse-papiers » : une icône qui copie, puis le confirme.

Un seul geste, un seul retour d'information partout où l'on copie une valeur : au clic le texte part dans le
presse-papiers, l'icône devient une coche, le bouton s'allume, et l'infobulle dit « Copied » sous le curseur, le
temps de la lire. Le bouton retrouve ensuite son état."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QToolButton, QToolTip

from ui.common import icons
from ui.common.labels import label
from ui.common.theme import C
from ui.common.widgets import BTN_ICON


class CopyButton(QToolButton):
    """`source()` rend le texte à copier au moment du clic, ou None s'il n'y a rien à copier (le clic ne fait alors
    rien). `tip` est l'infobulle au repos, déjà composée (`tooltip(...)` ou un libellé)."""

    FEEDBACK_MS = 900

    def __init__(self, source: Callable[[], Optional[str]], tip: str, parent=None, size: Optional[int] = None):
        super().__init__(parent)
        self._source = source
        self._rest_tip = tip
        if size:
            self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._restore_timer = QTimer(self)             # enfant du bouton : il disparaît avec lui
        self._restore_timer.setSingleShot(True)
        self._restore_timer.setInterval(self.FEEDBACK_MS)
        self._restore_timer.timeout.connect(self._rest)
        self.clicked.connect(self._copy)
        self._rest()

    def set_tip(self, tip: str) -> None:
        """Change l'infobulle au repos (le texte qu'elle annonce a pu changer)."""
        self._rest_tip = tip
        if not self._restore_timer.isActive():
            self.setToolTip(tip)

    def _copy(self) -> None:
        text = self._source()
        if text is None:
            return
        QApplication.clipboard().setText(text)
        self.setIcon(icons.get("copied", C.ACCENT))
        self.setStyleSheet(BTN_ICON + f"QToolButton{{background:{C.BG_SEL};border-radius:3px;}}")
        self.setToolTip(label("common.copied"))
        QToolTip.showText(QCursor.pos(), self.toolTip(), self)
        self._restore_timer.start()

    def _rest(self) -> None:
        self.setIcon(icons.get("copy", C.TEXT_DIM))
        self.setStyleSheet(BTN_ICON)
        self.setToolTip(self._rest_tip)
