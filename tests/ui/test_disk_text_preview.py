"""Text previews handle real encodings, structured data and read-only UI."""
import json

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QPushButton

from core import disk_tree
from ui.common.disk_preview import DiskPreviewPanel, resource_preview


def _preview(path, render=True):
    return resource_preview(None, disk_tree.DiskNode(path.name, path, disk_tree.UNSUPPORTED), render)


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'utf-32', 'cp1252'])
def test_encodings_and_crlf_are_read_without_modifying_file(qapp, tmp_path, encoding):
    path = tmp_path / 'dialogue.txt'
    original = 'Bonjour, été !\r\nÀ bientôt.\r\n'.encode(encoding)
    path.write_bytes(original)
    result = _preview(path)
    assert result.text == 'Bonjour, été !\r\nÀ bientôt.\r\n'
    assert any(value == 'CRLF' for _, value in result.metadata)
    assert path.read_bytes() == original


def test_lua_behavior_is_inspected_without_execution(qapp, tmp_path):
    path = tmp_path / 'behavior.lua'
    path.write_text('-- @behavior\nerror("do not execute")\n', encoding='utf-8')
    result = _preview(path)
    assert result.text.startswith('-- @behavior')
    assert any('Behavior' in value for _, value in result.metadata)
    assert result.image.isNull()
    hover = _preview(path, False)
    assert hover.lines and hover.text is None and not hover.metadata


def test_table_schema_and_text_variable_counts(qapp, tmp_path):
    path = tmp_path / 'items.table'
    path.write_text(json.dumps({'columns': [{'name': 'damage', 'type': 'int'}],
                                'rows': [{'damage': 4}, {'damage': 8}]}), encoding='utf-8')
    result = _preview(path)
    assert ('damage', 'int') in result.metadata
    assert any(line.endswith(': 2') for line in result.lines)
    path = tmp_path / 'variables.json'
    path.write_text('{"globals": [{"name": "score"}], "constants": []}', encoding='utf-8')
    assert any(line.endswith(': 1') for line in _preview(path).lines)


def test_invalid_json_still_shows_raw_content(qapp, tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{\n "broken":\n}', encoding='utf-8')
    result = _preview(path)
    assert result.text == path.read_bytes().decode('utf-8')
    assert result.note


def test_csv_quoted_newline_counts_records_not_physical_lines(qapp, tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('name,description\nAlice,"first\nsecond"\nBob,other\n', encoding='utf-8')
    result = _preview(path)
    assert any(line.endswith(': 2') for line in result.lines)
    assert any(value == 'name, description' for _, value in result.metadata)


def test_large_utf8_excerpt_and_binary_and_empty_files(qapp, tmp_path):
    path = tmp_path / 'huge.txt'
    path.write_bytes(('a' + 'é' * 300_000).encode('utf-8'))
    result = _preview(path)
    assert result.text.startswith('aéé')
    assert '\ufffd' not in result.text
    assert len(result.text.encode('utf-8')) <= 512 * 1024
    assert result.note
    path.write_bytes(b'not\x00text')
    assert _preview(path).text is None
    assert _preview(path).note
    path.write_bytes(b'')
    assert _preview(path).text == ''
    path.unlink()
    assert _preview(path).note


def test_text_dialog_is_read_only_and_supports_wrap_zoom_and_metadata(qapp, tmp_path):
    path = tmp_path / 'example.lua'
    source = 'local message = "<b>literal text</b>"\nreturn message\n'
    path.write_text(source, encoding='utf-8')
    panel = DiskPreviewPanel()
    panel.show_preview(path.name, _preview(path))
    assert panel._text.toPlainText() == source
    assert panel._image.isHidden()
    assert panel._enlarge.isEnabled()
    observed = {}

    def inspect():
        dialog = panel.findChild(QDialog)
        editor = dialog.findChild(QPlainTextEdit, 'diskPreviewText')
        observed['read_only'] = editor.isReadOnly()
        observed['text'] = editor.toPlainText()
        observed['size_before'] = editor.font().pointSizeF()
        next(button for button in dialog.findChildren(QPushButton) if button.text() == '+').click()
        observed['size_after'] = editor.font().pointSizeF()
        # First toolbar button toggles wrapping for text, instead of fitting an image.
        dialog.findChildren(QPushButton)[0].click()
        observed['wrap'] = editor.lineWrapMode()
        dialog.accept()

    QTimer.singleShot(0, inspect)
    panel._enlarge.click()
    assert observed['read_only']
    assert observed['text'] == source
    assert observed['size_after'] > observed['size_before']
    assert observed['wrap'] == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert path.read_text(encoding='utf-8') == source
    panel.show_preview('empty.txt', _preview(tmp_path / 'missing.txt'))
    assert panel._text.toPlainText() == ''
    assert not panel._enlarge.isEnabled()
    panel.close()


def test_preview_panel_remembers_collapsed_state_and_shows_empty_hint(qapp, tmp_path, monkeypatch):
    from core import interface_preferences
    monkeypatch.setattr(interface_preferences, 'CONFIG_FILE', tmp_path / 'interface.json')
    monkeypatch.setattr(interface_preferences, '_cache', None)
    panel = DiskPreviewPanel()
    assert not panel._empty.isHidden() and panel._body.isHidden()
    panel._chevron.click()
    assert DiskPreviewPanel()._collapsed
    panel._chevron.click()
    assert not DiskPreviewPanel()._collapsed
