"""Racine des tests — met `editor/` sur `sys.path`.

L'éditeur s'importe depuis `editor/` (`from core...`, `from codegen...`), jamais
depuis la racine du dépôt : c'est la porte qu'emprunte `main.py` au lancement et
celle que suit `tools/check_architecture.py`. Les tests entrent par la même,
sinon ils vérifieraient une arborescence de modules que personne n'exécute.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR   = Path(__file__).resolve().parent.parent
EDITOR_DIR = REPO_DIR / "editor"

if str(EDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(EDITOR_DIR))


# ── Couverture des diagnostics (cf. tools/diagnostic_coverage.py) ─────────────
#
# Chaque run note les lignes qui construisent un diagnostic. À la fin d'un run COMPLET, un
# avertissement dit quel diagnostic couvert ne l'est plus, ou quel nouveau n'est jamais déclenché.
# Il n'échoue jamais.

TOOLS_DIR = REPO_DIR / "tools"


def pytest_configure(config):
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    from diagnostic_coverage import Recorder
    config._diagnostic_recorder = Recorder()
    config._diagnostic_recorder.install()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    import json
    import os
    import diagnostic_coverage as dc

    recorder = getattr(config, "_diagnostic_recorder", None)
    if recorder is None:
        return
    out = os.environ.get("DIAGNOSTIC_COVERAGE_OUT")
    if out:                                   # le relevé que demande `tools/diagnostic_coverage.py`
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(sorted(recorder.hits), handle)
        return

    baseline = dc.load_baseline()
    collected = getattr(terminalreporter, "_numcollected", 0)
    update = bool(os.environ.get("DIAGNOSTIC_COVERAGE_UPDATE"))
    # « Complet » : ni -k ni -m (hors le « not slow » par défaut de pyproject), et presque autant de
    # tests que lors du relevé de référence.
    full = (bool(baseline) and not config.option.keyword
            and config.option.markexpr in ("", "not slow")
            and collected >= 0.9 * baseline.get("collected", 10 ** 9))
    if not (full or update):
        return
    sites = dc.enumerate_sites()
    covered = recorder.covered(sites)
    if update:
        dc.write_baseline(sites, covered, collected)
        terminalreporter.write_line(
            f"Diagnostic coverage reference updated: {len(covered & {s.key for s in sites})}"
            f"/{len(sites)} sites.", yellow=True)
        return
    report = dc.compare(sites, covered, baseline)
    for line in dc.summary_lines(report, baseline):
        terminalreporter.write_line(line, yellow=line.startswith("WARNING"))
