"""
ui/text_editor/glyph_sheet_panel.py — colonne centre (contexte Police) :
enveloppe scrollable de la planche + barre d'outils (fusion, re-découpe, zoom).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QSpinBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.backdrop_button import BackdropButton
from ui.text_editor.glyph_sheet import GlyphSheet


class GlyphSheetPanel(QWidget):
    """Enveloppe scrollable de la planche + barre d'outils.

    Ne décide rien : relaie les gestes de la planche vers l'écran (signaux
    `*_asked`), qui pousse les commandes.
    """

    glyph_selected = pyqtSignal(object)
    glyph_edited   = pyqtSignal(object, str, str)
    reslice_asked  = pyqtSignal(int, int)
    merge_asked    = pyqtSignal(list)
    selection_changed  = pyqtSignal(int, object)
    background_clicked = pyqtSignal()
    color_picked       = pyqtSignal(str, object)
    pick_ended         = pyqtSignal()

    _HINT_DEFAULT = "glsheet.hint_default"   # clé de libellé, résolue à l'usage

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._font = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.setSpacing(6)

        self._title = QLabel(label("glsheet.title"))
        self._title.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        self._title.setStyleSheet(QSS.title_panel)
        bl.addWidget(self._title)
        bl.addStretch()

        self._btn_merge = W.btn_ghost(label("glsheet.merge"))
        self._btn_merge.setFont(QFont(T.UI, T.XS))
        self._btn_merge.setToolTip(tooltip(title=label("glsheet.merge_title"), body=label("glsheet.merge_tip")))
        self._btn_merge.setEnabled(False)
        self._btn_merge.clicked.connect(self._ask_merge)
        bl.addWidget(self._btn_merge)

        # Correctif quand la cellule proposée à l'import est fausse (planche
        # irrégulière, marge) — cf. l'avertissement « vérifie la cellule ».
        lbl_cell = QLabel(label("glsheet.cell"))
        lbl_cell.setFont(QFont(T.UI, T.XS))
        lbl_cell.setStyleSheet(f"color:{C.TEXT_DIM};")
        bl.addWidget(lbl_cell)
        self._cw = QSpinBox(); self._ch = QSpinBox()
        for s in (self._cw, self._ch):
            s.setRange(1, 64); s.setFixedWidth(48)
            s.setFont(QFont(T.MONO, T.SM)); s.setStyleSheet(QSS.spinbox)
            bl.addWidget(s)
        self._btn_reslice = W.btn_ghost(label("glsheet.reslice"))
        self._btn_reslice.setFont(QFont(T.UI, T.XS))
        self._btn_reslice.setToolTip(tooltip(
            title=label("glsheet.reslice_title"), body=label("glsheet.reslice_tip"),
            warning=label("glsheet.reslice_warning"),
        ))
        self._btn_reslice.clicked.connect(
            lambda: self.reslice_asked.emit(self._cw.value(), self._ch.value()))
        bl.addWidget(self._btn_reslice)

        lbl_zoom = QLabel(label("glsheet.zoom"))
        lbl_zoom.setFont(QFont(T.UI, T.XS))
        lbl_zoom.setStyleSheet(f"color:{C.TEXT_DIM};")
        bl.addWidget(lbl_zoom)
        self._zoom = QSpinBox()
        self._zoom.setRange(GlyphSheet._MIN_ZOOM, GlyphSheet._MAX_ZOOM)
        self._zoom.setValue(6); self._zoom.setFixedWidth(48)
        self._zoom.setFont(QFont(T.MONO, T.SM)); self._zoom.setStyleSheet(QSS.spinbox)
        self._zoom.setToolTip(tooltip(title=label("glsheet.zoom")))
        bl.addWidget(self._zoom)
        root.addWidget(bar)

        self._scroll = QScrollArea()
        # La planche occupe toute la zone visible et centre son image
        # elle-même : la marge autour reste cliquable (clic « hors image »).
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
        self._sheet = GlyphSheet()
        self._scroll.setWidget(self._sheet)
        root.addWidget(self._scroll, 1)

        # Fond d'épreuve : posé DANS la planche, en bas à gauche — même widget et
        # même geste que l'aperçu écran. Une police sombre, une fois la
        # transparence active, se noie sinon dans le damier sombre.
        self._btn_bg = BackdropButton(self)
        self._btn_bg.changed.connect(self._apply_backdrop)

        self._hint = QLabel(label(self._HINT_DEFAULT))
        self._hint.setFont(QFont(T.UI, T.XS))
        self._hint.setStyleSheet(
            f"color:{C.TEXT_MUTED}; background:{C.BG_PANEL}; padding:4px 8px;"
            f"border-top:1px solid {C.BORDER_DARK};")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._zoom.valueChanged.connect(self._sheet.set_zoom)
        # La molette zoome aussi : le spinbox doit suivre, sinon il ment.
        self._sheet.zoom_changed.connect(self._sync_zoom_spin)
        self._sheet.selection_changed.connect(self._on_selection_changed)
        self._sheet.selection_changed.connect(self.selection_changed)
        self._sheet.background_clicked.connect(self.background_clicked)
        self._sheet.glyph_selected.connect(self.glyph_selected)
        self._sheet.glyph_edited.connect(self.glyph_edited)
        self._sheet.color_picked.connect(self.color_picked)
        self._sheet.pick_ended.connect(self.pick_ended)
        self._sheet.pick_ended.connect(lambda: self._set_hint(""))

    def resizeEvent(self, e):
        """Recale le bouton de fond d'épreuve en bas à gauche de la planche,
        au-dessus du bandeau d'aide."""
        super().resizeEvent(e)
        g = self._scroll.geometry()
        self._btn_bg.move(g.left() + 8, g.bottom() - self._btn_bg.height() - 8)
        self._btn_bg.raise_()

    def _apply_backdrop(self):
        self._sheet.set_backdrop(
            None if self._btn_bg.is_default() else self._btn_bg.color())

    # ── Pipette ───────────────────────────────────────────────────

    def begin_pick(self, role: str, name: str):
        """Arme la pipette et l'annonce dans le bandeau d'aide."""
        self._sheet.begin_pick(role)
        self._set_hint(label("glsheet.pick_hint", name=name))

    def refresh_keying(self):
        """Reconstruit la planche trouée (une couleur-clé a bougé)."""
        self._sheet.refresh_keying()

    def _set_hint(self, text: str):
        """Bandeau d'aide — vide = le message par défaut."""
        self._hint.setText(text or label(self._HINT_DEFAULT))

    def load(self, font, project):
        """Affiche `font` : titre, cellule courante et planche."""
        self._font = font
        self._blocking = True
        if font:
            self._cw.setValue(max(1, font.cell_w))
            self._ch.setValue(max(1, font.cell_h))
            self._title.setText(label("glsheet.sheet_name", name=font.name))
        else:
            self._title.setText(label("glsheet.title"))
        self._blocking = False
        self._sheet.load(font, project)

    def _on_selection_changed(self, n: int, rect):
        self._btn_merge.setEnabled(n > 1)

    def _ask_merge(self):
        idx = self._sheet.selected_indices()
        if len(idx) > 1:
            self.merge_asked.emit(idx)

    def _sync_zoom_spin(self, z: int):
        self._zoom.blockSignals(True)
        self._zoom.setValue(z)
        self._zoom.blockSignals(False)

    def select_glyph(self, glyph):
        """Resélectionne une case depuis l'extérieur (édition dans
        l'inspecteur) — garde le cadre de sélection cohérent."""
        f = self._font
        if f and glyph in f.glyphs:
            self._sheet.select_index(f.glyphs.index(glyph))

    def refresh(self):
        """Redessine la planche (les glyphes ont changé, pas la planche)."""
        self._sheet.update()
