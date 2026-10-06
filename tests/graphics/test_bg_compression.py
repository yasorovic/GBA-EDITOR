"""Réglages de compression du tuilé 4bpp : palettes, couleurs, réduction globale,
cible de tuiles.

Garanties : les défauts ne changent rien (ni encodage, ni sidecar) ; chaque
réglage fait ce qu'il dit ; la fusion de tuiles tient sa cible et ne produit que
des cases valides.
"""
from __future__ import annotations

from PIL import Image

from core.bg_import import encode_background, encode_by_mode
from core.bg_tile_merge import merge_tiles
from core.models.background import BackgroundAsset, BackgroundCompression as BC
from core.models.tile_codec import unpack_se


def _photo(size=(96, 64)):
    """Dégradé bruité : peu de tuiles identiques, beaucoup de couleurs par tuile."""
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = ((x * 7 + y * 3) % 256, (y * 11 + x) % 256, ((x + y) * 5) % 256)
    return img


# ── Modèle ────────────────────────────────────────────────────────────────────

def test_defauts_n_ecrivent_rien():
    assert BC().is_default() and BC().to_dict() == {}
    assert "compression" not in BackgroundAsset(name="x", asset="x.png").to_dict()


def test_seul_l_ecart_au_defaut_est_ecrit_et_relu():
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.compression = BC(palettes_max=4, global_colors=48)
    d = ba.to_dict()
    assert d["compression"] == {"palettes_max": 4, "global_colors": 48}
    assert BackgroundAsset.from_dict(d).compression == ba.compression


def test_valeurs_hors_plage_sont_ramenees():
    c = BC.from_dict({"palettes_max": 0, "colors_per_palette": 99, "global_colors": -5,
                      "tile_target": "x"})
    assert (c.palettes_max, c.colors_per_palette, c.global_colors, c.tile_target) == (1, 15, 0, 0)


# ── Encodage ──────────────────────────────────────────────────────────────────

def test_defaut_identique_a_l_absence_de_reglages():
    img = _photo()
    a = encode_background(img)
    b = encode_background(img, compression=BC())
    assert a["tileset"] == b["tileset"] and a["tilemap"] == b["tilemap"]


def test_palettes_max_est_respecte():
    c = encode_background(_photo(), compression=BC(palettes_max=3))
    assert len(c["palettes"]) <= 3


def test_couleurs_par_palette_est_respecte():
    c = encode_background(_photo(), compression=BC(colors_per_palette=6))
    assert all(len(p) <= 6 + 1 for p in c["palettes"])     # + l'index 0 réservé


def test_reduction_globale_limite_les_couleurs_par_tuile():
    plain = encode_background(_photo())["diagnostics"]["max_tile_colors"]
    reduced = encode_background(_photo(), compression=BC(global_colors=8))["diagnostics"]
    assert reduced["max_tile_colors"] <= 8 < plain


def test_dithering_ne_change_rien_sans_reduction_globale():
    img = _photo()
    a = encode_background(img, dither=False)
    b = encode_background(img, dither=True)
    assert a["tilemap"] == b["tilemap"]


def test_dithering_agit_avec_reduction_globale():
    img = _photo()
    comp = BC(global_colors=8)
    a = encode_background(img, compression=comp, dither=False)
    b = encode_background(img, compression=comp, dither=True)
    assert a["tileset"] != b["tileset"]


def test_cible_de_tuiles_est_tenue():
    img = _photo()
    full = encode_background(img, compression=BC(global_colors=16))
    n = len(full["tileset"])
    assert n > 20
    small = encode_background(img, compression=BC(global_colors=16, tile_target=20))
    assert len(small["tileset"]) == 20
    assert small["diagnostics"]["tiles_merged"] == n - 20


def test_cible_deja_atteinte_ne_change_rien():
    img = _photo()
    base = encode_background(img, compression=BC(global_colors=16))
    loose = encode_background(img, compression=BC(global_colors=16, tile_target=1000))
    assert base["tilemap"] == loose["tilemap"] and loose["diagnostics"]["tiles_merged"] == 0


def test_encode_by_mode_passe_les_reglages(tmp_path):
    path = tmp_path / "p.png"
    _photo().save(path)
    c = encode_by_mode(path, "tiled4", compression=BC(palettes_max=2))
    assert len(c["palettes"]) <= 2


