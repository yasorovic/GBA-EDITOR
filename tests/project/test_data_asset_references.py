"""Les colonnes graphiques citent des assets, pas des éléments d'interface."""
import pytest

from core.models.background import BackgroundAsset
from core.models.sprite import SpriteAsset
from core.models.data_table import COLUMN_CHOICES, DataColumn, DataTable
from core.project import Project
from core.validator import ValidationContext, _check_data_column_types, _check_data_tables
from codegen.runtime_codegen.data_tables import reference_index, generate_data_tables_c


def test_les_types_proposes_et_la_lecture_des_anciennes_images():
    assert "image" not in COLUMN_CHOICES
    assert {"sprite", "background"} <= set(COLUMN_CHOICES)
    table = DataTable.from_dict({"columns": [{"name": "icon", "type": "image"}],
                                "rows": [{"icon": "hud_heart"}]})
    assert table.columns[0].type == "image"
    assert table.value(table.rows[0], table.columns[0]) == "hud_heart"
    assert DataColumn(type="sprite").default() == ""
    assert DataColumn(type="background").default() == ""


@pytest.fixture
def project(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    for name in ("Hero", "Enemy"):
        p.sprites.append(SpriteAsset(name=name))
    for name in ("Sky", "Forest"):
        p.backgrounds.append(BackgroundAsset(name=name))
    p.data_tables.append(DataTable(name="Graphics", columns=[
        DataColumn("actor", "sprite"), DataColumn("decor", "background")],
        rows=[{"actor": "Enemy", "decor": "Forest"}, {}]))
    return p


def test_les_choix_et_les_references_du_build_utilisent_les_catalogues(project):
    assert project.data_column_choices("sprite") == ["Hero", "Enemy"]
    assert project.data_column_choices("background") == ["Sky", "Forest"]
    ctx = ValidationContext(project)
    _check_data_column_types(ctx)
    _check_data_tables(ctx)
    assert not ctx._msgs
    index = reference_index(project)
    assert index["sprite"]["Enemy"] == 1
    assert index["background"]["Forest"] == 1
    code = generate_data_tables_c(project.data_tables, index)
    assert "{ 1, 1 }" in code
    assert "NOT FOUND" not in code
    assert "actor: no reference" in code
    project.data_tables[0].rows[0]["actor"] = "MissingSprite"
    ctx = ValidationContext(project)
    _check_data_tables(ctx)
    assert any('no sprite named "MissingSprite"' in m.message for m in ctx._msgs)


@pytest.mark.parametrize("kind,old,new", [("sprite", "Enemy", "Goblin"),
                                          ("background", "Forest", "Woods")])
def test_renommer_un_asset_repare_et_enregistre_les_cellules(project, kind, old, new):
    if kind == "sprite":
        project.rename_sprite(project.get_sprite(old), new)
        field = "actor"
    else:
        project.rename_background(project.get_background(old), new)
        field = "decor"
    table = project.data_tables[0]
    assert table.rows[0][field] == new
    project.data_tables.load()
    assert project.data_tables.get(table.name).rows[0][field] == new
