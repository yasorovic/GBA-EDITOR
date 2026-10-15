"""L'écran Son montre le geste sans recalculer l'onde : l'oscilloscope trace le son qui joue (la hauteur s'y lit dans la
période, le volume dans l'amplitude), et aucun rendu ne part tant que la main tient un potard."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                            # noqa: E402
from asset_fixtures import create                                      # noqa: E402
from core.engine_emulation.module_render import RenderCancelled        # noqa: E402
from core.project import Project                                       # noqa: E402
from ui.sound_mixer import box_playback, sound_panel                   # noqa: E402
from ui.sound_mixer.box_playback import BoxPlayer, _AudioOutput, _DeckDevice   # noqa: E402
from ui.sound_mixer.music_editor import MusicEditor                    # noqa: E402
from ui.sound_mixer.sound_panel import SoundMixerScreen, _WaveformRenderTask   # noqa: E402
from ui.sound_mixer.waveform_view import _OSC_FRAMES, WaveformView, peak_envelope   # noqa: E402


def _sine(frames: int, cycles: float, amplitude: float = 0.3) -> np.ndarray:
    return (np.sin(np.linspace(0, 2 * np.pi * cycles, frames, endpoint=False)) * amplitude).astype(np.float32)


def _view(qapp) -> WaveformView:
    view = WaveformView()
    view.resize(400, 200)
    view.set_envelope(*peak_envelope(np.full((13379 * 4, 2), 3000, dtype=np.int16), 13379))
    return view


def _lit(view: WaveformView) -> int:
    """Le nombre de pixels clairs de l'image : de quoi comparer deux traces."""
    image = view.grab().toImage()
    return sum(1 for x in range(0, 400, 2) for y in range(20, 200) if image.pixelColor(x, y).lightness() > 90)


# ── L'oscilloscope ───────────────────────────────────────────────────────────────────────────


def test_le_scope_prefere_le_son_qui_joue_a_la_fenetre_fixe(qapp):
    view = _view(qapp)
    still = _sine(2 * _OSC_FRAMES, 4)
    live = _sine(2 * _OSC_FRAMES, 8)
    view.set_osc_sources(lambda frames: live, lambda seconds, frames: still)
    view._set_mode("osc")
    view._poll_osc()
    samples, is_live = view._osc_samples()
    assert is_live and np.array_equal(samples, live)
    view.set_osc_sources(lambda frames: None, lambda seconds, frames: still)       # le lecteur s'arrête
    view._poll_osc()
    samples, is_live = view._osc_samples()
    assert not is_live and np.array_equal(samples, still)


def test_la_fenetre_fixe_suit_le_volume_mais_pas_le_son_qui_joue(qapp):
    view = _view(qapp)
    still = _sine(2 * _OSC_FRAMES, 4)
    view.set_osc_sources(lambda frames: None, lambda seconds, frames: still)
    view._set_mode("osc")
    view.set_mix(50, 100, 100)
    samples, _ = view._osc_samples()
    assert np.allclose(samples, still * 0.5)                                        # le volume éteint la fenêtre fixe, tout de suite
    live = _sine(2 * _OSC_FRAMES, 4)
    view.set_osc_sources(lambda frames: live, lambda seconds, frames: still)
    view._poll_osc()
    samples, _ = view._osc_samples()
    assert np.array_equal(samples, live)                                            # le son qui joue a déjà le volume du lecteur


def test_plus_de_cycles_se_voient_dans_la_trace_et_un_volume_plus_bas_l_aplatit(qapp):
    view = _view(qapp)
    view._set_mode("osc")
    traces = {}
    for cycles, amplitude in ((4, 0.3), (8, 0.3), (4, 0.06)):
        signal = _sine(2 * _OSC_FRAMES, cycles, amplitude)
        view.set_osc_sources(lambda frames, s=signal: s, None)
        view._poll_osc()
        traces[(cycles, amplitude)] = _lit(view)
    # Une trace plus serrée ou plus haute colore plus de pixels qu'une trace plate : ce n'est pas la même image.
    assert len({*traces.values()}) == 3


