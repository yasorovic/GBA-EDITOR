"""ui/scene_manager/scene_graph_group_items.py — boîtes de groupe du Graphe.

Un groupe de scènes (dossier de la famille `scenes`, cf. `AssetFolderStore`) se
dessine ici de deux façons, décidées par la vue :

- **dépliée** : un cadre qui ENTOURE les cartes de ses scènes membres, avec un
  en-tête (nom + nombre) posé au-dessus d'elles. Le cadre est dérivé (il suit les
  positions des membres) : il ne se déplace pas lui-même.
- **repliée** : une boîte condensée réduite à son en-tête, à une position
  mémorisée et déplaçable ; ses scènes membres ne sont pas dessinées.

Le repli/dépli est un geste sur place (il ne change pas de niveau — la descente
par niveaux est un chantier distinct). Il passe par un petit chevron cliquable,
`GroupToggleItem`, enfant de la boîte : la vue le reconnaît au clic et bascule
l'état, sans que la boîte ait à connaître le store.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem

from ui.common.theme import C, T, ui_font

HEADER_H = 24.0
COLLAPSED_W = 168.0
COLLAPSED_H = 34.0
DOOR_W = 120.0
DOOR_H = 30.0
_RADIUS = 8.0
_PEN = 2.0
_TOGGLE = 16.0
# Épaisseur de la zone de saisie des bords (redimensionnement) et taille
# plancher d'un cadre déplié — assez pour garder l'en-tête lisible.
_EDGE = 8.0
_MIN_W = 120.0
_MIN_H = HEADER_H + 28.0
_GRID_STEP = 40.0


class GroupToggleItem(QGraphicsItem):
    """Chevron cliquable de repli/dépli, enfant d'une `SceneGroupBoxItem`."""

    def __init__(self, group_id: str, collapsed: bool, color: str, parent=None):
        super().__init__(parent)
        self.group_id = group_id
        self._collapsed = collapsed
        self._color = color
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # clic capté par la vue

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, _TOGGLE, _TOGGLE)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self._color or C.TEXT_DIM)))
        c = _TOGGLE / 2
        if self._collapsed:
            # ▸ replié : pointe vers la droite (« déplier pour ouvrir »).
            tri = QPolygonF([QPointF(c - 3, c - 5), QPointF(c + 4, c),
                             QPointF(c - 3, c + 5)])
        else:
            # ▾ déplié : pointe vers le bas.
            tri = QPolygonF([QPointF(c - 5, c - 3), QPointF(c + 5, c - 3),
                             QPointF(c, c + 4)])
        painter.drawPolygon(tri)


class BoundaryDoorItem(QGraphicsItem):
    """Porte de frontière d'un niveau : les transitions qui franchissent le bord
    du groupe ouvert, agrégées en « ← N entrées » ou « N sorties → », plutôt que
    des scènes externes qu'on pourrait croire éditables ici."""

    def __init__(self, incoming: bool, count: int):
        super().__init__()
        self.incoming = incoming
        self.count = count

    def boundingRect(self) -> QRectF:
        return QRectF(-_PEN, -_PEN, DOOR_W + 2 * _PEN, DOOR_H + 2 * _PEN)

    def anchor_rect(self) -> QRectF:
        return self.mapToScene(QRectF(0, 0, DOOR_W, DOOR_H)).boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        body = QRectF(0, 0, DOOR_W, DOOR_H)
        painter.setPen(QPen(QColor(C.TEXT_DIM), 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(C.BG_RAISED)))
        painter.drawRoundedRect(body, _RADIUS, _RADIUS)
        painter.setPen(QPen(QColor(C.TEXT_DIM)))
        painter.setFont(ui_font(T.SM))
        arrow = "←" if self.incoming else "→"
        text = f"{arrow} {self.count}" if self.incoming else f"{self.count} {arrow}"
        painter.drawText(body, Qt.AlignmentFlag.AlignCenter, text)


