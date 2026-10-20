"""ui/background_editor/background_editor_screen.py — écran Background Editor.

3 colonnes : finder (backgrounds) · canvas d'inpainting (BackgroundInpainting :
repeindre la palette par tuile 8×8, partagé entre scènes, cf. bg_inpaint_canvas) ·
inspecteur (dimensions, budget tuiles, liste des palettes éditables, algo de
compression). La compression est non-destructive (cf. core/bg_import) — le PNG
n'est jamais modifié, tout vit en métadonnées dans le .background du BackgroundAsset.
"""
from __future__ import annotations
import html
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QFileDialog, QLabel, QSpinBox,
    QMenu, QAbstractItemView, QPushButton, QGridLayout, QCheckBox,
    QSlider, QComboBox, QScrollArea, QFrame,
)
from ui.common.popup import MessageBox as QMessageBox
from PyQt6.QtGui import QFont, QDrag, QValidator, QCursor
from PyQt6.QtCore import (
    Qt, QSize, QMimeData, QObject, QRunnable, QThreadPool, QTimer, pyqtSignal,
)

from ui.common.deferred_writes import schedule_save
from ui.common.import_collision import ask_overwrite
from ui.common.import_folder import import_folder
from ui.common.theme import C, T, QSS, ui_font
from ui.common.unit_spin import UnitSpin
from ui.common.widgets import W, FinderSection, AssetHeaderBar, CollapsibleCard
from ui.common.responsive import InspectorScrollArea
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.icons import COLOR_BACKGROUND, COLOR_UI
from ui.common.palette_slot_grid import PaletteSlotGridAsset
from ui.common.asset_palette_view import background_palette_view
from core.models.palette import PaletteBank
from core.models.resource import MIME_ANIMATED_BG
from core.models.background import (
    BackgroundAdjust,
    KIND_SCENE, KIND_UI, KIND_ANIMATED, BG_KINDS, BG_KIND_LABELS,
    UI_ROLE_NINE, UI_ROLE_BG, ANIM_INSTANCE, ANIM_SHARED, BackgroundCompression,
)
from core.models.gba_color import COMPRESSION_METHODS
from core.command_dispatcher import get_dispatcher
from ui.common.asset_finder import AssetFinder
from ui.common.three_column_body import ThreeColumnBody
from ui.common.asset_kinds import (
    BACKGROUNDS_SCENE, BACKGROUNDS_UI, BACKGROUNDS_ANIM,
)

# Section du finder <-> `kind` du modèle. Le composant partagé ne parle que de
# libellés de famille ; l'écran, lui, raisonne en `kind`.
_LABEL_OF_KIND = {KIND_SCENE:    BACKGROUNDS_SCENE.label,
                  KIND_UI:       BACKGROUNDS_UI.label,
                  KIND_ANIMATED: BACKGROUNDS_ANIM.label}
_KIND_OF_LABEL = {v: k for k, v in _LABEL_OF_KIND.items()}
from core.history import get_history, DeleteResourceCmd, CreateAssetCmd, RefreshAfterCmd
from core.bg_import import QUANTIZERS_8BPP
from . import bg_inpaint_canvas
from .bg_inpaint_canvas import BgInpaintCanvas
from .background_encoding import BackgroundEncodingService, EncodingJob, EncodingState

_CANVAS_MAX = 4096    # plafond des champs de la carte Canvas, en pixels : assez grand pour un décor qui défile

_BG_COLOR = COLOR_BACKGROUND

# Un fond d'interface appartient à la famille INTERFACE, pas à la famille monde :
# la teinte dit à quoi sert l'asset, et c'est la seule chose qui distingue à
# l'œil un cadre de dialogue d'un décor dans la même liste (règle « une famille,
# une couleur » — cf. ui/common/icons.py).
_KIND_COLOR = {KIND_SCENE: COLOR_BACKGROUND, KIND_UI: COLOR_UI,
               KIND_ANIMATED: COLOR_BACKGROUND}

# L'encodage (bg_import) peut prendre plusieurs secondes sur un grand fond ou une photo : il tourne hors du thread de
# l'interface, par le service d'encodage (`background_encoding`), qui valide ensuite le résultat sur le fond.


class _SliderSpin(QSpinBox):
    """Champ numérique d'un curseur : on y tape la valeur, ou le mot qui désigne
    l'extrémité « désactivée » (« Off », « No limit »), qui est aussi ce qu'il
    affiche quand le curseur y est."""

    def __init__(self, special: str, special_at_max: bool):
        super().__init__()
        self._special = special
        self._at_max = special_at_max

    def _end(self) -> int:
        return self.maximum() if self._at_max else self.minimum()

    def textFromValue(self, value: int) -> str:
        return self._special if (self._special and value == self._end()) else str(value)

    def valueFromText(self, text: str) -> int:
        text = text.strip()
        if self._special and text.lower() == self._special.lower():
            return self._end()
        try:
            return int(text)
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        t = text.strip().lower()
        if self._special and t and self._special.lower().startswith(t):
            state = (QValidator.State.Acceptable if t == self._special.lower()
                     else QValidator.State.Intermediate)
            return state, text, pos
        return super().validate(text, pos)


class _AnalyzeSignals(QObject):
    done   = pyqtSignal(int, dict)   # token, mesures
    failed = pyqtSignal(int, str)


class _AnalyzeTask(QRunnable):
    """Mesure du 4bpp hors-thread — sur une grande image, extraire les couleurs
    de chaque tuile prend plusieurs secondes."""

    def __init__(self, token: int, png_path: Path, prep: dict):
        super().__init__()
        self._token = token
        self._png = str(png_path)
        self._prep = prep
        self.signals = _AnalyzeSignals()

    def run(self):
        try:
            from core.bg_import import prepare_source, analyze_tile_colors
            src = prepare_source(self._png, **self._prep)
            self.signals.done.emit(self._token, analyze_tile_colors(src))
        except Exception as e:  # noqa: BLE001 — remonté à l'UI, pas avalé
            self.signals.failed.emit(self._token, str(e))


# ── Finder (gauche) ─────────────────────────────────────────────────────────

