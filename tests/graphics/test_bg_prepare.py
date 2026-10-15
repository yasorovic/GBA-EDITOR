"""Préparation de la source d'un fond : l'image posée dans un canvas.

Trois garanties :
  · le PNG n'est JAMAIS modifié (on revient toujours à l'original) ;
  · toute l'encodage lit la même préparation (`encode_by_mode`) ;
  · le canvas a sa propre taille : l'image peut le déborder ou le laisser vide, et rien n'est rétréci en douce.
"""
from __future__ import annotations

import pytest
from PIL import Image

from core.bg_import import prepare_source, encode_by_mode
from core.models.background import BackgroundAsset


def _photo(tmp_path, size=(64, 48)):
    """Non indexée, pas de deux tuiles identiques : l'image « riche »."""
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256)
    path = tmp_path / "photo.png"
    img.save(path)
    return path


def _indexed(tmp_path, size=(32, 32)):
    """Indexée, trois couleurs, un motif asymétrique."""
    img = Image.new("P", size, 0)
    img.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 9))
    for x in range(size[0]):
        for y in range(size[1]):
            img.putpixel((x, y), (x + 2 * y) % 3)
    path = tmp_path / "idx.png"
    img.save(path)
    return path


def _legacy(path, crop=None, size=None):
    """L'ancien rendu : recadrer, puis redimensionner (ce que faisaient `import_crop` / `import_size`)."""
    img = Image.open(path)
    if crop:
        x, y, w, h = crop
        img = img.crop((x, y, x + w, y + h))
    if size and tuple(size) != img.size:
        filt = Image.NEAREST if img.mode in ("P", "PA") else Image.LANCZOS
        img = img.resize(tuple(size), filt)
    return img


# ── prepare_source ────────────────────────────────────────────────────────────

def test_prepare_source_rien_rend_la_source(tmp_path):
    path = _photo(tmp_path)
    assert prepare_source(path).size == (64, 48)


def test_un_canvas_plus_petit_rogne_l_image(tmp_path):
    path = _photo(tmp_path)
    out = prepare_source(path, canvas=(32, 24))
    assert out.size == (32, 24)
    assert out.convert("RGBA").tobytes() == Image.open(path).convert("RGBA").crop((0, 0, 32, 24)).tobytes()


def test_un_canvas_plus_grand_laisse_du_vide_transparent(tmp_path):
    path = _photo(tmp_path)
    out = prepare_source(path, canvas=(80, 60), pos=(8, 4))
    assert out.size == (80, 60) and out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((79, 59))[3] == 0     # le vide
    assert out.getpixel((8, 4)) == Image.open(path).convert("RGBA").getpixel((0, 0))


def test_une_image_qui_deborde_a_gauche_montre_sa_partie_visible(tmp_path):
    path = _photo(tmp_path)
    out = prepare_source(path, canvas=(32, 24), pos=(-10, -6))
    assert out.convert("RGBA").tobytes() == Image.open(path).convert("RGBA").crop((10, 6, 42, 30)).tobytes()


def test_une_image_hors_du_canvas_donne_un_canvas_vide(tmp_path):
    path = _photo(tmp_path)
    out = prepare_source(path, canvas=(16, 16), pos=(500, 500))
    assert out.size == (16, 16) and out.getchannel("A").getextrema() == (0, 0)


@pytest.mark.parametrize("crop,size", [
    (None, (32, 24)),
    ((8, 8, 32, 24), (16, 12)),
    ((8, 8, 32, 24), (64, 48)),
    ((0, 0, 64, 48), (128, 96)),
])
def test_la_pose_reproduit_l_ancien_recadrage_puis_taille_sur_une_photo(tmp_path, crop, size):
    """Un recadrage (x, y, w, h) + une taille (W, H) = un canvas W×H, l'image à l'échelle W/w posée en (−x·s, −y·s)."""
    path = _photo(tmp_path)
    sw, sh = Image.open(path).size
    cw, ch = crop[2:] if crop else (sw, sh)
    cx, cy = crop[:2] if crop else (0, 0)
    scale_x, scale_y = size[0] / cw, size[1] / ch
    out = prepare_source(path, canvas=size, size=(round(sw * scale_x), round(sh * scale_y)),
                         pos=(round(-cx * scale_x), round(-cy * scale_y)))
    assert out.convert("RGBA").tobytes() == _legacy(path, crop, size).convert("RGBA").tobytes()


