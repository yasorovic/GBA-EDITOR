"""ui/scene_manager/scene_graph_items.py — items peints du Graphe des scènes.

Trois formes, une par chose que la projection peut produire :

- `SceneCardItem` : une scène du projet (carte nommée, marquée si c'est le départ).
- `MissingTargetItem` : une cible ``scene:switch("X")`` dont aucune scène ne porte
  le nom. C'est un marqueur terminal d'erreur de liaison, JAMAIS un nœud : pas de
  départ possible, rien à ouvrir, rien à renommer. Un seul par nom manquant.
- `SceneGraphEdgeItem` : une transition dirigée d'une carte vers une carte ou un
  marqueur, avec un compteur quand plusieurs appels la portent, et une boucle
  quand elle revient sur sa source.

Les items ne lisent aucun modèle : la vue les construit à partir du `SceneGraph`
projeté et les place. Le placement précis (couches de dépendances) est l'étape 4 ;
ici chaque item sait seulement se dessiner et donner son ancrage.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from scripting.scene_graph import EntryState, ExitState, NodeDiagnostic
from ui.common.labels import label
from ui.common.notes_tooltip import notes_tooltip
from ui.common.theme import C, T, ui_font

CARD_W = 150.0
CARD_H = 46.0
_RADIUS = 8.0
_PEN = 2.0  # débord du trait le plus épais, pour le boundingRect
_ACTIVE_BAR_W = 4.0  # largeur du liseré « scène active » (bord gauche de la carte)

# Mode 2 (aperçu) : la carte s'agrandit pour porter une vignette du fond de la
# scène, sous un en-tête qui garde le nom. Ratio d'écran GBA (240×160 = 3:2).
PREVIEW_W = 176.0
PREVIEW_HEADER_H = 22.0
PREVIEW_IMG_H = round(PREVIEW_W * 160 / 240)          # 117
PREVIEW_H = PREVIEW_HEADER_H + PREVIEW_IMG_H
_PILL = 12.0   # diamètre de la pastille d'aperçu
_PILL_PAD = 7.0  # marge de la pastille au coin haut-droit de la carte
_PORT_R = 4.5  # rayon des points d'entrée/sortie, centrés sur le bord de la carte
_GRID_STEP = 20.0


class NodePortItem(QGraphicsItem):
    """Point d'entrée (gauche) ou de sortie (droite) d'un nœud — DIAGNOSTIC en
    lecture seule.

    La couleur dit l'état : lavande = cible(s) trouvée(s) / scène atteignable,
    jaune = cible calculée (point de vigilance), gris = cul-de-sac / scène
    inatteignable. Une cible introuvable n'est pas une pastille pleine mais une
    **croix rouge** : elle signale le problème sans le résoudre à la place de
    l'auteur. Le port ne capte aucun clic dans cette tranche (l'écriture depuis le
    graphe est la partie 4) ; il porte seulement sa couleur et son infobulle."""

    def __init__(self, color: str, cross: bool, tip: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._cross = cross
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setToolTip(tip)

    def boundingRect(self) -> QRectF:
        m = _PORT_R + _PEN
        return QRectF(-m, -m, 2 * m, 2 * m)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        if self._cross:
            painter.setPen(QPen(QColor(self._color), 2.0))
            r = _PORT_R
            painter.drawLine(QPointF(-r, -r), QPointF(r, r))
            painter.drawLine(QPointF(-r, r), QPointF(r, -r))
            return
        # Pastille pleine, cernée du fond profond pour la détacher du bord de carte.
        painter.setPen(QPen(QColor(C.BG_DEEP), 1.0))
        painter.setBrush(QBrush(QColor(self._color)))
        painter.drawEllipse(QPointF(0, 0), _PORT_R, _PORT_R)


def _entry_port(state: EntryState) -> NodePortItem:
    if state is EntryState.REACHABLE:
        return NodePortItem(C.ACCENT, False, label("scncanvas.graph_entry_reachable"))
    return NodePortItem(C.BORDER_MID, False, label("scncanvas.graph_entry_unreachable"))


def _exit_port(state: ExitState) -> NodePortItem:
    if state is ExitState.BROKEN:
        return NodePortItem(C.ACCENT_RED, True, label("scncanvas.graph_exit_broken"))
    if state is ExitState.DYNAMIC:
        return NodePortItem(C.ACCENT_YLW, False, label("scncanvas.graph_exit_dynamic"))
    if state is ExitState.LITERAL:
        return NodePortItem(C.ACCENT, False, label("scncanvas.graph_exit_literal"))
    return NodePortItem(C.BORDER_MID, False, label("scncanvas.graph_exit_none"))


class ScenePreviewToggleItem(QGraphicsItem):
    """Pastille ronde d'un nœud : bascule l'aperçu du fond de CETTE scène.

    Éteinte (aperçu désactivé) = anneau creux et sombre ; allumée = pleine et
    colorée. Le clic est capté par la vue (comme `GroupToggleItem`) : la pastille
    n'accepte aucun bouton et ne connaît aucun store — elle porte juste le nom de
    sa scène et son état."""

    def __init__(self, name: str, enabled: bool, parent=None):
        super().__init__(parent)
        self.name = name
        self._enabled = enabled
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # clic capté par la vue
        self.setToolTip(label("scncanvas.graph_preview_tip"))

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, _PILL, _PILL)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        disc = QRectF(1, 1, _PILL - 2, _PILL - 2)
        if self._enabled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C.ACCENT)))
        else:
            painter.setPen(QPen(QColor(C.BORDER_MID), 1.4))
            painter.setBrush(QBrush(QColor(C.BG_DEEP)))
        painter.drawEllipse(disc)


class SceneCardItem(QGraphicsItem):
    """Carte d'une scène.

    Deux rendus, choisis par la vue (mode global du Graphe) :

    - **condensé** (défaut) : la carte nommée, `is_start` marquée d'un liseré ;
    - **aperçu** (`preview` fournie) : une carte plus grande dont l'en-tête garde
      le nom et le corps montre une vignette des FONDS de la scène. Les acteurs et
      l'interface n'y figurent pas — c'est un repère de décor, pas une capture.

    L'item ne lit aucun modèle : la vue compose la vignette et la lui passe."""

    def __init__(self, name: str, is_start: bool = False,
                 preview_enabled: bool = False, preview: QPixmap | None = None,
                 is_active: bool = False, notes: str = "",
                 diagnostic: NodeDiagnostic | None = None,
                 geometry_changed=None):
        super().__init__()
        self.name = name
        self.is_start = is_start
        self.diagnostic = diagnostic
        # Note libre de l'auteur au survol (éditeur uniquement). La vue la lit du
        # modèle et la passe ; la carte ne connaît toujours aucun store. Vide →
        # pas de tooltip. La pastille d'aperçu (enfant) garde le sien.
        self.setToolTip(notes_tooltip(notes))
        # Scène ACTIVE (ouverte dans le canvas 2D) — liseré vertical à gauche,
        # distinct du liseré de sélection (bord accentué) et de la pastille de
        # départ. Même grammaire que le project viewer : barre gauche = active,
        # remplissage/bord = sélection (cf. project_ui_conventions).
        self.is_active = is_active
        self._preview_enabled = preview_enabled
        self._preview = preview           # peut être None même en aperçu (scène sans fond)
        # La TAILLE suit le choix de l'auteur (pastille), pas la présence d'une
        # image : une scène en aperçu mais sans fond montre un écran vide, elle
        # ne retombe pas en condensé.
        self._w = PREVIEW_W if preview_enabled else CARD_W
        self._h = PREVIEW_H if preview_enabled else CARD_H
        self._geometry_changed = geometry_changed
        # Un nœud se déplace et se sélectionne comme dans le canvas (RubberBand,
        # Ctrl/Shift). La position déplacée est persistée par la vue au
        # relâchement (sidecar d'éditeur, cf. SceneGraphState) ; l'item, lui, ne
        # connaît aucun store.
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        # Pastille de bascule d'aperçu, au coin haut-droit de la carte.
        pill = ScenePreviewToggleItem(name, preview_enabled, parent=self)
        pill.setPos(self._w - _PILL - _PILL_PAD, _PILL_PAD)
        pill.setZValue(1)
        # Points de diagnostic : entrée à gauche, sortie à droite, centrés sur le
        # bord et à mi-hauteur. Purement dérivés de la projection ; absents tant
        # qu'aucun diagnostic n'est fourni (tests isolés, cartes sans graphe).
        if diagnostic is not None:
            entry = _entry_port(diagnostic.entry)
            entry.setParentItem(self)
            entry.setPos(0, self._h / 2)
            entry.setZValue(1)
            out = _exit_port(diagnostic.exit)
            out.setParentItem(self)
            out.setPos(self._w, self._h / 2)
            out.setZValue(1)

    def boundingRect(self) -> QRectF:
        return QRectF(-_PEN, -_PEN, self._w + 2 * _PEN, self._h + 2 * _PEN)

    def anchor_rect(self) -> QRectF:
        """Rectangle de la carte en coordonnées de scène — pour tracer les arêtes."""
        return self.mapToScene(QRectF(0, 0, self._w, self._h)).boundingRect()

    def set_active(self, active: bool) -> None:
        """(Dé)marque la carte comme la scène active et repeint si ça change."""
        if self.is_active != active:
            self.is_active = active
            self.update()

    def itemChange(self, change, value):
        """Signale le déplacement sans connaître les arêtes de la vue.

        Les arêtes restent ainsi attachées pendant le glisser. Le callback ne
        persiste rien : l'écriture du sidecar reste groupée au relâchement.
        """
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._geometry_changed is not None):
            self._geometry_changed(self)
        return super().itemChange(change, value)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # Le geste garde l'impression d'un déplacement direct, mais la position
        # finale de chaque pas tombe sur la même trame que le fond du graphe.
        p = self.pos()
        snapped = QPointF(round(p.x() / _GRID_STEP) * _GRID_STEP,
                          round(p.y() / _GRID_STEP) * _GRID_STEP)
        if snapped != p:
            self.setPos(snapped)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        body = QRectF(0, 0, self._w, self._h)
        # Sélection = liseré accentué, prioritaire sur le liseré de départ pour
        # que la sélection reste lisible même sur la scène de départ.
        if self.isSelected():
            border = QColor(C.ACCENT)
            painter.setPen(QPen(border, 2.5))
        else:
            border = QColor(C.ACCENT if self.is_start else C.BORDER_MID)
            painter.setPen(QPen(border, 2.0 if self.is_start else 1.0))
        painter.setBrush(QBrush(QColor(C.BG_PANEL)))
        painter.drawRoundedRect(body, _RADIUS, _RADIUS)

        if self.is_active:
            # Liseré gauche « scène active », rogné au coin arrondi de la carte.
            clip = QPainterPath()
            clip.addRoundedRect(body, _RADIUS, _RADIUS)
            painter.save()
            painter.setClipPath(clip)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C.ACCENT)))
            painter.drawRect(QRectF(0, 0, _ACTIVE_BAR_W, self._h))
            painter.restore()

        if self._preview_enabled:
            self._paint_preview(painter)
            return

        if self.is_start:
            # Pastille de départ : dit « le jeu commence ici » sans texte en plus.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C.ACCENT)))
            painter.drawEllipse(QPointF(14, CARD_H / 2), 4.0, 4.0)

        painter.setPen(QPen(QColor(C.TEXT_HI)))
        painter.setFont(ui_font(T.MD, bold=self.is_start))
        # Le nom s'arrête avant la pastille (coin haut-droit) — pas de recouvrement.
        text = QRectF(24 if self.is_start else 12, 0, CARD_W - 32 - _PILL, CARD_H)
        painter.drawText(text, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.name)

    def _paint_preview(self, painter):
        """Mode aperçu : en-tête (pastille de départ + nom) puis la vignette du
        fond, sur un fond sombre façon écran éteint. Sans fond exploitable, l'écran
        reste vide — la scène a bien été mise en aperçu, il n'y a rien à montrer."""
        if self.is_start:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C.ACCENT)))
            painter.drawEllipse(QPointF(14, PREVIEW_HEADER_H / 2), 4.0, 4.0)
        painter.setPen(QPen(QColor(C.TEXT_HI)))
        painter.setFont(ui_font(T.MD, bold=self.is_start))
        header = QRectF(24 if self.is_start else 12, 0,
                        PREVIEW_W - 32 - _PILL, PREVIEW_HEADER_H)
        painter.drawText(header, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.name)

        img = QRectF(_PEN, PREVIEW_HEADER_H, PREVIEW_W - 2 * _PEN,
                     PREVIEW_IMG_H - _PEN)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(C.BG_DEEP)))
        painter.drawRect(img)
        if self._preview is not None:
            # La vignette du fond (240×160) épouse la zone (même ratio 3:2).
            painter.drawPixmap(img, self._preview, QRectF(self._preview.rect()))


