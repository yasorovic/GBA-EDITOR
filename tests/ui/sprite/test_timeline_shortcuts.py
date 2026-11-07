"""Suppr vide les frames, Ctrl+Suppr les retire, dans la timeline uniquement."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from core.models.sprite import SpriteAsset, AnimFrame, TilePlacement
from ui.sprite_editor.sprite_timeline import SpriteTimeline


@pytest.mark.parametrize("read_only", [False, True])
def test_suppr_et_ctrl_suppr_sur_selection_multiple(qapp, tmp_path, monkeypatch, read_only):
    from core import keybindings
    monkeypatch.setattr(keybindings, "CONFIG_FILE", tmp_path / "keys.json")
    monkeypatch.setattr(keybindings, "_instance", None)
    sprite = SpriteAsset(name="Hero")
    state = sprite.states[0]
    sd = state.directions[0]
    sd.frames = [AnimFrame(tiles=[TilePlacement()], event_name="step") for _ in range(3)]
    timeline = SpriteTimeline()
    timeline.load(sprite, state, sd, None, read_only=read_only)
    timeline.show()
    timeline.setFocus()
    qapp.processEvents()
    timeline._select_many([0, 1], 0)
    changed = []
    timeline.frames_changed.connect(lambda: changed.append(True))
    QTest.keyClick(timeline, Qt.Key.Key_Delete)
    assert len(sd.frames) == 3
    assert all(bool(frame.tiles) == read_only for frame in sd.frames[:2])
    assert all(frame.event_name == "step" for frame in sd.frames)
    QTest.keyClick(timeline, Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)
    assert len(sd.frames) == (3 if read_only else 1)
    assert len(changed) == (0 if read_only else 2)
    QTest.keyClick(timeline, Qt.Key.Key_Delete, Qt.KeyboardModifier.ControlModifier)
    assert len(sd.frames) == (3 if read_only else 1)
    timeline.close()
