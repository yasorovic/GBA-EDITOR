"""Backstage — fenêtre principale (MainWindow uniquement)."""

import queue
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QPushButton, QFrame,
    QStatusBar, QDialog,
    QMessageBox,
    QToolButton, QStackedWidget, QToolBar, QSizePolicy,
)
from PyQt6.QtGui import QAction, QFont, QKeySequence, QShortcut, QDesktopServices
from PyQt6.QtCore import Qt, QSettings, QByteArray, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication

from ui.common.theme import C, T, QSS
from ui.common.labels import label
from ui.common.tooltip import tooltip

from codegen import BuildWorker
from core.models.components import affine_sprite_component, displayed_sprite_component
from codegen.oam_alloc import project_obj_tiles, scene_affine_requests, scene_oam_layout
from codegen.rom_report import RomReport
from ui.common.stack_gauge import StackGauge
from ui.scene_manager.scene_canvas import SceneEditor
from ui.scene_manager.canvas.canvas_workspace import CanvasWorkspace
from core.resources import asset_reconciliation
from core.toolchain import Toolchain
from core.project_watcher import ProjectWatcher
from core.history import get_history, SetFieldCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.sprite import IMAGE_FILE_EXTS
from core.models.scene import Scene
from core.project import Project
from core.project_paths import ProjectManifestError
from core.scene_graph_state import SceneGraphState
from core.asset_folder_store import AssetFolderStore
from ui.screens import EditorScreen, ProjectScreen, plugin_screens, refresh_screen

# ── Sous-composants UI ────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from ui.scene_manager.assets_finder_panel import AssetsFinderPanel
from ui.scene_manager.scene_tree_panel import SceneTreePanel
from ui.common.build_panel import BuildPanel, ToolchainBar, AnimatedBuildButton
from ui.common.save_status_indicator import SaveStatusIndicator
from ui.common.settings_dialog import SettingsDialog
from core.external_tools import ExternalTools
from core.keybindings import bind, get_keybindings
from core import crash_log
from core.app_info import APP_DOCS_URL, APP_NAME
from ui.common.about_dialog import AboutDialog
from core.diagnostics import diagnostic_report
from ui.common.reveal import reveal_in_file_manager
from ui.scene_manager.inspectors import DynamicInspector
from ui.home.project_picker import HomeScreen, push_recent, PROJECTS_DIR

# Démarrage paresseux (chantier « L'écran construit à sa première visite ») :
# les sept écrans natifs différés — Data, Background, Sprite, Palette, Text,
# Sound, Script — ne sont PAS importés ici. Leur import (souvent lourd :
# QtMultimedia + numpy pour l'audio, grammaire luaparser pour les scripts) vit
# dans leur fabrique `_make_*`, appelée à la première visite. Seul le Scene
# Manager et ses composants (SceneEditor, panneaux, inspecteur) restent importés
# en tête : c'est l'écran visible au démarrage.


