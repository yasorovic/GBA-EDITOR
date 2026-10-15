"""Les repères d'une musique : des sons que la lecture déclenche en atteignant une position.

Ce qui se tient sans console : le modèle et sa sérialisation, la traduction en positions d'ordre (un WAV passe par le plan
du build, comme ses sections), ce que le build émet pour chaque nature, et ce que le validateur dit. Le C émis, lui, se
lit comme du texte ; que la lecture déclenche bien le son au bon pas ne se prouve que sur ROM.
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

from codegen.runtime_codegen import sound_emit                                  # noqa: E402
from core.models import audio                                                    # noqa: E402
from core.models.audio import (                                                  # noqa: E402
    CUE_JINGLE, CUE_JINGLE_ACTION, CUE_SFX, CUE_SOUND_ACTION, Jingle, Music, MusicCue, MusicSection,
)
from core.music_structure import (                                               # noqa: E402
    ERROR, WARNING, cue_problems, jingle_ignored_settings, music_cue_rows, retrim, wav_boundaries,
)


def _tracker(*cues, **kw) -> Music:
    music = Music(name="Theme", asset="assets/music/Theme.it", **kw)
    for position, kind, target in cues:
        music.add_cue(position, kind, target)
    return music


def _wav(*cues, **kw) -> Music:
    music = Music(name="Amb", asset="assets/music/Amb.wav", unit=audio.UNIT_MS, **kw)
    for position, kind, target in cues:
        music.add_cue(position, kind, target)
    return music


# ── Le modèle ─────────────────────────────────────────────────────


def test_un_repere_se_relit_comme_il_s_ecrit():
    music = _tracker((4, CUE_SFX, "Bip"), (2, CUE_SOUND_ACTION, "pas"))
    back = Music.from_dict(music.to_dict())
    assert [(c.position, c.kind, c.target) for c in back.cues] == [(2, CUE_SOUND_ACTION, "pas"), (4, CUE_SFX, "Bip")]


def test_les_reperes_restent_tries_par_position():
    music = _tracker((9, CUE_SFX, "a"), (1, CUE_SFX, "b"), (5, CUE_SFX, "c"))
    assert [c.position for c in music.cues] == [1, 5, 9]


def test_un_sidecar_d_avant_les_reperes_se_relit_sans_repere():
    assert Music.from_dict({"name": "Old", "asset": "assets/music/Old.it"}).cues == []


def test_une_nature_inconnue_ou_un_sidecar_ecrit_a_la_main_ne_plante_pas():
    back = Music.from_dict({"name": "M", "cues": [{"position": 3, "kind": "nope", "target": "x"}, "n'importe quoi"]})
    assert [(c.kind, c.position) for c in back.cues] == [(CUE_SFX, 3)]


def test_un_jingle_n_ignore_plus_ses_reperes():
    jingle = Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it")
    jingle.add_cue(0, CUE_SFX, "Bip")
    assert "cues" not in jingle_ignored_settings(jingle)


# ── Ce que la ROM lit : des positions d'ordre ─────────────────────


def test_un_module_garde_la_position_d_ordre_du_modele():
    music = _tracker((3, CUE_SFX, "Bip"))
    assert [(order, cue.target) for order, cue in music_cue_rows(music)] == [(3, "Bip")]


def test_un_repere_dans_une_autre_unite_que_le_fichier_n_a_pas_de_ligne():
    assert music_cue_rows(_tracker((3, CUE_SFX, "Bip"), unit=audio.UNIT_MS)) == []


def _write(path: Path, seconds: float, rate: int = 44100) -> Path:
    t = np.arange(int(rate * seconds)) / rate
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.sin(2 * np.pi * 440 * t) * 0.6 * 32767).astype("<i2").tobytes())
    return path


def test_un_wav_coupe_une_frontiere_a_chaque_repere():
    """Sans frontière, le repère tomberait au début du pattern qui le contient."""
    assert wav_boundaries(_wav((1200, CUE_SFX, "Bip"), (500, CUE_SFX, "Bip"))) == [500, 1200]
    assert wav_boundaries(_wav((0, CUE_SFX, "Bip"))) == []          # le début est toujours une frontière


def test_un_wav_traduit_ses_millisecondes_par_le_plan_du_build(tmp_path):
    track = _write(tmp_path / "Amb.wav", 3.0)
    music = _wav((0, CUE_SFX, "A"), (1000, CUE_SFX, "B"), (2000, CUE_SFX, "C"))
    orders = [order for order, _cue in music_cue_rows(music, track)]
    assert orders[0] == 0 and orders == sorted(set(orders))        # trois positions distinctes, dans l'ordre
    assert music_cue_rows(music) == []                              # sans fichier, pas de plan


def test_rogner_un_wav_fait_glisser_les_reperes_et_ecarte_ceux_qui_sortent():
    music = _wav((500, CUE_SFX, "A"), (2500, CUE_SFX, "B"), (4500, CUE_SFX, "C"))
    music.sections = [MusicSection("S", start=0, end=3000)]
    retrim(music, 1000, 4000, total_ms=5000)                       # garde [1000, 4000) : 3 s
    assert [(c.position, c.target) for c in music.cues] == [(1500, "B")]


# ── La position, mise en face du fichier ──────────────────────────


def test_un_repere_hors_du_fichier_est_une_erreur():
    music = _tracker((12, CUE_SFX, "Bip"))
    assert (ERROR, "a cue at 12 is outside the file (8 order positions).") in cue_problems(
        music, audio.UNIT_ORDER, 8, table=list(range(8)))


def test_un_repere_sur_un_separateur_ne_se_declencherait_jamais():
    problems = cue_problems(_tracker((1, CUE_SFX, "Bip")), audio.UNIT_ORDER, 4, table=[0, 254, 1, 255])
    assert [level for level, _m in problems] == [WARNING]


def test_un_repere_qui_ne_vise_rien_est_signale():
    problems = cue_problems(_tracker((0, CUE_SFX, "")), audio.UNIT_ORDER, 4, table=[0, 1, 2, 3])
    assert [level for level, _m in problems] == [WARNING]


# ── Ce que le build émet ──────────────────────────────────────────


class _Project(SimpleNamespace):
    def sound_action_names(self, kind: str) -> list:
        return {"sound_box": ["pas", "saut"], "jingle_box": ["victoire"]}[kind]


def _project() -> _Project:
    return _Project(sfx=[SimpleNamespace(name="Bip", volume=100)],
                    jingles=[SimpleNamespace(name="Fanfare", volume=100)])


def _emitted(music: Music, *jingles: Jingle) -> str:
    assets = {"music": [(music, None), *[(j, None) for j in jingles]]}
    return "\n".join(sound_emit.music_runtime_lines(_project(), assets))


def test_une_musique_sans_repere_a_un_pas_vide_mais_present():
    """La boucle principale l'appelle sans savoir s'il y en a."""
    code = _emitted(_tracker())
    assert "static void music_cue_tick(void){}" in code and "g_music_cue" not in code and "g_cue_last" not in code


def test_chaque_nature_est_resolue_au_build_en_index_ou_en_constante():
    music = _tracker((0, CUE_SOUND_ACTION, "saut"), (2, CUE_JINGLE_ACTION, "victoire"),
                     (4, CUE_SFX, "Bip"), (6, CUE_JINGLE, "Fanfare"))
    code = _emitted(music, Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it"))
    assert "{ MOD_THEME, 0, 0, 1, 0 }," in code            # l'action `saut` est la 2e : l'index, pas un nom
    assert "{ MOD_THEME, 2, 1, 0, 0 }," in code
    assert "{ MOD_THEME, 4, 2, SFX_BIP, 255 }," in code    # le volume d'un effet est sur 0-255
    assert "{ MOD_THEME, 6, 3, MOD_FANFARE, 1024 }," in code   # celui d'un jingle sur 0-1024
    assert "#define MUSIC_CUE_COUNT 4" in code


def test_la_boite_dit_a_l_execution_vers_quoi_pointe_une_action():
    code = _emitted(_tracker((0, CUE_SOUND_ACTION, "pas")))
    assert "sfx_play(g_sound_box_action[c->id], g_sound_box_action_vol[c->id], 0)" in code
    assert "g_jingle_box_action" not in code               # une nature absente n'émet pas son cas : le symbole n'existerait pas


def test_un_jingle_joue_avec_la_politique_de_son_asset():
    fanfare = Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it", music_policy=audio.JINGLE_DUCK, duck_level=30,
                     duck_release=45)
    code = _emitted(_tracker((0, CUE_JINGLE, "Fanfare")), fanfare)
    level = audio.volume_to_module(30)
    assert f"[MOD_FANFARE] = {{ 1, {level}, 45 }}," in code
    assert "music_jingle(id, volume, g_jingle_policy[id][0]" in code


def test_un_repere_qui_vise_un_inconnu_n_a_pas_de_ligne():
    """Le validateur le dit ; le build n'invente pas de cible."""
    code = _emitted(_tracker((0, CUE_SFX, "Fantome"), (2, CUE_SOUND_ACTION, "inconnue")))
    assert "g_music_cue" not in code


