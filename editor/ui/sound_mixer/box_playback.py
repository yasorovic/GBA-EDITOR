"""
ui/sound_mixer/box_playback.py — Écouter une MusicBox comme la ROM la jouera.

Le but est une boucle d'itération sans build : on règle un fondu, on clique un
nœud, on entend exactement ce que la console fera. Toute la décision est dans
`core/engine_emulation/music_deck.py`, qui transcrit `music_transition_tick()`
à la frame près ; ce fichier ne fait que rendre les modules, tenir le cache et
pousser les échantillons dans la carte son.

Deux fidélités valent d'être dites, parce qu'elles se voient à l'usage :

  - **Cliquer un nœud, c'est émettre un déclencheur.** L'aperçu cherche l'arête
    qui mène de l'état courant vers celui-là, et joue SA transition. S'il n'y a
    pas d'arête, il ne se passe rien — parce qu'il ne se passerait rien sur la
    console. Inventer un fondu par défaut ferait régler à l'oreille quelque
    chose que le jeu ne jouera jamais.
  - **`intensity` n'est pas jouée**, parce que le codegen ne l'émet pas : le C
    ne pose que l'id du module, la boucle et le volume.
"""
from __future__ import annotations

from ui.common.labels import label
from dataclasses import replace
from pathlib import Path
from typing import Optional

import sys
import traceback

