"""Poignée de glissement vertical : annonce la position du curseur, la vue décide de la cible.

Pendant le glissement, un FANTÔME (capture semi-transparente de la ligne tirée) suit le curseur et
la ligne d'origine s'atténue : le geste paraît déplacer la ligne elle-même."""
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect

from ui.common import icons
from ui.common.labels import label

_GHOST_OPACITY = 0.75
_SOURCE_OPACITY = 0.35
_ICON_PX = 16
_START_DISTANCE = 3         # px avant de considérer un clic comme un glissement


class _Ghost(QLabel):
    """Fenêtre flottante sans bordure, transparente aux clics, qui montre la capture."""

    def __init__(self, pixmap):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setPixmap(pixmap)
        self.resize(pixmap.deviceIndependentSize().toSize())
        self.setWindowOpacity(_GHOST_OPACITY)


class DragGrip(QLabel):
    moved = pyqtSignal(int)       # y global du curseur pendant le glissement
    released = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._down = False
        self._press = QPoint()
        self._ghost = None
        self._source = None            # () -> QWidget : ce que le fantôme reproduit
        self._offset = QPoint()
        self.setFixedWidth(_ICON_PX + 4)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet("background:transparent;")
        pixmap = icons.scaled_pixmap("drag_grip", icons.COLOR_DEFAULT, _ICON_PX,
                                     self.devicePixelRatioF()).copy()
        pixmap.setDevicePixelRatio(pixmap.width() / _ICON_PX)   # net en HiDPI, affiché à _ICON_PX
        self.setPixmap(pixmap)
        self.setToolTip(label("uiinsp.text.page_drag"))

    def set_ghost_source(self, source) -> None:
        self._source = source

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._down = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._press = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._down:
            return
        pos = event.globalPosition().toPoint()
        if self._ghost is None and abs(pos.y() - self._press.y()) >= _START_DISTANCE:
            self._start_ghost()
        if self._ghost is not None:
            self._place_ghost(pos)
        self.moved.emit(pos.y())

    def mouseReleaseEvent(self, event):
        if self._down:
            self._down = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._stop_ghost()
            self.released.emit(int(event.globalPosition().y()))

    # ── Fantôme ───────────────────────────────────────────────────

    def _start_ghost(self):
        widget = self._source() if self._source else None
        if widget is None:
            return
        self._ghost = _Ghost(widget.grab())
        self._offset = self._press - widget.mapToGlobal(QPoint(0, 0))
        self._left = widget.mapToGlobal(QPoint(0, 0)).x()
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(_SOURCE_OPACITY)
        widget.setGraphicsEffect(effect)
        self._dimmed = widget
        self._ghost.show()

    def _place_ghost(self, pos):
        # Même abscisse que la ligne : elle ne se déplace que verticalement.
        self._ghost.move(self._left, pos.y() - self._offset.y())

    def _stop_ghost(self):
        if self._ghost is not None:
            self._ghost.close()
            self._ghost.deleteLater()
            self._ghost = None
        dimmed, self._dimmed = getattr(self, "_dimmed", None), None
        if dimmed is not None:
            try:
                dimmed.setGraphicsEffect(None)
            except RuntimeError:          # la ligne a été détruite par le rafraîchissement
                pass
