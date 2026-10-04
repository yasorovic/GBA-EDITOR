"""
ui/common/settings_dialog.py — Réglages du logiciel : un dialogue, cinq
catégories dans une colonne de gauche (Toolchains / Theme / Interface /
Shortcuts / External Tools), un panneau à droite. Remplace l'ancien `ToolchainDialog`
(OK/Cancel) — ici chaque champ se sauvegarde à l'instant où il change, comme
`Toolchain`/`Keybindings`/`ExternalTools` le font déjà chacun de leur côté :
un bouton Close referme l'écran, il n'y a rien à annuler.

Portée des catégories, volontairement inégale (2026-08-23) :

  - **Toolchains** — devkitPro + mgba, ce qui existait déjà dans l'ancien
    dialogue, réemployé tel quel.
  - **Theme** — un seul thème existe aujourd'hui (indigo/périwinkle,
    cf. ARCHITECTURE.md « Thème GBA redesign ») : l'écran le DIT plutôt que
    de proposer un choix qui n'existe pas.
  - **Interface** — ce que l'éditeur MONTRE de lui-même
    (`core/interface_preferences.py`) : la langue et l'affichage des astuces,
    le niveau 3 des notices (ROADMAP v0.11). Ces réglages ont d'abord vécu dans
    les réglages du PROJET ; il en est sorti parce que `project.json` est
    versionné — couper les astuces les coupait pour toute l'équipe — et parce
    qu'un réglage de projet passe par l'historique d'annulation, où une
    préférence de machine n'a rien à faire.
  - **Shortcuts** — les raccourcis remappables de `core/keybindings.py`.
    Persisté immédiatement ; les sites déjà construits avec `bind()` se
    remettent à jour EN COURS DE SESSION (`Keybindings.changed`), les autres
    (menus/canvas déjà ouverts ailleurs dans le code sans passer par `bind`,
    s'il y en avait) au prochain lancement.
  - **External Tools** — trois chemins persistés (image / son / police),
    PAS câblés à un bouton « Edit externally » nulle part encore — portée
    resserrée à la demande (2026-08-23), le câblage est un chantier séparé.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QLabel, QLineEdit, QPushButton, QFileDialog,
    QFrame, QGridLayout, QKeySequenceEdit, QScrollArea,
    QCheckBox, QComboBox, QMainWindow,
)
from PyQt6.QtGui import QFont, QKeySequence
from PyQt6.QtCore import Qt, QProcess

from ui.common.theme import C, T, QSS
from ui.common.notice import refresh_tips
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common import catalog
from core.app_info import APP_NAME
from core.interface_preferences import (
    tips_shown, set_tips_shown, interface_language, set_interface_language,
    interface_theme, set_interface_theme,
    interface_scale_percent, set_interface_scale_percent, SCALE_CHOICES,
)
from core.toolchain import Toolchain
from core.external_tools import ExternalTools, TOOL_KINDS
from ui.common.widgets import CollapsibleCard
from core.keybindings import (
    get_keybindings, Binding, BINDINGS, DISPLAY_ONLY,
)


def _field_font() -> QFont:
    return QFont(T.MONO, T.MD)


def _path_row(parent_layout, label_text: str, initial: str,
             browse_fn) -> QLineEdit:
    """Une ligne label + chemin + Browse — même geste pour devkitPro/mgba/les
    3 outils externes, un seul endroit qui la dessine."""
    row = QHBoxLayout()
    n = QLabel(label_text)
    n.setFont(QFont(T.UI, T.MD))
    n.setFixedWidth(140)
    edit = QLineEdit(initial)
    edit.setFont(_field_font())
    edit.setStyleSheet(QSS.lineedit)
    btn = QPushButton(label("common.browse"))
    btn.setStyleSheet(QSS.button_ghost)
    btn.setFixedWidth(90)
    btn.clicked.connect(lambda: browse_fn(edit))
    row.addWidget(n)
    row.addWidget(edit, 1)
    row.addWidget(btn)
    parent_layout.addLayout(row)
    return edit


def _category_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
    lbl.setStyleSheet(f"color:{C.TEXT_HI};")
    return lbl


# ── Toolchains ──────────────────────────────────────────────────────────

class ToolchainsPanel(QWidget):
    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self._toolchain = toolchain
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title(label("settings.cat.toolchains")))
        note = QLabel(label("settings.toolchains.hint"))
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._dkp_edit = _path_row(lay, "devkitPro", str(toolchain.devkitpro_path or ""),
                                   self._browse_dkp)
        self._dkp_edit.editingFinished.connect(self._commit_dkp)
        self._mgba_edit = _path_row(lay, "mgba", str(toolchain.mgba_path or ""),
                                    self._browse_mgba)
        self._mgba_edit.editingFinished.connect(self._commit_mgba)
        lay.addStretch()

    def _browse_dkp(self, edit: QLineEdit):
        p = QFileDialog.getExistingDirectory(self, "devkitPro")
        if p:
            edit.setText(p)
            self._commit_dkp()

    def _browse_mgba(self, edit: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(self, label("settings.toolchains.pick_mgba"))
        if p:
            edit.setText(p)
            self._commit_mgba()

    def _commit_dkp(self):
        t = self._dkp_edit.text().strip()
        if t:
            self._toolchain.devkitpro_path = Path(t)

    def _commit_mgba(self):
        t = self._mgba_edit.text().strip()
        if t:
            self._toolchain.mgba_path = Path(t)


def restart_editor():
    """Ferme toutes les fenêtres (donc `closeEvent` de la fenêtre
    principale : écriture du projet, confirmation si elle échoue), puis
    relance le même programme avec les mêmes arguments. Si une fenêtre
    refuse de se fermer, on ne relance rien."""
    app = QApplication.instance()
    # La fenêtre principale d'abord : si l'utilisateur annule dans la boîte
    # « modifications non enregistrées », les réglages restent ouverts.
    main_window = next((w for w in app.topLevelWidgets()
                        if isinstance(w, QMainWindow) and w.isVisible()), None)
    if main_window is not None and not main_window.close():
        return
    app.closeAllWindows()
    if any(w.isVisible() for w in app.topLevelWidgets()):
        return
    if getattr(sys, "frozen", False):
        program, arguments = sys.executable, sys.argv[1:]
    else:
        program, arguments = sys.executable, sys.argv
    QProcess.startDetached(program, arguments)
    app.quit()


# ── Theme ───────────────────────────────────────────────────────────────

class ThemePanel(QWidget):
    """Thème sombre ou clair. Persisté à l'instant du choix ; appliqué au
    prochain démarrage, car les couleurs sont figées dans les feuilles de
    style à la construction des écrans."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title(label("settings.cat.theme")))

        self._theme = QComboBox()
        self._theme.setFont(QFont(T.UI, T.MD))
        self._theme.setStyleSheet(QSS.combobox)
        self._theme.addItem(label("settings.theme.dark"), "dark")
        self._theme.addItem(label("settings.theme.light"), "light")
        self._theme.setCurrentIndex(max(0, self._theme.findData(interface_theme())))
        self._applied_theme = interface_theme()
        self._theme.currentIndexChanged.connect(self._on_theme_changed)
        lay.addWidget(self._theme)

        note = QLabel(label("settings.theme.note", app_name=APP_NAME))
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        # Visible seulement tant que le choix diffère du thème de la session :
        # revenir au thème appliqué fait disparaître l'invite.
        self._restart_button = QPushButton(label("settings.theme.restart"))
        self._restart_button.setStyleSheet(QSS.button_ghost)
        self._restart_button.setFixedWidth(160)
        self._restart_button.clicked.connect(restart_editor)
        self._restart_button.setVisible(False)
        lay.addWidget(self._restart_button, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()

    def _on_theme_changed(self, index: int):
        theme = str(self._theme.itemData(index))
        set_interface_theme(theme)
        self._restart_button.setVisible(theme != self._applied_theme)



# ── Interface ───────────────────────────────────────────────────────────

class InterfacePanel(QWidget):
    """Ce que l'éditeur montre de lui-même.

    Les préférences se persistent à l'instant où elles changent : il n'y a
    rien à annuler. La langue prend effet au prochain démarrage, car les
    widgets existants ont déjà reçu leur texte lors de leur construction.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title(label("common.interface")))

        language_row = QHBoxLayout()
        language_label = QLabel(label("settings.interface.language"))
        language_label.setFont(QFont(T.UI, T.MD))
        language_label.setFixedWidth(140)
        self._language = QComboBox()
        self._language.setFont(QFont(T.UI, T.MD))
        self._language.setStyleSheet(QSS.combobox)
        current_language = interface_language()
        for code, name in catalog.available_languages():
            self._language.addItem(name, code)
        current_index = self._language.findData(current_language)
        self._language.setCurrentIndex(max(0, current_index))
        self._language.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(language_label)
        language_row.addWidget(self._language, 1)
        lay.addLayout(language_row)

        restart_note = QLabel(label("settings.interface.language_restart", app_name=APP_NAME))
        restart_note.setFont(QFont(T.UI, T.SM))
        restart_note.setStyleSheet(f"color:{C.TEXT_DIM};")
        restart_note.setWordWrap(True)
        lay.addWidget(restart_note)

        scale_row = QHBoxLayout()
        scale_label = QLabel(label("settings.interface.scale"))
        scale_label.setFont(QFont(T.UI, T.MD))
        scale_label.setFixedWidth(140)
        self._scale = QComboBox()
        self._scale.setFont(QFont(T.UI, T.MD))
        self._scale.setStyleSheet(QSS.combobox)
        for percent in SCALE_CHOICES:
            self._scale.addItem(f"{percent} %", percent)
        self._applied_scale = interface_scale_percent()
        self._scale.setCurrentIndex(max(0, self._scale.findData(self._applied_scale)))
        self._scale.currentIndexChanged.connect(self._on_scale_changed)
        scale_row.addWidget(scale_label)
        scale_row.addWidget(self._scale, 1)
        lay.addLayout(scale_row)

        scale_note = QLabel(label("settings.interface.scale_restart", app_name=APP_NAME))
        scale_note.setFont(QFont(T.UI, T.SM))
        scale_note.setStyleSheet(f"color:{C.TEXT_DIM};")
        scale_note.setWordWrap(True)
        lay.addWidget(scale_note)

        # Visible seulement tant que le choix diffère de l'échelle de la session.
        self._scale_restart = QPushButton(label("settings.theme.restart"))
        self._scale_restart.setStyleSheet(QSS.button_ghost)
        self._scale_restart.setFixedWidth(160)
        self._scale_restart.clicked.connect(restart_editor)
        self._scale_restart.setVisible(False)
        lay.addWidget(self._scale_restart, 0, Qt.AlignmentFlag.AlignLeft)

        self._chk_tips = QCheckBox(label("settings.interface.show_tips"))
        self._chk_tips.setFont(QFont(T.UI, T.MD))
        self._chk_tips.setStyleSheet(QSS.checkbox)
        self._chk_tips.setChecked(tips_shown())
        self._chk_tips.toggled.connect(self._on_toggled)
        lay.addWidget(self._chk_tips)

        lay.addStretch()

    def _on_toggled(self, value: bool):
        set_tips_shown(bool(value))
        # Les astuces DÉJÀ construites ailleurs dans l'application obéissent
        # tout de suite : sans ça le réglage n'aurait l'air de marcher qu'au
        # prochain lancement, et on le rebasculerait en croyant l'avoir raté.
        refresh_tips()

    def _on_scale_changed(self, index: int):
        percent = int(self._scale.itemData(index))
        set_interface_scale_percent(percent)
        self._scale_restart.setVisible(percent != self._applied_scale)

    def _on_language_changed(self, index: int):
        code = self._language.itemData(index)
        set_interface_language(str(code or ""))
        # Appliqué par main.py au prochain démarrage, avant tout widget.
        # Les nouveaux panneaux et les messages rafraîchis gardent eux aussi
        # la langue de cette session : aucun mélange avant le redémarrage.


# ── Shortcuts ───────────────────────────────────────────────────────────

# Le contexte des raccourcis valables dans tout le logiciel (cf. core/keybindings).
COMMON_CONTEXT = "global"


class ShortcutsPanel(QWidget):
    """Liste + édition des raccourcis de `core/keybindings.BINDINGS` : un
    encart « commun » d'abord (valable dans tout le logiciel), puis une carte
    repliable par écran, dans l'ordre du registre. Une substitution est visible
    tout de suite (fond legèrement teinté) et se remet au défaut d'un clic.

    Les entrées de `core.keybindings.DISPLAY_ONLY` (Undo/Redo, molette,
    clic-milieu — volontairement hors du registre remappable, cf.
    keybindings.py) closent leur carte pour la découvrabilité : touche en
    lecture seule, pas de bouton reset."""

    _CONTEXT_KEYS = {
        "global": "settings.shortcuts.context.global",
        "scene_canvas": "settings.shortcuts.context.scene_canvas",
        "sprite_editor": "settings.shortcuts.context.sprite_editor",
        "sound_mixer": "settings.shortcuts.context.sound_mixer",
        "scene_manager": "settings.shortcuts.context.scene_manager",
    }
    _DISPLAY_KEYS = {
        "undo": "settings.shortcuts.display.undo",
        "redo": "settings.shortcuts.display.redo",
        "wheel_zoom": "settings.shortcuts.display.wheel_zoom",
        "middle_pan": "settings.shortcuts.display.middle_pan",
    }
    # Gestes de souris : le nom du geste tient lieu de touche.
    _DISPLAY_GESTURES = {
        "wheel_zoom": "hints.mouse.wheel",
        "middle_pan": "hints.mouse.middle_drag",
    }
    _BINDING_KEYS = {
        "file.new": "common.new_project",
        "file.open": "common.open_project",
        "file.save": "common.save",
        "file.quit": "common.quit",
        "game.build": "common.build_run",
        "common.copy": "settings.shortcuts.action.common.copy",
        "common.paste": "settings.shortcuts.action.common.paste",
        "common.duplicate": "settings.shortcuts.action.common.duplicate",
        "common.delete": "settings.shortcuts.action.common.delete",
        "common.cancel": "settings.shortcuts.action.common.cancel",
        "common.fit": "settings.shortcuts.action.common.fit",
        "common.zoom_in": "settings.shortcuts.action.common.zoom_in",
        "common.zoom_out": "settings.shortcuts.action.common.zoom_out",
        "common.zoom_reset": "settings.shortcuts.action.common.zoom_reset",
        "canvas.tool_select": "settings.shortcuts.action.canvas.tool_select",
        "canvas.tool_add": "settings.shortcuts.action.canvas.tool_add",
        "canvas.tool_erase": "settings.shortcuts.action.canvas.tool_erase",
        "canvas.tool_collision": "settings.shortcuts.action.canvas.tool_collision",
        "canvas.tool_inpaint": "settings.shortcuts.action.canvas.tool_inpaint",
        "canvas.tool_ui": "settings.shortcuts.action.canvas.tool_ui",
        "sprite.flip_h": "settings.shortcuts.action.sprite.flip_h",
        "sprite.flip_v": "settings.shortcuts.action.sprite.flip_v",
        "sound.play_pause": "settings.shortcuts.action.sound.play_pause",
        "scene.group": "settings.shortcuts.action.scene.group",
        "scene.graph_toggle_minimap": "settings.shortcuts.action.scene.graph_toggle_minimap",
        "scene.graph_search": "settings.shortcuts.action.scene.graph_search",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kb = get_keybindings()
        self._edits: dict[str, QKeySequenceEdit] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title(label("settings.cat.shortcuts")))

        note = QLabel(label("settings.shortcuts.hint"))
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        # Le commun d'abord, dans un encart toujours visible ; puis une carte
        # repliable par écran, dans l'ordre du registre. Chaque carte porte ses
        # raccourcis remappables, puis ses rangées d'affichage seul.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(10)
        for context_id in dict.fromkeys(b.context_id for b in BINDINGS):
            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(4)
            grid.setColumnStretch(0, 1)
            for b in BINDINGS:
                if b.context_id == context_id:
                    self._add_binding_row(grid, b)
            for display in DISPLAY_ONLY:
                if display[0] == context_id:
                    self._add_display_row(grid, display)
            title = self._context_label(context_id)
            if context_id == COMMON_CONTEXT:
                card = self._common_card(title)
            else:
                card = CollapsibleCard(title, expanded=False)
            card.body_layout.addLayout(grid)
            column.addWidget(card)
        column.addStretch(1)
        scroll.setWidget(host)
        lay.addWidget(scroll, 1)

        reset_all = QPushButton(label("settings.shortcuts.reset_all"))
        reset_all.setStyleSheet(QSS.button_ghost)
        reset_all.clicked.connect(self._reset_all)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(reset_all)
        lay.addLayout(footer)

        self._refresh_conflicts()

    def _common_card(self, title: str) -> QFrame:
        """L'encart du commun : une carte non repliable, cernée d'accent pour
        se distinguer des cartes d'écran. `body_layout` comme CollapsibleCard."""
        card = QFrame()
        card.setObjectName("shortcutsCommon")
        card.setStyleSheet(QSS.card("shortcutsCommon")
                           + f"QFrame#shortcutsCommon {{ border: 1px solid {C.ACCENT}; }}")
        root = QVBoxLayout(card)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)
        heading = QLabel(title)
        heading.setStyleSheet(QSS.title_section())
        root.addWidget(heading)
        card.body_layout = root
        return card

    def _add_binding_row(self, grid: QGridLayout, b: Binding):
        row = grid.rowCount()
        name = QLabel(self._binding_label(b.id))
        name.setFont(QFont(T.UI, T.MD))
        grid.addWidget(name, row, 0)

        kse = QKeySequenceEdit(QKeySequence(self._kb.resolve(b.id)))
        kse.setFont(_field_font())
        kse.setFixedWidth(150)
        kse.keySequenceChanged.connect(lambda seq, bid=b.id: self._on_edited(bid, seq))
        grid.addWidget(kse, row, 1)
        self._edits[b.id] = kse

        reset_btn = QPushButton("↺")
        reset_btn.setFixedWidth(26)
        reset_btn.setToolTip(tooltip(
            title=label("settings.shortcuts.reset_title"),
            body=label("settings.shortcuts.reset_to", default=b.default)))
        reset_btn.clicked.connect(lambda _=False, bid=b.id: self._reset(bid))
        grid.addWidget(reset_btn, row, 2)

    def _add_display_row(self, grid: QGridLayout, entry: tuple[str, str, str]):
        _context_id, display_id, key = entry
        row = grid.rowCount()
        name = QLabel(label(self._DISPLAY_KEYS.get(display_id, display_id)))
        name.setFont(QFont(T.UI, T.MD))
        grid.addWidget(name, row, 0)
        gesture = self._DISPLAY_GESTURES.get(display_id)
        shown = QLabel(label(gesture) if gesture else key)
        shown.setFont(_field_font())
        shown.setFixedWidth(150)
        shown.setContentsMargins(8, 0, 0, 0)
        shown.setStyleSheet(f"color:{C.TEXT_DIM};")
        shown.setToolTip(tooltip(
            title=label("settings.shortcuts.system_key_title"),
            body=label("settings.shortcuts.system_key")))
        grid.addWidget(shown, row, 1)

    @classmethod
    def _context_label(cls, context_id: str) -> str:
        return label(cls._CONTEXT_KEYS.get(context_id, context_id))

    @classmethod
    def _binding_label(cls, binding_id: str) -> str:
        return label(cls._BINDING_KEYS.get(binding_id, binding_id))

    def _on_edited(self, binding_id: str, seq: QKeySequence):
        self._kb.set(binding_id, seq.toString())
        self._refresh_conflicts()

    def _reset(self, binding_id: str):
        self._kb.reset(binding_id)
        self._edits[binding_id].setKeySequence(QKeySequence(self._kb.resolve(binding_id)))
        self._refresh_conflicts()

    def _reset_all(self):
        self._kb.reset_all()
        for b in BINDINGS:
            self._edits[b.id].setKeySequence(QKeySequence(b.default))
        self._refresh_conflicts()

    def _refresh_conflicts(self):
        """Une touche prise par PLUSIEURS actions du MÊME contexte est un vrai
        conflit (une seule répondra) ; elle l'est aussi entre une action
        d'écran et une action COMMUNE, qui vaut partout. D'un écran à
        l'autre, la même touche est normale (S = Select tool en canvas, autre
        chose ailleurs).
        """
        by_context: dict[str, dict[str, list[str]]] = {}
        for b in BINDINGS:
            seq = self._kb.resolve(b.id)
            if not seq:
                continue
            by_context.setdefault(b.context_id, {}).setdefault(seq, []).append(b.id)

        common = by_context.get("global", {})
        conflicted: set[str] = set()
        for context_id, seqs in by_context.items():
            for seq, ids in seqs.items():
                group = ids if context_id == "global" else ids + common.get(seq, [])
                if len(group) > 1:
                    conflicted.update(group)

        for b in BINDINGS:
            edit = self._edits[b.id]
            customized = self._kb.is_customized(b.id)
            if b.id in conflicted:
                edit.setStyleSheet(f"background:{C.BG_INPUT};color:{C.ACCENT_RED};"
                                   f"border:1px solid {C.ACCENT_RED};border-radius:3px;padding:2px;")
            elif customized:
                edit.setStyleSheet(f"background:{C.BG_INPUT};color:{C.ACCENT};"
                                   f"border:1px solid {C.ACCENT};border-radius:3px;padding:2px;")
            else:
                edit.setStyleSheet(QSS.lineedit)


