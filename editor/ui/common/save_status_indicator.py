"""
ui/common/save_status_indicator.py — l'état d'enregistrement du projet, en haut à droite.

Un point de couleur et un mot : « Project saved » quand tout ce qui a été
modifié est sur le disque, « Unsaved changes » tant qu'une écriture différée
(debounce de l'inspecteur, nudge du canvas, frappe du Script Editor) n'est pas
partie. Le widget ne décide rien : la fenêtre lui dit dans quel état est le
projet (`set_saved`), il l'affiche.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from ui.common.labels import label
from ui.common.tooltip import tooltip
from ui.common.theme import C, T
from core.keybindings import get_keybindings


class SaveStatusIndicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFont(T.UI, T.MD))
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._saved: bool | None = None
        self.set_saved(True)

    def set_saved(self, saved: bool) -> None:
        if saved == self._saved:
            return
        self._saved = saved
        text, colour = (
            (label("win.save_state_saved"), C.TEXT_DIM) if saved
            else (label("win.save_state_unsaved"), C.ACCENT_WARM)
        )
        self.setText("● " + text)
        self.setStyleSheet(f"color:{colour}; padding:0 12px;")
        self.setToolTip(tooltip(
            title=text,
            shortcut="" if saved else get_keybindings().resolve("file.save"),
            body=label("win.save_state_saved_tip") if saved
            else label("win.save_state_unsaved_tip"),
        ))
