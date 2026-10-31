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
    assert restored.physics_solver_iterations == 4
    assert restored.physics_max_fall_speed == 8.0
    assert restored.physics_linear_damping == 0.0
    assert restored.physics_sleep_enabled
    assert restored.physics_sleep_threshold == 0.05
    assert restored.physics_sleep_frames == 30


def test_la_surcharge_de_scene_survit_a_la_serialisation():
    scene = Scene(name="Platform", physics_gravity_override=True,
                  physics_gravity_x=0.25, physics_gravity_y=0.5)
    restored = Scene.from_dict(scene.to_dict())
    assert restored.physics_gravity_override
    assert (restored.physics_gravity_x, restored.physics_gravity_y) == (0.25, 0.5)


def test_les_parametres_de_simulation_survivent_a_la_serialisation():
    scene = Scene(name="Tuned", physics_gravity_override=True, physics_solver_iterations=7,
                  physics_max_fall_speed=6.5, physics_linear_damping=0.1,
                  physics_sleep_enabled=True, physics_sleep_threshold=0.08,
                  physics_sleep_frames=45)
    restored = Scene.from_dict(scene.to_dict())
    assert restored.physics_solver_iterations == 7
    assert restored.physics_max_fall_speed == 6.5
    assert restored.physics_linear_damping == 0.1
    assert restored.physics_sleep_enabled
    assert restored.physics_sleep_threshold == 0.08
    assert restored.physics_sleep_frames == 45


def test_les_parametres_de_simulation_invalides_sont_bornes_a_la_lecture():
    restored = Scene.from_dict({
        "name": "Invalid", "physics_solver_iterations": 99,
        "physics_max_fall_speed": -2, "physics_linear_damping": 3,
        "physics_sleep_threshold": -1, "physics_sleep_frames": 999,
    })
    assert restored.physics_solver_iterations == 8
    assert restored.physics_max_fall_speed == 0
    assert restored.physics_linear_damping == 1
    assert restored.physics_sleep_threshold == 0
    assert restored.physics_sleep_frames == 255


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


def test_la_scene_herite_des_parametres_de_simulation_du_projet():
    scene = Scene(name="Inherited")
    assert scene.effective_physics_simulation(ProjectSettings())[3] is True
    settings = ProjectSettings(physics_solver_iterations=6, physics_max_fall_speed=12.0,
                               physics_linear_damping=0.1, physics_sleep_enabled=False,
                               physics_sleep_threshold=0.08, physics_sleep_frames=45)
    assert scene.effective_physics_simulation(settings) == (6, 12.0, 0.1, False, 0.08, 45)


def test_la_gravite_du_projet_survit_au_manifeste(tmp_path):
    from core.project import Project

    project = Project(tmp_path)
    project.settings.physics_gravity_x = 0.25
    project.settings.physics_gravity_y = 0.5
    project.settings.physics_solver_iterations = 6
    project.settings.physics_max_fall_speed = 12.0
    project.settings.physics_linear_damping = 0.1
    project.settings.physics_sleep_enabled = False
    project.settings.physics_sleep_threshold = 0.08
    project.settings.physics_sleep_frames = 45
    project.save_settings()
    restored = Project(tmp_path)
    restored.load_settings()
    assert (restored.settings.physics_gravity_x,
            restored.settings.physics_gravity_y) == (0.25, 0.5)
    assert restored.settings.physics_solver_iterations == 6
    assert restored.settings.physics_max_fall_speed == 12.0
    assert restored.settings.physics_linear_damping == 0.1
    assert not restored.settings.physics_sleep_enabled
    assert restored.settings.physics_sleep_threshold == 0.08
    assert restored.settings.physics_sleep_frames == 45
