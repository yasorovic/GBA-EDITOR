"""Conteneur des contextes du Canvas du Scene Manager.

`CanvasWorkspace` possède les VUES du Canvas, pas leur logique métier. La vue
de scène existante reste un `SceneEditor` autonome ; la vue Graphe est une
`SceneGraphView` que ce conteneur crée et enregistre sans lui ajouter des nœuds,
des arêtes ou des dépendances Qt côté scène.

Le basculement « Scene / Graph » vit ici, et non dans la barre du `SceneEditor` :
cette barre disparaît avec la vue de scène (empilement exclusif), il faut donc un
bandeau persistant au-dessus des deux vues. Changer de vue ne recharge pas la
scène active et ne touche ni l'arbre ni l'inspecteur — c'est un simple échange de
widget dans l'empilement.

La fenêtre conserve une référence à `scene_editor` pendant la transition : les
connexions existantes (inspecteur, bus de sélection, dispatcher) restent donc
identiques. Les nouveaux branchements qui concernent le choix de vue passent
par ce conteneur.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QStackedLayout, QToolButton, QVBoxLayout,
    QWidget,
)

from ui.common.labels import label
from ui.common.theme import C, T, ui_font
from ui.scene_manager.scene_graph_view import SceneGraphView


class CanvasWorkspace(QWidget):
    """Héberge les vues exclusives du Canvas et le basculement entre elles.

    La clé ``scene`` est réservée à la vue de scène éditable, ``graph`` à la vue
    Graphe. Une vue ajoutée ultérieurement doit seulement être un QWidget : elle
    reçoit son propre contrat de chargement de données, plutôt que de devenir une
    extension de `SceneEditor`.
    """

    view_changed = pyqtSignal(str)
    SCENE_VIEW = "scene"
    GRAPH_VIEW = "graph"

    def __init__(self, scene_editor: QWidget, parent=None):
        super().__init__(parent)
        if scene_editor is None:
            raise ValueError("CanvasWorkspace requiert la vue de scène")

        self._views: dict[str, QWidget] = {}
        self._buttons: dict[str, QToolButton] = {}
        self._active_view = ""
        self.scene_editor = scene_editor
        self.graph_view = SceneGraphView()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_switch_bar())

        pages = QWidget()
        self._stack = QStackedLayout(pages)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)
        root.addWidget(pages, 1)

        self.register_view(self.SCENE_VIEW, scene_editor)
        self.register_view(self.GRAPH_VIEW, self.graph_view)
        self.activate_view(self.SCENE_VIEW, emit=False)

    # ── Bandeau de bascule ────────────────────────────────────────────

    def _build_switch_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(5)

        group = QButtonGroup(bar)
        group.setExclusive(True)
        self._buttons[self.SCENE_VIEW] = self._segment(
            group, self.SCENE_VIEW, label("scncanvas.view_scene"),
            label("scncanvas.view_scene_tip"))
        self._buttons[self.GRAPH_VIEW] = self._segment(
            group, self.GRAPH_VIEW, label("scncanvas.view_graph"),
            label("scncanvas.view_graph_tip"))
        # Cas volontairement distinct des barres d'outils ordinaires : ces deux
        # boutons choisissent une *vue* (comme 2D / 3D dans Godot), pas une
        # action. Deux ressorts symétriques les maintiennent donc au centre.
        lay.addStretch(1)
        for name in (self.SCENE_VIEW, self.GRAPH_VIEW):
            lay.addWidget(self._buttons[name])
        lay.addStretch(1)
        return bar

    def _segment(self, group, name, text, tip) -> QToolButton:
        """Un segment du sélecteur de vue — cochable, exclusif dans le groupe."""
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(True)
        b.setFont(ui_font(T.MD))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"color:{C.TEXT_NORM};padding:3px 12px;margin:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border-color:{C.ACCENT};"
            f"color:{C.TEXT_HI};}}"
        )
        group.addButton(b)
        # Le clic sur un segment demande la vue ; l'activation, elle, coche en
        # retour (sync depuis activate_view) — les deux sens ne se bouclent pas
        # car activate_view sort tôt quand la vue est déjà active.
        b.clicked.connect(lambda _=False, n=name: self.activate_view(n))
        return b

    # ── Vues ──────────────────────────────────────────────────────────

    @property
    def active_view(self) -> str:
        return self._active_view

    def view(self, name: str) -> QWidget | None:
        """Renvoie une vue enregistrée, sans exposer le QStackedLayout."""
        return self._views.get(name)

    def register_view(self, name: str, widget: QWidget) -> None:
        """Ajoute une vue sous un nom stable."""
        if not name:
            raise ValueError("Une vue Canvas doit avoir un nom")
        if name in self._views:
            raise ValueError(f"La vue Canvas '{name}' existe déjà")
        if widget is None:
            raise ValueError("Une vue Canvas ne peut pas être vide")
        self._views[name] = widget
        self._stack.addWidget(widget)

    def activate_view(self, name: str, *, emit: bool = True) -> None:
        """Affiche une vue déjà enregistrée."""
        widget = self._views.get(name)
        if widget is None:
            raise KeyError(f"Vue Canvas inconnue : {name}")
        button = self._buttons.get(name)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        if name == self._active_view:
            return
        self._stack.setCurrentWidget(widget)
        self._active_view = name
        if emit:
            self.view_changed.emit(name)

    def load_project(self, project, graph_state=None, folder_store=None) -> None:
        """Charge la vue de scène et attache le projet à la vue Graphe.

        `graph_state` (positions/présentation) et `folder_store` (dossiers
        d'assets, dont les groupes de scènes) sont les stores partagés possédés
        par la fenêtre — mêmes objets que le project viewer. La vue Graphe ne
        projette qu'à son premier affichage (pull mémoïsé) : `set_project` ne fait
        qu'attacher projet et stores, sans re-parser aucun script tant que
        l'utilisateur n'a pas basculé sur « Graph ».
        """
        self.graph_view.set_project(project, graph_state, folder_store)
        if project and project.active_scene:
            self.scene_editor.load_project(project)
