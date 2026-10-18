"""`codegen/window_alloc.py` — quelle intention reçoit WIN0/WIN1 ; une erreur est visuelle et muette."""
from types import SimpleNamespace as NS

from codegen.window_alloc import scene_window_budget, scene_window_layout


def _camera(w=240, h=160):
    return NS(px=lambda name, project=None: {"frame_w": w, "frame_h": h}[name])


def _scene(cameras=(), windows=()):
    return NS(cameras=list(cameras), windows=[NS(name=n, is_obj=obj) for n, obj in windows])


def test_camera_takes_first_slot_then_windows_in_order_and_extras_overflow():
    layout = scene_window_layout(None, _scene([_camera(120, 160)], [("A", False), ("B", False)]))
    assert layout.camera_slot == 0
    assert layout.slots == {"A": 1}
    assert layout.overflow == ["B"]


def test_without_reduced_camera_two_windows_fit():
    layout = scene_window_layout(None, _scene([_camera()], [("A", False), ("B", False)]))
    assert layout.camera_slot is None
    assert layout.slots == {"A": 0, "B": 1}
    assert layout.overflow == []


def test_object_window_is_never_allocated_and_budget_shows_overflow():
    scene = _scene([_camera(100, 100)], [("A", False), ("B", False), ("O", True)])
    assert "O" not in scene_window_layout(None, scene).slots
    assert scene_window_budget(scene) == (3, 2)
