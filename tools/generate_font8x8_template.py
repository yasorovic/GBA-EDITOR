"""Build the Font8x8 Latin bitmap source shipped by the Basic starter.

The input tables come from https://github.com/dhepper/font8x8 (Public Domain).
They are deliberately kept out of the starter: the generated PNG + sidecar are
the native project format, ready to be used by a FontAsset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "editor" / "project_starters" / "Basic"

ROW = re.compile(r"\{\s*([^}]+)\}\s*,?\s*// U\+[0-9A-F]{4}")
COLS = 16
CELL = 8
FIRST = 0x20
LAST = 0xFF


def _table(path: Path, first_codepoint: int) -> dict[int, list[int]]:
    glyphs: dict[int, list[int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ROW.search(line)
        if not match:
            continue
        values = [int(value.strip(), 16) for value in match.group(1).split(",")]
        if len(values) != CELL:
            raise ValueError(f"{path.name}: glyphe incomplet à l'index {len(glyphs)}")
        # Les commentaires de la source sont erronés pour U+00B3 et U+00B4.
        # L'index du tableau est, lui, l'identité fiable du caractère.
        glyphs[first_codepoint + len(glyphs)] = values
    return glyphs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path,
                        help="dossier contenant font8x8_basic.h et font8x8_ext_latin.h")
    parser.add_argument("--target", type=Path, default=TARGET,
                        help="racine du starter à mettre à jour")
    args = parser.parse_args()

    glyph_bits = _table(args.source_dir / "font8x8_basic.h", 0x0000)
    glyph_bits.update(_table(args.source_dir / "font8x8_ext_latin.h", 0x00A0))
    # U+007F–U+009F est la zone de contrôle, donc elle n'appartient pas au
    # jeu Latin-1 imprimable d'une police de texte.
    chars = list(range(FIRST, 0x7F)) + list(range(0xA0, LAST + 1))
    if any(codepoint not in glyph_bits for codepoint in chars):
        raise ValueError("Les tables Font8x8 ne couvrent pas tout Latin-1 imprimable.")

    rows = (len(chars) + COLS - 1) // COLS
    image = Image.new("RGB", (COLS * CELL, rows * CELL), "#FF00FF")
    pixels = image.load()
    glyphs: list[dict] = []
    for index, codepoint in enumerate(chars):
        x, y = (index % COLS) * CELL, (index // COLS) * CELL
        for py, byte in enumerate(glyph_bits[codepoint]):
            for px in range(CELL):
                if byte & (1 << px):
                    pixels[x + px, y + py] = (0, 0, 0)
        glyphs.append({"char": chr(codepoint), "x": x, "y": y,
                       "w": CELL, "h": CELL, "advance": CELL,
                       "ox": 0, "oy": 0})

    fonts_dir = args.target / "assets" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    image.save(fonts_dir / "font8x8-latin.png")
    sidecar = {
        "name": "Font8x8 Latin",
        "asset": "assets/fonts/font8x8-latin.png",
        "source_format": "png",
        "cell_w": CELL,
        "cell_h": CELL,
        "line_height": CELL,
        "bg_color": "#FF00FF",
        "glyphs": glyphs,
    }
    (fonts_dir / "Font8x8 Latin.font").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
