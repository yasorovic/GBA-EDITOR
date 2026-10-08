"""The extraction guard runs without importing Qt or application modules."""
import ast
import json
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_ui_text", ROOT / "tools/check_ui_text.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


@pytest.mark.parametrize("entry", [
    {"text": "Hi", "singular": "Hi", "plural": "Hi"},
    {"singular": "One"}, {"text": ""}, {"text": 2},
    {"text": "{missing"}, {"text": "{}"}, {"text": "{user.name}"},
    {"text": "Hi", "typo": True},
])
def test_rejects_invalid_entry(entry):
    errors, _ = checks.validate_entries({"labels": {"test.message": entry}}, "labels")
    assert errors


def test_nested_format_parameters_and_escaped_braces():
    assert checks.parameters("{{raw}} {amount:{width}.{precision}f}") == {"amount", "width", "precision"}


def test_translation_cannot_override_presentation():
    errors, _ = checks.validate_entries(
        {"notices": {"test.message": {"text": "Hi", "tone": "render"}}},
        "notices", translated=True)
    assert errors


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"labels": {"test.key": {}, "test.key": {}}}')
    with pytest.raises(ValueError, match="duplicate key"):
        checks.read_json(path)


def test_targeted_extraction_keeps_user_data_and_technical_calls():
    tree = ast.parse('''
combo.addItem(label("choice.caption"), "stable-id")
widget.setStyleSheet("color: red")
button.setToolTip("Click here")
dialog.setWindowTitle(f"Delete {name}?")
combo.addItems(["First", "Second"])
''')
    found = [value for _, value in checks.inline_texts(tree)]
    assert len(found) == 4
    assert "Click here" in found
    assert "stable-id" not in found


def test_repository_ui_text_contract():
    assert checks.check(ROOT) == []


def test_import_aliases_and_notice_parameters_are_recognised():
    tree = ast.parse('''
from ui.common.labels import label as caption
from ui.common import notice as messages
caption("test.caption", name=value)
messages.text("test.notice", n=2)
other.text("unrelated")
''')
    assert [(name, function) for _, name, function in checks.text_calls(tree)] == [
        ("labels", "label"), ("notices", "text")]


def test_translation_shape_and_call_arguments_are_checked(tmp_path):
    for name in ("labels", "notices"):
        directory = tmp_path / "editor/ui/common" / name
        directory.mkdir(parents=True)
        master = {"test.message": {"text": "Hello {name}"}} if name == "labels" else {}
        (directory / f"{name}.json").write_text(json.dumps({name: master}))
    side = tmp_path / "editor/ui/common/labels/labels_fr.json"
    side.write_text(json.dumps({"labels": {"test.message": {"text": "Salut {wrong}"}}}))
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/ui_text_exceptions.json").write_text("[]")
    (tmp_path / "editor/main.py").write_text('from ui.common.labels import label\nlabel("test.message", typo=1)')
    (tmp_path / "editor/window.py").write_text("")
    errors = checks.check(tmp_path)
    assert any("parameters differ" in e for e in errors)
    assert any("missing parameters ['name']" in e for e in errors)
    assert any("unused parameters ['typo']" in e for e in errors)


def test_raw_prose_in_display_table_is_detected():
    tree = ast.parse('_MODES = [(0, "Unextracted mode")]')
    assert [n.value for n in checks.table_references(tree, "camera_inspector.py")] == ["Unextracted mode"]
