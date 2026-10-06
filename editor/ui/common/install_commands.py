"""ui/common/install_commands.py — les commandes qui installent un outil, à copier.

Sous Linux aucun installateur ne s'en charge : l'accueil, les réglages et la boîte
« Construction impossible » montrent ce même bloc, qui vient de
`core.toolchain.install_commands` (la source unique des commandes). Sous Windows
il n'y a rien à montrer : le bloc reste invisible et l'écran garde son lien.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.toolchain import install_commands
from ui.common.labels import label
from ui.common.theme import C, QSS, T
from ui.common.tooltip import tooltip

_COPIED_FEEDBACK_MS = 1500


class InstallCommands(QFrame):
    """Les commandes d'installation de `tool` ("devkitPro" ou "mGBA"), avec « Copier »."""

    def __init__(self, tool: str, parent=None):
        super().__init__(parent)
        self._commands = install_commands(tool)
        self._needed = True
        self.setStyleSheet(
            f"InstallCommands{{background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};"
            "border-radius:4px;}")
        self.setVisible(bool(self._commands))

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(label("install.heading", tool=tool))
        title.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;border:none;")
        self._copy = QPushButton(label("install.copy"))
        self._copy.setStyleSheet(QSS.button_ghost)
        self._copy.setToolTip(tooltip(title=label("install.copy_tip")))
        self._copy.clicked.connect(self._copy_to_clipboard)
        header.addWidget(title, 1)
        header.addWidget(self._copy)
        root.addLayout(header)

        text = QLabel("\n".join(self._commands))
        # Pas de retour à la ligne : un texte enroulé fait sous-estimer la hauteur
        # d'une boîte à son ouverture, et les dernières commandes seraient coupées.
        # Sans lui, la boîte s'élargit à la plus longue (`wget https://…`).
        text.setFont(QFont(T.MONO, T.SM))
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;border:none;")
        root.addWidget(text)

    def set_needed(self, needed: bool):
        """Un écran qui sait si l'outil est déjà là (les réglages) masque le bloc
        quand il ne sert plus ; sans commandes pour ce système, il reste masqué."""
        self._needed = needed
        self.setVisible(bool(self._commands) and needed)

    def _copy_to_clipboard(self):
        QApplication.clipboard().setText("\n".join(self._commands))
        self._copy.setText(label("install.copied"))
        QTimer.singleShot(_COPIED_FEEDBACK_MS, lambda: self._copy.setText(label("install.copy")))
