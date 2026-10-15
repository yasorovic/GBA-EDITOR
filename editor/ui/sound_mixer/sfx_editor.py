"""ui/sound_mixer/sfx_editor.py — la découpe d'un effet : l'onde de son fichier, la barre de découpe dessous, le poids ROM qui en résulte.

Comme l'éditeur d'une musique, il montre aussi le son TEL QUE LA ROM LE JOUERA — le `Track` de l'aperçu (cf.
`box_playback.track_for`, qui rend le fichier découpé, fondu et réglé en hauteur) : la barre du CANAL qu'il occupe parmi
ceux du projet, et l'oscilloscope (bascule Onde | Scope de l'onde). La poignée du fondu de sortie se glisse sur le bas de l'onde.

L'effet garde son fichier intact : `Sfx.trim_start` / `Sfx.trim_end` (ms depuis le début) disent quelle plage le build
rendra (cf. `core/sfx_render.py`, le même code que l'aperçu). Hors de la plage l'onde reste en retrait — ce qui est clair
est ce qui entre en ROM. La plage se règle à la `TrimBar` (la même que celle d'une musique ou d'un jingle WAV) et aux deux
champs ; l'onde, elle, n'a plus de poignée de découpe : elle montre.

Volume, hauteur, variation aléatoire de la hauteur et les deux fondus se règlent à la table de mixage (`mix_panel`, les
`MixFaders` d'une musique), que l'écran monte dans sa colonne de droite.

Le widget ne connaît pas la sauvegarde du projet au-delà de `save_sfx` : il écrit l'effet quand la main se pose (ou à
chaque changement d'un champ) et dit `changed`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from core.engine_emulation.module_render import GBA_MIX_RATE
from core.models.audio import Sfx
from core.sfx_render import effective_rate, planned_frames, read_wav
from core.wav_edit import MIN_TRIM_MS, fade_in_of, fade_out_of, trim_window
from ui.common.deferred_writes import schedule_save
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.common.unit_spin import UnitSpin
from ui.sound_mixer.channel_meters import ChannelMeters
from ui.sound_mixer.mix_faders import SFX_FADERS, SFX_FADES, SFX_PAN, MixFaders, mix_panel
from ui.sound_mixer.trim_bar import TrimBar
from ui.sound_mixer.waveform_view import WaveformView, peak_envelope

_CACHE = 8           # les ondes gardées : un effet se relit en un clic, pas en un décodage
_TRACK_SILENCE_MS = 150      # le silence après lequel l'aperçu est re-rendu pour le dernier réglage


class SfxEditor(QWidget):
    changed = pyqtSignal()
    original_rate_toggled = pyqtSignal(bool)        # A/B du taux : l'aperçu joue-t-il le fichier à son propre taux ?

    def __init__(self, track_provider=None, parent=None):
        """`track_provider(project, sfx)` rend le `Track` que l'aperçu jouerait, ou None (sans lui : ni canal, ni scope)."""
        super().__init__(parent)
        self._track_provider = track_provider
        self._track = None
        self._live_source = None                    # frames -> le son qui joue (cf. `set_live_source`)
        self._project = None
        self._sfx: Optional[Sfx] = None
        self._total_ms = 0
        self._frames = 0
        self._rate = 0
        self._blocking = False
        self._peaks: dict = {}                      # (chemin, date) -> (crêtes, secondes, frames, taux)
        self._file_peaks = np.zeros((0, 2), dtype=np.float32)    # les crêtes du fichier montré, pour la barre de découpe
        self._track_timer = QTimer(self)            # le rendu de l'aperçu attend la fin du geste (cf. `refresh_soon`)
        self._track_timer.setSingleShot(True)
        self._track_timer.setInterval(_TRACK_SILENCE_MS)
        self._track_timer.timeout.connect(self._refresh_track)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        self._wave = WaveformView()
        self._wave.show_cue(False)                  # un effet joue d'une traite : pas de départ à choisir
        self._wave.set_ramp_editable(True)
        self._wave.ramp_moving.connect(self._on_ramp_moving)
        self._wave.ramp_changed.connect(self._on_fade)
        self._wave.set_osc_sources(
            lambda frames: self._live_source(frames) if self._live_source is not None else None, self._still_window)
        self._wave.setMinimumHeight(140)
        self._wave.setToolTip(tooltip(title=label("sfxedit.wave_title"), body=label("sfxedit.wave_tip")))
        # L'onde, et à sa droite la barre du canal que l'effet occupe (une par canal du projet, pour voir ce qui reste de place).
        self._meters = ChannelMeters()
        self._meters.setVisible(False)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        grid.addWidget(self._wave, 0, 0)
        grid.addWidget(self._meters, 0, 1)
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid, 1)

        # La barre de découpe, la même que celle d'une musique ou d'un jingle WAV : le fichier entier en vignette, deux poignées.
        # Elle dit la même plage que les poignées de l'onde et les deux champs ; une seule écriture (`_commit`).
        self._trim_bar = TrimBar()
        self._trim_bar.setToolTip(tooltip(title=label("sndedit.trim_btn"), body=label("sndedit.trim_bar_tip")))
        self._trim_bar.moving.connect(self._on_bar_moving)
        self._trim_bar.changed.connect(lambda start, end: self._commit(start, end))
        self._trim_bar.setVisible(False)
        layout.addWidget(self._trim_bar)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._start = self._spin("sfxedit.start", "sfxedit.start_tip", row)
        self._end = self._spin("sfxedit.end", "sfxedit.end_tip", row)
        self._reset = QPushButton(label("sfxedit.reset"))
        self._reset.setFont(QFont(T.UI, T.MD))
        self._reset.setToolTip(tooltip(title=label("sfxedit.reset"), body=label("sfxedit.reset_tip")))
        self._reset.clicked.connect(lambda: self._commit(0, self._total_ms))
        row.addWidget(self._reset)
        # Écoute A/B du taux : le même effet au taux de son fichier, pour juger ce que le taux de la ROM lui coûte.
        self._ab = QPushButton(label("sfxedit.ab"))
        self._ab.setFont(QFont(T.UI, T.MD))
        self._ab.setCheckable(True)
        self._ab.setToolTip(tooltip(title=label("sfxedit.ab"), body=label("sfxedit.ab_tip")))
        self._ab.toggled.connect(self._on_ab)
        row.addWidget(self._ab)
        row.addStretch(1)
        layout.addLayout(row)

        self._summary = QLabel("")
        self._summary.setFont(QFont(T.UI, T.SM))
        self._summary.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        # La table de mixage de l'effet — volume, hauteur, variation, deux fondus, et l'axe du panoramique — comme celle d'une musique, mais montée
        # par l'écran dans sa colonne de droite (`mix_panel`) : l'éditeur écrit le modèle, le curseur ne le connaît pas.
        self._mix = MixFaders(SFX_FADERS, SFX_FADES, SFX_PAN)
        self._mix.changed.connect(self._on_mix)
        self.mix_panel = mix_panel(self._mix)
        self.mix_panel.setVisible(False)

    def _spin(self, title_key: str, tip_key: str, row: QHBoxLayout, suffix: str = " ms", on_change=None) -> UnitSpin:
        caption = QLabel(label(title_key))
        caption.setFont(QFont(T.UI, T.SM))
        caption.setStyleSheet(f"color:{C.TEXT_DIM};")
        spin = UnitSpin()
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
        if self._ab.isChecked():
            self._ab.setChecked(False)              # l'écoute A/B ne suit pas d'un effet à l'autre : on repart du son de la ROM
        self._project, self._sfx = project, sfx
        self._total_ms = self._frames = self._rate = 0
        self._file_peaks = np.zeros((0, 2), dtype=np.float32)
        shown = None
        path = project.asset_abs(sfx.asset) if project is not None and sfx is not None and sfx.asset else None
        if path is not None and path.is_file():
            shown = self._read(path)
        if shown is None:
            self._wave.set_envelope(np.zeros((0, 2), dtype=np.float32), 0.0)
            self._wave.set_loop_ms(None)
            self._sync_fields()
            self._sync_mix()
            return
        peaks, seconds, self._frames, self._rate = shown
        self._file_peaks = peaks
        self._total_ms = round(seconds * 1000)
        self._wave.set_envelope(peaks, seconds)
        self._sync_fields()
        self._sync_mix()
        self._refresh_track()

    def refresh(self) -> None:
        """Le taux, la hauteur ou le volume ont changé ailleurs (l'inspecteur) : le poids annoncé et le canal suivent, l'onde ne bouge pas."""
        self._track_timer.stop()
        self._sync_ab()
        self._update_summary()
        self._refresh_track()

    def refresh_soon(self) -> None:
        """Comme `refresh`, après un court silence : un champ qu'on tourne change dix fois par seconde, et chaque valeur
        coûte un rendu de l'effet. Le poids annoncé, lui, suit tout de suite (il ne rend rien)."""
        self._sync_ab()
        self._update_summary()
        self._track_timer.start()

    # ── Le son tel que la ROM le jouera : canal et oscilloscope ───

    def set_live_source(self, source) -> None:
        """D'où l'oscilloscope tire le son qui joue : `source(frames)` rend les dernières trames entendues, ou None."""
        self._live_source = source

    def _still_window(self, _seconds: float, frames: int):
        """Le début du rendu, ce que l'oscilloscope montre quand rien ne joue (un effet n'a pas de poignée de départ)."""
        track = self._track
        if track is None or track.pcm.shape[0] < frames:
            return None
        return track.pcm[:frames].astype(np.float32).mean(axis=1) / 32768.0

    def _refresh_track(self) -> None:
        """Relit le rendu de l'aperçu (en cache dans le lecteur tant que rien ne change) et pose la barre du canal."""
        self._track = None
        if self._track_provider is not None and self._project is not None and self._sfx is not None and self._total_ms > 0:
            self._track = self._track_provider(self._project, self._sfx)
        levels = None if self._track is None else self._track.levels
        self._meters.setVisible(levels is not None)
        if levels is not None:
            self._meters.set_levels(levels, GBA_MIX_RATE, self._project.settings.sound_channels)
            self._meters.set_gain(self._sfx.volume / 100)
        self._wave.show_mode_switch(self._track is not None)

    def set_playhead_seconds(self, seconds: float) -> None:
        """La lecture avance (`seconds` : dans le rendu, -1 à l'arrêt). L'onde montre le FICHIER : on y ajoute le début de la
        plage gardée, et la hauteur de départ accélère ou ralentit la lecture d'autant."""
        if self._track is None:
            return
        if seconds < 0:
            self._wave.set_playhead(-1.0)
        else:
            start, _end = self._window()
            self._wave.set_playhead(start / 1000 + seconds * int(getattr(self._sfx, "pitch", 100) or 100) / 100)
        self._meters.set_playhead(seconds)

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
        if ready:
            start, end = self._window()
            self._start.setValue(start)
            self._end.setValue(end)
            self._wave.set_loop_ms((start, end))
            self._trim_bar.load(self._file_peaks, self._total_ms, start, end)
            ramp_ms = min(end - start, round(fade_out_of(self._sfx) * 1000 / 60))      # un fondu ne dépasse pas la plage gardée
            self._wave.set_ramp((end - ramp_ms, end) if ramp_ms > 0 else None)
        else:
            self._wave.set_ramp(None)
        self._trim_bar.setVisible(ready)
        self._reset.setEnabled(ready and (self._sfx.trim_start > 0 or self._sfx.trim_end > 0))
        self._blocking = False
        self._sync_ab()
        self._update_summary()

    def _on_dragging(self, start: int, end: int) -> None:
        """Pendant le glisser : les champs et le poids suivent, rien n'est encore écrit."""
        self._blocking = True
        self._start.setValue(start)
        self._end.setValue(end)
        self._blocking = False
        self._trim_bar.set_window(start, end)
        self._update_summary(start, end)

    def _on_bar_moving(self, start: int, end: int) -> None:
        """Une poignée de la barre glisse : l'onde (qui n'a plus de poignée de découpe, seulement la plage claire), les champs et
        le poids suivent, rien n'est encore écrit."""
        self._wave.set_loop_ms((start, end))
        self._on_dragging(start, end)

    def _on_spin(self, _value: int) -> None:
        if self._blocking or self._sfx is None:
            return
        self._commit(self._start.value(), self._end.value())

    def _sync_mix(self) -> None:
        """Pose les valeurs de l'effet sur les curseurs, sans rien émettre. Les fondus ont besoin d'un fichier à couper ;
        le volume, la hauteur et la variation, non."""
        self.mix_panel.setEnabled(self._sfx is not None)
        if self._sfx is not None:
            self._mix.load(self._sfx, tempo_pitch=True, fades=self._total_ms > 0)

    def _on_ramp_moving(self, frames: int) -> None:
        """Pendant le glisser de la poignée : le curseur du fondu suit, rien n'est encore écrit."""
        if self._sfx is not None:
            self._mix.set_fades(fade_in_of(self._sfx), frames)

    def _on_fade(self, value: int) -> None:
        """La poignée de l'onde vient de poser le fondu de sortie (le curseur l'a déjà suivi pendant le glisser) : on
        l'écrit, par le même chemin qu'un curseur tenu (`_on_mix`)."""
        if self._sfx is not None:
            self._mix.set_fades(fade_in_of(self._sfx), int(value))
            self._on_mix("fade_out", int(value))

    def _on_mix(self, field: str, value: int) -> None:
        """Un curseur de la table de mixage bouge : l'effet est à jour tout de suite, le fichier suit après un silence (cf.
        `ui/common/deferred_writes.py`). Seul ce que le curseur change à l'écran se rafraîchit : le volume règle la barre du
        canal ; la hauteur et les fondus changent le rendu de l'aperçu ; la variation et le panoramique ne changent rien d'affiché (l'aperçu les
        lit à chaque lecture)."""
        if self._sfx is None or self._project is None:
            return
        setattr(self._sfx, field, int(value))
        schedule_save(self._project.sfx, self._sfx)
        if field == "volume":
            self._meters.set_gain(self._sfx.volume / 100)
        elif field == "pitch":
            self.refresh_soon()
        elif field in ("fade_in", "fade_out"):
            self._sync_fields()                  # la rampe de l'onde, et le poids annoncé
            self.refresh_soon()
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
        schedule_save(self._project.sfx, self._sfx)
        self._sync_fields()
        self.refresh_soon()
        self.changed.emit()

    def _update_summary(self, start: Optional[int] = None, end: Optional[int] = None) -> None:
        if self._sfx is None or self._project is None or self._total_ms <= 0:
            self._summary.setText(label("sfxedit.no_file") if self._sfx is not None else "")
            return
        if start is None or end is None:
            start, end = self._window()
        target = effective_rate(self._sfx, self._project.settings)
        keeping = Sfx(name="kept", trim_start=start, trim_end=0 if end >= self._total_ms else end)
        whole = planned_frames(Sfx(name="whole"), self._frames, self._rate, target)
        kept = planned_frames(keeping, self._frames, self._rate, target)
        if start <= 0 and end >= self._total_ms:
            text = label("sfxedit.summary_whole", total=self._total_ms, kb=f"{whole / 1024:.1f}")
        else:
            text = label("sfxedit.summary", start=start, end=end, kept=end - start,
                         total=self._total_ms, kb=f"{kept / 1024:.1f}", whole=f"{whole / 1024:.1f}")
        if self._rate_differs(target):
            # Le poids à côté de l'écoute A/B : ce que l'effet pèserait au taux de son fichier.
            at_file = planned_frames(keeping, self._frames, self._rate, 0)
            text += label("sfxedit.summary_rate", kb=f"{at_file / 1024:.1f}", rate=self._rate)
        self._summary.setText(text)

    def _rate_differs(self, target: int) -> bool:
        """La ROM rééchantillonne-t-elle l'effet (`target` : le taux visé, 0 = celui du fichier) ?"""
        return target > 0 and self._rate > 0 and target != self._rate

    def _sync_ab(self) -> None:
        """Le bouton A/B n'a de sens que si les deux taux diffèrent ; sinon il retombe (et le lecteur est prévenu)."""
        usable = (self._sfx is not None and self._project is not None and self._total_ms > 0
                  and self._rate_differs(effective_rate(self._sfx, self._project.settings)))
        self._ab.setEnabled(usable)
        if self._ab.isChecked() and not usable:
            self._ab.setChecked(False)

    def _on_ab(self, on: bool) -> None:
        """A/B : l'aperçu joue le fichier à son propre taux (`on`) ou au taux de la ROM. Le lecteur est prévenu d'abord ;
        le rendu et les barres de canal suivent ensuite, pour montrer ce qu'on entend."""
        self.original_rate_toggled.emit(on)
        self.refresh_soon()
