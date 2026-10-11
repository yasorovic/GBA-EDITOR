"""L'aperçu joue ce que la ROM jouera : section de boucle, fondus, tempo, hauteur, WAV.

Le C correspondant a été mesuré sur ROM le 2026-10-11 (ROADMAP « L'asset .music »), en
compilant le C réellement généré dans une ROM qui s'auto-mesure. Ces tests rejouent les
mêmes scénarios dans le `MusicDeck` et exigent les mêmes séquences — c'est ce qui tient
l'aperçu honnête : un réglage qui sonnerait autrement dans l'éditeur que sur la console
se règlerait à l'oreille pour rien.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                            # noqa: E402
from core.engine_emulation.module_render import GBA_MIX_RATE, render_module  # noqa: E402
from core.engine_emulation.music_deck import MODULE_FULL, MusicDeck, Track  # noqa: E402
from core.engine_emulation.wav_render import render_wav                # noqa: E402
from core.engine_emulation.xm_file import parse_xm                     # noqa: E402
from core.models.audio import Music, MusicSection, UNIT_MS              # noqa: E402

# 100 échantillons par frame ; 400 par ordre, donc 4 frames par ordre.
MIX = 6000
FRAME = 100
ORDER = 400


def _tracker(orders: int = 8, **kw) -> Track:
    """Un morceau de `orders` ordres dont l'échantillon `i` vaut `i` : on lit, dans la
    sortie, l'ordre d'où chaque échantillon vient."""
    n = orders * ORDER
    pcm = np.zeros((n, 2), dtype=np.int16)
    pcm[:, 0] = np.arange(n)
    return Track(pcm=pcm, marks={i: i * ORDER for i in range(orders)}, order_count=orders, **kw)


def _orders_played(deck: MusicDeck, frames: int) -> list[int]:
    """L'ordre d'où vient chaque frame de sortie, doublons consécutifs écrasés."""
    out = deck.pull(frames * FRAME)[:, 0].astype(int)
    seq: list[int] = []
    for value in out[::FRAME]:
        order = int(value) // ORDER
        if not seq or seq[-1] != order:
            seq.append(order)
    return seq


# ── La section de boucle, comme la ROM ────────────────────────────


def test_une_section_au_milieu_boucle_meme_sans_le_drapeau():
    """Mesuré sur ROM : section [2, 5), jouée avec `loop = 0` → positions
    0, 1, 2, 3, 4, 2, 3, 4, 2… — jamais au-delà de 4."""
    deck = MusicDeck(MIX)
    deck.play(_tracker(loop_orders=(2, 5)), MODULE_FULL, loop=False)
    seq = _orders_played(deck, 40)
    assert seq[:9] == [0, 1, 2, 3, 4, 2, 3, 4, 2]
    assert max(seq) == 4 and deck.playing


def test_une_section_jusqu_a_la_fin_du_morceau_est_rattrapee_par_le_retour_arriere():
    """Mesuré sur ROM : section [4, 8) d'un module de 8 ordres → …, 6, 7, 4. Le module
    reboucle seul à son restart, sous le début de la section, et le tick le renvoie."""
    deck = MusicDeck(MIX)
    deck.play(_tracker(loop_orders=(4, 8)), MODULE_FULL, loop=True)
    out = deck.pull(80 * FRAME)[:, 0].astype(int)
    orders = out // ORDER
    # Après la première passe, le début du morceau ne sonne qu'UNE frame par tour
    # (ce que la ROM laisse entendre, et que la roadmap dit) — jamais l'intro entière.
    first_pass = 8 * ORDER
    after = orders[first_pass:]
    assert (after < 4).sum() <= FRAME * (len(after) // (4 * ORDER) + 1)
    assert set(after[after >= 4]) == {4, 5, 6, 7}


def test_un_module_sans_section_ne_boucle_pas_a_l_interieur():
    deck = MusicDeck(MIX)
    deck.play(_tracker(), MODULE_FULL, loop=False)
    deck.pull(10 * 8 * ORDER // FRAME * FRAME)
    assert not deck.playing


def test_le_drapeau_ne_peut_pas_eteindre_une_boucle_de_section():
    deck = MusicDeck(MIX)
    deck.play(_tracker(loop_orders=(2, 5)), MODULE_FULL, loop=False)
    assert deck.looping
    deck.set_looping(False)
    assert deck.looping          # la ROM le démarre toujours en MM_PLAY_LOOP


# ── La boucle d'échantillon d'un WAV ──────────────────────────────


def test_une_boucle_d_echantillon_ne_s_arrete_jamais():
    pcm = np.zeros((1000, 2), dtype=np.int16)
    pcm[:, 0] = np.arange(1000)
    deck = MusicDeck(MIX)
    deck.play(Track(pcm=pcm, sample_loop=(400, 1000)), MODULE_FULL, loop=False)
    out = deck.pull(2600)[:, 0]
    assert deck.playing
    assert list(out[1000:1003]) == [400, 401, 402]          # le retour au début de la boucle
    assert list(out[1600:1603]) == [400, 401, 402]
    assert out.min() == 0 and out[1000:].min() == 400       # l'intro ne revient pas


# ── Les fondus, comme la ROM ──────────────────────────────────────


def _constant(level: int = 10000, n: int = 20000, **kw) -> Track:
    return Track(pcm=np.full((n, 2), level, dtype=np.int16), **kw)


def _levels(deck: MusicDeck, frames: int) -> list[int]:
    return [int(deck.pull(FRAME)[-1, 0]) for _ in range(frames)]


def test_le_fondu_d_entree_monte_de_zero_au_volume_en_n_frames():
    """Mesuré sur ROM : 60 frames → amplitude 0, 5, 11, 17, 23, puis stable (linéaire)."""
    deck = MusicDeck(MIX)
    deck.play(_constant(fade_in=60), MODULE_FULL, loop=True)
    levels = _levels(deck, 80)
    assert levels[0] == 0
    assert levels == sorted(levels)                       # ne redescend jamais
    # Le premier tick suit la première frame : `n` ticks, donc plein à la frame n + 1.
    assert levels[61] == 10000 and levels[79] == 10000
    # Linéaire : après 14 ticks sur 60, 14/60 du niveau.
    assert abs(levels[14] - 10000 * 14 // 60) <= 60


def test_sans_fondu_le_volume_est_plein_d_emblee():
    deck = MusicDeck(MIX)
    deck.play(_constant(), MODULE_FULL, loop=True)
    assert _levels(deck, 1) == [10000]


def test_le_fondu_de_sortie_s_eteint_puis_arrete_la_musique():
    """Mesuré sur ROM : `music_stop` avec 60 frames → 23, 18, 12, 6, 0 puis `mmActive() == 0`."""
    deck = MusicDeck(MIX)
    deck.play(_constant(fade_out=60), MODULE_FULL, loop=True)
    _levels(deck, 10)
    deck.music_stop()
    assert deck.playing                                    # le fondu commence, pas l'arrêt
    levels = _levels(deck, 80)
    assert levels[0] == 10000 or levels[0] > 9000
    assert levels[:55] == sorted(levels[:55], reverse=True)
    assert levels[-1] == 0 and not deck.playing


def test_music_stop_sans_fondu_arrete_net_et_stop_est_toujours_sec():
    deck = MusicDeck(MIX)
    deck.play(_constant(), MODULE_FULL, loop=True)
    deck.music_stop()
    assert not deck.playing
    deck.play(_constant(fade_out=60), MODULE_FULL, loop=True)
    deck.stop()                                            # le bouton Stop du lecteur
    assert not deck.playing


def test_un_nouveau_play_remplace_un_fondu_de_sortie_en_cours():
    deck = MusicDeck(MIX)
    deck.play(_constant(fade_out=60), MODULE_FULL, loop=True)
    deck.music_stop()
    _levels(deck, 20)
    deck.play(_constant(), MODULE_FULL, loop=True)
    assert _levels(deck, 80)[-1] == 10000 and deck.playing


# ── Le tempo et la hauteur du rendu ───────────────────────────────


def _xm():
    return parse_xm(F.make_xm(orders=[0, 0, 0, 0]))


def test_un_tempo_double_raccourcit_le_morceau_de_moitie():
    base = len(render_module(_xm()))
    fast = len(render_module(_xm(), tempo=2.0))
    slow = len(render_module(_xm(), tempo=0.5))
    assert abs(fast / base - 0.5) < 0.02 and abs(slow / base - 2.0) < 0.02


def _fundamental(audio) -> float:
    mono = audio[:, 0].astype(float)[:8192]
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    return float(np.argmax(spectrum) * GBA_MIX_RATE / len(mono))


def test_une_hauteur_double_double_la_frequence_et_ne_touche_pas_au_tempo():
    base = render_module(_xm())
    high = render_module(_xm(), pitch=2.0)
    assert 1.95 < _fundamental(high) / _fundamental(base) < 2.05
    assert len(high) == len(base)                          # le tempo, lui, n'a pas bougé


# ── Le rendu d'un WAV, comme le build le portera ──────────────────


def _wav(path: Path, seconds: float = 3.0, rate: int = 44100) -> Path:
    t = np.arange(int(rate * seconds)) / rate
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 0.5 * 32767).astype("<i2").tobytes())
    return path


def test_un_wav_sans_boucle_garde_sa_duree(tmp_path):
    track = render_wav(_wav(tmp_path / "a.wav"))
    assert abs(len(track.pcm) / GBA_MIX_RATE - 3.0) < 0.01
    assert track.sample_loop is None


def test_un_wav_a_boucle_ne_garde_que_l_intro_et_la_boucle(tmp_path):
    track = render_wav(_wav(tmp_path / "a.wav"), loop_ms=(500, 2000))
    assert abs(len(track.pcm) / GBA_MIX_RATE - 2.0) < 0.05           # le final n'y est pas
    start, end = track.sample_loop
    assert end == len(track.pcm) and abs(start / GBA_MIX_RATE - 0.5) < 0.05


def test_le_taux_choisi_se_voit_dans_le_rendu(tmp_path):
    """À 4 000 Hz l'échantillon est tenu 3 à 4 fois : le rendu change de marche, comme la ROM."""
    src = _wav(tmp_path / "a.wav")
    fine = render_wav(src, sample_rate=16726).pcm[:, 0]
    coarse = render_wav(src, sample_rate=4000).pcm[:, 0]
    runs = lambda a: int((np.diff(a) != 0).sum())
    assert runs(coarse) < runs(fine) / 2


