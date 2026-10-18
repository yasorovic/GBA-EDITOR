"""Bounded, read-only inspection of textual Disk files. Never executes code."""
from __future__ import annotations

import codecs
import csv
import io
import json

from core.lua_scripts import BEHAVIOR_MARKER
from core.models import asset_extensions as ext
from ui.common.labels import label


_JSON_EXTENSIONS = {'.json', ext.TABLE, ext.SCENE, ext.PREFAB, ext.LAYOUT,
                    ext.MUSIC_BOX, ext.JINGLE_BOX, ext.SOUND_BOX, ext.FONT_ASSET}
_FORMATS = {'.lua': 'Lua', '.c': 'C', '.h': 'C header', '.txt': 'Text',
            '.md': 'Markdown', '.csv': 'CSV', '.tsv': 'TSV',
            **{suffix: 'JSON' for suffix in _JSON_EXTENSIONS}}
_MAX_BYTES = 512 * 1024


def supports_text(path):
    return path.suffix.lower() in _FORMATS


def read_text_preview(node, result, render):
    """Fill the shared preview object; counts describe only the excerpt if capped."""
    suffix = node.path.suffix.lower()
    try:
        with node.path.open('rb') as handle:
            data = handle.read(_MAX_BYTES + 1)
        truncated = len(data) > _MAX_BYTES
        data = data[:_MAX_BYTES]
        if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = 'utf-32'
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = 'utf-16'
        else:
            encoding = 'utf-8-sig'
        try:
            text = codecs.getincrementaldecoder(encoding)().decode(data, final=not truncated)
        except UnicodeDecodeError:
            # Legacy Windows text remains readable; the detected fallback is explicit.
            encoding = 'cp1252'
            text = data.decode(encoding, errors='replace')
        if any(ord(char) < 32 and char not in '\t\n\r\f' for char in text):
            result.note = label('disk.text_binary')
            return
        lines = text.splitlines()
        result.lines.extend([_FORMATS[suffix], label('disk.text_counts', lines=len(lines), chars=len(text))])
        metadata = [(label('disk.text_encoding'), encoding.upper().replace('-SIG', '')),
                    (label('disk.text_line_endings'), 'CRLF' if '\r\n' in text else ('CR' if '\r' in text else 'LF'))]
        if not lines:
            metadata[-1] = (label('disk.text_line_endings'), '—')
        if suffix == '.lua':
            metadata.append((label('disk.text_role'), label(
                'disk.text_behavior' if lines and lines[0].strip() == BEHAVIOR_MARKER else 'disk.text_script')))
        if truncated:
            result.note = label('disk.text_truncated', kib=_MAX_BYTES // 1024)
        elif suffix in _JSON_EXTENSIONS:
            try:
                value = json.loads(text)
                if isinstance(value, dict):
                    metadata.append((label('disk.text_json_keys'), ', '.join(list(value)[:40])))
                    for key, title in [('rows', 'disk.text_rows'), ('columns', 'disk.text_columns'),
                                       ('texts', 'disk.text_entries'), ('globals', 'disk.text_globals'),
                                       ('constants', 'disk.text_constants')]:
                        if isinstance(value.get(key), (list, dict)):
                            count = len(value[key])
                            metadata.append((label(title), str(count)))
                            result.lines.append(f'{label(title)}: {count}')
                    if suffix == ext.TABLE and isinstance(value.get('columns'), list):
                        for column in value['columns'][:100]:
                            if isinstance(column, dict):
                                metadata.append((str(column.get('name', '')), str(column.get('type', ''))))
                elif isinstance(value, list):
                    result.lines.append(label('disk.text_list_entries', count=len(value)))
                metadata.append((label('disk.text_json_status'), label('disk.text_valid')))
            except (ValueError, RecursionError) as error:
                result.note = (label('disk.text_json_error', line=error.lineno, column=error.colno)
                               if isinstance(error, json.JSONDecodeError) else label('disk.text_json_unreadable'))
        elif suffix in ('.csv', '.tsv') and text:
            try:
                reader = csv.reader(io.StringIO(text, newline=''), delimiter='\t' if suffix == '.tsv' else ',')
                header = next(reader, [])
                row_count = sum(1 for row in reader if row)
                result.lines.extend([f'{label("disk.text_columns")}: {len(header)}',
                                     f'{label("disk.text_rows")}: {row_count}'])
                metadata.append((label('disk.text_headers'), ', '.join(header)))
                metadata.append((label('disk.text_header_note'), label('disk.text_first_row_header')))
            except csv.Error:
                result.note = label('disk.text_csv_unreadable')
        if render:
            result.text = text
            result.metadata.extend(metadata)
    except OSError:
        result.note = label('disk.preview_unavailable')