def test_la_pose_reproduit_l_ancien_rendu_d_une_source_indexee(tmp_path):
    path = _indexed(tmp_path)
    out = prepare_source(path, canvas=(16, 16), size=(16, 16))
    assert out.mode == "P"
    assert out.convert("RGBA").tobytes() == _legacy(path, None, (16, 16)).convert("RGBA").tobytes()


def test_source_indexee_garde_sa_palette(tmp_path):
    """Plus proche voisin : une source indexée reste indexée, pas lissée, et le vide est l'index 0 transparent."""
    path = _indexed(tmp_path)
    out = prepare_source(path, canvas=(48, 48), pos=(8, 8))
    assert out.mode == "P" and out.size == (48, 48)
    assert out.getpalette()[:9] == [0, 0, 0, 255, 0, 0, 0, 255, 0]
    assert {i for i, n in enumerate(out.histogram()) if n} <= {0, 1, 2}
    assert out.convert("RGBA").getpixel((0, 0))[3] == 0


def test_le_fichier_source_n_est_pas_modifie(tmp_path):
    path = _photo(tmp_path)
    before = path.read_bytes()
    prepare_source(path, canvas=(16, 16), pos=(-4, -4), size=(32, 32))
    encode_by_mode(path, "tiled8", prep={"canvas": (16, 16), "pos": (0, 0), "size": (16, 16)})
    assert path.read_bytes() == before


def test_encode_by_mode_applique_la_preparation(tmp_path):
    path = _photo(tmp_path, (64, 48))
    plain = encode_by_mode(path, "tiled8")
    small = encode_by_mode(path, "tiled8", prep={"canvas": (32, 24)})
    assert (plain["tiles_w"], plain["tiles_h"]) == (8, 6)
    assert (small["tiles_w"], small["tiles_h"]) == (4, 3)
    assert len(small["tileset"]) < len(plain["tileset"])


# ── Le bitmap ne rétrécit plus en douce ───────────────────────────────────────

def test_un_encodeur_bitmap_appele_avec_une_image_trop_grande_est_une_erreur_franche(tmp_path):
    """Le filet : l'encodeur lui-même ne rétrécit jamais. `encode_by_mode` pose le canvas avant."""
    from core.bg_import import encode_background_bitmap
    with pytest.raises(ValueError, match="240x160"):
        encode_background_bitmap(Image.open(_photo(tmp_path, (300, 200))))
    with pytest.raises(ValueError, match="240x160"):
        encode_background_bitmap(Image.open(_indexed(tmp_path, (300, 200))))


def test_une_photo_plus_grande_que_l_ecran_deborde_du_canvas_bitmap_sans_etre_rétrécie(tmp_path):
    """Un bitmap a un canvas fixe de 240×160 : l'image garde sa taille en (0, 0), le surplus est rogné."""
    from core.bg_import import render_bitmap_preview
    img = Image.new("RGB", (300, 200), (0, 0, 248))                  # bleu partout, sauf le coin haut-gauche 240×160
    img.paste((248, 0, 0), (0, 0, 240, 160))
    path = tmp_path / "corner.png"
    img.save(path)
    out = encode_by_mode(path, "bitmap")
    assert (out["out_w"], out["out_h"]) == (240, 160)
    shown = render_bitmap_preview(out)
    assert {shown.getpixel((x, y))[:3] for x in (0, 239) for y in (0, 159)} == {(248, 0, 0)}   # rouge : rien de rétréci


