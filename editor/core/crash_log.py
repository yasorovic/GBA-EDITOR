"""
core/crash_log.py — laisser une trace quand l'éditeur plante.

Sous PyQt6, une exception Python qui sort d'un slot sans `sys.excepthook`
personnalisé fait `abort()` : le processus meurt dans `Qt6Core.dll`, sans
message ni trace. Deux filets, dans le dossier de config de la machine :

- `sys.excepthook` écrit la trace dans `crash.log` et la confie au reporter (la fenêtre
  d'erreur, cf. `set_reporter`) ;
  l'éditeur continue, au lieu de mourir sur une exception ordinaire.
- `faulthandler` écrit la pile Python dans `crash_native.log` quand le
  processus meurt pour de bon (violation mémoire, `abort`).
"""
from __future__ import annotations

import datetime
import faulthandler
import sys
import traceback

from core.toolchain import config_dir

LOG_FILE = config_dir() / "crash.log"
NATIVE_LOG_FILE = config_dir() / "crash_native.log"

_native_log = None       # garder le fichier ouvert : faulthandler écrit dessus au crash
_reporter = None
_reporting = False


def _write(text: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"\n=== {datetime.datetime.now().isoformat(timespec='seconds')} ===\n{text}")
    except OSError:
        pass   # un log impossible à écrire ne doit pas aggraver le crash


def log_current_exception(context: str) -> None:
    """Écrit l'exception en cours dans `crash.log` SANS la montrer : pour une
    erreur que l'appelant présente déjà lui-même, en clair, à l'utilisateur."""
    _write(f"{context}\n{traceback.format_exc()}")


def set_reporter(reporter) -> None:
    """Branche ce qui MONTRE l'erreur : `reporter(summary, details, log_path)`.

    Le noyau écrit la trace ; l'affichage est de l'interface (cf.
    `ui/common/crash_dialog.py`), d'où ce branchement au démarrage plutôt
    qu'un import d'écran depuis `core`. Sans reporter, seule la trace est écrite."""
    global _reporter
    _reporter = reporter


def _report(summary: str, details: str) -> None:
    """Appelle le reporter. Gardé contre la ré-entrée (une exception levée
    pendant l'affichage rappellerait le hook) et contre un reporter qui échoue :
    la trace est déjà sur le disque, l'erreur du reporter s'ajoute au log."""
    global _reporting
    if _reporter is None or _reporting:
        return
    _reporting = True
    try:
        _reporter(summary, details, LOG_FILE)
    except Exception:
        _write("The error reporter failed:\n" + traceback.format_exc())
    finally:
        _reporting = False


def _excepthook(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _write(text)
    sys.stderr.write(text)
    _report(f"{exc_type.__name__}: {exc}", text)


def install() -> None:
    """À appeler une fois, avant de créer la QApplication."""
    global _native_log
    sys.excepthook = _excepthook
    try:
        NATIVE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _native_log = NATIVE_LOG_FILE.open("a", encoding="utf-8")
        faulthandler.enable(file=_native_log, all_threads=True)
    except OSError:
        faulthandler.enable()
