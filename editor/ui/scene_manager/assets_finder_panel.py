"""Panneau gauche (bas) du Scene Manager — ce que le PROJET contient.

Scènes, prefabs et scripts, rendus par le composant partagé
(`ui/common/asset_finder.py`) comme dans tous les autres écrans. Ce module ne
garde que ce qui est propre à CET écran : traduire une sélection en geste
(activer une scène, inspecter un prefab), et les entrées de menu qui supposent
un inspecteur en face (« Voir les instances », « Voir les utilisations »).

Le contenu de la scène active — acteurs et mise en page UI — vit dans
`scene_tree_panel.py`, au-dessus dans la même colonne.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenu, QFileDialog, QDialog
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QShortcut, QKeySequence

from ui.common.theme import QSS
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SCENES, PREFABS, SCRIPTS
from ui.common.labels import label
from ui.common.script_creation import show_add_script_menu

from core.project import Project
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher, unique_name
from core.keybindings import bind
# Source unique du dossier de projets par défaut (~/BackstageProjects) — ce module et
# window.py en avaient chacun une copie pointant vers le projects/ du repo :
# inexistant chez quelqu'un qui lance l'exe, et dans le dossier temporaire une
# fois figé.
from ui.home.project_picker import PROJECTS_DIR


class AssetsFinderPanel(QWidget):
    scene_selected        = pyqtSignal(int)      # INDEX dans project.scenes
    prefab_add_requested  = pyqtSignal()
    scene_add_requested   = pyqtSignal()
    script_opened         = pyqtSignal(str)
    project_created       = pyqtSignal(str, str, str)   # (name, path, starter_id)
    project_opened        = pyqtSignal(str)        # (path)
    prefab_uses_requested = pyqtSignal(object)     # Prefab
    script_uses_requested = pyqtSignal(str)        # chemin absolu du script
    scenes_selected       = pyqtSignal(list)       # noms de scènes sélectionnées (sync graphe)
    groups_changed        = pyqtSignal()           # un groupe de scènes a été créé (sync graphe)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._folder_store = None
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._finder = AssetFinder(label('assf.project_viewer'), [SCENES, PREFABS, SCRIPTS],
                                   min_width=180, max_width=420)
        root.addWidget(self._finder, 1)

        # Un changement de dossiers dans le finder (créer/grouper/déplacer/
        # renommer) doit rafraîchir le Graphe, qui lit le même store.
        self._finder.folders_changed.connect(self.groups_changed)
        self._finder.selected.connect(self._on_selected)
        self._finder.activated.connect(self._on_activated)
        self._finder.add_requested.connect(self._on_add_requested)
        # Sélection croisée avec le graphe : on ne relaie QUE la famille Scenes.
        self._finder.selection_changed.connect(self._on_selection_set)

        # Entrées de menu propres à cet écran : elles supposent un inspecteur
        # capable de les afficher, que seul le Scene Manager possède.
        # « Edit scene » ouvre la scène dans le canvas — même geste que le
        # double-clic (bascule), en pendant du « Edit scene » du Graphe.
        self._finder.add_action(SCENES.label, label("assf.edit_scene"),
                                lambda sc: self._on_activated(SCENES.label, sc))
        self._finder.add_action(PREFABS.label, label("assf.instantiate_prefab"),
                                lambda pf: get_dispatcher().instantiate_prefab(pf.name, 60, 60))
        self._finder.add_action(PREFABS.label, label("assf.edit_prefab"),
                                lambda pf: get_bus().select(pf))
        self._finder.add_action(PREFABS.label, label("assf.view_instances"),
                                self.prefab_uses_requested.emit)
        self._finder.add_action(SCRIPTS.label, label("assf.edit_script"),
                                lambda p: self.script_opened.emit(str(p)))
        self._finder.add_action(SCRIPTS.label, label("assf.view_uses"),
                                lambda p: self.script_uses_requested.emit(str(p)))

        # Ctrl+G : ranger les scènes sélectionnées dans un nouveau groupe. Le
        # raccourci vit dans le registre remappable ; il n'agit que si le finder
        # (ou un de ses enfants) a le focus — pas un raccourci global.
        self._sc_group = QShortcut(QKeySequence(), self)
        self._sc_group.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_group.activated.connect(self._group_selected_scenes)
        bind("scene.group", self._sc_group)

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, kind_label: str, obj):
        """Traduit « un asset a été choisi » dans le geste attendu de sa famille.

        Le clic simple INSPECTE, il n'ouvre pas : une scène se pose sur le bus,
        où son inspecteur la prend (il édite n'importe quelle scène, pas
        seulement l'active) — la BASCULE du canvas est réservée au double-clic
        (`_on_activated`). Prefab et script suivent la même règle : sur le bus,
        l'inspecteur les prend."""
        if kind_label == SCENES.label:
            get_bus().select(obj)     # -> SceneInspector, sans changer la scène active
        elif kind_label == PREFABS.label:
            get_bus().select(obj)
        elif kind_label == SCRIPTS.label:
            get_bus().select(obj)     # -> ScriptInspector (note + exports)

    def _on_activated(self, kind_label: str, obj):
        """Double-clic. Une scène s'OUVRE (le canvas bascule dessus, window.py la
        désigne par son index) ; un script s'ouvre dans l'éditeur ; un prefab
        s'édite."""
        if kind_label == SCENES.label:
            if self._project is not None and obj in self._project.scenes:
                self.scene_selected.emit(list(self._project.scenes).index(obj))
        elif kind_label == SCRIPTS.label:
            self.script_opened.emit(str(obj))
        elif kind_label == PREFABS.label:
            get_bus().select(obj)

    # ── Création ──────────────────────────────────────────────────

    def _on_add_requested(self, kind_label: str):
        if kind_label == SCENES.label:
            self._show_scene_add_menu()         # nouvelle scène, ou groupe
        elif kind_label == PREFABS.label:
            self._add_prefab()
        elif kind_label == SCRIPTS.label:
            self._show_add_script_menu()

    def _show_scene_add_menu(self):
        """« + » de la section Scenes : créer une scène, ou un groupe (dossier
        partagé avec les groupes du Graphe). Le groupe naît vide et renommable
        en place ; Ctrl+G le remplit d'une sélection existante."""
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.addAction(label("akind.new_scene"),
                       lambda: self.scene_add_requested.emit())   # window.py : reporte la scène active
        menu.addAction(label("assetfind.create_group"), self._create_scene_group)
        menu.exec(QCursor.pos())

    def _create_scene_group(self, member_names=()):
        """Crée un groupe de scènes (dossier de la famille), éventuellement
        peuplé, et l'ouvre en renommage en place. `groups_changed` prévient le
        Graphe, qui partage le même store."""
        if self._folder_store is None:
            return
        folder = self._folder_store.create_group(
            "scenes", label("assetfind.group_default_name"), list(member_names))
        self._finder.refresh()
        self.groups_changed.emit()
        if folder is not None:
            self._finder.begin_rename_folder(SCENES.label, folder.id)

    def _group_selected_scenes(self):
        """Ctrl+G : range les scènes SÉLECTIONNÉES dans un nouveau groupe. Sans
        sélection de scènes, ne fait rien — le geste opère sur ce qui est choisi."""
        names = [s.name for s in self._finder.selected_objs(SCENES.label)]
        if names:
            self._create_scene_group(names)

    def _add_prefab(self):
        if not self._project:
            return
        name = unique_name("Prefab", {p.name for p in self._project.prefabs})
        get_dispatcher().add_prefab(name)
        self.refresh()
        self.begin_rename_prefab(name)

    def _show_add_script_menu(self):
        """« + » de la section Scripts — menu partagé avec le Script finder. Le
        script créé est rafraîchi puis ouvert dans le Script Editor interne
        (window.open_script)."""
        show_add_script_menu(self, self._project, self._on_script_created)

    def _on_script_created(self, path: Path):
        self.refresh()
        self.script_opened.emit(str(path))

    # ── Renommage inline d'un asset fraîchement créé (pas de pop-up) ──

    def begin_rename_scene(self, name: str):
        self._begin_rename(SCENES.label, self._project.scenes.get(name) if self._project else None)

    def begin_rename_prefab(self, name: str):
        self._begin_rename(PREFABS.label, self._project.prefabs.get(name) if self._project else None)

    def _begin_rename(self, kind_label: str, obj):
        if obj is not None:
            self._finder.begin_rename(kind_label, obj)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)

    def _on_selection_set(self, kind_label: str, objs) -> None:
        """Relaie la sélection de scènes vers le graphe (highlight croisé)."""
        if kind_label == SCENES.label:
            self.scenes_selected.emit([s.name for s in objs])

    def highlight_scenes(self, names) -> None:
        """Surligne des scènes par nom — sélection venue du graphe. N'active pas.

        `fold_to_folder` : une scène rangée dans un groupe REPLIÉ ici (sa ligne
        n'est pas dépliée) reporte son surlignage sur le groupe — le panneau
        garde toujours un retour visuel de ce qui est sélectionné dans le graphe,
        même quand la scène elle-même est cachée."""
        if self._project is None:
            return
        wanted = set(names)
        objs = [s for s in self._project.scenes if s.name in wanted]
        self._finder.highlight_selection(SCENES.label, objs, fold_to_folder=True)

    def set_folder_store(self, store) -> None:
        """Active les dossiers d'auteur de la famille Scenes, adossés au store
        partagé (mêmes dossiers que les groupes du Graphe). Les scènes sont
        rangées par NOM — leur identité durable ; le renommage migre
        l'appartenance via le choke point `Project.rename_scene`."""
        from ui.common.asset_finder import FolderScheme
        self._folder_store = store
        fam = "scenes"
        scheme = FolderScheme(
            folders=lambda: store.folders(fam),
            create=lambda name, parent: store.create_folder(fam, name, parent),
            rename=lambda fid, name: store.rename_folder(fam, fid, name),
            delete=lambda fid: store.delete_folder(fam, fid),
            set_parent=lambda fid, parent: store.set_parent(fam, fid, parent),
            move=lambda scene, fid: store.move_member(fam, scene.name, fid),
            folder_of=lambda scene: store.folder_of(fam, scene.name),
            group=lambda scenes, parent: store.create_group(
                fam, label("assetfind.group_default_name"),
                [s.name for s in scenes], parent),
        )
        self._finder.set_folder_scheme(SCENES.label, scheme)

    def refresh(self):
        self._finder.refresh()

    def highlight_active_scene(self, scene) -> None:
        """Marque la scène ACTIVE (celle ouverte dans le canvas) d'un liseré
        gauche, distinct du remplissage de sélection — la scène active et la
        scène sélectionnée ne sont plus la même chose (cf. règle de design
        active/sélectionnée). Ne repeuple pas : la liste des scènes ne change
        pas quand on bascule de scène active (`window._on_scene_selected`), on ne
        fait que déplacer le liseré."""
        self._finder.set_active(SCENES.label, scene)

    def _refresh_scripts(self):
        # Une seule famille a bougé, mais tout repeupler coûte un parcours de
        # listes déjà en mémoire : pas de quoi se doter d'un chemin à part.
        self._finder.refresh()

    # ── Projets ───────────────────────────────────────────────────

    def _prompt_new(self):
        from ui.home.project_picker import NewProjectDialog
        dlg = NewProjectDialog(PROJECTS_DIR, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.project_created.emit(
                dlg.result_name, str(dlg.result_path), dlg.result_starter)

    def _prompt_open(self):
        path = QFileDialog.getExistingDirectory(self, label("assf.open_project"), str(PROJECTS_DIR))
        if path:
            self.project_opened.emit(path)

    @property
    def project(self) -> Project:
        return self._project
