"""L'inspecteur d'un jingle règle la politique envers la musique ; le sidecar la garde.

La case Loop n'y est plus (un jingle ne boucle pas) ; le niveau et la remontée ne valent que pour « baisser » et
n'apparaissent que pour elle."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "editor"))
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / "tests" / "audio"))

import module_fixtures as F                                   # noqa: E402
from asset_fixtures import create                             # noqa: E402
from core.project import Project                              # noqa: E402
from ui.common.deferred_writes import get_deferred_writes     # noqa: E402
from ui.sound_mixer.sound_panel import JingleInspector        # noqa: E402


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def inspector(qapp, project):
    path = project.assets_dir / "jingles" / "Fanfare.mod"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(F.make_mod())
    project.load()
    project.load_all_resources()
    widget = JingleInspector()
    widget.jingle = create(project, "jingles", path)
    widget.load(widget.jingle, project)
    return widget


def _on_disk(project: Project):
    reopened = Project.open(project.root)
    reopened.load_all_resources()
    return reopened.jingles.get("Fanfare")


def test_a_jingle_has_no_loop_box_and_starts_on_keep_playing(inspector):
    assert not hasattr(inspector, "_loop")
    assert inspector._policy.currentData() == "mix"
    assert inspector._duck_box.isHidden()


def test_choosing_to_lower_the_music_shows_its_level_and_climb(inspector):
    inspector._policy.setCurrentIndex(inspector._policy.findData("duck"))
    assert not inspector._duck_box.isHidden()
    inspector._policy.setCurrentIndex(inspector._policy.findData("pause"))
    assert inspector._duck_box.isHidden()


def test_loading_a_lowering_jingle_shows_its_fields_at_once(inspector, project):
    from core.models.audio import Jingle
    inspector.jingle.music_policy = "duck"
    inspector.load(inspector.jingle, project)
    assert not inspector._duck_box.isHidden()


def test_the_policy_is_written_once_and_survives_reopening(inspector, project):
    changed = []
    inspector.changed.connect(lambda: changed.append(1))
    inspector._policy.setCurrentIndex(inspector._policy.findData("duck"))
    inspector._duck_level.setValue(20)
    inspector._duck_release.setValue(45)

    assert inspector.jingle.music_policy == "duck" and changed == []        # rien à rafraîchir : ni rendu ni explorateur
    assert get_deferred_writes().has_pending()
    get_deferred_writes().flush()
    saved = _on_disk(project)
    assert (saved.music_policy, saved.duck_level, saved.duck_release) == ("duck", 20, 45)


def test_loading_another_jingle_does_not_write_anything_back(inspector, project):
    inspector._policy.setCurrentIndex(inspector._policy.findData("pause"))
    other_path = project.assets_dir / "jingles" / "Chime.mod"
    other_path.write_bytes(F.make_mod())
    other = create(project, "jingles", other_path)

    inspector.load(other, project)

    assert inspector._policy.currentData() == "mix"
    assert inspector.jingle.music_policy == "pause"                          # le premier n'a pas bougé
