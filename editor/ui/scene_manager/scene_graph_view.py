"""ui/scene_manager/scene_graph_view.py — la vue Graphe des scènes.

Vue autonome du Canvas (à côté du `SceneEditor` 2D) qui DESSINE le graphe des
transitions ``scene.switch`` d'un projet. La **structure** (nœuds/arêtes) reste
DÉRIVÉE des scripts : la vue reçoit une projection `SceneGraph` (domaine
scripting, sans Qt) et n'en possède rien. La **présentation** — où chaque nœud
est posé — est, elle, mémorisée : un node editor sans rangement à la main ne tient
pas sur un RPG de quarante scènes. Les positions vivent dans un sidecar d'éditeur
(`SceneGraphState`), jamais dans la `Scene` ni dans le manifeste.

Interaction, calquée sur le canvas de scène (`canvas/canvas_view.py`) :
pan au clic-milieu, zoom molette ancré sous le curseur, sélection au rectangle
(RubberBand) et Ctrl/Shift. Déplacer un nœud écrit sa position ; « Re-arrange »
relance l'auto-layout et écrase tout.

Recalcul — pull à l'activation, mémoïsé sur une empreinte. `scene_graph` relit
et re-parse chaque script ; on ne le rappelle donc que lorsque l'empreinte des
scripts change. Le déplacement d'un nœud, lui, ne change pas l'empreinte : il ne
re-parse rien : il ne fait que déplacer les items et rafraîchir les seules arêtes
attachées au nœud déplacé.
"""
from __future__ import annotations

import os
from uuid import uuid4

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform,
)
from PyQt6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QGraphicsScene, QGraphicsView, QMenu,
    QMessageBox, QLineEdit, QToolButton, QVBoxLayout, QWidget,
)

from core.history import Command, get_history, SetFieldCmd
from core.keybindings import bind
from core.selection_bus import get_bus
from core.scene_graph_state import SceneGraphState
from scripting.scene_graph import SceneGraph, node_diagnostics, scene_graph
from ui.common.labels import label
from ui.common.theme import C, QSS, T, ui_font
from ui.common.canvas_top_bar import CanvasTopBar
from ui.scene_manager.scene_graph_items import (
    CARD_H, CARD_W, MissingTargetItem, SceneCardItem, SceneGraphEdgeItem,
    ScenePreviewToggleItem,
)
from ui.scene_manager.scene_graph_breadcrumb import SceneGraphBreadcrumb
from ui.scene_manager.scene_graph_group_items import (
    COLLAPSED_H, COLLAPSED_W, DOOR_H, DOOR_W, HEADER_H, BoundaryDoorItem,
    GroupToggleItem, SceneGroupBoxItem,
)
from ui.scene_manager.scene_graph_note_items import NoteToggleItem, SceneGraphNoteItem
from ui.scene_manager.scene_graph_layout import layout_positions
from ui.scene_manager.scene_graph_commands import EdgePresentationCmd
from ui.scene_manager.canvas.canvas_const import GBA_W, GBA_H
from ui.scene_manager.canvas.canvas_raster import bg_pixmap, layer_png_path

_GROUP_PAD = 16.0  # respiration entre le cadre d'un groupe et ses cartes

_MIN_ZOOM = 0.25
_MAX_ZOOM = 4.0
_PAN_MARGIN = 2000.0  # respiration autour du contenu pour paner dans le vide
_GRID_STEP = 40.0


class _RewriteEdgeCmd(Command):
    """Réécriture groupée d'une transition Lua, annulable en un geste."""
    def __init__(self, changes, refresh):
        self._changes, self._refresh = changes, refresh
        self.label = "Reconnecter transition"
    def _apply(self, index):
        for path, before, after in self._changes:
            path.write_text((before, after)[index], encoding="utf-8")
        self._refresh(index)
    def execute(self): self._apply(1)
    def undo(self): self._apply(0)


class _GraphCanvas(QGraphicsView):
    """Vue graphique : pan/zoom/RubberBand, et remonte le clic gauche sans décider.

    Elle n'interprète pas le clic gauche : elle émet l'item sous le curseur (ou
    `None`), laissant `SceneGraphView` traduire le geste en sélection ou en
    ouverture. Le clic-milieu (pan) et la molette (zoom) sont, eux, traités ici
    car ils n'engagent que la vue.
    """

    clicked = pyqtSignal(object)
    double_clicked = pyqtSignal(object)
    drag_finished = pyqtSignal()   # fin d'un clic gauche (un nœud a pu bouger)
    ascend_requested = pyqtSignal()  # ← / repli sans sélection : remonter d'un niveau
    descend_requested = pyqtSignal()  # → : entrer dans le groupe sélectionné
    delete_requested = pyqtSignal()  # Backspace / Suppr : supprimer la sélection
    context_menu_requested = pyqtSignal(object, object)  # clic-droit → (pos globale, item)
    navigation_changed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_panning = True
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            # La vue tranche : supprimer la sélection, ou — si rien n'est
            # sélectionné — remonter d'un niveau (l'ancien rôle de Backspace).
            self.delete_requested.emit()
            event.accept()
            return
        # Navigation par niveaux au clavier : → entre dans le groupe sélectionné,
        # ← remonte (même geste que le double-clic et le fil d'Ariane).
        if event.key() == Qt.Key.Key_Right:
            self.descend_requested.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self.ascend_requested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.descend_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_panning = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event):
        # La vue ne décide pas du menu : elle en signale la demande, avec l'item
        # sous le curseur, à `SceneGraphView` — seul à savoir ce qu'un item
        # représente (scène, groupe) et à connaître la sélection.
        self.context_menu_requested.emit(
            event.globalPos(), self.itemAt(event.pos()))
        event.accept()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # pour recevoir Backspace
        self._zoom = 1.0
        self._panning = False
        self._space_panning = False
        self._pan_last = None
        self._rewire_edges: list[SceneGraphEdgeItem] = []

    def drawBackground(self, painter, rect):
        """Fond quadrillé léger, en coordonnées du graphe.

        Les points suivent donc le pan et restent stables sous les nœuds ; leur
        coût est borné par le rectangle visible, pas par la taille du graphe.
        """
        painter.fillRect(rect, QColor(C.BG_DEEP))
        pen = QPen(QColor(C.BORDER_MID))
        pen.setCosmetic(True)
        pen.setWidthF(2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        # En-deçà de 100% de zoom, le pas visuel double tous les -75% de zoom
        # (donc le nombre de points affichés /2) : moins on voit de la scène à
        # l'écran, moins la grille encombre. Le pas d'accrochage des nœuds
        # (_GRID_STEP) n'est pas concerné.
        step = _GRID_STEP
        away = 1.0 / self._zoom
        while away >= 1.75:
            step *= 2
            away /= 1.75
        left = int(rect.left() // step) * int(step)
        top = int(rect.top() // step) * int(step)
        right, bottom = rect.right(), rect.bottom()
        x = float(left)
        while x <= right:
            y = float(top)
            while y <= bottom:
                painter.drawPoint(int(x), int(y))
                y += step
            x += step

    # ── Zoom ──────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.set_zoom(self._zoom * factor)

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(_MIN_ZOOM, min(zoom, _MAX_ZOOM))
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)
        self.navigation_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.navigation_changed.emit()

    # ── Pan au clic-milieu (translation via les scrollbars) ───────────

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.MiddleButton
                or (event.button() == Qt.MouseButton.LeftButton and self._space_panning)):
            self._start_pan(event.position())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            # Le port d'entrée est la poignée de reconnexion. Les arêtes sont
            # derrière la carte, on les résout donc à partir de leur pointe.
            port_owner = self.itemAt(event.position().toPoint())
            while port_owner is not None and not isinstance(
                    port_owner, (SceneCardItem, MissingTargetItem)):
                port_owner = port_owner.parentItem()
            if port_owner is not None:
                rect = port_owner.anchor_rect()
                on_input = (abs(scene_pos.x() - rect.left()) <= 14
                            and abs(scene_pos.y() - rect.center().y()) <= 14)
                if on_input:
                    candidates = [i for i in self.scene().items()
                                  if isinstance(i, SceneGraphEdgeItem)
                                  and i.target_handle_contains(scene_pos)]
                    # Une sélection existante est l'intention explicite de
                    # l'auteur : le port sert alors de poignée commune, même
                    # si les arêtes sélectionnées arrivent actuellement sur
                    # des cibles différentes. Sans sélection, on résout la
                    # pointe sous le port de façon déterministe.
                    selected = [i for i in self.scene().selectedItems()
                                if isinstance(i, SceneGraphEdgeItem)]
                    chosen = selected or candidates[:1]
                    if chosen:
                        self._rewire_edges = chosen
                        self.setCursor(Qt.CursorShape.CrossCursor)
                        event.accept()
                        return
            # Qt met à jour Ctrl/Shift avant que l'inspecteur lise la sélection.
            clicked_item = self.itemAt(event.position().toPoint())
            super().mousePressEvent(event)
            self.clicked.emit(clicked_item)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rewire_edges:
            scene_pos = self.mapToScene(event.position().toPoint())
            for edge in self._rewire_edges:
                edge.preview_target(scene_pos)
            # Pendant le glisser uniquement, invalider tout le viewport évite
            # les traces de l'ancien chemin lorsque son bounding rect change.
            self.viewport().update()
            event.accept()
            return
        if self._panning and (event.buttons() & (Qt.MouseButton.MiddleButton | Qt.MouseButton.LeftButton)):
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
            hbar.setValue(hbar.value() - round(delta.x()))
            vbar.setValue(vbar.value() - round(delta.y()))
            event.accept()
            return
        # Filet de sécurité : un relâchement du bouton central manqué laisserait
        # le pan armé et le curseur figé en poing fermé ; le prochain mouvement
        # sans le bouton le rattrape.
        if self._panning:
            self._end_pan()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton) and self._panning:
            self._end_pan()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._rewire_edges:
            edges, self._rewire_edges = self._rewire_edges, []
            self.unsetCursor()
            scene_pos = self.mapToScene(event.position().toPoint())
            target = edges[0].rewire_target_at(scene_pos) if edges else None
            for edge in edges:
                edge.restore_target()
            if target is not None:
                edges[0].request_rewire(edges, target)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # Après Qt : le déplacement éventuel de l'item est arrivé à sa
            # position finale, la vue peut le persister.
            self.drag_finished.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.itemAt(event.position().toPoint()))
        super().mouseDoubleClickEvent(event)

    def _start_pan(self, viewport_pos):
        self._pan_last = viewport_pos
        if self._panning:
            return
        self._panning = True
        # Curseur applicatif (au-dessus de tout) plutôt que setCursor sur la vue :
        # QGraphicsView gère le curseur du viewport au survol des items et mémorise
        # comme « original » le curseur effectif au moment où l'on entre sur un
        # item. Un poing fermé posé sur la vue serait alors capturé comme original
        # et re-posé à chaque sortie d'item — d'où un poing figé. L'override est,
        # lui, orthogonal à cette machinerie et se retire proprement.
        QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan(self):
        if not self._panning:
            return
        self._panning = False
        self._pan_last = None
        QApplication.restoreOverrideCursor()


