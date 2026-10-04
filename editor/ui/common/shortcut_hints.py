"""ui/common/shortcut_hints.py — table des raccourcis flottante d'un canvas.

Un seul widget pour tous les canvas (Scene Manager, Graphe des scènes,
Background Editor, Sprite Editor, Graphe sonore, Palette Editor) : un cartouche
semi-transparent, ferré en bas à droite, qui liste les raccourcis et gestes de
l'outil actif. Replié, c'est une pastille ; la souris dessus le déploie vers
le haut, la souris partie il se referme.

Le cartouche ne liste que les outils et les gestes PROPRES à l'écran : les
raccourcis communs (copier, supprimer, ajuster, zoom, molette, clic-milieu)
vivent dans Réglages → Shortcuts, pas ici.

L'écran hôte reste maître du contenu : il donne un `provider(contexte)` qui
rend le titre et les rangées de l'outil, et dit quand le contexte change
(`set_context`). Le widget ne connaît ni outil ni canvas.

Les touches remappables se lisent via `bound(id)` — le registre
`core/keybindings.py` reste la seule source de vérité, et le cartouche se
reconstruit quand Réglages en change une.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QRect, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
    QWidget,
)

from core.keybindings import get_keybindings
from ui.common import icons
from ui.common.labels import label
from ui.common.theme import C, T, tint

@dataclass(frozen=True)
class KeyIcon:
    """Une touche représentée par une icône, avec des modificateurs éventuels."""

    name: str
    modifiers: tuple[str, ...] = ()


# (touches affichées, clé de libellé de l'effet). SEPARATOR trace un filet.
Shortcut = str | KeyIcon
Row = tuple[Shortcut, str]
# (clé de libellé du titre, rangées)
Hints = tuple[str, list[Row]]
SEPARATOR: Row = ("", "")

_CLOSE_DELAY_MS = 250   # tolère un crochet de la souris avant de refermer
_OPEN_MS = 140          # durée de l'ouverture / fermeture
_MARGIN = 12


# ── Vocabulaire commun aux tables ─────────────────────────────────────────

def bound(binding_id: str) -> str:
    """La touche EFFECTIVE d'un raccourci remappable (cf. core/keybindings)."""
    return get_keybindings().resolve(binding_id)


def mouse(kind: str) -> str:
    """Un geste de souris, traduit : wheel, middle_drag, left_click, left_drag,
    right_click, right_drag, double_click, drop."""
    return label(f"hints.mouse.{kind}")


def key_icon(name: str) -> KeyIcon:
    """Une icône du registre présentée comme raccourci dans le cartouche."""
    return KeyIcon(name)


def combo(*parts: Shortcut) -> Shortcut:
    """« Ctrl + Clic » — plusieurs touches ou gestes tenus ensemble."""
    icon = next((part for part in parts if isinstance(part, KeyIcon)), None)
    if icon is not None:
        return KeyIcon(icon.name, tuple(str(part) for part in parts if isinstance(part, str)))
    return " + ".join(parts)


# ── Le cartouche ──────────────────────────────────────────────────────────

