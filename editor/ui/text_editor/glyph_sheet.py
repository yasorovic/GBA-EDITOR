"""
ui/text_editor/glyph_sheet.py — la planche de glyphes elle-même (canvas).

L'enveloppe scrollable et sa barre d'outils vivent dans `glyph_sheet_panel.py` :
ici, uniquement le dessin, le hit-test et la saisie.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QRectF, QSize, QPoint, QPointF

from ui.common.canvas_backdrop import paint_backdrop, halo_rect
from ui.common.theme import C, T
from ui.text_editor.glyph_paint import key_out, checker_brush


class GlyphSheet(QWidget):
    """Planche de la police, découpée en cases.

    Pas un éditeur de pixels : les glyphes se dessinent dans un outil d'images,
    comme un sprite. Ce qui s'édite ici est la correspondance case → caractère,
    au clavier — une case sélectionnée prend le caractère tapé et la sélection
    avance.
    """

    glyph_selected    = pyqtSignal(object)          # Glyph | None
    glyph_edited      = pyqtSignal(object, str, str)  # (glyph, avant, après)
    zoom_changed      = pyqtSignal(int)
    selection_changed = pyqtSignal(int, object)     # (nb de cases, QRect|None)
    background_clicked = pyqtSignal()               # clic hors de la planche
    color_picked      = pyqtSignal(str, object)     # (rôle, (r,g,b))
    pick_ended        = pyqtSignal()                # pipette relâchée (prise ou annulée)

    _MIN_ZOOM, _MAX_ZOOM = 2, 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._pixmap: Optional[QPixmap] = None
        self._source: Optional[QPixmap] = None   # planche BRUTE, avant trouage
        self._image = None                       # QImage source — lecture des pixels
        self._zoom = 6
        self._index = -1          # index du glyphe sélectionné
        self._hover = -1          # index survolé — révèle son caractère
        self._pan_last = None     # origine du pan clic-central
        self._halo = None         # position du halo du fond de canvas (coord. widget)
        self._range: list = []    # sélection multiple (Maj+clic) — fusion
        self._picking = ""        # rôle de couleur en cours de prélèvement, "" = aucun
        self._backdrop = None     # damier teinté (BackdropButton) — None = fond éditeur
        self._backdrop_cache = None  # brosse du damier teinté, reconstruite au besoin
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)   # survol sans bouton enfoncé
        self.setStyleSheet(f"background:{C.BG_BASE};")

    # ── Chargement ────────────────────────────────────────────────

    def load(self, font, project):
        """Charge la planche de `font` et remet la sélection à zéro."""
        self._font = font
        self._index = -1
        self._source = None
        self._image = None
        if font and font.asset and project:
            path = project.asset_abs(font.asset)
            if path and path.exists():
                px = QPixmap(str(path))
                if not px.isNull():
                    self._source = px
                    self._image = px.toImage()
        self.refresh_keying()
        self._resize_to_content()
        self.update()
        self.glyph_selected.emit(None)

    # ── Couleurs-clés ─────────────────────────────────────────────
    # Planche affichée TROUÉE (damier sous les couleurs désignées), sans quoi la
    # pipette serait aveugle. Le PNG d'origine n'est jamais modifié.

    def refresh_keying(self):
        """Reconstruit l'image affichée depuis la planche brute."""
        self._pixmap = self._keyed_pixmap()
        self.update()

    def _keyed_pixmap(self) -> Optional[QPixmap]:
        """Planche brute + couleurs-clés courantes."""
        return key_out(self._source, self._font.key_colors() if self._font else [])

    def begin_pick(self, role: str):
        """Arme la pipette pour un rôle ('bg' | 'space') : le prochain clic
        prend la couleur du pixel visé, Échap annule."""
        self._picking = role
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def cancel_pick(self):
        """Désarme la pipette sans rien prélever."""
        if not self._picking:
            return
        self._picking = ""
        self.unsetCursor()
        self.pick_ended.emit()

    def _pick_at(self, pos) -> bool:
        """Prélève la couleur sous `pos` dans la planche BRUTE (dans l'image
        trouée, un pixel déjà transparent ne dirait plus d'où il vient).
        Retourne False si le clic tombe hors image."""
        if self._image is None:
            return False
        z = self._zoom
        o = self._origin()
        x = (int(pos.x()) - o.x()) // z
        y = (int(pos.y()) - o.y()) // z
        if not (0 <= x < self._image.width() and 0 <= y < self._image.height()):
            return False
        c = self._image.pixelColor(x, y)
        role = self._picking
        self._picking = ""
        self.unsetCursor()
        self.color_picked.emit(role, (c.red(), c.green(), c.blue()))
        self.pick_ended.emit()
        return True

    def set_zoom(self, z: int):
        self._zoom = max(self._MIN_ZOOM, min(int(z), self._MAX_ZOOM))
        self._resize_to_content()
        self.update()

    @property
    def zoom(self) -> int:
        return self._zoom

    def _resize_to_content(self):
        if self._pixmap:
            self.setMinimumSize(QSize(self._pixmap.width() * self._zoom,
                                      self._pixmap.height() * self._zoom))
        else:
            self.setMinimumSize(QSize(0, 0))
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    # ── Centrage ──────────────────────────────────────────────────

    def _origin(self) -> QPoint:
        """Décalage de centrage — point unique : le rendu le pose, le hit-test
        le retire. Sans lui, les deux divergent au premier zoom."""
        if not self._pixmap:
            return QPoint(0, 0)
        w = self._pixmap.width() * self._zoom
        h = self._pixmap.height() * self._zoom
        return QPoint(max(0, (self.width() - w) // 2),
                      max(0, (self.height() - h) // 2))

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_backdrop(p, QRectF(self.rect()), max(4, round(8 * self._zoom)),
                       QPointF(self._origin()), self._halo, tiled=True)
        if not self._pixmap or not self._font:
            return
        z = self._zoom
        o = self._origin()
        p.translate(o)
        # Pixel art : jamais de lissage.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        sheet_rect = QRect(0, 0, self._pixmap.width() * z, self._pixmap.height() * z)
        # Damier : sinon une zone trouée serait indiscernable, sur le fond uni
        # du panneau, d'une zone simplement sombre. Teinté par le fond d'épreuve
        # choisi — une police sombre reste sinon noyée dans le damier sombre.
        if self._font and self._font.key_colors():
            p.fillRect(sheet_rect, self._backdrop_brush())
        p.drawPixmap(sheet_rect, self._pixmap)

        # Quadrillage NU : annoter les 224 cases en continu noyait la planche
        # sous le texte. Le caractère n'apparaît qu'au survol.
        grid = QPen(QColor(C.BORDER_MID)); grid.setWidth(1)
        p.setPen(grid)
        for g in self._font.glyphs:
            p.drawRect(QRect(g.x * z, g.y * z, g.w * z, g.h * z))

        # Survol : la case s'assombrit et montre son caractère. Suspendu
        # pendant un prélèvement, où le voile fausserait la couleur visée.
        if not self._picking and 0 <= self._hover < len(self._font.glyphs):
            g = self._font.glyphs[self._hover]
            r = QRect(g.x * z, g.y * z, g.w * z, g.h * z)
            p.fillRect(r, QColor(0, 0, 0, 165))
            label = g.char if g.char.strip() else "␣"
            p.setPen(QColor(C.TEXT_HI))
            p.setFont(self._label_font(r, label))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

        # Sélection étendue : teinte sur les cases visées, pour voir la forme
        # du futur glyphe fusionné.
        if len(self._range) > 1:
            tint = QColor(C.ACCENT); tint.setAlpha(60)
            for i in self._range:
                g = self._font.glyphs[i]
                p.fillRect(QRect(g.x * z, g.y * z, g.w * z, g.h * z), tint)

        if 0 <= self._index < len(self._font.glyphs):
            g = self._font.glyphs[self._index]
            r = QRect(g.x * z, g.y * z, g.w * z, g.h * z)
            sel = QPen(QColor(C.ACCENT)); sel.setWidth(2)
            p.setPen(sel)
            p.drawRect(r.adjusted(1, 1, -1, -1))

    _CHECKER = None

    @classmethod
    def _checker_brush(cls) -> QBrush:
        """Damier sombre par défaut, mis en cache (aussi lu par l'inspecteur)."""
        if cls._CHECKER is None:
            cls._CHECKER = checker_brush()
        return cls._CHECKER

    def _backdrop_brush(self) -> QBrush:
        """Damier de la planche : teinté au fond d'épreuve, ou le défaut sombre."""
        if self._backdrop is None:
            return self._checker_brush()
        if self._backdrop_cache is None:
            self._backdrop_cache = checker_brush(self._backdrop)
        return self._backdrop_cache

    def set_backdrop(self, color):
        """Change le fond d'épreuve du damier (`None` = fond de l'éditeur)."""
        self._backdrop = color
        self._backdrop_cache = None
        self.update()

    def _label_font(self, r: QRect, label: str) -> QFont:
        """Police du caractère révélé, dimensionnée pour tenir dans la case —
        y compris une ligature (« ... »)."""
        size = max(6, int(r.height() * 0.55))
        if len(label) > 1:
            size = max(6, int(size * 1.4 / len(label)))
        return QFont(T.MONO, size, QFont.Weight.Bold)

    # ── Sélection ─────────────────────────────────────────────────

    def _hit(self, pos) -> int:
        """Index de la case sous `pos`, -1 hors planche."""
        if not self._font:
            return -1
        z = self._zoom
        o = self._origin()
        pt = QPoint(int(pos.x()) - o.x(), int(pos.y()) - o.y())
        for i, g in enumerate(self._font.glyphs):
            if QRect(g.x * z, g.y * z, g.w * z, g.h * z).contains(pt):
                return i
        return -1

    def selection_rect(self) -> Optional[QRect]:
        """Rectangle englobant la sélection, en coordonnées IMAGE — ce que
        l'inspecteur découpe pour son aperçu, et ce que la fusion produirait."""
        bounds = self._font.glyphs_bounds(self._range) if self._font else None
        return QRect(*bounds) if bounds else None

    def mousePressEvent(self, e):
        """Clic-central = pan, pipette armée = prélèvement, sinon sélection
        (Maj+clic étend en rectangle, hors planche remet à zéro)."""
        if e.button() == Qt.MouseButton.MiddleButton:
            # Pan au clic-central — même geste que le canvas du Scene Manager.
            self._pan_last = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        # Pipette armée : le clic prend une COULEUR, pas une case. Hors image
        # il annule, sinon on désignerait la couleur du panneau.
        if self._picking:
            if not self._pick_at(e.pos()):
                self.cancel_pick()
            e.accept()
            return
        idx = self._hit(e.pos())
        if idx < 0:
            # Hors planche : sélection à zéro, l'écran retombe sur son
            # contexte par défaut (règle du Scene Manager).
            self._range = []
            self._index = -1
            self.update()
            self.glyph_selected.emit(None)
            self.selection_changed.emit(0, None)
            self.background_clicked.emit()
            return
        # Maj+clic étend en RECTANGLE : c'est la forme qu'aura le glyphe
        # fusionné, autant la désigner directement.
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self._index >= 0:
            self._range = self._rect_indices(self._index, idx)
        else:
            self._range = [idx]
            if idx != self._index:
                self._index = idx
                self.glyph_selected.emit(self._font.glyphs[idx])
        self.update()
        self.selection_changed.emit(len(self._range), self.selection_rect())
        self.setFocus()

    def _rect_indices(self, a: int, b: int) -> list:
        """Indices des cases contenues dans le rectangle englobant `a` et `b`."""
        gs = self._font.glyphs
        ga, gb = gs[a], gs[b]
        x0, x1 = min(ga.x, gb.x), max(ga.x + ga.w, gb.x + gb.w)
        y0, y1 = min(ga.y, gb.y), max(ga.y + ga.h, gb.y + gb.h)
        return [i for i, g in enumerate(gs)
                if g.x >= x0 and g.x + g.w <= x1 and g.y >= y0 and g.y + g.h <= y1]

    def selected_indices(self) -> list:
        """Cases de la sélection étendue, dans l'ordre de la planche."""
        return list(self._range)

    def _move_halo(self, pos):
        """Halo du fond de canvas : ne repeint que son carré (voir canvas_backdrop)."""
        old = self._halo
        self._halo = QPointF(pos) if pos is not None else None
        dirty = halo_rect(old, self._halo, max(4.0, 8.0 * self._zoom))
        if dirty is not None:
            self.update(dirty.toAlignedRect())

    def mouseMoveEvent(self, e):
        self._move_halo(e.position())
        if self._pan_last is not None and (e.buttons() & Qt.MouseButton.MiddleButton):
            delta = e.position() - self._pan_last
            self._pan_last = e.position()
            area = self._scroll_area()
            if area:
                h, v = area.horizontalScrollBar(), area.verticalScrollBar()
                h.setValue(h.value() - round(delta.x()))
                v.setValue(v.value() - round(delta.y()))
            e.accept()
            return
        idx = self._hit(e.pos())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._move_halo(None)
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e):
        """Molette = zoom, en gardant le point visé sous le curseur (sinon la
        case qu'on vise fuit hors de l'écran)."""
        area = self._scroll_area()
        old = self._zoom
        new = old + (1 if e.angleDelta().y() > 0 else -1)
        new = max(self._MIN_ZOOM, min(new, self._MAX_ZOOM))
        if new == old:
            return
        # Converti en coordonnées IMAGE avant le zoom : l'offset de centrage
        # change avec le zoom, il doit sortir du calcul.
        o = self._origin()
        anchor = e.position()
        img_x = (anchor.x() - o.x()) / old
        img_y = (anchor.y() - o.y()) / old
        self.set_zoom(new)
        if area:
            no = self._origin()
            h, v = area.horizontalScrollBar(), area.verticalScrollBar()
            h.setValue(round(img_x * new + no.x() - (anchor.x() - h.value())))
            v.setValue(round(img_y * new + no.y() - (anchor.y() - v.value())))
        self.zoom_changed.emit(new)
        e.accept()

    def _scroll_area(self):
        """Le QScrollArea qui nous contient, pour le pan et le zoom."""
        from PyQt6.QtWidgets import QScrollArea as _QSA
        w = self.parentWidget()
        while w is not None and not isinstance(w, _QSA):
            w = w.parentWidget()
        return w

    def select_index(self, idx: int):
        """Sélectionne une case par son index."""
        if not self._font or not (0 <= idx < len(self._font.glyphs)):
            return
        self._index = idx
        self.update()
        self.glyph_selected.emit(self._font.glyphs[idx])

    # ── Saisie clavier ────────────────────────────────────────────

    def keyPressEvent(self, e):
        """Flèches = navigation, caractère imprimable = assignation."""
        if e.key() == Qt.Key.Key_Escape and self._picking:
            self.cancel_pick()
            return
        if not self._font or not self._font.glyphs:
            return super().keyPressEvent(e)
        n = len(self._font.glyphs)
        key = e.key()

        if key in (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down):
            cols = self._cols_per_row()
            step = {Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1,
                    Qt.Key.Key_Down: cols, Qt.Key.Key_Up: -cols}[key]
            self.select_index(max(0, min((self._index if self._index >= 0 else 0) + step, n - 1)))
            return

        text = e.text()
        # Remplace le caractère de la case et avance : c'est ce qui rend le
        # remappage d'une planche entière tenable au clavier.
        if text and text.isprintable() and self._index >= 0:
            g = self._font.glyphs[self._index]
            if text != g.char:
                self.glyph_edited.emit(g, g.char, text)
            if self._index + 1 < n:
                self.select_index(self._index + 1)
            else:
                self.update()
            return
        super().keyPressEvent(e)

    def _cols_per_row(self) -> int:
        """Pas de navigation vertical, donné par la grille de la planche."""
        return self._font.grid_cols() if self._font else 1
