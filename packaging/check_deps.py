#!/usr/bin/env python3
"""
Garde-fou dépendances — à lancer AVANT le build Nuitka.

Parcourt tous les .py de editor/ et runtime/, relève les imports de premier
niveau, retire la stdlib et les modules locaux, puis vérifie que tout le
reste est bien installé dans l'environnement courant. Sur une machine où
l'on vient de faire `.venv-build312/Scripts/python.exe -m pip install -r packaging/requirements.txt`, un import manquant
signifie donc : paquet absent de requirements.txt.

C'est le filet qui manquait pour la release 1 (luaparser était importé par
editor/scripting/ mais absent de requirements.txt : l'éditeur démarrait et
plantait au premier script Lua ouvert).

Usage :
    .venv-build312/Scripts/python.exe packaging/check_deps.py

Sortie : 0 si tout est couvert, 1 sinon (liste des modules manquants).

Note : la vérification est statique (AST). Elle attrape les `import x` en
dur, pas les imports dynamiques (importlib avec un nom calculé). Les seuls
imports dynamiques du projet sont les plugins, chargés depuis des fichiers
.py embarqués comme datas — hors périmètre ici.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["editor", "runtime"]


def local_top_level_names() -> set[str]:
    """
    Noms importables « localement ».

    editor/ est la racine du path à l'exécution (main.py l'insère dans
    sys.path, et c'est le dossier du script principal côté Nuitka) : ses
    sous-modules s'importent donc à plat — `from core...`, `from ui...`.
    Tout ce qui est directement sous editor/ est un nom local, au même
    titre que les dossiers de la racine du repo.
    """
    names = {p.stem for p in REPO_ROOT.iterdir()}
    names |= {p.stem for p in (REPO_ROOT / "editor").iterdir()}
    return {n for n in names if n and not n.startswith(".")}


def collect_imports() -> dict[str, set[str]]:
    """{module de premier niveau: {fichiers qui l'importent}}"""
    found: dict[str, set[str]] = {}
    for d in SCAN_DIRS:
        for path in (REPO_ROOT / d).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"!! illisible : {path.relative_to(REPO_ROOT)} — {exc}")
                continue
            rel = str(path.relative_to(REPO_ROOT))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        found.setdefault(alias.name.split(".")[0], set()).add(rel)
                elif isinstance(node, ast.ImportFrom):
                    # level > 0 = import relatif → forcément local
                    if node.level == 0 and node.module:
                        found.setdefault(node.module.split(".")[0], set()).add(rel)
    return found


def main() -> int:
    local = local_top_level_names()
    stdlib = sys.stdlib_module_names

    third_party = {
        name: files
        for name, files in collect_imports().items()
        if name not in local and name not in stdlib and not name.startswith("_")
    }

    missing: dict[str, set[str]] = {}
    for name, files in sorted(third_party.items()):
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            missing[name] = files
        else:
            print(f"  ok       {name}")

    if missing:
        print("\nDépendances manquantes (à ajouter à requirements.txt) :")
        for name, files in missing.items():
            sample = sorted(files)[:3]
            print(f"  MANQUANT {name}  ← {', '.join(sample)}"
                  f"{f' (+{len(files) - 3} autres)' if len(files) > 3 else ''}")
        return 1

    print(f"\n{len(third_party)} dépendances tierces, toutes installées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
