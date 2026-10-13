"""ui/sound_mixer/section_table.py — les sections de boucle d'une musique, en tableau.

Une ligne par section : boucle par icône, défaut par pastille, nom, puis `début → fin` et retrait.
La durée et l'écoute vivent sur la bande des ordres (cf. order_strip). Tout s'édite en place — le bouton « + » crée une ligne prérenseignée dont le nom prend le focus, pas une
fenêtre de saisie. Le tableau écrit directement sur la `Music` qu'on lui donne (le modèle est la
source unique) et dit `changed` ; c'est l'écran qui enregistre.

Les ordres sont ceux de la table BRUTE (cf. order_strip) et la plage est DEMI-OUVERTE dans le modèle :
la colonne « Fin » montre la dernière position INCLUSE (« ordres 04–11 » pour `[4, 12)`).

Un WAV a le même tableau, en MILLISECONDES entières (cf. models/audio.UNIT_MS), la fin y est
exclue comme dans le modèle, et il n'y a pas de bande des ordres pour choisir une plage — « + » ajoute une
section après la dernière.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup, QGridLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QRadioButton, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from core.models.audio import UNIT_MS, UNIT_ORDER
from core.music_structure import MAX_SECTIONS, MIN_SECTION_MS
from ui.common.icons import get as icon
from ui.common.labels import label
from ui.common.theme import C, QSS, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.section_colors import next_color

_ROW_HEIGHT = 26

# Les colonnes : défaut, boucle, nom, début, flèche, fin, retrait.
_COL = dict(default=0, loop=1, name=2, start=3, arrow=4, end=5, remove=6)


class SectionTable(QWidget):
    changed = pyqtSignal()
    section_added = pyqtSignal(object)         # la `MusicSection` que « + » vient de créer

    def __init__(self, parent=None):
        super().__init__(parent)
        self._music = None
        self._extent = 0                           # positions de la table d'ordres (ou millisecondes d'un WAV)
        self._unit = UNIT_ORDER
        self._selection = (0, 0)
        self._name_edits: dict = {}                # nom de section → son QLineEdit
        self._spins: dict = {}                     # id(section) → (début, fin) : les deux compteurs d'une ligne se répondent
        # Une carte par section, empilées : le tableau prend la hauteur de ce qu'il contient.
        self._cards = QVBoxLayout(self)
        self._cards.setContentsMargins(0, 0, 0, 0)
        self._cards.setSpacing(4)
        self._grid: QGridLayout | None = None      # la grille de la carte en cours de construction

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def load(self, music, extent: int, unit: str = UNIT_ORDER) -> None:
        """`extent` : le nombre de positions de la table (ou, pour un WAV, sa durée en ms)."""
        self._music, self._extent, self._unit = music, int(extent), unit
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
        while self._cards.count():
            item = self._cards.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._name_edits.clear()
        self._spins.clear()

    def _rebuild(self) -> None:
        self._clear()
        if self._music is None:
            return
        timed = self._unit == UNIT_MS
        group = QButtonGroup(self)
        for section in self._music.sections:
            self._add_card(section, group)
        if len(self._music.sections) < MAX_SECTIONS:          # au maximum : le bouton n'est plus là
            add = QPushButton("＋  " + label("sndedit.new_section"))
            add.setFont(QFont(T.UI, T.MD))
            add.setCursor(Qt.CursorShape.PointingHandCursor)
            add.setEnabled(self._extent > 0)
            add.setStyleSheet(
                f"QPushButton{{text-align:left; padding:3px 10px; color:{C.TEXT_DIM};"
                f"border:1px dashed {C.BORDER_MID}; background:transparent;}}"
                f"QPushButton:hover{{color:{C.TEXT_NORM}; border-color:{C.ACCENT};}}")
            add.setToolTip(tooltip(title=label("sndedit.new_section"),
                                   body=label("sndedit.new_section_tip_time" if timed else "sndedit.new_section_tip")))
            add.clicked.connect(self._on_add)
            self._cards.addWidget(add)
        # Le tableau se reconstruit parfois alors que l'éditeur est encore caché : la demande de mise en
        # page ne remonte pas, et le conteneur garde la hauteur du tableau d'AVANT (rangées écrasées).
        self.updateGeometry()

    def _add_card(self, section, group: QButtonGroup) -> None:
        """Une carte par section, entièrement éditable sur une seule ligne."""
        card = QFrame()
        card.setObjectName("sectionCard")
        card.setStyleSheet(
            f"QFrame#sectionCard{{background:{C.BG_BASE}; border:1px solid {C.BORDER}; border-radius:4px;}}"
            # Le fond de l'éditeur se pose sur tous ses enfants : sans cela, chaque libellé repeindrait un rectangle clair.
            "QFrame#sectionCard QLabel, QFrame#sectionCard QRadioButton"
            "{background:transparent;}")
        self._grid = QGridLayout(card)
        self._grid.setContentsMargins(8, 4, 8, 4)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnStretch(_COL["name"], 1)
        self._cards.addWidget(card)
        self._fill_card(0, section, group)

    def _fill_card(self, row: int, section, group: QButtonGroup) -> None:
        music = self._music
        timed = self._unit == UNIT_MS

        # Une pastille seule désigne la boucle par défaut, juste avant le bouton Loop.
        default = QRadioButton()
        default.setFixedSize(18, _ROW_HEIGHT)
        default.setChecked(music.loop_section == section.name)
        default.setEnabled(section.loop)
        default.setToolTip(tooltip(title=label("sndedit.col_default"),
                                   body=label("sndedit.default_tip")))
        group.addButton(default)
        default.toggled.connect(lambda on, s=section: on and self._on_default(s))
        self._grid.addWidget(default, row, _COL["default"])

        loop = QToolButton()
        loop.setCheckable(True)
        loop.setChecked(section.loop)
        loop.setIcon(icon("playback_loop", C.TEXT_DIM, C.ACCENT))
        loop.setIconSize(QSize(16, 16))
        loop.setFixedSize(_ROW_HEIGHT, _ROW_HEIGHT)
        loop.setCursor(Qt.CursorShape.PointingHandCursor)
        loop.setStyleSheet(
            f"QToolButton{{border:1px solid transparent; border-radius:3px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{background:{C.BG_SEL}; border-color:{C.ACCENT};}}")
        loop.setToolTip(tooltip(title=label("sndedit.col_loop"), body=label("sndedit.loop_tip")))
        loop.toggled.connect(lambda on, s=section: self._on_loop(s, on))
        self._grid.addWidget(loop, row, _COL["loop"])

        name = QLineEdit(section.name)
        name.setStyleSheet(QSS.lineedit)
        name.setFont(QFont(T.UI, T.MD))
        name.setFixedHeight(_ROW_HEIGHT)
        name.setToolTip(tooltip(title=label("sndedit.col_name")))
        name.editingFinished.connect(lambda e=name, s=section: self._on_rename(s, e))
        self._name_edits[section.name] = name
        self._grid.addWidget(name, row, _COL["name"])

        remove = QToolButton()
        remove.setText("×")
        remove.setFixedSize(22, 22)
        remove.setStyleSheet(QSS.toolbutton_danger)
        remove.setToolTip(tooltip(title=label("sndedit.remove_section")))
        remove.clicked.connect(lambda _c=False, s=section: self._on_remove(s))
        self._grid.addWidget(remove, row, _COL["remove"])

        # Les infobulles portent les intitulés complets ; la flèche rend la
        # plage lisible sans les répéter.
        start, end = self._make_spin(), self._make_spin()
        start.setValue(self._shown_start(section))
        end.setValue(self._shown_end(section))
        start.setToolTip(tooltip(title=label("sndedit.wav_start" if timed else "sndedit.col_start")))
        end.setToolTip(tooltip(title=label("sndedit.wav_end" if timed else "sndedit.col_end")))
        start.valueChanged.connect(lambda v, s=section: self._on_start(s, v))
        end.valueChanged.connect(lambda v, s=section: self._on_end(s, v))
        self._spins[id(section)] = (start, end)
        self._grid.addWidget(start, row, _COL["start"])
        arrow = QLabel("→")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFont(QFont(T.UI, T.MD))
        arrow.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._grid.addWidget(arrow, row, _COL["arrow"])
        self._grid.addWidget(end, row, _COL["end"])

    def _make_spin(self):
        """Le compteur d'un bord : des positions d'ordre, ou des millisecondes pour un WAV. Jamais de virgule."""
        spin = QSpinBox()
        if self._unit == UNIT_MS:
            spin.setSingleStep(10)                     # l'unité (ms) est dite par l'infobulle, pas par un suffixe
            spin.setRange(0, self._extent)
            spin.setFixedWidth(64)
        else:
            spin.setRange(0, max(0, self._extent - 1))
            # Les ordres tiennent sur trois chiffres : un format plus étroit
            # rend de la place au nom sans rendre les flèches difficiles à viser.
            spin.setFixedWidth(52)
        spin.setStyleSheet(QSS.spinbox)
        spin.setFixedHeight(_ROW_HEIGHT)
        return spin

    def _shown_start(self, section):
        return section.start

    def _shown_end(self, section):
        """La fin telle qu'on la montre : exclue pour un WAV comme dans le modèle, INCLUSE pour un module."""
        if self._unit == UNIT_MS:
            return section.end
        return max(0, min(max(0, self._extent - 1), section.end - 1))

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

    def _on_rename(self, section, edit: QLineEdit) -> None:
        new = edit.text().strip()
        taken = {s.name for s in self._music.sections if s is not section}
        if not new or new == section.name or new in taken:
            edit.setText(section.name)               # vide ou en double : on revient, sans fenêtre
            return
        self._music.rename_section(section.name, new)
        self._rebuild()
        self.changed.emit()

    def _on_start(self, section, value) -> None:
        if self._unit == UNIT_MS:
            section.start = value
            if section.end < section.start + MIN_SECTION_MS:
                section.end = min(self._extent, section.start + MIN_SECTION_MS)
                self._show_end(section)
        else:
            section.start = value
            if section.end <= value:
                section.end = value + 1
                self._show_end(section)
        self.changed.emit()

    def _on_end(self, section, value) -> None:
        if self._unit == UNIT_MS:
            section.end = max(value, section.start + MIN_SECTION_MS)
        else:
            section.end = max(value + 1, section.start + 1)
        if self._shown_end(section) != value:        # la fin ne passe pas sous le début
            self._show_end(section)
        self.changed.emit()

    def _show_end(self, section) -> None:
        """Remet à jour le compteur de fin d'une ligne SANS réémettre son signal."""
        spin = self._spins[id(section)][1]
        spin.blockSignals(True)
        spin.setValue(self._shown_end(section))
        spin.blockSignals(False)

    def show_range(self, section) -> None:
        """Le glisser d'une poignée a déplacé cette section : on met ses deux compteurs au diapason, sans
        réémettre de signal."""
        for spin, shown in zip(self._spins[id(section)], (self._shown_start(section), self._shown_end(section))):
            spin.blockSignals(True)
            spin.setValue(shown)
            spin.blockSignals(False)

    def _on_remove(self, section) -> None:
        self._music.remove_section(section.name)
        self._rebuild()
        self.changed.emit()

    def _default_range(self) -> tuple[int, int] | None:
        """La plage d'une section ajoutée sans sélection : le début de la table d'ordres, ou, pour un WAV,
        ce qui suit la dernière section (le milieu de la piste s'il n'y en a pas encore)."""
        if self._unit != UNIT_MS:
            # Une nouvelle section continue naturellement la dernière, sans
            # déplacer les plages déjà définies. Une sélection explicite sur
            # la bande des ordres garde toutefois toujours la priorité.
            start = max((s.end for s in self._music.sections), default=0)
            if start >= self._extent:
                return None
            return start, min(self._extent, start + 4)
        last_end = max((s.end for s in self._music.sections), default=0)
        if not self._music.sections:
            return self._extent // 4, 3 * self._extent // 4
        if last_end + MIN_SECTION_MS <= self._extent:
            return last_end, self._extent
        return max(0, self._extent - 1000), self._extent

    def _on_add(self) -> None:
        start, end = self._selection if self._unit != UNIT_MS else (0, 0)
        if end <= start:
            default_range = self._default_range()
            if default_range is None:
                return
            start, end = default_range
        section = self._music.add_section(start, end, color=next_color(self._music.sections))
        self._rebuild()
        self.section_added.emit(section)
        self.changed.emit()
        # Le nom prend le focus : on tape le sien sans avoir ouvert quoi que ce soit.
        QTimer.singleShot(0, lambda n=section.name: self.focus_name(n))
