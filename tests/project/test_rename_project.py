"""Renommer le projet renomme son manifeste `<Nom>.project`, le dossier ne bouge pas."""
from pathlib import Path

from core.project import Project
from core.project_paths import LEGACY_MANIFEST_NAME


def test_rename_moves_the_manifest_and_keeps_the_folder(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")

    applied = project.rename_project("  Platformer ")

    assert applied == "Platformer"
    assert project.settings.name == "Platformer"
    assert [p.name for p in project.root.glob("*.project")] == ["Platformer.project"]
    assert Project.open(project.root).settings.name == "Platformer"


def test_rename_refuses_a_name_the_disk_cannot_hold(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")

    for bad in ("", "   ", "a/b", "what?", "trailing."):
        assert project.rename_project(bad) == "Game"

    assert [p.name for p in project.root.glob("*.project")] == ["Game.project"]


def test_rename_refuses_a_name_already_taken_by_another_manifest(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    (project.root / "Other.project").write_text("{}", encoding="utf-8")

    assert project.rename_project("Other") == "Game"
    assert project.settings.name == "Game"
    assert (project.root / "Game.project").exists()


def test_rename_changes_only_the_case(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")

    assert project.rename_project("GAME") == "GAME"
    assert [p.name for p in project.root.glob("*.project")] == ["GAME.project"]


def test_rename_a_legacy_project_writes_the_new_manifest_and_drops_project_json(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    manifest = project.root / "Game.project"
    manifest.rename(project.root / LEGACY_MANIFEST_NAME)

    assert project.rename_project("Renamed") == "Renamed"
    assert [p.name for p in project.root.glob("*.project")] == ["Renamed.project"]
    assert not (project.root / LEGACY_MANIFEST_NAME).exists()
