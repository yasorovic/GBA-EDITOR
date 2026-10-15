"""Miroir d'un fond : une barre d'axe, le côté gauche (haut) se reflète de l'autre côté, AVANT la compression.

Garanties :
  · le reflet est exact, y compris quand il ne couvre pas tout le côté opposé (zigzag) ;
  · une image indexée reste indexée ;
  · le miroir fait partie de la préparation que lit l'encodeur — et il change bien le nombre de tuiles ;
  · le modèle ne l'écrit que s'il existe, et se relit sans planter.
"""
from __future__ import annotations

from PIL import Image

from core.bg_import import prepare_source, encode_by_mode
from core.bg_mirror import apply_mirror
from core.models.background import BackgroundAsset
from ui.background_editor.bg_mirror_overlay import MirrorOverlay, AXIS_X, AXIS_Y, GRAB_MOVE, GRAB_SIDE


def _ramp(size=(16, 8)):
    """Chaque colonne a sa propre valeur : un reflet se lit directement sur la ligne 0."""
    img = Image.new("L", size)
    img.putdata([x * 10 for y in range(size[1]) for x in range(size[0])])
    return img


def _row(img, y=0):
    return [img.getpixel((x, y)) for x in range(img.width)]


def test_the_left_side_is_kept_and_reflected_onto_the_right():
    out = apply_mirror(_ramp(), (8, None))
    assert _row(out) == [x * 10 for x in range(8)] + [x * 10 for x in range(7, -1, -1)]


def test_an_axis_past_the_middle_reflects_only_what_fits():
    out = apply_mirror(_ramp(), (12, None))
    assert _row(out)[:12] == [x * 10 for x in range(12)]
    assert _row(out)[12:] == [110, 100, 90, 80]


def test_an_axis_before_the_middle_zigzags_to_the_edge():
    out = apply_mirror(_ramp(), (4, None))
    assert _row(out) == [0, 10, 20, 30, 30, 20, 10, 0, 0, 10, 20, 30, 30, 20, 10, 0]


def test_the_horizontal_bar_reflects_the_top_onto_the_bottom():
    img = Image.new("L", (4, 8))
    img.putdata([y * 10 for y in range(8) for _ in range(4)])
    out = apply_mirror(img, (None, 4))
    assert [out.getpixel((0, y)) for y in range(8)] == [0, 10, 20, 30, 30, 20, 10, 0]


def test_both_axes_and_no_axis():
    img = _ramp()
    assert apply_mirror(img, None) is img
    assert apply_mirror(img, (None, None)) is img
    assert apply_mirror(img, (8, 4)).size == img.size


def test_an_axis_outside_the_image_is_brought_back_inside():
    out = apply_mirror(_ramp(), (500, None))
    assert out.size == (16, 8) and _row(out)[:15] == [x * 10 for x in range(15)]


def test_an_indexed_image_stays_indexed_with_its_palette():
    img = Image.new("P", (16, 8))
    img.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 9))
    img.putpixel((1, 1), 1)
    out = apply_mirror(img, (8, None))
    assert out.mode == "P" and out.getpalette() == img.getpalette()
    assert out.getpixel((14, 1)) == 1


def _asymmetric_photo(tmp_path):
    """Pas deux tuiles identiques : sans miroir, la déduplication n'a rien à trouver."""
    img = Image.new("RGB", (64, 32))
    px = img.load()
    for y in range(32):
        for x in range(64):
            px[x, y] = ((x * 7 + y * 3) % 256, (y * 11 + x) % 256, ((x * y) + 5) % 256)
    path = tmp_path / "photo.png"
    img.save(path)
    return path


def test_the_mirror_reaches_the_encoder_and_lets_tiles_be_shared(tmp_path):
    path = _asymmetric_photo(tmp_path)
    plain = encode_by_mode(path, "tiled4")
    mirrored = encode_by_mode(path, "tiled4", prep={"crop": None, "size": None, "adjust": None, "mirror": (32, None)})
    assert (plain["tiles_w"], plain["tiles_h"]) == (mirrored["tiles_w"], mirrored["tiles_h"])
    assert len(mirrored["tileset"]) < len(plain["tileset"])


