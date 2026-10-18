"""ui/background_editor/bg_placement_overlay.py — l'image d'un fond posée dans son canvas, à la souris.

Un seul item : il dessine le FICHIER (entier, même quand il déborde), grise ce qui sort du canvas, trace le cadre du
canvas et les poignées de l'image. Il tient aussi le geste (déplacer, mettre à l'échelle) ; les règles de modificateurs
sont dans `bg_placement_geometry`, et c'est la vue qui décide quand l'appeler.

Les coordonnées sont celles du CANVAS : (0, 0) est son coin haut-gauche.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsItem

from ui.common.theme import C
from ui.background_editor.bg_placement_geometry import HANDLES, move_rect, scale_rect

_HANDLE_PX = 8                 # côté d'une poignée, à l'écran
_REACH = 100_000               # le grisé couvre tout ce qui entoure le canvas, quel que soit le défilement

_CURSORS = {"nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
            "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
            "move": Qt.CursorShape.SizeAllCursor}


class PlacementOverlay(QGraphicsItem):
    """Deux états. PASSIF (le passe-partout, comme celui d'une caméra de Blender) : le fichier n'est montré que HORS du
    canvas, grisé, avec le cadre du canvas — ce qui sort du cadre existe toujours, on le voit. ACTIF (le mode Canvas) :
    le fichier entier, dans le canvas aussi, avec les poignées de l'image, et le geste."""

    def __init__(self):
        super().__init__()
        self.setVisible(False)
        self._pix = QPixmap()
        self._canvas = (0, 0)
        self._rect = (0, 0, 0, 0)
        self._zoom = 1.0
        self._active = False
        self._selected = False
        self._dim = 150                   # l'opacité du grisé hors canvas (0-255) : le passe-partout, réglable à la barre
        self._grab: Optional[str] = None
        self._start_rect = self._rect
        self._start_point = (0.0, 0.0)

    def boundingRect(self) -> QRectF:
        return QRectF(-_REACH, -_REACH, 2 * _REACH, 2 * _REACH)

    # ── État ─────────────────────────────────────────────────────
    def show_passive(self, pixmap: QPixmap, canvas: tuple, rect: tuple) -> None:
        """Le passe-partout : le fichier `pixmap` posé en `rect`, visible seulement hors du canvas."""
        self._pix, self._canvas, self._rect = pixmap, tuple(canvas), tuple(rect)
        self._active, self._grab = False, None
        self.setVisible(True)
        self.update()

    def start(self, pixmap: QPixmap, canvas: tuple, rect: tuple) -> None:
        """Le mode Canvas : le fichier entier et ses poignées."""
        self.show_passive(pixmap, canvas, rect)
        self._active = True
        self._selected = False        # les poignées n'apparaissent qu'au clic sur l'image

    def stop(self) -> None:
        """Rien n'est montré (fond sans fichier, ou mode quitté en attendant que le passe-partout soit remis)."""
        self._active, self._grab, self._selected = False, None, False
        self._pix = QPixmap()
        self.setVisible(False)

    @property
    def active(self) -> bool:
        return self._active

    def set_geometry(self, canvas: tuple, rect: tuple) -> None:
        self._canvas, self._rect = tuple(canvas), tuple(rect)
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self.update()

    def set_dim(self, percent: int) -> None:
        """L'intensité du passe-partout, de 0 (ce qui déborde se voit tel quel) à 100 (noir)."""
        self._dim = round(255 * max(0, min(100, int(percent))) / 100)
        self.update()

    def rect(self) -> tuple:
        return self._rect

    def canvas(self) -> tuple:
        return self._canvas

    @property
    def dragging(self) -> bool:
        return self._grab is not None

    # ── Dessin ───────────────────────────────────────────────────
    def paint(self, painter: QPainter, option, widget=None) -> None:
        x, y, w, h = self._rect
        cw, ch = self._canvas
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        outside = QPainterPath()
        outside.addRect(self.boundingRect())
        inside = QPainterPath()
        inside.addRect(QRectF(0, 0, cw, ch))
        around = outside.subtracted(inside)
        if not self._pix.isNull():
            painter.save()
            if not self._active:
                painter.setClipPath(around)       # passif : l'image encodée, elle, tient le dedans du canvas
            painter.drawPixmap(QRectF(x, y, w, h), self._pix, QRectF(self._pix.rect()))
            painter.restore()
        # Hors du canvas : le passe-partout. L'image reste visible dessous, c'est ce qui dit qu'elle déborde.
        painter.fillPath(around, QBrush(QColor(0, 0, 0, self._dim)))
        pen_w = 1.0 / max(self._zoom, 0.01)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(C.ACCENT), pen_w * 2))
        painter.drawRect(QRectF(0, 0, cw, ch))                      # le cadre du canvas
        if not self._active or not self._selected:
            return
        painter.setPen(QPen(QColor("#ffffff"), pen_w, Qt.PenStyle.DashLine))
        painter.drawRect(QRectF(x, y, w, h))                        # le contour de l'image
        half = _HANDLE_PX / 2 / max(self._zoom, 0.01)
        painter.setPen(QPen(QColor(C.ACCENT), pen_w))
        painter.setBrush(QBrush(QColor("#ffffff")))
        for name in HANDLES:
            hx, hy = self._handle_point(name)
            painter.drawRect(QRectF(hx - half, hy - half, 2 * half, 2 * half))

    def _handle_point(self, name: str) -> tuple:
        x, y, w, h = self._rect
        px = x if "w" in name else (x + w if "e" in name else x + w / 2)
        py = y if "n" in name else (y + h if "s" in name else y + h / 2)
        return px, py

    # ── Geste ────────────────────────────────────────────────────
    def hit(self, px: float, py: float) -> Optional[str]:
        """La poignée sous (px, py), « move » dans le corps de l'image, None ailleurs (le vide du canvas, le hors-canvas,
        et tout le temps quand le passe-partout est passif)."""
        if not self._active:
            return None
        reach = _HANDLE_PX / max(self._zoom, 0.01)
        for name in HANDLES if self._selected else ():
            hx, hy = self._handle_point(name)
            if abs(px - hx) <= reach and abs(py - hy) <= reach:
                return name
        x, y, w, h = self._rect
        return "move" if x <= px <= x + w and y <= py <= y + h else None

    def cursor_at(self, px: float, py: float):
        grab = self.hit(px, py)
        return QCursor(_CURSORS[grab]) if grab else None

    def begin(self, px: float, py: float) -> bool:
        grab = self.hit(px, py)
        if self._selected != (grab is not None):      # clic sur l'image = sélection ; clic à côté = désélection
            self._selected = grab is not None
            self.update()
        if grab is None:
            return False
        self._grab, self._start_rect, self._start_point = grab, self._rect, (px, py)
        return True

    def drag(self, px: float, py: float, shift: bool, ctrl: bool) -> None:
        if self._grab is None:
            return
        dx, dy = px - self._start_point[0], py - self._start_point[1]
        if self._grab == "move":
            self._rect = move_rect(self._start_rect, dx, dy, ctrl)
        else:
            self._rect = scale_rect(self._start_rect, self._grab, dx, dy, shift, ctrl)
        self.update()

    def end(self) -> None:
        self._grab = None
