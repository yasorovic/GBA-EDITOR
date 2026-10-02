"""
smoke_test.py — « le binaire livré démarre-t-il, et sait-il faire son travail ? »

`Backstage --smoke-test=<rapport.txt>` : crée un projet dans un dossier temporaire,
l'ouvre, VISITE chaque écran, valide le projet, vérifie que les données embarquées
sont là, puis sort avec le code 0 (tout va bien) ou 1. Le rapport est écrit dans un
fichier : la distribution Windows est sans console, et rien ne s'afficherait.

Pourquoi les écrans un par un : ils sont importés PARESSEUSEMENT, par leur nom. Un
module que Nuitka n'a pas vu n'échoue qu'à la première visite de son écran — c'est
exactement ce qu'un utilisateur découvrirait en cliquant. Ce test est l'endroit où
la CI le découvre à sa place, avant de publier.

Ce que ce test ne fait PAS : construire une ROM (devkitPro n'est pas sur le runner
de release) ni lancer d'émulateur.
"""
from __future__ import annotations

import faulthandler
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

WATCHDOG_SECONDS = 180      # une fenêtre modale oubliée bloquerait la CI sans fin


def _data_checks() -> list[tuple[str, Path]]:
    """Les données qui voyagent AVEC l'exécutable, et que le code lit par chemin."""
    import plugins
    import scripting
    from core.app_paths import APP_DIR, RUNTIME_DIR
    from core.project_starters import get_starter
    from ui.common import notice

    return [
        ("licence de l'éditeur", APP_DIR / "LICENSE"),
        ("notices tierces", APP_DIR / "THIRD-PARTY-NOTICES.md"),
        ("runtime : Makefile", RUNTIME_DIR / "Makefile"),
        ("runtime : en-têtes", RUNTIME_DIR / "include"),
        ("starter Basic", get_starter("Basic").path),
        ("référence de l'API", Path(scripting.__file__).parent / "api_reference.json"),
        ("catalogue des notices", Path(notice.__file__).parent / "notices"),
        # Là où `load_all_plugins` les cherche : à côté du paquet lui-même.
        ("dossier des plugins", Path(plugins.__file__).parent),
    ]


def run(app, plugin_errors) -> int:
    """Rend 0 si tout va bien. `app` : la QApplication déjà configurée par main."""
    report: list[str] = []
    failures: list[str] = []

    def note(line: str) -> None:
        report.append(line)

    def fail(line: str) -> None:
        failures.append(line)
        report.append("ECHEC  " + line)

    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
    workdir = Path(tempfile.mkdtemp(prefix="backstage-smoke-"))
    win = None
    try:
        from core.app_info import APP_NAME, APP_VERSION
        note(f"{APP_NAME} {APP_VERSION}")

        for what, path in _data_checks():
            (note if path.exists() else fail)(
                f"{'ok    ' if path.exists() else ''}{what} : {path}")

        for problem in plugin_errors:
            fail(f"plugin : {problem}")

        from window import MainWindow
        win = MainWindow()
        win._new_project("Smoke", workdir / "Smoke")
        note("ok    projet créé et ouvert")

        for index, name in enumerate(win._screen_names):
            try:
                win._show_screen(index)
                app.processEvents()
                note(f"ok    écran {name}")
            except Exception:
                fail(f"écran {name} :\n{traceback.format_exc()}")
        for problem in win.screen_errors:
            fail(f"contrat d'écran : {problem}")

        from core.validator import validate_project
        warnings, errors = validate_project(win.project)
        note(f"ok    validation du projet ({len(warnings)} avertissement(s), {len(errors)} erreur(s))")

        win.project.save()
        note("ok    projet enregistré")
    except Exception:
        fail("exception non rattrapée :\n" + traceback.format_exc())
    finally:
        faulthandler.cancel_dump_traceback_later()
        if win is not None:
            # La fenêtre est locale à `run` : sans fermeture explicite elle serait
            # détruite après la QApplication (cf. `main._shutdown_qt`).
            win.close()
            win.deleteLater()
            app.processEvents()
        shutil.rmtree(workdir, ignore_errors=True)

    report.append("")
    report.append("SMOKE OK" if not failures else f"SMOKE ECHEC ({len(failures)} problème(s))")
    return _emit(report, failures)


def _emit(report: list[str], failures: list[str]) -> int:
    text = "\n".join(report) + "\n"
    target = _report_path()
    if target is not None:
        target.write_text(text, encoding="utf-8")
    try:
        sys.stdout.write(text)         # absent dans la distribution sans console
    except (AttributeError, OSError):
        pass
    return 1 if failures else 0


def _report_path() -> Path | None:
    for arg in sys.argv[1:]:
        if arg.startswith("--smoke-test="):
            return Path(arg.split("=", 1)[1])
    return None
