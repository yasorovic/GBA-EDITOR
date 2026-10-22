"""ui/scene_manager/scene_graph_breadcrumb.py — fil d'Ariane du Graphe.

Barre en bas de la vue Graphe qui montre le chemin du niveau courant
(`All scenes / Game / Village`) et laisse remonter en cliquant un maillon. Elle
ne connaît ni le store ni les groupes : la vue lui donne une liste de maillons
`(id, nom)` et reçoit l'id cliqué (None = racine).
"""
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

from ui.common.theme import C, T, ui_font


class SceneGraphBreadcrumb(QFrame):
    """Chemin cliquable du niveau ouvert. `level_selected` porte l'id (None=racine)."""

    level_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"{type(self).__name__}{{background:{C.BG_RAISED}; border-top:1px solid {C.BORDER};}}")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(8, 3, 8, 3)
        self._lay.setSpacing(2)
        self._lay.addStretch()

    def set_path(self, crumbs: list[tuple]) -> None:
        """`crumbs` = [(id|None, nom), …] de la racine au niveau courant."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # Destruction SYNCHRONE (pas deleteLater) : le fil d'Ariane est
                # reconstruit à chaque rendu ; laisser s'accumuler des suppressions
                # différées finit par corrompre l'arbre Qt au GC de la vue.
                sip.delete(w)
        for i, (level_id, name) in enumerate(crumbs):
            last = i == len(crumbs) - 1
            if i > 0:
                sep = QLabel("›")
                sep.setFont(ui_font(T.SM))
                sep.setStyleSheet(f"color:{C.TEXT_MUTED};")
                self._lay.addWidget(sep)
            crumb = QToolButton()
            crumb.setText(name)
            crumb.setFont(ui_font(T.SM, bold=last))
            crumb.setAutoRaise(True)
            crumb.setCursor(Qt.CursorShape.ArrowCursor if last
                            else Qt.CursorShape.PointingHandCursor)
            crumb.setEnabled(not last)   # le niveau courant n'est pas cliquable
            crumb.setStyleSheet(
                f"QToolButton{{border:none;background:transparent;padding:1px 4px;"
                f"color:{C.TEXT_HI if last else C.TEXT_NORM};}}"
                f"QToolButton:hover{{color:{C.ACCENT};}}")
            crumb.clicked.connect(lambda _=False, lid=level_id: self.level_selected.emit(lid))
            self._lay.addWidget(crumb)
        self._lay.addStretch()
