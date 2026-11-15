from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace

from core.command_dispatcher import CommandDispatcher
from core.models.components import SpriteComponent
from core.models.scene import Actor, Prefab
from core.project import Project


def _project(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    prefab = Prefab(name="Hero", actor=Actor(
        name="Hero", components=[SpriteComponent(id="sprite", offset_x=1, offset_y=2)]))
    project.prefabs.append(prefab)
    project.prefabs.save(prefab)
    actor = project.instantiate_actor_from_prefab(prefab, "Hero_1")
    project.scenes[0].actors.append(actor)
    return project, prefab, actor


def test_une_scene_n_ecrit_que_les_surcharges_de_l_instance(tmp_path):
    project, _prefab, actor = _project(tmp_path)
    actor.components[0].offset_x = 9
    project.scenes.save(project.scenes[0])

    data = json.loads(project.scenes.path_of(project.scenes[0]).read_text(encoding="utf-8"))
    saved = next(item for item in data["actors"] if item["name"] == "Hero_1")
    assert "components" not in saved
    assert saved["overrides"] == {"components": {"sprite": {"offset_x": 9}}}

    reopened = Project.open(project.root)
    loaded = next(item for item in reopened.scenes[0].actors if item.name == "Hero_1")
    assert loaded.components[0].offset_x == 9
    assert loaded.components[0].offset_y == 2


def test_une_ancienne_copie_complete_migre_par_difference_sans_perte(tmp_path):
    project, _prefab, actor = _project(tmp_path)
    actor.components[0].offset_y = 12
    actor._prefab_override_format = False
    project.scenes.save(project.scenes[0])

    reopened = Project.open(project.root)
    loaded = next(item for item in reopened.scenes[0].actors if item.name == "Hero_1")
    assert loaded.components[0].offset_y == 12
    assert loaded.prefab_overrides == {"components": {"sprite": {"offset_y": 12}}}


def test_sauver_le_prefab_preserve_la_surcharge_sans_reecrire_la_scene(tmp_path):
    project, prefab, actor = _project(tmp_path)
    actor.components[0].offset_x = 9
    project.scenes.save(project.scenes[0])
    scene_path = project.scenes.path_of(project.scenes[0])
    before = scene_path.read_bytes()

    dispatcher = CommandDispatcher.__new__(CommandDispatcher)
    dispatcher._project = project
    dispatcher._watcher = SimpleNamespace(suspended=nullcontext)
    dispatcher._emit = lambda *_args, **_kwargs: None
    prefab.actor.components[0].offset_y = 20
    dispatcher.save_prefab(prefab)

    assert scene_path.read_bytes() == before
    assert actor.components[0].offset_x == 9
    assert actor.components[0].offset_y == 20


def test_relink_efface_les_surcharges_et_expose_les_absorbe(tmp_path):
    project, prefab, actor = _project(tmp_path)
    dispatcher = CommandDispatcher.__new__(CommandDispatcher)
    dispatcher._project = project
    dispatcher._watcher = SimpleNamespace(suspended=nullcontext)
    dispatcher._emit = lambda *_args, **_kwargs: None
    dispatcher._save_scene = lambda: project.scenes.save(project.scenes[0])

    actor.components[0].offset_x = 9
    assert dispatcher.expose_actor_to_prefab(actor)
    assert prefab.actor.components[0].offset_x == 9
    assert actor.prefab_overrides == {}

    actor.components[0].offset_x = 15
    assert dispatcher.relink_actor_to_prefab(actor)
    assert actor.components[0].offset_x == 9
    assert actor.prefab_overrides == {}
