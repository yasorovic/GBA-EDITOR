"""Le canvas de scène montre ce que la ROM affichera quand le bloc de palettes d'un fond n'a pas trouvé de place :
les tuiles lisent les banques 0.. de PAL_BG_RAM, telles que la scène les remplit (une banque jamais copiée = noir)."""
from __future__ import annotations

from codegen.palette_alloc import SceneBankLayout, _bg_palettes_key
from core.models.tile_codec import pack_se
from ui.scene_manager.canvas.canvas_raster import BgLayerRaster, _pal_to_rgb16

RED = 0x001F          # BGR555
BLUE = 0x7C00
TILE = "1" * 64       # une tuile 4bpp pleine d'index 1


def _compiled(banks_per_cell: list[int]) -> dict:
    """Une rangée de tuiles pleines d'index 1, la case i citant la sous-palette banks_per_cell[i]."""
    return {"tiles_w": len(banks_per_cell), "tiles_h": 1, "tileset": [TILE], "bpp": 4,
            "tilemap": [pack_se(0, pb, False, False) for pb in banks_per_cell],
            "palettes": [[0, BLUE] + [0] * 14, [0, BLUE] + [0] * 14]}      # les palettes PROPRES du fond : bleues


def _pixels(raster: BgLayerRaster) -> list[tuple]:
    raster.render({})
    image = raster.to_pixmap().toImage()
    return [image.pixelColor(x * 8 + 1, 1).getRgb()[:3] for x in range(raster.tiles_w)]


def test_without_overflow_a_tile_uses_its_own_sub_palette(qapp):
    assert _pixels(BgLayerRaster(_compiled([0, 1]), lambda slot: None)) == [(0, 0, 248), (0, 0, 248)]


def test_on_overflow_a_tile_reads_the_bank_the_rom_fills(qapp):
    hardware = [_pal_to_rgb16([0, RED]), None] + [None] * 14        # banque 0 remplie (rouge), banque 1 jamais copiée
    pixels = _pixels(BgLayerRaster(_compiled([0, 1]), lambda slot: None, hardware))
    assert pixels == [(248, 0, 0), (0, 0, 0)]                       # rouge ; noir, pas le bleu du fond


def test_a_block_without_room_is_reported_overflowed():
    class Asset:                           # la clé d'un fond compressé : ses palettes
        palettes = [[0, BLUE]]
        bpp = 4

    layout = SceneBankLayout([None] * 16, {}, {_bg_palettes_key(Asset): None})
    assert layout.bg_overflowed(Asset)
    placed = SceneBankLayout([None] * 16, {}, {_bg_palettes_key(Asset): 3})
    assert not placed.bg_overflowed(Asset)
    assert not SceneBankLayout([None] * 16, {}, {}).bg_overflowed(Asset)      # jamais alloué ≠ débordé
