"""ui/background_editor/bg_inpaint_canvas.py — canvas de peinture BackgroundInpainting.

Repeindre, AU NIVEAU ÉDITEUR (partagé entre toutes les scènes), la palette
(pal_bank local) de chaque tuile 8×8 d'un fond. Les overrides vivent dans
`BackgroundAsset.tile_palette_overrides` ; la baseline `tilemap` reste intacte
(cf. BackgroundAsset.effective_tilemap). Analogue au SceneInpaintingController,
mais côté asset — d'où la nomenclature « BackgroundInpainting ».

Le canvas sert AUSSI les deux autres emplois d'un fond (cf. `BG_KINDS`), parce
que ce sont trois emplois de la même image et qu'un second canvas aurait dupliqué
le zoom, le pan, la grille et le rendu :
  · fond d'INTERFACE en cadre étirable → guides de coupe glissables (les mêmes
    marges que règlent les champs de l'inspecteur) ;
  · fond ANIMÉ → grille de frames et lecture à la vitesse déclarée ;
  · n'importe quel fond → fonds animés POSÉS dessus, déposés depuis le finder,
    déplaçables et supprimables, stockés dans le .json de l'hôte.

Composants :
- BgInpaintController : état + peinture (brosse/fill/rect/gomme) + rendu
  incrémental + persistance + undo.
- BgInpaintView       : QGraphicsView (zoom molette, pan clic-central, grille 8×8)
  déléguant la souris à l'outil actif.
- BgInpaintToolbar    : barre d'outils flottante déplaçable (4 outils).
- _SliceOverlay / _FrameOverlay / _PlacementOverlay : superpositions par type.
- BgInpaintCanvas     : wrapper vue + toolbar.
"""
from __future__ import annotations
from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QLabel, QToolButton, QMenu,
    QGraphicsOpacityEffect,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap, QImage, QTransform, QPen, QBrush
from PyQt6.QtCore import Qt, QPoint, QPointF, QSize, QRectF, QTimer, QPropertyAnimation, pyqtSignal

from core.bg_import import render_bg_preview, render_bitmap_preview
from core.models.tile_codec import unpack_se, hex_to_tile, flip_h, flip_v
from core.models.gba_color import bgr555_to_rgb888
from core.models.resource import MIME_ANIMATED_BG
from core.models.background import (
    KIND_UI, KIND_ANIMATED, UI_ROLE_NINE, BackgroundAnimation,
)
from ui.common.theme import C, T, QSS
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.canvas_top_bar import CanvasTopBar, BAR_HEIGHT
from ui.background_editor.bg_prepare_overlay import PrepareOverlay, MODE_CROP, MODE_RESIZE
from ui.common.icons import get as _ico, COLOR_DEFAULT, COLOR_ACTIVE, COLOR_UI
from ui.common import external_editor
from ui.common.canvas_backdrop import draw_grid, draw_grid_halo

_BACKDROP_STEP = 16   # pas de la grille de fond, en pixels IMAGE (indépendant du zoom)


def _snap8(v) -> int:
    """Cale une coordonnée sur la grille 8×8, vers le bas.

    Ce que le matériel écrira pour un fond posé est une entrée de tilemap : une
    origine entre deux tuiles n'existe pas (même règle que
    `UIRegion.snap_to_tile`, et pour la même raison)."""
    n = int(v)
    return n - n % 8


def _pil_to_qimage(img) -> QImage:
    """PIL RGBA → QImage indépendant (buffer copié)."""
    data = bytes(img.tobytes("raw", "RGBA"))
    return QImage(data, img.width, img.height,
                  QImage.Format.Format_RGBA8888).copy()


class _HoverOverlay(QLabel):
    """Étiquette d'info flottante sur le canvas : semi-transparente au repos,
    pleinement opaque au survol (fondu court). L'opacité porte sur TOUT le widget
    (fond + texte) via un QGraphicsOpacityEffect."""
    _REST, _HOVER = 0.55, 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(self._REST)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(120)

    def _fade_to(self, v: float):
        self._anim.stop()
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(v)
        self._anim.start()

    def enterEvent(self, e):
        self._fade_to(self._HOVER); super().enterEvent(e)

    def leaveEvent(self, e):
        self._fade_to(self._REST); super().leaveEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Contrôleur de peinture (état + rendu + undo + persistance)
