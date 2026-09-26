"""
ui/common/responsive.py — inspecteurs qui se resserrent au lieu de déborder.

Un inspecteur est une colonne de lignes « libellé + champ ». Trop étroit, ses
widgets refusent de descendre sous la largeur de leur texte (un combo affiche
« From project (Cut (no transition)) » en entier, un bouton son libellé) : le
contenu dépasse et une barre de défilement horizontale apparaît.

`InspectorScrollArea` supprime la barre horizontale et autorise chaque widget de
saisie qu'elle contient à rétrécir (le style tronque le texte). Le passage se
refait à chaque changement de mise en page du contenu, donc aussi pour les
lignes que les inspecteurs recréent à chaque sélection.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFrame, QLabel, QLayout, QLineEdit, QPushButton,
    QScrollArea, QToolButton, QWidget,
)

_SHRINKABLE = (QComboBox, QPushButton, QToolButton, QLineEdit, QAbstractSpinBox, QLabel)


class InspectorScrollArea(QScrollArea):
    """QScrollArea d'inspecteur : verticale seulement, contenu qui se resserre."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._shrink_pending = False

    def setWidget(self, widget: QWidget):
        super().setWidget(widget)
        widget.installEventFilter(self)
        self._schedule_shrink()

    def minimumSizeHint(self) -> QSize:
        # Le plancher réel : la largeur minimale du contenu (une fois les widgets
        # rétrécis) + la barre verticale. Sans lui, un séparateur pourrait
        # écraser l'inspecteur sous ce seuil et couper le contenu sans recours,
        # puisqu'il n'y a plus de barre horizontale.
        hint = super().minimumSizeHint()
        content = self.widget()
        if content is None:
            return hint
        floor = content.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width()
        return QSize(max(hint.width(), floor), hint.height())

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.ChildAdded):
            self._schedule_shrink()
        return False

    def _schedule_shrink(self):
        # Coalescé : une rafale de lignes ajoutées ne déclenche qu'un passage.
        if not self._shrink_pending:
            self._shrink_pending = True
            QTimer.singleShot(0, self._shrink_children)

    def _shrink_children(self):
        self._shrink_pending = False
        content = self.widget()
        if content is None:
            return
        for child in content.findChildren(_SHRINKABLE):
            # Largeur déjà imposée (minimum ou largeur fixe) : on la respecte.
            # 1 et non 0 : Qt ne lit le minimum demandé qu'au-dessus de 0 et
            # retombe sinon sur minimumSizeHint, la largeur du texte.
            if child.minimumWidth() == 0:
                child.setMinimumWidth(1)


class FlowLayout(QLayout):
    """Widgets rangés de gauche à droite, renvoyés à la ligne quand la largeur
    manque. Remplace un QHBoxLayout de widgets à taille fixe dont la somme
    imposerait sa largeur à tout l'inspecteur.

    `add_trailing_break()` joue le rôle d'`addStretch()` : les widgets ajoutés
    APRÈS l'appel sont collés au bord droit de leur ligne."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._gap = spacing
        self._trailing_from: int | None = None

    def addItem(self, item):
        self._items.append(item)

    def add_trailing_break(self):
        self._trailing_from = len(self._items)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def _lines(self, width: int) -> list[list[int]]:
        lines: list[list[int]] = [[]]
        used = 0
        for index, item in enumerate(self._items):
            if item.isEmpty():
                continue
            w = item.sizeHint().width()
            if lines[-1] and used + self._gap + w > width:
                lines.append([])
                used = 0
            used += w + (self._gap if lines[-1] else 0)
            lines[-1].append(index)
        return lines if lines[-1] else lines[:-1]

    def _line_height(self, line: list[int]) -> int:
        return max(self._items[i].sizeHint().height() for i in line)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        lines = self._lines(width - margins.left() - margins.right())
        heights = [self._line_height(line) for line in lines]
        body = sum(heights) + self._gap * max(0, len(heights) - 1)
        return body + margins.top() + margins.bottom()

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        area = rect.marginsRemoved(self.contentsMargins())
        y = area.y()
        for line in self._lines(area.width()):
            height = self._line_height(line)
            x = area.x()
            right = area.right() + 1
            # Groupe de queue : posé de droite à gauche depuis le bord droit.
            tail = [i for i in line if self._trailing_from is not None
                    and i >= self._trailing_from]
            for i in reversed(tail):
                w = self._items[i].sizeHint().width()
                right -= w
                self._items[i].setGeometry(QRect(right, y + (height - self._items[i].sizeHint().height()) // 2,
                                                 w, self._items[i].sizeHint().height()))
                right -= self._gap
            for i in line:
                if i in tail:
                    continue
                item = self._items[i]
                size = item.sizeHint()
                item.setGeometry(QRect(x, y + (height - size.height()) // 2,
                                       size.width(), size.height()))
                x += size.width() + self._gap
            y += height + self._gap

    def sizeHint(self):
        margins = self.contentsMargins()
        visible = [i for i, item in enumerate(self._items) if not item.isEmpty()]
        width = sum(self._items[i].sizeHint().width() for i in visible)
        width += self._gap * max(0, len(visible) - 1)
        width += margins.left() + margins.right()
        return QSize(width, self.heightForWidth(width))

    def minimumSize(self):
        margins = self.contentsMargins()
        widest = max((item.minimumSize().width() for item in self._items
                      if not item.isEmpty()), default=0)
        tallest = max((item.minimumSize().height() for item in self._items
                       if not item.isEmpty()), default=0)
        return QSize(widest + margins.left() + margins.right(),
                     tallest + margins.top() + margins.bottom())
