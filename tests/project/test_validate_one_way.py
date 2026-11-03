"""Les diagnostics des faces à sens unique : une forme qui ne bloque pas, et un type de tuile que le runtime ne connaît pas."""
from __future__ import annotations

from core.models.collision_tiles import TILE_COUNT, TILE_ONEWAY_UP, TILE_SOLID
from core.models.components import CollisionShapeComponent
from core.models.scene import Actor
from core.project import Project
from core.validator import validate_project


def _projet(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


def _verdict(project):
    project.save()
    return validate_project(Project.open(project.root))


def test_un_sens_unique_sur_un_capteur_est_un_avertissement(tmp_path):
    project = _projet(tmp_path)
    actor = Actor(name="Plateforme")
    actor.components = [CollisionShapeComponent(id="b", response="sensor", one_way="gravity")]
    project.scenes[0].actors.append(actor)

    warns, errors = _verdict(project)

    [warn] = [w for w in warns if "One-way" in w.message]
    assert warn.actor == "Plateforme" and "Block" in warn.message
    assert not [e for e in errors if "One-way" in e.message]


def test_un_sens_unique_sur_une_boite_bloquante_ne_dit_rien(tmp_path):
    project = _projet(tmp_path)
    actor = Actor(name="Plateforme")
    actor.components = [CollisionShapeComponent(id="b", response="block", one_way="gravity")]
    project.scenes[0].actors.append(actor)

    warns, errors = _verdict(project)

    assert not [m for m in warns + errors if "One-way" in m.message]


def test_un_type_de_tuile_inconnu_est_une_erreur_qui_nomme_la_scene_et_la_case(tmp_path):
    project = _projet(tmp_path)
    scene = project.scenes[0]
    scene.ensure_collision_map()
    scene.collision_map[2][3] = TILE_COUNT
    scene.collision_map[2][4] = TILE_COUNT + 7
    scene.collision_map[0][0] = TILE_ONEWAY_UP

    _warns, errors = _verdict(project)

    [err] = [e for e in errors if "unknown type" in e.message]
    assert err.scene == scene.name
    assert "2 tile(s)" in err.message and f"{TILE_COUNT!r} at column 3, row 2" in err.message


def test_une_carte_de_types_connus_est_saine(tmp_path):
    project = _projet(tmp_path)
    scene = project.scenes[0]
    scene.ensure_collision_map()
    scene.collision_map[1][1] = TILE_SOLID
    scene.collision_map[1][2] = TILE_COUNT - 1

    _warns, errors = _verdict(project)

    assert not [e for e in errors if "unknown type" in e.message]
