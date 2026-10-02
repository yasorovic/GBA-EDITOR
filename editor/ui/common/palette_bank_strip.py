"""editor/ui/common/palette_bank_strip.py — bandeau flottant de sélection de
palette active (banque de peinture / aperçu).

Overlay bas-centre à coins arrondis, pastilles cliquables ; vue pure — émet
`selected(id)`, le consommateur mute son propre modèle et repositionne le
widget lui-même (`move()` en réponse à resizeEvent, cf. les 3 consommateurs).
Partagé par le Scene Manager (peinture BackgroundInpainting par tuile), le
Sprite Editor et le Background Editor (palette active de preview/peinture).
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QSize, pyqtSignal

from ui.common.theme import T, C
from ui.common.palette_swatch import swatch_icon


class PaletteBankStrip(QFrame):
    """Bandeau flottant : pastilles de palettes. Clic = sélection active.

    `load(entries, active)` accepte `entries: list[(id, label, colors)]`.
    La sélection précédente est retrouvée par CONTENU de palette (pas par
    `id`) au rechargement suivant : un `id` peut désigner une palette
    différente après insertion/suppression dans la liste du consommateur
    (ex. BackgroundAsset.remove_palette décale les index). Sans ce repérage
    par contenu, la pastille en surbrillance et l'aperçu peint/teinté
    pourraient diverger silencieusement après une telle mutation."""

    selected = pyqtSignal(object)   # id de l'entrée sélectionnée (clic utilisateur uniquement)

    _ICON = 22

    def __init__(self, empty_hint: str = None, parent=None):
        if empty_hint is None:
            empty_hint = label('common.no_palette')
        super().__init__(parent)
        self._active = None
        self._btns: dict = {}
        self._colors: dict = {}   # id -> couleurs, pour le repérage par contenu
        self.setStyleSheet(f"""
            PaletteBankStrip {{ background:{C.BG_BASE}; border:1px solid {C.BORDER_MID};
                                border-radius:8px; }}
            QToolButton {{ border:1px solid {C.BORDER}; background:transparent;
                          border-radius:4px; padding:1px; }}
            QToolButton:hover   {{ border-color:{C.TEXT_MUTED}; }}
            QToolButton:checked {{ border:2px solid {C.ACCENT}; }}
        """)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 5, 6, 5)
        self._layout.setSpacing(4)
        self._hint = QLabel(empty_hint)
        self._hint.setFont(QFont(T.UI, T.SM))
        self._hint.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        self._layout.addWidget(self._hint)
        self.setVisible(False)

    def active(self):
        """Id de l'entrée actuellement sélectionnée (None si la bande est vide)."""
        return self._active

    def reflow(self):
        """Recale la taille du bandeau sur son contenu, de façon fiable.

        `adjustSize()` seul lit `sizeHint()`, qui peut être périmé/minimal tant
        que le layout n'a pas été activé — d'où le bug intermittent où le
        bandeau se « compresse » à la taille d'une seule pastille. Activer le
        layout d'abord force un calcul de géométrie synchrone et à jour."""
        self._layout.activate()
        self.adjustSize()

    def load(self, entries: list, active=None):
        """`entries` : list[(id, label, colors)]. `active` : repli si aucune
        palette précédemment active n'est retrouvée par contenu (ni au premier
        chargement) — sinon la 1re entrée."""
        prev_colors = self._colors.get(self._active) if self._active is not None else None
        for b in self._btns.values():
            b.setParent(None)
            b.deleteLater()
        self._btns.clear()
        self._colors = {id_: list(colors) for id_, _label, colors in entries}
        self._hint.setVisible(not entries)

        resolved = active
        if prev_colors is not None:
            match = next((i for i, c in self._colors.items() if c == prev_colors), None)
            if match is not None:
                resolved = match
        if resolved not in self._colors:
            resolved = next(iter(self._colors), None)
        self._active = resolved

        for id_, entry_label, colors in entries:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setIcon(swatch_icon(list(colors), self._ICON))
            btn.setIconSize(QSize(self._ICON, self._ICON))
            btn.setFixedSize(30, 30)
            btn.setToolTip(tooltip(
                title=label("palstrip.select_title", name=entry_label)))
            btn.setChecked(id_ == self._active)
            btn.clicked.connect(lambda _c=False, i=id_: self._select(i))
            self._layout.addWidget(btn)
            self._btns[id_] = btn
        self.reflow()

    def _select(self, id_):
        if id_ == self._active:
            return
        self._active = id_
        for i, b in self._btns.items():
            b.setChecked(i == id_)
        self.selected.emit(id_)
