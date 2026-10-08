"""Validate editor catalogues and literal text at known UI entry points.

No Qt imports: this check can run before dependencies or the editor are loaded.
Exceptions live in ui_text_exceptions.json with a file, exact text and reason.
This is a targeted check, not a general Python data-flow analyser.
"""
from __future__ import annotations

import ast
import json
import re
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tables deliberately store keys until a widget is built. Audit these as well
# as calls, otherwise a new tool could silently put prose back into a table.
KEY_TABLES = {
    "canvas_toolbar.py": {"_MAIN_TOOLS": 2, "_COLLISION_MODES": 2,
                          "_INPAINT_MODES": 2, "_UI_MODES": 2},
    "bg_layer_row.py": {"_BLEND_TIPS_SIMPLE": None, "_BLEND_TIPS_FULL": None},
    "camera_inspector.py": {"_MODES": 1, "_NO_TARGET": None, "_DEFAULT_CAMERA": None},
    "ui_node_inspector.py": {"_ANCHORS": 1, "_TARGETS": 1},
    "project_inspector.py": {"TRANSITION_LABELS": 1, "_COUNTER_KEYS": None},
    "project_settings_dialog.py": {"_CATEGORY_KEYS": None},
    "rom_budget_bar.py": {"_CATEGORY_KEYS": None},
    "ui_inspector.py": {"_POS_WORD": None},
    "sprite_finder_panel.py": {"_DIR_LABELS": None},
    "font_inspector.py": {"_ADV_ORIGIN": None},
    "languages_card.py": {"_SAME": None},
    "pickers.py": {"_NONE_LABEL": None, "_UI_BANK_AUTO_LABEL": None,
                   "_FONT_AUTO_LABEL_BASE": None},
    "asset_kinds.py": {"_BACKGROUND_LABEL_KEYS": None},
}


def table_references(tree, filename):
    tables = KEY_TABLES.get(filename, {})
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name) or target.id not in tables:
                    continue
                value, start = node.value, tables[target.id]
                if isinstance(value, ast.Dict):
                    yield from value.values
                elif start is not None and isinstance(value, (ast.List, ast.Tuple)):
                    for row in value.elts:
                        if isinstance(row, (ast.List, ast.Tuple)):
                            yield from row.elts[start:]
                elif isinstance(value, ast.Constant):
                    yield value
        elif isinstance(node, ast.keyword) and node.arg in {"label_key", "add_tooltip_key", "empty_text_key"}:
            if isinstance(node.value, ast.Constant) and node.value.value:
                yield node.value


def text_calls(tree):
    """Resolve catalogue imports, including aliases, rather than any .text()."""
    names, modules = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in {"ui.common.labels", "ui.common.notice"}:
                for alias in node.names:
                    if alias.name in {"label", "text", "tip"}:
                        names[alias.asname or alias.name] = ("labels" if alias.name == "label" else "notices", alias.name)
            elif node.module == "ui.common":
                for alias in node.names:
                    if alias.name in {"labels", "notice"}:
                        modules[alias.asname or alias.name] = alias.name
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name) and call.func.id in names:
            yield call, *names[call.func.id]
        elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            module = modules.get(call.func.value.id)
            if module == "labels" and call.func.attr == "label":
                yield call, "labels", "label"
            elif module == "notice" and call.func.attr in {"text", "tip"}:
                yield call, "notices", call.func.attr

# Only arguments used for display; never combo userData or persisted identifiers.
FIRST = {
    "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox",
    "setText", "setToolTip", "setStatusTip", "setWindowTitle",
    "setPlaceholderText", "setTitle", "setInformativeText", "setDetailedText",
    "addItem", "addItems", "setHeaderLabels", "setHorizontalHeaderLabels",
    "section", "muted", "hint", "btn", "btn_accent", "btn_ghost", "btn_add",
    "CollapsibleCard", "QTableWidgetItem",
    "btn_danger", "pair", "row", "field", "checkbox", "AssetFinder",
    "set_add_tooltip", "set_empty_text",
    "title_panel", "title_group", "finder_bar", "section_bar", "title_section",
    "empty_state", "btn_search", "btn_reveal", "search_box", "combobox",
    "_category_title", "_row", "FinderSection", "QListWidgetItem", "CanvasTopBar",
    "_add_empty_row", "_add_section_header",
}


def display_args(call):
    name = getattr(call.func, "attr", getattr(call.func, "id", ""))
    owner = ast.unparse(call.func.value) if isinstance(call.func, ast.Attribute) else ""
    positions = [0] if name in FIRST else []
    if name in {"addTab", "setTabText", "setItemText"}:
        positions = [1]
    if name == "add_action":
        positions = [1]
    if name == "checkbox_row":
        positions = [0, 1]
    if name == "showText" and owner == "QToolTip":
        positions = [1]
    if owner == "QColorDialog" and name == "getColor":
        positions = [2]
    if name == "add_toggle":
        positions = [1]
    if owner == "QMessageBox" and name in {"warning", "critical", "information", "question"}:
        positions = [1, 2]
    if owner in {"QFileDialog", "QInputDialog"}:
        positions = [1, 2] if owner == "QInputDialog" else [1, 3]
    if name == "addAction":
        positions = [0] if call.args and isinstance(call.args[0], (ast.Constant, ast.JoinedStr)) else [1]
    for pos in positions:
        if pos < len(call.args):
            yield call.args[pos]
    for kw in call.keywords:
        if kw.arg in {"tooltip", "placeholder", "title", "hint", "add_label", "new_label"}:
            yield kw.value