def test_un_jingle_n_emet_pas_de_repere_d_ordre():
    """Les siens sont en temps : une autre table, lue par images (cf. plus bas)."""
    jingle = Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it")
    jingle.add_cue(0, CUE_SFX, "Bip")
    assert "g_music_cue" not in _emitted(_tracker(), jingle)


def test_le_pas_ne_declenche_qu_a_l_entree_dans_une_position_et_jamais_a_la_fin_d_une_boucle():
    code = _emitted(_tracker((0, CUE_SFX, "Bip")))
    assert "if(pos == g_cue_last) return;" in code
    assert "if(g_mloop_end > 0 && pos >= g_mloop_end) return;" in code
    assert "g_cue_last = -1;   /* a module that starts again" in code     # un module relancé rejoue son premier repère


# ── L'aperçu : le deck mixe les sons de repère ────────────────────


class _Rendu:
    """Un module minimal pour le deck : trois ordres, un repère par ordre connu."""

    def __init__(self, seconds: float = 3.0):
        from core.engine_emulation.music_deck import Track
        rate = 32768
        self.track = Track(pcm=np.zeros((int(rate * seconds), 2), dtype=np.int16),
                           marks={0: 0, 1: rate, 2: 2 * rate}, order_count=3)
        self.rate = rate


def _deck():
    from core.engine_emulation.music_deck import MusicDeck
    return MusicDeck(32768)


