"""ProjectInspector — carte d'identité du projet, mode par défaut de
l'inspecteur quand rien n'est sélectionné (clic hors de la zone active du
canvas, Échap, etc.).

Édite ProjectSettings avec les mêmes conventions que les autres inspecteurs :
commit à la perte de focus pour le texte, mutation undoable via SetFieldCmd,
persistance immédiate dans project.json.

`start_scene` est le point de départ du JEU — distinct de `last_scene`, la
dernière scène ouverte dans l'éditeur (cf. Project.set_active_scene).

Ce panneau ne porte QUE l'identité du projet — auteur, version, scène de
départ — et l'aperçu en lecture seule de son contenu (carte Content). Le reste
de `ProjectSettings` (build, visuel dont le backdrop, son, input, langues,
collisions) vit dans la fenêtre Game → Project Settings
(`ProjectSettingsDialog`, project_settings_dialog.py), au même titre que les
réglages du logiciel (`SettingsDialog`) : ce qu'on règle une fois plutôt que
ce qu'on garde sous les yeux en travaillant (2026-08-25)."""
from __future__ import annotations
from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QScrollArea, QLineEdit, QComboBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QSize

from core.project import Project
from core.history import get_history, SetFieldCmd
from ui.common.theme import C, T, QSS
from ui.common.responsive import InspectorScrollArea
from ui.common.widgets import CollapsibleCard
from ui.common import icons


# Compteurs affichés dans la carte CONTENU : (attribut projet, icône, singulier, pluriel)
_COUNTERS: tuple[tuple[str, str, str, str], ...] = (
    ("scenes",      "scene",      "scene",      "scenes"),
    ("prefabs",     "prefab",     "prefab",     "prefabs"),
    ("sprites",     "sprite",     "sprite",     "sprites"),
    ("backgrounds", "background", "background", "backgrounds"),
    ("palettes",    "palette",    "palette",    "palettes"),
    ("fonts",       "font",       "font",       "fonts"),
)


# Transitions de scène — mêmes valeurs que les effets de mélange (models/scene.py).
# Le projet définit la transition, une scène peut la surcharger : le
# SceneInspector reprend donc CES libellés et y ajoute son « From project »,
# pour que le même fondu ne soit pas nommé de deux façons selon le panneau.
TRANSITION_LABELS: tuple[tuple[str, str], ...] = (
    ("none",       'projinsp.cut_no_transition'),
    ("fade_black", 'projinsp.fade_to_black'),
    ("fade_white", 'projinsp.fade_to_white'),
)


_COUNTER_KEYS = {'scenes': 'projinsp.count_scenes', 'prefabs': 'projinsp.count_prefabs', 'sprites': 'projinsp.count_sprites', 'backgrounds': 'projinsp.count_backgrounds', 'palettes': 'projinsp.count_palettes', 'fonts': 'projinsp.count_fonts'}


