"""À l'ouverture de l'écran Animations, un sprite est toujours sélectionné : le dernier retenu, sinon le premier."""
from __future__ import annotations

from PyQt6.QtCore import QSettings

from core.models.scene import Scene  # noqa: F401  (charge les modèles dans le même ordre que l'éditeur)
from core.models.sprite import AnimState, SpriteAsset
from core.project import Project
from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen


def _project(tmp_path):
    project = Project(tmp_path / "jeu")
    project.root.mkdir(parents=True, exist_ok=True)
    for name in ("Alpha", "Beta"):
        project.sprites.append(SpriteAsset(name=name, asset=f"{name}.png", states=[AnimState(name="Idle")]))
    return project


def _opened(qapp, project):
    screen = SpriteEditorScreen()
    screen.load_project(project)
    qapp.processEvents()
    return screen


def test_the_first_sprite_is_selected_when_nothing_was_remembered(qapp, tmp_path):
    project = _project(tmp_path)
    QSettings("Backstage", "SpriteEditor").remove(f"last_sprite/{project.root}")

    screen = _opened(qapp, project)

    assert screen._left._current_sprite is not None and screen._left._current_sprite.name == "Alpha"


def test_the_remembered_sprite_comes_back_on_the_next_opening(qapp, tmp_path):
    project = _project(tmp_path)
    screen = _opened(qapp, project)
    screen.select_sprite("Beta")
    qapp.processEvents()

    reopened = _opened(qapp, project)

    assert reopened._left._current_sprite.name == "Beta"
