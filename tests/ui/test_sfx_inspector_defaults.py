"""L'inspecteur d'effet règle la hauteur et le panoramique de départ ; le sidecar les garde."""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

from asset_fixtures import create
from core.models.audio import PANNING_MAX, SFX_PITCH_MAX, SFX_PITCH_MIN
from core.project import Project
from ui.sound_mixer.sound_panel import SfxInspector


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def inspector(qapp, project):
    src = project.assets_dir / "coin.wav"
    src.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(src), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(bytes(1600))
    widget = SfxInspector()
    widget.sfx = create(project, "sfx", src)
    widget.load(widget.sfx, project)
    return widget


def test_the_fields_show_the_defaults_and_stay_inside_the_range(inspector):
    assert (inspector._pitch.value(), inspector._pan.value()) == (100, 0)
    assert (inspector._pitch.minimum(), inspector._pitch.maximum()) == (SFX_PITCH_MIN, SFX_PITCH_MAX)
    assert (inspector._pan.minimum(), inspector._pan.maximum()) == (-PANNING_MAX, PANNING_MAX)


def test_a_change_is_written_to_the_effect_and_survives_reopening(inspector, project):
    changed = []
    inspector.changed.connect(lambda: changed.append(1))

    inspector._pitch.setValue(150)
    inspector._pan.setValue(-40)

    assert (inspector.sfx.pitch, inspector.sfx.panning) == (150, -40) and len(changed) == 2
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    assert (reopened.sfx.get("coin").pitch, reopened.sfx.get("coin").panning) == (150, -40)


def test_loading_another_effect_does_not_write_anything_back(inspector, project):
    inspector._pitch.setValue(150)
    other_src = project.assets_dir / "boom.wav"
    other_src.write_bytes((project.assets_dir / "coin.wav").read_bytes())
    other = create(project, "sfx", other_src)

    inspector.load(other, project)

    assert (inspector._pitch.value(), inspector._pan.value()) == (100, 0)
    assert inspector.sfx.pitch == 150                                              # le premier n'a pas bougé


def test_the_random_variation_is_written_inside_its_range(inspector, project):
    from core.models.audio import SFX_PITCH_VARIATION_MAX
    assert (inspector._spread.value(), inspector._spread.maximum()) == (0, SFX_PITCH_VARIATION_MAX)

    inspector._spread.setValue(15)

    assert inspector.sfx.pitch_variation == 15
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    assert reopened.sfx.get("coin").pitch_variation == 15
