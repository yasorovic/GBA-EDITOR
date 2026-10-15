"""ui/background_editor/bg_mirror_overlay.py — barres de miroir posées sur le canvas du Background Editor.

Une barre verticale (axe X) et/ou une barre horizontale (axe Y). Deux prises par barre : la LIGNE, qu'on tire pour
déplacer l'axe, et la poignée-FLÈCHE en son centre, posée sur le côté gardé et dirigée vers le côté reflété (qu'on teinte :
c'est ce que le miroir remplace) ; tirer la flèche de l'autre côté de la barre inverse le côté gardé.

Comme `PrepareOverlay`, l'item dessine et tient un geste ; il n'émet rien et ne connaît ni la souris ni le modèle.
Près du milieu de l'image, la barre s'aimante au centre. Les positions des axes sont en pixels de l'image PRÉPARÉE (ce que stocke le modèle) ; `set_scale` les ramène aux pixels
affichés quand les deux diffèrent (un bitmap est ajusté à 240×160 à l'encodage)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QRectF, QPointF

from ui.common.theme import C
from ui.background_editor.bg_prepare_geometry import SNAP

AXIS_X = "x"      # barre verticale : par défaut le côté gauche se reflète à droite
AXIS_Y = "y"      # barre horizontale : par défaut le haut se reflète en bas
GRAB_MOVE = "move"   # la ligne : déplace l'axe
GRAB_SIDE = "side"   # la flèche : change le côté gardé

_HANDLE_PX = 14   # taille de la flèche À L'ÉCRAN (indépendante du zoom)
_HIT_PX = 8       # rayon de saisie à l'écran, sur la barre comme sur la flèche
_CENTER_PX = 6    # à cette distance À L'ÉCRAN du milieu de l'image, la barre s'y aimante


class MirrorOverlay(QGraphicsItem):
    def __init__(self):
        super().__init__()
        self._axes = {AXIS_X: None, AXIS_Y: None}      # pixels de l'image préparée
        self._flips = {AXIS_X: False, AXIS_Y: False}   # True : le côté droit (bas) est gardé
        self._prepared = (0, 0)                        # taille de l'image préparée
        self._display = (0, 0)                         # taille de l'image affichée
        self._scale = (1.0, 1.0)                       # affiché / préparé
        self._zoom = 1.0
        self._grab: Optional[tuple] = None             # (axe, GRAB_MOVE | GRAB_SIDE)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    # ── État ──────────────────────────────────────────────────────
    @property
    def dragging(self) -> bool:
        return self._grab is not None

    def axes(self) -> tuple:
        return self._axes[AXIS_X], self._axes[AXIS_Y]

    def flips(self) -> tuple:
        return self._flips[AXIS_X], self._flips[AXIS_Y]

    def set_axes(self, axis_x: Optional[int], axis_y: Optional[int], flips: tuple, prepared: tuple, display: tuple):
        """Les barres d'après le modèle. `flips` = (côté droit gardé en X, côté bas gardé en Y), `prepared` = taille de
        l'image préparée, `display` = celle qu'on voit."""
        self.prepareGeometryChange()
        self._axes = {AXIS_X: axis_x, AXIS_Y: axis_y}
        self._flips = {AXIS_X: bool(flips[0]), AXIS_Y: bool(flips[1])}
        self._prepared, self._display = prepared, display
        self._scale = (display[0] / prepared[0] if prepared[0] else 1.0,
                       display[1] / prepared[1] if prepared[1] else 1.0)
        self.setVisible(axis_x is not None or axis_y is not None)
        self.update()

    def set_zoom(self, zoom: float):
        self.prepareGeometryChange()
        self._zoom = max(zoom, 0.01)

    # ── Géométrie ─────────────────────────────────────────────────
    def _shown(self, which: str) -> Optional[float]:
        """Position AFFICHÉE de l'axe, ou None s'il n'y en a pas."""
        axis = self._axes[which]
        if axis is None:
            return None
        return axis * (self._scale[0] if which == AXIS_X else self._scale[1])

    def _arrow_center(self, which: str) -> Optional[QPointF]:
        """La flèche, à côté de la barre sur le côté GARDÉ, au milieu de sa longueur."""
        pos = self._shown(which)
        if pos is None:
            return None
        gap = (_HANDLE_PX / 2 + 2) / self._zoom * (1 if self._flips[which] else -1)
        w, h = self._display
        return QPointF(pos + gap, h / 2) if which == AXIS_X else QPointF(w / 2, pos + gap)

    def hit(self, x: float, y: float) -> Optional[tuple]:
        """(axe, prise) sous (x, y) — la flèche d'abord, puis la ligne — ou None."""
        tol = _HIT_PX / self._zoom
        reach = max(tol, _HANDLE_PX / 2 / self._zoom)
        for which in (AXIS_X, AXIS_Y):
            c = self._arrow_center(which)
            if c is not None and max(abs(c.x() - x), abs(c.y() - y)) <= reach:
                return which, GRAB_SIDE
        w, h = self._display
        pos = self._shown(AXIS_X)
        if pos is not None and abs(x - pos) <= tol and -tol <= y <= h + tol:
            return AXIS_X, GRAB_MOVE
        pos = self._shown(AXIS_Y)
        if pos is not None and abs(y - pos) <= tol and -tol <= x <= w + tol:
            return AXIS_Y, GRAB_MOVE
        return None

    def cursor_for(self, grab: tuple):
        which, mode = grab
        if mode == GRAB_SIDE:
            return Qt.CursorShape.PointingHandCursor
        return Qt.CursorShape.SizeHorCursor if which == AXIS_X else Qt.CursorShape.SizeVerCursor

    # ── Geste ─────────────────────────────────────────────────────
    def begin(self, grab: tuple):
        self._grab = grab

    def drag(self, x: float, y: float, snap: bool):
        """La ligne : pose l'axe sous la souris, ramené dans l'image préparée ; `snap` l'accroche à la grille 8×8, et
        près du milieu il s'aimante au centre. La flèche : le côté gardé est celui où se trouve la souris par rapport à
        la barre — la tirer de l'autre côté l'inverse."""
        if self._grab is None:
            return
        which, mode = self._grab
        horizontal = which == AXIS_X
        k = self._scale[0] if horizontal else self._scale[1]
        pointer = x if horizontal else y
        if mode == GRAB_SIDE:
            self._flips[which] = pointer > self._shown(which)
            self.update()
            return
        pos = pointer / k
        size = self._prepared[0] if horizontal else self._prepared[1]
        if snap:
            pos = round(pos / SNAP) * SNAP
        if abs(pos - size / 2) * k * self._zoom <= _CENTER_PX:
            pos = size // 2      # aimantation au centre : le miroir parfait est le cas courant
        self.prepareGeometryChange()
        self._axes[which] = max(1, min(round(pos), size - 1))
        self.update()

    def end(self):
        self._grab = None

    # ── Dessin ────────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        m = _HANDLE_PX * 2 / self._zoom
        w, h = self._display
        return QRectF(-m, -m, w + 2 * m, h + 2 * m)

    def _tint_rect(self, which: str) -> Optional[QRectF]:
        """Le côté REMPLACÉ : à droite de la barre verticale (à gauche si le côté droit est gardé), idem en vertical."""
        pos = self._shown(which)
        if pos is None:
            return None
        w, h = self._display
        flip = self._flips[which]
        if which == AXIS_X:
            return QRectF(0, 0, pos, h) if flip else QRectF(pos, 0, w - pos, h)
        return QRectF(0, 0, w, pos) if flip else QRectF(0, pos, w, h - pos)

    def paint(self, painter: QPainter, option, widget=None):
        w, h = self._display
        accent = QColor(C.ACCENT)
        tint = QBrush(QColor(accent.red(), accent.green(), accent.blue(), 36))
        for which in (AXIS_X, AXIS_Y):
            rect = self._tint_rect(which)
            if rect is not None:
                painter.fillRect(rect, tint)

        pen = QPen(accent)
        pen.setCosmetic(True)
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        x_pos, y_pos = self._shown(AXIS_X), self._shown(AXIS_Y)
        if x_pos is not None:
            painter.drawLine(QPointF(x_pos, 0), QPointF(x_pos, h))
        if y_pos is not None:
            painter.drawLine(QPointF(0, y_pos), QPointF(w, y_pos))

        half = _HANDLE_PX / 2 / self._zoom
        painter.setBrush(QBrush(accent))
        ring = QPen(QColor(C.BG_DEEP))
        ring.setCosmetic(True)
        painter.setPen(ring)
        for which in (AXIS_X, AXIS_Y):
            c = self._arrow_center(which)
            if c is None:
                continue
            # La pointe vise le côté reflété : à droite / en bas quand le côté gauche / haut est gardé.
            s = -1 if self._flips[which] else 1
            if which == AXIS_X:
                points = [QPointF(c.x() + s * half, c.y()), QPointF(c.x() - s * half, c.y() - half),
                          QPointF(c.x() - s * half, c.y() + half)]
            else:
                points = [QPointF(c.x(), c.y() + s * half), QPointF(c.x() - half, c.y() - s * half),
                          QPointF(c.x() + half, c.y() - s * half)]
            painter.drawPolygon(QPolygonF(points))
