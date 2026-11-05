"""Area : posée dans le canvas, déplaçable, copiable d'une scène à l'autre, listée dans l'arbre, éditée à l'inspecteur."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from core.command_dispatcher import get_dispatcher
from core.history import get_history
from core.models.scene import Area, Scene
from core.project import Project

DEMO = Path(__file__).resolve().parents[3] / "Project Demo" / "Platformer"


@pytest.fixture(autouse=True)
def _grid_choice_stays_in_the_test(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from ui.scene_manager.scene_canvas import SceneEditor
    ini = str(tmp_path / "canvas.ini")
    monkeypatch.setattr(SceneEditor, "_grid_settings", staticmethod(lambda: QSettings(ini, QSettings.Format.IniFormat)))


def _dispose(*editors):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
    for ed in editors:
        ed.close()
        ed.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def editor(qapp, tmp_path, monkeypatch):
    if not DEMO.exists():
        pytest.skip("démo absente")
    root = tmp_path / "P"
    shutil.copytree(DEMO, root)
    from ui.scene_manager.scene_canvas import SceneEditor
    project = Project.open(root)
    scene = project.active_scene
    scene.areas = [Area(name="Door", x=40, y=48), Area(name="Zone", x=100, y=60)]
    dispatcher = get_dispatcher()
    monkeypatch.setattr(dispatcher, "_project", project)
    monkeypatch.setattr(dispatcher, "_save_scene", lambda *a, **k: None)
    ed = SceneEditor()
    ed.resize(900, 700)
    ed.load_project(project)
    ed.show()
    ed._fit()
    get_history().clear()
    yield ed
    get_history().clear()
    _dispose(ed)


def _hit_point(view, item):
    rect = item.sceneBoundingRect()
    for iy in range(int(rect.height())):
        for ix in range(int(rect.width())):
            pt = view.mapFromScene(QPointF(rect.x() + ix + 0.5, rect.y() + iy + 0.5))
            if next((x for x in view.items(pt) if x.acceptedMouseButtons()), None) is item:
                return pt
    return None


def _item(editor, name):
    return next(it for it in editor._gba_scene._area_items if it.area.name == name)


def test_les_areas_de_la_scene_sont_des_items_du_canvas(editor):
    assert sorted(it.area.name for it in editor._gba_scene._area_items) == ["Door", "Zone"]
    rect = _item(editor, "Door").shape_rect()
    assert (rect.width(), rect.height()) == (32, 32)


def test_glisser_une_area_ecrit_le_modele_en_une_entree_annulable(editor):
    item = _item(editor, "Door")
    area = item.area
    before = (area.x, area.y)
    view = editor._gba_view
    start = _hit_point(view, item)
    assert start is not None
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 6):
        QTest.mouseMove(view.viewport(), start + QPoint(step * 8, step * 4))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(40, 20))
    assert (area.x, area.y) != before
    assert len(get_history()._undo) == 1
    get_history().undo()
    assert (area.x, area.y) == before


def test_selectionner_une_area_la_publie_sur_le_bus(editor):
    from core.selection_bus import get_bus
    item = _item(editor, "Zone")
    item.setSelected(True)
    editor._on_selection_changed()
    assert get_bus().current is item.area


def test_copier_une_area_la_colle_dans_une_autre_scene(editor):
    project = editor._project
    source_scene = project.active_scene
    other = Scene(name="Other", areas=[Area(name="Door", x=0, y=0)])    # un nom déjà pris, dans l'autre scène
    project.scenes.append(other)
    door = _item(editor, "Door")
    door.setSelected(True)
    editor._shortcut_copy()
    project.set_active_scene(len(project.scenes) - 1)
    editor._shortcut_paste()
    assert len(other.areas) == 2
    pasted = other.areas[-1]
    assert pasted is not door.area and pasted.name != "Door"          # une copie, au nom unique dans CETTE scène
    assert (pasted.x, pasted.y) == (door.area.x, door.area.y)         # même place : « reproduire ailleurs »
    assert [a.name for a in source_scene.areas] == ["Door", "Zone"]   # l'original ne bouge pas
    get_history().undo()
    assert len(other.areas) == 1                                      # un seul Ctrl+Z défait le collage


def test_les_fleches_deplacent_les_areas_en_une_entree_fusionnee(editor):
    item = _item(editor, "Door")
    item.setSelected(True)
    before = (item.area.x, item.area.y)
    for _ in range(3):
        editor._shortcut_nudge(1, 0)
    assert (item.area.x, item.area.y) == (before[0] + 3, before[1])
    assert (item.pos().x(), item.pos().y()) == (before[0] + 3, before[1])    # l'item suit le modèle
    assert len(get_history()._undo) == 1
    get_history().undo()
    assert (item.area.x, item.area.y) == before


def test_les_fleches_emportent_acteurs_et_areas_ensemble(editor):
    actor_item = editor._gba_scene._sprite_items[0]
    actor = actor_item.scene_sprite
    area_item = _item(editor, "Door")
    actor_item.setSelected(True)
    area_item.setSelected(True)
    actor_before, area_before = (actor.x, actor.y), (area_item.area.x, area_item.area.y)
    editor._shortcut_nudge(0, 2)
    assert (actor.x, actor.y) == (actor_before[0], actor_before[1] + 2)
    assert (area_item.area.x, area_item.area.y) == (area_before[0], area_before[1] + 2)
    assert len(get_history()._undo) == 1


def test_clic_droit_sur_une_area_demande_son_menu(editor, monkeypatch):
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtWidgets import QMenu
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: None)     # le vrai menu attendrait un clic
    item = _item(editor, "Zone")
    view = editor._gba_view
    pt = _hit_point(view, item)
    assert pt is not None
    asked = []
    view.area_context_requested.connect(lambda it, pos: asked.append(it))
    view.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pt, view.viewport().mapToGlobal(pt)))
    assert asked == [item] and item.isSelected()


def test_les_poignees_redimensionnent_la_forme_en_une_entree_annulable(editor):
    item = _item(editor, "Door")
    item.setSelected(True)
    shape = item.area.components[0]
    view = editor._gba_view
    corner = item.mapToScene(QPointF(*item._handle_points()["se"]))
    start = view.mapFromScene(corner)
    assert item._handle_at(item.mapFromScene(view.mapToScene(start))) == "se"
    target = view.mapFromScene(corner + QPointF(16, 8))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), target)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert shape.w > 32 and shape.h > 32 and (shape.x, shape.y) == (0, 0)      # le coin bas-droit seul bouge
    assert (item.area.x, item.area.y) == (40, 48)                              # l'Area ne se déplace pas
    assert len(get_history()._undo) == 1
    get_history().undo()
    assert (shape.w, shape.h) == (32, 32)


def test_une_poignee_haut_gauche_deplace_le_decalage_et_garde_le_bord_oppose(editor):
    item = _item(editor, "Door")
    item.setSelected(True)
    shape = item.area.components[0]
    item._resize_handle, item._resize_start = "nw", (0, 0, 32, 32)
    item._drag_resize(QPointF(-8, -4))
    assert (shape.x, shape.y, shape.w, shape.h) == (-8, -4, 40, 36)           # le bord bas-droit reste en (32, 32)
    item._drag_resize(QPointF(100, 100))                                      # au-delà du bord opposé : 1 px au moins
    assert (shape.w, shape.h) == (1, 1) and (shape.x, shape.y) == (31, 31)


def test_pas_de_poignee_quand_la_forme_est_liee_a_une_variable(editor):
    item = _item(editor, "Door")
    assert item._handle_points()
    item.area.components[0].w = {"var": "0123456789ab", "src": "global"}   # une référence : le geste l'écraserait
    assert item._handle_points() == {}


def test_renommer_une_area_refuse_un_nom_pris_et_s_annule(editor):
    dispatcher = get_dispatcher()
    door, zone = editor._project.active_scene.areas
    assert dispatcher.rename_area(door, "Zone") is False and door.name == "Door"
    assert dispatcher.rename_area(door, "  ") is False and dispatcher.rename_area(door, "Door") is False
    assert dispatcher.rename_area(door, "Gate") is True and door.name == "Gate"
    get_history().undo()
    assert door.name == "Door"


def test_dupliquer_et_supprimer_des_areas_sont_annulables(editor):
    scene = editor._project.active_scene
    dispatcher = get_dispatcher()
    copies = dispatcher.duplicate_areas([scene.areas[0]])
    assert len(scene.areas) == 3 and copies[0].name != "Door" and copies[0].id == ""
    dispatcher.delete_areas(copies)
    assert len(scene.areas) == 2
    get_history().undo()
    get_history().undo()
    assert [a.name for a in scene.areas] == ["Door", "Zone"]


def test_l_arbre_liste_les_areas_et_refuse_un_nom_pris(qapp, editor):
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
    from ui.scene_manager.scene_tree_panel import T_AREA, SceneTreePanel, _ROLE_OBJ, _ROLE_TYPE
    project = editor._project
    panel = SceneTreePanel()
    panel.load_project(project)
    tree = panel._tree
    items = []
    it = QTreeWidgetItemIterator(tree)
    while it.value():
        if it.value().data(0, _ROLE_TYPE) == T_AREA:
            items.append(it.value())
        it += 1
    assert sorted(i.text(0) for i in items) == ["Door", "Zone"]
    door = next(i for i in items if i.text(0) == "Door")
    door.setText(0, "Zone")                       # `itemChanged` valide : déjà pris, la ligne retrouve son nom
    assert door.text(0) == "Door" and door.data(0, _ROLE_OBJ).name == "Door"
    door.setText(0, "Gate")                       # accepté : l'arbre est reconstruit, la ligne d'avant n'existe plus
    assert project.active_scene.areas[0].name == "Gate"
    get_history().undo()
    assert project.active_scene.areas[0].name == "Door"
    panel.deleteLater()


def test_l_inspecteur_masque_ce_qui_n_a_pas_de_sens_pour_une_area_et_ses_edits_sont_annulables(qapp, editor):
    from ui.scene_manager.inspectors.area_inspector import AreaInspector
    project = editor._project
    area = project.active_scene.areas[0]
    insp = AreaInspector()
    insp.load(area, project, project.active_scene)
    assert {"w", "h", "x", "y", "tag"} <= set(insp._field_syncers)
    assert not {"solid", "response", "one_way", "material_id"} & set(insp._field_syncers)
    shape = area.components[0]
    insp._set_comp(shape, "w", 48)
    assert shape.w == 48
    insp._spin_x.setValue(70)
    assert area.x == 70
    get_history().undo()
    assert area.x == 40
    get_history().undo()
    assert shape.w == 32
    insp.deleteLater()
