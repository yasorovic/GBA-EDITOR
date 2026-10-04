"""ui/scene_manager/canvas/canvas_scene.py — la scène graphique du canvas.

Extrait de `scene_canvas` (A3) : `GBAScene`, le `QGraphicsScene` qui possède les
items (sprites d'acteurs, caméras, overlays, zones d'interface), gère l'item actif
et la multi-sélection, les guides d'alignement, le placement des caméras, les
layers BG et leurs masques de fenêtre. Elle instancie les primitives de
`canvas_items`/`canvas_region_item` (vers le bas) ; la vue et la façade la
possèdent, elle ne les connaît pas.
"""
from __future__ import annotations

from typing import Optional

from core.models.scene import Actor
from ui.common.theme import C
from ui.scene_manager.canvas.canvas_const import GBA_W, GBA_H
from ui.scene_manager.canvas.canvas_items import (
    SpriteItem, CameraItem, CollisionOverlay, ScreenBezelItem, GridItem,
    ActorBoxOverlay, GuideLine, MaskablePixmapItem, hw_layer_z,
)
from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem,
    QGraphicsLineItem,
)


class GBAScene(QGraphicsScene):
    sprite_moved = pyqtSignal()

    def __init__(self, canvas_w: int = GBA_W, canvas_h: int = GBA_H, parent=None):
        super().__init__(0, 0, canvas_w, canvas_h, parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._bg_items: list[Optional[QGraphicsPixmapItem]] = [None] * 4
        self._sprite_items: list[SpriteItem] = []
        self._grid_item: Optional[GridItem] = None
        self._border: Optional[ScreenBezelItem] = None
        self._backdrop: Optional[QGraphicsRectItem] = None
        self._camera: Optional[CameraItem] = None   # caméra DE DÉMARRAGE (screen-space, windows)
        self._extra_cameras: list[CameraItem] = []  # les AUTRES caméras de la scène
        self._windows: list = []   # WindowSlot de la scène (aperçu + masquage BG)
        self._obj_mask_rects: list = []   # découpe OBJ courante (sprites)
        self._ui_region_items: list = []  # zones de texte (UILayout de la scène)
        self._ui_elements_visible = True  # toggle "Interface elements" (top bar)
        # Guides d'alignement : deux lignes (une verticale, une horizontale)
        # créées à la demande, affichées le temps d'un drag/resize de zone.
        self._align_guide_v: Optional[QGraphicsLineItem] = None
        self._align_guide_h: Optional[QGraphicsLineItem] = None
        # Item ACTIF de la sélection : celui dont l'inspecteur montre le
        # contenu. Une multi-sélection en a toujours exactement un (le premier
        # sélectionné), redéfinissable au Ctrl+Shift+clic.
        self._active_item = None
        self._snap = False
        self._collision_view = False  # toggle "Collisions scène"
        self._setup_border()
        self._collision_overlay = CollisionOverlay()
        self.addItem(self._collision_overlay)
        self._actor_box_overlay = ActorBoxOverlay(canvas_w, canvas_h)
        self.addItem(self._actor_box_overlay)
        # Rafraîchit les boîtes de collision pendant un drag (sinon l'ancienne
        # position reste peinte — "traînée" visuelle tant que set_actors()
        # n'est pas rappelé explicitement).
        self.sprite_moved.connect(self._actor_box_overlay.update)

    @property
    def collision_overlay(self) -> "CollisionOverlay":
        return self._collision_overlay

    def descendant_sprite_items(self, item: "SpriteItem") -> list:
        """SpriteItem des acteurs qui descendent de `item.scene_sprite`
        (`Actor.parent`, ROADMAP v0.23) — pour faire suivre tout le
        sous-arbre quand on déplace un parent dans le canvas."""
        from core.models.scene import actor_descendant_names
        names = actor_descendant_names(
            [it.scene_sprite for it in self._sprite_items], item.scene_sprite.name)
        return [it for it in self._sprite_items
                if it is not item and it.scene_sprite.name in names]

    # ── Sélection multiple : membres + item ACTIF ─────────────────
    # Un item sélectionné est « membre » ; parmi eux, un seul est ACTIF —
    # c'est lui que l'inspecteur détaille et lui que les gestes visant « un »
    # item prennent pour cible. Les deux états se peignent différemment
    # (accent = membre, blanc = actif), même grammaire que la grille du
    # Palette Editor.

    def selectable_items(self) -> list:
        """Items sélectionnés éligibles à la multi-sélection : acteurs et zones
        de texte (la caméra est un singleton, elle n'en fait pas partie)."""
        try:
            selected = self.selectedItems()
        except RuntimeError:      # scène Qt détruite en cours de rebuild
            return []
        return [it for it in selected if isinstance(it, (SpriteItem, UIRegionItem))]

    @property
    def active_item(self):
        return self._active_item

    def set_active_item(self, item) -> bool:
        """Désigne l'item actif. Retourne True s'il a changé (l'appelant peut
        alors prévenir le bus). Repeint l'ancien et le nouveau."""
        if item is self._active_item:
            return False
        old, self._active_item = self._active_item, item
        for it in (old, item):
            if it is None:
                continue
            try:
                if it.scene() is self:
                    it.update()
            except RuntimeError:
                pass              # item C++ déjà détruit
        return True

    def reconcile_active(self):
        """Garde l'item actif cohérent avec la sélection : il doit toujours en
        être membre. Sinon → le PREMIER membre (règle « le premier item
        sélectionné est l'actif »), ou aucun si la sélection est vide."""
        members = self.selectable_items()
        if self._active_item in members:
            return False
        return self.set_active_item(members[0] if members else None)

    # ── Guides d'alignement des zones de texte ────────────────────
    def ui_align_segments(self, exclude_item):
        """Segments-cibles (start, size) des AUTRES zones, par axe, en
        coordonnées scène — lus tels qu'ils sont dessinés (offset d'actor
        compris). Retourne (xs, ys) où chaque élément est un (start, size)."""
        xs, ys = [], []
        ox, oy = exclude_item.screen_offset() if hasattr(exclude_item, "screen_offset") else (0, 0)
        for it in self._ui_region_items:
            if it is exclude_item:
                continue
            try:
                r, p = it.rect(), it.pos()
            except RuntimeError:
                continue
            # Dans le repère ÉCRAN de l'item qu'on déplace : ses bords sont
            # comparés au cadre 240×160, pas à la position de la caméra.
            xs.append((p.x() - ox + r.left(), r.width()))
            ys.append((p.y() - oy + r.top(),  r.height()))
        return xs, ys

    def _guide_pen(self) -> "QPen":
        """Guide d'alignement : semi-transparent et en tirets, pour se lire
        comme un repère et non comme une alarme."""
        c = QColor("#ff45d0")
        c.setAlpha(150)
        pen = QPen(c)
        pen.setCosmetic(True)           # 1 px écran quel que soit le zoom
        pen.setWidth(0)
        pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def show_align_guides(self, gx, gy):
        """Trace une ligne verticale à x=`gx` et/ou horizontale à y=`gy` (None =
        masquée). Les lignes courent sur toute l'étendue de la scène : un guide
        qui s'arrêterait au bord de la zone n'aiderait pas à viser une cible
        lointaine."""
        w, h = self._canvas_w, self._canvas_h
        if gx is not None:
            if self._align_guide_v is None:
                self._align_guide_v = GuideLine()
                self._align_guide_v.setPen(self._guide_pen())
                self._align_guide_v.setZValue(130)   # au-dessus des zones (120)
                self._align_guide_v.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.addItem(self._align_guide_v)
            self._align_guide_v.setLine(gx, 0, gx, h)
            self._align_guide_v.setVisible(True)
        elif self._align_guide_v:
            self._align_guide_v.setVisible(False)
        if gy is not None:
            if self._align_guide_h is None:
                self._align_guide_h = GuideLine()
                self._align_guide_h.setPen(self._guide_pen())
                self._align_guide_h.setZValue(130)
                self._align_guide_h.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.addItem(self._align_guide_h)
            self._align_guide_h.setLine(0, gy, w, gy)
            self._align_guide_h.setVisible(True)
        elif self._align_guide_h:
            self._align_guide_h.setVisible(False)

    def clear_align_guides(self):
        for g in (self._align_guide_v, self._align_guide_h):
            if g:
                g.setVisible(False)

    def update_actor_boxes(self, actors: list, var_defaults: dict | None = None):
        """Met à jour les boîtes de collision acteurs affichées."""
        self._actor_box_overlay.set_actors(actors, var_defaults)

    def set_collision_view(self, visible: bool):
        """Toggle 'Collisions scène' — indépendant de l'outil CollisionTool."""
        self._collision_view = visible
        self._collision_overlay.setVisible(visible)
        self._collision_overlay.update()

    def set_ui_elements_view(self, visible: bool):
        """Toggle 'Interface elements' — zones/conteneurs/textes de la mise en
        page. Mémorisé pour s'appliquer aussi aux items recréés par un futur
        set_ui_regions (rebuild sur chaque édition de la mise en page)."""
        self._ui_elements_visible = visible
        for it in self._ui_region_items:
            it.setVisible(visible)

    def resize_canvas(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h
        self.setSceneRect(0, 0, w, h)
        if self._border:
            self._border.resize(w, h)
        if self._backdrop:
            self._backdrop.setRect(0, 0, w, h)
        if self._camera:
            self._camera.set_canvas_size(w, h)
        for it in self._extra_cameras:
            it.set_canvas_size(w, h)
        for item in self._sprite_items:
            item.set_canvas_size(w, h)
        if self._grid_item:
            self._grid_item.resize(w, h)

    def set_backdrop(self, bgr555: int):
        """Couleur du backdrop (index 0 de PAL_BG_RAM) — peinte SOUS tous les
        layers (z=-1). C'est ce que le hardware affiche là où rien n'est dessiné :
        une window qui masque tout laisse donc apparaître cette couleur, et le
        canvas le reflète."""
        from core.models.gba_color import bgr555_to_rgb888
        r, g, b = bgr555_to_rgb888(int(bgr555) & 0x7FFF)
        if self._backdrop is None:
            self._backdrop = QGraphicsRectItem(0, 0, self._canvas_w, self._canvas_h)
            self._backdrop.setPen(QPen(Qt.PenStyle.NoPen))
            self._backdrop.setZValue(-1)
            self._backdrop.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._backdrop.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self._backdrop.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.addItem(self._backdrop)
        self._backdrop.setRect(0, 0, self._canvas_w, self._canvas_h)
        self._backdrop.setBrush(QBrush(QColor(r, g, b)))

    def _setup_border(self):
        self._border = ScreenBezelItem(self._canvas_w, self._canvas_h)
        self._border.setZValue(400)
        self.addItem(self._border)

    # ── Caméra ────────────────────────────────────────────────────

    def setup_camera(self, cam_x: int = 0, cam_y: int = 0, camera=None, project=None):
        """(Re)crée l'item de la caméra DE DÉMARRAGE — celle qui porte les
        sprites en espace écran et l'aperçu des windows. `camera` est l'objet
        modèle qu'elle représente (`None` = état implicite)."""
        if self._camera:
            # Détacher d'abord les sprites d'écran : retirer la caméra de la
            # scène emporterait ses enfants avec elle.
            for it in self._sprite_items:
                if it.parentItem() is self._camera:
                    it.setParentItem(None)
                    if it.scene() is None:
                        self.addItem(it)
            self.removeItem(self._camera)
        fw = camera.px('frame_w', project) if camera else GBA_W
        fh = camera.px('frame_h', project) if camera else GBA_H
        self._camera = CameraItem(self._canvas_w, self._canvas_h, cam_x, cam_y,
                                  frame_w=fw, frame_h=fh, camera=camera)
        self.addItem(self._camera)
        for it in self._sprite_items:
            self.sync_sprite_space(it)
        self.sync_ui_to_camera()

    def sync_ui_to_camera(self):
        """Replace les zones d'interface ancrées à l'écran sur la caméra de
        démarrage — appelé quand elle bouge ou est recréée."""
        for it in self._ui_region_items:
            try:
                it.reposition()
            except RuntimeError:
                continue          # item C++ détruit entre-temps
        self.refresh_screen_frame()

    def refresh_screen_frame(self):
        """Montre le cadre de la caméra de démarrage (et le voile hors cadre)
        tant qu'une zone ancrée à l'écran est sélectionnée : sans lui on ne
        voit pas où l'élément tombera sur l'écran de la console."""
        cam = self._camera
        if cam is None or cam.camera is None:
            return          # pas de caméra authorée : l'écran est à (0, 0)
        on = any(it.isSelected() and it.is_screen_anchored()
                 for it in self._ui_region_items)
        cam.set_view_forced(on)
        self.update()

    def setup_extra_cameras(self, cameras: list, project=None):
        """(Re)crée les items des AUTRES caméras de la scène — rectangles
        déplaçables/sélectionnables comme la caméra de démarrage, mais sans
        rôle dans le rendu écran (pas de sprites, pas de windows) : la scène
        n'a qu'UN écran, une seule caméra pilote son espace à la fois."""
        for it in self._extra_cameras:
            self.removeItem(it)
        self._extra_cameras = []
        for cam in cameras:
            it = CameraItem(self._canvas_w, self._canvas_h, cam.px('x', project), cam.px('y', project),
                            frame_w=cam.px('frame_w', project),
                            frame_h=cam.px('frame_h', project), camera=cam)
            self.addItem(it)
            self._extra_cameras.append(it)

    def camera_pos(self) -> tuple[int, int]:
        if self._camera:
            p = self._camera.pos()
            return int(p.x()), int(p.y())
        return 0, 0

    def camera_items(self) -> list:
        """Tous les items caméra de la scène (démarrage + autres)."""
        return ([self._camera] if self._camera else []) + list(self._extra_cameras)

    def set_windows(self, windows: list):
        """Aperçu des WindowSlot dans le cadre écran (porté par la caméra)."""
        self._windows = list(windows or [])
        if self._camera:
            self._camera.set_windows(self._windows)
        self.update_window_masks()

    def update_window_masks(self):
        """Applique aux layers BG le découpage des windows ACTIVES.

        Seule une window `visible` compte : une window authorée mais laissée à
        `window_show(region, 0)` n'a aucun effet sur console, elle ne doit donc
        rien masquer ici non plus. Recalculé au déplacement de la caméra, les
        rects étant en espace écran."""
        cam = self._camera.pos() if self._camera else QPointF(0, 0)

        def _screen_rect(ws) -> Optional[QRectF]:
            """Rect de la window en coordonnées de scène, clampé à l'écran."""
            x0 = max(0, min(int(ws.x), GBA_W))
            y0 = max(0, min(int(ws.y), GBA_H))
            x1 = max(x0, min(int(ws.x) + int(ws.w), GBA_W))
            y1 = max(y0, min(int(ws.y) + int(ws.h), GBA_H))
            if x1 <= x0 or y1 <= y0:
                return None
            return QRectF(cam.x() + x0, cam.y() + y0, x1 - x0, y1 - y0)

        # Windows actives et rectangulaires (la fenêtre-objet n'a pas de rect).
        active = [ws for ws in self._windows if ws.visible and not ws.is_obj]

        # Layers BG — bit par layer (WININ bits 0-3).
        for bg_index, item in enumerate(self._bg_items):
            if not isinstance(item, MaskablePixmapItem):
                continue
            rects = []
            for ws in active:
                shown = getattr(ws, "layers_shown", [True] * 4)
                if bg_index < len(shown) and shown[bg_index]:
                    continue   # ce layer traverse la window : rien à découper
                r = _screen_rect(ws)
                if r is not None:
                    rects.append(r)
            item.set_mask_rects(rects)

        # Sprites — bit OBJ commun à tous (WININ bit 4), pas par acteur.
        obj_rects = []
        for ws in active:
            if getattr(ws, "obj_shown", True):
                continue   # les sprites traversent cette window
            r = _screen_rect(ws)
            if r is not None:
                obj_rects.append(r)
        self._obj_mask_rects = obj_rects
        for sp in self._sprite_items:
            sp.set_mask_rects(obj_rects)

    # ── BG layers ─────────────────────────────────────────────────

    def set_bg(self, bg_index: int, pixmap: Optional[QPixmap]):
        # Priorité GBA = bg_slot directement (cf. `hw_layer_z`) : un fond
        # n'est jamais OBJ, donc toujours le cran BG de sa priorité.
        z = hw_layer_z(bg_index, is_obj=False)
        if self._bg_items[bg_index]:
            self.removeItem(self._bg_items[bg_index])
            self._bg_items[bg_index] = None
        if pixmap:
            item = MaskablePixmapItem(pixmap)
            item.setZValue(z)
            # OPACITÉ PLEINE, toujours. Les layers derrière BG0 étaient dessinés
            # à 90 % — une commodité d'édition (voir les couches empilées) qui
            # n'existe pas sur la console : le backdrop, et tout ce qui est
            # derrière, transparaissaient donc EN PERMANENCE à travers un décor
            # que la ROM affiche plein. Un fond uni un peu vif teintait tout
            # l'écran, et l'aperçu ne pouvait plus servir à juger une couleur.
            #
            # Pour regarder dessous, l'œil de la ligne de layer masque
            # franchement ce qu'on veut, sans mentir sur le reste du temps.
            item.setOpacity(1.0)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.addItem(item)
            self._bg_items[bg_index] = item

    def set_bg_visible(self, bg_index: int, visible: bool):
        """Masque/affiche un layer BG dans le canvas SANS détruire son pixmap
        (visibilité viewport éditeur seule — cf. BackgroundLayer.visible)."""
        if 0 <= bg_index < len(self._bg_items) and self._bg_items[bg_index]:
            self._bg_items[bg_index].setVisible(visible)

    # ── Sprites ───────────────────────────────────────────────────

    def add_sprite(
        self, pixmap: QPixmap, actor: Actor, save_fn=None,
        origin_x: int = 0, origin_y: int = 0,
        scale_x: float = 1.0, scale_y: float = 1.0,
        rotation: float = 0.0,
        flip_h: bool = False, flip_v: bool = False,
        resolver=None, placeholder: bool = False,
        pivot_x: float = 0.0, pivot_y: float = 0.0, show_pivot: bool = False,
    ) -> SpriteItem:
        item = SpriteItem(
            pixmap, actor,
            self._canvas_w, self._canvas_h,
            snap=self._snap, save_fn=save_fn,
            origin_x=origin_x, origin_y=origin_y,
            scale_x=scale_x, scale_y=scale_y,
            rotation=rotation, flip_h=flip_h, flip_v=flip_v,
            resolver=resolver, placeholder=placeholder,
            pivot_x=pivot_x, pivot_y=pivot_y, show_pivot=show_pivot,
        )
        self.addItem(item)
        self._sprite_items.append(item)
        self.sync_sprite_space(item)
        # Sprite créé après le calcul des masques (rechargement de scène) :
        # lui appliquer la découpe courante sans attendre le prochain recalcul.
        if self._obj_mask_rects:
            item.set_mask_rects(self._obj_mask_rects)
        return item

    def sync_sprite_space(self, item: SpriteItem):
        """Range l'item dans le bon repère selon `Actor.screen_space`.

        Un acteur ancré à l'écran devient ENFANT de la caméra — exactement ce
        que font déjà les windows (cf. CameraItem.set_windows) : sa position
        locale EST sa position dans l'écran GBA, elle suit la vue sans le
        moindre recalcul, et un déplacement à la souris rend directement des
        coordonnées d'écran à écrire dans le modèle (`itemChange` lit une
        position relative au parent).

        Idempotent : appelé à la création, au changement de caméra et à chaque
        modification de l'inspecteur, sans avoir à savoir ce qui a changé."""
        want = self._camera if getattr(item.scene_sprite, "screen_space", False) else None
        if item.parentItem() is not want:
            item.setParentItem(want)
            if want is None and item.scene() is None:
                # Détaché d'un parent qui n'était plus dans la scène : Qt l'a
                # sorti avec lui, il faut le remettre pour qu'il reste dessinable.
                self.addItem(item)
        # Toujours repositionner : c'est aussi le chemin d'un simple déplacement
        # (spinbox de l'inspecteur), où le repère n'a pas bougé.
        item.sync_pos()

    def clear_sprites(self):
        for item in self._sprite_items:
            self.removeItem(item)
        self._sprite_items.clear()

    # ── Zones de texte ────────────────────────────────────────────

    def set_ui_regions(self, layouts, project, scene, save_fn=None):
        """Redessine les éléments de TOUS les nœuds `Interface` de la scène (une
        liste depuis v0.25 ; un layout seul ou None est toléré).

        Reconstruction complète plutôt que mise à jour en place : un élément peut
        avoir changé d'ancrage (donc d'origine), de taille ou de cible, et
        recalculer chaque cas séparément multiplierait les chemins pour un
        nombre d'items qui se compte sur les doigts.

        La reconstruction ne doit PAS coûter la sélection : détruire l'item
        sélectionné fait émettre à Qt une sélection vide, que le canvas traduit
        en « clic dans le vide » → l'inspecteur de l'élément se refermait à chaque
        frappe dans une spinbox. On note l'élément sélectionné, on tait les
        signaux le temps du remplacement, et on le re-sélectionne sur son
        nouvel item."""
        if layouts is None:
            layouts = []
        elif not isinstance(layouts, (list, tuple)):
            layouts = [layouts]        # tolère un layout seul (appelants anciens)
        # Identité, pas égalité : deux éléments peuvent avoir les mêmes champs.
        kept = [it._region for it in self._ui_region_items if it.isSelected()]
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            for it in self._ui_region_items:
                if it.scene():
                    self.removeItem(it)
            self._ui_region_items = []
            # Les nœuds s'empilent dans l'ORDRE où la scène les référence : un pas
            # d'un cran entre nœuds, l'ordre d'arbre départageant à l'intérieur.
            for li, layout_asset in enumerate(layouts):
                # TOUS les éléments (zones, conteneurs, textes), pas seulement les
                # zones : chacun a une géométrie à dessiner et à manipuler.
                #
                # Le z-order suit l'ORDRE D'ARBRE (DFS) : un parent sous ses enfants
                # (le texte au-dessus du fond de son conteneur), un frère tardif
                # au-dessus du précédent. On le pose explicitement — sans ça tous
                # les items partageraient un z constant et l'empilement dépendrait
                # du seul ordre d'insertion, invisible à réordonner.
                z_of = {r.name: i for i, (_d, r) in enumerate(layout_asset.in_tree_order())}
                for r in layout_asset.elements:
                    item = UIRegionItem(layout_asset, r, project, scene, save_fn=save_fn)
                    # La base (`hw_layer_z`, posée au constructeur) place l'élément
                    # sur son VRAI layer hardware — désormais le `bg_slot` de SON
                    # nœud (v0.12). L'offset ici ne fait que départager, SOUS le
                    # cran : d'abord l'ordre des nœuds (deux interfaces sur le même
                    # slot s'écrivent dans l'ordre de scène, dernier au-dessus),
                    # puis l'ordre d'arbre entre éléments. Borné <1 pour ne jamais
                    # franchir le cran suivant (crans espacés de 2, OBJ à +1).
                    item.setZValue(item.zValue()
                                   + (li * 64 + z_of.get(r.name, 0)) / 100000.0)
                    item.setVisible(self._ui_elements_visible)
                    self.addItem(item)
                    self._ui_region_items.append(item)
                    item.reposition()
                    if any(r is k for k in kept):
                        item.setSelected(True)
        finally:
            self.blockSignals(was_blocked)
        self.refresh_screen_frame()

        # Pré-chauffage : résoudre MAINTENANT (hors écran, à la construction des
        # items) les couleurs de banque de chaque région. Chaque item les met en
        # cache pour sa vie, et `scene_layout_cache` fait PARTAGER une seule
        # allocation de scène — sans quoi ce coût (lourd : résolution des
        # palettes de police) retombe au PREMIER paint, région par région, et
        # fige l'affichage initial de la scène. Le build n'entre jamais dans ce
        # contexte : il recalcule, aucun risque de périmé.
        from codegen.palette_alloc import scene_layout_cache
        with scene_layout_cache():
            for it in self._ui_region_items:
                try:
                    it._bank_colors()
                except Exception:
                    pass

    def set_snap(self, snap: bool):
        self._snap = snap
        for item in self._sprite_items:
            item.set_snap(snap)

    # ── Grille ────────────────────────────────────────────────────

    def set_grid(self, visible: bool, cell: int = 8):
        if self._grid_item is None:
            self._grid_item = GridItem(self._canvas_w, self._canvas_h, cell)
            self._grid_item.setZValue(100)
            self.addItem(self._grid_item)
        else:
            self._grid_item.set_cell(cell)
        self._grid_item.setVisible(visible)

    # ── Fond damier ───────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor(C.CANVAS_BG))
        size = 8
        c1, c2 = QColor(C.CHECKER_A), QColor(C.CHECKER_B)
        x0 = int(rect.left() / size) * size
        y0 = int(rect.top() / size) * size
        x1 = int(rect.right() / size + 1) * size
        y1 = int(rect.bottom() / size + 1) * size
        for x in range(x0, x1, size):
            for y in range(y0, y1, size):
                c = c1 if (x // size + y // size) % 2 == 0 else c2
                painter.fillRect(x, y, size, size, c)
