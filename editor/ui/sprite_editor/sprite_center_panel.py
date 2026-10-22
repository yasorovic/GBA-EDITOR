"""ui/sprite_editor/sprite_center_panel.py — zone centre : sprite canvas | spritesheet, et dessous la timeline."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QTimer

from ui.common.theme import C
from ui.common.labels import label
from core.models.sprite import AnimState, SpriteAsset, StateDirection
from core.project import Project
from core.command_dispatcher import get_dispatcher
from core.keybindings import bind
from .sprite_canvas import SpriteCanvasPanel
from .sprite_timeline import SpriteTimeline, make_frame_pixmap
from .spritesheet_selector import SpritesheetSelector

# ── Zone centre — Preview ──────────────────────────────────────────────────────
# La barre playback (|◀ ▶ ▶| grille/palette) et le header (flip/fit/zoom,
# tag CANVAS, stats) sont flottants, superposés au canvas — voir
# SpriteCanvasToolbar / SpriteCanvasPanel dans sprite_canvas.py.


class SpriteCenterPanel(QWidget):
    """Zone centre : le sprite canvas (à gauche) et le spritesheet (à droite) côte à côte,
    la timeline dessous — la place laissée en bas sert au panneau de build."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._sprite:    Optional[SpriteAsset]   = None
        self._project:   Optional[Project]        = None
        self._state:     Optional[AnimState]      = None
        self._sd:        Optional[StateDirection] = None
        self._sel_frame: int = 0
        # Direction miroir (mirror_of défini) : affichée en lecture seule à
        # partir des frames de la direction source, retournées (flip).
        self._read_only:   bool = False
        self._disp_frames: Optional[list] = None
        self._flip:        tuple[bool, bool] = (False, False)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_play_tick)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:3px;}}"
            f"QSplitter::handle:horizontal:hover{{background:{C.ACCENT};}}"
        )

        self._sprite_canvas_panel = SpriteCanvasPanel()
        self._sprite_canvas = self._sprite_canvas_panel.canvas
        self._sprite_canvas.frame_painted.connect(self._on_frame_painted)
        self._sprite_canvas.set_persist_fn(self._on_frame_painted)
        self._sprite_canvas.selection_reset.connect(self._on_selection_reset)
        self._sprite_canvas.brush_picked_up.connect(self._on_brush_picked_up)

        self._spritesheet = SpritesheetSelector()
        self._spritesheet.selection_changed.connect(self._on_tile_selection_changed)

        splitter.addWidget(self._sprite_canvas_panel)
        splitter.addWidget(self._spritesheet)
        splitter.setSizes([560, 360])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter, 1)

        self._timeline = SpriteTimeline()
        self._timeline.frame_selected.connect(self._on_frame_selected)
        self._timeline.frames_changed.connect(self._on_frames_changed)
        root.addWidget(self._timeline)

        toolbar = self._sprite_canvas_panel.toolbar
        toolbar.btn_prev.clicked.connect(lambda: self._step_frame(-1))
        toolbar.btn_play.toggled.connect(self._on_play_toggled)
        toolbar.btn_next.clicked.connect(lambda: self._step_frame(+1))
        self._sprite_canvas_panel.paint_strip.selected.connect(self._on_paint_palette_selected)

        # Shift+X/Y : portés ici (pas sur SpriteCanvas seul) pour marcher
        # aussi bien après un clic dans le canvas que dans le tile picker —
        # WidgetWithChildrenShortcut s'active dès qu'un descendant a le focus.
        flip_x = QShortcut(QKeySequence(), self)
        flip_x.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_x.activated.connect(self._sprite_canvas.flip_brush_x)
        bind("sprite.flip_h", flip_x)
        flip_y = QShortcut(QKeySequence(), self)
        flip_y.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_y.activated.connect(self._sprite_canvas.flip_brush_y)
        bind("sprite.flip_v", flip_y)

    # ── API publique ──────────────────────────────────────────────────

    def refresh_palettes(self):
        """La PAL_BANK a été mutée par la grille (panneau droit) : recharge la
        bande de preview du canvas (peut avoir grandi/rétréci/changé de couleurs)."""
        self._load_paint_strip()

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._sprite  = sprite
        self._project = project
        self._sprite_canvas.set_own_palette(getattr(sprite, "own_palette", []))
        self._anim_timer.stop()
        self._sprite_canvas_panel.toolbar.btn_play.setChecked(False)
        self._sprite_canvas_panel.set_info(
            tiles=sprite.tiles_per_frame * sum(
                len(sd.frames)
                for s in sprite.states
                for sd in s.directions
                if sd.mirror_of is None
            ),
            unique=sprite.tiles_per_frame,
        )
        self._spritesheet.load(self._abs_path())
        self._load_paint_strip()

    def reload_image(self):
        """Le PNG du sprite courant a été retouché hors de l'éditeur : relit la planche, la bande de
        palettes, les miniatures de la timeline et le canvas, en gardant le sprite et la direction ouverts."""
        if self._sprite is None:
            return
        self.load_sprite(self._sprite, self._project)
        if self._state is not None and self._sd is not None:
            self.load_direction(self._state, self._sd)

    # ── Bande de preview (PAL_BANK du sprite, tête du canvas) ──────────

    def _load_paint_strip(self):
        """Peuple la bande depuis `sprite.palettes` (PAL_BANK) ; la bande
        préserve elle-même la sélection précédente si cette palette existe
        encore (par contenu, cf. PaletteBankStrip.load) — repli sur l'index 0
        seulement au premier chargement ou si elle a disparu. Teinte le canvas
        avec la palette RÉELLEMENT sélectionnée après coup (pas toujours [0]).
        Masquée si le sprite n'a pas encore de PAL_BANK (pas d'asset)."""
        strip = self._sprite_canvas_panel.paint_strip
        palettes = list(getattr(self._sprite, "palettes", []) or []) if self._sprite else []
        if palettes:
            entries = [(i, label("common.palette_i", i=i), cols) for i, cols in enumerate(palettes)]
            strip.load(entries, active=0)
            strip.setVisible(True)
            self._sprite_canvas_panel._position_paint_strip()
            self._sprite_canvas.set_tint(palettes[strip.active()])
        else:
            strip.setVisible(False)
            self._sprite_canvas.set_tint(None)

    def _on_paint_palette_selected(self, idx: int):
        if not self._sprite:
            return
        palettes = getattr(self._sprite, "palettes", []) or []
        if 0 <= idx < len(palettes):
            self._sprite_canvas.set_tint(palettes[idx])

    def load_direction(self, state: AnimState, sd: StateDirection):
        if not self._sprite or not self._project:
            return
        self._state = state
        self._sd = sd
        self._sel_frame = 0
        self._anim_timer.stop()
        self._sprite_canvas_panel.toolbar.btn_play.setChecked(False)

        # Miroir : les frames n'appartiennent pas à cette direction, elles sont
        # dérivées de la source (mirror_of) + flip. Affichage seul, pas d'édition
        # — c'est aussi ce que fait le build (grit_conversion._dedup_frames).
        self._read_only = sd.mirror_of is not None
        if self._read_only:
            src = next((s for s in state.directions if s.dir == sd.mirror_of), None)
            self._disp_frames = src.frames if src else sd.frames
            self._flip = (sd.flip_h, sd.flip_v)
        else:
            self._disp_frames = None
            self._flip = (False, False)

        self._timeline.load(self._sprite, state, sd, self._abs_path(),
                            self._read_only, self._disp_frames, self._flip,
                            project=self._project)
        self._sprite_canvas.set_read_only(self._read_only)
        self._sprite_canvas.set_display_flip(*self._flip)
        self._spritesheet.setEnabled(not self._read_only)
        from ui.sprite_editor.sprite_library_panel import dir_label
        self._sprite_canvas_panel.set_read_only_banner(
            label("sprctr.mirror_banner", dir=dir_label(sd)) if self._read_only else None)
        self._refresh_canvas()

    def _active_frames(self) -> list:
        """Frames effectivement affichées : source retournée pour un miroir,
        sinon les frames propres de la direction."""
        if self._read_only and self._disp_frames is not None:
            return self._disp_frames
        return self._sd.frames if self._sd else []

    # ── Slots internes ────────────────────────────────────────────────

    def _abs_path(self) -> Optional[Path]:
        if not self._project or not self._sprite or not self._sprite.asset:
            return None
        return self._project.root / self._sprite.asset

    def _on_frame_selected(self, index: int):
        self._sel_frame = index
        self._refresh_canvas()

    def _on_tile_selection_changed(self, tiles: list):
        self._sprite_canvas.set_brush(tiles)
        self._spritesheet.set_brush_label(len(tiles))

    def _on_selection_reset(self):
        self._spritesheet.clear_selection()
        self._sprite_canvas.set_brush([])

    def _on_brush_picked_up(self, n: int):
        """Tuiles ramassées directement dans le canvas (cf SpriteCanvas) —
        seul le libellé du picker doit refléter la nouvelle brosse ; ne pas
        appeler _spritesheet.clear_selection() ici, ça réémettrait une sélection
        vide et effacerait la brosse qu'on vient de charger."""
        self._spritesheet.set_brush_label(n)

    def _on_frame_painted(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
        if self._sd and 0 <= self._sel_frame < len(self._sd.frames):
            pm = make_frame_pixmap(self._abs_path(), self._sd.frames[self._sel_frame],
                                    self._sprite.frame_w, self._sprite.frame_h)
            self._timeline.refresh_thumb(self._sel_frame, pm)

    def _on_frames_changed(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)

    # ── Playback ──────────────────────────────────────────────────────

    def _on_play_toggled(self, playing: bool):
        if playing and self._sd and self._active_frames():
            speed_ms = max(16, int((self._state.speed if self._state else 8) * 1000 / 60))
            self._anim_timer.start(speed_ms)
        else:
            self._anim_timer.stop()

    def _on_play_tick(self):
        if not self._sd or not self._active_frames():
            return
        n = len(self._active_frames())
        next_frame = self._sel_frame + 1
        if next_frame >= n:
            if not (self._state and self._state.loop):
                self._anim_timer.stop()
                self._sprite_canvas_panel.toolbar.btn_play.setChecked(False)
                return
            next_frame = 0
        self._sel_frame = next_frame
        # Mettre à jour la sélection dans la timeline sans émettre frame_selected
        for i, t in enumerate(self._timeline._thumbs):
            t.set_selected(i == self._sel_frame)
        self._timeline._selected = self._sel_frame
        self._refresh_canvas()

    def _step_frame(self, direction: int):
        """Sélectionne la frame précédente ou suivante dans la timeline."""
        frames = self._active_frames()
        if not frames:
            return
        self._sel_frame = (self._sel_frame + direction) % len(frames)
        for i, thumb in enumerate(self._timeline._thumbs):
            thumb.set_selected(i == self._sel_frame)
        self._timeline._selected = self._sel_frame
        self._refresh_canvas()

    # ── Canvas ────────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if not self._sd or not self._sprite:
            self._sprite_canvas.load_frame(None, None, None)
            return
        frames = self._active_frames()
        if not frames or not (0 <= self._sel_frame < len(frames)):
            self._sprite_canvas.load_frame(None, None, None)
            return
        self._sprite_canvas.load_frame(self._sprite, self._abs_path(), frames[self._sel_frame])
