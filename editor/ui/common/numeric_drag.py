"""Interaction commune des champs numériques de l'éditeur.

La molette appartient au panneau qui contient le champ ; un déplacement
horizontal avec le bouton gauche maintenu ajuste la valeur, comme dans les
inspecteurs de moteurs de jeu.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QAbstractScrollArea, QAbstractSpinBox, QWidget


_DRAG_THRESHOLD = 3
_PIXELS_PER_STEP = 8


@dataclass
class _Drag:
    origin: QPoint
    value: float
    active: bool = False


class NumericDragBehavior(QObject):
    """Filtre d'événements pour tous les ``QSpinBox`` et ``QDoubleSpinBox``.

    L'installation au niveau de l'application couvre aussi les champs créés
    par les plugins, sans obliger chaque inspecteur à choisir une sous-classe.
    """
    def __init__(self, app: QApplication):
        super().__init__(app)
        self._drags: dict[QAbstractSpinBox, _Drag] = {}

    @staticmethod
    def _spinbox_for(obj) -> QAbstractSpinBox | None:
        # Le filtre est global : il reçoit aussi les événements d'objets non
        # graphiques (modèles de vue, dont `parent()` exige un index). Seuls les
        # widgets remontent, par `parentWidget()`.
        while isinstance(obj, QWidget):
            if isinstance(obj, QAbstractSpinBox):
                return obj
            obj = obj.parentWidget()
        return None

    @staticmethod
    def _spin_position(spin: QAbstractSpinBox, obj, position: QPoint) -> QPoint:
        return spin.mapFromGlobal(obj.mapToGlobal(position))

    @staticmethod
    def _in_editor(spin: QAbstractSpinBox, position: QPoint) -> bool:
        edit = spin.lineEdit()
        return edit is not None and edit.geometry().contains(position)

    @staticmethod
    def _set_drag_cursor(spin: QAbstractSpinBox, enabled: bool) -> None:
        shape = Qt.CursorShape.SizeHorCursor if enabled else Qt.CursorShape.IBeamCursor
        spin.setCursor(shape)
        if spin.lineEdit() is not None:
            spin.lineEdit().setCursor(shape)

    @staticmethod
    def _scroll_container(spin: QAbstractSpinBox) -> QAbstractScrollArea | None:
        parent = spin.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def _forward_wheel_to_scroll(self, spin: QAbstractSpinBox, event: QWheelEvent) -> None:
        scroll = self._scroll_container(spin)
        if scroll is None:
            return
        bar = scroll.verticalScrollBar()
        delta = event.pixelDelta().y()
        if not delta:
            delta = event.angleDelta().y() // 120 * bar.singleStep() * 3
        bar.setValue(bar.value() - delta)

    def eventFilter(self, obj, event):  # noqa: N802 - API Qt
        spin = self._spinbox_for(obj)
        if spin is None or not spin.isEnabled() or spin.isReadOnly():
            return False

        kind = event.type()
        if kind == QEvent.Type.Wheel:
            self._forward_wheel_to_scroll(spin, event)
            event.accept()
            return True

        if kind == QEvent.Type.MouseButtonPress:
            mouse = event
            if mouse.button() != Qt.MouseButton.LeftButton:
                return False
            pos = self._spin_position(spin, obj, mouse.position().toPoint())
            if not self._in_editor(spin, pos):
                return False
            self._drags[spin] = _Drag(pos, spin.value())
            self._set_drag_cursor(spin, True)
            return False  # un simple clic garde l'édition native du texte

        drag = self._drags.get(spin)
        if drag is None:
            return False

        if kind == QEvent.Type.MouseMove:
            mouse = event
            pos = self._spin_position(spin, obj, mouse.position().toPoint())
            dx = pos.x() - drag.origin.x()
            if not drag.active and abs(dx) >= _DRAG_THRESHOLD:
                drag.active = True
            if drag.active:
                steps = int(dx / _PIXELS_PER_STEP)
                spin.setValue(drag.value + steps * spin.singleStep())
                event.accept()
                return True
            return False

        if kind == QEvent.Type.MouseButtonRelease:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            self._drags.pop(spin, None)
            self._set_drag_cursor(spin, False)
            return drag.active
        return False


def install_numeric_drag_behavior(app: QApplication) -> NumericDragBehavior:
    """Active une seule fois l'interaction numérique globale de l'application."""
    existing = getattr(app, "_numeric_drag_behavior", None)
    if existing is not None:
        return existing
    behavior = NumericDragBehavior(app)
    app.installEventFilter(behavior)
    app._numeric_drag_behavior = behavior
    return behavior
