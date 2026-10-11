"""disk_locate : de l'acteur au fichier d'asset que « Localiser dans Disk » doit montrer."""
from types import SimpleNamespace

from core import disk_locate
from core.models.components import SpriteComponent


def _actor(prefab=None, sprite=None, active=True):
    comps = [SpriteComponent(sprite_name=sprite, active=active)] if sprite is not None else []
    return SimpleNamespace(prefab_name=prefab, components=comps)


def test_a_prefab_instance_targets_its_prefab():
    assert disk_locate.target_of(_actor(prefab="Hero", sprite="hero_sprite")) == ("prefabs", "Hero")


def test_a_plain_actor_targets_the_sprite_it_displays():
    assert disk_locate.target_of(_actor(sprite="hero_sprite")) == ("sprites", "hero_sprite")


def test_an_actor_without_displayed_sprite_targets_nothing():
    assert disk_locate.target_of(_actor()) is None
    assert disk_locate.target_of(_actor(sprite="hero_sprite", active=False)) is None


def test_file_of_reads_the_store_path_and_ignores_unknowns():
    item = SimpleNamespace(name="hero")
    store = SimpleNamespace(get=lambda n: item if n == "hero" else None, path_of=lambda i: f"assets/{i.name}.json")
    project = SimpleNamespace(source_families=lambda: (("sprites", store, None),), authored_families=lambda: ())
    assert disk_locate.file_of(project, "sprites", "hero") == "assets/hero.json"
    assert disk_locate.file_of(project, "sprites", "ghost") is None
    assert disk_locate.file_of(project, "scenes", "hero") is None
