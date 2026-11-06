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


def test_l_outil_d_ajout_pose_une_area_centree_et_aimantee_en_une_entree_annulable(editor):
    from ui.scene_manager.canvas_tools import AddAreaTool
    scene = editor._project.active_scene
    tool = AddAreaTool(editor._gba_view)
    tool.activate()
    try:
        assert tool._centre(QPointF(101, 83)) == (104, 80)             # aimanté à 8 px
        assert tool.on_press(QPointF(101, 83), None) is True
    finally:
        tool.deactivate()
    from PyQt6.QtWidgets import QApplication
    QApplication.processEvents()      # le retour à l'outil Sélection est différé (QTimer 0) : avant la fermeture de l'éditeur
    assert editor._canvas_container._toolbar.current_tool == "select"
    created = scene.areas[-1]
    assert len(scene.areas) == 3 and created.name not in ("Door", "Zone")
    assert (created.x, created.y) == (104 - 16, 80 - 16)               # le clic est le CENTRE de l'Area
    get_history().undo()
    assert len(scene.areas) == 2


def test_la_gomme_supprime_une_area_sous_le_curseur(editor):
    from ui.scene_manager.canvas_tools import EraseTool
    scene = editor._project.active_scene
    item = _item(editor, "Zone")
    point = item.mapToScene(item.shape_rect().center())
    EraseTool(editor._gba_view).on_press(point, None)
    assert [a.name for a in scene.areas] == ["Door"]
    get_history().undo()
    assert [a.name for a in scene.areas] == ["Door", "Zone"]


def test_le_bouton_plus_offre_acteur_et_area_et_la_touche_a_reprend_le_dernier_choix(editor):
    toolbar = editor._canvas_container._toolbar
    seen = []
    toolbar.tool_changed.connect(seen.append)
    toolbar._select_add_mode("add_area")
    assert toolbar.current_tool == "add_area" and toolbar._btns["add"].isChecked()    # le (+) reste coché
    toolbar.activate_shortcut("select")
    toolbar.activate_shortcut("add")                                                   # la touche A : dernier choix
    assert seen[-1] == "add_area" and toolbar.current_tool == "add_area"
    toolbar._select_add_mode("add")
    toolbar.activate_shortcut("add")
    assert seen[-1] == "add"


def _follow_first_actor(editor):
    """Fait suivre le premier acteur de la scène à l'Area « Door » ; rend (item de l'acteur, Area)."""
    item = editor._gba_scene._sprite_items[0]
    door = next(a for a in editor._project.active_scene.areas if a.name == "Door")
    door.parent = item.scene_sprite.name
    return item, door


def test_deplacer_un_parent_au_canvas_entraine_ses_areas_en_une_entree_annulable(editor):
    item, door = _follow_first_actor(editor)
    zone = next(a for a in editor._project.active_scene.areas if a.name == "Zone")      # sans parent : elle ne bouge pas
    actor = item.scene_sprite
    before = {"actor": (actor.x, actor.y), "door": (door.x, door.y), "zone": (zone.x, zone.y)}
    view = editor._gba_view
    start = _hit_point(view, item)
    assert start is not None
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 6):
        QTest.mouseMove(view.viewport(), start + QPoint(step * 8, step * 4))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(40, 20))
    dx, dy = actor.x - before["actor"][0], actor.y - before["actor"][1]
    assert (dx, dy) != (0, 0)
    assert (door.x - before["door"][0], door.y - before["door"][1]) == (dx, dy)          # l'Area suit du même écart
    assert (zone.x, zone.y) == before["zone"]
    area_item = _item(editor, "Door")
    assert (area_item.pos().x(), area_item.pos().y()) == (door.x, door.y)                # son item aussi, en direct
    assert len(get_history()._undo) == 1                                                  # un seul Ctrl+Z pour tout
    get_history().undo()
    assert (actor.x, actor.y) == before["actor"] and (door.x, door.y) == before["door"]


