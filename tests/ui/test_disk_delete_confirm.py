"""Supprimer depuis l'onglet Disk : pas de fenêtre pour un asset que rien ne cite (annulable, source gardée) ; une seule
question quand il est encore utilisé."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from ui.common.popup import MessageBox as QMessageBox

from asset_fixtures import create
from core import disk_tree
from core.models.components import SpriteComponent
from core.models.scene import Actor
from core.project import Project
from window import MainWindow


def _window(tmp_path: Path):
    project = Project.create(tmp_path / "Jeu", "Jeu")
    project = Project.open(project.root)
    project.load_all_resources()
    for name in ("hero", "tree"):
        path = project.user_library_dir / "Art" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), (200, 30, 30)).save(path)
        create(project, "sprites", path)
    pushed, shown = [], []
    fake = SimpleNamespace(project=project, _disk_push=pushed.append,
                           _status=SimpleNamespace(showMessage=lambda text, ms=0: shown.append(text)))
    return fake, project, pushed, shown


def _node(project, name):
    return disk_tree.DiskNode(f"{name}.sprite", project.user_library_dir / "Art" / f"{name}.sprite",
                              disk_tree.ASSET, name, "sprites")


def test_an_unused_asset_is_deleted_without_any_window(tmp_path, monkeypatch):
    fake, project, pushed, shown = _window(tmp_path)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.Yes)

    MainWindow._disk_delete_assets(fake, [_node(project, "tree")])

    assert asked == [] and len(pushed) == 1                                      # aucune fenêtre, la commande est poussée
    assert "Deleted 1 asset" in shown[0] and "Ctrl+Z" in shown[0]                # le geste dit comment l'annuler


def test_an_asset_still_in_use_asks_once_and_a_no_keeps_it(tmp_path, monkeypatch):
    fake, project, pushed, shown = _window(tmp_path)
    actor = Actor(name="Hero")
    actor.components.append(SpriteComponent(sprite_name="hero"))
    project.scenes[0].actors.append(actor)
    asked = []

    def refuse(parent, title, text, *rest):
        asked.append(text)
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "question", refuse)

    MainWindow._disk_delete_assets(fake, [_node(project, "hero"), _node(project, "tree")])

    assert len(asked) == 1 and 'actor "Hero"' in asked[0] and "Still used by" in asked[0]
    assert pushed == [] and shown == []                                          # refusé : rien n'est supprimé


def test_confirming_for_an_asset_in_use_deletes_it(tmp_path, monkeypatch):
    fake, project, pushed, _shown = _window(tmp_path)
    actor = Actor(name="Hero")
    actor.components.append(SpriteComponent(sprite_name="hero"))
    project.scenes[0].actors.append(actor)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    MainWindow._disk_delete_assets(fake, [_node(project, "hero")])

    assert len(pushed) == 1
