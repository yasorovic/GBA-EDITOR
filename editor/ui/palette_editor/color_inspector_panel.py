"""ui/palette_editor/color_inspector_panel.py — panneau droit : édition de la couleur active.

Vue PURE sur une seule couleur BGR555 : roue chromatique, hex, sliders RGB
(0-31, natif GBA) et TSL dérivé. Ne connaît ni le projet ni la banque — elle
reçoit une valeur via `load_color()` et émet `color_changed` ; c'est la grille
(PaletteGridPanel) qui écrit dans la palette et gère l'historique.
"""
from __future__ import annotations

import colorsys
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSlider,
    QSpinBox, QLineEdit, QScrollArea, QAbstractSpinBox,
)
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import W, CollapsibleCard
from ui.common.labels import label

from core.models.gba_color import (
    bgr555_to_rgb888, bgr555_components, components_to_bgr555, rgb888_to_bgr555,
)
from .color_wheel import ColorTriangleWheel


def _rgb01(rgb01) -> str:
    """(r,g,b) 0-1 -> 'rgb(R,G,B)' 0-255 pour un stop de gradient QSS."""
    r, g, b = rgb01
    return f"rgb({round(r * 255)},{round(g * 255)},{round(b * 255)})"


def _grad_slider_qss(stops: list[str]) -> str:
    """Feuille de style d'un QSlider dont la rainure affiche le gradient
    `stops` (chaînes 'rgb(...)') — simule la couleur résultante le long du
    slider. Poignée sobre lisible sur n'importe quel fond."""
    n = len(stops)
    grad_stops = ", ".join(
        f"stop:{(i / (n - 1)):.4f} {c}" for i, c in enumerate(stops)
    )
    return (
        "QSlider::groove:horizontal{height:12px;border-radius:6px;"
        f"border:1px solid {C.BORDER_MID};"
        f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,{grad_stops});}}"
        "QSlider::handle:horizontal{width:8px;height:20px;margin:-5px 0;"
        "border-radius:3px;background:#f0f0f0;border:1px solid #101010;}"
        "QSlider::handle:horizontal:hover{background:#ffffff;}"
    )


