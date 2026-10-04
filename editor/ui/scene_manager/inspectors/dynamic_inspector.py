"""DynamicInspector — remplace le QTabWidget Scene/Actor, route vers le bon panneau."""
from __future__ import annotations

from ui.common.labels import label
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T
from .actor_inspector import ActorInspector
from .scene_inspector import SceneInspector
from .camera_inspector import CameraInspector
from .project_inspector import ProjectInspector
from .script_inspector import ScriptInspector
from .ui_inspector import UIInspector
from .ui_node_inspector import UINodeInspector
from .uses_inspectors import PrefabUsesInspector, ScriptUsesInspector
from .edge_inspector import EdgeInspector
from .group_inspector import GroupInspector
from .graph_note_inspector import GraphNoteInspector


class DynamicInspector(QWidget):
    """
    Inspector contextuel sans onglets.
    Affiche automatiquement le bon panneau selon la selection :
      - rien        → message d'aide
      - scene       → SceneInspector (nom + BG slots)
      - actor       → ActorInspector (transform + components)
      - prefab      → ActorInspector (components seulement)
      - prefab uses → PrefabUsesInspector
    """
    changed       = pyqtSignal()
    actor_changed = pyqtSignal(object)   # Actor | None — payload propre pour window.py
    # Une zone éditée ou supprimée doit être redessinée dans le canvas : `changed`
    # est trop général (il est aussi émis par la scène et les actors).
    ui_regions_changed = pyqtSignal()
    # Relayé depuis SceneInspector : un réglage de mélange demande au canvas de
    # recomposer ses pixmaps (cf. SceneEditor.refresh_blend).
    blend_changed = pyqtSignal()
    slot_assigned = pyqtSignal(int, str)
    # Relayé depuis CameraInspector : position/frame édités dans l'inspecteur
    # (pas par drag canvas) — le canvas doit suivre (cf. window.py).
    camera_moved = pyqtSignal(object)   # Camera
    edge_presentation_changed = pyqtSignal(object)
    edge_script_changed = pyqtSignal()
    groups_changed = pyqtSignal()

    _MODE_EMPTY       = 0
    _MODE_SCENE       = 1
    _MODE_ACTOR       = 2
    _MODE_CAMERA      = 3
    _MODE_PREFAB_USES = 4
    _MODE_SCRIPT_USES = 5
    _MODE_PROJECT     = 6
    _MODE_SCRIPT      = 7
    _MODE_UI          = 8
    _MODE_UI_NODE     = 9
    _MODE_EDGE        = 10
    _MODE_GROUP       = 11
    _MODE_GRAPH_NOTE  = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None   # mis à jour via set_project()
        self._graph_state = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        # Plancher mesuré : le contenu des inspecteurs de scène (≈ 274 px) et
        # d'interface (≈ 291 px) ne rétrécit pas plus, et la barre horizontale
        # est coupée — sous ce seuil le séparateur rognait les champs sans
        # recours. 200 les laissait coupés dès l'ouverture.
        self.setMinimumWidth(300)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Bandeau contextuel coloré — composant partagé (voir ui/common/widgets.py),
        # même template/couleurs/renommage que Sprite Editor, Sound Mixer, Script Editor.
        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_header_rename)
        self._header_mode = "empty"
        main.addWidget(self._header)

        self._stack = QStackedWidget()
        main.addWidget(self._stack, 1)

        # 0 — vide
        empty_w = QWidget()
        empty_w.setStyleSheet(f"background:{C.BG_PANEL};")
        el = QVBoxLayout(empty_w)
        hint = QLabel(label('dyninsp.empty'))
        hint.setFont(QFont(T.UI, T.MD))
        hint.setStyleSheet(f"color:{C.BORDER_MID};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addStretch(); el.addWidget(hint); el.addStretch()
        self._stack.addWidget(empty_w)

        # Démarrage paresseux — MÊME schéma que window._build_screens. Les 9
        # inspecteurs contextuels sont lourds à CONSTRUIRE (leurs widgets, puis
        # leur polish au premier show), mais un seul est visible à la fois. On ne
        # monte ici qu'un placeholder par mode, à l'index == mode ; le vrai
        # inspecteur — et son câblage de signaux — naît à sa première venue via
        # `_ensure`. C'est l'essentiel du coût de construction de la fenêtre et
        # de son premier paint qui sort ainsi du chemin de démarrage.
        self._factories = {
            self._MODE_SCENE:       self._make_scene,
            self._MODE_ACTOR:       self._make_actor,
            self._MODE_CAMERA:      self._make_camera,
            self._MODE_PREFAB_USES: self._make_prefab_uses,
            self._MODE_SCRIPT_USES: self._make_script_uses,
            self._MODE_PROJECT:     self._make_project,
            self._MODE_SCRIPT:      self._make_script,
            self._MODE_UI:          self._make_ui,
            self._MODE_UI_NODE:     self._make_ui_node,
            self._MODE_EDGE:        self._make_edge,
            self._MODE_GROUP:       self._make_group,
            self._MODE_GRAPH_NOTE:  self._make_graph_note,
        }
        self._placeholders: dict[int, QWidget] = {}
        for _mode in self._factories:            # 1..9, dans l'ordre → index == mode
            ph = QWidget()
            self._placeholders[_mode] = ph
            self._stack.addWidget(ph)

        # Références des inspecteurs — None tant que non construits.
        self._scene_insp = None
        self._actor_insp = None
        self._camera_insp = None
        self._uses_insp = None
        self._script_uses_insp = None
        self._project_insp = None
        self._script_insp = None
        self._ui_insp = None
        self._ui_node_insp = None
        self._edge_insp = None
        self._group_insp = None
        self._graph_note_insp = None

        # Injecté par window.py AVANT toute construction d'inspecteur : mémorisé
        # ici, appliqué par les fabriques concernées à la naissance de leur
        # inspecteur (cf. set_script_open_fn).
        self._script_open_fn = None
        self._current_script_path = None   # utilisé par _on_header_rename

        self._stack.setCurrentIndex(self._MODE_EMPTY)

        from core.selection_bus import get_bus
        get_bus().changed.connect(self.on_selection)

    # ── Démarrage paresseux des sous-inspecteurs ─────────────────
    #
    # Une fabrique par mode : elle CONSTRUIT l'inspecteur, branche ses signaux
    # une seule fois, applique le callback d'ouverture de script s'il est déjà
    # connu, et le mémorise dans son attribut `self._X_insp`. `_ensure` la
    # déclenche à la première venue du mode et substitue le vrai widget au
    # placeholder, à l'index inchangé (== mode).

    def _ensure(self, mode: int) -> None:
        ph = self._placeholders.pop(mode, None)
        if ph is None:
            return   # déjà construit, ou mode sans fabrique (EMPTY)
        real = self._factories[mode]()
        self._stack.removeWidget(ph)
        ph.deleteLater()
        self._stack.insertWidget(mode, real)

    def _make_scene(self) -> QWidget:
        insp = SceneInspector()
        insp.changed.connect(self.changed)
        insp.slot_assigned.connect(self.slot_assigned)
        insp.edit_prefab_requested.connect(
            lambda prefab: self.show_prefab(prefab, self._project))
        insp.open_ref.connect(
            lambda path, line: self._script_open_fn(path, line)
            if self._script_open_fn else None)
        # Le nom de la scène peut changer via un rename interne (`changed`) :
        # tenir l'en-tête à jour. Branché ICI, une fois — `show_scene` empilait
        # auparavant une connexion identique à chaque appel.
        insp.changed.connect(
            lambda: self._header.set_name(insp._scene.name if insp._scene else ""))
        if self._script_open_fn:
            insp.set_script_open_fn(self._script_open_fn)
        self._scene_insp = insp
        return insp

    def _make_actor(self) -> QWidget:
        insp = ActorInspector()
        insp.changed.connect(self._on_actor_insp_changed)
        insp._script_open_fn = self._script_open_fn
        self._actor_insp = insp
        return insp

    def _make_camera(self) -> QWidget:
        insp = CameraInspector()
        insp.changed.connect(self.changed)
        insp.camera_moved.connect(self.camera_moved)
        if self._script_open_fn:
            insp.set_script_open_fn(self._script_open_fn)
        self._camera_insp = insp
        return insp

    def _make_prefab_uses(self) -> QWidget:
        insp = PrefabUsesInspector()
        insp.edit_requested.connect(lambda p: self.show_prefab(p, self._project))
        # Sauter au script à la ligne exacte du spawn — même callback que les
        # autres inspecteurs (window.open_script(path, line)).
        insp.open_ref.connect(
            lambda path, line: self._script_open_fn(path, line)
            if self._script_open_fn else None)
        self._uses_insp = insp
        return insp

    def _make_script_uses(self) -> QWidget:
        insp = ScriptUsesInspector()
        insp.edit_requested.connect(self._on_script_edit_requested)
        self._script_uses_insp = insp
        return insp

    def _make_project(self) -> QWidget:
        insp = ProjectInspector()
        self._project_insp = insp
        return insp

    def _make_script(self) -> QWidget:
        insp = ScriptInspector()
        self._script_insp = insp
        return insp

    def _make_ui(self) -> QWidget:
        insp = UIInspector()
        insp.changed.connect(self.changed)
        insp.changed.connect(self.ui_regions_changed)
        # Un renommage venu d'AILLEURS que l'en-tête (arbre, canvas) doit s'y
        # refléter : l'en-tête est désormais le seul endroit qui montre le nom.
        insp.renamed.connect(self._header.set_name)
        self._ui_insp = insp
        return insp

    def _make_ui_node(self) -> QWidget:
        insp = UINodeInspector()
        insp.changed.connect(self.changed)
        insp.changed.connect(self.ui_regions_changed)
        insp.renamed.connect(self._header.set_name)
        self._ui_node_insp = insp
        return insp

    def _make_edge(self) -> QWidget:
        insp = EdgeInspector()
        insp.set_graph_state(self._graph_state)
        insp.style_changed.connect(self.edge_presentation_changed)
        insp.script_changed.connect(self.edge_script_changed)
        # Sauter au script à la ligne exacte de l'appel — même callback que les
        # autres inspecteurs (window.open_script(path, line)).
        insp.open_ref.connect(
            lambda ref: self._script_open_fn(ref.path, ref.line)
            if self._script_open_fn else None)
        self._edge_insp = insp
        return insp

    def _make_group(self) -> QWidget:
        insp = GroupInspector()
        insp.changed.connect(self.groups_changed)
        self._group_insp = insp
        return insp

    def _make_graph_note(self) -> QWidget:
        insp = GraphNoteInspector()
        insp.changed.connect(self.groups_changed)  # même redessin éditorial du graphe
        self._graph_note_insp = insp
        return insp

    def _on_actor_insp_changed(self):
        """Relaye changed ET émet actor_changed(actor) avec le payload explicite."""
        self.changed.emit()
        self.actor_changed.emit(self._actor_insp._actor)

    # ── Helpers header ───────────────────────────────────────────

    # Kinds dont le NOM se change dans l'en-tête. Les éléments d'interface en
    # font partie depuis que leur inspecteur n'a plus de champ « Name » : le nom
    # se change là où il s'affiche, comme pour une scène ou un acteur.
    _RENAMABLE = ("scene", "actor", "prefab", "camera", "script_asset",
                  "ui_text", "ui_container", "ui_list", "ui_image", "ui_element",
                  "ui_layout")

    def _set_header(self, kind: str, type_text: str, name_text: str, editable=None):
        if editable is None:
            editable = kind in self._RENAMABLE
        self._header.set_header(kind, type_text, name_text, editable=editable)
        self._header_mode = kind

    def _on_header_rename(self, new_name: str):
        if self._header_mode == "scene":
            scene = self._scene_insp._scene
            project = self._scene_insp._project
            if scene and project and new_name != scene.name:
                project.rename_scene(scene, new_name)
                self._header.set_name(scene.name)
                self._scene_insp.changed.emit()
        elif self._header_mode in ("actor", "prefab"):
            actor = self._actor_insp._actor
            project = self._actor_insp._project
            if actor and new_name != actor.name:
                if self._actor_insp._is_prefab_template:
                    project.rename_prefab(actor, new_name)
                else:
                    # rename_actor s'occupe des actor:get("…") des scripts et
                    # du message de statut ; _persist() sauve la scène + les
                    # sprites du canvas.
                    project.rename_actor(actor, new_name)
                    self._actor_insp._persist()
                    from core.command_dispatcher import get_dispatcher
                    get_dispatcher()._emit("actors_list_changed")
                self._header.set_name(actor.name)
        elif self._header_mode == "camera":
            cam = self._camera_insp._camera
            scene = self._camera_insp._scene
            project = self._camera_insp._project
            if cam and scene and project and new_name != cam.name:
                # Collision project-wide refusée en silence par rename_camera
                # (cf. Project.rename_camera) : cam.name reste inchangé si
                # refusé, l'en-tête ré-affiche donc l'ancien nom tel quel.
                project.rename_camera(scene, cam, new_name)
                self._header.set_name(cam.name)
                self._camera_insp._refresh()
        elif self._header_mode == "ui_layout":
            # Le NŒUD Interface (l'asset), pas un de ses éléments — sa route de
            # renommage est distincte (fichier + refs des scènes).
            applied = self._ui_node_insp.rename(new_name)
            if applied:
                self._header.set_name(applied)
        elif self._header_mode.startswith("ui_"):
            # `rename` rend le nom RÉELLEMENT appliqué : une collision d'unicité
            # est résolue par le modèle, et l'en-tête doit montrer ce qui a été
            # écrit, pas ce qui a été tapé.
            applied = self._ui_insp.rename(new_name)
            if applied:
                self._header.set_name(applied)
        elif self._header_mode == "script_asset":
            path = self._current_script_path
            if not path or not path.exists():
                return
            new_stem = new_name.strip()
            if not new_stem or new_stem == path.stem:
                self._header.set_name(path.name)
                return
            new_path = path.parent / f"{new_stem}{path.suffix}"
            if new_path.exists():
                self._header.set_name(path.name)
                return
            from core.history import get_history, RenameFileCmd
            from core.command_dispatcher import get_dispatcher

            def _refresh():
                current = new_path if new_path.exists() else path
                self._current_script_path = current
                self._header.set_name(current.name)
                self._script_insp.load(current)
                get_dispatcher().notify_scripts_changed()

            get_history().push(RenameFileCmd(path, new_path, _refresh))

    # ── API publique ─────────────────────────────────────────────

    def set_project(self, project):
        """Appelé par MainWindow à chaque ouverture/changement de projet."""
        self._project = project

    def set_graph_state(self, state) -> None:
        """Partage le sidecar du graphe avec l'inspecteur de transition."""
        self._graph_state = state
        if self._edge_insp is not None:
            self._edge_insp.set_graph_state(state)

    def on_selection(self, obj):
        """Reçu du bus — afficher le bon panneau selon le type de l'objet."""
        from pathlib import Path as _P
        from core.models.scene import Actor, Prefab, Scene
        from core.selection_bus import (
            BackgroundLayerSelection, CameraSelection, UIRegionSelection, UILayoutSelection,
            ActorSelection)
        if obj is None:
            # Mode par défaut : aperçu du projet (pas le message d'aide vide) —
            # cf. clic hors de la zone active du canvas.
            self.show_project()
        elif isinstance(obj, UILayoutSelection):
            self.show_ui_node(obj.layout, obj.scene, self._project)
        elif isinstance(obj, UIRegionSelection):
            self.show_ui_element(obj.layout, obj.element, self._project)
        elif isinstance(obj, CameraSelection):
            # Clic sur l'ICÔNE caméra spécifiquement (cf. CameraItem.shape() —
            # le rectangle de vue 240×160 n'est qu'un retour visuel, il ne
            # déclenche jamais ce marqueur) → inspecteur caméra.
            self.show_camera(obj.scene, obj.camera, self._project)
        elif isinstance(obj, BackgroundLayerSelection):
            self.show_scene(obj.scene, self._project)
            self._scene_insp.focus_background_slot(obj.bg_slot)
        elif isinstance(obj, ActorSelection):
            scene = self._project.active_scene if self._project else None
            if obj.active:
                self.show_actor(obj.active, self._project, scene)
        elif isinstance(obj, Actor):
            scene = self._project.active_scene if self._project else None
            self.show_actor(obj, self._project, scene)
        elif isinstance(obj, Scene):
            # Sélection générique de la scène (clic vide dans la zone active du
            # canvas) → son propre inspecteur, comme Actor/Prefab.
            self.show_scene(obj, self._project)
        elif isinstance(obj, Prefab):
            self.show_prefab(obj, self._project)
        elif isinstance(obj, _P):
            # Un script (.lua) sélectionné dans le Project Viewer — pas de
            # Resource dédiée, un simple chemin de fichier sur le bus.
            self.show_script(obj, self._project)

    def show_ui_element(self, layout_asset, element, project):
        """Élément d'UI (texte, conteneur, image) → l'inspecteur adaptatif. Le
        bandeau prend le kind exact (même famille bleue Interface, titre par
        type) et devient l'endroit où le nom se change."""
        from core.models.ui_region import (
            KIND_CONTAINER, KIND_LIST, KIND_TEXT, KIND_IMAGE)
        kind = getattr(element, "kind", KIND_TEXT)
        scene = project.active_scene if project else None
        self._ensure(self._MODE_UI)
        self._ui_insp.load(layout_asset, element, project, scene)
        header_kind, title = {
            KIND_CONTAINER: ("ui_container", label('common.container')),
            KIND_LIST:  ("ui_list",  label('common.list')),
            KIND_TEXT:  ("ui_text",  label('common.text')),
            KIND_IMAGE: ("ui_image", label('common.image')),
        }.get(kind, ("ui_element", label('dyninsp.ui_element')))
        self._set_header(header_kind, title, element.name)
        self._stack.setCurrentIndex(self._MODE_UI)

    def show_ui_region(self, layout_asset, region, project):
        """Alias historique — même route que tout élément d'UI."""
        self.show_ui_element(layout_asset, region, project)

    def show_ui_node(self, layout, scene, project):
        """Le nœud « Interface » (l'asset) → l'inspecteur de chemin matériel. Le
        bandeau devient l'endroit où le nom du nœud se change."""
        scene = scene or (project.active_scene if project else None)
        self._ensure(self._MODE_UI_NODE)
        self._ui_node_insp.load(layout, scene, project)
        self._set_header("ui_layout", label('common.interface'), layout.name if layout else "")
        self._stack.setCurrentIndex(self._MODE_UI_NODE)

    def refresh_current(self):
        """Recharge le panneau courant depuis les données projet — capte les
        assets modifiés dans un autre écran (ex. palettes d'un fond recompressé
        → grisées de la carte PALETTES). Ne change pas le mode affiché
        ni ne rebranche de signaux."""
        if self._stack.currentIndex() == self._MODE_SCENE:
            sc, pr = self._scene_insp._scene, self._scene_insp._project
            if sc and pr:
                self._scene_insp.load(sc, pr)
        elif self._stack.currentIndex() == self._MODE_PROJECT:
            # Compteurs d'assets + liste des scènes du sélecteur de démarrage
            self._project_insp.load(self._project)

    def show_empty(self):
        self._set_header("empty", "", "")
        self._stack.setCurrentIndex(self._MODE_EMPTY)

    def show_project(self):
        """Mode par défaut de l'inspecteur — aucune sélection (clic hors
        canvas, Échap, suppression du dernier actor sélectionné…)."""
        self._ensure(self._MODE_PROJECT)
        self._project_insp.load(self._project)
        name = self._project.settings.name if self._project else ""
        self._set_header("project", label('dyninsp.project'), name)
        self._stack.setCurrentIndex(self._MODE_PROJECT)

    def show_scene(self, scene, project):
        self._ensure(self._MODE_SCENE)
        self._scene_insp.load(scene, project)
        self._set_header("scene", label('common.scene'), scene.name if scene else "")
        self._stack.setCurrentIndex(self._MODE_SCENE)

    def show_actor(self, actor, project, scene=None):
        self._ensure(self._MODE_ACTOR)
        self._actor_insp.load(actor, project, scene)
        self._set_header("actor", label('common.actor'), actor.name if actor else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_prefab(self, prefab, project):
        scene = project.active_scene if project else None
        self._ensure(self._MODE_ACTOR)
        self._actor_insp.load_prefab(prefab, project, scene)
        self._set_header("prefab", label('dyninsp.prefab'), prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_camera(self, scene, camera, project):
        self._ensure(self._MODE_CAMERA)
        self._camera_insp.load(scene, camera, project)
        self._set_header("camera", label('common.camera'), camera.name, editable=True)
        self._stack.setCurrentIndex(self._MODE_CAMERA)

    def show_script(self, path, project=None):
        """Script .lua sélectionné dans le Project Viewer — note libre +
        variables exposées (ScriptInspector)."""
        from pathlib import Path as _P
        path = _P(path)
        self._current_script_path = path
        self._ensure(self._MODE_SCRIPT)
        self._script_insp.load(path)
        self._set_header("script_asset", label('dyninsp.script'), path.name)
        self._stack.setCurrentIndex(self._MODE_SCRIPT)

    def show_edge(self, edge, project=None):
        """Transition(s) du graphe → inspecteur, y compris multi-sélection."""
        proj = project or self._project
        edges = list(edge) if isinstance(edge, (list, tuple)) else [edge]
        edges = [value for value in edges if value is not None]
        if not edges:
            return
        self._ensure(self._MODE_EDGE)
        self._edge_insp.load(edges, proj)
        name = (f"{edges[0].source} → {edges[0].target}" if len(edges) == 1
                else label("edgeinsp.transitions_selected", count=len(edges)))
        self._set_header("edge", label('common.transition'), name, editable=False)
        self._stack.setCurrentIndex(self._MODE_EDGE)

    def show_group(self, group_id, folders, state) -> None:
        """Groupe de scènes du graphe : organisation, sans impact gameplay."""
        folder = next((f for f in folders.folders("scenes") if f.id == group_id), None)
        if folder is None:
            return
        self._ensure(self._MODE_GROUP)
        self._group_insp.load(group_id, folders, state)
        self._set_header("group", label("assetfind.group"), folder.name, editable=False)
        self._stack.setCurrentIndex(self._MODE_GROUP)

    def show_graph_note(self, note_id, state) -> None:
        note = state.notes().get(note_id) if state else None
        if note is None:
            return
        self._ensure(self._MODE_GRAPH_NOTE)
        self._graph_note_insp.load(note_id, state)
        self._set_header("graph_note", label("graphnote.type"), note.get("title", "Note"), editable=False)
        self._stack.setCurrentIndex(self._MODE_GRAPH_NOTE)

    def show_prefab_uses(self, prefab, project=None):
        proj = project or self._project
        if not proj:
            return
        self._ensure(self._MODE_PREFAB_USES)
        self._uses_insp.load(prefab, proj)
        self._set_header("uses", label('dyninsp.instances'), prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_PREFAB_USES)

    def show_script_uses(self, script_path: str, project=None):
        proj = project or self._project
        if not proj:
            return
        from pathlib import Path as _P
        self._ensure(self._MODE_SCRIPT_USES)
        self._script_uses_insp.load(script_path, proj)
        self._set_header("script", label('dyninsp.script'), _P(script_path).name)
        self._stack.setCurrentIndex(self._MODE_SCRIPT_USES)

    def _on_script_edit_requested(self, path: str):
        """Ouvre le script dans l'éditeur — relayé par window.py via script_opened."""
        # On émet via un signal dédié ou on passe par le bus.
        # Ici on utilise directement l'import window pour éviter une dépendance circulaire :
        # c'est window.py qui connecte script_opened → open_script().
        # On stocke un callback optionnel.
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(path)

    def set_script_open_fn(self, fn):
        """Injecté par window.py pour ouvrir un script depuis un inspecteur.

        Mémorisé, puis appliqué aux inspecteurs concernés — à ceux DÉJÀ
        construits maintenant, et aux autres par leur fabrique le jour où ils
        naissent (démarrage paresseux). Couvre scene/actor/camera : au démarrage
        aucun n'existe encore, tout passe donc par les fabriques."""
        self._script_open_fn = fn
        if self._actor_insp is not None:
            self._actor_insp._script_open_fn = fn
        if self._camera_insp is not None:
            self._camera_insp.set_script_open_fn(fn)
        if self._scene_insp is not None:
            self._scene_insp.set_script_open_fn(fn)

    def update_actor_position(self, x: int, y: int):
        # Un drag canvas peut précéder toute ouverture de l'inspecteur d'acteur :
        # rien à mettre à jour tant qu'il n'existe pas, il se chargera à sa venue.
        if self._actor_insp is not None:
            self._actor_insp.update_position(x, y)

    def update_camera_position(self, camera, x: int, y: int):
        if self._camera_insp is not None:
            self._camera_insp.update_position(camera, x, y)

    @property
    def actor_inspector(self) -> ActorInspector | None:
        """L'inspecteur d'acteur s'il a déjà été construit, sinon None (démarrage
        paresseux) — les appelants (window._reload_actor_inspector) gèrent None."""
        return self._actor_insp
