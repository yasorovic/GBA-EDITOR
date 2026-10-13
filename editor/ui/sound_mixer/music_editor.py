"""ui/sound_mixer/music_editor.py — la colonne centrale de l'écran Son pour une musique ou un jingle
(la forme d'onde et la bande des ordres) ; les sections de boucle (`sections_panel`) et le mixage (`mix_panel`)
sont deux panneaux que l'écran loge dans la colonne de droite.

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

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import GBA_MIX_RATE
from core.models.audio import JINGLE_MAX_CHANNELS, UNIT_MS, UNIT_ORDER
from core.music_structure import source_unit, wav_rom_bytes, weight_level
from core.wav_module import wav_seconds
from ui.common.labels import label
from ui.common.theme import C, QSS, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.channel_meters import ChannelMeters
from ui.sound_mixer.mix_faders import MixFaders
from ui.sound_mixer.order_strip import OrderStrip
from ui.sound_mixer.polyphony_view import PolyphonyView
from ui.sound_mixer.section_colors import section_color
from ui.sound_mixer.section_table import SectionTable
from ui.sound_mixer.waveform_view import WaveformView


def _title(text: str) -> QLabel:
    title = QLabel(text)
    title.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
    title.setStyleSheet(f"color:{C.TEXT_HI};")
    return title


def _size_text(size: int) -> str:
    return f"{size / (1 << 20):.2f} MiB" if size >= 1 << 20 else f"{size / 1024:.1f} KiB"


# L'onde ne grandit pas sans fin sur un grand écran : au-delà de cette hauteur, ce qui reste sert au bandeau
# (résumé du fichier) puis à la table de mixage.
_WAVE_MAX = 210


class MusicEditor(QWidget):
    changed = pyqtSignal()
    preview_section = pyqtSignal(object)           # la `MusicSection` à écouter
    mix_changed = pyqtSignal(str)                  # « volume », « tempo » ou « pitch » vient de bouger (en direct)
    mix_released = pyqtSignal()                    # le curseur tenu vient d'être lâché
    structure_changed = pyqtSignal()               # les panneaux latéraux viennent d'apparaître ou de disparaître
    scrub_requested = pyqtSignal(float, bool)      # (seconde, main posée) : la tête de lecture est glissée dans l'onde

    def __init__(self, track_provider: Callable, weight_provider: Callable = lambda _music: None, parent=None):
        """`track_provider(project, music)` rend le `Track` à dessiner, ou None.
        `weight_provider(music)` rend le poids MESURÉ au dernier build (un module), ou None."""
        super().__init__(parent)
        self._track_provider = track_provider
        self._weight_provider = weight_provider
        self._project = None
        self._music = None
        self._track = None
        self._module = None
        self._unit: Optional[str] = None
        self._mismatched = False                   # des sections d'une autre unité que le fichier
        self._duration_ms = 0                      # la durée du fichier WAV, pas celle de son rendu (arrondie à la ligne)
        self._scope = None                         # la `MusicSection` sélectionnée : celle que le ▶ fait boucler ; None = tout le morceau
        self._sections_on = True                   # faux pour un jingle : il ne boucle pas, il n'a pas de section
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(QSS.scroll_area)
        root.addWidget(scroll)
        self._scroll = scroll
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        self._body_layout = lay
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(6)

        # ── Le bandeau : ce qu'est le fichier (sans répéter son nom, que le lecteur donne).
        # Il n'apparaît que s'il reste de la hauteur une fois l'onde au plus grand (cf. `_fit_banner`). ──
        self._banner = QWidget()
        head = QHBoxLayout(self._banner)
        head.setContentsMargins(0, 0, 0, 0)
        self._summary = QLabel()
        self._summary.setFont(QFont(T.UI, T.MD))
        self._summary.setStyleSheet(f"color:{C.TEXT_DIM};")
        head.addWidget(self._summary, 1, Qt.AlignmentFlag.AlignVCenter)
        # La pastille de poids en ROM n'est pas dans ce bandeau : l'écran la pose dans le lecteur, en bas
        # (cf. `weight_pill`). Elle reste à l'éditeur, qui sait la calculer.
        self._weight = QLabel(self)
        self._weight.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._weight.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weight.setFixedHeight(24)
        self._banner.setVisible(False)
        lay.addWidget(self._banner)

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
        s_lay.setSpacing(6)
        self._wave = WaveformView()
        self._wave.setMaximumHeight(_WAVE_MAX)
        self._wave.loop_moving.connect(self._on_wave_moving)
        self._wave.loop_changed.connect(self._on_wave_loop)
        self._wave.tuning_moving.connect(self._on_wave_tuning)
        self._wave.tuning_released.connect(self._on_fader_released)
        self._wave.fades_changed.connect(self._on_wave_fades)
        self._wave.cue_requested.connect(self._on_wave_cue)
        self._wave.seek_requested.connect(self.scrub_requested)
        self._live_source = None                     # frames -> le son qui joue (cf. `set_live_source`)
        self._wave.set_osc_sources(
            lambda frames: self._live_source(frames) if self._live_source is not None else None, self._still_window)
        # L'onde et la courbe de polyphonie partagent la même colonne (donc le même axe de temps) ; les barres des
        # canaux, à droite, les couvrent toutes les deux. Un module seulement : un WAV n'a qu'un canal.
        self._poly = PolyphonyView()
        self._poly.setVisible(False)
        self._meters = ChannelMeters()
        self._meters.setVisible(False)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        grid.addWidget(self._wave, 0, 0)             # l'onde prend toute la hauteur que le reste ne demande pas
        grid.addWidget(self._poly, 1, 0)
        grid.addWidget(self._meters, 0, 1, 2, 1)
        grid.setRowStretch(0, 1)
        grid.setColumnStretch(0, 1)
        s_lay.addLayout(grid, 1)

        # Un module : la bande des ordres, pour choisir une plage. Seule structure du bas : le tableau des
        # sections et la table de mixage vivent dans `sections_panel` et `mix_panel`, que l'écran loge dans l'inspecteur.
        self._strip_zone = QWidget()
        m_lay = QVBoxLayout(self._strip_zone)
        m_lay.setContentsMargins(0, 0, 0, 0)
        m_lay.setSpacing(0)
        self._strip = OrderStrip()
        self._strip.selection_changed.connect(self._on_strip_selection)
        self._strip.section_clicked.connect(self._on_strip_section_clicked)
        self._strip.section_preview.connect(self.preview_section)
        self._strip.section_range_moving.connect(self._on_strip_section_moving)
        self._strip.section_range_changed.connect(self._commit)
        m_lay.addWidget(self._strip)
        s_lay.addWidget(self._strip_zone)

        # ── Les deux panneaux de la colonne de droite : les sections de boucle (en haut, sous l'inspecteur)
        # et la table de mixage (ferrée en bas) ──
        self.mix_panel = QWidget()
        mix = QVBoxLayout(self.mix_panel)
        mix.setContentsMargins(10, 8, 10, 8)
        mix.setSpacing(8)
        # La table de mixage : volume, tempo, hauteur. Elle s'entend pendant qu'on la règle.
        mix.addWidget(_title(label("sndedit.mix_title")))
        self._faders = MixFaders()
        self._faders.changed.connect(self._on_fader)
        self._faders.released.connect(self._on_fader_released)
        mix.addWidget(self._faders)

        # Les sections : le même tableau pour un module (en ordres) et pour un WAV (en secondes).
        # Le titre est posé au-dessus ; chaque section est sa propre carte (cf. SectionTable).
        self.sections_panel = QWidget()
        panel_lay = QVBoxLayout(self.sections_panel)
        panel_lay.setContentsMargins(10, 4, 10, 10)
        self._sections_zone = QWidget()
        t_lay = QVBoxLayout(self._sections_zone)
        t_lay.setContentsMargins(0, 0, 0, 0)
        t_lay.setSpacing(8)
        t_lay.addWidget(_title(label("sndedit.loop_sections")))
        self._table = SectionTable()
        self._table.changed.connect(self._on_table_changed)
        self._table.section_added.connect(self._on_section_added)
        t_lay.addWidget(self._table)
        panel_lay.addWidget(self._sections_zone)
        panel_lay.addStretch(1)
        self.mix_panel.setVisible(False)
        self.sections_panel.setVisible(False)
        lay.addWidget(self._structure, 1)

        # Les curseurs écrivent le modèle à chaque cran ; le disque, lui, attend qu'on les lâche.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self.changed.emit)
        self._blank()

    # ── Chargement ────────────────────────────────────────────────

    def _blank(self, text: str = "") -> None:
        """Rien à structurer : on dit pourquoi, au lieu de montrer une zone vide."""
        self._message.setText(text)
        self._message.setVisible(bool(text))
        self._structure.setVisible(False)
        self.mix_panel.setVisible(False)
        self.sections_panel.setVisible(False)
        self._mismatch.setVisible(False)
        self._mismatched = False
        self._show_weight(None, label("sndedit.weight_unknown_tip"))
        self._banner.setVisible(False)
        self.structure_changed.emit()

    def load(self, project, music, sections: bool = True) -> None:
        """`sections=False` pour un jingle : on montre la forme d'onde, pas de quoi régler une boucle
        que la ROM ne jouera pas."""
        self._project, self._music, self._sections_on = project, music, sections
        self._wave.set_cue(0.0)
        self._scope = None
        self.reload()

    def reload(self) -> None:
        """Relit le fichier et le `Track` : à appeler quand le FICHIER ou ce qui change son rendu
        (tempo, hauteur, taux) a changé. Le cache du lecteur évite de refaire un rendu inutile."""
        music, project = self._music, self._project
        self._track = self._module = self._unit = None
        if music is None or project is None:
            return self._blank()
        path = project.asset_abs(music.asset) if music.asset else None
        if path is None or not path.exists():
            return self._blank(label("sndedit.no_file"))
        self._unit = source_unit(path)
        if self._unit is None:
            return self._blank(label("sndedit.unreadable"))
        try:
            if self._unit == UNIT_ORDER:
                self._module = load_module(path)
            self._track = self._track_provider(project, music)
        except Exception as exc:  # tolerated: unreadable file, said on screen — the validator names the cause
            return self._blank(label("sndedit.unreadable_why", reason=str(exc)))
        if self._track is None:
            return self._blank(label("sndedit.unreadable"))

        # Une musique sans section prend l'unité de son fichier ; avec des sections d'une autre unité,
        # on le dit (jamais réinterprétées en silence).
        if not music.sections:
            music.unit = self._unit
        if self._unit == UNIT_MS:
            self._duration_ms = round(wav_seconds(path) * 1000)
        self._message.setVisible(False)
        self._structure.setVisible(True)
        self.mix_panel.setVisible(True)
        self._wave.set_track(self._track.pcm, GBA_MIX_RATE, self._render_tempo())
        self._refresh_polyphony()
        self._mismatched = self._sections_on and bool(music.sections) and music.unit != self._unit
        self._mismatch.setVisible(self._mismatched)
        editable = not self._mismatched and self._sections_on
        self._strip_zone.setVisible(editable)
        self._sections_zone.setVisible(editable)
        self.sections_panel.setVisible(editable)
        self._wave.set_editable(self._unit == UNIT_MS and editable)
        self._refresh_sections()
        self._summary.setText(self._kind_text())
        self._refresh_weight(path)
        self._fit_banner()
        # Tempo et hauteur : un module seulement (un WAV les ignore, un jingle n'applique que son volume).
        tempo_pitch = self._unit == UNIT_ORDER and self._sections_on
        self._faders.load(music, tempo_pitch=tempo_pitch, fades=self._sections_on,
                          unavailable_key="sndedit.mix_wav_tip" if self._sections_on else "sndedit.mix_jingle_tip")
        # Les mêmes réglages se glissent sur l'onde : mêmes champs, mêmes bornes que les curseurs ; les fondus
        # sont ceux de la musique (un jingle n'en applique pas).
        self._show_mix()
        self._wave.set_tunable(("volume", "tempo", "pitch") if tempo_pitch else ("volume",))
        self._wave.set_fades(music.fade_in, music.fade_out, self._sections_on)
        self._structure.updateGeometry()
        self.structure_changed.emit()

    def _refresh_polyphony(self) -> None:
        """La courbe des canaux qui sonnent. Le plafond est celui du projet ; un jingle, lui, n'a que ses voies à lui.
        Un WAV a les siens : joué comme le module que le build en tire, il occupe un canal par voie."""
        levels = self._track.levels
        self._poly.setVisible(levels is not None)
        self._meters.setVisible(levels is not None)
        if levels is not None:
            ceiling = self._project.settings.sound_channels if self._sections_on else JINGLE_MAX_CHANNELS
            self._poly.set_levels(levels, self._track.pcm.shape[0], GBA_MIX_RATE, ceiling)
            self._meters.set_levels(levels, GBA_MIX_RATE, ceiling)

    def set_live_source(self, source) -> None:
        """D'où l'oscilloscope tire le son qui joue : `source(frames)` rend les dernières trames entendues, ou None."""
        self._live_source = source

    def _still_window(self, seconds: float, frames: int):
        """Une fenêtre du rendu de la piste, à `seconds` : ce que l'oscilloscope montre quand rien ne joue."""
        track = self._track
        if track is None or track.pcm.shape[0] < frames:
            return None
        start = min(int(seconds * GBA_MIX_RATE), track.pcm.shape[0] - frames)
        return track.pcm[start:start + frames].astype(np.float32).mean(axis=1) / 32768.0

    def apply_retuned_track(self, track, envelope=None) -> None:
        """Pose un rendu tempo/hauteur terminé hors du fil d'interface.

        Le reste de l'éditeur (sections, sélection, potards) est déjà vivant :
        on remplace seulement les données qui dépendent du rendu.
        """
        if track is None or self._track is None:
            return
        self._track = track
        if envelope is None:
            self._wave.set_track(track.pcm, GBA_MIX_RATE, self._render_tempo())
        else:
            self._wave.set_envelope(*envelope, self._render_tempo())
        self._refresh_polyphony()
        # Les bornes, noms et contrôles de sections n'ont pas changé : les
        # reconstruire ferait sauter la colonne de droite à chaque rendu. Les
        # bandes et la durée, elles, lisent le nouveau Track directement.
        self._strip.set_sections(self._music.sections)
        self._refresh_bands()
        self._show_mix()

    def _show_mix(self) -> None:
        """Les réglages de la musique à l'écran : l'onde et les barres des canaux les suivent tout de suite."""
        self._wave.set_mix(self._music.volume, self._render_tempo(), self._music.pitch)
        self._meters.set_gain(self._music.volume / 100)

    def _render_tempo(self) -> int:
        """Le tempo (%) que le rendu de la piste applique : celui de la musique pour un module, aucun pour un WAV
        ou un jingle (leur tempo n'existe pas, cf. `tempo_pitch` de `reload`)."""
        return self._music.tempo if self._unit == UNIT_ORDER and self._sections_on else 100

    def _kind_text(self) -> str:
        """Ce qu'est le fichier : son format et ce qu'il contient — sans son nom."""
        if self._module is None:
            return label("sndedit.kind_wav", seconds=str(round(self._duration_ms / 1000)))
        return "  ·  ".join((
            label("sndedit.kind_module"),
            label("sndedit.module_orders", n=len(self._module.order)),
            label("sndedit.module_patterns", n=len(self._module.patterns)),
            label("sndedit.module_channels", n=self._module.num_channels)))

    def _fit_banner(self) -> None:
        """Le bandeau n'apparaît que s'il reste de la hauteur une fois l'onde au plus grand : il ne prend jamais
        de place à l'onde ni au tableau."""
        if self._track is None:
            self._banner.setVisible(False)
            return
        lay, banner = self._body_layout, self._banner
        band = banner.sizeHint().height() + lay.spacing()
        needed = lay.minimumSize().height() - (band if banner.isVisible() else 0)
        spare = self._scroll.viewport().height() - needed - (_WAVE_MAX - self._wave.minimumHeight())
        banner.setVisible(spare >= band)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_banner()

    @property
    def weight_pill(self) -> QLabel:
        """Le poids en ROM de la musique ouverte : caché quand il n'y a pas de chiffre sûr. Le lecteur l'héberge."""
        return self._weight

    def _refresh_weight(self, path) -> None:
        """La pastille de poids en ROM. Un WAV se calcule (c'est le module que le build écrira, au taux et
        à la boucle réglés) ; un module tracker se LIT au dernier build, car mmutil mutualise ses échantillons
        et une estimation serait fausse : tant que rien n'est mesuré, la pastille donne la taille du fichier
        source, précédée d'un « ~ »."""
        estimated = False
        if self._unit == UNIT_MS:
            size = wav_rom_bytes(self._music, path)
            tip = label("sndedit.weight_wav_tip")
        else:
            entry = self._weight_provider(self._music)
            size = entry.own_bytes if entry else None
            tip = label("sndedit.weight_built_tip")
            if entry is None:
                size, estimated = path.stat().st_size, True
                tip = label("sndedit.weight_estimate_tip")
            if entry and entry.shared_bytes and entry.shared_with:
                tip += "\n" + label("sndedit.weight_shared_tip", kb=_size_text(entry.shared_bytes),
                                    n=entry.shared_with)
        self._show_weight(size, tip if size is not None else label("sndedit.weight_unknown_tip"), estimated)

    def _show_weight(self, size, tip: str, estimated: bool = False) -> None:
        """La pastille, toujours visible : le chiffre et sa gravité (précédé d'un « ~ » s'il est estimé), ou
        « — KiB » quand il n'y a rien à montrer."""
        if size is None:
            color, text = C.TEXT_MUTED, "—  KiB"
        else:
            color = {"ok": C.TEXT_DIM, "warn": C.ACCENT_WARM, "high": C.ACCENT_RED}[weight_level(size)]
            text = ("~" if estimated else "") + _size_text(size)
        self._weight.setVisible(True)
        self._weight.setText(label("sndedit.weight", size=text))
        self._weight.setStyleSheet(f"color:{color}; border:1px solid {color}; padding:0 10px; background:transparent;")
        self._weight.setToolTip(tooltip(title=label("sndedit.weight_title"), body=tip))

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
        if self._mismatched:
            return
        if self._unit == UNIT_ORDER and self._module is not None:
            self._strip.set_orders(self._module.order)
            self._strip.set_seconds_provider(self._seconds_of)
            self._table.load(music, len(self._module.order))
        elif self._unit == UNIT_MS:
            self._strip.set_timeline(self._duration_ms)
            self._strip.set_seconds_provider(lambda start, end: max(0, end - start) / 1000.0)
            self._table.load(music, self._duration_ms, UNIT_MS)
        self._strip.set_sections(music.sections)
        self._refresh_bands()

    def _refresh_bands(self) -> None:
        """Les bandes colorées derrière l'onde ; pour un WAV, les poignées de la section de boucle par défaut."""
        music = self._music
        if self._unit == UNIT_ORDER:
            self._wave.set_bands([
                (self._seconds_of(0, s.start) if s.start else 0.0,
                 self._seconds_of(0, s.end), section_color(s, rank))
                for rank, s in enumerate(music.sections) if s.start in self._track.marks])
            self._wave.set_loop_ms(None)
        else:
            self._wave.set_bands([(s.start / 1000.0, s.end / 1000.0, section_color(s, rank))
                                  for rank, s in enumerate(music.sections) if 0 <= s.start < s.end])
        self._refresh_scope()

    def _commit(self) -> None:
        """Une section a bougé : on redessine tout ce qui la montre, puis l'écran enregistre."""
        self._refresh_sections()
        if self._unit == UNIT_MS:                      # la boucle d'un WAV change ce que la ROM porte
            self._refresh_weight(self._project.asset_abs(self._music.asset))
        self.changed.emit()

    # ── Les gestes : un module ────────────────────────────────────

    def _on_table_changed(self) -> None:
        # Le tableau se reconstruit lui-même ; la bande et la forme d'onde, elles, suivent.
        self._strip.set_sections(self._music.sections)
        self._refresh_bands()
        if self._unit == UNIT_MS:                      # les sections d'un WAV changent ce que la ROM porte
            self._refresh_weight(self._project.asset_abs(self._music.asset))
        self.changed.emit()

    def _on_strip_section_moving(self, section, start: int, end: int) -> None:
        """Une poignée de la bande d'ordres déplace directement sa section.

        Les compteurs et les bandes de l'onde suivent pendant le geste ;
        l'enregistrement est regroupé au relâchement par `_commit`.
        """
        section.start, section.end = start, end
        self._table.show_range(section)
        self._strip.set_sections(self._music.sections)   # recalcule les rangées si deux plages se croisent
        self._refresh_bands()

    # ── Les curseurs ──────────────────────────────────────────────

    @property
    def mixing(self) -> bool:
        """Un curseur de la table de mixage est tenu."""
        return self._faders.held or self._wave.gesturing

    def _on_fader(self, field: str, value: int) -> None:
        """Le modèle suit à chaque cran, le son aussi ; le disque, lui, attend le relâchement. (Une molette ou une
        flèche du clavier ne tient rien : le disque attend alors un instant de calme.)"""
        setattr(self._music, field, value)
        if field in ("fade_in", "fade_out"):           # un fondu ne s'entend pas en direct : l'onde le dessine, le disque l'écrit
            self._wave.set_fades(self._music.fade_in, self._music.fade_out, self._sections_on)
            self._save_timer.start()
            return
        self._show_mix()
        self.mix_changed.emit(field)
        if not self.mixing:
            self._save_timer.start()

    def _on_wave_tuning(self, field: str, value: int) -> None:
        """Un glisser dans l'onde règle un champ : le curseur correspondant le dit, et c'est lui qui écrit le modèle
        (un seul chemin, qu'on tienne le curseur ou l'onde)."""
        self._faders.fader(field).setValue(value)

    def _on_fader_released(self) -> None:
        self._save_timer.stop()
        self.changed.emit()                          # le JSON s'écrit ICI, une fois
        self.mix_released.emit()

    # ── Les gestes : les poignées d'un WAV ────────────────────────

    def _loop_region(self):
        """La section sélectionnée : celle que les poignées de la forme d'onde déplacent."""
        return self.scope_section

    def _on_wave_moving(self, start: int, end: int) -> None:
        region = self._loop_region()
        if region is not None:
            region.start, region.end = start, end
            self._table.show_range(region)
            self._strip.set_sections(self._music.sections)

    def _on_wave_loop(self, start: int, end: int) -> None:
        region = self._loop_region()
        if region is not None:
            region.start, region.end = start, end
            self._commit()

    def _on_wave_fades(self, fade_in: int, fade_out: int) -> None:
        self._music.fade_in, self._music.fade_out = fade_in, fade_out
        self._faders.set_fades(fade_in, fade_out)
        self.changed.emit()

    # ── La section sélectionnée ───────────────────────────────────

    def _on_strip_selection(self, start: int, end: int) -> None:
        """Une autre plage (ou plus rien) : la section précédemment choisie ne l'est plus. Un clic sur le nom d'une
        section la désigne ensuite (`_on_strip_section_clicked`, émis juste après)."""
        self._table.set_selection(start, end)
        self._scope = None
        self._refresh_scope()

    def _on_strip_section_clicked(self, name: str) -> None:
        self._scope = self._music.section(name) if self._music is not None and self._sections_on else None
        self._refresh_scope()

    def _on_section_added(self, section) -> None:
        """« + » a créé une section : elle est choisie, ses bornes et ses poignées se montrent (le `changed` du tableau,
        émis juste après, redessine le reste)."""
        self._scope = section if self._sections_on else None

    @property
    def scope_section(self):
        """La section que le ▶ fait boucler, ou None : sans sélection, la musique se joue d'une traite."""
        music = self._music
        if self._scope is None or music is None or not any(s is self._scope for s in music.sections):
            return None
        return self._scope

    def scope_seconds(self):
        """(début, fin) de la section sélectionnée sur la frise, en secondes, ou None."""
        section = self.scope_section
        if section is None or self._track is None:
            return None
        if self._unit == UNIT_ORDER:
            marks, total = self._track.marks, self._track.pcm.shape[0]
            if section.start not in marks:
                return None
            return marks[section.start] / GBA_MIX_RATE, marks.get(section.end, total) / GBA_MIX_RATE
        return section.start / 1000.0, section.end / 1000.0

    def _refresh_scope(self) -> None:
        """Les bornes sur la règle de l'onde."""
        span, section = self.scope_seconds(), self.scope_section
        if self._unit == UNIT_MS:        # un WAV : les poignées de l'onde suivent la section sélectionnée
            self._wave.set_loop_ms((section.start, section.end) if section is not None else None)
        if span is None or section is None:
            self._wave.set_scope(None)
            return
        rank = self._music.sections.index(section)
        self._wave.set_scope((span[0], span[1], section_color(section, rank)))

    # ── Le point de départ ────────────────────────────────────────

    def start_seconds(self):
        """Où poser la tête de lecture une fois la musique lancée : la poignée de la règle, tant qu'elle tombe dans
        la section sélectionnée (hors d'elle, la section démarre à son début : None, rien à poser)."""
        cue, span = self.cue_seconds, self.scope_seconds()
        if cue <= 0 or (span is not None and not span[0] <= cue < span[1]):
            return None
        return cue

    @property
    def cue_seconds(self) -> float:
        """D'où la lecture démarre : la poignée de la règle (un WAV, joué comme le module que le build en tire,
        repart lui aussi de n'importe où)."""
        return self._wave.cue

    def _on_wave_cue(self, seconds: float, snap: bool, _dragging: bool) -> None:
        """La poignée de la règle est saisie : elle se pose où l'on veut — ou, avec Maj, au début de l'ordre visé —
        sans toucher à l'aperçu en cours : la tête de lecture ne bouge pas, la poignée ne sert qu'au prochain départ. (Un WAV n'a pas d'ordres : Maj le cale sur la seconde entière.)"""
        if snap and self._module is not None and self._track is not None and self._track.marks:
            order = self._track.order_at(int(seconds * GBA_MIX_RATE))
            seconds = self._track.marks.get(order, 0) / GBA_MIX_RATE
        elif snap:
            seconds = float(round(seconds))
        self._wave.set_cue(seconds)

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
        self._poly.set_playhead(seconds)
        self._meters.set_playhead(seconds)
        if self._module is not None:
            self._strip.set_playhead_order(self._track.order_at(int(seconds * GBA_MIX_RATE)))
        else:
            self._strip.set_playhead_ms(seconds * 1000.0 if seconds >= 0 else -1.0)
