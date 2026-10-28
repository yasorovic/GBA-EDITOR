"""L'analyse du log du banc de coût (tools/run_perf_bench.py) : phases, ligne de base, lignes coupées. Sans émulateur."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import run_perf_bench as bench  # noqa: E402


def _phase(nom, n, durees):
    return [f"PHASE {nom} {n}"] + [f"frame us={d} oam=3" for d in durees]


def test_surcout_et_cout_par_instance():
    lignes = (_phase("vide", 0, [400] * 40)
              + _phase("balles_immobiles", 100, [9999] * 10 + [2100] * 30)
              + _phase("fin", 0, [400] * 30))
    r = bench.analyser(lignes)
    assert r["baseline_us"] == 400
    balles = next(p for p in r["phases"] if p["name"] == "balles_immobiles")
    assert balles["median_us"] == 2100            # les 10 premières images (pose des acteurs) sont écartées
    assert balles["overhead_us"] == 1700
    assert balles["per_unit_us"] == 17.0
    assert all(p["name"] != "fin" for p in r["phases"])


def test_une_ligne_coupee_est_ecartee():
    lignes = _phase("vide", 0, [400] * 40) + _phase("count", 100, [500] * 35) + ["frame us=1"]
    count = next(p for p in bench.analyser(lignes)["phases"] if p["name"] == "count")
    assert count["samples"] == 25                 # 35 moins les 10 ignorées ; la ligne "frame us=1" sans oam= ne compte pas


def test_phase_trop_courte_est_omise():
    lignes = _phase("vide", 0, [400] * 40) + _phase("count", 100, [500] * 12)
    assert [p["name"] for p in bench.analyser(lignes)["phases"]] == ["vide"]


def test_sans_ligne_de_base():
    with pytest.raises(ValueError):
        bench.analyser(_phase("count", 100, [500] * 40))
