"""ui/scene_manager/canvas/canvas_items.py — les items graphiques du canvas.

Extrait de `scene_canvas` (A3) : les primitives `QGraphicsItem` que la scène
pose — sprite d'acteur draggable, rectangle de caméra, overlays (grille, bezel,
boîtes de collision, guides d'alignement) et l'overlay de carte de collision.
Plus les helpers de rendu qu'ils partagent : `hw_layer_z` (le z qui reproduit
l'ordre du hardware), le placeholder des acteurs sans sprite, `_screen_scale`.

Ne dépend que du modèle, du thème, de `canvas_const` et de Qt — aucun ne remonte
vers la scène/vue/façade (les items dialoguent avec leur scène via `self.scene()`
+ `hasattr`, sans l'importer). `_screen_scale`/`_draw_placeholder`/`_slope_path`/
`_WIN_COLORS` et les constantes de couleur restent privés (usage interne) ;
`hw_layer_z`/`make_placeholder_pixmap` et les classes traversent (façade + scène).
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.notes_tooltip import notes_tooltip
from typing import Optional

from core.history import MoveActorCmd, MoveActorGroupCmd, get_history
from core.models.scene import Actor
from core.models.field_value import number_value
from core.models import collision_tiles as CT
from core.models.collision_tiles import (
    COLLISION_TILE_SIZE,
    TILE_EMPTY, TILE_SOLID,
    TILE_SLOPE_L, TILE_SLOPE_L_HI, TILE_SLOPE_L_HI_INV, TILE_SLOPE_L_INV,
    TILE_SLOPE_L_LO, TILE_SLOPE_L_LO_INV,
    TILE_SLOPE_L_STEEP_HI, TILE_SLOPE_L_STEEP_HI_INV,
    TILE_SLOPE_L_STEEP_LO, TILE_SLOPE_L_STEEP_LO_INV,
    TILE_SLOPE_R, TILE_SLOPE_R_HI, TILE_SLOPE_R_HI_INV, TILE_SLOPE_R_INV,
    TILE_SLOPE_R_LO, TILE_SLOPE_R_LO_INV,
    TILE_SLOPE_R_STEEP_HI, TILE_SLOPE_R_STEEP_HI_INV,
    TILE_SLOPE_R_STEEP_LO, TILE_SLOPE_R_STEEP_LO_INV,
)
from core.models.tile_codec import flip_h, flip_v
from core.project import Project
from ui.common.theme import C
from ui.scene_manager.canvas.canvas_const import GBA_W, GBA_H
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsRectItem,
    QStyle, QStyleOptionGraphicsItem,
)


# Aperçu des windows matérielles — une teinte par région (WIN0, WIN1), reprise
# du bleu de la carte WINDOWS de l'inspecteur de scène.
_WIN_COLORS = (C.ACCENT_COOL, C.ACCENT_WARM)

_PLACEHOLDER_SIZE = 16
_PLACEHOLDER_ICO = 12


def _screen_scale(painter: QPainter, widget=None) -> float:
    """Combien de pixels ÉCRAN vaut une unité de scène pour ce painter — zoom de
    la vue (et transform de l'item) × devicePixelRatio de l'écran. Les icônes
    d'UI du canvas s'en servent pour se faire rendre à la bonne résolution au
    lieu d'être un pixmap agrandi."""
    lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
    return lod * (widget.devicePixelRatioF() if widget is not None else 1.0)


def _draw_placeholder(painter: QPainter, scale: float = 1.0) -> None:
    """Repère 16×16 des actors/prefabs sans sprite, dessiné dans le repère
    courant du painter. `scale` = facteur d'échelle écran effectif : le glyphe
    est demandé à cette résolution pour rester net quand la vue est zoomée."""
    from ui.common.icons import scaled_pixmap

    # Actor sans sprite : un simple repère Pac-Man neutre. Un badge bleu
    # n'avait aucune sémantique dans ce contexte et masquait la scène.
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    px = scaled_pixmap("actor_empty", "#f5f0d8", _PLACEHOLDER_ICO, scale)
    painter.drawPixmap(
        QRectF(2, 2, _PLACEHOLDER_ICO, _PLACEHOLDER_ICO), px, QRectF(px.rect())
    )


def make_placeholder_pixmap() -> QPixmap:
    """Pixmap 16×16 pour les actors/prefabs sans sprite.

    Porte la GÉOMÉTRIE de l'item (boundingRect, hit-test) ; à l'écran c'est
    `_draw_placeholder()` qui redessine le repère au zoom courant
    (cf. SpriteItem.paint) — un pixmap figé serait flou dès le zoom ×2."""
    px = QPixmap(_PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    _draw_placeholder(p)
    p.end()
    return px


# ──────────────────────────────────────────────────────────────────
#  Ordre de composition — UNE règle, celle du hardware, jamais un empilement
#  choisi pour le confort de l'édition.
#
#  Priorité GBA = bg_slot directement pour un fond ET pour le layer d'UI
#  (0 = devant, 3 = derrière — cf. `main_gen._gen_scene_init`, le commentaire
#  au-dessus de `bg_cnt_set`). Un acteur (OBJ) porte sa PROPRE priorité
#  (`Actor.priority`, 0-3, mêmes bornes) — et à priorité ÉGALE entre un OBJ et
#  un BG, c'est l'OBJ qui passe DEVANT (règle documentée du hardware GBA, pas
#  un choix de l'éditeur). D'où deux crans par niveau de priorité : le BG,
#  puis l'OBJ juste au-dessus.
#
#  Avant cette fonction, un acteur avait un zValue FIXE (10) et une zone
#  d'interface un zValue FIXE (120) : l'acteur passait donc TOUJOURS sous
#  l'interface dans le canvas, quelle que soit la priorité réelle — le
#  contraire de ce que montre la ROM dès que l'UI vit sur un BG de priorité
#  supérieure à 0 (le cas courant : text_bg vaut rarement 0).
# ──────────────────────────────────────────────────────────────────

def hw_layer_z(priority: int, is_obj: bool) -> float:
    """zValue Qt qui REPRODUIT l'ordre de composition du hardware, jamais un
    empilement approché. `priority` est déjà l'échelle GBA (0 devant, 3
    derrière) — bg_slot pour un fond ou le layer d'UI, `Actor.priority` pour
    un acteur."""
    p = max(0, min(3, int(priority)))
    return float((3 - p) * 2 + (1 if is_obj else 0))


# ──────────────────────────────────────────────────────────────────
#  Item sprite draggable
# ──────────────────────────────────────────────────────────────────
class SpriteItem(QGraphicsPixmapItem):
    def __init__(
        self,
        pixmap: QPixmap,
        actor: Actor,
        canvas_w: int,
        canvas_h: int,
        snap: bool = False,
        save_fn=None,
        origin_x: int = 0,
        origin_y: int = 0,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        rotation: float = 0.0,
        flip_h: bool = False,
        flip_v: bool = False,
        resolver=None,
        placeholder: bool = False,
        pivot_x: float = 0.0,
        pivot_y: float = 0.0,
        show_pivot: bool = False,
        parent=None,
    ):
        super().__init__(pixmap, parent)
        self.scene_sprite = actor
        # Posés avant tout appel pouvant interroger boundingRect() (setOffset…).
        self._pivot_point = QPointF()
        self._show_pivot = False
        # Actor sans sprite : le pixmap ne sert que de géométrie, le repère est
        # redessiné à chaque paint() au zoom courant (cf. _paint_content).
        self._placeholder = placeholder
        # Résout une position x/y (px littéral, tile, ou réf de variable) en
        # pixels concrets pour l'affichage — cf. core.models.field_value.
        self._pos_resolver = resolver
        self.snap = snap
        # Initialisés avant setPos()/setFlags() plus bas : itemChange() peut être
        # appelé dès la construction (ItemSendsGeometryChanges) et les lit.
        self._drag_origin: tuple[int, int] | None = None
        self._drag_confirmed = False
        # Sous-arbre (Actor.parent, ROADMAP v0.23) capturé au press, pour le
        # faire suivre en translation groupée pendant le drag — cf. itemChange.
        self._drag_descendants: list = []
        self._drag_desc_origin: list = []
        self._mask_rects: list = []   # découpe par les windows (cf. set_mask_rects)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._save_fn = save_fn
        self._origin_x = origin_x
        self._origin_y = origin_y

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        # OBJ, priorité de CET acteur — pas un zValue fixe : deux acteurs de
        # priorités différentes doivent s'empiler comme le hardware le ferait.
        self.setZValue(hw_layer_z(number_value(getattr(actor, "priority", 0), resolver), is_obj=True))

        # Décaler le pixmap dans le repère local pour que (0,0) = ancrage (origine)
        self.setOffset(-origin_x, -origin_y)
        # Point de pivot = centre du cadre + `pivot` (comme `sprite.pivot_x/y` au
        # runtime). (0, 0) = le centre, le comportement GBA natif. Il reste FIXE :
        # rotation, échelle et flip (échelle -1) s'exercent autour de lui.
        self._pivot_point = QPointF(-origin_x + pixmap.width() / 2 + pivot_x,
                                    -origin_y + pixmap.height() / 2 + pivot_y)
        self._show_pivot = show_pivot

        # Transform autour du pivot. Qt applique les opérations de droite à gauche
        # sur un point : la rotation vient donc AVANT l'échelle dans la chaîne,
        # pour que l'échelle (flip compris) agisse d'abord dans l'espace de la
        # texture, puis que la rotation tourne le tout — la matrice du matériel.
        # (`setTransformOriginPoint` ne sert qu'à setRotation/setScale : un
        # `setTransform` l'ignore.)
        sx_eff = scale_x * (-1.0 if flip_h else 1.0)
        sy_eff = scale_y * (-1.0 if flip_v else 1.0)
        has_transform = (
            abs(sx_eff - 1.0) > 1e-4 or abs(sy_eff - 1.0) > 1e-4
            or abs(rotation) > 1e-4
        )
        if has_transform:
            t = QTransform()
            t.translate(self._pivot_point.x(), self._pivot_point.y())
            if abs(rotation) > 1e-4:
                t.rotate(rotation)
            t.scale(sx_eff, sy_eff)
            t.translate(-self._pivot_point.x(), -self._pivot_point.y())
            self.setTransform(t)

        # Item (0,0) = position logique de l'acteur — la caméra suit directement
        self.setPos(*self.pos_px())

        # Note libre de l'auteur au survol (éditeur uniquement). Vide → pas de
        # tooltip : un acteur sans note n'a rien à dire ici, l'inspecteur détaille.
        self.setToolTip(notes_tooltip(getattr(actor, "notes", "")))

    def pos_px(self) -> tuple[int, int]:
        """Position logique de l'acteur résolue en pixels (px/tile/réf variable)."""
        from core.models.field_value import FieldValue
        a = self.scene_sprite
        return (FieldValue.parse(a.x).px(self._pos_resolver),
                FieldValue.parse(a.y).px(self._pos_resolver))

    def sync_pos(self):
        """Repositionne l'item Qt depuis le modèle (setPos programmatique)."""
        self.setPos(*self.pos_px())

    def set_canvas_size(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h

    # En-deçà de ce déplacement (px), on considère qu'il s'agit d'un simple
    # clic (jitter sous-pixel entre press/release) et pas d'un vrai drag —
    # sans ce garde-fou, itemChange() snappait la position au premier micro-
    # mouvement, faisant "sauter" l'acteur au clic (cf bug rapporté).
    _CLICK_THRESHOLD = 2

    def mousePressEvent(self, e):
        # Capturer la position (résolue en px) avant le début du drag
        self._drag_origin = self.pos_px()
        self._drag_confirmed = False
        sc = self.scene()
        self._drag_descendants = sc.descendant_sprite_items(self) if sc is not None else []
        self._drag_desc_origin = [(it, *it.pos_px()) for it in self._drag_descendants]
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._drag_origin is not None:
            old_x, old_y = self._drag_origin
            new_x, new_y = self.pos_px()
            if (old_x, old_y) != (new_x, new_y):
                # Le sous-arbre a suivi en direct (itemChange) : réunir ses
                # déplacements dans la MÊME entrée d'historique que le parent.
                items = [(self.scene_sprite, old_x, old_y, new_x, new_y)]
                for it, ox, oy in self._drag_desc_origin:
                    nx, ny = it.pos_px()
                    if (ox, oy) != (nx, ny):
                        items.append((it.scene_sprite, ox, oy, nx, ny))
                cmd = (MoveActorGroupCmd(items) if len(items) > 1 else
                       MoveActorCmd(self.scene_sprite, old_x, old_y, new_x, new_y))
                # Pousser la commande SANS re-exécuter (le drag a déjà modifié actor)
                h = get_history()
                h._undo.append(cmd)  # bypass execute() — déjà fait par le drag
                h._redo.clear()
                h.changed.emit()
                if self._save_fn:
                    self._save_fn()
            self._drag_origin = None
            self._drag_confirmed = False
            self._drag_descendants = []
            self._drag_desc_origin = []

    def item_pos(self) -> tuple[float, float]:
        """Position Qt de l'item = position logique de l'acteur (item origin = ancrage)."""
        px, py = self.pos_px()
        return float(px), float(py)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            x, y = p.x(), p.y()
            if self._drag_origin is None:
                # setPos() programmatique hors drag (construction, sync depuis
                # l'inspector via move_actor_item…) — le modèle est déjà
                # à jour, ne pas le réécrire (donc ne pas re-snapper une
                # valeur hors-grille saisie volontairement au clavier).
                return QPointF(x, y)
            if not self._drag_confirmed:
                ox, oy = self._drag_origin
                if abs(x - ox) < self._CLICK_THRESHOLD and abs(y - oy) < self._CLICK_THRESHOLD:
                    # Jitter de clic, pas un vrai drag : ignorer le mouvement.
                    return QPointF(ox, oy)
                self._drag_confirmed = True
            if self.snap:
                x = round(x / 8) * 8
                y = round(y / 8) * 8
            # L'item (0,0) est directement la position logique de l'acteur
            self.scene_sprite.x = int(x)
            self.scene_sprite.y = int(y)
            if self._drag_desc_origin:
                # Translation groupée du sous-arbre (ROADMAP v0.23) : delta
                # depuis le DÉBUT du drag, pas depuis l'appel précédent — évite
                # toute dérive par accumulation d'arrondis de snap.
                ox0, oy0 = self._drag_origin
                dx, dy = int(x) - ox0, int(y) - oy0
                for it, ox, oy in self._drag_desc_origin:
                    it.scene_sprite.x = ox + dx
                    it.scene_sprite.y = oy + dy
                    it.setPos(*it.pos_px())
            if self.scene() is not None:
                self.scene().sprite_moved.emit()
            return QPointF(x, y)
        return super().itemChange(change, value)

    def _marker_rect(self, center: QPointF) -> QRectF:
        """Zone d'un repère (origine ou pivot) dans l'espace du PARENT sans la
        position : il est dessiné là, transform défait, pas dans le repère de
        l'image."""
        reach = _ORIGIN_ICO_SIZE / 2 + 2
        return QRectF(center.x() - reach, center.y() - reach, 2 * reach, 2 * reach)

    def boundingRect(self) -> QRectF:
        """Pixmap + repères d'origine et de pivot. Les repères et leurs bords
        antialiasés débordent du pixmap dès que le point est sur un bord (ou
        dehors) : hors du boundingRect, Qt ne les efface pas au déplacement et
        laisse une traînée blanche (surtout hors du canvas, sans fond qui
        recouvre). Les repères vivent dans l'espace d'où le transform est défait
        (cf. paint) : leur zone en repère local est donc leur image par
        l'inverse du transform."""
        rect = super().boundingRect()
        inverse, ok = self.transform().inverted()
        if not ok:
            inverse = QTransform()
        zones = [self._marker_rect(QPointF(0, 0))]
        if self._show_pivot:
            zones.append(self._marker_rect(self._pivot_point))
        for zone in zones:
            rect = rect.united(inverse.mapRect(zone))
        return rect

    def _paint_markers(self, painter, widget):
        """Origine (rouge) et point de pivot (bleu), à la sélection.

        Dessinés dans l'espace où le transform du sprite est DÉFAIT : l'origine
        est la position de l'acteur et le pivot reste fixe, ni l'un ni l'autre ne
        tournent ni ne changent d'échelle avec l'image. Le painter reçoit
        l'inverse du transform avant le dessin."""
        from ui.common.icons import scaled_pixmap

        inverse, ok = self.transform().inverted()
        painter.save()
        if ok:
            painter.setWorldTransform(inverse * painter.worldTransform())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        half = _ORIGIN_ICO_SIZE / 2
        px = scaled_pixmap("actor_origin", C.AXIS_X, _ORIGIN_ICO_SIZE,
                           _screen_scale(painter, widget))
        painter.drawPixmap(QRectF(-half, -half, _ORIGIN_ICO_SIZE, _ORIGIN_ICO_SIZE),
                           px, QRectF(px.rect()))

        if self._show_pivot:
            # Anneau + croix : se distingue de la cible de l'origine même sans la
            # couleur (daltonisme), et reste lisible sur un fond clair.
            c = self._pivot_point
            pen = QPen(QColor(C.AXIS_Y), 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(c, half * 0.6, half * 0.6)
            painter.drawLine(QPointF(c.x() - half, c.y()), QPointF(c.x() + half, c.y()))
            painter.drawLine(QPointF(c.x(), c.y() - half), QPointF(c.x(), c.y() + half))
        painter.restore()

    def set_mask_rects(self, rects: list):
        """Régions (coordonnées de SCÈNE) où ce sprite ne s'affiche pas —
        windows actives dont le bit OBJ est coupé. Cf. GBAScene.update_window_masks."""
        if rects == self._mask_rects:
            return
        self._mask_rects = list(rects)
        self.update()

    def _paint_content(self, painter, option, widget):
        """Le sprite lui-même : pixmap du jeu (nearest-neighbor, c'est du pixel
        art), ou repère d'actor sans sprite — une icône d'UI, redessinée à la
        résolution écran pour ne pas devenir floue au zoom."""
        if not self._placeholder:
            super().paint(painter, option, widget)
            return
        painter.save()
        painter.translate(self.offset())
        _draw_placeholder(painter, _screen_scale(painter, widget))
        painter.restore()

    def paint(self, painter, option, widget=None):
        # Supprimer le rendu de sélection Qt par défaut (dashed bleu)
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.StateFlag.State_Selected
        if self._mask_rects:
            # Clip limité au PIXMAP : l'outline de sélection et le repère
            # d'origine ci-dessous restent visibles, sinon un acteur masqué
            # deviendrait impossible à repérer et à manipuler dans l'éditeur.
            # mapFromScene : l'item porte scale/flip/rotation et un offset,
            # les rects arrivent en coordonnées de scène.
            painter.save()
            path = QPainterPath()
            path.addRect(super().boundingRect())
            for r in self._mask_rects:
                cut = QPainterPath()
                cut.addPolygon(self.mapFromScene(r))
                path = path.subtracted(cut)
            painter.setClipPath(path)
            self._paint_content(painter, clean, widget)
            painter.restore()
        else:
            self._paint_content(painter, clean, widget)
        # Outline quand sélectionné : périwinkle pour un MEMBRE de la sélection,
        # blanc pour l'item ACTIF (celui que l'inspecteur détaille) — même
        # grammaire que la grille du Palette Editor.
        if self.isSelected():
            sc = self.scene()
            is_active = getattr(sc, "active_item", None) is self
            ring = QColor("#ffffff") if is_active else QColor(C.ACCENT)
            painter.save()
            painter.setPen(QPen(ring, 1, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = super().boundingRect().adjusted(0, 0, -1, -1)
            painter.drawRect(r)
            # Petits coins pour renforcer la visibilité
            painter.setPen(QPen(ring, 2))
            for cx, cy in [
                (r.left(), r.top()),
                (r.right(), r.top()),
                (r.left(), r.bottom()),
                (r.right(), r.bottom()),
            ]:
                painter.drawPoint(int(cx), int(cy))
            painter.restore()

        # Repères d'origine (rouge) et de pivot (bleu) : affichés seulement à la
        # sélection ; au repos, ils encombraient la scène sans apporter
        # d'information actionnable.
        if self.isSelected():
            self._paint_markers(painter, widget)

    def set_snap(self, snap: bool):
        self.snap = snap


# ──────────────────────────────────────────────────────────────────
#  Item caméra — icône draggable + zone de vision
# ──────────────────────────────────────────────────────────────────
_CAM_ICO_SIZE = 12  # px, repère compact au coin de la vue
_ORIGIN_ICO_SIZE = 8  # px, cible compacte affichée à la sélection


class MaskablePixmapItem(QGraphicsPixmapItem):
    """Layer BG dont des régions peuvent être découpées à l'affichage.

    Sert à refléter dans le canvas ce que les windows matérielles font
    réellement à l'écran : une window active dont `layers_shown[bg]` est faux
    empêche ce layer de s'afficher DANS son rectangle (registre WININ). Les
    rects sont donnés en coordonnées de scène — l'item étant posé à l'origine,
    coordonnées d'item et de scène coïncident."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(pixmap, parent)
        self._mask_rects: list[QRectF] = []

    def set_mask_rects(self, rects: list):
        if rects == self._mask_rects:
            return
        self._mask_rects = list(rects)
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        if self._mask_rects:
            path = QPainterPath()
            path.addRect(self.boundingRect())
            for r in self._mask_rects:
                cut = QPainterPath()
                cut.addRect(r)
                path = path.subtracted(cut)
            painter.setClipPath(path)
        super().paint(painter, option, widget)


class CameraItem(QGraphicsItem):
    """
    Icône caméra draggable positionnée en haut-gauche de la zone de vue.
    La zone de vision 240×160 est un enfant non-interactif, visible quand sélectionnée.

    boundingRect() couvre toujours GBA_W×GBA_H : Qt sait ainsi quelle zone
    nettoyer quand l'item se déplace, même quand le rectangle de vision est affiché.
    """

    def __init__(
        self, canvas_w: int, canvas_h: int, cam_x: int = 0, cam_y: int = 0,
        frame_w: int = GBA_W, frame_h: int = GBA_H, camera=None, parent=None,
    ):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        # La caméra (modèle) que cet item représente. Une scène peut en
        # posséder plusieurs (révisé 2026-08-24) : chaque CameraItem porte SA
        # référence. `None` = la scène n'a pas de caméra : l'item n'est alors
        # qu'un SUPPORT INVISIBLE à (0,0) — il porte les sprites en espace écran
        # et l'aperçu des windows, comme le runtime les pose sans caméra — et
        # n'offre ni icône, ni sélection, ni déplacement (rien à éditer).
        self.camera = camera

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        if camera is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            self.setAcceptHoverEvents(True)
        else:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(150)
        self.setPos(cam_x, cam_y)
        self._hovered = False

        # Zone de vision — enfant non-interactif. Sa taille EST le frame de la
        # caméra (Camera.frame_w/h, réglé le 2026-08-24) — plus petite que
        # GBA_W×GBA_H quand la caméra pilote WIN0 (cf. set_frame_size).
        self._frame_w = frame_w
        self._frame_h = frame_h
        pen = QPen(QColor("#ffdd44"))
        pen.setWidth(0)
        pen.setCosmetic(True)  # sans ça, seule l'épaisseur du trait ignore le zoom —
                                # le motif de tirets s'étire quand même avec la vue
        pen.setStyle(Qt.PenStyle.DashLine)
        self._view = QGraphicsRectItem(0, 0, frame_w, frame_h, self)
        self._view.setPen(pen)
        self._view.setBrush(QBrush(QColor(255, 221, 68, 12)))
        self._view.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._view.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._view.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._view.setAcceptHoverEvents(False)
        self._view.setVisible(False)

        # Windows (WIN0/WIN1) — enfants de la caméra : une window est en espace
        # ÉCRAN, elle suit donc la vue automatiquement (position locale = position
        # dans l'écran GBA), sans recalcul à chaque déplacement de caméra.
        self._window_items: list[QGraphicsRectItem] = []
        # setToolTip après construction : le tooltip se base sur self.camera,
        # déjà posé plus haut.
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        if self.camera is None:
            return ""
        name = self.camera.name
        detail = label('cvitems.camera_tip', name=name, w=self._frame_w, h=self._frame_h)
        notes = getattr(self.camera, "notes", "")
        return notes_tooltip(notes, detail)

    @property
    def frame_w(self) -> int:
        return self._frame_w

    @property
    def frame_h(self) -> int:
        return self._frame_h

    def set_frame_size(self, w: int, h: int):
        """Redimensionne le rectangle de vue — c'est le frame écran de la
        caméra (`Camera.frame_w/h`), pas juste un aperçu : plus petit que
        240×160, la caméra pilote WIN0 à l'activation (cf. camera_switch())."""
        self._frame_w, self._frame_h = w, h
        self.prepareGeometryChange()
        self._view.setRect(0, 0, w, h)
        self.setToolTip(self._tooltip())

    # ── Windows (aperçu) ──────────────────────────────────────────

    def set_windows(self, windows: list):
        """Dessine l'aperçu des WindowSlot de la scène dans le cadre écran.

        Le rectangle est clampé à 240×160 comme le fait `window_set()` au
        runtime — l'aperçu montre donc la zone RÉELLEMENT obtenue sur console,
        pas la saisie brute (une window plus large que l'écran est tronquée)."""
        for it in self._window_items:
            it.setParentItem(None)
            if it.scene():
                it.scene().removeItem(it)
        self._window_items = []

        for i, ws in enumerate(w for w in (windows or []) if not w.is_obj):
            # Fenêtre-objet : pas de rectangle — sa forme vient des pixels
            # opaques des sprites en obj_mode=2, non prévisualisable ici.
            # Quel rang matériel (WIN0/WIN1) chaque window nommée reçoit est
            # décidé par l'allocateur au build (`window_alloc.py`) — sans
            # incidence sur cet aperçu, qui montre la géométrie AUTHORÉE.
            x0 = max(0, min(int(ws.x), GBA_W))
            y0 = max(0, min(int(ws.y), GBA_H))
            x1 = max(x0, min(int(ws.x) + int(ws.w), GBA_W))
            y1 = max(y0, min(int(ws.y) + int(ws.h), GBA_H))

            color = QColor(_WIN_COLORS[i % len(_WIN_COLORS)])
            pen = QPen(color)
            pen.setWidth(0)
            pen.setCosmetic(True)
            # Trait plein = window active au runtime ; pointillé = authorée mais
            # window_show(…, 0) → invisible sur console.
            pen.setStyle(Qt.PenStyle.SolidLine if ws.visible else Qt.PenStyle.DotLine)

            rect = QGraphicsRectItem(x0, y0, x1 - x0, y1 - y0, self)
            rect.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(40 if ws.visible else 16)
            rect.setBrush(QBrush(fill))
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            rect.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            rect.setAcceptHoverEvents(False)
            rect.setToolTip(
                label('cvitems.window_tip', name=ws.name or label('cvitems.unnamed_window'),
                      w=x1 - x0, h=y1 - y0, x=x0, y=y0)
                + ("" if ws.visible else label('cvitems.window_inactive'))
            )
            self._window_items.append(rect)

        self._sync_view_visibility()

    # ── QGraphicsItem interface ───────────────────────────────────

    def boundingRect(self) -> QRectF:
        # Grand rect pour que Qt efface correctement lors du déplacement.
        return QRectF(0, 0, GBA_W, GBA_H)

    def shape(self) -> "QPainterPath":
        # Hit-test limité à l'icône seule — les actors en-dessous restent cliquables.
        path = QPainterPath()
        if self.camera is not None:
            path.addRect(QRectF(0, 0, _CAM_ICO_SIZE, _CAM_ICO_SIZE))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        # Icône UI (pas du pixel art de jeu) : rendue à la résolution écran du
        # zoom courant plutôt qu'agrandie depuis un pixmap de 20 px — sinon elle
        # est floue dès le zoom ×2 (le canvas s'ouvre déjà à ×2). Lissage local,
        # sans affecter le nearest-neighbor des sprites/BG ailleurs sur le canvas.
        from ui.common.icons import scaled_pixmap

        if self.camera is None:
            return   # support invisible : pas de caméra, rien à montrer

        # Palette locale de l'outil Caméra : une présence gris clair lisible
        # au repos, un contraste clair au survol, puis l'ambre de sélection.
        if self.isSelected():
            color = "#ffdd44"
        elif self._hovered:
            color = "#f2f2f2"
        else:
            color = "#d0d0d0"
        px = scaled_pixmap("camera", color, _CAM_ICO_SIZE,
                           _screen_scale(painter, widget))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(
            QRectF(0, 0, _CAM_ICO_SIZE, _CAM_ICO_SIZE), px, QRectF(px.rect())
        )

    # ── Canvas resize ─────────────────────────────────────────────

    def set_canvas_size(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h

    # ── itemChange ────────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            x = max(0, min(p.x(), self._canvas_w - GBA_W))
            y = max(0, min(p.y(), self._canvas_h - GBA_H))
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Les windows sont en espace écran : leur découpe des layers BG
            # (espace monde) doit suivre la caméra.
            sc = self.scene()
            if sc is not None and hasattr(sc, "update_window_masks"):
                sc.update_window_masks()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # prepareGeometryChange() notifie Qt que la zone de dessin
            # effective change (icon seul → icon + viewport 240×160).
            self.prepareGeometryChange()
            self._sync_view_visibility()
        return super().itemChange(change, value)

    def _sync_view_visibility(self):
        """Aperçu 240×160 visible seulement sélectionnée ou survolée."""
        self._view.setVisible(self.isSelected() or self._hovered)

    def hoverEnterEvent(self, e):
        self._hovered = True
        self._sync_view_visibility()
        self.update()
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._hovered = False
        self._sync_view_visibility()
        self.update()
        super().hoverLeaveEvent(e)



# ──────────────────────────────────────────────────────────────────
#  Bezel d'écran — cadre de l'espace authorable : trait périwinkle + lueur,
#  pour marquer l'écran sans se lire comme une erreur. AA activée localement
#  (la vue la désactive globalement pour le pixel art), sinon les coins
#  arrondis crénèlent.
# ──────────────────────────────────────────────────────────────────
class ScreenBezelItem(QGraphicsItem):
    _COLOR = QColor(C.ACCENT)

    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._w = w
        self._h = h
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w = w
        self._h = h

    def boundingRect(self) -> QRectF:
        m = 5.0   # marge pour le trait + halo peint (sinon Qt rogne au bord)
        return QRectF(-m, -m, self._w + 2 * m, self._h + 2 * m)

    def paint(self, painter: QPainter, option, widget=None):
        r = QRectF(0, 0, self._w, self._h)
        # Halo peint à la main : QGraphicsDropShadowEffect plante sous le
        # backend offscreen (crash natif en capture headless, 0xC0000409).
        for i, alpha in ((3, 18), (2, 34), (1, 55)):
            glow_pen = QPen(self._COLOR)
            glow_pen.setWidthF(1.4 + i * 1.3)
            glow_pen.setCosmetic(True)
            c = QColor(self._COLOR)
            c.setAlpha(alpha)
            glow_pen.setColor(c)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)
        pen = QPen(self._COLOR)
        pen.setWidthF(1.4)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)


# ──────────────────────────────────────────────────────────────────
#  Grille 8px — item unique (évite N QGraphicsLineItem)
# ──────────────────────────────────────────────────────────────────
class GridItem(QGraphicsItem):
    def __init__(self, w: int, h: int, cell: int = 8, parent=None):
        super().__init__(parent)
        self._w = w
        self._h = h
        self._cell = cell
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w = w
        self._h = h

    def set_cell(self, cell: int):
        self._cell = cell
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        # Grille fine 8px
        pen8 = QPen(QColor(255, 255, 255, 22))
        pen8.setWidth(0)
        # Grille large 16px (toujours visible au-dessus de la fine)
        pen16 = QPen(QColor(255, 255, 255, 55))
        pen16.setWidth(0)
        # Seules les lignes de la zone EXPOSÉE sont tracées (au glisser d'un
        # item, Qt ne repeint qu'une petite région), et par lots : un appel Qt
        # par pen au lieu d'un par ligne.
        cell = self._cell
        exposed = option.exposedRect
        x0 = max(0, int(exposed.left() // cell) * cell)
        x1 = min(self._w, int(exposed.right() // cell + 1) * cell)
        y0 = max(0, int(exposed.top() // cell) * cell)
        y1 = min(self._h, int(exposed.bottom() // cell + 1) * cell)
        fine, large = [], []
        for x in range(x0, x1 + 1, cell):
            (fine if cell == 8 and x % 16 != 0 else large).append(QLineF(x, y0, x, y1))
        for y in range(y0, y1 + 1, cell):
            (fine if cell == 8 and y % 16 != 0 else large).append(QLineF(x0, y, x1, y))
        painter.setPen(pen8)
        painter.drawLines(fine)
        painter.setPen(pen16)
        painter.drawLines(large)


# ──────────────────────────────────────────────────────────────────
#  Overlay boîtes de collision acteurs
# ──────────────────────────────────────────────────────────────────


class ActorBoxOverlay(QGraphicsItem):
    """
    Dessine les CollisionBoxComponent des acteurs passés via set_actors().
    Solid → rouge,  trigger → vert.
    z=160 (au-dessus des sprites, sous la caméra).
    """

    _C_SOLID = QColor(255, 70, 70, 100)
    _C_TRIGGER = QColor(70, 220, 120, 100)
    _B_SOLID = QColor(255, 90, 90, 240)
    _B_TRIGGER = QColor(90, 240, 140, 240)

    def __init__(self, canvas_w: int, canvas_h: int, parent=None):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._actors: list = []
        self._var_defaults: dict = {}   # (src, name) -> valeur par défaut (aperçu des refs)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(160)
        self.setVisible(False)

    def set_actors(self, actors: list, var_defaults: dict | None = None):
        self._actors = list(actors)
        if var_defaults is not None:
            self._var_defaults = var_defaults
        self.setVisible(bool(self._actors))
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._canvas_w, self._canvas_h)

    def paint(self, painter: QPainter, option, widget=None):
        from core.models.components import CollisionBoxComponent
        from core.models.field_value import FieldValue

        # Un champ peut être une référence de variable : on résout à la valeur
        # par défaut de la variable pour dessiner une box représentative.
        resolve = lambda src, name: self._var_defaults.get((src, name))

        pen_s = QPen(self._B_SOLID, 0)
        pen_t = QPen(self._B_TRIGGER, 0)
        for actor in self._actors:
            for comp in actor.components:
                if not isinstance(comp, CollisionBoxComponent) or not comp.active:
                    continue
                x = FieldValue.parse(actor.x).px(resolve) + FieldValue.parse(comp.x).px(resolve)
                y = FieldValue.parse(actor.y).px(resolve) + FieldValue.parse(comp.y).px(resolve)
                w = FieldValue.parse(comp.w).px(resolve)
                h = FieldValue.parse(comp.h).px(resolve)
                if comp.solid:
                    painter.fillRect(x, y, w, h, self._C_SOLID)
                    painter.setPen(pen_s)
                else:
                    painter.fillRect(x, y, w, h, self._C_TRIGGER)
                    painter.setPen(pen_t)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)


# ──────────────────────────────────────────────────────────────────
#  Scène GBA
# ──────────────────────────────────────────────────────────────────
class GuideLine(QGraphicsLineItem):
    """Guide d'alignement, élargi de la marge de repeinte que Qt ne calcule pas.

    Trait cosmétique (largeur 0) : Qt efface une zone de largeur nulle, donc le
    guide laisse une traînée en se déplaçant. Même piège que
    `UIRegionItem.boundingRect`."""

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-6.0, -6.0, 6.0, 6.0)




# ──────────────────────────────────────────────────────────────────
#  Overlay de collision (z=300)
# ──────────────────────────────────────────────────────────────────
_T = COLLISION_TILE_SIZE  # 8

_C_SOLID = QColor(255, 126, 88, 42)
# Surbrillance de survol : neutre, pour ne pas se confondre avec un type de tuile.
_C_HOVER = QColor(255, 255, 255, 46)
_B_HOVER = QColor(255, 255, 255, 200)
_C_STEEP = QColor(255, 183, 77, 48)
_C_GENTLE = QColor(255, 211, 102, 48)
_B_SOLID = QColor(255, 126, 88, 175)
_B_STEEP = QColor(255, 183, 77, 185)
_B_GENTLE = QColor(255, 211, 102, 185)
# Plafond — teinte bleue/violette pour distinguer visuellement
_C_STEEP_INV = QColor(110, 168, 255, 48)
_C_GENTLE_INV = QColor(152, 194, 255, 48)
_B_STEEP_INV = QColor(110, 168, 255, 185)
_B_GENTLE_INV = QColor(152, 194, 255, 185)

_FLOOR_SLOPES = (
    TILE_SLOPE_L,
    TILE_SLOPE_R,
    TILE_SLOPE_R_STEEP_HI,
    TILE_SLOPE_R_STEEP_LO,
    TILE_SLOPE_L_STEEP_HI,
    TILE_SLOPE_L_STEEP_LO,
)
_FLOOR_GENTLE = (TILE_SLOPE_L_LO, TILE_SLOPE_L_HI, TILE_SLOPE_R_LO, TILE_SLOPE_R_HI)
_CEIL_SLOPES = (
    TILE_SLOPE_L_INV,
    TILE_SLOPE_R_INV,
    TILE_SLOPE_R_STEEP_HI_INV,
    TILE_SLOPE_R_STEEP_LO_INV,
    TILE_SLOPE_L_STEEP_HI_INV,
    TILE_SLOPE_L_STEEP_LO_INV,
)
_CEIL_GENTLE = (
    TILE_SLOPE_L_LO_INV,
    TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_R_LO_INV,
    TILE_SLOPE_R_HI_INV,
)


def _slope_path(x: int, y: int, tile_type: int) -> QPainterPath:
    """Le contour de la matière d'une tuile de collision, posé en (x, y).

    Dérivé de `collision_tiles.polygon()` : la forme est décrite UNE fois, là où
    le codegen la lit aussi pour émettre la table du runtime. La physique du jeu
    et ce dessin ne peuvent donc plus diverger."""
    p = QPainterPath()
    poly = CT.polygon(tile_type)
    if not poly:
        return p
    p.moveTo(x + poly[0][0], y + poly[0][1])
    for px, py in poly[1:]:
        p.lineTo(x + px, y + py)
    p.closeSubpath()
    return p


class CollisionOverlay(QGraphicsItem):
    """
    Affiche la collision_map d'une scène par-dessus le canvas.
    Visible uniquement quand l'outil collision est actif.
    Ne reçoit pas les événements souris (géré par GBAView).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map: list[list[int]] = []
        self._rows = 0
        self._cols = 0
        self._preview: Optional[list[tuple[int, int, int]]] = None
        # Surbrillance sous la souris : (col, row, largeur, hauteur) en tuiles —
        # l'empreinte que le prochain geste de peinture va couvrir.
        self._hover: Optional[tuple[int, int, int, int]] = None
        self._cache: Optional[QPixmap] = None  # cache rendu hors-écran (map seule)
        self.setZValue(300)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    # ── Données ───────────────────────────────────────────────────

    def load(self, collision_map: list[list[int]]):
        self.prepareGeometryChange()
        self._map = collision_map
        self._rows = len(collision_map)
        self._cols = len(collision_map[0]) if self._rows else 0
        self._cache = None
        self.update()

    def get_map(self) -> list[list[int]]:
        return self._map

    def set_tile(self, col: int, row: int, tile_type: int):
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._map[row][col] = tile_type
            self._cache = None
            self.update()

    def tile_at(self, col: int, row: int) -> int:
        if 0 <= row < self._rows and 0 <= col < self._cols:
            return self._map[row][col]
        return TILE_EMPTY

    def set_preview(self, tiles: Optional[list[tuple[int, int, int]]]):
        """Mise à jour légère : le cache de base reste valide, on redessine juste le preview."""
        self._preview = tiles
        self.update()

    def set_hover(self, footprint: Optional[tuple[int, int, int, int]]):
        """Surbrillance de l'empreinte du pinceau, rognée aux bornes de la carte."""
        if footprint is not None:
            col, row, w, h = footprint
            c0, r0 = max(col, 0), max(row, 0)
            c1, r1 = min(col + w, self._cols), min(row + h, self._rows)
            footprint = (c0, r0, c1 - c0, r1 - r0) if c1 > c0 and r1 > r0 else None
        if footprint == self._hover:
            return
        self._hover = footprint
        self.update()

    def scene_to_tile(self, scene_x: float, scene_y: float) -> tuple[int, int]:
        return int(scene_x // _T), int(scene_y // _T)

    # ── Dessin ────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, max(1, self._cols) * _T, max(1, self._rows) * _T)

    def paint(self, painter: QPainter, option, widget=None):
        # Reconstruire le cache si invalidé
        w = max(1, self._cols) * _T
        h = max(1, self._rows) * _T
        if self._cache is None or self._cache.width() != w or self._cache.height() != h:
            self._cache = QPixmap(w, h)
            self._cache.fill(Qt.GlobalColor.transparent)
            cp = QPainter(self._cache)
            cp.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for row in range(self._rows):
                for col in range(self._cols):
                    self._draw_tile(cp, col, row, self._map[row][col], alpha_mul=1.0)
            cp.end()

        # Les collisions sont une information de tuile : elles restent nettes
        # à tous les zooms, sans halos ni faux coins arrondis.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(0, 0, self._cache)

        # Preview slope au-dessus du cache (pas mis en cache — éphémère)
        if self._preview:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for col, row, t in self._preview:
                self._draw_tile(painter, col, row, t, alpha_mul=1.55)
            painter.restore()

        if self._hover:
            col, row, w, h = self._hover
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.fillRect(col * _T, row * _T, w * _T, h * _T, _C_HOVER)
            painter.setPen(QPen(_B_HOVER, 0))
            painter.drawRect(col * _T, row * _T, w * _T - 1, h * _T - 1)
            painter.restore()

    def _draw_tile(
        self, painter: QPainter, col: int, row: int, t: int, alpha_mul: float
    ):
        if t == TILE_EMPTY:
            return
        x, y = col * _T, row * _T

        def _colored(base_fill, base_bord):
            f = QColor(base_fill)
            f.setAlpha(int(base_fill.alpha() * alpha_mul))
            b = QColor(base_bord)
            b.setAlpha(int(base_bord.alpha() * alpha_mul))
            return f, b

        if t == TILE_SOLID:
            fill, bord = _colored(_C_SOLID, _B_SOLID)
            painter.fillRect(x, y, _T, _T, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawRect(x, y, _T - 1, _T - 1)
            # Hachure pixelisée, plus lisible qu'une masse rouge opaque.
            hatch = QColor(bord)
            hatch.setAlpha(max(24, hatch.alpha() // 3))
            painter.save()
            painter.setClipRect(x, y, _T, _T)
            painter.setPen(QPen(hatch, 0))
            for offset in range(-_T, _T * 2, 4):
                painter.drawLine(x + offset, y + _T, x + offset + _T, y)
            painter.restore()
        elif t in _FLOOR_SLOPES:
            fill, bord = _colored(_C_STEEP, _B_STEEP)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _FLOOR_GENTLE:
            fill, bord = _colored(_C_GENTLE, _B_GENTLE)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _CEIL_SLOPES:
            fill, bord = _colored(_C_STEEP_INV, _B_STEEP_INV)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _CEIL_GENTLE:
            fill, bord = _colored(_C_GENTLE_INV, _B_GENTLE_INV)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)


