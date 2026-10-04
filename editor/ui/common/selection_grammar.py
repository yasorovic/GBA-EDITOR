"""ui/common/selection_grammar.py — la grammaire visuelle de sélection, une fois.

Tous les arbres à sélection multiple de l'éditeur (finders, arbre de contenu de
scène) parlent le même langage à trois niveaux, distincts et cumulables :

- **active** — l'asset OUVERT dans le canvas (une scène chargée). Signal : une
  **barre verticale à gauche** (accent). Le bord gauche lui est réservé : rien
  d'autre n'y dessine.
- **active selection** — la PREMIÈRE de la pile de sélection (l'item courant Qt).
  Signal : **remplissage plein** (`BG_SEL`).
- **passive selection** — les sélections SECONDAIRES d'une multi-sélection.
  Signal : **contour seul** (liseré fin), sans remplissage.

« active » et une sélection se cumulent sur une même ligne (barre + remplissage).
Le remplissage (primaire) et le contour (secondaire) se distinguent à l'œil sans
lire le texte, comme demandé.

Pourquoi un delegate et pas le QSS : une feuille de style Qt ne sait pas isoler
l'item COURANT des autres items sélectionnés (aucun pseudo-état `:current`). Le
delegate, lui, interroge `tree.currentItem()`. Il POSSÈDE donc seul le rendu de
sélection : il neutralise l'état sélectionné avant `super().paint` (pour que le
fond/texte de base redeviennent neutres), peint le langage de sélection sous le
texte, puis la barre active par-dessus. Le QSS n'a plus qu'à ne pas dessiner de
liseré de sélection à gauche (réservé à « active »).

Un arbre qui n'a pas de notion d'« actif » (la plupart des finders) n'expose pas
`active_item()` : le delegate le tolère et ne peint alors que les deux niveaux de
sélection.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtCore import Qt, QRect

from ui.common.theme import C

_ACTIVE_BAR_W = 3   # largeur de la barre « active » (bord gauche)
_PASSIVE_PEN = 1    # épaisseur du contour « passive selection »


class RowSelectionDelegate(QStyledItemDelegate):
    """Peint la grammaire de sélection à trois niveaux (cf. en-tête du module).

    Se construit avec l'arbre pour parent — c'est lui qu'il interroge pour l'item
    courant et l'item actif."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        # Neutralise la sélection (et le survol, sinon la règle QSS `:hover`
        # repeindrait par-dessus notre remplissage) : `super().paint` rend alors
        # une ligne « normale », et c'est nous qui disons ce qu'être sélectionné
        # veut dire.
        opt.state &= ~QStyle.StateFlag.State_Selected
        if selected:
            opt.state &= ~QStyle.StateFlag.State_MouseOver

        tree = self.parent()
        item = tree.itemFromIndex(index) if hasattr(tree, "itemFromIndex") else None
        current = item is not None and item is tree.currentItem()
        col = index.column()
        last_col = index.model().columnCount(index.parent()) - 1
        r: QRect = opt.rect

        # ── Fond de sélection, SOUS le texte ──────────────────────────
        if selected and current:
            painter.fillRect(r, QColor(C.BG_SEL))          # primaire : plein
        elif selected:
            # Secondaire : contour de ligne. Sur un arbre multi-colonnes, on ne
            # trace les bords verticaux qu'aux colonnes de bout, pour un cadre de
            # LIGNE et non un cadre par cellule.
            painter.save()
            painter.setPen(QPen(QColor(C.ACCENT), _PASSIVE_PEN))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Pixels INCLUSIFS, comme le remplissage : sinon un cran vide reste
            # entre deux cellules et le cadre s'arrête un pixel avant le fond.
            x0, x1 = r.left(), r.right()
            y0, y1 = r.top(), r.bottom()
            painter.drawLine(x0, y0, x1, y0)
            painter.drawLine(x0, y1, x1, y1)
            if col == 0:
                painter.drawLine(x0, y0, x0, y1)
            if col == last_col:
                painter.drawLine(x1, y0, x1, y1)
            painter.restore()

        super().paint(painter, opt, index)

        # ── Barre « active » (canvas), PAR-DESSUS, colonne de gauche ──
        if col == 0 and hasattr(tree, "active_item"):
            active = tree.active_item()
            if active is not None and item is active:
                painter.save()
                painter.fillRect(QRect(r.left(), r.top(), _ACTIVE_BAR_W, r.height()),
                                 QColor(C.ACCENT))
                painter.restore()
