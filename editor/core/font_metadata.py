"""Métadonnées intrinsèques d'une fonte SFNT (TTF ou OTF), sans rasterisation.

Le lecteur reste volontairement petit : nom de famille, style, poids et
italique suffisent à composer les familles du projet. Les contours, la cmap et
le rendu restent du ressort de FontRasterizer.
"""
from __future__ import annotations

import struct
from pathlib import Path


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _decode_name(platform: int, encoding: int, raw: bytes) -> str:
    try:
        if platform in (0, 3):
            return raw.decode("utf-16-be").strip("\0 ")
        if platform == 1:
            return raw.decode("mac_roman").strip("\0 ")
        return raw.decode("latin-1").strip("\0 ")
    except UnicodeDecodeError:
        return ""


def _style_weight(style: str) -> int:
    """Poids de secours quand une vieille face ne porte pas de table OS/2."""
    folded = style.casefold().replace("-", " ")
    # Ordre important : « Extra Bold » contient aussi « Bold ».
    for token, weight in (
        ("thin", 100), ("hairline", 100), ("extra light", 200),
        ("ultra light", 200), ("light", 300), ("book", 400),
        ("medium", 500), ("semi bold", 600), ("demi bold", 600),
        ("extra bold", 800), ("ultra bold", 800), ("black", 900),
        ("heavy", 900), ("bold", 700),
    ):
        if token in folded:
            return weight
    return 400


def vector_font_metadata(path: Path) -> dict:
    """Lit les métadonnées de famille d'un TTF/OTF valide.

    Le nom typographique (IDs 16/17) prime sur les noms historiques (1/2) :
    c'est celui qu'emploient les gestionnaires de polices modernes pour grouper
    les faces d'une même famille.
    """
    data = path.read_bytes()
    if len(data) < 12 or data[:4] == b"ttcf":
        raise ValueError("TTC collection is not supported — import a single TTF or "
                         "OTF face.")
    count = _u16(data, 4)
    tables: dict[bytes, tuple[int, int]] = {}
    for i in range(count):
        pos = 12 + i * 16
        if pos + 16 > len(data):
            raise ValueError("incomplete SFNT table.")
        tag = data[pos:pos + 4]
        offset, length = _u32(data, pos + 8), _u32(data, pos + 12)
        if offset + length <= len(data):
            tables[tag] = (offset, length)
    if b"name" not in tables:
        raise ValueError("table de noms absente.")
    off, length = tables[b"name"]
    if length < 6:
        raise ValueError("table de noms invalide.")
    records, strings_off = _u16(data, off + 2), _u16(data, off + 4)
    names: dict[int, list[tuple[int, int, str]]] = {}
    for i in range(records):
        pos = off + 6 + i * 12
        if pos + 12 > off + length:
            break
        platform, encoding, _language, name_id, size, rel = struct.unpack_from(">HHHHHH", data, pos)
        start = off + strings_off + rel
        raw = data[start:start + size] if start + size <= len(data) else b""
        text = _decode_name(platform, encoding, raw)
        if text:
            names.setdefault(name_id, []).append((platform, encoding, text))

    def name_of(*ids: int) -> str:
        for name_id in ids:
            values = names.get(name_id, [])
            values.sort(key=lambda item: 0 if item[0] in (0, 3) else 1)
            if values:
                return values[0][2]
        return ""

    family, style = name_of(16, 1), name_of(17, 2)
    if not family:
        raise ValueError("family name is missing.")
    weight = _style_weight(style)
    italic = "italic" in style.lower() or "oblique" in style.lower()
    if b"OS/2" in tables:
        os2, os2_len = tables[b"OS/2"]
        if os2_len >= 6:
            weight = max(1, _u16(data, os2 + 4))
        if os2_len >= 64:
            italic = italic or bool(_u16(data, os2 + 62) & 0x0001)
    if b"head" in tables:
        head, head_len = tables[b"head"]
        if head_len >= 46:
            italic = italic or bool(_u16(data, head + 44) & 0x0002)
    return {"family_name": family, "style_name": style or "Regular",
            "weight": weight, "italic": italic}
