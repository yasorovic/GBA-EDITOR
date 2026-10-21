"""
ui/common/about_dialog.py — fenêtre « À propos » : logo, version, auteur, liens.

Les adresses viennent de `core/app_info` ; un lien dont l'adresse est vide n'est
pas affiché. « Report an issue » ouvre le formulaire de rapport du dépôt.

« Check for updates » ouvre `UpdatesDialog` (état de `UpdateChecker`) ; un point
accent s'affiche sur la ligne quand une version plus récente existe.

« Release notes » et « Licenses » ouvrent un `DocumentsDialog` (un onglet par
texte, lus dans `APP_DIR`) : le journal des versions ; la licence de l'éditeur, celle
du moteur et les notices tierces. La GPL de l'éditeur et la LGPL de Qt exigent que ces textes soient atteignables
par l'utilisateur ; un onglet dont le fichier manque n'est pas affiché.
"""

from __future__ import annotations


from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTextBrowser,
)
from PyQt6.QtGui import QDesktopServices, QFont, QFontDatabase
from PyQt6.QtCore import Qt, QSize, QUrl, pyqtSignal

from ui.common import icons
from ui.common.labels import label
from ui.common.logo import BackstageLogo
from ui.common.panel_bar import tab_widget
from ui.common.theme import C, T
from core.app_paths import APP_DIR, RUNTIME_DIR
from core.app_info import (
    APP_AUTHOR, APP_DOCS_URL, APP_ISSUES_URL, APP_RELEASES_URL, APP_VERSION,
)
from ui.common.update_checker import UpdateChecker
from ui.common.updates_dialog import UpdatesDialog

_ICON_SIZE = QSize(22, 22)
_PLAIN_COLUMNS = 90   # les licences sont coupées à 80 colonnes ; un peu de marge
_MARKDOWN_COLUMN = 760  # px


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

    def __init__(self, icon_name: str, text: str, parent=None, trailing_icon="open_external"):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(12)
        row.addWidget(_icon_label(icon_name, C.TEXT_NORM))
        self._title = QLabel(text)
        self._title.setFont(QFont(T.UI, T.MD))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;border:none;")
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self._title, 1)
        if trailing_icon:
            row.addWidget(_icon_label(trailing_icon, C.TEXT_DIM))

    def set_text(self, text: str):
        self._title.setText(text)

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


# (clé de libellé, fichier, rendu Markdown ?)
_RELEASE_NOTES = (
    ("about.changelog", APP_DIR / "changelog" / "CHANGELOG.md", True),
)
_LICENSES = (
    ("about.license_editor", APP_DIR / "LICENSE", False),
    ("about.license_engine", RUNTIME_DIR / "LICENSE", False),
    ("about.license_notices", APP_DIR / "THIRD-PARTY-NOTICES.md", True),
)


class _CenteredBrowser(QTextBrowser):
    """Texte posé en colonne centrée : de part et d'autre, des marges égales."""

    def __init__(self, column_width: int, parent=None):
        super().__init__(parent)
        self._column_width = column_width

    def resizeEvent(self, event):
        super().resizeEvent(event)
        side = max(0, (self.width() - self._column_width) // 2)
        self.setViewportMargins(side, 0, side, 0)


class DocumentsDialog(QDialog):
    """Des textes livrés avec l'application, un onglet chacun."""

    def __init__(self, title_key: str, documents, parent=None):
        super().__init__(parent)
        self.setWindowTitle(label(title_key))
        self.resize(780, 560)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")
        root = QVBoxLayout(self)
        tabs = tab_widget()
        for key, path, markdown in documents:
            if not path.is_file():
                continue
            view = _CenteredBrowser(_MARKDOWN_COLUMN if markdown else 0)
            view.setOpenExternalLinks(True)
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.setStyleSheet(f"QTextBrowser{{background:{C.BG_PANEL};padding:8px;}}")
            text = path.read_text(encoding="utf-8", errors="replace")
            if markdown:
                view.setMarkdown(text)
            else:
                view.setPlainText(text)
                # Texte centré à coups d'espaces : seule une vraie chasse fixe (le nom
                # générique « monospace » n'en garantit pas une) le garde aligné.
                fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
                fixed.setPointSize(T.SM)
                view.setFont(fixed)
                view._column_width = view.fontMetrics().horizontalAdvance("0") * _PLAIN_COLUMNS
            tabs.addTab(view, label(key))
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(tabs)


class AboutDialog(QDialog):
    def __init__(self, checker: UpdateChecker, parent=None):
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
        release_notes = _LinkRow("release_notes", label("about.release_notes"), trailing_icon="")
        release_notes.clicked.connect(
            lambda: DocumentsDialog("about.release_notes", _RELEASE_NOTES, self).exec())
        links.addWidget(release_notes)
        if APP_RELEASES_URL:
            self._update_row = _LinkRow(
                "check_update", label("about.check_update"), trailing_icon="")
            self._update_row.clicked.connect(lambda: UpdatesDialog(checker, self).exec())
            checker.changed.connect(lambda: self._show_update_dot(checker))
            self._show_update_dot(checker)
            links.addWidget(self._update_row)
        if APP_ISSUES_URL:
            row = _LinkRow("report_issue", label("about.report_issue"))
            row.clicked.connect(lambda: _open(APP_ISSUES_URL))
            links.addWidget(row)
        licenses = _LinkRow("licenses", label("about.licenses"), trailing_icon="")
        licenses.clicked.connect(lambda: DocumentsDialog("about.licenses", _LICENSES, self).exec())
        links.addWidget(licenses)
        root.addLayout(links)

        root.addSpacing(18)
        summary = QLabel(label("about.licenses_summary"))
        summary.setFont(QFont(T.UI, T.SM))
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        root.addWidget(summary)
        root.addSpacing(6)
        author_lbl = QLabel(label("about.created_by", author=APP_AUTHOR))
        author_lbl.setFont(QFont(T.UI, T.SM))
        author_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        root.addWidget(author_lbl)

    def _show_update_dot(self, checker: UpdateChecker):
        text = label("about.check_update")
        if checker.badge:
            text += f' <span style="color:{C.ACCENT}">●</span>'
        self._update_row.set_text(text)

