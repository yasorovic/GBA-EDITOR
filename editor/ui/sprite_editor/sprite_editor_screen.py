"""
ui/sprite_editor/sprite_editor_screen.py — Éditeur de sprites (style GB Studio).

Layout : 3 colonnes
  Gauche  : liste des sprites du projet + arbre d'animations
  Centre  : barre playback + preview + tiles + frames
  Droite  : propriétés + collision + anim settings
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout

from ui.common.theme import C
from ui.common.three_column_body import ThreeColumnBody
from core.models.sprite import AnimState, SpriteAsset, StateDirection
from core.project import Project
from .sprite_finder_panel import SpriteFinderPanel
from .sprite_center_panel import SpriteCenterPanel
from .sprite_right_panel import SpriteRightPanel

class SpriteEditorScreen(QWidget):
    """Écran principal du Sprite Editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project: Optional[Project] = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._left   = SpriteFinderPanel()
        self._center = SpriteCenterPanel()
        self._right  = SpriteRightPanel()

        self.body = ThreeColumnBody(self._left, self._center, self._right,
                                    sizes=(240, 860, 270))
        root.addWidget(self.body)

        self._left.sprite_selected.connect(self._on_sprite_selected)
        self._left.direction_selected.connect(self._on_direction_selected)
        self._right.sprite_changed.connect(self._left.refresh_anim_tree)
        self._right.direction_added.connect(self._left.select_direction)
        self._right.image_changed.connect(self._on_image_changed)
        self._right.palettes_changed.connect(self._center.refresh_palettes)

    def _on_image_changed(self):
        """Le PNG du sprite courant a changé (réindexation/remplacement) —
        recharger le centre pour refléter les nouvelles couleurs/tuiles."""
        if self._project and self._right._sprite:
            self._center.load_sprite(self._right._sprite, self._project)

    def load_project(self, project: Project):
        self._project = project
        self._left.load_project(project)

    def refresh(self):
        """Re-dérive à la revisite de l'écran — appelé au centre par
        `Window._show_screen` (chantier « L'écran resynchronisé à sa revisite »).
        Une palette a pu être ajoutée, renommée ou retirée dans l'écran Palettes
        depuis la dernière visite ; sans cela la grille « + du catalogue » du
        panneau droit restait figée. Bon marché : on relit `project.palettes`
        (déjà en mémoire), pas le PNG du sprite."""
        if self._project is not None:
            self._right.refresh_palette_catalog()
            self._center.refresh_palettes()

    def select_sprite(self, name: str):
        """Ouvre le sprite `name` — navigation entrante depuis un autre écran."""
        self._left.select_sprite(name)

    def _on_sprite_selected(self, sprite: SpriteAsset):
        self._center.load_sprite(sprite, self._project)
        self._right.load_sprite(sprite, self._project)

    def _on_direction_selected(self, state: AnimState, sd: StateDirection):
        self._center.load_direction(state, sd)
        self._right.load_state(state)
