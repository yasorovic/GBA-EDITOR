"""Ce que le build émet pour les réglages d'une musique : la table et le C qui la lit.

Le comportement du C lui-même — la section qui boucle, les fondus, le tempo — a été
MESURÉ sur ROM le 2026-10-11, en compilant le C
réellement généré dans une ROM qui s'auto-mesure. Ces tests tiennent ce qui se
vérifie sans console : quelle ligne est émise pour quel réglage, et qu'un réglage
neutre n'en émet aucune.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))

from codegen.runtime_codegen import sound_emit                      # noqa: E402
from core.models import audio                                        # noqa: E402
from core.models.audio import Jingle, Music, MusicSection            # noqa: E402


def _tracker(**kw) -> Music:
    return Music(name="Theme", asset="assets/music/Theme.it", **kw)


def _wav(**kw) -> Music:
    return Music(name="Amb", asset="assets/music/Amb.wav", unit=audio.UNIT_MS, **kw)


# ── La ligne d'un module ──────────────────────────────────────────


def test_un_module_sans_reglage_n_a_pas_de_ligne():
    assert sound_emit.music_info_row(_tracker()) == (0, 0, 0, 0, 0, 0)


def test_les_reglages_se_convertissent_vers_les_echelles_du_materiel():
    row = sound_emit.music_info_row(_tracker(tempo=120, pitch=110, fade_in=30, fade_out=60))
    assert row == (0, 0, audio.tempo_to_module(120), audio.pitch_to_module(110), 30, 60)
    assert row[2] == 1229 and row[3] == 1126          # 120 % et 110 % de 1024


def test_la_section_de_boucle_devient_une_plage_de_positions_d_ordre():
    m = _tracker(sections=[MusicSection("Main", start=2, end=6, loop=True)], loop_section="Main")
    assert sound_emit.music_info_row(m)[:2] == (2, 6)


def test_une_section_dans_une_autre_unite_ou_inconnue_n_est_pas_emise():
    """Le validateur la signale ; le build n'invente pas une plage."""
    wrong_unit = _tracker(unit=audio.UNIT_MS, loop_section="S",
                          sections=[MusicSection("S", start=2, end=6, loop=True)])
    unknown = _tracker(loop_section="Nope", sections=[MusicSection("S", start=2, end=6)])
    reversed_ = _tracker(loop_section="S", sections=[MusicSection("S", start=6, end=2)])
    for m in (wrong_unit, unknown, reversed_):
        assert sound_emit.music_info_row(m)[:2] == (0, 0)


def test_un_wav_n_emet_ni_boucle_ni_tempo_ni_hauteur():
    """Sa boucle est dans le module (l'échantillon boucle) ; son tempo et sa hauteur le
    couperaient avant sa fin. Les fondus, eux, valent aussi pour lui."""
    m = _wav(tempo=150, pitch=120, fade_in=20, loop_section="L",
             sections=[MusicSection("L", start=500, end=2500, loop=True)])
    assert sound_emit.music_info_row(m) == (0, 0, 0, 0, 20, 0)


def test_les_fondus_sont_bornes():
    row = sound_emit.music_info_row(_tracker(fade_in=-5, fade_out=99999))
    assert row[4] == 0 and row[5] == audio.FADE_MAX_FRAMES


# ── La table émise ────────────────────────────────────────────────


def _lines(*items) -> str:
    return "\n".join(sound_emit.music_runtime_lines(None, {"music": [(m, None) for m in items]}))


def test_seuls_les_modules_regles_ont_une_ligne():
    code = _lines(_tracker(tempo=120), Music(name="Plain", asset="assets/music/Plain.it"))
    assert "[MOD_THEME] = {" in code and "MOD_PLAIN" not in code


def test_une_table_vide_reste_une_table_valide():
    """Zéro-longueur interdit : `MSL_NSONGS + 1`, et une ligne neutre."""
    code = _lines(Music(name="Plain", asset="assets/music/Plain.it"))
    assert "g_music_info[MSL_NSONGS + 1]" in code and "{ 0, 0, 0, 0, 0, 0 }" in code


def test_un_jingle_n_a_pas_de_ligne():
    jingle = Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it", tempo=150, fade_in=30)
    assert "MOD_FANFARE" not in _lines(jingle)


def test_les_trois_fonctions_de_l_api_sont_definies_et_pas_en_ligne():
    code = _lines(_tracker())
    for signature in ("void music_play(int id, int loop, int volume){",
                      "void music_stop(void){",
                      "void music_set_volume(int volume){"):
        assert signature in code
    assert "static inline" not in code.split("void music_play")[1].split("void music_stop")[0]


def test_un_module_a_section_boucle_quel_que_soit_son_drapeau():
    """`music_mode` force MM_PLAY_LOOP : un module joué une fois s'arrêterait."""
    code = _lines(_tracker())
    assert "g_music_info[id].loop_end > 0" in code and "MM_PLAY_LOOP : MM_PLAY_ONCE" in code


def test_sans_soundbank_les_trois_fonctions_existent_quand_meme():
    """Les scripts les appellent : un projet dont l'audio n'a pas pu être construit doit lier."""
    code = "\n".join(sound_emit.music_runtime_stub_lines())
    for name in ("music_play", "music_stop", "music_set_volume"):
        assert f"void {name}(" in code


# ── Un WAV est un module : ses sections sortent comme celles d'un module ──


def test_un_wav_a_section_emet_sa_ligne_et_sa_table_en_positions_d_ordre(tmp_path):
    import wave
    import numpy as np
    path = tmp_path / "Amb.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes((np.sin(np.arange(55125) * 0.1) * 9000).astype("<i2").tobytes())      # 2,5 s
    m = _wav(loop_section="Main", sections=[MusicSection("Intro", start=0, end=500),
                                            MusicSection("Main", start=500, end=1500, loop=True)])
    code = "\n".join(sound_emit.music_runtime_lines(None, {"music": [(m, path)]}))
    assert "{ 1, 2, 0, 0, 0, 0 },   /* Amb */" in code                       # la boucle : l'ordre 1, fin exclue 2
    assert "{ MOD_AMB, 0, 0, 1 },   /* Amb / Intro */" in code
    assert "{ MOD_AMB, 1, 1, 2 },   /* Amb / Main */" in code


def test_sans_son_fichier_un_wav_n_a_ni_ligne_ni_section():
    m = _wav(loop_section="Main", sections=[MusicSection("Main", start=500, end=1500, loop=True)])
    code = "\n".join(sound_emit.music_runtime_lines(None, {"music": [(m, None)]}))
    assert "/* Amb" not in code
