"""Le remplacement du PNG relit la planche et les vignettes sans cache Qt périmé."""
import os
from types import SimpleNamespace

from PyQt6.QtGui import QColor, QImage
from core.models.sprite import SpriteAsset, TilePlacement
from ui.sprite_editor.sprite_center_panel import SpriteCenterPanel
from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen


def test_remplacement_relit_sheet_et_timeline_meme_si_date_et_taille_identiques(qapp, tmp_path):
    path = tmp_path / "sheet.bmp"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(path))
    sprite = SpriteAsset(name="Hero", asset=path.name, frame_w=8, frame_h=8)
    state = sprite.states[0]
    sd = state.directions[0]
    sd.frames[0].tiles = [TilePlacement()]
    project = SimpleNamespace(root=tmp_path)
    panel = SpriteCenterPanel()
    panel.load_sprite(sprite, project)
    panel.load_direction(state, sd)
    assert panel._spritesheet._canvas._pixmap.toImage().pixelColor(0, 0) == QColor("red")
    stamp = path.stat()
    image.fill(QColor("blue"))
    assert image.save(str(path))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_size == stamp.st_size
    screen = SimpleNamespace(_project=project, _right=SimpleNamespace(_sprite=sprite), _center=panel)
    SpriteEditorScreen._on_image_changed(screen)

    assert panel._spritesheet._canvas._pixmap.toImage().pixelColor(0, 0) == QColor("blue")
    thumbnail = panel._timeline._thumbs[0]._pix_lbl.pixmap().toImage()
    assert thumbnail.pixelColor(26, 26) == QColor("blue")
    assert panel._state is state and panel._sd is sd
