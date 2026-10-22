"""L'extension d'un sidecar dit son type : une table unique, sans collision, et la migration qui y mène."""
import importlib.util
import json
from pathlib import Path

import pytest

from core.models import asset_extensions
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.resource import Resource
from core.models.sprite import IMAGE_FILE_EXTS
from core.project import Project

ROOT = Path(__file__).resolve().parents[2]


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_sidecar_extensions", ROOT / "tools" / "migrate_sidecar_extensions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stored_models() -> list[type]:
    """Chaque classe de modèle qui a choisi une extension à elle."""
    def walk(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)
    return [c for c in walk(Resource) if c.sidecar_extension != Resource.sidecar_extension]


def test_every_stored_model_has_its_own_extension_and_the_table_lists_them_all():
    models = _stored_models()
    extensions = [m.sidecar_extension for m in models]

    assert len(extensions) == len(set(extensions)), "two models share an extension"
    assert set(extensions) == asset_extensions.ALL_EXTENSIONS
    assert all(e.startswith(".") and e == e.lower() and "." not in e[1:] for e in extensions)


def test_no_sidecar_extension_is_the_extension_of_a_source_format():
    sources = IMAGE_FILE_EXTS | SFX_FILE_EXTS | MUSIC_FILE_EXTS | FONT_FILE_EXTS | {".hex", ".pal", ".lua", ".json"}
    assert asset_extensions.ALL_EXTENSIONS.isdisjoint(sources)


def test_the_store_of_every_family_writes_and_finds_its_own_extension(tmp_path: Path):
    project = Project(tmp_path)
    for store in project._resource_stores():
        assert store.suffix == store.cls.sidecar_extension
        assert store.index.suffix == store.cls.sidecar_extension
        assert store._path("x").suffix == store.cls.sidecar_extension


def test_every_extension_in_the_table_is_one_a_project_store_uses(tmp_path: Path):
    project = Project(tmp_path)
    used = {store.cls.sidecar_extension for store in project._resource_stores()}
    assert used == set(asset_extensions.FAMILY_EXTENSIONS.values())


def _old_project(root: Path) -> None:
    for folder, name in (("sprites", "Hero"), ("scenes", "Level"), ("palettes", "Night"),
                         ("fonts_assets", "Dialog"), ("sfx", "deep/Boom")):
        path = root / "assets" / folder / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": Path(name).name}), encoding="utf-8")
    (root / "assets" / "palettes" / "Night.hex").write_text("000000\n", encoding="utf-8")
    for kept in ("texts.json", "texts_fr.json", "variables.json"):
        (root / "assets" / kept).write_text("{}", encoding="utf-8")
    (root / "project" / "editor").mkdir(parents=True)
    (root / "project" / "editor" / "scene-tree.json").write_text("{}", encoding="utf-8")


def test_the_migration_renames_sidecars_wherever_they_are_and_leaves_the_rest(tmp_path: Path):
    _old_project(tmp_path)

    assert _migration().migrate(tmp_path, dry_run=False) == 5

    assets = tmp_path / "assets"
    for expected in ("sprites/Hero.sprite", "scenes/Level.scene", "palettes/Night.palette",
                     "fonts_assets/Dialog.fontasset", "sfx/deep/Boom.sfx", "palettes/Night.hex"):
        assert (assets / expected).is_file(), expected
    assert json.loads((assets / "sprites" / "Hero.sprite").read_text()) == {"name": "Hero"}   # le contenu ne bouge pas
    for kept in ("texts.json", "texts_fr.json", "variables.json"):
        assert (assets / kept).is_file(), kept
    assert (tmp_path / "project" / "editor" / "scene-tree.json").is_file()
    assert sorted(p.name for p in assets.rglob("*.json")) == ["texts.json", "texts_fr.json", "variables.json"]
    assert _migration().migrate(tmp_path, dry_run=False) == 0                                  # idempotent


def test_the_migration_dry_run_touches_nothing(tmp_path: Path):
    _old_project(tmp_path)
    assert _migration().migrate(tmp_path, dry_run=True) == 5
    assert (tmp_path / "assets" / "sprites" / "Hero.json").is_file()
    assert not (tmp_path / "assets" / "sprites" / "Hero.sprite").exists()


def test_the_migration_refuses_to_overwrite_and_renames_nothing(tmp_path: Path):
    _old_project(tmp_path)
    (tmp_path / "assets" / "scenes" / "Level.scene").write_text('{"mine": true}', encoding="utf-8")

    with pytest.raises(SystemExit, match="Level.scene already exists"):
        _migration().migrate(tmp_path, dry_run=False)

    assert (tmp_path / "assets" / "sprites" / "Hero.json").is_file()                           # rien n'a bougé
    assert json.loads((tmp_path / "assets" / "scenes" / "Level.scene").read_text()) == {"mine": True}


def test_a_migrated_project_opens_with_everything_it_had(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    project.load()
    from core.models.scene import Scene
    project.scenes.save(Scene(name="Level"))
    project.save()
    assert (project.user_library_dir / "Level.scene").is_file()
    assert not list(project.user_library_dir.glob("Level.json"))

    reopened = Project.open(project.root)
    reopened.load_all_resources()
    assert reopened.scenes.get("Level") is not None
