"""panel_bar — la barre d'outils fine d'un onglet.

Une seule mise en forme pour la console, les diagnostics et le disque (panneau
Build / debug) comme pour Disk (colonne de gauche) : le bouton d'action (Clear,
Refresh) est toujours au même endroit, à la même hauteur. Le look des onglets
eux-mêmes est celui de `QSS.tab`, global."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QTabWidget

from ui.common.theme import C, T

_BAR_HEIGHT = 26



def tab_widget() -> QTabWidget:
    """Un jeu d'onglets de l'éditeur.

    Le mode document fait occuper à la barre TOUTE la largeur : sans lui elle s'arrête au dernier
    onglet et laisse voir, à droite, le fond du conteneur — clair — au lieu du fond des barres
    d'onglets (`QSS.tab`).

    Pas de ligne de base : le style de Qt en trace une, aux couleurs de la PALETTE système (claires),
    tout en haut de la barre — une bande blanche entre les onglets et ce qui est au-dessus. Le filet
    sous les onglets est celui de `QSS.tab` (`QTabWidget::pane`)."""
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    tabs.tabBar().setDrawBase(False)
    return tabs


def panel_bar() -> tuple[QFrame, QHBoxLayout]:
    bar = QFrame()
    bar.setFixedHeight(_BAR_HEIGHT)
    bar.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
    row = QHBoxLayout(bar)
    row.setContentsMargins(8, 0, 8, 0)
    return bar, row


def bar_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setFont(QFont(T.UI, T.SM))
    button.setFixedHeight(20)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
