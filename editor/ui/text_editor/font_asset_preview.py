"""Aperçu comparatif fondé sur les ``RasterGlyph`` du pipeline.

La sortie GBA n'est plus composée à la main : elle appelle le même pont de
build (``codegen.font_build.build_font_asset``) et le même calcul de cellule
(``core.font_rasterizer.raster_glyph_cell``) que l'encodeur réel. C'est ce qui
garantit que la grille dessinée est la vraie grille de tuiles — un débordement
visible ici est un débordement rogné en ROM, jamais une approximation.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QTextEdit, QSpinBox, QFrame)
from PyQt6.QtGui import QFont, QImage, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect

from codegen.font_build import build_font_asset
from codegen.font_emit import glyph_tiles_w, glyph_advance_px, font_line_px
from core.font_rasterizer import (FontRasterizerError, FontRasterizerUnavailable,
                                  display_coverage, raster_glyph_cell)
from ui.common.theme import C, T, QSS
from ui.common.labels import label


_SAMPLE = "AaBb 0123!?\nInterligne"


class _RasterComparisonCanvas(QWidget):
    """Deux rendus synchronisés : zoom et panoramique communs.

    Le canevas est unique pour empêcher les deux moitiés de se décaler l'une
    par rapport à l'autre pendant une comparaison. Chaque côté est une boîte
    à part entière (encart de titre, fond et contour propres) pour que la
    couverture source et la sortie GBA ne se lisent jamais comme un seul bloc.
    """

    MIN_ZOOM, MAX_ZOOM = 1, 16
    _GAP, _HEADER_H, _BORDER_W = 16, 24, 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coverage = self._output = QImage()
        self._cells: list[QRect] = []
        self._coverage_title = self._output_title = ""
        self._zoom = 5
        self._pan = QPoint(0, 0)
        self._pan_last = None
        self.setMinimumHeight(100)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_titles(self, coverage_title: str, output_title: str):
        self._coverage_title, self._output_title = coverage_title, output_title
        self.update()

    def set_images(self, coverage: QImage, output: QImage):
        self._coverage, self._output = coverage, output
        self.update()

    def set_cells(self, cells: list[QRect]):
        """Rectangles des cellules GBA réelles (repère de l'image de sortie),
        un par glyphe placé — c'est la grille qui remplace l'ancien quadrillage
        décoratif, tuile par tuile réservée plutôt qu'uniforme."""
        self._cells = cells
        self.update()

    def clear(self):
        self._coverage = self._output = QImage()
        self._cells = []
        self.update()

    def _box_rect(self, side: int) -> QRect:
        box_w = (self.width() - self._GAP) // 2
        x0 = 0 if side == 0 else box_w + self._GAP
        return QRect(x0, 0, box_w if side == 0 else self.width() - x0, self.height())

    def _content_rect(self, side: int) -> QRect:
        return self._box_rect(side).adjusted(self._BORDER_W, self._HEADER_H, -self._BORDER_W, -self._BORDER_W)

    def _image_rect(self, image: QImage, side: int, zoom=None) -> QRect:
        zoom = self._zoom if zoom is None else zoom
        content = self._content_rect(side)
        w, h = image.width() * zoom, image.height() * zoom
        return QRect(content.x() + (content.width() - w) // 2 + self._pan.x(),
                     content.y() + (content.height() - h) // 2 + self._pan.y(), w, h)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(C.BG_BASE))
        for side, image in enumerate((self._coverage, self._output)):
            self._draw_box(painter, side, image)
        painter.setPen(QColor(C.TEXT_MUTED))
        painter.setFont(QFont(T.MONO, T.XS))
        painter.drawText(self._box_rect(1).right() - 34, self.height() - 7, f"x{self._zoom}")

    def _draw_box(self, painter: QPainter, side: int, image: QImage):
        """Encart de titre + surface de rendu, sous un même contour : la
        sortie GBA est noire, avec la grille de tuiles RÉELLEMENT réservées ;
        la couverture source reste un fond gris neutre, sans grille — ce n'est
        pas encore une tuile, juste l'encre brute du rasterizer."""
        is_output = side == 1
        box = self._box_rect(side)
        header = QRect(box.x(), box.y(), box.width(), self._HEADER_H)
        painter.fillRect(header, QColor(C.BG_RAISED))
        painter.setPen(QColor(C.TEXT_HI)); painter.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        painter.drawText(header, Qt.AlignmentFlag.AlignCenter, self._output_title if is_output else self._coverage_title)

        content = self._content_rect(side)
        painter.save()
        painter.setClipRect(content)
        painter.fillRect(content, QColor(C.BG_DEEP if is_output else C.BG_HOVER))
        if not image.isNull():
            rect = self._image_rect(image, side)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(rect, image)
            if is_output:
                self._draw_cells(painter, rect)
        painter.restore()

        painter.setPen(QPen(QColor(C.BORDER_MID), self._BORDER_W))
        half = self._BORDER_W // 2
        painter.drawRect(box.adjusted(half, half, -half, -half))

    def _draw_cells(self, painter: QPainter, image_rect: QRect):
        """Un rectangle par glyphe placé, à l'échelle et à la position EXACTES
        de sa cellule GBA (``self._cells``, en pixels image) : la vraie grille
        de tuiles, pas un quadrillage uniforme qui mentirait sur une police
        proportionnelle (l'avance d'un glyphe n'est alors pas multiple de 8)."""
        painter.setPen(QPen(QColor(C.TEXT_DIM), 1))
        z = self._zoom
        for cell in self._cells:
            painter.drawRect(QRect(image_rect.x() + round(cell.x() * z), image_rect.y() + round(cell.y() * z),
                                   round(cell.width() * z), round(cell.height() * z)))

    def wheelEvent(self, event):
        old = self._zoom
        new = max(self.MIN_ZOOM, min(self.MAX_ZOOM, old + (1 if event.angleDelta().y() > 0 else -1)))
        if new == old:
            event.accept(); return
        pos = event.position().toPoint()
        side = 0 if pos.x() < self.width() // 2 else 1
        image = self._coverage if side == 0 else self._output
        if not image.isNull():
            old_rect = self._image_rect(image, side, old)
            gx, gy = (pos.x() - old_rect.x()) / old, (pos.y() - old_rect.y()) / old
            self._zoom = new
            base = self._image_rect(image, side, new)
            self._pan += QPoint(round(pos.x() - base.x() - gx * new),
                                round(pos.y() - base.y() - gy * new))
        else:
            self._zoom = new
        self.update(); event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_last is not None and event.buttons() & Qt.MouseButton.MiddleButton:
            pos = event.position().toPoint()
            self._pan += pos - self._pan_last
            self._pan_last = pos
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None; self.unsetCursor(); event.accept(); return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-clic : retrouve instantanément la vue de comparaison."""
        self._zoom, self._pan = 5, QPoint(0, 0)
        self.update(); event.accept()


class FontAssetPreview(QWidget):
    """Compare la couverture et la sortie finale sur un texte libre."""

    field_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._asset = self._project = None
        self._blocking = False

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = QLabel(label("fontasset.preview_title")); header.setFixedHeight(28)
        header.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold)); header.setStyleSheet(QSS.title_panel)
        header.setContentsMargins(8, 0, 8, 0); root.addWidget(header)
        body = QWidget(); body.setStyleSheet(f"background:{C.BG_BASE};")
        lay = QVBoxLayout(body); lay.setContentsMargins(32, 16, 32, 18); lay.setSpacing(4)
        self._name = QLabel(""); self._name.setFont(QFont(T.MONO, T.LG, QFont.Weight.DemiBold)); self._name.setStyleSheet(f"color:{C.ACCENT};")
        lay.addWidget(self._name)
        lay.addSpacing(10)

        # Le libellé colle à son champ : c'est un groupe, pas deux lignes isolées.
        text_label = QLabel(label("fontasset.preview_sample_text")); text_label.setStyleSheet(QSS.label_field)
        lay.addWidget(text_label)
        text_row = QHBoxLayout(); text_row.setSpacing(0)
        self._text = QTextEdit(_SAMPLE); self._text.setAcceptRichText(False)
        self._text.setPlaceholderText(label("fontasset.preview_text_placeholder")); self._text.setToolTip(label("fontasset.preview_text_tip"))
        # Ferré à gauche : un champ d'essai n'a pas besoin de courir sur toute
        # la largeur du panneau, seulement d'être assez large pour l'échantillon.
        self._text.setFixedSize(420, 48); self._text.setFont(QFont(T.MONO, T.SM))
        self._text.setStyleSheet(f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI}; border:1px solid {C.BORDER_MID}; border-radius:4px; padding:4px;}} QTextEdit:focus{{border-color:{C.ACCENT};}}")
        text_row.addWidget(self._text); text_row.addStretch(1); lay.addLayout(text_row)
        lay.addSpacing(10)

        # La taille ne concerne que la sortie GBA (c'est elle qu'on rastérise) :
        # le réglage vit au-dessus de sa boîte, pas égaré en coin d'écran.
        size_row = QHBoxLayout(); size_row.setSpacing(0)
        size_row.addStretch(1)
        size_col = QHBoxLayout(); size_col.setSpacing(8); size_col.addStretch(1)
        size_label = QLabel(label("fontasset.preview_size")); size_label.setStyleSheet(QSS.label_field)
        size_col.addWidget(size_label)
        self._size = QSpinBox(); self._size.setRange(1, 128); self._size.setSuffix(" px"); self._size.setFont(QFont(T.MONO, T.SM)); self._size.setStyleSheet(QSS.spinbox)
        self._size.setToolTip(label("fontasset.preview_size_tip")); size_col.addWidget(self._size)
        # Une planche bitmap a une taille FIXE : le spinbox ne peut rien y changer,
        # donc l'éditer serait mentir. Un simple libellé informatif prend sa place.
        self._size_info = QLabel(""); self._size_info.setFont(QFont(T.MONO, T.SM)); self._size_info.setStyleSheet(f"color:{C.TEXT_NORM};")
        size_col.addWidget(self._size_info)
        size_row.addLayout(size_col, 1)
        lay.addLayout(size_row)

        # Canevas et pied forment un seul bloc « comparaison » : les titres
        # vivent maintenant dans l'encart de chaque boîte, pas au-dessus.
        self._canvas = _RasterComparisonCanvas(); self._canvas.setToolTip(label("fontasset.preview_canvas_tip"))
        self._canvas.set_titles(label("fontasset.preview_coverage"), label("fontasset.preview_output"))
        lay.addWidget(self._canvas, 1)
        footer = QFrame(); footer.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")
        footer_lay = QVBoxLayout(footer); footer_lay.setContentsMargins(8, 6, 8, 6); footer_lay.setSpacing(2)
        self._summary = QLabel(""); self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter); self._summary.setFont(QFont(T.MONO, T.SM)); self._summary.setStyleSheet(f"color:{C.TEXT_NORM}; border:none;"); footer_lay.addWidget(self._summary)
        self._status = QLabel(""); self._status.setAlignment(Qt.AlignmentFlag.AlignCenter); self._status.setWordWrap(True); self._status.setFont(QFont(T.UI, T.SM)); self._status.setStyleSheet(f"color:{C.TEXT_MUTED}; border:none;"); footer_lay.addWidget(self._status)
        lay.addWidget(footer)
        root.addWidget(body, 1)
        self._text.textChanged.connect(self._render); self._size.valueChanged.connect(self._size_changed)

    def load(self, asset, project):
        self._asset, self._project = asset, project
        self._blocking = True; self._name.setText(asset.name if asset else ""); self._size.setValue(asset.pixel_height if asset else 8); self._blocking = False
        self._canvas.clear()
        self._update_size_mode()
        if asset is None:
            self._summary.setText(""); self._set_status(""); return
        sources = " → ".join(asset.source_names()) or label("common.none_dash")
        self._summary.setText(label("fontasset.preview_summary", pixel_height=asset.pixel_height, line_height=asset.line_height, hinting=asset.hinting, pixel_fit=asset.pixel_fit, raster_mode=asset.raster_mode, sources=sources))
        self._render()

    def _bitmap_source(self):
        """La ``Font`` bitmap (png/fnt) de la source primaire regular, ou
        ``None`` si l'asset n'en a pas — c'est le cas qui rend le spinbox
        éditable inopérant : une planche n'a qu'une taille, la sienne."""
        if self._asset is None or self._project is None:
            return None
        name = self._asset.primary_source_name("regular")
        source = self._project.fonts.get(name) if name else None
        return source if source is not None and source.source_format in ("png", "fnt") else None

    def _update_size_mode(self):
        source = self._bitmap_source()
        self._size.setVisible(source is None)
        self._size_info.setVisible(source is not None)
        if source is not None:
            self._size_info.setText(label("fontasset.preview_size_fixed", pixel_height=source.cell_h))
            self._size_info.setToolTip(label("fontasset.preview_size_fixed_tip"))

    def _set_status(self, text: str):
        # Silence par défaut : le rendu se suffit à lui-même, seuls une perte
        # d'encre ou une erreur méritent un message.
        self._status.setText(text); self._status.setVisible(bool(text))

    def refresh(self):
        if self._asset is not None:
            self.load(self._asset, self._project)

    def _size_changed(self, value):
        if not self._blocking and self._asset is not None and value != self._asset.pixel_height:
            self.field_changed.emit("pixel_height", value)

    def _render(self):
        if self._asset is None or self._project is None:
            return
        text = self._text.toPlainText().replace("\r", "")
        try:
            # MÊME pont que le build : un texte qui rastérise ici rastérisera
            # pareil en ROM, tuile pour tuile, bearing pour bearing.
            font = build_font_asset(self._project, self._asset, chars={ch for ch in text if ch != "\n"})
        except FontRasterizerUnavailable as exc:
            self._canvas.clear(); self._set_status(label("fontasset.preview_unavailable", detail=str(exc))); return
        except FontRasterizerError as exc:
            self._canvas.clear(); self._set_status(label("fontasset.preview_error", detail=str(exc))); return

        glyph_by_char = {g.char: g for g in font.glyphs}
        rasters = font.raster_glyphs
        sequence, missing = [], []
        for ch in text:
            if ch == "\n":
                sequence.append(None); continue
            g = glyph_by_char.get(ch)
            raster = rasters.get(ch) if g is not None else None
            (sequence.append((g, raster)) if raster is not None else missing.append(ch))

        coverage_img, output_img, cells, kept = self._compose(font, sequence)
        self._canvas.set_images(coverage_img, output_img)
        self._canvas.set_cells(cells)
        self._set_status(self._quality_message(missing, kept))

    def _compose(self, font, sequence):
        """Pose chaque glyphe dans sa cellule GBA réelle (même ancrage, même
        rognage que ``codegen.font_emit``), puis rejoue le même rasterizer
        SANS le rognage pour la couverture source — les deux images partagent
        donc le même repère (x du pinceau, ligne de base), seul le contenu
        diffère de ce que le matériel garde ou perd."""
        # `cell_h` est le rognage RÉEL par glyphe (toujours arrondi à la tuile,
        # même chemin composé) ; `line_px` est le pas d'une ligne à l'autre,
        # déjà résolu par le build — les deux peuvent diverger pour une police
        # proportionnelle, et alors les cellules de deux lignes se chevauchent
        # réellement en ROM. Ne pas les confondre en une seule valeur.
        anchor_h = max(1, int(font.line_height))
        cell_h = max(1, (anchor_h + 7) // 8) * 8
        line_px = font_line_px(font)
        mode, threshold, pattern = self._asset.raster_mode, self._asset.coverage_threshold, self._asset.dither_pattern

        pen_x, row, placed = 2, 0, []
        max_ink_x, n_rows = 2, 1
        for item in sequence:
            if item is None:
                row += 1; pen_x = 2; n_rows = max(n_rows, row + 1); continue
            g, raster = item
            gtx = glyph_tiles_w(g)
            placed.append((raster, pen_x, row, gtx))
            max_ink_x = max(max_ink_x, pen_x + gtx * 8)
            pen_x += glyph_advance_px(g, font)
            max_ink_x = max(max_ink_x, pen_x)

        out_w = max_ink_x + 2
        out_h = max(1, (n_rows - 1) * line_px + cell_h)
        output = QImage(out_w, out_h, QImage.Format.Format_ARGB32); output.fill(Qt.GlobalColor.transparent)
        ink = QColor(C.TEXT_HI)
        cells, cov_placements = [], []
        raw_ink = final_ink = 0

        for raster, pen_x, row_i, gtx in placed:
            row_top, cell_w = row_i * line_px, gtx * 8
            cells.append(QRect(pen_x, row_top, cell_w, cell_h))
            coverage, _ = raster_glyph_cell(raster, cell_w, cell_h, raster_mode=mode,
                                            threshold=threshold, dither_pattern=pattern,
                                            anchor_h=anchor_h)
            for dy in range(cell_h):
                for dx in range(cell_w):
                    if coverage[dy][dx]:
                        final_ink += 1
                        color = QColor(ink); color.setAlpha(coverage[dy][dx])
                        output.setPixelColor(pen_x + dx, row_top + dy, color)
            raw_ink += sum(1 for value in raster.coverage if value)
            base_y = row_top + max(0, anchor_h - raster.bearing_y)
            cov_placements.append((raster, pen_x + raster.bearing_x, base_y))

        cov_min_y = min([0] + [y for _, _, y in cov_placements])
        cov_max_y = max([cell_h] + [y + raster.height for raster, _, y in cov_placements])
        coverage_img = QImage(out_w, max(1, cov_max_y - cov_min_y + 2), QImage.Format.Format_ARGB32)
        coverage_img.fill(Qt.GlobalColor.transparent)
        for raster, x, y in cov_placements:
            for gy in range(raster.height):
                for gx in range(raster.width):
                    alpha = display_coverage(raster.coverage_at(gx, gy), gx, gy, raster_mode="coverage",
                                             threshold=threshold, dither_pattern=pattern)
                    if alpha:
                        color = QColor(ink); color.setAlpha(alpha)
                        coverage_img.setPixelColor(x + gx, y - cov_min_y + gy, color)

        kept = round(100 * final_ink / raw_ink) if raw_ink else 100
        return coverage_img, output, cells, kept

    def _quality_message(self, missing: list[str], kept: int) -> str:
        if missing:
            return label("fontasset.preview_missing_chars", chars=" ".join(sorted(set(missing))))
        if self._asset.raster_mode != "coverage" and kept < 65:
            return label("fontasset.preview_ink_loss", kept=kept, threshold=self._asset.coverage_threshold)
        return ""
