"""`music.cut_to` reprend la cible au MÊME index d'ordre que la source.

Le contrôle d'avant comparait des longueurs de table, ce qui ne dit ni ce qui
tombera ni ce que la ROM en fait. Ce qu'il faut tenir : chaque position où la
source peut se trouver désigne un PATTERN dans la cible. Ce qui arrive sur un
index qui n'en désigne pas a été mesuré sur ROM le 2026-10-11 : un séparateur
retombe sur le pattern suivant, un 255 ou une position hors table REDÉMARRE la
cible avec `MM_PLAY_LOOP` et l'ARRÊTE avec `MM_PLAY_ONCE`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                  # noqa: E402
from core import validator                                   # noqa: E402
from core.engine_emulation.it_file import parse_it           # noqa: E402
from core.models.audio import Music                          # noqa: E402
from core.models.sound_box import (                          # noqa: E402
    MusicBox, MusicState, MusicTransition, TRANSITION_CUT, TRANSITION_FADE,
)
from core.music_structure import cut_problems                # noqa: E402
from core.project import Project                             # noqa: E402
from core.validator import ValidationContext                 # noqa: E402


def _mod(orders):
    return parse_it(F.make_it(orders=orders))


def _cut(src_orders, dst_orders, **kw):
    return cut_problems("A", "B", _mod(src_orders), _mod(dst_orders), **kw)


# ── Ce qui est sans danger ────────────────────────────────────────


def test_deux_tables_identiques_se_relaient():
    assert _cut([0, 0, 0, 0], [0, 0, 0, 0]) == []


def test_une_cible_plus_longue_que_la_source_ne_risque_rien():
    """L'ancien contrôle avertissait ici : la longueur différait. Pourtant chaque
    position de la source existe dans la cible."""
    assert _cut([0, 0, 0], [0, 0, 0, 0, 0, 0]) == []


def test_les_positions_apres_la_fin_de_la_source_ne_comptent_pas():
    """Après un 255, la source ne joue plus rien : ces positions ne sont jamais
    celles d'une coupe."""
    assert _cut([0, 255, 0, 0, 0], [0, 0]) == []


def test_un_separateur_cote_source_ne_gene_pas():
    assert _cut([0, 254, 0, 0], [0, 0, 0, 0]) == []


# ── Ce qui tombe à côté ───────────────────────────────────────────


def test_une_cible_plus_courte_est_signalee_avec_la_position_fautive():
    found = _cut([0, 0, 0, 0, 0, 0], [0, 0, 0, 0])
    assert len(found) == 1
    assert "no music from position 4" in found[0] and "2 of 6 positions" in found[0]


def test_la_consequence_depend_du_mode_de_lecture_de_la_cible():
    """Mesuré : MM_PLAY_LOOP redémarre, MM_PLAY_ONCE s'arrête."""
    assert "restarts from its beginning" in _cut([0] * 5, [0] * 3, dst_loop=True)[0]
    assert "goes silent" in _cut([0] * 5, [0] * 3, dst_loop=False)[0]


def test_deux_tables_de_meme_longueur_peuvent_quand_meme_tomber_a_cote():
    """Le cas que la comparaison de longueurs ne voyait pas : un séparateur à
    l'index 1 de la cible, là où la source joue un pattern."""
    found = _cut([0, 0, 0, 0], [0, 254, 0, 0])
    assert len(found) == 1 and "separator" in found[0] and "position 1" in found[0]


def test_une_fin_de_morceau_dans_la_cible_est_signalee_comme_une_position_hors_table():
    found = _cut([0, 0, 0, 0], [0, 0, 255, 0])
    assert len(found) == 1 and "no music from position 2" in found[0]


def test_un_module_illisible_ne_dit_rien_de_la_structure():
    assert cut_problems("A", "B", None, _mod([0, 0])) == []
    assert cut_problems("A", "B", _mod([0, 0]), None) == []


# ── Les pistes WAV ────────────────────────────────────────────────


def test_une_coupe_vers_un_wav_reste_signalee():
    found = cut_problems("A", "W", None, None, dst_wav=True)
    assert len(found) == 1 and "WAV track" in found[0] and "silent" in found[0]


def test_une_coupe_depuis_un_wav_attend_la_fin_de_son_pattern():
    """Le runtime guette le retour de la LIGNE à zéro ; un segment de WAV n'en a
    qu'une toutes les 256 lignes, soit ~3 s au pire."""
    found = cut_problems("W", "B", None, _mod([0, 0]), src_wav=True)
    assert len(found) == 1 and "3 s" in found[0] and "fade" in found[0]


# ── Le même contrôle, sur les arêtes d'une MusicBox ────────────────


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _music(project: Project, name: str, orders, loop: bool = True) -> None:
    path = project.assets_dir / "music" / f"{name}.it"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(F.make_it(orders=orders))
    project.music.append(Music(name=name, asset=f"assets/music/{name}.it", loop=loop))


