"""
ui/reorderable_bar.py — Barre de boutons de navigation réordonnables par drag & drop.

UX : le bouton draggué reste en place (grisé), un fantôme flotte sous le curseur,
un trait vert indique la position de drop. Le layout ne se reconstruit qu'au relâché.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QButtonGroup, QFrame
from PyQt6.QtCore import Qt, QSettings, QPoint, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QFont

from ui.common.theme import C, T

_SETTINGS_ORG = "GBAEditor"
_SETTINGS_APP = "Layout"
_SETTINGS_KEY = "screen_button_order"

_BTN_NORMAL = (
    f"QToolButton{{color:{C.TEXT_NORM};border:none;padding:6px 14px;border-radius:4px;}}"
    f"QToolButton:hover{{background:{C.BG_HOVER};color:{C.TEXT_HI};}}"
    f"QToolButton:checked{{background:{C.BG_SEL};color:{C.ACCENT};}}"
)
# Bouton source pendant le drag : grisé, sert de placeholder visuel
_BTN_GHOST_SRC = (
    f"QToolButton{{color:{C.BORDER};border:1px dashed {C.BORDER};"
    "padding:6px 14px;border-radius:4px;background:transparent;}"
)
# Bouton fantôme flottant
_BTN_GHOST = (
    f"QToolButton{{color:{C.TEXT_HI};border:1px solid {C.ACCENT};"
    f"padding:6px 14px;border-radius:4px;background:{C.BG_SEL};}}"
)


class ReorderableButtonBar(QWidget):
    """
    Barre horizontale de QToolButton réordonnables par drag & drop.

    screen_idx est stable (correspond à l'index dans SCREENS).
    L'ordre d'affichage est indépendant et persisté dans QSettings.
    """

    screen_requested = pyqtSignal(int)

    def __init__(self, screens: list[str], parent=None):
        super().__init__(parent)
        self._screens = screens
        self._order: list[int] = self._load_order()

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, QToolButton] = {}

        for i, name in enumerate(screens):
            btn = QToolButton()
            btn.setText(name)
            btn.setCheckable(True)
            btn.setFont(QFont(T.UI, T.MD))
            btn.setStyleSheet(_BTN_NORMAL)
            # La main fermée est réservée au déplacement en cours : au repos,
            # y compris au simple survol, le curseur reste celui par défaut.
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.clicked.connect(lambda _=False, idx=i: self.screen_requested.emit(idx))
            btn.installEventFilter(self)
            self._group.addButton(btn, i)
            self._buttons[i] = btn

        self._rebuild_layout()

        # ── Fantôme flottant ──────────────────────────────────────────
        self._ghost = QToolButton(self)
        self._ghost.setFont(QFont(T.UI, T.MD))
        self._ghost.setStyleSheet(_BTN_GHOST)
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ghost.hide()

        # ── Indicateur de drop (trait vertical vert) ──────────────────
        self._indicator = QFrame(self)
        self._indicator.setFixedWidth(2)
        self._indicator.setStyleSheet(f"background:{C.ACCENT};border-radius:1px;")
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.hide()

        # ── État drag ─────────────────────────────────────────────────
        self._drag_btn: QToolButton | None = None
        self._drag_start: QPoint | None = None
        self._dragging = False
        self._drag_target: int = 0   # index dans _order_without_dragged
        self._cursor_reset_token = 0

    # ── API publique ──────────────────────────────────────────────────

    def check_screen(self, screen_idx: int):
        btn = self._buttons.get(screen_idx)
        if btn:
            btn.setChecked(True)

    # ── Persistance ───────────────────────────────────────────────────

    def _load_order(self) -> list[int]:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        raw = s.value(_SETTINGS_KEY)
        n = len(self._screens)
        if isinstance(raw, list) and len(raw) == n:
            try:
                order = [int(x) for x in raw]
                if sorted(order) == list(range(n)):
                    return order
            except (ValueError, TypeError):
                pass
        return list(range(n))

    def _save_order(self):
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_SETTINGS_KEY, self._order)

    # ── Layout ────────────────────────────────────────────────────────

    def _rebuild_layout(self):
        for i in reversed(range(self._layout.count())):
            w = self._layout.itemAt(i).widget()
            if w:
                # hide() avant setParent(None) : même détaché puis rattaché
                # dans la foulée, un QToolButton visible reparenté à rien
                # devient furtivement une fenêtre top-level (le "micro popup"
                # qui flashe à l'ouverture d'un projet) — hide() l'évite.
                w.hide()
                w.setParent(None)
        for idx in self._order:
            btn = self._buttons[idx]
            self._layout.addWidget(btn)
            btn.show()

    def _screen_idx_of(self, btn: QToolButton) -> int:
        for idx, b in self._buttons.items():
            if b is btn:
                return idx
        return -1

    # ── Drag & drop ───────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if not isinstance(obj, QToolButton):
            return False

        t = event.type()

        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_btn = obj
            self._drag_start = event.globalPosition().toPoint()
            self._dragging = False
            return False  # laisser le clic normal se propager

        if t == QEvent.Type.MouseMove and self._drag_btn is obj:
            if not self._dragging:
                delta = (event.globalPosition().toPoint() - self._drag_start).manhattanLength()
                if delta < 8:
                    return False
                self._begin_drag(obj)

            if self._dragging:
                lx = self.mapFromGlobal(event.globalPosition().toPoint()).x()
                self._update_drag(lx)
                return True

        if t == QEvent.Type.MouseButtonRelease and self._drag_btn is obj:
            if self._dragging:
                self._end_drag()
                return True
            self._drag_btn = None

        return False

    def _begin_drag(self, btn: QToolButton):
        self._dragging = True
        self._cursor_reset_token += 1
        btn.setStyleSheet(_BTN_GHOST_SRC)
        btn.setCursor(Qt.CursorShape.ClosedHandCursor)

        # Initialiser le fantôme à la taille et position du bouton
        self._ghost.setText(btn.text())
        self._ghost.setFixedSize(btn.size())
        self._ghost.move(btn.pos())
        self._ghost.show()
        self._ghost.raise_()
        self._indicator.raise_()

        # Cible initiale = position actuelle dans _order
        drag_screen = self._screen_idx_of(btn)
        self._drag_target = self._order.index(drag_screen)

    def _update_drag(self, mouse_x: int):
        # Déplacer le fantôme (centré sous le curseur, clampé)
        gw = self._ghost.width()
        gx = max(0, min(mouse_x - gw // 2, self.width() - gw))
        gy = (self.height() - self._ghost.height()) // 2
        self._ghost.move(gx, gy)

        # Calculer la cible
        self._drag_target = self._compute_target(mouse_x)
        self._place_indicator(self._drag_target)

    def _compute_target(self, mouse_x: int) -> int:
        """Retourne l'index cible dans _order (hors bouton draggué)."""
        drag_screen = self._screen_idx_of(self._drag_btn)
        others = [idx for idx in self._order if idx != drag_screen]

        for j, screen_idx in enumerate(others):
            btn = self._buttons[screen_idx]
            geo = btn.geometry()
            mid = geo.x() + geo.width() // 2
            if mouse_x < mid:
                return j
        return len(others)

    def _place_indicator(self, target: int):
        drag_screen = self._screen_idx_of(self._drag_btn)
        others = [idx for idx in self._order if idx != drag_screen]

        h = self.height()
        pad = 6
        self._indicator.setFixedHeight(h - pad * 2)

        if not others:
            self._indicator.hide()
            return

        if target == 0:
            ref = self._buttons[others[0]].geometry()
            x = ref.x() - 3
        elif target >= len(others):
            ref = self._buttons[others[-1]].geometry()
            x = ref.right() + 1
        else:
            left = self._buttons[others[target - 1]].geometry()
            right = self._buttons[others[target]].geometry()
            x = (left.right() + right.x()) // 2 - 1

        self._indicator.move(x, pad)
        self._indicator.show()

    def _end_drag(self):
        drag_screen = self._screen_idx_of(self._drag_btn)
        others = [idx for idx in self._order if idx != drag_screen]
        others.insert(self._drag_target, drag_screen)
        self._order = others

        # Nettoyer l'UI de drag
        released_btn = self._drag_btn
        reset_token = self._cursor_reset_token
        released_btn.setStyleSheet(_BTN_NORMAL)
        released_btn.setCursor(Qt.CursorShape.OpenHandCursor)
        self._ghost.hide()
        self._indicator.hide()
        self._dragging = False
        self._drag_btn = None

        # Le relâché confirme visuellement la fin du geste, avant le retour
        # discret au curseur normal. Ne pas interrompre un nouveau drag lancé
        # pendant ce court délai, ni écourter le délai d'un geste suivant.
        QTimer.singleShot(
            100,
            lambda: None if reset_token != self._cursor_reset_token
            else released_btn.setCursor(Qt.CursorShape.ArrowCursor),
        )

        self._rebuild_layout()
        self._save_order()
