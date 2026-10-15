"""Teinte, saturation, luminosité, contraste : avant la compression, sur la palette d'une image indexée, sur les pixels
sinon, et sans jamais toucher au fichier ni écrire dans le sidecar quand tout est neutre."""
from __future__ import annotations

from PIL import Image

from core.bg_adjust import apply_adjust
from core.bg_import import encode_by_mode, prepare_source
from core.models.background import BackgroundAdjust, BackgroundAsset


def _indexed(tmp_path, colors=((200, 40, 40), (40, 200, 40))):
    image = Image.new("P", (16, 8), 0)
    image.putpalette([0, 0, 0, *colors[0], *colors[1]] + [0] * (256 * 3 - 9))
    for x in range(8):
        for y in range(8):
            image.putpixel((x, y), 1)
            image.putpixel((x + 8, y), 2)
    path = tmp_path / "idx.png"
    image.save(path, transparency=0)
    return path


def test_a_neutral_adjust_gives_the_image_back_untouched():
    image = Image.new("RGB", (4, 4), (10, 20, 30))
    assert apply_adjust(image, None) is image and apply_adjust(image, BackgroundAdjust()) is image


def test_an_indexed_image_is_adjusted_by_its_palette_and_keeps_its_indices(tmp_path):
    path = _indexed(tmp_path)
    source = Image.open(path)

    out = apply_adjust(source, BackgroundAdjust(brightness=60))

    assert out.mode == "P" and list(out.getdata()) == list(source.getdata())      # les index ne bougent pas
    assert out.getpalette()[3:6] > source.getpalette()[3:6]                       # la palette s'éclaircit
    assert out.info.get("transparency") == 0                                       # et la transparence reste


def test_hue_saturation_and_contrast_move_colors_the_way_their_names_say():
    red = Image.new("RGB", (2, 2), (200, 30, 30))

    turned = apply_adjust(red, BackgroundAdjust(hue=120)).getpixel((0, 0))
    gray = apply_adjust(red, BackgroundAdjust(saturation=-100)).getpixel((0, 0))
    flat = apply_adjust(Image.frombytes("RGB", (2, 1), bytes([60, 60, 60, 200, 200, 200])), BackgroundAdjust(contrast=-100))

    assert turned[1] > turned[0] and turned[1] > turned[2]                         # le rouge devient vert
    assert gray[0] == gray[1] == gray[2]
    assert flat.getpixel((0, 0)) == flat.getpixel((1, 0))                          # plus aucun écart


def test_alpha_survives_a_direct_color_adjust():
    image = Image.new("RGBA", (2, 1), (200, 30, 30, 255))
    image.putpixel((1, 0), (200, 30, 30, 0))

    out = apply_adjust(image, BackgroundAdjust(hue=90))

    assert out.mode == "RGBA" and [out.getpixel((x, 0))[3] for x in range(2)] == [255, 0]


def test_the_adjust_is_part_of_the_preparation_and_reaches_the_encoder(tmp_path):
    path = _indexed(tmp_path)
    plain = encode_by_mode(path, "tiled4")
    bright = encode_by_mode(path, "tiled4", prep={"canvas": None, "pos": None, "size": None, "adjust": BackgroundAdjust(brightness=60)})

    assert plain["tilemap"] == bright["tilemap"]                                   # même découpage…
    assert plain["palettes"][0][1] != bright["palettes"][0][1]                     # …couleurs réglées
    assert prepare_source(path, adjust=BackgroundAdjust()).getpalette() == Image.open(path).getpalette()


def test_the_adjust_round_trips_clamps_and_writes_nothing_when_neutral():
    ba = BackgroundAsset(name="sky")
    assert "settings" not in ba.to_dict()

    ba.adjust = BackgroundAdjust(hue=-30, contrast=20)
    again = BackgroundAsset.from_dict(ba.to_dict())
    assert again.adjust == ba.adjust and ba.to_dict()["settings"]["adjust"] == {"hue": -30, "contrast": 20}

    wild = BackgroundAdjust.from_dict({"hue": 999, "saturation": "x", "brightness": -500})
    assert (wild.hue, wild.saturation, wild.brightness) == (180, 0, -100)
    assert ba.import_prep()["adjust"] == ba.adjust


def _gradient(tmp_path):
    image = Image.new("RGB", (32, 32))
    image.putdata([((x + y) * 4,) * 3 for y in range(32) for x in range(32)])   # une rampe en diagonale
    path = tmp_path / "gradient.png"
    image.save(path)
    return path