class _BgList(QListWidget):
    """Liste d'UNE section du finder.

    Sous-classe seulement pour le DRAG : les fonds animés se posent sur le
    canvas d'un fond hôte, et Qt ne démarre un drag qu'à partir du widget
    source. Tout le reste (renommage, menu contextuel) est piloté par le
    panneau, qui seul connaît le projet.

    **Le choix d'un asset attend le relâchement**, il ne suit pas
    `currentItemChanged`. Qt fixe l'item courant dès l'APPUI, or un appui sur une
    liste glissable peut devenir un glissement : charger l'asset à ce moment-là
    faisait changer le canvas sous le curseur, et le fond hôte qu'on visait
    disparaissait avant même d'avoir bougé la souris. Le geste était donc
    impossible à terminer. D'où `chosen`, émis seulement quand l'utilisateur a
    vraiment choisi — au clavier, par programme, ou au relâchement d'un clic qui
    n'a pas tourné en glissement."""

    chosen = pyqtSignal(object)   # QListWidgetItem | None

    def __init__(self, color: str, draggable: bool, parent=None):
        super().__init__(parent)
        self._draggable = draggable
        self._mouse_select = False   # l'item courant change sous un appui souris
        self._drag_started = False
        self.currentItemChanged.connect(self._on_current)
        self.setStyleSheet(
            QSS.finder_list(color)
            # Éditeur de renommage en place : mêmes police/taille que la ligne,
            # sinon le QLineEdit s'ouvre avec la police par défaut (plus grande)
            # et le texte est rogné verticalement.
            + f"QListWidget QLineEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
              f"border:1px solid {color}; padding:0 4px; margin:0;"
              f"font-family:{T.MONO}; font-size:{T.MD}px;}}"
        )
        # Renommage en place : clic sur un item déjà sélectionné (même mécanisme
        # que les autres finders — sprite/scene/prefab).
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if draggable:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def _on_current(self, cur, _prev=None):
        # Sous un appui souris, on ne tranche pas : le relâchement dira si
        # c'était un clic (donc un choix) ou le début d'un glissement.
        if not self._mouse_select:
            self.chosen.emit(cur)

    def mousePressEvent(self, e):
        self._mouse_select = self._draggable
        self._drag_started = False
        super().mousePressEvent(e)
        self._mouse_select = False

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        # Après un glissement, Qt ne livre pas toujours le relâchement — et s'il
        # le livre, l'asset ne doit pas changer pour autant : le geste visait le
        # canvas, pas la liste.
        if self._draggable and not self._drag_started:
            self.chosen.emit(self.currentItem())

    def startDrag(self, actions):
        if not self._draggable:
            return
        self._drag_started = True
        item = self.currentItem()
        ba = item.data(Qt.ItemDataRole.UserRole) if item else None
        if ba is None:
            return
        mime = QMimeData()
        mime.setData(MIME_ANIMATED_BG, ba.name.encode("utf-8"))
        # Le texte accompagne le mime maison : un drop hors canvas (barre de
        # recherche, éditeur externe) écrit alors le NOM, jamais un binaire.
        mime.setText(ba.name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class _AnimatedSourceList(_BgList):
    """Les animés du projet, à glisser sur le canvas du fond courant.

    Doublon apparent avec la section ANIMATED du finder, mais celle-ci ne peut
    pas servir de source : y presser un item change l'asset ÉDITÉ (elle pilote la
    sélection), si bien qu'au relâchement le canvas n'affiche plus le fond hôte
    mais l'animé qu'on croyait déposer. Une source qui ne possède aucune
    sélection n'a pas ce problème.

    Hérite de `_BgList` pour que `startDrag` — et donc le format d'échange —
    reste écrit à un seul endroit."""

    ROW_H = 22

    def __init__(self, parent=None):
        super().__init__(COLOR_BACKGROUND, draggable=True, parent=parent)
        # Ni renommage ni menu : ce n'est pas un finder, c'est une réserve.
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setFont(QFont(T.MONO, T.SM))

    def set_assets(self, assets: list):
        self.clear()
        for ba in assets:
            it = QListWidgetItem(ba.name)
            it.setData(Qt.ItemDataRole.UserRole, ba)
            n = ba.frame_count()
            it.setToolTip(tooltip(
                title=ba.name, body=label("bgedit.anim_source_tip", n=n)))
            self.addItem(it)
        # Assez haute pour montrer jusqu'à quatre entrées, puis on défile : la
        # réserve ne doit pas repousser les palettes hors de l'écran.
        rows = min(max(len(assets), 1), 4)
        self.setFixedHeight(rows * self.ROW_H + 8)



# ── Propriétés (droite) ─────────────────────────────────────────────────────

class BgPropertiesPanel(QWidget):
    changed = pyqtSignal()          # compression recalculée → re-render du canvas
    renamed = pyqtSignal()          # fond renommé depuis l'en-tête → rafraîchir le finder
    kind_changed = pyqtSignal()     # type du fond changé → re-trier le finder
    palettes_changed = pyqtSignal()     # liste des palettes mutée → re-render du canvas
    geometry_changed = pyqtSignal()  # marges de coupe / découpe de frames → canvas
    recompress_requested = pyqtSignal(object, object, str, bool)  # (ba, png, mode_token, dither) → hors-thread
    restore_requested = pyqtSignal()    # « Restore original » : source entière, à sa taille, sans canvas ni miroir
    canvas_edited = pyqtSignal(object, object)   # (canvas (w, h), image posée (x, y, w, h)) : un champ de la carte Canvas
    canvas_fit_requested = pyqtSignal(str)       # « fit » | « fill » | « one_to_one » : les aides au placement
    layout_shown = pyqtSignal(str)               # « tiled » | « bitmap » : le layout que les boutons montrent (en attente compris)
    overlays_changed = pyqtSignal(list, list)  # (info_lines, warning_lines) → overlays du canvas
    placement_changed = pyqtSignal()  # cadence / image de départ d'une copie → rejouer le canvas
    adjust_preview_requested = pyqtSignal(object)   # BackgroundAdjust à prévisualiser, ou None : retour au rendu compressé
    preview_requested = pyqtSignal(object)    # dict des réglages en attente (le service d'encodage les prend), ou None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220); self.setMaximumWidth(440)
        self.setStyleSheet(f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};")
        self._project = None
        self._ba = None
        self._blocking = False
        self._staged = None      # (layout, profondeur) choisis, pas encore compressés

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # ── En-tête : nom du fond — composant partagé (même template/couleurs/
        # renommage que Scene Manager, Sprite Editor, Sound Mixer, Script Editor).
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_rename)
        outer.addWidget(self._header)

        # Le corps défile : quand « Compression… » s'ouvre, le contenu dépasse la hauteur du panneau, et sans défilement
        # les widgets s'écraseraient les uns sur les autres au lieu de garder leur taille.
        body = QWidget(); body.setStyleSheet(f"background:{C.BG_PANEL};")
        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        # Même gabarit que SceneInspector : des CollapsibleCard espacées de 6 px, dans une gouttière de 8 px.
        root = QVBoxLayout(body); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        # ── TYPE : à quoi sert l'image. Trois emplois d'un même asset (cf.
        #    core/models/background.BG_KINDS) — le type gouverne les sections
        #    ci-dessous et ce que le canvas superpose. Convertible sur place :
        #    un décor qu'on décide d'employer en cadre est le même PNG.
        kind_card = self._card(label("bgedit.sec_kind"), root)
        kind_row = QHBoxLayout(); kind_row.setContentsMargins(0, 0, 0, 0); kind_row.setSpacing(6)
        self._kind_btns: dict[str, QPushButton] = {}
        for k, lbl_key, tip_key in (
                (KIND_SCENE, "common.scene", "bgedit.kind_scene_tip"),
                (KIND_UI, "bgedit.kind_ui", "bgedit.kind_ui_tip"),
                (KIND_ANIMATED, "bgedit.kind_animated", "bgedit.kind_animated_tip")):
            b = self._mode_btn(label(lbl_key), label(tip_key))
            b.clicked.connect(lambda _=False, kk=k: self._set_kind(kk))
            kind_row.addWidget(b, 1)
            self._kind_btns[k] = b
        kind_card.body_layout.addLayout(kind_row)

        # ── MODE COULEUR : deux axes ORTHOGONAUX. Layout (tuilé/bitmap) ×
        #    profondeur (4/8/16 bpp) ; certaines combinaisons n'existent pas sur
        #    GBA → boutons profondeur filtrés selon le layout (cf. _refresh_mode_buttons).
        #    Changer d'axe recompresse le fond (hors-thread).
        mode_card = self._card(label("bgedit.sec_color_mode"), root)
        lay_row = QHBoxLayout(); lay_row.setContentsMargins(0, 0, 0, 0); lay_row.setSpacing(6)
        self._btn_tiled = self._mode_btn(label("bgedit.tiled"), label("bgedit.tiled_tip"))
        self._btn_bitmap = self._mode_btn(label("bgedit.bitmap"), label("bgedit.bitmap_tip"))
        self._btn_tiled.clicked.connect(lambda: self._set_layout("tiled"))
        self._btn_bitmap.clicked.connect(lambda: self._set_layout("bitmap"))
        lay_row.addWidget(self._btn_tiled, 1); lay_row.addWidget(self._btn_bitmap, 1)
        mode_card.body_layout.addLayout(lay_row)

        dep_row = QHBoxLayout(); dep_row.setContentsMargins(0, 2, 0, 2); dep_row.setSpacing(6)
        self._d4 = self._mode_btn(label("bgedit.d4"), label("bgedit.d4_tip"))
        self._d8 = self._mode_btn(label("bgedit.d8"), label("bgedit.d8_tip"))
        self._d16 = self._mode_btn(label("bgedit.d16"), label("bgedit.d16_tip"))
        self._d4.clicked.connect(lambda: self._set_depth(4))
        self._d8.clicked.connect(lambda: self._set_depth(8))
        self._d16.clicked.connect(lambda: self._set_depth(16))
        dep_row.addWidget(self._d4, 1); dep_row.addWidget(self._d8, 1); dep_row.addWidget(self._d16, 1)
        mode_card.body_layout.addLayout(dep_row)
        # La compression ne regarde que les fonds AVEC image, et seulement quand il y a de quoi la régler :
        # le bouton ci-dessous replie tout ce qui suit (dithering, mesure, curseurs). Il s'ouvre de lui-même quand
        # l'image ne tient pas telle quelle ou que des réglages s'écartent du défaut, jamais pour un fond vierge.
        self._tune_open = False
        self._preview_timer = QTimer(self)      # regroupe les crans d'un curseur : un aperçu par pause, pas par cran
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(30)
        self._preview_timer.timeout.connect(self._emit_adjust_preview)
        # La demande d'encodage est plus lente : elle attend une vraie pause (300 ms) avant d'être faite au service.
        self._request_timer = QTimer(self)
        self._request_timer.setSingleShot(True)
        self._request_timer.setInterval(300)
        self._request_timer.timeout.connect(self._emit_request)
        # Deux cartes, détachées : les AJUSTEMENTS (on y touche librement, l'aperçu suit en direct) puis la COMPRESSION,
        # dont les réglages en attente sont encodés par le service (bouton « Run encoding » du canvas).
        # La carte CANVAS : la taille du canvas et l'image posée dedans, en chiffres. Modifier un champ ouvre le mode
        # Canvas du canvas central, qui suit tout de suite (cf. BgInpaintCanvas.edit_canvas).
        self._canvas_card = self._card(label("bgedit.canvas_title"), root)
        canvas_card = self._canvas_card.body_layout
        self._canvas_spins: dict[str, QSpinBox] = {}
        for row_label, names, lo in ((label("bgedit.canvas_size"), (("canvas_w", "W"), ("canvas_h", "H")), 1),
                                     (label("bgedit.canvas_image_pos"), (("pos_x", "X"), ("pos_y", "Y")), -_CANVAS_MAX),
                                     (label("bgedit.canvas_image_size"), (("size_w", "W"), ("size_h", "H")), 1)):
            host = QWidget(); host.setStyleSheet("background:transparent;")
            hrow = QHBoxLayout(host); hrow.setContentsMargins(0, 0, 0, 0); hrow.setSpacing(4)
            for field_name, axis in names:
                tag = QLabel(axis)
                tag.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
                tag.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
                tag.setFixedWidth(14)
                sp = QSpinBox()
                sp.setFont(QFont(T.MONO, T.SM))
                sp.setStyleSheet(QSS.spinbox)
                sp.setRange(lo, _CANVAS_MAX)
                sp.setKeyboardTracking(False)
                sp.valueChanged.connect(lambda _v: self._on_canvas_field())
                hrow.addWidget(tag); hrow.addWidget(sp, 1)
                self._canvas_spins[field_name] = sp
            if names[0][0] == "canvas_w":
                # Un bitmap a un canvas FIXE : plutôt que des champs grisés (qui disent « pas maintenant »), une ligne qui dit
                # « jamais, et pourquoi ». Les deux se partagent la ligne ; `show_canvas_state` montre l'une ou l'autre.
                self._canvas_size_host = host
                self._canvas_fixed = QLabel("")
                self._canvas_fixed.setFont(QFont(T.MONO, T.SM))
                self._canvas_fixed.setStyleSheet(
                    f"color:{C.TEXT_DIM}; background:{C.BG_PANEL}; border:1px dashed {C.BORDER_MID};"
                    f"border-radius:3px; padding:3px 8px;")
                self._canvas_fixed.setToolTip(tooltip(title=label("bgedit.canvas_fixed_title"),
                                                      body=label("bgedit.canvas_fixed_tip")))
                self._canvas_fixed.setVisible(False)
                row_host = QWidget(); row_host.setStyleSheet("background:transparent;")
                rrow = QHBoxLayout(row_host); rrow.setContentsMargins(0, 0, 0, 0); rrow.setSpacing(0)
                rrow.addWidget(host, 1); rrow.addWidget(self._canvas_fixed, 1)
                host = row_host
            W.row(row_label, host, canvas_card, label_width=124)
        fit_host = QWidget(); fit_host.setStyleSheet("background:transparent;")
        frow = QHBoxLayout(fit_host); frow.setContentsMargins(0, 2, 0, 0); frow.setSpacing(4)
        for how, key in (("fit", "bgedit.canvas_fit"), ("fill", "bgedit.canvas_fill"), ("one_to_one", "bgedit.canvas_one_to_one")):
            b = self._mini_btn(label(key), tooltip(title=label(key), body=label(key + "_tip")))
            b.clicked.connect(lambda _=False, h=how: self.canvas_fit_requested.emit(h))
            frow.addWidget(b, 1)
        canvas_card.addWidget(fit_host)
        self._canvas_card.setVisible(False)
        # Les ajustements passent avant la compression : ils dirigent ce qu'elle reçoit. Chaque carte se replie
        # d'elle-même (CollapsibleCard) ; son pli suit `_adj_open` / `_tune_open` (cf. `_refresh_tune_visibility`).
        self._adj_card = self._card(label("bgedit.adj_title"), root)
        adj_card = self._adj_card.body_layout
        self._adj_card.toggled.connect(self._on_adj_toggled)
        self._comp_card = self._card(label("bgedit.comp_toggle"), root)
        comp_card = self._comp_card.body_layout
        self._comp_card.toggled.connect(self._on_tune_toggled)
        self._tune_host = QWidget(); self._tune_host.setStyleSheet("background:transparent;")
        tune = QVBoxLayout(self._tune_host); tune.setContentsMargins(0, 0, 0, 0); tune.setSpacing(2)
        self._chk_dither = QCheckBox(label("bgedit.dithering"))
        self._chk_dither.setFont(QFont(T.UI, T.SM))
        self._chk_dither.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_dither.setToolTip(tooltip(
            title=label("bgedit.dithering"), body=label("bgedit.dithering_tip")))
        self._chk_dither.toggled.connect(self._on_dither_toggled)
        # Le type de dithering : à côté de la case, il attend l'encodage comme elle.
        self._cmb_dither = QComboBox()
        self._cmb_dither.setFont(QFont(T.UI, T.SM))
        self._cmb_dither.setStyleSheet(QSS.combobox)
        self._cmb_dither.setToolTip(tooltip(title=label("bgedit.dither_kind"), body=label("bgedit.dither_kind_tip")))
        for token, key in (("floyd_steinberg", "bgedit.dither_floyd"), ("bayer4", "bgedit.dither_bayer4"),
                           ("bayer8", "bgedit.dither_bayer8")):
            self._cmb_dither.addItem(label(key), token)
        self._cmb_dither.currentIndexChanged.connect(self._on_dither_kind_changed)

        # Mesure du 4bpp : à la demande, sur l'image PRÉPARÉE. Sert à décider s'il
        # faut recadrer/réduire avant de passer en 4bpp — elle ne change rien.
        self._btn_analyze = self._mini_btn(
            label("bgedit.analyze"),
            tooltip(title=label("bgedit.analyze"), body=label("bgedit.analyze_tip"),
                    note=label("bgedit.analyze_tip_note")),
        )
        # Enfoncé = l'analyse est affichée ; un second clic la ferme.
        self._btn_analyze.setCheckable(True)
        self._btn_analyze.toggled.connect(self._on_analyze_toggled)
        # La mesure sert surtout à déboguer : le bouton est masqué, la fonction (`_on_analyze_toggled`) reste.
        self._btn_analyze.setVisible(False)
        tune.addWidget(self._btn_analyze)
        self._analysis = QLabel("")
        self._analysis.setTextFormat(Qt.TextFormat.RichText)
        self._analysis.setFont(QFont(T.MONO, T.SM))
        # Même teinte que la console de build : un relevé, pas un texte de l'interface.
        self._analysis.setStyleSheet(
            f"color:{C.CONSOLE_TEXT}; background:{C.BG_DEEP}; border:1px solid {C.BORDER};"
            f"border-radius:4px; padding:6px 8px;")
        self._analysis.setVisible(False)
        tune.addWidget(self._analysis)
        self._analyze_token = 0
        self._analyze_tasks: set = set()

        # ── COMPRESSION du tuilé 4bpp : l'inspecteur est CONTEXTUEL — cette boîte
        #    n'existe que pour le mode qu'elle règle (les autres modes auront la
        #    leur). Chaque réglage relance l'encodage hors-thread, après une courte
        #    pause : on regarde le rendu au canvas pendant qu'on tire le curseur.
        self._comp_host = QWidget(); self._comp_host.setStyleSheet("background:transparent;")
        comp = QVBoxLayout(self._comp_host); comp.setContentsMargins(0, 0, 0, 0); comp.setSpacing(2)
        W.separator(comp)
        self._comp_title = W.section(label("bgedit.comp_title"), comp)
        self._sl_palettes = self._slider_row(
            comp, label("bgedit.comp_palettes"), label("bgedit.comp_palettes_tip"), 1, 16)
        self._sl_colors = self._slider_row(
            comp, label("bgedit.comp_colors"), label("bgedit.comp_colors_tip"), 2, 15)
        self._sl_global = self._slider_row(
            comp, label("bgedit.comp_global"), label("bgedit.comp_global_tip"), 0, 256,
            special=label("bgedit.comp_off"))
        self._sl_pal8 = self._slider_row(
            comp, label("bgedit.comp_colors8"), label("bgedit.comp_colors8_tip"), 2, 255)
        self._sl_tiles = self._slider_row(
            comp, label("bgedit.comp_tiles"), label("bgedit.comp_tiles_tip"), 32, 1024,
            special=label("bgedit.comp_nolimit"), special_at_max=True,
            note=label("bgedit.comp_tiles_tip_note"))
        self._cmb_method = QComboBox()
        self._cmb_method.setFont(QFont(T.UI, T.SM))
        self._cmb_method.setStyleSheet(QSS.combobox)
        self._method_names = {"median_cut": label("bgedit.method_median_cut"),
                              "nearest_pair": label("bgedit.method_nearest_pair"),
                              "most_frequent": label("bgedit.method_most_frequent"),
                              "kmeans": label("bgedit.method_kmeans"),
                              "octree": label("bgedit.method_octree"),
                              "max_coverage": label("bgedit.method_max_coverage")}
        self._cmb_method.setToolTip(tooltip(
            title=label("bgedit.comp_method"), body=label("bgedit.comp_method_tip")))
        self._cmb_method.currentIndexChanged.connect(self._on_comp_changed)
        # La méthode ouvre la boîte, sans libellé : l'infobulle et la liste disent ce qu'elle est.
        comp.insertWidget(2, self._cmb_method)
        # Les lignes propres à un mode : la boîte montre celles du mode courant.
        self._rows_4bpp = [self._sl_palettes._row, self._sl_colors._row, self._sl_global._row]
        self._rows_8bpp = [self._sl_pal8._row]
        self._btn_comp_reset = self._mini_btn(
            label("bgedit.comp_reset"),
            tooltip(title=label("bgedit.comp_reset"), body=label("bgedit.comp_reset_tip")),
        )
        self._btn_comp_reset.clicked.connect(self._on_comp_reset)
        comp.addWidget(self._btn_comp_reset)
        # ── AJUSTEMENTS de l'image : avant la compression, parce qu'ils dirigent ce qu'elle reçoit.
        # Repliable, comme la compression : fermée tant qu'aucun ajustement n'est posé (cf. `_refresh_tune_visibility`).
        self._adj_open = False
        self._adj_host = QWidget(); self._adj_host.setStyleSheet("background:transparent;")
        adj = QVBoxLayout(self._adj_host); adj.setContentsMargins(0, 0, 0, 0); adj.setSpacing(2)
        self._sl_hue = self._slider_row(adj, label("bgedit.adj_hue"), label("bgedit.adj_hue_tip"), -180, 180)
        self._sl_sat = self._slider_row(adj, label("bgedit.adj_saturation"), label("bgedit.adj_saturation_tip"), -100, 100)
        self._sl_bri = self._slider_row(adj, label("bgedit.adj_brightness"), label("bgedit.adj_brightness_tip"), -100, 100)
        self._sl_con = self._slider_row(adj, label("bgedit.adj_contrast"), label("bgedit.adj_contrast_tip"), -100, 100)
        self._btn_adj_reset = self._mini_btn(
            label("bgedit.adj_reset"), tooltip(title=label("bgedit.adj_reset"), body=label("bgedit.adj_reset_tip")))
        self._btn_adj_reset.clicked.connect(self._on_adjust_reset)
        adj.addWidget(self._btn_adj_reset)
        adj_card.addWidget(self._adj_host)
        self._adj_card.setVisible(False)
        tune.addWidget(self._comp_host)
        self._comp_host.setVisible(False)
        # Le dithering vit DANS la boîte de compression : sa place suit l'ordre de résolution, qui dépend de la
        # profondeur (cf. `_arrange_compression`).
        self._dither_host = QWidget(); self._dither_host.setStyleSheet("background:transparent;")
        dither_row = QHBoxLayout(self._dither_host)
        dither_row.setContentsMargins(0, 2, 0, 2); dither_row.setSpacing(8)
        dither_row.addWidget(self._chk_dither); dither_row.addWidget(self._cmb_dither, 1)
        comp.insertWidget(comp.indexOf(self._btn_comp_reset), self._dither_host)
        self._arrange_compression(4)
        comp_card.addWidget(self._tune_host)

        # NB : les infos read-only (dimensions, origine palette, tuiles/palettes) et
        # les alertes de validation NON-BLOQUANTES ne vivent plus dans l'inspecteur —
        # elles sont poussées via `overlays_changed` sur des overlays du canvas
        # (infos bas-gauche, warnings haut-droite). cf. _emit_overlays / _info_lines /
        # _validation_lines. Le PNG source n'est jamais modifié : ces messages
        # décrivent seulement la représentation GBA.

        # ── UI ROLE (kind == ui) : comment le panneau étale l'image ──
        #    Deux façons, et une seule paire de valeurs pour les deux côtés :
        #    ce champ EST `UIContainer.fill_kind` (cf. UI_ROLES). Les marges ne
        #    comptent qu'en cadre étirable, et se règlent aussi au canvas — les
        #    champs et les guides écrivent le même modèle.
        self._ui_card = self._card(label("bgedit.sec_ui_role"), root)
        ui_body = self._ui_card.body_layout
        role_row = QHBoxLayout(); role_row.setContentsMargins(0, 0, 0, 0); role_row.setSpacing(6)
        self._btn_nine = self._mode_btn(label("bgedit.nine"), label("bgedit.nine_tip"))
        self._btn_plain = self._mode_btn(label("common.background"), label("bgedit.plain_tip"))
        self._btn_nine.clicked.connect(lambda: self._set_ui_role(UI_ROLE_NINE))
        self._btn_plain.clicked.connect(lambda: self._set_ui_role(UI_ROLE_BG))
        role_row.addWidget(self._btn_nine, 1); role_row.addWidget(self._btn_plain, 1)
        # Dans un conteneur et non posée en layout nu : `_refresh_kind_sections`
        # ne sait masquer que des widgets, et une ligne posée en layout restait
        # donc visible sur un décor — deux boutons de rôle d'interface offerts
        # sur une image qui n'en a pas.
        role_host = QWidget(); role_host.setStyleSheet("background:transparent;")
        role_host.setLayout(role_row)
        ui_body.addWidget(role_host)

        self._slice_spins: dict[str, QSpinBox] = {}
        slice_host = QWidget(); slice_host.setStyleSheet("background:transparent;")
        srow = QHBoxLayout(slice_host); srow.setContentsMargins(0, 0, 0, 0); srow.setSpacing(4)
        for field_name, lab in (("slice_left", "L"), ("slice_right", "R"),
                                ("slice_top", "T"), ("slice_bottom", "B")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 512)
            sp.setSingleStep(8)      # une tuile : le pas où la coupe existe vraiment
            sp.setKeyboardTracking(False)
            sp.setToolTip(tooltip(
                title=label(f"bgedit.margin_{field_name.removeprefix('slice_')}"),
                body=label("bgedit.margin_tip"), note=label("bgedit.margin_tip_note"),
            ))
            sp.valueChanged.connect(lambda v, f=field_name: self._on_slice(f, v))
            srow.addWidget(t); srow.addWidget(sp, 1)
            self._slice_spins[field_name] = sp
        self._slice_row = W.row(label("bgedit.margins"), slice_host, ui_body).parentWidget()
        self._ui_widgets = [self._ui_card]

        # ── ANIMATION (kind == animated) ─────────────────────────────
        #    Découpe en GRILLE + vitesse en ticks 60 Hz (l'unité de
        #    `AnimState.speed` — animer un décor se lit comme animer un sprite).
        self._anim_card = self._card(label("bgedit.sec_animation"), root)
        anim_body = self._anim_card.body_layout
        frame_host = QWidget(); frame_host.setStyleSheet("background:transparent;")
        frow = QHBoxLayout(frame_host); frow.setContentsMargins(0, 0, 0, 0); frow.setSpacing(4)
        self._frame_spins: dict[str, QSpinBox] = {}
        for field_name, lab in (("frame_w", "W"), ("frame_h", "H")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 1024)
            sp.setSingleStep(8)
            sp.setSpecialValueText(label("bgedit.frame_full"))   # 0 = une seule frame
            sp.setKeyboardTracking(False)
            sp.setToolTip(tooltip(
                title=label(f"bgedit.frame_{'width' if field_name == 'frame_w' else 'height'}"),
                body=label("bgedit.frame_tip"),
            ))
            sp.valueChanged.connect(lambda v, f=field_name: self._on_frame_size(f, v))
            frow.addWidget(t); frow.addWidget(sp, 1)
            self._frame_spins[field_name] = sp
        self._frame_row = W.row(label("common.frame"), frame_host, anim_body).parentWidget()

        self._speed = UnitSpin()
        self._speed.setFont(QFont(T.MONO, T.SM))
        self._speed.setStyleSheet(QSS.spinbox)
        self._speed.setRange(1, 255)
        self._speed.setSuffix(label("bgedit.ticks_suffix"))
        self._speed.setToolTip(tooltip(
            title=label("common.speed"), body=label("bgedit.speed_tip")))
        self._speed.setKeyboardTracking(False)
        self._speed.valueChanged.connect(self._on_speed)
        self._speed_row = W.row(label("common.speed"), self._speed, anim_body).parentWidget()

        self._chk_loop = QCheckBox(label("common.loop"))
        self._chk_loop.setFont(QFont(T.UI, T.SM))
        self._chk_loop.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_loop.toggled.connect(self._on_loop)
        anim_body.addWidget(self._chk_loop)

        # Mode de lecture — nommé par ce que l'auteur VOIT (les copies bougent
        # chacune pour soi, ou toutes ensemble), jamais par le procédé.
        mode_host = QWidget(); mode_host.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(mode_host); mrow.setContentsMargins(0, 0, 0, 0); mrow.setSpacing(6)
        self._anim_mode_btns: dict[str, QPushButton] = {}
        for mode, lbl_key, tip_key in (
            (ANIM_INSTANCE, "bgedit.per_instance", "bgedit.per_instance_tip"),
            (ANIM_SHARED, "bgedit.shared", "bgedit.shared_tip"),
        ):
            b = self._mode_btn(label(lbl_key), label(tip_key))
            b.clicked.connect(lambda _=False, m=mode: self._set_animation_mode(m))
            mrow.addWidget(b, 1)
            self._anim_mode_btns[mode] = b
        self._anim_mode_row = W.row(label("bgedit.playback"), mode_host, anim_body).parentWidget()

        self._anim_widgets = [self._anim_card]

        # ── ANIMATIONS À POSER ────────────────────────────────────────
        #    Réserve de glissement vers le canvas. Dans l'inspecteur et non dans
        #    le finder : celui-ci pilote l'asset édité, y presser un item ferait
        #    changer le canvas sous le drag (cf. _AnimatedSourceList).
        self._src_card = self._card(label("bgedit.sec_animations"), root)
        self._src_hint = QLabel(label("bgedit.src_hint"))
        self._src_hint.setFont(QFont(T.UI, T.SM))
        self._src_hint.setStyleSheet(f"color:{C.TEXT_MUTED}; background:transparent;")
        self._src_card.body_layout.addWidget(self._src_hint)
        self._src_list = _AnimatedSourceList()
        self._src_card.body_layout.addWidget(self._src_list)
        self._src_widgets = [self._src_card]

        # ── PLACEMENT (un animé sélectionné sur le canvas) ────────────
        #    Section pilotée par la SÉLECTION et non par le type de l'asset :
        #    elle décrit une copie posée, pas l'image courante.
        self._pl_card = self._card(label("bgedit.sec_placement"), root)
        pl_body = self._pl_card.body_layout
        self._pl_name = QLabel("")
        self._pl_name.setFont(QFont(T.MONO, T.SM))
        self._pl_name.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        pl_body.addWidget(self._pl_name)
        self._pl_start = QSpinBox()
        self._pl_start.setFont(QFont(T.MONO, T.SM))
        self._pl_start.setStyleSheet(QSS.spinbox)
        self._pl_start.setRange(0, 255)
        self._pl_start.setToolTip(tooltip(
            title=label("bgedit.start_frame"), body=label("bgedit.pl_start_tip")))
        self._pl_start.setKeyboardTracking(False)
        self._pl_start.valueChanged.connect(self._on_placement_start)
        self._pl_start_row = W.row(label("bgedit.start_frame"), self._pl_start, pl_body).parentWidget()

        self._pl_speed = UnitSpin()
        self._pl_speed.setFont(QFont(T.MONO, T.SM))
        self._pl_speed.setStyleSheet(QSS.spinbox)
        self._pl_speed.setRange(0, 255)
        self._pl_speed.setSuffix(label("bgedit.ticks_suffix"))
        self._pl_speed.setSpecialValueText(label("bgedit.default"))   # 0 = cadence de l'animé
        self._pl_speed.setToolTip(tooltip(
            title=label("common.speed"), body=label("bgedit.pl_speed_tip")))
        self._pl_speed.setKeyboardTracking(False)
        self._pl_speed.valueChanged.connect(self._on_placement_speed)
        self._pl_speed_row = W.row(label("common.speed"), self._pl_speed, pl_body).parentWidget()

        self._pl_widgets = [self._pl_card]
        self._placement = None
        for w in self._pl_widgets:
            w.setVisible(False)

        # ── PALETTES : grille unifiée (modèle Scene Inspector). Palettes dérivées
        #    du PNG grisées + overridables (clic = pointer une banque du catalogue,
        #    clic droit = restaurer l'origine) ; « + » ajoute une palette du
        #    catalogue (éditable, clic = remplacer, clic droit = retirer). La
        #    palette active de PEINTURE se choisit dans la bande en haut du canvas.
        pal_card = self._card(label("common.palettes"), root)
        self._pal_grid = PaletteSlotGridAsset(_BG_COLOR)
        self._pal_grid.scene_add.connect(self._on_pal_add)
        self._pal_grid.scene_replace.connect(self._on_pal_replace)
        self._pal_grid.scene_remove.connect(self._on_pal_remove)
        self._pal_grid.asset_override.connect(self._on_pal_override)
        self._pal_grid.asset_restore.connect(self._on_pal_restore)
        pal_card.body_layout.addWidget(self._pal_grid)

        # Ferrés en bas, avec « Extraire les palettes » : les gestes qui portent sur
        # l'image entière, du plus léger au plus lourd, hors du flux des réglages.
        root.addStretch()
        self._btn = self._footer_btn(
            label("bgedit.import_replace"),
            tooltip(title=label("bgedit.import_replace_title"),
                    body=label("bgedit.import_replace_tip")))
        self._btn.clicked.connect(self._on_replace)
        root.addWidget(self._btn)

        self._btn_restore = self._footer_btn(
            label("bgedit.restore"),
            tooltip(title=label("bgedit.restore_title"), body=label("bgedit.restore_tip"),
                    warning=label("bgedit.restore_tip_warning")))
        self._btn_restore.clicked.connect(self._on_restore)
        root.addWidget(self._btn_restore)

        # ── EXTRACT PALETTE — ferré en bas de l'inspecteur. Promeut les
        #    sous-palettes déduites du PNG en PaletteBank partagées du catalogue
        #    (visibles/éditables depuis le Palette Editor) et les assigne à ce fond.
        self._btn_extract = QPushButton(label("bgedit.extract"))
        self._btn_extract.setToolTip(tooltip(
            title=label("bgedit.extract_title"), body=label("bgedit.extract_tip"),
            warning=label("bgedit.extract_warning")))
        self._btn_extract.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_extract.setFixedHeight(38)
        self._btn_extract.setStyleSheet(
            f"QPushButton{{color:{_BG_COLOR}; background:transparent;"
            f"border:2px solid {_BG_COLOR}; border-radius:5px; letter-spacing:1px;"
            f"padding:4px 10px;}}"
            f"QPushButton:hover{{color:{C.BG_DEEP}; background:{_BG_COLOR};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:transparent;}}"
        )
        self._btn_extract.clicked.connect(self._on_extract_palette)
        root.addWidget(self._btn_extract)
        # Deux sorties de l'image telle qu'elle s'affiche : « Save as PNG » la CUIT dans un fichier du projet qui
        # devient la source du fond ; « Export to PNG » la copie où l'auteur veut, sans rien changer.
        png_row = QHBoxLayout(); png_row.setContentsMargins(0, 0, 0, 0); png_row.setSpacing(6)
        self._btn_save_png = self._footer_btn(
            label("bgedit.save_png"),
            tooltip(title=label("bgedit.save_png"), body=label("bgedit.save_png_tip")))
        self._btn_save_png.clicked.connect(self._on_save_png)
        self._btn_export_png = self._footer_btn(
            label("bgedit.export_png"),
            tooltip(title=label("bgedit.export_png"), body=label("bgedit.export_png_tip")))
        self._btn_export_png.clicked.connect(self._on_export_png)
        png_row.addWidget(self._btn_save_png, 1); png_row.addWidget(self._btn_export_png, 1)
        root.addLayout(png_row)

    def _footer_btn(self, text: str, tip: str = "") -> QPushButton:
        """Bouton d'action du pied de l'inspecteur : une seule taille et un seul
        style pour tous, sinon deux gestes voisins ne se lisent pas comme frères."""
        b = self._mini_btn(text, tip)
        b.setFont(QFont(T.UI, T.MD))
        b.setFixedHeight(30)
        return b

    def _slider_row(self, layout, name: str, tip: str, lo: int, hi: int, special: str = "",
                    special_at_max: bool = False, note: str = "") -> QSlider:
        """Ligne « libellé  [curseur]  [champ] ». Le champ et le curseur disent la
        même valeur : tirer l'un met l'autre à jour, taper dans le champ déplace le
        curseur. `special` nomme l'extrémité qui veut dire « désactivé » (0, ou le
        maximum pour la cible de tuiles : plus haut = moins de contrainte)."""
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        rich_tip = tooltip(title=name, body=tip, note=note)
        sl.setToolTip(rich_tip)
        # L'infobulle est rendue par le contrôleur commun, hors du style du slider.
        sl.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px; background:{C.BORDER_MID}; border-radius:2px;}}"
            f"QSlider::sub-page:horizontal{{background:{_BG_COLOR}; border-radius:2px;}}"
            f"QSlider::handle:horizontal{{width:12px; height:12px; margin:-4px 0;"
            f"border-radius:6px; background:{C.TEXT_NORM};}}"
            f"QSlider::handle:horizontal:hover{{background:{_BG_COLOR};}}")
        spin = _SliderSpin(special, special_at_max)
        spin.setRange(lo, hi)
        spin.setFont(QFont(T.MONO, T.SM))
        spin.setFixedWidth(80)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setKeyboardTracking(False)      # la valeur tapée compte à Entrée, pas à chaque chiffre
        spin.setToolTip(rich_tip)
        host = QWidget(); host.setStyleSheet("background:transparent;")
        h = QHBoxLayout(host); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        h.addWidget(sl, 1); h.addWidget(spin)
        W.row(name, host, layout, label_width=104)
        sl._row = host.parentWidget()      # pour montrer/cacher la ligne entière
        sl.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(sl.setValue)
        sl.valueChanged.connect(self._on_comp_changed)
        return sl

    def show_canvas_state(self, canvas, rect, source_size, canvas_editable: bool):
        """La carte Canvas d'après le canvas central : le canvas, l'image posée, et si la taille du canvas se règle.
        `canvas` est None quand le fond n'a pas de canvas à régler (la carte se cache)."""
        self._canvas_card.setVisible(canvas is not None)
        if canvas is None:
            return
        values = {"canvas_w": canvas[0], "canvas_h": canvas[1], "pos_x": rect[0], "pos_y": rect[1],
                  "size_w": rect[2], "size_h": rect[3]}
        for name, sp in self._canvas_spins.items():
            sp.blockSignals(True)
            sp.setValue(values[name])
            sp.blockSignals(False)
        self._canvas_size_host.setVisible(canvas_editable)
        self._canvas_fixed.setVisible(not canvas_editable)
        self._canvas_fixed.setText(label("bgedit.canvas_fixed", w=canvas[0], h=canvas[1]))

    def _on_canvas_field(self):
        s = self._canvas_spins
        self.canvas_edited.emit((s["canvas_w"].value(), s["canvas_h"].value()),
                                (s["pos_x"].value(), s["pos_y"].value(), s["size_w"].value(), s["size_h"].value()))

    @staticmethod
    def _card(title: str, root: QVBoxLayout) -> CollapsibleCard:
        """Une carte repliable posée dans `root` — la même que celles du Scene Inspector."""
        card = CollapsibleCard(title)
        root.addWidget(card)
        return card

    def _mini_btn(self, text: str, tip: str = "") -> QPushButton:
        b = QPushButton(text); b.setToolTip(tip)
        b.setFont(QFont(T.UI, T.SM))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:3px 8px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; background:{C.BG_HOVER};}}"
            f"QPushButton:checked{{color:{_BG_COLOR}; border:2px solid {_BG_COLOR};"
            f"background:{C.BG_SEL};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};}}"
        )
        return b

    def _mode_btn(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text); b.setToolTip(tooltip(title=text, body=tip))
        b.setCheckable(True)
        b.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:4px; padding:2px 10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            f"QPushButton:checked{{color:{_BG_COLOR}; border:2px solid {_BG_COLOR};"
            f"background:{C.BG_SEL};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:{C.BG_INPUT};}}"
        )
        return b

    # ── Mode couleur : 2 axes (layout × profondeur) ───────────────
    #    Combinaisons valides GBA : tuilé→{4,8}, bitmap→{8,16}. Le 16bpp direct
    #    n'est pas encore implémenté (repli Mode 4) → bouton visible mais désactivé.

    def _cur_axes(self) -> tuple[str, int]:
        """(layout, profondeur) courant de l'asset. Le bitmap est du Mode 4 (8bpp) :
        le 16bpp direct n'étant pas persisté, on le lit toujours comme 8."""
        if not self._ba:
            return ("tiled", 4)
        if self._ba.mode == "bitmap":
            return ("bitmap", 8)
        return ("tiled", 8 if self._ba.bpp == 8 else 4)

    @staticmethod
    def _axes_token(layout: str, depth: int) -> str:
        if layout == "tiled":
            return "tiled8" if depth == 8 else "tiled4"
        return "bitmap16" if depth == 16 else "bitmap"

    def _cur_mode_token(self) -> str:
        return self._axes_token(*self._cur_axes())

    def _shown_axes(self) -> tuple[str, int]:
        """Ce que les boutons montrent : le choix en attente de compression, sinon l'état du fond."""
        return self._staged or self._cur_axes()

    def _is_pending(self) -> bool:
        """Un réglage de l'inspecteur diffère-t-il du fond tel qu'il est compressé ?"""
        ba = self._ba
        return bool(ba and ba.asset and (
            self._axes_token(*self._shown_axes()) != self._cur_mode_token()
            or self._chk_dither.isChecked() != bool(ba.dither)
            or self._current_adjust() != ba.adjust
            or (self._comp_visible() and (
                self._current_compression() != ba.compression
                or self._cmb_method.currentData() not in (None, ba.quantize_method)))))

    def settings(self) -> dict:
        """Tout ce que l'encodage prend, d'un bloc : le même dict sert la demande au service, la clé du cache et la validation."""
        return {"token": self._axes_token(*self._shown_axes()), "dither": self._chk_dither.isChecked(),
                "compression": self._current_compression(), "adjust": self._current_adjust(),
                "method": self._cmb_method.currentData() or (self._ba.quantize_method if self._ba else "median_cut")}

    def _emit_request(self):
        """Après une pause : les réglages en attente (le service les encode), ou None : plus rien n'est en attente."""
        self.preview_requested.emit(self.settings() if self._is_pending() else None)

    def _refresh_pending(self):
        """Un réglage a bougé : après une pause, le service d'encodage en est averti (`preview_requested`). Un réglage en
        attente ouvre la carte de la compression, pour qu'on voie ce qui est en attente."""
        pending = self._is_pending()
        self._request_timer.start()
        if pending and not self._tune_open:
            self._tune_open = True
            self._refresh_tune_visibility()

    def _refresh_mode_buttons(self):
        layout, depth = self._shown_axes()
        tok = self._axes_token(layout, depth)
        tiled = layout == "tiled"
        base = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        self._blocking = True
        self._btn_tiled.setChecked(tiled)
        self._btn_bitmap.setChecked(not tiled)
        self._d4.setChecked(tiled and depth == 4)
        self._d8.setChecked(depth == 8)
        self._d16.setChecked(not tiled and depth == 16)
        # Filtre des profondeurs valides selon le layout.
        self._btn_tiled.setEnabled(base); self._btn_bitmap.setEnabled(base)
        self._d4.setEnabled(base and tiled)          # 4bpp : tuilé uniquement
        self._d8.setEnabled(base)                    # 8bpp : toujours
        self._d16.setEnabled(False)                  # 16bpp direct : à venir
        self._chk_dither.setVisible(True)
        if self._staged is None:
            self._chk_dither.setChecked(bool(self._ba and self._ba.dither))
        self._blocking = False
        self._refresh_pending()
        self.layout_shown.emit(layout)       # la carte Canvas suit le layout CHOISI, avant même qu'il soit compressé

    def _apply_axes(self, layout: str, depth: int):
        """Met (layout, depth) en attente : les boutons le montrent et le service d'encodage le prend après la pause."""
        if self._blocking or not self._ba or not self._project:
            self._refresh_mode_buttons(); return
        ap = self._png_path()
        if not ap or not ap.exists():
            self._refresh_mode_buttons(); return
        self._staged = None if self._axes_token(layout, depth) == self._cur_mode_token() else (layout, depth)
        self._refresh_mode_buttons()
        self._refresh_compression_layout()      # la boîte suit le layout et la profondeur CHOISIS, avant la compression

    def _set_layout(self, layout: str):
        # Bascule d'axe : on snappe la profondeur sur une valeur valide du layout
        # cible (tuilé→{4,8}, bitmap→{8,16}), en gardant l'actuelle si possible.
        _, depth = self._shown_axes()
        valid = (4, 8) if layout == "tiled" else (8, 16)
        self._apply_axes(layout, depth if depth in valid else 8)

    def _set_depth(self, depth: int):
        layout, _ = self._shown_axes()
        self._apply_axes(layout, depth)

    def _on_dither_kind_changed(self, *_):
        if self._blocking or not self._ba:
            return
        self._refresh_pending()

    def _on_dither_toggled(self, on: bool):
        # Le dithering se règle comme le mode : il attend l'encodage.
        if self._blocking or not self._ba:
            return
        self._refresh_pending()

    # ── Type de fond & sections dépendantes ───────────────────────

    def _set_kind(self, kind: str):
        """Convertit l'asset — même PNG, même compression, autre emploi. Le
        finder re-trie (l'asset change de section) et le canvas change ce qu'il
        superpose."""
        if self._blocking or not self._ba or not self._project:
            self._refresh_kind_buttons(); return
        if self._ba.kind == kind:
            self._refresh_kind_buttons(); return
        self._ba.kind = kind
        self._persist_bg()
        self.kind_changed.emit()

    def _refresh_kind_buttons(self):
        kind = self._ba.kind if self._ba else KIND_SCENE
        self._blocking = True
        for k, b in self._kind_btns.items():
            b.setChecked(k == kind)
            b.setEnabled(self._ba is not None)
        self._blocking = False

    def _refresh_kind_sections(self):
        """Montre la section propre au type courant. Un fond n'a qu'un emploi :
        empiler les trois panneaux ferait chercher lequel s'applique."""
        kind = self._ba.kind if self._ba else KIND_SCENE
        is_ui = self._ba is not None and kind == KIND_UI
        is_anim = self._ba is not None and kind == KIND_ANIMATED
        for w in self._ui_widgets:
            w.setVisible(is_ui)
        # Les marges ne veulent rien dire pour une image simplement posée.
        self._slice_row.setVisible(is_ui and self._ba.ui_role == UI_ROLE_NINE)
        for w in self._anim_widgets:
            w.setVisible(is_anim)
        self._blocking = True
        if is_ui:
            self._btn_nine.setChecked(self._ba.ui_role == UI_ROLE_NINE)
            self._btn_plain.setChecked(self._ba.ui_role == UI_ROLE_BG)
            for f, sp in self._slice_spins.items():
                sp.setValue(int(getattr(self._ba, f, 0)))
        if is_anim:
            for f, sp in self._frame_spins.items():
                sp.setValue(int(getattr(self._ba, f, 0)))
            self._speed.setValue(max(1, int(self._ba.speed)))
            self._chk_loop.setChecked(bool(self._ba.loop))
        self._blocking = False
        if is_anim:
            self._refresh_anim_mode_buttons()
        self._refresh_animation_sources()

    def _refresh_animation_sources(self):
        """Réserve d'animés à poser — cachée quand elle ne mènerait à rien.

        Absente sur un animé lui-même : le modèle permet d'en poser un sur un
        autre (une planche reste une image), mais l'éditeur ne le propose pas,
        et une réserve visible là inviterait à un montage que rien ne réclame.
        Absente aussi tant que le projet n'a aucun animé — une liste vide ne
        s'explique pas toute seule."""
        assets = [b for b in (self._project.backgrounds if self._project else [])
                  if b.kind == KIND_ANIMATED]
        show = bool(assets) and self._ba is not None and self._ba.kind != KIND_ANIMATED
        for w in self._src_widgets:
            w.setVisible(show)
        if show:
            self._src_list.set_assets(assets)

    # ── kind == ui ────────────────────────────────────────────────

    def _set_ui_role(self, role: str):
        if self._blocking or not self._ba:
            self._refresh_kind_sections(); return
        if self._ba.ui_role != role:
            self._ba.ui_role = role
            self._persist_bg()
        self._refresh_kind_sections()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_slice(self, field_name: str, value: int):
        if self._blocking or not self._ba:
            return
        setattr(self._ba, field_name, int(value))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def set_slice_margins(self, margins: dict):
        """Marges posées depuis le CANVAS (glissement d'un guide). Le canvas a
        déjà écrit le modèle : on ne fait que réaligner les champs, sans
        repersister ni réémettre — sinon chaque pixel de glissement rebouclerait
        sur le canvas qui l'a produit."""
        self._blocking = True
        for f, v in margins.items():
            sp = self._slice_spins.get(f)
            if sp is not None:
                sp.setValue(int(v))
        self._blocking = False
        self._emit_overlays()

    # ── kind == animated ──────────────────────────────────────────

    def _on_frame_size(self, field_name: str, value: int):
        if self._blocking or not self._ba:
            return
        setattr(self._ba, field_name, max(0, int(value)))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_speed(self, value: int):
        if self._blocking or not self._ba:
            return
        self._ba.speed = max(1, int(value))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_loop(self, on: bool):
        if self._blocking or not self._ba:
            return
        self._ba.loop = bool(on)
        self._persist_bg()
        self.geometry_changed.emit()

    def _set_animation_mode(self, mode: str):
        """Le mode vit sur l'ANIMÉ : le changer ici le change pour tous les fonds
        qui posent cette animation. Rien à réémettre côté canvas — les deux modes
        se jouent pareil dans l'éditeur, ils ne divergent qu'en ROM."""
        if self._blocking or not self._ba:
            self._refresh_anim_mode_buttons(); return
        if self._ba.animation_mode != mode:
            self._ba.animation_mode = mode
            self._persist_bg()
        self._refresh_anim_mode_buttons()

    def set_placement(self, pl):
        """Copie posée sélectionnée au canvas — None pour refermer la section.

        Masquée en mode `shared` plutôt que grisée : là-bas toutes les copies
        partagent un unique compteur, un décalage par copie n'y décrit rien. Un
        champ sans effet vaut moins qu'un champ absent."""
        ba = None
        if pl is not None and self._project is not None:
            ba = self._project.get_background(getattr(pl, "animated_name", ""))
        show = (pl is not None and ba is not None
                and getattr(ba, "animation_mode", ANIM_INSTANCE) != ANIM_SHARED)
        self._placement = pl if show else None
        for w in self._pl_widgets:
            w.setVisible(show)
        if not show:
            return
        self._blocking = True
        self._pl_name.setText(ba.name)
        # Plafond = la dernière image de la planche : au-delà ça reboucle, et un
        # nombre sans effet visible ne se règle pas.
        self._pl_start.setMaximum(max(0, ba.frame_count() - 1))
        self._pl_start.setValue(int(getattr(pl, "start_frame", 0) or 0))
        self._pl_speed.setValue(int(getattr(pl, "speed", 0) or 0))
        self._blocking = False

    def _on_placement_start(self, value: int):
        if self._blocking or self._placement is None:
            return
        self._placement.start_frame = max(0, int(value))
        self._persist_bg()
        self.placement_changed.emit()

    def _on_placement_speed(self, value: int):
        if self._blocking or self._placement is None:
            return
        self._placement.speed = max(0, int(value))
        self._persist_bg()
        self.placement_changed.emit()

    def _refresh_anim_mode_buttons(self):
        mode = getattr(self._ba, "animation_mode", ANIM_INSTANCE) if self._ba else ANIM_INSTANCE
        self._blocking = True
        for m, b in self._anim_mode_btns.items():
            b.setChecked(m == mode)
            b.setEnabled(self._ba is not None)
        self._blocking = False

    def load(self, ba, project):
        previous = self._ba
        self._staged = None
        self._project, self._ba = project, ba
        self._blocking = True
        if ba:
            self._header.set_header("background", ba.kind_label(), ba.name)
        else:
            self._header.set_header("empty", "", "")
        self._blocking = False
        self._clear_analysis()   # mesurait l'image d'avant (autre fond, autre taille)
        self._btn_analyze.setEnabled(bool(ba and ba.asset))
        self._refresh_kind_buttons()
        self._refresh_kind_sections()
        self._refresh_mode_buttons()
        # Les outils de compression sont toujours visibles pour permettre les
        # essais créatifs, y compris sur un fond déjà compatible.
        if ba is not previous:
            self._tune_open = True
            self._adj_open = bool(ba and not ba.adjust.is_default())     # fermés tant qu'aucun ajustement n'est posé
        self._refresh_compression_ui()
        self._refresh_pending()
        self.adjust_preview_requested.emit(None)      # un autre fond, ou la compression est faite : le rendu compressé
        self._refresh_png_buttons()
        self._reload_palettes()   # émet aussi les overlays (infos + warnings)

    # ── Mesure du 4bpp ────────────────────────────────────────────
    def _clear_analysis(self):
        """Ferme l'analyse et relâche le bouton — appelé aussi quand l'image change."""
        self._analyze_token += 1       # un résultat en vol devient périmé
        self._analysis.setVisible(False)
        self._btn_analyze.blockSignals(True)
        self._btn_analyze.setChecked(False)
        self._btn_analyze.blockSignals(False)

    def _on_analyze_toggled(self, on: bool):
        if not on:
            self._clear_analysis()
            return
        ba, ap = self._ba, self._png_path()
        if not ba or not ap or not ap.exists():
            self._clear_analysis()
            return
        self._analyze_token += 1
        token = self._analyze_token
        self._analysis.setText(label("bgedit.analyzing"))
        self._analysis.setVisible(True)
        task = _AnalyzeTask(token, ap, ba.import_prep())

        def _done(tok, m):
            self._analyze_tasks.discard(task)
            if tok == self._analyze_token:
                self._analysis.setText(self._analysis_text(m))

        def _failed(tok, msg):
            self._analyze_tasks.discard(task)
            if tok == self._analyze_token:
                self._analysis.setText(html.escape(label("bgedit.analysis_failed", msg=msg)))

        task.signals.done.connect(_done)
        task.signals.failed.connect(_failed)
        self._analyze_tasks.add(task)
        QThreadPool.globalInstance().start(task)

    @staticmethod
    def _analysis_text(m: dict) -> str:
        """Relevé compact, une mesure par ligne, valeurs alignées — le ton d'une
        sortie de débogage, pas d'une phrase."""
        b1, b2, b3 = m["buckets"]
        rows = [
            (label("bgedit.an_k_colors"),
             f"{m['colors_min']} · {m['colors_avg']:.1f} · {m['colors_max']}"),
            (label("bgedit.an_k_fit"), f"{b1} / {m['tiles']}"),
            (label("bgedit.an_k_mid"), str(b2)),
            (label("bgedit.an_k_high"), str(b3)),
            (label("bgedit.an_k_sets"), str(m["distinct_sets"])),
            (label("bgedit.an_k_shared"), str(m["shared_tiles"])),
            (label("bgedit.an_k_palettes"), f"{m['palettes_needed']} / 16"),
        ]
        width = max(len(k) for k, _ in rows)
        body = "\n".join(f"{html.escape(k.ljust(width))}  {html.escape(v)}" for k, v in rows)
        lossless = m["tiles_over"] == 0 and m["palettes_needed"] <= 16
        verdict = (label("bgedit.an_lossless") if lossless
                   else label("bgedit.an_lossy", over=m["tiles_over"]))
        color = C.TEXT_HI if lossless else C.ACCENT_RED
        return (f'<div style="white-space:pre">{body}\n'
                f'<span style="color:{color}">{html.escape(verdict)}</span></div>')

    # ── Compression (tuilé 4/8bpp et bitmap 8bpp) ─────────────────
    def _comp_visible(self) -> bool:
        ba = self._ba
        return bool(ba and self._shown_axes()[1] in (4, 8) and (ba.tileset or ba.bitmap))

    def _fill_methods(self, bpp: int):
        """La liste des méthodes dit ce que le mode sait faire : réduire les
        couleurs d'une tuile en 4bpp, quantifier la palette unique en 8bpp. La méthode choisie reste choisie quand
        elle existe dans la nouvelle liste."""
        tokens = (QUANTIZERS_8BPP if bpp == 8 else [t for t, _n in COMPRESSION_METHODS])
        current = self._cmb_method.currentData()
        self._cmb_method.blockSignals(True)
        self._cmb_method.clear()
        for token in tokens:
            self._cmb_method.addItem(self._method_names[token], token)
        self._cmb_method.setCurrentIndex(max(0, self._cmb_method.findData(current)))
        self._cmb_method.blockSignals(False)

    def _arrange_compression(self, bpp: int):
        """Range les réglages dans l'ordre où l'encodeur les RÉSOUT — de haut en bas, un réglage ne refait que ce qui
        le suit, donc plus il est bas moins il coûte (cf. `encode_background`) :
          4bpp : couleurs globales → dithering → méthode → couleurs par palette → palettes → tuiles ;
          8bpp : méthode → couleurs → dithering → tuiles (le dithering agit sur la quantification même).
        Les réglages d'une autre profondeur restent cachés derrière, sans importance."""
        lay = self._comp_host.layout()
        by_depth = {
            4: [self._sl_global._row, self._dither_host, self._cmb_method, self._sl_colors._row,
                self._sl_palettes._row, self._sl_tiles._row],
            8: [self._cmb_method, self._sl_pal8._row, self._dither_host, self._sl_tiles._row],
        }[8 if bpp == 8 else 4]
        movable = [self._cmb_method, self._sl_global._row, self._sl_colors._row, self._sl_palettes._row,
                   self._sl_pal8._row, self._sl_tiles._row, self._dither_host]
        for widget in movable:
            lay.removeWidget(widget)
        start = lay.indexOf(self._btn_comp_reset)          # « Reset » reste en dernier
        for offset, widget in enumerate(by_depth + [w for w in movable if w not in by_depth]):
            lay.insertWidget(start + offset, widget)

    def _refresh_compression_layout(self):
        """La boîte de compression d'après le layout et la profondeur MONTRÉS par les boutons — le choix en attente de
        compression compris : titre, ordre et lignes de curseurs, liste des méthodes, dithering. Elle ne touche à aucune
        valeur : un curseur déjà tiré reste où il est."""
        self._arrange_compression(self._shown_axes()[1])
        show = self._comp_visible()
        self._comp_host.setVisible(show)
        if not show:
            return
        layout, bpp = self._shown_axes()
        was, self._blocking = self._blocking, True
        self._comp_title.setText(label("bgedit.comp_title8") if bpp == 8 else label("bgedit.comp_title"))
        for row in self._rows_4bpp:
            row.setVisible(bpp == 4)
        for row in self._rows_8bpp:
            row.setVisible(bpp == 8)
        # Un bitmap n'a pas de tileset : la cible de tuiles ne s'y applique pas. Les couleurs, la méthode et le
        # dithering restent, eux, utiles.
        self._sl_tiles._row.setVisible(layout != "bitmap")
        self._fill_methods(bpp)
        self._sync_dither_enabled()
        self._blocking = was

    def _refresh_compression_ui(self):
        """Montre la boîte pour le mode qu'elle règle et y recopie l'état du fond.
        Signaux coupés : ce n'est pas l'auteur qui tire les curseurs."""
        self._refresh_tune_visibility()
        has_image = bool(self._ba and self._ba.asset)
        if self._ba:
            was, self._blocking = self._blocking, True
            a = self._ba.adjust
            for sl, v in ((self._sl_hue, a.hue), (self._sl_sat, a.saturation),
                          (self._sl_bri, a.brightness), (self._sl_con, a.contrast)):
                sl.setValue(v)
            self._blocking = was
        self._refresh_compression_layout()
        if not self._comp_visible():
            return
        c = self._ba.compression
        was, self._blocking = self._blocking, True
        for sl, v in ((self._sl_palettes, c.palettes_max), (self._sl_colors, c.colors_per_palette),
                      (self._sl_global, c.global_colors), (self._sl_pal8, c.palette_colors),
                      (self._sl_tiles, c.tile_target or self._sl_tiles.maximum())):
            sl.setValue(v)
        self._cmb_method.setCurrentIndex(max(0, self._cmb_method.findData(self._ba.quantize_method)))
        self._sync_dither_enabled()
        self._cmb_dither.setCurrentIndex(max(0, self._cmb_dither.findData(c.dither_kind)))
        self._blocking = was

    def _refresh_tune_visibility(self):
        """Les deux cartes et le pli de la compression — sans toucher aux valeurs des curseurs."""
        has_image = bool(self._ba and self._ba.asset)
        has_base = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        self._adj_card.setVisible(has_image and has_base)
        self._comp_card.setVisible(has_image)
        for card, is_open in ((self._comp_card, self._tune_open), (self._adj_card, self._adj_open)):
            card.blockSignals(True)      # le pli suit l'état : ce n'est pas un clic de l'auteur
            card.set_expanded(is_open)
            card.blockSignals(False)
        # Gel temporaire : la carte Compression reste, avec son bouton d'application du mode et sa barre d'attente.
        for frozen in (self._adj_host, self._tune_host):
            frozen.setEnabled(bg_inpaint_canvas.PREPARATION_TOOLS_ENABLED)

    def _on_tune_toggled(self, on: bool):
        self._tune_open = on
        self._refresh_compression_ui()

    def _on_adj_toggled(self, on: bool):
        self._adj_open = on
        self._refresh_tune_visibility()

    def _compression_needs_attention(self, ba) -> bool:
        """Vrai si l'image ne tient pas telle quelle (un constat de compression), ou si l'auteur a déjà réglé
        quelque chose — de quoi justifier d'ouvrir d'office la boîte. Faux pour un fond sans image."""
        if not ba or not ba.asset:
            return False
        return bool(self._compression_lines(ba) or not ba.compression.is_default() or ba.dither
                    or not ba.adjust.is_default())

    def _sync_dither_enabled(self) -> None:
        """La case ET le type de dithering se grisent ensemble, et l'infobulle dit pourquoi : en 4bpp il n'y a rien à
        diffuser tant que « Global colors » est à Off."""
        on = self._dither_applies()
        self._chk_dither.setEnabled(on)
        self._cmb_dither.setEnabled(on)
        base = tooltip(title=label("bgedit.dithering"), body=label("bgedit.dithering_tip"),
                       note=None if on else label("bgedit.dithering_needs_global"))
        self._chk_dither.setToolTip(base)

    def _dither_applies(self) -> bool:
        """En 8bpp le dithering agit sur la quantification ; en 4bpp seulement sur la
        réduction globale — sans elle, il n'y a aucune erreur à diffuser."""
        if self._ba and self._shown_axes()[1] == 8:
            return True
        return self._sl_global.value() > 0

    def _current_adjust(self) -> BackgroundAdjust:
        return BackgroundAdjust(hue=self._sl_hue.value(), saturation=self._sl_sat.value(),
                                brightness=self._sl_bri.value(), contrast=self._sl_con.value())

    def _on_adjust_reset(self):
        if not self._ba:
            return
        was, self._blocking = self._blocking, True
        for sl in (self._sl_hue, self._sl_sat, self._sl_bri, self._sl_con):
            sl.setValue(0)
        self._blocking = was
        self._refresh_pending()
        self._emit_adjust_preview()

    def _current_compression(self) -> BackgroundCompression:
        tiles = self._sl_tiles.value()
        return BackgroundCompression(
            palettes_max=self._sl_palettes.value(),
            colors_per_palette=self._sl_colors.value(),
            global_colors=self._sl_global.value(),
            palette_colors=self._sl_pal8.value(),
            tile_target=0 if tiles >= self._sl_tiles.maximum() else tiles,
            dither_kind=self._cmb_dither.currentData() or "floyd_steinberg")

    def _on_comp_changed(self, *_):
        if self._blocking or not self._ba:
            return
        # Un curseur qu'on tire ne compresse pas : il met son réglage en attente, le service d'encodage le prend.
        self._sync_dither_enabled()
        self._refresh_pending()
        self._preview_timer.start()

    def _emit_adjust_preview(self):
        """Les ajustements se voient en direct : l'écran prévisualise l'image réglée, avant toute compression."""
        ba = self._ba
        if not (ba and ba.asset):
            return
        current = self._current_adjust()
        if current != ba.adjust:
            self.adjust_preview_requested.emit(current)       # l'image réglée, tout de suite
        elif not self._is_pending():
            self.adjust_preview_requested.emit(None)          # rien en attente : le rendu compressé
        # Sinon, l'aperçu de la compression prendra le relais : on ne le fait pas clignoter.

    def _on_comp_reset(self):
        """Remet les curseurs de compression au défaut — en attente, comme tout réglage."""
        if not self._ba:
            return
        defaults = BackgroundCompression()
        was, self._blocking = self._blocking, True
        for sl, v in ((self._sl_palettes, defaults.palettes_max), (self._sl_colors, defaults.colors_per_palette),
                      (self._sl_global, defaults.global_colors), (self._sl_pal8, defaults.palette_colors),
                      (self._sl_tiles, self._sl_tiles.maximum())):
            sl.setValue(v)
        self._cmb_dither.setCurrentIndex(max(0, self._cmb_dither.findData(defaults.dither_kind)))
        self._cmb_method.setCurrentIndex(max(0, self._cmb_method.findData("median_cut")))
        self._blocking = was
        self._sync_dither_enabled()
        self._refresh_pending()

    def _emit_overlays(self):
        """Pousse les infos read-only + les warnings vers les overlays du canvas."""
        ba = self._ba
        info = self._info_lines(ba) if ba else []
        warns = self._validation_lines(ba) if ba else []
        self.overlays_changed.emit(info, warns)

    def _info_lines(self, ba) -> list:
        """Lignes descriptives read-only (dims, origine palette, tuiles, palettes)
        pour l'overlay bas-gauche du canvas."""
        if not ba or not (ba.tileset or ba.bitmap):
            return []
        lines: list = []
        if ba.mode == "bitmap" and ba.bitmap:
            lines.append(label('bgedit.out_w_out_h_px_bitmap_240_160', out_w=ba.out_w, out_h=ba.out_h))
        elif ba.tileset:
            lines.append(label('bgedit.value_value_2_px_tiles_w_tiles_h', value=ba.tiles_w * 8, value_2=ba.tiles_h * 8, tiles_w=ba.tiles_w, tiles_h=ba.tiles_h))
        indexed, ncol, capped = self._source_info(ba)
        origin = label('bgedit.indexed_original_palette') if indexed else "inferred"
        ncol_s = "256+" if capped else str(ncol)
        lines.append(label('bgedit.source_origin_ncol_s_colors', origin=origin, ncol_s=ncol_s))
        if ba.mode == "bitmap":
            lines.append(label('bgedit.mode_4_full_screen_no_tiles'))
            lines.append(label('bgedit.palette_256_colors_1'))
        else:
            budget = 256 if ba.bpp == 8 else 512
            lines.append(label('bgedit.unique_tiles_value_budget_bpp_bpp', value=len(ba.effective_tileset()), budget=budget, bpp=ba.bpp))
            lines.append(label('bgedit.palette_256_colors_1') if ba.bpp == 8
                         else label('bgedit.palettes_value_16', value=len(ba.palettes)))
        lines += self._kind_info_lines(ba)
        return lines

    def _kind_info_lines(self, ba) -> list:
        """Ce que le TYPE ajoute à la description. Les grandeurs dérivées vivent
        ici plutôt que dans un champ grisé de l'inspecteur : elles se recalculent
        à chaque frappe, et un champ qu'on ne peut pas éditer n'a rien à faire
        au milieu de ceux qu'on édite."""
        if ba.kind == KIND_UI:
            if ba.ui_role != UI_ROLE_NINE:
                return [label('bgedit.ui_plain_info')]
            l, r, t, b = ba.slice_margins()
            tl, tr, tt, tb = ba.slice_margins_tiles()
            return [label('bgedit.ui_nine_slice_margins_l_r_t_b', l=l, r=r, t=t, b=b),
                    label('bgedit.at_build_tl_tr_tt_tb_tiles', tl=tl, tr=tr, tt=tt, tb=tb)]
        if ba.kind == KIND_ANIMATED:
            cols, rows = ba.frame_grid()
            fw, fh = ba.frame_size()
            n = ba.frame_count()
            secs = ba.duration_frames() / 60.0
            return [label('bgedit.frames_n_cols_rows_grid_of_fw_fh', n=n, cols=cols, rows=rows, fw=fw, fh=fh),
                    label('bgedit.cycle_speed_ticks_frame_secs_2f_s', speed=ba.speed, secs=secs)
                    + ("" if ba.loop else label('bgedit.once'))]
        if ba.animations:
            n = len(ba.animations)
            return [label('bgedit.animations_placed_n', n=n)]
        return []

    def _source_info(self, ba) -> tuple[bool, int, bool]:
        """(indexed, n_colors, capped) du PNG source — mis en cache dans
        `ba.diagnostics` pour ne pas relire l'image à chaque sélection."""
        d = ba.diagnostics if isinstance(ba.diagnostics, dict) else {}
        if "src_indexed" in d and "src_colors" in d:
            return d["src_indexed"], d["src_colors"], bool(d.get("src_capped"))
        ap = self._png_path()
        if not ap or not ap.exists():
            return False, 0, False
        try:
            from core.bg_import import source_palette_info
            indexed, ncol, capped = source_palette_info(ap)
        except Exception:
            return False, 0, False
        if not isinstance(ba.diagnostics, dict):
            ba.diagnostics = {}
        ba.diagnostics.update(src_indexed=indexed, src_colors=ncol, src_capped=capped)
        return indexed, ncol, capped

    # ── Validation (non-bloquante) ────────────────────────────────

    def _diag_for(self, ba) -> dict:
        """Diagnostics de compression : depuis l'asset, sinon calculés à la volée
        pour les fonds importés avant le validateur (mémorisés sur l'asset)."""
        if not ba:
            return {}
        if ba.diagnostics:
            return ba.diagnostics
        ap = self._png_path()
        if ap and ap.exists():
            try:
                from core.bg_import import analyze_background_source, prepare_source
                ba.diagnostics = analyze_background_source(
                    prepare_source(ap, **ba.import_prep()),
                    method=ba.quantize_method)
            except Exception:
                ba.diagnostics = {}
        return ba.diagnostics or {}

    def _kind_validation_lines(self, ba) -> list:
        """Alertes que le TYPE ajoute — toutes non bloquantes, et toutes portant
        sur un écart entre ce que l'auteur a réglé et ce que le matériel rendra."""
        warn, err = C.ACCENT_YLW, C.ACCENT_RED
        out: list = []
        if ba.kind in (KIND_UI, KIND_ANIMATED) and ba.mode == "bitmap":
            out.append((label('bgedit.bitmap_needs_tiles', value=ba.kind_label().lower()), err))
            return out
        if ba.kind == KIND_UI and ba.ui_role == UI_ROLE_NINE:
            odd = [n for n, m in zip("LRTB", ba.slice_margins()) if m % 8]
            if odd:
                out.append((label('bgedit.margin_rounding', margins="/".join(odd)), warn))
            l, r, t, b = ba.slice_margins()
            iw, ih = ba.pixel_size()
            if iw and (l + r > iw or t + b > ih):
                out.append((label('bgedit.margins_overlap'), warn))
        if ba.kind == KIND_ANIMATED:
            if ba.frame_count() <= 0:
                out.append((label('bgedit.frame_too_large'), err))
            elif not ba.frame_grid_is_exact():
                cols, rows = ba.frame_grid()
                fw, fh = ba.frame_size()
                iw, ih = ba.pixel_size()
                out.append((label('bgedit.iw_ih_not_divisible_by_fw_fh_value', iw=iw, ih=ih, fw=fw, fh=fh, value=iw - cols * fw, value_2=ih - rows * fh), warn))
        return out

    def _compression_lines(self, ba) -> list:
        """Ce que l'encodage a dû sacrifier ou ne peut pas contenir, `(texte, couleur)` : tuiles à plus de 15
        couleurs, palettes fusionnées, couleurs réduites en 8bpp, budget de tuiles dépassé. C'est exactement ce que
        la boîte de compression sait régler ; la géométrie (multiple de 8) et le type du fond n'en font pas partie."""
        if not ba or not (ba.tileset or ba.bitmap):
            return []
        return self._compression_lines_from(ba.mode, ba.bpp, self._diag_for(ba),
                                            len(ba.effective_tileset()), len(ba.palettes))

    @staticmethod
    def _compression_lines_from(mode: str, bpp: int, diag: dict, tiles: int, palettes: int) -> list:
        """Les mêmes constats, d'après des mesures et non d'après un fond : celui qui est compressé, ou le résultat d'un
        aperçu pas encore appliqué — les deux disent donc exactement la même chose."""
        warn, err = C.ACCENT_YLW, C.ACCENT_RED
        lines: list = []
        if mode == "bitmap":
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append((label('bgedit.gt_256_colors_reduced_to_256_lossy'), warn))
            return lines
        if bpp == 8:
            # 8bpp : une seule palette de 256 ; perte si le source en avait plus.
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append((label('bgedit.reduced_256_8bpp'), warn))
            budget = 256
        else:
            mtc = diag.get("max_tile_colors", 0)
            if mtc > 15:
                n = diag.get("tiles_reduced", 0)
                lines.append((label('bgedit.n_tile_s_gt_15_colors_max_mtc', n=n, mtc=mtc), warn))
            pre = diag.get("pre_merge_palettes")
            if pre and pre > 16:
                lines.append((label('bgedit.palettes_merged', pre=pre, value=palettes), warn))
            budget = 512
        if tiles > budget:
            lines.append((label('bgedit.tiles_exceed_vram', value=tiles, bud=budget, bpp=bpp), err))
        return lines

    def _validation_lines(self, ba) -> list:
        if not ba or not (ba.tileset or ba.bitmap):
            return [(label('bgedit.compression_failed'), C.ACCENT_RED)]
        # L'overlay du canvas est sombre dans TOUS les thèmes : le « ok » ne peut
        # pas suivre TEXT_HI (foncé en thème clair), il reste blanc.
        warn, err, ok = C.ACCENT_YLW, C.ACCENT_RED, "#ffffff"
        kind_lines = self._kind_validation_lines(ba)
        if ba.mode == "bitmap":
            lines: list = self._compression_lines(ba)
            if not lines and not kind_lines:
                lines.append((label('bgedit.bitmap_ok'), ok))
            return kind_lines + lines
        diag = self._diag_for(ba)
        lines: list = []
        if diag and not diag.get("multiple_of_8", True):
            w, h = diag.get("src_w"), diag.get("src_h")
            lines.append((label('bgedit.w_h_px_not_a_multiple_of_8', w=w, h=h, value=ba.tiles_w * 8, value_2=ba.tiles_h * 8), warn))
        lines += self._compression_lines(ba)
        if not lines and not kind_lines:
            lines.append((label('bgedit.compat_ok', bpp=ba.bpp), ok))
        # Les alertes du TYPE d'abord : elles portent sur un réglage que l'auteur
        # vient de poser, celles de la compression sur ce que le PNG impose.
        return kind_lines + lines

    # ── Section PALETTES ──────────────────────────────────────────

    def refresh_palette_catalog(self):
        """Re-lit le catalogue de palettes du projet dans la grille — appelé
        quand l'écran redevient visible, une palette ayant pu changer dans
        l'écran Palettes entre-temps."""
        self._reload_palettes()

    def _reload_palettes(self, select: int = 0):
        # Grille unifiée : palettes dérivées grisées/overridables + palettes
        # ajoutées du catalogue. La palette de PEINTURE active vit désormais dans
        # la bande en haut du canvas (rebâtie via palettes_changed → canvas.reload).
        # `select` est conservé pour la compat d'appel mais n'est plus consommé ici.
        read_only = bool(self._ba and (self._ba.mode == "bitmap" or self._ba.bpp == 8))
        view = background_palette_view(self._ba, read_only=read_only)
        catalog = list(self._project.palettes) if self._project else []
        self._pal_grid.load(view, catalog)
        self._btn_extract.setEnabled(bool(self._ba and self._ba.palettes))
        self._emit_overlays()

    def _refresh_pal_count(self):
        self._emit_overlays()

    def _persist_bg(self):
        # Un champ qu'on tourne (découpe, taille de frame, vitesse, placement) passe ici à chaque cran : le fichier
        # s'écrit après un silence (cf. `ui/common/deferred_writes.py`) ; le canvas de scène, lui, suit tout de suite.
        if self._project and self._ba:
            schedule_save(self._project.backgrounds, self._ba)
            get_dispatcher().notify_background_changed(self._ba)

    def _on_pal_add(self, name: str):
        """« + » : ajoute une palette du catalogue (banque `name`)."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        idx = self._ba.add_palette_ref(name, bank.colors)       # une RÉFÉRENCE au catalogue, jamais une copie
        if idx < 0:
            QMessageBox.warning(self, label("bgedit.limit_title"),
                                label("bgedit.limit_text"))
            return
        self._persist_bg()
        self._reload_palettes()
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_pal_replace(self, idx: int, name: str):
        """Remplace une palette AJOUTÉE (index réel `idx`) par la banque `name`."""
        if not self._ba or not self._project or not (0 <= idx < len(self._ba.palettes)):
            return
        bank = self._project.get_palette(name)
        if not bank or not self._ba.replace_added_palette(idx, name, bank.colors):
            return
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_override(self, entry, name: str):
        """Override une palette DÉRIVÉE (grisée) par la banque catalogue `name` :
        ses couleurs effectives sont remplacées, l'origine PNG reste restaurable."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        self._ba.override_palette(entry.idx, name, bank.colors)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_restore(self, entry):
        """Restaure une palette dérivée overridée à ses couleurs PNG d'origine."""
        if not self._ba:
            return
        self._ba.restore_palette(entry.idx)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_remove(self, idx: int):
        """Retire une palette AJOUTÉE (index réel `idx`). Les tuiles qui la
        référencent retombent sur la palette 0."""
        if not self._ba or not (0 <= idx < len(self._ba.palettes)) or len(self._ba.palettes) <= 1:
            return
        if QMessageBox.question(
            self, label("bgedit.del_pal_title"),
            label("bgedit.del_pal_text", idx=idx),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._ba.remove_palette(idx)
        self._persist_bg()
        self._reload_palettes()
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_restore(self):
        if not self._project or not self._ba:
            return
        if QMessageBox.question(
            self, label("bgedit.restore_dialog_title"),
            label("bgedit.restore_dialog_text"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        if not self._ba.asset:
            # Fond sans image : la condition initiale est la toile vierge — on ne garde ni peinture ni repeint.
            self._ba.tile_palette_overrides = {}
            self._ba.tile_paint = {}
            self._persist_bg()
            self.changed.emit()   # le canvas se relit (`changed` → `canvas.reload`)
            self._emit_overlays()
            return
        png = self._png_path()
        if not png or not png.exists():
            QMessageBox.warning(self, label("bgedit.restore_no_png_title"),
                                label("bgedit.restore_no_png_text"))
            return
        # Purge l'inpainting et la peinture ; palettes/tileset/tilemap sont régénérés par la
        # recompression (hors-thread) depuis le PNG, dans le mode courant. Le recadrage et la
        # taille préparée sont aussi remis à None : « original » = la source entière, à sa taille.
        self._ba.tile_palette_overrides = {}
        self._ba.tile_paint = {}
        self._ba.added_palettes, self._ba.palette_overrides = [], {}     # « original » : les palettes repartent du PNG
        self.restore_requested.emit()

    def _on_rename(self, new_name: str):
        if self._blocking or not self._ba or not self._project:
            return
        new_name = new_name.strip()
        if not new_name or new_name == self._ba.name:
            return
        if self._project.get_background(new_name):
            QMessageBox.warning(self, label("bgedit.name_used_title"),
                                label("bgedit.name_used_text", name=new_name))
            self._header.set_name(self._ba.name)
            return
        with get_dispatcher().suspended():
            self._project.rename_background(self._ba, new_name)
        self._header.set_name(self._ba.name)
        self.renamed.emit()

    def _png_path(self):
        if not (self._project and self._ba and self._ba.asset):
            return None
        return self._project.background_image_path(self._ba)

    def _refresh_png_buttons(self):
        from core.bg_bake import can_bake
        ba = self._ba
        self._btn_save_png.setEnabled(can_bake(ba))
        self._btn_export_png.setEnabled(bool(ba and (ba.tileset or ba.bitmap)))

    def _on_export_png(self):
        """Copie l'image telle qu'elle s'affiche où l'auteur veut. Le fond ne change pas.

        Un fond tuilé 4bpp sort en PNG indexé par banques (comme « Save as PNG »), les autres en RGBA."""
        from core.bg_bake import can_bake, render_rgba, save_indexed_png
        ba = self._ba
        if not ba or not (ba.tileset or ba.bitmap):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, label("bgedit.export_png"), f"{ba.name}.png", label("bgedit.export_png_filter"))
        if not path:
            return
        path = path if path.lower().endswith(".png") else path + ".png"
        if can_bake(ba):
            save_indexed_png(ba, path)
        else:
            render_rgba(ba).save(path)

    def _free_png_path(self):
        """`<nom>.png` dans le dossier affiché par l'onglet Disk, ou le premier `<nom>_N.png` libre : un « Save as »
        ne recouvre jamais la source d'un autre fond, ni l'ancienne source de celui-ci."""
        folder = import_folder(self._project)
        n, path = 1, folder / f"{self._ba.name}.png"
        while path.exists():
            n += 1
            path = folder / f"{self._ba.name}_{n}.png"
        return path

    def _on_save_png(self):
        """CUIT le fond — peinture, repeints de palette, tout — dans un PNG indexé du projet et en fait sa source.

        L'image est relue et recompressée AVANT que le fond ne bouge ; si le rendu relu n'est pas identique pixel
        pour pixel, rien ne change et le fichier est retiré. Les banques sont gardées (cf. `core.bg_bake`)."""
        from core.bg_bake import can_bake, render_rgba, save_indexed_png
        from core.bg_import import encode_by_mode, render_bg_preview
        from core.resources.asset_reconciliation import apply_bg_encoding, file_stamp
        ba, project = self._ba, self._project
        if not (project and can_bake(ba)):
            return
        if QMessageBox.question(
            self, label("bgedit.save_png"), label("bgedit.save_png_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        dst = self._free_png_path()
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            before = render_rgba(ba)
            save_indexed_png(ba, dst)
            encoded = encode_by_mode(dst, "tiled4", ba.quantize_method, ba.dither)
            after = render_bg_preview({"tiles_w": encoded["tiles_w"], "tiles_h": encoded["tiles_h"],
                                       "tileset": encoded["tileset"], "palettes": encoded["palettes"],
                                       "tilemap": encoded["tilemap"], "bpp": 4})
            identical = before.size == after.size and before.tobytes() == after.tobytes()
        except (ValueError, OSError):
            identical = False
        if not identical:
            dst.unlink(missing_ok=True)
            QMessageBox.warning(self, label("bgedit.save_png"), label("bgedit.save_png_failed"))
            return
        ba.asset = project.asset_rel(dst)
        ba.canvas_size = ba.image_pos = ba.image_size = None
        ba.tile_palette_overrides = {}
        ba.tile_paint = {}
        ba.added_palettes, ba.palette_overrides = [], {}          # cuits dans l'image : ses banques les portent maintenant
        ba.choose_layout("tiled4")
        apply_bg_encoding(ba, encoded)
        ba.source_stamp = file_stamp(dst)
        self._persist_bg()
        self.load(ba, project)
        self.changed.emit()
        self.palettes_changed.emit()

    def _on_extract_palette(self):
        """Promeut les sous-palettes déduites (`ba.palettes`) en PaletteBank
        partagées du catalogue projet, sous un nom stable dérivé du fond. Les
        palettes créées deviennent visibles/éditables depuis le Palette Editor
        et restent celles utilisées par ce fond (elles EN sont l'origine — le
        rendu du fond est inchangé). Une ré-extraction (après recompression)
        met à jour les mêmes banques."""
        if not self._project or not self._ba:
            return
        ba = self._ba
        pals = [list(p) for p in ba.palettes]
        if not pals:
            QMessageBox.information(
                self, label("bgedit.no_extract_title"),
                label("bgedit.no_extract_text"))
            return
        # 256 couleurs (une banque unique) en 8bpp / bitmap ; 16 en 4bpp tuilé.
        size = 256 if (ba.mode == "bitmap" or ba.bpp == 8) else 16
        single = len(pals) == 1
        created: list[str] = []
        for i, cols in enumerate(pals):
            name = f"pal_{ba.name}" if single else f"pal_{ba.name}_{i}"
            existing = self._project.palettes.get(name)
            if existing:
                # Ré-extraction : on écrase les couleurs de la banque déjà générée
                # (action explicite, régénération attendue — cf. Sprite Editor).
                existing.colors = list(cols)
                existing.size = size
                bank = existing
            else:
                bank = PaletteBank(name=name, colors=list(cols), size=size)
            # Passe par le dispatcher : persistance (watcher suspendu) + événement
            # « palettes_changed » pour rafraîchir le Palette Editor / les finders.
            get_dispatcher().save_palette(bank)
            created.append(bank.name)
        QMessageBox.information(
            self, label("bgedit.extracted_title"),
            label("bgedit.extracted_text", n=len(created), name=ba.name,
                  list="\n  ".join(created)))

    def _on_replace(self):
        if not self._project or not self._ba:
            return
        from ui.common.source_import import replace_source
        dst = replace_source(self._project, self._ba, label("bgedit.choose_image"), label('bgedit.images_png'), self)
        if dst is None:
            return
        self._ba.asset = self._project.asset_rel(dst)
        # Le canvas et la pose se disent pour l'ANCIENNE image : sur la nouvelle ils
        # désigneraient autre chose.
        self._ba.canvas_size = self._ba.image_pos = self._ba.image_size = None
        self._ba.palette_overrides = {}      # ils visaient les palettes dérivées de l'ANCIENNE image (les ajoutées restent)
        # Ré-auto-détecter le mode pour la nouvelle image (pivot indexé/non-indexé).
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, label("bgedit.import_title"), d["warning"])
        except Exception:
            token = self._cur_mode_token()
        self.recompress_requested.emit(self._ba, dst, token, self._ba.dither)


# ── Écran ───────────────────────────────────────────────────────────────────

class BackgroundEditorScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project = None
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        # Trois sections, une par `kind` : chacune a son propre import (un PNG,
        # un cadre d'UI, une planche d'animation). Cf. ui/common/asset_kinds.py.
        self._finder = AssetFinder(
            label('bgedit.background_finder'),
            [BACKGROUNDS_SCENE, BACKGROUNDS_UI, BACKGROUNDS_ANIM],
            min_width=180, max_width=420)
        self._canvas = BgInpaintCanvas()
        self._props = BgPropertiesPanel()
        self.body = ThreeColumnBody(self._finder, self._canvas, self._props,
                                    sizes=(240, 800, 300))
        root.addWidget(self.body)

        self._finder.selected.connect(lambda _kind, ba: self._on_selected(ba))
        self._finder.add_requested.connect(
            lambda section: self._on_add(_KIND_OF_LABEL[section]))
        self._props.changed.connect(self._canvas.reload)
        self._props.renamed.connect(self._on_renamed)
        # Mutation de la liste des palettes → re-render du canvas (sa bande de
        # peinture en tête se reconstruit alors depuis ba.palettes).
        self._props.palettes_changed.connect(self._canvas.reload)
        # Type changé : l'asset passe d'une section du finder à l'autre, et le
        # canvas change ce qu'il superpose (guides de coupe / grille de frames).
        self._props.kind_changed.connect(self._on_kind_changed)
        # Découpe (marges de coupe, taille de frame, vitesse) → le canvas
        # redessine ses guides et rejoue l'animation au nouveau rythme.
        self._props.geometry_changed.connect(self._canvas.reload_geometry)
        # Chemin INVERSE : un guide glissé au canvas écrit le modèle, l'inspecteur
        # ne fait que réaligner ses champs (cf. set_slice_margins).
        self._canvas.slices_dragged.connect(self._props.set_slice_margins)
        self._canvas.placements_changed.connect(self._on_placements_changed)
        # Sélection d'une copie posée → section PLACEMENT de l'inspecteur (même
        # bus que le reste : c'est la sélection qui décide du contexte).
        self._canvas.placement_selected.connect(self._props.set_placement)
        # Chemin inverse : régler la cadence ou l'image de départ d'une copie
        # doit se voir tout de suite — c'est la seule raison de la régler ici
        # plutôt que dans un fichier.
        self._props.placement_changed.connect(self._canvas.reload_geometry)
        # Infos read-only + warnings → overlays du canvas (bas-gauche / haut-droite).
        self._props.overlays_changed.connect(self._canvas.set_overlays)
        # (Re)compression demandée par l'inspecteur (algo / remplacer / restaurer)
        # → exécutée hors-thread par l'écran.
        self._props.recompress_requested.connect(self._on_recompress)
        self._props.restore_requested.connect(lambda: self._on_prepare(
            {"canvas": None, "pos": None, "size": None, "mirror": (None, None, False, False)}))
        # Poser l'image dans son canvas / miroir → même worker.
        self._canvas.prepare_requested.connect(self._on_prepare)
        # La carte Canvas de l'inspecteur et le mode Canvas du canvas central se suivent dans les deux sens.
        self._canvas.canvas_state.connect(self._props.show_canvas_state)
        self._props.canvas_edited.connect(self._canvas.edit_canvas)
        self._props.canvas_fit_requested.connect(self._canvas.fit_canvas)
        self._props.layout_shown.connect(self._canvas.set_shown_layout)
        # Les réglages de compression, après leur pause : le service encode tout seul quand c'est bon marché ; le bouton
        # « Run encoding » (ligne d'état du canvas) l'encode quand c'est cher.
        self._canvas.run_encoding_requested.connect(self._on_run_encoding)
        self._props.adjust_preview_requested.connect(self._on_adjust_preview)
        self._props.preview_requested.connect(self._on_encoding_wanted)

        # UN service d'encodage pour tout : gestes, curseurs, bouton, import (cf. `background_encoding`). Étapes lourdes mais
        # indépendantes des curseurs palettes/cible : image préparée et couleurs par tuile — son cache d'étage est partagé.
        from core.bg_import import BackgroundWorkCache
        self._encode_work_cache = BackgroundWorkCache()
        self._encoding = BackgroundEncodingService(commit=self._commit_job, work_cache=self._encode_work_cache,
                                                   parent=self)
        self._encoding.state_changed.connect(self._on_encoding_state)
        self._encoding.failed.connect(self._on_encoding_failed)
        self._encoding_errors: dict = {}      # id du fond -> dernier message d'échec

    def load_project(self, project):
        if project is not self._project:
            self._encoding.cancel_all()
            self._encoding_errors.clear()
        self._project = project
        self._finder.load_project(project)
        self._refresh_finder()

    def refresh(self):
        """Re-dérive à la revisite de l'écran — appelé au centre par
        `Window._show_screen` (chantier « L'écran resynchronisé à sa revisite »).
        Une palette a pu être ajoutée, renommée ou retirée dans l'écran Palettes
        depuis la dernière visite ; sans cela la grille « + du catalogue » restait
        figée sur d'anciens noms. Bon marché : on relit `project.palettes` (déjà
        en mémoire), pas le PNG du fond."""
        if self._project is not None:
            self._props.refresh_palette_catalog()

    def select_background(self, name: str):
        """Ouvre le fond `name` — navigation entrante depuis un autre écran
        (ex. carte « Utilisations » du Palette Editor)."""
        self._refresh_finder(select=name)

    def _refresh_finder(self, select: str = None):
        """Repeuple les trois sections et met à l'écran le fond `select` — ou le
        premier trouvé, à défaut. La sélection est posée SIGNAUX COUPÉS puis
        notifiée à la main : `select()` ne réémet rien si la ligne était déjà
        courante, alors que l'appelant attend un rafraîchissement (renommage,
        recompression)."""
        self._finder.refresh()
        bgs = list(self._project.backgrounds) if self._project else []
        target = next((b for b in bgs if b.name == select), None)
        if target is None:
            target = bgs[0] if bgs else None
        if target is None:
            self._finder.clear_selection()
            self._on_selected(None)
            return
        self._finder.blockSignals(True)
        self._finder.select(_LABEL_OF_KIND.get(target.kind, ""), target)
        self._finder.blockSignals(False)
        self._on_selected(target)

    # ── Compression hors-thread ───────────────────────────────────

    def _commit_encoding(self, ba, c, used_prep: dict, used_comp, layout: str, method: str):
        """Un résultat de compression devient celui du fond : les RÉGLAGES qui l'ont produit (préparation, compression,
        layout, méthode) d'abord, puis le résultat, puis l'écriture. `apply_bg_encoding` ne range que le résultat."""
        from core.resources import asset_reconciliation
        ba.canvas_size, ba.image_pos, ba.image_size = used_prep["canvas"], used_prep["pos"], used_prep["size"]
        ba.adjust = used_prep["adjust"]
        ba.mirror_x, ba.mirror_y, ba.mirror_flip_x, ba.mirror_flip_y = used_prep["mirror"]
        ba.compression = used_comp
        ba.choose_layout(layout)
        ba.quantize_method = method
        asset_reconciliation.apply_bg_encoding(ba, c, asset_reconciliation.catalogue_lookup(self._project))
        with get_dispatcher().suspended():
            self._project.backgrounds.save(ba)
        get_dispatcher().notify_background_changed(ba)

    def _compress_async(self, ba, png_path, mode, method, dither, then=None, prep=None,
                        compression=None):
        """Compresse `png_path` dans un worker (mode token tiled4/tiled8/bitmap)
        puis applique le résultat à `ba` sur le thread UI. Non-bloquant.

        `prep` = nouvelle préparation de la source (recadrage/taille) ; elle n'est
        écrite sur `ba` qu'AVEC le résultat qui l'applique, jamais avant — une
        compression qui échoue ne laisse pas un fond réglé sur une géométrie que
        son encodage n'a pas. Sans `prep`, celle de `ba` est reprise telle quelle."""
        if not self._project or not png_path or not Path(png_path).exists():
            return
        job = EncodingJob(
            ba=ba, path=Path(png_path), token=mode, method=method or ba.quantize_method, dither=dither,
            prep={**ba.import_prep(), **(prep or {})},
            compression=compression if compression is not None else ba.compression)
        # Un geste (le canvas, l'import, « remplacer l'image ») : l'auteur l'a demandé, il part sans regarder le coût.
        self._encoding.request(job, immediate=True, then=then)

    def _commit_job(self, job: EncodingJob, result: dict) -> None:
        """Le service a un résultat qui correspond encore à ce qui est voulu : il devient celui du fond. Le dithering est un
        réglage, comme le reste : il se pose avec eux, avant le résultat."""
        job.ba.dither = job.dither
        self._commit_encoding(job.ba, result, job.prep, job.compression, job.token, job.method)

    def _on_encoding_state(self, ba) -> None:
        """Le service change d'état pour `ba` : la ligne d'état du canvas suit, pour le fond qu'on regarde."""
        if ba is not self._props._ba:
            return
        self._show_encoding_state(ba)

    def _show_encoding_state(self, ba) -> None:
        """Ligne d'état + image provisoire. Tant que le fond n'est pas à jour, le canvas montre l'image PRÉPARÉE de ce qui est
        voulu (badge « pas encore le rendu GBA ») au lieu d'un rendu qui n'est plus le bon ; à jour, le rendu reprend."""
        state = self._encoding.state(ba)
        job = self._encoding.wanted(ba)
        if state != EncodingState.FAILED:
            self._encoding_errors.pop(id(ba), None)
        self._canvas.set_encoding_state(state, mode=self._token_name(job.token if job else self._props._cur_mode_token()),
                                        message=self._encoding_errors.get(id(ba), ""),
                                        seconds=self._encoding.last_seconds(ba))
        if state != EncodingState.UP_TO_DATE and job is not None:
            self._show_prepared(job.prep, job.prep["adjust"], bitmap=job.token.startswith("bitmap"))
        elif state == EncodingState.UP_TO_DATE:
            self._canvas.set_adjust_preview(None)

    @staticmethod
    def _token_name(token: str) -> str:
        """Le layout voulu, en mots : « Tiled 4bpp », « Bitmap 8bpp »."""
        if token.startswith("tiled"):
            layout, depth = "tiled", (8 if token == "tiled8" else 4)
        else:
            layout, depth = "bitmap", (16 if token == "bitmap16" else 8)
        return f"{label('bgedit.' + layout)} {label('bgedit.d' + str(depth))}"

    def _on_encoding_failed(self, ba, message: str) -> None:
        """Un échec reste visible dans la ligne d'état, avec « Run encoding » pour le rejouer : pas de fenêtre."""
        self._encoding_errors[id(ba)] = message
        if ba is self._props._ba:
            self._show_encoding_state(ba)

    def _resync(self, ba) -> None:
        """Le fond vient d'être (re)compressé : l'inspecteur puis le canvas se relisent. Un seul chemin, pour qu'aucune fin de
        compression n'oublie la barre d'outils, les bandes de palettes ou les overlays (tout cela se resynchronise dans
        `BgInpaintCanvas.reload`)."""
        self._props.load(ba, self._project)
        self._canvas.reload()

    def _on_recompress(self, ba, png_path, mode, dither):
        self._compress_async(
            ba, png_path, mode, ba.quantize_method, dither,
            then=lambda: self._resync(ba))

    def _on_prepare(self, prep: dict):
        """Ce qui change dans la préparation de la source (cf. `BgInpaintCanvas.prepare_requested`) : le canvas, la pose
        de l'image et/ou le miroir. Même mode et même dithering, seule la source préparée change ; ce que `prep` ne
        dit pas reste ce que le fond a déjà."""
        ba = self._props._ba
        if not ba or not self._project or not ba.asset:
            return
        # Le layout CHOISI (en attente compris) : régler le canvas d'un fond qu'on vient de passer en tuilé le compresse en
        # tuilé, au lieu de forcer 240×160 d'un bitmap qui n'est plus voulu.
        token = self._props._axes_token(*self._props._shown_axes())
        self._compress_async(
            ba, self._project.background_image_path(ba), token,
            ba.quantize_method, ba.dither,
            then=lambda: self._resync(ba),
            prep=prep)

    def _job_from_settings(self, ba, settings: dict) -> EncodingJob:
        """Ce que l'inspecteur tient en réglage → un travail d'encodage. Le mode, la méthode, le dithering, la compression
        et les ajustements viennent du MÊME dictionnaire `settings()` ; le reste de la préparation est celui du fond."""
        return EncodingJob(
            ba=ba, path=self._project.background_image_path(ba), token=settings["token"], method=settings["method"],
            dither=settings["dither"], prep={**ba.import_prep(), "adjust": settings["adjust"]},
            compression=settings["compression"])

    def _on_encoding_wanted(self, settings) -> None:
        """Les réglages en attente de l'inspecteur, après leur pause : le service les encode tout seul quand c'est bon
        marché (le fond se met à jour sans geste), et les garde « en attente » sinon, pour « Recompute ». `None` : plus
        rien n'est en attente."""
        ba = self._props._ba
        if not ba or not self._project or not ba.asset:
            return
        if settings is None:
            self._encoding.withdraw(ba)
            self._show_encoding_state(ba)
            return
        self._encoding.request(self._job_from_settings(ba, settings), then=lambda: self._resync(ba),
                               then_key="resync")
        self._show_encoding_state(ba)

    def _on_run_encoding(self) -> None:
        """« Recompute » : encode les réglages affichés maintenant, même si c'est cher et même si le fond est à jour."""
        ba = self._props._ba
        if not ba or not self._project or not ba.asset:
            return
        self._encoding.request(self._job_from_settings(ba, self._props.settings()), immediate=True, force=True,
                               then=lambda: self._resync(ba), then_key="resync")
        self._show_encoding_state(ba)

    _PREVIEW_MAX = 640      # côté le plus long de l'image d'aperçu : assez pour juger, assez petit pour suivre un curseur

    def _on_adjust_preview(self, adjust):
        """Aperçu EN DIRECT des ajustements : l'image préparée (recadrée, redimensionnée), réglée, en couleurs — avant
        la réduction de couleurs et le découpage en tuiles. `None` : on revient au rendu compressé."""
        ba = self._props._ba
        if adjust is None or not ba or not self._project or not ba.asset:
            self._canvas.set_adjust_preview(None)
            return
        self._show_prepared(ba.import_prep(), adjust, bitmap=self._props._shown_axes()[0] == "bitmap")

    def _show_prepared(self, prep: dict, adjust, bitmap: bool = False) -> None:
        """Montre l'image préparée par `prep` (canvas, pose, taille, miroir), réglée par `adjust`. Un bitmap a un canvas
        fixe : c'est celui de son encodage."""
        ba = self._props._ba
        if not ba or not self._project or not ba.asset:
            self._canvas.set_adjust_preview(None)
            return
        from core.models.background import BITMAP_SIZE
        canvas = BITMAP_SIZE if bitmap else prep["canvas"]
        png = self._project.background_image_path(ba)
        key = (str(png), png.stat().st_mtime_ns if png.exists() else 0, canvas, prep["pos"], prep["size"], prep["mirror"])
        if getattr(self, "_preview_key", None) != key:
            from core.bg_import import prepare_source
            try:
                base = prepare_source(png, canvas, prep["pos"], prep["size"], mirror=prep["mirror"])
                base = base.copy()
                base.thumbnail((self._PREVIEW_MAX, self._PREVIEW_MAX))
            except (OSError, ValueError):
                self._canvas.set_adjust_preview(None)
                return
            self._preview_key, self._preview_base = key, base
        from core.bg_adjust import apply_adjust
        self._canvas.set_adjust_preview(apply_adjust(self._preview_base, adjust).convert("RGBA"))

    def _on_selected(self, ba):
        # Charger le canvas AVANT l'inspecteur : le canvas bâtit sa bande de
        # peinture depuis `ba` (palette active de peinture) ; l'inspecteur suit.
        self._canvas.load(self._project, ba)
        self._props.load(ba, self._project)
        if ba is not None:
            self._show_encoding_state(ba)
        else:
            self._canvas.set_encoding_state("none")

    def _on_renamed(self):
        # Renommage validé depuis l'en-tête de l'inspecteur : réaligner le finder
        # sur le nouveau nom (il émettra bg_selected → recharge preview + props).
        ba = self._props._ba
        if ba:
            self._refresh_finder(select=ba.name)

    def _on_kind_changed(self):
        ba = self._props._ba
        if ba:
            self._refresh_finder(select=ba.name)

    def _on_placements_changed(self):
        """Un fond animé posé, déplacé ou retiré : l'inspecteur n'en montre que
        le compte, mais c'est ce compte qui dit à l'auteur que son geste a pris."""
        self._props._emit_overlays()

    def _on_add(self, kind: str):
        """Le décor peut naître d'un PNG ou d'une image vide (un PNG transparent, créé à côté).

        Les deux autres sections gardent leur unique geste d'import : sans
        image, un cadre UI ou une planche animée ne porte aucune information
        utile. Le menu est donc limité à la section Backgrounds, là où un
        canvas tuilé vide a un sens.
        """
        if kind != KIND_SCENE:
            self._on_import(kind)
            return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        import_action = menu.addAction(label("bgedit.menu_import"))
        blank_action = menu.addAction(label("bgedit.menu_create_empty"))
        chosen = menu.exec(QCursor.pos())
        if chosen == import_action:
            self._on_import(kind)
        elif chosen == blank_action:
            self._create_blank_background()

    def _create_blank_background(self):
        """Crée une image vide (PNG indexé transparent 240 × 160, aux couleurs de la première palette du projet) dans
        le dossier affiché, puis un fond qui la pointe — le même chemin qu'un import. Annulable (Ctrl+Z)."""
        if not self._project:
            return
        from PIL import Image
        from core.models.gba_color import bgr555_to_rgb888
        from core.models.unique_name import unique_name
        folder = import_folder(self._project)
        taken = {ba.name for ba in self._project.backgrounds} | {p.stem for p in folder.glob("*.png")}
        name = unique_name("Background", taken)
        palette = next(iter(self._project.palettes), None)
        colors = list(palette.colors)[:16] if palette else [0x0000, 0x7FFF]
        colors += [0] * (16 - len(colors))
        image = Image.new("P", (240, 160), 0)
        image.putpalette([c for k in range(16) for c in (bgr555_to_rgb888(colors[k]) if k else (0, 0, 0))])
        path = folder / f"{name}.png"
        image.save(path, "PNG", transparency=0)
        # Peindre ne se fait que sur une palette AJOUTÉE (une référence au catalogue) : la première du projet, celle dont
        # l'image vide porte déjà les couleurs, est ajoutée d'office.
        self._import_png(path, KIND_SCENE, then_paint=True, paint_palette=palette.name if palette else None)

    def _on_import(self, kind: str = KIND_SCENE):
        if not self._project:
            return
        title = {KIND_SCENE: label("bgedit.import_scene"),
                 KIND_UI: label("bgedit.import_ui"),
                 KIND_ANIMATED: label("bgedit.import_anim")}.get(kind, label("bgedit.import_scene"))
        path, _ = QFileDialog.getOpenFileName(self, title, "", label('bgedit.images_png'))
        if not path:
            return
        from core import source_collisions
        from core.disk_commands import ImportFilesCmd
        folder = import_folder(self._project)
        if Path(path).parent.resolve() == folder.resolve():
            dst = Path(path)                                    # déjà dans le dossier affiché : rien à copier
        else:
            overwrite = False
            if source_collisions.collides(Path(path), folder):
                overwrite = ask_overwrite(self, [Path(path).name],
                                          source_collisions.citing(self._project, folder / Path(path).name))
                if overwrite is None:
                    return
            dst = source_collisions.destination(Path(path), folder, overwrite)
            get_history().push(ImportFilesCmd([(Path(path), dst)]))
        self._import_png(dst, kind)

    def _import_png(self, dst: Path, kind: str, then_paint: bool = False, paint_palette: Optional[str] = None):
        """Un PNG déjà dans le projet devient un fond rangé À CÔTÉ de lui, puis se compresse hors-thread.
        `paint_palette` : la banque du catalogue que le fond reçoit d'office comme palette ajoutée (une image vide, faite
        pour être peinte)."""
        ba = self._project.get_background(dst.stem)
        gesture = None
        if ba is None:
            from core import asset_creation
            # Sans encodage : il se fait plus bas, hors-thread. La commande n'est poussée qu'une fois le fond réglé.
            gesture = asset_creation.create_from_source(self._project, "backgrounds", [dst], defer_encoding=True)
            ba = gesture.items[0]
        # Le type vient du « + » sur lequel on a cliqué : la section où l'auteur
        # range l'image dit son emploi mieux que n'importe quelle heuristique
        # (rien dans les pixels ne distingue un cadre de dialogue d'un décor).
        ba.kind = kind
        if paint_palette and paint_palette not in ba.added_palettes:
            ba.added_palettes.append(paint_palette)      # ses couleurs se résolvent à la compression qui suit
        # Auto-détection unifiée (pivot indexé/non-indexé) : profondeur ← couleurs,
        # layout tuilé/bitmap ← unicité des tuiles.
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, label("bgedit.import_title"), d["warning"])
        except Exception:
            token = "tiled4"
        if kind != KIND_SCENE and token.startswith("bitmap"):
            # Un cadre et une planche de frames sont des TUILES : le Mode 4 n'a
            # pas de tilemap où répéter un bord ni où poser une frame. On garde
            # la profondeur détectée et on retombe sur le layout tuilé, plutôt
            # que d'importer un asset que rien ne saura dessiner.
            token = "tiled8"
        # Sélectionner immédiatement (canvas vide + « Compression… ») puis
        # compresser hors-thread — l'éditeur n'est jamais bloqué.
        if gesture is None:
            self._refresh_finder(select=ba.name)
        else:
            get_history().push(RefreshAfterCmd(gesture.command, lambda: self._after_creation_changed(ba)))
        self._compress_async(
            ba, dst, token, ba.quantize_method, ba.dither,
            then=lambda: self._after_import(ba, then_paint))

    def _after_creation_changed(self, ba) -> None:
        """Le fond importé vient d'être créé, annulé ou refait : le finder suit ; annulé, sa compression en cours ne valide rien
        (sinon elle réécrirait le fichier que l'annulation vient de retirer)."""
        present = ba in self._project.backgrounds
        if not present:
            self._encoding.cancel(ba)
        self._refresh_finder(select=ba.name if present else None)

    def _after_import(self, ba, then_paint: bool = False):
        """Réglages qui ne peuvent se poser qu'une fois la taille CONNUE — donc
        après la compression, qui est ce qui la fixe."""
        if ba.kind == KIND_ANIMATED and not (ba.frame_w or ba.frame_h):
            from core.models.background import guess_frame_size
            ba.frame_w, ba.frame_h = guess_frame_size(*ba.pixel_size())
            with get_dispatcher().suspended():
                self._project.backgrounds.save(ba)
        self._on_selected(ba)
        if then_paint:
            self._canvas.start_painting()      # une image vide ne sert qu'à être peinte
