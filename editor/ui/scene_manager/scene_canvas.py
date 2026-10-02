"""
Backstage — Scene Canvas
Canvas dynamique (plafond monde 32767×32767) avec caméra 240×160 déplaçable.

Layers (z-order) :
  z=0..3   → BG3..BG0 (PNG composités)
  z=10+n   → sprites placés (draggables)
  z=100    → grille 8px (optionnelle)
  z=150    → rectangle caméra (draggable)
  z=200    → bordure canvas
"""

from ui.common.labels import label
from ui.common.tooltip import tooltip
import copy
from typing import Optional

from core.command_dispatcher import get_dispatcher
from core.models.components import displayed_sprite_component
from core.models.scene import Actor
from core.project import Project
from core.sprite_compose import compose_frame_image
from core.models.gba_color import quantize_preview
from codegen.grit_conversion import resolve_obj_palette_bank
from core.selection_bus import get_bus, CameraSelection
from ui.common.theme import T, QSS, C
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.canvas_top_bar import CanvasTopBar
from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtWidgets import QVBoxLayout, QWidget
# Rasterisation des fonds + aperçus — extrait (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_raster import (
    BgLayerRaster, build_bg_raster, bg_pixmap, preview_frame_for_actor,
    layer_png_path,
)
# Items graphiques — extrait (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_items import (
    SpriteItem, MaskablePixmapItem, CameraItem, ScreenBezelItem, GridItem,
    ActorBoxOverlay, GuideLine, CollisionOverlay, hw_layer_z,
    make_placeholder_pixmap,
)
# Item de zone d'interface — extrait (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
# Scène graphique — extraite (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_scene import GBAScene
# Vue zoomable — extraite (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_view import GBAView
# Palette d'outils flottante — extraite (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_toolbar import FloatingToolbar
# Table des raccourcis de l'outil actif.
from ui.common.shortcut_hints import ShortcutHints
from ui.scene_manager.canvas.canvas_hints import scene_canvas_hints
# Contrôleurs (logique non graphique) — extraits (A3, sous-package canvas/).
from ui.scene_manager.canvas.canvas_controllers import (
    UIRegionController, SceneInpaintingController, CanvasClipboard,
)

# Constantes GBA — source unique dans canvas_const, ré-exportées ici (des
# appelants externes lisent `scene_canvas.GBA_W`).
from ui.scene_manager.canvas.canvas_const import (
    GBA_W, GBA_H, MAX_CANVAS_W, MAX_CANVAS_H,
)


