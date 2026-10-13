"""Un module joué EN DIRECT, tick par tick (`StreamTrack`) : le même son que le rendu entier, mais un tempo, une
hauteur et des sauts qu'on change pendant qu'on écoute.

Le rendu entier (`render_module_marked`) reste la référence : sans réglage en route, le flux doit lui être
identique à l'échantillon près. Le reste tient ce que le direct apporte — un tempo lu à chaque tick, un saut qui
prend effet au tick suivant, un morceau qui boucle ou qui finit comme dans le deck, et une mémoire qui ne grossit pas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                            # noqa: E402
from core.engine_emulation.module_render import GBA_MIX_RATE, render_module_marked   # noqa: E402
from core.engine_emulation.module_stream import StreamTrack            # noqa: E402
from core.engine_emulation.music_deck import MODULE_FULL, MusicDeck    # noqa: E402
from core.engine_emulation.xm_file import parse_xm                     # noqa: E402


def _mod(orders: int = 8, restart: int = 0):
    return parse_xm(F.make_xm(orders=[0] * orders, restart=restart))


def _orders_of_ticks(track: StreamTrack) -> list:
    return [order for order, _row in track._ticks]


def test_sans_reglage_en_route_le_flux_est_le_rendu_entier():
    mod = _mod()
    whole, marks = render_module_marked(mod, GBA_MIX_RATE)
    track = StreamTrack(mod, GBA_MIX_RATE)
    track.ensure(whole.shape[0] + 100)
    assert np.array_equal(track.slice(0, whole.shape[0]), whole)
    assert track.rendered == whole.shape[0]
    for order, offset in marks.items():                  # l'ordre joué en chaque point est celui des repères
        assert track.order_at(offset) == order


def test_le_flux_ne_produit_que_ce_qu_on_lui_demande():
    track = StreamTrack(_mod(), GBA_MIX_RATE)
    track.ensure(1000)
    assert 1000 <= track.rendered < 1000 + 400           # un tick de plus au plus


def test_le_tempo_est_lu_a_chaque_tick():
    """Un ordre dure 0,48 s ; à tempo 200 % le suivant dure moitié moins."""
    track = StreamTrack(_mod(), GBA_MIX_RATE)
    track.ensure(int(GBA_MIX_RATE * 0.5))                # l'ordre 0 est joué, l'ordre 1 commence
    track.set_tuning(2.0, 1.0)
    track.ensure(int(GBA_MIX_RATE * 1.2))
    starts = {}
    for offset, (order, _row) in zip(track._starts, track._ticks):
        starts.setdefault(order, offset)
    first = (starts[1] - starts[0]) / GBA_MIX_RATE
    second = (starts[2] - starts[1]) / GBA_MIX_RATE
    assert 0.46 < first < 0.50
    assert second < 0.30                                  # l'ordre 1 a commencé à tempo 100 % mais s'est fini à 200 %


def _fundamental(audio) -> float:
    mono = audio[:, 0].astype(float)[:4096]
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    return float(np.argmax(spectrum) * GBA_MIX_RATE / len(mono))


def test_la_hauteur_est_lue_a_chaque_tick():
    track = StreamTrack(_mod(), GBA_MIX_RATE)
    track.ensure(8192)
    before = _fundamental(track.slice(0, 8192))
    track.set_tuning(1.0, 2.0)
    mark = track.rendered
    track.ensure(mark + 8192)
    after = _fundamental(track.slice(mark + 400, mark + 400 + 8192))     # un tick plus loin : le réglage est pris
    assert 1.9 < after / before < 2.1


def test_un_saut_demande_prend_effet_au_tick_suivant():
    track = StreamTrack(_mod(), GBA_MIX_RATE)
    track.ensure(int(GBA_MIX_RATE * 1.5))                 # on est à l'ordre 3
    assert track.order_at(track.rendered - 1) == 3
    land = track.start_of(1)                              # `mmPosition(1)`
    assert land == track.rendered                         # le nouveau son commence juste après ce qui est produit
    track.ensure(land + 600)
    assert track.order_at(land) == 1                      # le tout premier tick d'après est dans l'ordre 1


def test_un_saut_sur_un_marqueur_ou_hors_table_n_a_pas_de_musique():
    track = StreamTrack(parse_xm(F.make_xm(orders=[0, 0, 0])), GBA_MIX_RATE)
    assert track.start_of(7) is None and track.start_of(-1) is None


def test_la_boucle_d_une_section_se_joue_comme_pour_un_rendu_fini():
    """Le MÊME deck, le même tick de boucle : section [2, 5) d'un module de 8 ordres → 0 1 2 3 4 2 3 4 2…"""
    track = StreamTrack(_mod(), GBA_MIX_RATE, loop_orders=(2, 5))
    deck = MusicDeck(GBA_MIX_RATE)
    deck.play(track, MODULE_FULL, loop=False)
    seen: list = []
    frame = round(GBA_MIX_RATE / 60)
    for _ in range(60 * 6):                               # six secondes
        deck.pull(frame)
        order = track.order_at(deck.position)
        if not seen or seen[-1] != order:
            seen.append(order)
    # Comme sur la console, la boucle se joue en SURVEILLANT la position : l'ordre suivant la section peut s'entendre
    # une frame avant qu'on soit renvoyé au début (mesuré sur ROM : ~10 ms). Jamais plus, jamais au-delà.
    assert seen[:5] == [0, 1, 2, 3, 4] and set(seen[5:]) <= {2, 3, 4, 5}
    assert all(after == 2 for before, after in zip(seen, seen[1:]) if before == 5)
    assert seen.count(2) >= 3 and deck.playing                # elle tourne : 2 3 4 2 3 4 …


