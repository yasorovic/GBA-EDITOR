"""SceneInspector — background layers, paramètres d'affichage, script de scène."""
from __future__ import annotations
from typing import Optional
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QScrollArea, QPushButton, QMessageBox, QMenu, QToolButton, QSpinBox,
    QLineEdit,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint

from core.models.palette import OWN_PAL_BANK
from core.models.scene import Scene
from core.project import Project
from core.models.scene import TRANSITION_INHERIT, EFFECT_NONE, BG_SLOTS_BY_MODE
from ui.scene_manager.inspectors.bg_layer_row import BgLayerRow
from ui.scene_manager.inspectors.project_inspector import TRANSITION_LABELS
from core.history import (
    get_history, Command, SetFieldCmd, SwapFieldCmd, AddListItemCmd,
    RemoveListItemCmd, SetSceneModeCmd,
)
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W, ScriptPickerPopup, NotesEdit, CollapsibleCard
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.palette_slot_grid import PaletteSlotGridAsset
from ui.common import icons


class _LazyPopupCombo(QComboBox):
    """QComboBox qui matérialise sa liste complète à l'OUVERTURE du menu.

    Certaines listes (les musiques) viennent d'un catalogue différé (v0.24) :
    les remplir à la construction de l'inspecteur rechargerait le disque à
    l'ouverture du projet, alors que le combo n'a besoin que d'afficher sa
    valeur courante. Le loader — posé par ``set_lazy_loader`` — n'est appelé
    qu'une fois, quand l'auteur déploie réellement le combo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lazy_loader = None
        self._lazy_done = False

    def set_lazy_loader(self, loader) -> None:
        self._lazy_loader = loader
        self._lazy_done = False

    def showPopup(self):
        if self._lazy_loader is not None and not self._lazy_done:
            self._lazy_done = True
            self._lazy_loader()
        super().showPopup()


# ── Transition — libellés ─────────────────────────────────────────
# Les mêmes mots que l'inspecteur de projet (qui les définit, la transition
# étant d'abord un réglage de projet), plus l'item d'absence de surcharge. Son
# libellé dit ce que la scène hérite RÉELLEMENT (cf. _refresh_transition) : un
# « from project » nu obligerait à aller voir ailleurs ce que ça donne.
_TRANSITIONS: tuple[tuple[str, str], ...] = (
    (TRANSITION_INHERIT, 'sceneinsp.from_project'),
) + TRANSITION_LABELS


def _script_source_line(path: Path, line: int) -> str:
    """Extrait une ligne pour l'aperçu d'un appel de prefab."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return lines[line - 1].strip() if 1 <= line <= len(lines) else ""


class _ScenePaletteCmd(Command):
    """Mutation undoable de l'allocation palette d'un pool ("obj"|"bg") de la
    scène. Snapshot COMPLET (active_*_palettes + pal_bank de toutes les
    instances du pool + `font_pal_banks` de la scène) → undo/redo fidèles, couvre
    uniformément replace / add / remove (avec réindexation des références) /
    override / restore — d'un acteur, d'un calque OU d'une police.

    `mutate_fn` applique la nouvelle configuration ; le snapshot avant (pris à
    la construction) et après (pris au 1er execute) suffisent à rejouer sans
    ré-exécuter la logique de mutation."""

    def __init__(self, scene, pool: str, mutate_fn, label: str,
                 persist_fn=None, refresh_fn=None):
        self._scene = scene
        self._pool = pool
        self._mutate = mutate_fn
        self.label = label
        self._persist = persist_fn
        self._refresh = refresh_fn
        self._before = self._snapshot()
        self._after = None

    def _active(self) -> list:
        return getattr(self._scene, f"active_{self._pool}_palettes")

    def _instances(self) -> list:
        return (self._scene.actors if self._pool == "obj"
                else self._scene.background_layers)

    def _snapshot(self):
        return (list(self._active()),
                [(o, getattr(o, "pal_bank", OWN_PAL_BANK)) for o in self._instances()],
                dict(getattr(self._scene, "font_pal_banks", {}) or {}))

    def _restore(self, snap):
        active, banks, font_banks = snap
        self._active()[:] = active
        for o, pb in banks:
            o.pal_bank = pb
        # `font_pal_banks` : une police overridée/restaurée depuis la grille en
        # fait partie. Réassigné en bloc, comme la liste active.
        self._scene.font_pal_banks = dict(font_banks)

    def _finish(self):
        if self._persist:
            self._persist()
        if self._refresh:
            self._refresh()

    def execute(self):
        if self._after is None:
            self._mutate()
            self._after = self._snapshot()
        else:
            self._restore(self._after)   # redo
        self._finish()

    def undo(self):
        self._restore(self._before)
        self._finish()


# ── Table des modes vidéo GBA (pilote l'inspecteur adaptatif) ──────────────────
# kind : "tiled" (0/1/2, fonds tuilés) | "bitmap" (3/4/5, un fond plein écran BG2).
# bg_slots : slots BG hardware valides ; affine : slots en mode affine (rotation).
# bg_palettes : la scène sélectionne-t-elle des banques de palette BG ? (non en 3/5).
# `tip` porte une CLÉ de libellé (résolue par `label()` à l'affichage), pas le
# texte : ces descriptions techniques de mode sont visibles (indice sous le
# bouton de mode, infobulles du menu).
# `bg_slots` vient de la source cœur `BG_SLOTS_BY_MODE` (core/models/scene.py) —
# un seul endroit tient la géométrie matérielle, l'UI et le validateur la lisent.
MODE_INFO: dict[int, dict] = {
    0: {"kind": "tiled",  "bg_slots": BG_SLOTS_BY_MODE[0], "affine": (),     "bg_palettes": True,
        "res": (240, 160), "tip": "sceneinsp.mode_tip_0"},
    1: {"kind": "tiled",  "bg_slots": BG_SLOTS_BY_MODE[1], "affine": (2,),   "bg_palettes": True,
        "res": (240, 160), "tip": "sceneinsp.mode_tip_1"},
    2: {"kind": "tiled",  "bg_slots": BG_SLOTS_BY_MODE[2], "affine": (2, 3), "bg_palettes": True,
        "res": (240, 160), "tip": "sceneinsp.mode_tip_2"},
    3: {"kind": "bitmap", "bg_slots": BG_SLOTS_BY_MODE[3], "affine": (),     "bg_palettes": False,
        "res": (240, 160), "bpp": 16, "tip": "sceneinsp.mode_tip_3"},
    4: {"kind": "bitmap", "bg_slots": BG_SLOTS_BY_MODE[4], "affine": (),     "bg_palettes": True,
        "res": (240, 160), "bpp": 8,  "tip": "sceneinsp.mode_tip_4"},
    5: {"kind": "bitmap", "bg_slots": BG_SLOTS_BY_MODE[5], "affine": (),     "bg_palettes": False,
        "res": (160, 128), "bpp": 16, "tip": "sceneinsp.mode_tip_5"},
}


