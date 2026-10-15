"""core/bg_bake.py — l'image d'un fond tel qu'il s'affiche : calque de peinture et repeints de palette compris.

Deux sorties. `render_rgba` : l'image vue (export, aperçu). `save_indexed_png` : un PNG INDEXÉ « par banques »,
index = banque × 16 + couleur, l'index 0 de chaque banque transparent (tRNS) — la convention des outils GBA. Les
banques survivent donc au fichier : `core.bg_import` le relit à l'identique, au lieu de re-déduire des palettes depuis
les seules couleurs peintes (ce qui fusionnerait deux banques de mêmes couleurs)."""
from __future__ import annotations

from core.models.gba_color import bgr555_to_rgb888
from core.models.tile_codec import flip_h, flip_v, hex_to_tile, unpack_se


def render_rgba(ba):
    """L'image RGBA du fond avec tout ce qui le compose, sans les animés posés dessus."""
    from core.bg_import import render_bg_preview, render_bitmap_preview
    if ba.mode == "bitmap":
        return render_bitmap_preview({"out_w": ba.out_w, "out_h": ba.out_h,
                                      "palettes": ba.palettes, "bitmap": ba.bitmap})
    return render_bg_preview({"tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
                              "tileset": ba.effective_tileset(), "palettes": ba.palettes,
                              "tilemap": ba.effective_tilemap(), "bpp": ba.bpp})


def can_bake(ba) -> bool:
    """Vrai pour un fond tuilé 4bpp d'au plus 16 palettes : le seul qui s'écrit en PNG indexé par banques."""
    return bool(ba and ba.mode == "tiled" and ba.bpp == 4 and ba.tileset and 1 <= len(ba.palettes) <= 16)


def render_indexed(ba):
    """`(image 'P', tRNS)` : le fond TUILÉ 4bpp en index par banques. ValueError hors de ce cadre."""
    from PIL import Image
    if not can_bake(ba):
        raise ValueError("only a tiled 4bpp background of at most 16 palettes can be saved as an indexed PNG")
    tiles = [hex_to_tile(t) for t in ba.effective_tileset()]
    tw = ba.tiles_w
    img = Image.new("P", (tw * 8, ba.tiles_h * 8), 0)
    px = img.load()
    for cell, se in enumerate(ba.effective_tilemap()):
        tid, bank, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        bank = bank if bank < len(ba.palettes) else 0
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                color = grid[y * 8 + x]
                px[ox + x, oy + y] = bank * 16 + color if color else 0
    palette: list = []
    for pal in ba.palettes:
        for k in range(16):
            palette += bgr555_to_rgb888(pal[k]) if 0 < k < len(pal) else (0, 0, 0)
    img.putpalette(palette)
    transparency = bytes(0 if i % 16 == 0 else 255 for i in range(16 * len(ba.palettes)))
    return img, transparency


def save_indexed_png(ba, path) -> None:
    img, transparency = render_indexed(ba)
    img.save(path, "PNG", transparency=transparency)