# ── Fusion ────────────────────────────────────────────────────────────────────

def test_fusion_ne_produit_que_des_cases_valides():
    c = encode_background(_photo(), compression=BC(global_colors=16, tile_target=10))
    n_tiles = len(c["tileset"])
    for se in c["tilemap"]:
        tid, pb, _fh, _fv = unpack_se(se)
        assert 0 <= tid < n_tiles and 0 <= pb < len(c["palettes"])


def test_fusion_repartit_la_perte_sur_toute_l_image():
    """Non-régression : départager par l'ordre de balayage écrasait le BAS de l'image
    d'abord. La perte doit se répartir, pas se concentrer sur le dernier tiers."""
    import numpy as np
    from core.bg_import import render_bg_preview
    img = _photo((128, 96))
    comp = BC(global_colors=24)
    ref = encode_background(img, compression=comp)
    n = len(ref["tileset"])
    merged = encode_background(img, compression=BC(global_colors=24, tile_target=n // 2))
    a = np.asarray(render_bg_preview(ref).convert("RGB"), dtype=np.int32)
    b = np.asarray(render_bg_preview(merged).convert("RGB"), dtype=np.int32)
    err = np.abs(a - b).sum(axis=(1, 2))
    thirds = [err[i * 32:(i + 1) * 32].sum() for i in range(3)]
    assert thirds[2] < 0.6 * sum(thirds), thirds


def test_fusion_prefere_fondre_les_zones_lisses():
    """Deux tuiles unies presque identiques se fondent avant de toucher un détail."""
    flat_a, flat_b, detail = [1] * 64, [1] * 63 + [2], [1, 2] * 32
    pal = [[(100, 100, 100), (110, 100, 100)]]
    cells = [(0, 0, False, False)] * 4 + [(1, 0, False, False)] * 4 + [(2, 0, False, False)] * 4
    tiles, out, merged = merge_tiles([flat_a, flat_b, detail], cells, pal, 2)
    assert merged == 1
    assert list(detail) in [list(t) for t in tiles]     # le détail est gardé


def test_fusion_garde_les_tuiles_les_plus_employees():
    plain = [0] * 64
    other = [1] * 64
    rare = [2] * 64
    pal = [[(255, 0, 0), (0, 255, 0)], ]
    cells = [(0, 0, False, False)] * 5 + [(1, 0, False, False)] * 3 + [(2, 0, False, False)]
    tiles, new_cells, merged = merge_tiles([plain, other, rare], cells, [[(10, 10, 10), (200, 0, 0),
                                                                          (0, 200, 0)]], 2)
    assert merged == 1 and len(tiles) == 2
    assert new_cells[-1][0] in (0, 1)


def test_methode_d_un_autre_mode_ne_fait_pas_echouer_le_4bpp():
    """Un fond venu du 8bpp/bitmap porte « quantize_256 » : basculer en 4bpp doit
    encoder, pas lever."""
    a = encode_background(_photo(), method="quantize_256")
    b = encode_background(_photo(), method="median_cut")
    assert a["tilemap"] == b["tilemap"]


# ── Répartition en palettes ───────────────────────────────────────────────────

def _horizon(size=(96, 96)):
    """Ciel clair au-dessus, mer sombre au-dessous, avec du grain : chaque tuile a
    plus de 15 couleurs, et les deux moitiés n'ont AUCUNE couleur en commun."""
    import random
    rnd = random.Random(7)
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            n = rnd.randint(-14, 14)
            if y < size[1] // 2:
                px[x, y] = (150 + y // 2 + n, 190 + n, 235 + n // 2)
            else:
                px[x, y] = (10 + n // 2, 60 + (y - 48) + n, 110 + n)
    return img


def test_photo_par_defaut_garde_chaque_zone():
    """Non-régression : garder les palettes les plus employées et renvoyer le reste
    au hasard laissait des zones entières (la mer) sans leurs couleurs."""
    import numpy as np
    from core.bg_import import render_bg_preview
    img = _horizon()
    c = encode_background(img)
    out = np.asarray(render_bg_preview(c).convert("RGB"), dtype=np.int32)[:96, :96]
    src = np.asarray(img, dtype=np.int32)
    for band in (slice(0, 48), slice(48, 96)):          # ciel, mer
        assert np.abs(out[band] - src[band]).mean() < 20


def test_palettes_restent_dans_la_limite_meme_en_perte():
    c = encode_background(_horizon(), compression=BC(palettes_max=2))
    assert len(c["palettes"]) <= 2
    assert all(len(p) <= 15 + 1 for p in c["palettes"])


def test_pixel_art_reste_sans_perte():
    """Peu de couleurs par tuile et peu de palettes : le chemin exact, pas de perte."""
    import numpy as np
    from core.bg_import import render_bg_preview
    img = Image.new("RGB", (32, 16), (200, 30, 30))
    for x in range(16, 32):
        for y in range(16):
            img.putpixel((x, y), (30, 30, 200) if (x + y) % 2 else (240, 240, 60))
    c = encode_background(img)
    out = np.asarray(render_bg_preview(c).convert("RGB"), dtype=np.int32)[:16, :32]
    src = np.asarray(img, dtype=np.int32) & 0xF8         # la grille 5 bits du matériel
    assert np.abs(out - src).max() <= 8


# ── 8bpp ──────────────────────────────────────────────────────────────────────

def test_palette_colors_est_relu_et_borne():
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.compression = BC(palette_colors=64)
    assert BackgroundAsset.from_dict(ba.to_dict()).compression.palette_colors == 64
    assert BC.from_dict({"palette_colors": 999}).palette_colors == 255
    assert BC.from_dict({"palette_colors": 0}).palette_colors == 2


def test_8bpp_defaut_identique_a_l_absence_de_reglages():
    from core.bg_import import encode_background_8bpp
    img = _photo()
    a = encode_background_8bpp(img)
    b = encode_background_8bpp(img, compression=BC())
    assert a["tilemap"] == b["tilemap"] and a["palettes"] == b["palettes"]


def test_8bpp_palette_colors_limite_la_palette():
    from core.bg_import import encode_background_8bpp
    c = encode_background_8bpp(_photo(), compression=BC(palette_colors=8))
    used = {v for t in c["tileset"] for v in bytes.fromhex(t)}
    assert max(used) <= 8                 # index 1..8 (0 = transparent)


def test_8bpp_dithering_agit_enfin():
    """Non-régression : `quantize(dither=…)` ignore l'option sans palette — le
    dithering du 8bpp n'avait jamais rien changé."""
    from core.bg_import import encode_background_8bpp
    img = _photo()
    comp = BC(palette_colors=8)
    a = encode_background_8bpp(img, dither=False, compression=comp)
    b = encode_background_8bpp(img, dither=True, compression=comp)
    assert a["tileset"] != b["tileset"]


def test_bitmap_dithering_agit_aussi():
    from core.bg_import import encode_background_bitmap
    img = Image.new("RGB", (64, 48))
    px = img.load()
    for y in range(48):
        for x in range(64):
            px[x, y] = (x * 4, y * 5, (x + y) * 2)
    assert encode_background_bitmap(img, dither=False)["bitmap"] != \
        encode_background_bitmap(img, dither=True)["bitmap"]


def test_8bpp_cible_de_tuiles_est_tenue():
    from core.bg_import import encode_background_8bpp
    img = _photo()
    n = len(encode_background_8bpp(img, compression=BC(palette_colors=32))["tileset"])
    assert n > 12
    c = encode_background_8bpp(img, compression=BC(palette_colors=32, tile_target=12))
    assert len(c["tileset"]) == 12 and c["diagnostics"]["tiles_merged"] == n - 12
    for se in c["tilemap"]:
        assert 0 <= unpack_se(se)[0] < 12


def test_8bpp_methodes_de_quantification():
    from core.bg_import import encode_background_8bpp, QUANTIZERS_8BPP
    outs = {m: encode_background_8bpp(_photo(), method=m, compression=BC(palette_colors=16))
            for m in QUANTIZERS_8BPP}
    assert all(o["quantize_method"] == m for m, o in outs.items())
    inconnue = encode_background_8bpp(_photo(), method="kmeans", compression=BC(palette_colors=16))
    assert inconnue["quantize_method"] == "median_cut"
