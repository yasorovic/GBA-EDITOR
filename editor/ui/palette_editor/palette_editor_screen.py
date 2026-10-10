"""Palette Editor screen — catalogue illimité et unifié de palettes nommées.

Plus de distinction OBJ/BG dans le catalogue (2026-07-08) — une palette est
juste 16 couleurs, réutilisable pour les deux pools. C'est la scène qui
choisit jusqu'à 16 palettes actives par pool parmi ce catalogue (voir Scene
Inspector, carte "Palettes actives").

Layout : 3 colonnes (même modèle que le Sprite Editor)
  Gauche  : catalogue des palettes du projet   (AssetFinder — partagé)
  Centre  : grille de swatches de la banque    (PaletteGridPanel)
  Droite  : inspecteur de la couleur active    (ColorInspectorPanel)
            + carte « USAGE » ferrée en bas, hauteur réglable (PaletteUsageCard)
"""
from __future__ import annotations

from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.three_column_body import ThreeColumnBody
from core.project import Project

from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import PALETTES
from .palette_grid_panel import PaletteGridPanel
from .color_inspector_panel import ColorInspectorPanel
from .palette_usage_card import PaletteUsageCard


class PaletteEditorScreen(QWidget):
    """Écran complet Palette Editor : finder unifié + grille + inspecteur couleur."""

    # Clic sur une ligne de la carte « USAGE » : (kind, nom). L'écran ne navigue
    # pas lui-même — la fenêtre route vers l'éditeur correspondant.
    usage_activated = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Pas de bandeau-titre d'écran : la nav du haut indique déjà où on est
        # (décision refonte thème 2026-08).
        self._finder    = AssetFinder(label('palscr.palette_finder'), [PALETTES],
                                      min_width=200, max_width=360)
        self._grid      = PaletteGridPanel()
        self._inspector = ColorInspectorPanel()
        self._usage     = PaletteUsageCard()

        # Colonne droite = inspecteur de couleur + carte « USAGE » FERRÉE en bas.
        # La carte parle de la PALETTE, pas de la couleur : elle ne défile donc
        # pas avec les contrôles et reste visible quel que soit le slot édité.
        # Splitter vertical (et pas un layout) : la liste d'usages peut être
        # longue, c'est à l'utilisateur de choisir combien il en voit d'un coup.
        # Non repliable des deux côtés — l'entête USAGE reste toujours atteignable.
        right = QSplitter(Qt.Orientation.Vertical)
        right.setStyleSheet(QSS.splitter)
        right.setChildrenCollapsible(False)
        right.setMinimumWidth(300)
        right.setMaximumWidth(480)
        right.addWidget(self._inspector)
        right.addWidget(self._usage)
        right.setStretchFactor(0, 1)   # l'inspecteur absorbe le redimensionnement vertical
        right.setStretchFactor(1, 0)
        right.setSizes([520, 180])

        self.body = ThreeColumnBody(self._finder, self._grid, right,
                                    sizes=(240, 620, 320))
        self.body.setCollapsible(1, False)
        self.body.setCollapsible(2, False)
        root.addWidget(self.body, 1)

        # Finder → grille + carte : la banque sélectionnée devient la banque
        # affichée (et celle dont on liste les usages).
        self._finder.selected.connect(lambda _kind, b: self._on_bank_selected(b.name))
        self._finder.emptied.connect(lambda _kind: self._on_bank_deleted())
        self._usage.usage_activated.connect(self.usage_activated)
        # Grille → inspecteur : la couleur active est la seule chose partagée.
        self._grid.color_selected.connect(self._inspector.load_color)
        self._grid.editing_enabled.connect(self._inspector.setVisible)
        self._grid.hex_focus_requested.connect(self._inspector.focus_hex)
        # Grille → finder : nom/icône à rafraîchir, ou banque à ramener à l'écran
        # (undo/redo visant une palette non affichée).
        self._grid.catalog_changed.connect(self._finder.refresh)
        self._grid.bank_focus_requested.connect(self._select_bank)
        # Inspecteur → grille : l'écriture (et l'historique) restent côté grille.
        self._inspector.color_changed.connect(self._grid.apply_color)
        self._inspector.grid_focus_requested.connect(self._grid.focus_grid)

        self._inspector.setVisible(False)

    # ── Sélection de banque ───────────────────────────────────────

    def _select_bank(self, name: str):
        """Le finder sélectionne un ASSET ; ici on n'a que son nom (la grille
        et l'historique travaillent par nom). La conversion vit dans l'écran,
        pas dans le composant partagé, qui ne connaît aucune famille."""
        bank = self._project.palettes.get(name or "") if self._project else None
        if bank is not None:
            self._finder.select(PALETTES.label, bank)

    def select_palette(self, name: str):
        """Ouvre la palette `name` — navigation entrante depuis un autre écran (onglet Disk)."""
        self._select_bank(name)

    def _on_bank_selected(self, name: str):
        self._grid.show_bank(name)
        self._usage.load(self._project, self._grid.bank_name)

    def _on_bank_deleted(self):
        self._grid.on_bank_deleted()
        still_there = bool(self._project
                           and self._project.palettes.get(self._grid.bank_name or ""))
        self._usage.load(self._project, self._grid.bank_name if still_there else None)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)
        self._grid.load_project(project)
        self._usage.load(project, None)

    def refresh(self):
        """Reconstruit le finder depuis project.palettes — appelé à la revisite
        de l'écran par `Window._show_screen` (chantier « L'écran resynchronisé à
        sa revisite »). Une palette extraite depuis le Sprite ou le Background
        Editor pendant qu'on était ailleurs apparaît ainsi au retour. Re-sélectionne
        la banque en cours d'édition si elle existe toujours."""
        if not self._project:
            return
        self._finder.refresh()
        self._select_bank(self._grid.bank_name)
        # Les usages peuvent avoir bougé sans que la banque change (slot de
        # scène réassigné, override d'asset) : recalculer dans tous les cas.
        self._usage.refresh()
