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


import pytest


@pytest.fixture(autouse=True)
def _tests_never_write_the_real_crash_log(tmp_path, monkeypatch):
    """Les journaux de crash de CHAQUE test vont dans son dossier temporaire, jamais dans celui de l'auteur.

    Beaucoup de tests provoquent des erreurs exprès (manifeste tronqué, dossier `build` déjà fichier…) ;
    `Project.open` en écrit la trace dans `crash.log`. Sans cette redirection, ces traces s'accumulaient
    par centaines dans le vrai `%APPDATA%/<app>/crash.log` et noyaient les vrais crashs de l'éditeur.
    Un test qui veut lire ce journal le redirige lui-même (`monkeypatch.setattr(crash_log, "LOG_FILE", …)`)
    : sa redirection passe après celle-ci."""
    from core import crash_log
    monkeypatch.setattr(crash_log, "LOG_FILE", tmp_path / "crash.log")
    monkeypatch.setattr(crash_log, "NATIVE_LOG_FILE", tmp_path / "crash_native.log")
    monkeypatch.setattr(crash_log, "_repeats", {})
    monkeypatch.setattr(crash_log, "_shown_summaries", set())


# ── Marqueurs de coût ─────────────────────────────────────────────────────────
#
# Deux marqueurs se posent d'après ce que le test utilise, pas d'après son dossier : un test qui
# change de dossier ou un nouveau test qui compile une sonde les reçoit sans que personne y pense.
#   ui     : le test demande `qapp`, ou vit sous tests/ui (certains créent leur propre QApplication).
#   native : le module cherche le compilateur de la machine (`compilateur_hote`, ou l'un des deux
#            équivalents locaux). Le marqueur vaut pour le module entier.
# `slow` (build devkitPro) reste posé à la main sur les tests concernés.
# Paliers : `-m "not ui and not native"` = logique pure, en secondes ; défaut = tout sauf `slow`.

_HOST_COMPILER_NAMES = ("compilateur_hote", "_compilateur_hote", "_host_gcc")


def pytest_collection_modifyitems(items):
    for item in items:
        if "qapp" in item.fixturenames or "ui" in item.path.parts:
            item.add_marker(pytest.mark.ui)
        if any(hasattr(item.module, name) for name in _HOST_COMPILER_NAMES):
            item.add_marker(pytest.mark.native)


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
