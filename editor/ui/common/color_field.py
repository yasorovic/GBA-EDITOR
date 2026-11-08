"""
ui/common/color_field.py — champ de couleur sans fenêtre de dialogue.

Une pastille. Un clic dessus ouvre, juste dessous, un petit sélecteur (carré
saturation/valeur, bande de teinte, valeur `#rrggbb` éditable) qui se ferme au clic
extérieur ou sur Échap. Pendant le glissé, la pastille
et la valeur suivent en aperçu ; la couleur n'est validée qu'au relâché, ce qui
fait un seul geste annulable par réglage.

Deux modes : couleur web 24 bits (`#rrggbb`), ou couleur de la console (BGR555),
quantifiée au choix. Remplace la fenêtre de couleur de Qt partout dans l'éditeur.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton, QVBoxLayout, QWidget

from core.models.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
from ui.common.theme import C, QSS, T

_HEX = re.compile(r"#?([0-9a-fA-F]{6})")
_SIDE = 150
_STRIP = 16


def _marker(p: QPainter, center: QPointF, radius: float) -> None:
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#000000"), 3))
    p.drawEllipse(center, radius, radius)
    p.setPen(QPen(QColor("#ffffff"), 1.5))
    p.drawEllipse(center, radius, radius)


class _SatValSquare(QWidget):
    """Saturation en abscisse, valeur en ordonnée, pour la teinte courante."""

    moved = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, picker: "_ColorPopup"):
        super().__init__(picker)
        self._picker = picker
        self.setFixedSize(_SIDE, _SIDE)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, _e):
        r = QRectF(self.rect())
        p = QPainter(self)
        p.fillRect(r, QColor.fromHsvF(self._picker.hue, 1.0, 1.0))
        white = QLinearGradient(r.topLeft(), r.topRight())
        white.setColorAt(0, QColor(255, 255, 255, 255))
        white.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, white)
        black = QLinearGradient(r.topLeft(), r.bottomLeft())
        black.setColorAt(0, QColor(0, 0, 0, 0))
        black.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(r, black)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _marker(p, QPointF(self._picker.sat * r.width(), (1 - self._picker.val) * r.height()), 5)

    def _pick(self, pos):
        self._picker.sat = min(1.0, max(0.0, pos.x() / self.width()))
        self._picker.val = min(1.0, max(0.0, 1 - pos.y() / self.height()))
        self.update()
        self.moved.emit()

    def mousePressEvent(self, e):
        self._pick(e.position())

    def mouseMoveEvent(self, e):
        self._pick(e.position())

    def mouseReleaseEvent(self, _e):
        self.released.emit()


class _HueStrip(QWidget):
    moved = pyqtSignal()
    released = pyqtSignal()

    def __init__(self, picker: "_ColorPopup"):
        super().__init__(picker)
        self._picker = picker
        self.setFixedSize(_STRIP, _SIDE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _e):
        r = QRectF(self.rect())
        p = QPainter(self)
        gradient = QLinearGradient(r.topLeft(), r.bottomLeft())
        for i in range(7):
            gradient.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1.0, 1.0))
        p.fillRect(r, gradient)
        y = self._picker.hue * r.height()
        p.setPen(QPen(QColor("#000000"), 3))
        p.drawLine(QPointF(0, y), QPointF(r.width(), y))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawLine(QPointF(0, y), QPointF(r.width(), y))

    def _pick(self, pos):
        self._picker.hue = min(0.9999, max(0.0, pos.y() / self.height()))
        self.update()
        self.moved.emit()

    def mousePressEvent(self, e):
        self._pick(e.position())

    def mouseMoveEvent(self, e):
        self._pick(e.position())

    def mouseReleaseEvent(self, _e):
        self.released.emit()


class _ColorPopup(QFrame):
    """Le sélecteur posé sous la pastille. Une fenêtre `Popup` : Qt la ferme
    au clic extérieur et sur Échap."""

    previewed = pyqtSignal(QColor)
    committed = pyqtSignal(QColor)
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.WindowType.Popup)
        self.hue, self.sat, self.val = 0.0, 0.0, 0.0
        self._shown = "#000000"
        self.setObjectName("colorPopup")
        self.setStyleSheet(f"#colorPopup{{background:{C.BG_RAISED};"
                           f"border:1px solid {C.BORDER_MID};border-radius:4px;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._square = _SatValSquare(self)
        self._strip = _HueStrip(self)
        row.addWidget(self._square)
        row.addWidget(self._strip)
        lay.addLayout(row)
        for part in (self._square, self._strip):
            part.moved.connect(self._on_moved)
            part.released.connect(lambda: self.committed.emit(self.color()))
        # La valeur 24 bits, éditable : la même couleur que le carré, en texte.
        self._hex = QLineEdit()
        self._hex.setFont(QFont(T.MONO, T.MD))
        self._hex.setStyleSheet(QSS.lineedit)
        self._hex.setMaxLength(7)
        self._hex.textEdited.connect(self._preview_text)
        self._hex.editingFinished.connect(self._typed)
        lay.addWidget(self._hex)

    def color(self) -> QColor:
        return QColor.fromHsvF(self.hue, self.sat, self.val)

    def set_color(self, color: QColor) -> None:
        hue, sat, val, _ = color.getHsvF()
        if hue >= 0:              # un gris n'a pas de teinte : on garde la précédente
            self.hue = hue
        self.sat, self.val = sat, val
        self._square.update()
        self._strip.update()

    def show_hex(self, color: QColor) -> None:
        """Affiche la couleur retenue par le champ (quantifiée en mode GBA)."""
        self._shown = color.name()
        if not self._hex.hasFocus():
            self._hex.setText(self._shown)

    def _typed(self):
        match = _HEX.fullmatch(self._hex.text().strip())
        self._hex.clearFocus()
        if match:
            color = QColor(f"#{match.group(1)}")
            self.set_color(color)
            self.committed.emit(color)   # le champ rappelle show_hex avec la valeur retenue
        else:
            self._hex.setText(self._shown)

    def _preview_text(self, text):
        match = _HEX.fullmatch(text.strip())
        self.previewed.emit(QColor(f"#{match.group(1)}") if match else self.color())

    def _on_moved(self):
        self._square.update()
        self.previewed.emit(self.color())

    def hideEvent(self, event):
        super().hideEvent(event)
        self.dismissed.emit()


class ColorField(QWidget):
    """Pastille qui ouvre le sélecteur. Émet `committed(valeur)` une fois par geste.

    `gba=False` : couleur web 24 bits, valeur `"#rrggbb"`.
    `gba=True` : couleur de la console, valeur `int` BGR555, affichée `0x7FFF` à côté
    de la pastille. Le choix est quantifié à 5 bits par composante : la pastille
    montre ce que la console affichera réellement, pas la couleur 8 bits choisie."""

    committed = pyqtSignal(object)
    previewed = pyqtSignal(object)

    def __init__(self, gba: bool = False, parent=None):
        super().__init__(parent)
        self._gba = gba
        self._value = 0 if gba else "#000000"
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._swatch = QToolButton()
        self._swatch.setFixedSize(40, 22)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.clicked.connect(self._open)
        row.addWidget(self._swatch)
        # La valeur se saisit dans le sélecteur ; en mode GBA, le BGR555 reste lisible ici.
        self._bgr555 = None
        if gba:
            self._bgr555 = QLabel()
            self._bgr555.setFont(QFont(T.MONO, T.XS))
            self._bgr555.setStyleSheet(f"color:{C.TEXT_MUTED};")
            row.addWidget(self._bgr555)
        self._popup: _ColorPopup | None = None

    def value(self):
        return self._value

    def set_value(self, value) -> None:
        """Affiche `value` sans émettre."""
        self._value = value if self._gba else value.lower()
        self._show(self._value)

    def _qcolor(self, value) -> QColor:
        return QColor(*bgr555_to_rgb888(value)) if self._gba else QColor(value)

    def _from_qcolor(self, color: QColor):
        if self._gba:
            return rgb888_to_bgr555(color.red(), color.green(), color.blue())
        return color.name()

    def _show(self, value) -> None:
        self._swatch.setStyleSheet(
            f"QToolButton{{background:{self._qcolor(value).name()};"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
            f"QToolButton:hover{{border-color:{C.ACCENT};}}")
        if self._bgr555 is not None:
            self._bgr555.setText(f"0x{value:04X}")
        if self._popup is not None:
            self._popup.show_hex(self._qcolor(value))

    def _commit(self, value) -> None:
        if value != self._value:
            self._value = value
            self.committed.emit(value)
        self._preview(self._value)

    def _preview(self, value):
        self._show(value)
        self.previewed.emit(value)

    def _open(self):
        if self._popup is None:
            self._popup = _ColorPopup(self)
            self._popup.previewed.connect(lambda c: self._preview(self._from_qcolor(c)))
            self._popup.committed.connect(lambda c: self._commit(self._from_qcolor(c)))
            self._popup.dismissed.connect(lambda: self._preview(self._value))
        self._popup.set_color(self._qcolor(self._value))
        self._popup.show_hex(self._qcolor(self._value))
        self._popup.move(self._swatch.mapToGlobal(self._swatch.rect().bottomLeft()))
        self._popup.show()
