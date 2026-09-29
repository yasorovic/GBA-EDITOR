"""ui/scene_manager/inspectors/bg_layer_row.py — ligne de calque de fond de
l'inspecteur de scène.

Un calque BG par ligne : sa vignette, son image, sa palette, son décalage de
parallaxe, et le glisser-déposer qui échange deux `bg_slot`.

Vient de `core/asset_manager.py`, supprimé : ce fichier était un module
d'INTERFACE rangé dans `core/`, donc la logique éditeur dépendait de l'UI. Les
trois autres classes qu'il portait (`AssignSlot`, `AssignPanel`,
`AssetManagerPanel`) n'étaient plus instanciées nulle part et sont parties avec
lui. Seule celle-ci vivait, et son unique client est l'inspecteur de scène —
d'où sa place ici."""
from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QToolButton,
    QDoubleSpinBox,
)
from PyQt6.QtGui import QPixmap, QFont, QDrag
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QMimeData

from ui.common.theme import C, T, QSS, tint
from ui.common.responsive import FlowLayout
from ui.common.widgets import W, ScriptPickerPopup
from ui.common.palette_swatch import bank_icon

LAYER_NAMES  = ["BG0", "BG1", "BG2", "BG3", "Sprite"]
LAYER_COLORS = ["#4caf78", "#5b9bd5", "#9b6bc4", "#c48b3c", "#e8a838"]
# Réordonnancement des lignes entre elles : échange de `bg_slot`.
MIME_BG_LAYER = "application/x-gba-bg-layer-slot"


