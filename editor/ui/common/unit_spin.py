"""
editor/ui/common/unit_spin.py — un champ entier dont l'UNITÉ est dehors.

Un `QSpinBox` avec `setSuffix(" %")` met l'unité DANS le texte qu'on édite : le curseur s'y promène, la
sélection l'emporte, une frappe la remplace. Les champs de valeur de l'éditeur (`ValueField` : « 120 » puis
un bouton « px ») ne l'ont jamais fait : le nombre seul est éditable, l'unité se lit à côté. `UnitSpin` donne
la même chose à tout champ entier qui n'a PAS besoin d'un mode (pixels / tiles / variable).

À utiliser À LA PLACE de `QSpinBox` + `setSuffix` / `setPrefix`. L'interface reprend celle du QSpinBox que les
écrans utilisaient déjà — `setSuffix(" %")` pose l'unité (les espaces de bord sont retirés : la mise en page
les donne), `setPrefix("Window ")` pose un libellé AVANT le champ — pour que changer d'un widget à l'autre
ne touche que la ligne qui le construit. `field` donne le QSpinBox lui-même quand il faut l'atteindre.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QWidget

from ui.common.theme import C, QSS, T


MIN_SPIN_WIDTH = 56      # quatre chiffres + les flèches : en dessous, la valeur n'est plus lisible
_UNIT_WIDTH = 30    # la largeur du bouton d'unité de `ValueField`


class QuietSpin(QSpinBox):
    """N'attrape la molette que s'il a déjà le focus : sinon il vole le défilement du panneau d'inspecteur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(MIN_SPIN_WIDTH)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def focusInEvent(self, event):
        # Le clic qui donne le focus pose le curseur ; la valeur est alors complétée au lieu
        # d'être remplacée (« 8 » tapé dans « 16 » donne 168). Sélectionner tout après ce clic.
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


class UnitSpin(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.field = QuietSpin()
        self.field.setStyleSheet(QSS.spinbox)
        self.field.setFont(QFont(T.MONO, T.MD))
        self._lead = self._dim_label()
        self._unit = self._dim_label()
        self._unit.setMinimumWidth(_UNIT_WIDTH)      # « % », « fr », « px » : une colonne, les champs d'un formulaire restent alignés
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._lead)
        layout.addWidget(self.field, 1)
        layout.addWidget(self._unit)
        self.field.valueChanged.connect(self._on_changed)
        self.setFocusProxy(self.field)
        self._sync()

    @staticmethod
    def _dim_label() -> QLabel:
        label = QLabel()
        label.setFont(QFont(T.UI, T.SM))
        label.setStyleSheet(f"color:{C.TEXT_DIM};")
        label.setVisible(False)
        return label

    # ── L'interface du QSpinBox, ce que les écrans en utilisaient ─────
    def setRange(self, low: int, high: int) -> None:
        self.field.setRange(low, high)
        self._sync()

    def setMinimum(self, value: int) -> None:
        self.field.setMinimum(value)
        self._sync()

    def setMaximum(self, value: int) -> None:
        self.field.setMaximum(value)

    def minimum(self) -> int:
        return self.field.minimum()

    def maximum(self) -> int:
        return self.field.maximum()

    def setValue(self, value: int) -> None:
        self.field.setValue(value)

    def value(self) -> int:
        return self.field.value()

    def setSingleStep(self, step: int) -> None:
        self.field.setSingleStep(step)

    def setKeyboardTracking(self, on: bool) -> None:
        self.field.setKeyboardTracking(on)

    def setSpecialValueText(self, text: str) -> None:
        """Le texte du plancher (« De l'animé ») : l'unité n'a rien à dire à côté d'un mot, elle se cache alors."""
        self.field.setSpecialValueText(text)
        self._sync()

    def setSuffix(self, text: str) -> None:
        self._unit.setText(text.strip())
        self._sync()

    def setPrefix(self, text: str) -> None:
        self._lead.setText(text.strip())
        self._sync()

    def setFont(self, font: QFont) -> None:
        self.field.setFont(font)

    def setStyleSheet(self, sheet: str) -> None:
        """La feuille de style est celle du CHAMP : les libellés d'unité gardent la leur."""
        self.field.setStyleSheet(sheet)

    def setToolTip(self, text: str) -> None:
        for part in (self.field, self._lead, self._unit):
            part.setToolTip(text)
        super().setToolTip(text)

    # ── Interne ───────────────────────────────────────────────────────
    def _on_changed(self, value: int) -> None:
        self._sync()
        self.valueChanged.emit(value)

    def _sync(self) -> None:
        showing_word = bool(self.field.specialValueText()) and self.field.value() == self.field.minimum()
        self._unit.setVisible(bool(self._unit.text()) and not showing_word)
        self._lead.setVisible(bool(self._lead.text()))