class ShortcutHints(QFrame):
    """Enfant de `host`, positionné en absolu dans son coin bas-droit.

    `host` : le canvas (QGraphicsView, QScrollArea…) ou un panneau. Pour une
    zone à défilement, le coin est celui du viewport. Le contenu pousse vers le
    haut : l'en-tête (pastille) reste sous la souris quand le cartouche s'ouvre.
    """

    def __init__(self, host: QWidget,
                 provider: Callable[[str], Hints], context: str = ""):
        super().__init__(host)
        self._host = host
        self._provider = provider
        self._context = context
        self._enabled = True
        self._expanded = False
        self.setObjectName("shortcutHints")
        self.setStyleSheet(
            f"#shortcutHints{{background:{tint(C.BG_RAISED, 0.92)};"
            f"border:1px solid {C.BORDER_MID};border-radius:8px;}}"
        )
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 6, 8, 6)
        self._lay.setSpacing(6)
        # Le corps vit dans une fenêtre de découpe dont la hauteur s'anime : il
        # glisse vers le haut sans que ses rangées ne se tassent. Il n'est pas
        # dans un layout — sa taille naturelle est posée une fois pour toutes.
        self._clip = QWidget()
        self._clip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._clip.setStyleSheet("background:transparent;")
        self._clip.hide()
        self._body: Optional[QWidget] = None
        self._body_w = self._body_h = 0
        self._progress = 0.0     # 0 = replié, 1 = étendu
        self._lay.addWidget(self._clip)
        header = self._build_header()
        self._pill_w = header.sizeHint().width()   # largeur replié : icône + mot + chevron
        self._lay.addWidget(header)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(_OPEN_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_progress)
        self._anim.finished.connect(self._on_anim_finished)

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(_CLOSE_DELAY_MS)
        self._close_timer.timeout.connect(lambda: self._set_expanded(False))

        host.installEventFilter(self)
        if isinstance(host, QAbstractScrollArea):
            host.viewport().installEventFilter(self)
        get_keybindings().changed.connect(lambda _id: self.refresh())
        self.refresh()

    # ── API ───────────────────────────────────────────────────────────

    def set_context(self, context: str) -> None:
        """L'outil (ou le mode) a changé : reconstruit le contenu."""
        if context == self._context:
            return
        self._context = context
        self.refresh()

    def refresh(self) -> None:
        title_key, rows = self._provider(self._context)
        if self._body is not None:
            self._body.setParent(None)   # quitte l'écran tout de suite, pas au prochain tour
            self._body.deleteLater()
            self._body = None
        if not rows:
            self.hide()
            return
        body = self._build_body(title_key, rows)
        body.setParent(self._clip)
        size = body.sizeHint()
        body.resize(size)
        body.show()
        self._body, self._body_w, self._body_h = body, size.width(), size.height()
        self._set_progress(self._progress)
        self.setVisible(self._enabled)

    def set_enabled(self, enabled: bool) -> None:
        """Masque/montre le cartouche sans toucher à son contenu — pour un écran
        qui n'a rien à montrer (ex: aucune palette ouverte)."""
        self._enabled = enabled
        self.setVisible(enabled and self._body is not None)
        self.reposition()

    def reposition(self) -> None:
        area = self._area()
        x = area.right() - self.width() - _MARGIN + 1
        y = area.bottom() - self.height() - _MARGIN + 1
        self.move(max(area.left(), x), max(area.top(), y))
        self.raise_()

    # ── Replié / étendu ───────────────────────────────────────────────

    def _set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._header_chevron.setPixmap(
            icons.get("hints_collapse" if expanded else "hints_expand", C.TEXT_NORM).pixmap(14, 14))
        if not expanded:   # la pastille retrouve son icône et son mot dès la fermeture
            self._header_icon.setVisible(True)
            self._header_title.setVisible(True)
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(1.0 if expanded else 0.0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        # Ouvert, le contenu parle de lui-même : l'icône et le mot ne servent
        # que la pastille repliée ; il ne reste que le chevron pour refermer.
        if self._expanded:
            self._header_icon.hide()
            self._header_title.hide()
            self._set_progress(self._progress)

    def _set_progress(self, progress: float) -> None:
        """Un pas de l'animation : le cartouche grandit depuis la pastille vers
        son coin haut-gauche, en largeur comme en hauteur. Le corps, collé au
        coin bas-droit de la fenêtre de découpe, se révèle au fur et à mesure."""
        self._progress = float(progress)
        pill_w = self._pill_w - 16          # largeur utile de la pastille (hors marges)
        w = round(pill_w + (self._body_w - pill_w) * self._progress)
        h = round(self._body_h * self._progress)
        self._clip.setFixedSize(max(w, 0), h)
        if self._body is not None:
            self._body.move(w - self._body_w, h - self._body_h)
        self._clip.setVisible(h > 0)
        self._lay.invalidate()   # un enfant masqué ne se retranche du calcul qu'après invalidation
        self._lay.activate()
        self.adjustSize()
        self.reposition()

    def enterEvent(self, e) -> None:
        self._close_timer.stop()
        self._set_expanded(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._close_timer.start()
        super().leaveEvent(e)

    # ── Géométrie ─────────────────────────────────────────────────────

    def _area(self) -> QRect:
        h = self._host
        if isinstance(h, QAbstractScrollArea):
            vp = h.viewport()
            return QRect(vp.pos(), vp.size())
        return h.rect()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.reposition()
        return False

    # ── Construction ──────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        """La pastille : icône clavier, « Raccourcis », chevron d'état.
        Toujours visible ; c'est tout ce qui reste quand c'est replié."""
        head = QWidget()
        head.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        head.setStyleSheet("background:transparent;")
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self._header_icon = kb = QLabel()
        kb.setPixmap(icons.get("hints_keyboard", C.TEXT_NORM).pixmap(16, 16))
        self._header_title = QLabel(label("hints.header"))
        self._header_title.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        self._header_title.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._header_chevron = QLabel()
        self._header_chevron.setPixmap(icons.get("hints_expand", C.TEXT_NORM).pixmap(14, 14))
        h.addWidget(kb)
        h.addWidget(self._header_title)
        h.addStretch()
        h.addWidget(self._header_chevron)
        return head

    def _build_body(self, title_key: str, rows: list[Row]) -> QWidget:
        body = QWidget()
        body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Un hôte qui pose `background:` sur lui-même le fait hériter à tous ses
        # descendants : sans cette règle, le corps se peint en rectangle plein
        # par-dessus le fond translucide du cartouche (carrés superposés).
        body.setStyleSheet("background:transparent;")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        if title_key:
            title = QLabel(label(title_key).upper())
            title.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            title.setStyleSheet(f"color:{C.TEXT_DIM};letter-spacing:1px;background:transparent;")
            v.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        r = 0
        for keys, effect_key in rows:
            if (keys, effect_key) == SEPARATOR:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background:{C.BORDER};")
                grid.addWidget(line, r, 0, 1, 2)
            else:
                chip = self._shortcut_chip(keys)
                effect = QLabel(label(effect_key))
                effect.setFont(QFont(T.UI, T.SM))
                effect.setStyleSheet(f"color:{C.TEXT_NORM};background:transparent;")
                grid.addWidget(chip, r, 0, Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(effect, r, 1)
            r += 1
        v.addLayout(grid)
        return body

    @staticmethod
    def _shortcut_chip(keys: Shortcut) -> QWidget:
        """Construit la capsule d'une touche, textuelle ou illustrée."""
        chip_style = (
            f"color:{C.TEXT_HI};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;padding:0 5px;")
        if isinstance(keys, str):
            chip = QLabel(keys)
            chip.setFont(QFont(T.MONO, T.SM))
            chip.setStyleSheet(chip_style)
            return chip

        chip = QFrame()
        chip.setStyleSheet(chip_style)
        row = QHBoxLayout(chip)
        row.setContentsMargins(5, 0, 5, 0)
        row.setSpacing(3)
        if keys.modifiers:
            modifier = QLabel(" + ".join(keys.modifiers) + " +")
            modifier.setFont(QFont(T.MONO, T.SM))
            modifier.setStyleSheet("background:transparent;border:none;padding:0;")
            row.addWidget(modifier)
        icon = QLabel()
        icon.setPixmap(icons.get(keys.name, C.TEXT_HI).pixmap(14, 14))
        icon.setStyleSheet("background:transparent;border:none;padding:0;")
        row.addWidget(icon)
        return chip
