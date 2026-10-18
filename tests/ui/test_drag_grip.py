"""La poignée montre un fantôme pendant le glissement, puis le retire."""
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from ui.common.drag_grip import DragGrip


def test_ghost_follows_the_cursor_and_the_source_is_restored(qapp):
    host = QWidget()
    layout = QVBoxLayout(host)
    row = QWidget()
    row.setFixedHeight(60)
    grip = DragGrip(row)
    grip.set_ghost_source(lambda: row)
    layout.addWidget(row)
    host.resize(300, 200)
    host.show()
    qapp.processEvents()
    seen = []
    grip.moved.connect(seen.append)
    dropped = []
    grip.released.connect(dropped.append)
    try:
        center = QPoint(grip.width() // 2, grip.height() // 2)
        QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(grip, center + QPoint(0, 20))
        qapp.processEvents()
        assert grip._ghost is not None and grip._ghost.isVisible()
        assert row.graphicsEffect() is not None            # la ligne d'origine s'atténue
        QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=center + QPoint(0, 20))
        qapp.processEvents()
        assert grip._ghost is None and row.graphicsEffect() is None
        assert seen and len(dropped) == 1
    finally:
        host.close()