# ── External Tools ──────────────────────────────────────────────────────

TOOL_KINDS_LABEL = dict(TOOL_KINDS)


class ExternalToolsPanel(QWidget):
    def __init__(self, tools: ExternalTools, parent=None):
        super().__init__(parent)
        self._tools = tools
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title(label("settings.cat.external_tools")))

        note = QLabel(label("settings.external.note"))
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._edits: dict[str, QLineEdit] = {}
        for kind, tool_label in TOOL_KINDS:
            initial = str(tools.path(kind) or "")
            edit = _path_row(lay, tool_label, initial,
                             lambda e, k=kind: self._browse(k, e))
            edit.editingFinished.connect(lambda k=kind: self._commit(k))
            self._edits[kind] = edit
        lay.addStretch()

    def _browse(self, kind: str, edit: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(
            self, TOOL_KINDS_LABEL.get(kind, label("settings.external.pick")))
        if p:
            edit.setText(p)
            self._commit(kind)

    def _commit(self, kind: str):
        t = self._edits[kind].text().strip()
        self._tools.set_path(kind, Path(t) if t else None)


# ── Le dialogue ─────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Colonne de catégories à gauche, panneau à droite — mêmes noms
    partout où on y entre (File → Settings, ToolchainBar → Configure,
    Game → build bloqué par un toolchain manquant)."""

    # Les valeurs sont des IDENTIFIANTS (comparés à `initial_category`, indexés) :
    # elles ne se traduisent pas. Le LIBELLÉ affiché passe par `_CAT_LABELS` — le
    # même piège qu'un nom de fichier qui doublerait comme clé (cf. v0.10).
    _CATEGORIES = ("Toolchains", "Theme", "Interface", "Shortcuts",
                   "External Tools")
    _CAT_LABELS = {
        "Toolchains": "settings.cat.toolchains",
        "Theme": "settings.cat.theme",
        "Interface": "common.interface",
        "Shortcuts": "settings.cat.shortcuts",
        "External Tools": "settings.cat.external_tools",
    }

    def __init__(self, toolchain: Toolchain, external_tools: ExternalTools,
                initial_category: str = "Toolchains", parent=None):
        super().__init__(parent)
        self.setWindowTitle(label("settings.window_title"))
        self.setStyleSheet(QSS.dialog)
        self.resize(760, 480)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(QSS.list_widget)
        self._list.setFixedWidth(160)
        self._list.setFont(QFont(T.UI, T.MD))
        for cat in self._CATEGORIES:
            self._list.addItem(QListWidgetItem(label(self._CAT_LABELS[cat])))
        body.addWidget(self._list)

        self._stack = QStackedWidget()
        panels = [
            ToolchainsPanel(toolchain),
            ThemePanel(),
            InterfacePanel(),
            ShortcutsPanel(),
            ExternalToolsPanel(external_tools),
        ]
        for panel in panels:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
            scroll.setWidget(panel)
            self._stack.addWidget(scroll)
        body.addWidget(self._stack, 1)

        self._list.currentRowChanged.connect(self._stack.setCurrentIndex)
        idx = self._CATEGORIES.index(initial_category) if initial_category in self._CATEGORIES else 0
        self._list.setCurrentRow(idx)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton(label("common.close"))
        btn_close.setStyleSheet(QSS.button_primary)
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)
