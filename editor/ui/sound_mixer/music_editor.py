"""ui/sound_mixer/music_editor.py — la colonne centrale de l'écran Son pour une musique ou un jingle.

Une seule composition, deux zones de structure — celle que le FORMAT du fichier permet :

  - un MODULE (`.mod` `.s3m` `.xm` `.it`) : la bande des ordres et le tableau des sections. La ROM
    y boucle à la position d'ordre près, et peut garder plusieurs sections nommées ;
  - un WAV : une forme d'onde à deux poignées. La ROM y boucle à l'échantillon près, mais n'a qu'UNE
    boucle, et la fin de la piste n'est jamais jouée (cf. models/audio.UNIT_MS).

Ce qu'on dessine est le `Track` du deck (cf. box_playback.track_for), donc ce qu'on entend. L'éditeur
écrit directement sur la `Music` reçue et dit `changed` ; c'est l'écran qui enregistre. Il ne règle
ni le volume ni le tempo : ce sont des réglages de l'asset, dans l'inspecteur.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import GBA_MIX_RATE
from core.models.audio import UNIT_MS, UNIT_ORDER
from core.music_structure import music_problems, source_unit, ERROR
from ui.common.labels import label
from ui.common.theme import C, QSS, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.order_strip import OrderStrip
from ui.sound_mixer.section_colors import section_color
from ui.sound_mixer.section_table import SectionTable
from ui.sound_mixer.waveform_view import WaveformView


def _title(text: str) -> QLabel:
    title = QLabel(text)
    title.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
    title.setStyleSheet(f"color:{C.TEXT_HI};")
    return title


class MusicEditor(QWidget):
    changed = pyqtSignal()
    preview_section = pyqtSignal(object)           # la `MusicSection` à écouter

    def __init__(self, track_provider: Callable, parent=None):
        """`track_provider(project, music)` rend le `Track` à dessiner, ou None."""
        super().__init__(parent)
        self._track_provider = track_provider
        self._project = None
        self._music = None
        self._track = None
        self._module = None
        self._unit: Optional[str] = None
        self._mismatched = False                   # des sections d'une autre unité que le fichier
        self._sections_on = True                   # faux pour un jingle : il ne boucle pas, il n'a pas de section
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(QSS.scroll_area)
        root.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        # ── En-tête : le nom, ce qu'est le fichier, et si la musique est bonne à construire ──
        head = QHBoxLayout()
        names = QVBoxLayout()
        names.setSpacing(2)
        self._title = QLabel()
        self._title.setFont(QFont(T.UI, T.XXL, QFont.Weight.DemiBold))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};")
        self._subtitle = QLabel()
        self._subtitle.setFont(QFont(T.UI, T.MD))
        self._subtitle.setStyleSheet(f"color:{C.TEXT_DIM};")
        names.addWidget(self._title)
        names.addWidget(self._subtitle)
        head.addLayout(names, 1)
        self._status = QLabel()
        self._status.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFixedHeight(26)
        head.addWidget(self._status, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        # ── Ce qui remplace la structure quand il n'y a rien à montrer ──
        self._message = QLabel()
        self._message.setFont(QFont(T.UI, T.MD))
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:24px;")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._message)

        # ── Les sections écrites pour un autre type de fichier ne se réinterprètent jamais ──
        self._mismatch = QFrame()
        self._mismatch.setStyleSheet(
            f"QFrame{{background:{C.BG_RAISED}; border:1px solid {C.ACCENT_WARM};}}")
        mismatch_lay = QHBoxLayout(self._mismatch)
        mismatch_text = QLabel(label("sndedit.unit_mismatch"))
        mismatch_text.setWordWrap(True)
        mismatch_text.setStyleSheet(f"color:{C.TEXT_NORM}; border:none;")
        reset = QPushButton(label("sndedit.reset"))
        reset.setStyleSheet(QSS.button_neutral)
        reset.clicked.connect(self._reset_sections)
        mismatch_lay.addWidget(mismatch_text, 1)
        mismatch_lay.addWidget(reset)
        lay.addWidget(self._mismatch)

        # ── La structure ──
        self._structure = QWidget()
        s_lay = QVBoxLayout(self._structure)
        s_lay.setContentsMargins(0, 0, 0, 0)
        s_lay.setSpacing(8)
        s_lay.addWidget(_title(label("sndedit.song_overview")))
        self._wave = WaveformView()
        self._wave.loop_moving.connect(self._on_wave_moving)
        self._wave.loop_changed.connect(self._on_wave_loop)
        s_lay.addWidget(self._wave)

        # Un module : la bande des ordres et le tableau.
        self._module_zone = QWidget()
        m_lay = QVBoxLayout(self._module_zone)
        m_lay.setContentsMargins(0, 0, 0, 0)
        m_lay.setSpacing(8)
        m_lay.addWidget(_title(label("sndedit.structure_orders")))
        self._strip = OrderStrip()
        self._strip.selection_changed.connect(lambda a, b: self._table.set_selection(a, b))
        m_lay.addWidget(self._strip)
        m_lay.addWidget(_title(label("sndedit.loop_sections")))
        self._table = SectionTable()
        self._table.changed.connect(self._on_table_changed)
        self._table.preview_requested.connect(self.preview_section)
        m_lay.addWidget(self._table)
        s_lay.addWidget(self._module_zone)

        # Un WAV : la boucle et ses deux bornes.
        self._wav_zone = QWidget()
        w_lay = QHBoxLayout(self._wav_zone)
        w_lay.setContentsMargins(0, 0, 0, 0)
        w_lay.setSpacing(10)
        self._wav_loop = QCheckBox(label("sndedit.wav_loop"))
        self._wav_loop.setStyleSheet(QSS.checkbox)
        self._wav_loop.setToolTip(tooltip(title=label("sndedit.wav_loop"),
                                          body=label("sndedit.wav_loop_tip")))
        self._wav_loop.toggled.connect(self._on_wav_toggled)
        self._wav_start = self._seconds_spin(self._on_wav_spin)
        self._wav_end = self._seconds_spin(self._on_wav_spin)
        w_lay.addWidget(self._wav_loop)
        w_lay.addWidget(QLabel(label("sndedit.wav_start")))
        w_lay.addWidget(self._wav_start)
        w_lay.addWidget(QLabel(label("sndedit.wav_end")))
        w_lay.addWidget(self._wav_end)
        w_lay.addStretch(1)
        s_lay.addWidget(self._wav_zone)
        lay.addWidget(self._structure)
        lay.addStretch(1)
        self._blank()

    @staticmethod
    def _seconds_spin(slot) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setStyleSheet(QSS.spinbox)
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        spin.setSuffix(" s")
        spin.setFixedWidth(112)
        spin.valueChanged.connect(slot)
        return spin

    # ── Chargement ────────────────────────────────────────────────

    def _blank(self, text: str = "") -> None:
        """Rien à structurer : on dit pourquoi, au lieu de montrer une zone vide."""
        self._message.setText(text)
        self._message.setVisible(bool(text))
        self._structure.setVisible(False)
        self._mismatch.setVisible(False)
        self._mismatched = False
        self._status.setVisible(False)

    def load(self, project, music, sections: bool = True) -> None:
        """`sections=False` pour un jingle : on montre la forme d'onde, pas de quoi régler une boucle
        que la ROM ne jouera pas."""
        self._project, self._music, self._sections_on = project, music, sections
        self.reload()

    def reload(self) -> None:
        """Relit le fichier et le `Track` : à appeler quand le FICHIER ou ce qui change son rendu
        (tempo, hauteur, taux) a changé. Le cache du lecteur évite de refaire un rendu inutile."""
        music, project = self._music, self._project
        self._track = self._module = self._unit = None
        if music is None or project is None:
            self._title.setText("")
            self._subtitle.setText("")
            return self._blank()
        self._title.setText(music.name)
        path = project.asset_abs(music.asset) if music.asset else None
        if path is None or not path.exists():
            self._subtitle.setText("")
            return self._blank(label("sndedit.no_file"))
        self._unit = source_unit(path)
        if self._unit is None:
            self._subtitle.setText(path.name)
            return self._blank(label("sndedit.unreadable"))
        try:
            if self._unit == UNIT_ORDER:
                self._module = load_module(path)
            self._track = self._track_provider(project, music)
        except Exception as exc:  # tolerated: unreadable file, said on screen — the validator names the cause
            self._subtitle.setText(path.name)
            return self._blank(label("sndedit.unreadable_why", reason=str(exc)))
        if self._track is None:
            self._subtitle.setText(path.name)
            return self._blank(label("sndedit.unreadable"))

        # Une musique sans section prend l'unité de son fichier ; avec des sections d'une autre unité,
        # on le dit (jamais réinterprétées en silence).
        if not music.sections:
            music.unit = self._unit
        self._message.setVisible(False)
        self._structure.setVisible(True)
        self._wave.set_track(self._track.pcm, GBA_MIX_RATE)
        self._subtitle.setText(f"{path.name}  ·  {self._kind_text()}")
        self._mismatched = self._sections_on and bool(music.sections) and music.unit != self._unit
        self._mismatch.setVisible(self._mismatched)
        editable = not self._mismatched and self._sections_on
        self._module_zone.setVisible(self._unit == UNIT_ORDER and editable)
        self._wav_zone.setVisible(self._unit == UNIT_MS and editable)
        self._wave.set_editable(self._unit == UNIT_MS and editable)
        self._refresh_sections()
        self._refresh_status(path)
        self._structure.updateGeometry()

    def _kind_text(self) -> str:
        if self._module is None:
            return label("sndedit.kind_wav", seconds=f"{self._wave.seconds:.1f}")
        return "  ·  ".join((
            label("sndedit.kind_module"),
            label("sndedit.module_orders", n=len(self._module.order)),
            label("sndedit.module_patterns", n=len(self._module.patterns)),
            label("sndedit.module_channels", n=self._module.num_channels)))

    # ── Les sections ──────────────────────────────────────────────

    def _seconds_of(self, start: int, end: int) -> float:
        """La durée de la plage d'ordres [début, fin), lue sur les repères du rendu."""
        marks, total = self._track.marks, self._track.pcm.shape[0]
        if start not in marks:
            return 0.0
        return max(0, marks.get(end, total) - marks[start]) / GBA_MIX_RATE

    def _refresh_sections(self) -> None:
        """Remet à jour tout ce qui dessine les sections, depuis la `Music`."""
        music = self._music
        if self._unit == UNIT_ORDER and self._module is not None and not self._mismatched:
            self._strip.set_orders(self._module.order)
            self._strip.set_sections(music.sections)
            self._table.load(music, len(self._module.order), self._seconds_of)
            self._wave.set_bands([
                (self._seconds_of(0, s.start) if s.start else 0.0,
                 self._seconds_of(0, s.end), section_color(s, rank))
                for rank, s in enumerate(music.sections)
                if s.start in self._track.marks])
            self._wave.set_loop_ms(None)
        elif self._unit == UNIT_MS and not self._mismatched:
            self._wave.set_bands([])
            region = next((s for s in music.sections if s.name == music.loop_section), None)
            self._wave.set_loop_ms((region.start, region.end) if region else None)
            self._show_wav_loop(region)

    def _show_wav_loop(self, region) -> None:
        """Pose la case et les deux bornes d'après la boucle (sans réémettre de signal)."""
        for widget in (self._wav_loop, self._wav_start, self._wav_end):
            widget.blockSignals(True)
        total = self._wave.seconds
        self._wav_start.setRange(0.0, total)
        self._wav_end.setRange(0.0, total)
        self._wav_loop.setChecked(region is not None)
        self._wav_start.setValue(region.start / 1000 if region else 0.0)
        self._wav_end.setValue(region.end / 1000 if region else total)
        self._wav_start.setEnabled(region is not None)
        self._wav_end.setEnabled(region is not None)
        for widget in (self._wav_loop, self._wav_start, self._wav_end):
            widget.blockSignals(False)

    def _refresh_status(self, path) -> None:
        """« Prête pour le build » ou le nombre de choses à corriger — les mêmes contrôles que le
        validateur, donc ce que le build dira."""
        module = self._module
        problems = music_problems(self._music, path, lambda _p: module)
        errors = sum(1 for level, _m in problems if level == ERROR)
        self._status.setVisible(True)
        if errors:
            self._status.setText(label("sndedit.status_fix", n=errors))
            color = C.ACCENT_RED
        else:
            self._status.setText(label("sndedit.status_ready"))
            color = C.TECH_OK
        self._status.setStyleSheet(
            f"color:{color}; border:1px solid {color}; padding:0 10px; background:transparent;")
        self._status.setToolTip("\n".join(message for _level, message in problems))

    def _commit(self) -> None:
        """Une section a bougé : on redessine tout ce qui la montre, puis l'écran enregistre."""
        self._refresh_sections()
        path = self._project.asset_abs(self._music.asset) if self._music.asset else None
        if path is not None:
            self._refresh_status(path)
        self.changed.emit()

    # ── Les gestes : un module ────────────────────────────────────

    def _on_table_changed(self) -> None:
        # Le tableau se reconstruit lui-même ; la bande et la forme d'onde, elles, suivent.
        music = self._music
        self._strip.set_sections(music.sections)
        self._wave.set_bands([
            (self._seconds_of(0, s.start) if s.start else 0.0,
             self._seconds_of(0, s.end), section_color(s, rank))
            for rank, s in enumerate(music.sections) if s.start in self._track.marks])
        path = self._project.asset_abs(music.asset) if music.asset else None
        if path is not None:
            self._refresh_status(path)
        self.changed.emit()

    # ── Les gestes : un WAV ───────────────────────────────────────

    def _on_wav_toggled(self, on: bool) -> None:
        music, total_ms = self._music, round(self._wave.seconds * 1000)
        if on:
            music.set_single_loop(total_ms // 4, 3 * total_ms // 4)
        elif music.loop_section:
            music.remove_section(music.loop_section)
        self._commit()

    def _on_wav_spin(self, _value: float) -> None:
        start, end = round(self._wav_start.value() * 1000), round(self._wav_end.value() * 1000)
        if end <= start:
            return                                          # on attend que les deux bornes se suivent
        self._music.set_single_loop(start, end)
        self._commit()

    def _on_wave_moving(self, start: int, end: int) -> None:
        for spin, ms in ((self._wav_start, start), (self._wav_end, end)):
            spin.blockSignals(True)
            spin.setValue(ms / 1000)
            spin.blockSignals(False)

    def _on_wave_loop(self, start: int, end: int) -> None:
        self._music.set_single_loop(start, end)
        self._commit()

    # ── Divers ────────────────────────────────────────────────────

    def _reset_sections(self) -> None:
        """Les sections d'un autre type de fichier : on les efface (l'auteur l'a demandé)."""
        self._music.sections.clear()
        self._music.loop_section = ""
        self._music.unit = self._unit
        self.reload()
        self.changed.emit()

    def set_playhead_seconds(self, seconds: float) -> None:
        if self._track is None:
            return
        self._wave.set_playhead(seconds)
        if self._module is not None:
            self._strip.set_playhead_order(self._track.order_at(int(seconds * GBA_MIX_RATE)))