def _reduced(path, kind, dither=True):
    from core.bg_import import encode_by_mode
    from core.models.background import BackgroundCompression
    from ui.background_editor.bg_inpaint_canvas import BgInpaintController  # noqa: F401  (même rendu que l'éditeur)
    encoded = encode_by_mode(path, "tiled4", dither=dither,
                             compression=BackgroundCompression(global_colors=4, dither_kind=kind))
    from core.bg_import import render_bg_preview
    return render_bg_preview({"tiles_w": encoded["tiles_w"], "tiles_h": encoded["tiles_h"], "tileset": encoded["tileset"],
                              "palettes": encoded["palettes"], "tilemap": encoded["tilemap"], "bpp": 4})


def test_each_dither_kind_reduces_to_the_same_few_colors_but_lays_them_out_differently(tmp_path):
    path = _gradient(tmp_path)
    plain = _reduced(path, "floyd_steinberg", dither=False)
    floyd = _reduced(path, "floyd_steinberg")
    bayer4 = _reduced(path, "bayer4")
    bayer8 = _reduced(path, "bayer8")

    for image in (floyd, bayer4, bayer8):
        assert len({px for px in image.getdata()}) <= 4
    assert len({floyd.tobytes(), bayer4.tobytes(), bayer8.tobytes(), plain.tobytes()}) == 4
    assert bayer4.tobytes() == _reduced(path, "bayer4").tobytes()            # déterministe : la trame ne dépend pas du hasard


def test_an_ordered_pattern_repeats_with_the_period_of_its_matrix_and_halves_a_flat_gray():
    from core.bg_import import _remap
    black_white = Image.new("P", (1, 1))
    black_white.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
    gray = Image.new("RGB", (16, 16), (128, 128, 128))

    out = _remap(gray, black_white, 2, "bayer4").convert("L")

    assert all(out.getpixel((x, y)) == out.getpixel((x + 4, y + 4)) for x in range(12) for y in range(12))
    whites = sum(1 for px in out.getdata() if px == 255)
    assert 100 <= whites <= 156                                                    # environ la moitié des 256 pixels


def test_the_dither_kind_is_stored_with_the_compression_and_clamped():
    from core.models.background import BackgroundCompression
    assert BackgroundCompression().to_dict() == {}
    chosen = BackgroundCompression(dither_kind="bayer8")
    assert BackgroundCompression.from_dict(chosen.to_dict()) == chosen and chosen.to_dict() == {"dither_kind": "bayer8"}
    assert BackgroundCompression.from_dict({"dither_kind": "nonsense"}).dither_kind == "floyd_steinberg"


def _six_colors_per_tile(tmp_path):
    image = Image.new("P", (16, 8), 0)
    image.putpalette([c for i in range(256) for c in ((i * 15) % 256, (i * 40) % 256, (i * 90) % 256)])
    for x in range(16):
        for y in range(8):
            image.putpixel((x, y), 1 + (x + y) % 6 + (0 if x < 8 else 6))     # deux tuiles de six couleurs, douze au total
    path = tmp_path / "six.png"
    image.save(path)
    return path


def test_an_indexed_png_keeps_its_palette_until_the_author_asks_for_a_reduction(tmp_path):
    from core.bg_import import encode_background
    from core.models.background import BackgroundCompression
    path = _six_colors_per_tile(tmp_path)

    untouched = encode_background(path)
    assert untouched["diagnostics"].get("src_indexed") is True                     # la palette d'auteur, telle quelle

    reduced = encode_background(path, compression=BackgroundCompression(colors_per_palette=3))
    assert reduced["diagnostics"].get("src_indexed") is not True                   # la demande est honorée
    assert reduced["diagnostics"]["max_tile_colors"] <= 3 or reduced["diagnostics"]["tiles_reduced"] > 0


def test_the_palette_count_target_changes_the_palette_count_of_an_indexed_png(tmp_path):
    from core.bg_import import encode_background
    from core.models.background import BackgroundCompression
    path = _six_colors_per_tile(tmp_path)

    many = encode_background(path, compression=BackgroundCompression(colors_per_palette=7))
    one = encode_background(path, compression=BackgroundCompression(palettes_max=1, colors_per_palette=7))

    assert len(one["palettes"]) == 1 and len(many["palettes"]) >= 1
    assert one["diagnostics"].get("src_indexed") is not True


def test_a_dither_type_alone_does_not_leave_the_indexed_direct_path(tmp_path):
    from core.bg_import import encode_background
    from core.models.background import BackgroundCompression
    assert encode_background(_six_colors_per_tile(tmp_path), compression=BackgroundCompression(
        dither_kind="bayer8"))["diagnostics"].get("src_indexed") is True
