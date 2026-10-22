"""
tools/ci_local.py — rejouer en local ce que `tests.yml` rejoue sur GitHub.

    python tools/ci_local.py             # ruff + architecture + pytest ciblé
    python tools/ci_local.py --slow      # + les tests `-m slow` (quelques minutes)
    python tools/ci_local.py --linux     # le même contrôle, dans WSL (Ubuntu)
    python tools/ci_local.py --all-tests # pytest sur toute la suite, pas seulement le ciblé

Les étapes sont celles de `.github/workflows/tests.yml`, dans le même ordre :
elles s'arrêtent à la première qui échoue. Ce que ce script ne couvre PAS : les jobs
de `release.yml` qui dépendent du runner (installation de devkitPro sous Windows,
Nuitka, NSIS, AppImage) — pour ceux-là, `workflow_dispatch` reste le bon outil.

Le pytest « ciblé » joue les tests modifiés depuis `origin/main` (commits, arbre de
travail, fichiers non suivis), plus les tests qui nomment un module modifié. Il ne
remplace pas la suite complète : `--all-tests` la lance.

`--linux` copie l'arbre dans le disque Linux de WSL (`~/gba-ci/src`) avant de lancer :
le disque Windows monté (`/mnt/e`) ignore la casse des noms de fichiers, donc une
erreur de casse n'y apparaît pas. Les paquets système Qt se préparent une fois
(la commande `apt` est affichée si une bibliothèque manque).
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_REF = "origin/main"
WSL_DISTRO = "Ubuntu-24.04"
WSL_HOME_DIR = "gba-ci"          # ~/gba-ci/{src,venv}

QT_APT_PACKAGES = "libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libpulse0"

# Copie vers WSL : ce qui est propre à la machine ou régénéré ne part pas.
WSL_COPY_EXCLUDES = (".git", ".venv*", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "build-out")


def _git_lines(*arguments: str) -> list[str]:
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files() -> list[str]:
    """Fichiers modifiés depuis `origin/main` : commits, arbre de travail, non suivis."""
    merge_base = _git_lines("merge-base", BASE_REF, "HEAD")
    since = merge_base[0] if merge_base else "HEAD"
    names = set(_git_lines("diff", "--name-only", since))
    names.update(_git_lines("ls-files", "--others", "--exclude-standard"))
    return sorted(name for name in names if (ROOT / name).is_file())


def targeted_tests(changed: list[str]) -> list[str]:
    """Les tests modifiés, plus ceux qui nomment le module d'un fichier Python modifié."""
    tests = {name for name in changed if name.startswith("tests/") and name.endswith(".py")}
    module_stems = {
        Path(name).stem for name in changed
        if name.endswith(".py") and not name.startswith("tests/") and Path(name).stem != "__init__"
    }
    if module_stems:
        pattern = re.compile(r"\b(" + "|".join(re.escape(stem) for stem in sorted(module_stems)) + r")\b")
        for test_file in (ROOT / "tests").rglob("test_*.py"):
            if pattern.search(test_file.read_text(encoding="utf-8", errors="replace")):
                tests.add(test_file.relative_to(ROOT).as_posix())
    return sorted(tests)


def run_step(title: str, command: list[str], env: dict[str, str]) -> bool:
    print(f"\n── {title}\n   $ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, env=env).returncode == 0


def run_local(arguments: argparse.Namespace) -> int:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    if arguments.native_required:
        env["GBA_TESTS_REQUIRE_NATIVE"] = "1"
    python = sys.executable

    steps: list[tuple[str, list[str]]] = [
        ("Ruff (erreurs certaines)", [python, "-m", "ruff", "check", "editor", "tools", "tests"]),
        ("Contrôle d'architecture", [python, "tools/check_architecture.py", "--fresh"]),
    ]
    if arguments.all_tests:
        steps.append(("Tests (toute la suite)", [python, "-m", "pytest", "tests", "-q", "-rs"]))
    else:
        targets = targeted_tests(changed_files())
        if targets:
            steps.append((f"Tests ciblés ({len(targets)} fichiers)", [python, "-m", "pytest", *targets, "-q", "-rs"]))
        else:
            print("Aucun test ciblé : aucun fichier modifié depuis", BASE_REF, "(ou aucun test ne le nomme).")
    if arguments.slow:
        steps.append(("Tests lents", [python, "-m", "pytest", "tests", "-m", "slow", "-q", "-rs"]))

    for title, command in steps:
        if not run_step(title, command, env):
            print(f"\n✗ Échec : {title}")
            return 1
    print("\n✓ Tout est vert.")
    return 0


def _wsl(script: str) -> int:
    return subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "bash", "-lc", script]).returncode


def run_linux(arguments: argparse.Namespace) -> int:
    """Copie l'arbre dans WSL, prépare le venv Linux au besoin, relance ce script là-bas."""
    drive, rest = ROOT.drive, ROOT.as_posix()[len(ROOT.drive):]
    source_in_wsl = f"/mnt/{drive[0].lower()}{rest}"
    excludes = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in WSL_COPY_EXCLUDES)
    forwarded = [flag for flag, on in (("--slow", arguments.slow), ("--all-tests", arguments.all_tests)) if on]

    script = f"""
set -e
base="$HOME/{WSL_HOME_DIR}"
mkdir -p "$base"
if [ ! -x "$base/venv/bin/python" ]; then
  python3 -m venv "$base/venv" || {{ echo "python3-venv manquant : sudo apt install python3-venv"; exit 1; }}
fi
# Dépendances : réinstallées seulement quand la liste a changé.
stamp="$(cat {shlex.quote(source_in_wsl)}/docs/development/requirements.txt {shlex.quote(source_in_wsl)}/docs/development/requirements-dev.txt | md5sum | cut -d' ' -f1)"
if [ "$(cat "$base/requirements.stamp" 2>/dev/null)" != "$stamp" ]; then
  "$base/venv/bin/pip" install --upgrade pip
  "$base/venv/bin/pip" install -r {shlex.quote(source_in_wsl)}/docs/development/requirements.txt -r {shlex.quote(source_in_wsl)}/docs/development/requirements-dev.txt
  echo "$stamp" > "$base/requirements.stamp"
fi
rm -rf "$base/src"; mkdir -p "$base/src"
tar -C {shlex.quote(source_in_wsl)} {excludes} -cf - . | tar -C "$base/src" -xf -
cd "$base/src"
# Le dépôt n'est pas copié : le « ciblé » ne sait pas ce qui a changé, donc toute la suite.
export QT_QPA_PLATFORM=offscreen GBA_TESTS_REQUIRE_NATIVE=1
"$base/venv/bin/python" tools/ci_local.py --in-wsl --all-tests {' '.join(forwarded)}
"""
    if "--all-tests" not in forwarded:
        print("Note : sous --linux, la suite complète tourne (le dépôt git n'est pas copié dans WSL).")
    code = _wsl(script)
    if code != 0:
        print(f"\nSi une bibliothèque Qt manque, dans WSL : sudo apt install -y --no-install-recommends {QT_APT_PACKAGES}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Rejoue localement les contrôles de tests.yml.")
    parser.add_argument("--slow", action="store_true", help="ajoute les tests `-m slow`")
    parser.add_argument("--linux", action="store_true", help="relance le tout dans WSL (Ubuntu)")
    parser.add_argument("--all-tests", action="store_true", help="toute la suite pytest, pas seulement le ciblé")
    parser.add_argument("--in-wsl", action="store_true", dest="native_required", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    return run_linux(arguments) if arguments.linux else run_local(arguments)


if __name__ == "__main__":
    sys.exit(main())
