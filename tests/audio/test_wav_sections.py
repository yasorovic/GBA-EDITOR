"""Un WAV en sections : un échantillon par segment, une position d'ordre par pattern.

Le build écrit un VRAI module : les frontières des
sections découpent la piste, chaque segment est un échantillon XM déclenché au début d'une
ligne, et une section est une plage de positions d'ordre — celle que lisent la ROM et l'aperçu.
Ces tests tiennent la structure du module et la traduction millisecondes → ordres ; la tenue
du son (pas de trou, pas de dérive) ne se prouve que sur ROM, et elle l'a été.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))

from core import wav_module                                          # noqa: E402
from core.engine_emulation.xm_file import parse_xm                   # noqa: E402
from core.models.audio import Music, MusicSection, UNIT_MS           # noqa: E402
from core.music_structure import (                                   # noqa: E402
    music_info_row, music_section_rows, wav_boundaries, wav_section_orders,
)

ROW = wav_module.ROW_SECONDS


def _tone(freq: float, seconds: float, rate: int = 44100) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return np.sin(2 * np.pi * freq * t) * 0.6


def _write(path: Path, samples: np.ndarray, rate: int = 44100) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((samples * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def track(tmp_path) -> Path:
    """Intro 300 Hz (0,5 s), corps 800 Hz (1 s), final 1 200 Hz (1 s)."""
    return _write(tmp_path / "track.wav",
                  np.concatenate([_tone(300, 0.5), _tone(800, 1.0), _tone(1200, 1.0)]))


def _music(*sections, loop_section="", **kw) -> Music:
    return Music(name="W", asset="assets/music/track.wav", unit=UNIT_MS, loop_section=loop_section,
                 sections=[MusicSection(name, start=start, end=end, loop=loop) for name, start, end, loop in sections], **kw)


# ── La grille : une ligne = 180 échantillons du mixeur de maxmod ──


def test_une_ligne_dure_un_nombre_entier_d_echantillons_du_mixeur():
    """Mesuré sur ROM le 2026-10-11 : maxmod tronque le tick à un nombre entier d'échantillons de son mixeur.
    À 255 BPM les lignes passaient 0,4 % trop vite ; à 219 BPM (vitesse 1) le compte tombe juste."""
    assert wav_module.MIXER_RATE * 2.5 * wav_module._SPEED / wav_module._BPM == wav_module.SAMPLES_PER_ROW
    assert wav_module.SAMPLES_PER_ROW == 180
    assert ROW == pytest.approx(0.0114155, rel=1e-5)


def test_le_module_ecrit_porte_la_vitesse_et_le_tempo_de_la_grille(track):
    mod = parse_xm(wav_module.wav_to_xm(track))
    assert (mod.speed, mod.bpm) == (wav_module._SPEED, wav_module._BPM)


# ── Le plan : où tombent les segments ─────────────────────────────


def test_sans_section_la_piste_est_un_seul_segment(track):
    mod = parse_xm(wav_module.wav_to_xm(track))
    assert len(mod.samples) == 1 and not mod.samples[0].loops
    assert mod.restart == 0


def test_chaque_frontiere_ouvre_un_segment_et_un_ordre(track):
    mod = parse_xm(wav_module.wav_to_xm(track, boundaries_ms=[500, 1500]))
    assert len(mod.samples) == 3
    assert len(mod.order) == 3                 # trois segments de moins de 256 lignes
    # Chaque premier pattern déclenche SON instrument.
    triggers = [next(cell.instrument for row in mod.patterns[o] for cell in row if cell.instrument)
                for o in mod.order]
    assert triggers == [1, 2, 3]


def test_les_segments_se_recollent_exactement_en_la_piste(track):
    """Découper ne change pas le son : mis bout à bout, les échantillons sont ceux d'un seul."""
    whole = parse_xm(wav_module.wav_to_xm(track)).samples[0].data
    cut = parse_xm(wav_module.wav_to_xm(track, boundaries_ms=[500, 1500, 1700])).samples
    assert np.array_equal(np.concatenate([s.data for s in cut]), whole)


def test_une_frontiere_tombe_sur_la_ligne_la_plus_proche(track):
    plan = wav_module.plan_wav(2.5, wav_module.WAV_MUSIC_RATE, [500])
    assert plan.chunks[0][1] * ROW == pytest.approx(0.5, abs=ROW / 2 + 1e-9)


def test_la_durée_d_un_segment_est_celle_de_ses_lignes(track):
    """Le segment dure ses lignes, à une frame près : le suivant démarre pile à sa fin."""
    mod = parse_xm(wav_module.wav_to_xm(track, boundaries_ms=[500, 1500]))
    plan = wav_module.plan_wav(2.5, wav_module.WAV_MUSIC_RATE, [500, 1500])
    per_row = plan.play_rate * ROW
    for sample, (a, b) in list(zip(mod.samples, plan.chunks))[:-1]:
        assert abs(sample.data.size - (b - a) * per_row) <= 1


def test_la_traduction_des_millisecondes_en_ordres(track):
    plan = wav_module.plan_wav(2.5, wav_module.WAV_MUSIC_RATE, [500, 1500])
    assert plan.order_at(0) == 0
    assert plan.order_at(500) == 1
    assert plan.order_at(1500) == 2
    assert plan.order_at(2500) == plan.order_count == 3     # la fin de la piste = la fin de la table
    with pytest.raises(ValueError, match="no segment starts"):
        plan.order_at(900)


