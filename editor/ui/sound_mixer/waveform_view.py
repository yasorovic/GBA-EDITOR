"""ui/sound_mixer/waveform_view.py — la forme d'onde d'une musique, telle que le deck la jouera.

On dessine le PCM du `Track` (cf. box_playback.track_for), pas le fichier source : un WAV y paraît
mono, au taux et à la quantification que la ROM portera, un module tel que le rend l'émulation. Ce
qu'on voit est ce qu'on entend.

Les sections sont des BANDES colorées (en secondes) posées derrière l'onde, pour un module comme pour
un WAV. Un WAV a en plus, sur sa section de boucle par défaut, deux POIGNÉES qu'on glisse : les valeurs
sont des millisecondes, l'unité d'un WAV dans le sidecar (cf. models/audio.UNIT_MS).

Deux autres gestes règlent la musique elle-même (le widget ne connaît pas la `Music` : il dit ce qui bouge,
l'éditeur écrit le modèle) :

  - un glisser dans l'onde : horizontal = tête de lecture, Maj + horizontal = tempo, vertical = hauteur,
    Maj + vertical = volume. L'axe se décide après quelques pixels ; pour un réglage, une barre qui suit le geste
    et une pastille donnent la nouvelle valeur ;
  - la poignée de départ, sur la règle : on la saisit et on la glisse librement, Maj la cale sur le début d'un ordre ;
  - les bornes de la section sélectionnée (cf. `set_scope`), pour montrer la part qui va boucler ;
  - deux poignées en bas de l'onde, à gauche et à droite : le fondu d'entrée et le fondu de sortie (en frames).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QButtonGroup, QToolButton, QWidget

from core.engine_emulation.module_render import GBA_MIX_RATE
from core.models.audio import FADE_MAX_FRAMES
from core.music_structure import MIN_SECTION_MS as _MIN_LOOP_MS    # la boucle d'un WAV ne peut pas être plus courte
from ui.common.labels import label
from ui.common.theme import C, T
from ui.common.tooltip import tooltip
from ui.sound_mixer.mix_faders import RANGES as _MIX_RANGES

_BINS = 1600            # crêtes gardées : au-delà, un écran n'a pas de pixel de plus
_RULER = 26             # hauteur de la règle des temps
_GRAB = 7               # distance (px) à laquelle une poignée se saisit
_FADE_BAND = 18         # hauteur (px), au bas de l'onde, où se saisissent les poignées de fondu
_CUE_HALF = 5           # demi-largeur (px) de la poignée de départ, sur la règle
_SEEK = "seek"          # le « réglage » d'un glisser horizontal sans Maj : la tête de lecture, pas un champ de la musique
_AXIS_LOCK = 6         # déplacement (px) après lequel un glisser dans l'onde choisit son axe
_WAVE_LIT = 165         # opacité (/255) du corps de l'onde, au cœur ; hors de la boucle, elle passe à _WAVE_DIM
_WAVE_DIM = 75
_DURATION_WIDTH = 58    # largeur (px) de la durée totale, posée à gauche de la bascule Onde | Scope (« 350 ms » doit y tenir)
_SWITCH_GAP = 10        # air (px) entre la durée et la bascule, et entre la bascule et le bord
_OSC_FRAMES = 400       # trames dessinées par l'oscilloscope : 30 ms
_OSC_FULL = 0.4         # l'amplitude (0..1) qui remplit la moitié de la hauteur : au-delà, la trace est écrêtée
_OSC_POLL_MS = 33       # l'oscilloscope se relit 30 fois par seconde


def _wave_palette() -> np.ndarray:
    """Le pixel ARGB prémultiplié de l'onde pour chaque opacité 0..255 : la teinte est fixe, seul l'alpha varie.
    Relue à chaque dessin, la teinte suit le thème."""
    red, green, blue, _ = QColor(C.ACCENT_COOL).getRgb()
    alpha = np.arange(256, dtype=np.uint32)
    return (alpha << 24) | ((alpha * red // 255) << 16) | ((alpha * green // 255) << 8) | (alpha * blue // 255)
_FRAMES_PER_SECOND = 60
# Le pas de la règle, en secondes : les fractions ne servent qu'à une piste COURTE (un effet), sur une musique le premier
# pas qui tient dans 78 px reste une seconde ou plus.
_STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600)


def _time_text(seconds: float, step: float) -> str:
    """Un repère de la règle : `m:ss` pour un pas d'au moins une seconde, des millisecondes en dessous (un effet dure
    quelques dixièmes de seconde, une graduation « 0:00 » ne lui dirait rien)."""
    if step >= 1:
        whole = round(seconds)
        return f"{whole // 60}:{whole % 60:02d}"
    return f"{round(seconds * 1000)} ms"


def _duration_text(seconds: float) -> str:
    """La durée totale au bout de la règle : `m:ss` dès dix secondes ; en dessous, des secondes (une décimale), puis des
    millisecondes sous la seconde — un effet dure quelques dixièmes."""
    if seconds >= 10:
        whole = round(seconds)
        return f"{whole // 60}:{whole % 60:02d}"
    return f"{seconds:.1f} s" if seconds >= 1 else f"{round(seconds * 1000)} ms"


def peak_envelope(pcm: np.ndarray, mix_rate: int) -> tuple[np.ndarray, float]:
    """Crêtes min/max destinées au dessin, sans dépendance à un widget Qt.

    Cette fonction est aussi appelée par le worker de retune : compacter le
    PCM sur le fil de fond évite un dernier à-coup quand son rendu est prêt.
    """
    n = int(pcm.shape[0]) if pcm.ndim else 0
    if n == 0 or mix_rate <= 0:
        return np.zeros((0, 2), dtype=np.float32), 0.0
    mono = pcm.astype(np.float32).mean(axis=1) / 32768.0
    bins = min(_BINS, n)
    edges = np.linspace(0, n, bins + 1).astype(int)[:-1]
    return np.stack([np.minimum.reduceat(mono, edges),
                     np.maximum.reduceat(mono, edges)], axis=1), n / mix_rate


@dataclass
class _Gesture:
    """Un glisser dans l'onde : d'où il part, et — une fois l'axe choisi — ce qu'il règle."""
    origin: QPointF
    field: str | None = None            # « tempo », « pitch » ou « volume » ; None tant que l'axe n'est pas décidé
    start: int = 0                      # la valeur du champ au départ


class WaveformView(QWidget):
    loop_moving = pyqtSignal(int, int)      # (début, fin) en ms, pendant le glisser
    loop_changed = pyqtSignal(int, int)     # idem, au relâchement : c'est lui qui écrit
    tuning_moving = pyqtSignal(str, int)    # (« tempo » | « pitch » | « volume », valeur en %), pendant le glisser
    tuning_released = pyqtSignal()          # le glisser dans l'onde est lâché
    fades_changed = pyqtSignal(int, int)    # (fondu d'entrée, fondu de sortie) en frames, au relâchement
    ramp_moving = pyqtSignal(int)           # fondu de sortie d'un EFFET (frames), pendant le glisser de sa poignée
    ramp_changed = pyqtSignal(int)          # idem, au relâchement : c'est lui qui écrit
    cue_requested = pyqtSignal(float, bool, bool)   # (seconde visée, Maj enfoncé, glisser en cours) : la poignée de départ, sur la règle
    seek_requested = pyqtSignal(float, bool)        # (seconde visée, main toujours posée) : la tête de lecture, glissée dans l'onde

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setMouseTracking(True)
        self.setToolTip(tooltip(title=label("sndedit.wave_title"), body=label("sndedit.wave_tip")))
        self._peaks = np.zeros((0, 2), dtype=np.float32)    # (min, max) par colonne
        self._seconds = 0.0
        self._bands: list = []                              # (début s, fin s, QColor)
        self._loop: tuple | None = None                     # (début ms, fin ms)
        self._editable = False
        self._playhead = -1.0
        self._scope: tuple | None = None                    # (début s, fin s, QColor) : la section qui va boucler
        self._cue = 0.0                                     # d'où la lecture part : la poignée de la règle
        self._drag: str | None = None                     # « start » | « end » (boucle), « fade_in » | « fade_out », « seek » (règle)
        self._mix = {"volume": 100, "tempo": 100, "pitch": 100}
        self._display_gain = 1.0                         # aperçu instantané du potard de volume, sans refaire le rendu
        self._display_tempo = 100                         # durée affichée provisoire pendant qu'un rendu exact arrive
        self._render_tempo = 100                          # le tempo (%) auquel l'enveloppe posée a été rendue
        self._tunable: tuple = ()                           # les champs que le glisser dans l'onde peut régler
        self._fades = (0, 0)                                # (entrée, sortie) en frames
        self._fades_editable = False
        self._gesture: _Gesture | None = None
        self._overlay: tuple | None = None                  # (sens, position, origine, ancre, texte) : barre et pastille
        self._cache: QPixmap | None = None                  # tout sauf la tête de lecture, peint une fois
        self._mode = "wave"                                 # « wave » | « osc » : le choix de l'auteur, gardé d'une musique à l'autre
        self._switch_shown = True                           # un effet n'a pas de scope : la bascule disparaît
        self._cue_shown = True                              # ni de départ à choisir : un effet joue d'une traite
        self._ramp: tuple | None = None                     # (début ms, fin ms) : la rampe d'un fondu de sortie d'effet
        self._ramp_editable = False                         # sa poignée se saisit (elle vit sur la fin de la plage `_loop`)
        self._osc_live = None                               # ce que le lecteur fait entendre à l'instant (mono, −1..1), ou None
        self._osc_source = None                             # frames -> les dernières trames qui s'entendent, ou None : le lecteur
        self._osc_still = None                              # (seconde, frames) -> une fenêtre du rendu, quand rien ne joue
        self._osc_timer = QTimer(self)
        self._osc_timer.setInterval(_OSC_POLL_MS)
        self._osc_timer.timeout.connect(self._poll_osc)
        self._build_mode_switch()

    # ── Ce qu'on lui donne ────────────────────────────────────────

    def set_track(self, pcm: np.ndarray, mix_rate: int, tempo: int = 100) -> None:
        """Garde les crêtes de `pcm` (stéréo int16) : un (min, max) par colonne de `_BINS`."""
        self.set_envelope(*peak_envelope(pcm, mix_rate), tempo)

    def set_envelope(self, peaks: np.ndarray, seconds: float, tempo: int = 100) -> None:
        """Pose une enveloppe déjà calculée par le worker de rendu. `tempo` (%) : celui auquel elle a été rendue —
        sa durée en tient déjà compte, la règle ne doit pas l'appliquer une seconde fois.

        La poignée de départ est une seconde de la frise : quand la frise change de durée, elle reste au même endroit
        de la musique."""
        if self._seconds > 0 and seconds > 0:
            self._cue *= seconds / self._seconds
        self._peaks = peaks
        self._seconds = seconds
        self._render_tempo = max(1, int(tempo))
        self._redraw()

    def set_bands(self, bands: list) -> None:
        self._bands = list(bands)
        self._redraw()

    def set_loop_ms(self, loop: tuple | None) -> None:
        self._loop = None if loop is None else (int(loop[0]), int(loop[1]))
        self._redraw()

    def set_editable(self, editable: bool) -> None:
        self._editable = bool(editable)
        self._redraw()

    def set_mix(self, volume: int, tempo: int, pitch: int) -> None:
        """Les réglages de la musique : le point de départ d'un glisser, et leur effet à l'écran, tout de suite.

        Le volume redimensionne la silhouette, le tempo gradue la règle autrement ; l'oscilloscope, lui, montre le
        son qui joue, donc aussi la hauteur. Aucun ne demande de rendu : l'enveloppe d'un rendu complet n'en dépend
        presque pas (mesuré le 2026-10-12 : 0,1 à 3,7 % d'écart). L'éditeur refait le rendu exact quand la main se pose.
        """
        self._mix = {"volume": int(volume), "tempo": int(tempo), "pitch": int(pitch)}
        gain = max(0.0, min(1.0, int(volume) / 100.0))
        if gain != self._display_gain or int(tempo) != self._display_tempo:
            self._display_gain = gain
            self._display_tempo = int(tempo)
            self._redraw()

    # ── Onde | Scope ──────────────────────────────────────────────

    def _build_mode_switch(self) -> None:
        """La bascule, posée au bout de la règle : deux boutons exclusifs, à la manière des contextes de l'écran."""
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._mode_buttons: dict[str, QToolButton] = {}
        for mode, key in (("wave", "wave"), ("osc", "scope")):
            button = QToolButton(self)
            button.setText(label(f"sndedit.view_{key}"))
            button.setToolTip(tooltip(title=label(f"sndedit.view_{key}"), body=label(f"sndedit.view_{key}_tip")))
            button.setCheckable(True)
            button.setFont(QFont(T.UI, T.XS))
            button.setFixedHeight(_RULER - 8)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};color:{C.TEXT_NORM};padding:0px 8px;}}"
                f"QToolButton:hover{{background:{C.BG_HOVER};}}"
                f"QToolButton:checked{{background:{C.BG_SEL};border-color:{C.ACCENT};color:{C.TEXT_HI};}}")
            group.addButton(button)
            button.clicked.connect(lambda _checked=False, m=mode: self._set_mode(m))
            self._mode_buttons[mode] = button
        self._mode_buttons["wave"].setChecked(True)
        self._place_mode_switch()

    def _place_mode_switch(self) -> None:
        x = self.width() - _SWITCH_GAP
        for mode in ("osc", "wave"):
            button = self._mode_buttons[mode]
            x -= button.sizeHint().width()
            button.move(x, (_RULER - button.height()) // 2 - 1)

    def show_mode_switch(self, shown: bool) -> None:
        """Montre ou cache la bascule Onde | Scope. Cachée, l'onde est seule : l'oscilloscope n'a de sens que pour ce que le
        deck joue (une musique), pas pour un effet."""
        self._switch_shown = bool(shown)
        for button in self._mode_buttons.values():
            button.setVisible(self._switch_shown)
        if not self._switch_shown and self._mode != "wave":
            self._mode_buttons["wave"].setChecked(True)
            self._set_mode("wave")
        self._redraw()

    def set_ramp_editable(self, editable: bool) -> None:
        """La poignée du fondu de sortie d'un effet : posée au début de la rampe — sur la fin de la plage gardée quand il n'y a
        pas de fondu —, elle se glisse vers la gauche pour l'allonger, comme les poignées de fondu d'une musique."""
        self._ramp_editable = bool(editable)
        self._redraw()

    def set_ramp(self, ramp: tuple | None) -> None:
        """La rampe d'un fondu de sortie, de `ramp[0]` à `ramp[1]` ms : l'onde s'y éteint. Un effet fond sur la fin de sa
        plage GARDÉE, pas sur celle du fichier — c'est pourquoi ce n'est pas le fondu des musiques, collé aux bords."""
        self._ramp = None if ramp is None else (int(ramp[0]), int(ramp[1]))
        self._redraw()

    def show_cue(self, shown: bool) -> None:
        """Montre ou cache la poignée de départ de la règle : une musique reprend sa lecture d'où on la pose, un effet
        joue toujours depuis son début."""
        self._cue_shown = bool(shown)
        self.update()

    def _ruler_reserved(self) -> int:
        """La largeur (px), au bout de la règle, prise par la bascule et la durée : les graduations s'arrêtent avant."""
        switch = sum(button.sizeHint().width() for button in self._mode_buttons.values()) if self._switch_shown else 0
        return _SWITCH_GAP + switch + (_SWITCH_GAP if self._switch_shown else 0) + _DURATION_WIDTH

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._osc_live = None
        self._sync_osc_timer()
        self._redraw()

    def set_osc_sources(self, live, still) -> None:
        """D'où l'oscilloscope tire son tracé. `live(frames)` : ce que le lecteur fait entendre à l'instant (ou None
        s'il ne joue pas). `still(seconde, frames)` : une fenêtre du rendu autour de la poignée de départ, pour ne pas
        laisser la zone vide à l'arrêt."""
        self._osc_source, self._osc_still = live, still

    def _osc_shown(self) -> bool:
        return getattr(self, "_mode", "wave") == "osc"

    def _sync_osc_timer(self) -> None:
        """On ne relit le lecteur que si l'oscilloscope se voit."""
        timer = getattr(self, "_osc_timer", None)
        if timer is None:
            # Un widget encore affiché qu'on détruit reçoit son `hideEvent` quand ses attributs Python n'existent plus :
            # l'exception levée dans ce slot faisait avorter tout le processus (à la fermeture, ou à la fin d'un test).
            return
        if self._osc_shown() and self.isVisible():
            timer.start()
        else:
            timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_osc_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_osc_timer()

    def _poll_osc(self) -> None:
        previous = self._osc_live
        self._osc_live = self._osc_source(2 * _OSC_FRAMES) if self._osc_source is not None else None
        if self._osc_live is not None or previous is not None:       # à l'arrêt, la fenêtre fixe n'a pas à se repeindre
            self.update()

    def set_tunable(self, fields: tuple) -> None:
        """Les champs (parmi « volume », « tempo », « pitch ») que cette musique accepte."""
        self._tunable = tuple(fields)

    def set_fades(self, fade_in: int, fade_out: int, editable: bool) -> None:
        self._fades = (int(fade_in), int(fade_out))
        self._fades_editable = bool(editable)
        self._redraw()

    @property
    def gesturing(self) -> bool:
        """Un glisser de réglage est en cours (l'éditeur attend qu'il finisse pour redessiner l'onde)."""
        return self._gesture is not None and self._gesture.field not in (None, _SEEK)

    def set_playhead(self, seconds: float) -> None:
        """La tête de lecture bouge à chaque image : on ne repeint que sa bande (l'onde est en cache)."""
        old, self._playhead = self._playhead, float(seconds)
        for value in (old, self._playhead):
            if value >= 0:
                x = int(self._x_of(value))
                self.update(QRect(x - 3, 0, 7, self.height()))

    def set_scope(self, scope: tuple | None) -> None:
        """La section sélectionnée : ses bornes sur la règle, le reste de l'onde en retrait. (Elle se règle dans la
        bande des ordres, pas ici.)"""
        self._scope = scope
        self._redraw()

    def set_cue(self, seconds: float) -> None:
        """La poignée de départ bouge avec le geste : comme la tête de lecture, elle est hors du cache."""
        old, self._cue = self._cue, max(0.0, float(seconds))
        if self._osc_shown():
            self.update()                       # la fenêtre fixe de l'oscilloscope suit la poignée
            return
        for value in (old, self._cue):
            x = int(self._x_of(value))
            self.update(QRect(x - _CUE_HALF - 1, 0, 2 * _CUE_HALF + 3, self.height()))

    @property
    def cue(self) -> float:
        return self._cue

    def _redraw(self) -> None:
        self._cache = None
        self.update()

    def resizeEvent(self, event):
        self._cache = None
        self._place_mode_switch()
        super().resizeEvent(event)

    @property
    def seconds(self) -> float:
        return self._seconds

    # ── Géométrie ─────────────────────────────────────────────────

    def _x_of(self, seconds: float) -> float:
        return seconds / self._seconds * self.width() if self._seconds > 0 else 0.0

    def _seconds_of(self, x: float) -> float:
        return max(0.0, min(self._seconds, x / max(1, self.width()) * self._seconds))

    def _display_seconds(self) -> float:
        """Durée temporaire donnée par le potard de tempo, sans modifier la
        frise exacte tant que le rendu de fond n'est pas prêt."""
        return self._seconds * self._render_tempo / max(1, self._display_tempo)

    def _display_x_of(self, seconds: float) -> float:
        duration = self._display_seconds()
        return seconds / duration * self.width() if duration > 0 else 0.0

    def _fade_x(self, which: str) -> float:
        """L'abscisse de la poignée d'un fondu : la fin de la rampe, mesurée depuis son bord."""
        fade_in, fade_out = self._fades
        if which == "fade_in":
            return self._x_of(fade_in / _FRAMES_PER_SECOND)
        return self._x_of(self._seconds - fade_out / _FRAMES_PER_SECOND)

    def _ramp_x(self) -> float:
        """L'abscisse de la poignée du fondu d'un effet : le début de sa rampe, ou la fin de la plage gardée sans rampe."""
        return self._x_of((self._ramp[0] if self._ramp else self._loop[1]) / 1000)

    def _handle_at(self, x: float, y: float) -> str | None:
        """La poignée sous le pointeur : un fondu (bande du bas) avant une borne de boucle."""
        if self._seconds <= 0 or self._osc_shown():
            return None
        if self._ramp_editable and self._loop and y >= self.height() - _FADE_BAND:
            if abs(x - self._ramp_x()) <= _GRAB:
                return "ramp"
        if self._fades_editable and y >= self.height() - _FADE_BAND:
            near = min(("fade_in", "fade_out"), key=lambda which: abs(x - self._fade_x(which)))
            if abs(x - self._fade_x(near)) <= _GRAB:
                return near
        if not (self._editable and self._loop):
            return None
        start_x, end_x = (self._x_of(ms / 1000) for ms in self._loop)
        if abs(x - start_x) <= _GRAB and abs(x - start_x) <= abs(x - end_x):
            return "start"
        return "end" if abs(x - end_x) <= _GRAB else None

    # ── La souris ─────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._seconds <= 0:
            return
        if e.position().y() < _RULER:                       # la règle : seule la poignée de départ se saisit
            if self._on_cue(e.position()):
                self._drag = "cue"
            return
        self._drag = self._handle_at(e.position().x(), e.position().y())
        self._gesture = _Gesture(e.position()) if self._drag is None else None

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag is None and self._gesture is None:
            grabbable = self._on_cue(pos) if pos.y() < _RULER else self._handle_at(pos.x(), pos.y())
            self.setCursor(Qt.CursorShape.SizeHorCursor if grabbable else Qt.CursorShape.ArrowCursor)
        elif self._drag == "cue":
            self._emit_cue(e, dragging=True)
        elif self._drag in ("fade_in", "fade_out"):
            self._move_fade(pos)
        elif self._drag == "ramp":
            self._move_ramp(pos)
        elif self._drag is not None:
            self._move_loop(pos.x())
        else:
            self._move_gesture(pos, e.modifiers())

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        drag, gesture = self._drag, self._gesture
        self._drag = self._gesture = self._overlay = None
        if gesture is not None and gesture.field == _SEEK:          # la main lâche la tête de lecture
            self.seek_requested.emit(self._seconds_of(e.position().x()), False)
        self.update()
        if drag in ("fade_in", "fade_out"):
            self.fades_changed.emit(*self._fades)
        elif drag == "ramp":
            self.ramp_changed.emit(self._ramp_frames())
        elif drag == "cue":
            pass
        elif drag is not None:
            self.loop_changed.emit(*self._loop)
        elif gesture is not None and gesture.field not in (None, _SEEK):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.tuning_released.emit()

    def _cue_x(self) -> float:
        """L'abscisse de la poignée de départ, tenue dans le widget (en butée, elle reste saisissable)."""
        return min(max(self._x_of(self._cue), _CUE_HALF + 0.5), self.width() - _CUE_HALF - 0.5)

    def _on_cue(self, pos: QPointF) -> bool:
        return (self._cue_shown and not self._osc_shown() and pos.y() < _RULER
                and abs(pos.x() - self._cue_x()) <= _CUE_HALF + 2)

    def _emit_cue(self, e, dragging: bool) -> None:
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.cue_requested.emit(self._seconds_of(e.position().x()), shift, dragging)

    def _move_loop(self, x: float) -> None:
        ms = round(self._seconds_of(x) * 1000)
        start, end = self._loop
        if self._drag == "start":
            start = max(0, min(ms, end - _MIN_LOOP_MS))
        else:
            end = min(round(self._seconds * 1000), max(ms, start + _MIN_LOOP_MS))
        self._loop = (start, end)
        self.loop_moving.emit(start, end)
        self._redraw()

    def _move_fade(self, pos: QPointF) -> None:
        """Un fondu va de son bord à la poignée ; il ne dépasse ni son plafond ni la piste."""
        longest = min(FADE_MAX_FRAMES, round(self._seconds * _FRAMES_PER_SECOND))
        seconds = self._seconds_of(pos.x())
        if self._drag == "fade_in":
            frames = round(seconds * _FRAMES_PER_SECOND)
            self._fades = (max(0, min(longest, frames)), self._fades[1])
        else:
            frames = round((self._seconds - seconds) * _FRAMES_PER_SECOND)
            self._fades = (self._fades[0], max(0, min(longest, frames)))
        frames = self._fades[0 if self._drag == "fade_in" else 1]
        key = "sndedit.gesture_fade_in" if self._drag == "fade_in" else "sndedit.gesture_fade_out"
        x = self._fade_x(self._drag)
        self._overlay = ("v", x, None, QPointF(x, self.height() - _FADE_BAND),
                         label(key, frames=frames))
        self._redraw()

    def _ramp_frames(self) -> int:
        """Le fondu de sortie que la rampe dessinée représente, en frames."""
        if not self._ramp:
            return 0
        return round((self._ramp[1] - self._ramp[0]) * _FRAMES_PER_SECOND / 1000)

    def _move_ramp(self, pos: QPointF) -> None:
        """La poignée glisse sur la plage gardée : la rampe va d'elle à la fin de la plage, sans dépasser ni le plafond des
        fondus ni le début de la plage."""
        start, end = self._loop
        longest = min(FADE_MAX_FRAMES, round((end - start) * _FRAMES_PER_SECOND / 1000))
        ms = self._seconds_of(pos.x()) * 1000
        frames = max(0, min(longest, round((end - ms) * _FRAMES_PER_SECOND / 1000)))
        self._ramp = (end - round(frames * 1000 / _FRAMES_PER_SECOND), end) if frames else None
        x = self._ramp_x()
        self._overlay = ("v", x, None, QPointF(x, self.height() - _FADE_BAND),
                         label("sndedit.gesture_fade_out", frames=frames))
        self.ramp_moving.emit(frames)
        self._redraw()

    def _move_gesture(self, pos: QPointF, modifiers) -> None:
        """Un glisser dans l'onde. Le sens décide du réglage une fois que le pointeur s'est assez éloigné ;
        la valeur se lit ensuite sur le déplacement DEPUIS le point de départ (une largeur d'onde = 100 points,
        une hauteur d'onde = 100 points)."""
        gesture = self._gesture
        dx, dy = pos.x() - gesture.origin.x(), pos.y() - gesture.origin.y()
        if gesture.field is None:
            if max(abs(dx), abs(dy)) < _AXIS_LOCK:
                return
            if abs(dx) >= abs(dy):
                field = "tempo" if modifiers & Qt.KeyboardModifier.ShiftModifier else _SEEK
            else:
                field = "volume" if modifiers & Qt.KeyboardModifier.ShiftModifier else "pitch"
            if field == _SEEK and self._osc_shown():            # la fenêtre de l'oscilloscope n'a pas de tête de lecture
                self._gesture = None
                return
            if field != _SEEK and field not in self._tunable:   # ce réglage n'existe pas ici : le geste s'éteint
                self._gesture = None
                return
            gesture.field = field
            if field != _SEEK:
                gesture.start = self._mix[field]
            self.setCursor(Qt.CursorShape.SizeVerCursor if field in ("pitch", "volume") else Qt.CursorShape.SizeHorCursor)
        field = gesture.field
        if field == _SEEK:                                  # un glisser horizontal pose la tête de lecture sous le pointeur
            self.seek_requested.emit(self._seconds_of(pos.x()), True)
            return
        low, high = _MIX_RANGES[field]
        plot_height = max(1, self.height() - _RULER)
        points = dx / max(1, self.width()) * 100 if field == "tempo" else -dy / plot_height * 100
        value = max(low, min(high, round(gesture.start + points)))
        # La barre se pose sur la valeur (pas sur le pointeur) : arrivée au bout de la plage, elle s'y arrête.
        shift = (value - gesture.start) / 100
        if field == "tempo":
            bar = gesture.origin.x() + shift * self.width()
            anchor, sense, origin = QPointF(bar, pos.y()), "v", gesture.origin.x()
        else:
            bar = gesture.origin.y() - shift * plot_height
            anchor, sense, origin = QPointF(pos.x(), bar), "h", gesture.origin.y()
        self._overlay = (sense, bar, origin, anchor, label(f"sndedit.gesture_{field}", value=value))
        self.update()
        if value != self._mix[field]:
            self._mix[field] = value
            self.tuning_moving.emit(field, value)

    # ── Le dessin ─────────────────────────────────────────────────

    def paintEvent(self, _e):
        ratio = self.devicePixelRatioF()
        if self._cache is None or self._cache.size() != self.size() * ratio:
            self._cache = QPixmap(self.size() * ratio)
            self._cache.setDevicePixelRatio(ratio)
            still = QPainter(self._cache)
            self._paint_still(still)
            still.end()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        if self._osc_shown():
            self._paint_osc(p)
        elif self._seconds > 0 and self._cue_shown:
            self._paint_cue(p)
        if self._seconds > 0 and self._playhead >= 0 and not self._osc_shown():
            x = self._x_of(self._playhead)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 1.5))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        if self._overlay is not None:
            self._paint_overlay(p)

    def _paint_cue(self, p: QPainter) -> None:
        """La poignée de départ : un repère sur la règle, et un filet pointillé qui descend dans l'onde."""
        x = self._cue_x()
        faint = QColor(C.ACCENT); faint.setAlpha(110)
        p.setPen(QPen(faint, 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, _RULER), QPointF(x, self.height()))
        p.setPen(QPen(QColor(C.BG_BASE), 1))
        p.setBrush(QColor(C.ACCENT))
        p.drawPolygon(QPolygonF([QPointF(x - _CUE_HALF, 2), QPointF(x + _CUE_HALF, 2),
                                 QPointF(x + _CUE_HALF, _RULER - 8), QPointF(x, _RULER - 1),
                                 QPointF(x - _CUE_HALF, _RULER - 8)]))
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_overlay(self, p: QPainter) -> None:
        """La barre qui accompagne le geste (verticale pour un déplacement horizontal, horizontale sinon), le
        point de départ en pointillé, et la pastille qui donne la valeur."""
        sense, bar, origin, anchor, text = self._overlay
        w, h = self.width(), self.height()
        if origin is not None:
            faint = QColor(C.ACCENT); faint.setAlpha(90)
            p.setPen(QPen(faint, 1, Qt.PenStyle.DashLine))
            p.drawLine(*((QPointF(origin, 0), QPointF(origin, h)) if sense == "v"
                         else (QPointF(0, origin), QPointF(w, origin))))
        p.setPen(QPen(QColor(C.ACCENT), 1.5))
        p.drawLine(*((QPointF(bar, 0), QPointF(bar, h)) if sense == "v"
                     else (QPointF(0, bar), QPointF(w, bar))))
        p.setFont(QFont(T.MONO, T.SM))
        metrics = p.fontMetrics()
        chip_w, chip_h = metrics.horizontalAdvance(text) + 16, metrics.height() + 8
        x = anchor.x() + 12
        if x + chip_w > w:                                  # pas la place à droite : la pastille passe à gauche
            x = anchor.x() - 12 - chip_w
        chip = QRectF(max(2.0, x), max(2.0, min(h - chip_h - 2, anchor.y() - chip_h - 8)), chip_w, chip_h)
        p.fillRect(chip, QColor(C.BG_RAISED))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(chip)
        p.setPen(QPen(QColor(C.TEXT_HI)))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_still(self, p: QPainter) -> None:
        """Tout ce qui ne bouge pas avec la lecture : fond, règle, bandes, onde, poignées. Peint UNE fois par
        changement et gardé — repeindre mille colonnes à chaque image figeait l'écran pendant l'écoute."""
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        plot = QRectF(0, _RULER, w, h - _RULER)
        self._paint_ruler(p, w)
        if self._osc_shown():                               # une fenêtre de 30 ms : ni bandes, ni boucle, ni fondus
            self._paint_osc_frame(p, plot)
            return
        if self._seconds <= 0 or not len(self._peaks):
            return
        for start, end, color in self._bands:
            band = QColor(color); band.setAlpha(46)
            p.fillRect(QRectF(self._x_of(start), plot.top(), self._x_of(end) - self._x_of(start),
                              plot.height()), band)
        self._paint_grid(p, plot)
        if self._loop:
            region = QColor(C.ACCENT_COOL); region.setAlpha(34)
            lo, hi = (self._x_of(ms / 1000) for ms in self._loop)
            p.fillRect(QRectF(lo, plot.top(), hi - lo, plot.height()), region)
        self._paint_wave(p, plot)
        if self._loop:
            self._paint_loop(p, plot)
        if self._ramp:
            self._paint_ramp(p, plot)
        if self._ramp_editable and self._loop:
            self._paint_ramp_handle(p, plot)
        if self._fades_editable:
            self._paint_fades(p, plot)
        if self._scope is not None:
            self._paint_scope(p, plot)

    def _paint_scope(self, p: QPainter, plot: QRectF) -> None:
        """Les bornes de lecture, comme sur un logiciel de montage : la plage sur la règle, une borne à chaque bout,
        et l'onde hors plage assombrie — ce qui reste clair est ce qui va boucler."""
        start, end, color = self._scope
        lo, hi = self._x_of(start), self._x_of(end)
        if not self._loop:               # un WAV assombrit déjà lui-même ce qui est hors de la plage
            shade = QColor(C.BG_BASE); shade.setAlpha(150)
            p.fillRect(QRectF(0, plot.top(), lo, plot.height()), shade)
            p.fillRect(QRectF(hi, plot.top(), plot.width() - hi, plot.height()), shade)
        fill = QColor(color); fill.setAlpha(90)
        p.fillRect(QRectF(lo, 0, hi - lo, _RULER - 1), fill)
        p.setPen(QPen(color, 2))
        for x, inward in ((lo + 1, 6), (hi - 1, -6)):
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            p.drawLine(QPointF(x, 1), QPointF(x + inward, 1))
            p.drawLine(QPointF(x, _RULER - 2), QPointF(x + inward, _RULER - 2))

    def _paint_ramp(self, p: QPainter, plot: QRectF) -> None:
        """Le fondu de sortie d'un effet : la part étouffée de l'onde assombrie au-dessus d'une diagonale, comme les fondus
        d'une musique."""
        lo, hi = (self._x_of(ms / 1000) for ms in self._ramp)
        shade = QColor(C.BG_BASE); shade.setAlpha(150)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shade)
        p.drawPolygon(QPolygonF([QPointF(hi, plot.top()), QPointF(lo, plot.top()), QPointF(hi, plot.bottom())]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.ACCENT_WARM), 1))
        p.drawLine(QPointF(lo, plot.top()), QPointF(hi, plot.bottom()))

    def _paint_ramp_handle(self, p: QPainter, plot: QRectF) -> None:
        """La poignée du fondu, sur le bas de l'onde, comme celles des fondus d'une musique."""
        p.setBrush(QColor(C.ACCENT_WARM))
        p.setPen(QPen(QColor(C.BG_BASE), 1))
        x = max(5.0, min(plot.width() - 5.0, self._ramp_x()))
        p.drawEllipse(QPointF(x, plot.bottom() - _FADE_BAND / 2), 4.5, 4.5)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_fades(self, p: QPainter, plot: QRectF) -> None:
        """Chaque fondu : la rampe de volume (une diagonale), la part étouffée de l'onde assombrie, et la poignée
        qui règle sa durée, posée sur le bas de l'onde."""
        w = plot.width()
        shade = QColor(C.BG_BASE); shade.setAlpha(150)
        fade_in_x, fade_out_x = self._fade_x("fade_in"), self._fade_x("fade_out")
        ramps = (
            (fade_in_x, QPolygonF([QPointF(0, plot.top()), QPointF(fade_in_x, plot.top()), QPointF(0, plot.bottom())]),
             QPointF(0, plot.bottom()), QPointF(fade_in_x, plot.top())),
            (fade_out_x, QPolygonF([QPointF(w, plot.top()), QPointF(fade_out_x, plot.top()), QPointF(w, plot.bottom())]),
             QPointF(fade_out_x, plot.top()), QPointF(w, plot.bottom())),
        )
        for x, area, line_from, line_to in ramps:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shade)
            p.drawPolygon(area)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(C.ACCENT_WARM), 1))
            if line_from.x() != line_to.x():
                p.drawLine(line_from, line_to)
            p.setBrush(QColor(C.ACCENT_WARM))
            p.setPen(QPen(QColor(C.BG_BASE), 1))
            p.drawEllipse(QPointF(max(5.0, min(w - 5.0, x)), plot.bottom() - _FADE_BAND / 2), 4.5, 4.5)
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_ruler(self, p: QPainter, w: int) -> None:
        p.setPen(QPen(QColor(C.BORDER)))
        p.drawLine(0, _RULER - 1, w, _RULER - 1)
        if self._seconds <= 0 or self._osc_shown():             # l'oscilloscope n'a pas de frise à graduer
            return
        duration = self._display_seconds()
        step = next((s for s in _STEPS if self._display_x_of(s) >= 78), _STEPS[-1])
        p.setFont(QFont(T.MONO, T.XS))
        count = 0
        while count * step <= duration:
            t = count * step                                            # un produit et non une somme : les fractions ne dérivent pas
            x = self._display_x_of(t)
            p.setPen(QPen(QColor(C.BORDER_MID)))
            p.drawLine(QPointF(x, _RULER - 6), QPointF(x, _RULER - 1))
            if x < w - self._ruler_reserved() - 30:                            # le bout de la règle est à la durée et à la bascule
                p.setPen(QPen(QColor(C.TEXT_DIM)))
                p.drawText(QPointF(x + 4, _RULER - 7), _time_text(t, step))
            count += 1
        p.setPen(QPen(QColor(C.ACCENT_WARM if self._display_tempo != 100 else C.TEXT_NORM)))   # la durée totale, à l'accent quand le tempo la change
        p.drawText(QRectF(w - self._ruler_reserved(), 0, _DURATION_WIDTH, _RULER - 3),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _duration_text(duration))

    def _paint_grid(self, p: QPainter, plot: QRectF) -> None:
        """Repères doux : ils donnent l'échelle, sans découper l'onde en cases."""
        grid = QColor(C.BORDER_MID); grid.setAlpha(85)
        p.setPen(QPen(grid, 1))
        for fraction in (0.25, 0.5, 0.75):
            y = plot.top() + fraction * plot.height()
            p.drawLine(QPointF(0, y), QPointF(plot.width(), y))
        if self._seconds <= 0:
            return
        duration = self._display_seconds()
        step = next((s for s in _STEPS if self._display_x_of(s) >= 78), _STEPS[-1])
        count = 1
        while count * step < duration:
            x = self._display_x_of(count * step)
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            count += 1

    def _paint_wave(self, p: QPainter, plot: QRectF) -> None:
        """Une silhouette continue plutôt qu'un rideau de traits verticaux.

        Les crêtes min/max restent exactes par pixel, mais elles sont réunies
        en une forme douce, plus facile à lire que les pointes isolées d'un
        module dense. La zone de boucle garde un peu plus de présence.

        Le remplissage est calculé en numpy, colonne par colonne, et posé comme une image : remplir un polygone de
        deux mille sommets coûtait 20 à 40 ms par rendu d'onde, ce qui comptait quand l'onde se refait pendant le geste.
        """
        mid = plot.center().y()
        baseline = QColor(C.ACCENT_COOL); baseline.setAlpha(100)
        p.setPen(QPen(baseline, 1))
        p.drawLine(QPointF(0, mid), QPointF(plot.width(), mid))
        ratio = self.devicePixelRatioF()
        width, height = max(1, round(plot.width() * ratio)), max(1, round(plot.height() * ratio))
        n = len(self._peaks)
        columns = self._peaks[np.arange(width) * n // width]            # (min, max) de chaque colonne en pixels physiques
        strength = np.full(width, _WAVE_LIT, dtype=np.float32)          # l'opacité du corps, colonne par colonne
        if self._loop:                                                  # hors de la boucle, l'onde reste en retrait
            lo, hi = (min(width, max(0, round(self._x_of(ms / 1000) * ratio))) for ms in self._loop)
            strength[:lo] = strength[hi:] = _WAVE_DIM
        scale = (plot.height() / 2 - 8) * self._display_gain * ratio   # le gain redimensionne autour de l'axe
        centre = (mid - plot.top()) * ratio
        top, bottom = centre - columns[:, 1] * scale, centre - columns[:, 0] * scale
        pixels = self._wave_pixels(top, bottom, strength, height)      # vit jusqu'au dessin : l'image n'en fait pas de copie
        image = QImage(pixels.data, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        p.drawImage(QPointF(0, plot.top()), image)
        xs = ((np.arange(width) + 0.5) / ratio).tolist()
        edges = [[QPointF(x, y) for x, y in zip(xs, (plot.top() + side / ratio).tolist())] for side in (top, bottom)]
        cuts = [0, *(np.flatnonzero(np.diff(strength)) + 1).tolist(), width]
        for start, end in zip(cuts, cuts[1:]):                          # le liseré suit l'opacité du corps
            edge = QColor(C.ACCENT_COOL); edge.setAlpha(min(220, int(strength[start]) + 35))
            p.setPen(QPen(edge, 0.8))
            for points in edges:
                p.drawPolyline(QPolygonF(points[start:end + 1]))

    @staticmethod
    def _wave_pixels(top: np.ndarray, bottom: np.ndarray, strength: np.ndarray, height: int) -> np.ndarray:
        """Le corps de l'onde, un pixel ARGB prémultiplié par case : par colonne, la part de chaque ligne entre `top`
        et `bottom` (les bords y sont fractionnaires, donc lissés), teintée d'un dégradé vertical — plus dense à
        l'axe que sur les bords."""
        pixels = np.zeros((height, len(top)), dtype=np.uint32)
        first, last = max(0, int(top.min())), min(height, int(np.ceil(bottom.max())) + 1)    # hors de ces lignes : rien
        if last > first:
            top, bottom = top.astype(np.float32), bottom.astype(np.float32)
            rows = np.arange(first, last, dtype=np.float32)[:, None]
            coverage = np.minimum(rows + 1, bottom) - np.maximum(rows, top)
            np.clip(coverage, 0, 1, out=coverage)
            fade = 1 - np.abs((rows + 0.5) / height * 2 - 1)
            rim = np.maximum(20, strength // 2)
            opacity = (rim + (strength - rim) * fade) * coverage + 0.5          # 0..255 : l'alpha de chaque pixel
            pixels[first:last] = _wave_palette()[opacity.astype(np.uint8)]
        return pixels

    def _paint_osc_frame(self, p: QPainter, plot: QRectF) -> None:
        """Le cadre de l'oscilloscope, peint une fois : l'axe, des repères d'amplitude, un repère toutes les 5 ms."""
        grid = QColor(C.BORDER_MID); grid.setAlpha(85)
        p.setPen(QPen(grid, 1))
        for fraction in (0.25, 0.75):
            y = plot.top() + fraction * plot.height()
            p.drawLine(QPointF(0, y), QPointF(plot.width(), y))
        for ms in range(5, int(_OSC_FRAMES * 1000 / GBA_MIX_RATE), 5):
            x = ms / 1000 * GBA_MIX_RATE / _OSC_FRAMES * plot.width()
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        axis = QColor(C.ACCENT_COOL); axis.setAlpha(100)
        p.setPen(QPen(axis, 1))
        p.drawLine(QPointF(0, plot.center().y()), QPointF(plot.width(), plot.center().y()))

    def _osc_samples(self):
        """Ce que l'oscilloscope trace : le son qui joue (déjà au volume, à la hauteur et au tempo du moment), sinon
        une fenêtre du rendu à la poignée de départ — que le volume éteint, lui aussi, tout de suite."""
        if self._osc_live is not None:
            return self._osc_live, True
        if self._osc_still is None:
            return None, False
        window = self._osc_still(self._cue, 2 * _OSC_FRAMES)
        return (None if window is None else window * self._display_gain), False

    def _paint_osc(self, p: QPainter) -> None:
        """La trace, relue à chaque image : peinte hors du cache, qui garde le cadre. Elle part d'un franchissement
        montant de zéro, comme le déclenchement d'un vrai oscilloscope : une note tenue reste en place au lieu de défiler."""
        samples, live = self._osc_samples()
        plot = QRectF(0, _RULER, self.width(), self.height() - _RULER)
        if samples is not None and len(samples) >= 2 * _OSC_FRAMES:
            rising = np.flatnonzero((samples[:_OSC_FRAMES] < 0) & (samples[1:_OSC_FRAMES + 1] >= 0))
            start = int(rising[0]) + 1 if len(rising) else 0
            shown = np.clip(samples[start:start + _OSC_FRAMES], -1.0, 1.0) / _OSC_FULL
            xs = np.linspace(0, plot.width(), len(shown)).tolist()
            ys = (plot.center().y() - np.clip(shown, -1.0, 1.0) * (plot.height() / 2 - 6)).tolist()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(C.ACCENT_COOL), 1.5))
            p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in zip(xs, ys)]))
        p.setFont(QFont(T.MONO, T.XS))
        p.setPen(QPen(QColor(C.TEXT_DIM)))
        window = round(_OSC_FRAMES * 1000 / GBA_MIX_RATE)
        text = (label("sndedit.scope_live", ms=window) if live else
                label("sndedit.scope_still", ms=window, time=f"{int(self._cue) // 60}:{int(self._cue) % 60:02d}"))
        p.drawText(QPointF(6, plot.bottom() - 6), text)

    def _paint_loop(self, p: QPainter, plot: QRectF) -> None:
        for ms in self._loop:
            x = self._x_of(ms / 1000)
            p.setPen(QPen(QColor(C.ACCENT_COOL), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if self._editable:
                p.fillRect(QRectF(x - 4, plot.top(), 8, 8), QColor(C.ACCENT_COOL))
