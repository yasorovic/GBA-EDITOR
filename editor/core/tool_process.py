"""Lancement des outils en ligne de commande (make, grit, gcc, bin2s, binutils).

L'éditeur installé n'a pas de console (Nuitka, `--windows-console-mode=disable`) :
sans précaution, Windows ouvre une fenêtre de console à chaque outil lancé, et
un build en enchaîne des dizaines. `CREATE_NO_WINDOW` donne à l'outil une console
invisible, que `make` et ses enfants (sh, gcc…) héritent au lieu d'en créer
d'autres. `stdin` est fermé : sans console, celui du parent est invalide.
"""

from __future__ import annotations

import os
import subprocess

from core.app_paths import IS_WINDOWS


def tool_environment(base: dict | None = None) -> dict:
    """L'environnement d'un outil EXTERNE (make, gcc, grit, mGBA, éditeur de texte).

    Dans l'AppImage, `AppRun` place les bibliothèques embarquées (Qt, OpenSSL…) en
    tête de `LD_LIBRARY_PATH`. Un outil du système qui hérite de ce chemin charge NOS
    bibliothèques à la place des siennes : un mGBA Qt de la distribution plante sur
    une version différente. `AppRun` garde la valeur d'origine dans
    `BACKSTAGE_ORIG_LD_LIBRARY_PATH` ; on la rend ici (ou on retire la variable)."""
    env = dict(os.environ if base is None else base)
    if "BACKSTAGE_ORIG_LD_LIBRARY_PATH" in env:
        original = env.pop("BACKSTAGE_ORIG_LD_LIBRARY_PATH")
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def run_tool(cmd, **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` pour un outil dont on capture la sortie, sans fenêtre."""
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs["env"] = tool_environment(kwargs.get("env"))
    if IS_WINDOWS:
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kwargs)