def literal_texts(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if any(c.isalpha() for c in node.value):
            yield node, node.value
    elif isinstance(node, ast.JoinedStr):
        # Treat an interpolated phrase as a whole, never translate its fragments.
        if any(isinstance(v, ast.Constant) and any(c.isalpha() for c in v.value)
               for v in node.values):
            yield node, ast.unparse(node)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for child in node.elts:
            yield from literal_texts(child)
    elif isinstance(node, ast.IfExp):
        yield from literal_texts(node.body)
        yield from literal_texts(node.orelse)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        yield from literal_texts(node.left)
        yield from literal_texts(node.right)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        yield from literal_texts(node.func.value)
    # Calls already represent a formatter, a catalogue or a data source.


def inline_texts(tree):
    seen = set()
    for call in ast.walk(tree):
        if isinstance(call, ast.Call):
            for arg in display_args(call):
                for node, value in literal_texts(arg):
                    loc = (node.lineno, node.col_offset)
                    if loc not in seen:
                        seen.add(loc)
                        yield node, value


def parameters(text):
    fields = set()
    for _, field, spec, conversion in string.Formatter().parse(text):
        if field is not None:
            if not field.isidentifier():
                raise ValueError(f"expected named parameter, got {field!r}")
            if conversion not in (None, "s", "r", "a"):
                raise ValueError(f"invalid conversion {conversion!r}")
            fields.add(field)
            fields.update(parameters(spec))
    return fields


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def validate_entries(data, name, *, translated=False):
    errors, signatures = [], {}
    if not isinstance(data, dict) or set(data) - {name, "lang"} or not isinstance(data.get(name), dict):
        return [f"expected an object containing only {name!r}"], signatures
    if "lang" in data and not isinstance(data["lang"], str):
        errors.append("lang must be a string")
    for key, entry in data[name].items():
        try:
            if not re.fullmatch(r"[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+", key):
                raise ValueError("invalid dotted key")
            if not isinstance(entry, dict):
                raise ValueError("expected an entry object")
            forms = set(entry) & {"text", "singular", "plural"}
            if forms not in ({"text"}, {"singular", "plural"}):
                raise ValueError("expected text OR both singular/plural")
            allowed = forms | ({"tone", "code"} if name == "notices" and not translated else set())
            if set(entry) - allowed:
                raise ValueError(f"unknown fields: {sorted(set(entry) - allowed)}")
            if name == "notices" and not translated:
                if entry.get("tone") not in {"info", "accent", "build", "render"}:
                    raise ValueError("missing or invalid tone")
                if "code" in entry and not isinstance(entry["code"], str):
                    raise ValueError("code must be a string")
            signature = {}
            for form in sorted(forms):
                if not isinstance(entry[form], str) or not entry[form].strip():
                    raise ValueError(f"{form} must be nonempty text")
                signature[form] = parameters(entry[form])
            signatures[key] = signature
        except ValueError as exc:
            errors.append(f"{key}: {exc}")
    return errors, signatures


def check(root=ROOT):
    errors = []
    signatures = {}
    for name in ("labels", "notices"):
        directory = root / "editor/ui/common" / name
        master = directory / f"{name}.json"
        try:
            problems, source = validate_entries(read_json(master), name)
            errors.extend(f"{master.name}: {p}" for p in problems)
            signatures[name] = source
            for side in sorted(directory.glob(f"{name}_*.json")):
                problems, target = validate_entries(read_json(side), name, translated=True)
                errors.extend(f"{side.name}: {p}" for p in problems)
                for key, forms in target.items():
                    if key not in source:
                        errors.append(f"{side.name}: unknown key {key}")
                    elif forms != source[key]:
                        errors.append(f"{side.name}: {key}: forms/parameters differ from source")
        except (ValueError, OSError) as exc:
            errors.append(f"{master}: {exc}")

    exemptions = read_json(root / "tools/ui_text_exceptions.json")
    allowed = {(e["file"], e["text"]): e["reason"] for e in exemptions}
    used = set()
    for relative, reason in allowed.items():
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"exception {relative}: missing reason")
    paths = sorted((root / "editor/ui").rglob("*.py"))
    paths += [root / "editor/main.py", root / "editor/window.py"]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(root).as_posix()
        for node, value in inline_texts(tree):
            identity = (rel, value)
            if identity in allowed:
                used.add(identity)
            else:
                errors.append(f"{rel}:{node.lineno}: inline UI text: {value!r}")
        for ref in table_references(tree, path.name):
            if isinstance(ref, ast.Constant) and ref.value not in signatures.get("labels", {}):
                errors.append(f"{rel}:{ref.lineno}: unknown label key in table: {ref.value!r}")
        # Immediate text calls must supply their parameters. Deferred notices
        # (note()/notice() then show_text()) are not inferred across methods.
        for call, catalogue, function in text_calls(tree):
            if not call.args or not isinstance(call.args[0], ast.Constant):
                continue
            key = call.args[0].value
            forms = signatures.get(catalogue, {}).get(key)
            if forms is None:
                errors.append(f"{rel}:{call.lineno}: unknown {catalogue} key {key!r}")
            elif not any(k.arg is None for k in call.keywords):
                required = set().union(*forms.values()) | ({"n"} if "singular" in forms else set())
                provided = {k.arg for k in call.keywords}
                if function == "tip":
                    provided -= {"layout"}
                missing = required - provided
                if missing:
                    errors.append(f"{rel}:{call.lineno}: {key}: missing parameters {sorted(missing)}")
                extra = provided - required
                if extra:
                    errors.append(f"{rel}:{call.lineno}: {key}: unused parameters {sorted(extra)}")
    for stale in allowed.keys() - used:
        errors.append(f"unused inline exception: {stale}")
    return errors


if __name__ == "__main__":
    problems = check()
    print("\n".join(problems) if problems else "UI text checks passed")
    raise SystemExit(bool(problems))