# ──────────────────────────────────────────────────────────────────
#  Wrapper canvas + toolbar flottante
# ──────────────────────────────────────────────────────────────────
class CanvasContainer(QWidget):
    """QWidget superposant GBAView et FloatingToolbar."""

    tool_changed = pyqtSignal(str)

    def __init__(self, view: GBAView, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        self._toolbar = FloatingToolbar(self)
        self._toolbar.move(10, 10)
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.raise_()

        # Table des raccourcis de l'outil actif (bas-droite, repliée au repos).
        self._hints = ShortcutHints(self, scene_canvas_hints, self._toolbar.current_tool)

        # Bandeau flottant de sélection de la banque de peinture (bas-centre,
        # même widget que Sprite Editor/Background Editor — cf. palette_bank_strip).
        self._inpaint_ctrl: Optional[SceneInpaintingController] = None
        self._inpaint_bank_strip = PaletteBankStrip(label('scncanvas.no_active_bg_bank'), self)
        self._inpaint_bank_strip.selected.connect(self._on_inpaint_bank_selected)
        self._inpaint_bank_strip.raise_()

    def bind_inpainting(self, ctrl: "SceneInpaintingController"):
        self._inpaint_ctrl = ctrl

    def _on_inpaint_bank_selected(self, slot: int):
        if self._inpaint_ctrl:
            self._inpaint_ctrl.set_inpaint_bank(slot)

    def refresh_inpaint_banks(self):
        ctrl = self._inpaint_ctrl
        banks = ctrl.scene_bg_banks() if ctrl else []
        entries = [(slot, label('scncanvas.bank_slot', slot=slot, name=bank.name), bank.colors) for slot, bank in banks]
        self._inpaint_bank_strip.load(entries, active=ctrl.inpaint_bank if ctrl else None)
        if ctrl:
            ctrl.set_inpaint_bank(self._inpaint_bank_strip.active())
        self._position_inpaint_strip()

    def set_inpaint_strip_visible(self, visible: bool):
        if visible:
            self.refresh_inpaint_banks()
        self._inpaint_bank_strip.setVisible(visible)
        self._inpaint_bank_strip.raise_()

    def _position_inpaint_strip(self):
        strip = self._inpaint_bank_strip
        strip.reflow()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(0, self.height() - strip.height() - 12)
        strip.move(x, y)

    def _on_tool_changed(self, tool: str):
        self._hints.set_context(tool)
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._toolbar.current_tool

    def activate_tool_shortcut(self, group: str):
        """Relais des raccourcis clavier d'outil vers la toolbar flottante."""
        self._toolbar.activate_shortcut(group)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self._toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        if self._inpaint_bank_strip.isVisible():
            self._position_inpaint_strip()
            self._inpaint_bank_strip.raise_()


# ──────────────────────────────────────────────────────────────────
#  Widget éditeur de scène complet
# ──────────────────────────────────────────────────────────────────
def _tile_snap(v: int) -> int:
    """Décalage aimanté à la tuile 8 px — appliqué aux copies d'éléments
    d'interface : une zone en cible BG occupe des entrées de tilemap, son
    origine ne peut pas tomber entre deux tuiles (cf. UIRegionItem)."""
    return int(round(v / 8.0)) * 8


_clipboard = CanvasClipboard()


class SceneEditor(QWidget):
    scene_changed = pyqtSignal()  # fin de drag / déplacement caméra → sauvegarder
    # Position d'une caméra changée PAR DRAG dans le canvas — l'inspecteur
    # doit suivre (cf. window.py, symétrique de CameraInspector.camera_moved
    # qui fait le chemin inverse).
    camera_position_changed = pyqtSignal(object, int, int)   # Camera|None, x, y
    # `_reload_ui_regions` est le point de convergence des TROIS origines d'une
    # mise en page modifiée (dessin/suppression/collage au canvas, édition dans
    # l'inspecteur, opération depuis l'arbre de scène — cf. les branchements de
    # `regions_changed`/`ui_regions_changed`/`ui_layout_changed` dans window.py)
    # : un conteneur qui change de fond (nine-slice/background) change
    # l'occupation des banques de palette (cf. codegen/palette_alloc.
    # scene_palette_view). window.py y branche le rafraîchissement de la carte
    # Palettes, une fois pour les trois origines au lieu de trois branchements.
    ui_regions_reloaded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._sprite_pixmaps: dict[int, QPixmap] = {}
        # Frames AVANT mélange — cf. `refresh_blend`.
        self._raw_sprite: dict[int, QPixmap] = {}
        # Layers AVANT mélange — idem.
        self._raw_bg: dict[int, QPixmap] = {}
        # Ce qui est derrière les sprites — un BottomLayer
        # (couleurs + masque des secondes cibles), cf. blend_preview.
        self._blend_bottom = None
        self._canvas_w = GBA_W
        self._canvas_h = GBA_H
        self._show_all_boxes = False
        # Masques purement éditoriaux, alimentés par le sidecar du Scene Tree.
        self._editor_hidden_members: set[str] = set()
        # Sauvegarde coalescée : un nudge clavier maintenu (auto-repeat) ne doit
        # pas écrire la scène sur disque à chaque frappe — on ne persiste qu'une
        # fois l'utilisateur arrêté, ce qui évite la rafale d'écritures atomiques
        # (source des verrous transitoires Windows) et réduit l'I/O.
        from PyQt6.QtCore import QTimer
        self._nudge_save_timer = QTimer(self)
        self._nudge_save_timer.setSingleShot(True)
        self._nudge_save_timer.setInterval(180)
        self._nudge_save_timer.timeout.connect(self._flush_nudge_save)
        self._setup_ui()

    def _flush_nudge_save(self):
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().save_scene()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Barre haut — composant partagé (cf. ui/common/canvas_top_bar) ──
        self._bar = CanvasTopBar(
            tooltip(title=label('scncanvas.fit'), shortcut="F")
        )
        self._bar.zoom_step_asked.connect(self._zoom_step)
        self._bar.fit_asked.connect(self._fit)
        self._bar.set_canvas_size(GBA_W, GBA_H)

        # ── Toggles d'affichage iconifiés (remplacent les cases texte) ──
        self._chk_grid8 = self._bar.add_toggle(
            "view_grid", tooltip(
                title=label('scncanvas.grid_8px'), body=label('scncanvas.grid_8px_tip')
            ), self._on_grid8_toggle)
        self._chk_grid16 = self._bar.add_toggle(
            "view_grid_large", tooltip(
                title=label('scncanvas.grid_16px'), body=label('scncanvas.grid_16px_tip')
            ), self._on_grid16_toggle)
        self._chk_snap = self._bar.add_toggle(
            "view_snap", tooltip(
                title=label('scncanvas.snap'), body=label('scncanvas.snap_tip')
            ),
            self._on_snap_toggle)
        self._bar.add_spacing(10)
        self._chk_boxes_actors = self._bar.add_toggle(
            "view_boxes", tooltip(
                title=label('scncanvas.actor_boxes'), body=label('scncanvas.actor_boxes_tip')
            ),
            self._on_boxes_actors_toggle)
        self._chk_collision_view = self._bar.add_toggle(
            "view_collision", tooltip(
                title=label('scncanvas.collisions'), body=label('scncanvas.collisions_tip')
            ),
            self._on_collision_view_toggle)
        self._bar.add_spacing(10)
        self._chk_ui_elements = self._bar.add_toggle(
            "ui_layout", tooltip(
                title=label('scncanvas.interface'), body=label('scncanvas.interface_tip')
            ),
            self._on_ui_elements_toggle)
        # blockSignals : self._gba_scene est créé plus bas, et le `toggled`
        # SYNCHRONE de setChecked ferait planter _on_ui_elements_toggle dessus
        # (AttributeError dans un slot appelé depuis C++ = plantage natif). Le
        # défaut True est déjà celui de GBAScene._ui_elements_visible.
        self._chk_ui_elements.blockSignals(True)
        self._chk_ui_elements.setChecked(True)
        self._chk_ui_elements.blockSignals(False)

        layout.addWidget(self._bar)

        # ── Canvas ────────────────────────────────────────────────
        self._gba_scene = GBAScene()
        self._gba_view = GBAView(self._gba_scene)
        self._gba_view.zoom_changed.connect(self._bar.set_zoom)
        self._gba_view.setMouseTracking(True)
        self._gba_scene.selectionChanged.connect(self._on_selection_changed)
        # Filet de sécurité : Qt.selectionChanged ne fire que si l'ensemble
        # sélectionné change réellement — un clic répété dans le même état
        # (déjà vide, dedans ou dehors) ne le déclenche pas, et l'inspecteur ne
        # se met jamais à jour. left_click_settled force la réévaluation après
        # CHAQUE clic gauche (cf. GBAView.mousePressEvent).
        self._gba_view.left_click_settled.connect(self._on_selection_changed)
        self._gba_scene.changed.connect(self._on_scene_item_changed)
        self._gba_view.prefab_template_dropped.connect(self._on_prefab_template_dropped)
        get_bus().changed.connect(self.on_selection)

        self._canvas_container = CanvasContainer(self._gba_view)
        layout.addWidget(self._canvas_container, 1)

        self._gba_view.viewport().setMouseTracking(True)
        self._gba_view.viewport().installEventFilter(self)

        # Outil par défaut
        from ui.scene_manager.canvas_tools import SelectTool

        self._gba_view.set_tool(SelectTool(self._gba_view))

        self._canvas_container.tool_changed.connect(self._on_tool_changed)
        self._gba_view.collision_painted.connect(self._on_collision_painted)
        # Après une pose, retour à Sélection — différé : l'outil qui émet est
        # encore au milieu de son on_press/on_release quand le signal part.
        self._gba_view.placement_done.connect(
            lambda: QTimer.singleShot(
                0, lambda: self._canvas_container.activate_tool_shortcut("select")))
        self._gba_view.actor_context_requested.connect(self._on_actor_context_menu)
        self._gba_view.duplicate_drag_started.connect(self._on_duplicate_drag)

        self._setup_shortcuts()

        # Contrôleur de peinture par palette BG + bandeau de palette flottant.
        self._inpainting_ctrl = SceneInpaintingController(self._gba_scene)
        self._gba_view.inpainting_controller = self._inpainting_ctrl
        self._canvas_container.bind_inpainting(self._inpainting_ctrl)

        # Contrôleur des zones de texte (outil « Zone de texte »).
        self._ui_region_ctrl = UIRegionController(self)
        self._gba_view.ui_region_controller = self._ui_region_ctrl
        self._ui_region_ctrl.region_created.connect(self._on_region_created)
        # Sauver PUIS redessiner : la zone créée (ou remise par un redo) n'a pas
        # encore d'item. Le redessin n'est pas branché sur le drag d'une zone
        # existante — détruire un item depuis son propre mouseReleaseEvent est
        # ce qui faisait planter le rechargement par le watcher.
        self._ui_region_ctrl.regions_changed.connect(self._save_ui_regions)
        self._ui_region_ctrl.regions_changed.connect(self._reload_ui_regions)

        self._update_zoom_label()

    # ── Événements ────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj == self._gba_view.viewport() and event.type() == QEvent.Type.MouseMove:
            pos = self._gba_view.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())
            inside = 0 <= x < self._canvas_w and 0 <= y < self._canvas_h
            self._bar.set_cursor_px(x if inside else None, y if inside else None)
        return False

    # ── Zoom ──────────────────────────────────────────────────────

    _ZOOM_LEVELS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]

    def _zoom_step(self, direction: int):
        current = self._gba_view._zoom
        levels = self._ZOOM_LEVELS
        idx = min(range(len(levels)), key=lambda i: abs(levels[i] - current))
        idx = max(0, min(idx + direction, len(levels) - 1))
        self._gba_view.zoom_to(levels[idx])
        self._update_zoom_label()

    # ── Raccourcis clavier ────────────────────────────────────────

    def _setup_shortcuts(self):
        """Raccourcis clavier du canvas. Contexte WidgetWithChildrenShortcut :
        actifs seulement quand le focus est dans le SceneEditor (donc pas quand
        on tape dans un champ d'un autre panneau)."""
        from PyQt6.QtGui import QShortcut, QKeySequence
        from core.keybindings import bind

        def mk(seq, slot):
            """Raccourci NON remappable — touche positionnelle (nudge) ou
            simple alias secondaire (Backspace = Suppr), jamais montré à
            l'écran Réglages. Cf. core/keybindings.py, tête de fichier."""
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            return sc

        def mkb(binding_id, slot):
            """Raccourci REMAPPABLE — touche posée par core/keybindings.py,
            éditable depuis Réglages → Shortcuts."""
            sc = QShortcut(QKeySequence(), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            bind(binding_id, sc)
            return sc

        # Bascule d'outil — mêmes lettres que les tooltips de la toolbar
        mkb("canvas.tool_select",    lambda: self._shortcut_tool("select"))
        mkb("canvas.tool_add",       lambda: self._shortcut_tool("add"))
        mkb("canvas.tool_erase",     lambda: self._shortcut_tool("erase"))
        mkb("canvas.tool_collision", lambda: self._shortcut_tool("collision"))
        mkb("canvas.tool_inpaint",   lambda: self._shortcut_tool("inpaint"))
        mkb("canvas.tool_ui",        lambda: self._shortcut_tool("ui"))
        # Vue
        mkb("canvas.fit", self._fit)
        # Sélection / édition
        mkb("canvas.cancel", self._shortcut_escape)
        mkb("canvas.delete", self._shortcut_delete)
        mk("Backspace", self._shortcut_delete)   # alias fixe, cf. mk() ci-dessus
        mkb("canvas.duplicate", self._shortcut_duplicate)
        mkb("canvas.copy", self._shortcut_copy)
        mkb("canvas.paste", self._shortcut_paste)
        # Nudge de la sélection : 1 px, Shift = 8 px (cran de grille) — touches
        # positionnelles, hors du registre remappable (cf. core/keybindings.py)
        for seq, (dx, dy) in {
            "Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1),
            "Shift+Left": (-8, 0), "Shift+Right": (8, 0),
            "Shift+Up": (0, -8), "Shift+Down": (0, 8),
        }.items():
            mk(seq, lambda dx=dx, dy=dy: self._shortcut_nudge(dx, dy))

    def _selected_sprite_items(self) -> list:
        return [it for it in self._gba_scene.selectedItems()
                if isinstance(it, SpriteItem)]

    def _selected_ui_items(self) -> list:
        return [it for it in self._gba_scene.selectedItems()
                if isinstance(it, UIRegionItem)]

    # ── Menu contextuel actor (clic-droit en mode Sélection) ──────

    def _on_actor_context_menu(self, item: "SpriteItem", global_pos):
        """Le menu agit sur TOUTE la sélection — même règle que Suppr et Ctrl+D,
        sinon un clic-droit sur 3 actors sélectionnés n'en supprimerait qu'un.
        `item` sert de repli quand il vient d'un clic hors sélection. Renommer
        reste réservé à un actor unique (un seul nom à saisir)."""
        from PyQt6.QtWidgets import QMenu
        from core.command_dispatcher import get_dispatcher
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        if item.scene_sprite not in actors:
            actors = [item.scene_sprite]
        n = len(actors)

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(QSS.menu)
        act_rename = menu.addAction(label('scncanvas.rename'))
        act_rename.setEnabled(n == 1)
        act_dup = menu.addAction(label('common.duplicate') if n == 1 else label('scncanvas.duplicate_n', n=n))
        menu.addSeparator()
        act_del = menu.addAction(label('common.delete') if n == 1 else label('scncanvas.delete_n', n=n))
        chosen = menu.exec(global_pos)
        if chosen is act_rename:
            self._rename_actor(actors[0])
        elif chosen is act_dup:
            # Par la sélection : le menu vise déjà tout le lot, et les copies
            # doivent hériter de la sélection comme après un Ctrl+D.
            self._select_copies(get_dispatcher().duplicate_actors(actors),
                                [], 'scncanvas.duplicated_elements')
        elif chosen is act_del:
            get_dispatcher().delete_actors(actors)

    def _rename_actor(self, actor):
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, label('scncanvas.rename_actor'), label('common.name_colon'), text=actor.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == actor.name:
            return
        from core.command_dispatcher import get_dispatcher
        disp = get_dispatcher()
        # Via le projet : réécrit les actor:get("…") des scripts et poste le
        # message de statut (même chemin que le renommage par l'en-tête).
        if self._project:
            self._project.rename_actor(actor, new_name)
        else:
            actor.name = new_name
        disp.save_scene()
        disp._emit("actors_list_changed")
        disp._emit("scene_sprites_changed")
        get_bus().select(actor)   # rafraîchit l'inspecteur / l'en-tête

    def _shortcut_tool(self, group: str):
        self._canvas_container.activate_tool_shortcut(group)

    def _shortcut_escape(self):
        self._gba_scene.clearSelection()
        self._canvas_container.activate_tool_shortcut("select")

    def _shortcut_delete(self):
        """Suppr — sur TOUTE la sélection, acteurs et éléments d'interface
        confondus (même portée que Ctrl+D, Alt+glisser et Ctrl+C/V)."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        # Vider le bus AVANT la suppression : la persistance des zones réémet
        # la sélection courante vers l'inspecteur, qui rechargerait un élément
        # déjà retiré de la mise en page.
        get_bus().clear()
        get_dispatcher().delete_actors(actors)
        gone = self._ui_region_ctrl.delete_elements(elements)
        n = len(actors) + len(elements)
        if gone or actors:
            get_dispatcher().status(label('scncanvas.deleted_elements', n=n))

    def _shortcut_duplicate(self):
        self._duplicate_selection(8, 8)

    # ── Dupliquer / copier / coller ───────────────────────────────
    # Ctrl+D, Alt+glisser et Ctrl+V passent par le même chemin, seule l'origine
    # du décalage change. Acteurs ET éléments d'interface.

    def _duplicate_selection(self, dx: int, dy: int, in_place: bool = False):
        """Duplique la sélection courante, décalée de (dx, dy). `in_place` : la
        copie naît pile sur l'original (Alt+glisser — la souris l'emporte ensuite)."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        new_actors = get_dispatcher().duplicate_actors(actors, dx, dy)
        # Une zone en cible BG s'écrit dans une tilemap : son origine ne peut
        # pas tomber entre deux tuiles, donc décalage aimanté.
        edx, edy = _tile_snap(dx), _tile_snap(dy)
        if elements and not edx and not edy and not in_place:
            # Geste plus court qu'une demi-tuile : la copie tomberait pile sur
            # l'original, donc invisible. Un cran de grille, comme au Ctrl+D.
            edx = edy = 8
        new_elements = self._ui_region_ctrl.duplicate_elements(elements, edx, edy)
        self._select_copies(new_actors, new_elements, 'scncanvas.duplicated_elements')

    def _on_duplicate_drag(self):
        """Alt+glisser entamé : la vue a remis les originaux en place, la copie
        naît dessus et la vue la saisit aussitôt."""
        self._duplicate_selection(0, 0, in_place=True)

    def _shortcut_copy(self):
        """Ctrl+C — met la sélection dans le presse-papier du canvas.

        Une sélection vide ne VIDE pas le presse-papier : un Ctrl+C manqué (clic
        à côté puis raccourci) perdrait sinon ce qu'on s'apprêtait à coller."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        # Même règle qu'à la duplication : un élément dont un ancêtre est du
        # lot voyage dans le sous-arbre de celui-ci, pas en double. Chaque nœud
        # `Interface` touché est traité à part (v0.25).
        groups = self._ui_region_ctrl.copy_groups(elements)
        scene = self._project.active_scene if self._project else None
        _clipboard.take(actors, groups, getattr(scene, "name", ""))
        n = len(actors) + len(groups)
        get_dispatcher().status(
            label('scncanvas.copied_elements', n=n))

    def _shortcut_paste(self):
        """Ctrl+V — colle le presse-papier dans la scène ACTIVE (pas forcément
        celle où la copie a été faite : c'est tout l'intérêt du geste)."""
        if _clipboard.empty or not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        d = _clipboard.paste_offset(getattr(scene, "name", ""))
        new_actors = get_dispatcher().paste_actors(_clipboard.actors, d, d)
        new_elements = self._ui_region_ctrl.paste_elements(
            _clipboard.ui_groups, _tile_snap(d), _tile_snap(d))
        self._select_copies(new_actors, new_elements, 'scncanvas.pasted_elements')

    def _select_copies(self, actors: list, elements: list, verb: str):
        """Donne la sélection aux copies fraîches : c'est sur elles que porte le
        geste suivant, jamais sur les originaux.

        Signaux tus pendant la bascule — chaque setSelected() ferait transiter
        le bus par un état « plus rien de sélectionné » que l'inspecteur
        traduirait par un retour à l'aperçu."""
        if not actors and not elements:
            return
        self._gba_scene.blockSignals(True)
        for item in self._gba_scene.selectedItems():
            item.setSelected(False)
        first = None
        for a in actors:
            it = self._find_item(a)
            if it is not None:
                it.setSelected(True)
                first = first or it
        for el in elements:
            for it in self._gba_scene._ui_region_items:
                if it._region is el:
                    it.setSelected(True)
                    first = first or it
                    break
        self._gba_scene.blockSignals(False)
        self._gba_scene.set_active_item(first)
        # L'inspecteur suit l'item ACTIF : on l'annonce sur le bus, qui sait ne
        # pas réduire la sélection quand l'objet en est déjà membre.
        if first is not None:
            if isinstance(first, SpriteItem):
                get_bus().select(first.scene_sprite)
            else:
                from core.selection_bus import UIRegionSelection
                get_bus().select(UIRegionSelection(first._layout, first._region))
        n = len(actors) + len(elements)
        get_dispatcher().status(label(verb, n=n))

    def _shortcut_nudge(self, dx: int, dy: int):
        items = self._selected_sprite_items()
        if not items:
            return
        from core.history import get_history, MoveActorCmd
        for it in items:
            a = it.scene_sprite
            ox, oy = it.pos_px()   # résout px/tile/réf avant d'ajouter le delta

            def persist(it=it):
                # Le garde-fou itemChange (_drag_origin is None) empêche le
                # re-snap et la réécriture du modèle sur ce setPos programmatique.
                it.sync_pos()
                self._update_actor_box_overlay()

            get_history().push(
                MoveActorCmd(a, ox, oy, ox + dx, oy + dy, persist_fn=persist))
        # Persistance différée/coalescée (cf. _nudge_save_timer) : un maintien de
        # flèche déclenche une seule sauvegarde après relâchement, pas une par
        # frappe. Le modèle en mémoire est déjà à jour pour l'affichage.
        self._nudge_save_timer.start()

    def _fit(self):
        self._gba_view.fit(self._canvas_w, self._canvas_h)
        self._update_zoom_label()

    def _update_zoom_label(self):
        self._bar.set_zoom(self._gba_view._zoom)

    def _on_grid8_toggle(self, checked: bool):
        if checked:
            self._chk_grid16.blockSignals(True)
            self._chk_grid16.setChecked(False)
            self._chk_grid16.blockSignals(False)
        self._gba_scene.set_grid(checked, cell=8)

    def _on_grid16_toggle(self, checked: bool):
        if checked:
            self._chk_grid8.blockSignals(True)
            self._chk_grid8.setChecked(False)
            self._chk_grid8.blockSignals(False)
        self._gba_scene.set_grid(checked, cell=16)

    def _on_snap_toggle(self, checked: bool):
        self._gba_scene.set_snap(checked)
        self._gba_view.set_snap(checked)

    def _on_boxes_actors_toggle(self, checked: bool):
        self._show_all_boxes = checked
        self._update_actor_box_overlay()

    def _on_collision_view_toggle(self, checked: bool):
        self._gba_scene.set_collision_view(checked)

    def _on_ui_elements_toggle(self, checked: bool):
        self._gba_scene.set_ui_elements_view(checked)
        self._apply_editor_visibility()

    def _update_actor_box_overlay(self):
        if not self._project:
            self._gba_scene.update_actor_boxes([])
            return
        # Valeurs par défaut des variables déclarées — pour dessiner les box
        # dont un champ (x/y/w/h) référence un global/const plutôt qu'un littéral.
        from core.models.field_value import var_defaults_from_project
        var_defaults = var_defaults_from_project(self._project)
        if self._show_all_boxes:
            self._gba_scene.update_actor_boxes(self._project.active_scene.actors, var_defaults)
        else:
            actors = [
                item.scene_sprite
                for item in self._gba_scene._sprite_items
                if item.isSelected()
            ]
            self._gba_scene.update_actor_boxes(actors, var_defaults)

    # ── Outil actif ───────────────────────────────────────────────

    def _on_tool_changed(self, tool_id: str):
        from ui.scene_manager.canvas_tools import AddActorTool, CollisionTool, EraseTool, SelectTool

        match tool_id:
            case t if t.startswith("collision"):
                from ui.scene_manager.canvas_tools import CollisionTool

                self._gba_view.set_tool(CollisionTool(self._gba_view, t))
            case t if t.startswith("inpaint"):
                from ui.scene_manager.canvas_tools import SceneInpaintingTool

                self._gba_view.set_tool(SceneInpaintingTool(self._gba_view, t))
            case "add":
                self._gba_view.set_tool(AddActorTool(self._gba_view))
            case "erase":
                self._gba_view.set_tool(EraseTool(self._gba_view))
            case t if t.startswith("ui_"):
                from ui.scene_manager.canvas_tools import UIWidgetTool

                # "ui_text" | "ui_container" | "ui_image" → kind du modèle
                self._gba_view.set_tool(UIWidgetTool(self._gba_view, t[3:]))
            case _:
                self._gba_view.set_tool(SelectTool(self._gba_view))
        # Bandeau de palette visible seulement pour les outils de peinture BG.
        self._canvas_container.set_inpaint_strip_visible(tool_id.startswith("inpaint"))

    def _reload_ui_regions(self):
        """(Re)dessine les éléments de TOUS les nœuds `Interface` de la scène
        active (v0.25)."""
        scene = self._project.active_scene if self._project else None
        layouts = (self._project.scene_ui_layouts(scene)
                   if (self._project and scene) else [])
        self._gba_scene.set_ui_regions(layouts, self._project, scene,
                                       save_fn=self._save_ui_regions)
        self._apply_editor_visibility()
        self.ui_regions_reloaded.emit()

    def _save_ui_regions(self):
        """Persiste après un déplacement de zone au canvas, et recharge
        l'inspecteur : ses spinbox montreraient sinon l'ancienne position."""
        if not self._project:
            return
        # Écriture par le dispatcher (watcher suspendu) — cf. la même règle dans
        # UIRegionInspector._persist : une écriture nue passe pour une édition
        # externe et déclenche un rechargement de scène en plein geste.
        get_dispatcher().save_all()
        self.scene_changed.emit()
        from core.selection_bus import get_bus, UIRegionSelection
        cur = get_bus().current
        if isinstance(cur, UIRegionSelection):
            get_bus().changed.emit(cur)

    def _on_region_created(self, layout, region):
        """Sélectionne la zone et l'annonce. La sauvegarde et le redessin
        passent par `regions_changed` — eux doivent aussi jouer à l'annulation.

        La mise en page est un asset PARTAGÉ : le message dit combien de scènes
        la référencent, sinon on ajoute une zone à douze scènes en croyant
        l'ajouter à une."""
        if not self._project:
            return
        from core.selection_bus import get_bus, UIRegionSelection
        get_bus().select(UIRegionSelection(layout, region))
        users = self._project.ui_layout_users(layout.name)
        shared = label('scncanvas.shared_layout', count=len(users)) if len(users) > 1 else ""
        # L'empreinte en tuiles ne se dit que pour ce qui occupe la tilemap ;
        # une image l'annonce dans son inspecteur, d'après son sprite.
        tiles = ""
        if getattr(region, "kind", "") != "image" and hasattr(region, "tile_rect"):
            tw, th = region.tile_rect()[2:]
            tiles = label('scncanvas.tile_size', width=tw, height=th)
        get_dispatcher().status(
            label('scncanvas.element_created', name=region.name,
                            layout=layout.name, shared=shared, tiles=tiles))

    def _on_collision_painted(self):
        """Persiste la collision_map après chaque stroke."""
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        scene.collision_map = self._gba_scene.collision_overlay.get_map()
        from core.command_dispatcher import get_dispatcher

        get_dispatcher().save_scene()

    # ── Chargement projet ─────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._sprite_pixmaps.clear()
        self._raw_sprite.clear()

        scene = project.active_scene

        # Calculer la taille du canvas à partir des BG PNG réels
        max_w, max_h = GBA_W, GBA_H
        for layer in (scene.background_layers if scene else []):
            if not layer.background_name:
                continue
            ba = project.get_background(layer.background_name)
            # La taille que le build verra (recadrage/redimensionnement compris),
            # pas celle du PNG : celui-ci n'est plus qu'une SOURCE.
            bw, bh = ba.pixel_size() if ba else (0, 0)
            if bw and bh:
                max_w, max_h = max(max_w, bw), max(max_h, bh)
                continue
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = project.background_images_dir / png
            if ap.exists():
                px = QPixmap(str(ap))
                if not px.isNull():
                    max_w = max(max_w, px.width())
                    max_h = max(max_h, px.height())

        # Clamper au plafond monde (32767, coordonnées s16 de la caméra) — pas à
        # 512 : une carte plus grande est streamée au build, pas interdite.
        self._canvas_w = min(max_w, MAX_CANVAS_W)
        self._canvas_h = min(max_h, MAX_CANVAS_H)
        self._gba_scene.resize_canvas(self._canvas_w, self._canvas_h)
        self._bar.set_canvas_size(self._canvas_w, self._canvas_h)

        # Collision map
        if scene:
            scene.ensure_collision_map(self._canvas_w, self._canvas_h)
            self._gba_scene.collision_overlay.load(scene.collision_map)

        # Backdrop (sous tous les layers)
        self.refresh_backdrop()

        self._setup_cameras(scene)

        # BG layers (sans rescale — taille native)
        shown = set()
        raw_layers: dict[int, QPixmap] = {}
        for layer in (scene.background_layers if scene else []):
            if not layer.background_name:
                continue
            ba = project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = project.background_images_dir / png
            raw_layers[layer.bg_slot] = bg_pixmap(project, scene, layer, ap)
            shown.add(layer.bg_slot)
        # Pixmaps BRUTS, avant tout mélange : c'est eux que `refresh_blend()`
        # recompose quand on tire sur un réglage. Les garder évite de relire les
        # PNG et de requantifier à chaque cran du curseur — la différence entre
        # un aperçu qui suit la souris et un aperçu qui la subit.
        self._raw_bg = dict(raw_layers)
        self._apply_blend_to_canvas()
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # Windows — APRÈS les layers BG : le masquage s'applique aux items
        # fraîchement créés ci-dessus.
        self._gba_scene.set_windows(getattr(scene, "windows", []) if scene else [])

        # Contexte de peinture par palette + peuplement du bandeau de palettes.
        self._inpainting_ctrl.set_context(project, scene)
        self._ui_region_ctrl.set_context(project, scene)
        self._reload_ui_regions()
        self._canvas_container.refresh_inpaint_banks()

        self._reload_sprites()

    def _apply_blend_to_canvas(self):
        """Recompose les layers depuis les pixmaps BRUTS et les repose.

        Séparé du chargement pour être rappelable seul : c'est ce qui rend
        l'aperçu vivant. Rien ici ne touche le disque — le coût est celui de la
        composition, pas celui de la lecture d'un PNG."""
        scene = self._project.active_scene if self._project else None
        raw = dict(getattr(self, "_raw_bg", {}) or {})
        self._blend_bottom = self._apply_layer_blend(scene, raw)
        for slot, px in raw.items():
            self._gba_scene.set_bg(slot, px)
            layer = next((L for L in (scene.background_layers if scene else [])
                          if L.bg_slot == slot), None)
            self._gba_scene.set_bg_visible(slot, getattr(layer, "visible", True))

    def refresh_blend(self):
        """Rejoue le mélange sur les layers ET les sprites, sans rien relire.

        Appelée quand un réglage de mélange change (effet, pourcentage, rôle
        d'un layer). Les items ne sont pas reconstruits : seuls leurs pixmaps
        changent, donc la sélection, le drag en cours et les poignées survivent
        — ce qui compte quand on tire sur un curseur en regardant le résultat.

        Les windows sont réappliquées après coup : `set_bg` recrée les items de
        layer, et leur masquage vit sur l'item, pas sur la scène."""
        if not self._project or not self._project.active_scene:
            return
        self._apply_blend_to_canvas()
        for item in self._gba_scene._sprite_items:
            raw = self._raw_sprite.get(id(item.scene_sprite))
            if raw is not None:
                item.setPixmap(self._blend_sprite(item.scene_sprite, raw))
        scene = self._project.active_scene
        self._gba_scene.set_windows(getattr(scene, "windows", []))

    def _apply_layer_blend(self, scene, raw_layers: dict) -> Optional[QPixmap]:
        """Remplace SUR PLACE les pixmaps des layers « dessus » par leur version
        mélangée, et rend ce qui se trouve derrière les SPRITES.

        Le dessous d'une couche, c'est la **première couche visible derrière
        elle, quelle qu'elle soit** — pas la première seconde cible. Une couche
        opaque hors du set occulte quand même ce qui est derrière et empêche
        donc le mélange à cet endroit (« le blending ne saute pas une couche »).
        Ne collecter que les secondes cibles faisait traverser le backdrop à
        travers un décor plein, et teintait tout l'écran en permanence.

        L'ordre de priorité GBA suit le numéro de BG : le codegen émet
        `pri = bg` et 0 est DEVANT, donc « derrière BG_n » = les slots de numéro
        SUPÉRIEUR, puis le backdrop.

        Rend None quand la scène ne mélange rien : l'appelant saute alors tout
        le chemin, et le canvas se comporte exactement comme avant."""
        from core.engine_emulation.blend_preview import blend_images, resolve_bottom, scene_blend_plan
        from core.models.scene import BLEND_BOTTOM
        if scene is None:
            return None
        plan = scene_blend_plan(scene)
        if plan is None:
            return None
        w, h = self._canvas_w, self._canvas_h
        bd = self._backdrop_qcolor()
        bd_rgb = (bd.red(), bd.green(), bd.blue())
        bd_target = plan["backdrop_role"] == BLEND_BOTTOM

        source = dict(raw_layers)

        def bottom_of(behind_of: Optional[int]):
            """Ce qui est immédiatement derrière `behind_of`, du plus AVANT au
            plus arrière. `None` = derrière les sprites, qui passent devant
            tous les layers — leur dessous est donc la pile entière."""
            slots = sorted(s for s in source
                           if behind_of is None or s > behind_of)
            entries = [(source[s].toImage(),
                        s in plan["bottom_slots"]) for s in slots]
            return resolve_bottom(entries, w, h, bd_rgb, bd_target)

        for slot in plan["top_slots"]:
            px = raw_layers.get(slot)
            if px is None or px.isNull():
                continue
            raw_layers[slot] = QPixmap.fromImage(blend_images(
                px.toImage(), bottom_of(slot),
                plan["mode"], plan["eva"], plan["evb"], plan["evy"]))
        return bottom_of(None)

    def _blend_sprite(self, actor, px: QPixmap) -> QPixmap:
        """Frame d'un acteur, mélangée si elle est une première cible.

        **Deux portes distinctes**, et c'est la source de confusion la plus
        commune du blending GBA :
          • `Scene.blend_obj_role == "top"` met TOUS les sprites dans la
            première cible, via BLDCNT comme un layer ;
          • `Actor.obj_mode == 1` (semi-transparent) force l'alpha pour CE
            sprite seul, quelles que soient les cibles de BLDCNT — mais il
            emploie quand même EVA/EVB, et il ne fait rien sans seconde cible.
        Un sprite peut donc être mélangé alors qu'aucun layer ne l'est.

        Le « dessous » est le composite des secondes cibles calculé au chargement
        des layers : un sprite est devant tous les layers, il n'y a donc pas de
        sous-ensemble à choisir selon sa position. Le découpage à sa POSITION
        n'est pas fait — le mélange est calculé contre le dessous entier, ce qui
        est exact tant que le dessous est uniforme sous le sprite. Un dessous
        qui varie sous le sprite demanderait de recomposer à chaque déplacement ;
        c'est la limite assumée de l'aperçu, pas du moteur."""
        from core.engine_emulation.blend_preview import blend_images, scene_blend_plan
        from core.models.scene import BLEND_TOP, BLEND_ALPHA
        scene = self._project.active_scene if self._project else None
        plan = scene_blend_plan(scene) if scene else None
        obj_semi = int(getattr(actor, "obj_mode", 0) or 0) == 1
        if plan is None and not obj_semi:
            return px
        if plan is None:
            return px          # obj_mode 1 sans mode de scène : rien à mélanger
        if plan["obj_role"] != BLEND_TOP and not obj_semi:
            return px
        # Un sprite semi-transparent est en ALPHA par construction, même si la
        # scène est réglée sur un fondu : le mode OAM ne lit pas BLDCNT.
        mode = BLEND_ALPHA if obj_semi else plan["mode"]
        return QPixmap.fromImage(blend_images(
            px.toImage(), getattr(self, "_blend_bottom", None),
            mode, plan["eva"], plan["evb"], plan["evy"]))

    def _backdrop_qcolor(self) -> QColor:
        """Couleur du backdrop de la scène, résolue comme le canvas la peint."""
        scene = self._project.active_scene if self._project else None
        raw = getattr(scene, "backdrop_color", None)
        if raw is None and self._project:
            raw = getattr(self._project.settings, "backdrop_color", 0)
        from core.models.gba_color import bgr555_to_rgb888
        r, g, b = bgr555_to_rgb888(int(raw or 0))
        return QColor(r, g, b)

    def _reload_sprites(self):
        if not self._project:
            return
        # Mémoriser la sélection avant le rebuild (par id, Actor est unhashable)
        prev_selected_ids = {
            id(item.scene_sprite)
            for item in self._gba_scene._sprite_items
            if item.isSelected()
        }
        # Bloquer les signaux AVANT clear pour que selectionChanged ne fire pas
        # pendant le rebuild et ne vide pas l'inspector via get_bus().clear()
        self._gba_scene.blockSignals(True)
        self._gba_scene.clear_sprites()
        p = self._project

        # Résolveur des positions référençant une variable (défaut de la var).
        from core.models.field_value import make_resolver
        _pos_resolver = make_resolver(p)

        scene = p.active_scene
        _placeholder: QPixmap | None = None
        for actor in scene.actors:
            # L'apparence AFFICHÉE, comme le build (cf. displayed_sprite_component) :
            # le canvas ne dessine pas un sprite que la ROM n'afficherait pas.
            sprite_comp = displayed_sprite_component(actor)
            sprite = (
                p.get_sprite(sprite_comp.sprite_name)
                if sprite_comp and sprite_comp.sprite_name
                else None
            )
            ap = p.asset_abs(sprite.asset) if sprite and sprite.asset else None
            frame_px = None
            dir_fh = dir_fv = False
            if sprite and ap and ap.exists():
                preview_frame, dir_fh, dir_fv = preview_frame_for_actor(
                    sprite, sprite_comp, actor)
                if preview_frame is not None:
                    img = compose_frame_image(ap, preview_frame, sprite.frame_w, sprite.frame_h)
                    bank = resolve_obj_palette_bank(p, actor, scene)
                    img = quantize_preview(img, sprite, bank)
                    if img.width > 0 and img.height > 0:
                        data = bytes(img.tobytes("raw", "RGBA"))
                        qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                        frame_px = QPixmap.fromImage(qi)
            is_placeholder = frame_px is None
            if is_placeholder:
                if _placeholder is None:
                    _placeholder = make_placeholder_pixmap()
                frame_px = _placeholder
            else:
                # La frame BRUTE est gardée à part : `refresh_blend()` rejoue le
                # mélange dessus sans recomposer la frame depuis son PNG. Un
                # placeholder n'y entre pas — il ne représente aucun pixel réel.
                self._raw_sprite[id(actor)] = frame_px
                frame_px = self._blend_sprite(actor, frame_px)
            self._sprite_pixmaps[id(actor)] = frame_px
            save_fn = lambda _s=self: _s.scene_changed.emit()
            ox  = getattr(sprite_comp, "origin_x", 0)   if sprite_comp else 0
            oy  = getattr(sprite_comp, "origin_y", 0)   if sprite_comp else 0
            # Transform affine MONDE (Actor) × LOCAL (SpriteComponent), comme au
            # runtime : le sprite hérite scale (produit) et rotation (somme) de
            # son actor, et se place en offset dans le repère local de l'actor.
            # Sans "Affine transform" sur le SPRITE, aucun slot n'est réservé au
            # build : rien de tout ça ne s'affiche, ni le transform de l'actor ni
            # celui du sprite — le canvas montre donc l'identité (0°/100%), comme
            # la ROM.
            _aff = bool(getattr(sprite_comp, "affine_transform", False)) if sprite_comp else False
            asx = getattr(actor, "scale_x", 1.0)  if _aff else 1.0
            asy = getattr(actor, "scale_y", 1.0)  if _aff else 1.0
            arot = getattr(actor, "rotation", 0)  if _aff else 0
            sx  = (getattr(sprite_comp, "scale_x",  1.0) if _aff else 1.0) * asx
            sy  = (getattr(sprite_comp, "scale_y",  1.0) if _aff else 1.0) * asy
            rot = (getattr(sprite_comp, "rotation", 0.0) if _aff else 0.0) + arot
            off_x = getattr(sprite_comp, "offset_x", 0) if (sprite_comp and _aff) else 0
            off_y = getattr(sprite_comp, "offset_y", 0) if (sprite_comp and _aff) else 0
            # Flip effectif = flip du component XOR flip de la direction miroir
            # (ex. Ouest = miroir horizontal de l'Est).
            fh  = bool(getattr(sprite_comp, "flip_h", False) if sprite_comp else False) ^ dir_fh
            fv  = bool(getattr(sprite_comp, "flip_v", False) if sprite_comp else False) ^ dir_fv
            item = self._gba_scene.add_sprite(
                frame_px, actor, save_fn=save_fn,
                origin_x=ox + off_x, origin_y=oy + off_y, scale_x=sx, scale_y=sy,
                rotation=rot, flip_h=fh, flip_v=fv,
                resolver=_pos_resolver, placeholder=is_placeholder,
            )
            item.scene_sprite = actor

        # Restaurer la sélection, puis débloquer
        for item in self._gba_scene._sprite_items:
            if id(item.scene_sprite) in prev_selected_ids:
                item.setSelected(True)
        self._gba_scene.blockSignals(False)
        self._apply_editor_visibility()

        if prev_selected_ids:
            self._update_actor_box_overlay()

    # ── Changements items ─────────────────────────────────────────

    def _on_scene_item_changed(self):
        """Appelé quand n'importe quel item de la scène change (position, etc.)."""
        if not self._project or not self._project.active_scene:
            return
        # Si une caméra est sélectionnée, mettre à jour l'inspecteur avec sa
        # nouvelle position — n'importe laquelle des caméras de la scène.
        for item in self._gba_scene.camera_items():
            if item.isSelected():
                x, y = int(item.pos().x()), int(item.pos().y())
                self._write_camera_pos(x, y, item)
                self.camera_position_changed.emit(item.camera, x, y)
                self.scene_changed.emit()

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selection_changed(self):
        """Qt selectionChanged → émettre vers le bus (jamais vers les autres panels)."""
        try:
            selected = self._gba_scene.selectedItems()
        except RuntimeError:
            # La scène Qt sous-jacente a été détruite entre l'émission du
            # signal et le traitement de ce slot (rebuild de la scène en
            # cours) — rien à traiter, elle n'existe déjà plus.
            return
        # L'item ACTIF doit rester membre de la sélection : un rubber band ou
        # une suppression peut l'avoir laissé de côté (règle : à défaut, le
        # premier membre devient actif).
        self._gba_scene.reconcile_active()
        if not selected:
            # Clic dans la zone active du canvas (sceneRect, cf. GBAScene) sans
            # rien toucher → sélection de la SCÈNE elle-même (SceneInspector,
            # comme Actor/Prefab affichent leur propre inspecteur). Ceci est
            # DISTINCT d'un clic sur l'icône caméra (ci-dessous, marqué
            # CameraSelection) : le rectangle de vue 240×160 n'est qu'un retour
            # visuel, il ne doit pas « prendre » le clic ni ouvrir l'inspecteur
            # caméra à la place. Clic en dehors — ou toute autre cause de
            # désélection (Échap, suppression du dernier actor…) où aucune
            # position de clic n'est disponible — → tout désélectionner,
            # l'inspecteur retombe sur son mode par défaut (aperçu du projet).
            pos = self._gba_view._last_click_scene_pos
            in_canvas = pos is not None and self._gba_scene.sceneRect().contains(pos)
            if in_canvas and self._project and self._project.active_scene:
                get_bus().select(self._project.active_scene)
            else:
                get_bus().clear()
            if not self._show_all_boxes:
                self._gba_scene.update_actor_boxes([])
            return
        # Le bus transporte l'item ACTIF (pas « le premier de la liste Qt ») :
        # c'est lui que l'inspecteur détaille. La caméra n'entre pas dans la
        # multi-sélection, elle garde son chemin propre.
        target = self._gba_scene.active_item or selected[0]
        if isinstance(target, CameraItem):
            if self._project and self._project.active_scene:
                # Sélectionner n'est pas régler : on ne matérialise pas la
                # caméra par défaut ici, seulement au premier vrai déplacement.
                get_bus().select(CameraSelection(self._project.active_scene, target.camera))
        elif isinstance(target, SpriteItem):
            actors = [item.scene_sprite for item in selected if isinstance(item, SpriteItem)]
            if len(actors) > 1:
                from core.selection_bus import ActorSelection
                get_bus().select(ActorSelection(actors, target.scene_sprite))
            else:
                get_bus().select(target.scene_sprite)
        elif isinstance(target, UIRegionItem):
            from core.selection_bus import UIRegionSelection
            get_bus().select(UIRegionSelection(target._layout, target._region))
        self._update_actor_box_overlay()

    def _item_for_selection(self, obj):
        """Item canvas correspondant à un objet du bus (Actor / zone de texte),
        ou None. La caméra a son propre chemin (elle n'entre pas dans la
        multi-sélection)."""
        from core.selection_bus import UIRegionSelection
        if isinstance(obj, Actor):
            return self._find_item(obj)
        if isinstance(obj, UIRegionSelection):
            for it in self._gba_scene._ui_region_items:
                if it._region is obj.region:
                    return it
        return None

    def on_selection(self, obj):
        """Reçu du bus — aligner le canvas sans reboucler.

        Si l'objet reçu est DÉJÀ membre de la sélection courante, la sélection
        n'est pas touchée : on se contente de le désigner ACTIF. Sans ce cas,
        n'importe quel aller-retour du bus (clic dans un autre panneau,
        rafraîchissement d'inspecteur, resynchro d'une multi-sélection) ramenait
        la sélection à un seul item."""
        target = self._item_for_selection(obj)
        if target is not None and target.isSelected():
            self._gba_scene.set_active_item(target)
            return

        self._gba_scene.blockSignals(True)
        # Désélectionner tout d'abord
        for item in self._gba_scene.selectedItems():
            item.setSelected(False)
        from core.selection_bus import ActorSelection
        if isinstance(obj, ActorSelection):
            active_item = None
            for actor in obj.actors:
                item = self._find_item(actor)
                if item:
                    item.setSelected(True)
                    if actor is obj.active:
                        active_item = item
            if active_item:
                self._gba_view.centerOn(active_item)
        elif isinstance(obj, Actor):
            item = self._find_item(obj)
            if item:
                item.setSelected(True)
                self._gba_view.centerOn(item)
        elif isinstance(obj, CameraSelection):
            # Re-sélectionner l'item caméra pour cet aller-retour bus : sans ce
            # cas, le clic sur l'icône (qui sélectionne nativement la caméra
            # via Qt AVANT même d'émettre CameraSelection sur le bus) se faisait
            # aussitôt désélectionner par la boucle ci-dessus — l'overlay jaune
            # (self._view) clignotait et restait dans un état incohérent avec
            # isSelected(). En NE traitant PAS ce cas ici (tout autre obj), la
            # caméra reste déselectionnée et son overlay disparaît fiablement.
            item = next((it for it in self._gba_scene.camera_items()
                        if it.camera is obj.camera), None)
            if item:
                item.setSelected(True)
        else:
            # Même raison que la caméra : la zone s'annonce sur le bus AVANT que
            # Qt ne la sélectionne (cf. UIRegionItem.mousePressEvent), et le bus
            # est réémis après un drag ou une édition. Sans ce cas, la boucle de
            # désélection ci-dessus effaçait le liseré d'une zone que
            # l'inspecteur montre pourtant comme sélectionnée.
            from core.selection_bus import UIRegionSelection
            if isinstance(obj, UIRegionSelection):
                for it in self._gba_scene._ui_region_items:
                    if it._region is obj.region:
                        it.setSelected(True)
                        break
        self._gba_scene.blockSignals(False)
        # Sélection ramenée à un seul item : c'est lui l'actif (sinon plus
        # aucun — la caméra et la scène « nue » n'en ont pas).
        if isinstance(obj, ActorSelection):
            self._gba_scene.set_active_item(self._find_item(obj.active))
        else:
            self._gba_scene.set_active_item(self._item_for_selection(obj))

    def move_actor_item(self, actor: Actor):
        """Repositionne l'item Qt d'un actor sans recréer la scène (drag ou spinbox)."""
        item = self._find_item(actor)
        if item:
            # Bascule de `screen_space` : le repère change, pas seulement la
            # position — sync_sprite_space repositionne aussi.
            self._gba_scene.sync_sprite_space(item)

    def _find_item(self, actor: Actor) -> Optional[SpriteItem]:
        for item in self._gba_scene._sprite_items:
            if item.scene_sprite is actor:
                return item
        return None

    def move_camera_item(self, camera):
        """Repositionne/redimensionne l'item Qt d'une caméra sans recréer la
        scène — appelé quand la position ou le frame ont été édités dans
        l'inspecteur (cf. CameraInspector.camera_moved), symétrique de
        `move_actor_item`."""
        for item in self._gba_scene.camera_items():
            if item.camera is camera:
                item.setPos(camera.x, camera.y)
                item.set_frame_size(camera.frame_w, camera.frame_h)
                return

    # ── Caméras : (re)construction et sauvegarde de position ───────

    def _setup_cameras(self, scene):
        """(Re)construit tous les items caméra de `scene` : celle de
        démarrage (`scene.camera` — porte sprites écran + windows) et les
        autres (rectangles indépendants). Factorisé pour servir à la fois au
        rechargement complet (`load_project`) et au rafraîchissement léger
        après ajout/suppression/renommage depuis le scene tree
        (`refresh_cameras`)."""
        _cam = self._project.scene_camera(scene) if (self._project and scene) else None
        self._gba_scene.setup_camera(_cam.x if _cam else 0, _cam.y if _cam else 0, camera=_cam)
        _others = [c for c in (scene.cameras if scene else []) if c is not _cam]
        self._gba_scene.setup_extra_cameras(_others)

    def refresh_cameras(self):
        """Reconstruit uniquement les items caméra — appelé après
        add_camera/delete_camera/rename_camera (événement
        `cameras_list_changed`), sans recharger tout le reste de la scène."""
        if self._project and self._project.active_scene:
            self._setup_cameras(self._project.active_scene)
            self._apply_editor_visibility()

    def reload_scene_items(self):
        """Resynchronise TOUS les items du canvas depuis le modèle — sprites,
        caméras, zones d'interface — sans toucher au zoom/pan ni aux fonds.

        C'est ce que la fenêtre appelle après un undo/redo (« le modèle en
        mémoire fait foi »). Reposer les seuls sprites ne suffit pas : un item de
        caméra ou de zone déplacé puis ANNULÉ resterait à sa position draggée
        alors que le modèle est revenu (cf. TodoTechnique, Correctifs). Point
        unique de la resynchro d'items pour ne pas oublier une famille."""
        self._reload_sprites()
        self.refresh_cameras()
        self._reload_ui_regions()

    def has_pending_save(self) -> bool:
        """Un déplacement au clavier attend encore son écriture (debounce)."""
        return self._nudge_save_timer.isActive()

    def flush_camera_pos(self):
        """Appelé avant save_scene pour persister le cadrage de TOUTES les
        caméras dont l'item a bougé (démarrage + autres)."""
        if not self._project or not self._project.active_scene:
            return
        for item in self._gba_scene.camera_items():
            x, y = int(item.pos().x()), int(item.pos().y())
            self._write_camera_pos(x, y, item)

    def _write_camera_pos(self, x: int, y: int, item):
        """Écrit le cadrage dans la caméra possédée par la scène active.

        `item.camera is None` désigne l'item de démarrage à l'état implicite :
        déplacer le cadre est un réglage, c'est ici qu'une vraie caméra naît
        (`ensure_scene_camera`) — l'item est alors rebranché sur l'objet réel,
        sinon un second déplacement dans le même geste la matérialiserait à
        chaque fois sans jamais reconnaître qu'elle existe déjà. Ne rien faire
        quand la position est déjà celle du défaut évite d'en créer une au
        premier clic sur le rectangle. Une caméra déjà réelle (démarrage ou
        non) s'écrit directement, sans matérialisation."""
        scene = self._project.active_scene if self._project else None
        if scene is None:
            return
        cam = item.camera
        if cam is None:
            if x == 0 and y == 0:
                return
            cam = self._project.ensure_scene_camera(scene)
            item.camera = cam
        if (cam.x, cam.y) == (x, y):
            return
        # Annulable comme un drag d'actor (cf. MoveActorCmd) : la MATÉRIALISATION
        # ci-dessus reste hors historique, seul le cadrage se défait.
        from core.history import get_history, MoveCameraCmd
        get_history().push(MoveCameraCmd(
            cam, cam.x, cam.y, x, y,
            persist_fn=lambda s=scene: self._project.save_scene(s)))

    def _on_prefab_template_dropped(self, prefab_name: str, pos: QPointF):
        if not self._project or not self._project.active_scene:
            return
        x = max(0, min(int(pos.x()), self._canvas_w))
        y = max(0, min(int(pos.y()), self._canvas_h))
        get_dispatcher().instantiate_prefab(prefab_name, x, y)

    def refresh_bg(self, bg_index: int = 0):
        """Recharge tous les BG depuis le BackgroundAsset actif de la scène."""
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        shown = set()
        for layer in scene.background_layers:
            if not layer.background_name:
                continue
            ba = self._project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = self._project.background_images_dir / png
            self._gba_scene.set_bg(layer.bg_slot, bg_pixmap(self._project, scene, layer, ap))
            self._gba_scene.set_bg_visible(layer.bg_slot, getattr(layer, "visible", True))
            shown.add(layer.bg_slot)
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # Les items BG viennent d'être recréés : réappliquer le découpage des
        # windows, sinon il est perdu à chaque rafraîchissement de fond.
        self._gba_scene.update_window_masks()

        # La banque de base / les layers ont pu changer : resynchroniser le
        # contrôleur de peinture (raster du layer actif) et le bandeau.
        prev_slot = self._inpainting_ctrl.inpaint_layer_slot
        self._inpainting_ctrl.set_context(self._project, scene)
        self._ui_region_ctrl.set_context(self._project, scene)
        self._reload_ui_regions()
        self._inpainting_ctrl.set_inpaint_layer(prev_slot)
        self._canvas_container.refresh_inpaint_banks()

    def set_inpaint_layer(self, bg_slot: int):
        """Choisit le layer BG peint par l'outil de peinture (via l'inspecteur)."""
        self._inpainting_ctrl.set_inpaint_layer(bg_slot)

    def set_layer_visible(self, bg_slot: int, visible: bool):
        """Masque/affiche un layer dans le canvas (visibilité viewport éditeur)."""
        self._gba_scene.set_bg_visible(bg_slot, visible)

    def set_editor_hidden_members(self, members: set[str] | list[str] | tuple[str, ...]):
        """Applique les masques du Scene Tree au Canvas, sans muter le jeu.

        ``members`` est issu du sidecar éditorial (``actor:…``, ``camera:…``,
        ``ui:…``). Il ne touche donc jamais ``Actor.visible`` ni la visibilité
        authorée des éléments d'interface.
        """
        self._editor_hidden_members = set(members)
        self._apply_editor_visibility()

    def _apply_editor_visibility(self):
        hidden = self._editor_hidden_members
        for item in self._gba_scene._sprite_items:
            item.setVisible(f"actor:{item.scene_sprite.name}" not in hidden)
        for item in self._gba_scene.camera_items():
            name = getattr(item.camera, "name", "")
            item.setVisible(f"camera:{name}" not in hidden)
        for item in self._gba_scene._ui_region_items:
            layout = getattr(item, "_layout", None)
            name = getattr(layout, "name", "")
            element = getattr(item, "_region", None)
            element_name = getattr(element, "name", "")
            item.setVisible(
                self._gba_scene._ui_elements_visible
                and f"ui:{name}" not in hidden
                and f"ui_element:{name}:{element_name}" not in hidden)
        self._update_actor_box_overlay()

    def refresh_windows(self):
        """Redessine l'aperçu des windows (après édition dans l'inspecteur)."""
        scene = self._project.active_scene if self._project else None
        self._gba_scene.set_windows(getattr(scene, "windows", []) if scene else [])

    def refresh_backdrop(self):
        """Réapplique la couleur de backdrop (override de scène, sinon projet)."""
        if not self._project:
            return
        scene = self._project.active_scene
        v = getattr(scene, "backdrop_color", None) if scene else None
        if v is None:
            v = self._project.settings.backdrop_color
        self._gba_scene.set_backdrop(v)

    def update_actor_position(self, actor: Actor):
        item = self._find_item(actor)
        if item:
            item.sync_pos()
