"""Les références audio des tables suivent la banque filtrée, pas le catalogue."""
import pytest

from codegen.grit_conversion import referenced_sound_names, resolve_sound_assets
from codegen.rom_build import BuildWorker
from codegen.runtime_codegen.data_tables import reference_index
from core.models.audio import Music, Sfx
from core.models.data_table import DataColumn, DataTable
from core.project import Project


@pytest.fixture
def project(tmp_path):
    p = Project.create(tmp_path / "Game", "Game")
    source = p.assets_dir / "audio.wav"
    source.write_bytes(b"audio")  # La résolution ne décode pas les fichiers.
    for store, cls in ((p.sfx, Sfx), (p.music, Music)):
        for name in ("Unused", "First", "Missing", "Second"):
            store.append(cls(name=name, asset="missing.wav" if name == "Missing" else p.asset_rel(source)))
    p.data_tables.append(DataTable(name="Sounds", columns=[
        DataColumn("effect", "sfx"), DataColumn("track", "music")], rows=[
        {"effect": " Second ", "track": "Second"},
        {"effect": "First", "track": " First "},
        {"effect": "Missing", "track": "Missing"}, {}]))
    return p


def test_table_only_references_are_kept_and_unused_audio_is_removed(project):
    assert referenced_sound_names(project) == ({"First", "Second", "Missing"},) * 2
    assets = resolve_sound_assets(project)
    for kind in ("sfx", "music"):
        assert [item.name for item, _ in assets[kind]] == ["First", "Second"]
    assert {(kind, name) for kind, name, _ in assets["skipped"]} == {
        ("sfx", "Unused"), ("music", "Unused")}


def test_audio_indices_match_the_filtered_bank_and_missing_files_are_silent(project):
    index = reference_index(project)
    for kind in ("sfx", "music"):
        assert index[kind]["First"] == 0
        assert index[kind]["Second"] == 1
        assert index[kind]["Missing"] == -1


def test_build_writes_tables_with_the_same_audio_order_as_mmutil(project):
    assets = resolve_sound_assets(project)
    # Un autre ordre rend visible un oubli de transmettre la banque à l'émetteur.
    for kind in ("sfx", "music"):
        assets[kind].reverse()
    worker = BuildWorker(project, None)
    worker._write_project_data_tables(project, assets)
    code = (project.src_dir / "data_tables.c").read_text(encoding="utf-8")
    assert "{ 0, 0 },   /* 1 : effect = Second, track = Second */" in code
    assert "{ 1, 1 },   /* 2 : effect = First, track = First */" in code
    assert "{ -1, -1 }" in code
    assert "NOT FOUND" not in code


def test_an_empty_bank_does_not_fall_back_to_catalogue_indices(project):
    index = reference_index(project, {"sfx": [], "music": []})
    assert index["sfx"]["Second"] == index["music"]["Second"] == -1
