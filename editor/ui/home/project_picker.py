"""
ui/project_picker.py — HomeScreen : écran d'accueil affiché au lancement.

• Liste les projets récemment ouverts (stockée dans ~/.backstage_recent.json)
• Double-clic ou Ouvrir → ouvre le projet
• Nouveau → crée un nouveau projet dans PROJECTS_DIR
• Clear list → supprime les entrées qui pointent vers des dossiers morts
• Statut devkitPro / mGBA avec lien de téléchargement discret si manquant
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QFileDialog, QSizePolicy,
    QLineEdit, QWidget, QMessageBox, QTabWidget, QComboBox,
)
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread

from ui.common.theme import C, T, QSS, tint
from ui.common.widgets import W, HoverIconButton
from ui.common.labels import label
from ui.common.reveal import reveal_in_file_manager
from core.app_info import APP_NAME
from core.toolchain import Toolchain, DEVKITPRO_URL, MGBA_URL
from core.project_templates import (
    ProjectTemplate, TEMPLATES, target_dir as template_target_dir,
    is_downloaded as template_is_downloaded, download_template,
)
from core.project_starters import USER_STARTERS_DIR, available_starters
from core.project_paths import (
    PROJECT_EXT, ProjectManifestError, ProjectNotFoundError, find_manifest)

# Emplacement proposé par défaut pour un nouveau projet — jamais créé au
# lancement. Il ne sert qu'à préremplir les champs et les dialogues de
# fichiers ; le dossier n'apparaît que si l'utilisateur crée réellement un
# projet dedans (Project.create fait le mkdir parents=True).
PROJECTS_DIR  = Path.home() / f"{APP_NAME}Projects"
_RECENT_FILE  = Path.home() / f".{APP_NAME.lower()}_recent.json"
_MAX_RECENT   = 12


# ── Persistance des récents ───────────────────────────────────────────

def load_recent() -> list[Path]:
    try:
        data = json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
        return [Path(p) for p in data if isinstance(p, str)]
    except Exception:
        return []


def save_recent(paths: list[Path]):
    try:
        _RECENT_FILE.write_text(
            json.dumps([str(p) for p in paths[:_MAX_RECENT]]),
            encoding="utf-8",
        )
    except Exception:
        pass


def push_recent(path: Path):
    recent = load_recent()
    recent = [p for p in recent if p != path]
    recent.insert(0, path)
    save_recent(recent[:_MAX_RECENT])


# ── Statut toolchain (devkitPro / mGBA) ─────────────────────────────────

class ToolchainStatus(QWidget):
    """
    Statut discret devkitPro / mGBA sur l'écran d'accueil.
    Une explication + un lien de téléchargement n'apparaissent que pour ce
    qui manque, sans bloquer l'utilisateur — pas de popup forcé au lancement.
    """

    configure_requested = pyqtSignal()

    _EXPLAIN_KEYS = {
        "devkitPro": "home.status.explain_devkitpro",
        "mGBA":      "home.status.explain_mgba",
    }

    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self._toolchain = toolchain
        self.setStyleSheet("background:transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.refresh()

    def refresh(self):
        """Relance la détection et reconstruit l'affichage."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        checks = [
            ("devkitPro", self._toolchain.devkitpro_ok, DEVKITPRO_URL),
            ("mGBA",      self._toolchain.mgba_ok,      MGBA_URL),
        ]
        missing = [c for c in checks if not c[1]]

        row = QWidget()
        row.setStyleSheet("background:transparent;")
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(16)
        for name, ok, _ in checks:
            lbl = QLabel(f"{'✓' if ok else '✗'} {name}")
            lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            lbl.setStyleSheet(
                f"color:{C.TEXT_NORM if ok else C.ACCENT_RED};background:transparent;"
            )
            row_l.addWidget(lbl)
        row_l.addStretch()

        cfg = QLabel(f'<a href="#" style="color:#555;text-decoration:none;">⚙ {label("home.status.configure")}</a>')
        cfg.setFont(QFont(T.UI, T.XS))
        cfg.setStyleSheet("background:transparent;")
        cfg.linkActivated.connect(lambda _: self.configure_requested.emit())
        row_l.addWidget(cfg)

        self._layout.addWidget(row)

        for name, ok, url in missing:
            expl = QLabel(
                f'<span style="color:#666;">{name} — {label(self._EXPLAIN_KEYS[name])}. '
                f'<a href="{url}" style="color:#4c8caf;">{label("home.status.download")}</a></span>'
            )
            expl.setFont(QFont(T.UI, T.XS))
            expl.setStyleSheet("background:transparent;")
            expl.setOpenExternalLinks(True)
            expl.setWordWrap(True)
            self._layout.addWidget(expl)


