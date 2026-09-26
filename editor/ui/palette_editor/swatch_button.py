"""ui/palette_editor/swatch_button.py — case de palette (swatch) peinte sur mesure."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve

from ui.common.theme import C

# Taille de cellule des swatches : grandes cases en 16 (4×4 qui remplit l'espace),
# compactes en 256 (16×16 = carte lisible).
SWATCH_CELL_16 = 56
SWATCH_CELL_256 = 32
SWATCH_GAP = 3


class SwatchButton(QPushButton):
    """Case de palette peinte sur mesure : coins arrondis + contour de sélection
    — blanc (case active/curseur) ou vert (membre d'une sélection) — ANIMÉ. Une
    valeur `_lift` (0→1) pilote l'apparition du contour : survol = fondu discret,
    sélection = « pop » (l'easing OutBack dépasse légèrement 1 puis revient) qui
    attire l'œil → meilleure lisibilité de l'état sans ombre interne. Taille fixe,
    tout est peint EN DEDANS → la géométrie ne bouge jamais."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rgb = (0, 0, 0)
        self._selected = False
        self._active = False
        self._checker = False        # slot index 0 (transparent GBA)
        self._hover = False
        self._lift = 0.0             # proéminence animée du contour (0..~1.1)
        self._anim: Optional[QVariantAnimation] = None
        self._ready = False          # 1er set = snap (pas d'anim au 1er rendu)

    # ── État + animation ──────────────────────────────────────────
    def set_swatch(self, rgb, selected: bool, active: bool, animate: bool = True):
        self._rgb, self._selected, self._active, self._checker = rgb, selected, active, False
        self._retarget(animate)
        self._ready = True
        self.update()

    def set_checker(self):
        self._checker = True
        self._ready = True
        self.update()

    def enterEvent(self, e):
        self._hover = True; self._retarget(True); super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False; self._retarget(True); super().leaveEvent(e)

    def _target(self) -> float:
        if self._active or self._selected:
            return 1.0
        if self._hover and self.isEnabled():
            return 0.4                # liseré de survol, discret
        return 0.0

    def _retarget(self, animate: bool):
        t = self._target()
        if not (animate and self._ready) or abs(self._lift - t) < 0.005:
            if self._anim:
                self._anim.stop()
            self._lift = t
            return
        if self._anim is None:
            self._anim = QVariantAnimation(self)
            self._anim.setDuration(150)
            self._anim.setEasingCurve(QEasingCurve.Type.OutBack)   # léger dépassement = pop
            self._anim.valueChanged.connect(self._on_anim)
        self._anim.stop()
        self._anim.setStartValue(float(self._lift))
        self._anim.setEndValue(float(t))
        self._anim.start()

    def _on_anim(self, v):
        self._lift = float(v)
        self.update()

    def _radius(self) -> float:
        return max(4.0, round(self.height() * 0.16))     # coins nettement arrondis

    # ── Peinture ──────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rad = self._radius()
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath(); path.addRoundedRect(rect, rad, rad)

        if self._checker:                      # damier transparence, non sélectionnable
            p.setClipPath(path)
            step = max(3, self.height() // 5)
            for yy in range(0, self.height(), step):
                for xx in range(0, self.width(), step):
                    on = ((xx // step) + (yy // step)) % 2 == 0
                    p.fillRect(xx, yy, step, step, QColor(C.CHECKER_B if on else C.CHECKER_A))
            return

        r, g, b = self._rgb
        p.fillPath(path, QColor(r, g, b))

        # Contour animé : la couleur dépend de l'état, l'épaisseur suit `_lift`
        # (croît en s'installant, avec un léger dépassement → pop). Dessiné EN
        # DEDANS pour ne pas rogner la géométrie.
        lift = max(0.0, self._lift)
        if lift > 0.02:
            if self._active:
                ring = QColor(C.TEXT_HI)      # blanc — curseur / case active
            elif self._selected:
                ring = QColor(C.ACCENT)   # vert — membre d'une multi-sélection
            elif self._hover and self.isEnabled():
                ring = QColor(C.TEXT_DIM)
            else:
                ring = None
            if ring is not None:
                w = 2.0 * min(1.15, lift)
                pen = QPen(ring); pen.setWidthF(w)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
                off = w / 2.0
                rp = QPainterPath()
                rp.addRoundedRect(rect.adjusted(off, off, -off, -off),
                                  max(1.0, rad - off), max(1.0, rad - off))
                p.drawPath(rp)