# ──────────────────────────────────────────────────────────────────
class BgInpaintController:
    """Pilote la peinture par palette d'un BackgroundAsset. Détient l'image
    rendue (baseline + overrides), applique/persiste les overrides tuile par
    tuile, et expose un delta undoable par stroke."""

    def __init__(self):
        self._project = None
        self._ba = None
        self._active_pal = 0
        self._stroke: Optional[dict] = None
        self._qimg: Optional[QImage] = None
        self._tiles: list = []          # tuiles décodées (cache patch)
        self._pal_rgb: list = []        # palettes RGB (cache patch)
        self._paint_enabled = True      # False en 8bpp (une seule palette, pas d'inpainting)
        self.on_rendered = None         # callback() : la vue rafraîchit son pixmap

    # ── Contexte ─────────────────────────────────────────────────
    def set_context(self, project, ba):
        self._project = project
        self._ba = ba
        self._stroke = None
        self._active_pal = 0
        self._render_full()

    def set_active_palette(self, idx: int):
        self._active_pal = idx

    @property
    def ready(self) -> bool:
        if self._ba is None:
            return False
        if getattr(self._ba, "mode", "tiled") == "bitmap":
            return bool(self._ba.bitmap)
        return bool(self._ba.tileset)

    def set_paint_enabled(self, on: bool):
        self._paint_enabled = on

    @property
    def paintable(self) -> bool:
        """Peinture possible : rendu prêt ET mode le permet (tuilé 4bpp uniquement)."""
        return self.ready and self._paint_enabled

    def tiles_size(self) -> tuple[int, int]:
        if not self._ba:
            return (0, 0)
        return (self._ba.tiles_w, self._ba.tiles_h)

    def image_size(self) -> tuple[int, int]:
        """Dimensions en pixels de l'image rendue (bitmap : out_w×out_h ; tuilé :
        tiles×8) — pour dimensionner la vue/le sceneRect."""
        if not self._ba:
            return (0, 0)
        if getattr(self._ba, "mode", "tiled") == "bitmap":
            return (self._ba.out_w, self._ba.out_h)
        return (self._ba.tiles_w * 8, self._ba.tiles_h * 8)

    def grid_visible(self) -> bool:
        return bool(self._ba and getattr(self._ba, "mode", "tiled") == "tiled" and self._ba.tileset)

    def pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self._qimg) if self._qimg else QPixmap()

    def _notify(self):
        if self.on_rendered:
            self.on_rendered()

    # ── Rendu ────────────────────────────────────────────────────
    def _render_full(self):
        if not self.ready:
            self._qimg = None
            return
        ba = self._ba
        if getattr(ba, "mode", "tiled") == "bitmap":
            # Mode 4 : bitmap plein écran, aucun patch incrémental (peinture off).
            self._qimg = _pil_to_qimage(render_bitmap_preview({
                "out_w": ba.out_w, "out_h": ba.out_h,
                "palettes": ba.palettes, "bitmap": ba.bitmap,
            }))
            self._tiles = []
            self._pal_rgb = []
            return
        compiled = {
            "tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
            "tileset": ba.tileset, "palettes": ba.palettes,
            "tilemap": ba.effective_tilemap(), "bpp": getattr(ba, "bpp", 4),
        }
        self._qimg = _pil_to_qimage(render_bg_preview(compiled))
        self._tiles = [hex_to_tile(t) for t in ba.tileset]
        self._pal_rgb = [[bgr555_to_rgb888(c) for c in pal] for pal in ba.palettes]

    def reload_render(self):
        """Re-render complet (après édition des palettes côté inspecteur)."""
        self._render_full()
        self._notify()

    def _patch(self, col: int, row: int):
        """Recolorise le bloc 8×8 (col,row) dans l'image, palette effective."""
        if self._qimg is None:
            return
        tw = self._ba.tiles_w or 1
        cell = row * tw + col
        if not (0 <= cell < len(self._ba.tilemap)):
            return
        tid, pb, fh, fv = unpack_se(self._ba.tilemap[cell])
        ov = self._ba.tile_palette_overrides.get((col, row))
        eff = pb if ov is None else ov
        grid = tuple(self._tiles[tid]) if tid < len(self._tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        pal = self._pal_rgb[eff] if eff < len(self._pal_rgb) else (
            self._pal_rgb[0] if self._pal_rgb else [(0, 0, 0)] * 16)
        blk = QImage(8, 8, QImage.Format.Format_RGBA8888)
        blk.fill(0)
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(pal):
                    continue
                r, g, b = pal[idx]
                blk.setPixelColor(x, y, QColor(r, g, b, 255))
        painter = QPainter(self._qimg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(col * 8, row * 8, blk)
        painter.end()

    # ── Palette effective / baseline d'une tuile ─────────────────
    def _base_pb(self, col: int, row: int) -> int:
        tw = self._ba.tiles_w or 1
        return unpack_se(self._ba.tilemap[row * tw + col])[1]

    def _effective_pb(self, col: int, row: int) -> int:
        ov = self._ba.tile_palette_overrides.get((col, row))
        return self._base_pb(col, row) if ov is None else ov

    # ── Peinture ─────────────────────────────────────────────────
    def begin_stroke(self):
        self._stroke = {}

    def _paint_one(self, col: int, row: int, erase: bool):
        """Applique la palette active (ou restaure l'origine si `erase`) à UNE
        tuile, enregistre le delta — SANS notifier (batch fill/rect)."""
        tw, th = self.tiles_size()
        if not (0 <= col < tw and 0 <= row < th):
            return
        key = (col, row)
        if erase:
            new = None
        else:
            # Peindre la palette de base = pas d'override (JSON minimal, gomme cohérente).
            new = None if self._active_pal == self._base_pb(col, row) else self._active_pal
        old = self._ba.tile_palette_overrides.get(key)
        if old == new:
            return
        if self._stroke is not None:
            self._stroke[key] = (self._stroke.get(key, (old, None))[0], new)
        if new is None:
            self._ba.tile_palette_overrides.pop(key, None)
        else:
            self._ba.tile_palette_overrides[key] = new
        self._patch(col, row)

    def set_tile(self, col: int, row: int, erase: bool = False):
        if not self.paintable:
            return
        self._paint_one(col, row, erase)
        self._notify()

    def fill(self, col: int, row: int):
        """Flood-fill contigu (4-voisins) des tuiles de même palette effective."""
        if not self.paintable:
            return
        tw, th = self.tiles_size()
        if not (0 <= col < tw and 0 <= row < th):
            return
        target = self._effective_pb(col, row)
        if self._active_pal == target:
            return
        seen: set = set()
        stack = [(col, row)]
        while stack:
            c, r = stack.pop()
            if (c, r) in seen or not (0 <= c < tw and 0 <= r < th):
                continue
            if self._effective_pb(c, r) != target:
                continue
            seen.add((c, r))
            self._paint_one(c, r, erase=False)
            stack += [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        self._notify()

    def paint_rect(self, c0: int, r0: int, c1: int, r1: int, erase: bool = False):
        if not self.paintable:
            return
        for r in range(min(r0, r1), max(r0, r1) + 1):
            for c in range(min(c0, c1), max(c0, c1) + 1):
                self._paint_one(c, r, erase)
        self._notify()

    def end_stroke(self):
        """Clôt le stroke : pousse la commande d'historique + persiste."""
        delta = self._stroke or {}
        self._stroke = None
        if not delta or not self.ready:
            return
        from core.history import BackgroundInpaintingCmd, get_history
        cmd = BackgroundInpaintingCmd(self, self._ba, dict(delta))
        h = get_history()
        h._undo.append(cmd)
        h._redo.clear()
        h.changed.emit()
        self._persist()

    # ── Undo/redo (appelé par BackgroundInpaintingCmd) ───────────
    def apply_override_delta(self, ba, delta: dict, forward: bool):
        for key, (old, new) in delta.items():
            val = new if forward else old
            if val is None:
                ba.tile_palette_overrides.pop(key, None)
            else:
                ba.tile_palette_overrides[key] = val
        if self._project:
            from core.command_dispatcher import get_dispatcher
            with get_dispatcher().suspended():
                self._project.save_background(ba)
            get_dispatcher().notify_background_changed(ba)
        if ba is self._ba:
            self._render_full()
            self._notify()

    def _persist(self):
        if not self._project or not self._ba:
            return
        from core.command_dispatcher import get_dispatcher
        with get_dispatcher().suspended():
            self._project.save_background(self._ba)
        get_dispatcher().notify_background_changed(self._ba)


# ──────────────────────────────────────────────────────────────────
#  Overlay grille 8×8 (item unique)
# ──────────────────────────────────────────────────────────────────
class _GridOverlay(QGraphicsItem):
    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._w, self._h = w, h
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w, self._h = w, h

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        # Bornée à `option.exposedRect` : sans ça, un grand fond retrace TOUTES
        # ses lignes à chaque repaint (y compris pendant un zoom, qui invalide
        # toute la vue), même la quasi-totalité hors champ.
        exposed = option.exposedRect.intersected(QRectF(0, 0, self._w, self._h))
        if exposed.isEmpty():
            return
        x0 = max(0, int(exposed.left()) - int(exposed.left()) % 8)
        y0 = max(0, int(exposed.top()) - int(exposed.top()) % 8)
        x1 = min(self._w, int(exposed.right()) + 8)
        y1 = min(self._h, int(exposed.bottom()) + 8)
        pen = QPen(QColor(255, 255, 255, 28))
        pen.setWidth(0)
        painter.setPen(pen)
        for x in range(x0, x1 + 1, 8):
            painter.drawLine(x, y0, x, y1)
        for y in range(y0, y1 + 1, 8):
            painter.drawLine(x0, y, x1, y)


# ──────────────────────────────────────────────────────────────────
#  Aperçu d'un fond en pixmap (cache partagé)
# ──────────────────────────────────────────────────────────────────
def asset_pixmap(ba) -> Optional[QPixmap]:
    """Rendu complet d'un BackgroundAsset compressé, ou None s'il n'a rien à
    montrer. Même chaîne que l'aperçu du canvas (`render_bg_preview`) : un
    second rendu divergerait au premier flip, comme il a divergé pour les
    frames de sprite."""
    if ba is None:
        return None
    if getattr(ba, "mode", "tiled") == "bitmap":
        if not ba.bitmap:
            return None
        img = render_bitmap_preview({"out_w": ba.out_w, "out_h": ba.out_h,
                                     "palettes": ba.palettes, "bitmap": ba.bitmap})
    else:
        if not ba.tileset:
            return None
        img = render_bg_preview({
            "tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
            "tileset": ba.tileset, "palettes": ba.palettes,
            "tilemap": ba.effective_tilemap(), "bpp": getattr(ba, "bpp", 4),
        })
    return QPixmap.fromImage(_pil_to_qimage(img))


# ──────────────────────────────────────────────────────────────────
#  Overlay : guides de coupe d'un cadre nine-slice
# ──────────────────────────────────────────────────────────────────
class _SliceOverlay(QGraphicsItem):
    """Les 4 lignes de coupe d'un fond d'interface, glissables.

    Le vrai sujet d'un cadre étirable n'est pas « combien de pixels » mais « où
    passe la coupe » : quatre nombres dans un formulaire obligent à compter les
    pixels dans un autre logiciel, alors que la réponse se voit. Les champs de
    l'inspecteur restent (on veut aussi taper 8), et écrivent le même modèle.

    Les coins — les seules cases qui ne se répètent pas — sont assombris, parce
    que c'est ce que la coupe DÉCIDE : tout le reste sera étiré ou tuilé."""

    GRAB = 4        # tolérance de saisie, en pixels d'IMAGE (indépendante du zoom)

    _KEYS = ("slice_left", "slice_right", "slice_top", "slice_bottom")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._w = self._h = 0
        self._m = {k: 0 for k in self._KEYS}
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_image_size(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w, self._h = w, h

    def set_margins(self, margins: dict):
        self._m.update({k: int(v) for k, v in margins.items() if k in self._m})
        self.update()

    def margins(self) -> dict:
        return dict(self._m)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    # Position (en px image) de chaque guide. Droite/bas comptent depuis leur
    # bord — c'est la sémantique d'une MARGE, pas d'une coordonnée.
    def _positions(self) -> dict:
        return {"slice_left": self._m["slice_left"],
                "slice_right": self._w - self._m["slice_right"],
                "slice_top": self._m["slice_top"],
                "slice_bottom": self._h - self._m["slice_bottom"]}

    def guide_at(self, x: float, y: float) -> Optional[str]:
        """Guide sous le curseur, le plus proche d'abord. None = zone libre, et
        le canvas rend alors la main à l'outil de peinture."""
        pos = self._positions()
        best, best_d = None, self.GRAB + 1
        for key in ("slice_left", "slice_right"):
            d = abs(x - pos[key])
            if d < best_d and 0 <= y <= self._h:
                best, best_d = key, d
        for key in ("slice_top", "slice_bottom"):
            d = abs(y - pos[key])
            if d < best_d and 0 <= x <= self._w:
                best, best_d = key, d
        return best

    def margin_for(self, key: str, x: float, y: float) -> int:
        """Marge que vaudrait `key` si son guide était lâché en (x, y). Bornée à
        l'image et au guide opposé : deux marges qui se croisent donneraient un
        cadre retourné, que `nine_slice_rects` devrait rattraper au rendu."""
        if key == "slice_left":
            return int(max(0, min(x, self._w - self._m["slice_right"])))
        if key == "slice_right":
            return int(max(0, min(self._w - x, self._w - self._m["slice_left"])))
        if key == "slice_top":
            return int(max(0, min(y, self._h - self._m["slice_bottom"])))
        return int(max(0, min(self._h - y, self._h - self._m["slice_top"])))

    def paint(self, painter: QPainter, option, widget=None):
        if not (self._w and self._h):
            return
        pos = self._positions()
        l, r = pos["slice_left"], pos["slice_right"]
        t, b = pos["slice_top"], pos["slice_bottom"]
        col = QColor(COLOR_UI)
        # Coins : ce que la coupe fige.
        shade = QColor(col); shade.setAlpha(48)
        for cx, cw in ((0, l), (r, self._w - r)):
            for cy, ch in ((0, t), (b, self._h - b)):
                if cw > 0 and ch > 0:
                    painter.fillRect(QRectF(cx, cy, cw, ch), QBrush(shade))
        pen = QPen(col)
        pen.setWidth(0)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(l), 0, int(l), self._h)
        painter.drawLine(int(r), 0, int(r), self._h)
        painter.drawLine(0, int(t), self._w, int(t))
        painter.drawLine(0, int(b), self._w, int(b))


# ──────────────────────────────────────────────────────────────────
#  Overlay : grille de frames d'une planche animée
# ──────────────────────────────────────────────────────────────────
class _FrameOverlay(QGraphicsItem):
    """La découpe d'une planche, et la frame en cours de lecture.

    Le voile sur TOUT sauf la frame courante plutôt qu'un cadre autour d'elle :
    c'est ce qui montre du premier coup d'œil qu'une planche mal découpée joue
    à cheval sur deux dessins."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._w = self._h = 0
        self._fw = self._fh = 0
        self._cols = self._rows = 0
        self._cur = 0
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_grid(self, img_w: int, img_h: int, fw: int, fh: int,
                 cols: int, rows: int):
        self.prepareGeometryChange()
        self._w, self._h = img_w, img_h
        self._fw, self._fh = max(1, fw), max(1, fh)
        self._cols, self._rows = cols, rows
        self.update()

    def set_current(self, index: int):
        if index != self._cur:
            self._cur = index
            self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        if not (self._cols and self._rows):
            return
        cur_c, cur_r = self._cur % self._cols, self._cur // self._cols
        veil = QColor(0, 0, 0, 120)
        for r in range(self._rows):
            for c in range(self._cols):
                if (c, r) == (cur_c, cur_r):
                    continue
                painter.fillRect(QRectF(c * self._fw, r * self._fh,
                                        self._fw, self._fh), QBrush(veil))
        # Les pixels hors grille n'appartiennent à aucune frame : même voile,
        # pour que la bande morte se VOIE (l'inspecteur, lui, la chiffre).
        gw, gh = self._cols * self._fw, self._rows * self._fh
        if gw < self._w:
            painter.fillRect(QRectF(gw, 0, self._w - gw, self._h), QBrush(veil))
        if gh < self._h:
            painter.fillRect(QRectF(0, gh, self._w, self._h - gh), QBrush(veil))
        pen = QPen(QColor(COLOR_ACTIVE))
        pen.setWidth(0)
        painter.setPen(pen)
        for c in range(self._cols + 1):
            painter.drawLine(c * self._fw, 0, c * self._fw, gh)
        for r in range(self._rows + 1):
            painter.drawLine(0, r * self._fh, gw, r * self._fh)


# ──────────────────────────────────────────────────────────────────
#  Overlay : fonds animés POSÉS sur l'hôte
# ──────────────────────────────────────────────────────────────────
class _PlacementOverlay(QGraphicsItem):
    """Les fonds animés déposés sur ce fond, JOUÉS sur place.

    Joués et pas figés sur leur première frame — contrairement aux images du
    canvas de scène, qui restent immobiles pour ne pas faire bouger le décor
    sous la souris. Ici l'animation EST l'objet qu'on pose : voir sa cadence et
    son raccord avec le décor est la seule raison de la poser dans un canvas
    plutôt que de taper deux coordonnées."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._w = self._h = 0
        self._items: list = []     # {pl, pix, w, h, fw, fh, cols, n, speed, loop}
        self._tick = 0
        self._selected = None      # BackgroundAnimation | None
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_image_size(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w, self._h = w, h

    def set_items(self, items: list):
        self._items = items
        self.update()

    def set_tick(self, tick: int):
        self._tick = tick
        self.update()

    def set_selected(self, pl):
        self._selected = pl
        self.update()

    def selected(self):
        return self._selected

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def hit(self, x: float, y: float):
        """Placement sous le point, le DERNIER posé d'abord (il est au-dessus)."""
        for it in reversed(self._items):
            pl = it["pl"]
            if pl.x <= x < pl.x + it["w"] and pl.y <= y < pl.y + it["h"]:
                return pl
        return None

    def _frame_index(self, it) -> int:
        """Image courante de CETTE copie — sa cadence et son image de départ, pas
        celles de la planche. Deux copies de la même planche peuvent donc être à
        des moments différents, exactement comme la ROM les jouera."""
        n = max(1, it["n"])
        step = self._tick // max(1, it["speed"]) + max(0, it["start_frame"])
        return step % n if it["loop"] else min(step, n - 1)

    def paint(self, painter: QPainter, option, widget=None):
        for it in self._items:
            pl = it["pl"]
            rect = QRectF(pl.x, pl.y, it["w"], it["h"])
            pix = it["pix"]
            if pix is None:
                # Référence pendante (animé supprimé/renommé hors éditeur) :
                # une croix à la place, jamais un trou — un placement invisible
                # se retrouverait dans le .json sans qu'on sache pourquoi.
                pen = QPen(QColor(C.ACCENT_RED)); pen.setWidth(0)
                painter.setPen(pen)
                painter.drawRect(rect)
                painter.drawLine(rect.topLeft().toPoint(), rect.bottomRight().toPoint())
                painter.drawLine(rect.topRight().toPoint(), rect.bottomLeft().toPoint())
                continue
            i = self._frame_index(it)
            cols = max(1, it["cols"])
            src = QRectF((i % cols) * it["fw"], (i // cols) * it["fh"],
                         it["fw"], it["fh"])
            painter.drawPixmap(rect, pix, src)
            if pl is self._selected:
                pen = QPen(QColor(COLOR_ACTIVE)); pen.setWidth(0)
                painter.setPen(pen)
                painter.drawRect(rect)


# ──────────────────────────────────────────────────────────────────
#  Vue zoomable / pan / peinture
# ──────────────────────────────────────────────────────────────────
class BgInpaintView(QGraphicsView):
    zoom_changed = pyqtSignal(float)
    cursor_moved = pyqtSignal(int, int)   # px dans l'image ; (-1,-1) = hors image
    slice_dragged = pyqtSignal(str, int)  # (clé de marge, valeur px)
    slice_released = pyqtSignal()         # fin de glissement → persistance
    anim_dropped = pyqtSignal(str, int, int)   # (nom du fond animé, x, y)
    placement_moved = pyqtSignal(object, int, int)  # (placement, x, y)
    placement_selected = pyqtSignal(object)         # placement | None
    placement_deleted = pyqtSignal(object)
    prepare_live = pyqtSignal(int, int)     # taille du recadrage / du redimensionnement en cours
    resize_released = pyqtSignal(int, int)  # poignée lâchée → nouvelle taille
    crop_finished = pyqtSignal(bool)        # Entrée (True) / Échap (False) en recadrage

    _ZOOM_LEVELS = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0]

    def __init__(self, controller: BgInpaintController, parent=None):
        self._ctrl = controller
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setBackgroundBrush(QColor(C.BG_DEEP))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._pix_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pix_item)
        self._grid = _GridOverlay(0, 0)
        self._grid.setZValue(10)
        self._scene.addItem(self._grid)
        self._grid_on = True     # préférence utilisateur (toggle de la barre)

        # Superpositions par type. Les placements passent SOUS les guides et la
        # grille : ceux-ci se règlent, un placement se regarde.
        self.placements = _PlacementOverlay()
        self.placements.setZValue(20)
        self._scene.addItem(self.placements)
        self.slices = _SliceOverlay()
        self.slices.setZValue(30)
        self.slices.setVisible(False)
        self._scene.addItem(self.slices)
        self.frames = _FrameOverlay()
        self.frames.setZValue(30)
        self.frames.setVisible(False)
        self._scene.addItem(self.frames)

        # Préparation de la source (recadrer / redimensionner). Au-dessus de tout :
        # tant qu'un de ces modes est actif, ses poignées priment sur le reste.
        self._prep = PrepareOverlay()
        self._prep.setZValue(40)
        self._scene.addItem(self._prep)
        # Le recadrage montre la SOURCE entière, à la place de l'image encodée.
        self._src_item = QGraphicsPixmapItem()
        self._src_item.setVisible(False)
        self._scene.addItem(self._src_item)
        self._crop_src_size: Optional[tuple] = None
        self._zoom_before_crop = 2.0
        self._hidden_by_crop: list = []
        self.zoom_changed.connect(self._prep.set_zoom)

        # Dépôt d'un fond animé venu du finder.
        self.setAcceptDrops(True)
        # Suppr sur un fond posé : sans focus clavier, la touche n'arriverait
        # jamais jusqu'ici.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._drag_guide: Optional[str] = None
        self._drag_pl = None                 # placement en cours de déplacement
        self._drag_pl_grab = (0, 0)          # accroche dans le placement

        self._zoom = 2.0
        self._apply_zoom()

        # Position du curseur en continu (barre du haut), même sans bouton enfoncé.
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self._tool = "brush"
        self._painting = False
        self._rect_start: Optional[tuple[int, int]] = None
        self._panning = False
        self._pan_last = QPoint()
        self._hover_scene: Optional[QPointF] = None   # halo de fond, coord. scène

        controller.on_rendered = self._on_rendered

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Fond du canvas : même grille + halo au survol que le Font Editor,
        au pas de la GBA (16 px image) — sauf au dézoom, où le pas double
        tant que son espacement à l'écran serait illisible : le nombre de
        lignes tracées reste borné, plutôt que de croître avec la surface de
        fond visible (c'est ce qui ramait en dézoomant beaucoup)."""
        painter.fillRect(rect, QColor(C.BG_DEEP))
        step = self._adaptive_step()
        draw_grid(painter, rect, step)
        draw_grid_halo(painter, rect, step, self._hover_scene)

    def _adaptive_step(self, min_screen_px: float = 8.0) -> float:
        step = _BACKDROP_STEP
        while step * self._zoom < min_screen_px:
            step *= 2
        return step

    # ── API ──────────────────────────────────────────────────────
    def _on_rendered(self):
        # Mise à jour du pixmap seule (peinture / re-render palette) — ne touche
        # pas au zoom : l'utilisateur garde son cadrage pendant qu'il peint.
        self._pix_item.setPixmap(self._ctrl.pixmap())

    _DEFAULT_ZOOM = 2.0

    def load_background(self):
        """Nouveau fond sélectionné : pixmap + grille + sceneRect, puis cadrage
        au zoom par défaut (200 %, comme le canvas du Scene Manager) centré sur
        l'image. Le centrage est aussi différé (singleShot) car, au moment du
        chargement, la vue n'a pas toujours sa taille finale (layout du splitter).
        Le bouton « ajuster » reste là pour les grands fonds."""
        self._pix_item.setPixmap(self._ctrl.pixmap())
        self.sync_image_size()
        self._zoom = self._DEFAULT_ZOOM
        self._apply_zoom()
        self._center()
        QTimer.singleShot(0, self._center)

    def sync_image_size(self):
        """Grille, calques et sceneRect sur les dimensions courantes de l'image
        (elles changent au changement de mode ou à la recompression), sans
        toucher au zoom. Sans effet pendant un recadrage : la vue y montre la
        source, dont la taille est déjà posée."""
        if self._crop_src_size:
            return
        w, h = self._ctrl.image_size()
        self._grid.resize(w, h)
        self.slices.set_image_size(w, h)
        self.placements.set_image_size(w, h)
        self._sync_grid()
        self._scene.setSceneRect(0, 0, max(w, 1), max(h, 1))

    def _extent(self) -> tuple[int, int]:
        """Ce que la vue montre : la source entière pendant un recadrage, l'image
        encodée sinon. Centrage, cadrage et curseur se mesurent sur la même."""
        return self._crop_src_size or self._ctrl.image_size()

    def _center(self):
        w, h = self._extent()
        if w and h:
            self.centerOn(w / 2, h / 2)

    def set_tool(self, tool: str):
        self._tool = tool

    # ── Préparation de la source ──────────────────────────────────
    @property
    def prepare_mode(self) -> Optional[str]:
        return self._prep.mode

    def begin_crop(self, png_path, crop: Optional[tuple]) -> bool:
        """Entre en recadrage : la source entière remplace l'image encodée, le
        rectangle part de `crop` (x, y, w, h) — ou de l'image entière. False si
        la source est illisible."""
        pm = QPixmap(str(png_path))
        if pm.isNull():
            return False
        self.end_resize()
        sw, sh = pm.width(), pm.height()
        self._src_item.setPixmap(pm)
        self._src_item.setVisible(True)
        # Tout le reste décrit l'image ENCODÉE : dans les pixels de la source il
        # dirait faux, on le range le temps du recadrage.
        self._hidden_by_crop = [it for it in (self._pix_item, self._grid, self.placements,
                                              self.slices, self.frames) if it.isVisible()]
        for it in self._hidden_by_crop:
            it.setVisible(False)
        self._crop_src_size = (sw, sh)
        self._scene.setSceneRect(-16, -16, sw + 32, sh + 32)   # place pour les poignées
        # La source est souvent plus grande que ce que le zoom courant montre : on
        # la cadre en entier (poignées comprises), le zoom d'avant revient à la sortie.
        self._zoom_before_crop = self._zoom
        self.fit(margin=12)
        self._prep.set_zoom(self._zoom)
        self._prep.start_crop((sw, sh), crop or (0, 0, sw, sh))
        return True

    def end_crop(self) -> Optional[tuple]:
        """Sort du recadrage et rend le rectangle (x, y, w, h) de la SOURCE, ou
        None si on n'y était pas."""
        if self._prep.mode != MODE_CROP:
            return None
        rect = self._prep.crop_rect()
        self._prep.stop()
        self._src_item.setVisible(False)
        self._crop_src_size = None
        for it in self._hidden_by_crop:
            it.setVisible(True)
        self._hidden_by_crop = []
        self.unsetCursor()
        self.sync_image_size()
        self._zoom = self._zoom_before_crop
        self._apply_zoom()
        self._center()
        return rect

    def begin_resize(self, size: tuple):
        """Poignées de redimensionnement sur l'image préparée `size` (w, h)."""
        if self._prep.mode == MODE_CROP:
            return
        # Les poignées de gauche et du haut sortent du repère de l'image quand on
        # agrandit : on laisse de la place autour, sans bouger ce qu'on regarde.
        centre = self.mapToScene(self.viewport().rect().center())
        w, h = self._ctrl.image_size()
        self._scene.setSceneRect(-max(w, size[0]), -max(h, size[1]),
                                 3 * max(w, size[0]), 3 * max(h, size[1]))
        self.centerOn(centre)
        self._prep.set_zoom(self._zoom)
        self._prep.start_resize(size)

    def end_resize(self):
        if self._prep.mode == MODE_RESIZE:
            centre = self.mapToScene(self.viewport().rect().center())
            self._prep.stop()
            self.unsetCursor()
            self.sync_image_size()
            self.centerOn(centre)

    def _emit_prepare_live(self):
        w, h = self._prep.size() if self._prep.mode == MODE_RESIZE else self._prep.crop_rect()[2:]
        self.prepare_live.emit(w, h)

    # ── Grille ───────────────────────────────────────────────────
    def _sync_grid(self):
        """La grille 8×8 n'a de sens qu'en tuilé : le toggle ne peut que la
        masquer, jamais la forcer sur un bitmap."""
        self._grid.setVisible(self._grid_on and self._ctrl.grid_visible())

    def set_grid_visible(self, on: bool):
        self._grid_on = on
        self._sync_grid()

    # ── Zoom ─────────────────────────────────────────────────────
    def _apply_zoom(self):
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.25, min(self._zoom * factor, 16.0))
        self._apply_zoom()

    def zoom_step(self, direction: int):
        """Zoom par crans (boutons de la barre) — cran le plus proche, puis ±1."""
        levels = self._ZOOM_LEVELS
        idx = min(range(len(levels)), key=lambda i: abs(levels[i] - self._zoom))
        self._zoom = levels[max(0, min(idx + direction, len(levels) - 1))]
        self._apply_zoom()

    def fit(self, margin: int = 0):
        """Cadre l'image entière. `margin` (pixels de l'image) laisse de la place
        aux poignées, qui débordent du bord qu'elles tiennent."""
        w, h = self._extent()
        if w and h:
            self.fitInView(-margin, -margin, w + 2 * margin, h + 2 * margin,
                           Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()
            self.zoom_changed.emit(self._zoom)

    # ── Hit-test ─────────────────────────────────────────────────
    def _cell_at(self, e) -> tuple[int, int]:
        pos = self.mapToScene(e.position().toPoint())
        return int(pos.x() // 8), int(pos.y() // 8)

    def _emit_cursor(self, e):
        pos = self.mapToScene(e.position().toPoint())
        x, y = int(pos.x()), int(pos.y())
        w, h = self._extent()
        inside = 0 <= x < w and 0 <= y < h
        self.cursor_moved.emit(x if inside else -1, y if inside else -1)

    def leaveEvent(self, e):
        self.cursor_moved.emit(-1, -1)
        old = self._hover_scene
        self._hover_scene = None
        self._invalidate_halo(old, None)
        super().leaveEvent(e)

    def _invalidate_halo(self, old: Optional[QPointF], new: Optional[QPointF]):
        """Redemande le repaint SEULEMENT du carré occupé par le halo (avant
        et après) — jamais tout le viewport : sur un grand fond, ça forçait
        Qt à retracer l'image entière, la grille 8×8 et les calques à chaque
        pixel de survol, pour un effet qui ne bouge qu'un halo de quelques
        dizaines de pixels."""
        radius = max(48.0, 1.5 * self._adaptive_step())
        scene_rect = None
        for pt in (old, new):
            if pt is None:
                continue
            r = QRectF(pt.x() - radius, pt.y() - radius, radius * 2, radius * 2)
            scene_rect = r if scene_rect is None else scene_rect.united(r)
        if scene_rect is None:
            return
        view_rect = self.mapFromScene(scene_rect).boundingRect().adjusted(-2, -2, 2, 2)
        self.viewport().update(view_rect)

    # ── Souris ───────────────────────────────────────────────────
    # PRÉCÉDENCE, du plus spécifique au plus général : un guide de coupe (il
    # faut être à quelques pixels de la ligne), puis un fond animé posé, puis
    # l'outil de peinture. L'inverse aurait obligé à changer d'outil pour
    # déplacer ce qu'on vient de déposer, alors que les deux premiers cas sont
    # rares et bornés dans l'espace.

    def _scene_pos(self, e) -> tuple[float, float]:
        p = self.mapToScene(e.position().toPoint())
        return p.x(), p.y()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self._prep.mode:
            # Recadrage / redimensionnement actif : le clic est à ses poignées, ou
            # à personne — jamais à la peinture ni aux fonds posés.
            if self._prep.begin(*self._scene_pos(e)):
                self._emit_prepare_live()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            x, y = self._scene_pos(e)
            if self.slices.isVisible():
                guide = self.slices.guide_at(x, y)
                if guide:
                    self._drag_guide = guide
                    e.accept()
                    return
            pl = self.placements.hit(x, y)
            if pl is not None:
                self._drag_pl = pl
                self._drag_pl_grab = (x - pl.x, y - pl.y)
                self.placements.set_selected(pl)
                self.placement_selected.emit(pl)
                e.accept()
                return
            # Clic dans le vide : on désélectionne avant de peindre, sinon le
            # contour resterait sur un objet qu'on ne vise plus.
            if self.placements.selected() is not None:
                self.placements.set_selected(None)
                self.placement_selected.emit(None)
            if self._ctrl.paintable:
                self._handle_press(e)
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        self._emit_cursor(e)
        old_hover = self._hover_scene
        self._hover_scene = self.mapToScene(e.position().toPoint())
        self._invalidate_halo(old_hover, self._hover_scene)
        if self._panning:
            p = e.position().toPoint()
            d = p - self._pan_last
            self._pan_last = p
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        if self._prep.mode:
            x, y = self._scene_pos(e)
            if self._prep.dragging:
                mods = e.modifiers()
                self._prep.drag(x, y, bool(mods & Qt.KeyboardModifier.ShiftModifier),
                                bool(mods & Qt.KeyboardModifier.ControlModifier))
                self._emit_prepare_live()
            else:
                cur = self._prep.cursor_at(x, y)
                self.setCursor(cur) if cur else self.unsetCursor()
            e.accept()
            return
        if self._drag_guide:
            x, y = self._scene_pos(e)
            self.slice_dragged.emit(self._drag_guide,
                                    self.slices.margin_for(self._drag_guide, x, y))
            e.accept()
            return
        if self._drag_pl is not None:
            x, y = self._scene_pos(e)
            nx, ny = _snap8(x - self._drag_pl_grab[0]), _snap8(y - self._drag_pl_grab[1])
            self.placement_moved.emit(self._drag_pl, nx, ny)
            e.accept()
            return
        if self._painting and self._tool in ("brush", "eraser"):
            c, r = self._cell_at(e)
            self._ctrl.set_tile(c, r, erase=(self._tool == "eraser"))
            e.accept()
            return
        # Curseur de redimensionnement au survol d'un guide : sans ça, rien ne
        # dit que la ligne se prend.
        if self.slices.isVisible():
            g = self.slices.guide_at(*self._scene_pos(e))
            if g:
                self.setCursor(Qt.CursorShape.SizeHorCursor if "left" in g or "right" in g
                               else Qt.CursorShape.SizeVerCursor)
            else:
                self.unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            e.accept()
            return
        if self._prep.dragging and e.button() == Qt.MouseButton.LeftButton:
            self._prep.end()
            if self._prep.mode == MODE_RESIZE:
                self.resize_released.emit(*self._prep.size())
            e.accept()
            return
        if self._drag_guide and e.button() == Qt.MouseButton.LeftButton:
            self._drag_guide = None
            self.slice_released.emit()
            e.accept()
            return
        if self._drag_pl is not None and e.button() == Qt.MouseButton.LeftButton:
            self._drag_pl = None
            self.slice_released.emit()   # même signal : « le geste est fini, persiste »
            e.accept()
            return
        if self._painting and e.button() == Qt.MouseButton.LeftButton:
            if self._tool == "rect" and self._rect_start is not None:
                c, r = self._cell_at(e)
                c0, r0 = self._rect_start
                self._ctrl.paint_rect(c0, r0, c, r)
                self._rect_start = None
            self._ctrl.end_stroke()
            self._painting = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        """Un seul menu, et seulement sur un fond animé posé : le reste du canvas
        appartient aux outils de peinture (clic droit réservé)."""
        pos = self.mapToScene(e.pos())
        pl = self.placements.hit(pos.x(), pos.y())
        e.accept()
        if pl is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        act_del = menu.addAction(label('bginp.remove_this_animation'))
        if menu.exec(e.globalPos()) == act_del:
            self.placement_deleted.emit(pl)

    def keyPressEvent(self, e):
        if self._prep.mode == MODE_CROP and e.key() in (
                Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.crop_finished.emit(e.key() != Qt.Key.Key_Escape)
            e.accept()
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            pl = self.placements.selected()
            if pl is not None:
                self.placement_deleted.emit(pl)
                e.accept()
                return
        super().keyPressEvent(e)

    # ── Dépôt d'un fond animé ────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_ANIMATED_BG):
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_ANIMATED_BG):
            e.acceptProposedAction()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_ANIMATED_BG):
            super().dropEvent(e)
            return
        name = bytes(e.mimeData().data(MIME_ANIMATED_BG)).decode("utf-8")
        p = self.mapToScene(e.position().toPoint())
        # Point BRUT du curseur : c'est le canvas qui centre la frame dessus et
        # cale le résultat sur la grille — lui seul connaît la taille de ce
        # qu'on dépose, et centrer après calage décalerait d'une demi-tuile.
        self.anim_dropped.emit(name, int(p.x()), int(p.y()))
        e.acceptProposedAction()

    def _handle_press(self, e):
        c, r = self._cell_at(e)
        tool = self._tool
        if tool in ("brush", "eraser"):
            self._ctrl.begin_stroke()
            self._painting = True
            self._ctrl.set_tile(c, r, erase=(tool == "eraser"))
        elif tool == "fill":
            self._ctrl.begin_stroke()
            self._ctrl.fill(c, r)
            self._ctrl.end_stroke()
        elif tool == "rect":
            self._ctrl.begin_stroke()
            self._painting = True
            self._rect_start = (c, r)


# ──────────────────────────────────────────────────────────────────
#  Barre d'outils flottante
# ──────────────────────────────────────────────────────────────────
class BgInpaintToolbar(QFrame):
    tool_changed = pyqtSignal(str)

    _TOOLS = [
        ("brush",  "tool_inpaint_brush", label('bginp.brush_tip')),
        ("fill",   "tool_fill",          label('bginp.fill_tip')),
        ("rect",   "tool_inpaint_rect",  label('bginp.rectangle_repaint_an_area')),
        ("eraser", "tool_erase",         label('bginp.eraser_tip')),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._drag_offset = QPoint()
        self._current = "brush"
        self.min_y = 0     # borne haute du drag (la barre du canvas l'occupe)

        self.setFixedWidth(46)
        self.setStyleSheet(f"""
            BgInpaintToolbar {{
                background: {C.BG_RAISED};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
            QToolButton {{ border: none; background: transparent; border-radius: 5px; }}
            QToolButton:hover   {{ background: {C.BG_HOVER}; }}
            QToolButton:checked {{ background: {C.BG_SEL}; border: 1px solid {C.ACCENT}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(2)
        # La toolbar n'est pas gérée par un layout parent (elle est déplaçable,
        # positionnée en absolu au-dessus du canvas) : sans cette contrainte, le
        # QFrame n'est jamais dimensionné à son contenu et les boutons sont écrasés.
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        from ui.common.widgets import DragHandle
        layout.addWidget(DragHandle(Qt.Orientation.Vertical))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER}; margin:2px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._btns: dict[str, QToolButton] = {}
        for tool_id, icon_key, tip in self._TOOLS:
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, COLOR_DEFAULT, COLOR_ACTIVE))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFixedSize(36, 36)
            btn.clicked.connect(lambda _=False, t=tool_id: self._select(t))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._btns[tool_id] = btn

        self._btns["brush"].setChecked(True)

    def _select(self, tool: str):
        self._current = tool
        for tid, b in self._btns.items():
            b.setChecked(tid == tool)
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._current

    # ── Drag ─────────────────────────────────────────────────────
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
            y = max(self.min_y, min(new_pos.y(), p.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Wrapper canvas + toolbar
class BgInpaintCanvas(QWidget):
    """Panneau central du Background Editor : bande de peinture + canvas + toolbar."""

    slices_dragged = pyqtSignal(dict)      # marges posées au canvas → inspecteur
    placements_changed = pyqtSignal()      # fond animé posé/déplacé/retiré
    placement_selected = pyqtSignal(object)  # placement | None (relayé du view)
    # Recadrage / taille voulus pour la source, (None, None) = « Original ». Le
    # canvas ne compresse pas lui-même : l'écran le fait hors-thread et écrit le
    # résultat sur le fond.
    prepare_requested = pyqtSignal(object, object)

    # Cadence de la lecture : un tick GBA (60 Hz), l'unité dans laquelle les
    # vitesses sont DÉCLARÉES. Rejouer à l'unité près est ce qui rend l'aperçu
    # comparable à la ROM ; un timer arrondi à 30 Hz ferait mentir la moitié des
    # vitesses paires.
    _TICK_MS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctrl = BgInpaintController()
        self._view = BgInpaintView(self._ctrl, self)
        self._ba = None
        self._project = None
        self._tick = 0

        # Barre d'état au-dessus du canvas — même composant que le Scene Manager.
        self._bar = CanvasTopBar(label('bginp.fit_background_to_view'))
        self._bar.zoom_step_asked.connect(self._view.zoom_step)
        self._bar.fit_asked.connect(self._view.fit)
        self._chk_grid = self._bar.add_toggle(
            "view_grid", label('bginp.8_px_grid_gba_tile'), self._view.set_grid_visible)
        self._chk_grid.setChecked(True)
        # Éditer l'image dans un logiciel externe (cf. external_editor) : ce
        # canvas peint des PALETTES, pas des pixels — pour le dessin, on
        # délègue plutôt que d'inventer un éditeur d'image dans Qt.
        self._btn_edit = self._bar.add_action(
            "edit_external", label('bginp.edit_image'), self._on_edit_image)
        self._btn_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_edit.customContextMenuRequested.connect(self._on_edit_menu)
        # Préparer la source d'une image « riche » : recadrer, redimensionner,
        # revenir à l'original. Le PNG n'est jamais touché (cf. bg_import.prepare_source).
        self._bar.add_spacing(8)
        self._tb_crop = self._bar.add_toggle(
            "prep_crop", label('bginp.crop_tip'), self._on_crop_toggled)
        self._tb_resize = self._bar.add_toggle(
            "prep_resize", label('bginp.resize_tip'), self._on_resize_toggled)
        self._btn_prep_reset = self._bar.add_action(
            "prep_reset", label('bginp.prep_reset_tip'), self._on_prep_reset)
        self._crop_cancelled = False   # Échap / changement de fond : pas d'application
        self._src_size = (0, 0)        # taille du PNG source, lue à la sélection
        self._view.prepare_live.connect(self._bar.set_canvas_size)
        self._view.resize_released.connect(self._on_resize_released)
        self._view.crop_finished.connect(self._on_crop_finished)
        self._view.zoom_changed.connect(self._bar.set_zoom)
        self._view.cursor_moved.connect(self._on_cursor_moved)
        self._bar.set_zoom(self._view._zoom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._bar)
        layout.addWidget(self._view)

        # Bandeau flottant de sélection de la palette de peinture (bas-centre,
        # même widget que Scene Manager/Sprite Editor — cf. palette_bank_strip).
        self._paint_strip = PaletteBankStrip(label('common.no_palette'), self)
        self._paint_strip.selected.connect(self.set_active_palette)
        self._paint_strip.setVisible(False)
        self._paint_strip.raise_()

        self._toolbar = BgInpaintToolbar(self)
        self._toolbar.min_y = BAR_HEIGHT
        self._toolbar.move(10, BAR_HEIGHT + 10)
        self._toolbar.tool_changed.connect(self._view.set_tool)
        self._toolbar.raise_()

        # Overlay « Compression… » (compression hors-thread — voir screen).
        self._busy = QLabel(label('bginp.compressing'), self)
        self._busy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._busy.setStyleSheet(
            f"background:rgba(0,0,0,160); color:#eeeeee; font-family:{T.UI_STACK};"
            "font-size:13px; border-radius:6px; padding:10px 20px;"
        )
        self._busy.hide()

        # Overlays d'infos : infos read-only du fond (bas-gauche) + warnings de
        # validation empilés (haut-droite). Alimentés par l'inspecteur via
        # set_overlays() ; repositionnés au resize.
        self._info_ov = self._make_overlay(Qt.AlignmentFlag.AlignLeft)
        self._warn_ov = self._make_overlay(Qt.AlignmentFlag.AlignRight)

        # ── Superpositions par type : géométrie éditée au canvas ──
        self._view.slice_dragged.connect(self._on_slice_dragged)
        self._view.slice_released.connect(self._persist_host)
        self._view.anim_dropped.connect(self._on_anim_dropped)
        self._view.placement_moved.connect(self._on_placement_moved)
        self._view.placement_deleted.connect(self._on_placement_deleted)
        self._view.placement_selected.connect(self.placement_selected)

        # Horloge de lecture. Un seul timer pour tout le canvas : la planche en
        # cours d'édition et les fonds posés avancent sur la MÊME base de temps,
        # sans quoi deux aperçus de la même animation se décaleraient.
        self._clock = QTimer(self)
        self._clock.setInterval(self._TICK_MS)
        self._clock.timeout.connect(self._on_tick)

    def _make_overlay(self, halign) -> QLabel:
        l = _HoverOverlay(self)
        l.setTextFormat(Qt.TextFormat.RichText)
        l.setAlignment(halign | Qt.AlignmentFlag.AlignTop)
        l.setStyleSheet(
            f"background:rgba(12,12,15,215); color:#e6e6e6; font-family:{T.UI_STACK};"
            "font-size:11px; border-radius:5px; padding:5px 8px;"
        )
        l.hide()
        return l

    def set_overlays(self, info_lines: list, warn_lines: list):
        """Infos read-only (bas-gauche) + warnings (haut-droite). `info_lines` =
        list[str] ; `warn_lines` = list[(texte_html, couleur)]."""
        if info_lines:
            self._info_ov.setText("<br>".join(info_lines))
            self._info_ov.adjustSize(); self._info_ov.show()
        else:
            self._info_ov.hide()
        if warn_lines:
            self._warn_ov.setText("<br>".join(
                f"<span style='color:{c};'>{t}</span>" for t, c in warn_lines))
            self._warn_ov.adjustSize(); self._warn_ov.show()
        else:
            self._warn_ov.hide()
        self._reposition_overlays()

    def _reposition_overlays(self):
        # Les flottants sont enfants du panneau entier : décaler du haut pour ne
        # pas recouvrir la barre.
        m = 10
        top = BAR_HEIGHT + m
        self._info_ov.move(m, max(top, self.height() - self._info_ov.height() - m))
        self._warn_ov.move(max(m, self.width() - self._warn_ov.width() - m), top)
        self._info_ov.raise_(); self._warn_ov.raise_()

    def set_busy(self, on: bool, text: str = label('bginp.compressing')):
        self._busy.setText(text)
        self._busy.setVisible(on)
        if on:
            self._busy.adjustSize()
            self._center_busy()
            self._busy.raise_()

    def _center_busy(self):
        self._busy.move((self.width() - self._busy.width()) // 2,
                        BAR_HEIGHT + (self.height() - BAR_HEIGHT - self._busy.height()) // 2)

    def _on_cursor_moved(self, x: int, y: int):
        self._bar.set_cursor_px(*((None, None) if x < 0 else (x, y)))

    # ── Préparation de la source ─────────────────────────────────
    # Deux gestes, une seule sortie : `prepare_requested(crop, size)`. Le
    # recadrage s'applique à la sortie du mode (Entrée ou bascule) — pendant qu'on
    # règle, la vue montre la source, pas l'encodage, donc rien à recompresser à
    # chaque poignée. Le redimensionnement, lui, s'applique au relâchement : c'est
    # l'image encodée qu'il montre.

    def _prep_available(self) -> bool:
        ba = self._ba
        return bool(ba and not ba.is_ui and not ba.is_animated and ba.image_name()
                    and (ba.tileset or ba.bitmap) and self._src_size[0])

    def _read_source_size(self) -> tuple:
        path = self._source_png_path()
        if path is None or not path.exists():
            return (0, 0)
        try:
            from PIL import Image
            with Image.open(path) as im:
                return im.size
        except Exception:
            return (0, 0)

    def _prepared_size(self) -> tuple:
        """Taille de l'image préparée, avant le rembourrage à un multiple de 8."""
        ba = self._ba
        if ba.import_size:
            return tuple(ba.import_size)
        if ba.import_crop:
            return tuple(ba.import_crop[2:])
        return self._src_size

    @staticmethod
    def _set_checked(btn, on: bool):
        btn.blockSignals(True)
        btn.setChecked(on)
        btn.blockSignals(False)

    def _refresh_prepare_ui(self):
        """Boutons et poignées d'après l'état du fond courant."""
        ok = self._prep_available()
        for b in (self._tb_crop, self._tb_resize):
            b.setEnabled(ok)
        self._btn_prep_reset.setEnabled(
            ok and bool(self._ba.import_crop or self._ba.import_size))
        if not ok:
            self._set_checked(self._tb_crop, False)
            self._set_checked(self._tb_resize, False)
            self._view.end_crop()
            self._view.end_resize()
        elif self._tb_resize.isChecked():
            self._view.begin_resize(self._prepared_size())

    def _cancel_prepare_modes(self):
        """Quitte recadrage/redimensionnement sans rien appliquer (autre fond
        choisi, réinitialisation)."""
        if self._tb_crop.isChecked():
            self._crop_cancelled = True
            self._tb_crop.setChecked(False)
        if self._tb_resize.isChecked():
            self._tb_resize.setChecked(False)

    def _on_crop_toggled(self, on: bool):
        if on:
            if self._tb_resize.isChecked():
                self._tb_resize.setChecked(False)
            if not self._view.begin_crop(self._source_png_path(), self._ba.import_crop):
                self._set_checked(self._tb_crop, False)
                return
            self._bar.set_canvas_size(*self._src_size)
            self._view.setFocus()
            return
        rect = self._view.end_crop()
        self._bar.set_canvas_size(*self._ctrl.image_size())
        cancelled, self._crop_cancelled = self._crop_cancelled, False
        if rect is not None and not cancelled:
            self._apply_crop(rect)

    def _on_crop_finished(self, accept: bool):
        self._crop_cancelled = not accept
        self._tb_crop.setChecked(False)

    def _apply_crop(self, rect: tuple):
        sw, sh = self._src_size
        crop = None if tuple(rect) == (0, 0, sw, sh) else tuple(rect)
        old = self._ba.import_crop
        if crop == old:
            return
        # Recadrer ne change pas l'échelle : une taille déjà réglée suit le
        # nouveau cadre, sinon le fond changerait de grain à chaque coup de ciseaux.
        size = self._ba.import_size
        if size:
            ow, oh = old[2:] if old else (sw, sh)
            nw, nh = crop[2:] if crop else (sw, sh)
            size = (max(1, round(nw * size[0] / ow)), max(1, round(nh * size[1] / oh)))
        self.prepare_requested.emit(crop, size)

    def _on_resize_toggled(self, on: bool):
        if not on:
            self._view.end_resize()
            return
        if self._tb_crop.isChecked():
            self._tb_crop.setChecked(False)   # applique le recadrage en cours
        self._view.begin_resize(self._prepared_size())

    def _on_resize_released(self, w: int, h: int):
        crop = self._ba.import_crop
        base = tuple(crop[2:]) if crop else self._src_size
        size = None if (w, h) == base else (w, h)
        if size != self._ba.import_size:
            self.prepare_requested.emit(crop, size)

    def _on_prep_reset(self):
        self._cancel_prepare_modes()
        self.prepare_requested.emit(None, None)

    # ── Édition externe ──────────────────────────────────────────

    def _source_png_path(self):
        """PNG source du fond courant (sur disque), ou None."""
        if not (self._project and self._ba):
            return None
        img = self._ba.image_name()
        return (self._project.background_images_dir / img) if img else None

    def _on_edit_image(self):
        path = self._source_png_path()
        if path is not None:
            external_editor.open_image(path, self)

    def _on_edit_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        cur = external_editor.get_configured_editor()
        act_choose = menu.addAction(label('common.choose_editor'))
        act_default = menu.addAction(label('common.use_default'))
        act_default.setEnabled(bool(cur))
        chosen = menu.exec(self._btn_edit.mapToGlobal(pos))
        if chosen == act_choose:
            external_editor.choose_editor(self)
        elif chosen == act_default:
            external_editor.use_system_default()

    def _position_paint_strip(self):
        """Centre le bandeau en bas du panneau. À la sélection d'un fond au
        démarrage, le splitter n'a pas encore attribué sa largeur finale au
        canvas : on repositionne aussi au tour de boucle suivant (et à chaque
        resize) pour que le bandeau ne reste pas calé sur une géométrie périmée."""
        strip = self._paint_strip
        strip.reflow()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(BAR_HEIGHT, self.height() - strip.height() - 12)
        strip.move(x, y)

    @staticmethod
    def _palette_entries(palettes: list) -> list:
        return [(i, label('common.palette_i', i=i), cols) for i, cols in enumerate(palettes)]

    # ── Superpositions par type ──────────────────────────────────

    def reload_geometry(self):
        """Réaligne guides, grille de frames et placements sur le modèle. Appelé
        chaque fois qu'un réglage de découpe change, d'où qu'il vienne."""
        ba = self._ba
        v = self._view
        is_nine = bool(ba and ba.kind == KIND_UI and ba.ui_role == UI_ROLE_NINE)
        v.slices.setVisible(is_nine)
        if is_nine:
            v.slices.set_margins({k: getattr(ba, k) for k in
                                  ("slice_left", "slice_right",
                                   "slice_top", "slice_bottom")})
        is_anim = bool(ba and ba.kind == KIND_ANIMATED)
        v.frames.setVisible(is_anim)
        if is_anim:
            cols, rows = ba.frame_grid()
            v.frames.set_grid(*ba.pixel_size(), *ba.frame_size(), cols, rows)
        v.placements.set_items(self._placement_items())
        self._sync_clock()

    def _placement_items(self) -> list:
        """Ce qu'il faut pour DESSINER chaque fond posé : la planche rendue une
        fois, sa découpe et sa cadence. Résolu ici et pas dans l'overlay — un
        item graphique n'a pas à connaître le projet, et la planche ne se rend
        qu'au (re)chargement plutôt qu'à chaque frame."""
        ba, p = self._ba, self._project
        if ba is None or p is None:
            return []
        cache: dict = {}
        out: list = []
        for pl in ba.animations:
            src = p.get_background(pl.animated_name)
            if src is None:
                out.append({"pl": pl, "pix": None, "w": 8, "h": 8,
                            "fw": 8, "fh": 8, "cols": 1, "n": 1,
                            "speed": 8, "start_frame": 0, "loop": True})
                continue
            if pl.animated_name not in cache:
                cache[pl.animated_name] = asset_pixmap(src)
            fw, fh = src.frame_size()
            cols, _rows = src.frame_grid()
            out.append({"pl": pl, "pix": cache[pl.animated_name],
                        "w": fw, "h": fh, "fw": fw, "fh": fh,
                        "cols": max(1, cols), "n": max(1, src.frame_count()),
                        # Cadence et départ PROPRES À LA COPIE — mêmes lectures
                        # que le build (cf. BackgroundAnimation.effective_speed).
                        "speed": pl.effective_speed(src),
                        "start_frame": max(0, int(getattr(pl, "start_frame", 0) or 0)),
                        "loop": bool(src.loop)})
        return out

    def _sync_clock(self):
        """L'horloge ne tourne que s'il y a quelque chose à animer. Un timer à
        60 Hz qui repeint un décor immobile brûlerait un cœur pour rien."""
        ba = self._ba
        playing = bool(ba and (
            (ba.kind == KIND_ANIMATED and ba.frame_count() > 1)
            or ba.animations))
        if playing and not self._clock.isActive():
            self._clock.start()
        elif not playing and self._clock.isActive():
            self._clock.stop()

    def _on_tick(self):
        self._tick += 1
        self._view.placements.set_tick(self._tick)
        ba = self._ba
        if ba is not None and ba.kind == KIND_ANIMATED:
            n = max(1, ba.frame_count())
            step = self._tick // max(1, ba.speed)
            self._view.frames.set_current(step % n if ba.loop else min(step, n - 1))

    # ── Écriture du modèle depuis le canvas ──────────────────────

    def _on_slice_dragged(self, key: str, value: int):
        """Guide glissé : on écrit le modèle EN CONTINU (le rendu doit suivre le
        curseur) mais on ne persiste qu'au relâchement — un fichier réécrit à
        chaque pixel ferait tourner le watcher en boucle."""
        if self._ba is None:
            return
        setattr(self._ba, key, int(value))
        self._view.slices.set_margins({key: int(value)})
        self.slices_dragged.emit({key: int(value)})

    def _persist_host(self):
        if not (self._project and self._ba):
            return
        from core.command_dispatcher import get_dispatcher
        with get_dispatcher().suspended():
            self._project.backgrounds.save(self._ba)
        get_dispatcher().notify_background_changed(self._ba)

    def _on_anim_dropped(self, name: str, x: int, y: int):
        if not (self._project and self._ba):
            return
        src = self._project.get_background(name)
        if src is None or src.kind != KIND_ANIMATED:
            return
        if src is self._ba:
            return          # se poser sur soi-même : la lecture boucle sur elle-même
        fw, fh = src.frame_size()
        pl = BackgroundAnimation(animated_name=name,
                                 x=_snap8(x - fw // 2), y=_snap8(y - fh // 2))
        self._ba.animations.append(pl)
        self._persist_host()
        self.reload_geometry()
        self._view.placements.set_selected(pl)
        self.placement_selected.emit(pl)
        self.placements_changed.emit()

    def _on_placement_moved(self, pl, x: int, y: int):
        pl.x, pl.y = int(x), int(y)
        self._view.placements.update()

    def _on_placement_deleted(self, pl):
        if self._ba is None or pl not in self._ba.animations:
            return
        self._ba.animations.remove(pl)
        self._persist_host()
        self._view.placements.set_selected(None)
        self.placement_selected.emit(None)
        self.reload_geometry()
        self.placements_changed.emit()

    def load(self, project, ba):
        self._cancel_prepare_modes()   # avant de changer de fond : rien n'est appliqué
        self._ba = ba
        self._project = project
        self._view.placements.set_selected(None)
        self.placement_selected.emit(None)   # referme la section PLACEMENT
        self._ctrl.set_context(project, ba)
        # Inpainting = tuilé 4bpp uniquement. En 8bpp (une palette 256) et en
        # bitmap (Mode 4) : peinture désactivée, toolbar + bande masquées (aperçu seul).
        paintable = bool(ba and getattr(ba, "mode", "tiled") == "tiled"
                         and getattr(ba, "bpp", 4) == 4)
        self._ctrl.set_paint_enabled(paintable)
        self._toolbar.setVisible(paintable)
        if paintable:
            self._paint_strip.load(self._palette_entries(ba.palettes), active=0)
            self._paint_strip.setVisible(True)
            self._position_paint_strip()
            QTimer.singleShot(0, self._position_paint_strip)
            self._ctrl.set_active_palette(self._paint_strip.active())
        else:
            self._paint_strip.setVisible(False)
        self._view.load_background()
        self.reload_geometry()
        self._bar.set_canvas_size(*self._ctrl.image_size())
        self._bar.set_cursor_px(None, None)
        self._btn_edit.setEnabled(bool(ba and ba.image_name()))
        self._src_size = self._read_source_size()
        self._refresh_prepare_ui()

    def set_active_palette(self, idx: int):
        self._ctrl.set_active_palette(idx)

    def reload(self):
        """Re-render après édition des palettes (inspecteur) — reconstruit aussi
        la bande de peinture (la liste des palettes a pu changer) puis met à jour
        le pixmap via on_rendered, sans réinitialiser le zoom."""
        if self._ba is not None and self._ctrl.paintable:
            cur = self._paint_strip.active()
            self._paint_strip.load(self._palette_entries(self._ba.palettes), active=cur)
            self._position_paint_strip()
            self._ctrl.set_active_palette(self._paint_strip.active())
        self._ctrl.reload_render()
        self._view.sync_image_size()
        self._bar.set_canvas_size(*self._ctrl.image_size())
        self.reload_geometry()
        self._src_size = self._read_source_size()
        self._refresh_prepare_ui()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self._toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(BAR_HEIGHT, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        # isVisibleTo (et non isVisible) : au démarrage, les resize arrivent avant
        # que la fenêtre soit montrée — isVisible() serait encore False et le
        # bandeau resterait figé sur la géométrie initiale du splitter.
        if self._paint_strip.isVisibleTo(self):
            self._position_paint_strip()
            self._paint_strip.raise_()
        self._reposition_overlays()
        if self._busy.isVisible():
            self._center_busy()