# ── Le lecteur : les réglages de l'asset arrivent sur le Track ────


@pytest.fixture
def player():
    # Un QObject, pas un widget : aucune application Qt à lancer tant qu'on n'ouvre pas la carte son.
    from ui.sound_mixer.box_playback import BoxPlayer
    return BoxPlayer()


def _project_of(path: Path):
    return SimpleNamespace(asset_abs=lambda rel: path)


def test_le_track_porte_les_reglages_de_l_asset(player, tmp_path):
    path = tmp_path / "t.xm"
    path.write_bytes(F.make_xm(orders=[0] * 8))
    music = Music(name="T", asset="t.xm", loop_section="S", fade_in=30, fade_out=60,
                  sections=[MusicSection("S", start=2, end=6, loop=True)])
    track = player._render_file(_project_of(path), music, "T")
    assert (track.loop_orders, track.fade_in, track.fade_out) == ((2, 6), 30, 60)
    assert track.forces_loop


def test_un_reglage_de_tempo_ne_rejoue_pas_l_ancien_rendu(player, tmp_path):
    """Le cache est par fichier ET par ce qui change le rendu : sans cela, régler le tempo
    ne changerait rien à l'oreille."""
    path = tmp_path / "t.xm"
    path.write_bytes(F.make_xm(orders=[0, 0, 0, 0]))
    project = _project_of(path)
    normal = player._render_file(project, Music(name="T", asset="t.xm"), "T")
    fast = player._render_file(project, Music(name="T", asset="t.xm", tempo=200), "T")
    assert len(fast.pcm) < 0.6 * len(normal.pcm)


def test_deux_etats_qui_partagent_un_fichier_ne_se_marchent_pas_dessus(player, tmp_path):
    path = tmp_path / "t.xm"
    path.write_bytes(F.make_xm(orders=[0] * 8))
    project = _project_of(path)
    with_fade = player._render_file(project, Music(name="A", asset="t.xm", fade_in=30), "A")
    plain = player._render_file(project, Music(name="B", asset="t.xm"), "B")
    assert with_fade.fade_in == 30 and plain.fade_in == 0
    assert with_fade.pcm is plain.pcm                      # le rendu, lui, est partagé


def test_un_wav_a_section_donne_une_boucle_d_echantillon(player, tmp_path):
    path = _wav(tmp_path / "w.wav")
    music = Music(name="W", asset="w.wav", unit=UNIT_MS, loop_section="L", sample_rate=11025,
                  sections=[MusicSection("L", start=500, end=2000, loop=True)])
    track = player._render_file(_project_of(path), music, "W")
    assert track.sample_loop is not None and track.loop_orders is None
