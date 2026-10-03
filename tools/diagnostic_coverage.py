"""Combien des diagnostics que le code PEUT émettre sont déclenchés par les tests ?

Un message que personne n'a jamais vu sortir n'est pas vérifié : il peut citer le mauvais fichier,
être en français, ou ne jamais se produire. Cet outil le mesure.

- **Statique** : `enumerate_sites` repère dans le code (AST) chaque appel qui fabrique un diagnostic
  (`ctx.warn/error`, `build_error/warning`, `CheckError`). Chaque site a une clé stable — fichier,
  fonction, empreinte du message — qui survit à un décalage de lignes.
- **Dynamique** : `Recorder` note, pendant un run de tests, la ligne qui construit chaque
  `ValidationMessage` / `CheckError`.
- **Cliquet** : la référence `tools/diagnostic_coverage_baseline.json` dit quels sites étaient
  couverts au dernier relevé. À la fin d'un run COMPLET de `pytest`, `tests/conftest.py` AVERTIT — sans
  jamais échouer — d'un diagnostic couvert qui ne l'est plus, ou d'un nouveau diagnostic jamais déclenché.

Relever la référence (après avoir ajouté des tests, ou assumé qu'un site ne l'est plus) :

    DIAGNOSTIC_COVERAGE_UPDATE=1 python -m pytest tests --ignore=tests/native

Voir les sites jamais atteints :

    python tools/diagnostic_coverage.py            # lance pytest, imprime le rapport
"""
from __future__ import annotations

import ast
import collections
import itertools
import json
import os
import subprocess
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
EDITOR_DIR = REPO_DIR / "editor"
BASELINE = REPO_DIR / "tools" / "diagnostic_coverage_baseline.json"

# Un appel à l'une de ces fonctions fabrique un diagnostic quand l'un de ses arguments est un message.
EMITTERS = {"warn", "error", "_warn", "report", "build_error", "build_warning", "CheckError"}
# Hors périmètre : l'interface ne produit pas de diagnostics de build.
SKIPPED_DIRS = ("ui/", "plugins/", "project_starters/")
# Les fonctions par lesquelles passe la construction : la ligne qui compte est celle de leur appelant.
PASS_THROUGH = {"build_error", "build_warning", "warn", "error", "__init__", "report", "make", "_emit", "_warn"}


@dataclass(frozen=True)
class Site:
    file: str       # relatif à editor/
    function: str   # fonction englobante
    key: str        # clé stable : `fichier::fonction::empreinte`
    start: int
    end: int


