"""Préparation de la source d'un fond : recadrer, redimensionner.

Trois garanties :
  · le PNG n'est JAMAIS modifié (on revient toujours à l'original) ;
  · toute l'encodage lit la même préparation (`encode_by_mode`) ;
  · les règles de modificateurs (Maj = proportions, Ctrl = 8 px) tiennent.
"""
from __future__ import annotations

from PIL import Image

from core.bg_import import prepare_source, encode_by_mode
from core.models.background import BackgroundAsset
from ui.background_editor.bg_prepare_geometry import crop_target, resize_target


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


# ── prepare_source ────────────────────────────────────────────────────────────

def test_prepare_source_rien_rend_la_source(tmp_path):
    path = _photo(tmp_path)
    assert prepare_source(path).size == (64, 48)


def test_recadrage_puis_taille(tmp_path):
    path = _photo(tmp_path)
    img = prepare_source(path, crop=(8, 8, 32, 24), size=(16, 12))
    assert img.size == (16, 12)


def test_recadrage_hors_image_est_ramene_dedans(tmp_path):
    path = _photo(tmp_path)
    assert prepare_source(path, crop=(60, 40, 100, 100)).size == (4, 8)


def test_source_indexee_garde_sa_palette(tmp_path):
    """Plus proche voisin : une source indexée reste indexée, pas lissée."""
    img = Image.new("P", (32, 32))
    img.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 9))
    img.putpixel((1, 1), 1)
    path = tmp_path / "idx.png"
    img.save(path)
    out = prepare_source(path, size=(16, 16))
    assert out.mode == "P"
    assert {i for i, n in enumerate(out.histogram()) if n} <= {0, 1}


def test_le_fichier_source_n_est_pas_modifie(tmp_path):
    path = _photo(tmp_path)
    before = path.read_bytes()
    prepare_source(path, crop=(0, 0, 16, 16), size=(8, 8))
    encode_by_mode(path, "tiled8", prep={"crop": (0, 0, 16, 16), "size": (8, 8)})
    assert path.read_bytes() == before


def test_encode_by_mode_applique_la_preparation(tmp_path):
    path = _photo(tmp_path, (64, 48))
    plain = encode_by_mode(path, "tiled8")
    small = encode_by_mode(path, "tiled8", prep={"crop": None, "size": (32, 24)})
    assert (plain["tiles_w"], plain["tiles_h"]) == (8, 6)
    assert (small["tiles_w"], small["tiles_h"]) == (4, 3)
    assert len(small["tileset"]) < len(plain["tileset"])


# ── Sidecar ───────────────────────────────────────────────────────────────────

def test_preparation_survit_a_l_aller_retour_json():
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.import_crop, ba.import_size = (8, 16, 100, 60), (50, 30)
    back = BackgroundAsset.from_dict(ba.to_dict())
    assert back.import_crop == (8, 16, 100, 60)
    assert back.import_size == (50, 30)


def test_sans_preparation_rien_n_est_ecrit():
    d = BackgroundAsset(name="x", asset="x.png").to_dict()
    assert "import_crop" not in d and "import_size" not in d


def test_preparation_illisible_se_relit_comme_absente():
    ba = BackgroundAsset.from_dict({"name": "x", "import_crop": [1, 2], "import_size": [0, 5]})
    assert ba.import_crop is None and ba.import_size is None


# ── Géométrie ─────────────────────────────────────────────────────────────────

def test_redimensionnement_libre():
    assert resize_target(100, 50, "se", 20, -10, False, False) == (120, 40)


def test_redimensionnement_proportionnel_par_un_coin():
    w, h = resize_target(100, 50, "se", 50, 0, True, False)
    assert (w, h) == (150, 75)


def test_redimensionnement_proportionnel_par_le_bord_droit():
    assert resize_target(100, 50, "e", 100, 0, True, False) == (200, 100)


def test_redimensionnement_accroche_a_8():
    assert resize_target(100, 50, "se", 3, 3, False, True) == (104, 56)


def test_redimensionnement_ne_descend_pas_sous_un_pixel():
    assert resize_target(10, 10, "se", -500, -500, False, False) == (1, 1)


def test_recadrage_libre_reste_dans_l_image():
    rect = (10, 10, 50, 40)
    assert crop_target(rect, (100, 80), "se", 500, 500, False, False) == (10, 10, 100, 80)
    assert crop_target(rect, (100, 80), "nw", -500, -500, False, False) == (0, 0, 50, 40)


def test_recadrage_deplacement_borne():
    assert crop_target((10, 10, 50, 40), (100, 80), "move", 500, 500, False, False) \
        == (60, 50, 100, 80)


def test_recadrage_taille_minimale():
    l, t, r, b = crop_target((10, 10, 50, 40), (100, 80), "e", -500, 0, False, False)
    assert r - l == 8


def test_recadrage_accroche_a_8():
    assert crop_target((0, 0, 50, 40), (100, 80), "se", 7, 7, False, True) == (0, 0, 56, 48)


def test_recadrage_maj_garde_les_proportions_de_l_origine():
    # Source 100×50 (2:1) : quel que soit le geste, le cadre reste 2:1.
    for handle, dx, dy in (("se", 30, 5), ("nw", -10, -3), ("e", 20, 0), ("s", 0, 10)):
        l, t, r, b = crop_target((20, 10, 60, 30), (100, 50), handle, dx, dy, True, False)
        assert abs((r - l) / (b - t) - 2.0) < 0.06, (handle, (l, t, r, b))
        assert 0 <= l < r <= 100 and 0 <= t < b <= 50


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


def test_redimensionnement_par_la_gauche_et_le_haut():
    # Tirer le bord gauche vers l'extérieur (dx négatif) agrandit.
    assert resize_target(100, 50, "w", -20, 0, False, False) == (120, 50)
    assert resize_target(100, 50, "n", 0, -10, False, False) == (100, 60)
    assert resize_target(100, 50, "nw", -20, -10, False, False) == (120, 60)
    # … et vers l'intérieur réduit.
    assert resize_target(100, 50, "w", 30, 0, False, False) == (70, 50)


def test_redimensionnement_proportionnel_par_un_bord_du_haut():
    assert resize_target(100, 50, "n", 0, -25, True, False) == (150, 75)
    assert resize_target(100, 50, "w", -100, 0, True, False) == (200, 100)
