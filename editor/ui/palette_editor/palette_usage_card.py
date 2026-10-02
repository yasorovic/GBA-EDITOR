"""ui/palette_editor/palette_usage_card.py — carte « USAGE », ferrée en bas de
l'inspecteur du Palette Editor.

Répond à « qui se sert de cette palette ? » : sprites, fonds, prefabs et scènes,
groupés par type. Un clic sur une ligne ouvre l'écran qui édite cet élément —
la carte ne navigue pas elle-même, elle émet `usage_activated(kind, name)` et
laisse la fenêtre router (cf. MainWindow._open_palette_usage).

Le calcul vit dans `Project.palette_usages()`, aux côtés de `rename_palette` :
c'est le même inventaire de référents, il ne doit exister qu'à un endroit.

Hauteur libre : la carte est un enfant du splitter vertical de la colonne
droite (cf. palette_editor_screen), donc c'est l'utilisateur qui décide de sa
taille — d'où l'absence de plafond ici.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common import icons
from ui.common.labels import label
from ui.common.tooltip import tooltip

# Type d'usage -> (icône, couleur, clé de groupe pluralisable).
# L'ordre de ce tableau EST l'ordre d'affichage des groupes.
_KINDS = (
    ("sprite",     "sprite",     icons.COLOR_SPRITE,     "paluse.sprite"),
    ("background", "background", icons.COLOR_BACKGROUND, "paluse.background"),
    ("prefab",     "prefab",     icons.COLOR_PREFAB,     "paluse.prefab"),
    ("scene",      "scene",      icons.COLOR_SCENE,      "paluse.scene"),
)

_HDR_H = 28
_MIN_H = _HDR_H + 30      # entête + une ligne : la carte ne disparaît jamais


class PaletteUsageCard(QWidget):
    """Carte ferrée en bas de la colonne droite : entête « USAGE · N » + liste
    groupée par type, chaque ligne cliquable."""

    usage_activated = pyqtSignal(str, str)   # kind, nom de l'élément

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._bank_name: Optional[str] = None
        self.setMinimumHeight(_MIN_H)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-left:1px solid {C.BORDER};")
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(_HDR_H)
        hdr.setStyleSheet(
            f"background:{C.BG_RAISED}; border-top:1px solid {C.BORDER};"
            f"border-bottom:1px solid {C.BORDER_DARK};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        title = QLabel(label("paluse.title"))
        title.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        title.setStyleSheet(QSS.title_panel)
        hl.addWidget(title)
        hl.addStretch()
        self._count = QLabel("")
        self._count.setFont(QFont(T.MONO, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_DIM};")
        hl.addWidget(self._count)
        root.addWidget(hdr)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(QSS.scroll_area + QSS.scrollbar)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self._list = QVBoxLayout(body)
        self._list.setContentsMargins(0, 4, 0, 6)
        self._list.setSpacing(0)
        self._scroll.setWidget(body)
        root.addWidget(self._scroll, 1)

    # ── API ───────────────────────────────────────────────────────

    def load(self, project, bank_name: Optional[str]):
        """(Re)construit la liste pour la banque `bank_name`."""
        self._project = project
        self._bank_name = bank_name
        self._clear()
        if not (project and bank_name):
            self._count.setText("")
            self._add_empty(label("paluse.none_selected"))
            self._list.addStretch()
            return

        usages = project.palette_usages(bank_name)
        self._count.setText(str(len(usages)) if usages else "")
        if not usages:
            self._add_empty(label("paluse.no_use"))
            self._list.addStretch()
            return

        for kind, icon_name, color, name_key in _KINDS:
            group = [u for u in usages if u.kind == kind]
            if not group:
                continue
            self._add_group(icon_name, color,
                            label(name_key, n=len(group)), len(group))
            for usage in group:
                self._add_leaf(usage)
        self._list.addStretch()

    def clear(self):
        self.load(self._project, None)

    def refresh(self):
        """Recalcule pour la banque déjà affichée (usages modifiés ailleurs :
        sélection de scène, override d'un asset…)."""
        self.load(self._project, self._bank_name)

    # ── Lignes ────────────────────────────────────────────────────

    def _clear(self):
        while self._list.count():
            item = self._list.takeAt(0)
            w = item.widget()
            if w:
                # hide() avant setParent(None) : un widget visible détaché
                # redeviendrait une fenêtre top-level (cf. uses_inspectors).
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _add_empty(self, text: str):
        lbl = QLabel(text)
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:10px 12px;")
        lbl.setWordWrap(True)
        self._list.addWidget(lbl)

    def _add_group(self, icon_name: str, color: str, label: str, count: int):
        row = QFrame()
        row.setFixedHeight(22)
        row.setStyleSheet(f"background:{C.BG_PANEL};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 10, 0)
        rl.setSpacing(6)
        ico = QLabel()
        ico.setFixedWidth(16)
        ico.setPixmap(icons.get(icon_name, color).pixmap(QSize(13, 13)))
        rl.addWidget(ico)
        lbl = QLabel(label)
        lbl.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        lbl.setStyleSheet(f"color:{color};")
        rl.addWidget(lbl, 1)
        cnt = QLabel(f"×{count}")
        cnt.setFont(QFont(T.MONO, T.XS))
        cnt.setStyleSheet(f"color:{C.TEXT_MUTED};")
        rl.addWidget(cnt)
        self._list.addWidget(row)

    def _add_leaf(self, usage):
        row = QFrame()
        row.setFixedHeight(22)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            f"QFrame{{background:transparent;}}"
            f"QFrame:hover{{background:{C.BG_HOVER};}}"
        )
        row.setToolTip(tooltip(
            title=label("paluse.open_title"),
            body=label("paluse.open_tip", detail=usage.detail),
        ))
        rl = QHBoxLayout(row)
        rl.setContentsMargins(26, 0, 10, 0)
        rl.setSpacing(6)
        name = QLabel(usage.name)
        name.setFont(QFont(T.UI, T.SM))
        name.setStyleSheet(f"color:{C.TEXT_NORM};")
        rl.addWidget(name)
        detail = QLabel(usage.detail)
        detail.setFont(QFont(T.UI, T.XS))
        detail.setStyleSheet(f"color:{C.TEXT_MUTED};")
        detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rl.addWidget(detail, 1)
        row.mousePressEvent = lambda e, u=usage: self.usage_activated.emit(u.kind, u.name)
        self._list.addWidget(row)
