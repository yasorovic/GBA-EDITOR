"""Ce que l'éditeur ouvre quand on lui passe un fichier au lancement (cf. `core/launch_target`)."""
from __future__ import annotations

from core.launch_target import LaunchTarget, find_project_root, parse_launch_arguments
from core.project import Project


def _project(tmp_path):
    return Project.create(tmp_path / "Game", "Game")


def test_a_manifest_opens_its_folder(tmp_path):
    project = _project(tmp_path)
    manifest = project.root / "Game.project"
    assert parse_launch_arguments([str(manifest)]) == LaunchTarget(project.root)


def test_an_asset_opens_the_project_that_holds_it_and_names_the_file(tmp_path):
    project = _project(tmp_path)
    deep = project.user_library_dir / "Persos" / "Heros"
    deep.mkdir(parents=True)
    sidecar = deep / "Hero.sprite"
    sidecar.write_text("{}", encoding="utf-8")

    target = parse_launch_arguments([str(sidecar)])

    assert target == LaunchTarget(project.root.resolve(), sidecar.resolve())


def test_a_script_opens_like_an_asset(tmp_path):
    project = _project(tmp_path)
    script = project.user_library_dir / "hero.lua"
    script.write_text("-- hero\n", encoding="utf-8")

    assert parse_launch_arguments([str(script)]).asset == script.resolve()


def test_a_file_outside_any_project_or_of_another_kind_is_ignored(tmp_path):
    stray = tmp_path / "Hero.sprite"
    stray.write_text("{}", encoding="utf-8")
    notes = _project(tmp_path).user_library_dir / "notes.txt"
    notes.write_text("x", encoding="utf-8")

    assert find_project_root(stray) is None
    assert parse_launch_arguments([str(stray), str(notes), "--flag", str(tmp_path / "missing.sprite")]) is None
