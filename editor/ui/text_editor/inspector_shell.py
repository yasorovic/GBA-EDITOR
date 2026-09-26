"""
ui/text_editor/inspector_shell.py — coquille commune aux deux inspecteurs.

Les deux contextes ne diffèrent que par la COULEUR du titre : un seul
constructeur, pour que la bascule ne se lise pas comme un changement d'écran.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from PyQt6.QtGui import QFont

from ui.common.theme import C, T
from ui.common.responsive import InspectorScrollArea


def insp_scroll(color: str, title: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
    """Titre coloré + zone scrollable.
    Retourne (hôte, layout à remplir, label de nom dans l'en-tête)."""
    host = QWidget()
    host.setStyleSheet(f"background:{C.BG_PANEL};")
    outer = QVBoxLayout(host)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(24)
    hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER_DARK};")
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(8, 0, 8, 0)
    lbl = QLabel(title)
    lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
    lbl.setStyleSheet(f"color:{color}; letter-spacing:1px;")
    hl.addWidget(lbl)
    hl.addStretch()
    name_lbl = QLabel("")
    name_lbl.setFont(QFont(T.MONO, T.XS))
    name_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
    hl.addWidget(name_lbl)
    outer.addWidget(hdr)

    scroll = InspectorScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(8)
    scroll.setWidget(inner)
    outer.addWidget(scroll, 1)
    return host, lay, name_lbl
