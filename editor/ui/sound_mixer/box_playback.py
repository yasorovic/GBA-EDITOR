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
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import render_module_marked, GBA_MIX_RATE
from core.engine_emulation.music_deck import MusicDeck, Track, MODULE_FULL
from core.models.audio import volume_to_module
from core.models.sound_box import TRANSITION_CUT


class _DeckDevice(QIODevice):
    """Le robinet : Qt tire, le deck produit."""

    def __init__(self, deck: MusicDeck, parent=None):
        super().__init__(parent)
        self._deck = deck

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        # Un module bouclé ne tarit jamais ; le silence en est aussi.
        return 1 << 20

    def readData(self, maxlen: int) -> bytes:
        n = int(maxlen) // 4          # 2 canaux × 2 octets
        if n <= 0:
            return b""
        return self._deck.pull(n).tobytes()

    def writeData(self, data) -> int:
        return 0


class BoxPlayer(QObject):
    """Joue la MusicBox courante comme la ROM la jouerait."""

    # L'état LOGIQUE courant — il change dès le déclenchement, comme
    # `g_music_box_state_cur` dans main.c, avant même que le fondu s'entende.
    state_changed = pyqtSignal(str)
    # Nom de la piste effectivement résolue, et son état de boucle.
    track_changed = pyqtSignal(str, bool)
    # Ce qu'il y a à dire à l'auteur : pas d'arête, module manquant…
    message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._box = None
        self._deck = MusicDeck(GBA_MIX_RATE)
        self._device: Optional[_DeckDevice] = None
        self._sink: Optional[QAudioSink] = None
        self._current = ""
        self._volume = 0.8
        # Modules rendus, par chemin de fichier. Le rendu d'un morceau long
        # prend jusqu'à une seconde : le refaire à chaque transition rendrait
        # l'aperçu inutilisable.
        self._tracks: dict[Path, Track] = {}

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
        return self._sink is not None

    @property
    def current_state(self) -> str:
        return self._current

    # ── Marche / arrêt ────────────────────────────────────────────

    def start(self):
        """Démarre sur l'état de départ — ce que fait `main()` au boot."""
        if self.running or self._box is None:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(GBA_MIX_RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt)
        self._sink.setVolume(self._volume)
        self._device = _DeckDevice(self._deck)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink.start(self._device)

        start = self._box.start or (self._box.states[0].name
                                    if self._box.states else "")
        self._current = ""
        self._enter(start, transition=False)

    def stop(self):
        if self._sink is not None:
            self._sink.stop()
            self._sink = None
        if self._device is not None:
            self._device.close()
            self._device = None
        self._deck.stop()

    def set_volume(self, value: float):
        self._volume = max(0.0, min(1.0, value))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    @property
    def position_seconds(self) -> float:
        return self._deck.position / GBA_MIX_RATE

    @property
    def duration_seconds(self) -> float:
        return self._deck.duration / GBA_MIX_RATE

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
        self._current = name
        self.state_changed.emit(name)

        track = self._track_of(st)
        volume = volume_to_module(st.level)
        if track is None:
            # `if(id < 0){ music_stop(); return; }` — un état sans piste est un
            # silence, pas une erreur.
            self._deck.stop()
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
        path = self._project.asset_abs(music.asset)
        if path is None or not path.exists():
            self.message.emit(label('boxplay.tat_name_fichier_manquant', name=state.name))
            return None
        if path not in self._tracks:
            try:
                pcm, marks = render_module_marked(load_module(path))
            except Exception as exc:
                self.message.emit(label('boxplay.name_illisible_exc', name=music.name, exc=exc))
                return None
            self._tracks[path] = Track(pcm=pcm, marks=marks)
        return self._tracks[path]
