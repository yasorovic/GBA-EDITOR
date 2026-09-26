"""UINodeInspector — le nœud `Interface` lui-même (l'asset `UILayout`).

Le nœud porte le CHEMIN MATÉRIEL de tout son sous-arbre (v0.25) : un ancrage
(screen / world / actor) et une cible (BG / OBJ), source de vérité unique dont
chaque élément hérite. C'est ce que le clic sur la racine « Interface » de
l'arbre de scène ouvre — là où il ne faisait rien avant.

Séparé de `UIInspector` (qui édite un ÉLÉMENT) pour la même raison que le modèle
a remonté ces deux champs de l'élément vers le nœud : un réglage posé une fois,
au bon endroit, plutôt que répété — et faussement éditable — sur chaque élément.

Le nom se change dans l'EN-TÊTE (`AssetHeaderBar`, cf. DynamicInspector), comme
scène / acteur / élément : pas de champ « Name » ici.

Ce que l'inspecteur DIT et ne laisse pas deviner :
  • la cible n'est pas un menu quand elle est contrainte — ancrage actor, ou
    scène bitmap → OBJ : le champ affiche la valeur ET sa raison ;
  • un ancrage actor sans acteur choisi tombe à l'origine de l'écran ;
  • le nœud est un ASSET partagé — l'éditer touche N scènes, dit en couleur.
"""
from __future__ import annotations
from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QScrollArea,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.project import Project
from core.models.ui_region import (
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, TARGET_BG, TARGET_OBJ,
    forced_target,
)
from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W, CollapsibleCard
from ui.common.notice import note

_ANCHORS = [
    (ANCHOR_SCREEN, 'uinode.screen_fixed'),
    (ANCHOR_WORLD,  'uinode.world_scrolls'),
    (ANCHOR_ACTOR,  'uinode.actor_follows'),
]
_TARGETS = [(TARGET_BG, 'uinode.background_bg'), (TARGET_OBJ, 'uinode.sprite_obj')]