def _message_of(call: ast.Call) -> str:
    """Le texte du message d'un appel (premier argument chaîne ou f-string), normalisé ; "" s'il est calculé."""
    for arg in call.args:
        if isinstance(arg, ast.JoinedStr) or (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            return ast.unparse(arg)
    return ""


def enumerate_sites(editor_dir: Path = EDITOR_DIR) -> list[Site]:
    sites: list[Site] = []
    for path in sorted(editor_dir.rglob("*.py")):
        rel = path.relative_to(editor_dir).as_posix()
        if rel.startswith(SKIPPED_DIRS) or "__pycache__" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        functions = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        seen: collections.Counter = collections.Counter()
        for node in sorted((n for n in ast.walk(tree) if isinstance(n, ast.Call)),
                           key=lambda n: (n.lineno, n.col_offset)):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name not in EMITTERS:
                continue
            message = _message_of(node)
            if not (message or name in ("CheckError", "build_error", "build_warning")):
                continue
            function = max((fn for fn in functions if fn[0] <= node.lineno <= fn[1]),
                           key=lambda fn: fn[0], default=(0, 0, "<module>"))[2]
            if function in PASS_THROUGH:
                continue        # un conduit : ses APPELANTS sont les sites, pas l'appel qui le traverse
            base = f"{rel}::{function}::{zlib.crc32((message or name).encode('utf-8')):08x}"
            seen[base] += 1
            key = base if seen[base] == 1 else f"{base}#{seen[base]}"
            sites.append(Site(rel, function, key, node.lineno, node.end_lineno))
    return sites


class Recorder:
    """Note les lignes qui construisent un diagnostic. S'installe une fois, sans effet sur le comportement."""

    def __init__(self):
        self.hits: set[tuple[str, int]] = set()
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        import core.validator as validator
        import scripting.checker as checker
        for cls in (validator.ValidationMessage, checker.CheckError):
            cls.__init__ = self._wrap(cls.__init__)
        self._installed = True

    def _wrap(self, original):
        recorder = self

        def init(this, *args, **kwargs):
            recorder._record()
            original(this, *args, **kwargs)
        return init

    def _record(self) -> None:
        frame = sys._getframe(2)
        while frame is not None and frame.f_code.co_name in PASS_THROUGH:
            frame = frame.f_back
        if frame is None:
            return
        path = Path(os.path.normpath(frame.f_code.co_filename))
        try:
            rel = path.relative_to(EDITOR_DIR).as_posix()
        except ValueError:
            return
        self.hits.add((rel, frame.f_lineno))

    def covered(self, sites: list[Site]) -> set[str]:
        by_file = collections.defaultdict(list)
        for s in sites:
            by_file[s.file].append(s)
        return {s.key for file, line in self.hits for s in by_file.get(file, ())
                if s.start <= line <= s.end}


@dataclass
class Report:
    total: int
    covered: set[str]
    lost: list[str]        # couverts à la référence, non couverts maintenant
    new_unhit: list[str]   # absents de la référence et non couverts

    @property
    def ratio(self) -> float:
        return len(self.covered) / self.total if self.total else 1.0


def load_baseline(path: Path = BASELINE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # tolerated: sans référence, il n'y a rien à comparer
        return {}


def compare(sites: list[Site], covered: set[str], baseline: dict) -> Report:
    known = baseline.get("sites", {})
    keys = {s.key for s in sites}
    lost = sorted(k for k, was in known.items() if was and k in keys and k not in covered)
    new_unhit = sorted(k for k in keys if k not in known and k not in covered)
    return Report(len(keys), covered & keys, lost, new_unhit)


def write_baseline(sites: list[Site], covered: set[str], collected: int, path: Path = BASELINE) -> None:
    payload = {
        "collected": collected,
        "sites": {s.key: (s.key in covered) for s in sorted(sites, key=lambda s: s.key)},
    }
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def summary_lines(report: Report, baseline: dict) -> list[str]:
    was = sum(1 for v in baseline.get("sites", {}).values() if v)
    lines = [f"Diagnostic coverage: {len(report.covered)}/{report.total} sites exercised "
             f"({report.ratio:.0%}); reference: {was}/{len(baseline.get('sites', {}))}."]
    if report.lost:
        lines.append(f"WARNING: {len(report.lost)} diagnostic(s) exercised at the reference are no longer:")
        lines += [f"    {k}" for k in report.lost[:15]]
    if report.new_unhit:
        lines.append(f"WARNING: {len(report.new_unhit)} new diagnostic(s) never exercised by any test:")
        lines += [f"    {k}" for k in report.new_unhit[:15]]
    return lines


def main() -> int:
    """Lance la suite avec le relevé activé, puis liste les sites jamais atteints."""
    out = REPO_DIR / "tools" / ".diagnostic_hits.json"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", DIAGNOSTIC_COVERAGE_OUT=str(out))
    cmd = [sys.executable, "-X", "utf8", "-m", "pytest", "tests", "--ignore=tests/native",
           "--ignore=tests/ui", "-p", "no:cacheprovider", "-q"]
    subprocess.run(cmd, cwd=REPO_DIR, env=env)
    if not out.exists():
        print("No hits were recorded.")
        return 1
    hits = {tuple(h) for h in json.loads(out.read_text(encoding="utf-8"))}
    out.unlink()
    recorder = Recorder()
    recorder.hits = hits
    sites = enumerate_sites()
    covered = recorder.covered(sites)
    never = [s for s in sites if s.key not in covered]
    print(f"\n{len(covered)}/{len(sites)} sites exercised; {len(never)} never reached:\n")
    for file, group in itertools.groupby(sorted(never, key=lambda s: (s.file, s.start)),
                                         key=lambda s: s.file):
        group = list(group)
        print(f"{file} ({len(group)})")
        for s in group:
            print(f"    {s.start:5}  {s.function}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
