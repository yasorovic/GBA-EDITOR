"""ui/sound_mixer/sfx_editor.py — la découpe d'un effet : l'onde de son fichier, deux poignées, le poids ROM qui en résulte.

L'effet garde son fichier intact : `Sfx.trim_start` / `Sfx.trim_end` (ms depuis le début) disent quelle plage le build
rendra (cf. `core/sfx_render.py`, le même code que l'aperçu). Hors des poignées l'onde reste en retrait — ce qui est clair
est ce qui entre en ROM. Les poignées de `WaveformView` sont celles de la boucle d'un WAV de musique : même geste, même
unité (les millisecondes), un seul widget d'onde pour tout l'écran Son.

Le widget ne connaît pas la sauvegarde du projet au-delà de `save_sfx` : il écrit l'effet quand la main se pose (ou à
chaque changement d'un champ) et dit `changed`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.command_dispatcher import get_dispatcher
from core.models.audio import FADE_MAX_FRAMES, Sfx
from core.sfx_render import MIN_TRIM_MS, effective_rate, fade_out_of, planned_frames, read_wav, trim_window
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.waveform_view import WaveformView, peak_envelope

_CACHE = 8           # les ondes gardées : un effet se relit en un clic, pas en un décodage


class SfxEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._sfx: Optional[Sfx] = None
        self._total_ms = 0
        self._frames = 0
        self._rate = 0
        self._blocking = False
        self._peaks: dict = {}                      # (chemin, date) -> (crêtes, secondes, frames, taux)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        self._wave = WaveformView()
        self._wave.show_mode_switch(False)
        self._wave.show_cue(False)
        self._wave.setMinimumHeight(140)
        self._wave.setToolTip(tooltip(title=label("sfxedit.wave_title"), body=label("sfxedit.wave_tip")))
        self._wave.loop_moving.connect(self._on_dragging)
        self._wave.loop_changed.connect(lambda start, end: self._commit(start, end))
        layout.addWidget(self._wave, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._start = self._spin("sfxedit.start", "sfxedit.start_tip", row)
        self._end = self._spin("sfxedit.end", "sfxedit.end_tip", row)
        self._fade = self._spin("sfxedit.fade", "sfxedit.fade_tip", row, suffix=" fr", on_change=self._on_fade)
        self._reset = QPushButton(label("sfxedit.reset"))
        self._reset.setFont(QFont(T.UI, T.MD))
        self._reset.setToolTip(tooltip(title=label("sfxedit.reset"), body=label("sfxedit.reset_tip")))
        self._reset.clicked.connect(lambda: self._commit(0, self._total_ms))
        row.addWidget(self._reset)
        row.addStretch(1)
        layout.addLayout(row)

        self._summary = QLabel("")
        self._summary.setFont(QFont(T.UI, T.SM))
        self._summary.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

    def _spin(self, title_key: str, tip_key: str, row: QHBoxLayout, suffix: str = " ms", on_change=None) -> QSpinBox:
        caption = QLabel(label(title_key))
        caption.setFont(QFont(T.UI, T.SM))
        caption.setStyleSheet(f"color:{C.TEXT_DIM};")
        spin = QSpinBox()
        spin.setSuffix(suffix)
        spin.setFont(QFont(T.MONO, T.MD))
        spin.setStyleSheet(
            f"QSpinBox{{background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};"
            "border-radius:3px;padding:2px;}")
        spin.setToolTip(tooltip(title=label(title_key), body=label(tip_key)))
        spin.valueChanged.connect(on_change or self._on_spin)
        row.addWidget(caption)
        row.addWidget(spin)
        return spin

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def load(self, project, sfx: Optional[Sfx]) -> None:
        """Montre l'onde du fichier de `sfx` et sa découpe ; sans effet ou sans fichier lisible, rien à régler."""
        self._project, self._sfx = project, sfx
        self._total_ms = self._frames = self._rate = 0
        shown = None
        path = project.asset_abs(sfx.asset) if project is not None and sfx is not None and sfx.asset else None
        if path is not None and path.is_file():
            shown = self._read(path)
        if shown is None:
            self._wave.set_envelope(np.zeros((0, 2), dtype=np.float32), 0.0)
            self._wave.set_loop_ms(None)
            self._wave.set_editable(False)
            self._sync_fields()
            return
        peaks, seconds, self._frames, self._rate = shown
        self._total_ms = round(seconds * 1000)
        self._wave.set_envelope(peaks, seconds)
        self._wave.set_editable(True)
        self._sync_fields()

    def refresh(self) -> None:
        """Le taux ou le fichier a changé ailleurs (l'inspecteur) : le poids annoncé suit, l'onde ne bouge pas."""
        self._update_summary()

    def _read(self, path: Path):
        try:
            key = (path, path.stat().st_mtime_ns)
        except OSError:
            return None
        if key in self._peaks:
            return self._peaks[key]
        try:
            got = read_wav(path)
        except Exception:                           # un fichier abîmé : `check_audio_file` le dit au validateur
            return None
        if got is None:
            return None
        data, rate, channels = got
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)
        if data.size == 0 or rate <= 0:
            return None
        mono = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
        peaks, seconds = peak_envelope(np.stack([mono, mono], axis=1), rate)
        if len(self._peaks) >= _CACHE:
            self._peaks.pop(next(iter(self._peaks)))
        self._peaks[key] = (peaks, seconds, int(data.size), int(rate))
        return self._peaks[key]

    # ── Les champs et l'onde disent la même plage ─────────────────

    def _window(self) -> tuple[int, int]:
        return trim_window(self._sfx, self._total_ms)

    def _sync_fields(self) -> None:
        """Pose la plage de l'effet sur l'onde et les deux champs, sans rien écrire."""
        ready = self._sfx is not None and self._total_ms > 0
        self._blocking = True
        for spin in (self._start, self._end):
            spin.setEnabled(ready)
            spin.setRange(0, max(0, self._total_ms))
        self._fade.setEnabled(ready)
        self._fade.setRange(0, FADE_MAX_FRAMES)
        if ready:
            start, end = self._window()
            self._start.setValue(start)
            self._end.setValue(end)
            self._fade.setValue(fade_out_of(self._sfx))
            self._wave.set_loop_ms((start, end))
            ramp_ms = min(end - start, round(fade_out_of(self._sfx) * 1000 / 60))      # un fondu ne dépasse pas la plage gardée
            self._wave.set_ramp((end - ramp_ms, end) if ramp_ms > 0 else None)
        else:
            self._wave.set_ramp(None)
        self._reset.setEnabled(ready and (self._sfx.trim_start > 0 or self._sfx.trim_end > 0))
        self._blocking = False
        self._update_summary()

    def _on_dragging(self, start: int, end: int) -> None:
        """Pendant le glisser : les champs et le poids suivent, rien n'est encore écrit."""
        self._blocking = True
        self._start.setValue(start)
        self._end.setValue(end)
        self._blocking = False
        self._update_summary(start, end)

    def _on_spin(self, _value: int) -> None:
        if self._blocking or self._sfx is None:
            return
        self._commit(self._start.value(), self._end.value())

    def _on_fade(self, value: int) -> None:
        """Le fondu de sortie, en frames : écrit tout de suite, comme les champs de la plage."""
        if self._blocking or self._sfx is None or self._project is None:
            return
        self._sfx.fade_out = int(value)
        with get_dispatcher().suspended():
            self._project.save_sfx(self._sfx)
        self._sync_fields()
        self.changed.emit()

    def _commit(self, start: int, end: int) -> None:
        """Écrit la plage `start`–`end` (ms) dans l'effet. Une plage qui couvre tout le fichier s'écrit « pas de découpe » :
        la fin à 0 suit un fichier qu'on remplacerait par un plus long."""
        if self._sfx is None or self._project is None or self._total_ms <= 0:
            return
        start = max(0, min(int(start), self._total_ms - MIN_TRIM_MS))
        end = max(start + MIN_TRIM_MS, min(int(end), self._total_ms))
        self._sfx.trim_start = start
        self._sfx.trim_end = 0 if end >= self._total_ms else end
        with get_dispatcher().suspended():
            self._project.save_sfx(self._sfx)
        self._sync_fields()
        self.changed.emit()

    def _update_summary(self, start: Optional[int] = None, end: Optional[int] = None) -> None:
        if self._sfx is None or self._project is None or self._total_ms <= 0:
            self._summary.setText(label("sfxedit.no_file") if self._sfx is not None else "")
            return
        if start is None or end is None:
            start, end = self._window()
        target = effective_rate(self._sfx, self._project.settings)
        whole = planned_frames(Sfx(name="whole"), self._frames, self._rate, target)
        kept = planned_frames(Sfx(name="kept", trim_start=start, trim_end=0 if end >= self._total_ms else end),
                              self._frames, self._rate, target)
        if start <= 0 and end >= self._total_ms:
            self._summary.setText(label("sfxedit.summary_whole", total=self._total_ms, kb=f"{whole / 1024:.1f}"))
        else:
            self._summary.setText(label("sfxedit.summary", start=start, end=end, kept=end - start,
                                        total=self._total_ms, kb=f"{kept / 1024:.1f}", whole=f"{whole / 1024:.1f}"))
