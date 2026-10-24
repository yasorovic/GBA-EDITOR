"""ui/common/canvas_top_bar.py — barre d'état au-dessus d'un canvas.

Barre unique partagée par tous les écrans à canvas (Scene Manager, Background
Editor…) : zoom (−/%/+/ajuster) à gauche, toggles d'affichage propres à l'écran
au milieu, dimensions + position du curseur à droite.

L'écran hôte reste maître de son canvas : la barre ne fait qu'émettre
`zoom_step_asked` / `fit_asked` et afficher ce qu'on lui pousse
(`set_zoom`, `set_canvas_size`, `set_cursor_px`).
"""
from __future__ import annotations

from ui.common.labels import label
from ui.common.tooltip import tooltip
from core.keybindings import get_keybindings
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T
from ui.common import icons
from ui.common.cursor_unit import CursorUnitButton

BAR_HEIGHT = 36


class CycleToolButton(QToolButton):
    """Un bouton, plusieurs états : un clic passe au suivant, le dernier revient à zéro.

    Même apparence que `CanvasTopBar.add_toggle` (l'état coché en est le fond) : l'état 0 est le repos, tout autre état l'allume."""

    state_changed = pyqtSignal(int)

    def __init__(self, states: list, parent=None):
        super().__init__(parent)
        self._states = list(states)          # [(clé d'icône, infobulle)]
        self._state = 0
        self.setCheckable(True)              # pour le sélecteur :checked ; l'état se pose à la main
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"border-radius:4px;padding:0px;margin:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )
        self.clicked.connect(lambda: self.set_state((self._state + 1) % len(self._states)))
        self._refresh()

    @property
    def state(self) -> int:
        return self._state

    def set_state(self, state: int) -> None:
        state = state % len(self._states)
        changed = state != self._state
        self._state = state
        self._refresh()
        if changed:
            self.state_changed.emit(state)

    def _refresh(self) -> None:
        icon_key, tip = self._states[self._state]
        self.setIcon(icons.get(icon_key, icons.COLOR_DEFAULT, C.ACCENT))
        self.setToolTip(tip)
        self.setChecked(self._state > 0)


