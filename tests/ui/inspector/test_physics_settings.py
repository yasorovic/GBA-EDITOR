"""Les deux niveaux d'édition des réglages physiques restent synchronisés."""
from core.history import get_history
from core.models.scene import Scene
from core.project import Project
from ui.scene_manager.inspectors.project_settings_dialog import PhysicsCollisionsPanel
from ui.scene_manager.inspectors.scene_inspector import SceneInspector


def test_le_panneau_projet_edite_la_gravite_et_l_annulation(qapp, tmp_path):
    history = get_history()
    history.clear()
    project = Project(tmp_path)
    panel = PhysicsCollisionsPanel(project)

    panel._spin_gravity_y.setValue(0.5)
    panel._spin_physics_iterations.setValue(6)
    panel._spin_physics_max_fall.setValue(12.0)
    panel._spin_physics_damping.setValue(0.1)
    panel._chk_physics_sleep.setChecked(False)
    assert project.settings.physics_gravity_y == 0.5
    assert project.settings.physics_solver_iterations == 6
    assert project.settings.physics_max_fall_speed == 12.0
    assert project.settings.physics_linear_damping == 0.1
    assert not project.settings.physics_sleep_enabled
    history.undo()
    assert project.settings.physics_sleep_enabled

    history.clear()
    panel.close()


def test_la_carte_scene_affiche_l_heritage_et_cree_une_surcharge(qapp, tmp_path):
    history = get_history()
    history.clear()
    project = Project(tmp_path)
    project.settings.physics_gravity_x = 0.25
    project.settings.physics_gravity_y = 0.5
    scene = Scene(name="Platform")
    project.scenes.append(scene)
    inspector = SceneInspector()
    inspector.load(scene, project)

    assert inspector._chk_physics_project.isChecked()
    assert not inspector._spin_gravity_x.isEnabled()
    assert (inspector._spin_gravity_x.value(),
            inspector._spin_gravity_y.value()) == (0.25, 0.5)

    inspector._chk_physics_project.setChecked(False)
    assert scene.physics_gravity_override
    assert (scene.physics_gravity_x, scene.physics_gravity_y) == (0.25, 0.5)
    assert inspector._spin_gravity_x.isEnabled()

    inspector._spin_gravity_y.setValue(0.75)
    assert scene.physics_gravity_y == 0.75
    inspector._chk_physics_project.setChecked(True)
    assert scene.effective_physics_gravity(project.settings) == (0.25, 0.5)

    history.undo()
    assert scene.physics_gravity_override
    assert inspector._spin_gravity_y.value() == 0.75

    history.clear()
    inspector.close()


def test_la_carte_scene_edite_les_parametres_de_simulation(qapp, tmp_path):
    history = get_history()
    history.clear()
    project = Project(tmp_path)
    scene = Scene(name="Simulation")
    project.scenes.append(scene)
    inspector = SceneInspector()
    inspector.load(scene, project)

    assert not inspector._spin_physics_iterations.isEnabled()
    inspector._chk_physics_project.setChecked(False)

    inspector._spin_physics_iterations.setValue(6)
    inspector._spin_physics_max_fall.setValue(8.0)
    inspector._spin_physics_damping.setValue(0.1)
    inspector._chk_physics_sleep.setChecked(True)
    inspector._spin_physics_sleep_threshold.setValue(0.08)
    inspector._spin_physics_sleep_frames.setValue(45)

    assert scene.physics_solver_iterations == 6
    assert scene.physics_max_fall_speed == 8.0
    assert scene.physics_linear_damping == 0.1
    assert scene.physics_sleep_enabled
    assert scene.physics_sleep_threshold == 0.08
    assert scene.physics_sleep_frames == 45
    assert inspector._spin_physics_sleep_threshold.isEnabled()

    history.undo()
    assert scene.physics_sleep_frames == 30
    history.clear()
    inspector.close()
