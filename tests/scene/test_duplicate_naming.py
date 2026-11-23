"""Dupliquer suit la même suite de noms que tout le reste : la copie d'un `Chaser1_2` redonne `Chaser1_3`, jamais
`Chaser1_2_2`. Le cœur de la règle (`copy_name`) est testé dans tests/project/test_duplicate_asset.py ; ici on verrouille
que les gestes de l'éditeur (acteurs, areas, éléments d'interface) passent bien par elle, et non par `unique_name` brut."""
from __future__ import annotations

from pathlib import Path

from core.command_dispatcher import CommandDispatcher
from core.models.scene import Actor, Area, Scene
from core.project import Project


def _dispatcher(tmp_path: Path):
    project = Project.create(tmp_path / "Jeu", "Jeu")
    project = Project.open(project.root)
    project.load_all_resources()
    scene = project.active_scene
    disp = CommandDispatcher()
    disp._project = project
    return disp, scene


def test_duplicating_an_actor_copy_continues_the_series(tmp_path):
    disp, scene = _dispatcher(tmp_path)
    scene.actors.append(Actor(name="Chaser1", x=0, y=0))

    last = scene.actors[-1]
    produced = []
    for _ in range(5):
        last = disp._make_actor_copies(scene, [last], 8, 8)[0]
        scene.actors.append(last)
        produced.append(last.name)

    assert produced == ["Chaser1_2", "Chaser1_3", "Chaser1_4", "Chaser1_5", "Chaser1_6"]


def test_duplicating_an_area_copy_continues_the_series(tmp_path):
    disp, scene = _dispatcher(tmp_path)
    scene.areas.append(Area(name="Zone", x=0, y=0))

    last = scene.areas[-1]
    produced = []
    for _ in range(3):
        last = disp._make_area_copies(scene, [last], 8, 8)[0]
        scene.areas.append(last)
        produced.append(last.name)

    assert produced == ["Zone_2", "Zone_3", "Zone_4"]