class MissingTargetItem(QGraphicsItem):
    """Marqueur d'une cible introuvable — barré d'un ✕, en rouge, non éditable."""

    def __init__(self, name: str, geometry_changed=None):
        super().__init__()
        self.name = name
        self._geometry_changed = geometry_changed
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        # Une cible introuvable est terminale : seulement un port D'ENTRÉE,
        # sélectionnable via son parent pour reconnecter les arêtes fautives.
        entry = NodePortItem(C.ACCENT_RED, False,
                              label("edgeinsp.target_missing", target=name), parent=self)
        entry.setPos(0, CARD_H / 2)
        entry.setZValue(1)

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._geometry_changed is not None):
            self._geometry_changed(self)
        return super().itemChange(change, value)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        p = self.pos()
        snapped = QPointF(round(p.x() / _GRID_STEP) * _GRID_STEP,
                          round(p.y() / _GRID_STEP) * _GRID_STEP)
        if snapped != p:
            self.setPos(snapped)

    def boundingRect(self) -> QRectF:
        return QRectF(-_PEN, -_PEN, CARD_W + 2 * _PEN, CARD_H + 2 * _PEN)

    def anchor_rect(self) -> QRectF:
        return self.mapToScene(QRectF(0, 0, CARD_W, CARD_H)).boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        body = QRectF(0, 0, CARD_W, CARD_H)
        painter.setPen(QPen(QColor(C.ACCENT_RED), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(C.BG_PANEL)))
        painter.drawRoundedRect(body, _RADIUS, _RADIUS)

        # Le ✕ : la liaison pointe vers un nom qu'aucune scène ne porte.
        painter.setPen(QPen(QColor(C.ACCENT_RED), 2.0))
        cx, cy, r = 16.0, CARD_H / 2, 5.0
        painter.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
        painter.drawLine(QPointF(cx - r, cy + r), QPointF(cx + r, cy - r))

        painter.setPen(QPen(QColor(C.ACCENT_RED)))
        painter.setFont(ui_font(T.MD))
        text = QRectF(30, 0, CARD_W - 38, CARD_H)
        painter.drawText(text, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self.name)


