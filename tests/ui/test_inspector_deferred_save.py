"""Un champ qu'on tourne dans un inspecteur n'écrit pas la scène à chaque cran : une écriture, après le geste.

Les inspecteurs d'acteur et de scène passent par `SetFieldCmd`, qui appelle `persist_fn` à CHAQUE valeur ; la fusion des
commandes ne fusionne que l'historique d'annulation. L'écriture, elle, passe par la file différée
(`ui/common/deferred_writes.py`) : le modèle est à jour tout de suite, le disque après un silence.
"""
from __future__ import annotations

import pytest

from core.history import get_history
from core.models.scene import Actor
from core.project import Project
from ui.common.deferred_writes import get_deferred_writes
from ui.scene_manager.inspectors.actor_inspector import ActorInspector


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


@pytest.fixture
def project(tmp_path) -> Project:
    return Project.create(tmp_path / "Game", "Game")


@pytest.fixture
def scene_writes(project, monkeypatch):
    """Les écritures de scène que le disque reçoit (sans les empêcher)."""
    written: list = []
    real = project.scenes.save
    monkeypatch.setattr(project.scenes, "save", lambda item, *a, **k: (written.append(item), real(item, *a, **k))[1])
    return written


def test_turning_an_actor_field_writes_the_scene_once_after_the_gesture(qapp, history, project, scene_writes):
    scene = project.active_scene
    actor = Actor(name="Hero", rotation=0)
    scene.actors.append(actor)
    inspector = ActorInspector()
    inspector.load(actor, project, scene)

    for value in range(1, 11):
        inspector._trotation._spin.setValue(value)

    assert actor.rotation == 10                      # le modèle suit chaque cran
    assert scene_writes == [] and get_deferred_writes().has_pending()

    get_deferred_writes().flush()

    assert scene_writes == [scene]                    # une seule écriture, de l'état final
    assert not get_deferred_writes().has_pending()


def test_turning_an_interface_field_writes_only_its_layout_not_the_whole_project(qapp, history, project, monkeypatch):
    from core.command_dispatcher import get_dispatcher
    from core.models.ui_region import UILayout, UIText
    from ui.scene_manager.inspectors.ui_inspector import UIInspector
    layout = UILayout(name="HUD")
    element = UIText(name="Score", x=0, y=0, w=32, h=8)
    layout.elements.append(element)
    project.ui_layouts.append(layout)
    project.ui_layouts.save(layout)
    layout_writes, project_writes = [], []
    real = project.ui_layouts.save
    monkeypatch.setattr(project.ui_layouts, "save", lambda item, *a, **k: (layout_writes.append(item), real(item, *a, **k))[1])
    monkeypatch.setattr(get_dispatcher(), "save_all", lambda: project_writes.append(1))
    inspector = UIInspector()
    inspector.load(layout, element, project=project, scene=project.active_scene)

    for value in range(1, 11):
        inspector._sp["x"].setValue(value)

    assert element.x == 10 and layout_writes == []                       # le modèle suit, le disque attend
    get_deferred_writes().flush()
    assert layout_writes == [layout] and project_writes == []            # une écriture de la mise en page, pas du projet


def test_an_undo_is_written_too(qapp, history, project, scene_writes):
    scene = project.active_scene
    actor = Actor(name="Hero", rotation=0)
    scene.actors.append(actor)
    inspector = ActorInspector()
    inspector.load(actor, project, scene)
    inspector._trotation._spin.setValue(5)
    get_deferred_writes().flush()
    scene_writes.clear()

    history.undo()

    assert actor.rotation == 0 and get_deferred_writes().has_pending()
    get_deferred_writes().flush()
    assert scene_writes == [scene]


def test_turning_a_project_setting_writes_the_manifest_once_after_the_gesture(qapp, history, project, monkeypatch):
    from ui.scene_manager.inspectors.project_settings_dialog import SoundPanel
    writes = []
    real = project.save_settings
    monkeypatch.setattr(project, "save_settings", lambda: (writes.append(1), real())[1])
    panel = SoundPanel(project)

    for value in range(9, 15):
        panel._spin_channels.setValue(value)

    assert project.settings.sound_channels == 14 and writes == []       # le réglage vaut tout de suite, le disque attend
    get_deferred_writes().flush()
    assert writes == [1]


def test_turning_a_sprite_speed_writes_the_sidecar_once_after_the_gesture(qapp, history, project, monkeypatch):
    from asset_fixtures import create
    from ui.sprite_editor.sprite_right_panel import SpriteRightPanel
    from core.models.sprite import AnimState
    src = project.assets_dir / "hero.png"
    src.parent.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtGui import QImage
    image = QImage(32, 16, QImage.Format.Format_ARGB32)
    image.fill(0xFFFF0000)
    assert image.save(str(src))
    sprite = create(project, "sprites", src)
    written = []
    real = project.sprites.save
    monkeypatch.setattr(project.sprites, "save", lambda item, *a, **k: (written.append(item), real(item, *a, **k))[1])
    panel = SpriteRightPanel()
    panel.load_sprite(sprite, project)
    panel._state = AnimState(name="idle")

    for value in range(10, 20):
        panel._sp_speed.setValue(value)

    assert panel._state.speed == 19 and written == []
    get_deferred_writes().flush()
    assert written == [sprite]


def test_an_inspector_change_arms_one_whole_project_write_in_the_shared_queue(qapp, monkeypatch):
    """Le minuteur de 400 ms de la fenêtre n'existe plus : son filet (`save_all`) passe par la même file que le reste,
    donc `has_pending` l'annonce à l'indicateur « Unsaved changes » et chaque `flush` (écran, build, Ctrl+S) le vide."""
    from types import SimpleNamespace
    from core.command_dispatcher import get_dispatcher
    from window import MainWindow
    saved = []
    monkeypatch.setattr(get_dispatcher(), "save_all", lambda: saved.append(1))
    window = SimpleNamespace(scene_editor=SimpleNamespace(move_actor_item=lambda actor: None))

    for _ in range(5):
        MainWindow._on_inspector_actor_changed(window, Actor(name="Hero"))

    assert saved == [] and get_deferred_writes().has_pending()
    get_deferred_writes().flush()
    assert saved == [1]