def test_le_scope_ne_se_relit_que_s_il_se_voit(qapp):
    view = _view(qapp)
    view.show()
    assert not view._osc_timer.isActive()               # l'onde : rien à relire
    view._set_mode("osc")
    assert view._osc_timer.isActive()
    view.hide()
    assert not view._osc_timer.isActive()
    view.show()
    assert view._osc_timer.isActive()
    view._set_mode("wave")
    assert not view._osc_timer.isActive()


def test_dans_le_scope_rien_de_la_frise_ne_se_saisit(qapp):
    view = _view(qapp)
    view.set_loop_ms((500, 2000))
    view.set_editable(True)
    view.set_fades(30, 30, True)
    assert view._handle_at(view._x_of(0.5), 100) == "start"      # l'onde : la borne de boucle se saisit
    view._set_mode("osc")
    assert view._handle_at(view._x_of(0.5), 100) is None
    assert view._handle_at(view._fade_x("fade_in"), 190) is None


# ── Le tampon du lecteur ─────────────────────────────────────────────────────────────────────


class _Deck:
    """Un deck qui rend un compteur : on retrouve chaque trame par sa valeur."""

    playing = True                      # un deck qui joue toujours : le périphérique le lit à chaque paquet (cf. `sound_frames`)

    def __init__(self):
        self.n = 0

    def pull(self, frames: int) -> np.ndarray:
        values = np.arange(self.n, self.n + frames, dtype=np.int16)
        self.n += frames
        return np.stack([values, values], axis=1)


def test_le_peripherique_garde_les_dernieres_trames_tirees(qapp):
    device = _DeckDevice(_Deck())
    for _ in range(3):
        device.readData(1000 * 4)
    assert device.tail.shape[0] == 3000
    assert device.tail[-1, 0] == 2999 and device.tail[0, 0] == 0
    for _ in range(20):
        device.readData(1000 * 4)
    assert device.tail.shape[0] == box_playback._SCOPE_TAIL           # plafonné : il ne grossit pas sans fin


def test_la_fenetre_entendue_retire_ce_que_le_deck_a_tire_en_avance(qapp):
    output = _AudioOutput(_Deck())
    output._device = _DeckDevice(_Deck())
    output.active = True
    output._device.readData(4000 * 4)                                  # 4000 trames tirées : 0..3999
    output.queued_frames = 600                                         # dont 600 que la carte son n'a pas jouées
    window = output.heard_window(100)
    assert len(window) == 100
    assert window[-1] == pytest.approx(3399 / 32768, abs=1e-6)         # la dernière trame ENTENDUE, pas la dernière tirée
    assert output.heard_window(4000) is None                           # pas assez de son entendu pour cette fenêtre
    output.active = False
    assert output.heard_window(100) is None


# ── Le worker de rendu ───────────────────────────────────────────────────────────────────────


def _pump(until, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while not until() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)


def test_le_worker_annule_signale_failed_et_pas_done(qapp, tmp_path):
    path = tmp_path / "long.it"
    path.write_bytes(F.make_it(orders=[0] * 400))
    events = []
    task = _WaveformRenderTask(3, dict(path=path, wav=False, rate=0, bounds=(), tempo_q=1024, pitch_q=1024))
    task.signals.done.connect(lambda token, track, env: events.append("done"))
    task.signals.failed.connect(lambda token: events.append("failed"))
    task.cancel()                               # annulé avant même de commencer : il s'arrête au premier point de contrôle
    QThreadPool.globalInstance().start(task)
    _pump(lambda: events)
    assert events == ["failed"]


# ── Un glisser sur l'écran : aucun rendu pendant, un seul après, et il cède à la main qui reprend ────