class _GraphMinimap(QWidget):
    """Aperçu de navigation : cartes, groupes, notes et zone actuellement vue.

    La mini-carte est volontairement une synthèse de la mise en page, sans
    arêtes ni texte : à cette échelle, ils brouilleraient le repère plutôt que
    l'aider. Quand tout tient dans le viewport, elle reste présente mais s'efface
    progressivement à 20 %, évitant les apparitions/disparitions brusques.
    """

    _W, _H, _PAD = 180, 120, 8

    def __init__(self, canvas: _GraphCanvas):
        super().__init__(canvas.viewport())
        self._canvas = canvas
        self._dragging = False
        self._enabled = True
        self._overflowing: bool | None = None
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.2)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._opacity_animation.setDuration(180)
        self._opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide()

    def _content_rect(self) -> QRectF:
        relevant = (SceneCardItem, MissingTargetItem, SceneGroupBoxItem, SceneGraphNoteItem)
        rects = [item.sceneBoundingRect() for item in self._canvas.scene().items()
                 if isinstance(item, relevant)]
        if not rects:
            return QRectF()
        out = QRectF(rects[0])
        for rect in rects[1:]:
            out = out.united(rect)
        return out

    def _geometry(self):
        content = self._content_rect()
        visible = self._canvas.mapToScene(self._canvas.viewport().rect()).boundingRect()
        if content.isEmpty():
            return None
        # La zone visible fait partie de la carte de référence. Sans cette union,
        # son cadre est rogné dès qu'il dépasse les éléments du graphe (haut/bas
        # dans le cas rapporté), précisément quand la minimap est nécessaire.
        source = content.united(visible).adjusted(-24, -24, 24, 24)
        inner = QRectF(self._PAD, self._PAD, self.width() - 2 * self._PAD,
                       self.height() - 2 * self._PAD)
        scale = min(inner.width() / source.width(), inner.height() / source.height())
        drawn = QRectF(inner.left(), inner.top(), source.width() * scale,
                       source.height() * scale)
        drawn.moveCenter(inner.center())
        return source, visible, drawn, scale, not visible.contains(content)

    def _set_opacity(self, overflowing: bool) -> None:
        if overflowing == self._overflowing:
            return
        self._overflowing = overflowing
        self._opacity_animation.stop()
        self._opacity_animation.setStartValue(self._opacity_effect.opacity())
        self._opacity_animation.setEndValue(1.0 if overflowing else 0.2)
        self._opacity_animation.start()

    def refresh(self) -> None:
        if not self._enabled:
            self.hide()
            return
        geo = self._geometry()
        self.setVisible(geo is not None)
        if geo is not None:
            self._set_opacity(geo[4])
            self.update()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.refresh()

    def paintEvent(self, event):
        geo = self._geometry()
        if geo is None:
            return
        source, visible, target, scale, _overflowing = geo
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(C.BORDER_MID), 1))
        painter.setBrush(QBrush(QColor(C.BG_RAISED)))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        painter.save()
        painter.setClipRect(target)

        def mini(rect: QRectF) -> QRectF:
            return QRectF(target.left() + (rect.left() - source.left()) * scale,
                         target.top() + (rect.top() - source.top()) * scale,
                         max(2.0, rect.width() * scale), max(2.0, rect.height() * scale))

        for item in self._canvas.scene().items():
            if isinstance(item, SceneGroupBoxItem):
                color = QColor(item.color or C.BORDER_MID)
                painter.setPen(QPen(color, 1)); painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(mini(item.sceneBoundingRect()))
            elif isinstance(item, SceneGraphNoteItem):
                color = QColor(item.color or "#FFFFFF")
                painter.setPen(QPen(color, 1)); painter.setBrush(QBrush(color))
                painter.drawRect(mini(item.sceneBoundingRect()))
            elif isinstance(item, (SceneCardItem, MissingTargetItem)):
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QBrush(QColor(C.TEXT_DIM)))
                painter.drawRect(mini(item.sceneBoundingRect()))
        painter.setPen(QPen(QColor(C.ACCENT), 1.5)); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(mini(visible))
        painter.restore()

    def _navigate(self, pos) -> None:
        geo = self._geometry()
        if geo is None:
            return
        source, _visible, target, scale, _overflowing = geo
        scene_pos = QPointF(source.left() + (pos.x() - target.left()) / scale,
                            source.top() + (pos.y() - target.top()) / scale)
        self._canvas.centerOn(scene_pos)
        self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True; self._navigate(event.position()); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._navigate(event.position()); event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False; event.accept(); return
        super().mouseReleaseEvent(event)


def _fingerprint(project) -> tuple:
    """Empreinte bon marché de ce qui fait varier la STRUCTURE projetée.

    Noms de scènes et scène de départ, plus l'état sur disque de chaque script
    exécutable (`stat`, sans lecture ni parsing). La position des nœuds n'y entre
    pas : la déplacer ne doit pas re-parser une seule ligne de Lua.
    """
    scenes = tuple(getattr(project, "scenes", ()) or ())
    start = getattr(getattr(project, "settings", None), "start_scene", "")
    stamps: set[tuple] = set()
    if hasattr(project, "scene_scripts"):
        for scene in scenes:
            scripts, _opaque = project.scene_scripts(scene)
            for path in scripts:
                try:
                    st = os.stat(path)
                    stamps.add((str(path), st.st_mtime_ns, st.st_size))
                except OSError:
                    stamps.add((str(path), None, None))
    return (start, tuple(scene.name for scene in scenes), tuple(sorted(stamps)))


