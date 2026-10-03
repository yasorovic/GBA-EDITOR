"""
ui/common/about_dialog.py — fenêtre « À propos » : logo, version, auteur, liens.

Les adresses viennent de `core/app_info` ; un lien dont l'adresse est vide n'est
pas affiché. « Report an issue » ouvre le formulaire de rapport du dépôt.
"""

from __future__ import annotations


from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtCore import Qt, QSize, QUrl, pyqtSignal

from ui.common import icons
from ui.common.labels import label
from ui.common.logo import BackstageLogo
from ui.common.theme import C, T
from core.app_info import (
    APP_AUTHOR, APP_DOCS_URL, APP_ISSUES_URL, APP_RELEASES_URL, APP_VERSION,
)

_ICON_SIZE = QSize(22, 22)


def _open(url: str):
    QDesktopServices.openUrl(QUrl(url))


def _icon_label(name: str, color: str) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(icons.get(name, color).pixmap(_ICON_SIZE))
    lbl.setFixedWidth(_ICON_SIZE.width() + 4)
    lbl.setStyleSheet("background:transparent;border:none;")
    lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return lbl


class _Card(QFrame):
    """Rangée arrondie d'un lien."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutCard")
        self.setFixedHeight(48)
        self._set_background(C.BG_PANEL)

    def _set_background(self, color: str):
        self.setStyleSheet(
            f"QFrame#aboutCard{{background:{color};border:1px solid {C.BORDER};"
            "border-radius:8px;}")


class _LinkRow(_Card):
    """Carte cliquable : icône, titre, pictogramme « s'ouvre dehors »."""

    clicked = pyqtSignal()

    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(12)
        row.addWidget(_icon_label(icon_name, C.TEXT_NORM))
        title = QLabel(text)
        title.setFont(QFont(T.UI, T.MD))
        title.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;border:none;")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(title, 1)
        row.addWidget(_icon_label("open_external", C.TEXT_DIM))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._set_background(C.BG_HOVER)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_background(C.BG_PANEL)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(label("win.about"))
        self.setFixedWidth(520)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 24, 36, 24)
        root.setSpacing(0)

        root.addWidget(BackstageLogo(320), 0, Qt.AlignmentFlag.AlignHCenter)
        root.addSpacing(14)

        version = QLabel(f"v{APP_VERSION}")
        version.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(
            f"color:{C.TEXT_HI};background:{C.BG_PANEL};border:1px solid {C.ACCENT};"
            "border-radius:14px;padding:4px 16px;")
        root.addWidget(version, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addSpacing(14)

        tagline = QLabel(label("about.tagline"))
        tagline.setFont(QFont(T.UI, T.MD))
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        root.addWidget(tagline)

        root.addSpacing(16)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background:{C.BORDER};border:none;")
        root.addWidget(rule)
        root.addSpacing(18)

        links = QVBoxLayout()
        links.setSpacing(10)
        if APP_DOCS_URL:
            row = _LinkRow("docs", label("about.docs"))
            row.clicked.connect(lambda: _open(APP_DOCS_URL))
            links.addWidget(row)
        if APP_RELEASES_URL:
            row = _LinkRow("release_notes", label("about.release_notes"))
            row.clicked.connect(lambda: _open(APP_RELEASES_URL))
            links.addWidget(row)
        if APP_ISSUES_URL:
            row = _LinkRow("report_issue", label("about.report_issue"))
            row.clicked.connect(lambda: _open(APP_ISSUES_URL))
            links.addWidget(row)
        root.addLayout(links)

        root.addSpacing(18)
        author_lbl = QLabel(label("about.created_by", author=APP_AUTHOR))
        author_lbl.setFont(QFont(T.UI, T.SM))
        author_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        root.addWidget(author_lbl)
