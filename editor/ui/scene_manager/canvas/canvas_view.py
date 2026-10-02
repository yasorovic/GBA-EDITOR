"""ui/scene_manager/canvas/canvas_view.py — la vue zoomable du canvas.

Extrait de `scene_canvas` (A3) : `GBAView`, le `QGraphicsView` — zoom/pan,
souris, drag&drop de prefabs, multi-sélection, menu contextuel, et le DISPATCH
vers l'outil actif. C'est elle qui porte le côté « vue » du cycle intrinsèque
avec `canvas_tools` : la vue instancie l'outil (import local), l'outil connaît la
vue (type). Cf. TodoTechnique A3 / BOUCLES_ACCEPTEES.
"""
from __future__ import annotations

from typing import Optional

from core.models.resource import MIME_PREFAB_TEMPLATE
from ui.common.theme import C
from ui.scene_manager.canvas.canvas_const import GBA_W, GBA_H
from ui.scene_manager.canvas.canvas_scene import GBAScene
from ui.scene_manager.canvas.canvas_items import SpriteItem, CollisionOverlay
from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QTransform, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication, QGraphicsView, QGraphicsItem, QGraphicsRectItem,
)


# ──────────────────────────────────────────────────────────────────
#  Vue zoomable
# ──────────────────────────────────────────────────────────────────
class GBAView(QGraphicsView):
    prefab_template_dropped = pyqtSignal(str, QPointF)
    zoom_changed = pyqtSignal(float)
    # Émis après CHAQUE clic gauche traité par Qt (RubberBandDrag), qu'il ait
    # ou non changé la sélection — Qt.selectionChanged ne se déclenche QUE si
    # l'ensemble sélectionné change réellement : un clic répété en dehors du
    # canvas alors que la sélection est déjà vide, ou un 2e clic dans la zone
    # active alors qu'une actor était déjà désélectionné, ne le ferait jamais
    # fire, et l'inspecteur resterait figé sur son panneau précédent. Ce signal
    # force une réévaluation à chaque clic, indépendamment de tout changement.
    left_click_settled = pyqtSignal()

    def __init__(self, scene: GBAScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(C.BG_DEEP))
        # Focus clavier : nécessaire pour que les raccourcis du canvas (contexte
        # WidgetWithChildren de SceneEditor) se déclenchent quand la vue est active.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._zoom = 2.0
        self._apply_zoom()
        self.setAcceptDrops(True)
        # Outil actif — initialisé après import (évite la circularité)
        self._active_tool: "BaseTool | None" = None
        # Snap preview — 16×16, visible uniquement si snap actif
        self._snap_on = False
        self._snap_preview: "QGraphicsRectItem | None" = None
        # Contrôleur de peinture par palette BG (injecté par SceneEditor).
        self.inpainting_controller: "Optional[SceneInpaintingController]" = None
        self.ui_region_controller: "Optional[UIRegionController]" = None
        # Pan au clic-central — agit sur les scrollbars, donc indépendant de
        # l'outil actif et du zoom. `_pan_last` = dernière position viewport (px).
        self._panning = False
        self._pan_last: "Optional[QPointF]" = None
        # Un Shift+clic (multi-sélection) est traité ici sans passer à Qt : le
        # relâchement correspondant doit l'être aussi, d'où ce drapeau.
        self._swallow_left_release = False
        # Position (coords scène) du dernier clic gauche non consommé par l'outil
        # actif — lu par SceneEditor._on_selection_changed pour distinguer un clic
        # dans la zone active du canvas (→ re-sélectionne la scène) d'un clic en
        # dehors (→ désélectionne tout). Valide uniquement PENDANT l'appel à
        # super().mousePressEvent() ci-dessous (remis à None juste après) : ça
        # évite qu'une valeur périmée soit relue par un _on_selection_changed
        # déclenché plus tard pour une tout autre raison (Échap, clic droit…).
        self._last_click_scene_pos: "Optional[QPointF]" = None
        # Alt+glisser = dupliquer : instantané des items glissés, pris au press
        # (cf. _arm_alt_duplicate). None = geste ordinaire.
        self._alt_drag: "Optional[list]" = None
        self._alt_press_scene = QPointF()
        self._alt_press_viewport = QPointF()

    def drawBackground(self, painter: QPainter, rect):
        """Fond de travail mat avec repère pointillé très discret."""
        painter.save()
        painter.fillRect(rect, QColor(C.CANVAS_BG))
        # Repère calé sur la grille de jeu (16px) pour rester lisible comme
        # repère de placement, pas seulement de texture de fond.
        pen = QPen(QColor(C.BORDER_MID))
        pen.setCosmetic(True)
        pen.setWidthF(2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # En-deçà de 100% de zoom, le pas visuel double tous les -50% de
        # zoom (donc le nombre de points affichés /2) : moins on voit de la
        # scène à l'écran, moins la grille encombre.
        step = 16
        away = 1.0 / self._zoom
        while away >= 1.5:
            step *= 2
            away /= 1.5
        left = int(rect.left() // step) * step
        top = int(rect.top() // step) * step
        for x in range(left, int(rect.right()) + 1, step):
            for y in range(top, int(rect.bottom()) + 1, step):
                painter.drawPoint(x, y)
        painter.restore()

    def leaveEvent(self, e):
        if self._snap_preview:
            self._snap_preview.setVisible(False)
        if self._active_tool:
            self._active_tool.on_leave()
        super().leaveEvent(e)

    def dragLeaveEvent(self, e):
        e.accept()  # supprime le warning Qt "drag leave before drag enter"

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            name = bytes(e.mimeData().data(MIME_PREFAB_TEMPLATE)).decode("utf-8")
            pos = self.mapToScene(e.position().toPoint())
            self.prefab_template_dropped.emit(name, pos)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def _apply_zoom(self):
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.5, min(self._zoom * factor, 8.0))
        self._apply_zoom()

    def fit(self, w: int = GBA_W, h: int = GBA_H):
        self.fitInView(0, 0, w, h, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def zoom_to(self, level: float):
        self._zoom = max(0.5, min(level, 8.0))
        self._apply_zoom()

    # ── Outil actif ───────────────────────────────────────────────

    collision_painted = pyqtSignal()
    # Clic-droit sur un actor en mode Sélection → (SpriteItem, QPoint global).
    actor_context_requested = pyqtSignal(object, object)
    # Alt+glisser franchi le seuil : les originaux ont été remis en place ; il
    # reste à créer les copies, SUR place, avant que la souris ne les emporte.
    duplicate_drag_started = pyqtSignal()
    # Un outil de pose (acteur, élément d'interface) vient de poser son objet :
    # le canvas rend alors la main à l'outil Sélection.
    placement_done = pyqtSignal()

    @property
    def collision_overlay(self) -> Optional["CollisionOverlay"]:
        s = self.scene()
        return s.collision_overlay if isinstance(s, GBAScene) else None

    def set_tool(self, tool: "BaseTool") -> None:
        if self._active_tool is not None:
            self._active_tool.deactivate()
        self._active_tool = tool
        tool.activate()

    def set_snap(self, enabled: bool) -> None:
        self._snap_on = enabled
        if not enabled and self._snap_preview:
            self._snap_preview.setVisible(False)

    def _ensure_snap_preview(self):
        if self._snap_preview is None:
            item = QGraphicsRectItem(0, 0, 16, 16)
            item.setBrush(QBrush(QColor(100, 255, 120, 55)))
            item.setPen(QPen(QColor(100, 255, 120, 210), 0))
            item.setZValue(49)  # sous le preview AddActorTool (z=50)
            item.setVisible(False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene().addItem(item)
            self._snap_preview = item

    # ── Délégation souris → outil actif ──────────────────────────

    def mousePressEvent(self, e):
        _btn = e.button()
        if _btn == Qt.MouseButton.MiddleButton:
            self._start_pan(e.position())
            e.accept()
            return
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_press(pos, e):
                e.accept()
                return
        # En mode Sélection, le bouton droit ne sert QU'AU menu contextuel : on
        # ne le passe pas à QGraphicsView, qui viderait la sélection dès que le
        # clic tombe à côté d'un actor — or c'est justement cette sélection que
        # le menu doit pouvoir viser (cf. contextMenuEvent).
        if _btn == Qt.MouseButton.RightButton and self._is_select_tool():
            e.accept()
            return
        # Grammaire de sélection commune avec le Scene Tree : Ctrl bascule un
        # élément, Shift l'ajoute. Elle est traitée ici (et non par Qt) afin de
        # conserver la notion d'item actif utilisée par l'inspecteur.
        if (_btn == Qt.MouseButton.LeftButton and self._is_select_tool()
                and (e.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                      | Qt.KeyboardModifier.ShiftModifier))
                and self._selectable_item_at(
                    self.mapToScene(e.position().toPoint())) is not None):
            self._multi_select_press(self.mapToScene(e.position().toPoint()),
                                     e.modifiers())
            # Le relâchement qui suit doit être avalé lui aussi : un press que Qt
            # n'a pas vu suivi d'un release qu'il voit laisse sa machinerie de
            # grab de souris dans un état incohérent (les clics suivants
            # repartent alors vers le dernier item saisi, où qu'on clique).
            self._swallow_left_release = True
            e.accept()
            return
        if _btn == Qt.MouseButton.LeftButton:
            self._last_click_scene_pos = self.mapToScene(e.position().toPoint())
        super().mousePressEvent(e)
        if _btn == Qt.MouseButton.LeftButton:
            # APRÈS Qt : c'est lui qui vient d'arrêter la sélection que le geste
            # va déplacer (un clic sur un item hors sélection la remplace).
            if (self._is_select_tool()
                    and (e.modifiers() & Qt.KeyboardModifier.AltModifier)):
                self._arm_alt_duplicate(self._last_click_scene_pos, e.position())
            self.left_click_settled.emit()
        self._last_click_scene_pos = None

    def mouseMoveEvent(self, e):
        # Pan au clic-central : translate la vue via les scrollbars, avant toute
        # autre logique (snap preview, délégation outil).
        if self._panning and (e.buttons() & Qt.MouseButton.MiddleButton):
            delta = e.position() - self._pan_last
            self._pan_last = e.position()
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - round(delta.x()))
            vbar.setValue(vbar.value() - round(delta.y()))
            e.accept()
            return
        # Filet de sécurité : si le relâchement du bouton central a été manqué
        # (survenu hors du viewport, avalé par un reflow…), le pan resterait armé
        # et le curseur figé en poing fermé. Le prochain mouvement sans le bouton
        # le rattrape et restaure le curseur.
        if self._panning:
            self._end_pan()
        if (self._alt_drag is not None and (e.buttons() & Qt.MouseButton.LeftButton)
                and self._alt_drag_crossed(e)):
            self._start_alt_duplicate()
        pos = self.mapToScene(e.position().toPoint())
        # Snap preview — indépendant de l'outil actif
        if self._snap_on:
            self._ensure_snap_preview()
            sx = int(pos.x() // 16) * 16
            sy = int(pos.y() // 16) * 16
            self._snap_preview.setPos(sx, sy)
            self._snap_preview.setVisible(True)
        # Délégation à l'outil (hover + drag)
        if self._active_tool:
            if self._active_tool.on_move(pos, e):
                e.accept()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        _btn = e.button()
        # Repris ici quoi qu'il arrive : un geste avorté (pan, outil qui prend
        # la main) ne doit pas laisser un instantané périmé armer le prochain.
        self._alt_drag = None
        if _btn == Qt.MouseButton.MiddleButton and self._panning:
            self._end_pan()
            e.accept()
            return
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_release(pos, e):
                e.accept()
                return
        if _btn == Qt.MouseButton.RightButton and self._is_select_tool():
            e.accept()              # symétrique du press : le droit est au menu
            return
        if _btn == Qt.MouseButton.LeftButton and self._swallow_left_release:
            self._swallow_left_release = False   # pendant du Shift+clic ci-dessus
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # ── Alt+glisser = dupliquer ───────────────────────────────────
    # La copie naît AU FRANCHISSEMENT du seuil, sur place, puis c'est elle que
    # la souris emporte : l'original ne quitte jamais sa position. Qt tient le
    # grab de souris sur l'original ; on remet donc celui-ci en place, on
    # relâche le geste, on crée les copies (sélectionnées), puis on REJOUE le
    # clic d'origine pour que Qt saisisse la copie.

    # En deçà (px scène) c'est un clic Alt, pas un glisser : sinon un
    # frémissement de souris crée une copie invisible sous l'original.
    _ALT_DRAG_THRESHOLD = 2

    def _arm_alt_duplicate(self, scene_pos, viewport_pos):
        """Mémorise les items que le glisser va emporter (pour les remettre en
        place) et le point du clic (pour le rejouer sur la copie).

        Position Qt (le geste s'y mesure) ET position MODÈLE d'un acteur : le
        drag réécrit `actor.x/y` à chaque frame et perdrait l'expression
        d'origine (« 4t », une réf de variable)."""
        sc = self.scene()
        if scene_pos is None or not hasattr(sc, "selectable_items"):
            return
        if self._selectable_item_at(scene_pos) is None:
            return          # Alt dans le vide : rubber band, rien à dupliquer
        entries = []
        for it in sc.selectable_items():
            actor = getattr(it, "scene_sprite", None)
            model = (actor.x, actor.y) if actor is not None else None
            entries.append((it, QPointF(it.pos()), model))
        self._alt_drag = entries or None
        self._alt_press_scene = QPointF(scene_pos)
        self._alt_press_viewport = QPointF(viewport_pos)

    def _alt_drag_crossed(self, e) -> bool:
        d = self.mapToScene(e.position().toPoint()) - self._alt_press_scene
        return (abs(d.x()) >= self._ALT_DRAG_THRESHOLD
                or abs(d.y()) >= self._ALT_DRAG_THRESHOLD)

    def _start_alt_duplicate(self):
        entries, self._alt_drag = self._alt_drag, None
        self._restore_alt_originals(entries)
        at = self._alt_press_viewport
        # Fin du geste sur les originaux (neutralisés : aucune commande de
        # déplacement n'est poussée).
        self.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, at, Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.duplicate_drag_started.emit()      # copies créées + sélectionnées
        # Sans Alt, sinon le clic rejoué réarmerait une duplication.
        self.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, at, Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    def _restore_alt_originals(self, entries: list):
        """Remet les originaux en place et coupe leur geste de déplacement."""
        for it, origin, model in entries:
            try:
                if isinstance(it, SpriteItem):
                    it._drag_origin = None
                else:
                    it._press_pos = None
                cur = it.pos()
            except RuntimeError:
                continue                      # item C++ détruit entre-temps
            if model is not None:
                it.scene_sprite.x, it.scene_sprite.y = model
                it.sync_pos()
            else:
                # Un conteneur a emmené ses descendants à l'écran (leur modèle
                # est relatif au parent, il n'a pas bougé) : même delta retour.
                if hasattr(it, "_move_descendants"):
                    it._move_descendants(origin.x() - cur.x(), origin.y() - cur.y())
                it.setPos(origin)

    # ── Pan clic-central ──────────────────────────────────────────

    def _start_pan(self, viewport_pos: "QPointF"):
        self._pan_last = viewport_pos
        if self._panning:
            return
        self._panning = True
        # Curseur applicatif (au-dessus de tout) plutôt que setCursor sur la vue :
        # QGraphicsView mémorise comme « original » le curseur effectif du viewport
        # au survol des items (ex. le curseur d'outil), et le re-pose à chaque
        # sortie d'item. Un poing fermé posé sur la vue serait ainsi capturé et
        # figé. L'override est orthogonal à cette machinerie et se retire proprement,
        # révélant à nouveau le curseur d'outil en place.
        QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan(self):
        if not self._panning:
            return
        self._panning = False
        self._pan_last = None
        QApplication.restoreOverrideCursor()

    def _actor_item_at(self, scene_pos) -> "Optional[SpriteItem]":
        """Premier SpriteItem sous la position (scène) donnée, sinon None."""
        for it in self.scene().items(scene_pos):
            if isinstance(it, SpriteItem):
                return it
        return None

    def _is_select_tool(self) -> bool:
        # Import local : canvas_tools importe ce module (cycle à l'import).
        from ui.scene_manager.canvas_tools import SelectTool
        return isinstance(self._active_tool, SelectTool)

    def _selectable_item_at(self, scene_pos):
        """Premier item éligible à la multi-sélection sous la position :
        acteur ou zone de texte."""
        for it in self.scene().items(scene_pos):
            if isinstance(it, (SpriteItem, UIRegionItem)):
                return it
        return None

    def _multi_select_press(self, scene_pos, modifiers):
        """Applique la grammaire de sélection partagée dans l'éditeur.

        Ctrl+clic bascule l'appartenance d'un élément ; Shift+clic l'ajoute.
        Ctrl est prioritaire si les deux touches sont maintenues. Dans les deux
        cas, l'élément visé devient actif : l'inspecteur suit donc naturellement
        le dernier choix de l'utilisateur."""
        sc = self.scene()
        item = self._selectable_item_at(scene_pos)
        if item is None:
            return
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            item.setSelected(not item.isSelected())
            if item.isSelected():
                sc.set_active_item(item)
            else:
                sc.reconcile_active()
        else:
            item.setSelected(True)
            sc.set_active_item(item)
        # Même signal que tout clic gauche : il porte déjà « la sélection a
        # peut-être bougé, resynchronise » — indispensable pour le Ctrl+Shift,
        # qui ne change pas l'appartenance donc n'émet pas selectionChanged.
        self.left_click_settled.emit()

    def contextMenuEvent(self, e):
        """En mode Sélection : clic-droit → menu contextuel (Renommer /
        Dupliquer / Supprimer).

        La cible est, dans l'ordre : l'actor sous le curseur, sinon la SÉLECTION
        COURANTE — dès qu'un actor est sélectionné, le clic-droit ouvre donc son
        menu même à côté de lui, sans avoir à viser le sprite. Deux règles de
        sélection : un actor cliqué HORS sélection la remplace (le menu agit sur
        ce qu'on montre), un actor cliqué DANS une multi-sélection la préserve
        (sinon un clic-droit réduirait silencieusement la sélection à un seul).
        Pour les autres outils, le clic-droit sert à peindre ou à l'outil — pas
        de menu OS."""
        if self._is_select_tool():
            item = self._actor_item_at(self.mapToScene(e.pos()))
            if item is not None:
                if not item.isSelected():
                    self.scene().clearSelection()
                    item.setSelected(True)
            else:
                item = next((it for it in self.scene().selectedItems()
                             if isinstance(it, SpriteItem)), None)
            if item is not None:
                self.actor_context_requested.emit(item, e.globalPos())
            e.accept()
            return
        if self._active_tool:
            e.accept()
            return
        super().contextMenuEvent(e)
