"""Un jingle en module se coupe aux positions d'ordre : ce que la coupe écrit, par format, et ce que l'asset en dit.

La fonction est UNE (`core/module_trim.cut_orders`) : le build l'écrit dans `build/music/`, l'aperçu la lit — on vérifie donc ici le
module qu'elle rend, en le relisant avec le lecteur de l'éditeur."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import module_fixtures as F                                            # noqa: E402
from core.engine_emulation.module_model import ORDER_END, parse_module  # noqa: E402
from core.models.audio import Jingle                                    # noqa: E402
from core.module_trim import cut_orders, is_order_cut, order_problem, order_window  # noqa: E402


def _mod_with_patterns(orders: list[int]) -> bytes:
    """Un MOD dont chaque motif porte une marque (sa note à la ligne 1), pour voir LEQUEL sort de la coupe."""
    base = F.make_mod()
    header, pattern, samples = base[:1084], base[1084:1084 + 1024], base[1084 + 1024:]
    count = max(orders) + 1
    patterns = []
    for number in range(count):
        marked = bytearray(pattern)
        marked[16:20] = bytes([0x01, 0xAC + number, 0x10, 0x00])      # ligne 1, canal 0 : une période par motif
        patterns.append(bytes(marked))
    table = bytes(orders).ljust(128, b"\x00")
    head = header[:950] + bytes([len(orders), 127]) + table + header[1080:]
    return head + b"".join(patterns) + samples


def test_xm_keeps_only_the_range_and_its_length_follows():
    data = F.make_xm(orders=[0, 0, 0, 0])
    assert parse_module(cut_orders(data, 1, 3)).order == [0, 0]
    assert parse_module(cut_orders(data, 2, 0)).order == [0, 0]            # fin à 0 : jusqu'au bout


def test_it_and_s3m_keep_their_size_and_end_the_table_with_the_end_marker():
    for make, kind in ((F.make_it, "it"), (F.make_s3m, "s3m")):
        data = make(orders=[0, 0, 0, 0])
        cut = cut_orders(data, 1, 3)
        assert len(cut) == len(data), kind                                   # les adresses qui suivent la table restent justes
        order = parse_module(cut).order
        assert order[:2] == [0, 0] and set(order[2:]) == {ORDER_END}, kind
        assert len(order) == 4


def test_mod_rewrites_its_patterns_so_the_samples_stay_where_they_are():
    data = _mod_with_patterns([0, 1, 2, 1])
    original = parse_module(data)
    cut = parse_module(cut_orders(data, 1, 3))
    assert cut.order == [0, 1]                                               # renumérotés : motifs 1 et 2 sont devenus 0 et 1
    assert len(cut.patterns) == 2
    assert cut.patterns[0] == original.patterns[1] and cut.patterns[1] == original.patterns[2]
    assert [s.data.tobytes() for s in cut.samples] == [s.data.tobytes() for s in original.samples]      # l'échantillon n'a pas bougé d'un octet


def test_mod_drops_the_patterns_the_range_no_longer_plays():
    data = _mod_with_patterns([0, 1, 2, 1])
    assert len(cut_orders(data, 1, 2)) == len(data) - 2 * 1024              # un seul motif gardé sur trois


def test_a_range_that_keeps_nothing_is_refused():
    for data in (F.make_xm(orders=[0, 0]), F.make_it(orders=[0, 0]), _mod_with_patterns([0, 1])):
        with pytest.raises(ValueError, match="keeps nothing"):
            cut_orders(data, 5, 0)


def test_an_unknown_file_is_refused():
    with pytest.raises(ValueError):
        cut_orders(b"RIFF....WAVEfmt ", 0, 1)


def test_the_window_is_bounded_to_the_table_and_the_end_is_never_zero():
    assert order_window(Jingle(name="J"), 8) == (0, 8)
    assert order_window(Jingle(name="J", order_start=2, order_end=6), 8) == (2, 6)
    assert order_window(Jingle(name="J", order_start=2, order_end=99), 8) == (2, 8)
    assert order_window(Jingle(name="J", order_start=3), 8) == (3, 8)


def test_an_untouched_jingle_is_not_cut():
    assert not is_order_cut(Jingle(name="J"))
    assert is_order_cut(Jingle(name="J", order_start=1)) and is_order_cut(Jingle(name="J", order_end=3))


def test_the_problems_the_validator_names():
    assert order_problem(Jingle(name="J"), 4) is None
    assert "past the last order" in order_problem(Jingle(name="J", order_start=4), 4)
    assert "before it starts" in order_problem(Jingle(name="J", order_start=3, order_end=2), 4)


def test_the_range_survives_the_sidecar_and_an_old_sidecar_reads_as_whole():
    jingle = Jingle(name="J", order_start=2, order_end=5)
    again = Jingle.from_dict(jingle.to_dict())
    assert (again.order_start, again.order_end) == (2, 5)
    old = Jingle.from_dict({"name": "J", "asset": "assets/jingles/J.it"})
    assert (old.order_start, old.order_end) == (0, 0)
    assert Jingle.from_dict({"name": "J", "order_start": -3}).order_start == 0


def test_the_validator_flags_a_range_past_the_module_and_ignores_it_on_a_wav(tmp_path):
    from core.music_structure import music_problems
    module_path = tmp_path / "J.it"
    module_path.write_bytes(F.make_it(orders=[0, 0, 0, 0]))
    from core.engine_emulation.module_model import load_module
    bad = Jingle(name="J", asset="assets/jingles/J.it", order_start=9)
    problems = music_problems(bad, module_path, load_module)
    assert any("past the last order" in text for _level, text in problems)
    ok = Jingle(name="J", asset="assets/jingles/J.it", order_start=1, order_end=3)
    assert not any("order" in text for _level, text in music_problems(ok, module_path, load_module))