class BgLayerRow(QFrame):
    """
    Ligne compacte : [○] [thumb/×] [BG0] [vitesse] [stretch] [× layer]
    - × sur la vignette → retire le background assigné
    - × à droite       → retire le layer entier
    - Vignette vide    → fond gris + icône selon l'état (vide / UI layer)
    """
    asset_changed    = pyqtSignal(int, str)
    speed_changed    = pyqtSignal(int, float)
    bound_toggled    = pyqtSignal(int)
    layer_removed    = pyqtSignal(int)
    pal_bank_changed   = pyqtSignal(int, str)  # slot_index, nom de la PaletteBank
    layer_swap_requested = pyqtSignal(int, int)  # (bg_slot source, bg_slot cible)
    visibility_toggled   = pyqtSignal(int, bool)  # (bg_slot, visible)
    inpaint_layer_selected = pyqtSignal(int)       # bg_slot du layer peint
    blend_role_changed   = pyqtSignal(int, str)    # (bg_slot, "" | "top" | "bottom")

    _SPEED_DEFAULTS = [4.0, 3.0, 1.0, 0.5]

    def __init__(self, slot_index: int, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self._color = LAYER_COLORS[slot_index]
        self._path: str = ""
        self._highlight = False
        self._is_ui_layer = False
        self._pal_banks: list = []
        self._bg_names: list = []
        self._drag_start = None
        self.setAcceptDrops(True)
        self._update_style()

        # Passe à la ligne quand l'inspecteur est étroit : la somme de ces
        # widgets à taille fixe imposait sa largeur à tout le panneau.
        row = FlowLayout(self, spacing=8)
        row.setContentsMargins(6, 4, 6, 4)

        # Bouton collision layer
        self._radio = QPushButton("○")
        self._radio.setFixedSize(22, 22)
        self._radio.setCheckable(False)
        self._radio.setFont(QFont(T.UI, 11))
        self._radio.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:transparent;border:none;padding:0;}}"
            f"QPushButton:hover{{color:{self._color};}}"
        )
        self._radio.setToolTip(label('bglayer.set_as_the_collision_layer'))
        self._radio.clicked.connect(lambda: self.bound_toggled.emit(self.slot_index))
        row.addWidget(self._radio)

        # Conteneur vignette + bouton × overlay
        thumb_container = QWidget()
        thumb_container.setFixedSize(48, 32)
        thumb_container.setStyleSheet("background:transparent;")

        self._thumb = QLabel(thumb_container)
        self._thumb.setGeometry(0, 0, 48, 32)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            f"background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};border-radius:2px;"
            f"color:{C.TEXT_MUTED};font-size:14px;"
        )
        self._thumb.setText("🖼")
        self._thumb.setToolTip(label('bglayer.click_or_drop_a_png'))
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.mousePressEvent = lambda e: self._open_dialog()

        self._btn_clear = QPushButton("×", thumb_container)
        self._btn_clear.setGeometry(32, 0, 16, 16)
        self._btn_clear.setFont(QFont(T.UI, 7, QFont.Weight.DemiBold))
        self._btn_clear.setStyleSheet(
            f"QPushButton{{background:{tint(C.ACCENT_RED, 0.18)};color:{C.ACCENT_RED};border:none;border-radius:2px;}}"
            f"QPushButton:hover{{background:{C.ACCENT_RED};color:#fff;}}"
        )
        self._btn_clear.setToolTip(label('bglayer.remove_this_background'))
        self._btn_clear.setVisible(False)
        self._btn_clear.clicked.connect(self._clear)

        row.addWidget(thumb_container)

        # Badge BG0 / BG1… — aussi poignée de glisser-déposer pour réordonner
        # les layers (échange de bg_slot, donc de priorité d'affichage : le
        # codegen émet `pri = bg` dans BGxCNT, et 0 est DEVANT sur GBA — BG0 est
        # donc au premier plan, BG3 au fond).
        badge = QLabel(LAYER_NAMES[slot_index])
        badge.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        badge.setStyleSheet(f"color:{self._color};background:transparent;")
        badge.setFixedWidth(34)
        badge.setCursor(Qt.CursorShape.OpenHandCursor)
        badge.setToolTip(label('bglayer.reorder_tip'))
        badge.mousePressEvent = self._badge_press
        badge.mouseMoveEvent = self._badge_move
        row.addWidget(badge)

        # Spinbox vitesse
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.0, 8.0)
        self._speed.setSingleStep(0.25)
        self._speed.setDecimals(2)
        self._speed.setValue(self._SPEED_DEFAULTS[slot_index])
        self._speed.setFont(QFont(T.MONO, T.SM))
        self._speed.setFixedWidth(68)
        self._speed.setStyleSheet(QSS.spinbox)
        self._speed.valueChanged.connect(
            lambda v: self.speed_changed.emit(self.slot_index, v)
        )
        row.addWidget(self._speed)

        # Icône palette — compacte (pas de ScriptSlot complet, pas la place
        # dans une rangée de 40px). Ouvre le même ScriptPickerPopup que
        # palette_picker_slot, câblé sur BackgroundLayer.pal_bank.
        self._pal_btn = QToolButton()
        self._pal_btn.setFixedSize(30, 30)
        self._pal_btn.setIconSize(QSize(24, 24))
        self._pal_btn.setToolTip(label('bglayer.choose_this_layer_s_palette'))
        self._pal_btn.setStyleSheet(
            "QToolButton{background:transparent;border:1px solid #333;"
            "border-radius:3px;padding:0;}"
            f"QToolButton:hover{{border-color:{self._color};}}"
        )
        self._pal_btn.clicked.connect(self._open_pal_picker)
        row.addWidget(self._pal_btn)

        # Rôle dans le mélange de couleurs — CYCLIQUE (aucun → dessus → dessous)
        # plutôt qu'un combo : la rangée fait 40 px et trois états se cliquent
        # plus vite qu'ils ne se déroulent. Caché tant que la scène n'a pas de
        # mode : un rôle sans mode ne veut rien dire (cf. models/scene.py).
        self._blend_role = ""
        self._blend_ui = "hidden"
        self._blend_btn = QToolButton()
        self._blend_btn.setFixedSize(24, 24)
        self._blend_btn.setIconSize(QSize(16, 16))
        self._blend_btn.setStyleSheet(
            "QToolButton{background:transparent;border:none;padding:0;}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-radius:3px;}}"
        )
        self._blend_btn.clicked.connect(self._cycle_blend_role)
        self._blend_btn.setVisible(False)
        self._sync_blend_btn()
        row.addWidget(self._blend_btn)

        row.add_trailing_break()

        # Sélecteur du layer peint par l'outil de peinture par palette (pinceau).
        from ui.common.icons import get as _ico
        self._inpaint_layer_btn = QToolButton()
        self._inpaint_layer_btn.setCheckable(True)
        self._inpaint_layer_btn.setFixedSize(22, 22)
        self._inpaint_layer_btn.setIconSize(QSize(16, 16))
        self._inpaint_layer_btn.setIcon(_ico("tool_inpaint_brush", C.TEXT_DIM, self._color))
        self._inpaint_layer_btn.setToolTip(label('bglayer.inpaint_tip'))
        self._inpaint_layer_btn.setStyleSheet(
            "QToolButton{background:transparent;border:none;padding:0;}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {self._color};"
            "border-radius:3px;}"
        )
        self._inpaint_layer_btn.clicked.connect(
            lambda: self.inpaint_layer_selected.emit(self.slot_index)
        )
        row.addWidget(self._inpaint_layer_btn)

        # Œil de visibilité (viewport éditeur).
        self._eye_btn = QToolButton()
        self._eye_btn.setFixedSize(22, 22)
        self._eye_btn.setIconSize(QSize(16, 16))
        self._visible = True
        self._eye_btn.setIcon(_ico("eye", C.TEXT_DIM, self._color))
        self._eye_btn.setToolTip(label('bglayer.visibility_tip'))
        self._eye_btn.setStyleSheet(
            "QToolButton{background:transparent;border:none;padding:0;}"
        )
        self._eye_btn.clicked.connect(self._toggle_visibility)
        row.addWidget(self._eye_btn)

        btn_remove = W.btn_danger("×")
        btn_remove.setFixedSize(22, 22)
        btn_remove.setToolTip(label('bglayer.remove_this_layer'))
        btn_remove.clicked.connect(lambda: self.layer_removed.emit(self.slot_index))
        row.addWidget(btn_remove)

    # ── Apparence ─────────────────────────────────────────────────

    _BLEND_ICONS = {"": "blend_off", "top": "blend_top", "bottom": "blend_bottom"}
    # Deux vocabulaires pour le même champ : celui de l'INTENTION quand la
    # scène est réglée par un effet, celui du REGISTRE quand elle est composée à
    # la main. Le mot « cible » n'a pas à remonter jusqu'à qui a juste choisi
    # « layer translucide » dans un menu.
    _BLEND_TIPS_SIMPLE = {
        "top":    'bglayer.through_tip',
        "bottom": 'bglayer.behind_tip',
    }
    _BLEND_TIPS_FULL = {
        "": 'bglayer.no_blend_tip',
        "top": 'bglayer.top_tip',
        "bottom": 'bglayer.bottom_tip',
    }

    # Ce que le bouton propose, piloté par l'effet de la scène :
    #   "hidden" — rien à choisir (aucun effet, ou fondu d'écran qui prend tout)
    #   "toggle" — devant ↔ derrière, DEUX états : en translucidité, un layer
    #              est soit celui qu'on voit à travers, soit ce qu'il y a
    #              derrière. Un troisième état « hors du mélange » n'existe pas
    #              dans cette intention, et le traverser au clic donnait un cran
    #              mort au milieu du geste.
    #   "full"   — les trois rôles du registre, pour un réglage composé à la main.
    def _sync_blend_btn(self):
        from ui.common.icons import get as _ico
        key = self._BLEND_ICONS.get(self._blend_role, "blend_off")
        active = self._blend_role != ""
        self._blend_btn.setIcon(_ico(key, self._color if active else C.TEXT_DIM,
                                     self._color))
        tips = (self._BLEND_TIPS_SIMPLE if self._blend_ui == "toggle"
                else self._BLEND_TIPS_FULL)
        self._blend_btn.setToolTip(label(tips[self._blend_role]) if self._blend_role in tips else "")

    def _cycle_blend_role(self):
        order = (["top", "bottom"] if self._blend_ui == "toggle"
                 else ["", "top", "bottom"])
        try:
            nxt = order[(order.index(self._blend_role) + 1) % len(order)]
        except ValueError:
            nxt = order[0]      # rôle hors du cycle courant : on y rentre
        self._blend_role = nxt
        self._sync_blend_btn()
        self.blend_role_changed.emit(self.slot_index, nxt)

    def set_blend_role(self, role: str):
        self._blend_role = role if role in ("", "top", "bottom") else ""
        self._sync_blend_btn()

    def set_blend_ui(self, ui_mode: str):
        """« hidden » | « toggle » | « full » — cf. le commentaire ci-dessus."""
        self._blend_ui = ui_mode if ui_mode in ("hidden", "toggle", "full") else "hidden"
        self._blend_btn.setVisible(self._blend_ui != "hidden")
        self._sync_blend_btn()

    # ── Apparence ─────────────────────────────────────────────────

    def _update_style(self):
        if self._highlight:
            self.setStyleSheet(
                f"BgLayerRow{{border:2px dashed {self._color};"
                f"background:{C.BG_SEL};border-radius:4px;}}"
            )
        else:
            self.setStyleSheet(
                f"BgLayerRow{{border:1px solid {C.BORDER_DARK};"
                f"border-radius:4px;background:{C.BG_PANEL};}}"
            )

    # ── Asset ─────────────────────────────────────────────────────

    def set_backgrounds(self, names, current: str = ""):
        """Fonds proposés au picker de ce layer.

        ``names`` est soit une liste figée, soit un CALLABLE qui la rend — le
        second n'est appelé qu'à l'ouverture du popup. La liste complète des
        fonds appartient à un catalogue différé (v0.24) : la résoudre à la
        construction de la ligne rechargerait tout le disque à l'ouverture du
        projet, alors que la ligne n'a besoin que de sa vignette (le fond
        courant, déjà préchargé). On ne matérialise donc le catalogue que si
        l'utilisateur déploie effectivement le choix."""
        self._bg_names = names

    def _open_dialog(self):
        """Choisit un BackgroundImage EXISTANT (assets/backgrounds/) — les images
        s'importent via le Background Editor, plus de QFileDialog Windows ici.
        Entrée « Vide » en tête pour un layer sans image (même contrat que
        « Sans palette » côté pal_bank, cf. ui/common/pickers.py)."""
        from ui.common.widgets import ScriptPickerPopup
        names = self._bg_names() if callable(self._bg_names) else self._bg_names
        entries = [(label('bglayer.empty_no_image'), "", None)]
        entries += [(n, n, None) for n in (names or [])]
        popup = ScriptPickerPopup(entries, self._color, parent=self, new_label=None)
        popup.picked.connect(lambda name: self.asset_changed.emit(self.slot_index, name))
        popup.show_below(self._thumb)

    def set_asset(self, path: str):
        self._path = path
        px = QPixmap(path)
        if not px.isNull():
            self._thumb.setPixmap(
                px.scaled(46, 30,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._thumb.setText("")
        self._btn_clear.setVisible(True)

    def clear_asset(self):
        self._path = ""
        self._thumb.setPixmap(QPixmap())
        self._thumb.setText("UI" if self._is_ui_layer else "🖼")
        self._btn_clear.setVisible(False)

    def set_ui_layer(self, is_ui: bool):
        self._is_ui_layer = is_ui
        if not self._path:
            self._thumb.setText("UI" if is_ui else "🖼")
        if is_ui:
            self._thumb.setStyleSheet(
                f"background:{C.BG_BASE};border:1px solid {C.BORDER_MID};border-radius:2px;"
                f"color:{C.TEXT_DIM};font-size:11px;font-weight:bold;"
            )
        else:
            self._thumb.setStyleSheet(
                f"background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};border-radius:2px;"
                f"color:{C.TEXT_MUTED};font-size:14px;"
            )

    def set_speed(self, value: float):
        self._speed.blockSignals(True)
        self._speed.setValue(value)
        self._speed.blockSignals(False)

    def set_pal_banks(self, banks: list, current_name: Optional[str]):
        """banks : PaletteBank actives de la scène (scene.active_bg_palettes,
        filtrées des slots vides/introuvables) ; current_name : nom résolu du
        slot actuel (BackgroundLayer.pal_bank), None si non résolvable —
        même contrat que component_editors/sprite.py pour Actor.pal_bank."""
        self._pal_banks = banks
        current = next((b for b in banks if b.name == current_name), None) if current_name else None
        if current:
            self._pal_btn.setIcon(bank_icon(current))
            self._pal_btn.setToolTip(label('bglayer.layer_palette_name', name=current.name))
        else:
            # « Sans palette » : couleurs d'origine du PNG (défaut) — icône
            # neutre plutôt qu'un bouton vide.
            from ui.common.icons import get as _ico
            self._pal_btn.setIcon(_ico("tool_palette", C.TEXT_DIM, self._color))
            self._pal_btn.setToolTip(label('bglayer.no_palette_tip'))

    def _open_pal_picker(self):
        from ui.common.pickers import PALETTE_NONE
        entries = [(label('bglayer.no_palette_png_colors'), PALETTE_NONE, None)]
        entries += [(bank.name, bank.name, bank_icon(bank)) for bank in self._pal_banks]
        popup = ScriptPickerPopup(entries, self._color, parent=self, new_label=None)
        popup.picked.connect(lambda name: self.pal_bank_changed.emit(self.slot_index, name))
        popup.show_below(self._pal_btn)

    def set_bound(self, checked: bool):
        if checked:
            self._radio.setText("●")
            self._radio.setStyleSheet(
                f"QPushButton{{color:{self._color};background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{self._color};}}"
            )
        else:
            self._radio.setText("○")
            self._radio.setStyleSheet(
                f"QPushButton{{color:{C.TEXT_MUTED};background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{self._color};}}"
            )

    def set_speed_visible(self, visible: bool):
        self._speed.setVisible(visible)

    # ── Visibilité viewport + cible de peinture ───────────────────

    def _toggle_visibility(self):
        self.set_visible_state(not self._visible)
        self.visibility_toggled.emit(self.slot_index, self._visible)

    def set_visible_state(self, visible: bool):
        """Reflète l'état de visibilité (icône œil ouvert/barré)."""
        from ui.common.icons import get as _ico
        self._visible = visible
        key = "eye" if visible else "eye_off"
        color = C.TEXT_DIM if visible else "#555"
        self._eye_btn.setIcon(_ico(key, color, self._color))

    def set_inpaint_layer(self, active: bool):
        """Marque ce layer comme cible active de l'outil de peinture."""
        self._inpaint_layer_btn.setChecked(active)

    def _clear(self):
        self.clear_asset()
        self.asset_changed.emit(self.slot_index, "")

    # ── Drag & drop — réordonnancement (échange de bg_slot/priorité) ──
    # Plus de drop de FICHIER ici : l'assignation d'une image se fait via le
    # picker de BackgroundImages (import au Background Editor). Le drag initié
    # depuis le badge BG0/BG1… sert à échanger la priorité de deux layers.

    def _badge_press(self, e):
        self._drag_start = e.position().toPoint()

    def _badge_move(self, e):
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._drag_start).manhattanLength() < 8:
            return
        self._drag_start = None
        drag = QDrag(self)
        md = QMimeData()
        md.setData(MIME_BG_LAYER, str(self.slot_index).encode("utf-8"))
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_BG_LAYER):
            self._highlight = True
            self._update_style()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight = False
        self._update_style()

    def dropEvent(self, event):
        self._highlight = False
        self._update_style()
        if not event.mimeData().hasFormat(MIME_BG_LAYER):
            return
        src = int(bytes(event.mimeData().data(MIME_BG_LAYER)).decode("utf-8"))
        if src != self.slot_index:
            self.layer_swap_requested.emit(src, self.slot_index)
        event.acceptProposedAction()
