"""Supprimer un élément puis en recréer un du même nom ne doit pas faire effacer
le remplaçant à la fermeture (`commit_all_removals`)."""
from pathlib import Path

from core.models.scene import Scene
from core.project import Project


def test_recreated_scene_survives_closing(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    project.scenes.soft_delete(project.scenes[0])

    replacement = Scene(name="Scene_01")
    replacement.notes = "mon travail"
    project.scenes.append(replacement)
    project.save_scene(replacement)

    project.commit_all_removals()

    reopened = Project.open(project.root)
    assert [scene.notes for scene in reopened.scenes] == ["mon travail"]


def test_a_plain_soft_delete_is_still_committed(tmp_path: Path):
    project = Project.create(tmp_path / "Game", "Game")
    project.scenes.soft_delete(project.scenes[0])

    project.commit_all_removals()

    assert not (project.root / "project" / "scenes" / "Scene_01.json").exists()
