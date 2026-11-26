"""Le Path de waypoints est une donnée de scène, stable au JSON."""
from core.models.scene import Scene
from core.models.waypoint_path import (
    PATH_LOOP, PATH_ONCE, PATH_PING_PONG, WaypointPath,
)


def test_le_path_garde_son_origine_ses_points_et_son_mode():
    path = WaypointPath(name="Patrouille", x=48, y=64,
                        points=[[-8, 0], [12, 4]], mode=PATH_PING_PONG)
    copy = WaypointPath.from_dict(path.to_dict())

    assert copy.name == "Patrouille"
    assert (copy.x, copy.y) == (48, 64)
    assert copy.points == [(-8, 0), (12, 4)]
    assert copy.mode == PATH_PING_PONG


def test_un_path_sans_mode_garde_le_bouclage_comme_defaut():
    assert WaypointPath.from_dict({"name": "Ronde", "points": []}).mode == PATH_LOOP


def test_la_scene_serialize_ses_paths_comme_des_membres():
    scene = Scene(name="Quai", paths=[WaypointPath(name="Bateau", mode=PATH_ONCE,
                                                      parent="Navire")])
    loaded = Scene.from_dict(scene.to_dict())

    assert len(loaded.paths) == 1
    assert loaded.paths[0].parent == "Navire"
    assert loaded.paths[0].mode == PATH_ONCE
    assert loaded.paths[0].id
