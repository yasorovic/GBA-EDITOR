"""ui/sprite_editor/sprite_right_panel.py — panneau droit : propriétés, collision, anim settings."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QComboBox, QScrollArea
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.models.sprite import AnimFrame, AnimState, SpriteAsset, StateDirection
from core.project import Project
from core.models.sprite import valid_frame_heights, resolve_direction_mirrors
from core.command_dispatcher import get_dispatcher
from .direction_widget import DirectionWidget

class SpriteRightPanel(QWidget):
    """
    Panneau droit : header (nom éditable) + paramètres sprite + widget directionnel.
    """

    sprite_changed   = pyqtSignal()
    direction_added  = pyqtSignal(object, object)  # AnimState, StateDirection nouvellement ajoutée
    image_changed    = pyqtSignal()                # source du sprite changée — recharger le centre
    palettes_changed = pyqtSignal()                # PAL_BANK mutée (grille) — rafraîchir la bande de preview

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(440)
        self.setStyleSheet(
            f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};"
        )
        self._project: Optional[Project] = None
        self._sprite:  Optional[SpriteAsset] = None
        self._state:   Optional[AnimState] = None
        self._blocking = False
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header : nom du sprite — composant partagé (voir ui/widgets.py),
        # même template/couleurs/renommage que Scene Manager, Sound Mixer, Script Editor.
        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_name_changed)
        root.addWidget(self._header)

        # ── Contenu scrollable ────────────────────────────────────
        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{C.BG_PANEL}; border:none;}}"
        )

        content = QWidget()
        content.setStyleSheet(f"background:{C.BG_PANEL};")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(10, 8, 10, 8)
        self._content_layout.setSpacing(2)

        self._build_params()
        self._build_direction()
        self._build_palette()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_params(self):
        lay = self._content_layout
        W.section(label("sprpanel.canvas_size"), lay)

        # Frame W / H
        self._cb_w = QComboBox(); self._cb_w.setFont(QFont(T.MONO, T.SM))
        self._cb_h = QComboBox(); self._cb_h.setFont(QFont(T.MONO, T.SM))
        for v in [8, 16, 32, 64]:
            self._cb_w.addItem(str(v))
        self._cb_w.currentIndexChanged.connect(self._on_frame_w_changed)
        self._cb_h.currentIndexChanged.connect(self._on_frame_h_changed)
        self._cb_w.setToolTip(tooltip(
            title=label("sprpanel.frame_width"), body=label("sprpanel.frame_size_tip")
        ))
        self._cb_h.setToolTip(tooltip(
            title=label("sprpanel.frame_height"), body=label("sprpanel.frame_size_tip")
        ))
        W.pair(label("common.frame"), "W", C.AXIS_X, self._cb_w, "H", C.AXIS_Y, self._cb_h, lay)

        W.separator(lay)
        W.section(label("sprpanel.animation"), lay)

        self._sp_speed = W.spinbox(8, min_v=1, max_v=120)
        self._sp_speed.setToolTip(tooltip(
            title=label("common.speed"), body=label("sprpanel.speed_tip")
        ))
        self._sp_speed.valueChanged.connect(self._on_speed_changed)
        W.row(label("common.speed"), self._sp_speed, lay)

        self._chk_loop = W.checkbox_row("", label("common.loop"), lay)
        self._chk_loop.setChecked(True)
        self._chk_loop.toggled.connect(self._on_loop_changed)

        W.separator(lay)

    def _build_direction(self):
        lay = self._content_layout
        W.section(label("sprpanel.directions"), lay)
        self._dir_widget = DirectionWidget()
        self._dir_widget.directions_changed.connect(self._on_directions_changed)
        lay.addWidget(self._dir_widget)

    def _build_palette(self):
        from ui.common.palette_slot_grid import PaletteSlotGridAsset
        lay = self._content_layout
        W.separator(lay)
        W.section(label("sprpanel.palette"), lay)

        # Grille unifiée (modèle scène/background) : les sous-palettes de la
        # PAL_BANK du sprite — dérivées du PNG grisées + overridables, « + » pour
        # ajouter une banque du catalogue. La palette active de PEINTURE/preview se
        # choisit dans la bande en tête du canvas.
        self._pal_grid = PaletteSlotGridAsset(C.ACCENT_WARM)
        self._pal_grid.scene_add.connect(self._on_pal_add)
        self._pal_grid.scene_replace.connect(self._on_pal_replace)
        self._pal_grid.scene_remove.connect(self._on_pal_remove)
        self._pal_grid.asset_override.connect(self._on_pal_override)
        self._pal_grid.asset_restore.connect(self._on_pal_restore)
        lay.addWidget(self._pal_grid)

        self._btn_import = W.btn_accent(label("sprpanel.import_replace"))
        self._btn_import.setToolTip(tooltip(
            title=label("sprpanel.import_replace_title"), body=label("sprpanel.import_replace_tip")
        ))
        self._btn_import.clicked.connect(self._on_replace_image)
        lay.addWidget(self._btn_import)

        self._btn_extract = W.btn_accent(label("sprpanel.extract"))
        self._btn_extract.setToolTip(tooltip(
            title=label("sprpanel.extract_title"), body=label("sprpanel.extract_tip"),
            warning=label("sprpanel.extract_warning"),
        ))
        self._btn_extract.clicked.connect(self._on_extract_palette)
        lay.addWidget(self._btn_extract)

    def refresh_palette_catalog(self):
        """Re-lit le catalogue de palettes du projet dans la grille — appelé
        quand l'écran redevient visible, une palette ayant pu changer dans
        l'écran Palettes entre-temps."""
        self._reload_palettes()

    # ── Grille de palettes (sous-palettes de la PAL_BANK) ─────────
    def _reload_palettes(self):
        from ui.common.asset_palette_view import sprite_palette_view
        view = sprite_palette_view(self._sprite)
        catalog = list(self._project.palettes) if self._project else []
        self._pal_grid.load(view, catalog)

    def _pal_mutated(self):
        """Persiste + rafraîchit la grille et le centre (bande de preview)."""
        get_dispatcher().save_sprite(self._sprite)
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_add(self, name: str):
        if not self._sprite or not self._project:
            return
        bank = self._project.get_palette(name)
        if bank and self._sprite.add_palette_colors(bank.colors) >= 0:
            self._pal_mutated()

    def _on_pal_replace(self, idx: int, name: str):
        if not self._sprite or not self._project or not (0 <= idx < len(self._sprite.palettes)):
            return
        bank = self._project.get_palette(name)
        if bank:
            self._sprite.replace_palette(idx, bank.colors)
            self._pal_mutated()

    def _on_pal_override(self, entry, name: str):
        if not self._sprite or not self._project:
            return
        bank = self._project.get_palette(name)
        if bank:
            self._sprite.override_palette(entry.idx, name, bank.colors)
            self._pal_mutated()

    def _on_pal_restore(self, entry):
        if self._sprite:
            self._sprite.restore_palette(entry.idx)
            self._pal_mutated()

    def _on_pal_remove(self, idx: int):
        if (self._sprite and 0 <= idx < len(self._sprite.palettes)
                and len(self._sprite.palettes) > 1):
            self._sprite.remove_palette(idx)
            self._pal_mutated()

    def _on_replace_image(self):
        """Remplace le fichier image du sprite courant (ré-encodage non-destructif)."""
        if not self._sprite or not self._project:
            return
        from .import_png_dialog import replace_sprite_image
        if replace_sprite_image(self._project, self._sprite, self):
            self._after_image_change()

    def _after_image_change(self):
        get_dispatcher().save_sprite(self._sprite)
        self._reload_palettes()
        self.image_changed.emit()

    # ── API publique ──────────────────────────────────────────────

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._project = project
        self._sprite  = sprite
        self._state   = sprite.states[0] if sprite.states else None
        self._blocking = True

        self._header.set_header("sprite", label("common.sprite"), sprite.name)

        # Frame size
        self._cb_w.setCurrentText(str(sprite.frame_w))
        self._refresh_h_combo(sprite.frame_w, sprite.frame_h)

        # Animation (premier state)
        if self._state:
            self._sp_speed.setValue(self._state.speed)
            self._chk_loop.setChecked(self._state.loop)
            self._dir_widget.load(self._state)

        # Grille des sous-palettes (PAL_BANK du sprite)
        self._reload_palettes()

        self._blocking = False

    def load_state(self, state: AnimState):
        """Met à jour les paramètres d'animation pour l'état sélectionné."""
        self._state = state
        self._blocking = True
        self._sp_speed.setValue(state.speed)
        self._chk_loop.setChecked(state.loop)
        self._dir_widget.load(state)
        self._blocking = False

    # ── Helpers ───────────────────────────────────────────────────

    def _refresh_h_combo(self, w_val: int, keep_h: int = 0):
        self._cb_h.blockSignals(True)
        self._cb_h.clear()
        valid = valid_frame_heights(w_val)
        for v in valid:
            self._cb_h.addItem(str(v))
        target = str(keep_h) if keep_h in valid else str(valid[0])
        self._cb_h.setCurrentText(target)
        self._cb_h.blockSignals(False)

    def _save(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
            self.sprite_changed.emit()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_extract_palette(self):
        if not self._sprite or not self._project or not self._sprite.asset:
            return
        ap = self._project.root / self._sprite.asset
        if not ap.exists():
            return
        from core.models.gba_color import extract_palette_from_image
        from core.models.palette import PaletteBank
        colors = extract_palette_from_image(ap)
        name = f"pal_{self._sprite.name}"
        existing = self._project.palettes.get(name)
        if existing:
            # Ré-extraction d'une palette déjà générée : on écrase ses couleurs
            # (action explicite "extraire", régénération attendue).
            existing.colors = colors
            bank = existing
        else:
            bank = PaletteBank(name=name, colors=colors)
        # Passe par le dispatcher : persistance (watcher suspendu) + événement
        # "palettes_changed" pour que le Palette Finder se rafraîchisse.
        get_dispatcher().save_palette(bank)

    def _on_name_changed(self, new_name: str):
        if self._blocking or not self._sprite or not self._project:
            return
        new_name = new_name.strip()
        if new_name and new_name != self._sprite.name:
            get_dispatcher().rename_sprite(self._sprite, new_name)
            self.sprite_changed.emit()

    def _on_frame_w_changed(self, _):
        if self._blocking or not self._sprite:
            return
        w = int(self._cb_w.currentText())
        old_h = int(self._cb_h.currentText()) if self._cb_h.currentText() else 16
        self._refresh_h_combo(w, old_h)
        self._sprite.frame_w = w
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_frame_h_changed(self, _):
        if self._blocking or not self._sprite:
            return
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_speed_changed(self, value: int):
        if self._blocking or not self._state:
            return
        self._state.speed = value
        self._save()

    def _on_loop_changed(self, checked: bool):
        if self._blocking or not self._state:
            return
        self._state.loop = checked
        self._save()

    def _on_directions_changed(self, active_dirs: list, h_mirror: bool, v_mirror: bool):
        if self._blocking or not self._state or not self._sprite:
            return
        # Reconstruire les StateDirection depuis la sélection
        dir_map = {sd.dir: sd for sd in self._state.directions}
        added_dirs = [d for d in active_dirs if d not in dir_map]
        mirrors = resolve_direction_mirrors(active_dirs, h_mirror, v_mirror)

        new_dirs = []
        for d in active_dirs:
            existing = dir_map.get(d)
            if d in mirrors:
                src, fh, fv = mirrors[d]
                new_dirs.append(StateDirection(
                    dir=d,
                    frames=existing.frames if existing else [AnimFrame()],
                    flip_h=fh, flip_v=fv,
                    mirror_of=src,
                ))
            else:
                new_dirs.append(existing or StateDirection(
                    dir=d, frames=[AnimFrame()],
                ))

        self._state.directions = new_dirs or [StateDirection()]
        self._save()

        # Une direction tout juste créée doit devenir visible immédiatement
        # dans l'arbre de gauche et le canvas central — sinon ceux-ci
        # continuent d'afficher/peindre l'ancienne direction sélectionnée.
        if added_dirs:
            added_sd = next((d for d in self._state.directions if d.dir == added_dirs[0]), None)
            if added_sd is not None:
                self.direction_added.emit(self._state, added_sd)