def _box(project: Project, edges, states=("a", "b", "c")) -> list[str]:
    project.music_boxes.append(MusicBox(
        name="m", start="a",
        states=[MusicState(name=n, music=n.upper()) for n in states],
        transitions=edges))
    ctx = ValidationContext(project)
    validator._check_sound_boxes(ctx)
    return [m.message for m in ctx._msgs if "cut" in m.message]


def test_une_arete_cut_est_comparee_a_sa_source_et_nomme_la_position(project):
    _music(project, "A", [0] * 6)
    _music(project, "B", [0] * 4)
    found = _box(project, [MusicTransition(src="a", dst="b", trigger="go", kind=TRANSITION_CUT)],
                 states=("a", "b"))
    assert len(found) == 1 and "no music from position 4" in found[0]
    assert 'cut a → b' in found[0]


def test_une_arete_fade_n_est_pas_concernee(project):
    _music(project, "A", [0] * 6)
    _music(project, "B", [0] * 4)
    assert _box(project, [MusicTransition(src="a", dst="b", trigger="go", kind=TRANSITION_FADE)],
                states=("a", "b")) == []


def test_une_arete_sans_source_regarde_tous_les_autres_etats(project):
    """`src` vide = « depuis n'importe quel état » : chaque musique peut être celle
    qui joue au moment de la coupe."""
    _music(project, "A", [0] * 6)
    _music(project, "B", [0] * 4)
    _music(project, "C", [0] * 4)
    found = _box(project, [MusicTransition(src="", dst="c", trigger="die", kind=TRANSITION_CUT)])
    assert len(found) == 1 and '"A"' in found[0] and "cut * → c" in found[0]


def test_le_mode_de_lecture_vient_de_l_etat_d_arrivee(project):
    _music(project, "A", [0] * 6)
    _music(project, "B", [0] * 4)
    project.music_boxes.append(MusicBox(
        name="m", start="a",
        states=[MusicState(name="a", music="A"), MusicState(name="b", music="B", loop=False)],
        transitions=[MusicTransition(src="a", dst="b", trigger="go", kind=TRANSITION_CUT)]))
    ctx = ValidationContext(project)
    validator._check_sound_boxes(ctx)
    assert any("goes silent" in m.message for m in ctx._msgs)


# ── L'aperçu fait ce que fait la ROM ──────────────────────────────


def _track(marks, order_count, restart=0, n=400, offset=0):
    import numpy as np
    from core.engine_emulation.music_deck import Track
    pcm = np.zeros((n, 2), dtype=np.int16)
    pcm[:, 0] = np.arange(n) + offset
    return Track(pcm=pcm, marks=marks, restart=restart, order_count=order_count)


def test_une_position_se_resout_comme_mmposition():
    track = _track({0: 0, 1: 100, 3: 300}, order_count=5)
    assert track.start_of(1) == 100
    assert track.start_of(2) == 300       # séparateur : le pattern SUIVANT
    assert track.start_of(4) is None      # dans la table, mais plus rien après
    assert track.start_of(9) is None      # hors table
    assert _track({}, order_count=0).start_of(7) == 0   # un WAV : pas de structure à violer


def _cut_at_order_one(loop: bool):
    from core.engine_emulation.music_deck import MusicDeck
    src = _track({0: 0, 1: 100, 2: 200, 3: 300}, order_count=4)
    dst = _track({0: 0}, order_count=1, offset=1000)          # n'a rien à la position 1
    deck = MusicDeck(mix_rate=6000)                            # 100 échantillons par frame
    deck.play(src, volume=1024, loop=True)
    deck.cut_to(dst, volume=1024, loop=loop)
    return deck, deck.pull(150)


def test_une_coupe_sans_musique_a_cette_position_redemarre_avec_la_boucle():
    deck, out = _cut_at_order_one(loop=True)
    assert deck.playing
    assert list(out[100:105, 0]) == [1000, 1001, 1002, 1003, 1004]   # le début (restart 0)


def test_une_coupe_sans_musique_a_cette_position_s_arrete_sans_la_boucle():
    deck, out = _cut_at_order_one(loop=False)
    assert not deck.playing
    assert not out[100:150].any()


def test_poser_la_tete_de_lecture_saute_a_l_ordre_sans_etre_ramene_par_la_section():
    from core.engine_emulation.music_deck import MusicDeck
    track = _track({0: 0, 1: 100, 2: 200, 3: 300}, order_count=4)
    track.loop_orders = (2, 4)                                 # la section commence à l'ordre 2
    deck = MusicDeck(mix_rate=6000)
    deck.play(track, volume=1024, loop=True, start_at=250)     # dedans : la section est « entrée »
    deck.pull(10)
    deck.seek_to_order(0)                                      # avant la section : on y reste
    assert deck.position == 0
    deck.pull(150)
    assert track.order_at(deck.position) == 1                  # pas ramené au début de la section
