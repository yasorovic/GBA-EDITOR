"""editor/ui/palette_editor/color_wheel.py : Roue chromatique anneau + triangle.

Sélecteur de couleur « type Krita » : un anneau extérieur choisit la TEINTE,
un triangle intérieur (qui tourne pour pointer la teinte courante) choisit
saturation/luminosité. Modèle barycentrique teinte/blanc/noir — un point du
triangle = wA·(teinte pure) + wB·blanc + wC·noir, ce qui donne exactement le
comportement HSL attendu (vers le blanc = plus clair/désaturé, vers le noir =
plus sombre, vers le coin teinte = saturé).

Émet `color_changed(bgr555)` à l'interaction ; `set_value(bgr555)` repositionne
les curseurs sans réémettre. Coexiste avec les sliders RGB555/HSB de l'éditeur
(tous éditent la même couleur active)."""
from __future__ import annotations

import colorsys
import math

import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QPainter, QImage, QColor, QConicalGradient, QPainterPath, QPen, QBrush,
)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal

from core.models.gba_color import bgr555_to_rgb888, rgb888_to_bgr555

_SIDE = 172
_MARGIN = 6
_RING_T = 15                       # épaisseur de l'anneau de teinte


class ColorTriangleWheel(QWidget):
    color_changed = pyqtSignal(int)   # BGR555

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_SIDE, _SIDE)
        self._cx = self._cy = _SIDE / 2
        self._r_out = _SIDE / 2 - _MARGIN
        self._r_in = self._r_out - _RING_T
        self._r_tri = self._r_in - 6
        # État canonique : teinte 0-1 + barycentriques (teinte / blanc / noir).
        self._hue = 0.0
        self._wa, self._wb, self._wc = 1.0, 0.0, 0.0
        self._drag = None             # "ring" | "tri" | None
        self._ring_img: QImage | None = None
        self._tri_img: QImage | None = None
        self._built_dpr = 0.0         # DPR pour lequel les images ont été bâties
        self._rebuild_ring()
        self._rebuild_triangle()

    # ── HiDPI ─────────────────────────────────────────────────────

    def _dpr(self) -> float:
        """Ratio de pixels physiques de l'écran courant (1.0 par défaut). Les
        images internes sont bâties à cette résolution puis taggées pour que Qt
        les affiche nettes, sans upscaling, à leur taille logique."""
        try:
            return float(self.devicePixelRatioF()) or 1.0
        except Exception:
            return 1.0

    # ── État / conversions ────────────────────────────────────────

    def set_value(self, bgr555: int):
        """Positionne teinte + triangle depuis une couleur BGR555, sans émettre.
        Ignoré pendant un drag (l'utilisateur pilote déjà l'état)."""
        if self._drag is not None:
            return
        r, g, b = (c / 255 for c in bgr555_to_rgb888(bgr555))
        mx, mn = max(r, g, b), min(r, g, b)
        c = mx - mn
        if c > 1e-6:                  # teinte indéfinie sur un gris → on garde l'ancienne
            if mx == r:
                h = ((g - b) / c) % 6
            elif mx == g:
                h = (b - r) / c + 2
            else:
                h = (r - g) / c + 4
            new_hue = (h / 6) % 1.0
            if abs(new_hue - self._hue) > 1e-4:
                self._hue = new_hue
                self._rebuild_triangle()
        # barycentriques : wA=chroma, wB=min (blanc), wC=1-max (noir) — somme = 1.
        self._wa, self._wb, self._wc = c, mn, 1 - mx
        self.update()

    def _current_bgr555(self) -> int:
        hr, hg, hb = colorsys.hsv_to_rgb(self._hue, 1.0, 1.0)
        r = self._wa * hr + self._wb
        g = self._wa * hg + self._wb
        b = self._wa * hb + self._wb
        return rgb888_to_bgr555(round(min(1, max(0, r)) * 255),
                                round(min(1, max(0, g)) * 255),
                                round(min(1, max(0, b)) * 255))

    # ── Géométrie ─────────────────────────────────────────────────

    def _tri_vertices(self):
        """(A teinte, B blanc, C noir) en coordonnées écran — A pointe la teinte."""
        th = self._hue * 2 * math.pi
        r, cx, cy = self._r_tri, self._cx, self._cy
        return (
            np.array([cx + r * math.cos(th),              cy - r * math.sin(th)]),
            np.array([cx + r * math.cos(th + 2 * math.pi / 3), cy - r * math.sin(th + 2 * math.pi / 3)]),
            np.array([cx + r * math.cos(th + 4 * math.pi / 3), cy - r * math.sin(th + 4 * math.pi / 3)]),
        )

    @staticmethod
    def _barycentric(px, py, A, B, C):
        v0, v1 = B - A, C - A
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        denom = d00 * d11 - d01 * d01
        wx, wy = px - A[0], py - A[1]
        d20 = wx * v0[0] + wy * v0[1]
        d21 = wx * v1[0] + wy * v1[1]
        wb = (d11 * d20 - d01 * d21) / denom
        wc = (d00 * d21 - d01 * d20) / denom
        return 1 - wb - wc, wb, wc

    # ── Rendu (images cachées) ────────────────────────────────────

    def _rebuild_ring(self):
        dpr = self._dpr()
        n = round(_SIDE * dpr)
        img = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)      # le painter travaille en coords logiques
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QConicalGradient(self._cx, self._cy, 0.0)
        for i in range(0, 361, 3):        # pas fin → anneau parfaitement lisse
            r, g, b = colorsys.hsv_to_rgb((i % 360) / 360, 1, 1)
            grad.setColorAt(i / 360, QColor(round(r * 255), round(g * 255), round(b * 255)))
        path = QPainterPath()
        path.addEllipse(QPointF(self._cx, self._cy), self._r_out, self._r_out)
        inner = QPainterPath()
        inner.addEllipse(QPointF(self._cx, self._cy), self._r_in, self._r_in)
        p.setClipPath(path.subtracted(inner))
        p.fillRect(0, 0, _SIDE, _SIDE, QBrush(grad))
        p.end()
        self._ring_img = img
        self._built_dpr = dpr

    def _rebuild_triangle(self):
        dpr = self._dpr()
        n = round(_SIDE * dpr)
        A, B, C = (v * dpr for v in self._tri_vertices())   # sommets en px physiques
        ys, xs = np.mgrid[0:n, 0:n].astype(np.float64)
        px, py = xs + 0.5, ys + 0.5
        wa, wb, wc = self._barycentric(px, py, A, B, C)
        mask = (wa >= 0) & (wb >= 0) & (wc >= 0)
        hr, hg, hb = colorsys.hsv_to_rgb(self._hue, 1.0, 1.0)
        hue = np.array([hr, hg, hb]) * 255.0
        col = wa[..., None] * hue[None, None, :] + wb[..., None] * 255.0
        buf = np.zeros((n, n, 4), np.uint8)
        buf[..., 0:3] = np.clip(col, 0, 255).astype(np.uint8)
        buf[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
        img = QImage(buf.tobytes(), n, n, QImage.Format.Format_RGBA8888).copy()
        img.setDevicePixelRatio(dpr)
        self._tri_img = img

    # ── Peinture ──────────────────────────────────────────────────

    def paintEvent(self, _e):
        # Fenêtre passée sur un écran de DPR différent → images bâties pour
        # l'ancien ratio : les reconstruire avant de peindre (net partout).
        if abs(self._dpr() - self._built_dpr) > 1e-3:
            self._rebuild_ring()
            self._rebuild_triangle()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._ring_img:
            p.drawImage(0, 0, self._ring_img)
        if self._tri_img:
            p.drawImage(0, 0, self._tri_img)
        # Curseur anneau (sur l'axe médian de l'anneau, à la teinte courante).
        rm = (self._r_in + self._r_out) / 2
        th = self._hue * 2 * math.pi
        self._marker(p, self._cx + rm * math.cos(th), self._cy - rm * math.sin(th), 6)
        # Curseur triangle.
        A, B, C = self._tri_vertices()
        P = self._wa * A + self._wb * B + self._wc * C
        self._marker(p, P[0], P[1], 5)
        p.end()

    def _marker(self, p: QPainter, x: float, y: float, rad: float):
        p.setPen(QPen(QColor(0, 0, 0, 200), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.drawEllipse(QPointF(x, y), rad + 1, rad + 1)

    # ── Souris ────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        d = math.hypot(x - self._cx, y - self._cy)
        if self._r_in - 3 <= d <= self._r_out + 3:
            self._drag = "ring"
            self._set_hue(x, y)
        else:
            A, B, C = self._tri_vertices()
            wa, wb, wc = self._barycentric(x, y, A, B, C)
            if wa >= -0.02 and wb >= -0.02 and wc >= -0.02:
                self._drag = "tri"
                self._set_tri(x, y)

    def mouseMoveEvent(self, e):
        if self._drag == "ring":
            self._set_hue(e.position().x(), e.position().y())
        elif self._drag == "tri":
            self._set_tri(e.position().x(), e.position().y())

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def _set_hue(self, x, y):
        self._hue = (math.atan2(self._cy - y, x - self._cx) / (2 * math.pi)) % 1.0
        self._rebuild_triangle()
        self.update()
        self.color_changed.emit(self._current_bgr555())

    def _set_tri(self, x, y):
        A, B, C = self._tri_vertices()
        wa, wb, wc = self._barycentric(x, y, A, B, C)
        w = [max(0.0, wa), max(0.0, wb), max(0.0, wc)]   # projette dans le triangle
        s = sum(w)
        if s <= 0:
            return
        self._wa, self._wb, self._wc = (v / s for v in w)
        self.update()
        self.color_changed.emit(self._current_bgr555())