def test_les_fleches_sur_un_parent_emportent_ses_areas(editor):
    item, door = _follow_first_actor(editor)
    item.setSelected(True)
    before = (door.x, door.y)
    editor._shortcut_nudge(3, 1)
    assert (door.x, door.y) == (before[0] + 3, before[1] + 1)
    assert (_item(editor, "Door").pos().x(), _item(editor, "Door").pos().y()) == (door.x, door.y)
    assert len(get_history()._undo) == 1
    get_history().undo()
    assert (door.x, door.y) == before


def test_choisir_un_parent_a_l_inspecteur_est_annulable_et_ne_deplace_pas_l_area(qapp, editor):
    from ui.scene_manager.inspectors.area_inspector import AreaInspector
    project = editor._project
    scene = project.active_scene
    area = next(a for a in scene.areas if a.name == "Door")
    insp = AreaInspector()
    insp.load(area, project, scene)
    names = [insp._cmb_parent.itemData(i) for i in range(insp._cmb_parent.count())]
    assert names[0] is None and names[1:] == [a.name for a in scene.actors]              # (none), puis les acteurs de la scène
    position = (area.x, area.y)
    insp._cmb_parent.setCurrentIndex(1)
    assert area.parent == scene.actors[0].name and (area.x, area.y) == position
    get_history().undo()
    assert area.parent is None
    insp.deleteLater()


def test_l_arbre_accroche_une_area_sous_son_parent_et_le_depot_la_rattache(qapp, editor):
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
    from ui.scene_manager.scene_tree_panel import T_ACTOR, T_AREA, SceneTreePanel, _ROLE_OBJ, _ROLE_TYPE
    project = editor._project
    scene = project.active_scene
    door = next(a for a in scene.areas if a.name == "Door")
    assert get_dispatcher().set_area_parent(door, "Ghost") is False                      # pas un acteur de la scène : refusé
    assert get_dispatcher().set_area_parent(door, scene.actors[0].name) is True
    panel = SceneTreePanel()
    panel.load_project(project)
    it = QTreeWidgetItemIterator(panel._tree)
    found = None
    while it.value():
        if it.value().data(0, _ROLE_TYPE) == T_AREA and it.value().data(0, _ROLE_OBJ) is door:
            found = it.value()
        it += 1
    assert found is not None and found.parent().data(0, _ROLE_TYPE) == T_ACTOR
    assert found.parent().data(0, _ROLE_OBJ) is scene.actors[0]                         # sous son parent
    assert get_dispatcher().set_area_parent(door, None) is True                          # libérée
    assert door.parent is None and get_dispatcher().set_area_parent(door, None) is False  # déjà libre : rien à faire
    get_history().undo()                       # les deux écritures du même champ ont fusionné : retour à l'état d'avant
    assert door.parent is None
    assert get_dispatcher().set_area_parent(door, scene.actors[0].name) is True
    get_history().undo()
    assert door.parent is None
    panel.deleteLater()


def test_supprimer_un_parent_supprime_son_sous_arbre_en_une_entree_annulable(editor):
    scene = editor._project.active_scene
    parent, child, other = scene.actors[0], scene.actors[1], scene.actors[2]
    child.parent = parent.name                                   # un acteur enfant
    door = next(a for a in scene.areas if a.name == "Door")
    zone = next(a for a in scene.areas if a.name == "Zone")
    door.parent = parent.name                                    # une Area qui suit le parent
    zone.parent = child.name                                     # une Area qui suit l'enfant : elle part aussi
    free = Area(name="Free", x=1, y=2)                           # sans parent : elle reste
    scene.areas.append(free)
    before_actors, before_areas = list(scene.actors), list(scene.areas)
    get_dispatcher().delete_actors([parent])
    assert parent not in scene.actors and child not in scene.actors and other in scene.actors
    assert scene.areas == [free]                                 # Door et Zone suivaient le sous-arbre supprimé
    assert len(get_history()._undo) == 1                         # un seul Ctrl+Z pour tout le sous-arbre
    get_history().undo()
    assert scene.actors == before_actors and scene.areas == before_areas                     # même contenu, même ordre
    assert door.parent == parent.name and zone.parent == child.name and child.parent == parent.name


