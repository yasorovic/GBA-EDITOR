"""
PrefabUsesInspector / ScriptUsesInspector.

Deux vues "Voir les utilisations" affichées dans l'inspector, groupées dans
un seul fichier car structurellement proches (header coloré + section bar +
liste + vidage de liste) — d'où la base commune _UsesInspectorBase ci-dessous.
Chaque sous-classe ne diffère que par ses couleurs, son bouton d'action
optionnel, et la façon dont elle peuple la liste (load()), qui reste propre
à son domaine (instances de prefab / actors utilisant un script).
"""
from __future__ import annotations
from ui.common.labels import label
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QScrollArea,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.selection_bus import get_bus
from ui.common.theme import C, T
from ui.common.widgets import CollapsibleCard
from ui.common import icons


# ──────────────────────────────────────────────────────────────────
#  Base commune : header coloré + section bar (+ bouton d'action
#  optionnel) + liste scrollable + helpers de construction de lignes.
# ──────────────────────────────────────────────────────────────────
class _UsesInspectorBase(QWidget):
    _HEADER_COLOR = icons.COLOR_DEFAULT
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = ""
    _ACTION_BTN_TEXT: str | None = None
    _ACTION_BTN_COLOR: str | None = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._root_layout = root

        # ── Header coloré avec nom de l'élément inspecté ──────────
        self._top = QFrame()
        self._top.setFixedHeight(40)
        self._top.setStyleSheet(
            f"background:{self._HEADER_COLOR}{self._HEADER_BG_ALPHA}; "
            f"border-bottom:1px solid {self._HEADER_COLOR}{self._HEADER_BORDER_ALPHA};"
        )
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(12, 0, 8, 0)
        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        btn_close = QPushButton("v")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            f"QPushButton{{color:{self._HEADER_COLOR};background:transparent;border:none;"
            f"font-family:{T.UI_STACK};font-size:10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_close.setToolTip(label('uses.close_this_view'))
        btn_close.clicked.connect(self._on_close)
        tl.addWidget(self._name_lbl, 1)
        tl.addWidget(btn_close)
        root.addWidget(self._top)

        # ── Carte : titre + bouton d'action optionnel + liste ─────
        self._card = CollapsibleCard(self._SECTION_TITLE, color=self._HEADER_COLOR)
        self._card.set_expanding(True)
        # Une liste ouverte utilise toute la hauteur utile. Repliée, elle ne
        # doit plus garder sa cellule extensible : sinon Qt centre son en-tête
        # dans le grand espace restant et décale les inspecteurs suivants.
        self._card.toggled.connect(self._on_card_toggled)
        if self._ACTION_BTN_TEXT:
            self._action_btn = QPushButton(self._ACTION_BTN_TEXT)
            self._action_btn.setFont(QFont(T.UI, T.SM))
            self._action_btn.setFixedHeight(20)
            self._action_btn.setStyleSheet(
                f"QPushButton{{color:{self._ACTION_BTN_COLOR};background:transparent;border:none;"
                f"font-family:{T.UI_STACK};font-size:8px;}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            )
            self._action_btn.clicked.connect(self._on_action)
            self._card.add_header_widget(self._action_btn)
        root.addWidget(self._card, 1)

        # ── Liste des utilisations ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{C.BG_PANEL};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        self._card.body_layout.setContentsMargins(0, 0, 0, 0)
        self._card.body_layout.addWidget(scroll)

    def _on_card_toggled(self, expanded: bool) -> None:
        """Réserve la hauteur libre à la liste seulement lorsqu'elle est visible."""
        index = self._root_layout.indexOf(self._card)
        if index >= 0:
            self._root_layout.setStretch(index, 1 if expanded else 0)
            self._root_layout.invalidate()

    # ── Helpers de construction de liste, communs aux sous-classes ──

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            old_w = item.widget()
            if old_w:
                # hide() avant setParent(None) : un widget visible détaché de
                # son parent redevient une fenêtre top-level à part entière.
                old_w.hide()
                old_w.setParent(None)
                old_w.deleteLater()

    def _add_empty_row(self, text: str):
        empty = QLabel(f"  {text}")
        empty.setFont(QFont(T.UI, T.MD))
        empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:12px;")
        self._list_layout.addWidget(empty)

    def _add_group_row(self, icon: str, label: str, color: str, count: int | None = None):
        row = QFrame()
        row.setFixedHeight(24)
        row.setStyleSheet(f"background:{C.BG_RAISED};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 8, 0)
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont(T.UI, T.MD))
        icon_lbl.setStyleSheet(f"color:{color};")
        icon_lbl.setFixedWidth(16)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.UI, T.MD))
        name_lbl.setStyleSheet(f"color:{color};")
        rl.addWidget(icon_lbl)
        rl.addWidget(name_lbl, 1)
        if count is not None:
            count_lbl = QLabel(f"×{count}")
            count_lbl.setFont(QFont(T.UI, T.SM))
            count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            rl.addWidget(count_lbl)
        self._list_layout.addWidget(row)

    def _add_leaf_row(self, label: str, on_click):
        leaf = QFrame()
        leaf.setFixedHeight(22)
        leaf.setStyleSheet(f"background:{C.BG_PANEL};")
        leaf.setCursor(Qt.CursorShape.PointingHandCursor)
        ll = QHBoxLayout(leaf)
        ll.setContentsMargins(28, 0, 8, 0)
        icon_lbl = QLabel("·")
        icon_lbl.setFont(QFont(T.UI, T.MD))
        icon_lbl.setStyleSheet(f"color:{C.BORDER_MID};")
        icon_lbl.setFixedWidth(12)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.UI, T.MD))
        name_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        ll.addWidget(icon_lbl)
        ll.addWidget(name_lbl, 1)
        self._list_layout.addWidget(leaf)
        leaf.mousePressEvent = lambda e, cb=on_click: cb()

    # ── Actions par défaut, surchargeables ───────────────────────────

    def _on_action(self):
        pass

    def _on_close(self):
        get_bus().clear()


