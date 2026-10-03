"""Le modèle FontAsset — recette de rendu, séparée des sources de police."""

from core.models.font_asset import FontAsset
from core.models.font import Font
from core.resources import asset_reconciliation
from core.project import Project
from core.font_metadata import _style_weight


def test_font_asset_conserve_les_sources_par_variante_et_la_recette():
    asset = FontAsset(
        name="dialog",
        sources={"regular": ["latin", "cjk"], "bold": ["latin_bold", "cjk"]},
        pixel_height=10,
        line_height=12,
        pixel_fit="grid_fit",
        hinting="light",
        raster_mode="dither",
        coverage_threshold=96,
        dither_pattern="bayer_4x4",
        offset_x=1,
        offset_y=-1,
        bg_color=(1, 2, 3),
        space_color=(4, 5, 6),
    )

    restored = FontAsset.from_dict(asset.to_dict())

    assert restored.source_names() == ["latin", "cjk"]
    assert restored.primary_source_name("bold") == "latin_bold"
    assert restored.source_names("italic") == []
    assert restored.pixel_height == 10
    assert restored.line_height == 12
    assert restored.pixel_fit == "grid_fit"
    assert restored.hinting == "light"
    assert restored.raster_mode == "dither"
    assert restored.coverage_threshold == 96
    assert restored.dither_pattern == "bayer_4x4"
    assert restored.key_colors() == [(1, 2, 3), (4, 5, 6)]


def test_font_asset_ecarte_les_choix_et_variantes_inconnus():
    asset = FontAsset.from_dict({
        "name": "dialog",
        "sources": {"regular": ["latin", "", 42], "oblique": ["latin"]},
        "pixel_height": 0,
        "line_height": -2,
        "pixel_fit": "invented",
        "hinting": "aggressive",
        "raster_mode": "lcd",
        "coverage_threshold": 999,
        "dither_pattern": "blue_noise",
    })

    assert asset.source_names() == ["latin"]
    assert asset.pixel_height == 1
    assert asset.line_height == 1
    assert asset.pixel_fit == "auto"
    assert asset.hinting == "normal"
    assert asset.raster_mode == "binary"
    assert asset.coverage_threshold == 255
    assert asset.dither_pattern == "none"


def test_project_persists_font_assets_dans_leur_dossier_projet(tmp_path):
    project = Project(tmp_path)
    project.font_assets.append(FontAsset(name="dialog", sources={"regular": ["latin"]}))
    project.font_assets.save_all()

    assert (tmp_path / "project" / "fonts_assets" / "dialog.json").exists()

    reopened = Project(tmp_path)
    reopened.font_assets.load()

    assert reopened.get_font_asset("dialog").source_names() == ["latin"]


def test_renommer_une_source_repare_les_chaines_de_couverture(tmp_path):
    project = Project(tmp_path)
    source = Font(name="latin")
    asset = FontAsset(name="dialog", sources={"regular": ["latin", "cjk"]})
    project.fonts.append(source)
    project.font_assets.append(asset)

    project.rename_font(source, "latin_ui")

    assert asset.source_names() == ["latin_ui", "cjk"]


def test_deposer_une_source_vectorielle_invalide_est_refusee_sans_rasteriser(tmp_path):
    project = Project(tmp_path)
    source = tmp_path / "assets" / "fonts" / "ComicNeue.ttf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not a real font: discovery must not rasterize")

    warning = asset_reconciliation.sync_font_file(project, source)
    font = project.fonts.get("ComicNeue")

    assert "import failed" in warning
    assert font is None


def test_reconciliation_regroupe_toutes_les_faces_sans_ecraser_le_regular(tmp_path):
    project = Project(tmp_path)
    project.fonts.items = [
        Font(name="Comic-Regular", source_format="ttf", family_name="Comic Neue", weight=400),
        Font(name="Comic-Bold", source_format="ttf", family_name="Comic Neue", weight=700),
        Font(name="Comic-Italic", source_format="ttf", family_name="Comic Neue", weight=400, italic=True),
        Font(name="Comic-Light", source_format="ttf", family_name="Comic Neue", weight=300),
    ]

    asset_reconciliation.reconcile_font_assets(project)
    asset = project.get_font_asset("Comic Neue")

    assert asset.source_names() == ["Comic-Regular"]
    assert [(face.source_name, face.weight, face.italic) for face in asset.faces] == [
        ("Comic-Light", 300, False), ("Comic-Regular", 400, False),
        ("Comic-Italic", 400, True), ("Comic-Bold", 700, False),
    ]


def test_reconciliation_cree_un_asset_pour_chaque_source_bitmap(tmp_path):
    project = Project(tmp_path)
    project.fonts.items = [Font(name="ascii", source_format="png")]

    asset_reconciliation.reconcile_font_assets(project)

    assert project.get_font_asset("ascii").source_names() == ["ascii"]


def test_reconciliation_retire_les_faces_et_la_source_primaire_supprimees(tmp_path):
    project = Project(tmp_path)
    project.fonts.items = [
        Font(name="Comic-Regular", source_format="ttf", family_name="Comic Neue", weight=400),
        Font(name="Comic-Bold", source_format="ttf", family_name="Comic Neue", weight=700),
    ]
    asset_reconciliation.reconcile_font_assets(project)
    project.fonts.soft_delete(project.fonts.get("Comic-Regular"))

    asset_reconciliation.reconcile_font_assets(project)
    asset = project.get_font_asset("Comic Neue")

    assert [face.source_name for face in asset.faces] == ["Comic-Bold"]
    assert asset.sources["regular"] == []


def test_style_typographique_secourt_le_poids_dune_face_sans_os2():
    assert _style_weight("Light Italic") == 300
    assert _style_weight("Extra Bold") == 800
    assert _style_weight("Regular") == 400
