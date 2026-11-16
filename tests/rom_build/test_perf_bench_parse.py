"""L'analyse du log du banc de coût (tools/run_perf_bench.py) : phases, ligne de base, lignes coupées. Sans émulateur."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import run_perf_bench as bench  # noqa: E402


def _phase(nom, n, durees):
    """La ligne d'image telle que `debug_budget_report` l'écrit aujourd'hui (gba_debug.h) : tous les compteurs."""
    ligne = "frame us={} oam=3 character=0 block=0 contact=0 area=0 fx=0 snd=0"
    return [f"PHASE {nom} {n}"] + [ligne.format(d) for d in durees]


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
    lignes = (_phase("vide", 0, [400] * 40) + _phase("count", 100, [500] * 35)
              + ["frame us=1", "frame us=500 oam=3 charac"])
    count = next(p for p in bench.analyser(lignes)["phases"] if p["name"] == "count")
    assert count["samples"] == 25                 # 35 moins les 10 ignorées ; les deux lignes coupées ne comptent pas


def test_les_compteurs_ajoutes_ne_cassent_pas_la_lecture():
    """La liste des compteurs s'allonge au fil des chantiers : seul `us=` est lu, le reste est accepté tel quel."""
    base = _phase("vide", 0, [400] * 40)
    debordement = ["frame us=500 oam=3 character=1 block=0 contact=9 area=0 fx=0 snd=0 contact_overflow=1"] * 35
    count = next(p for p in bench.analyser(base + ["PHASE count 100"] + debordement)["phases"]
                 if p["name"] == "count")
    assert count["samples"] == 25 and count["median_us"] == 500


def test_phase_trop_courte_est_omise():
    lignes = _phase("vide", 0, [400] * 40) + _phase("count", 100, [500] * 12)
    assert [p["name"] for p in bench.analyser(lignes)["phases"]] == ["vide"]


def test_sans_ligne_de_base():
    with pytest.raises(ValueError):
        bench.analyser(_phase("count", 100, [500] * 40))
