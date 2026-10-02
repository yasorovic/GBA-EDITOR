"""
ui/sound_mixer/music_graph.py — Le graphe de la MusicBox.

La MusicBox est la SEULE des trois boîtes à avoir des arêtes (ROADMAP
v0.8.7) : elle seule est continue, donc elle seule a des transitions. C'est
aussi la seule où un graphe dit quelque chose qu'une liste ne dit pas — quel
état mène à quel autre, et par quel déclencheur. Les emplacements (SoundBox,
JingleBox) restent des tables : ils n'ont pas d'arêtes.

Le graphe ne règle rien. Un nœud se déplace, se sélectionne et se relie ; la
piste, la boucle, le niveau, l'intensité et les transitions sortantes se
règlent dans l'inspecteur de droite — comme un actor dans le Scene Manager.

Les positions des nœuds sont de la DONNÉE (`MusicState.x/y`), rangée avec
l'état. Une disposition recalculée à chaque ouverture effacerait le travail de
l'auteur à chaque fois.
"""
from __future__ import annotations

from ui.common.labels import label
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPainterPath, QPainterPathStroker, QPen, QBrush, QColor,
    QPolygonF, QTransform,
)
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem

from core.history import get_history, AddListItemCmd, RemoveListItemCmd, SetFieldCmd
from ui.common.theme import C, T, ui_font
from ui.common.shortcut_hints import ShortcutHints
from ui.sound_mixer.music_graph_hints import music_graph_hints
from ui.sound_mixer.sound_commands import (
    MoveMusicNodesCmd, AddBoxStateCmd, RemoveMusicStateCmd,
)
from core.models.resource import MIME_MUSIC
from core.models.sound_box import (
    MusicBox, MusicState, MusicTransition, TRANSITION_CUT,
)

# Géométrie du nœud, en pixels de scène.
NODE_W, NODE_H = 180, 108
_HEADER_H = 26
_ROW_H = 18
_PORT_R = 5.0

# Écart d'une disposition automatique. Assez large pour qu'une étiquette de
# déclencheur tienne entre deux colonnes sans chevaucher un nœud.
_COL_STEP, _ROW_STEP = 260, 150

# Rayon de la poignée qu'on attrape au bout d'un fil sélectionné, et la marge
# d'accroche autour — un disque de 5 px ne se vise pas à la souris.
_GRIP_R, _GRIP_HIT = 5.0, 10.0


def _wire(p1: QPointF, p2: QPointF) -> QPainterPath:
    """La courbe d'un fil, tangente horizontale aux deux bouts.

    Partagée par l'arête posée et le fil qu'on tire : deux tracés différents
    donneraient à la souris une autre forme que celle qu'on relâche.
    """
    dx = max(60.0, abs(p2.x() - p1.x()) * 0.5)
    path = QPainterPath(p1)
    path.cubicTo(p1 + QPointF(dx, 0), p2 - QPointF(dx, 0), p2)
    return path


# ══════════════════════════════════════════════════════════════════
#  Le nœud — un état musical
# ══════════════════════════════════════════════════════════════════

