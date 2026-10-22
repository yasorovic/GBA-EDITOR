"""
PrefabUsesInspector.

La vue "Voir les utilisations" d'un prefab, affichée dans l'inspector. Sa base
(`ui/common/uses_list.py`) est partagée avec la vue des utilisations d'un script, qui vit dans
le Script Editor (`ui/script_editor/script_uses_panel.py`).
"""
from __future__ import annotations
from ui.common.labels import label
from pathlib import Path

from PyQt6.QtCore import pyqtSignal

from core.selection_bus import get_bus
from ui.common import icons


from ui.common.uses_list import UsesListBase


# ──────────────────────────────────────────────────────────────────
#  PrefabUsesInspector — liste des instances d'un prefab par scène
# ──────────────────────────────────────────────────────────────────
class PrefabUsesInspector(UsesListBase):
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
        # rien exécuter. Même lecture que celle qui *propose* le
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
