"""Le Scene Tree ne recalcule sa hauteur qu'une fois par repeuplement, pas à chaque ligne insérée."""
from pathlib import Path

import pytest

from core.project import Project

DEMO = Path(__file__).resolve().parent.parent.parent.parent / "Project Demo" / "Platformer"


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


def test_scene_library_partage_les_onglets_content_et_priority(qapp, tmp_path):
    from ui.common.asset_kinds import SCENES
    from ui.common.labels import label
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel
    from ui.scene_manager.scene_tree_panel import SceneTreePanel

    project = Project.create(tmp_path / "Game", "Game")
    library = SceneLibraryPanel()
    library.load_project(project)
    panel = SceneTreePanel(library=library)
    panel.load_project(project)
    panel.resize(280, 500)
    panel.show()
    qapp.processEvents()
    assert panel._context_tabs.count() == 3
    assert library.isHidden() and panel._scroll.isVisible()
    panel._btn_search.setChecked(True)
    panel._context_tabs.setCurrentIndex(2)
    assert library.isVisible() and panel._scroll.isHidden()
    assert panel._scene_lbl.text() == label("scenelibrary.scene_library")
    assert panel._btn_add.isHidden() and panel._btn_search.isHidden() and panel._filters_bar.isHidden()
    selected = []
    library.scene_selected.connect(selected.append)
    library._on_activated(SCENES.label, project.scenes[0])
    assert selected == [0]
    panel.set_active_scene(project.scenes[0])
    assert panel._context == "library" and library.isVisible()
    panel._context_tabs.setCurrentIndex(1)
    assert library.isHidden() and panel._priority_tree.isVisible()
    panel._context_tabs.setCurrentIndex(0)
    assert panel._tree.isVisible() and panel._btn_add.isVisible() and panel._filters_bar.isVisible()
    assert panel._scene_lbl.text() == project.scenes[0].name


def test_scene_library_reste_accessible_sans_scene_active(qapp):
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel
    from ui.scene_manager.scene_tree_panel import SceneTreePanel

    library = SceneLibraryPanel()
    panel = SceneTreePanel(library=library)
    panel._set_context("library")
    panel.show()
    qapp.processEvents()
    assert library.isVisible() and panel._scroll.isHidden()
    assert panel._context_tabs.currentIndex() == 2


def test_onglets_etroits_tronquent_les_noms_sans_boutons_de_defilement(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QToolButton
    from ui.scene_manager.scene_library_panel import SceneLibraryPanel
    from ui.scene_manager.scene_tree_panel import SceneTreePanel

    from ui.common.eliding_style import ElidingStyle
    from ui.common.theme import GLOBAL_QSS
    previous_stylesheet = qapp.styleSheet()
    previous_style = qapp.style().objectName() or "Fusion"
    drawn = []

    class RecordingStyle(ElidingStyle):
        def drawItemText(self, painter, rect, flags, palette, enabled, text, textRole=None):
            drawn.append(text)
            super().drawItemText(painter, rect, flags, palette, enabled, text, textRole)

    qapp.setStyle(RecordingStyle())
    qapp.setStyleSheet(GLOBAL_QSS)
    try:
        panel = SceneTreePanel(library=SceneLibraryPanel())
        panel.resize(220, 400)
        panel.show()
        qapp.processEvents()
        tabs = panel._context_tabs
        assert tabs.elideMode() == Qt.TextElideMode.ElideRight
        assert not tabs.usesScrollButtons()
        assert not any(button.isVisible() for button in tabs.findChildren(QToolButton))
        assert tabs.tabRect(tabs.count() - 1).right() < tabs.width()
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            assert panel._context == panel._contexts[index][0]
        drawn.clear()
        panel.resize(392, 400)
        qapp.processEvents()
        panel.grab()
        assert tabs.width() == tabs.parentWidget().width()
        assert all(tabs.tabText(index) in drawn for index in range(tabs.count()))
    finally:
        panel.hide()
        qapp.setStyle(previous_style)
        qapp.setStyleSheet(previous_stylesheet)
