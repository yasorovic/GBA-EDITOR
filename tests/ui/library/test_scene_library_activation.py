"""La scène s'ouvre par son icône ou au clic central ; son nom reste une sélection d'inspection."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from core.models.scene import Scene
from core.project import Project
from ui.common.asset_kinds import SCENES
from ui.common.asset_library import _ROLE_OBJ
from ui.common.theme import C
from ui.scene_manager.scene_library_panel import SceneLibraryPanel


@pytest.fixture
def library(qapp, tmp_path, monkeypatch):
    project = Project.create(tmp_path / "Game", "Game")
    project.scenes.append(Scene(name="Other"))
    inspected = []
    monkeypatch.setattr("ui.scene_manager.scene_library_panel.get_bus",
                        lambda: SimpleNamespace(select=inspected.append))
    panel = SceneLibraryPanel()
    panel.load_project(project)
    panel._library._sections[SCENES.label].set_expanded(True)
    panel.resize(320, 400)
    panel.show()
    qapp.processEvents()
    tree = panel._library._trees[SCENES.label]
    return panel, tree, project, inspected


def test_nom_inspecte_sans_changer_la_scene(qapp, library):
    panel, tree, project, inspected = library
    opened = []
    panel.scene_selected.connect(opened.append)
    item = tree._locate(project.scenes[1])
    rect = tree.activation_icon_rect(item)
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.right() + 12, rect.center().y()))
    qapp.processEvents()
    assert inspected == [project.scenes[1]]
    assert opened == [] and project.active_scene is project.scenes[0]


@pytest.mark.parametrize("gesture", ["icon", "middle", "middle_locate"])
def test_un_clic_ouvre_la_scene_sans_changer_la_selection(qapp, library, gesture):
    panel, tree, project, inspected = library
    first, other = project.scenes
    tree.highlight_objs([first])
    qapp.processEvents()
    inspected.clear()
    opened = []
    def activate(index):
        opened.append(index)
        project.set_active_scene(index)
        panel.highlight_active_scene(project.active_scene)
    panel.scene_selected.connect(activate)
    item = tree._locate(other)
    icon = tree.activation_icon_rect(item)
    point = icon.center() if gesture == "icon" else QPoint(icon.right() + 40, icon.center().y())
    if gesture == "middle_locate":
        point.setX(tree.columnViewportPosition(2) + 8)
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton if gesture == "icon" else Qt.MouseButton.MiddleButton,
                     pos=point)
    qapp.processEvents()
    assert opened == [1] and project.active_scene is other
    assert tree.active_item().data(0, _ROLE_OBJ) is other
    assert tree._selected_objs() == [first] and inspected == []


def test_icone_active_blanche_survol_gris_et_inactive_masquee(qapp, library, monkeypatch):
    from ui.common import asset_library
    panel, tree, project, inspected = library
    active = tree._locate(project.scenes[0])
    other = tree._locate(project.scenes[1])
    assert tree.active_item() is active
    marks = []
    class Icon:
        def __init__(self, name, color):
            self.name, self.color = name, color
        def paint(self, painter, rect):
            if self.name == "scene":
                marks.append((rect.top(), self.color))
    monkeypatch.setattr(asset_library, "_ico", lambda name, color: Icon(name, color))
    def painted(hovered):
        tree._hover = (hovered, 0)
        marks.clear()
        tree.viewport().grab()
        return list(marks)
    assert painted(None) == [(tree.activation_icon_rect(active).top(), C.TEXT_HI)]
    assert painted(other) == [(tree.activation_icon_rect(active).top(), C.TEXT_HI),
                              (tree.activation_icon_rect(other).top(), C.TEXT_DIM)]
    assert painted(active) == [(tree.activation_icon_rect(active).top(), C.TEXT_HI)]


def test_activation_supporte_un_repeuplement_pendant_le_changement_de_scene(qapp, library):
    panel, tree, project, inspected = library
    opened = []
    def activate(index):
        opened.append(index)
        project.set_active_scene(index)
        panel.refresh()
        panel.highlight_active_scene(project.active_scene)
    panel.scene_selected.connect(activate)
    point = tree.activation_icon_rect(tree._locate(project.scenes[1])).center()
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=point)
    qapp.processEvents()
    assert opened == [1] and tree.active_item().data(0, _ROLE_OBJ) is project.scenes[1]


def test_icone_centree_et_separee_de_la_barre(qapp, library):
    from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
    panel, tree, project, inspected = library
    item = tree._locate(project.scenes[0])
    row = tree.visualItemRect(item)
    icon = tree.activation_icon_rect(item)
    assert abs(icon.center().y() - row.center().y()) <= 1
    assert icon.left() - row.left() >= 8
    option = QStyleOptionViewItem()
    tree.initViewItemOption(option)
    option.rect = row
    tree.itemDelegate().initStyleOption(option, tree.indexFromItem(item, 0))
    text = tree.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, tree)
    assert text.left() > icon.right()