class SceneGraphView(QWidget):
    """Vue exclusive du Canvas rendant le graphe des scènes.

    Autonome : sa propre `QGraphicsScene` et sa propre `QGraphicsView`, aucun
    lien avec le canvas 2D. Elle projette à l'affichage (ou sur `refresh`) et ne
    re-projette que si l'empreinte a changé.

    Navigation : un clic sur une scène la sélectionne via le `SelectionBus`
    (l'inspecteur suit). Les gestes hors de son ressort sont émis en intentions
    que la fenêtre traduit : `scene_opened`, `edge_selected`, `edge_opened`.
    """

    scene_opened = pyqtSignal(str)      # double-clic sur une scène
    edge_selected = pyqtSignal(object)  # clic → liste[SceneGraphEdge]
    edge_opened = pyqtSignal(object)    # double-clic sur une arête → SceneGraphEdge
    scenes_selected = pyqtSignal(list)  # sélection (multi) → noms de scènes
    groups_changed = pyqtSignal()       # un groupe de scènes a été créé (sync project viewer)
    selection_cleared = pyqtSignal()    # aucune carte/arête/groupe active
    group_selected = pyqtSignal(str)    # clic sur un groupe → son inspecteur
    note_selected = pyqtSignal(str)     # clic sur une note → son inspecteur
    scene_create_requested = pyqtSignal(float, float)  # clic-droit vide → (x, y) graphe

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._state: SceneGraphState | None = None
        self._folders = None            # AssetFolderStore partagé (famille scenes)
        self._graph: SceneGraph | None = None
        self._fingerprint: tuple | None = None
        self._level: str | None = None  # groupe ouvert (None = racine)
        self._active_name: str | None = None  # scène ouverte dans le canvas (liseré)
        # Aperçu du fond PAR SCÈNE (piloté par la pastille du nœud, persisté dans
        # le sidecar) ; le cache mémoïse la vignette d'une scène entre deux rendus.
        self._preview_cache: dict[str, QPixmap | None] = {}  # nom scène -> vignette
        self._syncing = False           # garde anti-boucle de sélection croisée
        self._cards: dict[str, SceneCardItem] = {}
        self._boxes: dict[str, SceneGroupBoxItem] = {}   # groupe replié -> boîte
        self._frames: dict[str, SceneGroupBoxItem] = {}  # groupe déplié -> cadre
        self._name_box: dict[str, SceneGroupBoxItem] = {}  # scène cachée -> sa boîte
        self._missing: dict[str, MissingTargetItem] = {}
        self._notes: dict[str, SceneGraphNoteItem] = {}
        self._notes_visible = True
        self._edge_bindings: dict[object, list[SceneGraphEdgeItem]] = {}

        self._scene = QGraphicsScene(self)
        self._view = _GraphCanvas(self._scene, self)
        self._view.setBackgroundBrush(QColor(C.BG_DEEP))
        self._view.clicked.connect(self._on_click)
        self._view.double_clicked.connect(self._on_double_click)
        self._view.drag_finished.connect(self._persist_moves)
        self._view.ascend_requested.connect(self._ascend)
        self._view.descend_requested.connect(self._descend_selected)
        self._view.delete_requested.connect(self._delete_selection)
        self._view.context_menu_requested.connect(self._show_context_menu)
        self._view.navigation_changed.connect(self._update_minimap)
        self._view.horizontalScrollBar().valueChanged.connect(self._update_minimap)
        self._view.verticalScrollBar().valueChanged.connect(self._update_minimap)
        self._minimap = _GraphMinimap(self._view)
        # Ctrl+G : ranger les scènes sélectionnées du graphe dans un nouveau
        # groupe. Même id remappable que le project viewer — un seul geste,
        # deux vues ; n'agit que si la vue (ou un enfant) a le focus.
        self._sc_group = QShortcut(QKeySequence(), self)
        self._sc_group.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_group.activated.connect(self._group_selected_scenes)
        bind("scene.group", self._sc_group)
        self._graph_shortcuts: list[QShortcut] = []
        for binding_id, callback in (
            ("scene.graph_fit", self._focus_graph),
            ("scene.graph_zoom_reset", lambda: self._view.set_zoom(1.0)),
            ("scene.graph_zoom_in", lambda: self._view.set_zoom(self._view._zoom * 1.15)),
            ("scene.graph_zoom_out", lambda: self._view.set_zoom(self._view._zoom / 1.15)),
            ("scene.graph_toggle_minimap", self._toggle_minimap),
            ("scene.graph_deselect", self._scene.clearSelection),
            ("scene.graph_search", self._open_scene_search),
        ):
            shortcut = QShortcut(QKeySequence(), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            bind(binding_id, shortcut)
            self._graph_shortcuts.append(shortcut)
        # Sélection croisée avec le project viewer : la sélection Qt de la scène
        # graphique remonte les scènes sélectionnées (rectangle, Ctrl/Shift).
        self._scene.selectionChanged.connect(self._emit_scene_selection)
        # Les arêtes n'empruntent pas le SelectionBus : elles ont leur propre
        # inspecteur. Ce branchement couvre donc Ctrl/clic et RubberBand,
        # qui ne passent pas par le signal `clicked` de la vue.
        self._scene.selectionChanged.connect(self._on_graph_selection_changed)

        self._breadcrumb = SceneGraphBreadcrumb()
        self._breadcrumb.level_selected.connect(self._go_to_level)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._view, 1)
        layout.addWidget(self._breadcrumb)
        self._view.navigation_changed.connect(self._update_zoom_label)
        self._update_zoom_label()

    def _update_zoom_label(self, *_unused) -> None:
        self._top_bar.set_zoom(self._view._zoom)

    # ── Barre d'outils propre à la vue Graphe ─────────────────────────

    # Paliers de zoom du graphe — mêmes bornes que _MIN_ZOOM/_MAX_ZOOM.
    _ZOOM_LEVELS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]

    def _build_toolbar(self) -> CanvasTopBar:
        # Barre partagée avec le Scene Editor (cf. ui/common/canvas_top_bar) :
        # même widget de zoom, ancré à gauche, dans les deux vues. Le graphe
        # n'a pas de dimensions canvas/curseur pixel à afficher à droite.
        bar = CanvasTopBar(label("scncanvas.graph_fit_tip"), show_coords=False)
        bar.zoom_step_asked.connect(self._zoom_step)
        bar.fit_asked.connect(self._fit_graph)
        self._top_bar = bar

        self._btn_minimap = bar.add_toggle(
            "view_minimap", label("scncanvas.graph_minimap_tip"), self._set_minimap_visible)
        self._btn_minimap.setChecked(True)
        self._btn_notes = bar.add_toggle(
            "view_notes", label("scncanvas.graph_show_notes_tip"), self._set_notes_visible)
        self._btn_notes.setChecked(True)
        self._btn_search = bar.add_toggle(
            "search", label("scncanvas.graph_search_tip"), self._set_scene_search_visible)

        self._scene_search = QLineEdit()
        self._scene_search.setPlaceholderText(label("scncanvas.graph_search_placeholder"))
        self._scene_search.setFixedWidth(180)
        self._scene_search.setVisible(False)
        self._scene_search.returnPressed.connect(self._search_scene)
        bar.add_widget(self._scene_search)

        self._btn_rearrange = QToolButton()
        self._btn_rearrange.setText(label("scncanvas.graph_rearrange"))
        self._btn_rearrange.setToolTip(label("scncanvas.graph_rearrange_tip"))
        self._btn_rearrange.setFont(ui_font(T.MD))
        self._btn_rearrange.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rearrange.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"color:{C.TEXT_NORM};padding:3px 12px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}")
        self._btn_rearrange.clicked.connect(self._rearrange)
        bar.add_trailing(self._btn_rearrange)
        return bar

    def _zoom_step(self, direction: int) -> None:
        current = self._view._zoom
        levels = self._ZOOM_LEVELS
        idx = min(range(len(levels)), key=lambda i: abs(levels[i] - current))
        idx = max(0, min(idx + direction, len(levels) - 1))
        self._view.set_zoom(levels[idx])

    def _update_minimap(self, *_unused) -> None:
        """Repositionne et recalcule la mini-carte après navigation ou rendu."""
        viewport = self._view.viewport()
        self._minimap.move(max(8, viewport.width() - self._minimap.width() - 12),
                           max(8, viewport.height() - self._minimap.height() - 12))
        self._minimap.raise_()
        self._minimap.refresh()

    def _focus_graph(self) -> None:
        """F : recentre la sélection, ou cadre tout le graphe si elle est vide."""
        if not self._center_graph_on_selection():
            self._fit_graph()

    def _fit_graph(self) -> None:
        """Cadre les éléments du niveau ouvert, avec une marge respirante."""
        content = self._scene.itemsBoundingRect()
        if content.isEmpty():
            return
        self._view.fitInView(content.adjusted(-48, -48, 48, 48),
                             Qt.AspectRatioMode.KeepAspectRatio)
        self._view._zoom = self._view.transform().m11()
        self._view.navigation_changed.emit()

    def _center_graph_on_selection(self) -> bool:
        """Centre les éléments sélectionnés et indique si une cible existait."""
        focusable = (SceneCardItem, MissingTargetItem, SceneGroupBoxItem, SceneGraphNoteItem)
        items = [item for item in self._scene.selectedItems() if isinstance(item, focusable)]
        if items:
            rect = items[0].sceneBoundingRect()
            for item in items[1:]:
                rect = rect.united(item.sceneBoundingRect())
        else:
            return False
        self._view.centerOn(rect.center())
        self._update_minimap()
        return True

    def _set_minimap_visible(self, visible: bool) -> None:
        self._minimap.set_enabled(visible)

    def _toggle_minimap(self) -> None:
        self._btn_minimap.setChecked(not self._btn_minimap.isChecked())

    def _open_scene_search(self) -> None:
        self._btn_search.setChecked(True)
        self._scene_search.setFocus()
        self._scene_search.selectAll()

    def _set_scene_search_visible(self, visible: bool) -> None:
        self._scene_search.setVisible(visible)
        if visible:
            self._scene_search.setFocus()

    def _search_scene(self) -> None:
        query = self._scene_search.text().strip().casefold()
        if not query:
            return
        scenes = list(getattr(self._project, "scenes", ()) or ())
        found = next((scene for scene in scenes if scene.name.casefold() == query), None)
        found = found or next((scene for scene in scenes if query in scene.name.casefold()), None)
        if found is None:
            self._scene_search.setStyleSheet(f"border:1px solid {C.ACCENT_RED};")
            return
        self._scene_search.setStyleSheet("")
        # Une recherche est globale : ouvrir le niveau parent direct garantit que
        # la carte existe réellement, plutôt que de centrer une boîte repliée.
        target_level = self._folders.folder_of("scenes", found.name) if self._folders else None
        if target_level != self._level:
            self._level = target_level
            if self._graph is not None:
                self._render(self._graph)
        card = self._cards.get(found.name)
        if card is not None:
            self._scene.clearSelection()
            card.setSelected(True)
            self._view.centerOn(card.sceneBoundingRect().center())
            self._update_minimap()

    # ── Navigation ────────────────────────────────────────────────────

    def _scene_by_name(self, name: str):
        for scene in getattr(self._project, "scenes", ()) or ():
            if scene.name == name:
                return scene
        return None

    def _on_click(self, item) -> None:
        if isinstance(item, ScenePreviewToggleItem):
            self._toggle_scene_preview(item.name)
        elif isinstance(item, GroupToggleItem):
            self._toggle_group(item.group_id)
        elif isinstance(item, NoteToggleItem):
            self._toggle_note(item.note_id)
        elif isinstance(item, SceneCardItem):
            scene = self._scene_by_name(item.name)
            if scene is not None:
                get_bus().select(scene)
        elif isinstance(item, SceneGroupBoxItem):
            self.group_selected.emit(item.group_id)
        elif isinstance(item, SceneGraphNoteItem):
            self.note_selected.emit(item.note_id)
        elif isinstance(item, SceneGraphEdgeItem):
            self._emit_selected_edges(item)
        # Un marqueur de cible absente n'ouvre ni ne sélectionne rien.

    # ── Sélection croisée avec le project viewer ──────────────────────

    def _emit_scene_selection(self) -> None:
        """Remonte les scènes sélectionnées dans le graphe (sauf pendant un rendu
        ou une synchro entrante, pour ne pas boucler)."""
        if self._syncing:
            return
        names = [i.name for i in self._scene.selectedItems()
                 if isinstance(i, SceneCardItem)]
        self.scenes_selected.emit(names)

    def _emit_selected_edges(self, fallback=None) -> None:
        edges = [item.edge for item in self._scene.selectedItems()
                 if isinstance(item, SceneGraphEdgeItem)
                 and getattr(item, "edge", None) is not None]
        self.edge_selected.emit(edges or ([fallback.edge] if fallback is not None else []))

    def _on_graph_selection_changed(self) -> None:
        if self._syncing:
            return
        if not self._scene.selectedItems():
            self.selection_cleared.emit()
            return
        edges = [item.edge for item in self._scene.selectedItems()
                 if isinstance(item, SceneGraphEdgeItem)
                 and getattr(item, "edge", None) is not None]
        if edges:
            self.edge_selected.emit(edges)

    def selected_scene_name(self) -> str | None:
        """Nom de la scène sélectionnée si UNE SEULE l'est — pour que la bascule
        vers l'éditeur de scène ouvre celle-ci. None si zéro ou plusieurs cartes
        sélectionnées (aucune cible unique)."""
        names = [i.name for i in self._scene.selectedItems()
                 if isinstance(i, SceneCardItem)]
        return names[0] if len(names) == 1 else None

    def set_active_scene(self, name: str | None) -> None:
        """Marque la scène ACTIVE (ouverte dans le canvas 2D) d'un liseré gauche,
        distinct de la sélection. La bascule ne change pas l'empreinte du graphe,
        donc `refresh` ne re-projetterait pas : on ne fait que déplacer le liseré
        sur les cartes déjà en scène."""
        self._active_name = name
        for n, card in self._cards.items():
            card.set_active(n == name)

    def highlight_scenes(self, names) -> None:
        """Sélectionne les cartes de ces scènes — appelé quand la sélection vient
        du project viewer. Ne réémet pas (`_syncing`)."""
        wanted = set(names)
        self._syncing = True
        try:
            for name, card in self._cards.items():
                card.setSelected(name in wanted)
        finally:
            self._syncing = False

    # ── Groupes (dossiers de la famille scenes, partagés) ─────────────

    def _show_context_menu(self, global_pos, item) -> None:
        """Clic-droit, action ou menu selon le contexte de l'item sous le curseur :
        - une arête → bascule immédiate droite / courbe ;
        - une carte de scène → « Supprimer la scène » ;
        - une boîte/cadre de groupe (ou son chevron) → « Supprimer le groupe » ;
        - le vide → « Créer une scène ici » et « Créer un groupe » des scènes
          sélectionnées.
        Le groupe est un dossier de la famille — le même objet que côté viewer."""
        if isinstance(item, SceneGraphEdgeItem):
            self._toggle_edge_style(item)
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        if isinstance(item, SceneCardItem):
            menu.addAction(label("scncanvas.graph_edit_scene"),
                           lambda name=item.name: self.scene_opened.emit(name))
            # Désigner le point de départ du JEU — toujours présent (découvrable),
            # mais grisé sur la scène qui l'est DÉJÀ : la désigner elle-même ne
            # ferait rien.
            start = getattr(getattr(self._project, "settings", None), "start_scene", "")
            act_start = menu.addAction(label("scncanvas.graph_set_start"),
                                       lambda name=item.name: self._set_start_scene(name))
            act_start.setEnabled(item.name != start)
            menu.addSeparator()
            menu.addAction(label("common.delete"),
                           lambda name=item.name: self._delete_scene(name))
        elif isinstance(item, (SceneGroupBoxItem, GroupToggleItem)):
            if self._folders is None:
                return
            # Deux suppressions DISTINCTES : le dossier seul (contenu remonté) ou
            # le dossier ET son contenu (scènes du sous-arbre supprimées).
            menu.addAction(label("scttree.delete_folder"),
                           lambda gid=item.group_id: self._delete_group(gid))
            menu.addAction(label("scncanvas.graph_delete_folder_content"),
                           lambda gid=item.group_id: self._delete_group_deep(gid))
        elif isinstance(item, (SceneGraphNoteItem, NoteToggleItem)):
            menu.addAction(label("common.delete"), lambda nid=item.note_id: self._delete_note(nid))
        else:
            # Le vide : créer une scène au point cliqué (toujours), et — si les
            # dossiers sont partagés — ranger la sélection dans un nouveau groupe.
            menu.addAction(label("scncanvas.graph_create_scene"),
                           lambda: self._request_create_scene(global_pos))
            menu.addAction(label("scncanvas.graph_create_note"),
                           lambda: self._create_note_at(global_pos))
            if self._folders is not None:
                menu.addAction(label("assetfind.create_group"), self._group_selected_scenes)
        if not menu.isEmpty():
            menu.exec(global_pos)

    def _request_create_scene(self, global_pos) -> None:
        """Traduit le clic-droit dans le vide en coordonnées du graphe et demande
        à la fenêtre de créer la scène : la carte naîtra centrée sous le curseur
        (cf. `place_new_scene`)."""
        view_pos = self._view.mapFromGlobal(global_pos)
        pt = self._view.mapToScene(view_pos)
        self.scene_create_requested.emit(pt.x() - CARD_W / 2, pt.y() - CARD_H / 2)

    def _create_note_at(self, global_pos) -> None:
        if self._state is None:
            return
        pt = self._view.mapToScene(self._view.mapFromGlobal(global_pos))
        note_id = uuid4().hex
        if self._state.create_note(note_id, pt.x(), pt.y()) and self._graph is not None:
            self._render(self._graph)
            note = self._notes.get(note_id)
            if note is not None:
                note.setSelected(True)
                self.note_selected.emit(note_id)

    def _delete_note(self, note_id: str) -> None:
        if self._state is not None and self._state.delete_note(note_id) and self._graph is not None:
            self._render(self._graph)

    def _toggle_note(self, note_id: str) -> None:
        if self._state is not None:
            note = self._state.notes().get(note_id, {})
            self._state.update_note(note_id, collapsed=not bool(note.get("collapsed", False)))
            if self._graph is not None:
                self._render(self._graph)

    def _set_notes_visible(self, visible: bool) -> None:
        self._notes_visible = visible
        if self._graph is not None:
            self._render(self._graph)

    def place_new_scene(self, name: str, x: float, y: float) -> None:
        """Pose une scène fraîchement créée à (x, y) et la rattache au niveau
        ouvert. Appelée par la fenêtre APRÈS la création (l'ajout a déjà re-projeté
        via `project_tree_changed`) : on écrit sa position et son appartenance, puis
        on redessine et on la sélectionne. `refresh` ne suffirait pas — l'empreinte
        n'a pas changé depuis la re-projection de la création."""
        if self._state is not None:
            self._state.set_scene_position(name, x, y)
        if self._folders is not None and self._level is not None:
            self._folders.move_member("scenes", name, self._level)
        if self._graph is not None:
            self._render(self._graph)
        scene = self._scene_by_name(name)
        if scene is not None:
            get_bus().select(scene)

    def _toggle_edge_style(self, item: SceneGraphEdgeItem) -> None:
        """Clic droit direct : droite ↔ courbe pour CETTE transition seulement.

        Annulable (Ctrl+Z) comme l'édition depuis l'inspecteur : la même commande
        persiste le tracé et la vue le reflète, sans écriture directe du sidecar.
        """
        edge = getattr(item, "edge", None)
        if edge is None or self._state is None:
            return
        # « auto » est visuellement droit dans la majorité des cas : le premier
        # clic va donc naturellement vers la courbe. Le clic suivant la redresse.
        style = "straight" if item.style == "curve" else "curve"
        before = [self._state.edge_style(edge.source, edge.target)]
        item.setSelected(True)
        get_history().push(EdgePresentationCmd(
            self._state, [edge], "style", before, [style],
            lambda edges, _field: self.refresh_edge_presentation(list(edges))))

    def refresh_edge_presentation(self, edge) -> None:
        """Applique immédiatement depuis l'inspecteur le tracé mémorisé."""
        edges = list(edge) if isinstance(edge, (list, tuple)) else [edge]
        for item in self._scene.items():
            if isinstance(item, SceneGraphEdgeItem) and getattr(item, "edge", None) in edges:
                current = item.edge
                style = self._state.edge_style(current.source, current.target) if self._state else "auto"
                item.set_style(style)

    def _set_start_scene(self, name: str) -> None:
        """Désigne `name` comme scène de départ du JEU (annulable, Ctrl+Z), via la
        même commande que l'inspecteur de projet (`ProjectSettings.start_scene`).
        `start_scene` entre dans l'empreinte du graphe : le `refresh` re-projette,
        et la pastille de départ comme le diagnostic d'entrée suivent."""
        if self._project is None:
            return
        old = getattr(self._project.settings, "start_scene", None)
        if old == name:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, "start_scene", old, name,
            label="Projet.start_scene", persist_fn=self._persist_start_scene))

    def _persist_start_scene(self) -> None:
        """Sauvegarde les réglages et redessine — appelé à l'exécution ET à l'undo
        de la commande, pour que le graphe reflète toujours le point de départ réel."""
        if self._project is not None:
            self._project.save_settings()
        self.refresh()

    def _delete_scene(self, name: str) -> None:
        """Supprime une scène (annulable, Ctrl+Z) après confirmation — même
        commande que le project viewer, poussée dans l'historique partagé."""
        from ui.common.asset_kinds import SCENES
        scene = self._scene_by_name(name)
        if scene is None:
            return
        if QMessageBox.question(
            self, label("common.delete"),
            label("akind.delete_scene_name_ctrl_z_to_undo", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        get_history().push(SCENES.delete(self._project, scene))
        self.refresh()            # une scène en moins change l'empreinte

    def _delete_group(self, group_id: str) -> None:
        """Supprime un groupe (dossier). Ses scènes et sous-groupes ne sont pas
        détruits : ils remontent au parent (cf. `AssetFolderStore.delete_folder`)."""
        if self._folders is None:
            return
        # Parent lu AVANT la suppression : après, le dossier n'existe plus.
        if self._level == group_id:
            self._level = self._parent_of(group_id)   # le niveau ouvert a disparu
        self._folders.delete_folder("scenes", group_id)
        if self._graph is not None:
            self._render(self._graph)
        self.groups_changed.emit()

    def _scenes_in_subtree(self, group_id: str) -> list:
        """Les scènes rangées dans `group_id` ou l'un de ses sous-dossiers."""
        subtree = {group_id} | self._group_descendants(group_id)
        return [s for s in getattr(self._project, "scenes", ()) or ()
                if (self._folders.folder_of("scenes", s.name) if self._folders else None)
                in subtree]

    def _delete_group_deep(self, group_id: str) -> None:
        """Supprime un dossier ET son contenu : les scènes de tout son sous-arbre
        (suppression annulable par scène, Ctrl+Z), puis la structure de dossiers.
        Distinct de `_delete_group`, qui préserve le contenu. Le retrait des
        dossiers du sidecar n'est pas annulable (cf. chantier undo des sidecars) ;
        les scènes, elles, le sont — d'où la confirmation avant le geste."""
        if self._folders is None:
            return
        from ui.common.asset_kinds import SCENES
        scenes = self._scenes_in_subtree(group_id)
        if QMessageBox.question(
            self, label("common.delete"),
            label("scncanvas.graph_delete_folder_content_confirm", count=len(scenes)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        if self._level == group_id or group_id in self._ancestor_ids(
                self._level, {f.id: f for f in self._folders.folders("scenes")}):
            self._level = self._parent_of(group_id)   # le niveau ouvert disparaît
        for scene in scenes:
            get_history().push(SCENES.delete(self._project, scene))
        self._folders.delete_folder_tree("scenes", group_id)
        self.refresh()                 # des scènes en moins changent l'empreinte
        self.groups_changed.emit()

    def _delete_selection(self) -> None:
        """Retour arrière / Suppr : supprime les éléments SÉLECTIONNÉS — cartes de
        scènes et boîtes de groupes repliées —, chacun SEUL (une scène est
        supprimée ; un dossier voit son contenu remonter, comme `_delete_group`).
        Sans sélection, le geste retombe sur « remonter d'un niveau » (Backspace
        historique). Une seule confirmation résume le lot."""
        from ui.common.asset_kinds import SCENES
        cards = [i for i in self._scene.selectedItems() if isinstance(i, SceneCardItem)]
        boxes = [i for i in self._scene.selectedItems() if isinstance(i, SceneGroupBoxItem)]
        notes = [i for i in self._scene.selectedItems() if isinstance(i, SceneGraphNoteItem)]
        if not cards and not boxes and not notes:
            self._ascend()             # rien de sélectionné → comportement d'origine
            return
        if QMessageBox.question(
            self, label("common.delete"),
            label("scncanvas.graph_delete_selection_confirm",
                  scenes=len(cards), folders=len(boxes)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for card in cards:
            scene = self._scene_by_name(card.name)
            if scene is not None:
                get_history().push(SCENES.delete(self._project, scene))
        if self._folders is not None:
            for box in boxes:
                if self._level == box.group_id:
                    self._level = self._parent_of(box.group_id)
                self._folders.delete_folder("scenes", box.group_id)
        if self._state is not None:
            for note in notes:
                self._state.delete_note(note.note_id)
        self.refresh()
        if boxes:
            self.groups_changed.emit()

    def _group_selected_scenes(self) -> None:
        """Range les scènes sélectionnées dans un nouveau groupe, au NIVEAU
        ouvert (leur parent devient le groupe courant). Sans sélection, le groupe
        naît vide — il n'apparaît au graphe qu'une fois peuplé, mais existe dans
        le project viewer."""
        if self._folders is None:
            return
        names = [i.name for i in self._scene.selectedItems()
                 if isinstance(i, SceneCardItem)]
        self._folders.create_group(
            "scenes", label("assetfind.group_default_name"), names, self._level)
        if self._graph is not None:
            self._render(self._graph)
        self.groups_changed.emit()

    def reload_groups(self) -> None:
        """Redessine après un changement de dossiers venu d'ailleurs (project
        viewer) : l'empreinte des scripts n'a pas bougé, mais l'appartenance des
        scènes oui, donc `refresh` seul ne re-projetterait pas."""
        if self._graph is not None:
            self._render(self._graph)

    def _toggle_group(self, group_id: str) -> None:
        """Replie/déplie une boîte de groupe sur place et redessine."""
        if self._state is None or self._graph is None:
            return
        self._state.set_group_collapsed(group_id, not self._state.group_collapsed(group_id))
        self._render(self._graph)

    def _on_double_click(self, item) -> None:
        if isinstance(item, GroupToggleItem):
            return  # le chevron a déjà basculé le repli au press ; pas de descente
        if isinstance(item, SceneGroupBoxItem):
            self._descend(item.group_id)
        elif isinstance(item, SceneCardItem):
            self.scene_opened.emit(item.name)
        elif isinstance(item, SceneGraphEdgeItem):
            self.edge_opened.emit(item.edge)

    # ── Niveaux (descente / remontée) ─────────────────────────────────

    def _descend(self, group_id: str) -> None:
        if self._graph is None:
            return
        self._level = group_id
        self._render(self._graph)

    def _descend_selected(self) -> None:
        """Flèche droite : entrer dans le groupe sélectionné — même geste que le
        double-clic sur sa boîte. N'agit que si UN SEUL groupe est sélectionné
        (une cible unique) ; sinon il n'y a rien où descendre sans ambiguïté."""
        boxes = [i for i in self._scene.selectedItems()
                 if isinstance(i, SceneGroupBoxItem)]
        if len(boxes) == 1:
            self._descend(boxes[0].group_id)

    def _ascend(self) -> None:
        """Flèche gauche (et repli du Backspace sans sélection) : remonter au
        groupe parent (rien à la racine)."""
        if self._level is None or self._graph is None:
            return
        self._level = self._parent_of(self._level)
        self._render(self._graph)

    def _go_to_level(self, level_id) -> None:
        if self._graph is None:
            return
        self._level = level_id
        self._render(self._graph)

    def _parent_of(self, group_id: str | None) -> str | None:
        if group_id is None or self._folders is None:
            return None
        for f in self._folders.folders("scenes"):
            if f.id == group_id:
                return f.parent_id
        return None

    def _root_label(self) -> str:
        """Nom de la racine du fil d'Ariane : le NOM DU PROJET, qui fait office de
        « toutes les scènes ». Repli sur le libellé générique si le projet n'a pas
        de nom exploitable (tests isolés)."""
        name = getattr(getattr(self._project, "settings", None), "name", "")
        return name or label("scncanvas.graph_root")

    def _breadcrumb_path(self) -> list[tuple]:
        """Maillons racine→niveau courant : [(None, <nom du projet>), (gid, nom)…]."""
        crumbs: list[tuple] = [(None, self._root_label())]
        if self._folders is None or self._level is None:
            return crumbs
        infos = {f.id: f for f in self._folders.folders("scenes")}
        chain: list[tuple] = []
        gid = self._level
        seen: set[str] = set()
        while gid and gid in infos and gid not in seen:
            seen.add(gid)
            chain.append((gid, infos[gid].name))
            gid = infos[gid].parent_id
        crumbs.extend(reversed(chain))
        return crumbs

    @property
    def graph(self) -> SceneGraph | None:
        """Dernière projection rendue, ou `None` avant tout affichage."""
        return self._graph

    def set_project(self, project, state: SceneGraphState | None = None,
                    folder_store=None) -> None:
        """Attache le projet SANS projeter : le calcul attend l'affichage.

        `state` (positions/présentation du graphe) et `folder_store` (dossiers
        d'assets, dont les groupes de scènes) sont possédés par la fenêtre et
        PARTAGÉS avec le project viewer — deux instances du même fichier se
        désynchroniseraient. Absents (tests isolés), la vue crée `state` elle-même
        et se passe de groupes. Les orphelins sont purgés, puis l'empreinte est
        invalidée pour que le prochain `refresh` re-projette.
        """
        self._project = project
        self._folders = folder_store
        self._level = None              # tout nouveau projet s'ouvre à la racine
        self._preview_cache.clear()     # les vignettes du projet précédent n'ont plus cours
        root = getattr(project, "root", None)
        if state is not None:
            self._state = state
        elif root is not None:
            self._state = SceneGraphState(root)
        else:
            self._state = None
        if self._state is not None:
            names = {s.name for s in getattr(project, "scenes", ()) or ()}
            gids = ({f.id for f in folder_store.folders("scenes")}
                    if folder_store is not None else None)
            self._state.prune(names, gids)
        self._fingerprint = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        """Re-projette si l'empreinte a changé, puis redessine.

        Idempotent à empreinte constante : un simple ré-affichage ne re-parse
        aucun script et conserve le même objet `SceneGraph`.
        """
        if self._project is None:
            return
        fingerprint = _fingerprint(self._project)
        if fingerprint == self._fingerprint and self._graph is not None:
            return
        self._fingerprint = fingerprint
        self._graph = scene_graph(self._project)
        self._render(self._graph)

    # ── Positions : graine auto puis mémorisation ─────────────────────

    def _node_positions(self, graph: SceneGraph) -> dict[str, tuple[float, float]]:
        """Position de chaque scène : le sidecar s'il la connaît, sinon l'auto-
        layout — aussitôt écrit, pour que chaque nœud ait dès le départ une place
        stockée (stabilité plutôt que réactivité)."""
        seed = layout_positions(graph)
        out: dict[str, tuple[float, float]] = {}
        materialize: dict[str, tuple[float, float]] = {}
        for node in graph.nodes:
            stored = self._state.scene_position(node.name) if self._state else None
            if stored is None:
                stored = seed.get(node.name, (0.0, 0.0))
                materialize[node.name] = stored
            out[node.name] = stored
        for name, pos in materialize.items():
            if self._state is not None:
                self._state.set_scene_position(name, pos[0], pos[1])
        # Les cibles introuvables ne sont jamais mémorisées : place volatile
        # dérivée de l'auto-layout, à droite de leur source.
        for name, pos in seed.items():
            out.setdefault(name, pos)
        return out

    def _persist_moves(self) -> None:
        """Écrit la position des cartes, des boîtes repliées et des cadres dépliés
        qui ont bougé, recalcule l'appartenance des cartes déplacées (dans un
        cadre → membre ; hors de tout cadre → hors groupe), puis redessine. Les
        arêtes ont déjà suivi visuellement pendant le geste. Appelé à la fin d'un
        clic gauche."""
        if self._state is None:
            return
        moved = False
        moved_cards: list[str] = []
        moved_groups: list[str] = []
        for name, card in self._cards.items():
            p = card.pos()
            if self._state.scene_position(name) != (p.x(), p.y()):
                self._state.set_scene_position(name, p.x(), p.y())
                moved = True
                moved_cards.append(name)
        for name, marker in self._missing.items():
            p = marker.pos()
            if self._state.missing_position(name) != (p.x(), p.y()):
                self._state.set_missing_position(name, p.x(), p.y())
                moved = True
        for gid, box in self._boxes.items():
            p = box.pos()
            if self._state.group_box_position(gid) != (p.x(), p.y()):
                self._state.set_group_box_position(gid, p.x(), p.y())
                moved = True
                moved_groups.append(gid)
        for gid, frame in self._frames.items():
            p = frame.pos()
            geo = (p.x(), p.y(), frame._w, frame._h)
            old = self._state.group_frame(gid)
            if old != geo:
                self._state.set_group_frame(gid, *geo)
                moved = True
                # Un cadre change de groupe parent seulement s'il s'est DÉPLACÉ :
                # un simple redimensionnement (bords) ne le fait pas fuir de son
                # groupe. `old` peut être None (première pose) → traité comme un
                # déplacement, l'appartenance se calera sur sa position.
                if old is None or (old[0], old[1]) != (p.x(), p.y()):
                    moved_groups.append(gid)
        for note_id, note in self._notes.items():
            p = note.pos()
            if self._state.note_position(note_id) != (p.x(), p.y()):
                self._state.set_note_position(note_id, p.x(), p.y())
                moved = True
        # L'appartenance des cartes ET des groupes déplacés se recalcule au même
        # geste : un groupe glissé DANS un autre s'y imbrique, glissé au-dehors
        # en ressort (mêmes règles que les cartes, cf. `_recompute_membership`).
        if self._recompute_membership(moved_cards) | self._recompute_group_membership(moved_groups):
            moved = True
            self.groups_changed.emit()   # le project viewer partage le store
        if moved and self._graph is not None:
            self._render(self._graph)

    def _item_geometry_changed(self, item) -> None:
        """Rafraîchit uniquement les liens attachés à l'item qui bouge.

        Aucun rendu de scène, auto-layout ou écriture disque ici : cette voie est
        appelée à chaque pixel du drag et doit rester strictement visuelle.
        """
        for edge in self._edge_bindings.get(item, ()):
            edge.refresh_geometry()

    def _add_live_edge(self, source_item, target_item, count: int, edge) -> None:
        style = (self._state.edge_style(edge.source, edge.target)
                 if self._state is not None else "auto")
        item = SceneGraphEdgeItem(source_item.anchor_rect(), target_item.anchor_rect(), count,
                                  style=style, rewire_requested=self._retarget_edges)
        item.edge = edge
        item.setZValue(-1)
        item.bind_anchors(source_item, target_item)
        self._scene.addItem(item)
        for endpoint in {source_item, target_item}:
            self._edge_bindings.setdefault(endpoint, []).append(item)

    def _retarget_edges(self, items, target) -> None:
        """Reconnecte en une commande toutes les arêtes saisies sur un port."""
        if not isinstance(target, SceneCardItem):
            return
        edges = [getattr(item, "edge", None) for item in items]
        edges = [edge for edge in edges if edge is not None and edge.target != target.name]
        if not edges:
            return
        grouped = {}
        for edge in edges:
            for ref in edge.refs:
                grouped.setdefault(ref.path, []).append(ref)
        changes = []
        for path, refs in grouped.items():
            try:
                before = path.read_text(encoding="utf-8")
            except OSError:
                continue
            after = before
            for ref in sorted(refs, key=lambda r: r.start, reverse=True):
                literal = after[ref.start:ref.stop + 1]
                quote = literal[:1]
                value = target.name.replace("\\", "\\\\").replace(quote, "\\" + quote)
                after = after[:ref.start] + quote + value + quote + after[ref.stop + 1:]
            if after != before:
                changes.append((path, before, after))
        if changes:
            get_history().push(_RewriteEdgeCmd(
                changes, lambda index: self._refresh_retargeted_edges(
                    [(edge.source, edge.target) for edge in edges] if index == 0
                    else [(edge.source, target.name) for edge in edges])))

    def _refresh_retargeted_edges(self, pairs) -> None:
        self.refresh()
        if self._graph is not None:
            wanted = set(pairs)
            updated = [edge for edge in self._graph.edges
                       if (edge.source, edge.target) in wanted]
            if updated:
                for item in self._scene.items():
                    if (isinstance(item, SceneGraphEdgeItem)
                            and getattr(item, "edge", None) in updated):
                        item.setSelected(True)
                self.edge_selected.emit(updated)

    def _recompute_membership(self, moved_cards: list[str]) -> bool:
        """Range chaque carte DÉPLACÉE dans le groupe dont le cadre/boîte la
        contient, ou hors de tout groupe (au niveau courant) sinon. N'agit que sur
        ce qui a bougé : redimensionner un cadre ne fait pas fuir ses membres, seul
        un glisser de carte change l'appartenance. Rend True si quelque chose a
        changé dans le store."""
        if self._folders is None or not moved_cards:
            return False
        changed = False
        for name in moved_cards:
            card = self._cards.get(name)
            if card is None:
                continue
            target = self._group_at(card.anchor_rect().center())
            if self._folders.folder_of("scenes", name) != target:
                self._folders.move_member("scenes", name, target)
                changed = True
        return changed

    def _recompute_group_membership(self, moved_groups: list[str]) -> bool:
        """Range chaque GROUPE déplacé sous le groupe dont le cadre/boîte le
        contient, ou hors de tout groupe (au niveau courant) sinon — le pendant
        de `_recompute_membership` pour les cartes. Un groupe glissé dans un
        autre s'y imbrique ; glissé au-dehors, il en ressort.

        Exclusions : le groupe lui-même et ses DESCENDANTS ne peuvent pas
        l'accueillir (un groupe ne se range pas en lui-même) — `set_parent`
        refuse le cycle de toute façon, mais les exclure évite de viser un
        conteneur qui serait refusé alors qu'un conteneur valide, plus grand,
        contient aussi le point."""
        if self._folders is None or not moved_groups:
            return False
        changed = False
        boxes = {**self._boxes, **self._frames}
        for gid in moved_groups:
            item = boxes.get(gid)
            if item is None:
                continue
            excluded = {gid} | self._group_descendants(gid)
            target = self._group_at(item.anchor_rect().center(), exclude=excluded)
            if self._folders.set_parent("scenes", gid, target):
                changed = True
        return changed

    def _group_descendants(self, gid: str) -> set[str]:
        """Ids des groupes dont `gid` est un ancêtre (à tout niveau)."""
        if self._folders is None:
            return set()
        children: dict[str | None, list[str]] = {}
        for f in self._folders.folders("scenes"):
            children.setdefault(f.parent_id, []).append(f.id)
        out: set[str] = set()
        stack = list(children.get(gid, []))
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            stack.extend(children.get(cur, []))
        return out

    def _group_at(self, point, exclude: set[str] | None = None) -> str | None:
        """Groupe (dossier) dont la boîte/cadre du niveau courant contient `point`
        — le plus petit en cas de recouvrement. `exclude` retire des candidats
        (un groupe déplacé ne s'accueille pas lui-même). Aucun → le niveau courant
        lui-même (racine None = hors de tout groupe ; sous-niveau L = membre
        direct de L)."""
        exclude = exclude or set()
        best, best_area = None, None
        for gid, box in {**self._boxes, **self._frames}.items():
            if gid in exclude:
                continue
            rect = box.anchor_rect()
            if rect.contains(point):
                area = rect.width() * rect.height()
                if best_area is None or area < best_area:
                    best, best_area = gid, area
        return best if best is not None else self._level

    def _rearrange(self) -> None:
        """Relance l'auto-layout complet et écrase toutes les positions."""
        if self._graph is None or self._state is None:
            return
        seed = layout_positions(self._graph)
        self._state.replace_scene_positions(
            {node.name: seed.get(node.name, (0.0, 0.0)) for node in self._graph.nodes})
        self._render(self._graph)

    # ── Mode de rendu des nœuds : condensé / aperçu du fond ─────────────

    def _toggle_scene_preview(self, name: str) -> None:
        """Clic sur la pastille d'un nœud : (dé)active l'aperçu du fond de CETTE
        scène. La vignette est reconstruite à l'activation (le fond a pu changer),
        puis mise en cache — un déplacement de nœud ne la recalcule pas."""
        if self._state is None:
            return
        self._state.set_scene_preview(name, not self._state.scene_preview(name))
        self._preview_cache.pop(name, None)   # vignette fraîche au prochain rendu
        if self._graph is not None:
            self._render(self._graph)

    def _preview_for(self, name: str) -> QPixmap | None:
        """Vignette d'une scène, mémoïsée (None seulement si la scène est
        introuvable ; sans fond, la vignette est la couleur de backdrop)."""
        if name not in self._preview_cache:
            scene = self._scene_by_name(name)
            self._preview_cache[name] = (
                self._scene_preview(scene) if scene is not None else None)
        return self._preview_cache[name]

    def _backdrop_rgb(self, scene) -> tuple[int, int, int]:
        """Couleur de backdrop EFFECTIVE de la scène (index 0 de PAL_BG_RAM) :
        l'override de la scène, sinon le défaut du projet — même résolution que le
        canvas (`scene_canvas`). C'est ce que le matériel affiche là où rien n'est
        dessiné."""
        raw = getattr(scene, "backdrop_color", None)
        if raw is None:
            raw = getattr(getattr(self._project, "settings", None), "backdrop_color", 0)
        from core.models.gba_color import bgr555_to_rgb888
        return bgr555_to_rgb888(int(raw or 0) & 0x7FFF)

    def _scene_preview(self, scene) -> QPixmap | None:
        """Compose l'écran 240×160 de la scène : la couleur de backdrop en base,
        puis les FONDS par-dessus, du calque le plus au fond (slot 3) au plus
        devant (slot 0). Acteurs et interface sont volontairement absents — c'est
        un repère de décor. Sans aucun fond, la vignette est le backdrop seul (ce
        que le matériel montrerait) ; jamais None pour une scène existante."""
        layers = [L for L in getattr(scene, "background_layers", []) or ()
                  if getattr(L, "background_name", "")]
        canvas = QImage(GBA_W, GBA_H, QImage.Format.Format_RGBA8888)
        canvas.fill(QColor(*self._backdrop_rgb(scene)))
        painter = QPainter(canvas)
        try:
            for layer in sorted(layers, key=lambda L: -getattr(L, "bg_slot", 0)):
                try:
                    ap = layer_png_path(self._project, layer)
                    pm = bg_pixmap(self._project, scene, layer, ap)
                except Exception:
                    pm = None
                if pm is not None and not pm.isNull():
                    painter.drawPixmap(0, 0, pm)   # calé en haut-gauche, rogné à l'écran
        finally:
            painter.end()
        return QPixmap.fromImage(canvas)

    # ── Niveau courant : répartition des scènes ────────────────────────

    def _folder_chain(self, name: str, fmap: dict) -> list[str]:
        """Dossiers de la scène `name`, du plus proche (son dossier direct) à la
        racine — la chaîne d'appartenance."""
        fid = self._folders.folder_of("scenes", name) if self._folders else None
        chain: list[str] = []
        cur, seen = fid, set()
        while cur and cur in fmap and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = fmap[cur].parent_id
        return chain

    def _shown_groups(self, fmap: dict, level: str | None) -> dict[str, dict]:
        """Groupes VISIBLES au niveau `level` : ses enfants directs, puis — en
        descendant SEULEMENT par les groupes dépliés — leurs enfants, récursivement.
        Un groupe replié est montré (comme boîte) mais ses descendants ne le sont
        pas. Chaque entrée porte son état replié et sa profondeur (pour le z)."""
        shown: dict[str, dict] = {}
        children: dict[str | None, list] = {}
        for f in fmap.values():
            children.setdefault(f.parent_id, []).append(f)

        def collapsed(gid: str) -> bool:
            return self._state.group_collapsed(gid) if self._state else True

        def walk(parent: str | None, depth: int) -> None:
            for f in children.get(parent, []):
                col = collapsed(f.id)
                # Les anciennes couleurs de dossiers ne teintent plus le graphe.
                shown[f.id] = {"name": f.name, "color": "",
                               "collapsed": col, "parent": f.parent_id, "depth": depth}
                if not col:
                    walk(f.id, depth + 1)

        walk(level, 0)
        return shown

    def _place_scene(self, name: str, fmap: dict, level: str | None,
                     shown: dict) -> tuple[str, str | None]:
        """Où rendre une scène : `("card", gid|None)` (carte, dans le groupe `gid`
        ou directement au niveau), `("box", gid)` (cachée dans la boîte du groupe
        replié `gid`) ou `("out", None)` (hors du sous-arbre du niveau — un lien
        vers elle sortira par une porte de frontière)."""
        chain = self._folder_chain(name, fmap)
        if level is None:
            below = chain                       # tout, jusqu'à la racine
        elif level not in chain:
            return ("out", None)                # pas dans le sous-arbre du niveau
        else:
            below = chain[:chain.index(level)]  # entre la scène et le niveau
        if not below:
            return ("card", None)               # membre direct du niveau
        # Le groupe replié le PLUS HAUT (le plus proche du niveau) la cache.
        for gid in reversed(below):
            if gid not in shown:
                return ("out", None)            # un ancêtre replié plus haut la cache déjà
            if shown[gid]["collapsed"]:
                return ("box", gid)
        return ("card", below[0])               # tout déplié → carte dans son groupe direct

    # ── Rendu ─────────────────────────────────────────────────────────

    def _render(self, graph: SceneGraph) -> None:
        """Dessine le NIVEAU courant : scènes directes et sous-groupes (boîte
        repliée / cadre déplié). Les transitions qui franchissent le bord du
        niveau deviennent des portes de frontière ; celles vers un membre d'une
        boîte repliée s'y raccordent."""
        # Le clear()/addItem d'un rendu fait varier la sélection Qt ; on ne veut
        # pas que ce bruit remonte comme une sélection croisée.
        self._syncing = True
        try:
            self._render_body(graph)
        finally:
            self._syncing = False

    def _render_body(self, graph: SceneGraph) -> None:
        self._scene.clear()
        self._cards = {}
        self._boxes = {}
        self._frames = {}
        self._name_box = {}
        self._missing = {}
        self._notes = {}
        self._edge_bindings = {}
        pos = self._node_positions(graph)
        node_names = {node.name for node in graph.nodes}
        fmap = {f.id: f for f in self._folders.folders("scenes")} if self._folders else {}
        if self._level is not None and self._level not in fmap:
            self._level = None          # le groupe ouvert a disparu → racine
        level = self._level

        notes_by_name = {s.name: getattr(s, "notes", "")
                         for s in getattr(self._project, "scenes", ()) or ()}
        # Rendu du SOUS-ARBRE du niveau courant, en descendant par les groupes
        # DÉPLIÉS : un cadre déplié montre ses sous-groupes à l'intérieur (comme
        # ses cartes), pour qu'imbriquer ET sortir un groupe soient tous deux des
        # glissers. `shown` = groupes visibles ; `place` = où va chaque scène.
        shown = self._shown_groups(fmap, level)
        place = {name: self._place_scene(name, fmap, level, shown) for name in node_names}
        card_names = {n for n, (kind, _c) in place.items() if kind == "card"}

        # Diagnostics (atteignabilité, cul-de-sac, cible calculée/cassée) : dérivés
        # de la projection, sans re-parser un script — les ports des cartes les
        # rendent en lecture seule.
        diag = node_diagnostics(graph)
        for node in graph.nodes:
            if node.name in card_names:
                enabled = self._state.scene_preview(node.name) if self._state else False
                preview = self._preview_for(node.name) if enabled else None
                card = SceneCardItem(node.name, node.is_start,
                                     preview_enabled=enabled, preview=preview,
                                     is_active=node.name == self._active_name,
                                     notes=notes_by_name.get(node.name, ""),
                                     diagnostic=diag.get(node.name),
                                     geometry_changed=self._item_geometry_changed)
                card.setPos(*pos[node.name])
                self._scene.addItem(card)
                self._cards[node.name] = card

        # Cibles introuvables : marqueurs de la RACINE seulement (au sein d'un
        # niveau, un lien vers un nom sans scène sort par une porte de sortie).
        missing: dict[str, MissingTargetItem] = {}
        if level is None:
            missing_names = {edge.target for edge in graph.edges if edge.target not in node_names}
            if self._state is not None:
                self._state.prune_missing_positions(missing_names)
            for edge in graph.edges:
                if edge.target in node_names or edge.target in missing:
                    continue
                marker = MissingTargetItem(edge.target, geometry_changed=self._item_geometry_changed)
                marker_pos = (self._state.missing_position(edge.target) if self._state else None)
                marker.setPos(*(marker_pos or pos[edge.target]))
                self._scene.addItem(marker)
                missing[edge.target] = marker
                self._missing[edge.target] = marker

        self._render_groups(shown, place, pos, node_names)
        if self._notes_visible and self._state is not None:
            for note_id, note in self._state.notes().items():
                item = SceneGraphNoteItem(note_id, note.get("title", "Note"),
                                          note.get("text", ""), note.get("color", ""),
                                          bool(note.get("collapsed", False)),
                                          geometry_changed=self._item_geometry_changed)
                item.setPos(*(self._state.note_position(note_id) or (0.0, 0.0)))
                item.setZValue(2)
                self._scene.addItem(item)
                self._notes[note_id] = item

        def anchor(name):
            """(rect, clé, interne?, item) — interne = visible à ce niveau."""
            if name in self._cards:
                item = self._cards[name]
                return item.anchor_rect(), f"card:{name}", True, item
            if name in self._name_box:
                box = self._name_box[name]
                return box.anchor_rect(), f"box:{box.group_id}", True, box
            if name in missing:
                item = missing[name]
                return item.anchor_rect(), f"missing:{name}", True, item
            return None, None, False, None

        # Arêtes traversant le bord du niveau : on retient l'ancre INTERNE (le
        # nœud visible) pour la relier ensuite à sa porte de frontière.
        entry_links: list[tuple] = []   # (edge, rect du nœud cible interne)
        exit_links: list[tuple] = []    # (edge, rect du nœud source interne)
        for edge in graph.edges:
            source, skey, s_in, source_item = anchor(edge.source)
            target, tkey, t_in, target_item = anchor(edge.target)
            if s_in and t_in:
                if skey == tkey and skey.startswith("box:"):
                    continue            # lien interne à une boîte repliée
                self._add_live_edge(source_item, target_item, len(edge.refs), edge)
            elif s_in and not t_in:
                exit_links.append((edge, source_item))   # sort du niveau
            elif t_in and not s_in:
                entry_links.append((edge, target_item))  # entre dans le niveau

        self._render_doors(entry_links, exit_links)
        self._breadcrumb.set_path(self._breadcrumb_path())

        content = self._scene.itemsBoundingRect()
        self._scene.setSceneRect(content.adjusted(-_PAN_MARGIN, -_PAN_MARGIN,
                                                  _PAN_MARGIN, _PAN_MARGIN))
        self._update_minimap()

    def _render_doors(self, entry_links: list, exit_links: list) -> None:
        """Portes de frontière — entrées à gauche du contenu, sorties à droite —
        ET les liens qui les relient au nœud interne concerné : une flèche part
        de la porte d'entrée vers chaque cible interne, et de chaque source
        interne vers la porte de sortie. Sans ces traits, les portes flottaient
        sans dire QUEL nœud franchit le bord."""
        if not entry_links and not exit_links:
            return
        content = self._scene.itemsBoundingRect()
        top = content.top()
        if entry_links:
            door = BoundaryDoorItem(True, len(entry_links))
            door.setPos(content.left() - DOOR_W - 40, top)
            door.setZValue(-1)
            self._scene.addItem(door)
            self._link_doors(door, entry_links, incoming=True)
        if exit_links:
            door = BoundaryDoorItem(False, len(exit_links))
            door.setPos(content.right() + 40, top)
            door.setZValue(-1)
            self._scene.addItem(door)
            self._link_doors(door, exit_links, incoming=False)

    def _link_doors(self, door, links: list, incoming: bool) -> None:
        """Trace une arête entre la porte et chaque nœud interne. Entrée : de la
        porte vers la cible ; sortie : de la source vers la porte. Cliquable comme
        une arête interne (elle ouvre le même appel `scene.switch`)."""
        for edge, node_item in links:
            source, target = (door, node_item) if incoming else (node_item, door)
            self._add_live_edge(source, target, len(edge.refs), edge)

    def _ancestor_ids(self, gid: str | None, fmap: dict) -> set[str]:
        """Ids des dossiers ancêtres STRICTS de `gid`."""
        out: set[str] = set()
        cur = fmap[gid].parent_id if gid in fmap else None
        while cur and cur in fmap and cur not in out:
            out.add(cur)
            cur = fmap[cur].parent_id
        return out

    def _render_groups(self, shown: dict, place: dict, pos: dict,
                       node_names: set) -> None:
        """Dessine chaque groupe visible : boîte condensée (replié) ou cadre
        englobant (déplié). Un cadre déplié encadre ses cartes ET ses sous-groupes ;
        le déplacer par l'en-tête emporte tout son sous-arbre. Boîtes d'abord
        (positions prêtes), puis cadres du PLUS PROFOND au plus haut (un cadre
        parent doit lire la géométrie de ses cadres enfants pour s'amorcer)."""
        fmap = {f.id: f for f in self._folders.folders("scenes")} if self._folders else {}
        direct_count = {gid: sum(1 for n in node_names
                                 if (self._folders.folder_of("scenes", n) if self._folders else None) == gid)
                        for gid in shown}
        # Scènes cachées par chaque boîte repliée (pour ancrer leurs arêtes).
        boxed: dict[str, list[str]] = {}
        for name, (kind, gid) in place.items():
            if kind == "box":
                boxed.setdefault(gid, []).append(name)

        # ── Boîtes (groupes repliés) ──────────────────────────────────
        for gid, g in shown.items():
            if not g["collapsed"]:
                continue
            box_pos = self._state.group_box_position(gid) if self._state else None
            if box_pos is None:
                members = boxed.get(gid, [])
                box_pos = ((min(pos[m][0] for m in members),
                            min(pos[m][1] for m in members)) if members else (0.0, 0.0))
                if self._state is not None:
                    self._state.set_group_box_position(gid, *box_pos)
            box = SceneGroupBoxItem(gid, g["name"], direct_count[gid], True,
                                    COLLAPSED_W, COLLAPSED_H, g["color"],
                                    geometry_changed=self._item_geometry_changed)
            box.setPos(*box_pos)
            box.setZValue(0)
            self._scene.addItem(box)
            self._boxes[gid] = box
            for name in boxed.get(gid, []):
                self._name_box[name] = box

        # ── Cadres (groupes dépliés), du plus profond au plus haut ────
        card_of = self._cards
        for gid in sorted((g for g, m in shown.items() if not m["collapsed"]),
                          key=lambda g: -shown[g]["depth"]):
            g = shown[gid]
            frame_geo = self._state.group_frame(gid) if self._state else None
            if frame_geo is None:
                # Amorce sur ce qu'il encadre : cartes membres directes + boîtes/
                # cadres enfants directs déjà posés.
                rects = [card_of[n].anchor_rect() for n, (k, c) in place.items()
                         if k == "card" and c == gid and n in card_of]
                rects += [it.anchor_rect() for cg, it in {**self._boxes, **self._frames}.items()
                          if fmap.get(cg) is not None and fmap[cg].parent_id == gid]
                if rects:
                    left = min(r.left() for r in rects) - _GROUP_PAD
                    right = max(r.right() for r in rects) + _GROUP_PAD
                    bottom = max(r.bottom() for r in rects) + _GROUP_PAD
                    top = min(r.top() for r in rects) - _GROUP_PAD - HEADER_H
                    frame_geo = (left, top, right - left, bottom - top)
                else:
                    frame_geo = (0.0, 0.0, 160.0, HEADER_H + 40.0)
                if self._state is not None:
                    self._state.set_group_frame(gid, *frame_geo)
            fx, fy, fw, fh = frame_geo
            frame = SceneGroupBoxItem(gid, g["name"], direct_count[gid], False,
                                      fw, fh, g["color"],
                                      geometry_changed=self._item_geometry_changed)
            frame.setPos(fx, fy)
            # Derrière les cartes (z 0) ; un cadre plus profond passe DEVANT le
            # cadre parent (son fond), sans jamais masquer les cartes.
            frame.setZValue(-10.0 + g["depth"])
            self._scene.addItem(frame)
            self._frames[gid] = frame

        # ── Emporter tout le sous-arbre quand on déplace un cadre ─────
        # (fait après coup : tous les items existent, cartes et groupes.)
        for gid, frame in self._frames.items():
            sub = [it for n, it in card_of.items()
                   if (fid := (self._folders.folder_of("scenes", n) if self._folders else None))
                   and (fid == gid or gid in self._ancestor_ids(fid, fmap))]
            sub += [it for cg, it in {**self._boxes, **self._frames}.items()
                    if cg != gid and gid in self._ancestor_ids(cg, fmap)]
            frame.member_items = sub
