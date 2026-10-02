"""ui/common/crash_dialog.py — la fenêtre qu'on voit quand l'éditeur rencontre
une erreur inattendue.

Branchée sur `core.crash_log` au démarrage (cf. `main.py`) : le noyau écrit la
trace, cette fenêtre la MONTRE. La mascotte « build raté » est la même que celle
du bouton Build & Run (`build_panel.mascot_renderer`) — une seule source.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QGuiApplication, QPainter
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui.common.build_panel import mascot_renderer
from ui.common.labels import label
from ui.common.reveal import reveal_in_file_manager
from ui.common.theme import C, QSS, T

_MASCOT_W, _MASCOT_H = 78, 120   # le SVG fait 217×330 : on garde ses proportions


class _Mascot(QWidget):
    """La mascotte « build raté », peinte à sa taille propre."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_MASCOT_W, _MASCOT_H)

    def paintEvent(self, _event):
        renderer = mascot_renderer("failed")
        if renderer is None:
            return   # SVG absent : un dialogue d'erreur ne doit pas en lever une autre
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, _MASCOT_W, _MASCOT_H))


class CrashDialog(QDialog):
    def __init__(self, summary: str, details: str, log_path: Path, parent=None):
        super().__init__(parent)
        self._details = details
        self._log_path = log_path
        self.setWindowTitle(label("crash.window_title"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(_Mascot(), 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(6)
        title = QLabel(label("crash.title"))
        title.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        intro = QLabel(label("crash.intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;")
        error = QLabel(summary)
        error.setWordWrap(True)
        error.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        error.setFont(QFont(T.MONO, T.SM))
        error.setStyleSheet(f"color:{C.ACCENT_RED};background:transparent;")
        text.addWidget(title)
        text.addWidget(intro)
        text.addWidget(error)
        text.addStretch()
        top.addLayout(text, 1)
        root.addLayout(top)

        self._details_view = QPlainTextEdit(details)
        self._details_view.setReadOnly(True)
        self._details_view.setFont(QFont(T.MONO, T.SM))
        self._details_view.setMinimumHeight(180)
        self._details_view.setVisible(False)
        root.addWidget(self._details_view)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._toggle_btn = QPushButton(label("crash.show_details"))
        self._toggle_btn.setStyleSheet(QSS.button_ghost)
        self._toggle_btn.clicked.connect(self._toggle_details)
        copy_btn = QPushButton(label("crash.copy"))
        copy_btn.setStyleSheet(QSS.button_ghost)
        copy_btn.clicked.connect(self._copy)
        folder_btn = QPushButton(label("crash.open_log_folder"))
        folder_btn.setStyleSheet(QSS.button_ghost)
        folder_btn.clicked.connect(lambda: reveal_in_file_manager(self._log_path))
        close_btn = QPushButton(label("common.close"))
        close_btn.setStyleSheet(QSS.button_primary)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        for button in (self._toggle_btn, copy_btn, folder_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

    def _toggle_details(self):
        show = not self._details_view.isVisible()
        self._details_view.setVisible(show)
        self._toggle_btn.setText(label("crash.hide_details" if show else "crash.show_details"))
        self.adjustSize()

    def _copy(self):
        QGuiApplication.clipboard().setText(self._details)


def show_crash_dialog(summary: str, details: str, log_path: Path) -> None:
    """Le reporter que `main.py` branche sur `core.crash_log`."""
    CrashDialog(summary, details, log_path).exec()
