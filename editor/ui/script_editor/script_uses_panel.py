"""
ui/script_editor/script_uses_panel.py — « Voir les utilisations » d'un script.

Remplace la colonne droite du Script Editor (la bibliothèque de scripts) le temps de la
consultation : les scènes, prefabs et scripts de scène qui pointent le fichier. La vue ne
navigue pas elle-même : elle dit QUELLE cible, la fenêtre bascule sur le Scene Manager.
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import pyqtSignal

from ui.common import icons
from ui.common.labels import label
from ui.common.uses_list import UsesListBase


class ScriptUsesPanel(UsesListBase):
    """
    Vue 'SCRIPT USES', colonne droite du Script Editor : toutes les scènes et acteurs
    qui ont un ScriptComponent pointant vers ce fichier script. Un clic sur une ligne demande
    à la fenêtre d'aller l'y sélectionner (`target_requested`) ; « v » revient à la bibliothèque.

    Structure :
        ┌─ Header orange : nom du script  ──────── [v] ─┐
        │  SCRIPT USES              [Éditer le script]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        └────────────────────────────────────────────────┘
    """
    edit_requested   = pyqtSignal(str)      # path du script
    target_requested = pyqtSignal(object)   # Actor | Prefab | Scene qui utilise le script
    close_requested  = pyqtSignal()

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
                self._add_leaf_row(actor.name, lambda a=actor: self.target_requested.emit(a))

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
                self._add_leaf_row(pf.name, lambda p=pf: self.target_requested.emit(p))

        # ── Scripts de scène (Scene.script — distinct des scripts d'actor) ──
        linked_scenes = [s for s in project.scenes if Path(s.script or "").name == name]
        if linked_scenes:
            found_any = True
            self._add_group_row("▤", label('uses.scene_scripts'), icons.COLOR_SCRIPT)
            for scene in linked_scenes:
                self._add_leaf_row(scene.name, lambda s=scene: self.target_requested.emit(s))

        if not found_any:
            self._add_empty_row(label('uses.no_actor_uses_this_script'))

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_action(self):
        if self._script_path:
            self.edit_requested.emit(self._script_path)

    def _on_close(self):
        self.close_requested.emit()
