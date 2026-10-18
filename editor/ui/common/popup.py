"""Gabarit partagé des QMessageBox, appliqué sans modifier leurs appels.

La colonne illustrée couvre le texte et les boutons. Qt conserve la gestion
des réponses, raccourcis, boutons par défaut et détails dépliables.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QRectF, QSize
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QGridLayout, QLabel, QMessageBox, QWidget

from ui.common.theme import C, QSS


_ICON_DIR = Path(__file__).parent / "CustomIcons"
_ILLUSTRATIONS = {
    QMessageBox.Icon.Information: "BUILD-STUDY.svg",
    QMessageBox.Icon.Warning: "Warning_icon.svg",
    QMessageBox.Icon.Question: "QuestionMark_icon.svg",
    QMessageBox.Icon.Critical: "BUILD-FAILED.svg",
}


class PopupIllustration(QWidget):
    """Mascottes pleine hauteur ; symboles d'attention et de question plus discrets."""

    def __init__(self, box: QMessageBox):
        super().__init__(box)
        filename = _ILLUSTRATIONS.get(box.icon())
        self._renderer = QSvgRenderer(str(_ICON_DIR / filename), self) if filename else None
        self._pixmap = box.iconPixmap()
        view = (self._renderer.viewBoxF() if self._renderer and self._renderer.isValid()
                else QRectF(self._pixmap.rect()))
        self._ratio = view.width() / view.height() if view.height() else 1.0
        self._max_height = 72 if box.icon() in (QMessageBox.Icon.Warning, QMessageBox.Icon.Question) else None
        self.setMinimumHeight(120)
        self.setFixedWidth(self.sizeHint().width())

    def sizeHint(self):
        return QSize(round((self._max_height or 120) * self._ratio), 120)

    def resizeEvent(self, event):
        height = min(self.height(), self._max_height or self.height())
        self.setFixedWidth(max(1, round(height * self._ratio)))
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(self.rect())
        if self._max_height:
            height = min(target.height(), self._max_height)
            target.setTop((self.height() - height) / 2)
            target.setHeight(height)
        if self._renderer and self._renderer.isValid():
            self._renderer.render(painter, target)
        elif not self._pixmap.isNull():
            painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))


def apply_popup_template(box: QMessageBox) -> None:
    """Habille une boîte construite par Qt ou par l'éditeur, une seule fois."""
    if box.property("popupTemplateApplied"):
        return
    box.setStyleSheet(
        f"QMessageBox{{background:{C.BG_BASE};}}"
        f"QMessageBox QLabel{{background:transparent;color:{C.TEXT_NORM};border:none;}}")
    for button in box.buttons():
        button.setStyleSheet(QSS.button_primary if button.isDefault() else QSS.button_ghost)
    grid = box.layout()
    icon = box.findChild(QLabel, "qt_msgboxex_icon_label")
    if not isinstance(grid, QGridLayout) or icon is None:
        return
    box.setProperty("popupTemplateApplied", True)
    grid.setContentsMargins(20, 18, 20, 14)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(12)

    if not box.iconPixmap().isNull():
        grid.removeWidget(icon)
        icon.hide()
        # Les boutons et les détails occupent normalement aussi la colonne
        # de l'icône : ils passent sous le texte pour libérer toute sa hauteur.
        for index in range(grid.count()):
            item = grid.itemAt(index)
            row, column, rows, columns = grid.getItemPosition(index)
            widget = item.widget()
            if widget is not None and column < 2:
                grid.addWidget(widget, row, 2, rows, max(1, column + columns - 2))
        if not hasattr(box, "_popup_illustration"):
            box._popup_illustration = PopupIllustration(box)
        grid.addWidget(box._popup_illustration, 0, 0, grid.rowCount(), 1)
        box._popup_illustration.show()
        box.setMinimumHeight(152)

    box.adjustSize()


class _PopupFilter(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        # Les méthodes statiques de QMessageBox créent leur fenêtre en C++ :
        # garder son wrapper Python vivant conserve aussi celui de l'illustration.
        self._visible_boxes = {}

    def eventFilter(self, watched, event):
        if isinstance(watched, QMessageBox):
            if event.type() == QEvent.Type.Polish:
                watched.setOption(QMessageBox.Option.DontUseNativeDialog, True)
            elif event.type() == QEvent.Type.Show:
                self._visible_boxes[id(watched)] = watched
                apply_popup_template(watched)
            elif event.type() == QEvent.Type.Hide:
                self._visible_boxes.pop(id(watched), None)
            elif (event.type() == QEvent.Type.LayoutRequest
                  and hasattr(watched, "_popup_illustration")
                  and watched.layout().indexOf(watched._popup_illustration) < 0):
                # Qt reconstruit sa grille lorsque les détails sont dépliés.
                watched.setProperty("popupTemplateApplied", False)
                apply_popup_template(watched)
        return False


def install_popup_template(app: QApplication) -> None:
    """Installation unique au démarrage, pour tous les pop-up de l'application."""
    if not hasattr(app, "_popup_template_filter"):
        app._popup_template_filter = _PopupFilter(app)
        app.installEventFilter(app._popup_template_filter)


class MessageBox(QMessageBox):
    """Point d'entrée des messages de l'éditeur, avec le gabarit dès l'ouverture.

    Même API que QMessageBox, y compris les raccourcis statiques et leurs
    réponses. Le filtre global reste utile aux messages des plugins tiers.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setOption(QMessageBox.Option.DontUseNativeDialog, True)

    def showEvent(self, event):
        apply_popup_template(self)
        super().showEvent(event)

    @classmethod
    def _message(cls, icon, parent, title, text, buttons, defaultButton):
        box = cls(icon, title, text, buttons, parent)
        if defaultButton != cls.StandardButton.NoButton:
            box.setDefaultButton(defaultButton)
        return cls.StandardButton(box.exec())

    @classmethod
    def information(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok,
                    defaultButton=QMessageBox.StandardButton.NoButton):
        return cls._message(cls.Icon.Information, parent, title, text, buttons, defaultButton)

    @classmethod
    def warning(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok,
                defaultButton=QMessageBox.StandardButton.NoButton):
        return cls._message(cls.Icon.Warning, parent, title, text, buttons, defaultButton)

    @classmethod
    def critical(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok,
                 defaultButton=QMessageBox.StandardButton.NoButton):
        return cls._message(cls.Icon.Critical, parent, title, text, buttons, defaultButton)

    @classmethod
    def question(cls, parent, title, text,
                 buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                 defaultButton=QMessageBox.StandardButton.NoButton):
        return cls._message(cls.Icon.Question, parent, title, text, buttons, defaultButton)
