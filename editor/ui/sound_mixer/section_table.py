"""ui/sound_mixer/section_table.py — les sections de boucle d'un module, en tableau.

Une ligne par section : boucle, par défaut, couleur, nom, début, fin, durée, écoute, retrait. Tout
s'édite en place — le bouton « + » crée une ligne prérenseignée dont le nom prend le focus, pas une
fenêtre de saisie. Le tableau écrit directement sur la `Music` qu'on lui donne (le modèle est la
source unique) et dit `changed` ; c'est l'écran qui enregistre.

Les ordres sont ceux de la table BRUTE (cf. order_strip) et la plage est DEMI-OUVERTE dans le modèle :
la colonne « Fin » montre la dernière position INCLUSE (« ordres 04–11 » pour `[4, 12)`).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
    QSpinBox, QToolButton, QWidget,
)

from ui.common.icons import get as _ico
from ui.common.labels import label
from ui.common.theme import C, QSS, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.section_colors import next_color, section_color, section_palette

# Les colonnes : boucle, par défaut, couleur, nom, début, fin, durée, écoute, retrait.
_COL = dict(loop=0, default=1, color=2, name=3, start=4, end=5, length=6, preview=7, remove=8)


def _duration_text(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"


class SectionTable(QWidget):
    changed = pyqtSignal()
    preview_requested = pyqtSignal(object)         # la `MusicSection` à écouter

    def __init__(self, parent=None):
        super().__init__(parent)
        self._music = None
        self._extent = 0                           # positions de la table d'ordres
        self._seconds_of: Callable | None = None
        self._selection = (0, 0)
        self._name_edits: dict = {}                # nom de section → son QLineEdit
        self._spins: dict = {}                     # id(section) → (début, fin) : les deux compteurs d'une ligne se répondent
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(5)
        self._grid.setColumnStretch(_COL["name"], 1)

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def load(self, music, extent: int, seconds_of: Callable | None = None) -> None:
        """`extent` : le nombre de positions de la table ; `seconds_of(début, fin)` : la durée de
        cette plage, pour la colonne de droite (None = on ne sait pas la dire)."""
        self._music, self._extent, self._seconds_of = music, int(extent), seconds_of
        self._rebuild()

    def set_selection(self, start: int, end: int) -> None:
        """La plage choisie sur la bande des ordres : c'est celle que « + » donne à la nouvelle section."""
        self._selection = (start, end)

    def focus_name(self, name: str) -> None:
        edit = self._name_edits.get(name)
        if edit is not None:
            edit.setFocus()
            edit.selectAll()

    # ── Construction ──────────────────────────────────────────────

    def _clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._name_edits.clear()
        self._spins.clear()

    def _rebuild(self) -> None:
        self._clear()
        if self._music is None:
            return
        for key, text in (("loop", "sndedit.col_loop"), ("default", "sndedit.col_default"),
                          ("color", "sndedit.col_color"), ("name", "sndedit.col_name"),
                          ("start", "sndedit.col_start"), ("end", "sndedit.col_end"),
                          ("length", "sndedit.col_length")):
            head = QLabel(label(text))
            head.setFont(QFont(T.UI, T.SM))
            head.setStyleSheet(f"color:{C.TEXT_DIM};")
            self._grid.addWidget(head, 0, _COL[key])
        group = QButtonGroup(self)
        for rank, section in enumerate(self._music.sections):
            self._add_row(1 + rank, rank, section, group)
        add = QPushButton("＋  " + label("sndedit.new_section"))
        add.setFont(QFont(T.UI, T.MD))
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setEnabled(self._extent > 0)
        add.setStyleSheet(
            f"QPushButton{{text-align:left; padding:6px 10px; color:{C.TEXT_DIM};"
            f"border:1px dashed {C.BORDER_MID}; background:transparent;}}"
            f"QPushButton:hover{{color:{C.TEXT_NORM}; border-color:{C.ACCENT};}}")
        add.setToolTip(tooltip(title=label("sndedit.new_section"),
                               body=label("sndedit.new_section_tip")))
        add.clicked.connect(self._on_add)
        self._grid.addWidget(add, 1 + len(self._music.sections), 0, 1, len(_COL))
        # Le tableau se reconstruit parfois alors que l'éditeur est encore caché : la demande de mise en
        # page ne remonte pas, et le conteneur garde la hauteur du tableau d'AVANT (rangées écrasées).
        self.updateGeometry()

    def _add_row(self, row: int, rank: int, section, group: QButtonGroup) -> None:
        music = self._music
        last = max(0, self._extent - 1)

        loop = QCheckBox()
        loop.setStyleSheet(QSS.checkbox)
        loop.setChecked(section.loop)
        loop.setToolTip(tooltip(title=label("sndedit.col_loop"), body=label("sndedit.loop_tip")))
        loop.toggled.connect(lambda on, s=section: self._on_loop(s, on))
        self._grid.addWidget(loop, row, _COL["loop"])

        default = QRadioButton()
        default.setChecked(music.loop_section == section.name)
        default.setEnabled(section.loop)
        default.setToolTip(tooltip(title=label("sndedit.col_default"),
                                   body=label("sndedit.default_tip")))
        group.addButton(default)
        default.toggled.connect(lambda on, s=section: on and self._on_default(s))
        self._grid.addWidget(default, row, _COL["default"])

        color = QToolButton()
        color.setFixedSize(24, 24)
        color.setCursor(Qt.CursorShape.PointingHandCursor)
        color.setStyleSheet(
            f"QToolButton{{background:{section_color(section, rank).name()};"
            f"border:1px solid {C.BORDER_MID};}}"
            f"QToolButton:hover{{border-color:{C.ACCENT};}}")
        color.setToolTip(tooltip(title=label("sndedit.col_color"), body=label("sndedit.color_tip")))
        color.clicked.connect(lambda _c=False, s=section, r=rank: self._on_color(s, r))
        self._grid.addWidget(color, row, _COL["color"])

        name = QLineEdit(section.name)
        name.setStyleSheet(QSS.lineedit)
        name.setFont(QFont(T.UI, T.MD))
        name.editingFinished.connect(lambda e=name, s=section: self._on_rename(s, e))
        self._name_edits[section.name] = name
        self._grid.addWidget(name, row, _COL["name"])

        start = QSpinBox()
        start.setStyleSheet(QSS.spinbox)
        start.setRange(0, last)
        start.setValue(section.start)
        start.setFixedWidth(64)
        start.valueChanged.connect(lambda v, s=section: self._on_start(s, v))
        self._grid.addWidget(start, row, _COL["start"])

        end = QSpinBox()
        end.setStyleSheet(QSS.spinbox)
        end.setRange(0, last)
        end.setValue(max(0, min(last, section.end - 1)))     # inclusive à l'écran, demi-ouvert dans le modèle
        end.setFixedWidth(64)
        end.valueChanged.connect(lambda v, s=section: self._on_end(s, v))
        self._grid.addWidget(end, row, _COL["end"])
        self._spins[id(section)] = (start, end)

        length = QLabel(self._length_text(section))
        length.setFont(QFont(T.MONO, T.SM))
        length.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._grid.addWidget(length, row, _COL["length"])

        preview = QToolButton()
        preview.setIcon(_ico("playback_play", C.TEXT_DIM, C.ACCENT))
        preview.setIconSize(QSize(14, 14))
        preview.setFixedSize(30, 24)
        preview.setStyleSheet(QSS.toolbutton_icon)
        preview.setToolTip(tooltip(title=label("sndedit.preview_section"),
                                   body=label("sndedit.preview_section_tip")))
        preview.clicked.connect(lambda _c=False, s=section: self.preview_requested.emit(s))
        self._grid.addWidget(preview, row, _COL["preview"])

        remove = QToolButton()
        remove.setText("×")
        remove.setFixedSize(24, 24)
        remove.setStyleSheet(QSS.toolbutton_danger)
        remove.setToolTip(tooltip(title=label("sndedit.remove_section")))
        remove.clicked.connect(lambda _c=False, s=section: self._on_remove(s))
        self._grid.addWidget(remove, row, _COL["remove"])

    def _length_text(self, section) -> str:
        if self._seconds_of is None:
            return "—"
        return _duration_text(self._seconds_of(section.start, section.end))

    # ── Les gestes ────────────────────────────────────────────────

    def _on_loop(self, section, on: bool) -> None:
        section.loop = on
        if not on and self._music.loop_section == section.name:
            self._music.loop_section = next((s.name for s in self._music.sections
                                             if s.loop and s is not section), "")
        elif on and not self._music.loop_section:
            self._music.loop_section = section.name
        self._rebuild()
        self.changed.emit()

    def _on_default(self, section) -> None:
        self._music.loop_section = section.name
        self.changed.emit()

    def _on_color(self, section, rank: int) -> None:
        palette = section_palette()
        current = section_color(section, rank).name().lower()
        index = next((i for i, c in enumerate(palette) if c.lower() == current), -1)
        section.color = palette[(index + 1) % len(palette)]
        self._rebuild()
        self.changed.emit()

    def _on_rename(self, section, edit: QLineEdit) -> None:
        new = edit.text().strip()
        taken = {s.name for s in self._music.sections if s is not section}
        if not new or new == section.name or new in taken:
            edit.setText(section.name)               # vide ou en double : on revient, sans fenêtre
            return
        self._music.rename_section(section.name, new)
        self._rebuild()
        self.changed.emit()

    def _on_start(self, section, value: int) -> None:
        section.start = value
        if section.end <= value:
            section.end = value + 1
            self._show_end(section, value)
        self.changed.emit()

    def _on_end(self, section, value: int) -> None:
        section.end = max(value + 1, section.start + 1)
        if section.end - 1 != value:                 # la fin ne passe pas sous le début
            self._show_end(section, section.end - 1)
        self.changed.emit()

    def _show_end(self, section, inclusive: int) -> None:
        """Remet à jour le compteur de fin d'une ligne SANS réémettre son signal."""
        spin = self._spins[id(section)][1]
        spin.blockSignals(True)
        spin.setValue(inclusive)
        spin.blockSignals(False)

    def _on_remove(self, section) -> None:
        self._music.remove_section(section.name)
        self._rebuild()
        self.changed.emit()

    def _on_add(self) -> None:
        start, end = self._selection
        if end <= start:
            start, end = 0, min(self._extent, 4)
        section = self._music.add_section(start, end, color=next_color(self._music.sections))
        self._rebuild()
        self.changed.emit()
        # Le nom prend le focus : on tape le sien sans avoir ouvert quoi que ce soit.
        QTimer.singleShot(0, lambda n=section.name: self.focus_name(n))
