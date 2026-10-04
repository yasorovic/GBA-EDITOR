"""ui/common/tree_selection.py — surlignage par identité dans un QTreeWidget.

Deux arbres de l'éditeur reçoivent une sélection venue d'AILLEURS et doivent la
refléter sans la réémettre : le project viewer (sélection croisée avec le graphe
des scènes) et le Scene Tree Contenu (sélection croisée avec le canvas via le
bus). Le geste est identique — bloquer les signaux pour ne pas boucler, tout
désélectionner, cocher les items qui correspondent — seul le CRITÈRE d'identité
diffère (le finder compare `id(obj)`, le Scene Tree un type de nœud plus l'objet).
On factorise donc le geste et on laisse le critère à l'appelant, via un prédicat.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

try:
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
except ImportError:              # même repli défensif que les arbres appelants
    QTreeWidgetItemIterator = None


def highlight_matching(tree: QTreeWidget,
                       predicate: Callable[[QTreeWidgetItem], bool],
                       *, scroll_to_first: bool = False,
                       current: Callable[[QTreeWidgetItem], bool] | None = None) -> None:
    """Sélectionne, SANS réémettre, les items pour lesquels `predicate` est vrai.

    `blockSignals` évite que la sélection reposée ne reparte en boucle vers la vue
    qui l'a émise (et, pour le project viewer, n'active/charge une scène). Parcours
    de haut en bas pour que `scroll_to_first` vise la première correspondance.

    L'item COURANT Qt est posé lui aussi (sans toucher à la sélection) : la
    grammaire de sélection (`selection_grammar`) peint en plein l'item courant
    sélectionné et en simple contour les autres. Sans courant, une sélection
    venue d'ailleurs s'afficherait comme « secondaire ». `current` désigne
    l'item primaire d'une multi-sélection ; à défaut, la première correspondance.
    """
    tree.blockSignals(True)
    tree.clearSelection()
    first: QTreeWidgetItem | None = None
    primary: QTreeWidgetItem | None = None
    if QTreeWidgetItemIterator is not None:
        it = QTreeWidgetItemIterator(tree)
        while it.value():
            node = it.value()
            if predicate(node):
                node.setSelected(True)
                if first is None:
                    first = node
                if current is not None and current(node):
                    primary = node
            it += 1
    if (primary or first) is not None:
        tree.setCurrentItem(primary or first, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
    tree.blockSignals(False)
    if scroll_to_first and first is not None:
        tree.scrollToItem(first)