class SceneGroupBoxItem(QGraphicsItem):
    """Cadre (déplié) ou boîte condensée (replié) d'un groupe de scènes.

    Repliée, la boîte se déplace comme un nœud (`ItemIsMovable`). Dépliée, elle
    est un rectangle que l'auteur **déplace par son en-tête** (les cartes membres
    suivent) et **redimensionne par ses bords latéraux et bas** ; le mouvement et
    la taille sont gérés à la main plutôt que par `ItemIsMovable`, pour restreindre
    la prise à l'en-tête et emporter les membres. L'appartenance, elle, ne change
    qu'en glissant une carte dans ou hors du cadre — c'est la vue qui la recalcule
    au relâchement, par simple contenance géométrique."""

    def __init__(self, group_id: str, name: str, count: int, collapsed: bool,
                 width: float, height: float, color: str = "",
                 geometry_changed=None):
        super().__init__()
        self.group_id = group_id
        self.name = name
        self.count = count
        self.collapsed = collapsed
        self.color = color
        self._w = width
        self._h = height
        self._geometry_changed = geometry_changed
        # Cartes membres visibles — le déplacement de l'en-tête les emporte pour
        # qu'elles restent dans le cadre. Renseignées par la vue après création.
        self.member_items: list = []
        self._mode: str | None = None      # 'move' | 'e' | 'w' | 's' | 'se' | 'sw'
        self._grab_scene = None            # position scène au début du geste
        self._grab_pos = None              # position du cadre au début
        self._grab_wh = None               # (w, h) au début
        self._grab_members: list = []      # positions de départ des membres
        if collapsed:
            # Une boîte repliée se déplace et se sélectionne comme un nœud ; la
            # vue persiste sa position au relâchement.
            self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                          | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        else:
            self.setAcceptHoverEvents(True)   # curseurs de redimensionnement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        toggle = GroupToggleItem(group_id, collapsed, color, parent=self)
        toggle.setPos(6, (HEADER_H - _TOGGLE) / 2)
        toggle.setZValue(1)

    def boundingRect(self) -> QRectF:
        return QRectF(-_PEN, -_PEN, self._w + 2 * _PEN, self._h + 2 * _PEN)

    def anchor_rect(self) -> QRectF:
        """Rectangle de la boîte en coordonnées de scène — pour ancrer les arêtes
        qui touchent un membre caché (groupe replié) et tester la contenance
        d'une carte glissée."""
        return self.mapToScene(QRectF(0, 0, self._w, self._h)).boundingRect()

    def itemChange(self, change, value):
        if (change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._geometry_changed is not None):
            self._geometry_changed(self)
        return super().itemChange(change, value)

    def _geometry_did_change(self) -> None:
        if self._geometry_changed is not None:
            self._geometry_changed(self)

    @staticmethod
    def _snap(pos):
        return QPointF(round(pos.x() / _GRID_STEP) * _GRID_STEP,
                       round(pos.y() / _GRID_STEP) * _GRID_STEP)

    # ── Déplacement par l'en-tête / redimensionnement par les bords ─────

    def _zone(self, pos) -> str | None:
        """Zone sous le curseur (coordonnées de l'item) : bord de
        redimensionnement, en-tête déplaçable, ou rien (intérieur laissé au
        rectangle de sélection de la vue). Le chevron de repli est exclu — son
        clic bascule l'état, il ne saisit pas la boîte."""
        x, y = pos.x(), pos.y()
        left, right = x <= _EDGE, x >= self._w - _EDGE
        bottom = y >= self._h - _EDGE
        if bottom and right:
            return "se"
        if bottom and left:
            return "sw"
        if right:
            return "e"
        if left:
            return "w"
        if bottom:
            return "s"
        if y <= HEADER_H and x > 6 + _TOGGLE + 4:
            return "move"
        return None

    _CURSORS = {
        "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
        "s": Qt.CursorShape.SizeVerCursor,
        "se": Qt.CursorShape.SizeFDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
        "move": Qt.CursorShape.SizeAllCursor,
    }

    def hoverMoveEvent(self, event):
        if not self.collapsed:
            zone = self._zone(event.pos())
            self.setCursor(self._CURSORS.get(zone, Qt.CursorShape.ArrowCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.collapsed:
            return super().mousePressEvent(event)
        zone = self._zone(event.pos())
        if zone is None:
            # Intérieur vide : laisser passer pour le rubber-band de la vue.
            event.ignore()
            return
        self._mode = zone
        self._grab_scene = event.scenePos()
        self._grab_pos = self.pos()
        self._grab_wh = (self._w, self._h)
        self._grab_members = [(it, it.pos()) for it in self.member_items]
        event.accept()

    def mouseMoveEvent(self, event):
        if self.collapsed or self._mode is None:
            super().mouseMoveEvent(event)
            if self.collapsed:
                p = self.pos()
                snapped = self._snap(p)
                if snapped != p:
                    self.setPos(snapped)
            return
        dx = event.scenePos().x() - self._grab_scene.x()
        dy = event.scenePos().y() - self._grab_scene.y()
        if self._mode == "move":
            snapped = self._snap(QPointF(self._grab_pos.x() + dx,
                                         self._grab_pos.y() + dy))
            self.setPos(snapped)
            for it, start in self._grab_members:
                it.setPos(start.x() + snapped.x() - self._grab_pos.x(),
                          start.y() + snapped.y() - self._grab_pos.y())
            return
        w0, h0 = self._grab_wh
        x, y = self._grab_pos.x(), self._grab_pos.y()
        w, h = w0, h0
        if self._mode in ("e", "se"):
            w = max(_MIN_W, w0 + dx)
        if self._mode in ("s", "se", "sw"):
            h = max(_MIN_H, h0 + dy)
        if self._mode in ("w", "sw"):
            w = max(_MIN_W, w0 - dx)
            x = self._grab_pos.x() + (w0 - w)
        self.prepareGeometryChange()
        self._w, self._h = w, h
        self.setPos(x, y)
        self.update()
        self._geometry_did_change()

    def mouseReleaseEvent(self, event):
        if self.collapsed:
            return super().mouseReleaseEvent(event)
        self._mode = None
        event.accept()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        border = QColor(self.color) if self.color else QColor(C.BORDER_MID)
        if self.isSelected():
            border = QColor(C.ACCENT)
        body = QRectF(0, 0, self._w, self._h)

        if self.collapsed:
            painter.setPen(QPen(border, 1.5))
            painter.setBrush(QBrush(QColor(C.BG_PANEL)))
            painter.drawRoundedRect(body, _RADIUS, _RADIUS)
        else:
            # Cadre : remplissage très discret pour lire l'appartenance sans
            # masquer les cartes, en-tête plein en haut.
            fill = QColor(self.color) if self.color else QColor(C.BORDER_MID)
            fill.setAlpha(24)
            painter.setPen(QPen(border, 1.5, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(fill))
            painter.drawRoundedRect(body, _RADIUS, _RADIUS)
            header = QColor(self.color) if self.color else QColor(C.BORDER_MID)
            header.setAlpha(48)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(header))
            painter.drawRoundedRect(QRectF(0, 0, self._w, HEADER_H), _RADIUS, _RADIUS)
            painter.drawRect(QRectF(0, HEADER_H - _RADIUS, self._w, _RADIUS))

        painter.setPen(QPen(QColor(C.TEXT_HI)))
        painter.setFont(ui_font(T.MD, bold=True))
        text = QRectF(6 + _TOGGLE + 4, 0, self._w - _TOGGLE - 16, HEADER_H)
        painter.drawText(text, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         f"{self.name}  ({self.count})")
