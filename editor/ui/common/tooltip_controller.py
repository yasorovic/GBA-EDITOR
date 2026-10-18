"""One tooltip renderer for widgets, item views, tabs, canvas items and providers.

Qt emits ToolTip after the application style's hover delay. Resolve content here
before consuming that event: swallowing it without querying item roles used to
silence tree/table/canvas tooltips. Never call QToolTip.showText from an editor view.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PyQt6 import sip
from PyQt6.QtCore import QObject, QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QHelpEvent, QPainter, QPen, QTextCursor, QTextDocument, QTextOption
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QGraphicsView, QHeaderView, QLabel,
    QMenu, QTabBar, QVBoxLayout, QWidget,
)

from ui.common.theme import C, T, ui_font
from ui.common.tooltip import TOOLTIP_DURATION_MS, TOOLTIP_MAX_WIDTH, tooltip_html


@dataclass(frozen=True)
class TooltipContent:
    text: str
    rect: QRect


def set_tooltip_provider(widget, provider):
    """Register a lazy provider: QPoint in widget coordinates → content or None.

    None falls back to the normal item/widget tip; empty text suppresses the tip.
    Providers compute metadata only at hover time, never on every mouse move.
    """
    widget._editor_tooltip_provider = provider


def resolve_tooltip(widget: QWidget, position: QPoint) -> TooltipContent:
    provider = getattr(widget, '_editor_tooltip_provider', None)
    if provider is not None:
        result = provider(position)
        if result is not None:
            return result

    parent = widget.parentWidget()
    view = parent if isinstance(parent, QAbstractItemView) and parent.viewport() is widget else None
    if isinstance(view, QHeaderView):
        section = view.logicalIndexAt(position)
        if section >= 0:
            text = view.model().headerData(section, view.orientation(), Qt.ItemDataRole.ToolTipRole)
            offset, size = view.sectionViewportPosition(section), view.sectionSize(section)
            rect = (QRect(offset, 0, size, widget.height())
                    if view.orientation() == Qt.Orientation.Horizontal
                    else QRect(0, offset, widget.width(), size))
            if text:
                return TooltipContent(str(text), rect)
    elif view is not None:
        index = view.indexAt(position)
        text = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
        if text:
            return TooltipContent(str(text), view.visualRect(index))
    elif isinstance(parent, QGraphicsView) and parent.viewport() is widget:
        item = parent.itemAt(position)
        while item is not None:
            if item.toolTip():
                rect = parent.mapFromScene(item.mapToScene(item.boundingRect())).boundingRect()
                return TooltipContent(item.toolTip(), rect)
            item = item.parentItem()
    elif isinstance(widget, QTabBar):
        index = widget.tabAt(position)
        if index >= 0 and widget.tabToolTip(index):
            return TooltipContent(widget.tabToolTip(index), widget.tabRect(index))
    elif isinstance(widget, QMenu) and widget.toolTipsVisible():
        action = widget.actionAt(position)
        if action is not None and action.toolTip():
            return TooltipContent(action.toolTip(), widget.actionGeometry(action))

    # Child labels/viewport widgets also inherit the enclosing control's help.
    ancestor = widget
    while ancestor is not None:
        if ancestor.toolTip():
            rect = QRect(widget.mapFromGlobal(ancestor.mapToGlobal(QPoint())), ancestor.size())
            return TooltipContent(ancestor.toolTip(), rect)
        if ancestor.isWindow():
            break
        ancestor = ancestor.parentWidget()
    return TooltipContent('', widget.rect())


class _TooltipBubble(QFrame):
    """Theme-owned surface: no native first frame, focus or mouse interception."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setObjectName('editor_tooltip')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._background = QColor(C.BG_RAISED)
        self._border = QColor(C.BORDER_MID)
        self.setStyleSheet(
            f"QFrame#editor_tooltip{{background:transparent;color:{C.TEXT_NORM};"
            "border:none;padding:0;}"
            "QLabel{background:transparent;border:none;padding:0;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        self._text = QLabel(self)
        self._text.setTextFormat(Qt.TextFormat.RichText)
        self._text.setWordWrap(True)
        self._text.setFont(ui_font(T.SM))
        self._text.setStyleSheet(f"color:{C.TEXT_NORM};")
        layout.addWidget(self._text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._background)
        painter.setPen(QPen(self._border))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 7, 7)

    def show_text(self, position: QPoint, text: str):
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(position, self.size())
        maximum_width = max(1, min(TOOLTIP_MAX_WIDTH, area.width() - 16))
        html = tooltip_html(text)
        document = QTextDocument()
        document.setDefaultFont(self._text.font())
        document.setDocumentMargin(0)
        option = document.defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(option)
        document.setHtml(html)
        document.setTextWidth(maximum_width)
        width = max(1, min(maximum_width, ceil(document.idealWidth())))
        document.setTextWidth(width)
        maximum_height = max(1, area.height() - 10)
        if document.size().height() > maximum_height:
            # Preserve rich formatting while shortening oversized author notes.
            # Binary search prevents huge notes from overflowing the screen.
            low, high, best = 0, document.characterCount() - 1, None
            while low <= high:
                middle = (low + high) // 2
                candidate = document.clone()
                cursor = QTextCursor(candidate)
                cursor.setPosition(middle)
                cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertText('…')
                if candidate.size().height() <= maximum_height:
                    best, low = candidate, middle + 1
                else:
                    high = middle - 1
            if best is not None:
                document, html = best, best.toHtml()
        self._text.setText(html)
        # Explicit document measurement also wraps very long, unbroken paths;
        # QLabel.adjustSize() alone kept their height at a single clipped line.
        self._text.setFixedSize(width, min(maximum_height, ceil(document.size().height())))
        self.adjustSize()
        x, y = position.x() + 14, position.y() + 20
        if y + self.height() > area.bottom():
            y = position.y() - self.height() - 8
        self.move(max(area.left(), min(x, area.right() - self.width() + 1)),
                  max(area.top(), min(y, area.bottom() - self.height() + 1)))
        self.show()


