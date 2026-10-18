"""La poignée de page est une main: ouverte au repos, fermée pendant la prise."""
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent

from ui.common.drag_grip import DragGrip


def _mouse(kind, button=Qt.MouseButton.LeftButton):
    return QMouseEvent(kind, QPointF(1, 1), QPointF(1, 1), button, button, Qt.KeyboardModifier.NoModifier)


def test_grip_cursor_open_then_closed_then_open(qapp):
    grip = DragGrip()
    assert grip.cursor().shape() == Qt.CursorShape.OpenHandCursor
    grip.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress))
    assert grip.cursor().shape() == Qt.CursorShape.ClosedHandCursor
    grip.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease))
    assert grip.cursor().shape() == Qt.CursorShape.OpenHandCursor