def test_the_mirror_follows_the_crop_and_the_size(tmp_path):
    path = _asymmetric_photo(tmp_path)
    out = prepare_source(path, crop=(0, 0, 32, 32), size=(16, 16), mirror=(8, None))
    assert out.size == (16, 16)
    assert [out.getpixel((15 - i, 3)) for i in range(8)] == [out.getpixel((i, 3)) for i in range(8)]


def test_the_asset_writes_the_mirror_only_when_there_is_one_and_reads_it_back():
    ba = BackgroundAsset(name="room")
    assert "mirror_x" not in ba.to_dict() and "mirror_y" not in ba.to_dict()
    assert ba.import_prep()["mirror"] == (None, None, False, False)

    ba.mirror_x, ba.mirror_y, ba.mirror_flip_x = 120, 80, True
    again = BackgroundAsset.from_dict(ba.to_dict())
    assert (again.mirror_x, again.mirror_y) == (120, 80)
    assert again.import_prep()["mirror"] == (120, 80, True, False)

    broken = BackgroundAsset.from_dict({"mirror_x": "oops", "mirror_y": 0})
    assert (broken.mirror_x, broken.mirror_y) == (None, None)


def test_the_bars_are_grabbed_by_handle_or_bar_and_stay_inside_the_image():
    bars = MirrorOverlay()
    bars.set_axes(64, 40, (False, False), (128, 80), (128, 80))
    assert bars.hit(64, 5) == (AXIS_X, GRAB_MOVE) and bars.hit(5, 40) == (AXIS_Y, GRAB_MOVE)
    assert bars.hit(20, 20) is None

    bars.begin((AXIS_X, GRAB_MOVE))
    bars.drag(-30, 0, snap=False)
    assert bars.axes()[0] == 1
    bars.drag(500, 0, snap=False)
    assert bars.axes()[0] == 127
    bars.drag(37, 0, snap=True)
    assert bars.axes()[0] == 40
    bars.end()
    assert not bars.dragging


def test_the_bars_follow_a_display_that_differs_from_the_prepared_size():
    bars = MirrorOverlay()
    bars.set_axes(100, None, (False, False), (200, 100), (240, 120))        # un bitmap ajusté à l'encodage : ×1,2
    assert bars.hit(120, 20) == (AXIS_X, GRAB_MOVE)
    bars.begin((AXIS_X, GRAB_MOVE))
    bars.drag(60, 0, snap=False)
    assert bars.axes()[0] == 50


def test_a_bar_dragged_near_the_middle_snaps_to_the_centre_and_not_farther():
    bars = MirrorOverlay()
    bars.set_axes(10, 10, (False, False), (128, 80), (128, 80))   # zoom 1 : 6 px d'écran = 6 px d'image
    bars.begin((AXIS_X, GRAB_MOVE))
    bars.drag(68, 0, snap=False)
    assert bars.axes()[0] == 64
    bars.drag(72, 0, snap=False)
    assert bars.axes()[0] == 72
    bars.begin((AXIS_Y, GRAB_MOVE))
    bars.drag(0, 37, snap=False)
    assert bars.axes()[1] == 40


def test_flipping_keeps_the_right_side_and_the_top_side_instead():
    kept_right = apply_mirror(_ramp(), (8, None, True, False))
    assert _row(kept_right) == [x * 10 for x in range(15, 7, -1)] + [x * 10 for x in range(8, 16)]
    img = Image.new("L", (4, 8))
    img.putdata([y * 10 for y in range(8) for _ in range(4)])
    kept_bottom = apply_mirror(img, (None, 4, False, True))
    assert [kept_bottom.getpixel((0, y)) for y in range(8)] == [70, 60, 50, 40, 40, 50, 60, 70]


def test_dragging_the_arrow_across_the_bar_flips_the_kept_side_and_back():
    bars = MirrorOverlay()
    bars.set_axes(64, None, (False, False), (128, 80), (128, 80))
    arrow = bars.hit(64 - 9, 40)                                  # la flèche est sur le côté gardé (gauche)
    assert arrow == (AXIS_X, GRAB_SIDE)

    bars.begin(arrow)
    bars.drag(80, 40, snap=False)
    assert bars.flips() == (True, False) and bars.axes() == (64, None)    # la barre n'a pas bougé
    assert bars.hit(64 + 9, 40) == (AXIS_X, GRAB_SIDE)                    # la flèche a changé de côté
    bars.drag(30, 40, snap=False)
    assert bars.flips() == (False, False)
    bars.end()
