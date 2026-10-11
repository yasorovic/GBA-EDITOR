"""ui/common/reveal.py — REVEAL : ouvrir l'explorateur de fichiers du système sur un élément.

Deux gestes portent deux noms dans tout l'éditeur, et ne se mélangent pas :

* **Locate** — ouvre l'onglet Disk de l'éditeur et y trouve le fichier (cf. `ui/common/locate_bus.py`).
* **Reveal** — ouvre l'explorateur du système et y trouve le fichier (ce module).

Un fichier est SÉLECTIONNÉ dans son dossier là où le système sait le faire (Windows, macOS) ;
ailleurs, Qt ne garantit rien, on ouvre alors son dossier. Un dossier s'ouvre simplement."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def reveal_in_file_manager(path) -> None:
    """Montre `path` dans l'explorateur de fichiers par défaut du système : le fichier y est sélectionné,
    le dossier y est ouvert. Silencieux si `path` est vide ou n'existe pas encore — pas de message
    d'erreur pour un dossier qu'un projet fraîchement créé n'a simplement pas encore créé sur disque."""
    if not path:
        return
    p = Path(path)
    if p.is_file():
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(p)])
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
            return
    target = p if p.is_dir() else p.parent
    if not target.exists():
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
