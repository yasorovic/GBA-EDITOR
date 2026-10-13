"""Le scrub : la main tient la tête de lecture, le son suit son geste et la lecture automatique attend."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "editor"))

from core.engine_emulation.music_deck import MODULE_FULL, MusicDeck, Track   # noqa: E402

_RATE = 32768


def _deck():
    pcm = np.zeros((_RATE * 4, 2), dtype=np.int16)
    pcm[:, 0] = (np.arange(pcm.shape[0]) % 2000) + 1000          # jamais muet
    deck = MusicDeck(_RATE)
    deck.play(Track(pcm=pcm), MODULE_FULL, loop=True)
    return deck, pcm


def test_le_scrub_suspend_la_lecture_et_suit_la_cible():
    deck, pcm = _deck()
    deck.pull(1000)
    live = deck.position
    deck.scrub_to(pcm, target=20000, start=5000)
    assert deck.scrubbing
    sounded = [bool(np.any(deck.pull(512) != 0)) for _ in range(40)]
    assert sounded[0]                                     # le geste s'entend tout de suite
    assert deck.position == live                          # la lecture automatique n'a pas avancé
    assert abs(deck.scrub_position - 20000) < 200         # le son a rejoint la main


def test_le_scrub_recule_et_se_tait_quand_la_main_s_arrete():
    deck, pcm = _deck()
    deck.scrub_to(pcm, target=1000, start=30000)
    before = deck.scrub_position
    assert np.any(deck.pull(512) != 0)
    assert deck.scrub_position < before                   # vers l'arrière
    for _ in range(60):
        deck.pull(512)
    assert not np.any(deck.pull(512))                     # arrivé : silence


def test_la_vitesse_est_bornee_et_la_fin_rend_la_main():
    deck, pcm = _deck()
    deck.scrub_to(pcm, target=100000, start=0)
    deck.pull(512)
    assert deck.scrub_position <= 6.0 * 512 + 1           # au plus six fois la vitesse normale
    deck.scrub_end()
    assert not deck.scrubbing
    assert np.any(deck.pull(512) != 0)                    # la lecture normale reprend
