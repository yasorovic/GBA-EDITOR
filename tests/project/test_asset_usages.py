"""Avant de supprimer un asset, on dit ce qui le cite encore."""
from pathlib import Path

from PIL import Image

from asset_fixtures import create
from core.asset_usages import usages
from core.models.components import SpriteComponent
from core.models.scene import Actor, Prefab
from core.models.background import BackgroundLayer
from core.project import Project


def _project(tmp_path: Path) -> Project:
    p = Project.create(tmp_path / "Jeu", "Jeu")
    p = Project.open(p.root)
    p.load_all_resources()
    return p


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (200, 30, 30)).save(path)
    return path


def test_a_sprite_is_reported_with_the_actors_and_prefabs_that_use_it(tmp_path: Path):
    p = _project(tmp_path)
    hero = create(p, "sprites", _png(p.assets_dir / "Art" / "hero.png"))
    actor = Actor(name="Hero")
    actor.components.append(SpriteComponent(sprite_name="hero"))
    p.scenes[0].actors.append(actor)
    prefab = Prefab(name="Crate")
    prefab.components.append(SpriteComponent(sprite_name="hero"))
    p.prefabs.append(prefab)

    found = usages(p, "sprites", hero)

    assert found == [f'scene "{p.scenes[0].name}": actor "Hero"', 'prefab "Crate"']


def test_a_background_is_reported_with_the_layers_that_show_it(tmp_path: Path):
    p = _project(tmp_path)
    sky = create(p, "backgrounds", _png(p.assets_dir / "Art" / "sky.png"))
    p.scenes[0].background_layers.append(BackgroundLayer(background_name="sky", bg_slot=2))

    assert usages(p, "backgrounds", sky) == [f'scene "{p.scenes[0].name}": background layer 2']


def test_a_name_in_quotes_in_a_script_is_a_use_wherever_the_script_lives(tmp_path: Path):
    from core.models.audio import Sfx
    p = _project(tmp_path)
    boom = Sfx(name="boom")
    p.sfx.append(boom)
    script = p.assets_dir / "Levels" / "Hero.lua"
    script.parent.mkdir(parents=True)
    script.write_text('function on_update()\n    sfx.play("boom")\nend\n', encoding="utf-8")
    (p.assets_dir / "Levels" / "Other.lua").write_text("function on_update()\nend\n", encoding="utf-8")

    assert usages(p, "sfx", boom) == ["script Hero.lua"]


def test_an_unused_asset_has_no_usage(tmp_path: Path):
    p = _project(tmp_path)
    hero = create(p, "sprites", _png(p.assets_dir / "Art" / "hero.png"))
    assert usages(p, "sprites", hero) == []
