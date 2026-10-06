"""ui/common/toolchain_dialog.py — la fenêtre qui explique pourquoi on ne peut pas
construire la ROM faute d'outils, et propose d'ouvrir les réglages de la toolchain.

Même mise en page que `crash_dialog.CrashDialog` (mascotte, titre, texte, boutons
en bas) : deux fenêtres qui disent « ça ne va pas » se ressemblent.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.app_info import APP_NAME
from core.toolchain import DEVKITPRO_TOOLS, DEVKITPRO_URL, MGBA_URL
from ui.common.crash_dialog import Mascot
from ui.common.install_commands import InstallCommands
from ui.common.labels import label
from ui.common.theme import C, QSS, T


def _link(url: str) -> str:
    return f'<a href="{url}" style="color:{C.ACCENT_COOL};">{url}</a>'


class ToolchainMissingDialog(QDialog):
    """`open_settings_requested` : True après un clic sur « Ouvrir les réglages »."""

    def __init__(self, missing: list[str], parent=None):
        super().__init__(parent)
        self.open_settings_requested = False
        self.setWindowTitle(label("win.toolchain_missing_title"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(Mascot(), 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(6)
        title = QLabel(label("win.toolchain_missing_heading"))
        title.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        intro = QLabel(label("win.toolchain_missing", app_name=APP_NAME))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;")
        not_found = QLabel(label("win.toolchain_missing_list", missing=", ".join(missing)))
        not_found.setWordWrap(True)
        not_found.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        not_found.setFont(QFont(T.MONO, T.SM))
        not_found.setStyleSheet(f"color:{C.ACCENT_RED};background:transparent;")
        links = QLabel("<br>".join((
            label("win.toolchain_get", tool="devkitPro", link=_link(DEVKITPRO_URL)),
            label("win.toolchain_get", tool="mGBA", link=_link(MGBA_URL)))))
        links.setOpenExternalLinks(True)
        links.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;")
        for widget in (title, intro, not_found, links):
            text.addWidget(widget)
        # Sous Linux : les commandes qui installent ce qui manque (rien sous Windows).
        for tool, parts in (("devkitPro", DEVKITPRO_TOOLS), ("mGBA", ("mgba",))):
            if any(part in missing for part in parts):
                text.addWidget(InstallCommands(tool))
        text.addStretch()
        top.addLayout(text, 1)
        root.addLayout(top)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        settings_btn = QPushButton(label("win.toolchain_open_settings"))
        settings_btn.setStyleSheet(QSS.button_primary)
        settings_btn.setDefault(True)
        settings_btn.clicked.connect(self._open_settings)
        close_btn = QPushButton(label("common.close"))
        close_btn.setStyleSheet(QSS.button_ghost)
        close_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        buttons.addWidget(settings_btn)
        root.addLayout(buttons)

    def _open_settings(self):
        self.open_settings_requested = True
        self.accept()