def test_le_deck_declenche_le_son_d_un_repere_en_entrant_dans_son_ordre():
    r, deck = _Rendu(), _deck()
    deck.play(r.track, 1024, loop=False)
    ping = np.full((4000, 2), 1000, dtype=np.int16)
    deck.set_cues({1: [(ping, 1024)]})
    before = deck.pull(r.rate // 2)                       # la 1re demi-seconde : l'ordre 0, rien ne sonne
    assert not before.any()
    heard = deck.pull(r.rate // 2 + 2000)                 # on franchit l'ordre 1 : le son part
    assert heard[: r.rate // 2].max() == 0 and int(heard.max()) == 1000


def test_chaque_tour_de_boucle_rejoue_le_repere():
    r, deck = _Rendu(1.5), _deck()
    deck.play(r.track, 1024, loop=True)
    ping = np.full((200, 2), 500, dtype=np.int16)
    deck.set_cues({0: [(ping, 1024)]})
    loud = 0
    for _ in range(40):                                  # ~2,4 s : la piste (1,5 s) a bouclé
        block = deck.pull(r.rate // 16)
        loud += int(block.any())
    assert loud >= 2                                      # le repère de l'ordre 0 a sonné au 1er passage ET au 2e


def test_un_son_de_repere_ne_depasse_pas_le_plein_niveau():
    r, deck = _Rendu(), _deck()
    deck.play(r.track, 1024, loop=False)
    deck.set_cues({0: [(np.full((500, 2), 30000, dtype=np.int16), 1024)] * 3})
    assert int(deck.pull(1200).max()) == 32767           # trois voix saturent, elles ne débordent pas


def test_arreter_le_deck_eteint_les_reperes():
    r, deck = _Rendu(), _deck()
    deck.play(r.track, 1024, loop=False)
    deck.set_cues({0: [(np.full((500, 2), 900, dtype=np.int16), 1024)]})
    deck.stop()
    deck.play(r.track, 1024, loop=False)
    assert not deck.pull(1200).any()                       # plus de repère après un arrêt : un autre aperçu n'en hérite pas


# ── Les repères d'un jingle : du temps, compté en images par la ROM ──


def _fanfare(*cues) -> Jingle:
    jingle = Jingle(name="Fanfare", asset="assets/jingles/Fanfare.it")
    for position, kind, target in cues:
        jingle.add_cue(position, kind, target)
    return jingle


def test_les_reperes_d_un_jingle_se_convertissent_en_images_de_la_console():
    from core.music_structure import VBLANK_HZ, jingle_cue_frames
    rows = jingle_cue_frames(_fanfare((0, CUE_SFX, "a"), (1000, CUE_SFX, "b"), (2500, CUE_SOUND_ACTION, "pas")))
    assert [frame for frame, _cue in rows] == [0, round(VBLANK_HZ), round(2.5 * VBLANK_HZ)]
    assert 59.7 < VBLANK_HZ < 59.8                         # 16 777 216 / 280 896, pas 60


def test_un_jingle_ne_lance_pas_un_jingle():
    from core.music_structure import jingle_cue_frames
    jingle = _fanfare((500, CUE_JINGLE, "Autre"), (500, CUE_JINGLE_ACTION, "win"), (500, CUE_SFX, "Bip"))
    assert [cue.kind for _frame, cue in jingle_cue_frames(jingle)] == [CUE_SFX]
    problems = cue_problems(jingle, audio.UNIT_MS, None)
    assert [level for level, _m in problems].count(WARNING) == 2


def test_les_reperes_d_un_jingle_module_sont_en_ms_meme_si_le_fichier_est_en_ordres():
    """13 jingles sur 19 de la démo n'ont qu'UN ordre : un repère par ordre ne pourrait viser que leur début."""
    jingle = _fanfare((1500, CUE_SFX, "Bip"))
    assert jingle.unit == audio.UNIT_ORDER
    assert cue_problems(jingle, audio.UNIT_MS, None) == []
    assert music_cue_rows(jingle) == [] and wav_boundaries(jingle) == []


def test_le_c_compte_les_images_d_un_jingle_depuis_son_depart():
    fanfare = _fanfare((0, CUE_SFX, "Bip"), (1000, CUE_SOUND_ACTION, "pas"))
    code = _emitted(_tracker(), fanfare)
    assert "static const MusicCue g_jingle_cue[JINGLE_CUE_COUNT]" in code
    assert "{ MOD_FANFARE, 0, 2, SFX_BIP, 255 }," in code and "{ MOD_FANFARE, 60, 0, 0, 0 }," in code
    assert "g_jingle_cur = id; g_jingle_frame = 0;" in code           # un nouveau jingle repart de zéro
    assert "g_jingle_cue[i].order == g_jingle_frame" in code and "g_jingle_frame++;" in code
    assert "if(!g_jingle_watch) return;" in code                      # un jingle fini ne tire plus rien
    assert "g_music_cue" not in code and "music_cue_music_tick" not in code
    assert "static void music_cue_tick(void){\n    music_cue_jingle_tick();\n}" in code


def test_musique_et_jingle_ont_chacun_leur_pas():
    code = _emitted(_tracker((0, CUE_SFX, "Bip")), _fanfare((0, CUE_SFX, "Bip")))
    assert "music_cue_music_tick();" in code and "music_cue_jingle_tick();" in code


def test_un_son_a_retard_ne_part_qu_apres_son_retard():
    r, deck = _Rendu(), _deck()
    deck.play(r.track, 1024, loop=False)
    deck.start_voices([(np.full((300, 2), 700, dtype=np.int16), 1024, 2000)])
    heard = deck.pull(3000)
    assert heard[:2000].max() == 0 and int(heard[2000:2300].min()) == 700 and heard[2300:].max() == 0


def test_un_son_a_retard_qui_commence_dans_un_bloc_suivant_est_aligne():
    r, deck = _Rendu(), _deck()
    deck.play(r.track, 1024, loop=False)
    deck.start_voices([(np.full((100, 2), 400, dtype=np.int16), 1024, 5000)])
    first = deck.pull(3000)
    second = deck.pull(3000)                              # le son tombe à 2000 échantillons du début de ce bloc
    assert first.max() == 0 and second[:2000].max() == 0 and int(second[2000:2100].min()) == 400