@pytest.fixture
def screen(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(BoxPlayer, "_open_sink", lambda self: None)     # pas de carte son en test
    project = Project.create(tmp_path / "Game", "Game")
    music = project.assets_dir / "music"
    music.mkdir(parents=True, exist_ok=True)
    (music / "Theme.it").write_bytes(F.make_it(orders=[0] * 8))
    create(project, "music", music / "Theme.it")
    s = SoundMixerScreen()
    s.load_project(project)
    s._on_asset_selected(project.music.get("Theme"))
    return s


def _idle(screen) -> bool:
    return (not screen._retune_running and screen._retune_pending is None
            and not screen._retune_timer.isActive())


def _slow_render(monkeypatch, counts: dict):
    real = sound_panel.render_track

    def render(*, checkpoint=None, **params):
        counts["started"] += 1
        try:
            for _ in range(20):                 # ~0,4 s : plus long qu'une pause du geste
                time.sleep(0.02)
                checkpoint()
        except RenderCancelled:
            counts["cancelled"] += 1
            raise
        counts["finished"] += 1
        return real(**params)

    monkeypatch.setattr(sound_panel, "render_track", render)


def test_aucun_rendu_pendant_que_la_main_tient_puis_un_seul_au_relachement(screen, monkeypatch):
    held = {"on": True}
    monkeypatch.setattr(MusicEditor, "mixing", property(lambda self: held["on"]))
    counts = {"started": 0, "cancelled": 0, "finished": 0}
    _slow_render(monkeypatch, counts)
    theme = screen._edited_music
    for step in range(15):                      # 0,6 s de glisser, un cran toutes les 40 ms : bien des pauses de 100 ms
        theme.tempo = 100 + 3 * (step + 1)
        screen._on_mix_changed("tempo")
        _pump(lambda: False, 0.04)
    _pump(lambda: False, 0.3)                   # la main reste posée, immobile
    assert counts["started"] == 0               # l'onde et la règle suivent sans rendu

    held["on"] = False                          # la main lâche
    screen._schedule_retune()
    _pump(lambda: _idle(screen))
    assert counts == {"started": 1, "cancelled": 0, "finished": 1}
    assert screen._retune_applied_key == screen._box_player.waveform_render_request(screen._project, theme)[0]


def test_un_cran_abandonne_le_rendu_qui_tournait(screen, monkeypatch):
    monkeypatch.setattr(MusicEditor, "mixing", property(lambda self: False))   # un tempo changé à la molette
    counts = {"started": 0, "cancelled": 0, "finished": 0}
    _slow_render(monkeypatch, counts)
    theme = screen._edited_music
    theme.tempo = 120
    screen._on_mix_changed("tempo")
    _pump(lambda: counts["started"] == 1)       # le rendu de 120 % tourne
    theme.tempo = 140
    screen._on_mix_changed("tempo")             # la main reprend : il n'a plus de raison d'aller au bout
    _pump(lambda: _idle(screen))
    assert counts["cancelled"] == 1 and counts["finished"] == 1
    assert screen._retune_applied_key == screen._box_player.waveform_render_request(screen._project, theme)[0]


def test_l_ecran_donne_au_scope_le_son_de_l_apercu_en_cours(screen, monkeypatch):
    theme = screen._edited_music
    heard = _sine(2 * _OSC_FRAMES, 5)
    monkeypatch.setattr(BoxPlayer, "scope_window", lambda self, asset, frames: heard if asset is theme else None)
    assert np.array_equal(screen._live_scope_window(2 * _OSC_FRAMES), heard)
    assert np.array_equal(screen._music_editor._wave._osc_source(2 * _OSC_FRAMES), heard)


# ── Les barres des canaux suivent le volume de la musique ────────────────────────────────────


def test_les_barres_des_canaux_retrecissent_avec_le_volume(qapp):
    from core.engine_emulation.module_render import ChannelLevels
    from ui.sound_mixer.channel_meters import ChannelMeters
    levels = ChannelLevels(np.array([0, 100], dtype=np.int64), np.full((2, 2), 0.6, dtype=np.float32))
    meters = ChannelMeters()
    meters.set_levels(levels, 100, 2)
    meters.set_playhead(0.0)
    full = meters._shown.copy()
    meters.set_gain(0.5)
    meters._shown[:] = 0                                   # une barre repart de zéro : on lit sa cible
    meters.set_playhead(0.0)
    assert np.allclose(meters._shown, full * 0.5)
    meters.set_gain(0.0)
    meters._shown[:] = 0
    meters.set_playhead(0.0)
    assert not meters._shown.any()                         # volume nul : plus rien ne sonne


def test_le_curseur_de_volume_regle_les_barres(screen):
    editor = screen._music_editor
    editor._on_fader("volume", 40)
    assert editor._meters._gain == pytest.approx(0.4)
    editor._on_fader("volume", 100)
    assert editor._meters._gain == 1.0
