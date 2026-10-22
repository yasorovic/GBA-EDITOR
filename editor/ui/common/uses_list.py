"""
ui/common/uses_list.py — la base des vues « Voir les utilisations ».

Header coloré + section bar (+ bouton d'action optionnel) + liste défilante + vidage de
liste. Partagée par `PrefabUsesInspector` (inspecteur du Scene Manager) et
`ScriptUsesPanel` (colonne droite du Script Editor) : chacune ne diffère que par ses
couleurs, son bouton d'action et la façon dont `load()` peuple la liste.
"""
from __future__ import annotations
from ui.common.labels import label

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from core.selection_bus import get_bus
from ui.common.theme import C, T
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import CollapsibleCard
from ui.common import icons


# ──────────────────────────────────────────────────────────────────
#  Base commune : header coloré + section bar (+ bouton d'action
#  optionnel) + liste scrollable + helpers de construction de lignes.
# ──────────────────────────────────────────────────────────────────
class UsesListBase(QWidget):
    _HEADER_COLOR = icons.COLOR_DEFAULT
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = ""
    _ACTION_BTN_TEXT: str | None = None
    _ACTION_BTN_COLOR: str | None = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._root_layout = root

        # ── Header coloré avec nom de l'élément inspecté ──────────
        self._top = QFrame()
        self._top.setFixedHeight(40)
        self._top.setStyleSheet(
            f"background:{self._HEADER_COLOR}{self._HEADER_BG_ALPHA}; "
            f"border-bottom:1px solid {self._HEADER_COLOR}{self._HEADER_BORDER_ALPHA};"
        )
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(12, 0, 8, 0)
        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        btn_close = QPushButton("v")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            f"QPushButton{{color:{self._HEADER_COLOR};background:transparent;border:none;"
            f"font-family:{T.UI_STACK};font-size:10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_close.setToolTip(label('uses.close_this_view'))
        btn_close.clicked.connect(self._on_close)
        tl.addWidget(self._name_lbl, 1)
        tl.addWidget(btn_close)
        root.addWidget(self._top)

        # ── Carte : titre + bouton d'action optionnel + liste ─────
        self._card = CollapsibleCard(self._SECTION_TITLE, color=self._HEADER_COLOR)
        self._card.set_expanding(True)
        # Une liste ouverte utilise toute la hauteur utile. Repliée, elle ne
        # doit plus garder sa cellule extensible : sinon Qt centre son en-tête
        # dans le grand espace restant et décale les inspecteurs suivants.
        self._card.toggled.connect(self._on_card_toggled)
        if self._ACTION_BTN_TEXT:
            self._action_btn = QPushButton(self._ACTION_BTN_TEXT)
            self._action_btn.setFont(QFont(T.UI, T.SM))
            self._action_btn.setFixedHeight(20)
            self._action_btn.setStyleSheet(
                f"QPushButton{{color:{self._ACTION_BTN_COLOR};background:transparent;border:none;"
                f"font-family:{T.UI_STACK};font-size:8px;}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            )
            self._action_btn.clicked.connect(self._on_action)
            self._card.add_header_widget(self._action_btn)
        root.addWidget(self._card, 1)

        # ── Liste des utilisations ────────────────────────────────
        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{C.BG_PANEL};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        self._card.body_layout.setContentsMargins(0, 0, 0, 0)
        self._card.body_layout.addWidget(scroll)

    def _on_card_toggled(self, expanded: bool) -> None:
        """Réserve la hauteur libre à la liste seulement lorsqu'elle est visible."""
        index = self._root_layout.indexOf(self._card)
        if index >= 0:
            self._root_layout.setStretch(index, 1 if expanded else 0)
            self._root_layout.invalidate()

    # ── Helpers de construction de liste, communs aux sous-classes ──

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            old_w = item.widget()
            if old_w:
                # hide() avant setParent(None) : un widget visible détaché de
                # son parent redevient une fenêtre top-level à part entière.
                old_w.hide()
                old_w.setParent(None)
                old_w.deleteLater()

    def _add_empty_row(self, text: str):
        empty = QLabel(f"  {text}")
        empty.setFont(QFont(T.UI, T.MD))
        empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:12px;")
        self._list_layout.addWidget(empty)

    def _add_group_row(self, icon: str, label: str, color: str, count: int | None = None):
        row = QFrame()
        row.setFixedHeight(24)
        row.setStyleSheet(f"background:{C.BG_RAISED};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 8, 0)
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont(T.UI, T.MD))
        icon_lbl.setStyleSheet(f"color:{color};")
        icon_lbl.setFixedWidth(16)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.UI, T.MD))
        name_lbl.setStyleSheet(f"color:{color};")
        rl.addWidget(icon_lbl)
        rl.addWidget(name_lbl, 1)
        if count is not None:
            count_lbl = QLabel(f"×{count}")
            count_lbl.setFont(QFont(T.UI, T.SM))
            count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            rl.addWidget(count_lbl)
        self._list_layout.addWidget(row)

    def _add_leaf_row(self, label: str, on_click):
        leaf = QFrame()
        leaf.setFixedHeight(22)
        leaf.setStyleSheet(f"background:{C.BG_PANEL};")
        leaf.setCursor(Qt.CursorShape.PointingHandCursor)
        ll = QHBoxLayout(leaf)
        ll.setContentsMargins(28, 0, 8, 0)
        icon_lbl = QLabel("·")
        icon_lbl.setFont(QFont(T.UI, T.MD))
        icon_lbl.setStyleSheet(f"color:{C.BORDER_MID};")
        icon_lbl.setFixedWidth(12)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.UI, T.MD))
        name_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        ll.addWidget(icon_lbl)
        ll.addWidget(name_lbl, 1)
        self._list_layout.addWidget(leaf)
        leaf.mousePressEvent = lambda e, cb=on_click: cb()

    # ── Actions par défaut, surchargeables ───────────────────────────

    def _on_action(self):
        pass

    def _on_close(self):
        get_bus().clear()
