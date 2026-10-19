"""Tout ce que l'auteur manipule vit dans assets/ ; project/ n'est plus qu'à l'éditeur."""
import importlib.util
import json
from pathlib import Path

import pytest

from core import disk_tree
from core.project import Project

ROOT = Path(__file__).resolve().parents[2]


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_project_to_assets", ROOT / "tools" / "migrate_project_to_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old_layout(root: Path) -> None:
    project = root / "project"
    for folder in ("scenes", "prefab", "ui_layouts", "music_boxes", "data", "fonts_assets", "editor", "licenses"):
        (project / folder).mkdir(parents=True)
    (project / "scenes" / "Level.json").write_text("{}", encoding="utf-8")
    (project / "data" / "Items.json").write_text("{}", encoding="utf-8")
    (project / "editor" / "scene-tree.json").write_text("{}", encoding="utf-8")
    (project / "licenses" / "OFL.txt").write_text("x", encoding="utf-8")
    (project / "README.md").write_text("x", encoding="utf-8")
    for name in ("texts.json", "texts_fr.json", "variables.json"):
        (project / name).write_text("{}", encoding="utf-8")
    (root / "assets").mkdir()


def test_a_new_project_keeps_nothing_it_edits_under_project(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    project.load()
    for directory in ((project.assets_dir / "scenes"), (project.assets_dir / "prefab"), (project.assets_dir / "ui_layouts"), (project.assets_dir / "music_boxes"),
                      (project.assets_dir / "jingle_boxes"), (project.assets_dir / "sound_boxes"), (project.assets_dir / "data")):
        assert directory.parent == project.assets_dir, directory
    assert (project.assets_dir / "fonts" / "fonts_assets") == (project.assets_dir / "fonts") / "fonts_assets"
    assert project.texts_file.parent == project.variables_file.parent == project.assets_dir
    assert project.translation_file("fr") == project.assets_dir / "texts_fr.json"

    project.save_texts()
    project.save_variables()
    on_disk = {p.name for p in project.project_dir.iterdir()} if project.project_dir.exists() else set()
    assert not on_disk & {"scenes", "prefab", "ui_layouts", "texts.json", "variables.json", "data", "fonts_assets"}
    assert (project.assets_dir / "texts.json").is_file() and (project.assets_dir / "variables.json").is_file()


def test_the_migration_moves_everything_the_author_edits_and_nothing_else(tmp_path: Path):
    migrate = _migration()
    _old_layout(tmp_path)

    assert migrate.migrate(tmp_path, dry_run=True) == 9
    assert (tmp_path / "project" / "scenes" / "Level.json").exists()           # le dry-run ne touche à rien

    assert migrate.migrate(tmp_path, dry_run=False) == 9
    assets, project = tmp_path / "assets", tmp_path / "project"
    assert (assets / "scenes" / "Level.json").is_file() and (assets / "data" / "Items.json").is_file()
    assert all((assets / name).is_file() for name in ("texts.json", "texts_fr.json", "variables.json"))
    assert (assets / "prefab").is_dir() and (assets / "ui_layouts").is_dir() and (assets / "fonts_assets").is_dir()
    assert sorted(p.name for p in project.iterdir()) == ["README.md", "editor", "licenses"]   # ce qui n'est pas à l'auteur
    assert migrate.migrate(tmp_path, dry_run=False) == 0                       # idempotent


def test_the_migration_never_overwrites_and_says_why(tmp_path: Path):
    migrate = _migration()
    _old_layout(tmp_path)
    (tmp_path / "assets" / "scenes").mkdir()
    (tmp_path / "assets" / "scenes" / "Level.json").write_text('{"mine": true}', encoding="utf-8")

    with pytest.raises(SystemExit) as refused:
        migrate.migrate(tmp_path, dry_run=False)
    assert "scenes/Level.json" in str(refused.value).replace("\\", "/") and "already exists" in str(refused.value)
    assert json.loads((tmp_path / "assets" / "scenes" / "Level.json").read_text()) == {"mine": True}
    assert (tmp_path / "project" / "scenes" / "Level.json").exists()           # rien n'a bougé


def test_the_disk_tab_knows_what_the_author_creates_in_the_editor(tmp_path: Path):
    from core.models.scene import Scene
    project = Project.create(tmp_path / "Game", "Game")
    project.load()
    level = Scene(name="Level")
    project.scenes.append(level)
    project.save_scene(level)
    project.save_texts()
    project.save_variables()
    project.load_all_resources()

    nodes = {n.path.relative_to(project.assets_dir).as_posix(): n
             for n in disk_tree.build_disk_tree(project).walk() if n.path != project.assets_dir}
    assert (nodes["Level.scene"].kind, nodes["Level.scene"].family) == (disk_tree.ASSET, "scenes")
    assert (nodes["texts.json"].kind, nodes["texts.json"].family) == (disk_tree.ASSET, "texts")
    assert (nodes["variables.json"].kind, nodes["variables.json"].family) == (disk_tree.ASSET, "variables")
