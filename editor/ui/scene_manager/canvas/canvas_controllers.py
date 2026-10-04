"""ui/scene_manager/canvas/canvas_controllers.py — les contrôleurs du canvas.

Extrait de `scene_canvas` (A3) : la logique NON graphique du canvas.
`UIRegionController` crée/duplique/colle/supprime les éléments d'interface (via le
dispatcher, donc annulable) ; `SceneInpaintingController` pilote la peinture par
palette d'un layer BG (strokes d'inpaint, rebuild du pixmap) ; `CanvasClipboard`
est le presse-papier interne du copier/coller.

Dépend vers le bas : modèle, dispatcher/historique, `selection_bus`, et
`canvas_raster`/`canvas_scene` pour l'inpaint. Aucun de ceux-là ne l'importe.
"""
from __future__ import annotations

import copy
from typing import Optional

from core.project import Project
from core.command_dispatcher import get_dispatcher
from core.selection_bus import get_bus
from codegen.grit_conversion import resolve_palette_bank
from ui.scene_manager.canvas.canvas_raster import (
    BgLayerRaster, build_bg_raster, layer_png_path,
)
from ui.scene_manager.canvas.canvas_scene import GBAScene
from PyQt6.QtCore import QObject, pyqtSignal


class UIRegionController(QObject):
    """Crée et persiste les zones de texte dessinées dans le canvas.

    Analogue à `SceneInpaintingController` : détient le contexte (projet,
    scène) et applique le geste de l'outil au modèle.

    **Crée la mise en page à la demande.** Dessiner une zone dans une scène qui
    n'en référence aucune en fabrique une, nommée d'après la scène. Obliger à
    créer d'abord une mise en page vide, puis à la référencer, puis à dessiner,
    ferait payer trois gestes pour une intention — alors que le cas courant est
    « une mise en page par scène » et qu'elle reste partageable ensuite.

    L'unicité du nom est cherchée sur TOUT le projet : c'est l'espace de noms
    des constantes `REGION_*` (cf. models/ui_region.py)."""

    # Deux signaux et pas un : `persist_fn` d'une commande d'historique est
    # rappelé à l'ANNULATION comme à l'exécution. Confondre les deux ferait
    # annoncer « zone créée » en annulant sa création, et resélectionnerait une
    # zone qui vient d'être retirée.
    regions_changed = pyqtSignal()                # sauver + redessiner
    region_created  = pyqtSignal(object, object)  # (UILayout, UIRegion) — une fois

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._scene = None
        # Dernier nœud `Interface` que la sélection a désigné : récepteur par
        # défaut d'un widget dessiné quand la scène en compte plusieurs
        # (v0.25, cf. `_ensure_layout`). Suivi par le BUS et pas par un clic
        # sur le canvas — sélectionner le nœud dans l'arbre de scène doit
        # compter tout autant que cliquer un de ses éléments.
        self._active_layout = None
        get_bus().changed.connect(self._track_selected_layout)

    def _track_selected_layout(self, obj):
        # UILayoutSelection (le nœud lui-même) comme UIElementSelection (un de
        # ses éléments) portent `.layout` ; un acteur ou une caméra, non — donc
        # sélectionner autre chose n'efface pas le dernier nœud retenu.
        lay = getattr(obj, "layout", None)
        if lay is not None:
            self._active_layout = lay

    def set_context(self, project: Optional[Project], scene):
        self._project, self._scene = project, scene

    @property
    def ready(self) -> bool:
        return self._project is not None and self._scene is not None

    def receiving_anchor(self) -> str:
        """Ancrage du nœud `Interface` qui recevrait un widget dessiné MAINTENANT
        (sans en créer un) ; « screen » si la scène n'en a pas encore — c'est
        l'ancrage d'un nœud neuf."""
        from core.models.ui_region import ANCHOR_SCREEN
        if not self.ready:
            return ANCHOR_SCREEN
        bounds = self._project.scene_ui_layouts(self._scene)
        for b in bounds:
            if b.layout is self._active_layout:
                return b.anchor
        return bounds[0].anchor if bounds else ANCHOR_SCREEN

    def _ensure_layout(self):
        from core.models.ui_region import UILayout
        # La scène référence une LISTE de nœuds `Interface` (v0.25). Le
        # récepteur d'un widget dessiné est le DERNIER nœud sélectionné s'il
        # appartient encore à la scène active ; sinon le premier (défaut
        # stable) ; sinon un nœud neuf créé à la volée — dessiner dans une
        # scène vierge reste le cas d'usage principal.
        # `scene_ui_layouts` rend des `BoundInterface` ; l'édition de CONTENU vise
        # l'asset `UILayout` (`.layout`), pas la vue liée. `_active_layout` est déjà
        # un asset (cf. `_track_selected_layout`), d'où la comparaison par identité
        # d'asset.
        from core.models.ui_region import InterfaceNode
        bounds = self._project.scene_ui_layouts(self._scene)
        if bounds:
            for b in bounds:
                if b.layout is self._active_layout:
                    return b.layout
            return bounds[0].layout
        base = getattr(self._scene, "name", "") or "ui"
        name, n = base, 2
        while self._project.get_ui_layout(name) is not None:
            name = f"{base}_{n:02d}"; n += 1
        lay = UILayout(name=name)
        self._project.ui_layouts.append(lay)
        if not any(nd.layout_name == name for nd in self._scene.ui_layouts):
            self._scene.ui_layouts.append(InterfaceNode(layout_name=name))
        return lay

    def create_element(self, kind: str, x: int, y: int, w: int, h: int):
        """Crée un élément du `kind` demandé (texte, conteneur, image) au
        rectangle dessiné — même flux pour les trois types, seule la fabrique
        change. L'unicité se cherche sur TOUT le projet, quel que soit le type
        (cf. `Project.ui_element_names`).

        Une image neuve n'a pas de sprite : elle garde le rectangle dessiné
        jusqu'à ce qu'on lui en donne un, et l'inspecteur la redimensionnera
        alors sur sa frame. Lui en attribuer un d'office (« le premier du
        projet ») poserait un dessin que personne n'a demandé."""
        from core.models.ui_region import (
            UIContainer, UIList, UIText, UIImage,
            KIND_CONTAINER, KIND_LIST, KIND_IMAGE, unique_element_name,
        )
        from core.history import get_history, AddListItemCmd
        if not self.ready:
            return None
        lay = self._ensure_layout()
        if self._project.seed_default_ui_palette(self._scene):
            get_dispatcher().save_scene()
        x, y, w, h = int(x), int(y), int(w), int(h)
        taken = set(lay.element_names()) | set(self._project.ui_element_names())
        if kind == KIND_CONTAINER:
            el = UIContainer(name=unique_element_name(taken, "container"),
                         x=x, y=y, w=w, h=h)
            label = "container"
        elif kind == KIND_LIST:
            el = UIList(name=unique_element_name(taken, "list"),
                        x=x, y=y, w=w, h=h)
            label = "list"
        elif kind == KIND_IMAGE:
            el = UIImage(name=unique_element_name(taken, "image"),
                         x=x, y=y, w=w, h=h)
            label = "image"
        else:
            el = UIText(name=unique_element_name(taken, "text"),
                        x=x, y=y, w=w, h=h)
            label = "text"
        # Par l'historique : dessiner un élément est une modification comme une
        # autre, elle doit s'annuler. `_ensure_layout` reste hors historique —
        # une mise en page vide et non référencée ne gêne personne, alors qu'un
        # undo qui la retire casserait les éléments créés ensuite.
        get_history().push(AddListItemCmd(
            lay.elements, el, persist_fn=self.regions_changed.emit,
            label=f"Add {label} {el.name}"))
        self.region_created.emit(lay, el)
        return el

    def create_region(self, x: int, y: int, w: int, h: int):
        """Alias historique — un emplacement de texte."""
        from core.models.ui_region import KIND_TEXT
        return self.create_element(KIND_TEXT, x, y, w, h)

    # ── Dupliquer / coller ────────────────────────────────────────

    def _layout_of(self, element):
        """Le nœud `Interface` qui CONTIENT `element`, parmi les N de la scène
        du contexte (v0.25). Par identité — deux éléments de nœuds différents
        peuvent porter le même nom d'un projet à l'autre, mais pas le même objet.

        La scène est celle du CONTEXTE (`set_context`), pas `active_scene` : les
        deux divergent le temps d'une bascule, et lire `active_scene` faisait
        chercher `copy_groups` dans la mauvaise scène — copie vide alors que le
        collage (qui lit déjà `self._scene`) visait la bonne."""
        if not self._project or self._scene is None:
            return None
        for lay in self._project.scene_ui_layouts(self._scene):
            if any(e is element for e in lay.elements):
                return lay
        return None

    def _group_by_layout(self, elements) -> list:
        """[(nœud, [éléments])] — répartit une sélection (potentiellement à cheval
        sur plusieurs nœuds) sur son nœud propriétaire, dans l'ordre rencontré."""
        order: list = []
        by_id: dict = {}
        for e in elements:
            lay = self._layout_of(e)
            if lay is None:
                continue
            if id(lay) not in by_id:
                by_id[id(lay)] = (lay, [])
                order.append(id(lay))
            by_id[id(lay)][1].append(e)
        return [by_id[k] for k in order]

    def subtree_of(self, element) -> list:
        """L'élément et TOUT son sous-arbre, racine en tête — l'unité que
        copient le presse-papier et le dupliquer."""
        lay = self._layout_of(element) if self.ready else None
        if lay is None:
            return [element]
        return [element] + lay.descendants(element.name)

    def copy_groups(self, elements: list) -> list:
        """[sous-arbre, …] pour le presse-papier — même règle qu'à la
        duplication : un élément dont un ANCÊTRE est du lot est ignoré, son
        sous-arbre voyageant déjà dans la copie de cet ancêtre."""
        if not self.ready or not elements:
            return []
        out: list = []
        for lay, els in self._group_by_layout(elements):
            picked = {e.name for e in els}
            roots = [e for e in els if not (set(lay.ancestors(e.name)) & picked)]
            out += [self.subtree_of(e) for e in roots]
        return out

    def duplicate_elements(self, elements: list, dx: int = 8, dy: int = 8) -> list:
        """Duplique des éléments (sous-arbres compris) décalés de (dx, dy), chacun
        dans SON nœud `Interface`.

        Un élément dont un ANCÊTRE est du lot est ignoré : son sous-arbre est
        déjà emporté par la copie de cet ancêtre."""
        if not self.ready or not elements:
            return []
        out: list = []
        for lay, els in self._group_by_layout(elements):
            picked = {e.name for e in els}
            roots = [e for e in els if not (set(lay.ancestors(e.name)) & picked)]
            groups = [self.subtree_of(e) for e in roots]
            out += self._add_element_copies(lay, groups, dx, dy, "Duplicated")
        return out

    def paste_elements(self, groups: list, dx: int = 0, dy: int = 0) -> list:
        """Colle des sous-arbres venus du presse-papier du canvas (chacun sa
        racine en tête). Crée la mise en page de la scène si elle n'en a pas :
        coller dans une scène vierge est le cas d'usage principal."""
        if not self.ready or not groups:
            return []
        return self._add_element_copies(self._ensure_layout(), groups, dx, dy,
                                        "Pasted")

    def delete_elements(self, elements: list) -> list:
        """Supprime des éléments d'interface et TOUT leur sous-arbre, en une
        seule entrée d'historique.

        Le sous-arbre part avec le parent, comme il le suit à la duplication —
        et pour une raison plus dure qu'une symétrie : la position d'un enfant
        est RELATIVE à son conteneur. Laisser les orphelins derrière ne les
        laisserait pas en place, ça les ferait sauter ailleurs à l'écran (leur
        origine redevient celle du socle d'ancrage)."""
        from core.history import get_history, RemoveListItemsCmd
        if not self.ready or not elements:
            return []
        # Une sélection peut être à cheval sur plusieurs nœuds : chaque victime
        # part de la liste de SON nœud, une commande par nœud touché.
        all_victims: list = []
        for lay, els in self._group_by_layout(elements):
            victims: list = []
            for el in els:
                for e in [el] + lay.descendants(el.name):
                    if not any(v is e for v in victims):
                        victims.append(e)
            if not victims:
                continue
            n = len(els)
            get_history().push(RemoveListItemsCmd(
                lay.elements, victims, persist_fn=self.regions_changed.emit,
                label=f"Deleted {n} interface element{'s' if n > 1 else ''}"))
            all_victims += victims
        return all_victims

    def _add_element_copies(self, lay, groups: list, dx: int, dy: int,
                            verb: str) -> list:
        """Cœur commun : copie profonde de chaque sous-arbre, noms uniques,
        refs `parent` réécrites vers les copies, décalage sur la seule RACINE
        (les enfants sont positionnés relativement à leur parent, les décaler
        aussi les ferait glisser deux fois)."""
        from core.models.ui_region import unique_element_name
        from core.history import get_history, AddListItemsCmd
        taken = set(lay.element_names()) | set(self._project.ui_element_names())
        copies: list = []
        roots: list = []
        for group in groups:
            if not group:
                continue
            rename: dict[str, str] = {}
            pairs: list = []
            for src in group:
                new = copy.deepcopy(src)
                # Espace de noms : le projet entier, tous types confondus (cf.
                # Project.ui_element_names) — les refs `parent` restent ainsi
                # sans ambiguïté et les constantes C ne collisionnent pas.
                new.name = unique_element_name(taken, src.name)
                taken.add(new.name)
                rename[src.name] = new.name
                pairs.append((src, new))
            for src, new in pairs:
                if src.parent in rename:
                    # Parent copié avec le lot : l'enfant suit SA copie, sinon
                    # le sous-arbre se rebrancherait sur le conteneur d'origine.
                    new.parent = rename[src.parent]
                elif lay.get(src.parent) is not None:
                    new.parent = src.parent      # parent resté en place
                else:
                    # Collée dans une mise en page qui ne connaît pas son parent
                    # (autre scène) : redevient racine, pas de ref pendante.
                    new.parent = ""
            root = pairs[0][1]
            root.x = int(root.x) + int(dx)
            root.y = int(root.y) + int(dy)
            roots.append(root)
            copies.extend(new for _s, new in pairs)
        if not copies:
            return []
        n = len(roots)
        get_history().push(AddListItemsCmd(
            lay.elements, copies, persist_fn=self.regions_changed.emit,
            label=f"{verb} {n} interface element{'s' if n > 1 else ''}"))
        return roots


