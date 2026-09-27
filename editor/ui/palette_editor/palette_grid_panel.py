"""ui/palette_editor/palette_grid_panel.py — zone centre : grille de swatches de la banque active.

Propriétaire de l'ÉTAT d'édition (banque affichée, slot actif, sélection) et de
toutes les écritures dans la palette (couleur unique, rampe, vider, supprimer),
qui passent systématiquement par l'historique. L'inspecteur de couleur (panneau
droit) n'est qu'une vue : il reçoit `color_selected` et renvoie `apply_color()`.

Zoom : mêmes gestes que les canvas de l'app (molette = zoom ×1.15, boutons
−/%/+/ajuster par crans, pan au clic-central). Ici pas de QGraphicsView — la
grille est faite de vrais widgets : zoomer = redimensionner les cases en place
dans un QScrollArea, sans reconstruire la grille (la sélection et les
animations de contour survivent au zoom).
"""
from __future__ import annotations

import colorsys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QSpinBox,
    QMenu, QMessageBox, QFileDialog, QDialog, QComboBox, QDialogButtonBox,
    QScrollArea, QPushButton,
)
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtCore import Qt, QEvent, QPoint, QSize, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common import icons
from ui.common.labels import label

from core.models.palette import PaletteBank
from core.project import Project
from core.models.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
from core.history import get_history, SetPaletteColorCmd, SetPaletteColorsCmd

from .palette_file_io import serialize_palette
from .swatch_button import SwatchButton, SWATCH_CELL_16, SWATCH_CELL_256, SWATCH_GAP

