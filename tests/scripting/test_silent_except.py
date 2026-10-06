"""Aucun `except` large ne se tait dans la chaîne de build (chantier « La fiabilité du
journal de build », tranche 1).

Un `except Exception: continue` fait disparaître une panne sans qu'aucune ligne du journal
n'existe pour la soupçonner : c'est ainsi que `local x = 1; ADFZ = 5` compilait « proprement ».
Un handler de `Exception`, nu, ou de `LuaParseError` doit donc :

- lever, ou émettre un diagnostic (`emit`, `warn`, `error`…) ; ou
- porter sur sa ligne `# tolerated: <raison>` — la raison dit QUI rapporte la panne à sa place.

Les handlers étroits (`OSError`, `ValueError`…) ne sont pas concernés : ils nomment ce qu'ils
attendent.
"""
from __future__ import annotations

import ast
from pathlib import Path

EDITOR = Path(__file__).resolve().parents[2] / "editor"
SCANNED = ("codegen", "scripting", "core/validator.py")
BROAD = {"Exception", "BaseException", "LuaParseError"}
REPORTING = {"emit", "_emit", "warn", "error", "_warn", "report", "log_current_exception", "print"}


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = {n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)}
    return bool(names & BROAD)


def _speaks(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            f = node.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in REPORTING:
                return True
            # `self.warnings.append(...)` / `errors.append(...)` : une liste de diagnostics
            if (isinstance(f, ast.Attribute) and f.attr == "append"
                    and ast.unparse(f.value).endswith(("warnings", "errors"))):
                return True
    return False


def _files():
    for entry in SCANNED:
        path = EDITOR / entry
        yield from ([path] if path.is_file() else sorted(path.rglob("*.py")))


def test_aucun_except_large_ne_se_tait():
    silent = []
    for path in _files():
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ExceptHandler) or not _is_broad(node):
                continue
            if _speaks(node) or "# tolerated:" in lines[node.lineno - 1]:
                continue
            silent.append(f"{path.relative_to(EDITOR)}:{node.lineno}")
    assert silent == [], (
        "except large muet — émettre un diagnostic, ou ajouter `# tolerated: <raison>` "
        f"sur la ligne de l'except : {silent}")


def test_la_garde_voit_un_except_muet(tmp_path):
    """La garde elle-même : un `except Exception: continue` nu est vu, le même annoté ne l'est pas."""
    muet = ast.parse("try:\n    f()\nexcept Exception:\n    pass\n").body[0].handlers[0]
    parle = ast.parse("try:\n    f()\nexcept Exception:\n    emit('x')\n").body[0].handlers[0]
    etroit = ast.parse("try:\n    f()\nexcept OSError:\n    pass\n").body[0].handlers[0]
    assert _is_broad(muet) and not _speaks(muet)
    assert _is_broad(parle) and _speaks(parle)
    assert not _is_broad(etroit)
