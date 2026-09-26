"""ui/background_editor/bg_prepare_overlay.py — poignées de recadrage et de
redimensionnement posées sur le canvas du Background Editor.

L'item dessine et tient un geste ; il n'émet rien et ne connaît ni la souris ni
le modèle. La vue lui passe les positions (`begin` / `drag` / `end`), les règles
de modificateurs sont dans `bg_prepare_geometry`, et c'est le canvas qui décide
quoi faire du résultat.

Deux modes, qui ne montrent pas la même chose :
  · « crop »   — le rectangle vit dans les pixels de la SOURCE (l'image entière est
                 affichée, le dehors du rectangle est assombri) ;
  · « resize » — le rectangle est l'image PRÉPARÉE ; les huit poignées se tirent, le côté
                 opposé reste fixe. L'image encodée se repose en (0, 0) une fois appliquée.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF

from ui.common.theme import C
from ui.background_editor.bg_prepare_geometry import crop_target, resize_target

MODE_CROP = "crop"
MODE_RESIZE = "resize"

_HANDLE_PX = 9        # côté d'une poignée À L'ÉCRAN (indépendant du zoom)
_HIT_PX = 8           # rayon de saisie à l'écran

_CURSORS = {
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "move": Qt.CursorShape.SizeAllCursor,
}


class PrepareOverlay(QGraphicsItem):
    def __init__(self):
        super().__init__()
        self._mode: Optional[str] = None
        self._rect = (0, 0, 0, 0)         # (l, t, r, b), pixels de l'image du mode
        self._bounds = (0, 0)             # taille de la source (mode crop)
        self._zoom = 1.0
        self._grab: Optional[str] = None
        self._start_rect = self._rect
        self._start_pt = (0.0, 0.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    # ── État ──────────────────────────────────────────────────────
    @property
    def mode(self) -> Optional[str]:
        return self._mode

    @property
    def dragging(self) -> bool:
        return self._grab is not None

    def start_crop(self, source_size: tuple, rect: tuple):
        """Mode recadrage : `rect` = (x, y, w, h) courant, dans la source."""
        x, y, w, h = rect
        self.prepareGeometryChange()
        self._mode = MODE_CROP
        self._bounds = source_size
        self._rect = (x, y, x + w, y + h)
        self.setVisible(True)

    def start_resize(self, size: tuple):
        """Mode redimensionnement : `size` = (w, h) de l'image préparée."""
        self.prepareGeometryChange()
        self._mode = MODE_RESIZE
        self._rect = (0, 0, size[0], size[1])
        self.setVisible(True)

    def stop(self):
        self.prepareGeometryChange()
        self._mode = None
        self._grab = None
        self.setVisible(False)

    def set_zoom(self, zoom: float):
        self.prepareGeometryChange()
        self._zoom = max(zoom, 0.01)

    def crop_rect(self) -> tuple:
        """(x, y, w, h) du recadrage courant."""
        l, t, r, b = self._rect
        return (l, t, r - l, b - t)

    def size(self) -> tuple:
        l, t, r, b = self._rect
        return (r - l, b - t)

    # ── Poignées ──────────────────────────────────────────────────
    def _handles(self) -> dict:
        l, t, r, b = self._rect
        cx, cy = (l + r) / 2, (t + b) / 2
        return {"nw": QPointF(l, t), "n": QPointF(cx, t), "ne": QPointF(r, t),
                "w": QPointF(l, cy), "e": QPointF(r, cy),
                "sw": QPointF(l, b), "s": QPointF(cx, b), "se": QPointF(r, b)}

    def hit(self, x: float, y: float) -> Optional[str]:
        """Nom de la poignée sous (x, y) — ou « move » à l'intérieur d'un
        recadrage — sinon None."""
        if self._mode is None:
            return None
        tol = _HIT_PX / self._zoom
        best, best_d = None, tol
        for name, p in self._handles().items():
            d = max(abs(p.x() - x), abs(p.y() - y))
            if d <= best_d:
                best, best_d = name, d
        if best:
            return best
        l, t, r, b = self._rect
        if self._mode == MODE_CROP and l <= x <= r and t <= y <= b:
            return "move"
        return None

    def cursor_at(self, x: float, y: float):
        h = self.hit(x, y)
        return _CURSORS.get(h) if h else None

    # ── Geste ─────────────────────────────────────────────────────
    def begin(self, x: float, y: float) -> bool:
        h = self.hit(x, y)
        if h is None:
            return False
        self._grab = h
        self._start_rect = self._rect
        self._start_pt = (x, y)
        return True

    def drag(self, x: float, y: float, shift: bool, ctrl: bool):
        if self._grab is None:
            return
        dx, dy = x - self._start_pt[0], y - self._start_pt[1]
        l, t, r, b = self._start_rect
        self.prepareGeometryChange()
        if self._mode == MODE_RESIZE:
            w, h = resize_target(r - l, b - t, self._grab, dx, dy, shift, ctrl)
            # Le côté opposé à la poignée reste où il est : tirer la gauche ou le
            # haut fait reculer ce bord, pas glisser toute l'image. Sans poignée sur
            # un axe (proportionnel), le bord haut-gauche tient.
            nl = r - w if "w" in self._grab else l
            nt = b - h if "n" in self._grab else t
            self._rect = (nl, nt, nl + w, nt + h)
        else:
            self._rect = crop_target(self._start_rect, self._bounds, self._grab,
                                     dx, dy, shift, ctrl)
        self.update()

    def end(self):
        self._grab = None

    # ── Dessin ────────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        m = _HANDLE_PX / self._zoom
        if self._mode == MODE_CROP:
            return QRectF(-m, -m, self._bounds[0] + 2 * m, self._bounds[1] + 2 * m)
        l, t, r, b = self._rect
        return QRectF(l - m, t - m, r - l + 2 * m, b - t + 2 * m)

    def paint(self, painter: QPainter, option, widget=None):
        if self._mode is None:
            return
        l, t, r, b = self._rect
        rect = QRectF(l, t, r - l, b - t)
        accent = QColor(C.ACCENT)
        if self._mode == MODE_CROP:
            # Le dehors du recadrage est ce qui sera JETÉ : on l'assombrit.
            bw, bh = self._bounds
            dim = QBrush(QColor(0, 0, 0, 140))
            painter.fillRect(QRectF(0, 0, bw, t), dim)
            painter.fillRect(QRectF(0, b, bw, bh - b), dim)
            painter.fillRect(QRectF(0, t, l, b - t), dim)
            painter.fillRect(QRectF(r, t, bw - r, b - t), dim)
        pen = QPen(accent)
        pen.setCosmetic(True)
        pen.setWidth(1)
        if self._mode == MODE_RESIZE:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        side = _HANDLE_PX / self._zoom
        painter.setBrush(QBrush(accent))
        solid = QPen(QColor(C.BG_DEEP))
        solid.setCosmetic(True)
        painter.setPen(solid)
        for p in self._handles().values():
            painter.drawRect(QRectF(p.x() - side / 2, p.y() - side / 2, side, side))
