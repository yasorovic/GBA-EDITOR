"""Le squelette commun des écrans : library | centre | inspecteur, et sous la
colonne centrale un emplacement pour le panneau de build.

Chaque écran refaisait ce `QSplitter` à la main (poignées, stretch, tailles) ; ce
composant le possède une fois. Le panneau de build, lui, n'a qu'UNE instance dans
la fenêtre : elle l'accroche à l'écran affiché (`attach_dock`) et lui dit s'il
est ouvert (`set_dock_open`) — l'écran ne sait rien du build.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ui.common.theme import QSS

_DOCK_HEIGHT = 160     # hauteur donnée au panneau quand il s'ouvre
_DEFAULT_COLUMN_HEIGHT = 760   # avant le premier affichage, le splitter n'a pas de hauteur


class ThreeColumnBody(QSplitter):
    """Trois colonnes. Le centre est empilé avec l'emplacement du panneau de build.

    Un écran dont le centre est vide (le Sound Mixer, le temps de son recentrage) donne
    un centre vide plutôt que de le retirer : la colonne et sa poignée restent.
    """

    def __init__(self, left: QWidget, center: QWidget, right: QWidget,
                 sizes: tuple[int, int, int] = (240, 760, 300), parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setStyleSheet(QSS.splitter)

        self._dock_host = QWidget()
        self._dock_layout = QVBoxLayout(self._dock_host)
        self._dock_layout.setContentsMargins(0, 0, 0, 0)
        self._dock_layout.setSpacing(0)

        self.center_split = QSplitter(Qt.Orientation.Vertical)
        self.center_split.setStyleSheet(QSS.splitter)
        self.center_split.addWidget(center)
        self.center_split.addWidget(self._dock_host)
        self.center_split.setSizes([_DEFAULT_COLUMN_HEIGHT, 0])
        self.center_split.setStretchFactor(0, 1)
        self.center_split.setStretchFactor(1, 0)
        self.center_split.setCollapsible(1, True)

        self.addWidget(left)
        self.addWidget(self.center_split)
        self.addWidget(right)
        self.setSizes(list(sizes))
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)     # le centre absorbe le redimensionnement
        self.setStretchFactor(2, 0)

    # ── Emplacement du panneau de build ──────────────────────────────
    #
    # Fermé = replié à zéro DANS le splitter, jamais masqué : sa poignée reste au
    # bord bas du centre, et c'est elle qu'on tire pour l'ouvrir.

    def attach_dock(self, panel: QWidget) -> None:
        """Accroche le panneau ici ; Qt le décroche de l'écran précédent."""
        self._dock_layout.addWidget(panel)

    def holds_dock(self, panel: QWidget) -> bool:
        return panel.parentWidget() is self._dock_host

    def dock_is_open(self) -> bool:
        return self._dock_height() > 0

    def set_dock_open(self, opened: bool) -> None:
        total = sum(self.center_split.sizes()) or _DEFAULT_COLUMN_HEIGHT
        height = min(_DOCK_HEIGHT, total // 2) if opened else 0
        self.center_split.setSizes([total - height, height])

    def _dock_height(self) -> int:
        return self.center_split.sizes()[self.center_split.indexOf(self._dock_host)]