def test_un_morceau_qui_finit_s_arrete_ou_reboucle_selon_le_drapeau():
    once = StreamTrack(_mod(3), GBA_MIX_RATE)
    deck = MusicDeck(GBA_MIX_RATE)
    deck.play(once, MODULE_FULL, loop=False)
    deck.pull(GBA_MIX_RATE * 3)
    assert not deck.playing                                # 1,44 s de morceau : fini
    looping = StreamTrack(_mod(3, restart=1), GBA_MIX_RATE)
    deck.play(looping, MODULE_FULL, loop=True)
    deck.pull(GBA_MIX_RATE * 3)
    assert deck.playing                                    # reboucle sans fin, à l'ordre de restart
    assert looping.order_at(deck.position) in (1, 2)


def test_la_memoire_ne_grossit_pas_avec_les_tours_de_boucle():
    track = StreamTrack(_mod(3), GBA_MIX_RATE)
    deck = MusicDeck(GBA_MIX_RATE)
    deck.play(track, MODULE_FULL, loop=True)
    for _ in range(40):                                    # une minute de morceau de 1,44 s, tirée par petits bouts
        deck.pull(GBA_MIX_RATE * 2 // 3)
    kept = sum(chunk.shape[0] for chunk in track._chunks)
    assert kept < GBA_MIX_RATE * 5


def test_la_tete_de_lecture_se_situe_sur_le_rendu_entier():
    mod = _mod()
    whole, marks = render_module_marked(mod, GBA_MIX_RATE)
    from core.engine_emulation.music_deck import Track
    reference = Track(pcm=whole, marks=marks, order_count=len(mod.order))
    track = StreamTrack(mod, GBA_MIX_RATE, reference=reference)
    track.ensure(int(GBA_MIX_RATE * 1.0))
    seconds = track.song_seconds(int(GBA_MIX_RATE * 1.0) - 1, GBA_MIX_RATE)
    assert abs(seconds - 1.0) < 0.05
    assert abs(track.total_seconds(GBA_MIX_RATE) - whole.shape[0] / GBA_MIX_RATE) < 1e-6
