"""Les palettes d'un fond sont des RÉFÉRENCES au catalogue : les ajoutées (« + ») et les overrides se retrouvent après un
encodage, la peinture suit leur position, et rien n'est copié.

Principe : l'encodage refait les palettes DÉRIVÉES du PNG ; ce que l'auteur a cité (par nom) est un réglage, que
`resolve_palettes` remet par-dessus à chaque fois.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from core.bg_import import encode_by_mode
from core.models.background import BackgroundAsset, BackgroundCompression
from core.resources.asset_reconciliation import apply_bg_encoding, catalogue_lookup

GREEN = [0, 0x03E0] + [0] * 14
BLUE = [0, 0x7C00] + [0] * 14
CATALOGUE = {"Green": GREEN, "Blue": BLUE}


def _lookup(name):
    return list(CATALOGUE[name]) if name in CATALOGUE else None


def _photo(tmp_path: Path, size=(32, 32)) -> Path:
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256)
    path = tmp_path / "photo.png"
    img.save(path)
    return path


def _encode(ba, path, palettes_max, lookup=_lookup):
    ba.compression = BackgroundCompression(palettes_max=palettes_max)
    apply_bg_encoding(ba, encode_by_mode(path, "tiled4", compression=ba.compression), lookup)


def _fond(tmp_path, palettes_max=1):
    path = _photo(tmp_path)
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout("tiled4")
    _encode(ba, path, palettes_max)
    return ba, path


# ── Ajouter par référence ─────────────────────────────────────────────────────

def test_plus_ajoute_une_reference_au_catalogue_et_ses_couleurs_en_cache():
    ba = BackgroundAsset(name="x")
    bank = ba.add_palette_ref("Green", GREEN)

    assert ba.added_palettes == ["Green"] and bank == ba.derived_count() + 0 == 0
    assert ba.palettes[bank] == GREEN


def test_les_seize_banques_se_partagent_entre_derivees_et_ajoutees():
    ba = BackgroundAsset(name="x")
    ba.source_palettes = [[0] * 16 for _ in range(15)]
    ba.palettes = [list(p) for p in ba.source_palettes]

    assert ba.add_palette_ref("Green", GREEN) == 15
    assert ba.add_palette_ref("Blue", BLUE) == -1                      # la 17ᵉ n'existe pas


def test_remplacer_une_palette_ajoutee_garde_la_peinture_a_sa_position():
    ba = BackgroundAsset(name="x")
    bank = ba.add_palette_ref("Green", GREEN)
    ba.tile_paint = {(0, 0): (1, 0)}

    assert ba.replace_added_palette(bank, "Blue", BLUE)

    assert ba.added_palettes == ["Blue"] and ba.palettes[bank] == BLUE and ba.tile_paint == {(0, 0): (1, 0)}
    assert not ba.replace_added_palette(5, "Blue", BLUE)               # pas une palette ajoutée


# ── Un encodage ne les perd pas ───────────────────────────────────────────────

def test_un_nouvel_encodage_garde_les_palettes_ajoutees_et_la_peinture_suit_leur_position(tmp_path):
    ba, path = _fond(tmp_path, palettes_max=1)
    ba.add_palette_ref("Green", GREEN)
    ba.tiles_w = ba.tiles_h = 4
    ba.tile_paint = {(1, 1): (1, 0)}
    derived_before = ba.derived_count()
    assert ba.painted_cells()[(1, 1)] == (1, derived_before)

    _encode(ba, path, palettes_max=4)                                  # plus de palettes dérivées qu'avant

    assert ba.derived_count() > derived_before
    assert ba.added_palettes == ["Green"] and ba.palettes[-1] == GREEN       # elle est toujours là, couleurs comprises
    assert ba.painted_cells()[(1, 1)] == (1, ba.derived_count())             # la peinture a suivi : même palette, autre banque
    assert ba.tile_paint == {(1, 1): (1, 0)}                                 # et rien n'a bougé dans le réglage


def test_un_override_se_reapplique_apres_un_encodage(tmp_path):
    ba, path = _fond(tmp_path, palettes_max=2)
    ba.palette_overrides = {0: "Blue"}

    _encode(ba, path, palettes_max=2)

    assert ba.palettes[0] == BLUE and ba.source_palettes[0] != BLUE            # la couleur du PNG reste restaurable
    assert ba.palette_overrides == {0: "Blue"}


def test_un_override_sur_une_palette_derivee_qui_n_existe_plus_est_leve_et_dit(tmp_path):
    ba, path = _fond(tmp_path, palettes_max=4)
    assert ba.derived_count() > 1
    ba.palette_overrides = {ba.derived_count() - 1: "Blue"}

    _encode(ba, path, palettes_max=1)                                          # un seul groupe de couleurs

    assert ba.palette_overrides == {} and ba.diagnostics["palette_overrides_dropped"]


def test_une_banque_disparue_du_catalogue_garde_ses_dernieres_couleurs(tmp_path):
    ba, path = _fond(tmp_path)
    ba.add_palette_ref("Green", GREEN)
    kept = ba.added_palette_colors()

    _encode(ba, path, palettes_max=1, lookup=lambda name: None)                # le catalogue ne connaît plus « Green »

    assert ba.added_palettes == ["Green"] and ba.added_palette_colors() == kept


def test_un_fond_8bpp_ou_bitmap_n_a_qu_une_palette_ni_ajoutees_ni_overrides(tmp_path):
    path = _photo(tmp_path)
    ba = BackgroundAsset(name="x", asset="x.png")
    ba.choose_layout("tiled8")
    ba.added_palettes, ba.palette_overrides = ["Green"], {0: "Blue"}
    apply_bg_encoding(ba, encode_by_mode(path, "tiled8"), _lookup)

    assert len(ba.palettes) == 1 and ba.palettes == ba.source_palettes
    assert ba.added_palettes == ["Green"]                                      # le réglage reste, pour le retour en 4bpp


# ── Le sidecar ────────────────────────────────────────────────────────────────

def test_les_references_et_la_peinture_sont_des_reglages_le_cache_est_un_resultat(tmp_path):
    ba, _path = _fond(tmp_path)
    ba.add_palette_ref("Green", GREEN)
    ba.palette_overrides = {0: "Blue"}
    ba.tile_paint = {(0, 0): (1, 0)}
    d = ba.to_dict()

    assert d["settings"]["added_palettes"] == ["Green"] and d["settings"]["palette_overrides"] == {"0": "Blue"}
    assert d["settings"]["tile_paint"] == {"0,0": [1, 0]}
    assert "palette_overrides" not in d["encoded"] and "added_palettes" not in d["encoded"]
    assert "palettes" in d["encoded"]                                          # le cache résolu, ce que le build lit

    again = BackgroundAsset.from_dict(d)
    assert again.added_palettes == ["Green"] and again.palette_overrides == {0: "Blue"}
    assert again.palettes == ba.palettes and again.painted_cells() == ba.painted_cells()


def test_un_sidecar_d_avant_lit_son_palette_overrides_a_plat():
    ba = BackgroundAsset.from_dict({"name": "x", "palette_overrides": {"0": "Blue"}})

    assert ba.palette_overrides == {0: "Blue"} and ba.to_dict()["settings"]["palette_overrides"] == {"0": "Blue"}


# ── Le projet : renommage, usages, édition d'une banque ───────────────────────

def _project(tmp_path: Path):
    from core.project import Project
    p = Project.create(tmp_path / "Jeu", "Jeu")
    (p.palettes_dir / "Night.hex").write_text("#000000\n#102030\n#405060\n", encoding="utf-8")
    p = Project.open(p.root)
    ba = BackgroundAsset(name="sky")
    night = p.palettes.get("Night")
    ba.add_palette_ref("Night", night.colors)
    p.backgrounds.append(ba)
    return p, ba, night


def test_renommer_une_banque_repare_les_fonds_qui_la_citent(tmp_path):
    p, ba, night = _project(tmp_path)
    assert [(u.kind, u.name) for u in p.palette_usages("Night")] == [("background", "sky")]

    p.rename_palette(night, "Midnight")

    assert ba.added_palettes == ["Midnight"]
    assert [(u.kind, u.name) for u in p.palette_usages("Midnight")] == [("background", "sky")]
    assert p.palette_usages("Night") == []


def test_editer_une_banque_met_a_jour_les_fonds_qui_la_citent(tmp_path):
    from core.command_dispatcher import CommandDispatcher
    p, ba, night = _project(tmp_path)
    night.colors[1] = 0x7FFF
    dispatcher = CommandDispatcher()
    dispatcher._project = p

    dispatcher._refresh_background_palettes("Night")

    assert ba.palettes[0][1] == 0x7FFF and ba.added_palettes == ["Night"]      # une référence, pas une copie


def test_le_validateur_signale_une_banque_citee_qui_n_existe_plus(tmp_path):
    from core.validator import validate_project
    p, ba, night = _project(tmp_path)
    ba.added_palettes.append("Ghost")
    ba.palettes.append([0] * 16)
    p.backgrounds.save(ba)                                  # `validate_project` relit tout depuis le disque

    warnings = [str(m) for m in validate_project(p)[0]]

    assert any("sky" in w and "Ghost" in w and "no longer in the palette catalogue" in w for w in warnings)
    assert not any("Night" in w and "no longer" in w for w in warnings)


def test_catalogue_lookup_rend_les_couleurs_d_une_banque_ou_rien(tmp_path):
    p, _ba, night = _project(tmp_path)
    lookup = catalogue_lookup(p)

    assert lookup("Night") == list(night.colors) and lookup("Nope") is None
    assert catalogue_lookup(None) is None
