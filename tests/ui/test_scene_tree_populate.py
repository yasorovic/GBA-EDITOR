"""Le Scene Tree ne recalcule sa hauteur qu'une fois par repeuplement, pas à chaque ligne insérée."""
from pathlib import Path

import pytest

from core.project import Project

DEMO = Path(__file__).resolve().parent.parent.parent / "Project Demo" / "PongAdvanced"


def test_populate_fits_once_and_still_sizes_the_tree(qapp):
    if not DEMO.exists():
        pytest.skip("démo absente")
    from core.models.scene import Actor
    from ui.scene_manager.scene_tree_panel import SceneTreePanel
    project = Project.open(DEMO)
    project.set_active_scene(0)
    for i in range(40):
        project.active_scene.actors.append(Actor(name=f"Extra{i}", x=i, y=0))
    panel = SceneTreePanel()
    panel.resize(320, 800)
    panel.load_project(project)
    tree = panel._tree
    heights = []
    cls = type(tree)
    cls.setFixedHeight = lambda self, h: heights.append(h) or super(cls, self).setFixedHeight(h)
    try:
        tree.populate(project, project.active_scene)
    finally:
        del cls.setFixedHeight
    assert len(heights) == 1                    # une seule mise à la hauteur, à la fin
    assert heights[0] >= 40 * 8                 # et elle suit bien le contenu
