"""Disk previews preserve source/asset semantics and never encode resources."""
from types import SimpleNamespace

from PIL import Image
from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QScrollArea, QTextEdit

from core import disk_tree
from core.models.background import BackgroundAsset
from core.models.palette import PaletteBank
from core.models.sprite import AnimFrame, AnimState, SpriteAsset, StateDirection, TilePlacement
from ui.common.disk_preview import resource_preview
from ui.common.disk_view import DiskView


def _node(path, family='', kind=disk_tree.ASSET):
    return disk_tree.DiskNode(path.name, path, kind, path.stem, family)


def test_source_metadata_does_not_decode_sheet_and_preview_is_bounded(qapp, tmp_path):
    path = tmp_path / 'sheet.png'
    Image.new('RGBA', (8192, 16), 'red').save(path)
    node = _node(path, 'fonts', disk_tree.LINKED_SOURCE)
    metadata = resource_preview(None, node)
    assert '8192 × 16' in metadata.lines[0] and 'PNG' in metadata.lines[0]
    assert metadata.image.isNull()
    assert metadata.metadata == []
    rendered = resource_preview(None, node, True)
    assert rendered.image.width() == 4096
    assert rendered.note
    assert any(value == 'RGBA' for _, value in rendered.metadata)


def test_sprite_preview_uses_composed_tiles_instead_of_whole_sheet(qapp, tmp_path):
    path = tmp_path / 'sheet.png'
    image = Image.new('RGBA', (16, 8), 'red')
    image.paste('blue', (8, 0, 16, 8))
    image.save(path)
    frame = AnimFrame(tiles=[TilePlacement(src_col=1)])
    sprite = SpriteAsset(asset=str(path), frame_w=8, frame_h=8,
                         states=[AnimState(directions=[StateDirection(frames=[frame])])])
    project = SimpleNamespace(get_sprite=lambda _: sprite, asset_abs=lambda _: path)
    result = resource_preview(project, _node(tmp_path / 'Player.sprite', 'sprites'), True)
    assert result.image.size().width() == 8
    assert result.image.pixelColor(0, 0).name() == '#0000ff'
    assert any('8 × 8' in line for line in result.lines)
    assert result.note
    assert any('Idle' in key and '60 Hz' in value for key, value in result.metadata)


def test_palette_asset_and_hex_source(qapp, tmp_path):
    path = tmp_path / 'colors.hex'
    path.write_text('#000000\n#ff0000\n', encoding='utf-8')
    result = resource_preview(None, _node(path, kind=disk_tree.FREE_SOURCE), True)
    assert not result.image.isNull()
    assert result.image.pixelColor(24, 0).red() > 240
    palette = PaletteBank(colors=[0, 31], size=16)
    project = SimpleNamespace(get_palette=lambda _: palette)
    asset = resource_preview(project, _node(tmp_path / 'colors.palette', 'palettes'), True)
    assert asset.lines == result.lines
    assert asset.image == result.image
    assert any('#' in value for _, value in asset.metadata)


def test_background_preview_uses_encoded_output_without_source(qapp, tmp_path):
    bg = BackgroundAsset(mode='bitmap', bpp=8, out_w=2, out_h=1,
                         bitmap='0101', palettes=[[0, 31]])
    project = SimpleNamespace(get_background=lambda _: bg)
    result = resource_preview(project, _node(tmp_path / 'BG.background', 'backgrounds'), True)
    assert result.image.width() == 2
    assert result.image.pixelColor(0, 0).red() > 240
    assert any('2 × 1' in line for line in result.lines)
    assert any(value == '2' for _, value in result.metadata)


def test_tiled_background_renders_tiles_and_unencoded_uses_source(qapp, tmp_path):
    path = tmp_path / 'bg.png'
    Image.new('RGBA', (32, 16), 'blue').save(path)
    bg = BackgroundAsset(asset=str(path), tiles_w=1, tiles_h=1,
                         tileset=['1' * 64], tilemap=[0], palettes=[[0, 31]])
    project = SimpleNamespace(get_background=lambda _: bg, asset_abs=lambda _: path)
    node = _node(tmp_path / 'BG.background', 'backgrounds')
    result = resource_preview(project, node, True)
    assert result.image.width() == 8
    assert result.image.pixelColor(0, 0).red() > 240
    bg.tilemap.clear()
    result = resource_preview(project, node, True)
    assert result.image.width() == 32
    assert result.image.pixelColor(0, 0).blue() == 255
    path.unlink()
    result = resource_preview(project, node, True)
    assert result.image.isNull() and result.note


def test_missing_and_corrupt_sources_and_unsupported_families(qapp, tmp_path):
    path = tmp_path / 'bad.png'
    path.write_text('invalid', encoding='utf-8')
    assert resource_preview(None, _node(path, kind=disk_tree.FREE_SOURCE), True).note
    path.unlink()
    assert resource_preview(None, _node(path, kind=disk_tree.FREE_SOURCE), True).image.isNull()
    assert resource_preview(None, _node(tmp_path / 'binary.bin'), True) is None
    assert resource_preview(None, _node(tmp_path, kind=disk_tree.FOLDER), True) is None


def test_selection_hover_dialog_zoom_and_navigation(qapp, tmp_path, monkeypatch):
    # Exercise HTML escaping through the display name.
    path = tmp_path / 'sheet.png'
    Image.new('RGBA', (320, 16), 'red').save(path)
    node = _node(path, kind=disk_tree.FREE_SOURCE)
    node.name = '<sheet>.png'
    view = DiskView()
    view.resize(1000, 350)
    view.set_preview_provider(lambda node, render: resource_preview(None, node, render))
    view.set_tree(disk_tree.DiskNode('assets', tmp_path, disk_tree.FOLDER, children=[node]))
    view.show()
    view._list.setCurrentRow(1)
    qapp.processEvents()
    assert not view._preview.isHidden()
    assert view._preview._image.image.width() == 320
    from ui.common.tooltip_controller import resolve_tooltip
    captured = []
    position = view._list.visualItemRect(view._list.item(1)).center()
    captured.append(resolve_tooltip(view._list.viewport(), position).text)
    assert '320 × 16' in captured[0] and '&lt;sheet&gt;' in captured[0]

    widths = []
    def check_dialog():
        dialog = view.findChild(QDialog)
        scroll = dialog.findChild(QScrollArea, 'diskPreviewImageScroll')
        metadata = dialog.findChild(QScrollArea, 'diskPreviewMetadataScroll')
        captured.extend(widget.text() for widget in metadata.findChildren(QLabel))
        captured.extend(widget.toPlainText() for widget in metadata.findChildren(QTextEdit))
        plus = next(b for b in dialog.findChildren(QPushButton) if b.text() == '+')
        before = scroll.widget().width()
        plus.click()
        widths.extend([before, scroll.widget().width()])
        dialog.accept()

    QTimer.singleShot(0, check_dialog)
    view._preview._enlarge.click()
    assert widths[1] > widths[0]
    assert str(path) in captured
    assert any('320 × 16' in value for value in captured)
    view._list.clearSelection()
    assert view._preview._body.isHidden() and not view._preview._empty.isHidden()   # le panneau reste en place, vide
    view._list.setCurrentRow(1)
    view.set_tree(None)
    assert view._preview._body.isHidden() and not view._preview._empty.isHidden()
    view.close()
