"""La file d'écritures différées : un geste continu n'écrit qu'une fois, et rien ne reste en attente quand on part."""
from __future__ import annotations

import pytest

from ui.common.deferred_writes import DeferredWrites


@pytest.fixture
def queue(qapp):
    return DeferredWrites()


def test_a_scheduled_write_waits_and_the_indicator_has_something_pending(queue):
    done = []
    queue.schedule("a", lambda: done.append("a"))

    assert queue.has_pending() and done == []
    assert queue._timer.isActive()                                  # elle partira seule après le silence


def test_the_same_key_keeps_only_the_last_write(queue):
    done = []
    for value in range(10):
        queue.schedule("sidecar", lambda value=value: done.append(value))

    queue.flush()

    assert done == [9]                                              # l'état final, pas dix écritures


def test_different_keys_do_not_overwrite_each_other(queue):
    done = []
    queue.schedule("a", lambda: done.append("a"))
    queue.schedule("b", lambda: done.append("b"))

    queue.flush()

    assert sorted(done) == ["a", "b"] and not queue.has_pending() and not queue._timer.isActive()


def test_the_silence_timer_flushes(queue):
    done = []
    queue.schedule("a", lambda: done.append(1))

    queue._timer.stop()
    queue._timer.timeout.emit()

    assert done == [1] and not queue.has_pending()


def test_a_failing_write_does_not_stop_the_others_and_is_reported(queue):
    done = []

    def boom():
        raise OSError("disk full")

    queue.schedule("bad", boom)
    queue.schedule("good", lambda: done.append("good"))

    with pytest.raises(OSError, match="disk full"):
        queue.flush()

    assert done == ["good"] and not queue.has_pending()             # l'écriture en échec n'est pas rejouée en boucle


def test_nothing_is_written_while_a_mouse_button_is_held_the_write_waits_for_the_release(queue, monkeypatch):
    """Une main qui hésite en plein glisser (souris immobile plus que le silence) ne réécrit pas le fichier à chaque pause."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    done = []
    queue.schedule("a", lambda: done.append(1))
    held = {"on": True}
    monkeypatch.setattr(QGuiApplication, "mouseButtons",
                        staticmethod(lambda: Qt.MouseButton.LeftButton if held["on"] else Qt.MouseButton.NoButton))

    queue._timer.stop()
    queue._timer.timeout.emit()                                    # le silence passe, la main est toujours posée

    assert done == [] and queue.has_pending() and queue._timer.isActive()   # on a repris un silence, rien n'est parti

    held["on"] = False
    queue._timer.stop()
    queue._timer.timeout.emit()                                    # la main s'est levée

    assert done == [1] and not queue.has_pending()


def test_an_explicit_flush_does_not_wait_for_the_mouse(queue, monkeypatch):
    """Changer d'écran, lancer un build, fermer : on écrit tout de suite, la souris fût-elle enfoncée."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    monkeypatch.setattr(QGuiApplication, "mouseButtons", staticmethod(lambda: Qt.MouseButton.LeftButton))
    done = []
    queue.schedule("a", lambda: done.append(1))

    queue.flush()

    assert done == [1]
