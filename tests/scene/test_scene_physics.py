"""La gravité suit le projet, sauf surcharge explicite de la scène."""
from core.models.settings import ProjectSettings
from core.models.scene import Scene


def test_la_gravite_de_scene_est_absente_tant_qu_elle_est_nulle():
    scene = Scene(name="Legacy")
    data = scene.to_dict()
    assert "physics_gravity_override" not in data
    assert "physics_gravity_x" not in data and "physics_gravity_y" not in data
    restored = Scene.from_dict(data)
    assert not restored.physics_gravity_override
    assert (restored.physics_gravity_x, restored.physics_gravity_y) == (0.0, 0.0)


def test_la_surcharge_de_scene_survit_a_la_serialisation():
    scene = Scene(name="Platform", physics_gravity_override=True,
                  physics_gravity_x=0.25, physics_gravity_y=0.5)
    restored = Scene.from_dict(scene.to_dict())
    assert restored.physics_gravity_override
    assert (restored.physics_gravity_x, restored.physics_gravity_y) == (0.25, 0.5)


def test_une_ancienne_gravite_de_scene_devient_une_surcharge():
    restored = Scene.from_dict({
        "name": "Legacy", "physics_gravity_x": 0.0, "physics_gravity_y": 0.5,
    })
    assert restored.physics_gravity_override
    assert restored.effective_physics_gravity(ProjectSettings(
        physics_gravity_y=1.0)) == (0.0, 0.5)


def test_la_scene_herite_de_la_gravite_du_projet():
    scene = Scene(name="Inherited")
    settings = ProjectSettings(physics_gravity_x=0.25, physics_gravity_y=0.5)
    assert scene.effective_physics_gravity(settings) == (0.25, 0.5)


def test_la_gravite_du_projet_survit_au_manifeste(tmp_path):
    from core.project import Project

    project = Project(tmp_path)
    project.settings.physics_gravity_x = 0.25
    project.settings.physics_gravity_y = 0.5
    project.save_settings()
    restored = Project(tmp_path)
    restored.load_settings()
    assert (restored.settings.physics_gravity_x,
            restored.settings.physics_gravity_y) == (0.25, 0.5)
