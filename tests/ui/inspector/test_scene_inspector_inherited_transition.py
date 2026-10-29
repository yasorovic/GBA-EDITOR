"""La transition affichée par l'inspecteur de scène (sans surcharge) suit le réglage du projet après `refresh_current`."""
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
    assert combo.currentData() == "none" and combo.findData("") < 0     # une valeur réelle, pas d'item « héritée »

    project.settings.transition_kind = "fade_black"
    inspector.refresh_current()

    assert combo.currentData() == "fade_black"