class ColorInspectorPanel(QWidget):
    """Carte « inspecteur de couleur » ancrée à droite : header fixe
    (COULEUR · index) + corps défilant (roue, hex/BGR555, RGB, TSL). Largeur
    ajustable via la poignée du splitter (bornée pour rester lisible)."""

    color_changed        = pyqtSignal(int)   # BGR555 édité par l'utilisateur
    grid_focus_requested = pyqtSignal()      # Entrée dans le champ HEX → focus à la grille

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value: Optional[int] = None
        self._blocking = False
        self.setMinimumWidth(300)
        self.setMaximumWidth(480)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-left:1px solid {C.BORDER};")
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        _CENTER = Qt.AlignmentFlag.AlignHCenter

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card_hdr = QFrame()
        card_hdr.setFixedHeight(32)
        card_hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        chl = QHBoxLayout(card_hdr)
        chl.setContentsMargins(12, 0, 12, 0)
        self._color_hdr = QLabel(label("colins.color"))
        self._color_hdr.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._color_hdr.setStyleSheet(QSS.title_section())
        chl.addWidget(self._color_hdr)
        root.addWidget(card_hdr)

        # Corps défilant (QScrollArea) : plus aucun débordement quelle que soit
        # la hauteur / l'échelle HiDPI.
        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(QSS.scroll_area + QSS.scrollbar)
        root.addWidget(scroll, 1)

        editor = QWidget()
        editor.setStyleSheet("background:transparent;")
        el = QVBoxLayout(editor)
        el.setContentsMargins(12, 12, 12, 12)
        el.setSpacing(10)

        # ── 1. Roue chromatique (élément de sélection principal) ──────
        wheel_card = CollapsibleCard(label("colins.wheel"))
        self._wheel = ColorTriangleWheel()
        self._wheel.color_changed.connect(self._on_wheel_changed)
        wheel_card.body_layout.addWidget(self._wheel, alignment=_CENTER)

        # ── 2. Ligne d'identité : chip aperçu + HEX éditable + copie ;
        # BGR555 natif GBA (ce qui finit en ROM) + badge « snap » (hex ajusté
        # à la grille 15 bits) dessous. ──────────────────────────────
        ident = QHBoxLayout()
        ident.setContentsMargins(0, 0, 0, 0)
        ident.setSpacing(10)

        self._preview = QLabel()
        self._preview.setFixedSize(44, 44)
        self._preview.setStyleSheet(f"border:1px solid {C.BORDER_MID}; border-radius:4px;")
        ident.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignTop)

        ident_col = QVBoxLayout()
        ident_col.setContentsMargins(0, 0, 0, 0)
        ident_col.setSpacing(6)

        hex_row = QHBoxLayout()
        hex_row.setContentsMargins(0, 0, 0, 0)
        hex_row.setSpacing(6)
        _LBL_W = 64                       # large assez pour « BGR555 » non tronqué
        hex_lab = QLabel("HEX")
        hex_lab.setFixedWidth(_LBL_W)
        hex_lab.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        hex_lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        hex_row.addWidget(hex_lab)
        self._hex = QLineEdit()
        self._hex.setMaxLength(7)
        self._hex.setFont(QFont(T.MONO, T.MD))
        self._hex.setStyleSheet(QSS.lineedit)
        self._hex.editingFinished.connect(self._on_hex_changed)
        # Entrée valide ET rend le focus à la grille → les flèches reprennent.
        self._hex.returnPressed.connect(self.grid_focus_requested.emit)
        hex_row.addWidget(self._hex, 1)
        btn_copy = W.btn_ghost(label("common.copy"))   # libellé explicite (⧉ était incompris)
        btn_copy.setToolTip(label("colins.copy_tip"))
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_color)
        hex_row.addWidget(btn_copy)
        ident_col.addLayout(hex_row)

        bgr_row = QHBoxLayout()
        bgr_row.setContentsMargins(0, 0, 0, 0)
        bgr_row.setSpacing(6)
        bgr_lab = QLabel("BGR555")
        bgr_lab.setFixedWidth(_LBL_W)
        bgr_lab.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        bgr_lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        bgr_row.addWidget(bgr_lab)
        self._bgr = QLabel("—")
        self._bgr.setFont(QFont(T.MONO, T.MD))
        self._bgr.setStyleSheet(f"color:{C.TEXT_NORM};")
        bgr_row.addWidget(self._bgr)
        self._snap = QLabel("")
        self._snap.setFont(QFont(T.MONO, T.SM))
        self._snap.setStyleSheet(f"color:{C.AXIS_X};")
        self._snap.setToolTip(label("colins.snap_tip"))
        self._snap.setVisible(False)
        bgr_row.addWidget(self._snap)
        bgr_row.addStretch(1)
        ident_col.addLayout(bgr_row)

        ident.addLayout(ident_col, 1)
        wheel_card.body_layout.addLayout(ident)
        el.addWidget(wheel_card)

        # ── 3. Sliders RGB (0-31, natif GBA), rainure dégradée ────────
        self._sliders: dict[str, QSlider] = {}
        self._spins: dict[str, QSpinBox] = {}
        self._hsb_sliders: dict[str, QSlider] = {}
        self._hsb_spins: dict[str, QSpinBox] = {}

        rgb_card = CollapsibleCard("RGB")
        for ch, chan_color in (("r", C.AXIS_X), ("g", C.POWER), ("b", C.AXIS_Y)):
            sl, sp = self._make_channel_row(
                rgb_card.body_layout, ch.upper(), chan_color, 0, 31,
                lambda v, ch=ch: self._on_rgb_changed(ch, v),
            )
            self._sliders[ch] = sl
            self._spins[ch] = sp
        el.addWidget(rgb_card)

        # ── 4. TSL (dérivé) — repliée par défaut : HEX + RGB suffisent le
        # plus souvent.
        hsb_card = CollapsibleCard("HSB", expanded=False)
        for ch, lbl, maxv, chan_color in (
            ("h", "H", 359, C.TEXT_DIM), ("s", "S", 100, C.TEXT_DIM), ("v", "L", 100, C.TEXT_DIM),
        ):
            sl, sp = self._make_channel_row(
                hsb_card.body_layout, lbl, chan_color, 0, maxv,
                lambda v, ch=ch: self._on_hsb_changed(ch, v),
            )
            self._hsb_sliders[ch] = sl
            self._hsb_spins[ch] = sp
        el.addWidget(hsb_card)
        el.addStretch(1)

        scroll.setWidget(editor)

    # ── Construction d'une ligne slider coloré + spinbox ───────────

    def _make_channel_row(self, parent_layout, label, color, min_v, max_v, on_change):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lab = QLabel(label)
        lab.setFixedWidth(18)
        lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lab.setStyleSheet(f"color:{color};")
        row.addWidget(lab)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(min_v, max_v)
        sl.setMinimumWidth(140)
        sl.valueChanged.connect(on_change)
        row.addWidget(sl, 1)
        sp = QSpinBox()
        sp.setRange(min_v, max_v)
        sp.setFixedWidth(44)
        sp.setFont(QFont(T.MONO, T.MD))
        sp.setStyleSheet(QSS.spinbox)
        # Pas de boutons ▲▼ : leur colonne dessine un trait vertical collé au
        # nombre (« petite barre »). Valeur éditable au clavier / molette / slider.
        sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp.valueChanged.connect(on_change)
        row.addWidget(sp)
        parent_layout.addLayout(row)
        return sl, sp

    # ── API panneau ───────────────────────────────────────────────

    def load_color(self, index: int, value: int):
        """Affiche le slot `index` et sa couleur `value` (BGR555)."""
        self._color_hdr.setText(label("colins.color_index", index=index,
                                      hex=f"{index:02X}"))
        self._load_channels(value)

    def focus_hex(self):
        """Place le curseur dans le champ HEX (Entrée depuis la grille)."""
        self._hex.setFocus()
        self._hex.selectAll()

    # ── Synchronisation des contrôles ─────────────────────────────

    def _load_channels(self, value: int):
        """Synchronise tous les contrôles (RGB, HSB, hex, preview, gradients)
        depuis une valeur BGR555, sans re-déclencher les handlers."""
        self._blocking = True
        self._value = value
        r, g, b = bgr555_components(value)                 # 0-31
        for ch, v in (("r", r), ("g", g), ("b", b)):
            self._sliders[ch].setValue(v)
            self._spins[ch].setValue(v)
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        for ch, v in (("h", round(h * 359)), ("s", round(s * 100)), ("v", round(l * 100))):
            self._hsb_sliders[ch].setValue(v)
            self._hsb_spins[ch].setValue(v)
        R, G, B = bgr555_to_rgb888(value)
        self._hex.setText(f"#{R:02X}{G:02X}{B:02X}")
        self._bgr.setText(f"0x{value & 0x7FFF:04X}")
        self._snap.setText("")            # valeur exacte : pas de snap par défaut
        self._snap.setVisible(False)      # vide → ne réserve aucune fente (barre parasite)
        self._update_preview(value)
        self._update_gradients(value)
        self._wheel.set_value(value)   # no-op pendant un drag de la roue
        self._blocking = False

    def _update_preview(self, value: int):
        r, g, b = bgr555_to_rgb888(value)
        self._preview.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID}; border-radius:6px;"
        )

    def _update_gradients(self, value: int):
        """Recolore chaque rainure de slider pour simuler la couleur obtenue
        le long du slider (les autres canaux fixés à la valeur courante)."""
        r, g, b = bgr555_components(value)
        R, G, B = bgr555_to_rgb888(value)
        self._sliders["r"].setStyleSheet(_grad_slider_qss([f"rgb(0,{G},{B})", f"rgb(255,{G},{B})"]))
        self._sliders["g"].setStyleSheet(_grad_slider_qss([f"rgb({R},0,{B})", f"rgb({R},255,{B})"]))
        self._sliders["b"].setStyleSheet(_grad_slider_qss([f"rgb({R},{G},0)", f"rgb({R},{G},255)"]))
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        self._hsb_sliders["h"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(i / 6, s, l)) for i in range(7)]))
        self._hsb_sliders["s"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(h, 0, l)), _rgb01(colorsys.hsv_to_rgb(h, 1, l))]))
        self._hsb_sliders["v"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(h, s, 0)), _rgb01(colorsys.hsv_to_rgb(h, s, 1))]))

    # ── Édition (roue, RGB, TSL, hex) ─────────────────────────────

    def _copy_color(self):
        if self._value is None:
            return
        r, g, b = bgr555_to_rgb888(self._value)
        QGuiApplication.clipboard().setText(f"#{r:02X}{g:02X}{b:02X}")

    def _on_wheel_changed(self, value: int):
        if self._blocking or self._value is None:
            return
        self.color_changed.emit(value)

    def _on_rgb_changed(self, ch: str, v: int):
        if self._blocking or self._value is None:
            return
        r, g, b = bgr555_components(self._value)
        r, g, b = {"r": (v, g, b), "g": (r, v, b), "b": (r, g, v)}[ch]
        self.color_changed.emit(components_to_bgr555(r, g, b))

    def _on_hsb_changed(self, ch: str, v: int):
        if self._blocking or self._value is None:
            return
        r, g, b = bgr555_components(self._value)
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        hsb = {"h": h * 359, "s": s * 100, "v": l * 100}
        hsb[ch] = v
        rr, gg, bb = colorsys.hsv_to_rgb(hsb["h"] / 359, hsb["s"] / 100, hsb["v"] / 100)
        self.color_changed.emit(
            components_to_bgr555(round(rr * 31), round(gg * 31), round(bb * 31)))

    def _on_hex_changed(self):
        cur = self._value
        if self._blocking or cur is None:
            return
        t = self._hex.text().strip().lstrip("#")
        if len(t) != 6:
            self._load_channels(cur)   # entrée invalide -> restaure
            return
        try:
            R, G, B = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        except ValueError:
            self._load_channels(cur)
            return
        new = rgb888_to_bgr555(R, G, B)
        self.color_changed.emit(new)
        # La grille a resynchronisé l'inspecteur (snap remis à ""). Si l'hex
        # 24 bits saisi ne retombe pas exactement sur la grille 15 bits, on le
        # signale.
        if bgr555_to_rgb888(new) != (R, G, B):
            self._snap.setText(label("colins.snap_badge"))
            self._snap.setVisible(True)