def test_un_segment_trop_long_pour_un_echantillon_est_coupe_en_morceaux(tmp_path):
    """Un échantillon porte ~61 s à 16 726 Hz (`MAX_SAMPLE_FRAMES`) : au-delà, on coupe à une limite de ligne."""
    long = _write(tmp_path / "long.wav", _tone(300, 70, rate=2000), rate=2000)
    mod = parse_xm(wav_module.wav_to_xm(long))
    assert len(mod.samples) == 2
    assert all(s.data.size <= wav_module.MAX_SAMPLE_FRAMES for s in mod.samples)
    assert sum(s.data.size for s in mod.samples) == pytest.approx(70 * wav_module.WAV_MUSIC_RATE, abs=2)
    # Un seul segment, donc deux ordres de plus, et le deuxième déclenche l'instrument suivant.
    assert [mod.samples.index(s) for s in mod.samples] == [0, 1]


def test_une_piste_trop_longue_pour_la_table_d_ordres_est_refusee():
    with pytest.raises(ValueError, match="too long"):
        wav_module.plan_wav(wav_module.MAX_SECONDS + 5, wav_module.WAV_MUSIC_RATE)
    assert wav_module.plan_wav(wav_module.MAX_SECONDS - 5, wav_module.WAV_MUSIC_RATE).order_count <= 256


def test_trop_de_segments_pour_les_instruments_d_un_module_est_refuse():
    bounds = [i * 100 for i in range(1, 140)]
    with pytest.raises(ValueError, match="too many segments"):
        wav_module.plan_wav(20.0, wav_module.WAV_MUSIC_RATE, bounds)


# ── Le taux de build ──────────────────────────────────────────────


def test_le_taux_par_defaut_ne_change_pas_la_hauteur_des_octets():
    """À 16 726 Hz — le double exact de 8 363 — c'est (12, 0), et l'échantillon sonne à ce taux-là."""
    assert wav_module._tuning(wav_module.WAV_MUSIC_RATE) == (12, 0)
    assert wav_module._tuning(8363) == (0, 0)
    assert wav_module.played_rate(wav_module.WAV_MUSIC_RATE) == pytest.approx(16726.0)


def test_un_taux_plus_bas_accorde_l_echantillon_par_note_relative_et_finetune():
    relative, fine = wav_module._tuning(11025)
    # 12·log2(11025/8363) = 4,78 demi-tons → 5, et −0,22 demi-ton de finetune.
    assert (relative, fine) == (5, -28)


def test_le_taux_joue_reste_a_un_tiers_de_pour_cent_du_taux_demande():
    for rate in (4000, 8000, 11025, 13379, 16726):
        assert abs(wav_module.played_rate(rate) / rate - 1) < 0.003


def test_un_taux_plus_bas_raccourcit_l_echantillon(tmp_path):
    src = _write(tmp_path / "a.wav", _tone(440, 2.0))
    hi = parse_xm(wav_module.wav_to_xm(src, 16726)).samples[0].data.size
    lo = parse_xm(wav_module.wav_to_xm(src, 11025)).samples[0].data.size
    assert lo < hi and abs(lo / hi - 11025 / 16726) < 0.01


def test_la_piste_est_rendue_au_taux_joue_pour_que_ses_segments_ne_derivent_pas(tmp_path):
    """11 025 Hz s'accorde à 11 0xx Hz : la piste durerait 0,2 % de trop si on la rendait à 11 025."""
    src = _write(tmp_path / "a.wav", _tone(440, 20.0))
    size = parse_xm(wav_module.wav_to_xm(src, 11025)).samples[0].data.size
    assert size == pytest.approx(20.0 * wav_module.played_rate(11025), abs=2)


# ── Ce que la ROM lit : les sections en positions d'ordre ──────────


def test_les_frontieres_sont_les_debuts_et_les_fins_des_sections():
    music = _music(("Intro", 0, 500, False), ("Main", 500, 1500, True), ("Bad", 900, 100, False),
                   loop_section="Main")
    assert wav_boundaries(music) == [0, 500, 1500]           # la section inversée n'en pose pas


def test_les_sections_d_un_wav_se_lisent_en_ordres(track):
    music = _music(("Intro", 0, 500, False), ("Main", 500, 1500, True), ("Outro", 1500, 2500, False),
                   loop_section="Main")
    rows = music_section_rows(music, track)
    assert rows == [("Intro", 0, 1), ("Main", 1, 2), ("Outro", 2, 3)]
    assert wav_section_orders(music, track) == rows


def test_la_ligne_d_info_donne_la_boucle_en_ordres_et_ignore_tempo_et_hauteur(track):
    music = _music(("Intro", 0, 500, False), ("Main", 500, 1500, True), loop_section="Main",
                   tempo=150, pitch=120, fade_in=30)
    assert music_info_row(music, track) == (1, 2, 0, 0, 30, 0)


def test_sans_fichier_un_wav_n_a_pas_de_section_atteignable():
    music = _music(("Main", 500, 1500, True), loop_section="Main")
    assert music_section_rows(music) == []
    assert music_info_row(music) == (0, 0, 0, 0, 0, 0)


def test_une_section_plus_courte_qu_une_ligne_disparait(track):
    music = _music(("Blip", 1000, 1004, False), ("Main", 500, 1500, True), loop_section="Main")
    names = [n for n, _a, _b in wav_section_orders(music, track)]
    assert names == ["Main"]


def test_des_sections_qui_se_recouvrent_restent_legales(track):
    music = _music(("A", 0, 1500, False), ("B", 500, 2500, False))
    assert wav_section_orders(music, track) == [("A", 0, 2), ("B", 1, 3)]
