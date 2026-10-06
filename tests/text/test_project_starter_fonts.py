"""Les polices livrées par le starter Basic sont prêtes dès le premier écran."""
from __future__ import annotations

from core.project import Project


def test_basic_starter_provisions_three_ready_to_use_font_assets(tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")

    assert {(font.name, font.source_format) for font in project.fonts} == {
        ("Font8x8 Latin", "png"),
        ("misaki-gothic", "ttf"),
        ("unifont-jp-17.0.04", "otf"),
    }
    assert {
        (asset.name, tuple(asset.source_names()), asset.pixel_height, asset.line_height)
        for asset in project.font_assets
    } == {
        ("Font8x8 Latin", ("Font8x8 Latin",), 8, 8),
        ("Misaki Gothic 8", ("misaki-gothic",), 8, 8),
        ("GNU Unifont JP 16", ("unifont-jp-17.0.04",), 16, 16),
    }


def test_basic_starter_copies_font_license_notices(tmp_path):
    project = Project.create(tmp_path / "MyGame", "MyGame")

    licenses = project.project_dir / "licenses"
    assert {path.name for path in licenses.iterdir()} == {
        "Font8x8.txt", "GNU-Unifont-JP.txt", "Misaki.txt",
    }
