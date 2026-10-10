"""
ui/sprite_editor/sprite_canvas.py — le sprite canvas : composition de la frame courante,
peinte tuile par tuile (édition d'une AnimState/StateDirection), avec sa barre d'outils
flottante.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QFrame
from PyQt6.QtGui import QFont, QColor, QPixmap, QImage, QPainter, QPen, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRect, QRectF, QSize

from ui.common.theme import C, T, tint
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.icons import get as _ico
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.shortcut_hints import ShortcutHints
from ui.sprite_editor.sprite_canvas_hints import sprite_canvas_hints
from ui.common.canvas_backdrop import draw_grid, draw_grid_halo
from core.models.sprite import AnimFrame, SpriteAsset, TilePlacement
from core.history import get_history, PaintFrameCmd
from core.sprite_compose import compose_frame_image
from core.keybindings import get_keybindings

HINTS_CLEARANCE = 140  # marge droite des coordonnées : laisse la pastille des raccourcis


class SpriteCanvas(QWidget):
    """
    Zone de composition — grille de tuiles 8×8.
    Clic gauche = peindre (brosse active) ou, sans brosse, tracer un
    rectangle pour ramasser les tuiles posées (un simple clic en ramasse
    une seule) ; clic gauche hors de l'image = vider la brosse ; clic droit = effacer +
    reset sélection picker. Molette = zoom, molette centrale glissée = pan.
    Shift+X / Shift+Y = flip horizontal/vertical de la brosse active.
    """

    DEFAULT_ZOOM = 10    # zoom à l'ouverture et à chaque nouveau sprite (Fit = 0)

    frame_painted      = pyqtSignal()
    selection_reset    = pyqtSignal()   # demande reset de la sélection dans le picker
    hover_changed       = pyqtSignal(object)  # (col, row) survolé, ou None
    brush_picked_up     = pyqtSignal(int)     # nb de tuiles ramassées depuis le canvas
    mode_changed        = pyqtSignal()        # brosse posée/retirée, lecture seule basculée

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sprite:     Optional[SpriteAsset] = None
        self._abs_path:   Optional[Path]        = None
        self._src_pixmap: Optional[QPixmap]     = None
        self._frame:      Optional[AnimFrame]   = None
        self._tile_w = self._tile_h = 1
        self._show_grid  = True
        # Teinte de preview (aperçu uniquement — banque choisie via le
        # dropdown palette de la barre d'outils, cf SpriteCenterPanel) :
        # liste de couleurs BGR555, ou None pour les pixels sources.
        self._tint_bank: Optional[list[int]] = None
        # Compression NON-DESTRUCTIVE du sprite courant (own_palette BGR555) —
        # source de vérité du rendu dérivé. [] = pas de compression (source brut).
        self._own_palette: list = []
        # Mode de preview : True = "indexé" (own_palette -> banque de preview,
        # rendu in-game), False = "png" (couleurs compressées de own_palette).
        # Défaut = PNG (couleurs propres du sprite, sans banque de preview).
        self._preview_indexed: bool = False
        # (rel_c, rel_r, src_col, src_row, flip_h, flip_v)
        self._brush: list[tuple[int, int, int, int, bool, bool]] = []
        self._hover: Optional[tuple[int, int]]       = None
        self._persist_fn = None
        # Zoom/pan manuel
        self._zoom: int = self.DEFAULT_ZOOM   # 0 = auto-fit, >0 = manuel
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._mid_drag: Optional[tuple] = None   # (start_pos, start_pan_x, start_pan_y)
        # Sélection de tuiles déjà posées (active seulement sans brosse)
        self._select_start: Optional[tuple[int, int]] = None
        self._select_end:   Optional[tuple[int, int]] = None
        self._mouse_pos: Optional[QPointF] = None   # halo de fond, coord. widget
        # Lecture seule : direction miroir. L'édition (peindre/effacer/ramasser)
        # est bloquée ; l'image composée est retournée pour l'affichage (flip).
        self._read_only:  bool = False
        self._flip_disp:  tuple[bool, bool] = (False, False)
        # Image composée mise en cache : compose_frame_image relit le PNG source
        # à chaque appel (I/O disque + recadrage par tuile) — la recalculer à
        # chaque peinture serait déjà coûteux, mais à CHAQUE mouvement de souris
        # (halo de fond) ce serait imperceptible... jusqu'à ce que ça ne le soit
        # plus. Invalidée uniquement quand le contenu affiché change réellement.
        self._composed_pixmap: Optional[QPixmap] = None
        self._checker_cache: tuple[int, QPixmap] = (0, QPixmap())
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        # Focus au clic — les raccourcis Shift+X/Y sont portés par
        # SpriteCenterPanel (WidgetWithChildrenShortcut) pour marcher aussi
        # bien après un clic dans le tile picker qu'après un clic ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ── API ──────────────────────────────────────────────────────────

    def load_frame(self, sprite: Optional[SpriteAsset], abs_path: Optional[Path],
                   frame: Optional[AnimFrame]):
        prev_sprite = self._sprite
        prev_dims   = (self._tile_w, self._tile_h)
        self._sprite   = sprite
        self._abs_path = abs_path
        self._frame    = frame
        self._tile_w   = sprite.tile_w if sprite else 1
        self._tile_h   = sprite.tile_h if sprite else 1
        self._src_pixmap = QPixmap(str(abs_path)) if abs_path and abs_path.exists() else None
        # Ne réinitialiser le zoom/pan que si le sprite change (dimensions
        # potentiellement différentes) — sinon la navigation de frames ET la
        # lecture d'animation (load_frame appelé à chaque tick) remettraient
        # un zoom manuel à "fit" à chaque frame.
        if sprite is not prev_sprite or (self._tile_w, self._tile_h) != prev_dims:
            self._zoom = self.DEFAULT_ZOOM; self._pan_x = self._pan_y = 0
        self._recompose()
        self.update()

    def set_brush(self, tiles: list[tuple[int, int]]):
        if not tiles:
            self._brush = []
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            min_c = min(c for c, r in tiles)
            min_r = min(r for c, r in tiles)
            self._brush = [(c - min_c, r - min_r, c, r, False, False) for c, r in tiles]
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()
        self.mode_changed.emit()

    def hint_context(self) -> str:
        """Le geste que le canvas offre maintenant — clé de la table des
        raccourcis : brosse active, sélection de tuiles posées, ou lecture seule."""
        if self._read_only:
            return "readonly"
        return "brush" if self._brush else "pick"

    def flip_brush_x(self):
        """Miroir horizontal de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_h)."""
        if not self._brush:
            return
        max_c = max(rel_c for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(max_c - rel_c, rel_r, sc, sr, not fh, fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def flip_brush_y(self):
        """Miroir vertical de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_v)."""
        if not self._brush:
            return
        max_r = max(rel_r for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(rel_c, max_r - rel_r, sc, sr, fh, not fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def set_persist_fn(self, fn):
        self._persist_fn = fn

    def set_read_only(self, ro: bool):
        """Direction miroir : édition bloquée. On coupe aussi la brosse et le
        curseur repasse en flèche pour signaler qu'on ne peut rien poser."""
        self._read_only = ro
        if ro:
            self._brush = []
            self._select_start = self._select_end = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()
        self.mode_changed.emit()

    def set_display_flip(self, flip_h: bool, flip_v: bool):
        """Miroir d'affichage de l'image composée (preview d'une direction
        miroir) — n'affecte pas les tuiles stockées."""
        self._flip_disp = (flip_h, flip_v)
        self._recompose()
        self.update()

    def set_grid(self, on: bool):
        self._show_grid = on
        self.update()

    def set_tint(self, bank_colors: Optional[list[int]]):
        """Banque de preview appliquée à l'image composée via la vraie
        quantification (nearest, comme au build) — pas à la brosse fantôme,
        ni aux pixels sources. None = couleurs sources telles quelles."""
        self._tint_bank = bank_colors
        self._recompose()
        self.update()

    def set_preview_indexed(self, indexed: bool):
        """True = mode 'indexed' (own_palette recoloré par la banque de preview,
        rendu in-game), False = mode 'png' (couleurs compressées de own_palette)."""
        self._preview_indexed = indexed
        self._recompose()
        self.update()

    def set_own_palette(self, own_palette: Optional[list]):
        """Compression du sprite courant (own_palette BGR555). Le rendu dérive de
        ça : mode 'png' l'affiche telle quelle, mode 'indexed' la recolore via la
        banque de preview. [] / None = source brut (pas encore compressé)."""
        self._own_palette = list(own_palette or [])
        self._recompose()
        self.update()

    def _recompose(self):
        """Recalcule l'image composée (lit le PNG source, recadre tuile par
        tuile) et la met en cache — seul point d'appel de compose_frame_image,
        pour que le halo de fond (repeint à chaque mouvement de souris) ne le
        redéclenche jamais."""
        if not self._frame or not self._sprite:
            self._composed_pixmap = None
            return
        img = compose_frame_image(self._abs_path, self._frame,
                                  self._tile_w * 8, self._tile_h * 8)
        # Rendu dérivé du source + own_palette (jamais le PNG modifié) :
        #   mode 'png'     -> couleurs compressées (own_palette telle quelle)
        #   mode 'indexed' -> index de own_palette recolorés par la banque preview
        if self._own_palette:
            from core.models.gba_color import render_indexed, recolor_indexed
            p_img = render_indexed(img, self._own_palette)
            if self._preview_indexed and self._tint_bank:
                img = recolor_indexed(p_img, self._tint_bank)
            else:
                img = p_img.convert("RGBA")
        # Miroir d'affichage (direction miroir en lecture seule).
        if self._flip_disp[0] or self._flip_disp[1]:
            from PIL import Image as _Im
            if self._flip_disp[0]:
                img = img.transpose(_Im.FLIP_LEFT_RIGHT)
            if self._flip_disp[1]:
                img = img.transpose(_Im.FLIP_TOP_BOTTOM)
        if img.width > 0 and img.height > 0:
            data = bytes(img.tobytes("raw", "RGBA"))
            qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            self._composed_pixmap = QPixmap.fromImage(qi)
        else:
            self._composed_pixmap = None

    def _checker_pattern(self, cs: int) -> QPixmap:
        """Tuile 2×2 cases du damier de transparence, mise en cache par taille
        de case — un QBrush carrelé plutôt qu'un fillRect par case."""
        if self._checker_cache[0] != cs:
            pm = QPixmap(cs * 2, cs * 2)
            pm.fill(QColor(C.CHECKER_A))
            p = QPainter(pm)
            p.fillRect(cs, 0, cs, cs, QColor(C.CHECKER_B))
            p.fillRect(0, cs, cs, cs, QColor(C.CHECKER_B))
            p.end()
            self._checker_cache = (cs, pm)
        return self._checker_cache[1]

    # ── Géométrie ────────────────────────────────────────────────────

    def _auto_zoom(self) -> int:
        w, h = self.width(), self.height()
        pw, ph = max(self._tile_w * 8, 1), max(self._tile_h * 8, 1)
        return max(1, min(w // pw, h // ph))

    # ── Zoom (molette ou boutons du header) ─────────────────────────

    def _adjust_zoom(self, delta: int):
        cur = self._zoom if self._zoom > 0 else self._auto_zoom()
        self._zoom = max(1, min(24, cur + delta))
        if self._zoom == self._auto_zoom():
            self._zoom = 0; self._pan_x = self._pan_y = 0
        self.update()

    def zoom_in(self):
        self._adjust_zoom(1)

    def zoom_out(self):
        self._adjust_zoom(-1)

    def zoom_fit(self):
        self._zoom = 0
        self._pan_x = self._pan_y = 0
        self.update()

    def _geometry(self):
        zoom = self._zoom if self._zoom > 0 else self._auto_zoom()
        pw, ph = self._tile_w * 8, self._tile_h * 8
        dw, dh = pw * zoom, ph * zoom
        ox = (self.width()  - dw) // 2 + self._pan_x
        oy = (self.height() - dh) // 2 + self._pan_y
        return zoom, ox, oy, dw, dh

    def _cell_at(self, pos) -> Optional[tuple[int, int]]:
        zoom, ox, oy, dw, dh = self._geometry()
        x, y = pos.x() - ox, pos.y() - oy
        if x < 0 or y < 0 or x >= dw or y >= dh:
            return None
        return int(x // (8 * zoom)), int(y // (8 * zoom))

    # ── Événements souris ─────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = (e.pos(), self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._frame or not self._sprite or self._read_only:
            return
        cell = self._cell_at(e.position())
        if cell is None:
            # Clic gauche hors de l'image : on lâche la brosse.
            if e.button() == Qt.MouseButton.LeftButton and self._brush:
                self.set_brush([])
                self.selection_reset.emit()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._brush:
                self._do_paint(*cell)
            else:
                # Pas de brosse active : rectangle de sélection des tuiles déjà
                # posées, pour les ramasser (cf mouseReleaseEvent) ; sans
                # glisser, c'est la seule case cliquée.
                self._select_start = self._select_end = cell
                self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._do_erase(*cell)
            self.selection_reset.emit()

    def mouseMoveEvent(self, e):
        self._mouse_pos = e.position()
        self.update()   # halo de fond : suit le pointeur même sans changer de cellule
        if self._mid_drag and e.buttons() & Qt.MouseButton.MiddleButton:
            sp, spx, spy = self._mid_drag
            self._pan_x = spx + int(e.pos().x() - sp.x())
            self._pan_y = spy + int(e.pos().y() - sp.y())
            self.update(); return
        cell = self._cell_at(e.position())
        if cell != self._hover:
            self._hover = cell
            self.update()
            self.hover_changed.emit(cell)
        if self._read_only:
            return
        if e.buttons() & Qt.MouseButton.LeftButton and cell:
            if self._brush:
                self._do_paint(*cell)
            elif self._select_start is not None:
                self._select_end = cell
                self.update()
        elif e.buttons() & Qt.MouseButton.RightButton and cell:
            self._do_erase(*cell)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor if self._brush
                           else Qt.CursorShape.ArrowCursor)
        elif e.button() == Qt.MouseButton.LeftButton and self._select_start is not None:
            self._finish_canvas_selection()

    def leaveEvent(self, e):
        self._hover = None
        self._mouse_pos = None
        self.update()
        self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._adjust_zoom(1 if delta > 0 else -1)
        e.accept()

    # ── Peinture / effacement ─────────────────────────────────────────

    def _snapshot(self) -> list:
        return [TilePlacement(t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
                for t in self._frame.tiles]

    def _do_paint(self, col: int, row: int):
        if not self._frame or not self._brush:
            return
        old = self._snapshot()
        changed = False
        for rel_c, rel_r, sc, sr, fh, fv in self._brush:
            dc, dr = col + rel_c, row + rel_r
            if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                continue
            self._frame.tiles = [t for t in self._frame.tiles
                                 if not (t.dst_col == dc and t.dst_row == dr)]
            self._frame.tiles.append(TilePlacement(sc, sr, dc, dr, fh, fv))
            changed = True
        if changed:
            self._recompose()
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _do_erase(self, col: int, row: int):
        if not self._frame:
            return
        old = self._snapshot()
        self._frame.tiles = [t for t in self._frame.tiles
                             if not (t.dst_col == col and t.dst_row == row)]
        if len(self._frame.tiles) != len(old):
            self._recompose()
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _finish_canvas_selection(self):
        """
        Fin de la sélection rectangulaire (aucune brosse active) : ramasse
        les tuiles déjà posées sous le rectangle — les retire du canvas et
        les charge comme brosse, prêtes à être reposées ailleurs sans
        repasser par le tile picker.
        """
        c0, r0 = self._select_start
        c1, r1 = self._select_end
        self._select_start = self._select_end = None
        if not self._frame:
            self.update()
            return
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        picked = [t for t in self._frame.tiles
                  if cmin <= t.dst_col <= cmax and rmin <= t.dst_row <= rmax]
        if not picked:
            self.update()
            return
        old = self._snapshot()
        picked_pos = {(t.dst_col, t.dst_row) for t in picked}
        self._frame.tiles = [t for t in self._frame.tiles
                             if (t.dst_col, t.dst_row) not in picked_pos]
        self._recompose()
        self.frame_painted.emit()
        get_history().record(PaintFrameCmd(
            self._frame, old, self._snapshot(), self._persist_fn))

        self._brush = [(t.dst_col - cmin, t.dst_row - rmin, t.src_col, t.src_row,
                        t.flip_h, t.flip_v) for t in picked]
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.brush_picked_up.emit(len(self._brush))
        self.update()

    # ── Rendu ─────────────────────────────────────────────────────────

    def paintEvent(self, e):
        painter = QPainter(self)

        zoom, ox, oy, dw, dh = self._geometry()
        tile_px = 8 * zoom

        # Fond du canvas : même grille + halo au survol que le Font Editor,
        # au pas d'une tuile GBA (8 px, cadré sur l'origine de l'image).
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        draw_grid(painter, QRectF(self.rect()), tile_px, QPointF(ox, oy), tiled=True)
        draw_grid_halo(painter, QRectF(self.rect()), tile_px, self._mouse_pos, QPointF(ox, oy))

        if not self._frame or not self._sprite:
            painter.setPen(QColor(C.TEXT_MUTED))
            painter.setFont(QFont(T.UI, T.MD))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             label("sprframe.select_frame"))
            painter.end()
            return

        # Damier transparence — motif carrelé via QBrush (une seule passe),
        # plutôt qu'un fillRect par case : la boucle Python redevenait le coût
        # dominant du halo de fond, repeint à chaque mouvement de souris.
        cs = max(4, zoom * 2)
        painter.save()
        painter.setBrushOrigin(ox, oy)
        painter.fillRect(QRect(ox, oy, dw, dh), QBrush(self._checker_pattern(cs)))
        painter.restore()

        # Image composée — mise en cache par _recompose(), jamais recalculée ici
        # (sinon chaque mouvement de souris relirait le PNG source pour le halo).
        if self._composed_pixmap is not None:
            painter.drawPixmap(QRect(ox, oy, dw, dh), self._composed_pixmap)

        # Grille 8×8
        if self._show_grid:
            painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
            x = ox
            while x <= ox + dw:
                painter.drawLine(x, oy, x, oy + dh); x += tile_px
            y = oy
            while y <= oy + dh:
                painter.drawLine(ox, y, ox + dw, y); y += tile_px

        # Ghost preview de la brosse
        if self._hover and self._brush and self._src_pixmap:
            hc, hr = self._hover
            painter.setOpacity(0.55)
            for rel_c, rel_r, sc, sr, fh, fv in self._brush:
                dc, dr = hc + rel_c, hr + rel_r
                if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                    continue
                dest = QRect(ox + dc * tile_px, oy + dr * tile_px, tile_px, tile_px)
                src = QRect(sc * 8, sr * 8, 8, 8)
                if fh or fv:
                    painter.save()
                    cx, cy = dest.center().x(), dest.center().y()
                    painter.translate(cx, cy)
                    painter.scale(-1 if fh else 1, -1 if fv else 1)
                    painter.translate(-cx, -cy)
                    painter.drawPixmap(dest, self._src_pixmap, src)
                    painter.restore()
                else:
                    painter.drawPixmap(dest, self._src_pixmap, src)
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(C.ACCENT), 2))
            painter.drawRect(QRect(ox + hc * tile_px, oy + hr * tile_px, tile_px, tile_px))
        elif self._hover:
            painter.setPen(QPen(QColor(C.TEXT_DIM), 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(ox + self._hover[0] * tile_px,
                                   oy + self._hover[1] * tile_px, tile_px, tile_px))

        # Sélection en cours (ramassage de tuiles déjà posées, sans brosse)
        if self._select_start is not None and self._select_end is not None:
            c0, r0 = self._select_start
            c1, r1 = self._select_end
            cmin, cmax = min(c0, c1), max(c0, c1)
            rmin, rmax = min(r0, r1), max(r0, r1)
            rect = QRect(ox + cmin * tile_px, oy + rmin * tile_px,
                         (cmax - cmin + 1) * tile_px, (rmax - rmin + 1) * tile_px)
            fill_color = QColor(C.ACCENT_COOL)
            fill_color.setAlpha(64)
            painter.fillRect(rect, fill_color)
            painter.setPen(QPen(QColor(C.ACCENT_COOL), 2))
            painter.drawRect(rect)

        # Indicateur de zoom manuel
        if self._zoom > 0:
            painter.setPen(QColor(C.TEXT_DIM))
            painter.setFont(QFont(T.MONO, T.XS))
            painter.drawText(6, self.height() - 6, f"{self._zoom}×")

        painter.end()


class SpriteCanvasToolbar(QFrame):
    """
    Barre d'outils flottante et déplaçable superposée au canvas — même
    modèle que FloatingToolbar/CanvasContainer du Scene Manager
    (core/scene_editor.py), en horizontal : playback (|◀ ▶ ▶|), grille,
    flip brosse (X/Y), Fit.
    """

    def __init__(self, canvas: "SpriteCanvas", parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._dragging = False
        self._drag_offset = QPoint()

        self.setStyleSheet(
            f"SpriteCanvasToolbar{{background:{C.BG_RAISED};border:1px solid {C.BORDER};border-radius:8px;}}"
            "QToolButton{border:none;background:transparent;border-radius:4px;}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(4)

        from ui.common.widgets import DragHandle
        layout.addWidget(DragHandle(Qt.Orientation.Horizontal))

        def _sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setStyleSheet(f"color:{C.BORDER};margin:2px 6px;")
            layout.addWidget(s)

        def _icon_btn(icon_key: str, tip: str, checkable: bool = False) -> QToolButton:
            b = QToolButton()
            b.setIcon(_ico(icon_key, C.TEXT_DIM, C.ACCENT))
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(36, 36)
            b.setCheckable(checkable)
            b.setToolTip(tip)
            layout.addWidget(b)
            return b

        self.btn_prev = _icon_btn("playback_prev", tooltip(
            title=label("sprframe.previous_frame"), body=label("sprframe.previous_frame_tip")
        ))
        self.btn_play = _icon_btn("playback_play", tooltip(
            title=label("sprframe.play_preview"), body=label("sprframe.play_preview_tip")
        ), checkable=True)
        self.btn_next = _icon_btn("playback_next", tooltip(
            title=label("sprframe.next_frame"), body=label("sprframe.next_frame_tip")
        ))
        _sep()
        self.btn_grid = _icon_btn("playback_grid", tooltip(
            title=label("sprframe.grid"), body=label("sprframe.grid_tip")
        ), checkable=True)
        _sep()
        self.btn_flip_x = _icon_btn("mirror_h", tooltip(
            title=label("sprframe.flip_x"), shortcut=get_keybindings().resolve("sprite.flip_h")
        ))
        self.btn_flip_y = _icon_btn("mirror_v", tooltip(
            title=label("sprframe.flip_y"), shortcut=get_keybindings().resolve("sprite.flip_v")
        ))
        _sep()

        _TXT_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;"
            f"font-size:{T.LG}px;padding:0 8px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )
        self.btn_fit = QToolButton(); self.btn_fit.setText(label("sprframe.fit"))
        self.btn_fit.setStyleSheet(_TXT_BTN)
        self.btn_fit.setFixedHeight(36)
        self.btn_fit.setToolTip(tooltip(title=label("sprframe.fit_title")))
        layout.addWidget(self.btn_fit)

        # Grille + flip/zoom pilotent directement le canvas (pas d'état
        # externe à coordonner) ; play + palette restent exposés pour être
        # câblés par SpriteCenterPanel (timer d'animation, dropdown palette).
        self.btn_grid.setChecked(True)
        self.btn_grid.toggled.connect(self._canvas.set_grid)
        self.btn_flip_x.clicked.connect(self._canvas.flip_brush_x)
        self.btn_flip_y.clicked.connect(self._canvas.flip_brush_y)
        self.btn_fit.clicked.connect(self._canvas.zoom_fit)

        self.adjustSize()

    # ── Drag (identique à FloatingToolbar, core/scene_editor.py) ───────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and self.parent():
            new_pos = self.mapToParent(e.pos()) - self._drag_offset
            p = self.parent()
            x = max(0, min(new_pos.x(), p.width() - self.width()))
            y = max(0, min(new_pos.y(), p.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


class SpriteCanvasPanel(QWidget):
    """
    Enrobe SpriteCanvas avec une barre d'outils flottante
    (SpriteCanvasToolbar) et des textes flottants (tag CANVAS, stats
    Tiles/Unique, coordonnées survolées) superposés au canvas — même modèle
    que CanvasContainer/FloatingToolbar du Scene Manager.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = SpriteCanvas()
        self.canvas.hover_changed.connect(self._on_hover_changed)
        root.addWidget(self.canvas, 1)

        # Bandeau flottant de sélection de palette (bas-centre, même widget que
        # Scene Manager/Background Editor — cf. palette_bank_strip) : les
        # sous-palettes de la PAL_BANK du sprite (SpriteCenterPanel.load_sprite),
        # clic = palette active pour le mode « Indexé ». Masqué si aucune palette.
        self.paint_strip = PaletteBankStrip(label("common.no_palette"), self)
        self.paint_strip.setVisible(False)
        self.paint_strip.raise_()

        self.toolbar = SpriteCanvasToolbar(self.canvas, self)
        self.toolbar.move(10, 10)
        self.toolbar.raise_()

        # Table des raccourcis (bas-droite ; les coordonnées survolées sont décalées
        # en conséquence dans _reposition_overlays).
        self._hints = ShortcutHints(self, sprite_canvas_hints, self.canvas.hint_context())
        self.canvas.mode_changed.connect(self._sync_hints)
        self.canvas.brush_picked_up.connect(lambda _n: self._sync_hints())

        _FLOAT_STY = f"color:{C.TEXT_MUTED};background:transparent;"
        self._info_lbl = QLabel("", self)
        self._info_lbl.setFont(QFont(T.MONO, T.XS))
        self._info_lbl.setStyleSheet(_FLOAT_STY)
        self._info_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._coord_lbl = QLabel("", self)
        self._coord_lbl.setFont(QFont(T.MONO, T.XS))
        self._coord_lbl.setStyleSheet(_FLOAT_STY)
        self._coord_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Bandeau miroir / lecture seule — visible seulement pour une direction
        # miroir (mirror_of défini) : signale que le contenu n'est pas éditable.
        self._ro_lbl = QLabel("", self)
        self._ro_lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._ro_lbl.setStyleSheet(
            f"color:{C.ACCENT_COOL};background:{tint(C.ACCENT_COOL, 0.15)};"
            f"border:1px solid {C.ACCENT_COOL};border-radius:4px;padding:3px 8px;"
        )
        self._ro_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ro_lbl.hide()

        self._reposition_overlays()

    def _sync_hints(self):
        self._hints.set_context(self.canvas.hint_context())

    def set_read_only_banner(self, text: Optional[str]):
        """Affiche/masque le bandeau miroir. text=None → masqué."""
        if text:
            self._ro_lbl.setText(text)
            self._ro_lbl.adjustSize()
            self._ro_lbl.show()
        else:
            self._ro_lbl.hide()
        self._reposition_overlays()

    def set_info(self, tiles: int, unique: int):
        self._info_lbl.setText(label("sprframe.info", tiles=tiles, unique=unique))
        self._info_lbl.adjustSize()
        self._reposition_overlays()

    def _on_hover_changed(self, cell):
        self._coord_lbl.setText(label("sprframe.coord", c=cell[0], r=cell[1]) if cell else "")
        self._coord_lbl.adjustSize()
        self._reposition_overlays()

    def _reposition_overlays(self):
        self._coord_lbl.move(self.width() - self._coord_lbl.width() - HINTS_CLEARANCE,
                             self.height() - self._coord_lbl.height() - 8)
        self._info_lbl.move(self.width() - self._info_lbl.width() - 10, 8)
        self._ro_lbl.move((self.width() - self._ro_lbl.width()) // 2, 8)
        self._position_paint_strip()

    def _position_paint_strip(self):
        strip = self.paint_strip
        strip.reflow()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(0, self.height() - strip.height() - 12)
        strip.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self.toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        self._reposition_overlays()
        if self.paint_strip.isVisible():
            self.paint_strip.raise_()