# ── Widget d'une entrée ───────────────────────────────────────────────

class _ProjectItem(QWidget):
    remove_requested = pyqtSignal(object)  # Path : retire seulement l'entrée récente

    def __init__(self, path: Path, dead: bool = False, parent=None):
        super().__init__(parent)
        self.path = path
        self.dead = dead

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(10)

        # Icône dossier
        icon = QLabel("📁" if not dead else "⚠")
        icon.setFont(QFont(T.UI, 16))
        icon.setFixedWidth(28)
        icon.setStyleSheet("background:transparent;")
        hl.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)

        name_lbl = QLabel(path.name)
        name_lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        name_lbl.setStyleSheet(
            f"color:{'#888' if dead else C.TEXT_HI};background:transparent;"
        )
        col.addWidget(name_lbl)

        path_lbl = QLabel(str(path))
        path_lbl.setFont(QFont(T.MONO, T.XS))
        path_lbl.setStyleSheet(
            f"color:{C.ACCENT_RED if dead else C.TEXT_DIM};background:transparent;"
        )
        path_lbl.setWordWrap(False)
        col.addWidget(path_lbl)

        hl.addLayout(col, 1)

        if dead:
            dead_badge = QLabel(label("home.project.not_found"))
            dead_badge.setFont(QFont(T.UI, T.XS))
            dead_badge.setStyleSheet(
                f"color:{C.ACCENT_RED};background:{tint(C.ACCENT_RED, 0.15)};border:1px solid {C.ACCENT_RED};"
                "border-radius:3px;padding:1px 5px;"
            )
            hl.addWidget(dead_badge)
        else:
            btn_reveal = W.btn_reveal(label("home.project.reveal"))
            btn_reveal.clicked.connect(lambda: reveal_in_file_manager(self.path))
            hl.addWidget(btn_reveal)

        # Retire ce projet de la liste des récents. Le dossier et son contenu
        # restent intacts sur le disque.
        btn_remove = HoverIconButton("clear", C.ACCENT_RED, "#ff3030")
        btn_remove.setFixedSize(22, 22)
        btn_remove.setIconSize(QSize(14, 14))
        btn_remove.setToolTip(label("home.project.remove_recent"))
        btn_remove.setStyleSheet(
            f"QToolButton{{background:transparent;border:none;padding:0;}}"
        )
        btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.path))
        hl.addWidget(btn_remove)


# ── Widget d'un template téléchargeable ────────────────────────────────

