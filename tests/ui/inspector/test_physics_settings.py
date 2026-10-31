"""Les deux niveaux d'édition de la gravité restent synchronisés."""
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
    assert project.settings.physics_gravity_y == 0.5
    history.undo()
    assert project.settings.physics_gravity_y == 0.0
    assert panel._spin_gravity_y.value() == 0.0

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
