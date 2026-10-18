"""
scripting/script_notes.py — Note libre utilisateur d'un script.

Convention : un bloc de commentaire Lua tout en tête de fichier, jamais
exécuté, jamais compilé — mimique les champs `notes` de Scene/Actor/Prefab
pour un objet qui n'a pas de sidecar JSON (un script est un simple fichier).

    --[[@note
    Texte libre sur une ou plusieurs lignes.
    ]]

Toujours la toute première chose du fichier (avant la table `exports`,
cf. scripting/exports_parser.py). read_note()/write_note() ne touchent que ce
bloc — le reste du script est préservé tel quel.
"""
from __future__ import annotations
import re
from core.resources.resource_store import atomic_write
from pathlib import Path
from typing import Optional

_NOTE_RE = re.compile(r'\A--\[\[@note\r?\n(.*?)\r?\n\]\]\r?\n?\r?\n?', re.DOTALL)


def note_block_span(text: str) -> Optional[tuple[int, int]]:
    """Span (start, end) du bloc @note s'il est présent en tête de fichier."""
    m = _NOTE_RE.match(text)
    return (m.start(), m.end()) if m else None


def read_note(lua_path: Path) -> str:
    if not lua_path or not lua_path.exists():
        return ""
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    m = _NOTE_RE.match(text)
    return m.group(1) if m else ""


def write_note(lua_path: Path, note: str) -> None:
    """Écrit (ou retire, si `note` est vide) le bloc @note en tête du fichier."""
    text = lua_path.read_text(encoding="utf-8", errors="ignore") if lua_path.exists() else ""
    span = note_block_span(text)
    note = note.strip("\n")
    block = f"--[[@note\n{note}\n]]\n\n" if note else ""
    if span:
        text = text[:span[0]] + block + text[span[1]:]
    else:
        text = block + text
    atomic_write(lua_path, text)