class _StateNode(QGraphicsItem):
    """Ce qui joue dans cet état, lisible sans ouvrir l'inspecteur.

    Le nœud n'a aucun champ de saisie : il en faudrait un par réglage, donc un
    nœud dont la taille dépend de son contenu, et un graphe qu'on ne peut plus
    lire d'un coup d'œil.
    """

    def __init__(self, state: MusicState, is_start: bool):
        super().__init__()
        self.state = state
        self.is_start = is_start
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(float(state.x), float(state.y))

    # ── Géométrie ─────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        # La marge tient le liseré de sélection (2 px) et le port de sortie.
        return QRectF(-3, -3, NODE_W + _PORT_R + 6, NODE_H + 6)

    def port_scene_pos(self) -> QPointF:
        """Le point d'où part une arête — bord droit, hauteur de l'en-tête."""
        return self.pos() + QPointF(NODE_W, _HEADER_H / 2)

    def entry_scene_pos(self) -> QPointF:
        """Le point où une arête arrive — bord gauche, hauteur de l'en-tête."""
        return self.pos() + QPointF(0, _HEADER_H / 2)

    def port_contains(self, scene_pos: QPointF) -> bool:
        d = scene_pos - self.port_scene_pos()
        return (d.x() * d.x() + d.y() * d.y()) <= (_PORT_R + 4) ** 2

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.state.x = int(round(self.pos().x()))
            self.state.y = int(round(self.pos().y()))
            # `setPos` du constructeur passe ici AVANT que le nœud soit dans
            # une scène : pas de vue à prévenir, et rien à recalculer.
            sc = self.scene()
            view = sc.views()[0] if sc is not None and sc.views() else None
            if isinstance(view, MusicGraphView):
                view.node_moved()
        return super().itemChange(change, value)

    # ── Peinture ──────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sel = self.isSelected()

        body = QPainterPath()
        body.addRoundedRect(QRectF(0, 0, NODE_W, NODE_H), 7, 7)
        painter.fillPath(body, QColor(C.BG_RAISED))

        header = QPainterPath()
        header.addRoundedRect(QRectF(0, 0, NODE_W, _HEADER_H), 7, 7)
        header.addRect(QRectF(0, _HEADER_H - 7, NODE_W, 7))
        painter.fillPath(header, QColor(C.BG_SEL if sel else C.BG_INPUT))

        painter.setPen(QPen(QColor(C.SEL_BORDER if sel else C.BORDER),
                            2 if sel else 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body)

        # Pastille de l'état de DÉPART. C'est le seul fait du modèle qu'un nœud
        # porte à lui seul : le reste est du réglage, et se lit à droite.
        painter.setPen(QPen(QColor(C.ACCENT if self.is_start else C.BORDER_MID), 1))
        painter.setBrush(QBrush(QColor(C.ACCENT)) if self.is_start
                         else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(13, _HEADER_H / 2), 4, 4)

        painter.setFont(ui_font(T.MD, bold=True))
        painter.setPen(QColor(C.TEXT_HI if sel else C.TEXT_NORM))
        painter.drawText(QRectF(24, 0, NODE_W - 34, _HEADER_H),
                         int(Qt.AlignmentFlag.AlignVCenter),
                         self._elided(painter, self.state.name, NODE_W - 34))

        # Port de sortie — la poignée de câblage.
        painter.setPen(QPen(QColor(C.BORDER_MID), 1))
        painter.setBrush(QBrush(QColor(C.BG_PANEL)))
        painter.drawEllipse(QPointF(NODE_W, _HEADER_H / 2), _PORT_R, _PORT_R)

        st = self.state
        y = _HEADER_H + 4
        painter.setFont(ui_font(T.SM))
        painter.setPen(QColor(C.TEXT_NORM if st.music else C.TEXT_MUTED))
        painter.drawText(QRectF(12, y, NODE_W - 24, _ROW_H),
                         int(Qt.AlignmentFlag.AlignVCenter),
                         self._elided(painter, f"♪  {st.music or label('musgraph.silence')}",
                                      NODE_W - 24))

        y += _ROW_H
        painter.setPen(QColor(C.TEXT_DIM))
        painter.drawText(QRectF(12, y, NODE_W - 24, _ROW_H),
                         int(Qt.AlignmentFlag.AlignVCenter),
                         label('musgraph.loop') if st.loop else label('musgraph.once'))

        y += _ROW_H
        self._meter(painter, y, label('musgraph.level'), st.level, 100, C.ACCENT)
        y += _ROW_H
        self._meter(painter, y, st.intensity_target, st.intensity, 200,
                    C.ACCENT_COOL)

    def _meter(self, painter: QPainter, y: float, label: str,
               value: int, full: int, color: str):
        """Un réglage continu : son nom, sa jauge, sa valeur."""
        painter.setFont(ui_font(T.XS))
        painter.setPen(QColor(C.TEXT_DIM))
        painter.drawText(QRectF(12, y, 52, _ROW_H),
                         int(Qt.AlignmentFlag.AlignVCenter), label)

        x0, x1 = 68.0, NODE_W - 46.0
        track = QRectF(x0, y + _ROW_H / 2 - 2, x1 - x0, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(C.BORDER)))
        painter.drawRoundedRect(track, 2, 2)
        ratio = max(0.0, min(1.0, value / float(full)))
        if ratio > 0:
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRoundedRect(
                QRectF(track.x(), track.y(), track.width() * ratio, track.height()),
                2, 2)

        painter.setFont(ui_font(T.XS, family=T.MONO))
        painter.setPen(QColor(C.TEXT_NORM))
        painter.drawText(QRectF(NODE_W - 44, y, 34, _ROW_H),
                         int(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter), f"{value}%")

    @staticmethod
    def _elided(painter: QPainter, text: str, width: float) -> str:
        return painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, int(width))


