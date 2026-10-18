"""Un résultat d'encodage sait de quels réglages il vient : il est « à jour » ou « périmé », sans rien recalculer.

L'empreinte (`encode_settings_fingerprint`) porte ce qui DÉTERMINE l'encodage ; les palettes citées, la peinture et les
repeints se posent par-dessus le résultat sans le changer, ils n'en font pas partie.
"""
from __future__ import annotations

import pytest
from PIL import Image

from core.bg_import import encode_by_mode
from core.models.background import BackgroundAdjust, BackgroundAsset, BackgroundCompression
from core.resources.asset_reconciliation import apply_bg_encoding


def _encoded(tmp_path, token="tiled4"):
    img = Image.new("RGB", (32, 32))
    px = img.load()
    for y in range(32):
        for x in range(32):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256)
    path = tmp_path / "photo.png"
    img.save(path)
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout(token)
    apply_bg_encoding(ba, encode_by_mode(path, token, prep=ba.import_prep(), compression=ba.compression))
    return ba


# ── L'empreinte ───────────────────────────────────────────────────────────────

def test_l_empreinte_est_stable_et_courte():
    a, b = BackgroundAsset(name="x"), BackgroundAsset(name="y")

    assert a.encode_settings_fingerprint() == b.encode_settings_fingerprint()      # le nom n'y est pas
    assert len(a.encode_settings_fingerprint()) == 12


@pytest.mark.parametrize("change", [
    lambda ba: setattr(ba, "canvas_size", (64, 64)),
    lambda ba: setattr(ba, "image_pos", (4, 8)),
    lambda ba: setattr(ba, "image_size", (100, 50)),
    lambda ba: setattr(ba, "mirror_x", 16),
    lambda ba: setattr(ba, "mirror_flip_y", True),
    lambda ba: setattr(ba, "adjust", BackgroundAdjust(hue=30)),
    lambda ba: setattr(ba, "compression", BackgroundCompression(palettes_max=4)),
    lambda ba: setattr(ba, "dither", True),
    lambda ba: setattr(ba, "quantize_method", "kmeans"),
    lambda ba: ba.choose_layout("tiled8"),
    lambda ba: ba.choose_layout("bitmap"),
])
def test_chaque_reglage_de_l_encodage_change_l_empreinte(change):
    ba = BackgroundAsset(name="x")
    before = ba.encode_settings_fingerprint()

    change(ba)

    assert ba.encode_settings_fingerprint() != before


@pytest.mark.parametrize("change", [
    lambda ba: ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14),
    lambda ba: setattr(ba, "palette_overrides", {0: "Blue"}),
    lambda ba: setattr(ba, "tile_paint", {(0, 0): (1, 0)}),
    lambda ba: setattr(ba, "tile_palette_overrides", {(0, 0): 0}),
    lambda ba: setattr(ba, "name", "autre"),
])
def test_la_peinture_les_repeints_et_les_palettes_citees_ne_changent_pas_l_empreinte(change):
    ba = BackgroundAsset(name="x")
    before = ba.encode_settings_fingerprint()

    change(ba)

    assert ba.encode_settings_fingerprint() == before


def test_le_canvas_d_un_bitmap_est_fixe_donc_hors_de_l_empreinte():
    ba = BackgroundAsset(name="x")
    ba.choose_layout("bitmap")
    before = ba.encode_settings_fingerprint()

    ba.canvas_size = (99, 99)                                    # sans effet : l'encodeur impose 240×160

    assert ba.encode_settings_fingerprint() == before


# ── À jour ou périmé ──────────────────────────────────────────────────────────

def test_un_fond_sans_resultat_n_est_pas_a_jour():
    assert not BackgroundAsset(name="x").encoding_is_current()


def test_un_encodage_pose_l_empreinte_des_reglages_et_le_resultat_est_a_jour(tmp_path):
    ba = _encoded(tmp_path)

    assert ba.encoded_for == ba.encode_settings_fingerprint() and ba.encoding_is_current()


def test_changer_un_reglage_perime_le_resultat_et_un_nouvel_encodage_le_remet_a_jour(tmp_path):
    ba = _encoded(tmp_path)

    ba.compression = BackgroundCompression(palettes_max=3)
    assert not ba.encoding_is_current()

    ba.compression = BackgroundCompression()                     # le retour aux réglages d'origine : à jour sans recalcul
    assert ba.encoding_is_current()


def test_peindre_ou_ajouter_une_palette_ne_perime_pas_le_resultat(tmp_path):
    ba = _encoded(tmp_path)

    ba.add_palette_ref("Green", [0, 0x03E0] + [0] * 14)
    ba.tile_paint = {(0, 0): (1, 0)}

    assert ba.encoding_is_current()


def test_la_source_retouchee_perime_le_resultat_quand_on_donne_son_empreinte_actuelle(tmp_path):
    ba = _encoded(tmp_path)
    ba.source_stamp = "100:abc"

    assert ba.encoding_is_current("100:abc")
    assert not ba.encoding_is_current("200:def")                 # le PNG a changé depuis l'encodage
    assert ba.encoding_is_current(None)                          # sans empreinte actuelle, la source n'est pas jugée
    ba.source_stamp = ""
    assert ba.encoding_is_current("200:def")                     # origine inconnue : on ne conclut pas


# ── Le sidecar ────────────────────────────────────────────────────────────────

def test_l_empreinte_voyage_dans_le_bloc_encoded_et_se_relit(tmp_path):
    ba = _encoded(tmp_path)
    d = ba.to_dict()

    assert d["encoded"]["encoded_for"] == ba.encoded_for and "encoded_for" not in d.get("settings", {})
    again = BackgroundAsset.from_dict(d)
    assert again.encoded_for == ba.encoded_for and again.encoding_is_current()

    again.compression = BackgroundCompression(palettes_max=2)    # les réglages relus ne sont plus ceux du résultat
    assert not again.encoding_is_current()


def test_un_sidecar_d_avant_l_empreinte_est_tenu_pour_a_jour_et_ne_se_reencode_pas_a_l_ouverture(tmp_path):
    d = _encoded(tmp_path).to_dict()
    del d["encoded"]["encoded_for"]                              # un projet d'avant ce champ

    old = BackgroundAsset.from_dict(d)

    assert old.encoded_for == "" and old.encoding_is_current()