def test_repasser_en_tuile_garde_le_canvas_du_bitmap(tmp_path):
    """Le canvas est une valeur du fond, pas du layout : encodé en bitmap (240×160), il reste 240×160 en tuilé."""
    from core.resources.asset_reconciliation import apply_bg_encoding
    path = _photo(tmp_path, (300, 200))
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout("bitmap")                                   # le réglage : le canvas d'un bitmap vaut 240×160
    assert ba.canvas_size == (240, 160)
    apply_bg_encoding(ba, encode_by_mode(path, "bitmap", prep=ba.import_prep()))
    assert ba.canvas_size == (240, 160)

    tiled = encode_by_mode(path, "tiled8", prep=ba.import_prep())
    assert (tiled["tiles_w"], tiled["tiles_h"]) == (30, 20)                      # 240×160, l'image déborde


def test_un_bitmap_indexe_deborde_aussi_et_garde_sa_palette(tmp_path):
    path = _indexed(tmp_path, (300, 200))
    out = encode_by_mode(path, "bitmap")
    assert (out["out_w"], out["out_h"]) == (240, 160)
    assert out["diagnostics"]["src_indexed"] is True


def test_une_image_plus_petite_que_l_ecran_laisse_du_vide_transparent_en_bitmap(tmp_path):
    path = _photo(tmp_path, (240, 134))
    out = encode_by_mode(path, "bitmap")
    assert (out["out_w"], out["out_h"]) == (240, 160)
    buf = bytes.fromhex(out["bitmap"])
    assert set(buf[240 * 134:]) == {0}                         # le vide du bas est l'index 0, transparent


# ── Sidecar ───────────────────────────────────────────────────────────────────

def test_preparation_survit_a_l_aller_retour_json():
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.canvas_size, ba.image_pos, ba.image_size = (240, 160), (-8, 16), (500, 300)
    back = BackgroundAsset.from_dict(ba.to_dict())
    assert (back.canvas_size, back.image_pos, back.image_size) == ((240, 160), (-8, 16), (500, 300))


def test_sans_preparation_rien_n_est_ecrit():
    d = BackgroundAsset(name="x", asset="x.png").to_dict()
    assert "settings" not in d


def test_preparation_illisible_se_relit_comme_absente():
    ba = BackgroundAsset.from_dict({"name": "x", "canvas_size": [1], "image_pos": "a", "image_size": [0, 5]})
    assert ba.canvas_size is None and ba.image_pos is None and ba.image_size is None


def test_import_prep_porte_le_canvas_la_pose_et_la_taille():
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.canvas_size, ba.image_pos, ba.image_size = (8, 8), (1, 2), (16, 16)
    prep = ba.import_prep()
    assert (prep["canvas"], prep["pos"], prep["size"]) == ((8, 8), (1, 2), (16, 16))


# ── Mesure du 4bpp ────────────────────────────────────────────────────────────

def test_analyse_image_a_deux_couleurs_tient_en_4bpp(tmp_path):
    from core.bg_import import analyze_tile_colors
    img = Image.new("RGB", (16, 8), (200, 0, 0))
    for x in range(8, 16):                      # 2e tuile : autre couleur
        for y in range(8):
            img.putpixel((x, y), (0, 0, 200))
    m = analyze_tile_colors(img)
    assert m["tiles"] == 2 and m["colors_max"] == 1
    assert m["tiles_over"] == 0 and m["distinct_sets"] == 2 and m["shared_tiles"] == 0
    assert m["palettes_needed"] == 1            # les deux jeux tiennent dans une palette


def test_analyse_compte_les_tuiles_au_jeu_de_couleurs_identique():
    from core.bg_import import analyze_tile_colors
    m = analyze_tile_colors(Image.new("RGB", (32, 8), (10, 20, 30)))
    assert m["tiles"] == 4 and m["distinct_sets"] == 1 and m["shared_tiles"] == 4


def test_analyse_photo_signale_les_tuiles_a_reduire(tmp_path):
    from core.bg_import import analyze_tile_colors
    m = analyze_tile_colors(_photo(tmp_path))
    assert m["tiles_over"] > 0 and m["colors_max"] > 15
    assert sum(m["buckets"]) == m["tiles"]


# ── Réglages et résultats : deux blocs, deux responsabilités ──────────────────

