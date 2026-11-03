"""La molette ne change jamais la valeur d'une liste déroulante, focus ou non."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QVBoxLayout, QWidget

from ui.common.numeric_drag import install_numeric_drag_behavior


@pytest.mark.ui
@pytest.mark.parametrize("focused", [False, True])
def test_wheel_does_not_change_combo(focused):
    app = QApplication.instance() or QApplication([])
    install_numeric_drag_behavior(app)
    host = QWidget()
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    QVBoxLayout(host).addWidget(combo)
    host.show()
    if focused:
        combo.setFocus()
    app.processEvents()
    event = QWheelEvent(QPointF(5, 5), QPointF(combo.mapToGlobal(QPoint(5, 5))), QPoint(0, 0),
                        QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(combo, event)
    assert combo.currentIndex() == 0
