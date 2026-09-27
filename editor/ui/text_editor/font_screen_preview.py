"""
ui/text_editor/font_screen_preview.py — aperçu écran GBA d'un texte, rendu avec
les vrais glyphes de la police.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QSizePolicy, QMenu, QApplication
from PyQt6.QtGui import QFont, QImage, QPainter, QPen, QColor, QKeySequence
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal

from core.engine_emulation.text_layout import layout_marked_text, layout_projection_text
from codegen.font_build import build_font_asset
from core.font_rasterizer import FontRasterizerError, display_coverage
from ui.common.theme import C, T, QSS
from ui.common.labels import label
from ui.common.backdrop_button import BackdropButton


class FontScreenPreview(QWidget):
    """Écran GBA simulé, dessiné avec les VRAIS glyphes de la police : ce qui
    s'affiche ici est ce que la console affichera.

    À ne pas confondre avec `ScreenTextPreview` (ui/common), simple jauge de
    longueur à chasse fixe de 8 px, qui se trompe dès qu'une police 16×16 ou une
    ligature entre en jeu.

    Le widget est son propre viewport : molette = zoom, clic-central = pan,
    double-clic = retour à l'ajustement automatique — mêmes gestes que la
    planche de glyphes et que le canvas du Scene Manager.
    """

    GBA_W, GBA_H = 240, 160
    TILE = 8
    MIN_ZOOM, MAX_ZOOM = 1, 8
    FIT_MAX = 3          # l'ajustement automatique ne dépasse pas ×3
    MARGIN = 24          # px d'écran qui restent forcément atteignables au pan

    edited = pyqtSignal(str)
    committed = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._text = ""                 # source balisée, jamais le texte aplati
        self._values: dict = {}
        self._render_fonts: dict[str, object] = {}
        self._render_text = None
        self._render_error = ""
        self._glyph_images: dict[tuple[str, str], QImage] = {}
        self._show_markup = False
        self._editable = False
        self._baseline = ""
        self._anchor = self._caret = 0
        self._placed_source: list[tuple[int, int, int, int, int, int]] = []
        self._selecting = False
        self._undo: list[tuple[str, int, int]] = []
        self._redo: list[tuple[str, int, int]] = []
        # Zoom None = ajusté au volet ; un chiffre = choisi à la molette, et il
        # ne bouge plus quand on redimensionne.
        self._zoom: Optional[int] = None
        self._pan = QPoint(0, 0)
        self._pan_last: Optional[QPoint] = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Fond d'épreuve : posé DANS l'aperçu, en bas à gauche — il commente ce
        # qu'on regarde, pas la table des textes.
        self._btn_bg = BackdropButton(self)
        self._btn_bg.changed.connect(self.update)

    def set_font_asset(self, font, project):
        """Choisit une recette de police, comme le font les TextBox.

        Une FontAsset peut provenir d'une planche bitmap ou d'une fonte
        vectorielle : il n'y a donc volontairement aucune planche PNG à
        charger ici. Le même sous-ensemble temporaire que le build est produit
        à la demande par :func:`build_font_asset`.
        """
        self._font, self._project = font, project
        self._invalidate_render()
        self.update()

    def set_text(self, text: str, values: Optional[dict] = None):
        self._text = text or ""
        self._values = dict(values or {})
        self._invalidate_render()
        self.update()

    # ── Contrat d'édition partagé avec MarkupToolbar ──────────────

    def set_editable(self, editable: bool):
        self._editable = editable
        self.setCursor(Qt.CursorShape.IBeamCursor if editable else Qt.CursorShape.ArrowCursor)

    def set_markup_visible(self, visible: bool):
        self._show_markup = bool(visible)
        self.update()

    def markup_visible(self) -> bool:
        return self._show_markup

    def set_text_silent(self, text: str):
        self._baseline = self._text = text or ""
        self._anchor = self._caret = min(self._caret, len(self._text))
        self._undo.clear()
        self._redo.clear()
        self._invalidate_render()
        self.update()

    def source(self) -> str:
        return self._text

    def selection(self) -> tuple[int, int]:
        return min(self._anchor, self._caret), max(self._anchor, self._caret)

    def replace_source(self, edits: list[tuple[int, int, str]], select: tuple[int, int]):
        before = (self._text, self._anchor, self._caret)
        source = self._text
        for a, b, text in sorted(edits, reverse=True):
            source = source[:a] + text + source[b:]
        if source == self._text:
            return
        self._undo.append(before)
        self._redo.clear()
        self._text = source
        self._anchor = select[0]
        self._caret = select[0] + select[1]
        self._invalidate_render()
        self.edited.emit(source)
        self.update()

    def _restore_history(self, undo: bool):
        source = self._undo if undo else self._redo
        other = self._redo if undo else self._undo
        if not source:
            return
        other.append((self._text, self._anchor, self._caret))
        self._text, self._anchor, self._caret = source.pop()
        self._invalidate_render()
        self.edited.emit(self._text)
        self.update()

    def commit(self):
        if self._text != self._baseline:
            before, self._baseline = self._baseline, self._text
            self.committed.emit(before, self._text)

    def _invalidate_render(self):
        self._render_fonts = {}
        self._render_text = None
        self._render_error = ""
        self._glyph_images = {}

    def _fonts_for_text(self):
        """Matérialise les recettes présentes dans le texte balisé.

        C'est le pont utilisé par le build ; le preview ne doit surtout pas
        réinventer une lecture directe des sources de la FontAsset.
        """
        cache_key = (self._text, tuple(sorted(self._values.items())))
        if self._render_text == cache_key:
            return self._render_fonts
        self._render_text, self._render_fonts, self._render_error = cache_key, {}, ""
        self._glyph_images = {}
        if not self._font or not self._project:
            return None
        try:
            from core.text_markup import display_text
            from codegen.font_emit import text_markup_font_names
            shown = display_text(self._text, self._values)
            chars = {char for char in shown if char not in "\r\n"} or {" "}
            assets = {getattr(self._font, "name", ""): self._font}
            for name in text_markup_font_names(self._text):
                asset = getattr(self._project, "font_assets", ()).get(name)
                if asset is not None:
                    assets[name] = asset
            self._render_fonts = {
                name: build_font_asset(self._project, asset, chars)
                for name, asset in assets.items()
            }
        except FontRasterizerError as exc:
            self._render_error = str(exc)
        return self._render_fonts

    def _glyph_image(self, font, glyph) -> QImage:
        """Cellule GBA du glyphe, avec le même dépôt que l'encodeur ROM."""
        key = (getattr(font, "name", ""), glyph.char)
        cached = self._glyph_images.get(key)
        if cached is not None:
            return cached
        image = QImage(max(1, glyph.w), max(1, glyph.h), QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.transparent)
        raster = font.raster_glyphs.get(glyph.char)
        asset = (self._font if getattr(font, "name", "") == getattr(self._font, "name", "")
                 else getattr(self._project, "font_assets", ()).get(getattr(font, "name", "")))
        if asset is None:
            return image
        if raster is not None:
            base_y = max(0, glyph.h - raster.bearing_y)
            for y in range(raster.height):
                for x in range(raster.width):
                    dx, dy = raster.bearing_x + x, base_y + y
                    if not (0 <= dx < image.width() and 0 <= dy < image.height()):
                        continue
                    coverage = display_coverage(
                        raster.coverage_at(x, y), dx, dy,
                        raster_mode=asset.raster_mode,
                        threshold=asset.coverage_threshold,
                        dither_pattern=asset.dither_pattern,
                    )
                    if coverage:
                        image.setPixelColor(dx, dy, QColor(255, 255, 255, coverage))
        self._glyph_images[key] = image
        return image

    # ── Fond d'épreuve ────────────────────────────────────────────

    @staticmethod
    def _readable_on(bg: QColor) -> QColor:
        """Encre lisible sur `bg` — les messages de l'aperçu doivent survivre
        au fond blanc comme au fond noir."""
        return QColor("#1a1a22") if bg.lightness() > 140 else QColor(C.TEXT_DIM)

    # ── Géométrie ─────────────────────────────────────────────────

    def _fit_scale(self) -> int:
        """Échelle ENTIÈRE qui tient dans le volet : le pixel art ne supporte
        pas l'interpolation."""
        if not self.width() or not self.height():
            return 1
        return max(1, min(self.width() // self.GBA_W,
                          self.height() // self.GBA_H, self.FIT_MAX))

    def _scale(self) -> int:
        return self._zoom if self._zoom is not None else self._fit_scale()

    def _origin(self) -> QPoint:
        """Coin haut-gauche de l'écran simulé : centré dans le volet, décalé du
        pan. Centré parce que la largeur du volet ne tombe jamais juste sur un
        multiple de 240 — collé à gauche, ça se lirait comme un désalignement."""
        s = self._scale()
        return QPoint((self.width() - self.GBA_W * s) // 2 + self._pan.x(),
                      (self.height() - self.GBA_H * s) // 2 + self._pan.y())

    def _clamp_pan(self):
        """Garde toujours un morceau d'écran dans le volet — panné trop loin, il
        serait introuvable sans barres de défilement."""
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        cx, cy = (self.width() - w) // 2, (self.height() - h) // 2
        m = self.MARGIN
        self._pan.setX(max(m - w - cx, min(self._pan.x(), self.width() - m - cx)))
        self._pan.setY(max(m - h - cy, min(self._pan.y(), self.height() - m - cy)))

    def reset_view(self):
        """Retour à l'ajustement automatique, écran recentré."""
        self._zoom = None
        self._pan = QPoint(0, 0)
        self.update()

    def resizeEvent(self, e):
        self._btn_bg.move(8, self.height() - self._btn_bg.height() - 8)
        self._clamp_pan()
        super().resizeEvent(e)

    # ── Zoom / pan ────────────────────────────────────────────────

    def wheelEvent(self, e):
        """Molette = zoom, en gardant le point visé sous le curseur (sinon le
        mot qu'on lit fuit hors du volet)."""
        old = self._scale()
        new = max(self.MIN_ZOOM,
                  min(old + (1 if e.angleDelta().y() > 0 else -1), self.MAX_ZOOM))
        if new == old:
            e.accept()
            return
        # Point visé en coordonnées ÉCRAN GBA avant le zoom : le centrage
        # dépend de l'échelle, il doit sortir du calcul.
        o, pos = self._origin(), e.position()
        gx, gy = (pos.x() - o.x()) / old, (pos.y() - o.y()) / old
        self._zoom = new
        cx = (self.width() - self.GBA_W * new) // 2
        cy = (self.height() - self.GBA_H * new) // 2
        self._pan = QPoint(round(pos.x() - gx * new) - cx,
                           round(pos.y() - gy * new) - cy)
        self._clamp_pan()
        self.update()
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            # Pan au clic-central — même geste que le canvas du Scene Manager.
            self._pan_last = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        if self._editable and e.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._caret = self._source_at(e.position().toPoint())
            if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._anchor = self._caret
            self._selecting = True
            self.update()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan_last is not None and (e.buttons() & Qt.MouseButton.MiddleButton):
            pos = e.position().toPoint()
            self._pan += pos - self._pan_last
            self._pan_last = pos
            self._clamp_pan()
            self.update()
            e.accept()
            return
        if self._editable and self._selecting and (e.buttons() & Qt.MouseButton.LeftButton):
            self._caret = self._source_at(e.position().toPoint())
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        """Double-clic = vue remise à plat, pour sortir d'un zoom perdu sans
        compter les crans de molette."""
        self.reset_view()
        e.accept()

    def keyPressEvent(self, e):
        if not self._editable:
            super().keyPressEvent(e)
            return
        a, b = self.selection()
        key = e.key()
        if e.matches(QKeySequence.StandardKey.SelectAll):
            self._anchor, self._caret = 0, len(self._text)
            self.update(); e.accept(); return
        if e.matches(QKeySequence.StandardKey.Undo):
            self._restore_history(True); e.accept(); return
        if e.matches(QKeySequence.StandardKey.Redo):
            self._restore_history(False); e.accept(); return
        if e.matches(QKeySequence.StandardKey.Copy):
            QApplication.clipboard().setText(self._text[a:b])
            e.accept(); return
        if e.matches(QKeySequence.StandardKey.Cut):
            QApplication.clipboard().setText(self._text[a:b])
            if a != b:
                self.replace_source([(a, b, "")], (a, 0))
            e.accept(); return
        if e.matches(QKeySequence.StandardKey.Paste):
            self.replace_source([(a, b, QApplication.clipboard().text())],
                                (a + len(QApplication.clipboard().text()), 0))
            e.accept(); return
        from core.text_markup import project
        projection = project(self._text, self._values, show_markup=self._show_markup)
        if key == Qt.Key.Key_Left:
            visible = projection.source_to_visible(self._caret)
            self._caret = projection.visible_to_source(max(0, visible - 1))
            if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier): self._anchor = self._caret
        elif key == Qt.Key.Key_Right:
            visible = projection.source_to_visible(self._caret, right=True)
            self._caret = projection.visible_to_source(min(len(projection.text), visible + 1), right=True)
            if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier): self._anchor = self._caret
        elif key == Qt.Key.Key_Backspace:
            if a != b: self.replace_source([(a, b, "")], (a, 0))
            elif a: self.replace_source([(a - 1, a, "")], (a - 1, 0))
        elif key == Qt.Key.Key_Delete:
            if a != b: self.replace_source([(a, b, "")], (a, 0))
            elif a < len(self._text): self.replace_source([(a, a + 1, "")], (a, 0))
        elif e.text() and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.replace_source([(a, b, e.text())], (a + len(e.text()), 0))
        else:
            super().keyPressEvent(e)
            return
        self.update()
        e.accept()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.commit()

    def contextMenuEvent(self, e):
        if not self._editable:
            super().contextMenuEvent(e)
            return
        from core.text_markup import removable_markup_edits
        a, b = self.selection()
        edits = removable_markup_edits(self._text, a, b)
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        remove = menu.addAction(label("fsprev.remove_markup"))
        remove.setEnabled(bool(edits))
        if edits:
            remove.triggered.connect(lambda: self._remove_markup(edits, a, b))
        menu.exec(e.globalPos())
        e.accept()

    def _remove_markup(self, edits, a: int, b: int):
        def after_removals(position: int) -> int:
            mapped = position
            # Le calcul se fait dans le même ordre que les suppressions : une
            # borne sélectionnée SUR une balise rejoint son bord, une borne
            # après elle est décalée de sa longueur.
            for start, end, _text in sorted(edits):
                if mapped >= end:
                    mapped -= end - start
                elif mapped > start:
                    mapped = start
            return mapped
        new_a, new_b = after_removals(a), after_removals(b)
        self.replace_source(edits, (new_a, max(0, new_b - new_a)))

    def _source_at(self, point: QPoint) -> int:
        """Borne source la plus proche du clic, en coordonnées widget."""
        if not self._placed_source:
            return len(self._text)
        scale, origin = self._scale(), self._origin()
        gx, gy = (point.x() - origin.x()) / scale, (point.y() - origin.y()) / scale
        best = min(self._placed_source,
                   key=lambda item: abs(gx - item[2]) + abs(gy - item[3]) * self.GBA_W)
        a, b, x, _y, advance, _height = best
        return b if gx >= x + advance / 2 else a

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        bg = self._btn_bg.color()
        ink = self._readable_on(bg)

        p.fillRect(self.rect(), QColor(C.BG_DEEP))
        o = self._origin()
        p.translate(o)
        p.fillRect(QRect(0, 0, w, h), bg)
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(QRect(0, 0, w - 1, h - 1))

        fonts = self._fonts_for_text()
        if not self._font:
            p.setPen(ink)
            p.setFont(QFont(T.UI, T.XS))
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       label("fsprev.choose_font"))
            return
        if not fonts:
            p.setPen(ink)
            p.setFont(QFont(T.UI, T.XS))
            p.drawText(QRect(12, 12, w - 24, h - 24), Qt.AlignmentFlag.AlignCenter,
                       self._render_error or label("fsprev.choose_font"))
            return

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        base = fonts.get(getattr(self._font, "name", ""))
        if base is None:
            return
        self._placed_source = []
        if self._show_markup:
            from core.text_markup import project
            projected = project(self._text, self._values, show_markup=True)
            placed, over = layout_projection_text(base, projected, fonts,
                                                   self.GBA_W, self.GBA_H)
            draw_placed = [(f, g, x, y) for f, g, x, y, _a, _b in placed]
            for _f, g, x, y, a, b in placed:
                from codegen.font_emit import glyph_advance_px
                self._placed_source.append((a, b, x, y, glyph_advance_px(g, _f), g.h))
        else:
            placed, over = layout_marked_text(base, self._text, fonts, self._values,
                                              self.GBA_W, self.GBA_H)
            draw_placed = placed
            # Le rendu joueur ne porte pas encore les bornes source ; la
            # projection cachée les rétablit pour le clic et le caret.
            from core.text_markup import project
            hit_projection = project(self._text, self._values)
            hit_placed, _ = layout_projection_text(base, hit_projection, fonts,
                                                    self.GBA_W, self.GBA_H)
            from codegen.font_emit import glyph_advance_px
            self._placed_source = [(a, b, x, y, glyph_advance_px(g, f), g.h)
                                   for f, g, x, y, a, b in hit_placed]
        sel_a, sel_b = self.selection()
        if sel_a != sel_b:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.ACCENT).darker(170))
            for a, b, px, py, advance, glyph_h in self._placed_source:
                if a < sel_b and b > sel_a:
                    p.drawRect(QRect(px * s, py * s, max(1, advance * s),
                                     max(1, glyph_h * s)))
        for glyph_font, g, px, py in draw_placed:
            image = self._glyph_image(glyph_font, g)
            p.drawImage(QRect(px * s, py * s, image.width() * s, image.height() * s), image)

        if self._editable and self.hasFocus():
            caret = next((item for item in self._placed_source if item[0] >= self._caret), None)
            if caret is None and self._placed_source:
                a, b, px, py, adv, glyph_h = self._placed_source[-1]
                px += adv
            elif caret:
                _a, _b, px, py, _adv, glyph_h = caret
            else:
                px = py = 0
                glyph_h = 8
            p.setPen(QPen(QColor(C.ACCENT), max(1, s)))
            p.drawLine(px * s, py * s, px * s, (py + glyph_h) * s)

        # Facteur affiché dans le VOLET, pas dans l'écran : c'est une donnée de
        # l'éditeur, elle n'a rien à faire sur la surface simulée.
        p.resetTransform()
        p.setPen(QColor(C.TEXT_MUTED))
        p.setFont(QFont(T.MONO, T.XS))
        p.drawText(QRect(0, self.height() - 20, self.width() - 8, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"×{s}" + ("" if self._zoom is None else label("fsprev.dbl_fit")))
        if over:
            p.setPen(QColor(C.ACCENT_YLW))
            p.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            p.drawText(QRect(8, self.height() - 20, self.width() - 16, 14),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       label("fsprev.overflows"))
