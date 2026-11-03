"""La couverture des diagnostics (chantier « La fiabilité du journal de build », tranche 4).

`tools/diagnostic_coverage.py` énumère les sites qui peuvent émettre un diagnostic et compare ce qu'un
run déclenche à la liste d'exemptions. Ces tests protègent le mécanisme lui-même : une clé qui survit à
un décalage de lignes, un site non testé et non exempté qui avertit, une exemption inutile ou orpheline
qui avertit, et un avertissement qui n'échoue jamais.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
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


def test_un_site_non_teste_et_non_exempte_avertit(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    a, b, c = (s.key for s in sites)
    exemptions = {b: "nécessite devkitPro"}

    report = dc.compare(sites, covered={a}, exemptions=exemptions)

    assert report.unexempted == [c]                      # ni testé ni exempté
    assert report.obsolete == [] and report.stale == []
    lines = dc.summary_lines(report, exemptions)
    assert lines[0].startswith("Diagnostic coverage: 1/3 sites exercised") and "1 exempted" in lines[0]
    assert sum(line.startswith("WARNING") for line in lines) == 1


def test_une_exemption_devenue_inutile_ou_orpheline_avertit(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    a, b, c = (s.key for s in sites)
    exemptions = {a: "testé depuis", "core/validator.py::gone::deadbeef": "message réécrit"}

    report = dc.compare(sites, covered={a, b, c}, exemptions=exemptions)

    assert report.obsolete == [a]                        # exempté, mais un test le déclenche
    assert report.stale == ["core/validator.py::gone::deadbeef"]
    assert report.unexempted == []
    assert sum(line.startswith("WARNING") for line in dc.summary_lines(report, exemptions)) == 2


def test_rien_a_signaler_quand_tout_est_teste_ou_exempte(tmp_path):
    sites = dc.enumerate_sites(_tree(tmp_path))
    a, b, c = (s.key for s in sites)
    report = dc.compare(sites, covered={a, b}, exemptions={c: "hors périmètre"})
    assert not any(line.startswith("WARNING") for line in dc.summary_lines(report, {c: "hors périmètre"}))


def test_sans_fichier_d_exemptions_rien_n_est_exempte(tmp_path):
    assert dc.load_exemptions(tmp_path / "absent.json") == {}


def test_les_exemptions_du_depot_nomment_des_sites_qui_existent_encore():
    """Pas d'exemption orpheline : toute clé du fichier existe dans le code. Une clé qui a disparu (message réécrit,
    fonction renommée) veut dire que l'exemption est à mettre à jour, sinon le site réécrit réapparaît non exempté."""
    current = {s.key for s in dc.enumerate_sites()}
    stale = sorted(set(dc.load_exemptions()) - current)
    assert stale == [], "exemptions orphelines : " + ", ".join(stale[:5])