# ──────────────────────────────────────────────────────────────────
#  PrefabUsesInspector — liste des instances d'un prefab par scène
# ──────────────────────────────────────────────────────────────────
class PrefabUsesInspector(_UsesInspectorBase):
    """
    Vue 'PREFAB USES' affichée dans l'inspector quand on clique
    'Voir les instances' dans le panneau projet.

    Structure :
        ┌─ Header bleu : nom du prefab  ────────── [v] ─┐
        │  PREFAB USES              [Éditer le prefab]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        │      · Actor 2                                │
        │  ▸ Scene B                                    │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(object)   # Prefab — demande d'édition
    open_ref       = pyqtSignal(str, int) # (chemin de script, ligne) — sauter au spawn

    _HEADER_COLOR = icons.COLOR_PREFAB
    _HEADER_BG_ALPHA = "30"
    _HEADER_BORDER_ALPHA = "50"
    _SECTION_TITLE = label('uses.prefab_uses')
    _ACTION_BTN_TEXT = label('uses.edit_prefab')
    _ACTION_BTN_COLOR = icons.COLOR_PREFAB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefab  = None
        self._project = None

    # ── Chargement ────────────────────────────────────────────────

    def load(self, prefab, project):
        self._prefab  = prefab
        self._project = project
        self._name_lbl.setText(prefab.name)
        self._clear_list()

        # « Utilisé par » : les instances POSÉES dans une scène.
        found = False
        for scene in project.scenes:
            linked = [a for a in scene.actors if a.prefab_name == prefab.name]
            if not linked:
                continue
            found = True
            self._add_group_row("◈", scene.name, "#7ecfff", count=len(linked))
            for actor in linked:
                # Clic → sélectionner l'actor dans la scène active
                self._add_leaf_row(actor.name, lambda a=actor: get_bus().select(a))

        # « Spawné par » : les scripts qui appellent `actor:spawn("<ce prefab>")`.
        # Troisième lien de dépendance, distinct des instances posées : le nom
        # du prefab est un littéral obligatoire, donc lisible statiquement sans
        # rien exécuter (ROADMAP v0.17). Même lecture que celle qui *propose* le
        # pool à la scène — pas un second parseur.
        from scripting.refactor import find_call_sites_in_project
        from scripting.api import DOMAIN_PREFAB
        by_script: dict = {}
        for site in find_call_sites_in_project(project, DOMAIN_PREFAB):
            if site.values.get(DOMAIN_PREFAB) == prefab.name:
                by_script.setdefault(str(site.path), []).append(site.line)
        if by_script:
            found = True
            self._add_group_row("↗", label('uses.spawned_by'), icons.COLOR_SCRIPT)
            for path, lines in by_script.items():
                for line in sorted(lines):
                    leaf = f"{Path(path).name} · {label('uses.spawn_line', line=line)}"
                    self._add_leaf_row(
                        leaf, lambda p=path, l=line: self.open_ref.emit(p, l))

        if not found:
            self._add_empty_row(label('uses.no_instance_in_the_project'))

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_action(self):
        if self._prefab:
            self.edit_requested.emit(self._prefab)

    def _on_close(self):
        """Renvoie à la vue précédente via le bus (re-sélectionne le prefab)."""
        if self._prefab:
            get_bus().select(self._prefab)


# ──────────────────────────────────────────────────────────────────
#  ScriptUsesInspector — liste des actors qui utilisent un script
# ──────────────────────────────────────────────────────────────────
class ScriptUsesInspector(_UsesInspectorBase):
    """
    Vue 'SCRIPT USES' — affiche toutes les scènes et actors
    qui ont un ScriptComponent pointant vers ce fichier script.

    Structure :
        ┌─ Header orange : nom du script  ──────── [v] ─┐
        │  SCRIPT USES              [Éditer le script]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(str)   # path du script

    _HEADER_COLOR = icons.COLOR_SCRIPT
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = label('uses.script_uses')
    _ACTION_BTN_TEXT = label('uses.edit_script')
    _ACTION_BTN_COLOR = icons.COLOR_SCRIPT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._script_path = None
        self._project     = None

    # ── Chargement ────────────────────────────────────────────────

    def load(self, script_path: str, project):
        self._script_path = script_path
        self._project     = project

        name = Path(script_path).name
        self._name_lbl.setText(name)
        self._clear_list()

        found_any = False

        # ── Acteurs placés dans une scène (inline ou instance de prefab) ──
        for scene in project.scenes:
            linked = [
                a for a in scene.actors
                if a.get_component("script") is not None
                and Path(a.get_component("script").script or "").name == name
            ]
            if not linked:
                continue
            found_any = True
            self._add_group_row("✦", scene.name, icons.COLOR_SCENE, count=len(linked))
            for actor in linked:
                self._add_leaf_row(actor.name, lambda a=actor: get_bus().select(a))

        # ── Prefabs (template — inclut les prefabs spawnés par script, jamais
        #    placés dans scene.actors, donc invisibles à la boucle ci-dessus) ──
        linked_prefabs = [
            pf for pf in project.prefabs
            if pf.get_component("script") is not None
            and Path(pf.get_component("script").script or "").name == name
        ]
        if linked_prefabs:
            found_any = True
            self._add_group_row("◆", label('common.prefabs'), icons.COLOR_PREFAB)
            for pf in linked_prefabs:
                self._add_leaf_row(pf.name, lambda p=pf: get_bus().select(p))

        # ── Scripts de scène (Scene.script — distinct des scripts d'actor) ──
        linked_scenes = [s for s in project.scenes if Path(s.script or "").name == name]
        if linked_scenes:
            found_any = True
            self._add_group_row("▤", label('uses.scene_scripts'), icons.COLOR_SCRIPT)
            for scene in linked_scenes:
                self._add_leaf_row(scene.name, lambda s=scene: get_bus().select(s))

        if not found_any:
            self._add_empty_row(label('uses.no_actor_uses_this_script'))

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_action(self):
        if self._script_path:
            self.edit_requested.emit(self._script_path)