import numpy as np
from PyQt6.QtCore import (
    QCoreApplication, QIODevice, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import render_module_detailed, GBA_MIX_RATE
from core.engine_emulation.module_stream import StreamTrack
from core.engine_emulation.music_deck import MusicDeck, Track, MODULE_FULL
from core.engine_emulation.xm_file import parse_xm
from core.models.audio import Jingle, Music, Sfx, volume_to_module
from core.sfx_render import preview_file
from core.music_structure import music_info_row, wav_boundaries
from core.wav_module import effective_rate, wav_to_xm
from core.models.sound_box import TRANSITION_CUT


# Les rendus gardés : assez pour les états d'une boîte, pas pour chaque cran d'un curseur.
_TRACK_CACHE = 12
_SINK_BUFFER_SECONDS = 0.05      # le tampon de la carte son : plus court, le scrub colle au geste ; trop court, il craque
_SCOPE_TAIL = 8192               # trames gardées derrière le deck pour l'oscilloscope : de quoi couvrir l'avance sur l'oreille


def load_playable(path: Path, wav: bool, rate: int, bounds: tuple):
    """Le module que le build écrirait pour ce fichier : un module tracker tel quel, un WAV encapsulé."""
    return parse_xm(wav_to_xm(path, effective_rate(rate), bounds)) if wav else load_module(path)


def render_track(path: Path, wav: bool, rate: int, bounds: tuple, tempo_q: int, pitch_q: int,
                 checkpoint=None) -> Track:
    """Le rendu entier d'un fichier, sans rien d'autre : ni Qt, ni cache, ni asset. `checkpoint` : cf.
    `render_module_detailed`."""
    mod = load_playable(path, wav, rate, bounds)
    rendered = render_module_detailed(
        mod, GBA_MIX_RATE, (tempo_q or MODULE_FULL) / MODULE_FULL, (pitch_q or MODULE_FULL) / MODULE_FULL,
        checkpoint)
    return Track(pcm=rendered.pcm, marks=rendered.marks, restart=mod.restart, order_count=len(mod.order),
                 levels=rendered.levels)


class _DeckDevice(QIODevice):
    """Le robinet : Qt tire, le deck produit."""

    def __init__(self, deck: MusicDeck, parent=None):
        super().__init__(parent)
        self._deck = deck
        # Trames tirées depuis l'ouverture : avec ce que la carte son a jouées,
        # elles donnent l'avance du deck sur l'oreille.
        self.pulled_frames = 0
        # Les trames tirées jusqu'à la fin du SON : celles du dernier paquet où le deck jouait encore (la fin de ce paquet est
        # du silence, qu'on compte en trop). Tant que la carte son n'a pas joué ce nombre, le son n'a pas fini de
        # s'entendre — même si le deck, lui, l'a déjà tout produit.
        self.sound_frames = 0
        # Les dernières trames tirées, pour l'oscilloscope de l'écran Son. Le thread audio REMPLACE ce tableau d'un
        # bloc (jamais il ne l'écrit en place) : l'interface en lit une référence, sans verrou.
        self.tail = np.zeros((0, 2), dtype=np.int16)

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        # Un module bouclé ne tarit jamais ; le silence en est aussi.
        return 1 << 20

    def readData(self, maxlen: int) -> bytes:
        n = int(maxlen) // 4          # 2 canaux × 2 octets
        if n <= 0:
            return b""
        was_playing = self._deck.playing
        try:
            pcm = self._deck.pull(n)
        except Exception:
            # Ici on est dans le thread audio : une exception qui remonterait à Qt arrêterait tout le programme.
            traceback.print_exc(file=sys.stderr)
            pcm = np.zeros((n, 2), dtype=np.int16)
        self.pulled_frames += pcm.shape[0]
        if was_playing:
            self.sound_frames = self.pulled_frames
        self.tail = np.concatenate((self.tail, pcm))[-_SCOPE_TAIL:]
        return pcm.tobytes()

    def writeData(self, data) -> int:
        return 0


class _AudioOutput(QObject):
    """La carte son, DANS SON THREAD : Qt y tire le deck par paquets de quelques dizaines de millisecondes. Sur le
    thread de l'interface, la moindre pause (un repaint, un rendu posé) coupait le son. Ici, seuls le deck et son
    verrou sont partagés."""

    def __init__(self, deck: MusicDeck):
        super().__init__()
        self._deck = deck
        self._sink: Optional[QAudioSink] = None
        self._device: Optional[_DeckDevice] = None
        self._timer: Optional[QTimer] = None
        # Publiés pour l'interface, qui ne touche pas à la carte son depuis son thread.
        self.queued_frames = 0          # tiré du deck mais pas encore joué
        self.active = False

    @pyqtSlot(float)
    def open(self, volume: float):
        fmt = QAudioFormat()
        fmt.setSampleRate(GBA_MIX_RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt)
        # Un tampon court : ce qu'on entend suit le geste (scrub, saut) au lieu de traîner derrière lui.
        self._sink.setBufferSize(round(GBA_MIX_RATE * _SINK_BUFFER_SECONDS) * 4)
        self._sink.setVolume(volume)
        self._device = _DeckDevice(self._deck)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink.start(self._device)
        self._timer = QTimer(self)
        self._timer.setInterval(5)
        self._timer.timeout.connect(self._publish)
        self._timer.start()
        self.active = True

    @pyqtSlot()
    def close(self):
        self.active = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        if self._device is not None:
            self._device.close()
            self._device = None
        self.queued_frames = 0

    @pyqtSlot(float)
    def set_volume(self, volume: float):
        if self._sink is not None:
            self._sink.setVolume(volume)

    def still_audible(self) -> bool:
        """Le son tiré du deck n'a pas fini d'être JOUÉ par la carte son. Le deck tire loin devant l'oreille : un son court
        (un effet de 0,15 s) est tout entier produit dès le premier paquet, `deck.playing` retombe aussitôt, et l'interface qui
        s'en sert pour arrêter l'aperçu fermait la carte son avant qu'on ait rien entendu."""
        device = self._device
        if not self.active or device is None:
            return False
        # Les trames jouées se déduisent de ce que `_publish` a publié : l'interface ne touche pas à la carte son depuis son thread.
        return device.pulled_frames - self.queued_frames < device.sound_frames

    def heard_window(self, frames: int):
        """Les `frames` dernières trames qui S'ENTENDENT (mono, −1..1), ou None s'il n'y en a pas encore : le deck a
        tiré devant la carte son, on retire ce qui n'est pas encore joué (cf. `BoxPlayer._heard_frame`)."""
        device = self._device
        if not self.active or device is None:
            return None
        tail = device.tail
        end = tail.shape[0] - self.queued_frames
        if end < frames:
            return None
        return tail[end - frames:end].astype(np.float32).mean(axis=1) / 32768.0

    def _publish(self):
        if self._sink is not None and self._device is not None:
            played = int(self._sink.processedUSecs() * GBA_MIX_RATE / 1_000_000)
            self.queued_frames = max(0, self._device.pulled_frames - played)


class BoxPlayer(QObject):
    """Joue la MusicBox courante comme la ROM la jouerait."""

    # L'état LOGIQUE courant — il change dès le déclenchement, comme
    # `g_music_box_state_cur` dans main.c, avant même que le fondu s'entende.
    state_changed = pyqtSignal(str)
    # Nom de la piste effectivement résolue, et son état de boucle.
    track_changed = pyqtSignal(str, bool)
    # Ce qu'il y a à dire à l'auteur : pas d'arête, module manquant…
    message = pyqtSignal(str)
    # Les ordres à la carte son : exécutés dans son thread, l'appelant attend qu'ils soient faits.
    _output_open = pyqtSignal(float)
    _output_close = pyqtSignal()
    _output_volume = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._box = None
        self._deck = MusicDeck(GBA_MIX_RATE)
        self._output: Optional[_AudioOutput] = None      # créé à la première lecture, avec son thread
        self._thread: Optional[QThread] = None
        self._current = ""
        self._volume = 0.8
        # Modules rendus. Le rendu d'un morceau long prend jusqu'à une seconde : le
        # refaire à chaque transition rendrait l'aperçu inutilisable. La clé porte
        # tout ce qui change CE QUE LE FICHIER RENDRA — le chemin, le tempo, la
        # hauteur, le taux, la boucle d'un WAV — pour qu'un réglage modifié ne rejoue
        # pas l'ancien rendu. Les fondus et la section d'un module, eux, ne changent
        # pas le rendu : ils se posent sur le `Track` à chaque appel.
        self._tracks: dict[tuple, Track] = {}
        self._previewed = None       # (asset, section) que l'aperçu joue, ou None
        self._hold = None            # (seconde, échantillon d'atterrissage) : la tête s'affiche là tant que le saut ne s'entend pas
        self._last_seek = None       # (ordre, ligne) où le dernier saut a posé la tête : un glisser n'en relance pas le même

    # ── Chargement ────────────────────────────────────────────────

    def load(self, project, box):
        was_on = self.running
        self.stop()
        self._project, self._box = project, box
        self._current = ""
        if was_on:
            self.start()

    @property
    def running(self) -> bool:
        return self._output is not None and self._output.active

    @property
    def sounding(self) -> bool:
        """Un son se fait entendre : le deck en produit encore, ou la carte son joue encore ce qu'il a déjà produit. Faux
        seulement quand un son non bouclé a fini DE S'ENTENDRE — pas quand le deck a fini de le produire, qui arrive bien
        avant pour un son court."""
        if self._deck.playing:
            return True
        return self._output is not None and self._output.still_audible()

    @property
    def current_state(self) -> str:
        return self._current

    # ── Marche / arrêt ────────────────────────────────────────────

    def start(self):
        """Démarre sur l'état de départ — ce que fait `main()` au boot."""
        if self.running or self._box is None:
            return
        self._open_sink()

        start =self._box.start or (self._box.states[0].name
                                    if self._box.states else "")
        self._current = ""
        self._enter(start, transition=False)

    def _open_sink(self):
        if self._output is None:
            self._thread = QThread()
            self._thread.setObjectName("backstage-audio")
            self._output = _AudioOutput(self._deck)
            self._output.moveToThread(self._thread)
            blocking = Qt.ConnectionType.BlockingQueuedConnection
            self._output_open.connect(self._output.open, blocking)
            self._output_close.connect(self._output.close, blocking)
            self._output_volume.connect(self._output.set_volume, blocking)
            self._thread.start()
            QCoreApplication.instance().aboutToQuit.connect(self.shutdown)
        self._output_open.emit(self._volume)

    def shutdown(self):
        """Ferme la carte son et arrête son thread (à la sortie du programme)."""
        if self._thread is None:
            return
        self.stop()
        self._thread.quit()
        self._thread.wait(2000)
        self._thread = self._output = None

    def track_for(self, project, asset) -> Optional[Track]:
        """Le `Track` que le deck jouerait pour cet asset, rendu et mis en cache — ce que l'écran
        Son dessine (waveform, repères d'ordre) est donc EXACTEMENT ce qu'on entend."""
        return self._track_of_asset(project, asset)

    def waveform_render_request(self, project, asset):
        """Prépare un rendu d'onde hors-thread, sans toucher au cache depuis
        le worker. Retourne le rendu déjà en cache, ou les seuls arguments purs
        que `render_track` peut calculer sans Qt ni modèle mutable."""
        prepared = self._prepare(project, asset, asset.name)
        if prepared is None:
            return None
        _path, key, params, info = prepared
        cached = self._tracks.get(key)
        return key, params, info, self._finish(cached, info) if cached is not None else None

    def accept_waveform_render(self, key, info: tuple, track: Track) -> Track:
        """Mémorise dans le fil UI un rendu calculé par le worker."""
        self._remember(key, track)
        return self._finish(track, info)

    def preview(self, project, asset, section=None) -> bool:
        """Joue UN asset du Sound finder, hors de toute boîte.

        Même deck et même sortie que la boîte : ce qu'on entend est rendu
        comme la boîte le rendrait. Un effet joue une fois ; une musique suit
        sa propre boucle. Rend False (et dit pourquoi) si rien ne peut sonner.

        Avec `section` (une `MusicSection` de cet asset), la lecture COMMENCE à son début et
        boucle dessus : c'est le ▶ d'une ligne du tableau des sections. On rend l'asset avec CETTE
        section pour boucle par défaut — le même chemin que `music:set_section` à l'exécution.
        """
        played = replace(asset, loop_section=section.name) if section is not None else asset
        track = self._live_track(project, played)
        if track is None:
            return False
        if not self.running:
            self._open_sink()
        loop = bool(getattr(asset, "loop", False))
        start_at = 0
        if section is not None and track.loop_orders is not None:
            start_at = track.start_of(track.loop_orders[0]) or 0     # la section est en ordres, WAV compris
        self._current = ""
        self._previewed = (asset, section)
        self._hold = None
        self._deck.play(track, volume_to_module(asset.volume), loop, start_at)
        self.track_changed.emit(asset.name, loop)
        return True

    # ── Suivre les curseurs : volume, tempo, hauteur ──────────────

    def previewing(self, asset) -> bool:
        """Cet asset est-il celui que l'aperçu joue en ce moment ?"""
        return self._previewed is not None and self._previewed[0] is asset and self._deck.playing

    def scope_window(self, asset, frames: int):
        """Ce que l'aperçu de cet asset fait entendre à l'instant : les `frames` dernières trames, en mono (−1..1).
        None quand il ne joue pas, ou quand la carte son n'a pas encore joué assez de son pour remplir la fenêtre."""
        if self._output is None or not self.previewing(asset):
            return None
        return self._output.heard_window(frames)

    def set_preview_volume(self, asset):
        """Le volume de l'asset a changé : le deck le prend tout de suite, comme `music_set_volume`."""
        if self.previewing(asset):
            self._deck.set_volume(volume_to_module(asset.volume))

    def set_preview_tuning(self, asset):
        """Le tempo ou la hauteur de l'asset a changé : le rendu en direct les lit au tick suivant. Rien à
        refaire, rien à attendre — c'est tout l'intérêt de jouer le module tick par tick."""
        track = self._deck.track
        if self.previewing(asset) and isinstance(track, StreamTrack):
            _start, _end, tempo_q, pitch_q, _fi, _fo = music_info_row(asset)
            track.set_tuning((tempo_q or MODULE_FULL) / MODULE_FULL, (pitch_q or MODULE_FULL) / MODULE_FULL)

    def scrub(self, seconds: float) -> None:
        """La main tient la tête de lecture : la lecture automatique est suspendue, le son suit le geste (vitesse et
        sens compris). Il est lu dans le rendu entier de l'asset, la frise de l'écran."""
        track = self._deck.track
        reference = getattr(track, "reference", None) if isinstance(track, StreamTrack) else None
        if reference is None or not reference.marks:
            return
        self._deck.scrub_to(reference.pcm, seconds * GBA_MIX_RATE, self.position_seconds * GBA_MIX_RATE)

    def scrub_end(self, seconds: float) -> None:
        """La main lâche : la lecture reprend, en direct, à la ligne où elle l'a laissée."""
        if self._deck.scrubbing:
            self._deck.scrub_end()
            self.seek(seconds)

    def seek(self, seconds: float, repeat: bool = True) -> None:
        """Le geste « poser la tête de lecture » sur la frise de l'écran : l'aperçu repart de la LIGNE qui contient
        cette seconde. (La ROM ne saute qu'à l'ordre ; la précision en plus ne vaut que pour l'écoute.) `repeat`
        faux : un glisser qui reste sur la même ligne ne la relance pas à chaque pixel."""
        track = self._deck.track
        where = track.locate(seconds, GBA_MIX_RATE) if isinstance(track, StreamTrack) else None
        if where is not None and (repeat or where != self._last_seek):
            self._last_seek = where
            self._deck.seek_to_row(*where)
            self._hold = (seconds, self._deck.position)

    def refresh_reference(self, project, asset):
        """L'éditeur vient de redessiner l'onde pour de nouveaux réglages : la tête de lecture se situe sur ce
        nouveau rendu (qui vient du cache)."""
        track = self._deck.track
        if self.previewing(asset) and isinstance(track, StreamTrack):
            section = self._previewed[1]
            track.reference = self._track_of_asset(project, replace(asset, loop_section=section.name)
                                                   if section is not None else asset)

    def _live_track(self, project, asset) -> Optional[StreamTrack]:
        """Le module de cet asset joué en direct : même fichier, mêmes réglages que le rendu entier, mais produit tick
        par tick. Le rendu entier (en cache : l'éditeur l'a déjà fait pour dessiner l'onde) lui sert de frise."""
        prepared = self._prepare(project, asset, asset.name)
        reference = self._track_of_asset(project, asset)
        if prepared is None or reference is None:
            return None
        _path, _key, params, (start, end, fade_in, fade_out) = prepared
        try:
            mod = load_playable(params["path"], params["wav"], params["rate"], params["bounds"])
        except Exception as exc:
            self.message.emit(label('boxplay.name_illisible_exc', name=asset.name, exc=exc))
            return None
        return StreamTrack(mod, GBA_MIX_RATE,
                           tempo=(params["tempo_q"] or MODULE_FULL) / MODULE_FULL,
                           pitch=(params["pitch_q"] or MODULE_FULL) / MODULE_FULL,
                           loop_orders=(start, end) if end > 0 else None, fade_in=fade_in, fade_out=fade_out,
                           reference=reference)

    def stop(self):
        self._previewed = None
        if self._output is not None and self._output.active:
            self._output_close.emit()
        self._deck.stop()

    def set_volume(self, value: float):
        self._volume = max(0.0, min(1.0, value))
        if self._output is not None and self._output.active:
            self._output_volume.emit(self._volume)

    @property
    def position_seconds(self) -> float:
        if self._deck.scrubbing:
            return self._deck.scrub_target / GBA_MIX_RATE
        track = self._deck.track
        if track is None:
            return 0.0
        frame = self._heard_frame(track)
        if self._hold is not None:
            # Le saut est posé mais le son d'avant joue encore : le rendu n'a aucun tick à cet endroit (la frise
            # dirait « début de piste »). On garde la seconde visée jusqu'à ce que le nouveau son s'entende.
            seconds, landing = self._hold
            if frame < landing:
                return seconds
            self._hold = None
        with self._deck.lock:            # le thread audio remplit ce rendu en direct
            return track.song_seconds(frame, GBA_MIX_RATE)

    def _heard_frame(self, track) -> int:
        """La trame en train de s'entendre, pas celle que le deck a déjà produite.

        Qt tire le deck par paquets, loin devant la carte son : lire `deck.position`
        ferait avancer la tête par à-coups. On retire donc ce qui est tiré mais pas
        encore joué."""
        frame = self._deck.position
        if self._output is not None:
            frame -= self._output.queued_frames
        if frame < 0:                      # le deck a rebouclé, l'oreille pas encore
            frame += track.pcm.shape[0]
        return max(0, frame)

    @property
    def duration_seconds(self) -> float:
        track = self._deck.track
        return 0.0 if track is None else track.total_seconds(GBA_MIX_RATE)

    @property
    def looping(self) -> bool:
        return self._deck.looping

    def set_looping(self, enabled: bool):
        """Commande de monitoring : la boucle appliquée par la ROM à l'état courant."""
        self._deck.set_looping(enabled)

    # ── Le geste : cliquer un nœud ────────────────────────────────

    def go_to(self, state_name: str):
        """Ce que ferait `music_box_trigger` pour atteindre cet état.

        On cherche l'arête, comme le runtime parcourt `g_music_box_tr` : une
        arête dont la destination est cet état, et dont l'origine est l'état
        courant ou « n'importe lequel ».
        """
        if not self.running or self._box is None or state_name == self._current:
            return
        edge = next(
            (t for t in self._box.transitions
             if t.dst == state_name and t.src in ("", self._current)), None)
        if edge is None:
            self.message.emit(
                label('boxplay.no_transition', _current=self._current, state_name=state_name))
            return
        self._enter(state_name, transition=True,
                    cut=edge.kind == TRANSITION_CUT, frames=int(edge.frames))

    def _enter(self, name: str, *, transition: bool,
               cut: bool = False, frames: int = 30):
        """`_music_box_enter` : l'état logique change AVANT que le son suive."""
        st = self._box.state(name) if self._box else None
        if st is None:
            return
        self._previewed = None
        self._current = name
        self.state_changed.emit(name)

        track = self._track_of(st)
        volume = volume_to_module(st.level)
        if track is None:
            # `if(id < 0){ music_stop(); return; }` — un état sans piste est un
            # silence, pas une erreur. `music_stop`, et non l'arrêt sec : le fondu de
            # sortie de la musique qui jouait s'applique, comme dans le jeu.
            self._deck.music_stop()
            self.track_changed.emit("", False)
            return
        loop = bool(st.loop)
        if not transition:
            self._deck.play(track, volume, loop)
        elif cut:
            self._deck.cut_to(track, volume, loop)
        else:
            self._deck.fade_to(track, volume, frames, loop)
        self.track_changed.emit(st.music, loop)

    # ── Rendu des modules ─────────────────────────────────────────

    def _track_of(self, state) -> Optional[Track]:
        if not state.music or self._project is None:
            return None
        music = self._project.music.get(state.music)
        if music is None or not music.asset:
            self.message.emit(label('boxplay.tat_name_piste_introuvable', name=state.name))
            return None
        return self._render_file(self._project, music, state.name)

    def _track_of_asset(self, project, asset) -> Optional[Track]:
        if not asset.asset:
            self.message.emit(label('boxplay.tat_name_piste_introuvable', name=asset.name))
            return None
        return self._render_file(project, asset, asset.name)

    def _render_file(self, project, asset, owner: str) -> Optional[Track]:
        """Le fichier de l'asset rendu et mis en cache ; `owner` nomme le
        demandeur (état de boîte ou asset) dans les messages."""
        path = project.asset_abs(asset.asset)
        if path is None or not path.exists():
            self.message.emit(label('boxplay.tat_name_fichier_manquant', name=owner))
            return None

        path, key, params, info = self._prepare(project, asset, owner)
        if key not in self._tracks:
            try:
                self._remember(key, render_track(**params))
            except Exception as exc:
                self.message.emit(label('boxplay.name_illisible_exc', name=asset.name, exc=exc))
                return None
        return self._finish(self._tracks[key], info)

    def _prepare(self, project, asset, owner: str):
        """Tout ce qu'il faut pour rendre un asset, sans rendre : (chemin, clé de cache, arguments de
        `render_track`, réglages à poser sur la copie du Track). None si le fichier manque."""
        path = project.asset_abs(asset.asset)
        if path is None or not path.exists():
            self.message.emit(label('boxplay.tat_name_fichier_manquant', name=owner))
            return None
        if isinstance(asset, Sfx):
            # Un effet s'écoute découpé et au taux du build : le MÊME rendu que la ROM (cf. core/sfx_render).
            path = preview_file(path, asset, project.settings)
        # Les réglages de la musique, lus par la MÊME fonction que le build : un jingle
        # n'en applique aucun (il joue sur l'autre couche), un effet n'en a pas.
        is_music = isinstance(asset, Music) and not isinstance(asset, Jingle)
        start, end, tempo_q, pitch_q, fade_in, fade_out = (
            music_info_row(asset, path) if is_music else (0, 0, 0, 0, 0, 0))
        wav = path.suffix.lower() == ".wav"
        rate = int(getattr(asset, "sample_rate", 0) or 0) if isinstance(asset, Music) else 0
        # Un WAV est joué comme le build l'écrit : le MÊME module (taux, segments, quantification à 8 bits),
        # rendu par le même chemin qu'un module tracker.
        bounds = tuple(wav_boundaries(asset)) if is_music and wav else ()
        key = (path, path.stat().st_mtime_ns, tempo_q, pitch_q, rate, bounds)
        params = dict(path=path, wav=wav, rate=rate, bounds=bounds, tempo_q=tempo_q, pitch_q=pitch_q)
        return path, key, params, (start, end, fade_in, fade_out)

    def _remember(self, key, track: Track) -> None:
        self._tracks[key] = track
        while len(self._tracks) > _TRACK_CACHE:        # un curseur de tempo en rend des dizaines
            del self._tracks[next(iter(self._tracks))]

    @staticmethod
    def _finish(base: Track, info: tuple) -> Track:
        """Ce qui ne change pas le rendu se pose sur une COPIE : deux états qui partagent un fichier ne se
        marchent pas dessus."""
        start, end, fade_in, fade_out = info
        return replace(base, loop_orders=(start, end) if end > 0 else None, fade_in=fade_in, fade_out=fade_out)
