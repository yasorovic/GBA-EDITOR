"""La liste des actions : une ligne du temps (rétablir grisé au-dessus, annuler dessous), un clic joue tous les pas
jusqu'à la ligne, et la profondeur de la pile est un réglage de la machine."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import interface_preferences as prefs
from core.history import AddActorCmd, CommandHistory
from core.models.scene import Actor, Scene


def _history(*names):
    history, scene = CommandHistory(), Scene(name="Test")
    for name in names:
        history.push(AddActorCmd(scene, Actor(name=name)))
    return history, scene.actors


def test_the_popup_lists_redo_above_undo_and_clicks_report_signed_steps(qapp):
    from ui.common.action_list_popup import ActionListPopup

    history, _ = _history("one", "two", "three", "four")
    history.undo()
    history.undo()                                   # pile : one, two ; à rejouer : three puis four
    popup = ActionListPopup()
    popup.set_entries(history.undo_labels, history.redo_labels)

    rows = [popup._list.item(i) for i in range(popup._list.count())]
    assert [r.text() for r in rows] == ["Add actor four", "Add actor three", "Add actor two", "Add actor one"]   # le plus récent en haut

    picked = []
    popup.picked.connect(picked.append)
    popup._list.itemClicked.emit(rows[0])            # tout rejouer, jusqu'à « four »
    popup._list.itemClicked.emit(rows[1])            # « three » : la prochaine à rejouer
    popup._list.itemClicked.emit(rows[3])            # « one » : défaire deux actions
    assert picked == [2, 1, -2]


def test_the_empty_popup_says_so_and_a_click_plays_nothing(qapp):
    from ui.common.action_list_popup import ActionListPopup

    popup = ActionListPopup()
    popup.set_entries([], [])
    picked = []
    popup.picked.connect(picked.append)
    popup._list.itemClicked.emit(popup._list.item(0))
    assert popup._list.count() == 1 and picked == []


def test_jumping_plays_every_step_then_refreshes_once():
    from window import MainWindow

    history, box = _history("one", "two", "three")
    flushed, said = [], []
    w = SimpleNamespace(_history=history, _status=SimpleNamespace(showMessage=lambda *a: said.append(a)),
                        _flush_after_undo_redo=lambda: flushed.append(1))

    MainWindow._jump_history(w, -2)
    from ui.common.labels import history_text
    assert [actor.name for actor in box] == ["one"]
    assert [history_text(action) for action in history.redo_labels] == ["Add actor two", "Add actor three"]
    assert len(flushed) == 1
    MainWindow._jump_history(w, 2)
    assert [actor.name for actor in box] == ["one", "two", "three"] and len(flushed) == 2
    MainWindow._jump_history(w, 5)                   # rien à rejouer : aucun rafraîchissement de plus
    assert len(flushed) == 2


def test_the_undo_depth_is_a_machine_setting_and_trims_at_once(monkeypatch, tmp_path):
    monkeypatch.setattr(prefs, "CONFIG_FILE", tmp_path / "interface.json")
    monkeypatch.setattr(prefs, "_cache", None)

    assert prefs.undo_depth() == 200
    history, _ = _history(*[str(i) for i in range(30)])
    assert len(history.undo_labels) == 30

    prefs.set_undo_depth(10)
    history.trim()
    from ui.common.labels import history_text
    assert history_text(history.undo_labels[0]) == "Add actor 29" and len(history.undo_labels) == 10

    prefs.set_undo_depth(5000)                       # borné
    assert prefs.undo_depth() == prefs.UNDO_DEPTH_RANGE[1]