class CanvasTopBar(QFrame):
    zoom_step_asked = pyqtSignal(int)   # -1 = dézoomer, +1 = zoomer
    fit_asked = pyqtSignal()

    def __init__(self, fit_tip: str = None, parent=None, show_coords: bool = True):
        if fit_tip is None:
            fit_tip = tooltip(title=label('cvtop.fit_to_view'), shortcut=get_keybindings().resolve("common.fit"))
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setStyleSheet(f"{type(self).__name__}{{background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};}}")
        self._font = QFont(T.MONO, T.MD)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(12)
        self._lay = lay

        self._btn_zoom_out = self._icon_btn(
            "zoom_out", 16, (24, 24),
            tooltip(title=label('cvtop.zoom_out'), shortcut=label('cvtop.wheel_down')),
        )
        self._btn_zoom_out.clicked.connect(lambda: self.zoom_step_asked.emit(-1))
        lay.addWidget(self._btn_zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFont(self._font)
        self._zoom_label.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._zoom_label.setFixedWidth(46)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._zoom_label)

        self._btn_zoom_in = self._icon_btn(
            "zoom_in", 16, (24, 24),
            tooltip(title=label('cvtop.zoom_in'), shortcut=label('cvtop.wheel_up')),
        )
        self._btn_zoom_in.clicked.connect(lambda: self.zoom_step_asked.emit(+1))
        lay.addWidget(self._btn_zoom_in)

        self._btn_fit = self._icon_btn("fit_page", 18, (28, 24), fit_tip)
        self._btn_fit.clicked.connect(self.fit_asked)
        lay.addWidget(self._btn_fit)

        lay.addSpacing(16)

        # Zone des toggles propres à l'écran — remplie via add_toggle/add_spacing.
        self._extras_at = lay.count()
        lay.addStretch()

        self._size_label = QLabel("")
        self._size_label.setFont(self._font)
        self._size_label.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._coord_label = CursorUnitButton(self._font)
        if show_coords:
            lay.addWidget(self._size_label)
            lay.addSpacing(8)
            lay.addWidget(self._coord_label)

    def add_trailing(self, widget) -> None:
        """Ajoute un widget tout à droite de la barre, après la zone des
        extras et les labels taille/curseur (ex: bouton d'action final)."""
        self._lay.addWidget(widget)

    # ── Construction ──────────────────────────────────────────────

    def _icon_btn(self, key: str, icon_px: int, size, tip: str) -> QPushButton:
        b = QPushButton()
        b.setIcon(icons.get(key, C.TEXT_NORM))
        b.setIconSize(QSize(icon_px, icon_px))
        b.setFixedSize(*size)
        b.setToolTip(tip)
        return b

    def add_toggle(self, icon_key: str, tip: str, slot=None) -> QToolButton:
        """Toggle iconifié inséré dans la zone du milieu.
        L'état coché est porté par le sélecteur QSS :checked (fond périwinkle),
        donc robuste même sous blockSignals (ex: exclusion grille 8/16)."""
        b = QToolButton()
        b.setIcon(icons.get(icon_key, icons.COLOR_DEFAULT, C.ACCENT))
        b.setIconSize(QSize(18, 18))
        b.setCheckable(True)
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"border-radius:4px;padding:0px;margin:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )
        if slot is not None:
            b.toggled.connect(slot)
        self._lay.insertWidget(self._extras_at, b)
        self._extras_at += 1
        return b

    def add_state_toggle(self, states: list, slot=None) -> "CycleToolButton":
        """Bouton à états inséré dans la zone du milieu, comme `add_toggle` : chaque clic passe à l'état suivant, puis revient au premier.
        `states` = [(icône, infobulle), …] ; l'état 0 est « inactif » (fond neutre), les autres portent le fond de l'état coché.
        `slot(état)` est appelé à chaque changement."""
        b = CycleToolButton(states)
        if slot is not None:
            b.state_changed.connect(slot)
        self._lay.insertWidget(self._extras_at, b)
        self._extras_at += 1
        return b

    def add_action(self, icon_key: str, tip: str, slot=None) -> QToolButton:
        """Bouton d'action (non cochable) inséré dans la zone du milieu — même
        emplacement que add_toggle, mais pour un geste ponctuel (ex: ouvrir
        l'image dans un logiciel externe) plutôt qu'un état d'affichage."""
        b = QToolButton()
        b.setIcon(icons.get(icon_key, icons.COLOR_DEFAULT))
        b.setIconSize(QSize(18, 18))
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"border-radius:4px;padding:0px;margin:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
        )
        if slot is not None:
            b.clicked.connect(slot)
        self._lay.insertWidget(self._extras_at, b)
        self._extras_at += 1
        return b

    def add_slider(self, tip: str, lo: int, hi: int, value: int, slot=None, width: int = 72) -> QSlider:
        """Petit curseur horizontal posé à DROITE, juste avant les dimensions du canvas (ex : l'intensité du passe-partout).
        `slot(valeur)` est appelé à chaque cran."""
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        s.setFixedWidth(width)
        s.setToolTip(tip)
        s.setStyleSheet(
            f"QSlider::groove:horizontal{{height:4px; background:{C.BORDER_MID}; border-radius:2px;}}"
            f"QSlider::sub-page:horizontal{{background:{C.ACCENT}; border-radius:2px;}}"
            f"QSlider::handle:horizontal{{width:10px; height:10px; margin:-3px 0; border-radius:5px;"
            f"background:{C.TEXT_NORM};}}"
            f"QSlider::handle:horizontal:hover{{background:{C.ACCENT};}}")
        if slot is not None:
            s.valueChanged.connect(slot)
        at = self._lay.indexOf(self._size_label)
        if at >= 0:
            self._lay.insertWidget(at, s)
        else:
            self._lay.addWidget(s)
        return s

    def add_cycle(self, icon_key: str, tip_for, values: list, slot=None) -> QToolButton:
        """Une icône fixe (non cliquable) suivie d'UN bouton qui fait défiler `values` : un clic passe à la valeur suivante,
        puis revient à la première après la dernière (ex : la taille de la brosse). `tip_for(valeur)` rend l'infobulle de
        la valeur affichée ; `slot(valeur)` est appelé à chaque changement. Rend le bouton ; sa valeur courante est
        `button.property("value")`."""
        box = QFrame()
        box.setStyleSheet("background:transparent; border:none;")
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        glyph = QLabel()
        glyph.setPixmap(icons.get(icon_key, C.TEXT_DIM).pixmap(QSize(16, 16)))
        glyph.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(glyph)

        b = QToolButton()
        b.setFont(self._font)
        b.setFixedSize(34, 28)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};color:{C.TEXT_NORM};"
            f"border-radius:4px;padding:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}")

        def show_value(value):
            b.setProperty("value", value)
            b.setText(str(value))
            b.setToolTip(tip_for(value))

        def advance():
            at = values.index(b.property("value"))
            value = values[(at + 1) % len(values)]
            show_value(value)
            if slot is not None:
                slot(value)

        show_value(values[0])
        b.clicked.connect(advance)
        row.addWidget(b)
        self.add_widget(box)
        return b

    def add_widget(self, widget) -> None:
        """Insère un widget quelconque dans la zone des extras (ex: champ de
        recherche), au même titre qu'un toggle ou une action."""
        self._lay.insertWidget(self._extras_at, widget)
        self._extras_at += 1

    def add_spacing(self, px: int):
        """Respiration entre deux groupes de toggles."""
        self._lay.insertSpacing(self._extras_at, px)
        self._extras_at += 1

    # ── Affichage ─────────────────────────────────────────────────

    def set_zoom(self, zoom: float):
        self._zoom_label.setText(f"{round(zoom * 100)}%")

    def set_canvas_size(self, w: int, h: int):
        self._size_label.setText(f"{w}×{h}" if w and h else "")

    def set_cursor_px(self, x: int | None, y: int | None):
        """Position du curseur en pixels du canvas, (None, None) hors du canvas. L'unité affichée est celle du réglage commun."""
        self._coord_label.set_position(x, y)
