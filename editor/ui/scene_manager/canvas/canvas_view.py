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
from ui.scene_manager.canvas.canvas_alt_duplicate import AltDuplicateGesture
from ui.scene_manager.canvas.canvas_scene import GBAScene
from ui.scene_manager.canvas.canvas_items import SpriteItem, CollisionOverlay, SnapPreviewItem
from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSizeF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF, QTransform, QWheelEvent
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
    # Émis après CHAQUE relâchement du bouton gauche traité par Qt : fin d'un
    # glisser d'item (la caméra y écrit son cadrage final).
    left_released = pyqtSignal()

    def __init__(self, scene: GBAScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(C.BG_DEEP))
        # Le fond (grille de points) est mis en cache : au pan, Qt décale le
        # cache et ne redessine que la bande découverte.
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        # Focus clavier : nécessaire pour que les raccourcis du canvas (contexte
        # WidgetWithChildren de SceneEditor) se déclenchent quand la vue est active.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._zoom = 2.0
        self._apply_zoom()
        # Le canvas change de taille (scène, fond) : la zone défilable suit.
        scene.sceneRectChanged.connect(lambda _rect: self._update_pan_area())
        # Le voile hors-caméra dépend de la sélection : repeindre toute la vue.
        scene.selectionChanged.connect(lambda: self.viewport().update())
        self.setAcceptDrops(True)
        # Outil actif — initialisé après import (évite la circularité)
        self._active_tool: "BaseTool | None" = None
        # Snap preview — contour 8×8, visible uniquement si snap actif
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
        # Alt+glisser = dupliquer : geste autonome (cf. canvas_alt_duplicate).
        self._alt_duplicate = AltDuplicateGesture(self)

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
        # Un seul appel Qt pour tous les points : une boucle drawPoint en Python
        # ralentissait le rafraîchissement pendant le pan.
        points = QPolygonF([
            QPointF(x, y)
            for x in range(left, int(rect.right()) + 1, step)
            for y in range(top, int(rect.bottom()) + 1, step)
        ])
        painter.drawPoints(points)
        painter.restore()

    def drawForeground(self, painter: QPainter, rect):
        """Assombrit (noir 50 %) le canvas HORS du cadre de la caméra sélectionnée.

        Peint ici, au premier plan de la VUE, plutôt que par un item : un item
        couvrant tout le canvas devrait être invalidé à chaque pas de la caméra,
        alors que ce voile ne change que dans la bande que la caméra découvre."""
        sc = self.scene()
        if not isinstance(sc, GBAScene):
            return
        cameras = [c for c in sc.camera_items() if (c.isSelected() or c.view_forced) and c.camera is not None]
        if not cameras:
            return
        shade = QPainterPath()
        shade.addRect(sc.sceneRect().intersected(rect))
        for cam in cameras:
            hole = QPainterPath()
            hole.addRect(QRectF(cam.pos(), QSizeF(cam.frame_w, cam.frame_h)))
            shade = shade.subtracted(hole)
        painter.fillPath(shade, QColor(0, 0, 0, 128))

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

    def _update_pan_area(self):
        """Zone défilable de la VUE : le canvas plus une marge d'une demi-fenêtre.

        Sans marge, la zone défilable est celle de la scène (le canvas) : dès
        qu'il tient dans la fenêtre — zoom faible ou petite scène — les barres
        n'ont aucune plage et le pan au clic-central n'a rien à déplacer. Posée
        sur la VUE, la marge laisse `GBAScene.sceneRect()` intact : c'est lui
        qui borne la zone active du canvas (clics, grille, fond)."""
        scene = self.scene()
        if scene is None:
            return
        zoom = max(self._zoom, 0.5)
        mx = self.viewport().width() / zoom * 0.5
        my = self.viewport().height() / zoom * 0.5
        self.setSceneRect(scene.sceneRect().adjusted(-mx, -my, mx, my))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_pan_area()

    def _apply_zoom(self):
        # Le point de la scène sous le curseur (ou au centre de la vue) reste à
        # sa place : changer la zone défilable déplace sinon le contenu.
        cursor = self.viewport().mapFromGlobal(QCursor.pos())
        anchor = cursor if self.viewport().rect().contains(cursor)             else self.viewport().rect().center()
        pinned = self.mapToScene(anchor)
        self._update_pan_area()
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)
        shift = self.mapFromScene(pinned) - anchor
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + shift.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + shift.y())
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.5, min(self._zoom * factor, 8.0))
        self._apply_zoom()

    def fit(self, w: int = GBA_W, h: int = GBA_H):
        self._update_pan_area()
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
    # Alt+glisser relâché au-delà du seuil : (dx, dy) en px scène. La création
    # des copies est l'affaire de l'appelant.
    duplicate_drag_finished = pyqtSignal(int, int)
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
            item = SnapPreviewItem(0, 0, 8, 8)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setPen(QPen(QColor(255, 255, 255, 230), 0))
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
        # Alt+clic sur un item : le geste de duplication prend la main seul.
        if (_btn == Qt.MouseButton.LeftButton and self._is_select_tool()
                and (e.modifiers() & Qt.KeyboardModifier.AltModifier)
                and self._alt_duplicate.begin(
                    self.mapToScene(e.position().toPoint()))):
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
        pos = self.mapToScene(e.position().toPoint())
        if self._alt_duplicate.active:
            if e.buttons() & Qt.MouseButton.LeftButton:
                self._alt_duplicate.move(pos)
            else:
                self._alt_duplicate.cancel()    # relâchement manqué
            e.accept()
            return
        # Snap preview — indépendant de l'outil actif
        if self._snap_on:
            self._ensure_snap_preview()
            sx = int(pos.x() // 8) * 8
            sy = int(pos.y() // 8) * 8
            self._snap_preview.setPos(sx, sy)
            # Masqué tant qu'une sélection est active : le curseur de pose n'a
            # plus de sens quand on manipule déjà quelque chose.
            self._snap_preview.setVisible(not self.scene().selectedItems())
        elif self._snap_preview:
            self._snap_preview.setVisible(False)
        # Délégation à l'outil (hover + drag)
        if self._active_tool:
            if self._active_tool.on_move(pos, e):
                e.accept()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        _btn = e.button()
        if _btn == Qt.MouseButton.LeftButton and self._alt_duplicate.active:
            shift = self._alt_duplicate.finish(
                self.mapToScene(e.position().toPoint()))
            if shift is not None:
                self.duplicate_drag_finished.emit(*shift)
            e.accept()
            return
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
        if _btn == Qt.MouseButton.LeftButton:
            self.left_released.emit()

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