def _port_anchors(source: QRectF, target: QRectF) -> tuple[QPointF, QPointF]:
    """Ancres sémantiques d'une transition : sortie droite → entrée gauche.

    Elles coïncident exactement avec les ports visibles d'une carte de scène.
    Pour les boîtes, marqueurs et portes (qui n'ont pas de pastille dessinée),
    cette même convention préserve une circulation de gauche à droite cohérente.
    """
    return (QPointF(source.right(), source.center().y()),
            QPointF(target.left(), target.center().y()))


def _arrow_head(tip: QPointF, direction: QPointF, size: float = 9.0) -> QPolygonF:
    """Triangle plein pointant vers `tip`, orienté par le vecteur `direction`."""
    length = math.hypot(direction.x(), direction.y()) or 1.0
    ux, uy = direction.x() / length, direction.y() / length
    px, py = -uy, ux  # perpendiculaire
    base = QPointF(tip.x() - ux * size, tip.y() - uy * size)
    half = size * 0.5
    return QPolygonF([
        tip,
        QPointF(base.x() + px * half, base.y() + py * half),
        QPointF(base.x() - px * half, base.y() - py * half),
    ])


class SceneGraphEdgeItem(QGraphicsItem):
    """Arête dirigée entre deux ancrages, avec compteur et boucle.

    Initialement construite avec deux rectangles en coordonnées de scène, elle
    peut aussi être liée à deux items : sa géométrie se rafraîchit alors pendant
    leur déplacement. Quand ils coïncident, l'arête se dessine en boucle au-
    dessus de la carte.
    """

    def __init__(self, source: QRectF, target: QRectF, count: int,
                 curved: bool = False, style: str = "auto", rewire_requested=None):
        super().__init__()
        self.count = count
        # Une arête est une cible d'inspection à part entière : Qt garde sa
        # sélection (clic, Ctrl-clic, rectangle) et ``paint`` la rend lisible.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self._source_item = None
        self._target_item = None
        self._rewire_requested = rewire_requested
        self._style = style if style in {"auto", "straight", "curve"} else "auto"
        self._path = QPainterPath()
        self._head = QPolygonF()
        self._badge = QPointF()
        self._set_endpoints(source, target, curved)

    @property
    def style(self) -> str:
        return self._style

    def set_style(self, style: str) -> None:
        """Force immédiatement le tracé droit ou la courbe ease-in/ease-out."""
        if style not in {"auto", "straight", "curve"}:
            raise ValueError(f"Unknown edge style: {style}")
        if style == self._style:
            return
        self._style = style
        if self._source_item is None or self._target_item is None:
            self._set_endpoints(self._source_rect, self._target_rect,
                                self._target_rect.center().x() < self._source_rect.center().x())
        else:
            self.refresh_geometry()

    def bind_anchors(self, source_item, target_item) -> None:
        """Lie l'arête à deux items exposant ``anchor_rect``.

        La vue inscrit ensuite l'arête auprès de chacun des deux items : au
        déplacement, seule sa géométrie de peinture est mise à jour.
        """
        self._source_item = source_item
        self._target_item = target_item
        self.refresh_geometry()

    def refresh_geometry(self) -> None:
        if self._source_item is None or self._target_item is None:
            return
        source = self._source_item.anchor_rect()
        target = self._target_item.anchor_rect()
        self._set_endpoints(source, target, target.center().x() < source.center().x())

    def _set_endpoints(self, source: QRectF, target: QRectF, curved: bool) -> None:
        # Le bounding rect peut grandir, rétrécir ou changer de côté : Qt doit
        # l'apprendre AVANT que le nouveau chemin soit construit.
        self.prepareGeometryChange()
        self._source_rect = QRectF(source)
        self._target_rect = QRectF(target)
        self._loop = source == target
        self._path = QPainterPath()
        self._head = QPolygonF()
        self._badge = QPointF()
        if self._loop:
            self._build_loop(source)
        elif self._style == "curve":
            self._build_curve(source, target)
        elif self._style == "straight":
            self._build_line(source, target)
        elif curved:
            self._build_back(source, target)
        else:
            self._build_line(source, target)
        self.update()

    def _build_line(self, source: QRectF, target: QRectF) -> None:
        a, b = _port_anchors(source, target)
        self._path.moveTo(a)
        self._path.lineTo(b)
        self._head = _arrow_head(b, QPointF(b.x() - a.x(), b.y() - a.y()))
        self._badge = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)

    def _build_back(self, source: QRectF, target: QRectF) -> None:
        # Retour (cible à gauche) : sort du port droit, plonge sous les cartes et
        # revient au port gauche de la cible — sans jamais quitter les ancres.
        a, b = _port_anchors(source, target)
        bow = 52.0
        c1 = QPointF(a.x() + bow, a.y() + bow)
        c2 = QPointF(b.x() - bow, b.y() + bow)
        self._path.moveTo(a)
        self._path.cubicTo(c1, c2, b)
        self._head = _arrow_head(b, QPointF(b.x() - c2.x(), b.y() - c2.y()))
        self._badge = QPointF((a.x() + b.x()) / 2, max(a.y(), b.y()) + bow)

    def _build_curve(self, source: QRectF, target: QRectF) -> None:
        """Courbe cubique avec sortie et arrivée horizontales (ease in/out)."""
        a, b = _port_anchors(source, target)
        bend = max(42.0, abs(b.x() - a.x()) * 0.38)
        c1 = QPointF(a.x() + bend, a.y())
        c2 = QPointF(b.x() - bend, b.y())
        self._path.moveTo(a)
        self._path.cubicTo(c1, c2, b)
        self._head = _arrow_head(b, QPointF(b.x() - c2.x(), b.y() - c2.y()))
        self._badge = self._path.pointAtPercent(0.5)

    def _build_loop(self, rect: QRectF) -> None:
        # Sort par le haut, revient par le haut : une courbe lisible même petite.
        top = rect.top()
        left = QPointF(rect.center().x() - 20, top)
        right = QPointF(rect.center().x() + 20, top)
        peak = 34.0
        self._path.moveTo(left)
        self._path.cubicTo(QPointF(left.x() - 30, top - peak),
                           QPointF(right.x() + 30, top - peak), right)
        self._head = _arrow_head(right, QPointF(0, 1))  # rentre vers le bas
        self._badge = QPointF(rect.center().x(), top - peak)

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().united(
            self._head.boundingRect()).adjusted(-12, -12, 12, 12)

    # La reconnexion est entièrement pilotée par la vue (`_GraphCanvas`), seule
    # à connaître le port d'entrée servant de poignée : elle appelle
    # ``target_handle_contains`` → ``preview_target`` → ``rewire_target_at`` /
    # ``request_rewire``. L'item n'intercepte donc aucun clic de son côté.

    def target_handle_contains(self, scene_pos) -> bool:
        """Zone de saisie volontairement large autour de la pointe de flèche."""
        return self._head.boundingRect().adjusted(-16, -16, 16, 16).contains(
            self.mapFromScene(scene_pos))

    def rewire_target_at(self, scene_pos):
        """Résout la carte sous une dépose, sans modifier le graphe."""
        if self.scene() is None:
            return None
        for item in self.scene().items(scene_pos):
            candidate = item
            while candidate is not None and not hasattr(candidate, "name"):
                candidate = candidate.parentItem()
            if candidate is not None:
                return candidate
        return None

    def request_rewire(self, items, target) -> None:
        """Délègue une dépose, seule ou groupée, au propriétaire du graphe."""
        if self._rewire_requested is not None:
            self._rewire_requested(items, target)

    def preview_target(self, scene_pos) -> None:
        """Déplace visuellement l'extrémité libre sous le curseur, sans modèle."""
        if self._source_item is None:
            return
        source = self._source_item.anchor_rect()
        # Rectangle dégénéré : son bord gauche et son centre sont exactement le
        # curseur, donc l'ancre d'entrée et la pointe coïncident.
        target = QRectF(scene_pos.x(), scene_pos.y(), 0.0, 0.0)
        self._set_endpoints(source, target, target.center().x() < source.center().x())

    def restore_target(self) -> None:
        self.refresh_geometry()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        selected = self.isSelected()
        color = QColor(C.ACCENT if selected else C.TEXT_DIM)
        painter.setPen(QPen(color, 2.5 if selected else 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(self._head)

        if self.count > 1:
            # Compteur : « ce lien est cité N fois », pas « il se déclenche N fois ».
            r = 9.0
            painter.setBrush(QBrush(QColor(C.ACCENT)))
            painter.drawEllipse(self._badge, r, r)
            painter.setPen(QPen(QColor(C.BG_DEEP)))
            painter.setFont(ui_font(T.XS, bold=True))
            painter.drawText(QRectF(self._badge.x() - r, self._badge.y() - r, 2 * r, 2 * r),
                             Qt.AlignmentFlag.AlignCenter, str(self.count))