class _TemplateItem(QWidget):
    """Une entrée de l'onglet Templates : nom + description + bouton d'état
    (Download → ✓ Downloaded une fois sur le disque). Le double-clic sur la
    ligne ouvre le projet extrait, géré par HomeScreen."""

    download_requested = pyqtSignal(object)  # ProjectTemplate
    _TEXT_KEYS = {
        "pong": ("home.template.pong.name", "home.template.pong.description"),
    }

    def __init__(self, template: ProjectTemplate, downloaded: bool, parent=None):
        super().__init__(parent)
        self.template = template
        self.downloaded = downloaded

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(10)

        icon = QLabel("🧩")
        icon.setFont(QFont(T.UI, 16))
        icon.setFixedWidth(28)
        icon.setStyleSheet("background:transparent;")
        hl.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        name_key, description_key = self._TEXT_KEYS.get(
            template.id, ("", ""))
        name_lbl = QLabel(label(name_key) if name_key else template.display_name)
        name_lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        name_lbl.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        col.addWidget(name_lbl)
        desc_lbl = QLabel(label(description_key) if description_key
                          else template.description)
        desc_lbl.setFont(QFont(T.UI, T.XS))
        desc_lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        col.addWidget(desc_lbl)
        hl.addLayout(col, 1)

        self._btn = QPushButton()
        self._btn.setFont(QFont(T.UI, T.SM))
        self._btn.setFixedHeight(26)
        self._btn.clicked.connect(lambda: self.download_requested.emit(self.template))
        hl.addWidget(self._btn)

        self.set_downloaded(downloaded)

    def set_downloaded(self, downloaded: bool):
        self.downloaded = downloaded
        if downloaded:
            self._btn.setText(f"✓ {label('home.template.downloaded')}")
            self._btn.setEnabled(False)
            self._btn.setStyleSheet(
                f"QPushButton{{color:{C.TEXT_DIM};background:transparent;"
                f"border:1px solid {C.BORDER_MID};border-radius:3px;padding:2px 10px;}}"
                f"QPushButton:disabled{{color:{C.TEXT_DIM};border-color:{C.BORDER_MID};}}"
            )
        else:
            self._btn.setText(label("home.template.download"))
            self._btn.setEnabled(True)
            self._btn.setStyleSheet(QSS.button_accent_outline)

    def set_busy(self, text: str):
        self._btn.setEnabled(False)
        self._btn.setText(text)