class SceneInpaintingController:
    """Pilote la peinture par palette d'un layer BG dans le canvas de scène.

    Analogue au couple collision_overlay/collision_painted : détient l'état
    (projet, scène, layer actif, banque de peinture active, raster du layer
    actif) et applique/persiste les overrides `SE_PALBANK` tuile par tuile.
    Peignable dès que le layer a une image exploitable (la palette d'origine
    de l'asset sert de base) — indépendant de `layer.pal_bank`."""

    def __init__(self, gba_scene: "GBAScene"):
        self._gfx = gba_scene
        self._project: Optional[Project] = None
        self._scene = None
        self._layer = None          # BackgroundLayer actif (peint)
        self._raster: Optional[BgLayerRaster] = None
        self._bank: Optional[int] = None   # slot (0-15) de la banque de peinture
        self._stroke: Optional[dict] = None  # delta en cours {(c,r): (old,new)}

    # ── Contexte ─────────────────────────────────────────────────
    def set_context(self, project: Optional[Project], scene):
        self._project = project
        self._scene = scene
        self._layer = None
        self._raster = None
        self._stroke = None
        # Banque de peinture par défaut = 1re banque BG active (si présente).
        actives = getattr(scene, "active_bg_palettes", []) if scene else []
        self._bank = 0 if actives else None

    def set_inpaint_layer(self, bg_slot: Optional[int]):
        """Choisit le layer peint (par bg_slot). Construit son raster."""
        self._layer = None
        self._raster = None
        if bg_slot is None or not self._scene:
            return
        for L in self._scene.background_layers:
            if L.bg_slot == bg_slot:
                self._layer = L
                break
        if self._layer is not None and self._project:
            ap = layer_png_path(self._project, self._layer)
            self._raster = build_bg_raster(self._project, self._scene, self._layer, ap)

    def set_inpaint_bank(self, slot: Optional[int]):
        self._bank = slot

    def scene_bg_banks(self) -> list:
        """Liste (slot, PaletteBank) des banques BG actives résolues de la scène
        — source du bandeau de sélection de peinture."""
        out: list = []
        if not self._scene or not self._project:
            return out
        names = getattr(self._scene, "active_bg_palettes", [])
        for slot in range(len(names)):
            b = resolve_palette_bank(self._project, names, slot)
            if b and b.colors:
                out.append((slot, b))
        return out

    @property
    def inpaint_layer_slot(self) -> Optional[int]:
        return self._layer.bg_slot if self._layer is not None else None

    @property
    def inpaint_bank(self) -> Optional[int]:
        return self._bank

    @property
    def ready(self) -> bool:
        """Peinture possible : layer avec image exploitable (raster construit
        depuis la palette d'origine) + banque de peinture choisie."""
        return self._raster is not None and self._bank is not None

    def tiles_size(self) -> tuple[int, int]:
        if self._raster is None:
            return (0, 0)
        return (self._raster.tiles_w, self._raster.tiles_h)

    # ── Peinture ─────────────────────────────────────────────────
    def begin_stroke(self):
        self._stroke = {}

    def inpaint_tile(self, col: int, row: int, erase: bool = False):
        """Peint (ou efface) l'override d'une tuile ; met à jour le canvas en
        direct. Enregistre l'ancienne valeur dans le stroke courant."""
        if not self.ready or self._layer is None:
            return
        if not (0 <= col < self._raster.tiles_w and 0 <= row < self._raster.tiles_h):
            return
        key = (col, row)
        new = None if erase else self._bank
        old = self._layer.tile_palette_overrides.get(key)
        if old == new:
            return
        if self._stroke is not None:
            if key not in self._stroke:
                self._stroke[key] = (old, new)
            else:
                self._stroke[key] = (self._stroke[key][0], new)
        self._apply_tile(key, new)
        self._refresh()

    def _apply_tile(self, key: tuple[int, int], slot: Optional[int]):
        if slot is None:
            self._layer.tile_palette_overrides.pop(key, None)
        else:
            self._layer.tile_palette_overrides[key] = slot
        if self._raster is not None:
            self._raster.patch_tile(key[0], key[1], slot)

    def _refresh(self):
        if self._raster is not None and self._layer is not None:
            self._gfx.set_bg(self._layer.bg_slot, self._raster.to_pixmap())

    def end_stroke(self):
        """Clôt le stroke : pousse la commande d'historique + persiste."""
        delta = self._stroke or {}
        self._stroke = None
        if not delta or self._layer is None:
            return
        from core.history import SceneInpaintingCmd, get_history
        cmd = SceneInpaintingCmd(self, self._layer, self._layer.bg_slot, dict(delta))
        h = get_history()
        h._undo.append(cmd)
        h._redo.clear()
        h.changed.emit()
        self._persist()

    # ── Undo/redo (appelé par SceneInpaintingCmd) ────────────────────────
    def apply_override_delta(self, layer, bg_slot: int, delta: dict, forward: bool):
        """Réapplique un delta sur un layer (forward=redo, sinon undo), rebâtit
        le pixmap de ce layer, et persiste. Robuste même si ce n'est plus le
        layer actif."""
        for key, (old, new) in delta.items():
            slot = new if forward else old
            if slot is None:
                layer.tile_palette_overrides.pop(key, None)
            else:
                layer.tile_palette_overrides[key] = slot
        self.rebuild_layer_pixmap(bg_slot)
        self._persist()

    def rebuild_layer_pixmap(self, bg_slot: int):
        """Reconstruit le raster + pixmap d'un layer depuis son état courant."""
        if not self._scene or not self._project:
            return
        layer = next((L for L in self._scene.background_layers
                      if L.bg_slot == bg_slot), None)
        if layer is None:
            return
        ap = layer_png_path(self._project, layer)
        raster = build_bg_raster(self._project, self._scene, layer, ap)
        if raster is not None:
            self._gfx.set_bg(bg_slot, raster.to_pixmap())
            if self._layer is layer:
                self._raster = raster

    def _persist(self):
        if not self._project or not self._scene:
            return
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().save_scene()



