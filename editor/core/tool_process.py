"""Lancement des outils en ligne de commande (make, grit, gcc, bin2s, binutils).

L'éditeur installé n'a pas de console (Nuitka, `--windows-console-mode=disable`) :
sans précaution, Windows ouvre une fenêtre de console à chaque outil lancé, et
un build en enchaîne des dizaines. `CREATE_NO_WINDOW` donne à l'outil une console
invisible, que `make` et ses enfants (sh, gcc…) héritent au lieu d'en créer
d'autres. `stdin` est fermé : sans console, celui du parent est invalide.
"""

from __future__ import annotations

import subprocess

from core.app_paths import IS_WINDOWS


def run_tool(cmd, **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` pour un outil dont on capture la sortie, sans fenêtre."""
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if IS_WINDOWS:
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kwargs)