class _TemplateDownloadThread(QThread):
    """Télécharge un template hors du thread UI — le zip du dépôt entier
    peut prendre plusieurs secondes à récupérer et extraire."""

    progress    = pyqtSignal(str)
    succeeded   = pyqtSignal(str)   # chemin extrait (str : Path traverse mal les signaux Qt)
    failed      = pyqtSignal(str)

    def __init__(self, template: ProjectTemplate, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._template = template
        self._projects_dir = projects_dir

    def run(self):
        try:
            dest = download_template(
                self._template, self._projects_dir, progress_cb=self.progress.emit
            )
            self.succeeded.emit(str(dest))
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Écran d'accueil ───────────────────────────────────────────────────

class HomeScreen(QDialog):
    """
    Écran d'accueil — affiché au lancement (et rouvrable via _go_home()
    dans window.py pour changer de projet en cours de session).

    Attributs après exec() == Accepted :
      result_path   : Path vers le dossier projet choisi / créé
      result_is_new : bool — True si nouveau projet
      result_name   : str  — nom saisi (si nouveau)
      result_starter: str — preset choisi (si nouveau)
    """

    result_path:   Optional[Path] = None
    result_is_new: bool           = False
    result_name:   str            = ""
    result_starter: str           = "Basic"
    _TEMPLATE_PROGRESS_KEYS = {
        "Downloading…": "home.template.downloading",
        "Extracting…": "home.template.extracting",
    }

    def __init__(self, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        self._recent       = load_recent()
        self._toolchain    = Toolchain()

        self.setWindowTitle(label("home.window_title", app_name=APP_NAME))
        self.setMinimumSize(580, 460)
        self.setMaximumSize(720, 640)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{C.BG_BASE};}}"
        )

        self._download_thread: Optional[_TemplateDownloadThread] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-bottom:1px solid {C.BORDER_DARK};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel(APP_NAME)
        title_lbl.setFont(QFont(T.UI, 16, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        sub_lbl = QLabel(label("home.subtitle"))
        sub_lbl.setFont(QFont(T.UI, T.SM))
        sub_lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")

        hc = QVBoxLayout()
        hc.setSpacing(2)
        hc.addWidget(title_lbl)
        hc.addWidget(sub_lbl)
        hl.addLayout(hc, 1)
        root.addWidget(hdr)

        # ── Onglets : Projects (récents) / Templates (démos) ───────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(QSS.tab)
        self._tabs.addTab(self._build_projects_tab(), label("home.tab.projects"))
        # Sans source de modèles configurée (cf. core/app_info.APP_TEMPLATES_URL),
        # il n'y a rien à lister : pas d'onglet vide qui promet un téléchargement.
        if TEMPLATES:
            self._tabs.addTab(self._build_templates_tab(), label("home.tab.templates"))
        root.addWidget(self._tabs, 1)

        # ── Statut toolchain (devkitPro / mGBA) ────────────────────
        status_wrap = QWidget()
        status_wrap.setStyleSheet(
            f"background:{C.BG_PANEL};border-top:1px solid {C.BORDER_DARK};"
        )
        sw_l = QVBoxLayout(status_wrap)
        sw_l.setContentsMargins(16, 8, 16, 8)
        self._toolchain_status = ToolchainStatus(self._toolchain)
        self._toolchain_status.configure_requested.connect(self._open_toolchain_dialog)
        sw_l.addWidget(self._toolchain_status)
        root.addWidget(status_wrap)

    # ── Onglet Projects ────────────────────────────────────────────

    def _build_projects_tab(self) -> QWidget:
        tab = QWidget()
        tl = QVBoxLayout(tab)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE};border:none;outline:none;}}"
            f"QListWidget::item{{padding:0;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )
        self._list.setIconSize(QSize(0, 0))
        self._list.setSpacing(0)
        self._list.itemDoubleClicked.connect(self._open_selected)
        tl.addWidget(self._list, 1)

        self._populate()

        # ── Message si liste vide ─────────────────────────────────
        self._empty_lbl = QLabel(label("home.empty"))
        self._empty_lbl.setFont(QFont(T.UI, T.MD))
        self._empty_lbl.setStyleSheet(
            f"color:{C.TEXT_MUTED};background:{C.BG_BASE};"
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setVisible(not self._recent)
        tl.addWidget(self._empty_lbl)

        # ── Barre du bas : Clear · Load · Open · Create ────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-top:1px solid {C.BORDER_DARK};"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)

        btn_clear = QPushButton(f"🗑  {label('home.clear')}")
        btn_clear.setFont(QFont(T.UI, T.SM))
        btn_clear.setFixedHeight(30)
        btn_clear.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT_RED};background:{C.BG_INPUT};"
            f"border:1px solid {tint(C.ACCENT_RED, 0.35)};border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{tint(C.ACCENT_RED, 0.15)};border-color:{C.ACCENT_RED};}}"
            f"QPushButton:pressed{{background:{tint(C.ACCENT_RED, 0.25)};}}"
        )
        btn_clear.setToolTip(label("home.clear_tip"))
        btn_clear.clicked.connect(self._clear_dead)
        fl.addWidget(btn_clear)

        fl.addStretch()

        btn_load = QPushButton(label("home.load"))
        btn_load.setFont(QFont(T.UI, T.SM))
        btn_load.setFixedHeight(30)
        btn_load.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};border-color:#555;}}"
        )
        btn_load.clicked.connect(self._browse)
        fl.addWidget(btn_load)

        self._btn_open = QPushButton(label("common.open"))
        self._btn_open.setFont(QFont(T.UI, T.SM))
        self._btn_open.setFixedHeight(30)
        self._btn_open.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};border-color:#555;}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
        )
        self._btn_open.clicked.connect(self._open_selected)
        fl.addWidget(self._btn_open)

        btn_new = QPushButton(f"+ {label('home.create_project')}")
        btn_new.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        btn_new.setFixedHeight(30)
        btn_new.setStyleSheet(
            f"QPushButton{{color:{C.ON_ACCENT};background:{C.ACCENT};"
            f"border:none;border-radius:4px;padding:0 14px;}}"
            f"QPushButton:hover{{background:{C.ACCENT_HOVER};}}"
            f"QPushButton:pressed{{background:{C.ACCENT_PRESSED};}}"
        )
        btn_new.clicked.connect(self._new_project)
        fl.addWidget(btn_new)

        tl.addWidget(footer)

        # Sélectionner le premier item valide
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if w and not w.dead:
                self._list.setCurrentRow(i)
                break

        # Enter pour ouvrir
        self._list.itemSelectionChanged.connect(self._on_sel)
        self._on_sel()

        return tab

    # ── Onglet Templates ───────────────────────────────────────────

    def _build_templates_tab(self) -> QWidget:
        tab = QWidget()
        tl = QVBoxLayout(tab)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        self._tpl_list = QListWidget()
        self._tpl_list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE};border:none;outline:none;}}"
            f"QListWidget::item{{padding:0;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )
        self._tpl_list.setIconSize(QSize(0, 0))
        self._tpl_list.setSpacing(0)
        self._tpl_list.itemDoubleClicked.connect(self._open_template_selected)
        tl.addWidget(self._tpl_list, 1)

        self._populate_templates()

        return tab

    # ── Population ─────────────────────────────────────────────────

    def _populate(self):
        self._list.clear()
        for path in self._recent:
            dead = not path.exists()
            item = QListWidgetItem(self._list)
            w = _ProjectItem(path, dead)
            w.remove_requested.connect(self._remove_recent)
            item.setSizeHint(QSize(0, 64))
            self._list.addItem(item)
            self._list.setItemWidget(item, w)

    def _populate_templates(self):
        self._tpl_list.clear()
        for template in TEMPLATES:
            downloaded = template_is_downloaded(template, self._projects_dir)
            item = QListWidgetItem(self._tpl_list)
            w = _TemplateItem(template, downloaded)
            w.download_requested.connect(self._download_template)
            item.setSizeHint(QSize(0, 56))
            self._tpl_list.addItem(item)
            self._tpl_list.setItemWidget(item, w)

    # ── Actions — Projects ────────────────────────────────────────

    def _on_sel(self):
        row = self._list.currentRow()
        w = self._list.itemWidget(self._list.item(row)) if row >= 0 else None
        self._btn_open.setEnabled(bool(w and not w.dead))

    def _open_selected(self, *_):
        row = self._list.currentRow()
        if row < 0:
            return
        w = self._list.itemWidget(self._list.item(row))
        if not w or w.dead:
            return
        self._accept(w.path, is_new=False)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._tabs.currentIndex() == 0:
                self._open_selected()
            else:
                self._open_template_selected()
        else:
            super().keyPressEvent(ev)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, label("home.browse_title"), str(self._projects_dir)
        )
        if path:
            self._accept(Path(path), is_new=False)

    def _new_project(self):
        dlg = NewProjectDialog(self._projects_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.result_starter = dlg.result_starter
            self._accept(dlg.result_path, is_new=True, name=dlg.result_name)

    def _clear_dead(self):
        alive = [p for p in self._recent if p.exists()]
        save_recent(alive)
        self._recent = alive
        self._populate()
        self._empty_lbl.setVisible(not self._recent)
        self._on_sel()

    def _remove_recent(self, path: Path):
        """Retire immédiatement une entrée des récents, sans action disque."""
        self._recent = [recent for recent in self._recent if recent != path]
        save_recent(self._recent)
        self._populate()
        self._empty_lbl.setVisible(not self._recent)
        self._on_sel()

    def _open_toolchain_dialog(self):
        from ui.common.settings_dialog import SettingsDialog
        from core.external_tools import ExternalTools
        dlg = SettingsDialog(self._toolchain, ExternalTools(), "Toolchains", self)
        dlg.exec()
        self._toolchain_status.refresh()

    def _accept(self, path: Path, is_new: bool = False, name: str = ""):
        # Un dossier à ouvrir doit porter un manifeste : sinon on le dit ici et
        # on reste sur l'accueil, au lieu de pousser dans les récents (et
        # d'ouvrir) un projet fantôme.
        if not is_new:
            try:
                if find_manifest(path) is None:
                    raise ProjectNotFoundError(
                        f"« {path.name} » n'est pas un projet : aucun fichier "
                        f"{PROJECT_EXT} dans ce dossier.")
            except ProjectManifestError as exc:
                QMessageBox.critical(self, label("common.open_project"), str(exc))
                return
        push_recent(path)
        self.result_path   = path
        self.result_is_new = is_new
        self.result_name   = name
        self.accept()

    # ── Actions — Templates ───────────────────────────────────────

    def _row_of_template(self, template: ProjectTemplate) -> Optional[int]:
        for i in range(self._tpl_list.count()):
            w = self._tpl_list.itemWidget(self._tpl_list.item(i))
            if w and w.template is template:
                return i
        return None

    def _download_template(self, template: ProjectTemplate):
        if self._download_thread and self._download_thread.isRunning():
            return  # un téléchargement à la fois
        row = self._row_of_template(template)
        w = self._tpl_list.itemWidget(self._tpl_list.item(row)) if row is not None else None
        if w:
            w.set_busy(label("home.template.downloading"))

        thread = _TemplateDownloadThread(template, self._projects_dir, self)
        thread.progress.connect(
            lambda msg: w.set_busy(self._template_progress_text(msg)) if w else None)
        thread.succeeded.connect(lambda _dest: self._on_template_downloaded(template))
        thread.failed.connect(lambda err: self._on_template_download_failed(template, err))
        self._download_thread = thread
        thread.start()

    def _on_template_downloaded(self, template: ProjectTemplate):
        row = self._row_of_template(template)
        if row is not None:
            w = self._tpl_list.itemWidget(self._tpl_list.item(row))
            if w:
                w.set_downloaded(True)

    @classmethod
    def _template_progress_text(cls, raw: str) -> str:
        """Le worker ne connaît que son état ; l'UI traduit son affichage."""
        return label(cls._TEMPLATE_PROGRESS_KEYS.get(raw, raw))

    def _on_template_download_failed(self, template: ProjectTemplate, message: str):
        row = self._row_of_template(template)
        if row is not None:
            w = self._tpl_list.itemWidget(self._tpl_list.item(row))
            if w:
                w.set_downloaded(False)
        QMessageBox.warning(self, label("home.download_failed"), message)

    def _open_template_selected(self, *_):
        row = self._tpl_list.currentRow()
        if row < 0:
            return
        w = self._tpl_list.itemWidget(self._tpl_list.item(row))
        if not w or not w.downloaded:
            return
        self._accept(template_target_dir(w.template, self._projects_dir), is_new=False)


# ── Dialogue nouveau projet ───────────────────────────────────────────

class NewProjectDialog(QDialog):
    """
    Nom + dossier parent éditables séparément (le nom ne dicte plus
    l'emplacement) ; le chemin final s'affiche en aperçu sous les deux champs.
    """

    result_path: Optional[Path] = None
    result_name: str            = ""
    result_starter: str         = "Basic"

    def __init__(self, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        self.setWindowTitle(label("common.new_project"))
        self.setFixedSize(480, 320)
        self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(52)
        hdr.setStyleSheet(
            f"background:{C.BG_PANEL};border-bottom:1px solid {C.BORDER_DARK};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(10)
        icon_lbl = QLabel("📁")
        icon_lbl.setFont(QFont(T.UI, T.XXL))
        icon_lbl.setStyleSheet("background:transparent;")
        hl.addWidget(icon_lbl)
        title_lbl = QLabel(label("common.new_project"))
        title_lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        hl.addWidget(title_lbl)
        hl.addStretch()
        root.addWidget(hdr)

        # ── Corps ────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 18, 20, 0)
        bl.setSpacing(14)

        def _field_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
            return lbl

        # Nom du projet
        bl.addWidget(_field_label(label("home.new.name")))
        self._name_edit = QLineEdit()
        self._name_edit.setFont(QFont(T.MONO, T.MD))
        self._name_edit.setStyleSheet(QSS.lineedit)
        self._name_edit.setFixedHeight(32)
        self._name_edit.setPlaceholderText(label("home.new.name_placeholder"))
        bl.addWidget(self._name_edit)

        # Les presets personnels sont de simples dossiers sous le répertoire
        # utilisateur : aucun format caché, ni import/export propriétaire.
        bl.addWidget(_field_label(label('projpick.project_preset')))
        self._starter_combo = QComboBox()
        self._starter_combo.setFont(QFont(T.UI, T.SM))
        self._starter_combo.setStyleSheet(QSS.lineedit)
        self._starter_combo.setFixedHeight(32)
        for starter in available_starters():
            caption = starter.display_name if starter.builtin else label('projpick.display_name_personal', display_name=starter.display_name)
            self._starter_combo.addItem(caption, starter.id)
        self._starter_combo.setToolTip(
            label('projpick.add_personal_hint', USER_STARTERS_DIR=USER_STARTERS_DIR)
        )
        bl.addWidget(self._starter_combo)

        # Dossier parent
        bl.addWidget(_field_label(label("home.new.location")))
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._dir_edit = QLineEdit(str(projects_dir))
        self._dir_edit.setFont(QFont(T.MONO, T.MD))
        self._dir_edit.setStyleSheet(QSS.lineedit)
        self._dir_edit.setFixedHeight(32)
        btn_dir = QPushButton(label("common.browse"))
        btn_dir.setFont(QFont(T.UI, T.SM))
        btn_dir.setFixedHeight(32)
        btn_dir.setStyleSheet(QSS.button_ghost)
        btn_dir.clicked.connect(self._pick_dir)
        row2.addWidget(self._dir_edit, 1)
        row2.addWidget(btn_dir)
        bl.addLayout(row2)

        # Aperçu du chemin final
        self._preview_lbl = QLabel()
        self._preview_lbl.setFont(QFont(T.MONO, T.XS))
        self._preview_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        self._preview_lbl.setWordWrap(True)
        bl.addWidget(self._preview_lbl)

        bl.addStretch()
        root.addWidget(body, 1)

        # ── Boutons ──────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background:{C.BG_PANEL};border-top:1px solid {C.BORDER_DARK};"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)
        fl.addStretch()
        btn_cancel = QPushButton(label("common.cancel"))
        btn_cancel.setFont(QFont(T.UI, T.SM))
        btn_cancel.setFixedHeight(30)
        btn_cancel.setStyleSheet(QSS.button_ghost)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(label("common.create"))
        btn_ok.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        btn_ok.setFixedHeight(30)
        btn_ok.setStyleSheet(
            f"QPushButton{{color:{C.ON_ACCENT};background:{C.ACCENT};"
            f"border:none;border-radius:4px;padding:0 16px;}}"
            f"QPushButton:hover{{background:{C.ACCENT_HOVER};}}"
            f"QPushButton:pressed{{background:{C.ACCENT_PRESSED};}}"
        )
        btn_ok.clicked.connect(self._create)
        fl.addWidget(btn_cancel)
        fl.addWidget(btn_ok)
        root.addWidget(footer)

        self._name_edit.textChanged.connect(self._update_preview)
        self._dir_edit.textChanged.connect(self._update_preview)
        self._update_preview()

        self._name_edit.setFocus()
        self._name_edit.returnPressed.connect(self._create)

    def _update_preview(self):
        name = self._name_edit.text().strip()
        dir_ = self._dir_edit.text().strip() or str(self._projects_dir)
        if name:
            self._preview_lbl.setText(f"→ {Path(dir_) / name}")
        else:
            self._preview_lbl.setText(f"→ {dir_}")

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, label("home.new.pick_dir_title"),
            self._dir_edit.text().strip() or str(self._projects_dir)
        )
        if path:
            self._dir_edit.setText(path)

    def _create(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return
        dir_ = self._dir_edit.text().strip()
        if not dir_:
            self._dir_edit.setFocus()
            return
        path = Path(dir_) / name
        if path.exists():
            QMessageBox.warning(self, label("common.error"),
                                label("home.new.exists", name=name))
            return
        # Le dossier n'est PAS créé ici : c'est `Project.create` qui le fait. Le
        # créer avant laissait, si la création échouait ensuite, un dossier vide.
        self.result_path = path
        self.result_name = name
        self.result_starter = self._starter_combo.currentData() or "Basic"
        self.accept()
