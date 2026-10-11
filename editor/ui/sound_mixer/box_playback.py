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

from PyQt6.QtCore import QIODevice, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from core.engine_emulation.module_model import load_module
from core.engine_emulation.module_render import render_module_marked, GBA_MIX_RATE
from core.engine_emulation.music_deck import MusicDeck, Track, MODULE_FULL
from core.engine_emulation.wav_render import render_wav
from core.models.audio import Jingle, Music, volume_to_module
from core.music_structure import music_info_row, wav_loop_region
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
        # Modules rendus. Le rendu d'un morceau long prend jusqu'à une seconde : le
        # refaire à chaque transition rendrait l'aperçu inutilisable. La clé porte
        # tout ce qui change CE QUE LE FICHIER RENDRA — le chemin, le tempo, la
        # hauteur, le taux, la boucle d'un WAV — pour qu'un réglage modifié ne rejoue
        # pas l'ancien rendu. Les fondus et la section d'un module, eux, ne changent
        # pas le rendu : ils se posent sur le `Track` à chaque appel.
        self._tracks: dict[tuple, Track] = {}

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
    def sounding(self) -> bool:
        """Le deck produit encore du son (faux quand un son non bouclé a fini)."""
        return self._deck.playing

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
        fmt = QAudioFormat()
        fmt.setSampleRate(GBA_MIX_RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt)
        self._sink.setVolume(self._volume)
        self._device = _DeckDevice(self._deck)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)
        self._sink.start(self._device)

    def track_for(self, project, asset) -> Optional[Track]:
        """Le `Track` que le deck jouerait pour cet asset, rendu et mis en cache — ce que l'écran
        Son dessine (waveform, repères d'ordre) est donc EXACTEMENT ce qu'on entend."""
        return self._track_of_asset(project, asset)

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
        track = self._track_of_asset(project, played)
        if track is None:
            return False
        if not self.running:
            self._open_sink()
        loop = bool(getattr(asset, "loop", False))
        start_at = 0
        if section is not None:
            if track.sample_loop is not None:          # un WAV : la boucle commence à son échantillon
                start_at = track.sample_loop[0]
            else:
                start_at = track.start_of(section.start) or 0
        self._current = ""
        self._deck.play(track, volume_to_module(asset.volume), loop, start_at)
        self.track_changed.emit(asset.name, loop)
        return True

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

        # Les réglages de la musique, lus par la MÊME fonction que le build : un jingle
        # n'en applique aucun (il joue sur l'autre couche), un effet n'en a pas.
        is_music = isinstance(asset, Music) and not isinstance(asset, Jingle)
        start, end, tempo_q, pitch_q, fade_in, fade_out = (
            music_info_row(asset) if is_music else (0, 0, 0, 0, 0, 0))
        wav = path.suffix.lower() == ".wav"
        rate = int(getattr(asset, "sample_rate", 0) or 0) if isinstance(asset, Music) else 0
        loop_ms = wav_loop_region(asset) if is_music and wav else None

        key = (path, path.stat().st_mtime_ns, tempo_q, pitch_q, rate, loop_ms)
        if key not in self._tracks:
            try:
                if wav:
                    self._tracks[key] = render_wav(path, GBA_MIX_RATE, rate, loop_ms)
                else:
                    mod = load_module(path)
                    pcm, marks = render_module_marked(
                        mod, GBA_MIX_RATE, (tempo_q or MODULE_FULL) / MODULE_FULL,
                        (pitch_q or MODULE_FULL) / MODULE_FULL)
                    self._tracks[key] = Track(pcm=pcm, marks=marks, restart=mod.restart,
                                              order_count=len(mod.order))
            except Exception as exc:
                self.message.emit(label('boxplay.name_illisible_exc', name=asset.name, exc=exc))
                return None
        # Ce qui ne change pas le rendu se pose sur une COPIE : deux états qui partagent un
        # fichier ne se marchent pas dessus.
        return replace(self._tracks[key], loop_orders=(start, end) if end > 0 else None,
                       fade_in=fade_in, fade_out=fade_out)
