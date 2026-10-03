"""Le cliquet de couverture des diagnostics (chantier « La fiabilité du journal de build », tranche 4).

`tools/diagnostic_coverage.py` énumère les sites qui peuvent émettre un diagnostic et compare ce qu'un
run déclenche à une référence. Ces tests protègent le mécanisme lui-même : une clé qui survit à un
décalage de lignes, un site perdu ou nouveau qui avertit, et un avertissement qui n'échoue jamais.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
import diagnostic_coverage as dc  # noqa: E402

SOURCE = '''
def check_sprite(ctx, actor):
    ctx.error(actor, "Sprite not found")
    ctx.warn(actor, f"Sprite {actor.name} has no PNG")


def check_other(ctx):
    build_error("make is missing", "make")
'''


def _tree(tmp_path: Path, source: str = SOURCE) -> Path:
    editor = tmp_path / "editor"
    (editor / "core").mkdir(parents=True, exist_ok=True)
    (editor / "core" / "validator.py").write_text(source, encoding="utf-8")
    return editor


def test_chaque_appel_qui_porte_un_message_est_un_site(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    assert [s.function for s in sites] == ["check_sprite", "check_sprite", "check_other"]
    assert all(s.file == "core/validator.py" for s in sites)


def test_la_cle_survit_a_un_decalage_de_lignes(tmp_path):
    before = {s.key for s in dc.enumerate_sites(_tree(tmp_path))}
    after = {s.key for s in dc.enumerate_sites(_tree(tmp_path, "\n\n\n# un commentaire\n" + SOURCE))}
    assert before == after


def test_un_appel_sans_message_n_est_pas_un_site(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path, "def f(ctx, m):\n    ctx.error(None, m)\n"))
    assert sites == []


def test_le_recorder_couvre_le_site_dont_il_a_vu_la_ligne(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    recorder = dc.Recorder()
    recorder.hits = {("core/validator.py", 3)}          # la ligne de ctx.error(...)
    assert recorder.covered(sites) == {sites[0].key}


def test_un_site_perdu_et_un_site_nouveau_avertissent(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    a, b, c = (s.key for s in sites)
    baseline = {"sites": {a: True, b: True}}             # `c` n'existait pas à la référence

    report = dc.compare(sites, covered={a}, baseline=baseline)

    assert report.lost == [b]                            # couvert avant, plus maintenant
    assert report.new_unhit == [c]                       # nouveau, jamais déclenché
    lines = dc.summary_lines(report, baseline)
    assert lines[0].startswith("Diagnostic coverage: 1/3 sites exercised")
    assert sum(line.startswith("WARNING") for line in lines) == 2


def test_rien_a_signaler_quand_la_couverture_se_maintient(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    keys = {s.key for s in sites}
    report = dc.compare(sites, covered=keys, baseline={"sites": {k: True for k in keys}})
    assert report.lost == [] and report.new_unhit == []
    assert not any(line.startswith("WARNING") for line in dc.summary_lines(report, {"sites": {}}))


def test_la_reference_se_relit_telle_quelle(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    path = tmp_path / "baseline.json"
    dc.write_baseline(sites, {sites[0].key}, collected=42, path=path)
    loaded = dc.load_baseline(path)
    assert loaded["collected"] == 42
    assert sum(loaded["sites"].values()) == 1


def test_sans_reference_il_n_y_a_rien_a_comparer(tmp_path):
    assert dc.load_baseline(tmp_path / "absent.json") == {}


def test_la_reference_du_depot_est_a_jour_avec_le_code():
    """Pas de site « fantôme » : toute clé de la référence existe encore dans le code. Une clé qui
    a disparu (message réécrit, fonction renommée) veut dire que la référence est à relever."""
    baseline = dc.load_baseline()
    if not baseline:
        pytest.skip("pas de référence relevée")
    current = {s.key for s in dc.enumerate_sites()}
    stale = sorted(set(baseline["sites"]) - current)
    # un message réécrit change sa clé : on le tolère en petit nombre, on ne laisse pas dériver
    assert len(stale) <= max(5, len(current) // 20), (
        f"{len(stale)} clé(s) de la référence n'existent plus ; relever avec "
        "DIAGNOSTIC_COVERAGE_UPDATE=1 : " + ", ".join(stale[:5]))
