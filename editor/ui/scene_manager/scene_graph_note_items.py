"""Notes libres, déplaçables et repliables du Graphe des scènes."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from ui.common.theme import C, T, ui_font

NOTE_W = 220.0
HEADER_H = 28.0
BODY_H = 108.0
_RADIUS = 7.0
_TOGGLE = 16.0
_GRID_STEP = 40.0


class NoteToggleItem(QGraphicsItem):
    """Chevron enfant, reconnu par la vue pour replier la note."""

    def __init__(self, note_id: str, collapsed: bool, color: str, parent=None):
        super().__init__(parent)
        self.note_id, self.collapsed, self.color = note_id, collapsed, color
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return QRectF(0, 0, _TOGGLE, _TOGGLE)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.color or C.TEXT_DIM)))
        c = _TOGGLE / 2
        points = ([QPointF(c - 3, c - 5), QPointF(c + 4, c), QPointF(c - 3, c + 5)]
                  if self.collapsed else
                  [QPointF(c - 5, c - 3), QPointF(c + 5, c - 3), QPointF(c, c + 4)])
        painter.drawPolygon(QPolygonF(points))


class SceneGraphNoteItem(QGraphicsItem):
    """Carton éditorial : aucun port, aucune arête, uniquement une annotation."""

    def __init__(self, note_id: str, title: str, text: str, color: str,
                 collapsed: bool, geometry_changed=None):
        super().__init__()
        self.note_id, self.title, self.text = note_id, title, text
        self.color, self.collapsed = color, collapsed
        self._geometry_changed = geometry_changed
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        toggle = NoteToggleItem(note_id, collapsed, color, self)
        toggle.setPos(7, (HEADER_H - _TOGGLE) / 2)
        toggle.setZValue(1)

    @property
    def _h(self) -> float:
        return HEADER_H if self.collapsed else HEADER_H + BODY_H

    def boundingRect(self):
        return QRectF(-2, -2, NOTE_W + 4, self._h + 4)

    def itemChange(self, change, value):
        if change is QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            point = value
            return QPointF(round(point.x() / _GRID_STEP) * _GRID_STEP,
                           round(point.y() / _GRID_STEP) * _GRID_STEP)
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._geometry_changed is not None):
            self._geometry_changed(self)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        base = QColor(self.color or "#FFFFFF")
        border = QColor(C.ACCENT) if self.isSelected() else base
        body = QRectF(0, 0, NOTE_W, self._h)
        fill = QColor(base); fill.setAlpha(30)
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(body, _RADIUS, _RADIUS)
        header = QColor(base); header.setAlpha(70)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QBrush(header))
        painter.drawRoundedRect(QRectF(0, 0, NOTE_W, HEADER_H), _RADIUS, _RADIUS)
        painter.drawRect(QRectF(0, HEADER_H - _RADIUS, NOTE_W, _RADIUS))
        painter.setPen(QPen(QColor(C.TEXT_HI))); painter.setFont(ui_font(T.MD, bold=True))
        painter.drawText(QRectF(29, 0, NOTE_W - 36, HEADER_H),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.title or "Note")
        if not self.collapsed:
            painter.setPen(QPen(QColor(C.TEXT_NORM))); painter.setFont(ui_font(T.SM))
            painter.drawText(QRectF(10, HEADER_H + 8, NOTE_W - 20, BODY_H - 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop |
                             Qt.TextFlag.TextWordWrap, self.text)