# Crans des boutons −/+ (la molette, elle, est continue) — même esprit que
# scene_canvas / bg_inpaint_canvas, recalé sur des cases déjà grandes au repos.
_ZOOM_LEVELS = [0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
_ZOOM_MIN, _ZOOM_MAX = _ZOOM_LEVELS[0], _ZOOM_LEVELS[-1]
_COORD_ROW_W = 22       # largeur de la colonne d'index (vue 256), à zoom 1


class PaletteGridPanel(QWidget):
    """Zone centre : entête (nom · taille · export) + grille de swatches."""

    color_selected  = pyqtSignal(int, int)   # index, valeur BGR555 du slot actif
    editing_enabled = pyqtSignal(bool)       # une couleur est éditable → afficher l'inspecteur
    catalog_changed = pyqtSignal()           # nom/icône de banque à rafraîchir dans le finder
    bank_focus_requested = pyqtSignal(str)   # undo/redo visant une banque non affichée
    hex_focus_requested  = pyqtSignal()      # Entrée dans la grille → curseur au champ HEX

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._bank_name: Optional[str] = None
        self._active_index: Optional[int] = None    # slot édité (curseur)
        self._anchor_index: Optional[int] = None     # ancre de la sélection au drag
        self._sel_range: Optional[tuple[int, int]] = None   # (lo, hi) contigu, ou None (mode rect)
        self._selected_set: set[int] = set()         # indices actuellement surlignés
        self._active_drawn: Optional[int] = None      # case au liseré meneur actuel
        self._dragging = False                       # sélection au cliqué-glissé en cours
        self._drag_mode = "rect"                     # "rect" (défaut) | "range" (Shift+drag)
        self._drag_grab: Optional[SwatchButton] = None
        self._zoom = 1.0                             # facteur appliqué à la case de base
        self._coord_labels: list[tuple[QLabel, bool]] = []   # (label, est_une_ligne)
        self._pan_from: Optional[QPoint] = None      # pan au clic-central
        self._pan_scroll: tuple[int, int] = (0, 0)
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        center_hdr = QFrame()
        center_hdr.setFixedHeight(32)
        center_hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        chl = QHBoxLayout(center_hdr)
        chl.setContentsMargins(14, 0, 8, 0)
        chl.setSpacing(10)
        self._title = QLabel("")
        self._title.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};")
        chl.addWidget(self._title)
        self._size_lbl = QLabel("")
        self._size_lbl.setFont(QFont(T.UI, T.SM))
        self._size_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        chl.addWidget(self._size_lbl)
        chl.addStretch()

        # Barre d'actions sur la palette (point D) : import/export interop +
        # génération de rampe (reste dans les index existants, ne réordonne pas).
        self._tools = QWidget()
        tl = QHBoxLayout(self._tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)

        # Zoom : mêmes contrôles et mêmes libellés que CanvasTopBar (−/%/+/ajuster).
        tl.addWidget(self._zoom_btn("zoom_out", label("palgrid.zoom_out_tip"),
                                    lambda: self.zoom_step(-1)))
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setFont(QFont(T.MONO, T.SM))
        self._zoom_lbl.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._zoom_lbl.setFixedWidth(42)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.addWidget(self._zoom_lbl)
        tl.addWidget(self._zoom_btn("zoom_in", label("palgrid.zoom_in_tip"),
                                    lambda: self.zoom_step(+1)))
        tl.addWidget(self._zoom_btn("fit_page", label("palgrid.fit_tip"), self.fit))
        tl.addSpacing(10)

        self._btn_export = W.btn_ghost(label("palgrid.export"))
        self._btn_export.setToolTip(label("palgrid.export_tip"))
        self._btn_export.clicked.connect(self._export_palette)
        tl.addWidget(self._btn_export)
        chl.addWidget(self._tools)
        root.addWidget(center_hdr)

        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 16, 16, 16)
        il.setSpacing(14)

        self._empty_lbl = QLabel(label("palgrid.empty"))
        self._empty_lbl.setFont(QFont(T.UI, T.MD))
        self._empty_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Grille de swatches. Conteneur focusable pour la navigation clavier
        # (flèches, Ctrl+C/V), placé dans un QScrollArea qui le CENTRE tant qu'il
        # tient dans la vue et fait apparaître des barres dès qu'on zoome au-delà.
        self._swatch_container = QWidget()
        self._swatch_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._swatch_container.installEventFilter(self)
        self._swatch_grid = QGridLayout(self._swatch_container)
        self._swatch_grid.setContentsMargins(0, 0, 0, 0)
        self._swatch_grid.setSpacing(SWATCH_GAP)
        self._swatch_grid.setSizeConstraint(QGridLayout.SizeConstraint.SetFixedSize)
        self._swatch_btns: list[SwatchButton] = []

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)      # le conteneur garde sa taille naturelle
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(QSS.scroll_area + QSS.scrollbar)
        self._scroll.setWidget(self._swatch_container)
        self._scroll.viewport().installEventFilter(self)   # molette = zoom, clic-central = pan

        il.addWidget(self._empty_lbl, 1)
        il.addWidget(self._scroll, 1)

        root.addWidget(inner, 1)
        self.show_empty()

    def _zoom_btn(self, icon_key: str, tip: str, slot) -> QPushButton:
        """Bouton iconifié du groupe zoom — même fabrication que CanvasTopBar."""
        b = QPushButton()
        b.setIcon(icons.get(icon_key, C.TEXT_NORM))
        b.setIconSize(QSize(15, 15))
        b.setFixedSize(22, 22)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;border-radius:3px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
        )
        b.clicked.connect(slot)
        return b

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._bank_name = None
        self.show_empty()

    @property
    def bank_name(self) -> Optional[str]:
        """Nom de la banque actuellement affichée (None si aucune)."""
        return self._bank_name

    def _current_bank(self) -> Optional[PaletteBank]:
        if not self._project or self._bank_name is None:
            return None
        return self._project.palettes.get(self._bank_name)

    def show_bank(self, name: str):
        self._bank_name = name
        bank = self._current_bank()
        if bank is None:
            self.show_empty()
            return

        self._empty_lbl.setVisible(False)
        self._scroll.setVisible(True)
        self._tools.setVisible(True)
        size = getattr(bank, "size", 16)
        self._title.setText(bank.name)
        self._size_lbl.setText(label("palgrid.size", n=size,
                                     bpp="8bpp" if size == 256 else "4bpp"))

        self._active_index = 1 if len(bank.colors) > 1 else None
        self._anchor_index = self._active_index
        self._sel_range = None
        self._render_swatches(bank, selectable=True)
        self.editing_enabled.emit(bool(bank.colors))
        if self._active_index is not None:
            self.color_selected.emit(self._active_index, bank.colors[self._active_index])

    def show_empty(self):
        self._empty_lbl.setVisible(True)
        self._scroll.setVisible(False)
        self._tools.setVisible(False)
        self._title.setText("")
        self._size_lbl.setText("")
        self.editing_enabled.emit(False)
        self._clear_swatches()

    def on_bank_deleted(self):
        if self._bank_name is None or not self._current_bank():
            self.show_empty()

    def focus_grid(self):
        """Rend le focus clavier à la grille (flèches, Ctrl+C/V)."""
        self._swatch_container.setFocus(Qt.FocusReason.OtherFocusReason)

    # ── Zoom ──────────────────────────────────────────────────────
    # La grille est faite de widgets : zoomer = redonner une taille aux cases
    # déjà en place (pas de reconstruction → sélection et animations intactes).

    @property
    def zoom(self) -> float:
        return self._zoom

    def _cell(self, size: int) -> int:
        """Côté d'une case, en pixels, pour la taille de banque donnée."""
        base = SWATCH_CELL_256 if size == 256 else SWATCH_CELL_16
        return max(8, round(base * self._zoom))

    def set_zoom(self, zoom: float, anchor: Optional[QPoint] = None):
        """Applique un facteur (borné). `anchor` = point de la vue à garder sous
        le curseur — sinon le contenu grandit depuis le coin haut-gauche et on
        « perd » la case qu'on visait en zoomant."""
        zoom = max(_ZOOM_MIN, min(float(zoom), _ZOOM_MAX))
        if abs(zoom - self._zoom) < 1e-3:
            return
        old = self._zoom
        self._zoom = zoom
        self._zoom_lbl.setText(f"{round(zoom * 100)}%")

        bank = self._current_bank()
        if bank is None:
            return
        size = getattr(bank, "size", 16)
        cell = self._cell(size)
        # Point visé, en coordonnées du conteneur, AVANT redimensionnement.
        target = (self._swatch_container.mapFrom(self._scroll.viewport(), anchor)
                  if anchor is not None else None)

        for btn in self._swatch_btns:
            btn.setFixedSize(cell, cell)
        row_w = max(14, round(_COORD_ROW_W * self._zoom))
        for lab, is_row in self._coord_labels:
            lab.setFixedWidth(row_w if is_row else cell)
        self._swatch_container.adjustSize()

        if target is not None:
            ratio = zoom / old
            hbar, vbar = self._scroll.horizontalScrollBar(), self._scroll.verticalScrollBar()
            hbar.setValue(round(target.x() * ratio - anchor.x()))
            vbar.setValue(round(target.y() * ratio - anchor.y()))

    def zoom_step(self, direction: int):
        """Zoom par crans (boutons −/+) : cran le plus proche, puis ±1."""
        idx = min(range(len(_ZOOM_LEVELS)), key=lambda i: abs(_ZOOM_LEVELS[i] - self._zoom))
        self.set_zoom(_ZOOM_LEVELS[max(0, min(idx + direction, len(_ZOOM_LEVELS) - 1))])

    def fit(self):
        """Ajuste le zoom pour que toute la palette tienne dans la vue.

        Par approximations successives : la taille du conteneur n'est PAS
        proportionnelle au zoom (les espacements de la grille et la colonne
        d'index ont une part fixe), et la vue elle-même grandit quand les barres
        de défilement disparaissent. Une simple règle de trois laisse donc
        dépasser — 2-3 passes suffisent à converger."""
        if self._current_bank() is None:
            return
        for _ in range(4):
            hint = self._swatch_container.sizeHint()
            vp = self._scroll.viewport()
            if hint.width() <= 0 or hint.height() <= 0:
                return
            ratio = min((vp.width() - 8) / hint.width(), (vp.height() - 8) / hint.height())
            if 0.99 <= ratio <= 1.0:
                return                     # ça tient déjà, au poil près
            before = self._zoom
            self.set_zoom(self._zoom * ratio)
            if self._zoom == before:       # borne atteinte : inutile d'insister
                return

    # ── Actions palette : export / rampe (point D) ───────────────────

    def _export_palette(self):
        bank = self._current_bank()
        if not bank:
            return
        path, sel = QFileDialog.getSaveFileName(
            self, label("palgrid.export_dialog"), bank.name,
            label("palgrid.export_filter"))
        if not path:
            return
        low = path.lower()
        fmt = ("pal" if low.endswith(".pal") or "JASC" in sel else
               "hex" if low.endswith(".txt") or "Hex" in sel else "gpl")
        rgb = [bgr555_to_rgb888(c) for c in bank.colors]
        try:
            Path(path).write_text(serialize_palette(bank.name, rgb, fmt), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, label("palgrid.export"),
                                label("palgrid.write_failed", error=e))

    def _make_ramp(self):
        """Interpole un dégradé entre deux index (inclus) — les extrémités
        gardent leur couleur, on ne remplit que l'intervalle. Bornes = plage
        sélectionnée (shift+clic). Reste dans les index existants (ne réordonne
        rien)."""
        bank = self._current_bank()
        if not bank or not self._sel_range:
            return
        n = len(bank.colors)
        lo, hi = self._sel_range
        dlg = QDialog(self)
        dlg.setWindowTitle(label("palgrid.ramp_title"))
        v = QVBoxLayout(dlg)
        row = QHBoxLayout()
        sa = QSpinBox(); sa.setRange(1, n - 1); sa.setValue(lo)
        sb = QSpinBox(); sb.setRange(1, n - 1); sb.setValue(hi)
        row.addWidget(QLabel(label("palgrid.from_index"))); row.addWidget(sa)
        row.addWidget(QLabel(label("palgrid.to"))); row.addWidget(sb)
        v.addLayout(row)
        space = QComboBox()
        space.addItems([label("palgrid.ramp_rgb"), label("palgrid.ramp_hsl")])
        v.addWidget(space)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        a, b = sorted((sa.value(), sb.value()))
        if a == b:
            return
        ca = bgr555_to_rgb888(bank.colors[a])
        cb = bgr555_to_rgb888(bank.colors[b])
        use_hsl = space.currentIndex() == 1
        # Delta {index: (avant, après)} plutôt qu'une écriture directe : la rampe
        # devient UNE entrée d'undo, comme « Vider ».
        delta: dict[int, tuple[int, int]] = {}
        for i in range(a, b + 1):
            t = (i - a) / (b - a)
            if use_hsl:
                ha, la, sa_ = colorsys.rgb_to_hls(*[x / 255 for x in ca])
                hb, lb, sb_ = colorsys.rgb_to_hls(*[x / 255 for x in cb])
                dh = ((hb - ha + 0.5) % 1.0) - 0.5      # teinte : plus court chemin
                r, g, bl = colorsys.hls_to_rgb((ha + dh * t) % 1.0,
                                               la + (lb - la) * t, sa_ + (sb_ - sa_) * t)
                rgb = (round(r * 255), round(g * 255), round(bl * 255))
            else:
                rgb = tuple(round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
            new = rgb888_to_bgr555(*rgb)
            if new != bank.colors[i]:
                delta[i] = (bank.colors[i], new)
        if not delta:
            return
        get_history().push(
            SetPaletteColorsCmd(bank, delta, self._persist_bank, "Generate a ramp"))

    # ── Swatches ──────────────────────────────────────────────────

    def _clear_swatches(self):
        while self._swatch_grid.count():
            item = self._swatch_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._swatch_btns.clear()
        self._coord_labels.clear()
        self._selected_set = set()

    def _style_swatch(self, btn: SwatchButton, index: int, color: int,
                      selected: bool, active: bool = False, animate: bool = True):
        # Délègue au SwatchButton (peinture custom) : remplissage + contour animé
        # blanc (actif) / vert (sélection). `active` = curseur / meneur d'une plage,
        # `selected` = membre d'une multi-sélection.
        btn.set_swatch(bgr555_to_rgb888(color), selected=selected, active=active,
                       animate=animate)

    def _coord_label(self, text: str, width: int, is_row: bool) -> QLabel:
        lab = QLabel(text)
        lab.setFixedWidth(width)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFont(QFont(T.MONO, T.XS))
        lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        # Mémorisés pour suivre le zoom (les colonnes suivent la case, la colonne
        # d'index a sa propre largeur).
        self._coord_labels.append((lab, is_row))
        return lab

    def _render_swatches(self, bank: PaletteBank, selectable: bool):
        self._clear_swatches()
        # Grille carrée harmonisée : cellules de MÊME taille en 16 (4×4) et 256
        # (16×16). En 256, la rangée/colonne 0 porte des coordonnées hexa (carte
        # lisible plutôt que mur). Swatches sans bordure (débruitage) ; index 0 =
        # transparent (hardware GBA) → damier, jamais cliquable.
        size = getattr(bank, "size", 16)
        cols = 16 if size == 256 else 4
        cw = ch = self._cell(size)              # taille de base × zoom courant
        off = 1 if size == 256 else 0
        if size == 256:
            hexd = "0123456789ABCDEF"
            row_w = max(14, round(_COORD_ROW_W * self._zoom))
            for c in range(16):
                self._swatch_grid.addWidget(self._coord_label(hexd[c], cw, False), 0, c + 1)
            for r in range(16):
                self._swatch_grid.addWidget(
                    self._coord_label(f"{r * 16:02X}", row_w, True), r + 1, 0)
        for i, c in enumerate(bank.colors):
            btn = SwatchButton()
            btn.setFixedSize(cw, ch)
            if i == 0:
                btn.set_checker()              # damier transparence (hardware GBA)
                btn.setEnabled(False)
                btn.setToolTip(label("palgrid.reserved_tip"))
            else:
                # La case active (couleur éditée) porte le contour blanc.
                is_active = bool(selectable and i == self._active_index)
                self._style_swatch(btn, i, c, selected=is_active, active=is_active)
                if selectable:
                    btn.installEventFilter(self)   # sélection au cliqué-glissé
                else:
                    btn.setEnabled(False)
            self._swatch_grid.addWidget(btn, i // cols + off, i % cols + off)
            self._swatch_btns.append(btn)
        self._selected_set = ({self._active_index}
                              if selectable and self._active_index else set())
        self._active_drawn = self._active_index if self._selected_set else None

    # ── Sélection au cliqué-glissé (drag) ────────────────────────────

    def eventFilter(self, obj, event):
        """Souris déléguée par les swatches : clic-gauche = début de sélection
        (drag = rectangle, Shift+drag = plage contiguë par index), relâcher =
        fin, clic-droit = menu. Clavier délégué par le conteneur : flèches
        (navigation, + Shift pour étendre la plage), Ctrl+C/V, Suppr, Entrée.
        Molette (n'importe où sur la zone) = zoom, clic-central = pan — mêmes
        gestes que les canvas de l'app."""
        et = event.type()
        if et == QEvent.Type.Wheel:
            self._handle_wheel(event)
            return True
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.MiddleButton:
            self._begin_pan(event.globalPosition().toPoint())
            return True
        if self._pan_from is not None:
            if et == QEvent.Type.MouseMove:
                self._pan_to(event.globalPosition().toPoint())
                return True
            if (et == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.MiddleButton):
                self._end_pan()
                return True

        if et == QEvent.Type.KeyPress and obj is self._swatch_container:
            if self._handle_grid_key(event):
                return True
        elif et == QEvent.Type.MouseButtonPress and obj in self._swatch_btns:
            idx = self._swatch_btns.index(obj)
            if event.button() == Qt.MouseButton.RightButton:
                if self._selected_set:
                    self._show_swatch_menu(event.globalPosition().toPoint())
                    return True
                return False
            if event.button() == Qt.MouseButton.LeftButton and idx >= 1:
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._begin_drag(idx, shift)
                return True
        elif et == QEvent.Type.MouseMove and self._dragging:
            self._drag_to(event.globalPosition().toPoint())
            return True
        elif (et == QEvent.Type.MouseButtonRelease and self._dragging
              and event.button() == Qt.MouseButton.LeftButton):
            self._end_drag()
            return True
        return super().eventFilter(obj, event)

    # ── Molette (zoom) et clic-central (pan) ─────────────────────────

    def _handle_wheel(self, event):
        """Molette = zoom continu ×1.15, ancré sous le curseur (même facteur que
        scene_canvas / bg_inpaint_canvas)."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        vp = self._scroll.viewport()
        anchor = vp.mapFromGlobal(event.globalPosition().toPoint())
        self.set_zoom(self._zoom * factor, anchor=anchor)

    def _begin_pan(self, gpos):
        self._pan_from = gpos
        self._pan_scroll = (self._scroll.horizontalScrollBar().value(),
                            self._scroll.verticalScrollBar().value())
        self._scroll.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _pan_to(self, gpos):
        dx = gpos.x() - self._pan_from.x()
        dy = gpos.y() - self._pan_from.y()
        self._scroll.horizontalScrollBar().setValue(self._pan_scroll[0] - dx)
        self._scroll.verticalScrollBar().setValue(self._pan_scroll[1] - dy)

    def _end_pan(self):
        self._pan_from = None
        self._scroll.viewport().unsetCursor()

    def _handle_grid_key(self, event) -> bool:
        """Navigation clavier dans la grille : flèches (+ shift pour étendre la
        plage), Ctrl+C / Ctrl+V pour copier/coller la couleur active."""
        key, mod = event.key(), event.modifiers()
        if mod & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self._copy_color(); return True
            if key == Qt.Key.Key_V:
                self._paste_color(); return True
            # Ctrl + +/-/0 : zoom au clavier (0 = 100 %).
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_step(+1); return True
            if key == Qt.Key.Key_Minus:
                self.zoom_step(-1); return True
            if key == Qt.Key.Key_0:
                self.set_zoom(1.0); return True
            return False
        bank = self._current_bank()
        if not bank or self._active_index is None:
            return False
        # F : ajuster à la vue (même raccourci que les canvas).
        if key == Qt.Key.Key_F:
            self.fit(); return True
        # Suppr / Backspace : vider le(s) slot(s) sélectionné(s) (0x0000).
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._clear_selected(); return True
        # Entrée : passer au champ HEX pour une saisie numérique rapide.
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.hex_focus_requested.emit(); return True
        size = getattr(bank, "size", 16)
        cols = 16 if size == 256 else 4
        delta = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1,
                 Qt.Key.Key_Up: -cols, Qt.Key.Key_Down: cols}.get(key)
        if delta is None:
            return False
        ni = self._active_index + delta
        if not (1 <= ni < len(bank.colors)):      # ne franchit ni l'index 0 ni les bornes
            return True
        if (mod & Qt.KeyboardModifier.ShiftModifier) and self._anchor_index is not None:
            lo, hi = sorted((self._anchor_index, ni))
            self._sel_range = (lo, hi) if lo != hi else None
            new = {i for i in range(lo, hi + 1) if 1 <= i < len(bank.colors)}
        else:
            self._anchor_index = ni
            self._sel_range = None
            new = {ni}
        self._active_index = ni
        self._apply_selection(bank, new, ni)
        self.color_selected.emit(ni, bank.colors[ni])
        return True

    def _copy_color(self):
        v = self._active_value()
        if v is None:
            return
        r, g, b = bgr555_to_rgb888(v)
        QGuiApplication.clipboard().setText(f"#{r:02X}{g:02X}{b:02X}")

    def _paste_color(self):
        if self._active_index is None:
            return
        t = QGuiApplication.clipboard().text().strip().lstrip("#")
        if len(t) != 6:
            return
        try:
            r, g, b = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        except ValueError:
            return
        self.apply_color(rgb888_to_bgr555(r, g, b))

    def _cell_at_global(self, gpos) -> Optional[int]:
        """Index du swatch sous le curseur (coord. écran) — hit-test géométrique
        sur les boutons (ignore les labels de coordonnées)."""
        local = self._swatch_container.mapFromGlobal(gpos)
        for i, b in enumerate(self._swatch_btns):
            if b.geometry().contains(local):
                return i
        return None

    def _begin_drag(self, index: int, shift: bool = False):
        bank = self._current_bank()
        if not bank or not (1 <= index < len(bank.colors)):
            return
        self._dragging = True
        self._swatch_container.setFocus()      # active la navigation clavier
        n = len(bank.colors)
        if shift and self._anchor_index is not None and 1 <= self._anchor_index < n:
            # Shift+clic (ou shift+drag) : PROLONGE la sélection contiguë depuis
            # l'ancre (dernier clic simple) jusqu'à `index` → tous les index entre
            # les deux extrémités. L'ancre est conservée (pas de reset).
            self._drag_mode = "range"
            lo, hi = sorted((self._anchor_index, index))
            self._sel_range = (lo, hi) if lo != hi else None
            new = {i for i in range(lo, hi + 1) if 1 <= i < n}
        else:
            # Clic simple : nouvelle ancre ; le drag simple fera un rectangle 2D.
            self._drag_mode = "rect"
            self._anchor_index = index
            self._sel_range = None
            new = {index}
        self._active_index = index
        self._apply_selection(bank, new, index)
        self.color_selected.emit(index, bank.colors[index])
        self._drag_grab = self._swatch_btns[index]
        self._drag_grab.grabMouse()

    def _drag_to(self, gpos):
        bank = self._current_bank()
        if not bank or self._anchor_index is None:
            return
        idx = self._cell_at_global(gpos)
        if idx is None or not (1 <= idx < len(bank.colors)) or idx == self._active_index:
            return
        n = len(bank.colors)
        cols = 16 if getattr(bank, "size", 16) == 256 else 4
        if self._drag_mode == "range":
            # Plage contiguë par index (Shift+drag) — sert aussi de base à la rampe.
            lo, hi = sorted((self._anchor_index, idx))
            self._sel_range = (lo, hi) if lo != hi else None
            new = {i for i in range(lo, hi + 1) if 1 <= i < n}
        else:
            # Rectangle 2D (drag simple) — comme les autres canvas. Non contigu
            # par index → pas de rampe (voir menu contextuel). Ignore l'index 0.
            self._sel_range = None
            ar, ac = divmod(self._anchor_index, cols)
            br, bc = divmod(idx, cols)
            r0, r1 = sorted((ar, br))
            c0, c1 = sorted((ac, bc))
            new = {rr * cols + cc
                   for rr in range(r0, r1 + 1) for cc in range(c0, c1 + 1)
                   if 1 <= rr * cols + cc < n}
        self._active_index = idx
        self._apply_selection(bank, new, idx, animate=False)   # move continu → snap
        self.color_selected.emit(idx, bank.colors[idx])

    def _end_drag(self):
        if self._drag_grab is not None:
            self._drag_grab.releaseMouse()
            self._drag_grab = None
        self._dragging = False

    # ── Menu contextuel (clic-droit sur la sélection) ────────────────

    def _show_swatch_menu(self, gpos):
        if not self._selected_set:
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        a_ramp = menu.addAction(label("palgrid.create_ramp"))
        # Rampe = interpolation le long d'index CONTIGUS → uniquement en mode
        # plage (Shift+drag / Shift+flèches), pas sur une sélection rectangle.
        a_ramp.setEnabled(self._sel_range is not None
                          and self._sel_range[1] - self._sel_range[0] >= 2)
        menu.addSeparator()
        a_clear = menu.addAction(label("palgrid.menu_clear"))
        a_del = menu.addAction(label("palgrid.menu_delete"))
        act = menu.exec(gpos)
        if act == a_ramp:
            self._make_ramp()
        elif act == a_clear:
            self._clear_selected()
        elif act == a_del:
            self._delete_selected()

    def _clear_selected(self):
        """Remet les slots sélectionnés à noir (0x0000) — la palette garde sa
        taille et ses index. Undoable en une seule entrée (Ctrl+Z)."""
        bank = self._current_bank()
        if not bank or not self._selected_set:
            return
        delta = {i: (bank.colors[i], 0) for i in self._selected_set
                 if 1 <= i < len(bank.colors) and bank.colors[i] != 0}
        if not delta:
            return
        get_history().push(
            SetPaletteColorsCmd(bank, delta, self._persist_bank, "Clear colors"))

    def _delete_selected(self):
        """Supprime les slots sélectionnés et DÉCALE les suivants vers la gauche ;
        complète la fin en noir pour préserver la taille (16/256) et l'index 0.
        Le décalage est exprimé en delta {index: (avant, après)} — la taille de la
        banque ne change jamais — donc une seule entrée d'undo, comme « Vider »."""
        bank = self._current_bank()
        if not bank or not self._selected_set:
            return
        lo, hi = min(self._selected_set), max(self._selected_set)
        size = getattr(bank, "size", len(bank.colors))
        shifted = bank.colors[:lo] + bank.colors[hi + 1:]
        shifted += [0] * (size - len(shifted))
        delta = {i: (bank.colors[i], shifted[i])
                 for i in range(lo, min(size, len(bank.colors)))
                 if bank.colors[i] != shifted[i]}
        if not delta:
            return
        self._sel_range = None
        self._active_index = min(lo, len(bank.colors) - 1)
        self._anchor_index = self._active_index
        get_history().push(
            SetPaletteColorsCmd(bank, delta, self._persist_bank, "Delete colors"))

    def _apply_selection(self, bank: PaletteBank, new_set: set[int],
                         leader: Optional[int], animate: bool = True):
        """Applique une sélection ARBITRAIRE (rectangle ou plage) en ne re-stylant
        que les cases dont l'état change (diff — crucial en 256 couleurs). La case
        `leader` (curseur actif) porte le liseré blanc ; les autres membres, le
        vert. `animate=False` pour les gros changements (rubber-band, bulk) afin
        d'éviter des dizaines d'animations simultanées."""
        def _restyle(idx):
            if 0 < idx < len(self._swatch_btns) and idx < len(bank.colors):
                self._style_swatch(self._swatch_btns[idx], idx, bank.colors[idx],
                                   selected=(idx in new_set), active=(idx == leader),
                                   animate=animate)

        for idx in self._selected_set - new_set:      # sortis de la sélection
            _restyle(idx)
        for idx in new_set - self._selected_set:       # entrés
            _restyle(idx)
        # Le meneur a bougé à l'intérieur de la sélection : re-styliser l'ancien
        # (rétrogradé en vert) et le nouveau (promu blanc).
        if self._active_drawn != leader:
            for idx in {self._active_drawn, leader}:
                if idx is not None and idx in new_set:
                    _restyle(idx)
        self._selected_set = set(new_set)
        self._active_drawn = leader

    def _restore_selection(self, bank: PaletteBank):
        """Ré-applique la sélection après un re-render complet (bulk) : plage
        contiguë si `_sel_range`, sinon la case active seule. Sans animation
        (les boutons viennent d'être recréés → état snap)."""
        if self._sel_range:
            new = {i for i in range(self._sel_range[0], self._sel_range[1] + 1)
                   if 1 <= i < len(bank.colors)}
        elif self._active_index is not None:
            new = {self._active_index}
        else:
            new = set()
        self._apply_selection(bank, new, self._active_index, animate=False)

    def _active_value(self) -> Optional[int]:
        bank = self._current_bank()
        if bank and self._active_index is not None and self._active_index < len(bank.colors):
            return bank.colors[self._active_index]
        return None

    # ── Écriture d'une couleur (point de passage unique) ─────────────

    def apply_color(self, new_value: int):
        """Écrit `new_value` DANS LE SLOT ÉDITÉ (à son index, sans réordonner)
        via l'historique (undo/redo). Point de passage unique des modes d'édition
        de l'inspecteur (roue, RGB, TSL, hex) et du collage. L'ordre des couleurs
        = l'ordre des index hardware, laissé tel quel : c'est à l'utilisateur
        d'organiser ses couleurs (l'index est ce qui est réellement visible
        in-game)."""
        if self._active_index is None:
            return
        bank = self._current_bank()
        if not bank or not (1 <= self._active_index < len(bank.colors)):
            return
        idx = self._active_index
        old = bank.colors[idx]
        if old == new_value:
            return
        # Passe par l'historique : Ctrl+Z/Y annulent/refont ; les modifs
        # consécutives sur le même slot (drag) fusionnent en une seule entrée.
        get_history().push(
            SetPaletteColorCmd(bank, idx, old, new_value, self._persist_color))

    # ── Callbacks de persistance (execute/undo des commandes couleur) ──

    def _persist_color(self, bank: PaletteBank, index: int):
        """Rappelée par SetPaletteColorCmd (execute ET undo) : persiste la
        banque et resynchronise l'UI de façon ciblée (swatch + inspecteur si
        slot actif + finder). Garantit le rafraîchissement sur Ctrl+Z/Y,
        indépendamment de window._flush_after_undo_redo()."""
        self._project.palettes.save(bank)
        if bank is not self._current_bank():
            # Undo/redo visant une banque non affichée : la ramener à l'écran
            # (re-render complet via la sélection du finder).
            self._bank_name = bank.name
            self.bank_focus_requested.emit(bank.name)
            return
        if 0 <= index < len(self._swatch_btns) and index < len(bank.colors):
            is_leader = index == self._active_index
            self._style_swatch(self._swatch_btns[index], index, bank.colors[index],
                               selected=(is_leader or index in self._selected_set),
                               active=is_leader)
        if index == self._active_index and index < len(bank.colors):
            self.color_selected.emit(index, bank.colors[index])
        self.catalog_changed.emit()

    def _persist_bank(self, bank: PaletteBank):
        """Rappelée par SetPaletteColorsCmd (édition groupée) : persiste et
        re-render toute la grille de la banque affichée."""
        self._project.palettes.save(bank)
        if bank is not self._current_bank():
            self._bank_name = bank.name
            self.bank_focus_requested.emit(bank.name)
            return
        self._render_swatches(bank, selectable=True)
        self._restore_selection(bank)
        if self._active_index is not None and self._active_index < len(bank.colors):
            self.color_selected.emit(self._active_index, bank.colors[self._active_index])
        self.catalog_changed.emit()