class UINodeInspector(QWidget):
    """Édite l'ancrage + la cible d'un nœud `Interface` (asset `UILayout`)."""
    changed = pyqtSignal()
    renamed = pyqtSignal(str)     # relayé à l'en-tête (renommage venu d'ailleurs)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = None
        self._scene = None
        self._project: Optional[Project] = None
        self._blocking = False

        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        L = QVBoxLayout(inner)
        L.setContentsMargins(8, 8, 8, 8)
        L.setSpacing(10)
        scroll.setWidget(inner)

        # ── Portée (asset partagé) ────────────────────────────────
        self._name_lbl = note(L, "ui.layout.name")
        self._shared = note(L, "ui.layout.shared")

        # ── Chemin matériel ───────────────────────────────────────
        card = CollapsibleCard(label('uinode.hardware_path'))
        self._anchor = QComboBox()
        self._anchor.setFont(QFont(T.UI, T.MD))
        self._anchor.setStyleSheet(QSS.combobox)
        for _, lab in _ANCHORS:
            self._anchor.addItem(label(lab))
        self._anchor.currentIndexChanged.connect(self._on_anchor)
        W.row(label('uinode.anchor'), self._anchor, card.body_layout)

        self._actor = QComboBox()
        self._actor.setFont(QFont(T.UI, T.MD))
        self._actor.setStyleSheet(QSS.combobox)
        self._actor.currentIndexChanged.connect(self._on_actor)
        self._actor_row = W.row(label('common.actor'), self._actor, card.body_layout).parentWidget()

        self._target = QComboBox()
        self._target.setFont(QFont(T.UI, T.MD))
        self._target.setStyleSheet(QSS.combobox)
        for _, lab in _TARGETS:
            self._target.addItem(label(lab))
        self._target.currentIndexChanged.connect(self._on_target)
        self._target_row = W.row(label('uinode.target'), self._target, card.body_layout).parentWidget()

        # Slot BG du NŒUD (v0.12) — par instance dans la scène, pas sur l'asset :
        # un HUD partagé peut vivre sur BG0 ici et BG2 ailleurs. N'a de sens qu'en
        # cible BG (masqué en OBJ) ; le combo ne liste que les slots permis par le
        # mode vidéo (d'où bitmap → BG2 seul).
        self._bg_slot = QComboBox()
        self._bg_slot.setFont(QFont(T.UI, T.MD))
        self._bg_slot.setStyleSheet(QSS.combobox)
        self._bg_slot.currentIndexChanged.connect(self._on_bg_slot)
        self._bg_slot_row = W.row(label('uinode.bg_slot'), self._bg_slot, card.body_layout).parentWidget()

        # La raison quand la cible est IMPOSÉE (actor / bitmap), et l'alerte quand
        # un ancrage actor n'a pas d'acteur — chacune sous le réglage qui la cause.
        self._frame_why = note(card.body_layout)
        self._anchor_why = note(card.body_layout, "ui.anchor.no_actor")
        L.addWidget(card)
        L.addStretch(1)

    # ── Chargement ────────────────────────────────────────────────
    def load(self, layout, scene, project: Project):
        self._layout, self._scene, self._project = layout, scene, project
        # Le NŒUD de CETTE scène qui référence l'asset — c'est lui qui porte
        # `bg_slot` (cf. InterfaceNode). Le premier qui le cite : un même layout
        # posé deux fois dans une scène est une collision que le validateur
        # interdit, on n'a donc jamais à choisir entre deux.
        self._node = next((n for n in getattr(scene, "ui_layouts", []) or []
                           if n.layout_name == layout.name), None) if scene else None
        self._blocking = True
        try:
            users = project.ui_layout_users(layout.name) if project else []
            self._name_lbl.show_text(name=layout.name)
            if len(users) > 1:
                self._shared.show_text(n=len(users))
            else:
                self._shared.clear()
            self._reload_actors()
            self._sync()
        finally:
            self._blocking = False

    def _render_mode(self) -> int:
        return int(getattr(self._scene, "render_mode", 0) or 0)

    def _reload_actors(self):
        self._actor.clear()
        names = [a.name for a in getattr(self._scene, "actors", [])] if self._scene else []
        anchor = getattr(self._layout, "anchor", ANCHOR_SCREEN)
        actor = getattr(self._layout, "anchor_actor", "")
        # Placeholder EN TÊTE tant qu'aucun acteur n'est choisi. Sans lui, le
        # combo AFFICHAIT le premier acteur alors que le modèle est vide — et
        # re-choisir l'item déjà montré n'émet aucun `currentIndexChanged`, donc
        # sur une scène à UN seul acteur le nœud ne pouvait JAMAIS obtenir son
        # ancre : `anchor_actor` restait "" en silence. On sépare l'affichage du
        # modèle : `data` porte le nom (ou "" pour le placeholder), lu par `_on_actor`.
        if not names:
            self._actor.addItem(label('uinode.no_actor'), "")
        else:
            if not actor:
                self._actor.addItem(label('uinode.choose_an_actor'), "")
            for nm in names:
                self._actor.addItem(nm, nm)
        self._anchor.setCurrentIndex(
            next((i for i, (a, _) in enumerate(_ANCHORS) if a == anchor), 0))
        j = self._actor.findData(actor) if actor else -1
        self._actor.setCurrentIndex(j if j >= 0 else 0)
        self._actor_row.setVisible(anchor == ANCHOR_ACTOR)

    def _sync(self):
        """Verrouille la cible et en DIT la raison — une contrainte muette se lit
        comme un bug."""
        lay, rm = self._layout, self._render_mode()
        anchor = getattr(lay, "anchor", ANCHOR_SCREEN)
        forced = forced_target(anchor, rm)
        eff = lay.resolved_target(None, rm)
        self._target.setCurrentIndex(
            next((i for i, (t, _) in enumerate(_TARGETS) if t == eff), 0))
        self._target.setEnabled(forced is None)
        if forced:
            # Deux raisons matérielles, deux messages distincts (cf. le modèle) —
            # une raison qui se compose à l'exécution ne se traduit pas.
            self._frame_why.show_text(
                "ui.anchor.forced_actor" if anchor == ANCHOR_ACTOR
                else "ui.anchor.forced_bitmap", mode=rm)
        else:
            self._frame_why.clear()
        if anchor == ANCHOR_ACTOR and not getattr(lay, "anchor_actor", ""):
            self._anchor_why.show_text()
        else:
            self._anchor_why.clear()
        self._sync_bg_slot(eff, rm)

    def _sync_bg_slot(self, eff_target: str, rm: int):
        """Le slot BG n'a de sens qu'en cible BG : masqué en OBJ. Le combo ne liste
        que les slots permis par le mode vidéo ; le `bg_slot` du nœud est ramené
        dans cette liste s'il n'y est pas (mode changé sous ses pieds)."""
        from ui.scene_manager.inspectors.scene_inspector import MODE_INFO
        node = getattr(self, "_node", None)
        show = (eff_target == TARGET_BG) and node is not None
        self._bg_slot_row.setVisible(show)
        if not show:
            return
        allowed = list(MODE_INFO.get(rm, MODE_INFO[0])["bg_slots"])
        self._bg_slot.blockSignals(True)
        self._bg_slot.clear()
        for s in allowed:
            self._bg_slot.addItem(f"BG{s}", s)
        cur = int(getattr(node, "bg_slot", allowed[0]))
        j = self._bg_slot.findData(cur)
        self._bg_slot.setCurrentIndex(j if j >= 0 else 0)
        self._bg_slot.blockSignals(False)

    # ── Écriture ──────────────────────────────────────────────────
    def _set(self, field: str, value, label: str):
        from core.history import get_history, SetFieldCmd
        old = getattr(self._layout, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(self._layout, field, old, value,
                                       label=label, persist_fn=self._persist))

    def _persist(self):
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def rename(self, new_name: str) -> str:
        """Renomme le nœud — appelé par l'EN-TÊTE. Tout le travail (unicité,
        refs des scènes, fichier) est dans `Project.rename_ui_layout`."""
        lay = self._layout
        if lay is None or not self._project:
            return ""
        old = lay.name
        applied = self._project.rename_ui_layout(lay, new_name)
        if applied != old:
            self.renamed.emit(applied)
        return applied

    def _on_anchor(self, i):
        if self._blocking or self._layout is None:
            return
        self._set("anchor", _ANCHORS[i][0], "Interface anchor")
        self._blocking = True
        try:
            self._reload_actors()
            self._sync()
        finally:
            self._blocking = False

    def _on_actor(self, i):
        if self._blocking or self._layout is None or i < 0:
            return
        # `data`, pas `currentText` : le placeholder « — choose an actor — » porte
        # "" et ne doit rien écrire ; un acteur réel porte son nom.
        name = self._actor.currentData()
        if not name:
            return
        self._set("anchor_actor", name, "Interface actor")
        self._sync()

    def _on_target(self, i):
        if self._blocking or self._layout is None:
            return
        self._set("target", _TARGETS[i][0], "Interface target")

    def _on_bg_slot(self, i):
        node = getattr(self, "_node", None)
        if self._blocking or node is None or i < 0:
            return
        slot = self._bg_slot.currentData()
        if slot is None or int(slot) == int(getattr(node, "bg_slot", -1)):
            return
        from core.history import get_history, SetFieldCmd
        get_history().push(SetFieldCmd(node, "bg_slot", int(node.bg_slot), int(slot),
                                       label="Interface BG slot", persist_fn=self._persist))