# ──────────────────────────────────────────────────────────────────
#  GBA Status Bar — contraintes hardware visibles en permanence
# ──────────────────────────────────────────────────────────────────
class GbaStatusBar(QWidget):
    """
    Barre fixe en bas de la fenêtre : les mémoires de la GBA, nommées comme le
    matériel les nomme (OAM, OBJ VRAM, palettes OBJ/BG, SRAM), et ce que la ROM
    en occupera. Inspiré de GB Studio : les limites hardware sont visibles, pas
    cachées.

    Chaque compteur lit les MÊMES faits que le build (`oam_alloc`, `palette_alloc`,
    `gen_save`) — la barre ne compte rien de son côté. Deux portées, dites dans
    l'infobulle : l'OAM, les matrices affines, le coût par ligne, les palettes et
    la VRAM BG sont ceux de la SCÈNE active (une seule scène est vivante à la
    fois) ; la VRAM OBJ, la SRAM et la RAM sont ceux du PROJET.

    Trois compteurs ne se connaissent qu'APRÈS un build (VRAM BG, EWRAM, IWRAM) :
    leur valeur dépend de grit et du linker. Avant, ils affichent « ? » plutôt
    qu'un chiffre deviné ; ensuite ils gardent la mesure du DERNIER build, comme
    le bandeau ROM.
    """
    # Compteurs neutres par défaut : la couleur n'apparaît qu'en alerte (jaune
    # = proche du budget, rouge = dépassé). Le vert POWER reste réservé aux
    # signaux « live » (Build, process actif).
    _STYLE_OK   = f"color:{C.TEXT_NORM};"
    _STYLE_WARN = f"color:{C.ACCENT_YLW};"
    _STYLE_CRIT = f"color:{C.ACCENT_RED};"
    _WARN_RATIO = 0.75  # même seuil que SoundBudgetBar / RomBudgetBar

    # (clé, nom du matériel, unité, plafond initial). Les noms sont ceux du
    # matériel et ne se traduisent pas ; les clés d'infobulle sont
    # `win.<clé>_title|tip|note`. Les mémoires en octets ("kib") se comptent en
    # octets (seuil exact) et se lisent en Kio.
    _SPECS = (
        ("oam",    "OAM",        "count", 128),
        ("affine", "AFFINE",     "count", 32),
        ("cycles", "OBJ cycles", "count", 1210),
        ("vram",   "OBJ VRAM",   "count", 1024),
        ("objpal", "OBJ PAL",    "count", 16),
        ("bgpal",  "BG PAL",     "count", 16),
        ("bgvram", "BG VRAM",    "kib",   64 * 1024),
        ("sram",   "SRAM",       "kib",   32 * 1024),
        ("ewram",  "EWRAM",      "kib",   256 * 1024),
        ("iwram",  "IWRAM",      "kib",   32 * 1024),
    )
    # Ceux dont la valeur vient du build : « ? » tant qu'aucun n'a eu lieu.
    _FROM_BUILD = ("bgvram", "ewram", "iwram")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(25)
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        # Filet de séparation posé SUR la barre : un QWidget nu ne peint pas de
        # `border-top` par feuille de style de façon fiable, on le dessine donc
        # comme une ligne pleine largeur à part.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top_rule = QFrame()
        top_rule.setFixedHeight(C.SPLITTER_WIDTH)
        top_rule.setStyleSheet(f"background:{C.SPLITTER}; border:none;")
        outer.addWidget(top_rule)

        row = QWidget()
        outer.addWidget(row)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # Dernier rapport de build reçu (None = aucun depuis l'ouverture du projet).
        self._report: RomReport | None = None
        self._scene_name: str | None = None

        # clé -> [label de valeur, unité, plafond courant]
        self._counters: dict[str, list] = {}
        self._tip_targets: dict[str, list] = {}
        for i, (key, name, unit, limit) in enumerate(self._SPECS):
            if i > 0:
                # Espacement posé par le layout (et non par une marge en feuille
                # de style) : fiable, et symétrique de part et d'autre du filet.
                layout.addSpacing(8)
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color:{C.BORDER}; margin:4px 0;")
                layout.addWidget(sep)
                layout.addSpacing(8)
            lbl_name = QLabel(f"{name} ")
            lbl_name.setFont(QFont(T.MONO, T.XS))
            lbl_name.setStyleSheet(f"color:{C.TEXT_MUTED};")
            layout.addWidget(lbl_name)
            lbl_val = QLabel()
            lbl_val.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            note = label(f"win.{key}_note")
            if key in self._FROM_BUILD:
                note += "\n" + label("win.after_build_note")
            tip = tooltip(title=label(f"win.{key}_title"), body=label(f"win.{key}_tip"),
                          note=note)
            lbl_val.setToolTip(tip)
            lbl_name.setToolTip(tip)
            layout.addWidget(lbl_val)
            self._tip_targets[key] = [lbl_name, lbl_val]
            if key == "iwram":
                # La marge de l'IWRAM protège la pile : elle se lit d'un coup d'œil
                # comme une pile qui se remplit, du vert au rouge.
                layout.addSpacing(6)
                self._iwram_stack = StackGauge()
                self._iwram_stack.setToolTip(tip)
                layout.addWidget(self._iwram_stack)
                self._tip_targets[key].append(self._iwram_stack)
            self._counters[key] = [lbl_val, unit, limit]
            self._set(key, None if key in self._FROM_BUILD else 0)

        layout.addStretch()

    def set_build_report(self, report: RomReport | None):
        """Reçoit la mesure du dernier build (None à l'ouverture d'un projet : une
        mesure d'un autre projet ne doit pas rester affichée)."""
        self._report = report
        self._refresh_measured()

    def _refresh_measured(self):
        """Les trois compteurs que seul un build renseigne. EWRAM/IWRAM sont ceux du
        projet ; la VRAM BG est celle de la scène active, « ? » si le dernier build
        ne la connaissait pas (scène créée depuis)."""
        r = self._report
        self._set("ewram", r.ewram_bytes if r else None)
        self._set("iwram", r.iwram_bytes if r else None)
        self._iwram_stack.set_ratio(r.iwram_bytes / self._counters["iwram"][2] if r else None)
        self._refresh_iwram_tip()
        blocks = r.bg_vram_blocks.get(self._scene_name) if r and self._scene_name else None
        self._set("bgvram", None if blocks is None else blocks * 2048)

    def update_scene(self, scene: Scene, project: Project):
        """Recalcule les compteurs depuis la scène active et le projet."""
        from codegen.runtime_codegen.gen_save import SRAM_BYTES, save_total_bytes
        # Portée PROJET : indépendante de la scène ouverte.
        self._set("vram", *project_obj_tiles(project))
        self._set("sram", save_total_bytes(project), SRAM_BYTES)
        self._scene_name = scene.name if scene else None
        self._refresh_measured()
        if not scene:
            for key in ("oam", "affine", "cycles", "objpal", "bgpal"):
                self._set(key, 0)
            return

        # OAM : l'empreinte que le build réserve (acteurs actifs à apparence,
        # visibles ou non — `visible` n'est qu'un drapeau d'affichage —, OBJ
        # d'interface, pools de prefabs). Le même nombre que `_check_actor_budget`.
        oam_count = scene_oam_layout(project, scene).used

        # Rectangles occupant l'écran : (y, hauteur, coût en cycles par ligne).
        spans: list[tuple[int, int, int]] = []
        for a in scene.actors:
            if not (a.visible and a.active):
                continue
            # Le coût par scanline est celui du sprite AFFICHÉ : une seule
            # apparence dessine à la fois. Un sprite affine paie le double de sa
            # largeur plus 10, un sprite ordinaire sa largeur.
            shown = displayed_sprite_component(a)
            sp = project.get_sprite(shown.sprite_name) if shown else None
            if sp and sp.asset:
                affine = affine_sprite_component(a)
                cost = (2 * sp.frame_w + 10 if affine and affine.affine_transform
                        else sp.frame_w)
                spans.append((a.y, sp.frame_h, cost))

        # Zones de texte en cible sprite — leur coût est EXACT, pas estimé :
        # il ne dépend que de la géométrie authorée (cf. models/ui_region).
        from core.models.ui_region import strip_geometry, TARGET_OBJ
        rm = int(getattr(scene, "render_mode", 0) or 0)
        def _actor_pos(name):
            return next(((a.x, a.y) for a in scene.actors if a.name == name), None)
        slots = (project.scene_ui_slots(scene)
                 if hasattr(project, "scene_ui_slots") else [])
        for layout, r in slots:
            if layout.resolved_target(r, rm) != TARGET_OBJ:
                continue
            g = strip_geometry(r, project.region_animated_glyphs(r))
            # y ÉCRAN résolu par le modèle : offsets cumulés jusqu'au root +
            # socle du frame (l'acteur pour un root actor). Sans ça une bulle
            # atterrissait hors écran et ne coûtait rien.
            _, ry, _ = layout.absolute_origin(r, _actor_pos)
            # Une bande est un pavage de sprites de 8 px de haut : chaque rangée
            # pèse la largeur totale de la zone sur les 8 lignes qu'elle couvre.
            for row in range(g["rows"]):
                spans.append((ry + row * 8, 8, sum(g["cols"])))
            # Un glyphe animé est un OBJ 16×16 de plus. Où il tombe dans la zone
            # dépend du texte, donc du runtime : on les impute tous à la première
            # rangée, ce qui majore. Les omettre sous-estimerait la pire ligne,
            # ce qui est le seul sens dans lequel une jauge ne doit pas mentir.
            if g["anim"]:
                spans.append((ry, 16, g["anim"] * 16))

        # Pire ligne de l'écran : seules comptent les lignes qu'un objet recouvre
        # réellement. Sommer tout l'écran donnerait un chiffre toujours rouge ; ne
        # rien sommer du tout laissait passer une ligne de texte en sprites.
        line_cost = [0] * 160
        for y, h, w in spans:
            for ly in range(max(0, y), min(160, y + max(1, h))):
                line_cost[ly] += w
        scanline_cost = max(line_cost) if line_cost else 0

        # Banques de palette occupées (référencées + propres auto-allouées) : OBJ
        # et BG sont deux jeux de 16 distincts.
        from codegen.palette_alloc import scene_bank_layout
        self._set("oam", oam_count)
        self._set("affine", scene_affine_requests(project, scene))
        self._set("cycles", scanline_cost)
        self._set("objpal", scene_bank_layout(project, scene, "obj").bank_count())
        self._set("bgpal", scene_bank_layout(project, scene, "bg").bank_count())

    def _refresh_iwram_tip(self):
        """L'infobulle de l'IWRAM nomme ce qui l'occupe : les sections du linker
        (dites en clair), puis les plus gros éléments, avec leur nom dans le code
        généré. Sans build, elle garde le texte générique."""
        note = label("win.iwram_note") + "\n" + label("win.after_build_note")
        body = label("win.iwram_tip")
        r = self._report
        if r and r.iwram_sections:
            lines = [label("win.iwram_stored")]
            known = (".iwram", ".bss", ".data")
            parts = {sec: r.iwram_sections.get(sec, 0) for sec in known}
            other = sum(v for sec, v in r.iwram_sections.items() if sec not in known)
            for sec, size in sorted(parts.items(), key=lambda kv: -kv[1]):
                if size:
                    lines.append(f"{label('win.iwram_part' + sec.replace('.', '_'))} : "
                                 f"{size / 1024:.1f} KiB")
            if other >= 52:       # sous 0,05 Kio, la ligne s'afficherait « 0.0 KiB »
                lines.append(f"{label('win.iwram_part_other')} : {other / 1024:.1f} KiB")
            if r.iwram_top:
                lines.append(label("win.iwram_largest"))
                lines += [f"{name} : {size / 1024:.1f} KiB" for name, size in r.iwram_top]
            body += "\n" + "\n".join(lines)
        tip = tooltip(title=label("win.iwram_title"), body=body, note=note)
        for widget in self._tip_targets["iwram"]:
            widget.setToolTip(tip)

    def _set(self, key: str, value: int | None, limit: int | None = None):
        """Écrit un compteur. `value` None = inconnu (« ? », couleur neutre).
        `limit` remplace le plafond : la VRAM OBJ passe de 1024 à 512 tuiles dès
        qu'une scène est en mode bitmap."""
        counter = self._counters[key]
        lbl, unit, current = counter
        if limit is not None:
            counter[2] = current = limit
        if unit == "kib":
            used = "?" if value is None else f"{value / 1024:.1f}"
            text = label("win.kib_value", used=used, limit=current // 1024)
        else:
            text = label("win.count_value", used="?" if value is None else value,
                         limit=current)
        lbl.setText(text)
        if value is None:
            lbl.setStyleSheet(self._STYLE_OK)
        elif value >= current:
            lbl.setStyleSheet(self._STYLE_CRIT)
        elif value >= current * self._WARN_RATIO:
            lbl.setStyleSheet(self._STYLE_WARN)
        else:
            lbl.setStyleSheet(self._STYLE_OK)


# ──────────────────────────────────────────────────────────────────
#  Écrans dont la fenêtre est le propriétaire
# ──────────────────────────────────────────────────────────────────
class _ScreenPlaceholder(QWidget):
    """Occupe la place d'un écran natif non encore construit dans le
    `QStackedWidget` (démarrage paresseux). `_ensure_screen` le remplace par le
    vrai widget à la première visite ; sa seule fonction est de tenir l'index et
    d'être reconnaissable comme « pas encore là »."""


class SceneManagerScreen(QWidget):
    """Les colonnes du Scene Manager (colonne 1 scindée en deux panneaux
    empilés : liste projet au-dessus, contenu de la scène active en-dessous).

    Assemblée par `MainWindow._build_scene_manager_screen` : ses colonnes sont
    des attributs de la FENÊTRE (`assets_finder_panel`, `scene_tree_panel`,
    `scene_editor`, `_inspector`), lues depuis une trentaine d'endroits. Les
    faire descendre ici est un chantier à part — cette classe existe pour que
    l'écran porte le même contrat que les sept autres, et pour que la
    propagation du projet aux colonnes soit écrite une fois, ici, plutôt que
    dispersée dans
    `_refresh_ui`."""

    def __init__(self, finder, scene_tree, canvas, inspector, parent=None):
        super().__init__(parent)
        self._finder     = finder
        self._scene_tree = scene_tree
        self._canvas     = canvas
        self._inspector  = inspector

    def load_project(self, project):
        # Deux sidecars d'éditeur, UNE instance chacun par session, possédés ici
        # et partagés : positions du Graphe (`SceneGraphState`) et dossiers
        # d'assets (`AssetFolderStore`, dont les groupes de scènes du Graphe et
        # les dossiers du project viewer sont deux vues). Deux instances du même
        # fichier se désynchroniseraient.
        self._graph_state = SceneGraphState(project.root)
        self._folder_store = AssetFolderStore(project.root)
        self._folder_store.prune("scenes", {s.name for s in project.scenes})
        self._finder.load_project(project)
        self._finder.set_folder_store(self._folder_store)
        self._scene_tree.load_project(project)
        self._inspector.set_project(project)
        self._inspector.set_graph_state(self._graph_state)
        if project.active_scene:
            self._canvas.load_project(project, self._graph_state, self._folder_store)
        if project.active_scene:
            # Inspecteur de scène par défaut, sans passer par le bus.
            self._inspector.show_scene(project.active_scene, project)


# Durée d'affichage d'un avertissement déclenché par le watcher (dépôt/retouche
# d'un fichier HORS de l'éditeur) : l'utilisateur regarde l'explorateur de
# fichiers, pas la barre de statut, au moment où ça se produit — un délai
# court disparaît avant d'être vu (cf. bug rapporté 2026-09-01, import TTF
# vectoriel refusé, jamais remarqué à 6 s).
_WATCHER_WARNING_MS = 60000


# ──────────────────────────────────────────────────────────────────
#  Fenêtre principale
# ──────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    # Routage assets/<dossier>/*.ext → (sync, remove, rename, label) — une seule
    # table pour _on_asset_appeared/_removed/_renamed, qui n'était avant
    # dupliquée qu'avec "sync_"/"remove_" échangés.
    #
    # Les FONCTIONS d'`asset_encoding`, pas leurs noms. La table portait des
    # chaînes appelées par `getattr(self.project, nom)` : les treize passe-plats
    # correspondants ont été retirés de `Project` (cf. core/project.py, « ce
    # module ne fait plus passe-plat vers asset_encoding ») et le routage a
    # continué de les épeler. Rien ne pouvait le voir — ni l'import, ni
    # `check_architecture.py`, qui contrôle pourtant les noms résolus — et
    # déposer un PNG dans assets/sprites/ levait un AttributeError dans un slot
    # Qt, donc tuait l'éditeur. Une référence directe échoue à l'import.
    _ASSET_ROUTES = [
        ("sprites",     IMAGE_FILE_EXTS, asset_reconciliation.sync_sprite_png,
                                          asset_reconciliation.remove_sprite_png,
                                          asset_reconciliation.rename_sprite_png,     "Sprite"),
        ("backgrounds", IMAGE_FILE_EXTS, asset_reconciliation.sync_background_png,
                                          asset_reconciliation.remove_background_png,
                                          asset_reconciliation.rename_background_png, "Background"),
        ("sfx",         SFX_FILE_EXTS,    asset_reconciliation.sync_sfx_file,
                                          asset_reconciliation.remove_sfx_file,
                                          asset_reconciliation.rename_sfx_file,       "SFX"),
        ("music",       MUSIC_FILE_EXTS,  asset_reconciliation.sync_music_file,
                                          asset_reconciliation.remove_music_file,
                                          asset_reconciliation.rename_music_file,     "Music"),
        ("fonts",       FONT_FILE_EXTS,   asset_reconciliation.sync_font_file,
                                          asset_reconciliation.remove_font_file,
                                          asset_reconciliation.rename_font_file,      "Font"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        # La taille par défaut ne dépasse pas l'écran : à 150 % sur un écran 1080p,
        # la zone utile ne fait que 1280×680 (barre de titre en sus) et le bas de
        # la fenêtre — barre d'état comprise — sortait de l'écran.
        usable = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, usable.width()), min(760, usable.height() - 40))
        self.project: Project = None
        # Un écran reçoit le projet quand il devient utile, pas au simple
        # démarrage de la fenêtre. C'est la frontière UI du chargement différé
        # des assets : le canvas ouvre ses références ponctuelles, tandis que
        # leurs éditeurs demandent la collection entière à leur première vue.
        self._project_loaded_screen_indices: set[int] = set()
        self._worker = None
        self.toolchain = Toolchain()
        self._external_tools = ExternalTools()
        self._watcher = ProjectWatcher(self)
        # Retour du focus (Explorateur → éditeur) : on rattrape par comparaison
        # avec le disque tout ce que le watcher temps réel a pu rater.
        QGuiApplication.instance().applicationStateChanged.connect(self._on_application_state_changed)
        self._history = get_history()

        # Debounce : regrouper les sauvegardes rapides (SpinBox drag, etc.)
        self._save_timer = QTimer(); self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._flush_changes)

        self._setup_ui()

        # Raccourcis clavier globaux — après _setup_ui() pour que _btn_undo existe
        self._history.changed.connect(self._on_history_changed)
        self._sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._sc_undo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_undo.activated.connect(self._do_undo)
        self._sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._sc_redo_y.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_redo_y.activated.connect(self._do_redo)
        self._sc_redo_z = QShortcut(QKeySequence.StandardKey.Redo, self)
        self._sc_redo_z.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_redo_z.activated.connect(self._do_redo)
        self._restore_layout()

    def _setup_ui(self):
        # Le catalogue AVANT la barre d'outils : elle en tire ses libellés.
        # Construire le catalogue ne construit aucun widget — ce sont des
        # fabriques.
        self._screens: list[EditorScreen] = self._screen_catalogue()
        self._setup_toolbar()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.toolchain_bar = ToolchainBar(self.toolchain)
        self.toolchain_bar.configure_requested.connect(lambda: self._open_settings("Toolchains"))
        root_layout.addWidget(self.toolchain_bar)
        QApplication.instance().applicationStateChanged.connect(self._recheck_toolchain_on_focus)

        self._screen_stack = QStackedWidget()
        root_layout.addWidget(self._screen_stack, 1)

        # Écrans éditeur — l'accueil (HomeScreen) est un QDialog séparé
        # (ui/project_picker.py), affiché par main.py avant la fenêtre
        # principale, et rouvrable via _go_home() pour changer de projet.
        self._build_screens()

        # Nav cachée tant qu'aucun projet n'est chargé
        self._screen_stack.setCurrentIndex(0)   # Scene Manager
        self._set_editor_nav_visible(False)

        self._gba_bar = GbaStatusBar()
        root_layout.addWidget(self._gba_bar)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    # ── Catalogue d'écrans ────────────────────────────────────────
    #
    # L'UNIQUE liste. La barre de navigation, l'ordre du QStackedWidget et la
    # propagation du projet en dérivent tous — il n'y a plus deux listes à
    # tenir d'accord, ni d'index à compter. Ajouter un écran, c'est ajouter
    # une ligne ici et écrire sa fabrique.
    #
    # Une fabrique par écran plutôt qu'une classe : deux écrans ne se
    # construisent pas par simple appel de constructeur, et ceux que la fenêtre
    # ré-adresse plus tard (`self._sprite_editor.select_sprite(...)`) doivent
    # garder une référence nommée. Le branchement propre à un écran vit dans sa
    # fabrique, à côté de sa construction, au lieu d'être dispersé.

    def _screen_catalogue(self) -> list[EditorScreen]:
        return [
            EditorScreen("Scenes",      self._build_scene_manager_screen),
            EditorScreen("Datas",       self._make_data_editor),
            EditorScreen("Backgrounds", self._make_background_editor),
            EditorScreen("Animations",  self._make_sprite_editor),
            EditorScreen("Palettes",    self._make_palette_editor),
            EditorScreen("Texts",       self._make_text_editor),
            EditorScreen("Sounds",      self._make_sound_mixer),
            EditorScreen("Scripts",     self._make_script_editor),
        ] + plugin_screens()

    @property
    def _screen_names(self) -> list[str]:
        return [s.name for s in self._screens]

    def _screen_titles(self) -> list[str]:
        """Libellés affichés (barre de navigation, menu View) : le nom du
        catalogue reste l'identifiant, le texte passe par le catalogue de
        labels. Un écran de plugin, sans clé, garde son nom."""
        titles = {
            "Scenes":      label("win.screen_scenes"),
            "Datas":       label("win.screen_datas"),
            "Backgrounds": label("win.screen_backgrounds"),
            "Animations":  label("win.screen_animations"),
            "Palettes":    label("win.screen_palettes"),
            "Texts":       label("win.screen_texts"),
            "Sounds":      label("win.screen_sounds"),
            "Scripts":     label("win.screen_scripts"),
        }
        return [titles.get(name, name) for name in self._screen_names]

    def _build_screens(self):
        """Monte les écrans du catalogue — mais n'en construit qu'une partie.

        Démarrage paresseux (chantier « L'écran construit à sa première
        visite ») : seuls le Scene Manager (index 0, qui porte le menu, les
        splitters restaurés et le câblage du dispatcher) et les écrans de
        PLUGIN sont construits ici. Les autres écrans natifs reçoivent un
        placeholder dans le `QStackedWidget` — leur vrai widget, et donc l'import
        de leur module (souvent lourd : audio, luaparser…), n'arrive qu'à la
        première visite via `_ensure_screen`.

        Le contrat `ProjectScreen` est vérifié à la construction et pas par un
        contrôle statique : un écran venu d'un plugin n'existe pour personne
        avant ce moment. Les plugins restent donc construits ici, pour que le
        défaut se signale AU DÉMARRAGE comme avant — un écran natif, lui,
        satisfait le contrat par construction, le différer ne perd aucun message.
        """
        self._screen_widgets: list[QWidget] = []
        self.screen_errors: list[str] = []
        for index, spec in enumerate(self._screens):
            placeholder = _ScreenPlaceholder()
            self._screen_widgets.append(placeholder)
            self._screen_stack.addWidget(placeholder)
            if index == 0 or spec.plugin:
                self._ensure_screen(index)

    def _ensure_screen(self, index: int) -> QWidget:
        """Construit l'écran d'index `index` s'il ne l'est pas encore, et le
        substitue à son placeholder dans le `QStackedWidget`.

        Idempotent : un écran déjà réel est renvoyé tel quel. L'index dans le
        stack reste celui du catalogue — le placeholder tient la place jusque-là,
        et l'insertion+retrait ne décale pas les écrans suivants.
        """
        if not (0 <= index < len(self._screens)):
            return self._screen_widgets[index]
        current = self._screen_widgets[index]
        if not isinstance(current, _ScreenPlaceholder):
            return current   # déjà construit (Scene Manager, plugin, ou 2e appel)
        spec = self._screens[index]
        widget = spec.build()
        self._screen_widgets[index] = widget
        # Insère le vrai widget à SON index, puis retire le placeholder : l'ordre
        # du stack continue de coïncider avec celui du catalogue.
        self._screen_stack.insertWidget(index, widget)
        self._screen_stack.removeWidget(current)
        current.deleteLater()
        if not isinstance(widget, ProjectScreen):
            self.screen_errors.append(label("win.screen_contract", name=spec.name))
        return widget

    def _call_if_built(self, attr: str, method: str, *args) -> None:
        """Appelle `method` sur l'écran nommé UNIQUEMENT s'il a déjà été
        construit. Démarrage paresseux : un événement du dispatcher peut viser un
        écran encore différé — on le saute alors, il lira l'état frais à sa
        première visite (`load_project`)."""
        screen = getattr(self, attr, None)
        if screen is not None:
            getattr(screen, method)(*args)

    def _make_data_editor(self) -> QWidget:
        from ui.data_editor.data_editor_screen import DataEditorScreen
        self._data_editor = DataEditorScreen()
        return self._data_editor

    def _make_background_editor(self) -> QWidget:
        from ui.background_editor.background_editor_screen import BackgroundEditorScreen
        self._bg_editor = BackgroundEditorScreen()
        return self._bg_editor

    def _make_sprite_editor(self) -> QWidget:
        from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen
        self._sprite_editor = SpriteEditorScreen()
        return self._sprite_editor

    def _make_palette_editor(self) -> QWidget:
        from ui.palette_editor.palette_editor_screen import PaletteEditorScreen
        self._palette_editor = PaletteEditorScreen()
        self._palette_editor.usage_activated.connect(self._open_palette_usage)
        return self._palette_editor

    def _make_text_editor(self) -> QWidget:
        from ui.text_editor.text_editor_screen import TextEditorScreen
        self._text_editor = TextEditorScreen()
        return self._text_editor

    def _make_sound_mixer(self) -> QWidget:
        from ui.sound_mixer.sound_panel import SoundMixerScreen
        self._sound_mixer = SoundMixerScreen()
        return self._sound_mixer

    def _make_script_editor(self) -> QWidget:
        from ui.script_editor.script_editor import ScriptEditorScreen
        self._script_editor = ScriptEditorScreen()
        self._script_editor.back_requested.connect(
            lambda: self._switch_screen("Scenes")
        )
        self._script_editor.build_panel.cartridge_mib_changed.connect(self._set_cartridge_mib)
        self._script_editor.build_panel.console.location_activated.connect(self._open_build_location)
        self._wire_diagnostics(self._script_editor.build_panel)
        return self._script_editor

    def _build_scene_manager_screen(self) -> QWidget:
        # L'écran est construit EN DERNIER (cf. fin de méthode) : il reçoit ses
        # trois colonnes, qui n'existent qu'une fois le splitter peuplé.

        # Splitter horizontal principal : 3 colonnes
        self._h_split = QSplitter(Qt.Orientation.Horizontal)
        self._h_split.setStyleSheet(QSS.splitter)

        # ── Colonne 1 : Project Panel (haut) + Scene Tree (bas) ───
        # Deux questions distinctes, deux panneaux : « quelles scènes/prefabs/
        # scripts existe-t-il dans le projet » (AssetsFinderPanel) et « qu'y
        # a-t-il DANS la scène active » (SceneTreePanel — acteurs + mise en
        # page UI, à la façon du Scene dock de Godot).
        self.assets_finder_panel = AssetsFinderPanel()
        self._setup_menu()
        self.assets_finder_panel.scene_selected.connect(self._on_scene_selected)
        self.assets_finder_panel.scene_add_requested.connect(self._add_scene)
        self.assets_finder_panel.prefab_add_requested.connect(self._add_prefab)
        self.assets_finder_panel.script_opened.connect(self.open_script)
        self.assets_finder_panel.project_created.connect(self._new_project)
        self.assets_finder_panel.project_opened.connect(self._on_home_open)
        self.assets_finder_panel.prefab_uses_requested.connect(
            lambda p: self._inspector.show_prefab_uses(p))
        self.assets_finder_panel.script_uses_requested.connect(
            lambda path: self._inspector.show_script_uses(path))

        self.scene_tree_panel = SceneTreePanel()

        self._left_v_split = QSplitter(Qt.Orientation.Vertical)
        self._left_v_split.setStyleSheet(QSS.splitter)
        self._left_v_split.addWidget(self.scene_tree_panel)
        self._left_v_split.addWidget(self.assets_finder_panel)
        self._left_v_split.setSizes([260, 420])
        self._left_v_split.setStretchFactor(0, 1)
        self._left_v_split.setStretchFactor(1, 1)
        self._h_split.addWidget(self._left_v_split)

        # ── Colonne 2 : Canvas (haut) + Console (bas) ────────────
        self._center_v_split = QSplitter(Qt.Orientation.Vertical)
        self._center_v_split.setStyleSheet(QSS.splitter)

        self.scene_editor = SceneEditor()
        self.scene_editor.scene_changed.connect(self._on_scene_changed)
        # Le workspace possède les CONTEXTES du Canvas. `scene_editor` reste
        # l'éditeur/rendu de scène, afin que le futur graphe ne le transforme
        # pas en monolithe et que les connexions existantes restent stables.
        self.canvas_workspace = CanvasWorkspace(self.scene_editor)
        self._center_v_split.addWidget(self.canvas_workspace)
        # Navigation depuis le Graphe de scènes : la vue émet des INTENTIONS, la
        # fenêtre les exécute avec ses façades existantes (ouvrir une scène,
        # ouvrir un script). La sélection au clic, elle, passe déjà par le bus.
        _graph = self.canvas_workspace.graph_view
        _graph.scene_opened.connect(self._open_scene_from_graph)
        _graph.edge_selected.connect(self._show_edge_calls)
        _graph.edge_opened.connect(self._open_edge_from_graph)
        _graph.group_selected.connect(self._show_graph_group)
        _graph.note_selected.connect(self._show_graph_note)
        _graph.scene_create_requested.connect(self._create_scene_from_graph)
        # Un clic dans le vide / Échap qui retire la dernière sélection du
        # graphe rend son panneau par défaut : l'aperçu du projet.
        _graph.selection_cleared.connect(get_bus().clear)
        # Basculer Graphe → Scène ouvre la scène sélectionnée dans le graphe :
        # l'éditeur de scène pointe alors sur ce que l'auteur regardait.
        self.canvas_workspace.view_changed.connect(self._on_canvas_view_changed)
        # Sélection croisée graphe ↔ project viewer (highlight, sans activation) :
        # chaque vue surligne ce que l'autre sélectionne. Les gardes internes
        # (`_syncing` côté graphe, `blockSignals` côté finder) évitent la boucle.
        _graph.scenes_selected.connect(self.assets_finder_panel.highlight_scenes)
        self.assets_finder_panel.scenes_selected.connect(_graph.highlight_scenes)
        # Créer un groupe dans une vue le fait apparaître dans l'autre : les deux
        # lisent le même store de dossiers, mais chacune doit se redessiner.
        _graph.groups_changed.connect(self.assets_finder_panel.refresh)
        self.assets_finder_panel.groups_changed.connect(_graph.reload_groups)

        self.build_panel = BuildPanel()
        self.build_panel.btn_build.clicked.connect(self._run_build)
        self.build_panel.cartridge_mib_changed.connect(self._set_cartridge_mib)
        self.build_panel.console.location_activated.connect(self._open_build_location)
        self._wire_diagnostics(self.build_panel)
        self.build_panel.setMinimumHeight(80)
        self._center_v_split.addWidget(self.build_panel)
        self._center_v_split.setSizes([600, 160])
        self._center_v_split.setStretchFactor(0, 1)
        self._center_v_split.setStretchFactor(1, 0)

        self._h_split.addWidget(self._center_v_split)

        # ── Colonne 3 : Inspector (pleine hauteur) ────────────────
        self._inspector = DynamicInspector()
        self._inspector.actor_changed.connect(self._on_inspector_actor_changed)
        self._inspector.groups_changed.connect(_graph.reload_groups)
        self._inspector.groups_changed.connect(self.assets_finder_panel.refresh)
        self._inspector.edge_presentation_changed.connect(
            self.canvas_workspace.graph_view.refresh_edge_presentation)
        self._inspector.edge_script_changed.connect(
            self.canvas_workspace.graph_view.refresh)
        # Position/frame édités dans l'inspecteur caméra → le canvas suit (et
        # l'inverse : drag canvas → l'inspecteur suit, cf. plus bas).
        self._inspector.camera_moved.connect(self.scene_editor.move_camera_item)
        self.scene_editor.camera_position_changed.connect(
            self._inspector.update_camera_position)
        # Une zone éditée dans l'inspecteur doit se redessiner dans le canvas.
        self._inspector.ui_regions_changed.connect(
            self.scene_editor._reload_ui_regions)
        # `ui_regions_reloaded` : point de convergence des trois origines d'une
        # mise en page modifiée (dessin/suppression/collage au canvas, édition
        # dans l'inspecteur ci-dessus, opération depuis l'arbre plus bas) — un
        # conteneur qui change de fond change l'occupation des banques de
        # palette (carte Palettes de l'inspecteur de SCÈNE), pas seulement le
        # dessin du canvas.
        self.scene_editor.ui_regions_reloaded.connect(
            self._inspector.refresh_current)
        # Mélange de couleurs : recomposition des pixmaps du canvas, en direct.
        # `refresh_blend` ne relit aucun fichier, on peut donc la brancher sur
        # chaque cran du curseur sans le rendre poussif.
        self._inspector.blend_changed.connect(self.scene_editor.refresh_blend)
        # set_script_open_fn couvre désormais scene/actor/camera (appliqué par
        # leurs fabriques au démarrage paresseux) — plus d'accès direct à
        # `_scene_insp`, qui n'existe pas encore à ce stade.
        self._inspector.set_script_open_fn(self.open_script)
        self._h_split.addWidget(self._inspector)

        # Mise en page UI éditée depuis l'arbre de scène (ajout/suppression/
        # reparentage/réordonnancement/renommage) → sauver ET redessiner le
        # canvas, même contrat qu'avant (porté par SceneTreePanel désormais).
        # À l'inverse, une édition venue de l'inspecteur ou du canvas
        # reconstruit l'arbre.
        self.scene_tree_panel.ui_layout_changed.connect(
            self.scene_editor._save_ui_regions)
        self.scene_tree_panel.ui_layout_changed.connect(
            self.scene_editor._reload_ui_regions)
        self.scene_tree_panel.editor_visibility_changed.connect(
            self.scene_editor.set_editor_hidden_members)
        self._inspector.ui_regions_changed.connect(
            self.scene_tree_panel.refresh)
        self.scene_editor.scene_changed.connect(
            self.scene_tree_panel.refresh)

        # Bus de sélection — vider sur changement de scène/écran
        self._bus = get_bus()

        # CommandDispatcher — abonnements aux événements engine
        _d = get_dispatcher()
        _d.on("scene_sprites_changed", self.scene_editor._reload_sprites)
        _d.on("actors_list_changed",   self.scene_tree_panel.refresh)
        _d.on("actors_list_changed",   self._update_gba_bar)
        _d.on("actors_list_changed",   self._refresh_actor_inspector)
        # Carte Palettes de l'inspecteur de SCÈNE : un acteur posé (prefab
        # instancié au canvas compris) ou re-quantifié change l'occupation des
        # banques (cf. codegen/palette_alloc.scene_palette_view) : elle doit
        # suivre l'événement, pas attendre un aller-retour d'écran.
        _d.on("actors_list_changed",   self._inspector.refresh_current)
        _d.on("scene_sprites_changed", self._inspector.refresh_current)
        _d.on("cameras_list_changed",  self.scene_tree_panel.refresh)
        _d.on("cameras_list_changed",  self.scene_editor.refresh_cameras)
        _d.on("bg_slot_changed",       self.scene_editor.refresh_bg)
        _d.on("inpaint_layer_changed", self.scene_editor.set_inpaint_layer)
        _d.on("bg_layer_visibility",    self.scene_editor.set_layer_visible)
        _d.on("windows_changed",        self.scene_editor.refresh_windows)
        _d.on("backdrop_changed",       self.scene_editor.refresh_backdrop)
        _d.on("status_message",        lambda msg: self._status.showMessage(msg, 6000))
        _d.on("project_tree_changed",  self.assets_finder_panel.refresh)
        _d.on("project_tree_changed",  self.scene_tree_panel.refresh)
        _d.on("project_tree_changed",  self._update_build_state)
        # Le graphe des scènes dérive lui aussi de l'arbre projet : une scène
        # créée/supprimée/renommée doit s'y voir en direct quand il est affiché
        # (sinon il n'apprend le changement qu'au prochain showEvent). Hors écran,
        # inutile de re-parser : le showEvent s'en charge à la prochaine visite.
        _d.on("project_tree_changed",  self._refresh_graph_if_visible)
        _d.on("scripts_changed",       self.assets_finder_panel._refresh_scripts)
        # lambda : _text_editor / _script_editor / _palette_editor sont construits
        # à leur PREMIÈRE VISITE (démarrage paresseux), donc après ce bloc
        # d'abonnement. On résout l'attribut au moment de l'émission, et un écran
        # non encore construit ignore l'événement — il lira l'état frais à sa
        # venue (`load_project`). D'où `_call_if_built` plutôt qu'un accès direct.
        _d.on("scripts_changed",       lambda: self._call_if_built("_text_editor", "invalidate_script_usages"))
        _d.on("ui_text_links_changed", lambda: self._call_if_built("_text_editor", "invalidate_script_usages"))
        _d.on("flush_script_edits",    lambda: self._call_if_built("_script_editor", "flush_pending_edits"))
        # NB : l'écran Palettes n'a PAS d'abonnement `palettes_changed`. Seuls le
        # Sprite Editor et le Background Editor émettent cet événement (via
        # `save_palette`), donc toujours quand l'écran Palettes est CACHÉ : son
        # `refresh()` à la revisite (`_show_screen`, chantier « L'écran
        # resynchronisé à sa revisite ») le remet à jour au retour, sans
        # rafraîchir un écran invisible.

        self._h_split.setSizes([220, 760, 300])
        self._h_split.setStretchFactor(0, 0)
        self._h_split.setStretchFactor(1, 1)
        self._h_split.setStretchFactor(2, 0)

        screen = SceneManagerScreen(self.assets_finder_panel, self.scene_tree_panel,
                                    self.canvas_workspace, self._inspector)
        screen_layout = QVBoxLayout(screen)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(0)
        screen_layout.addWidget(self._h_split)
        return screen

    # ── Persistance layout ────────────────────────────────────────

    def _restore_layout(self):
        s = QSettings(APP_NAME, "Layout")
        geom = s.value("geometry")
        if isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        for name, splitter in (
            ("h_split", self._h_split),
            ("center_v_split", self._center_v_split),
            ("left_v_split", self._left_v_split),
        ):
            data = s.value(name)
            if isinstance(data, QByteArray):
                splitter.restoreState(data)

    def _save_layout(self):
        s = QSettings(APP_NAME, "Layout")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("h_split", self._h_split.saveState())
        s.setValue("center_v_split", self._center_v_split.saveState())
        s.setValue("left_v_split", self._left_v_split.saveState())

    def closeEvent(self, event):
        if not self._confirm_close():
            event.ignore()
            return
        self._save_layout()
        if self.project:
            self.project.commit_all_removals()
        super().closeEvent(event)

    def _confirm_close(self) -> bool:
        """Propose d'écrire ce qui est en attente ; faux si l'utilisateur
        annule, ou si l'écriture échoue et qu'il préfère rester. Ne jamais
        perdre du travail en silence : l'abandon est un choix explicite."""
        if not self.project:
            return True
        if self._has_pending_changes():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            # Application-modale : la fermeture peut venir du dialogue de
            # réglages (redémarrage), lui-même modal.
            box.setWindowModality(Qt.WindowModality.ApplicationModal)
            box.setWindowTitle(label("win.close_unsaved_title"))
            box.setText(label("win.close_unsaved"))
            save = box.addButton(label("common.save"), QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton(label("win.close_discard"), QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(label("common.cancel"), QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(save)
            box.setEscapeButton(cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is discard:
                return True
            if clicked is not save:
                return False
        try:
            self._persist_project()
        except OSError as exc:
            answer = QMessageBox.question(
                self, label("win.close_save_failed_title"),
                label("win.close_save_failed", error=exc))
            return answer == QMessageBox.StandardButton.Yes
        return True

    # ── Menu ──────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()
        mb.setMinimumHeight(32)
        mb.setStyleSheet(
            f"QMenuBar{{background:{C.BG_PANEL};color:{C.TEXT_NORM};font-family:{T.UI_STACK};font-size:{T.MD}px;padding:4px 4px;border-bottom:{C.SPLITTER_WIDTH}px solid {C.SPLITTER};}}"
            "QMenuBar::item{padding:4px 10px;border-radius:3px;}"
            f"QMenuBar::item:selected{{background:{C.BG_HOVER};}}"
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};font-family:{T.UI_STACK};font-size:{T.MD}px;}}"
            "QMenu::item{padding:5px 20px 5px 12px;}"
            f"QMenu::item:selected{{background:{C.BG_SEL};}}"
        )
        m_file = mb.addMenu(label("win.menu_file"))
        a_new  = QAction(label("common.new_project"),  self); bind("file.new",  a_new)
        a_open = QAction(label("common.open_project"), self); bind("file.open", a_open)
        a_save = QAction(label("common.save"),         self); bind("file.save", a_save)
        a_save.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        # Réglages du LOGICIEL (devkitPro/mgba, thème, raccourcis, outils
        # tiers — un état par machine) : distinct du menu Game → Project
        # Settings, qui ouvre le projet OUVERT. Même dialogue que le bouton
        # « ⚙ Configure » de la barre toolchain, une seconde porte vers la
        # même donnée.
        a_file_settings = QAction(label("common.settings"), self)
        a_quit = QAction(label("common.quit"), self); bind("file.quit", a_quit)
        a_new.triggered.connect(self.assets_finder_panel._prompt_new)
        a_open.triggered.connect(self.assets_finder_panel._prompt_open)
        a_save.triggered.connect(self._save_project)
        a_file_settings.triggered.connect(self._open_settings)
        a_quit.triggered.connect(self.close)
        for a in [a_new, a_open, a_save, None, a_file_settings, None, a_quit]:
            if a: m_file.addAction(a)
            else: m_file.addSeparator()
        m_game = mb.addMenu(label("win.menu_game"))
        a_build = QAction(label("common.build_run"), self); bind("game.build", a_build)
        a_build.triggered.connect(self._run_build)
        m_game.addAction(a_build)
        m_game.addSeparator()
        a_project_settings = QAction(label("win.project_settings"), self)
        a_project_settings.triggered.connect(self._open_project_settings)
        m_game.addAction(a_project_settings)
        m_view = mb.addMenu(label("win.menu_view"))
        m_view.aboutToShow.connect(lambda: self._fill_view_menu(m_view))
        m_help = mb.addMenu(label("win.menu_help"))
        # Sans site de documentation (cf. core/app_info.APP_DOCS_URL), l'entrée
        # n'existe pas : un menu qui ouvre une adresse vide serait un piège.
        if APP_DOCS_URL:
            a_docs = QAction(label("win.documentation"), self)
            a_docs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(APP_DOCS_URL)))
            m_help.addAction(a_docs)
            m_help.addSeparator()
        # Les deux portes d'un rapport de bug : où est le journal, et le
        # résumé qu'on colle dans le compte rendu.
        a_logs = QAction(label("win.open_log_folder"), self)
        a_logs.triggered.connect(self._open_log_folder)
        m_help.addAction(a_logs)
        a_diag = QAction(label("win.copy_diagnostics"), self)
        a_diag.triggered.connect(self._copy_diagnostics)
        m_help.addAction(a_diag)
        m_help.addSeparator()
        a_about = QAction(label("win.about"), self)
        a_about.triggered.connect(lambda: AboutDialog(self).exec())
        m_help.addAction(a_about)

    def _open_log_folder(self):
        """Ouvre le dossier de `crash.log`. Créé au besoin : tant que rien n'a
        planté il n'existe pas, et un menu qui ne fait rien ressemble à une panne."""
        crash_log.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        reveal_in_file_manager(crash_log.LOG_FILE.parent)

    def _copy_diagnostics(self):
        QApplication.clipboard().setText(diagnostic_report(self.project, self.toolchain))
        self._status.showMessage(label("win.diagnostics_copied"), 5000)

    def _fill_view_menu(self, menu):
        """Liste des écrans, dans l'ordre de la barre de navigation (que
        l'utilisateur peut réordonner) ; reconstruite à chaque ouverture."""
        menu.clear()
        names = self._screen_names
        titles = self._screen_titles()
        for idx in self._nav_bar.screen_order():
            action = menu.addAction(titles[idx])
            action.triggered.connect(lambda _=False, i=idx: self._switch_screen(names[i]))

    # ── Toolbar ───────────────────────────────────────────────────

    def _setup_toolbar(self):
        tb = QToolBar("Principale")
        tb.setMovable(False)
        tb.setMinimumHeight(48)
        tb.setStyleSheet(
            f"QToolBar{{background:{C.BG_RAISED};border-bottom:{C.SPLITTER_WIDTH}px solid {C.SPLITTER};spacing:4px;padding:4px 12px;}}"
            f"QToolButton{{color:{C.TEXT_NORM};border:none;padding:4px 12px;font-family:{T.UI_STACK};font-size:{T.MD}px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-radius:4px;}}"
        )
        self.addToolBar(tb)
        self._tb_project_lbl = QPushButton(APP_NAME)
        self._tb_project_lbl.setFont(QFont(T.UI, T.XL, QFont.Weight.DemiBold))
        self._tb_project_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tb_project_lbl.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:none;border:none;padding:0 12px;}}"
            f"QPushButton:hover{{color:{C.TEXT_DIM};}}"
        )
        self._tb_project_lbl.clicked.connect(self._go_home)
        tb.addWidget(self._tb_project_lbl)
        tb.addSeparator()
        self._tb_build_btn = AnimatedBuildButton()
        self._tb_build_btn.setEnabled(False)
        self._tb_build_btn.clicked.connect(self._run_build)
        tb.addWidget(self._tb_build_btn)
        tb.addSeparator()

        # Boutons Undo / Redo
        _undo_redo_style = (
            f"QToolButton{{color:{C.TEXT_DIM};border:none;padding:4px 10px;"
            f"font-family:{T.UI_STACK};font-size:{T.MD}px;border-radius:4px;}}"
            f"QToolButton:hover:enabled{{background:{C.BG_HOVER};color:{C.TEXT_NORM};}}"
            f"QToolButton:disabled{{color:{C.TEXT_MUTED};}}"
        )
        self._btn_undo = QToolButton()
        self._btn_undo.setText(label("win.undo"))
        self._btn_undo.setFont(QFont(T.UI, T.MD))
        self._btn_undo.setStyleSheet(_undo_redo_style)
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._do_undo)
        tb.addWidget(self._btn_undo)

        self._btn_redo = QToolButton()
        self._btn_redo.setText(label("win.redo"))
        self._btn_redo.setFont(QFont(T.UI, T.MD))
        self._btn_redo.setStyleSheet(_undo_redo_style)
        self._btn_redo.setEnabled(False)
        self._btn_redo.clicked.connect(self._do_redo)
        tb.addWidget(self._btn_redo)
        tb.addSeparator()

        from ui.common.reorderable_bar import ReorderableButtonBar
        self._nav_bar = ReorderableButtonBar(self._screen_titles())
        self._nav_bar.screen_requested.connect(self._show_screen)
        tb.addWidget(self._nav_bar)
        self._nav_bar.check_screen(0)

        # Tout à droite : l'état d'enregistrement du projet.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        self._save_indicator = SaveStatusIndicator()
        self._tb_save_indicator = tb.addWidget(self._save_indicator)
        # Sans plancher, une fenêtre étroite renvoyait l'état d'enregistrement dans le
        # menu de débordement de la barre (le « >> ») au lieu de le montrer.
        tb.setMinimumWidth(tb.sizeHint().width())
        # Les écritures différées (inspecteur, nudge, script) n'émettent pas de
        # signal à leur départ : on lit leurs minuteries, peu coûteux.
        self._save_indicator_timer = QTimer(self)
        self._save_indicator_timer.setInterval(200)
        self._save_indicator_timer.timeout.connect(self._refresh_save_indicator)
        self._save_indicator_timer.start()

    def _has_pending_changes(self) -> bool:
        """Vrai tant qu'une modification n'a pas encore été écrite sur le disque."""
        if self._save_timer.isActive() or self.scene_editor.has_pending_save():
            return True
        se = getattr(self, "_script_editor", None)
        return se is not None and se.has_unsaved_edits()

    def _refresh_save_indicator(self):
        self._tb_save_indicator.setVisible(self.project is not None and self._nav_bar.isVisible())
        self._save_indicator.set_saved(not self._has_pending_changes())

    def _open_project_settings(self):
        """Menu Game → Project Settings — cartouche, audio, debug build,
        transition par défaut, langues, collisions (`ProjectSettingsDialog`,
        même squelette que `SettingsDialog`). L'identité du projet (auteur,
        version, scène de départ, backdrop) reste dans `ProjectInspector`,
        visible en permanence dans le Scene Manager quand rien n'est
        sélectionné : ce n'est pas un réglage qu'on va chercher, c'est ce
        qu'on garde sous les yeux."""
        if not self.project:
            return
        from ui.scene_manager.inspectors.project_settings_dialog import ProjectSettingsDialog
        dlg = ProjectSettingsDialog(self.project, parent=self)
        dlg.exec()
        self._refresh_settings_dependents()

    def _refresh_settings_dependents(self):
        """Resynchronise tout ce qui met en cache un champ de `ProjectSettings`
        et n'est pas déjà branché sur un événement dédié.

        `backdrop_color` n'a pas besoin d'être ici : `VisualPanel` émet déjà
        `backdrop_changed` sur le dispatcher (`core.command_dispatcher`), et
        `scene_canvas.refresh_backdrop` l'écoute — le mécanisme EXISTANT et
        idiomatique du projet pour « ceci a changé, pas au build ». C'est lui
        qu'il faut étendre champ par champ, PAS le `ProjectWatcher` : il ne
        suit que des fichiers déposés de l'EXTÉRIEUR (assets, scripts, scènes)
        et s'appuierait ici sur `project.json`, que ce dialogue vient
        lui-même d'écrire — s'y abonner obligerait à suspendre le watcher
        pendant toute l'ouverture de la fenêtre pour éviter l'aller-retour,
        pour un gain nul face à un appel direct ici.

        Reste donc ce qui n'émet PAS encore un tel événement : les langues
        (`TextEditorScreen`, une seule ligne suffit, pas la peine d'un
        événement pour un seul abonné) et la cartouche visée, dupliquée dans
        les DEUX bandeaux ROM (Scene Manager, Script Editor) — même resynchro
        que fait déjà `_set_cartridge_mib` quand le choix vient du bandeau
        lui-même plutôt que de cette fenêtre."""
        if not self.project:
            return
        # Écrans peut-être encore différés (démarrage paresseux) : on ne
        # rafraîchit que ceux déjà construits — un écran neuf lira l'état à jour
        # à sa première visite (`load_project`).
        if (te := getattr(self, "_text_editor", None)) is not None:
            te.refresh()
        cart_mib = getattr(self.project.settings, "cartridge_mib", 4)
        self.build_panel.set_cartridge_mib(cart_mib)
        if (sbp := self._script_build_panel()) is not None:
            sbp.set_cartridge_mib(cart_mib)

    def _show_screen(self, index: int):
        # Un seul catalogue : l'index de nav EST l'index du stack, par
        # construction (`_build_screens` monte dans l'ordre de `_screens`).
        # Démarrage paresseux : l'écran est construit maintenant s'il ne l'était
        # pas — c'est sa première visite.
        self._ensure_screen(index)
        # Revisite ? On le capture AVANT `_load_screen_for_project`, qui ajoute
        # l'index au set à la première visite : sinon, la première visite serait
        # prise pour une revisite et rafraîchirait juste après avoir chargé.
        revisit = bool(self.project) and index in self._project_loaded_screen_indices
        self._load_screen_for_project(index)
        self._screen_stack.setCurrentIndex(index)
        # Première visite : `load_project` a déjà tout peuplé. Visite suivante :
        # l'écran a pu se périmer pendant qu'on était ailleurs — on le re-dérive
        # (chantier « L'écran resynchronisé à sa revisite »).
        if revisit:
            self._refresh_screen_for_project(index)
        self._history.clear()
        self._bus.clear()

    def _load_screen_for_project(self, index: int):
        """Prépare un écran lors de sa première visite pour ce projet.

        Les autres écrans restent volontairement inertes à l'ouverture : leur
        finder n'a pas à désérialiser tous les assets juste parce qu'il existe
        dans un ``QStackedWidget`` invisible.
        """
        if not self.project or index in self._project_loaded_screen_indices:
            return
        if not (0 <= index < len(self._screen_widgets)):
            return
        # Un appelant peut viser un écran encore différé (watcher qui ré-encode
        # un fond, ouverture d'un script…) : le construire avant de le charger.
        self._ensure_screen(index)
        spec = self._screens[index]
        widget = self._screen_widgets[index]
        if not isinstance(widget, ProjectScreen):
            return

        if spec.name == "Backgrounds":
            self.project.load_backgrounds()
        elif spec.name == "Animations":
            self.project.load_sprites()
        elif spec.name == "Sounds":
            self.project.load_audio()
        elif spec.name == "Datas":
            # Les colonnes de référence d'une table citent effets et musiques
            # (cf. DATA_COLUMN_SOURCES) : leur picker a besoin du catalogue.
            self.project.load_audio()
        elif spec.name == "Scripts":
            # La sidebar RÉFÉRENCES liste tous les sprites et fonds.
            self.project.load_sprites()
            self.project.load_backgrounds()

        if not spec.plugin:
            widget.load_project(self.project)
        else:
            try:
                widget.load_project(self.project)
            except Exception as exc:
                self._status.showMessage(
                    label("win.screen_error", name=spec.name, error=exc), 8000)
                return
        self._project_loaded_screen_indices.add(index)

    def _refresh_screen_for_project(self, index: int):
        """Re-dérive un écran DÉJÀ chargé, à une visite autre que la première.

        Le symétrique de `_load_screen_for_project` pour les revisites : là où
        `load_project` peuple à la première visite, `refresh` remet les catalogues
        à jour quand on revient sur l'écran après une modification faite ailleurs.
        Volontairement bon marché — le contrat de `refresh` interdit tout accès
        disque ou re-décodage (cf. `ui/screens.refresh_screen`). N'appelle donc
        AUCUN `load_*` du projet ici : les catalogues visés sont déjà en mémoire.
        """
        if not self.project or index not in self._project_loaded_screen_indices:
            return
        if not (0 <= index < len(self._screen_widgets)):
            return
        widget = self._screen_widgets[index]
        if not isinstance(widget, ProjectScreen):
            return
        spec = self._screens[index]
        if not spec.plugin:
            refresh_screen(widget)
        else:
            # Écran de plugin = code tiers : une exception n'y remonte pas jusqu'au
            # slot Qt (même prudence que `_load_screen_for_project`).
            try:
                refresh_screen(widget)
            except Exception as exc:
                self._status.showMessage(
                    label("win.screen_error", name=spec.name, error=exc), 8000)

    def _switch_screen(self, name: str):
        names = self._screen_names
        idx = names.index(name) if name in names else 0
        self._show_screen(idx)
        self._nav_bar.check_screen(idx)

    def _go_home(self):
        """Ouvre l'écran d'accueil (HomeScreen) pour changer de projet."""
        picker = HomeScreen(PROJECTS_DIR, self)
        if picker.exec() == QDialog.DialogCode.Accepted and picker.result_path:
            if picker.result_is_new and picker.result_name:
                self._new_project(
                    picker.result_name, picker.result_path, picker.result_starter)
            else:
                self._open_project(picker.result_path)

    def open_script(self, path, line: int | None = None):
        """Ouvre un script .lua dans le Script Editor et bascule l'écran.

        `line` (1-indexée, optionnelle) fait sauter le curseur à la ligne — le
        clic sur un `fichier.lua:ligne` du journal de build passe par là. On
        bascule l'écran AVANT d'ouvrir, pour que l'éditeur soit visible quand
        `goto_line` centre la ligne."""
        from pathlib import Path
        # Démarrage paresseux : construire l'écran Scripts s'il ne l'est pas
        # encore, avant de l'adresser.
        self._ensure_screen(self._screen_names.index("Scripts"))
        self._script_editor.load_project(self.project)
        self._switch_screen("Scripts")
        self._script_editor.open_script(Path(path), line)

    def _open_build_location(self, filename: str, line: int):
        """Un `fichier.lua:ligne` du journal de build a été cliqué : ouvre le
        script à cette ligne. Le journal ne cite qu'un NOM de fichier (le
        codegen émet `sp.name`) — on le retrouve par son basename sous le dossier
        des scripts du projet."""
        if not self.project:
            return
        from pathlib import Path
        root = getattr(self.project, "scripts_dir", None) or \
            (self.project.root / "project" / "scripts")
        match = next((p for p in Path(root).rglob(filename)), None)
        if match is None:
            self._status.showMessage(label("win.script_not_found", name=filename), 4000)
            return
        self.open_script(match, line)

    # ── Diagnostics (panneau du validateur) ───────────────────────
    def _wire_diagnostics(self, build_panel):
        """Branche l'onglet Diagnostics d'un BuildPanel : relance la validation,
        et route les clics (script → ligne, acteur → sélection)."""
        d = build_panel.diagnostics
        d.refresh_requested.connect(self._refresh_diagnostics)
        d.location_activated.connect(self._open_build_location)
        d.actor_activated.connect(self._select_actor_by_name)
        d.element_activated.connect(self._select_ui_element)

    def _refresh_diagnostics(self):
        """Relance `validate_project` sur la scène active et alimente les deux
        onglets Diagnostics. À la demande (bouton Refresh) et au changement de
        scène — pas à chaque frappe (un parse complet coûte)."""
        if not self.project:
            return
        from core.validator import validate_project
        warns, errors = validate_project(self.project)
        for bp in (getattr(self, "build_panel", None),
                   getattr(getattr(self, "_script_editor", None), "build_panel", None)):
            if bp is not None:
                bp.diagnostics.set_diagnostics(warns, errors)

    def _select_actor_by_name(self, scene_name: str, name: str):
        """Clic sur un diagnostic d'acteur ou de scène : ouvrir la scène du diagnostic si ce
        n'est pas la scène active (le validateur contrôle toutes les scènes), puis y sélectionner
        l'acteur. `scene_name` vide : la scène active. `name` vide : seulement la scène."""
        if not self.project:
            return
        active = self.project.active_scene
        if scene_name and (active is None or active.name != scene_name):
            idx = next((i for i, s in enumerate(self.project.scenes) if s.name == scene_name), None)
            if idx is None:
                self._status.showMessage(label("win.actor_not_found", name=scene_name), 4000)
                return
            self._on_scene_selected(idx, refresh_diagnostics=False)
        scene = self.project.active_scene
        if scene is None or not name:
            return
        actor = next((a for a in scene.actors if a.name == name), None)
        if actor is not None:
            self._bus.select(actor)
        else:
            self._status.showMessage(
                label("win.actor_not_found", name=name), 4000)

    def _select_ui_element(self, layout_name: str, name: str):
        """Clic sur un diagnostic de zone d'UI : bascule sur Scenes et sélectionne
        l'élément. Résolu par nom via `Project.all_elements` (mise en page +
        élément), comme le journal résout un `fichier.lua:ligne`."""
        if not self.project:
            return
        from core.selection_bus import UIElementSelection
        match = next(((lay, el) for lay, el in self.project.all_elements()
                      if lay.name == layout_name and el.name == name), None)
        if match is None:
            self._status.showMessage(label("win.element_not_found", name=name), 4000)
            return
        self._switch_screen("Scenes")
        self._bus.select(UIElementSelection(*match))

    def _open_palette_usage(self, kind: str, name: str):
        """Clic sur une ligne de la carte « USAGE » du Palette Editor :
        ouvrir l'écran qui édite cet élément et l'y sélectionner. La sélection
        vient APRÈS le changement d'écran — _show_screen vide le bus."""
        if not self.project:
            return
        if kind == "sprite":
            self._switch_screen("Animations")
            self._sprite_editor.select_sprite(name)
        elif kind == "background":
            self._switch_screen("Backgrounds")
            self._bg_editor.select_background(name)
        elif kind == "scene":
            index = next((i for i, s in enumerate(self.project.scenes) if s.name == name), None)
            if index is None:
                return
            self._switch_screen("Scenes")
            self._on_scene_selected(index)
        elif kind == "prefab":
            prefab = self.project.prefabs.get(name)
            if prefab is None:
                return
            self._switch_screen("Scenes")
            self._bus.select(prefab)

    # ── Chargement projet ─────────────────────────────────────────

    def _on_home_open(self, path: str):
        self._open_project(Path(path))

    def _new_project(self, name: str, path, starter_id: str = "Basic"):
        path = Path(path)
        self.project = Project.create(path, name, starter_id)
        self._project_loaded_screen_indices.clear()
        self._gba_bar.set_build_report(None)   # la mesure d'un autre projet ne reste pas
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        push_recent(path)
        self._enter_editor()
        self._refresh_ui()
        self._status.showMessage(label("win.new_project_msg", name=name))

    def _open_project(self, path: Path):
        # Plusieurs .project dans le dossier : on refuse d'en choisir un
        # (cf. ROADMAP v0.10). On le dit et on abandonne l'ouverture — l'écran
        # courant reste, aucun projet n'est à moitié chargé.
        try:
            self.project = Project.open(path)
        except ProjectManifestError as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, label("common.open_project"), str(exc))
            return
        self._project_loaded_screen_indices.clear()
        self._gba_bar.set_build_report(None)   # la mesure d'un autre projet ne reste pas
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        push_recent(path)
        self._enter_editor()
        self._refresh_ui()
        # Un asset que la réconciliation n'a pas su importer laissait un panneau
        # vide et rien d'autre. Le dire ici, au seul moment où l'utilisateur
        # peut faire le lien avec le fichier qu'il vient de déposer.
        warns = getattr(self.project, "load_warnings", [])
        if warns:
            first = warns[0]
            more = label("win.more_warnings", n=len(warns) - 1) if len(warns) > 1 else ""
            self._status.showMessage(first + more, 12000)
        else:
            self._status.showMessage(label("win.project_msg", name=self.project.settings.name))

    def _enter_editor(self):
        """Affiche l'éditeur (nav visible) sur le Scene Manager."""
        self._set_editor_nav_visible(True)
        self._show_screen(0)   # Scene Manager

    def _set_editor_nav_visible(self, visible: bool):
        """Affiche ou masque les boutons de navigation de l'éditeur."""
        self._nav_bar.setVisible(visible)
        self._tb_build_btn.setVisible(visible)
        self._btn_undo.setVisible(visible)
        self._btn_redo.setVisible(visible)
        # La barre compacte n'a d'utilité que dans l'éditeur (bouton Configurer
        # rapide) — l'accueil affiche déjà son propre statut, plus explicite.
        self.toolchain_bar.setVisible(visible)

    def _refresh_assets_ui(self):
        """Les catalogues d'assets ont changé HORS de l'éditeur (fichier ajouté,
        supprimé, renommé, sidecar retouché) : le modèle est à jour, mais les
        écrans déjà chargés affichent encore l'ancienne liste — `refresh` à la
        revisite ne relit que les palettes, `load_project` ne rejoue qu'à la
        première visite. On invalide donc les écrans chargés : celui qu'on
        regarde est repeuplé tout de suite, les autres à leur prochaine visite."""
        if not self.project:
            return
        self._project_loaded_screen_indices.clear()
        self.assets_finder_panel.refresh()
        self._refresh_ui()      # recharge l'écran visible (index absent du set)

    def _recheck_toolchain_on_focus(self, state):
        """Retour sur l'éditeur après l'installateur de devkitPro ou de mGBA : tant
        qu'il manque un outil, on relit la détection pour que la barre et le bouton
        Build passent au vert sans rien cliquer. Plus rien à vérifier une fois complet."""
        if state != Qt.ApplicationState.ApplicationActive:
            return
        if self.toolchain.devkitpro_ok and self.toolchain.mgba_ok:
            return
        self.toolchain.recheck()
        self.toolchain_bar.refresh()
        self._update_build_state()

    def _update_build_state(self):
        """Active ou grise le build selon toolchain + présence d'une scène.

        Séparé de `_refresh_ui` : créer ou supprimer une scène change la
        réponse sans qu'il faille recharger l'écran visible."""
        if not self.project: return
        toolchain_ok = self.toolchain.devkitpro_ok and self.toolchain.mgba_ok
        can_build = toolchain_ok and bool(self.project.scenes)
        tooltip = self._build_tooltip()
        # Outils manquants : le bouton est grisé mais reste cliquable, le clic
        # ouvre l'explication puis les réglages (`_run_build`). Sans scène, il
        # n'y a rien à expliquer : grisé pour de bon.
        self._tb_build_btn.setEnabled(bool(self.project.scenes))
        self._tb_build_btn.set_unavailable(not toolchain_ok)
        self._tb_build_btn.setToolTip(tooltip)
        self.build_panel.btn_build.setEnabled(can_build)
        self.build_panel.btn_build.setToolTip(tooltip)

    def _refresh_ui(self):
        if not self.project: return
        name = self.project.settings.name
        self.setWindowTitle(label("win.window_title", app_name=APP_NAME, name=name))
        self._tb_project_lbl.setText(name)   # QPushButton.setText
        self._update_build_state()
        cart_mib = getattr(self.project.settings, "cartridge_mib", 4)
        self.build_panel.set_cartridge_mib(cart_mib)
        if (sbp := self._script_build_panel()) is not None:
            sbp.set_cartridge_mib(cart_mib)
        # Seul l'écran visible reçoit le projet maintenant. Les autres le
        # recevront dans ``_show_screen`` lors de leur première visite.
        self._load_screen_for_project(self._screen_stack.currentIndex())
        self._update_gba_bar()

    # ── Slots scène ───────────────────────────────────────────────

    def _on_scene_selected(self, index: int, refresh_diagnostics: bool = True):
        if not self.project: return
        self.project.set_active_scene(index)
        self._history.clear()
        self._bus.clear()      # nouvelle scène = nouvelle sélection
        self.scene_editor.load_project(self.project)
        self._inspector.show_scene(self.project.active_scene, self.project)
        self.assets_finder_panel.highlight_active_scene(self.project.active_scene)
        # Le liseré « scène active » du graphe suit la même bascule (la bascule
        # ne change pas l'empreinte du graphe, donc `refresh` ne le ferait pas).
        self.canvas_workspace.graph_view.set_active_scene(
            self.project.active_scene.name if self.project.active_scene else None)
        self.scene_tree_panel.set_active_scene(self.project.active_scene)
        self._update_gba_bar()
        # La validation porte sur toutes les scènes : changer de scène ne la change pas. On
        # ne la relance que pour la mise à jour de l'onglet ; un clic sur un diagnostic (qui
        # bascule de scène) la garde, pour ne pas remplacer sous le doigt la liste du build.
        if refresh_diagnostics:
            self._refresh_diagnostics()
        self._status.showMessage(label("win.active_scene_msg", name=self.project.active_scene.name))

    def _open_scene_from_graph(self, name: str):
        """Double-clic (ou clic-droit « Edit ») sur une scène du Graphe : revenir
        au Canvas 2D et l'ouvrir.

        Réutilise le flux d'ouverture de scène de l'arbre (`_on_scene_selected`)
        après avoir rebasculé le workspace sur la vue de scène, pour que
        l'éditeur soit visible quand la scène se charge. On charge nous-mêmes ici :
        `_suppress_view_switch_load` neutralise le chargement automatique de la
        bascule (`_on_canvas_view_changed`), sinon la scène se chargerait deux
        fois — la scène VOULUE ici prime sur la simple sélection."""
        if not self.project:
            return
        idx = next((i for i, s in enumerate(self.project.scenes) if s.name == name), None)
        if idx is None:
            return
        self._suppress_view_switch_load = True
        try:
            self.canvas_workspace.activate_view(CanvasWorkspace.SCENE_VIEW)
        finally:
            self._suppress_view_switch_load = False
        self._on_scene_selected(idx)

    def _on_canvas_view_changed(self, view: str):
        """Bascule de vue du Canvas. En passant sur la vue de scène, on ouvre la
        scène sélectionnée dans le Graphe (s'il y en a une seule) : l'éditeur
        pointe sur ce que l'auteur regardait. Neutralisé pendant une ouverture
        explicite (`_open_scene_from_graph`), qui charge déjà la bonne scène."""
        if (view != CanvasWorkspace.SCENE_VIEW
                or getattr(self, "_suppress_view_switch_load", False)
                or not self.project):
            return
        name = self.canvas_workspace.graph_view.selected_scene_name()
        if not name:
            return
        idx = next((i for i, s in enumerate(self.project.scenes) if s.name == name), None)
        if idx is not None and self.project.active_scene is not self.project.scenes[idx]:
            self._on_scene_selected(idx)

    def _refresh_graph_if_visible(self):
        """Re-projette le graphe des scènes s'il est à l'écran (sa mémoïsation ne
        recalcule que si l'empreinte a changé). Caché, il se met à jour seul à sa
        prochaine ouverture (showEvent) — pas de re-parse inutile hors vue."""
        graph = self.canvas_workspace.graph_view
        if graph.isVisible():
            graph.refresh()

    def _show_edge_calls(self, edge):
        """Clic sur une arête : l'inspecteur d'arête (occurrences + saut au code),
        et un rappel agrégé dans la barre d'état."""
        self._inspector.show_edge(edge, self.project)
        if isinstance(edge, (list, tuple)):
            if len(edge) != 1:
                self._status.showMessage(
                    label("edgeinsp.transitions_selected", count=len(edge)), 4000)
                return
            edge = edge[0]
        self._status.showMessage(
            label("scncanvas.graph_edge_calls", source=edge.source,
                  target=edge.target, count=len(edge.refs)), 4000)

    def _show_graph_group(self, group_id: str) -> None:
        """Ouvre l'inspecteur d'un groupe seulement après chargement du projet."""
        graph = self.canvas_workspace.graph_view
        if graph._folders is not None and graph._state is not None:
            self._inspector.show_group(group_id, graph._folders, graph._state)

    def _show_graph_note(self, note_id: str) -> None:
        graph = self.canvas_workspace.graph_view
        if graph._state is not None:
            self._inspector.show_graph_note(note_id, graph._state)

    def _open_edge_from_graph(self, edge):
        """Double-clic sur une arête : ouvrir le Script Editor à l'appel.

        La sortie de secours du Graphe (condition, déplacement, suppression) :
        on ouvre le premier appel agrégé, à sa ligne exacte via `LuaRef`."""
        if not edge.refs:
            return
        ref = edge.refs[0]
        self.open_script(ref.path, ref.line)

    def _create_scene(self) -> str:
        """Crée une scène au nom unique. La toute première devient la scène
        active : sans elle le panneau restait sur « No active scene » et le
        canvas vide, alors que le modèle avait déjà une scène."""
        from core.command_dispatcher import unique_name
        was_empty = not self.project.scenes
        name = unique_name("Scene", {s.name for s in self.project.scenes})
        get_dispatcher().add_scene(name)
        if was_empty:
            self._on_scene_selected(0)
        return name

    def _add_scene(self):
        if not self.project: return
        name = self._create_scene()
        self.assets_finder_panel.refresh()
        self.assets_finder_panel.begin_rename_scene(name)

    def _create_scene_from_graph(self, x: float, y: float):
        """Clic-droit « Créer une scène ici » dans le graphe : même création que
        `_add_scene`, mais la carte est posée au point cliqué (et rattachée au
        niveau ouvert du graphe) plutôt que laissée à l'auto-layout."""
        if not self.project: return
        name = self._create_scene()   # re-projette le graphe (project_tree_changed)
        self.canvas_workspace.graph_view.place_new_scene(name, x, y)

    # ── Slots prefab ─────────────────────────────────────────────

    def _add_prefab(self):
        if not self.project: return
        from core.command_dispatcher import unique_name
        name = unique_name("Prefab", {p.name for p in self.project.prefabs})
        get_dispatcher().add_prefab(name)
        self.assets_finder_panel.refresh()
        self.assets_finder_panel.begin_rename_prefab(name)

    def _on_scene_changed(self):
        """Fin de drag actor ou déplacement caméra — sauvegarder via le dispatcher."""
        if not self.project or not self.project.active_scene:
            return
        self.scene_editor.flush_camera_pos()
        get_dispatcher().save_scene()

    def _on_inspector_actor_changed(self, actor):
        """Un champ a changé dans l'inspector — payload propre, pas d'accès privé."""
        if actor:
            self.scene_editor.move_actor_item(actor)
        self._save_timer.start()    # 400 ms → _flush_changes (debounce)

    def _flush_changes(self):
        """Sauvegarde globale différée (400 ms après le dernier changement inspector)."""
        get_dispatcher().save_all()

    def _save_project(self):
        """
        Ctrl+S global — seul raccourci de sauvegarde de l'app (contexte
        ApplicationShortcut : actif quel que soit l'écran affiché dans le
        QStackedWidget). Flush d'abord l'état en cours d'édition des écrans
        qui ont un concept de "non sauvegardé" avant l'écriture disque —
        les autres écrans persistent déjà à chaque modification.
        """
        if not self.project:
            return
        self._persist_project()
        self._status.showMessage(label("win.saved"), 2000)

    def _persist_project(self):
        """Écrit tout ce qui est en attente, puis le projet entier.

        Partagé par Ctrl+S et par la fermeture : les écritures différées
        (debounce de 400 ms, nudge du canvas, frappe du Script Editor) ne
        partent pas toutes seules quand la fenêtre se ferme avant leur
        minuterie."""
        self._save_timer.stop()
        self.scene_editor.flush_camera_pos()
        # Le Script Editor n'a du texte non enregistré que s'il a été ouvert.
        if (se := getattr(self, "_script_editor", None)) is not None:
            se.flush_pending_edits()
        self.project.save()

    def _refresh_actor_inspector(self):
        """Recharge l'inspecteur d'acteur s'il en montre un — un champ (ex :
        Parent, posé depuis l'arbre de scène par drag & drop) peut avoir
        changé ailleurs que par l'inspecteur lui-même."""
        self._reload_actor_inspector()

    def _reload_actor_inspector(self):
        """Recharge l'inspecteur d'acteur EN RESPECTANT ce qu'il affiche —
        acteur de scène, racine d'un prefab, ou partie d'un prefab (ROADMAP
        v0.23) — pas juste `.load()` à l'aveugle : un prefab EST son actor
        racine (core/models/scene.Prefab), `.load()` seule ne sait pas
        retrouver ce contexte depuis l'Actor nu qu'elle affiche déjà."""
        actor_insp = self._inspector.actor_inspector
        if actor_insp is None or not actor_insp._actor:
            return
        scene = self.project.active_scene if self.project else None
        if actor_insp._is_prefab_template and actor_insp._prefab:
            actor_insp.load_prefab(actor_insp._prefab, self.project, scene)
        elif actor_insp._child_owner is not None:
            actor_insp.load_child(actor_insp._actor, actor_insp._child_owner,
                                   self.project, scene)
        else:
            actor_insp.load(actor_insp._actor, self.project, scene)

    def _update_gba_bar(self):
        """Met à jour les compteurs hardware GBA (OAM, VRAM, PAL, scanline)."""
        if self.project and self.project.active_scene:
            self._gba_bar.update_scene(self.project.active_scene, self.project)

    # ── Undo / Redo ───────────────────────────────────────────────

    def _on_history_changed(self):
        self._btn_undo.setEnabled(self._history.can_undo)
        self._btn_redo.setEnabled(self._history.can_redo)
        ul = self._history.undo_label
        rl = self._history.redo_label
        self._btn_undo.setToolTip(
            tooltip(title=label("win.undo_tip", label=ul), shortcut="Ctrl+Z") if ul
            else tooltip(title=label("win.undo_none")))
        self._btn_redo.setToolTip(
            tooltip(title=label("win.redo_tip", label=rl), shortcut="Ctrl+Y") if rl
            else tooltip(title=label("win.redo_none")))

    def _do_undo(self):
        lbl = self._history.undo()
        if lbl:
            self._status.showMessage(label("win.undone", label=lbl), 2000)
            self._flush_after_undo_redo()

    def _do_redo(self):
        lbl = self._history.redo()
        if lbl:
            self._status.showMessage(label("win.redone", label=lbl), 2000)
            self._flush_after_undo_redo()

    def _flush_after_undo_redo(self):
        """Rafraîchit l'UI après un undo ou redo."""
        if not self.project:
            return
        # Textes/polices : indépendants de la scène active, donc rafraîchis
        # AVANT le garde-fou ci-dessous (annuler un renommage de clé doit se
        # voir même dans un projet sans scène). Sauté si l'écran Texte n'a pas
        # encore été ouvert (démarrage paresseux) — il lira l'état à sa venue.
        if (te := getattr(self, "_text_editor", None)) is not None:
            te.refresh()
        if not self.project.active_scene:
            return
        # Sauvegarder l'état actuel (le modèle en mémoire = vérité après undo)
        with self._watcher.suspended():
            self.project.save_scene(self.project.active_scene)
        # Resynchro des ITEMS du canvas depuis le modèle (sprites, caméras,
        # zones) — sans reset zoom/pan/BG. Reposer les seuls sprites laissait un
        # item de caméra ou de zone annulé à sa position draggée (cf. Correctifs).
        self.assets_finder_panel.refresh()
        self.scene_tree_panel.refresh()
        self.scene_editor.reload_scene_items()
        self._update_gba_bar()
        # Recharger l'inspector scène — s'il a déjà été construit (démarrage
        # paresseux) ET montre une scène.
        si = self._inspector._scene_insp
        if si is not None and si._scene:
            si.load(si._scene, self.project)
        # Recharger l'inspector si un actor est sélectionné
        self._reload_actor_inspector()

    # ── Réactivité fichiers externes ─────────────────────────────

    def _on_application_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationActive and self.project:
            self._watcher.rescan()

    def _connect_watcher(self):
        """
        Connecte tous les signaux du ProjectWatcher aux handlers.
        Se déconnecte d'abord : _open_project()/_new_project() rappellent
        cette méthode à chaque changement de projet sur le même watcher
        persistant (self._watcher) — sans ça, chaque événement fichier finit
        par déclencher le handler N fois après N ouvertures de projet.
        """
        w = self._watcher
        for sig in (w.asset_appeared, w.asset_removed, w.asset_renamed,
                    w.asset_modified,
                    w.lua_changed, w.scene_changed, w.sidecar_changed):
            try:
                sig.disconnect()
            except TypeError:
                pass   # aucune connexion existante — rien à faire
        w.asset_appeared.connect(self._on_asset_appeared)
        w.asset_removed.connect(self._on_asset_removed)
        w.asset_renamed.connect(self._on_asset_renamed)
        w.asset_modified.connect(self._on_asset_modified)
        w.lua_changed.connect(self._on_lua_changed)
        w.scene_changed.connect(self._on_scene_file_changed)
        w.sidecar_changed.connect(self._on_sidecar_changed)

    def _match_asset_route(self, p: Path):
        """Trouve la route (sync/remove/rename/label) pour un fichier
        assets/<dossier>/*.ext."""
        suffix, parent = p.suffix.lower(), p.parent.name
        for folder, exts, sync_fn, remove_fn, rename_fn, label in self._ASSET_ROUTES:
            if parent == folder and suffix in exts:
                return sync_fn, remove_fn, rename_fn, label
        return None

    def _on_asset_appeared(self, path: str):
        """Nouveau fichier brut détecté dans assets/ — créer le sidecar si nécessaire."""
        if not self.project:
            return
        p = Path(path)
        route = self._match_asset_route(p)
        if not route:
            # Extension d'asset reconnue, mais pas par CE dossier (un .wav dans
            # backgrounds/) : le fichier reste là sans asset — le dire, plutôt
            # que de le laisser muet.
            self._status.showMessage(
                label("win.asset_misplaced", name=p.name, folder=p.parent.name,
                      ext=p.suffix.lower()), _WATCHER_WARNING_MS)
            return
        sync_fn, _, _, route_label = route
        # Certains sync_* renvoient un avertissement d'import (police sans
        # glyphe, format illisible…) — le taire laisserait un asset muet à
        # l'écran sans que l'utilisateur sache pourquoi. D'autres renvoient la
        # Resource créée (Sfx/Music) : seule une chaîne est un avertissement.
        #
        # `suspended` : sync_* ÉCRIT le sidecar .json, et depuis que ceux-ci
        # sont surveillés cette écriture nous reviendrait comme une modification
        # externe — on rechargerait l'asset qu'on vient de créer.
        with self._watcher.suspended():
            result = sync_fn(self.project, p)
        warning = result if isinstance(result, str) else None
        self._refresh_assets_ui()
        if warning:
            self._status.showMessage(warning, _WATCHER_WARNING_MS)
        else:
            self._status.showMessage(label("win.asset_imported", kind=route_label, name=p.name), 3000)

    def _on_sidecar_changed(self, path: str):
        """Un sidecar `.json` d'asset a été créé ou modifié hors de l'éditeur.

        Le nom du dossier EST celui du `ResourceStore` (assets/fonts/ →
        `project.fonts`) : pas de table de correspondance à tenir, la même
        convention que le watcher applique déjà pour décider quoi surveiller.

        `load_one` recharge cet asset seul depuis le disque. Recharger le
        projet entier serait plus simple et beaucoup plus brutal — on perdrait
        la sélection et l'historique pour une police retouchée à la main.
        """
        if not self.project:
            return
        p = Path(path)
        store = getattr(self.project, p.parent.name, None)
        if store is None or not hasattr(store, "load_one"):
            return
        if store.load_one(p.stem) is None:
            return
        self._refresh_assets_ui()
        self._status.showMessage(
            label("win.asset_reloaded", kind=p.parent.name[:-1].capitalize(), name=p.stem), 3000)

    def _on_asset_removed(self, path: str):
        """Fichier brut supprimé de assets/ — suppression différée du JSON, UI mise à jour."""
        if not self.project:
            return
        p = Path(path)
        route = self._match_asset_route(p)
        if not route:
            return
        _, remove_fn, _, route_label = route
        with self._watcher.suspended():
            remove_fn(self.project, p)
            if p.parent.name == "fonts":
                asset_reconciliation.reconcile_font_assets(self.project)
        self._refresh_assets_ui()
        self._status.showMessage(label("win.asset_removed", kind=route_label, name=p.name), 3000)

    def _on_asset_renamed(self, old: str, new: str):
        """Fichier brut renommé dans assets/ — l'asset SUIT son fichier.

        Le watcher apparie la disparition et l'apparition ; sans lui, ce geste
        arrivait ici en deux temps, et l'asset était détruit avec tout ce qui
        avait été authoré dessus pendant qu'un asset vierge naissait du nouveau
        nom.

        `suspended` pour la même raison que dans `_on_asset_appeared` : les
        `rename_*` écrivent le sidecar, et depuis que ceux-ci sont surveillés
        l'écriture nous reviendrait comme une modification externe."""
        if not self.project:
            return
        old_p, new_p = Path(old), Path(new)
        route = self._match_asset_route(new_p)
        if not route:
            # L'extension a changé pour une que cette famille ne connaît pas :
            # ce n'est plus un renommage de son point de vue, c'est une
            # disparition.
            self._on_asset_removed(old)
            return
        _, _, rename_fn, route_label = route
        with self._watcher.suspended():
            result = rename_fn(self.project, old_p, new_p)
            if new_p.parent.name == "fonts":
                asset_reconciliation.reconcile_font_assets(self.project)
        warning = result if isinstance(result, str) else None
        self._refresh_assets_ui()
        if warning:
            self._status.showMessage(warning, _WATCHER_WARNING_MS)
        else:
            self._status.showMessage(
                label("win.asset_renamed", kind=route_label,
                      old=old_p.name, new=new_p.name), 3000)

    def _on_asset_modified(self, path: str):
        """Fichier existant modifié dans assets/ (ex. PNG retouché) — rafraîchir la preview."""
        p = Path(path)
        if p.suffix.lower() in IMAGE_FILE_EXTS and p.parent.name == "backgrounds":
            # Un fond ne se contente pas d'un rafraîchissement d'affichage : sa
            # compression (palettes + tuiles) est stockée dans le sidecar, et
            # c'est ELLE que lit le build. Sans ré-encodage, l'ancienne image
            # resterait à l'écran ET dans la ROM.
            if not self.project:
                return
            self._load_screen_for_project(self._screen_names.index("Backgrounds"))
            with self._watcher.suspended():   # le sidecar réécrit est NOTRE écriture
                warning = asset_reconciliation.resync_background_png(self.project, p)
            # Le fond retouché reste celui qu'on regardait : `select` le remet à
            # l'écran plutôt que de renvoyer au premier de la liste.
            self._bg_editor._refresh_finder(select=p.stem)
            self.scene_editor.load_project(self.project)
            self._update_gba_bar()
            self._status.showMessage(warning or label("win.bg_updated", name=p.stem),
                                     _WATCHER_WARNING_MS if warning else 3000)
            return
        if p.suffix.lower() in IMAGE_FILE_EXTS and p.parent.name == "sprites":
            # Comme un fond : les palettes stockées viennent des pixels, il faut
            # les refaire. La ROM, elle, était juste — grit relit le PNG au
            # build — mais l'éditeur affichait les anciennes couleurs (aperçu
            # d'acteur, coût en palettes, allocation de banques).
            if not self.project:
                return
            self._load_screen_for_project(self._screen_names.index("Animations"))
            with self._watcher.suspended():   # le sidecar réécrit est NOTRE écriture
                warning = asset_reconciliation.resync_sprite_png(self.project, p)
            self._sprite_editor.load_project(self.project)
            self.scene_editor._reload_sprites()
            if (actor_insp := self._inspector.actor_inspector) is not None:
                actor_insp._refresh_sprite_preview()
            self._update_gba_bar()
            self._status.showMessage(warning or label("win.sprite_updated", name=p.stem),
                                     _WATCHER_WARNING_MS if warning else 3000)
            return
        if p.parent.name == "fonts":
            # Planche retouchée : les métriques affichées (glyphes, coût en
            # tuiles) sont dérivées de l'asset, pas du fichier — un refresh
            # suffit, l'asset lui-même n'est jamais ré-analysé automatiquement
            # (sinon on écraserait les corrections de l'utilisateur). MAIS
            # `sync_font_file` est un no-op pour une police déjà connue — il
            # ne fait un import réel que si `project.fonts.get(name)` est
            # None, exactement le cas d'un fichier jamais importé avec succès
            # (import refusé la première fois, puis retouché/redéposé) : sans
            # cet appel, ce cas retombait dans le message générique tout en
            # bas, silencieux sur la vraie raison (cf. bug rapporté 2026-09-01).
            if self.project:
                with self._watcher.suspended():
                    warning = asset_reconciliation.sync_font_file(self.project, p)
                    asset_reconciliation.reconcile_font_assets(self.project)
                if (te := getattr(self, "_text_editor", None)) is not None:
                    te.refresh()
                if warning:
                    self._status.showMessage(warning, _WATCHER_WARNING_MS)
                    return
        if (actor_insp := self._inspector.actor_inspector) is not None:
            actor_insp._refresh_sprite_preview()
        self._status.showMessage(label("win.asset_modified", name=Path(path).name), 2000)

    def _on_lua_changed(self, path: str):
        """Un .lua a changé (éditeur externe). L'inspecteur d'acteur est à
        démarrage paresseux : absent tant qu'aucun acteur n'a été inspecté (ex :
        on édite un script de scène sans avoir ouvert d'acteur), il n'a alors rien
        à resynchroniser."""
        if (actor_insp := self._inspector.actor_inspector) is not None:
            actor_insp.notify_lua_changed(path)
        self._status.showMessage(label("win.script_modified", name=Path(path).name), 2000)

    def _on_scene_file_changed(self, path: str):
        """Un .json de scène a changé depuis un éditeur externe — recharger la scène active."""
        if not self.project:
            return
        active = self.project.active_scene
        if not active:
            return
        scene_file = self.project.scenes._path(active.name)
        if Path(path) == scene_file:
            self.project.scenes.load_one(active.name)
            self.scene_editor.load_project(self.project)
            self._inspector.show_scene(self.project.active_scene, self.project)
            self._status.showMessage(label("win.scene_reloaded", name=active.name), 2000)

    def _open_settings(self, category: str = "Toolchains"):
        """Écran Réglages unique (File → Settings, bouton « ⚙ Configure » de
        la barre toolchain, et le garde-fou du build quand devkitPro/mgba
        manquent) — `category` ne fait que présélectionner l'entrée de
        gauche, les trois autres restent à un clic."""
        dlg = SettingsDialog(self.toolchain, self._external_tools, category, self)
        dlg.exec()
        self.toolchain_bar.refresh()
        if self.project:
            self._refresh_ui()

    def _build_tooltip(self) -> str:
        """Explique pourquoi Build & Run est grisé, ou son raccourci sinon."""
        missing = []
        if not self.toolchain.devkitpro_ok:
            missing.append("devkitPro (ARM + grit)")
        if not self.toolchain.mgba_ok:
            missing.append("mGBA")
        if missing:
            return tooltip(title=label("win.build_unavailable", n=len(missing),
                                       what=", ".join(missing)),
                           body=label("win.build_unavailable_tip"))
        if self.project and not self.project.scenes:
            return tooltip(title=label("win.build_no_scene"))
        return tooltip(title=label("win.build_run_title"), shortcut=get_keybindings().resolve("game.build"),
                       body=label("win.build_run_tip"))

    # ── Build ─────────────────────────────────────────────────────

    def _set_cartridge_mib(self, mib: int):
        """Choix de cartouche fait depuis le mot « ROM » du bandeau — même
        réglage, même commande annulable que le combo de l'inspecteur de
        projet (`ProjectInspector._set_setting`) : deux entrées, un seul
        champ. Les DEUX bandeaux (Scene Manager, Script Editor) se
        resynchronisent aussitôt, avant même le prochain build."""
        if not self.project:
            return
        settings = self.project.settings
        old = getattr(settings, "cartridge_mib", 4)
        if old == mib:
            return
        project = self.project

        def _persist():
            # Resynchronise les DEUX bandeaux sur `execute` ET `undo` — même
            # règle que `ProjectInspector._persist` pour son combo.
            project.save()
            cur = getattr(settings, "cartridge_mib", 4)
            self.build_panel.set_cartridge_mib(cur)
            if (sbp := self._script_build_panel()) is not None:
                sbp.set_cartridge_mib(cur)

        get_history().push(SetFieldCmd(
            settings, "cartridge_mib", old, mib,
            label="Projet.cartridge_mib", persist_fn=_persist,
        ))

    def _script_build_panel(self):
        """La seconde console de build (celle du Script Editor) SI cet écran a
        été construit, sinon None. Démarrage paresseux : le build est
        déclenchable depuis la barre d'outils sans jamais avoir ouvert Scripts —
        on n'alimente sa console mirroir que si elle existe déjà. Ouvrir Scripts
        plus tard montre une console vierge, cohérent avec un écran neuf."""
        se = getattr(self, "_script_editor", None)
        return se.build_panel if se is not None else None

    def _explain_missing_toolchain(self):
        """Dit POURQUOI on ne peut pas construire maintenant, et où trouver ce qui
        manque, avant d'ouvrir les réglages — au lieu d'une fenêtre de réglages qui
        surgit sans un mot (cf. ALPHA_CHECKLIST, « Build & Run sans devkitPro »)."""
        from ui.common.toolchain_dialog import ToolchainMissingDialog
        missing = [tool for tool, path in self.toolchain.check().items() if not path]
        dialog = ToolchainMissingDialog(missing, self)
        dialog.exec()
        if dialog.open_settings_requested:
            self._open_settings("Toolchains")

    def _run_build(self):
        if not self.project or not self.project.active_scene: return
        if self._worker is not None: return     # un build tourne déjà : le clic est ignoré
        if not (self.toolchain.devkitpro_ok and self.toolchain.mgba_ok):
            self.toolchain.recheck()    # outils installés depuis le dernier inventaire ?
            if not (self.toolchain.devkitpro_ok and self.toolchain.mgba_ok):
                self._explain_missing_toolchain(); return
            self._update_build_state()

        self.build_panel.reveal()
        if (sbp := self._script_build_panel()) is not None:
            sbp.reveal()
        self.build_panel.set_building(True)
        self._tb_build_btn.build_started.emit()
        msg = label("win.build_start", project=self.project.settings.name,
                    scene=self.project.active_scene.name)
        self.build_panel.log_info(msg)
        self.build_panel.start_build_diagnostics()
        if (sbp := self._script_build_panel()) is not None:
            sbp.log_info(msg)
            sbp.start_build_diagnostics()

        # Bridge thread-safe : BuildWorker (thread Python) → Qt main thread
        # Les callbacks de l'engine sont appelés depuis le thread de build ;
        # on les empile dans une queue et un QTimer les draine sur le main thread.
        self._build_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._build_drain = QTimer()
        self._build_drain.setInterval(30)
        self._build_drain.timeout.connect(self._drain_build_queue)

        if (sbp := self._script_build_panel()) is not None:
            sbp.console.clear()
        self._worker = BuildWorker(project=self.project, toolchain=self.toolchain)
        self._worker.on("log_line",   lambda m:  self._build_queue.put(("log",      m)))
        self._worker.on("error_line", lambda m:  self._build_queue.put(("error",    m)))
        self._worker.on("diagnostic", lambda d:  self._build_queue.put(("diagnostic", d)))
        self._worker.on("progress",   lambda f:  self._build_queue.put(("progress", f)))
        self._worker.on("finished",   lambda ok: self._build_queue.put(("finished", ok)))
        self._worker.on("rom_report", lambda r:  self._build_queue.put(("rom_report", r)))
        self._worker.start()
        self._build_drain.start()

    def _drain_build_queue(self):
        """Draine les messages du thread de build vers les widgets Qt (main thread)."""
        try:
            while True:
                kind, data = self._build_queue.get_nowait()
                sbp = self._script_build_panel()
                if kind == "log":
                    self.build_panel.log(data)
                    if sbp is not None: sbp.log(data)
                elif kind == "error":
                    self.build_panel.log_error(data)
                    if sbp is not None: sbp.log_error(data)
                elif kind == "diagnostic":
                    self.build_panel.log_diagnostic(data)
                    if sbp is not None: sbp.log_diagnostic(data)
                elif kind == "progress":
                    self._tb_build_btn.set_progress(data)
                elif kind == "rom_report":
                    self.build_panel.update_rom_report(data)
                    self._gba_bar.set_build_report(data)
                    self._update_gba_bar()
                    if sbp is not None: sbp.update_rom_report(data)
                elif kind == "finished":
                    self._build_drain.stop()
                    self._on_build_finished(data)
        except queue.Empty:
            pass

    def _on_build_finished(self, success: bool):
        self._worker = None
        self.build_panel.set_building(False)
        self.build_panel.show_build_diagnostics()
        if (panel := self._script_build_panel()) is not None:
            panel.show_build_diagnostics()
        self._tb_build_btn.build_finished.emit(success)
        sbp = self._script_build_panel()
        if success:
            self.build_panel.log_info(label("win.build_rom_ok"))
            if sbp is not None: sbp.log_info(label("win.build_rom_ok"))
            self._status.showMessage(label("win.build_ok"))
        else:
            self.build_panel.log_error(label("win.build_failed_log"))
            if sbp is not None: sbp.log_error(label("win.build_failed_log"))
            self._status.showMessage(label("win.build_error"))
