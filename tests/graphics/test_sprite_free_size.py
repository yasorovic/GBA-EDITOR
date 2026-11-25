"""Tailles de frame libres : la taille DESSINÉE est un multiple de 8 quelconque
(jusqu'à 64), le matériel lit la forme OAM qui la contient (padding au build).

Le runtime ne change pas (toujours un OBJ par acteur) : on vérifie que le modèle
expose bien les deux tailles, et que le build compose la feuille à la taille OAM
en laissant le dessin en haut à gauche."""
from PIL import Image

from core.models.sprite import (
    AnimFrame, AnimState, SpriteAsset, StateDirection, TilePlacement,
    oam_fit, snap_frame_size,
)
from codegen.grit_conversion import build_sprite_sheet_indexed


def test_oam_fit_complete_vers_la_plus_petite_forme_contenante():
    # Déjà une forme OAM : inchangé.
    assert oam_fit(8, 32) == (8, 32)
    assert oam_fit(64, 64) == (64, 64)
    # Carré non légal -> carré supérieur.
    assert oam_fit(24, 24) == (32, 32)
    # Large non légal -> le plus petit large contenant.
    assert oam_fit(48, 32) == (64, 32)
    assert oam_fit(40, 16) == (64, 32)
    # Haut non légal -> le plus petit haut contenant.
    assert oam_fit(8, 24) == (8, 32)


def test_snap_frame_size_ramene_au_multiple_de_8_borne():
    assert snap_frame_size(21) == 24    # arrondi au plus proche multiple de 8
    assert snap_frame_size(19) == 16
    assert snap_frame_size(3) == 8      # plancher
    assert snap_frame_size(999) == 64   # plafond


def test_les_proprietes_separent_dessine_et_padded():
    sp = SpriteAsset(name="hero", asset="hero.png", frame_w=24, frame_h=24)
    # Grille DESSINÉE (canvas) : 3×3.
    assert (sp.draw_cols, sp.draw_rows) == (3, 3)
    # Forme OAM (matériel / VRAM) : 32×32 = 16 tuiles.
    assert sp.oam_dims == (32, 32)
    assert (sp.oam_w, sp.oam_h) == (32, 32)
    assert (sp.tile_w, sp.tile_h) == (4, 4)
    assert sp.tiles_per_frame == 16
    assert (sp.oam_shape, sp.oam_size) == (0, 2)   # carré 32×32


def test_forme_oam_large_depuis_une_taille_libre():
    sp = SpriteAsset(name="wide", asset="wide.png", frame_w=48, frame_h=32)
    assert sp.oam_dims == (64, 32)
    assert (sp.oam_shape, sp.oam_size) == (1, 3)   # large 64×32
    assert sp.tiles_per_frame == 8 * 4


def _sprite_24(tmp_path):
    """Un sprite 24×24 (3×3 tuiles) et son PNG source indexé plein."""
    png = tmp_path / "src.png"
    img = Image.new("P", (24, 24), 0)
    img.putpalette([0, 0, 0, 255, 0, 0, 0, 255, 0] + [0] * (256 * 3 - 9))
    # Remplit d'index 1 (rouge) pour distinguer dessin et padding.
    for y in range(24):
        for x in range(24):
            img.putpixel((x, y), 1)
    img.save(png)
    tiles = [TilePlacement(src_col=c, src_row=r, dst_col=c, dst_row=r)
             for r in range(3) for c in range(3)]
    sp = SpriteAsset(
        name="hero", asset="src.png", frame_w=24, frame_h=24,
        states=[AnimState(name="idle",
                          directions=[StateDirection(dir=0, frames=[AnimFrame(tiles=tiles)])])],
    )
    return png, sp


def test_le_build_compose_la_feuille_a_la_taille_oam(tmp_path):
    png, sp = _sprite_24(tmp_path)
    logs = []
    out = build_sprite_sheet_indexed(png, sp, tmp_path, lambda *a, **k: logs.append(a))
    assert out is not None and out.exists()
    sheet = Image.open(out)
    # Une frame, feuille complétée à la forme OAM 32×32 (pas 24×24).
    assert sheet.size == (32, 32)
    # Le dessin reste en haut à gauche...
    assert sheet.getpixel((0, 0)) == 1
    assert sheet.getpixel((23, 23)) == 1
    # ...et le padding est transparent (index 0).
    assert sheet.getpixel((24, 0)) == 0
    assert sheet.getpixel((31, 31)) == 0