# ──────────────────────────────────────────────────────────────────
#  SceneInspector
# ──────────────────────────────────────────────────────────────────
class SceneInspector(QWidget):
    changed = pyqtSignal()
    slot_assigned = pyqtSignal(int, str)
    edit_prefab_requested = pyqtSignal(object)
    open_ref = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = InspectorScrollArea()
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel(label("sceneinsp.empty"))
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        # ── Carte Note libre ───────────────────────────────────────
        notes_card = CollapsibleCard(label("common.note"))
        notes_inner = notes_card.body_layout
        self._notes_edit = NotesEdit()
        self._notes_edit.setToolTip(tooltip(
            title=label("common.note"), body=label("sceneinsp.notes_tip"),
        ))
        self._notes_edit.committed.connect(lambda text: self._set_scene_field("notes", text))
        notes_inner.addWidget(self._notes_edit)
        cl.addWidget(notes_card)

        # ── Carte Mode vidéo (Scene Mode) — mode + paramètres + script ─────
        # Fusion des anciennes cartes SCENE MODE / PARAMÈTRES / SCRIPT : un seul
        # bouton affiche le mode actif (menu déroulant pour en choisir un autre,
        # même logique de garde-fou/pruning qu'avant), les paramètres de la scène
        # (Layer UI, Scrolling) prennent place à sa droite, et le script de scène
        # est rattaché juste en dessous.
        mode_card = CollapsibleCard(label("sceneinsp.card.mode"))
        mode_inner = mode_card.body_layout

        mode_row = QHBoxLayout(); mode_row.setContentsMargins(0, 0, 0, 0); mode_row.setSpacing(12)
        self._btn_mode = QPushButton(label("sceneinsp.mode_btn", n=0))
        self._btn_mode.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mode.setFixedSize(84, 44)
        self._btn_mode.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT}; background:{C.BG_INPUT};"
            f"border:2px solid {C.ACCENT}; border-radius:5px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
        )
        self._btn_mode.setToolTip(tooltip(title=label("sceneinsp.mode_btn_title")))
        self._btn_mode.clicked.connect(self._show_mode_menu)
        mode_row.addWidget(self._btn_mode)

        # Colonne paramètres (Layer UI + Scrolling) — masquée en mode bitmap
        # (cf. _apply_mode_ui), placée à droite du bouton de mode.
        self._param_col = QWidget()
        param_inner = QVBoxLayout(self._param_col)
        param_inner.setContentsMargins(0, 0, 0, 0)
        param_inner.setSpacing(4)

        scroll_row = QHBoxLayout(); scroll_row.setSpacing(6)
        lbl_scroll = QLabel(label("sceneinsp.scrolling"))
        lbl_scroll.setFont(QFont(T.UI, T.SM)); lbl_scroll.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_scroll.setFixedWidth(70)
        scroll_row.addWidget(lbl_scroll)
        self._chk_scroll_h = self._mk_scroll_toggle("scroll_h", label("sceneinsp.scroll_h_tip"))
        self._chk_scroll_v = self._mk_scroll_toggle("scroll_v", label("sceneinsp.scroll_v_tip"))
        scroll_row.addWidget(self._chk_scroll_h)
        scroll_row.addWidget(self._chk_scroll_v)
        scroll_row.addStretch()
        self._chk_scroll_h.toggled.connect(self._on_scroll_changed)
        self._chk_scroll_v.toggled.connect(self._on_scroll_changed)
        param_inner.addLayout(scroll_row)

        # ── Backdrop ──────────────────────────────────────────────
        # Couleur de l'index 0 de PAL_BG_RAM : ce que le hardware affiche là où
        # AUCUN layer ni sprite ne dessine — donc aussi ce qui apparaît dans une
        # window qui masque tout.
        bd_row = QHBoxLayout(); bd_row.setSpacing(6)
        lbl_bd = QLabel(label("sceneinsp.backdrop"))
        lbl_bd.setFont(QFont(T.UI, T.SM)); lbl_bd.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_bd.setFixedWidth(70)
        self._btn_backdrop = QPushButton()
        self._btn_backdrop.setFixedSize(40, 22)
        self._btn_backdrop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backdrop.clicked.connect(self._pick_backdrop)
        self._btn_backdrop.setToolTip(tooltip(
            title=label("sceneinsp.backdrop_title"),
            body=label("sceneinsp.backdrop_tip"),
            note=label("sceneinsp.backdrop_note"),
        ))
        self._lbl_backdrop = QLabel()
        self._lbl_backdrop.setFont(QFont(T.MONO, T.XS))
        self._lbl_backdrop.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._btn_backdrop_reset = W.btn_ghost(label("sceneinsp.backdrop_reset"))
        self._btn_backdrop_reset.setFont(QFont(T.UI, T.XS))
        self._btn_backdrop_reset.setToolTip(tooltip(
            title=label("sceneinsp.backdrop_reset"),
            body=label("sceneinsp.backdrop_reset_tip"),
        ))
        self._btn_backdrop_reset.clicked.connect(self._reset_backdrop)
        bd_row.addWidget(lbl_bd)
        bd_row.addWidget(self._btn_backdrop)
        bd_row.addWidget(self._lbl_backdrop)
        bd_row.addStretch(1)
        bd_row.addWidget(self._btn_backdrop_reset)
        param_inner.addLayout(bd_row)

        mode_row.addWidget(self._param_col, 1)
        mode_inner.addLayout(mode_row)

        self._mode_hint = QLabel("")
        self._mode_hint.setFont(QFont(T.UI, T.XS)); self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:2px;")
        mode_inner.addWidget(self._mode_hint)

        # ── Transition ────────────────────────────────────────────
        # Le fondu joué en QUITTANT cette scène et en l'OUVRANT. Hors de la
        # colonne des paramètres : une transition vaut aussi en mode bitmap,
        # alors que cette colonne y est masquée.
        trans_row = QHBoxLayout(); trans_row.setSpacing(6)
        lbl_trans = QLabel(label("sceneinsp.transition"))
        lbl_trans.setFont(QFont(T.UI, T.SM)); lbl_trans.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_trans.setFixedWidth(70)
        self._combo_trans = QComboBox()
        self._combo_trans.setFont(QFont(T.UI, T.SM))
        self._combo_trans.setStyleSheet(QSS.combobox)
        for kind, trans_label in _TRANSITIONS:
            self._combo_trans.addItem(label(trans_label), kind)
        self._combo_trans.setToolTip(tooltip(
            title=label("sceneinsp.transition_title"),
            body=label("sceneinsp.transition_tip"),
        ))
        self._combo_trans.currentIndexChanged.connect(self._on_transition_kind)
        self._spin_trans = QSpinBox()
        self._spin_trans.setRange(1, 255)
        self._spin_trans.setFixedWidth(60)
        self._spin_trans.setSuffix(label("sceneinsp.frames_suffix"))
        self._spin_trans.setFont(QFont(T.MONO, T.SM))
        self._spin_trans.setStyleSheet(QSS.spinbox)
        self._spin_trans.setToolTip(tooltip(
            title=label("sceneinsp.transition_duration"),
            body=label("sceneinsp.transition_frames_tip"),
        ))
        self._spin_trans.valueChanged.connect(
            lambda v: self._set_scene_field("transition_frames", int(v)))
        trans_row.addWidget(lbl_trans)
        trans_row.addWidget(self._combo_trans, 1)
        trans_row.addWidget(self._spin_trans)
        mode_inner.addLayout(trans_row)

        # ── Music ─────────────────────────────────────────────────
        # Trois valeurs et non deux : « Keep playing » n'est pas le silence,
        # c'est l'absence d'ordre — traverser une porte ne doit pas relancer
        # le thème. Le silence se déclare (cf. ROADMAP v0.8.2).
        music_row = QHBoxLayout(); music_row.setSpacing(6)
        lbl_music = QLabel(label("sceneinsp.music"))
        lbl_music.setFont(QFont(T.UI, T.SM)); lbl_music.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_music.setFixedWidth(70)
        self._combo_music = _LazyPopupCombo()
        self._combo_music.setFont(QFont(T.UI, T.SM))
        self._combo_music.setStyleSheet(QSS.combobox)
        self._combo_music.setToolTip(tooltip(
            title=label("sceneinsp.music_title"),
            body=label("sceneinsp.music_tip"),
            note=label("sceneinsp.music_note"),
        ))
        self._combo_music.set_lazy_loader(self._materialize_music_catalog)
        self._combo_music.currentIndexChanged.connect(self._on_music)
        music_row.addWidget(lbl_music)
        music_row.addWidget(self._combo_music, 1)
        mode_inner.addLayout(music_row)

        W.separator(mode_inner)

        from ui.common.widgets import ScriptSlot, ScriptPickerPopup  # noqa: F401 (ScriptPickerPopup used later)
        self._scene_script_slot = ScriptSlot(
            add_label    = label("sceneinsp.script_add"),
            accent_color = icons.COLOR_SCRIPT,
            hint         = label("sceneinsp.script_hint"),
        )
        self._scene_script_slot.set_callbacks(
            on_add   = self._scene_script_new,
            on_open  = self._scene_script_open,
            on_clear = self._scene_script_clear,
        )
        mode_inner.addWidget(self._scene_script_slot)

        cl.addWidget(mode_card)

        # ── Carte Background Asset ────────────────────────────────
        bg_card = CollapsibleCard(label("sceneinsp.card.bg"))
        self._bg_card = bg_card
        bg_inner = bg_card.body_layout

        # Rows dynamiques des BackgroundLayers (portés par la scène)
        self._bg_layer_rows: list[BgLayerRow] = []
        self._inpaint_layer_slot: Optional[int] = None  # layer BG peint actif
        self._bg_layers_container = QVBoxLayout()
        self._bg_layers_container.setContentsMargins(0, 2, 0, 0)
        self._bg_layers_container.setSpacing(3)
        bg_inner.addLayout(self._bg_layers_container)

        # Slot « fond bitmap » (modes 3/4/5) — un seul fond plein écran sur BG2.
        self._bitmap_box = QWidget()
        bmp_l = QVBoxLayout(self._bitmap_box)
        bmp_l.setContentsMargins(0, 2, 0, 0); bmp_l.setSpacing(3)
        self._btn_bitmap_pick = QPushButton(label("sceneinsp.bitmap_pick"))
        self._btn_bitmap_pick.setFont(QFont(T.UI, T.SM))
        self._btn_bitmap_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_bitmap_pick.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px 8px; text-align:left;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; border-color:{icons.COLOR_BACKGROUND};}}"
        )
        self._btn_bitmap_pick.clicked.connect(self._pick_bitmap_bg)
        bmp_l.addWidget(self._btn_bitmap_pick)
        self._bitmap_note = QLabel("")
        self._bitmap_note.setFont(QFont(T.UI, T.XS)); self._bitmap_note.setWordWrap(True)
        self._bitmap_note.setStyleSheet(f"color:{C.TEXT_DIM};")
        bmp_l.addWidget(self._bitmap_note)
        bg_inner.addWidget(self._bitmap_box)
        self._bitmap_box.setVisible(False)

        cl.addWidget(bg_card)

        # ── Carte Palettes ─────────────────────────────────────────
        # Le catalogue de palettes (Palette Editor) est illimité au niveau
        # projet — c'est ICI qu'on choisit jusqu'à 16 palettes par pool comme
        # "actives" pour cette scène. Actor.pal_bank référence un slot de
        # cette sélection (0-15), pas directement le catalogue.
        # Cette carte explique l'allocation, mais n'est pas nécessaire pour
        # poser une scène sur le canvas. Son calcul peut rasteriser les polices
        # logiques du projet : ne jamais le faire sur le chemin d'ouverture.
        pal_card = CollapsibleCard(label("common.palettes"), expanded=False)
        self._pal_card = pal_card
        self._palette_view_pending = True
        pal_card.toggled.connect(self._on_palette_card_toggled)
        pal_inner = pal_card.body_layout

        self._pal_grids: dict[str, PaletteSlotGridAsset] = {}
        self._pal_sublabels: dict[str, QLabel] = {}
        for pool, color, title in (("obj", C.ACCENT_WARM, label("sceneinsp.pal_obj")),
                                    ("bg", C.ACCENT_COOL, label("sceneinsp.pal_bg"))):
            sub_lbl = QLabel(title)
            sub_lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            sub_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px; margin-top:4px;")
            pal_inner.addWidget(sub_lbl)
            grid = PaletteSlotGridAsset(color)
            grid.scene_replace.connect(lambda slot, name, pool=pool: self._on_scene_replace(pool, slot, name))
            grid.scene_add.connect(lambda name, pool=pool: self._on_scene_add(pool, name))
            grid.scene_remove.connect(lambda slot, pool=pool: self._on_scene_remove(pool, slot))
            grid.asset_override.connect(lambda entry, name, pool=pool: self._on_asset_override(pool, entry, name))
            grid.asset_restore.connect(lambda entry, pool=pool: self._on_asset_restore(pool, entry))
            pal_inner.addWidget(grid)
            self._pal_grids[pool] = grid
            self._pal_sublabels[pool] = sub_lbl

        cl.addWidget(pal_card)

        # ── Carte User Interface — HUD texte : layer, couleurs, police ──
        # Les trois réglages dont dépend tout texte TTE, regroupés ensemble
        # plutôt qu'éclatés dans la colonne « Scene mode » : ils forment une
        # même décision (où le HUD s'affiche, avec quoi), pas des paramètres
        # de rendu du fond.
        ui_card = CollapsibleCard(label("sceneinsp.card.ui"))
        self._ui_card = ui_card
        ui_inner = ui_card.body_layout

        # Le slot BG de l'UI n'est plus un réglage de scène (v0.12) : chaque nœud
        # `Interface` porte le sien (`InterfaceNode.bg_slot`), édité dans son propre
        # inspecteur et lisible dans la projection Priorité du Scene Tree. L'ancien
        # combo « UI layer » a donc été retiré d'ici.

        # ── Banque de couleurs de l'UI ────────────────────────────
        # Où le texte lit ses couleurs : un SLOT de la sélection BG de la scène.
        # « Automatic » (le défaut) garde le comportement historique, la police
        # imposant sa propre palette. Slot picker plutôt qu'un QComboBox : même
        # widget que l'inspecteur d'élément d'UI pour ce même champ (cf.
        # `ui_inspector._reload_ui_pal_slot`) — il ne doit pas se présenter
        # différemment selon l'écran d'où on le change.
        pal_row = QHBoxLayout(); pal_row.setSpacing(6)
        lbl_pal = QLabel(label("sceneinsp.ui_colors"))
        lbl_pal.setFont(QFont(T.UI, T.SM)); lbl_pal.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_pal.setFixedWidth(70)
        self._ui_pal_slot = None
        self._ui_pal_box = QHBoxLayout()
        pal_row.addWidget(lbl_pal)
        pal_row.addLayout(self._ui_pal_box, 1)
        ui_inner.addLayout(pal_row)

        # ── Police par défaut de la scène ─────────────────────────
        # Celle que `scene_init` charge, donc celle qu'obtient tout texte qui
        # n'en nomme pas — un élément d'UI réglé sur « (scene font) », ou un
        # `text.draw` sans `text.set_font`.
        font_row = QHBoxLayout(); font_row.setSpacing(6)
        lbl_font = QLabel(label("sceneinsp.ui_font"))
        lbl_font.setFont(QFont(T.UI, T.SM)); lbl_font.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_font.setFixedWidth(70)
        self._font_slot = None
        self._font_box = QHBoxLayout()
        font_row.addWidget(lbl_font)
        font_row.addLayout(self._font_box, 1)
        ui_inner.addLayout(font_row)

        cl.addWidget(ui_card)

        # ── Carte Prefabs de la scène ──────────────────────────────
        # L'allocation OAM est désormais automatique. Cette carte ne cherche
        # donc plus à la régler : elle rend visible la surface de prefabs que
        # cette scène connaît, via ses acteurs et ses scripts.
        budget_card = CollapsibleCard(label("sceneinsp.card.budget"), color=C.ACCENT_WARM)
        budget_inner = budget_card.body_layout
        self._prefab_scene_container = QVBoxLayout()
        self._prefab_scene_container.setContentsMargins(0, 2, 0, 0)
        self._prefab_scene_container.setSpacing(6)
        budget_inner.addLayout(self._prefab_scene_container)

        cl.addWidget(budget_card)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def focus_background_slot(self, slot: int):
        """Expose le calque BG demandé par une autre projection de la scène."""
        self._bg_card.set_expanded(True)
        for row in self._bg_layer_rows:
            if row.slot_index == slot:
                row.setFocus(Qt.FocusReason.OtherFocusReason)
                self._scroll.ensureWidgetVisible(row)
                return

    def load(self, scene: Scene, project: Project):
        self._scene = scene; self._project = project
        if not scene:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._notes_edit.set_text_silent(getattr(scene, "notes", ""))
        self._chk_scroll_h.setChecked(scene.scroll_h)
        self._chk_scroll_v.setChecked(scene.scroll_v)
        self._refresh_scroll_speeds()
        self._refresh_scene_script_label()
        self._palette_view_pending = True
        if self._pal_card.is_expanded():
            self._rebuild_palette_slots()
        # La sélection BG est persistée sur la scène ; elle ne dépend pas de la
        # carte détaillée des palettes, qui peut rester repliée.
        self._reload_ui_pal()
        self._reload_scene_font()
        self._rebuild_scene_prefabs()
        self._refresh_backdrop()
        self._apply_mode_ui()
        self._refresh_transition()
        self._refresh_music()
        self._blocking = False

    def _on_palette_card_toggled(self, expanded: bool) -> None:
        """Construit la vue coûteuse seulement quand l'auteur la consulte."""
        if expanded and self._palette_view_pending:
            self._rebuild_palette_slots()

    def _mk_scroll_toggle(self, icon_key: str, tip: str) -> QToolButton:
        """Toggle iconifié (double flèche) pour un axe de scrolling — remplace
        la case à cocher texte, cohérent avec les toggles d'affichage du canvas
        (cf. scene_canvas._mk_view_toggle)."""
        b = QToolButton()
        b.setIcon(icons.get(icon_key, C.TEXT_DIM, C.ACCENT))
        b.setIconSize(QSize(16, 16))
        b.setCheckable(True)
        b.setFixedSize(28, 26)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER_MID};background:{C.BG_INPUT};"
            f"border-radius:4px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )
        return b

    # ── Scene Mode (0-5) ──────────────────────────────────────────

    def _show_mode_menu(self):
        """Menu déroulant du bouton de mode — remplace l'ancienne rangée de
        6 boutons. Seul le Mode 0 rend réellement pour l'instant ; les autres
        restent grisés (le sélecteur/inspecteur adaptatif existe déjà, pas
        encore le rendu), même garde-fou qu'avant."""
        current = getattr(self._scene, "render_mode", 0) if self._scene else 0
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setToolTipsVisible(True)
        for m in range(6):
            item_text = label("sceneinsp.mode_menu", n=m) + ("  ✓" if m == current else "")
            act = menu.addAction(item_text)
            if m == 0:
                act.setToolTip(tooltip(
                    title=label("sceneinsp.mode_menu", n=m),
                    body=label(MODE_INFO[0]["tip"]),
                ))
            else:
                act.setEnabled(False)
                act.setToolTip(tooltip(
                    title=label("sceneinsp.mode_menu", n=m),
                    body=label(MODE_INFO[m]["tip"]),
                    note=label("sceneinsp.mode_not_impl_note"),
                ))
            act.triggered.connect(lambda _c=False, m=m: self._on_set_mode(m))
        menu.exec(self._btn_mode.mapToGlobal(QPoint(0, self._btn_mode.height())))

    def _refresh_mode_buttons(self):
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        self._btn_mode.setText(label("sceneinsp.mode_btn", n=mode))

    def _is_bitmap_layer(self, layer) -> bool:
        ba = self._project.get_background(layer.background_name) if (self._project and layer.background_name) else None
        return bool(ba and getattr(ba, "mode", "tiled") == "bitmap")

    def _pruned_by_mode(self, m: int) -> list:
        """Liste lisible des éléments qui seront supprimés en passant au mode `m`."""
        info = MODE_INFO[m]
        out: list = []
        if info["kind"] == "bitmap":
            for L in self._scene.background_layers:
                if not self._is_bitmap_layer(L):
                    out.append(label('sceneinsp.layer_to_remove', slot=L.bg_slot, name=L.background_name or label('sceneinsp.empty_val')))
        else:
            valid = set(info["bg_slots"])
            for L in self._scene.background_layers:
                if L.bg_slot not in valid or self._is_bitmap_layer(L):
                    out.append(label('sceneinsp.layer_to_remove', slot=L.bg_slot, name=L.background_name or label('sceneinsp.empty_val')))
        if not info["bg_palettes"]:
            n = sum(1 for name in self._scene.active_bg_palettes if name)
            if n:
                out.append(label('sceneinsp.palettes_to_remove', n=n))
        return out

    def _on_set_mode(self, m: int):
        if self._blocking or not self._scene:
            return
        if m == getattr(self._scene, "render_mode", 0):
            self._refresh_mode_buttons(); return
        pruned = self._pruned_by_mode(m)
        if pruned:
            msg = label('sceneinsp.confirm_mode_change', mode=m, items="\n• ".join(pruned))
            if QMessageBox.question(
                self, label('sceneinsp.change_scene_mode'), msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self._refresh_mode_buttons()
                return
        info = MODE_INFO[m]
        old = self._scene.background_layers
        if info["kind"] == "bitmap":
            new_layers = [L for L in old if self._is_bitmap_layer(L)][:1]
            for L in new_layers:
                L.bg_slot = 2
        else:
            valid = set(info["bg_slots"])
            new_layers = [L for L in old if L.bg_slot in valid and not self._is_bitmap_layer(L)]
        new_bg_pals = list(self._scene.active_bg_palettes) if info["bg_palettes"] else []
        get_history().push(SetSceneModeCmd(
            self._scene, m, new_layers, new_bg_pals,
            persist_fn=self._persist_scene,
            refresh_fn=lambda: self.load(self._scene, self._project),
        ))
        self.changed.emit()

    def _clear_layer_rows(self):
        for row in self._bg_layer_rows:
            row.hide(); row.setParent(None); row.deleteLater()
        self._bg_layer_rows.clear()

    def _refresh_bitmap_slot(self, info: dict):
        """Met à jour le slot « fond bitmap » (modes 3/4/5) depuis la scène."""
        layer = next((L for L in self._scene.background_layers
                      if self._is_bitmap_layer(L)), None)
        name = layer.background_name if layer else None
        self._btn_bitmap_pick.setText(name or label("sceneinsp.bitmap_pick"))
        rw, rh = info.get("res", (240, 160))
        bpp = info.get("bpp", 8)
        depth = (label("sceneinsp.bitmap_depth_8") if bpp == 8
                 else label("sceneinsp.bitmap_depth_16"))
        self._bitmap_note.setText(
            label("sceneinsp.bitmap_note", w=rw, h=rh, depth=depth)
            + ("" if name else label("sceneinsp.bitmap_no_bg")))

    def _pick_bitmap_bg(self):
        if not self._project or not self._scene:
            return
        self._project.load_backgrounds()   # ouverture explicite du catalogue différé
        bitmaps = [b for b in self._project.backgrounds
                   if getattr(b, "mode", "tiled") == "bitmap"]
        if not bitmaps:
            QMessageBox.information(
                self, label("sceneinsp.no_bitmap_title"),
                label("sceneinsp.no_bitmap_text"))
            return
        entries = [(b.name, b.name) for b in bitmaps]
        popup = ScriptPickerPopup(entries, icons.COLOR_BACKGROUND, parent=self, new_label=None)
        popup.picked.connect(self._set_bitmap_bg)
        popup.show_below(self._btn_bitmap_pick)

    def _set_bitmap_bg(self, name: str):
        from core.models.background import BackgroundLayer
        self._scene.background_layers[:] = [BackgroundLayer(background_name=name, bg_slot=2)]
        self._persist_scene()
        self._apply_mode_ui()
        self.changed.emit()

    def _apply_mode_ui(self):
        """Adapte l'inspecteur au mode de la scène : zone background, paramètres,
        palettes actives."""
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        info = MODE_INFO.get(mode, MODE_INFO[0])
        is_tiled = info["kind"] == "tiled"
        self._refresh_mode_buttons()
        self._mode_hint.setText(label(info["tip"]))
        # BACKGROUND : rangées tuilées vs slot bitmap.
        self._bitmap_box.setVisible(not is_tiled)
        self._clear_layer_rows()
        if is_tiled:
            self._rebuild_layer_rows()
        else:
            self._refresh_bitmap_slot(info)
        # Paramètres (texte TTE + scroll) : tuilé seulement — la carte User
        # Interface sélectionne un BG comme layer HUD, qui n'existe pas en
        # bitmap (une seule couche, déjà prise par le fond plein écran).
        self._param_col.setVisible(is_tiled)
        self._ui_card.setVisible(is_tiled)
        # PALETTES : OBJ toujours, BG seulement en tuilé.
        self._pal_sublabels["bg"].setVisible(is_tiled)
        self._pal_grids["bg"].setVisible(is_tiled)

    def _rebuild_layer_rows(self):
        """Reconstruit les BgLayerRow depuis les layers de la SCÈNE."""
        for row in self._bg_layer_rows:
            # hide() avant setParent(None) : un widget visible détaché de son
            # parent redevient une fenêtre top-level à part entière (c'est le
            # popup flottant "Backstage" observé au Ctrl+S) ; deleteLater()
            # pour le détruire proprement plutôt que le laisser orphelin.
            row.hide()
            row.setParent(None)
            row.deleteLater()
        self._bg_layer_rows.clear()

        if not (self._project and self._scene):
            return

        # Une ligne par slot BG du mode vidéo, toujours : le mode décide du
        # nombre de lignes, l'auteur ne les crée ni ne les supprime. Une ligne
        # absente de la scène (projet ancien, retour d'un mode plus étroit)
        # est matérialisée vide ; elle n'est écrite qu'à la prochaine édition.
        from core.models.background import BackgroundLayer
        valid_slots = MODE_INFO.get(getattr(self._scene, "render_mode", 0),
                                    MODE_INFO[0])["bg_slots"]
        present = {L.bg_slot for L in self._scene.background_layers}
        for slot in valid_slots:
            if slot not in present:
                self._scene.background_layers.append(
                    BackgroundLayer(background_name="", bg_slot=slot, scroll_speed=1.0))

        active_names = self._scene.active_bg_palettes
        active_banks = [b for n in active_names if (b := self._project.get_palette(n))]

        def _bg_names_provider():
            # Catalogue différé (v0.24) : matérialisé seulement quand l'auteur
            # déploie le picker d'un layer, pas à la construction de l'inspecteur
            # (donc pas à l'ouverture du projet — cf. BgLayerRow.set_backgrounds).
            self._project.load_backgrounds()
            return [b.name for b in self._project.backgrounds]

        for layer in sorted(self._scene.background_layers, key=lambda L: L.bg_slot):
            row = BgLayerRow(layer.bg_slot)
            row.set_backgrounds(_bg_names_provider, layer.background_name)
            if layer.background_name:
                ba = self._project.get_background(layer.background_name)
                png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
                ap = self._project.background_images_dir / png
                if ap.exists():
                    row.set_asset(str(ap))
            row.set_speed(layer.scroll_speed)
            current_pal_name = (
                active_names[layer.pal_bank]
                if 0 <= layer.pal_bank < len(active_names) else None
            )
            row.set_pal_banks(active_banks, current_pal_name)
            row.asset_changed.connect(lambda _, name, l=layer: self._on_layer_image(l, name))
            row.speed_changed.connect(lambda _, v, l=layer: self._on_layer_speed(l, v))
            row.pal_bank_changed.connect(lambda _, n, l=layer: self._on_layer_pal_bank(l, n))
            row.bound_toggled.connect(lambda idx: self._on_bound_toggled(idx))
            row.layer_swap_requested.connect(self._on_layer_swap)
            row.visibility_toggled.connect(self._on_layer_visibility)
            row.inpaint_layer_selected.connect(self._on_inpaint_layer)
            row.set_visible_state(getattr(layer, "visible", True))
            row.set_inpaint_layer(layer.bg_slot == self._inpaint_layer_slot)
            self._bg_layers_container.addWidget(row)
            self._bg_layer_rows.append(row)

        self._refresh_bound_rows()

    def _dim_label(self, text: str) -> QLabel:
        """Libellé de champ en ton atténué, réutilisé par les cartes qui n'ont
        pas de style dédié (ex. Actor budget)."""
        lbl = QLabel(text)
        lbl.setFont(QFont(T.UI, T.XS))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        return lbl

    def _persist_scene(self):
        if self._project and self._scene:
            # Suspendre le watcher pendant l'écriture : sinon le fichier de scène
            # qu'on vient d'écrire est re-détecté comme « modifié en externe »,
            # ce qui recharge la scène et RECONSTRUIT l'inspecteur — détruisant
            # le widget en cours d'interaction (ex. le QDoubleSpinBox de vitesse
            # d'un BG sous la molette) → crash. Cf. dispatcher._save_scene.
            with get_dispatcher().suspended():
                self._project.save_scene(self._scene)

    def _on_layer_image(self, layer, name: str):
        """Un BackgroundImage (nom) a été choisi pour un layer — l'image existe
        déjà dans assets/backgrounds/ (import via le Background Editor)."""
        if not self._scene or layer.background_name == name:
            return
        get_history().push(SetFieldCmd(
            layer, "background_name", layer.background_name, name,
            label=f"BG{layer.bg_slot}.background_name",
            persist_fn=lambda: (self._persist_scene(), self._rebuild_layer_rows()),
        ))
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_speed(self, layer, value: float):
        if not self._scene or layer.scroll_speed == value:
            return
        get_history().push(SetFieldCmd(
            layer, "scroll_speed", layer.scroll_speed, value,
            label=f"BG{layer.bg_slot}.scroll_speed", persist_fn=self._persist_scene,
        ))

    def _on_layer_pal_bank(self, layer, pal_name: str):
        """Banque de palette d'un layer — index dans scene.active_bg_palettes
        (même mécanisme qu'Actor.pal_bank)."""
        if not self._scene: return
        from ui.common.pickers import PALETTE_NONE
        from core.models.palette import OWN_PAL_BANK
        active_names = self._scene.active_bg_palettes
        if pal_name == PALETTE_NONE:
            idx = OWN_PAL_BANK
        else:
            try:
                idx = active_names.index(pal_name)
            except ValueError:
                return
        if layer.pal_bank == idx:
            return
        get_history().push(SetFieldCmd(
            layer, "pal_bank", layer.pal_bank, idx,
            label=f"BG{layer.bg_slot}.pal_bank", persist_fn=self._persist_scene,
        ))
        self._rebuild_layer_rows()
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_visibility(self, bg_slot: int, visible: bool):
        """Œil de visibilité viewport d'un layer — persiste layer.visible et
        met à jour le canvas (le codegen ignore ce champ)."""
        if not self._scene:
            return
        layer = next((l for l in self._scene.background_layers
                      if l.bg_slot == bg_slot), None)
        if layer is None or layer.visible == visible:
            return
        layer.visible = visible
        self._persist_scene()
        get_dispatcher()._emit("bg_layer_visibility", bg_slot, visible)

    def _on_inpaint_layer(self, bg_slot: int):
        """Sélectionne le layer peint par l'outil de peinture par palette.
        Radio-like : une seule cible active, les autres lignes se décochent."""
        self._inpaint_layer_slot = bg_slot
        for row in self._bg_layer_rows:
            row.set_inpaint_layer(row.slot_index == bg_slot)
        get_dispatcher()._emit("inpaint_layer_changed", bg_slot)

    def _on_layer_swap(self, src_slot: int, dst_slot: int):
        """Glisser-déposer d'un BgLayerRow sur un autre : échange leurs
        bg_slot — donc leur priorité d'affichage (pri = 3 - bg_slot côté
        codegen). Ne déplace ni image ni palette : seul le bg_slot change."""
        if not self._scene or src_slot == dst_slot:
            return
        src = next((l for l in self._scene.background_layers if l.bg_slot == src_slot), None)
        dst = next((l for l in self._scene.background_layers if l.bg_slot == dst_slot), None)
        if not src or not dst:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(SwapFieldCmd(
            src, dst, "bg_slot",
            label=f"Échanger BG{src_slot} <-> BG{dst_slot}", persist_fn=_refresh,
        ))
        get_dispatcher()._emit("bg_slot_changed", src_slot)
        get_dispatcher()._emit("bg_slot_changed", dst_slot)
        self.changed.emit()

    # ── Prefabs connus de la scène ─────────────────────────────────

    def _scene_prefab_usage(self) -> tuple[dict[str, int], dict[str, list]]:
        """Les prefabs connus ici : ``{nom: acteurs posés}``, puis leurs spawns.

        La portée est volontairement celle de la scène : son script, les scripts
        de ses acteurs et ceux de leurs prefabs. Un spawn n'est recensé que si
        son nom est littéral, comme partout ailleurs dans l'éditeur. Son nombre
        d'occurrences n'est pas un nombre d'instances à l'écran : on affiche
        donc les deux informations sans les confondre.
        """
        scene, project = self._scene, self._project
        if not (scene and project):
            return {}, {}
        placed: dict[str, int] = {}
        for actor in scene.actors:
            name = getattr(actor, "prefab_name", "")
            if name:
                placed[name] = placed.get(name, 0) + 1

        scripts: set[Path] = set()
        def _add(comp):
            if comp and getattr(comp, "script", ""):
                scripts.add(project.asset_abs(comp.script).resolve())
        if getattr(scene, "script", ""):
            scripts.add(project.asset_abs(scene.script).resolve())
        prefab_by_name = {p.name: p for p in project.prefabs}
        for a in scene.actors:
            _add(a.get_component("script"))
            pf = prefab_by_name.get(getattr(a, "prefab_name", ""))
            if pf:
                _add(pf.get_component("script"))

        spawned: dict[str, list] = {}
        if scripts:
            from scripting.refactor import find_call_sites_in_project
            from scripting.api import DOMAIN_PREFAB
            for site in find_call_sites_in_project(project, DOMAIN_PREFAB):
                if site.path.resolve() in scripts:
                    name = site.values.get(DOMAIN_PREFAB)
                    if name:
                        spawned.setdefault(name, []).append(site)
        return placed, spawned

    def _rebuild_scene_prefabs(self):
        """Construit la liste compacte des prefabs utiles à cette scène."""
        while self._prefab_scene_container.count():
            item = self._prefab_scene_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not (self._scene and self._project):
            return

        placed, spawned = self._scene_prefab_usage()
        prefab_by_name = {pf.name: pf for pf in self._project.prefabs}
        names = sorted(set(placed) | set(spawned), key=str.casefold)
        if not names:
            lbl = QLabel(label("sceneinsp.no_scene_prefab"))
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            lbl.setWordWrap(True)
            self._prefab_scene_container.addWidget(lbl)
            return

        for name in names:
            pf = prefab_by_name.get(name)
            holder = QWidget(); holder.setStyleSheet("background:transparent;")
            rows = QVBoxLayout(holder); rows.setContentsMargins(0, 2, 0, 2); rows.setSpacing(3)
            head = QHBoxLayout(); head.setSpacing(8)
            title = QLabel(name)
            title.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            title.setStyleSheet(f"color:{icons.COLOR_PREFAB};")
            head.addWidget(title)
            head.addStretch(1)
            if pf:
                edit = QPushButton(label("sceneinsp.edit_prefab"))
                edit.setCursor(Qt.CursorShape.PointingHandCursor)
                edit.setStyleSheet(QSS.button_ghost)
                edit.clicked.connect(lambda _, prefab=pf: self.edit_prefab_requested.emit(prefab))
                head.addWidget(edit)
            rows.addLayout(head)

            details = []
            if name in placed:
                details.append(label("sceneinsp.prefab_placed", count=placed[name]))
            sites = spawned.get(name, [])
            if sites:
                details.append(label("sceneinsp.prefab_spawn_calls", count=len(sites)))
            detail = QLabel(" · ".join(details))
            detail.setFont(QFont(T.UI, T.XS)); detail.setStyleSheet(f"color:{C.TEXT_MUTED};")
            rows.addWidget(detail)
            # Même motif que les appelants de l'inspecteur d'arête : une ligne
            # de code reconnaissable, puis un geste explicite pour l'ouvrir.
            for site in sites:
                caller = QFrame()
                caller.setStyleSheet(
                    f"QFrame{{background:{C.BG_RAISED};border:1px solid {C.BORDER};}}"
                    f"QFrame:hover{{background:{C.BG_HOVER};}}")
                call_row = QHBoxLayout(caller)
                call_row.setContentsMargins(9, 7, 7, 7); call_row.setSpacing(8)
                marker = QLabel("•")
                marker.setStyleSheet(f"color:{C.ACCENT};")
                prefix = QLabel(f"{site.path.name} : {site.line}")
                prefix.setFont(QFont(T.CODE, T.SM))
                prefix.setStyleSheet(f"color:{C.TEXT_DIM};")
                source = QLineEdit(_script_source_line(site.path, site.line))
                source.setReadOnly(True)
                source.setCursor(Qt.CursorShape.ArrowCursor)
                source.setFont(QFont(T.CODE, T.SM))
                source.setStyleSheet(
                    f"QLineEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
                    f"border:1px solid {C.BORDER_MID};padding:3px 5px;}}")
                open_btn = QPushButton(label("common.open"))
                open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                open_btn.setStyleSheet(
                    f"color:{C.ACCENT};background:transparent;border:none;")
                open_btn.clicked.connect(
                    lambda _, p=str(site.path), l=site.line: self.open_ref.emit(p, l))
                call_row.addWidget(marker); call_row.addWidget(prefix)
                call_row.addWidget(source, 1); call_row.addWidget(open_btn)
                rows.addWidget(caller)
            self._prefab_scene_container.addWidget(holder)

    # ── Palettes actives ────────────────────────────────────────────

    _DEFAULT_PALETTE_NAME    = "DMG (GB Default)"        # OBJ : 3 nuances (index 0 transparent)
    _DEFAULT_BG_PALETTE_NAME = "DMG (GB Default) (BG)"   # BG  : 4 nuances

    def _rebuild_palette_slots(self):
        from codegen.palette_alloc import scene_palette_view, ScenePaletteView
        if not self._scene or not self._project:
            empty = ScenePaletteView("", [], [], 0)
            for pool in ("obj", "bg"):
                self._pal_grids[pool].load(empty, [])
            return

        # Catalogue unifié — les deux barres (OBJ/BG) piochent dans le même
        # project.palettes, seule la sélection ACTIVE reste séparée par pool
        # (contrainte hardware : PAL_OBJ_RAM et PAL_BG_RAM sont distincts).
        banks = list(self._project.palettes)
        for pool in ("obj", "bg"):
            attr = "active_obj_palettes" if pool == "obj" else "active_bg_palettes"
            active = getattr(self._scene, attr)

            # Scène neuve sans aucune sélection -> défaut DMG au slot 0
            # (variante BG pour le pool BG), plutôt qu'un pool entièrement
            # noir/vide. Repli sur la variante OBJ si la BG n'existe pas.
            default_name = self._DEFAULT_BG_PALETTE_NAME if pool == "bg" else self._DEFAULT_PALETTE_NAME
            if not active and not self._project.get_palette(default_name):
                default_name = self._DEFAULT_PALETTE_NAME
            if not active and self._project.get_palette(default_name):
                active.append(default_name)
                self._persist()

            view = scene_palette_view(self._project, self._scene, pool)
            self._pal_grids[pool].load(view, banks)
        self._palette_view_pending = False

    # ── Handlers grille de palettes ─────────────────────────────────

    def _active_list(self, pool: str) -> list:
        return self._scene.active_obj_palettes if pool == "obj" else self._scene.active_bg_palettes

    def _palette_refresh(self, pool: str):
        """Rebâtit la grille + rafraîchit le canvas après une mutation palette."""
        self._palette_view_pending = True
        if self._pal_card.is_expanded():
            self._rebuild_palette_slots()
        if pool == "bg":
            self._rebuild_layer_rows()   # les BgLayerRow résolvent leur icône via active_bg_palettes
            for L in self._scene.background_layers:
                get_dispatcher()._emit("bg_slot_changed", L.bg_slot)
        else:
            get_dispatcher()._emit("scene_sprites_changed")   # re-quantifier les acteurs
        self.changed.emit()

    def _push_palette_cmd(self, pool: str, mutate_fn, label: str):
        get_history().push(_ScenePaletteCmd(
            self._scene, pool, mutate_fn, label,
            persist_fn=self._persist,
            refresh_fn=lambda p=pool: self._palette_refresh(p),
        ))

    def _on_scene_replace(self, pool: str, slot: int, name: str):
        """Remplace la palette de scène du slot par une autre du catalogue."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)) or active[slot] == name:
            return

        def mutate(a=active, s=slot, n=name):
            a[s] = n
        self._push_palette_cmd(pool, mutate, f"Palette scène [{slot}] → {name}")

    def _on_scene_add(self, pool: str, name: str):
        """Ajoute une palette de scène au premier slot libre — donc juste après
        la dernière palette de scène (les slots libres = banques auto des
        assets). Le « + » et les grisées se décalent d'un cran."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)

        def mutate(a=active, n=name):
            free = next((i for i, x in enumerate(a) if not x), None)
            if free is None:
                a.append(n)
            else:
                a[free] = n
        self._push_palette_cmd(pool, mutate, f"Ajouter palette scène {name}")

    def _on_scene_remove(self, pool: str, slot: int):
        """Retire la palette de scène du slot et RÉINDEXE les références :
        instance pointant sur `slot` → OWN ; pointant au-delà → décrémentée."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)):
            return
        instances = self._instances_for(pool)

        def mutate(a=active, s=slot, insts=instances):
            del a[s]
            for o in insts:
                pb = getattr(o, "pal_bank", OWN_PAL_BANK)
                if pb == s:
                    o.pal_bank = OWN_PAL_BANK
                elif pb > s:
                    o.pal_bank = pb - 1
        self._push_palette_cmd(pool, mutate, f"Remove scene palette [{slot}]")

    def _default_font_name(self) -> str:
        """Nom de la police par défaut de la scène — la clé "" de
        `font_pal_banks` s'y résout (cf. `font_pal_key`)."""
        from codegen.font_emit import encodable_project_fonts
        from codegen.font_emit import default_font_name
        return default_font_name(encodable_project_fonts(self._project), self._scene,
                                 getattr(self._project.settings, "default_font", ""))

    def _entry_targets(self, entry) -> tuple[list, list]:
        """(instances à muter par `pal_bank`, clés `font_pal_banks` à muter) d'une
        entrée d'asset — un acteur/calque porte son `pal_bank`, une police porte
        sa banque sur la scène (clé résolue par `font_pal_key`)."""
        from core.models.scene import font_pal_key
        objs, fkeys = [], []
        default = None
        for i in entry.instances:
            if i.kind == "font":
                if default is None:
                    default = self._default_font_name()
                fkeys.append(font_pal_key(i.obj, default))
            elif getattr(i, "obj", None) is not None:
                objs.append(i.obj)
        return objs, fkeys

    def _on_asset_override(self, pool: str, entry, name: str):
        """Override la palette propre d'un groupe d'assets vers une palette du
        CATALOGUE de l'éditeur (comme une couleur normale, pas seulement les
        palettes déjà actives de la scène) : réutilise le slot actif existant
        si `name` y figure déjà, sinon l'ajoute au premier slot libre (même
        logique que `_on_scene_add`) — jamais deux slots pour la même palette.

        Le groupe peut mêler acteurs/calques (leur `pal_bank`) et polices (leur
        entrée dans `Scene.font_pal_banks`) : les deux pointent vers le même
        slot."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        objs, fkeys = self._entry_targets(entry)
        if not objs and not fkeys:
            return

        def mutate(a=active, n=name, objs=objs, fkeys=fkeys):
            try:
                slot = a.index(n)
            except ValueError:
                free = next((i for i, x in enumerate(a) if not x), None)
                if free is None:
                    if len(a) >= 16:
                        return
                    a.append(n)
                    slot = len(a) - 1
                else:
                    a[free] = n
                    slot = free
            for o in objs:
                o.pal_bank = slot
            for k in fkeys:
                self._scene.font_pal_banks[k] = slot
        self._push_palette_cmd(pool, mutate, f"Override asset → {name}")

    def _on_asset_restore(self, pool: str, entry):
        """Revient à la palette d'origine (propre) du groupe d'assets — un
        acteur/calque repasse en `OWN_PAL_BANK`, une police perd son entrée de
        `font_pal_banks` (absente = propre)."""
        if self._blocking or not self._scene:
            return
        objs, fkeys = self._entry_targets(entry)
        if not objs and not fkeys:
            return

        def mutate(objs=objs, fkeys=fkeys):
            for o in objs:
                o.pal_bank = OWN_PAL_BANK
            for k in fkeys:
                self._scene.font_pal_banks.pop(k, None)
        self._push_palette_cmd(pool, mutate, "Restaurer palette d'origine")

    def _instances_for(self, pool: str) -> list:
        return self._scene.actors if pool == "obj" else self._scene.background_layers

    def _on_bound_toggled(self, idx: int):
        if self._blocking or not self._scene: return
        self._set_scene_field("collision_layer", idx, extra_persist=self._refresh_bound_rows)
        self.changed.emit()

    def _refresh_bound_rows(self):
        cl_idx = getattr(self._scene, "collision_layer", 0)
        for row in self._bg_layer_rows:
            row.set_bound(row.slot_index == cl_idx)

    def _refresh_scroll_speeds(self):
        pass  # vitesse gérée dans BackgroundAsset désormais

    def _on_scroll_changed(self):
        if self._blocking or not self._scene: return
        self._set_scene_field("scroll_h", self._chk_scroll_h.isChecked())
        self._set_scene_field("scroll_v", self._chk_scroll_v.isChecked())
        self.changed.emit()

    # ── Transition ──────────────────────────────────────────────────

    def _refresh_transition(self):
        """Réaffiche la surcharge — et, sur l'item « From project », CE QUE la
        scène hérite : sans ça, savoir ce qu'on obtient demande d'aller ouvrir
        l'inspecteur de projet."""
        sc, p = self._scene, self._project
        kind = getattr(sc, "transition_kind", TRANSITION_INHERIT)
        st = p.settings if p else None
        inherited = getattr(st, "transition_kind", EFFECT_NONE) or EFFECT_NONE
        inh_frames = getattr(st, "transition_frames", 16)
        trans = label(dict(_TRANSITIONS).get(inherited, inherited))
        self._combo_trans.setItemText(
            0, label('sceneinsp.inherited_transition', transition=trans)
            + (label('sceneinsp.transition_frames', frames=inh_frames) if inherited != EFFECT_NONE else ""))
        self._combo_trans.blockSignals(True)
        idx = self._combo_trans.findData(kind)
        self._combo_trans.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_trans.blockSignals(False)
        self._spin_trans.blockSignals(True)
        self._spin_trans.setValue(getattr(sc, "transition_frames", 16))
        self._spin_trans.blockSignals(False)
        # La durée n'appartient à la scène que si elle surcharge par un fondu.
        self._spin_trans.setVisible(kind not in (TRANSITION_INHERIT, EFFECT_NONE))

    def _refresh_music(self):
        """Repeuple la liste depuis le catalogue — il change sous l'inspecteur
        (import, renommage, suppression dans le Sound Mixer)."""
        from core.models.scene import MUSIC_INHERIT, MUSIC_NONE
        sc, p = self._scene, self._project
        want = getattr(sc, "music", MUSIC_INHERIT) or MUSIC_INHERIT
        # Catalogue différé : tant que l'auteur n'a pas déployé le combo (ni
        # visité l'écran Sounds), ``p.music`` ne contient que ce qu'on a
        # matérialisé. On charge la SEULE piste courante pour qu'elle s'affiche
        # sous son nom (et non « manquante ») sans lire tout le dossier — la
        # liste complète arrive au premier ``showPopup`` (cf. _LazyPopupCombo).
        if p and want not in (MUSIC_INHERIT, MUSIC_NONE):
            p.music.ensure_loaded(want)
        self._combo_music.blockSignals(True)
        self._combo_music.clear()
        self._combo_music.addItem(label("sceneinsp.music_keep"), MUSIC_INHERIT)
        self._combo_music.addItem(label("sceneinsp.music_silence"), MUSIC_NONE)
        for m in (getattr(p, "music", []) if p else []):
            self._combo_music.addItem(m.name, m.name)
        idx = self._combo_music.findData(want)
        if idx < 0:
            # Piste disparue : on la garde VISIBLE plutôt que de retomber en
            # silence sur « Keep playing ». Le champ dirait le contraire du
            # fichier, et le validateur signale déjà le problème.
            self._combo_music.addItem(label("common.missing_name", name=want), want)
            idx = self._combo_music.count() - 1
        self._combo_music.setCurrentIndex(idx)
        self._combo_music.blockSignals(False)

    def _materialize_music_catalog(self):
        """Loader du combo music : matérialise le catalogue différé puis repeuple
        la liste complète. Appelé une seule fois, au premier déploiement."""
        if self._project:
            self._project.load_audio()
            self._reload_music_combo()

    def _on_music(self, idx: int):
        if self._blocking or not self._scene: return
        from core.models.scene import MUSIC_INHERIT
        self._set_scene_field("music", self._combo_music.itemData(idx) or MUSIC_INHERIT)
        self.changed.emit()

    def _on_transition_kind(self, idx: int):
        if self._blocking or not self._scene: return
        self._set_scene_field("transition_kind",
                              self._combo_trans.itemData(idx) or TRANSITION_INHERIT,
                              extra_persist=self._refresh_transition)
        self.changed.emit()

    # ── Backdrop ────────────────────────────────────────────────────

    def _effective_backdrop(self) -> int:
        """BGR555 réellement compilé : override de scène, sinon défaut projet
        (même résolution que main_gen._resolve_backdrop_color)."""
        if not self._scene:
            return 0
        v = getattr(self._scene, "backdrop_color", None)
        if v is not None:
            return v
        return self._project.settings.backdrop_color if self._project else 0

    def _refresh_backdrop(self):
        from core.models.gba_color import bgr555_to_rgb888
        v = self._effective_backdrop()
        r, g, b = bgr555_to_rgb888(v)
        self._btn_backdrop.setStyleSheet(
            f"QPushButton{{background:rgb({r},{g},{b});"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        overridden = getattr(self._scene, "backdrop_color", None) is not None
        self._lbl_backdrop.setText(
            f"0x{v:04X}" + ("" if overridden else label("sceneinsp.backdrop_project_suffix")))
        self._btn_backdrop_reset.setVisible(overridden)

    def _pick_backdrop(self):
        from PyQt6.QtWidgets import QColorDialog
        from core.models.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
        if not self._scene:
            return
        r, g, b = bgr555_to_rgb888(self._effective_backdrop())
        col = QColorDialog.getColor(
            QColor(r, g, b), self, label("sceneinsp.backdrop_dialog"),
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if not col.isValid():
            return
        # Quantification BGR555 : la valeur stockée est celle que la console
        # affichera réellement, pas la couleur 8 bits choisie dans le dialogue.
        self._set_scene_field(
            "backdrop_color", rgb888_to_bgr555(col.red(), col.green(), col.blue()),
            extra_persist=self._notify_backdrop,
        )
        self.changed.emit()

    def _reset_backdrop(self):
        """Retire l'override de scène — la couleur du projet reprend la main."""
        self._set_scene_field("backdrop_color", None, extra_persist=self._notify_backdrop)
        self.changed.emit()

    def _notify_backdrop(self):
        self._refresh_backdrop()
        get_dispatcher()._emit("backdrop_changed")

    def _reload_ui_pal(self):
        """(Re)construit le slot de banque d'UI depuis la sélection BG de la
        scène — LA MÊME liste, dans le même ordre, que
        `TextInspector._reload_ui_pal_slot` : c'est le même champ, il ne doit
        pas se présenter différemment selon l'écran d'où on le change.

        Les slots VIDES sont listés quand même, mais dits comme tels : la
        sélection peut être remplie après coup, et masquer le slot ferait
        disparaître un choix déjà fait dans le JSON. Reconstruit et non
        repeuplé : le picker capture sa liste à la construction."""
        if not self._scene:
            return
        from ui.common.pickers import ui_pal_bank_slot
        active = list(getattr(self._scene, "active_bg_palettes", []) or [])
        # Le picker édite l'entrée de la police PAR DÉFAUT (clé "") de
        # `font_pal_banks` — l'un des deux chemins vers le même réglage, l'autre
        # étant la grille de palettes.
        cur = int((getattr(self._scene, "font_pal_banks", {}) or {}).get("", -1))
        if self._ui_pal_slot is not None:
            self._ui_pal_box.removeWidget(self._ui_pal_slot)
            self._ui_pal_slot.deleteLater()
        self._ui_pal_slot = ui_pal_bank_slot(
            active, cur, icons.COLOR_UI, on_picked=self._on_ui_pal_changed,
            project=self._project, parent=self)
        self._ui_pal_slot.setToolTip(tooltip(
            title=label("sceneinsp.ui_colors_title"), body=label("sceneinsp.ui_colors_tip"),
        ))
        self._ui_pal_box.addWidget(self._ui_pal_slot)

    def _on_ui_pal_changed(self, new: int):
        """Override de la police par défaut vers un slot de scène (clé "" de
        `font_pal_banks`), ou retour à sa palette propre (-1 = absent de la map).
        Écrit un dict NEUF — `SetFieldCmd` compare avant/après, muter en place lui
        montrerait deux fois la même référence (cf. `_on_pool_changed`)."""
        if not self._scene:
            return
        banks = dict(getattr(self._scene, "font_pal_banks", {}) or {})
        if 0 <= int(new) < 16:
            banks[""] = int(new)
        else:
            banks.pop("", None)
        self._set_scene_field("font_pal_banks", banks)
        # La grille reflète le même réglage : la police par défaut y passe de
        # « propre » (grisée) à « override » (marqueur), ou l'inverse.
        self._palette_refresh("bg")

    def _reload_scene_font(self):
        """(Re)construit le slot de police par défaut de la scène.

        Une police sans source exploitable reste visible mais signalée. Le
        test de disponibilité ne rasterise pas les glyphes : remplir un menu ne
        doit pas déclencher le travail réservé au build ou à un aperçu."""
        if not self._scene:
            return
        from ui.common.pickers import font_picker_slot
        p = self._project
        try:
            from codegen.font_build import available_project_font_names
            usable = available_project_font_names(p) if p else set()
        except Exception:
            usable = {f.name for f in (getattr(p, "fonts", []) or [])} if p else set()
        cur = getattr(self._scene, "font_name", "") or ""
        if self._font_slot is not None:
            self._font_box.removeWidget(self._font_slot)
            self._font_slot.deleteLater()
        self._font_slot = font_picker_slot(
            list(getattr(p, "fonts", []) or []), usable, cur, icons.COLOR_UI,
            on_picked=self._on_scene_font_changed, parent=self,
            project_default=getattr(p.settings, "default_font", "") if p else "")
        self._font_slot.setToolTip(tooltip(
            title=label("sceneinsp.ui_font_title"), body=label("sceneinsp.ui_font_tip"),
        ))
        self._font_box.addWidget(self._font_slot)

    def _on_scene_font_changed(self, name: str):
        if self._blocking or not self._scene:
            return
        self._set_scene_field("font_name", name or "")
        self.changed.emit()

    def _persist(self):
        if self._project and self._scene:
            get_dispatcher().save_scene()

    def _set_scene_field(self, field: str, value, extra_persist=None):
        """Pousse un SetFieldCmd undoable sur un champ scalaire de la scène
        (no-op si la valeur est inchangée)."""
        if self._blocking or not self._scene: return
        old = getattr(self._scene, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._scene, field, old, value,
            label=f"{self._scene.name}.{field}",
            persist_fn=_do_persist,
        ))

    # ── Script de scène — helpers ──────────────────────────────────

    def _refresh_scene_script_label(self):
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc and self._project else None
        if sp and sp.exists():
            self._scene_script_slot.set_script(sp.name)
        else:
            self._scene_script_slot.clear_script()

    def _scene_script_new(self):
        """Ouvre le picker : liste des scripts de scène + bouton Nouveau."""
        if not self._scene or not self._project: return
        from ui.common.widgets import ScriptPickerPopup

        # Les scripts attachables du projet : le contexte vient de l'attache, pas du dossier
        scripts = [(f.name, str(f.relative_to(self._project.root)).replace("\\", "/"))
                   for f in self._project.script_files()]

        popup = ScriptPickerPopup(scripts, icons.COLOR_SCRIPT, parent=self)
        popup.picked.connect(self._scene_script_assign)
        popup.new_requested.connect(self._scene_script_create_new)
        popup.show_below(self._scene_script_slot)

    def _scene_script_assign(self, rel: str):
        """Assigne un script existant à la scène."""
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def _scene_script_create_new(self):
        """Dialogue de création d'un nouveau script de scène."""
        if not self._scene or not self._project: return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, label('sceneinsp.new_scene_script'), label('common.name_without_lua'))
        if not ok or not name.strip(): return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        d = self._project.scripts_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            ctx = ScriptTemplateContext(kind="scene", name=name.strip(), scene_name=self._scene.name)
            sp.write_text(generate_script_template(ctx), encoding="utf-8")
        rel = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
        self.changed.emit()
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_open(self):
        if not self._scene or not self._project: return
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc else None
        if sp and sp.exists() and hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_clear(self):
        self._set_scene_field("script", "", extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn
