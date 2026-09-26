"""
editor/ui/script_editor/script_editor.py — Écran d'édition de scripts Lua pour acteurs GBA.

Layout :
┌──────────────────────────────────────────────────────────────┐
│  ← Retour   Hero.lua                             [Enregistrer]│
├───────────────────┬──────────────────────────────────────────┤
│  ▾ EVENTS         │                                          │
│    ● on_start     │   function on_start()                    │
│    ○ on_update    │       self:play_anim("idle")             │
│                   │   end                                    │
│  ▾ API            │                                          │
│    Mouvement      │   function on_update()                   │
│    self:move()    │       ...                                │
│    ...            │   end                                    │
│  ▾ RÉFÉRENCES     │                                          │
│    Scènes         │                                          │
│    Actors         │                                          │
│    Scripts        │                                          │
│    Prefabs        │                                          │
└───────────────────┴──────────────────────────────────────────┘
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QFrame,
    QInputDialog, QMessageBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QFileSystemWatcher

from scripting.api import EVENT_REGISTRY as _EVENT_META
from ui.common.theme import C, T
from ui.common.labels import label
from ui.common.icons import COLOR_SCRIPT
from ui.common.build_panel import BuildPanel
from .colors import _BG, _BG_HDR, _BORDER, _TEXT_HI, _TEXT_NORM, _C_EVENT
from .lua_editor import LuaEditor
from .sidebar_panel import SidebarPanel
from .script_finder_panel import ScriptFinderPanel

class ScriptEditorScreen(QWidget):
    """Écran complet d'édition de script Lua."""

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Optional[Path] = None
        self._project = None
        self._dirty = False
        self._root_scripts_dir: Optional[Path] = None

        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._refresh_events)

        self._file_watcher = QFileSystemWatcher()
        self._file_watcher.fileChanged.connect(self._on_external_change)
        self._external_reload_timer = QTimer()
        self._external_reload_timer.setSingleShot(True)
        self._external_reload_timer.setInterval(300)
        self._external_reload_timer.timeout.connect(self._reload_from_disk)

        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barre du haut ──────────────────────────────────────────
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"background:{_BG_HDR};border-bottom:1px solid {_BORDER};")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(8, 0, 8, 0)
        bar_l.setSpacing(8)

        btn_back = QPushButton(label("scred.back"))
        btn_back.setFont(QFont(T.UI, T.MD))
        btn_back.setFixedHeight(24)
        btn_back.setStyleSheet(
            f"QPushButton{{color:{_TEXT_NORM};background:none;border:1px solid {C.BORDER};"
            f"border-radius:3px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{_TEXT_HI};border-color:{C.BORDER_MID};}}"
        )
        btn_back.clicked.connect(self._on_back)
        bar_l.addWidget(btn_back)

        # Couleur alignée sur la palette canonique par type d'objet (voir ui/icons.py,
        # même source que AssetHeaderBar utilisé dans Scene Manager / Sprite Editor / Sound Mixer).
        # Pas de bandeau dédié ici : ce titre partage la barre d'outils avec Retour/Enregistrer.
        self._title_lbl = QLabel("—")
        self._title_lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._title_lbl.setStyleSheet(f"color:{COLOR_SCRIPT};")
        bar_l.addWidget(self._title_lbl, 1)

        self._save_btn = QPushButton(label("common.save"))
        self._save_btn.setFont(QFont(T.UI, T.MD))
        self._save_btn.setFixedHeight(24)
        self._save_btn.setStyleSheet(
            f"QPushButton{{color:{_C_EVENT};background:none;border:1px solid {_C_EVENT};"
            "border-radius:3px;padding:0 8px;}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
        )
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        bar_l.addWidget(self._save_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{_BORDER};")
        sep.setFixedWidth(1)
        bar_l.addWidget(sep)

        btn_new = QPushButton(label("scred.new_script_btn"))
        btn_new.setFont(QFont(T.UI, T.SM))
        btn_new.setFixedHeight(24)
        btn_new.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:none;border:1px solid {C.BORDER};"
            f"border-radius:3px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};border-color:{C.BORDER_MID};}}"
        )
        btn_new.clicked.connect(self._create_script)
        bar_l.addWidget(btn_new)

        root.addWidget(bar)

        # ── Corps : sidebar | (éditeur / log) | scripts ──────────────
        self._sidebar = SidebarPanel()
        self._sidebar.snippet_requested.connect(self._editor_insert_snippet)
        self._sidebar.stub_requested.connect(self._on_event_activated)

        self._editor = LuaEditor()
        self._editor.textChanged.connect(self._on_text_changed)

        # Colonne centrale : éditeur (haut) + log (bas)
        self.build_panel = BuildPanel()
        self.build_panel.setMinimumHeight(60)

        center_split = QSplitter(Qt.Orientation.Vertical)
        center_split.setStyleSheet(
            f"QSplitter::handle{{background:{_BORDER};}}"
            "QSplitter::handle:vertical{{height:2px;}}"
        )
        center_split.addWidget(self._editor)
        center_split.addWidget(self.build_panel)
        center_split.setSizes([600, 150])
        center_split.setStretchFactor(0, 1)
        center_split.setStretchFactor(1, 0)

        # ScriptFinderPanel — colonne droite
        self._file_tree = ScriptFinderPanel()
        self._file_tree.file_requested.connect(lambda p: self.open_script(Path(p)))
        self._file_tree.snippet_requested.connect(self._editor_insert_snippet)

        # Corps dans un QSplitter horizontal : colonnes redimensionnables à la
        # souris, comme le Sprite Editor / Scene Manager (panneaux « étirables »
        # bornés par min/max, pas de largeur fixe). Le centre s'étire, les côtés
        # gardent leur taille. childrenCollapsible=False : la poignée ne réduit
        # pas une colonne à 0 par accident.
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setStyleSheet(
            f"QSplitter::handle{{background:{_BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{C.ACCENT};}}"
        )
        body.setChildrenCollapsible(False)
        body.addWidget(self._sidebar)
        body.addWidget(center_split)
        body.addWidget(self._file_tree)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([220, 900, 224])
        root.addWidget(body, 1)

    # ── API publique ──────────────────────────────────────────────────

    def open_script(self, path: Path, line: int | None = None):
        watched = self._file_watcher.files()
        if watched:
            self._file_watcher.removePaths(watched)

        self._path = path
        self._title_lbl.setText(path.name)
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        self._editor.blockSignals(True)
        self._editor.setPlainText(source)
        self._editor.blockSignals(False)
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._refresh_events()

        ctx = self._detect_context(path)
        self._sidebar.set_context(ctx)
        self._editor.set_completion_context(ctx)
        self._file_tree.highlight_file(path)

        if path.exists():
            self._file_watcher.addPath(str(path))

        # Saut à la ligne (journal de build cliqué) — après setPlainText, quand
        # les blocs existent.
        if line is not None:
            self._editor.goto_line(line)

    def load_project(self, project):
        """Connecte le projet pour peupler les sections dynamiques.

        `load_project` et non `set_project` : c'est le contrat `ProjectScreen`
        (cf. ui/screens.py), que les six autres écrans écrivaient déjà ainsi."""
        self._project = project
        self._file_tree.set_project(project)
        self._refresh_catalogs()
        if project:
            scripts_dir = getattr(project, "scripts_dir", None) or \
                          project.root / "project" / "scripts"
            self._root_scripts_dir = scripts_dir
            self._file_tree.set_root(scripts_dir)

    def _refresh_catalogs(self):
        """Re-dérive ce qui dépend des CATALOGUES du projet : la section
        RÉFÉRENCES de la sidebar et les noms d'autocomplétion. Tout le reste
        (fichier ouvert, contexte, arbre) est intact."""
        from scripting.project_names import names_by_domain
        self._sidebar.set_project(self._project)
        self._editor.set_completion_project_names(
            names_by_domain(self._project) if self._project else None)

    def refresh(self):
        """Re-dérive à la revisite de l'écran — appelé au centre par
        `Window._show_screen` (chantier « L'écran resynchronisé à sa revisite »).
        Un sprite, un fond, un son, un global ou une police a pu naître dans un
        AUTRE écran depuis la dernière visite ; sans cela la sidebar et surtout
        l'autocomplétion ignoraient en silence les noms neufs. Bon marché : on ne
        relit que des noms déjà en mémoire, pas de décodage d'asset."""
        if self._project is not None:
            self._refresh_catalogs()

    # ── Détection contexte ────────────────────────────────────────────

    def _detect_context(self, path: Path) -> str:
        """Ce que l'éditeur propose (événements, `self`) dépend de ce à quoi le script est
        ATTACHÉ, jamais de son dossier. Seul un behavior se reconnaît à son dossier : c'est
        un module, attaché à rien, référencé par son chemin."""
        if path.parent == getattr(self._project, "scripts_behaviors_dir", None):
            return "behavior"
        if self._project is not None:
            from core.script_owners import family_of_script
            family = family_of_script(self._project, path)
            if family:
                return family
        return "unknown"

    # ── Handlers ─────────────────────────────────────────────────────

    def _editor_insert_snippet(self, snippet: str):
        self._editor.insert_at_cursor(snippet)

    def _on_text_changed(self):
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._title_lbl.setText(f"● {self._path.name}" if self._path else "●")
        self._refresh_timer.start()

    def _on_event_activated(self, event_name: str):
        defined = self._get_defined_events()
        if event_name in defined:
            self._editor.jump_to_function(event_name)
        else:
            meta = _EVENT_META.get(event_name, {})
            stub = meta.get("stub", f"function {event_name}()\n    \nend\n")
            self._editor.insert_stub(stub)
            self._editor.jump_to_function(event_name)

    def _refresh_events(self):
        self._sidebar.update_defined_events(self._get_defined_events())

    def _get_defined_events(self) -> set[str]:
        source = self._editor.toPlainText()
        defined = set()
        try:
            from scripting.parser import parse as lua_parse
            script = lua_parse(source)
            defined = {fn.name for fn in script.functions}
        except Exception:
            import re
            for m in re.finditer(r"^function\s+(\w+)\s*\(", source, re.MULTILINE):
                defined.add(m.group(1))
        return defined

    def _on_external_change(self, path: str):
        if Path(path).exists():
            self._file_watcher.addPath(path)
        if not self._dirty:
            self._external_reload_timer.start()
        else:
            self._title_lbl.setText(label(
                "scred.external_conflict",
                name=self._path.name if self._path else "?"))

    def _reload_from_disk(self):
        if not self._path or not self._path.exists():
            return
        source = self._path.read_text(encoding="utf-8")
        pos = self._editor.textCursor().position()
        self._editor.blockSignals(True)
        self._editor.setPlainText(source)
        self._editor.blockSignals(False)
        cur = self._editor.textCursor()
        cur.setPosition(min(pos, len(source)))
        self._editor.setTextCursor(cur)
        self._title_lbl.setText(f"↻ {self._path.name}")
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._refresh_events()

    # ── Création de scripts ───────────────────────────────────────────

    def _create_script(self):
        if not self._root_scripts_dir:
            QMessageBox.warning(self, label("scred.no_project_title"),
                                label("scred.no_project_msg"))
            return
        name, ok = QInputDialog.getText(self, label("scred.new_script_title"),
                                        label("scred.script_name"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".lua"):
            name += ".lua"
        self._root_scripts_dir.mkdir(parents=True, exist_ok=True)
        path = self._root_scripts_dir / name
        if path.exists():
            QMessageBox.warning(self, label("scred.file_exists_title"),
                                label("scred.file_exists_msg", name=name))
            return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        ctx = ScriptTemplateContext(kind="empty", name=name[:-4] if name.endswith(".lua") else name)
        path.write_text(generate_script_template(ctx), encoding="utf-8")
        self._file_tree.set_root(self._root_scripts_dir)
        self._file_tree.highlight_file(path)
        self.open_script(path)

    # ── Navigation ───────────────────────────────────────────────────

    def _on_back(self):
        if self._dirty:
            self._save()
        self.back_requested.emit()

    # ── Sauvegarde ───────────────────────────────────────────────────

    def flush_pending_edits(self):
        """Appelé par le Ctrl+S global (window.py) avant la sauvegarde projet —
        persiste le script en cours d'édition s'il a des changements non sauvés."""
        if self._dirty:
            self._save()

    def _save(self):
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._editor.toPlainText(), encoding="utf-8")
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._title_lbl.setText(self._path.name)
