"""Les règles physiques appartiennent à la scène et restent neutres par défaut."""
from core.models.scene import Scene


def test_la_gravite_de_scene_est_absente_tant_qu_elle_est_nulle():
    scene = Scene(name="Legacy")
    data = scene.to_dict()
    assert "physics_gravity_x" not in data and "physics_gravity_y" not in data
    restored = Scene.from_dict(data)
    assert (restored.physics_gravity_x, restored.physics_gravity_y) == (0.0, 0.0)


def test_la_gravite_de_scene_survit_a_la_serialisation():
    scene = Scene(name="Platform", physics_gravity_x=0.25, physics_gravity_y=0.5)
    restored = Scene.from_dict(scene.to_dict())
    assert (restored.physics_gravity_x, restored.physics_gravity_y) == (0.25, 0.5)