def test_supprimer_un_enfant_laisse_son_parent_et_les_areas_du_parent(editor):
    scene = editor._project.active_scene
    parent, child = scene.actors[0], scene.actors[1]
    child.parent = parent.name
    door = next(a for a in scene.areas if a.name == "Door")
    door.parent = parent.name
    get_dispatcher().delete_actors([child])
    assert parent in scene.actors and child not in scene.actors and door in scene.areas


def test_coller_une_area_dans_une_scene_sans_son_parent_la_libere(editor):
    from core.models.scene import Scene
    project = editor._project
    _item_, door = _follow_first_actor(editor)
    other = Scene(name="Other")
    project.scenes.append(other)
    door_item = _item(editor, "Door")
    door_item.setSelected(True)
    editor._shortcut_copy()
    project.set_active_scene(len(project.scenes) - 1)
    editor._shortcut_paste()
    assert other.areas[-1].parent is None                    # ce parent n'existe pas là : libre plutôt que pendante
    assert door.parent is not None                           # l'original garde le sien


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


def test_la_case_declencheur_ajoute_desactive_et_reactive_le_composant(qapp, editor):
    from core.models.components import TriggerComponent
    from ui.scene_manager.inspectors.area_inspector import AreaInspector
    project = editor._project
    area = project.active_scene.areas[0]
    insp = AreaInspector()
    insp.load(area, project, project.active_scene)
    assert insp._chk_trigger.isChecked() and area.is_trigger()
    insp._chk_trigger.setChecked(False)                    # décoché : désactivé, jamais retiré
    triggers = [c for c in area.components if isinstance(c, TriggerComponent)]
    assert len(triggers) == 1 and not triggers[0].active and not area.is_trigger()
    get_history().undo()                                   # annuler rend le déclencheur
    assert area.is_trigger()
    insp._chk_trigger.setChecked(False)
    get_history().push_executed(type("Coupure", (), {"label": "coupure", "execute": lambda s: None,
                                                     "undo": lambda s: None, "merge": lambda s, n: False})())
    insp._chk_trigger.setChecked(True)                     # recoché : le MÊME composant revient
    assert [c for c in area.components if isinstance(c, TriggerComponent)] == triggers and area.is_trigger()
    area.components = [c for c in area.components if not isinstance(c, TriggerComponent)]
    insp.load(area, project, project.active_scene)
    assert not insp._chk_trigger.isChecked()
    insp._chk_trigger.setChecked(True)                     # sans composant : il est ajouté
    assert area.is_trigger() and len([c for c in area.components if isinstance(c, TriggerComponent)]) == 1
    get_history().undo()
    assert not area.is_trigger() and not any(isinstance(c, TriggerComponent) for c in area.components)
    insp.deleteLater()


def test_les_effets_physiques_s_ajoutent_se_reglent_et_s_annulent(qapp, editor):
    from core.models.components import ForceFieldComponent, GravityOverrideComponent
    from ui.scene_manager.inspectors.area_inspector import AreaInspector
    project = editor._project
    area = project.active_scene.areas[0]
    insp = AreaInspector()
    insp.load(area, project, project.active_scene)
    assert not insp._fx_checks[ForceFieldComponent].isChecked()
    assert not insp._fx_inputs[(ForceFieldComponent, "force_x")].isEnabled()           # grisé sans composant
    insp._fx_checks[ForceFieldComponent].setChecked(True)                               # ajouté
    force = area.effect(ForceFieldComponent)
    assert force is not None and insp._fx_inputs[(ForceFieldComponent, "force_x")].isEnabled()
    insp._fx_inputs[(ForceFieldComponent, "force_x")].setValue(0.5)
    insp._fx_inputs[(ForceFieldComponent, "affects_characters")].setChecked(True)
    assert force.force_x == 0.5 and force.affects_characters
    insp._fx_checks[ForceFieldComponent].setChecked(False)                              # désactivé, jamais retiré
    assert area.effect(ForceFieldComponent) is None and force in area.components
    assert area.effect(GravityOverrideComponent) is None                                # l'autre effet ne bouge pas
    get_history().undo()                                                                # annuler rend la zone active
    assert area.effect(ForceFieldComponent) is force and insp._fx_checks[ForceFieldComponent].isChecked()
    insp.deleteLater()


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
