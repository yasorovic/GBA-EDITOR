"""Glisser plusieurs acteurs sélectionnés : tous écrivent leur position, en UNE entrée d'historique.

Qt déplace toute la sélection avec l'item saisi ; sans armement des autres, ils glissaient à l'écran sans que leur
x/y bouge dans le modèle (ils revenaient à leur place au rechargement), et seul l'item saisi entrait dans l'historique.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from core.history import get_history
from core.project import Project

DEMO = Path(__file__).resolve().parents[3] / "Project Demo" / "Platformer"


@pytest.fixture(autouse=True)
def _grid_choice_stays_in_the_test(tmp_path, monkeypatch):
    """La grille retenue d'une session à l'autre ne touche jamais les réglages de l'auteur."""
    from PyQt6.QtCore import QSettings
    from ui.scene_manager.scene_canvas import SceneEditor
    ini = str(tmp_path / "canvas.ini")
    monkeypatch.setattr(SceneEditor, "_grid_settings", staticmethod(lambda: QSettings(ini, QSettings.Format.IniFormat)))


@pytest.fixture
def editor(qapp, tmp_path):
    if not DEMO.exists():
        pytest.skip("démo absente")
    root = tmp_path / "P"
    shutil.copytree(DEMO, root)
    from ui.scene_manager.scene_canvas import SceneEditor
    ed = SceneEditor()
    ed.resize(900, 700)
    ed.load_project(Project.open(root))
    ed.show()
    ed._fit()
    get_history().clear()
    yield ed
    get_history().clear()


def _hit_point(view, item):
    """Un point du viewport où le clic arrive sur cet item (le cadre d'écran, au-dessus, laisse passer la souris)."""
    rect = item.sceneBoundingRect()
    for iy in range(int(rect.height())):
        for ix in range(int(rect.width())):
            pt = view.mapFromScene(QPointF(rect.x() + ix + 0.5, rect.y() + iy + 0.5))
            if next((x for x in view.items(pt) if x.acceptedMouseButtons()), None) is item:
                return pt
    return None


def test_les_acteurs_selectionnes_suivent_dans_le_modele_et_l_historique(editor):
    scene = editor._gba_scene
    items = list(scene._sprite_items)[:3]
    assert len(items) == 3
    for it in items:
        it.setSelected(True)
    before = [(it.scene_sprite.x, it.scene_sprite.y) for it in items]
    view = editor._gba_view
    viewport = view.viewport()
    start = _hit_point(view, items[0])
    assert start is not None
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 6):
        QTest.mouseMove(viewport, start + QPoint(step * 8, step * 4))
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + QPoint(40, 20))
    after = [(it.scene_sprite.x, it.scene_sprite.y) for it in items]
    assert all(a != b for a, b in zip(after, before))                               # tous ont bougé dans le modèle
    assert len({(a[0] - b[0], a[1] - b[1]) for a, b in zip(after, before)}) == 1   # du même écart
    assert len(get_history()._undo) == 1                                           # un seul Ctrl+Z
    get_history().undo()
    assert [(it.scene_sprite.x, it.scene_sprite.y) for it in items] == before


def test_un_acteur_devenu_repere_ne_retrouve_pas_son_ancienne_image(editor):
    item = next(it for it in editor._gba_scene._sprite_items if not it._placeholder)
    actor = item.scene_sprite
    editor._raw_sprite[id(actor)] = item.pixmap()          # ce que le chargement y a rangé
    actor.components = [c for c in actor.components if type(c).__name__ != "SpriteComponent"]
    editor._reload_sprites()
    assert id(actor) not in editor._raw_sprite


def _parent_and_child(editor):
    """Deux acteurs de la scène reliés par `Actor.parent`."""
    actors = [it.scene_sprite for it in editor._gba_scene._sprite_items]
    parent, child = actors[0], actors[1]
    child.parent = parent.name
    return parent, child


def test_une_fleche_sur_plusieurs_acteurs_est_une_seule_entree_et_emporte_les_enfants(editor):
    parent, child = _parent_and_child(editor)
    items = list(editor._gba_scene._sprite_items)
    items[0].setSelected(True)                       # le parent seul est sélectionné
    before = {a.name: (a.x, a.y) for a in (parent, child)}
    for _ in range(5):                               # flèche maintenue
        editor._shortcut_nudge(1, 0)
    assert (parent.x, parent.y) == (before[parent.name][0] + 5, before[parent.name][1])
    assert (child.x, child.y) == (before[child.name][0] + 5, before[child.name][1])    # l'enfant suit, comme à la souris
    assert len(get_history()._undo) == 1             # fusionné : un seul Ctrl+Z pour toute la rafale
    get_history().undo()
    assert {a.name: (a.x, a.y) for a in (parent, child)} == before