class CanvasClipboard:
    """Presse-papier INTERNE du canvas (Ctrl+C / Ctrl+V).

    Interne et pas le presse-papier système : ce qu'on copie est un graphe
    d'objets du projet (composants, sous-arbre d'interface), pas du texte.

    Au niveau du MODULE et pas de l'écran : changer de scène reconstruit
    l'éditeur, or coller dans une AUTRE scène est tout l'intérêt face au Ctrl+D.

    Le contenu est une copie profonde : modifier ou supprimer la source après
    la copie ne change pas ce qui sera collé."""

    def __init__(self):
        self.actors: list = []
        self.ui_groups: list = []   # sous-arbres d'interface, racine en tête
        self.scene_name: str = ""   # scène d'origine (cf. paste_offset)
        self.pastes: int = 0

    @property
    def empty(self) -> bool:
        return not self.actors and not self.ui_groups

    def take(self, actors: list, ui_groups: list, scene_name: str):
        self.actors = copy.deepcopy(actors)
        self.ui_groups = copy.deepcopy(ui_groups)
        self.scene_name = scene_name
        self.pastes = 0

    def paste_offset(self, scene_name: str) -> int:
        """Décalage du prochain collage, en px.

        Dans la scène d'origine on décale de 8 px de plus à chaque collage,
        sinon la copie se cache sous l'original. Dans une AUTRE scène, le
        premier collage garde la position exacte : c'est « reproduire cette
        mise en place ailleurs »."""
        self.pastes += 1
        n = self.pastes if scene_name == self.scene_name else self.pastes - 1
        return 8 * n
