"""
ui/common/updates_dialog.py — la fenêtre « Updates » : où en est la version, ses notes.

Lit l'état de `UpdateChecker`. Un seul bouton : « Search for update », qui devient
« Update to X » quand une version plus récente existe — il la télécharge (barre de
progression) puis, selon la distribution, l'installe ou ouvre le dossier de téléchargement
(cf. `UpdateChecker.download`) ; lancé depuis les sources, il ouvre la page de la
release. Ce que la vérification
envoie est dit ici, en une phrase ; sa fréquence se règle dans Réglages > Updates.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
    QStackedWidget, QToolButton, QVBoxLayout,
)
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtCore import Qt, QUrl

from core.app_info import APP_VERSION
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

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        root.addWidget(self._progress)

        self._notes = QTextBrowser()
        self._notes.setOpenExternalLinks(True)
        self._notes.setFrameShape(QFrame.Shape.NoFrame)
        self._notes.setStyleSheet(f"QTextBrowser{{background:{C.BG_PANEL};padding:8px;}}")

        self._detail = QLabel()
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        # Une seule zone centrale, de taille fixe : les notes s'il y a une version, sinon un
        # texte centré. Le reste de la fenêtre ne bouge donc jamais d'un état à l'autre.
        self._body = QStackedWidget()
        self._body.addWidget(self._detail)
        self._body.addWidget(self._notes)
        root.addWidget(self._body, 1)

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

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"color:{C.BORDER};")
        root.addWidget(rule)

        privacy = QLabel(label("about.update_privacy"))
        privacy.setWordWrap(True)
        privacy.setFont(QFont(T.UI, T.SM))
        privacy.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        privacy.setVisible(False)
        retain = privacy.sizePolicy()
        retain.setRetainSizeWhenHidden(True)   # l'ouvrir ne pousse rien vers le haut
        privacy.setSizePolicy(retain)
        toggle = QToolButton()
        toggle.setText(label("about.privacy_details"))
        toggle.setCheckable(True)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setAutoRaise(True)
        toggle.setFont(QFont(T.UI, T.SM))
        toggle.setStyleSheet(f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;}}"
                             f"QToolButton:hover{{color:{C.TEXT_HI};}}")

        def show_privacy(shown: bool):
            toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
            privacy.setVisible(shown)

        toggle.toggled.connect(show_privacy)
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(toggle)
        toggle_row.addStretch(1)
        root.addLayout(toggle_row)
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
        self._button.setEnabled(not c.checking)
        self._progress.setVisible(c.downloading)
        self._progress.setValue(c.progress)
        self._body.setCurrentWidget(self._notes if c.available else self._detail)
        self._detail.setText(
            label("about.up_to_date_detail", version=f"v{APP_VERSION}")
            if not (c.checking or c.failed) else "")
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
        if c.downloading:
            self._button.setText(label("common.cancel"))
        else:
            self._button.setText(
                label("about.update_to", version=c.available.version) if c.available
                else label("about.search_update"))

    def _on_button(self):
        if self._checker.downloading:
            self._checker.cancel_download()
        elif self._checker.available and self._checker.kind:
            self._checker.download()
        elif self._checker.available:
            QDesktopServices.openUrl(QUrl(self._checker.available.page_url))
        else:
            self._checker.check()