def _encoded_background(tmp_path, token="tiled4"):
    from core.resources.asset_reconciliation import apply_bg_encoding
    path = _photo(tmp_path, (32, 32))
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout(token)
    if token.startswith("tiled"):
        ba.canvas_size = (24, 24)
    apply_bg_encoding(ba, encode_by_mode(path, token, prep=ba.import_prep()))
    return ba


def test_le_sidecar_separe_les_reglages_du_resultat(tmp_path):
    ba = _encoded_background(tmp_path)
    ba.tile_paint = {(1, 1): (3, 0)}
    d = ba.to_dict()

    assert d["settings"]["canvas_size"] == [24, 24] and "tile_paint" in d["settings"]
    assert {"tileset", "tilemap", "palettes", "tiles_w", "tiles_h"} <= set(d["encoded"])
    assert not {"tileset", "tilemap", "palettes", "canvas_size"} & set(d)                  # plus rien à plat
    assert not {"tileset", "tilemap", "palettes"} & set(d["settings"])                     # aucun résultat dans les réglages
    assert not {"canvas_size", "mode", "compression", "tile_paint"} & set(d["encoded"])    # aucun réglage dans le résultat


def test_un_sidecar_a_plat_d_avant_les_deux_blocs_se_relit_tel_quel(tmp_path):
    ba = _encoded_background(tmp_path)
    d = ba.to_dict()
    flat = {**{k: v for k, v in d.items() if k not in ("settings", "encoded")},
            **d["encoded"], **d["settings"]}                                 # l'ancien format : tout au même niveau

    again = BackgroundAsset.from_dict(flat)

    assert again.tileset == ba.tileset and again.tilemap == ba.tilemap and again.canvas_size == (24, 24)
    assert again.to_dict() == d                                              # réécrit en deux blocs à la prochaine sauvegarde


def test_un_bitmap_ecrit_son_mode_en_reglage_et_son_tampon_en_resultat(tmp_path):
    ba = _encoded_background(tmp_path, "bitmap")
    d = ba.to_dict()

    assert d["settings"]["mode"] == "bitmap" and d["settings"]["canvas_size"] == [240, 160]
    assert {"bitmap", "out_w", "out_h", "palettes"} <= set(d["encoded"]) and "mode" not in d["encoded"]
    assert BackgroundAsset.from_dict(d).mode == "bitmap"


def test_un_encodage_ne_touche_a_aucun_reglage(tmp_path):
    """`apply_bg_encoding` range un résultat : ni layout, ni profondeur, ni méthode, ni canvas, ni retouches de tuiles."""
    from core.resources.asset_reconciliation import apply_bg_encoding
    path = _photo(tmp_path, (32, 32))
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout("tiled8")
    ba.quantize_method, ba.canvas_size, ba.dither = "kmeans", (24, 24), True
    ba.tile_paint, ba.tile_palette_overrides = {(0, 0): (1, 0)}, {(1, 0): 2}
    before = dict(ba._settings_dict())

    apply_bg_encoding(ba, encode_by_mode(path, "bitmap", prep={"canvas": (24, 24)}))      # un résultat d'un AUTRE layout

    assert ba._settings_dict() == before and ba.mode == "tiled" and ba.bpp == 8
    assert ba.bitmap and not ba.tileset                                                  # seul le résultat a changé


def test_choisir_un_layout_est_un_reglage_qui_pose_le_canvas_du_bitmap_et_vide_les_retouches_de_tuiles():
    ba = BackgroundAsset(name="x")
    ba.tile_paint, ba.tile_palette_overrides = {(0, 0): (1, 0)}, {(1, 0): 2}

    ba.choose_layout("bitmap")
    assert (ba.mode, ba.bpp, ba.canvas_size) == ("bitmap", 8, (240, 160))
    assert ba.tile_paint == {} and ba.tile_palette_overrides == {}                       # un bitmap n'a pas de tuiles

    ba.choose_layout("tiled4")
    assert (ba.mode, ba.bpp) == ("tiled", 4) and ba.canvas_size == (240, 160)            # repasser en tuilé garde le canvas
