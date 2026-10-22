"""Le libellé « From project (…) » de l'inspecteur de scène suit le réglage de transition du projet après `refresh_current`."""
from __future__ import annotations


def test_la_transition_heritee_se_relit_apres_un_reglage_du_projet(qapp, tmp_path):
    from core.models.scene import Scene
    from core.project import Project
    from ui.scene_manager.inspectors import DynamicInspector

    project = Project(tmp_path / "jeu")
    scene = Scene(name="Village")
    project.scenes.append(scene)
    inspector = DynamicInspector()
    inspector.set_project(project)
    inspector.show_scene(scene, project)
    combo = inspector._scene_insp._combo_trans
    before = combo.itemText(0)

    project.settings.transition_kind = "fade_black"
    inspector.refresh_current()

    assert combo.itemText(0) != before