class ProjectInspector(QWidget):
    """Identité éditable du projet (auteur, version, scène de démarrage) +
    inventaire des assets."""

    _LABEL_W = 104

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = InspectorScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        # ── Carte Identité ────────────────────────────────────────
        id_card = CollapsibleCard(label('projinsp.identity'))
        id_inner = id_card.body_layout

        self._ed_author = QLineEdit()
        self._ed_author.setPlaceholderText(label('projinsp.anonymous'))
        self._ed_author.editingFinished.connect(
            lambda: self._set_setting("author", self._ed_author.text().strip()))
        self._row(label('projinsp.author'), self._ed_author, id_inner)

        self._ed_version = QLineEdit()
        self._ed_version.setPlaceholderText("0.1")
        self._ed_version.setMaximumWidth(110)
        self._ed_version.editingFinished.connect(
            lambda: self._set_setting("version", self._ed_version.text().strip()))
        self._row(label('projinsp.version'), self._ed_version, id_inner, stretch=False)

        self._combo_start = QComboBox()
        self._combo_start.setFont(QFont(T.UI, T.MD))
        self._combo_start.setStyleSheet(QSS.combobox)
        self._combo_start.setToolTip(
            label('projinsp.start_scene_tip')
        )
        self._combo_start.currentIndexChanged.connect(self._on_start_scene_changed)
        self._row(label('projinsp.start'), self._combo_start, id_inner)

        layout.addWidget(id_card)

        # ── Carte Contenu ─────────────────────────────────────────
        content_card = CollapsibleCard(label('projinsp.content'))
        content_inner = content_card.body_layout

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self._count_labels: dict[str, QLabel] = {}
        for i, (attr, icon_key, _sing, _plur) in enumerate(_COUNTERS):
            chip, value_lbl = self._stat_chip(icon_key)
            self._count_labels[attr] = value_lbl
            grid.addWidget(chip, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        content_inner.addLayout(grid)

        layout.addWidget(content_card)

        self._hint = QLabel(
            label('projinsp.empty')
        )
        self._hint.setFont(QFont(T.UI, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:2px 4px;")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        layout.addStretch()

    # ── Construction ──────────────────────────────────────────────

    def _row(self, label: str, widget: QWidget, layout: QVBoxLayout,
             stretch: bool = True):
        if isinstance(widget, QLineEdit):
            widget.setFont(QFont(T.MONO, T.MD))
            widget.setStyleSheet(QSS.lineedit)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl.setFixedWidth(self._LABEL_W)
        row.addWidget(lbl)
        row.addWidget(widget, 1 if stretch else 0)
        if not stretch:
            row.addStretch(1)
        layout.addLayout(row)

    def _stat_chip(self, icon_key: str) -> tuple[QWidget, QLabel]:
        """Puce « icône · 3 scènes » — le QLabel retourné porte le texte à
        rafraîchir."""
        chip = QWidget()
        h = QHBoxLayout(chip)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(icons.get(icon_key, icons.COLOR_DEFAULT).pixmap(QSize(14, 14)))
        ico.setFixedWidth(16)
        value = QLabel("—")
        value.setFont(QFont(T.UI, T.SM))
        value.setStyleSheet(f"color:{C.TEXT_NORM};")
        h.addWidget(ico)
        h.addWidget(value, 1)
        return chip, value

    # ── Chargement ────────────────────────────────────────────────

    def load(self, project: Optional[Project]):
        self._project = project
        self._blocking = True
        try:
            enabled = project is not None
            for w in (self._ed_author, self._ed_version, self._combo_start):
                w.setEnabled(enabled)
            self._refresh_fields()
            self._refresh_counts()
        finally:
            self._blocking = False

    def _refresh_fields(self):
        """(Re)synchronise les widgets depuis ProjectSettings — appelé au
        chargement ET après chaque mutation (donc aussi après un undo)."""
        p = self._project
        self._ed_author.setText(p.settings.author if p else "")
        self._ed_version.setText(p.settings.version if p else "")

        self._combo_start.blockSignals(True)
        self._combo_start.clear()
        if p:
            names = [s.name for s in p.scenes]
            start = p.settings.start_scene
            if start and start not in names:
                # Scène de démarrage disparue (supprimée hors éditeur) : on la
                # garde visible plutôt que de la réécrire silencieusement.
                self._combo_start.addItem(label('projinsp.start_not_found', start=start), start)
                names = [start] + names
            for name in names:
                if self._combo_start.findData(name) < 0:
                    self._combo_start.addItem(name, name)
            idx = self._combo_start.findData(start)
            self._combo_start.setCurrentIndex(idx if idx >= 0 else 0)
            self._combo_start.setEnabled(self._combo_start.count() > 0)
        self._combo_start.blockSignals(False)

    def _refresh_counts(self):
        p = self._project
        for attr, _icon, sing, plur in _COUNTERS:
            n = len(getattr(p, attr)) if p else 0
            self._count_labels[attr].setText(label(_COUNTER_KEYS[attr], n=n))

    # ── Mutations ─────────────────────────────────────────────────

    def _persist(self):
        if self._project:
            self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_fields()   # resynchronise l'UI après execute ET undo
        finally:
            self._blocking = False

    def _set_setting(self, field: str, value):
        if self._blocking or not self._project:
            return
        old = getattr(self._project.settings, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            self._project.settings, field, old, value,
            label=f"Projet.{field}", persist_fn=self._persist,
        ))

    def _on_start_scene_changed(self, _idx: int):
        name = self._combo_start.currentData()
        if name is not None:
            self._set_setting("start_scene", name)
