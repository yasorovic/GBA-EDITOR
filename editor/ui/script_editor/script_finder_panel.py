"""ui/script_editor/script_finder_panel.py — colonne droite du Script Editor.

Trois sections empilées : l'arbre des scripts du projet, puis les constantes et
les globales. Seule la première liste des ASSETS — elle est donc rendue par le
composant partagé (`ui/common/asset_finder.py`), comme dans tous les autres
écrans. Les deux autres ne listent pas des fichiers mais des variables déclarées
dans le projet, avec leur type et leur valeur : elles gardent leur table.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal

from ui.common.widgets import FinderSection
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SCRIPTS
from ui.common.labels import label
from ui.common.script_creation import show_add_script_menu
from .colors import _BG
from .var_table_panel import VarTablePanel


class ScriptFinderPanel(QWidget):
    """Colonne « étirable » bornée min/max, même modèle que les autres finders."""

    file_requested    = pyqtSignal(str)   # chemin absolu du .lua à ouvrir
    snippet_requested = pyqtSignal(str)   # snippet à insérer dans l'éditeur

    _COL_MIN = 220
    _COL_MAX = 420

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self.setStyleSheet(f"background:{_BG};")
        self.setMinimumWidth(self._COL_MIN)
        self.setMaximumWidth(self._COL_MAX)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scripts (composant partagé — il porte le bandeau d'identité) ──
        # Un simple clic ouvre : dans CET écran, choisir un script et l'éditer
        # sont le même geste. Ailleurs (Project viewer) la sélection ne fait
        # que peupler l'inspecteur, d'où deux signaux distincts.
        self._scripts = AssetFinder(label('scrfind.script_finder'), [SCRIPTS],
                                    min_width=self._COL_MIN, max_width=self._COL_MAX)
        self._scripts.selected.connect(lambda _kind, p: self.file_requested.emit(str(p)))
        # « + » : même menu que le Project viewer (script seul / behavior).
        self._scripts.add_requested.connect(
            lambda _label: show_add_script_menu(self, self._project, self._on_script_created))
        root.addWidget(self._scripts, 1)
        # Les deux sections ci-dessous rejoignent la MÊME colonne défilante que
        # les scripts : posées à côté, elles flotteraient en bas du panneau.

        # ── Constantes / globales — PAS des assets : des variables typées,
        #    avec leur valeur. Leur table reste. ────────────────────────
        sec_const = FinderSection(label("vartbl.constants"))
        self._constants_panel = VarTablePanel(kind="const")
        self._constants_panel.snippet_requested.connect(self.snippet_requested)
        sec_const.set_widget(self._constants_panel)
        sec_const.add_clicked.connect(self._constants_panel._add_var)
        self._scripts.add_section(sec_const)

        sec_globals = FinderSection(label("vartbl.globals"))
        self._globals_panel = VarTablePanel(kind="global")
        self._globals_panel.snippet_requested.connect(self.snippet_requested)
        sec_globals.set_widget(self._globals_panel)
        sec_globals.add_clicked.connect(self._globals_panel._add_var)
        self._scripts.add_section(sec_globals)

    # ── API publique ──────────────────────────────────────────────────

    def set_project(self, project):
        self._project = project
        self._scripts.load_project(project)
        self._constants_panel.set_project(project)
        self._globals_panel.set_project(project)

    def _on_script_created(self, path: Path):
        self._scripts.refresh()
        self.highlight_file(path)
        self.file_requested.emit(str(path))

    def set_root(self, _scripts_dir: Path = None):
        """Repeuple l'arbre. Le dossier n'est plus un paramètre — la famille
        SCRIPTS lit `project.scripts_dir` elle-même ; l'argument reste accepté
        pour les appelants qui le passent encore."""
        self._scripts.refresh()

    def highlight_file(self, path: Path):
        self._scripts.select(SCRIPTS.label, Path(path))
