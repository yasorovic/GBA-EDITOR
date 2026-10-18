"""L'encre par défaut garde les couleurs du build, les index vides se nomment."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from codegen.font_emit import font_palette
from core.font_rasterizer import RasterGlyph
from core.models.font import Font, Glyph
from core.models.font_asset import FontAsset
from ui.common.labels import label
from ui.common.pickers import ColorIndexSlot
from ui.scene_manager.canvas.canvas_region_item import UIRegionItem


def test_unresolved_color_entries_are_explicitly_empty(qapp):
    slot = ColorIndexSlot('Default', '#ffffff', compact_label='Ink')
    slot.set_value(None, 0)
    entries = slot._entries()
    assert entries[0][:2] == ('Default', '0')
    assert len(entries) == 16
    assert all(label('pick.empty') in name for name, value, icon in entries[1:])
    slot.set_value(SimpleNamespace(colors=[]), 0)
    assert len(slot._entries()) == 16
    assert label('pick.empty') in slot._entries()[1][0]
    slot.set_value(SimpleNamespace(colors=[0, 0]), 0)
    assert label('pick.empty') not in slot._entries()[1][0]  # le noir existe


@pytest.mark.parametrize('ink_index', [0, 1])
def test_asset_preview_preserves_bitmap_ink_and_explicit_recolor(qapp, monkeypatch, ink_index):
    # Deux encres différentes : le défaut ne doit ni blanchir ni aplatir.
    raster = RasterGlyph('A', 2, 1, bytes([255, 255]), 2, 0, 1, 'bitmap',
                         colors=bytes([0, 0, 0, 248, 0, 0]))
    font = Font(name='Bitmap', cell_w=8, cell_h=8, line_height=8)
    font.raster_glyphs = {'A': raster}
    asset = FontAsset(name='Bitmap', pixel_height=1, line_height=8)
    project = SimpleNamespace(fonts={}, asset_abs=lambda path: None)
    context = SimpleNamespace(
        _region=SimpleNamespace(text_color=ink_index, font_weight=400, font_italic=False,
                                align='left', wraps=True),
        _project=project, rect=lambda: QRectF(0, 0, 16, 8),
        _bank_colors=lambda: [(0, 0, 0), (0, 248, 0)],
        _text_font=lambda: font,
        _fill_highlight=lambda *args: None,
    )
    context._own_ink_color = lambda f: UIRegionItem._own_ink_color(context, f)
    monkeypatch.setattr('core.font_rasterizer.rasterize_asset_glyph',
                        lambda *args, **kwargs: raster)
    image = QImage(16, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor('transparent'))
    painter = QPainter(image)
    try:
        assert UIRegionItem._paint_vector_text(context, painter, asset, 'A') is False
    finally:
        painter.end()
    assert image.pixelColor(0, 0).getRgb() == ((0, 248, 0, 255) if ink_index else (0, 0, 0, 255))
    assert image.pixelColor(1, 0).getRgb() == ((0, 248, 0, 255) if ink_index else (248, 0, 0, 255))
    assert font_palette(font, None)[1] == 0  # noir valide dans la palette du build


def test_built_glyph_keeps_bitmap_colors_in_font_markup(qapp):
    raster = RasterGlyph('A', 2, 1, bytes([255, 255]), 2, 0, 1, 'bitmap',
                         colors=bytes([0, 0, 0, 248, 0, 0]))
    font = Font(name='Bitmap', cell_w=8, cell_h=8, line_height=8)
    font.raster_glyphs = {'A': raster}
    context = SimpleNamespace(_own_ink_color=lambda f: QColor('black'))
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(QColor('transparent'))
    painter = QPainter(image)
    try:
        assert UIRegionItem._paint_built_glyph(
            context, painter, font, Glyph(char='A', w=8, h=8), 0, 0, None)
    finally:
        painter.end()
    assert image.pixelColor(0, 7).getRgb() == (0, 0, 0, 255)
    assert image.pixelColor(1, 7).getRgb() == (248, 0, 0, 255)