def test_dupliquer_un_parent_et_son_enfant_rattache_la_copie_a_la_copie(editor, monkeypatch):
    from core.command_dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    monkeypatch.setattr(dispatcher, "_project", editor._project)
    monkeypatch.setattr(dispatcher, "_save_scene", lambda *a, **k: None)
    parent, child = _parent_and_child(editor)
    copies = dispatcher.duplicate_actors([parent, child])
    parent_copy, child_copy = copies
    assert child_copy.parent == parent_copy.name                  # et non l'original
    solo = dispatcher.duplicate_actors([child])[0]
    assert solo.parent == parent.name                             # parent resté en place : gardé
    editor._project.active_scene.actors.remove(parent)
    stray = dispatcher.paste_actors([child])[0]
    assert stray.parent is None                                   # parent absent de la scène : racine


def test_une_camera_selectionnee_ne_declenche_une_sauvegarde_que_si_elle_a_bouge(editor):
    from PyQt6.QtWidgets import QApplication
    item = next(it for it in editor._gba_scene.camera_items() if it.camera is not None)
    item.setSelected(True)
    QApplication.processEvents()
    emitted = []
    editor.scene_changed.connect(lambda: emitted.append(1))
    editor._chk_grid.set_state(1)                         # une repeinture de la scène, sans rien déplacer
    editor._chk_grid.set_state(0)
    QApplication.processEvents()
    editor._on_scene_item_changed()
    assert emitted == []
    item.setPos(item.pos().x() + 8, item.pos().y())       # un vrai déplacement, bouton relâché
    editor._on_scene_item_changed()
    assert emitted == [1]


def test_renommer_un_acteur_est_annulable_et_refuse_un_nom_pris(editor):
    scene = editor._project.active_scene
    first, second = scene.actors[0], scene.actors[1]
    old = first.name
    assert editor._project.rename_actor(first, second.name) is False          # déjà pris dans la scène : refusé
    assert first.name == old
    from core.history import RenameActorCmd
    get_history().push(RenameActorCmd(editor._project, first, "Renamed_Hero"))
    assert first.name == "Renamed_Hero"
    get_history().undo()
    assert first.name == old


def test_une_commande_deja_executee_respecte_le_plafond_de_l_historique(editor):
    from core.history import _MAX_HISTORY, Command

    class Noop(Command):
        label = "noop"
        def execute(self): raise AssertionError("ne doit pas être rejouée")
        def undo(self): pass

    history = get_history()
    for _ in range(_MAX_HISTORY + 20):
        history.push_executed(Noop())
    assert len(history._undo) == _MAX_HISTORY


def test_un_enfant_selectionne_avec_son_parent_ne_bouge_pas_deux_fois(editor):
    scene = editor._gba_scene
    items = list(scene._sprite_items)[:3]
    parent, child, other = (it.scene_sprite for it in items)
    child.parent = parent.name
    for it in items:
        it.setSelected(True)
    before = [(a.x, a.y) for a in (parent, child, other)]
    view = editor._gba_view
    viewport = view.viewport()
    start = _hit_point(view, items[2])                  # on saisit l'acteur libre
    assert start is not None
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    for step in range(1, 6):
        QTest.mouseMove(viewport, start + QPoint(step * 8, step * 4))
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + QPoint(40, 20))
    deltas = {(a.x - b[0], a.y - b[1]) for a, b in zip((parent, child, other), before)}
    assert len(deltas) == 1 and deltas != {(0, 0)}      # même écart pour tous : l'enfant n'est pas doublé


def test_defaire_un_renommage_sauvegarde_la_scene_de_l_acteur(editor):
    from core.history import RenameActorCmd
    scene = editor._project.active_scene
    actor = scene.actors[0]
    saved = []
    editor._project.save_scene = lambda s: saved.append(s)     # sans écrire sur disque
    get_history().push(RenameActorCmd(editor._project, actor, "Renamed_Hero"))
    saved.clear()
    get_history().undo()
    assert saved == [scene]


def test_un_seul_bouton_parcourt_pas_de_grille_8_puis_16_et_revient(editor):
    from PyQt6.QtWidgets import QApplication
    button, scene = editor._chk_grid, editor._gba_scene

    def grid():
        item = scene._grid_item
        return (item.isVisible(), item._cell) if item is not None else (False, None)
    assert button.state == 0 and not button.isChecked() and grid()[0] is False
    seen = []
    for _ in range(4):
        button.click()
        QApplication.processEvents()
        seen.append((button.state, button.isChecked(), grid()))
    assert [s[0] for s in seen] == [1, 2, 0, 1]
    assert [s[1] for s in seen] == [True, True, False, True]
    assert seen[0][2] == (True, 8) and seen[1][2] == (True, 16) and seen[2][2][0] is False


def test_la_grille_choisie_revient_a_la_prochaine_ouverture(editor, tmp_path):
    from ui.scene_manager.scene_canvas import SceneEditor
    editor._chk_grid.set_state(2)
    second = SceneEditor()
    second.show()
    assert second._chk_grid.state == 2 and second._chk_grid.isChecked()
    assert second._gba_scene._grid_item is not None and second._gba_scene._grid_item.isVisible()
    editor._chk_grid.set_state(0)
    third = SceneEditor()
    assert third._chk_grid.state == 0