# ══════════════════════════════════════════════════════════════════
#  L'arête — une transition
# ══════════════════════════════════════════════════════════════════

class _TransitionEdge(QGraphicsItem):
    """Une arête, et ce qui la déclenche.

    `src` à None = « depuis n'importe quel état » : l'arête n'a pas d'origine
    dans le graphe, elle entre donc par un moignon. Lui inventer un nœud
    d'origine ferait croire à un état qui n'existe pas.
    """

    def __init__(self, tr: MusicTransition,
                 src: Optional[_StateNode], dst: _StateNode):
        super().__init__()
        self.tr, self.src, self.dst = tr, src, dst
        self.setZValue(-1)
        # Sélectionnable : c'est ce qui permet de couper le fil là où on le
        # voit, au lieu d'aller le chercher dans une liste.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._path = QPainterPath()
        self._label = QRectF()
        self.recompute()

    def recompute(self):
        self.prepareGeometryChange()
        self.p2 = self.dst.entry_scene_pos() - QPointF(9, 0)
        self.p1 = (self.src.port_scene_pos() if self.src is not None
                   else self.p2 - QPointF(54, 0))
        self._path = _wire(self.p1, self.p2)
        mid = self._path.pointAtPercent(0.5)
        self._label = QRectF(mid.x() - 60, mid.y() - 20, 120, 15)

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().united(self._label).adjusted(-8, -8, 8, 8)

    def grip_at(self, scene_pos: QPointF) -> str:
        """Quelle extrémité est sous le curseur : "src", "dst" ou "".

        Seulement quand le fil est sélectionné : sinon chaque bout de chaque
        arête volerait les clics du nœud qu'il touche.
        """
        if not self.isSelected():
            return ""
        for name, pt in (("dst", self.p2), ("src", self.p1)):
            d = scene_pos - pt
            if d.x() * d.x() + d.y() * d.y() <= _GRIP_HIT ** 2:
                return name
        return ""

    def shape(self) -> QPainterPath:
        """Zone cliquable : le trait épaissi, plus son étiquette.

        Un trait d'un pixel et demi ne s'attrape pas à la souris ; et
        l'étiquette du déclencheur est ce qu'on vise naturellement.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        hit = stroker.createStroke(self._path)
        hit.addRect(self._label)
        return hit

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        picked = self.isSelected()
        lit = picked or self.dst.isSelected() or (
            self.src is not None and self.src.isSelected())
        color = QColor(C.SEL_BORDER if picked else
                       (C.ACCENT if lit else C.BORDER_MID))
        # Trait plein = fondu traversant, tireté = coupe à la position. Les deux
        # seules transitions que le matériel tient (v0.8.3).
        pen = QPen(color, 2.6 if picked else (2.0 if lit else 1.4))
        pen.setStyle(Qt.PenStyle.DashLine if self.tr.kind == TRANSITION_CUT
                     else Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

        end = self._path.pointAtPercent(1.0)
        head = QPolygonF([end, end + QPointF(-8, -4), end + QPointF(-8, 4)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(head)

        painter.setFont(ui_font(T.XS))
        text = self.tr.trigger or label('musgraph.no_trigger')
        w = painter.fontMetrics().horizontalAdvance(text) + 12
        chip = QRectF(self._label.center().x() - w / 2, self._label.y(),
                      w, self._label.height())
        painter.setBrush(QBrush(QColor(C.BG_BASE)))
        painter.drawRoundedRect(chip, 4, 4)
        painter.setPen(QColor(C.TEXT_NORM if self.tr.trigger else C.ACCENT_YLW))
        painter.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), text)

        # Les deux bouts ne s'attrapent QUE sélectionnés : c'est ce qui les
        # rend visibles et empêche un fil au repos de gêner ses voisins.
        if picked:
            painter.setPen(QPen(QColor(C.SEL_BORDER), 2))
            painter.setBrush(QBrush(QColor(C.BG_PANEL)))
            for pt in (self.p1, self.p2):
                painter.drawEllipse(pt, _GRIP_R, _GRIP_R)


# ══════════════════════════════════════════════════════════════════
#  La vue
# ══════════════════════════════════════════════════════════════════

class MusicGraphView(QGraphicsView):
    """Le panneau central : nœuds déplaçables, arêtes câblables."""

    # L'état sélectionné, ou None — c'est ce que l'inspecteur de droite suit.
    selected = pyqtSignal(object)
    # Le modèle a changé : à sauvegarder.
    changed = pyqtSignal()
    # Niveau de zoom, en pourcent — la molette zoome aussi, la barre d'outils
    # doit donc l'apprendre au lieu de le supposer.
    zoomed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph: Optional[MusicBox] = None
        self._nodes: dict[str, _StateNode] = {}
        self._edges: list[_TransitionEdge] = []
        self._zoom = 1.0
        self._dragged = False          # un nœud a bougé depuis le dernier press
        self._link_src: Optional[_StateNode] = None
        self._link_path = None
        # Le bout de fil qu'on est en train de décrocher : (arête, "src"|"dst").
        self._grip: Optional[tuple] = None
        self._panning = False
        self._pan_last: Optional[QPointF] = None
        # Positions des nœuds au début d'un glisser — la commande a besoin de
        # l'AVANT, que Qt a déjà écrasé quand on relâche.
        self._move_from: list = []

        scene = QGraphicsScene(self)
        scene.setSceneRect(-2000, -2000, 4000, 4000)
        scene.selectionChanged.connect(self._on_selection)
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(C.BG_BASE))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAcceptDrops(True)
        # Table des raccourcis (bas-droite, repliée au repos).
        self._hints = ShortcutHints(self, music_graph_hints)

    # ── Fond quadrillé ────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)
        step = 32
        painter.setPen(QPen(QColor(C.BORDER_DARK), 0))
        x = int(rect.left()) - int(rect.left()) % step
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = int(rect.top()) - int(rect.top()) % step
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    # ── Chargement ────────────────────────────────────────────────

    @property
    def graph(self) -> Optional[MusicBox]:
        return self._graph

    def load(self, box: MusicBox):
        self._graph = box
        # Un graphe encore jamais disposé (import, ou boîte créée avant que les
        # positions n'existent) : on le range une fois, l'auteur garde la main
        # ensuite.
        if box.states and all(s.x == 0 and s.y == 0 for s in box.states):
            self._arrange(box)
        self.rebuild()

    def rebuild(self):
        """Reconstruit nœuds et arêtes depuis le modèle."""
        node = self.current_node()
        keep_state = node.state if node is not None else None
        edge = self.current_edge()
        keep_tr = edge.tr if edge is not None else None
        sc = self.scene()
        sc.blockSignals(True)
        sc.clear()
        self._nodes.clear()
        self._edges.clear()
        self._link_src, self._link_path, self._grip = None, None, None
        g = self._graph
        if g is not None:
            for st in g.states:
                node = _StateNode(st, st.name == g.start)
                sc.addItem(node)
                self._nodes[st.name] = node
            for tr in g.transitions:
                dst = self._nodes.get(tr.dst)
                if dst is None:
                    continue        # arête vers un état supprimé : rien à dessiner
                src = self._nodes.get(tr.src) if tr.src else None
                if tr.src and src is None:
                    continue
                edge = _TransitionEdge(tr, src, dst)
                sc.addItem(edge)
                self._edges.append(edge)
        sc.blockSignals(False)
        # Par IDENTITÉ, pas par nom : une reconstruction déclenchée par un
        # renommage ne doit pas perdre la sélection en cherchant l'ancien nom.
        # Vaut aussi pour l'arête, qu'on vient peut-être de rebrancher.
        for n in self._nodes.values():
            if n.state is keep_state:
                n.setSelected(True)
                break
        for ed in self._edges:
            if ed.tr is keep_tr:
                ed.setSelected(True)
                break
        self._on_selection()

    def _arrange(self, g: MusicBox):
        """Disposition en colonnes par distance à l'état de départ.

        Un parcours en largeur suit les arêtes : la lecture gauche→droite d'un
        graphe rangé ainsi est celle de la partie qui se joue.
        """
        order = [s.name for s in g.states]
        depth = {n: 0 for n in order}
        seen = set()
        frontier = [g.start] if g.start in depth else order[:1]
        seen.update(frontier)
        d = 0
        while frontier:
            nxt = []
            for name in frontier:
                depth[name] = d
                for tr in g.transitions:
                    if tr.src == name and tr.dst in depth and tr.dst not in seen:
                        seen.add(tr.dst)
                        nxt.append(tr.dst)
            frontier, d = nxt, d + 1
        for name in order:                     # inatteignables : dernière colonne
            if name not in seen:
                depth[name] = d
        rows: dict[int, int] = {}
        for st in g.states:
            col = depth[st.name]
            row = rows.get(col, 0)
            rows[col] = row + 1
            st.x, st.y = col * _COL_STEP, row * _ROW_STEP

    def auto_layout(self):
        g = self._graph
        if g is None or not g.states:
            return
        before = [(s, (s.x, s.y)) for s in g.states]
        self._arrange(g)
        moves = [(s, old, (s.x, s.y)) for s, old in before if old != (s.x, s.y)]
        if not moves:
            return
        # Déjà appliqué par _arrange : on ENREGISTRE sans réexécuter, sinon la
        # disposition serait calculée deux fois.
        for state, old, _new in moves:
            state.x, state.y = old
        cmd = MoveMusicNodesCmd(moves, self._after_edit)
        cmd.label = "Auto-disposer"
        get_history().push(cmd)

    # ── Sélection ─────────────────────────────────────────────────

    def current_name(self) -> str:
        node = self.current_node()
        return node.state.name if node else ""

    def current_node(self) -> Optional[_StateNode]:
        for it in self.scene().selectedItems():
            if isinstance(it, _StateNode):
                return it
        return None

    def current_edge(self) -> Optional[_TransitionEdge]:
        for it in self.scene().selectedItems():
            if isinstance(it, _TransitionEdge):
                return it
        return None

    def select_state(self, name: str):
        self.scene().clearSelection()
        node = self._nodes.get(name)
        if node is not None:
            node.setSelected(True)
            self.centerOn(node)

    def _on_selection(self):
        for e in self._edges:
            e.update()
        node = self.current_node()
        if node is None:
            # Une arête sélectionnée montre l'état qui la POSSÈDE : son bloc
            # est alors sous les yeux, dans l'inspecteur, prêt à être réglé.
            edge = self.current_edge()
            if edge is not None:
                node = edge.src or edge.dst
        self.selected.emit(node.state if node else None)

    def node_moved(self):
        """Appelé par un nœud qui vient de bouger."""
        self._dragged = True
        for e in self._edges:
            e.recompute()

    def _after_edit(self):
        """Ce qui suit toute écriture — qu'elle vienne d'un geste ou d'un undo.

        Les commandes le reçoivent comme `persist_fn` : elles ne connaissent
        donc ni la vue ni le projet, et l'annulation repasse exactement par le
        même chemin que le geste. `rebuild()` relit les positions depuis le
        modèle, ce qui replace aussi les nœuds après un Ctrl+Z.
        """
        self.rebuild()
        self.changed.emit()

    # ── Édition ───────────────────────────────────────────────────

    def add_state(self) -> Optional[MusicState]:
        """Crée un état au centre de la vue, nommé automatiquement.

        Pas de pop-up de saisie : le nom se corrige dans l'inspecteur, qui
        prend le focus juste après.
        """
        g = self._graph
        if g is None:
            return None
        from core.command_dispatcher import unique_name
        # L'espace de noms est celui de CETTE boîte : une SoundBox peut
        # porter le même nom d'état sans que rien ne devienne ambigu.
        taken = [s.name for s in g.states]
        center = self.mapToScene(self.viewport().rect().center())
        x, y = int(center.x() - NODE_W / 2), int(center.y() - NODE_H / 2)
        # Décaler tant que la place est prise : un nœud posé pile sur un autre
        # se laisse sélectionner mais ne se voit pas.
        while any(abs(s.x - x) < 24 and abs(s.y - y) < 24 for s in g.states):
            x, y = x + 28, y + 28
        st = MusicState(name=unique_name("state", taken), x=x, y=y)
        get_history().push(AddBoxStateCmd(g, st, self._after_edit))
        self.select_state(st.name)
        return st

    def delete_selected(self):
        g = self._graph
        if g is None:
            return
        edge = self.current_edge()
        if edge is not None:
            if edge.tr in g.transitions:
                get_history().push(RemoveListItemCmd(
                    g.transitions, edge.tr, self._after_edit,
                    label="Supprimer une transition"))
            return
        node = self.current_node()
        if node is None:
            return
        # Composée : l'état, ses arêtes et son statut de départ partent
        # ensemble, donc reviennent ensemble (cf. sound_commands.py).
        get_history().push(RemoveMusicStateCmd(g, node.state, self._after_edit))

    def _drop(self, edge: "_TransitionEdge", which: str,
              target: Optional[_StateNode]):
        """Ce que devient un bout de fil lâché — et les deux bouts diffèrent.

        La DESTINATION est obligatoire : une transition qui ne mène nulle part
        n'est pas une transition, la lâcher dans le vide la supprime. L'ORIGINE
        est facultative — « depuis n'importe quel état » est un cas courant,
        donc la lâcher dans le vide rend l'arête globale au lieu de la couper.
        """
        g = self._graph
        if g is None or edge.tr not in g.transitions:
            return
        tr = edge.tr
        if which == "dst" and target is None:
            get_history().push(RemoveListItemCmd(
                g.transitions, tr, self._after_edit,
                label="Décrocher une transition"))
            return
        attr = "dst" if which == "dst" else "src"
        new = target.state.name if target is not None else ""
        if getattr(tr, attr) == new:
            self._after_edit()
            return
        get_history().push(SetFieldCmd(
            tr, attr, getattr(tr, attr), new,
            "Rebrancher une transition", self._after_edit))

    def _link(self, src: _StateNode, dst: _StateNode):
        """Relie deux nœuds — le déclencheur est nommé automatiquement.

        Le vocabulaire des déclencheurs appartient au graphe : c'est lui qui
        les déclare, et le checker refuse un `sound.trigger()` qui n'y figure
        pas. Un nom auto est donc un nom valide tout de suite, à renommer.
        """
        g = self._graph
        if g is None:
            return
        from core.command_dispatcher import unique_name
        taken = [t.trigger for t in g.transitions if t.trigger]
        tr = MusicTransition(src=src.state.name, dst=dst.state.name,
                             trigger=unique_name("trigger", taken))
        get_history().push(AddListItemCmd(
            g.transitions, tr, self._after_edit, label="Ajouter une transition"))
        self.select_state(src.state.name)

    # ── Dépôt d'une musique venue du finder ───────────────────────

    def dragEnterEvent(self, e):
        if self._graph is not None and e.mimeData().hasFormat(MIME_MUSIC):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._graph is not None and e.mimeData().hasFormat(MIME_MUSIC):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dragLeaveEvent(self, e):
        e.accept()      # supprime l'avertissement Qt « drag leave before enter »

    def dropEvent(self, e):
        """Une piste lâchée sur un nœud le RÈGLE ; sur le vide, elle CRÉE.

        Deux gestes et pas un : viser un nœud, c'est dire « celui-ci joue
        ça » ; viser le vide, c'est dire « il manque un état pour ça ». Un
        seul des deux obligerait à créer puis régler, ou à régler puis
        déplacer.
        """
        g = self._graph
        if g is None or not e.mimeData().hasFormat(MIME_MUSIC):
            super().dropEvent(e)
            return
        name = bytes(e.mimeData().data(MIME_MUSIC)).decode("utf-8")
        pos = e.position().toPoint()
        node = self._node_at(pos)
        if node is not None:
            if node.state.music != name:
                get_history().push(SetFieldCmd(
                    node.state, "music", node.state.music, name,
                    f"Piste de {node.state.name}", self._after_edit))
            self.select_state(node.state.name)
        else:
            from core.command_dispatcher import unique_name
            scene_pos = self.mapToScene(pos)
            st = MusicState(
                name=unique_name(name, [s.name for s in g.states]),
                music=name,
                x=int(scene_pos.x() - NODE_W / 2),
                y=int(scene_pos.y() - NODE_H / 2))
            get_history().push(AddBoxStateCmd(g, st, self._after_edit))
            self.select_state(st.name)
        e.acceptProposedAction()

    # ── Souris ────────────────────────────────────────────────────

    def _node_at(self, view_pos) -> Optional[_StateNode]:
        for it in self.items(view_pos):
            if isinstance(it, _StateNode):
                return it
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragged = False
            scene_pos = self.mapToScene(e.position().toPoint())
            edge = self.current_edge()
            grip = edge.grip_at(scene_pos) if edge is not None else ""
            if grip:
                # Le fil décroché suit la souris ; l'arête posée s'efface le
                # temps du geste pour ne pas en dessiner deux.
                self._grip = (edge, grip)
                edge.setVisible(False)
                self._link_path = self.scene().addPath(
                    QPainterPath(), QPen(QColor(C.ACCENT), 1.6,
                                         Qt.PenStyle.DashLine))
                self._link_path.setZValue(10)
                e.accept()
                return
            node = self._node_at(e.position().toPoint())
            if node is not None and node.port_contains(
                    self.mapToScene(e.position().toPoint())):
                self._link_src = node
                self._link_path = self.scene().addPath(
                    QPainterPath(), QPen(QColor(C.ACCENT), 1.6,
                                         Qt.PenStyle.DashLine))
                self._link_path.setZValue(10)
                e.accept()
                return
        super().mousePressEvent(e)
        # APRÈS Qt : c'est ce clic qui vient peut-être de changer la sélection,
        # et le glisser emportera tous les nœuds sélectionnés.
        if e.button() == Qt.MouseButton.LeftButton:
            self._move_from = [(it.state, (it.state.x, it.state.y))
                               for it in self.scene().selectedItems()
                               if isinstance(it, _StateNode)]

    def mouseMoveEvent(self, e):
        if self._panning and self._pan_last is not None:
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(d.y()))
            e.accept()
            return
        if self._grip is not None:
            edge, which = self._grip
            free = self.mapToScene(e.position().toPoint())
            # L'autre bout ne bouge pas : c'est lui qui donne le sens du fil.
            self._link_path.setPath(_wire(edge.p1, free) if which == "dst"
                                    else _wire(free, edge.p2))
            e.accept()
            return
        if self._link_src is not None:
            self._link_path.setPath(
                _wire(self._link_src.port_scene_pos(),
                      self.mapToScene(e.position().toPoint())))
            e.accept()
            return
        edge = self.current_edge()
        if edge is not None and edge.grip_at(
                self.mapToScene(e.position().toPoint())):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning, self._pan_last = False, None
            self.unsetCursor()
            e.accept()
            return
        if self._grip is not None:
            (edge, which), self._grip = self._grip, None
            self.scene().removeItem(self._link_path)
            self._link_path = None
            edge.setVisible(True)
            self._drop(edge, which, self._node_at(e.position().toPoint()))
            e.accept()
            return
        if self._link_src is not None:
            src, self._link_src = self._link_src, None
            self.scene().removeItem(self._link_path)
            self._link_path = None
            dst = self._node_at(e.position().toPoint())
            if dst is not None and dst is not src:
                self._link(src, dst)
            e.accept()
            return
        super().mouseReleaseEvent(e)
        if self._dragged:
            self._dragged = False
            moves = [(st, old, (st.x, st.y))
                     for st, old in self._move_from if old != (st.x, st.y)]
            self._move_from = []
            if moves:
                # Déjà déplacés par Qt : on remet les positions d'origine pour
                # que la commande les repose elle-même, une seule fois.
                for state, old, _new in moves:
                    state.x, state.y = old
                get_history().push(MoveMusicNodesCmd(moves, self._after_edit))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            e.accept()
            return
        super().keyPressEvent(e)

    # ── Zoom ──────────────────────────────────────────────────────

    def wheelEvent(self, e):
        self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)

    def zoom_by(self, factor: float):
        self._zoom = max(0.25, min(self._zoom * factor, 3.0))
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)
        self.zoomed.emit(self.zoom_percent())

    def zoom_percent(self) -> int:
        return int(round(self._zoom * 100))

    def fit(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-40, -40, 40, 40),
                       Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoomed.emit(self.zoom_percent())