class TooltipController(QObject):
    def __init__(self, app):
        super().__init__(app)
        self._bubble = None
        self._anchor = None
        self._closed = False
        self._rect = QRect()
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.timeout.connect(self.hide)
        app.aboutToQuit.connect(self.hide)

    def hide(self):
        self._expiry.stop()
        if self._bubble is not None:
            self._bubble.hide()
        if self._anchor is not None and not sip.isdeleted(self._anchor):
            self._anchor.destroyed.disconnect(self.hide)
        self._anchor = None

    def shutdown(self):
        """Release the top-level bubble while QApplication still exists."""
        if self._closed:
            return
        self._closed = True
        app = self.parent()
        app.removeEventFilter(self)
        self.hide()
        if self._bubble is not None:
            self._bubble.deleteLater()
            self._bubble = None
        app._tooltip_controller = None
        self.deleteLater()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.ToolTip and isinstance(obj, QWidget) and isinstance(event, QHelpEvent):
            content = resolve_tooltip(obj, event.pos())
            if not content.text.strip():
                self.hide()
                event.ignore()
                return True
            self.hide()
            self._anchor, self._rect = obj, content.rect
            obj.destroyed.connect(self.hide)
            if self._bubble is None:
                self._bubble = _TooltipBubble()
            self._bubble.show_text(event.globalPos(), content.text)
            self._expiry.start(TOOLTIP_DURATION_MS)
            event.accept()
            return True
        if self._anchor is not None:
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel,
                        QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
                self.hide()
            elif obj is self._anchor and kind in (
                    QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Close,
                    QEvent.Type.DeferredDelete, QEvent.Type.ToolTipChange):
                self.hide()
            elif kind == QEvent.Type.MouseMove and isinstance(obj, QWidget):
                position = self._anchor.mapFromGlobal(event.globalPosition().toPoint())
                if not self._rect.contains(position):
                    self.hide()
        return False


def install_tooltips(app):
    """Idempotent startup hook; the intentional tooltip window is created lazily."""
    controller = getattr(app, '_tooltip_controller', None)
    if controller is None:
        controller = TooltipController(app)
        app._tooltip_controller = controller
        app.installEventFilter(controller)
    return controller
