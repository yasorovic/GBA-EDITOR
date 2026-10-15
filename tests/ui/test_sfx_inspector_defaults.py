"""L'inspecteur d'effet règle le taux et la protection ; le panoramique de départ se règle à la table de mixage de l'éditeur
d'effet (l'axe `panning`) ; le sidecar les garde. (Volume, hauteur, variation et fondus : cf. `test_sfx_editor.py`.)"""
from __future__ import annotations

import wave
from pathlib import Path

import pytest

from asset_fixtures import create
from core.models.audio import PANNING_MAX
from core.project import Project
from ui.common.deferred_writes import get_deferred_writes
from ui.sound_mixer.sfx_editor import SfxEditor
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


@pytest.fixture
def pan(qapp, project, inspector):
    """L'axe du panoramique, à la table de mixage de l'éditeur d'effet, sur le même effet que l'inspecteur."""
    editor = SfxEditor()
    editor.load(project, inspector.sfx)
    return editor._mix.fader("panning")


def test_the_axis_shows_the_default_and_stays_inside_the_range(pan, inspector):
    assert pan.value() == 0
    assert (pan.minimum(), pan.maximum()) == (-PANNING_MAX, PANNING_MAX)
    # Ce qui se règle ailleurs n'a plus de champ ici.
    assert not any(hasattr(inspector, name) for name in ("_pitch", "_spread", "_vol", "_pan"))


def _on_disk(project: Project):
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    return reopened.sfx.get("coin")


def test_a_change_is_written_to_the_effect_and_survives_reopening(pan, inspector, project):
    changed = []
    inspector.changed.connect(lambda: changed.append(1))

    pan.setValue(-40)

    # Le panoramique ne change ni le rendu ni l'explorateur : rien n'est rafraîchi à chaque cran.
    assert inspector.sfx.panning == -40 and changed == []
    get_deferred_writes().flush()
    assert _on_disk(project).panning == -40


def test_loading_another_effect_does_not_write_anything_back(pan, inspector, project):
    pan.setValue(25)
    other_src = project.assets_dir / "boom.wav"
    other_src.write_bytes((project.assets_dir / "coin.wav").read_bytes())
    other = create(project, "sfx", other_src)

    editor = SfxEditor()
    editor.load(project, other)

    assert editor._mix.fader("panning").value() == 0
    assert inspector.sfx.panning == 25                                             # le premier n'a pas bougé


def test_turning_a_field_writes_once_after_the_hand_stops_not_at_every_notch(pan, inspector, project):
    for value in range(1, 11):
        pan.setValue(value)

    assert get_deferred_writes().has_pending()                    # la valeur vit en mémoire, rien n'est parti
    assert _on_disk(project).panning == 0

    get_deferred_writes().flush()

    assert not get_deferred_writes().has_pending()
    assert _on_disk(project).panning == 10                        # l'état final, pas dix écritures


def test_an_effect_deleted_while_its_write_waits_is_not_written_back(pan, inspector, project):
    pan.setValue(30)
    project.sfx.delete(inspector.sfx)

    get_deferred_writes().flush()

    assert _on_disk(project) is None


def test_the_effect_editor_and_the_inspector_share_one_write(inspector, project):
    editor = SfxEditor()
    editor.load(project, inspector.sfx)

    editor._mix.fader("panning").setValue(30)
    editor._mix.fade("fade_out").setValue(12)                     # deux réglages, un même effet : une seule écriture

    assert len(get_deferred_writes()._pending) == 1
    get_deferred_writes().flush()
    saved = _on_disk(project)
    assert (saved.panning, saved.fade_out) == (30, 12)


def test_the_axis_reads_and_types_the_side_not_the_sign():
    from ui.sound_mixer.mix_faders import pan_text, pan_value
    assert [pan_text(v) for v in (-40, 0, 25)] == ["L 40", "C", "R 25"]
    assert [pan_value(t) for t in ("L 40", "C", "R 25", "-40", "25", "0", "x")] == [-40, 0, 25, -40, 25, 0, None]
