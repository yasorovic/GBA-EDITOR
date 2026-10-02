"""
ui/common/backdrop_button.py — bouton « fond d'épreuve » : fait défiler une
liste de couleurs de fond pour LIRE un rendu (police claire sur sombre, police
sombre sur clair…).

Aide de lecture pure — ne touche ni au texte, ni à la ROM. Partagé par l'aperçu
écran du Text Editor et par la planche de glyphes, qui souffraient du même mal :
sur le fond sombre de l'éditeur, une police sombre disparaît.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QToolButton
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common import icons
from ui.common.theme import C
from ui.common.labels import label
from ui.common.tooltip import tooltip


# Fonds d'ÉPREUVE, pas le backdrop de la ROM. Du plus sombre au plus clair, plus
# un fond franc. (clé de nom affiché, couleur) — le nom est résolu à l'usage.
# Index 0 = fond de l'éditeur : le rendu « par défaut ».
BACKDROPS = (
    ("backdrop.editor",  C.BG_DEEP),
    ("backdrop.black",   "#000000"),
    ("backdrop.grey",    "#808080"),
    ("backdrop.white",   "#ffffff"),
    ("backdrop.magenta", "#ff00ff"),
)


class BackdropButton(QToolButton):
    """Petit bouton 32×32 qui fait défiler `BACKDROPS`.

    Émet `changed` à chaque cran ; `color()` donne la couleur courante et
    `is_default()` dit si l'on est resté sur le fond de l'éditeur.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, backdrops=BACKDROPS):
        super().__init__(parent)
        self._backdrops = backdrops
        self._index = 0
        self.setFixedSize(32, 32)
        self.setIconSize(self.size() * 0.7)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QToolButton{{background:{C.BG_PANEL}; border:1px solid {C.BORDER_MID};"
            f"border-radius:4px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER}; border-color:{C.ACCENT};}}"
        )
        self.clicked.connect(self._cycle)
        self._sync()

    def color(self) -> QColor:
        return QColor(self._backdrops[self._index][1])

    def is_default(self) -> bool:
        return self._index == 0

    def _cycle(self):
        self._index = (self._index + 1) % len(self._backdrops)
        self._sync()
        self.changed.emit()

    def _sync(self):
        name_key, _ = self._backdrops[self._index]
        nxt_key, _ = self._backdrops[(self._index + 1) % len(self._backdrops)]
        # Accentué dès qu'on n'est plus sur le fond de l'éditeur : ce qu'on
        # regarde n'est alors plus le rendu « par défaut ».
        self.setIcon(icons.get(
            "playback_contrast",
            C.TEXT_NORM if self._index == 0 else C.ACCENT))
        self.setToolTip(tooltip(
            title=label("backdrop.title"),
            body=label("backdrop.tip", name=label(name_key), next=label(nxt_key)),
            note=label("backdrop.note")))
