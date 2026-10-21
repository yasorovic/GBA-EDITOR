"""
ui/common/updates_dialog.py — la fenêtre « Updates » : où en est la version, ses notes.

Lit l'état de `UpdateChecker`. Un seul bouton : « Search for update », qui devient
« Update to X » quand une version plus récente existe — il la télécharge (barre de
progression) puis, selon la distribution, l'installe ou ouvre le dossier de téléchargement
(cf. `UpdateChecker.download`) ; lancé depuis les sources, il ouvre la page de la
release. Le réglage de la vérification
automatique et ce que cette vérification envoie sont dits ici, en une phrase.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
    QVBoxLayout,
)
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtCore import Qt, QUrl

from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.update_checker import UpdateChecker


class UpdatesDialog(QDialog):
    def __init__(self, checker: UpdateChecker, parent=None):
        super().__init__(parent)
        self._checker = checker
        self.setWindowTitle(label("about.updates"))
        self.resize(560, 420)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        self._status = QLabel()
        self._status.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._status.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        root.addWidget(self._status)

        self._notes = QTextBrowser()
        self._notes.setOpenExternalLinks(True)
        self._notes.setFrameShape(QFrame.Shape.NoFrame)
        self._notes.setStyleSheet(f"QTextBrowser{{background:{C.BG_PANEL};padding:8px;}}")
        root.addWidget(self._notes, 1)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        root.addWidget(self._progress)

        self._button = QPushButton()
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_button)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._button)
        root.addLayout(row)

        if checker.kind in ("portable", "appimage"):
            folder_row = QHBoxLayout()
            self._folder = QLabel()
            self._folder.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
            browse = QPushButton(label("about.browse"))
            browse.clicked.connect(self._choose_folder)
            folder_row.addWidget(QLabel(label("about.download_folder")))
            folder_row.addWidget(self._folder, 1)
            folder_row.addWidget(browse)
            root.addLayout(folder_row)

        auto = QCheckBox(label("about.auto_check"))
        auto.setChecked(checker.auto_check)
        auto.toggled.connect(lambda enabled: setattr(checker, "auto_check", enabled))
        root.addWidget(auto)
        privacy = QLabel(label("about.update_privacy"))
        privacy.setWordWrap(True)
        privacy.setFont(QFont(T.UI, T.SM))
        privacy.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        root.addWidget(privacy)

        checker.changed.connect(self._refresh)
        self._refresh()
        if not checker.checked:
            checker.check()

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, label("about.download_folder"), str(self._checker.download_dir))
        if folder:
            self._checker.download_dir = Path(folder)

    def _refresh(self):
        c = self._checker
        if hasattr(self, "_folder"):
            self._folder.setText(str(c.download_dir))
        self._button.setEnabled(not (c.checking or c.downloading))
        self._progress.setVisible(c.downloading)
        self._progress.setValue(c.progress)
        self._notes.setVisible(c.available is not None and not c.downloading)
        if c.checking:
            self._status.setText(label("about.checking_update"))
        elif c.downloading:
            self._status.setText(label("about.downloading", percent=c.progress))
        elif c.download_failed:
            self._status.setText(label("about.download_failed"))
        elif c.downloaded:
            self._status.setText(label("about.downloaded", folder=c.downloaded.parent))
        elif c.available:
            self._status.setText(label("about.update_available", version=c.available.version))
            self._notes.setMarkdown(c.available.notes)
        elif c.failed:
            self._status.setText(label("about.update_failed"))
        else:
            self._status.setText(label("about.up_to_date"))
        self._button.setText(
            label("about.update_to", version=c.available.version) if c.available
            else label("about.search_update"))

    def _on_button(self):
        if self._checker.available and self._checker.kind:
            self._checker.download()
        elif self._checker.available:
            QDesktopServices.openUrl(QUrl(self._checker.available.page_url))
        else:
            self._checker.check()
