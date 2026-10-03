"""
ui/common/logo.py — le logo Backstage, affiché par l'accueil et la fenêtre « À propos ».

Blanc sur le thème sombre, noir sur le clair. Le cadre du SVG porte une petite
marge : le logo ne touche pas les bords de son widget.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtSvgWidgets import QSvgWidget

from ui.common.theme import C

_LOGO_DIR   = Path(__file__).resolve().parent / "CustomIcons"
_LOGO_FILE  = _LOGO_DIR / ("Backstage_logo.svg" if C.IS_LIGHT else "Backstage_logo_white.svg")
_LOGO_RATIO = 274 / 566     # hauteur / largeur du viewBox du SVG (marge comprise)


class BackstageLogo(QSvgWidget):
    def __init__(self, width: int, parent=None):
        super().__init__(str(_LOGO_FILE), parent)
        self.setFixedSize(width, round(width * _LOGO_RATIO))
        self.setStyleSheet("background:transparent;")
