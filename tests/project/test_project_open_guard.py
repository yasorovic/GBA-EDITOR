"""Un dossier sans manifeste n'est pas un projet : `Project.open` le refuse
sans rien écrire dessus (sinon un dossier vide devenait un projet fantôme)."""
from pathlib import Path

import pytest

from core.project import Project
from core.project_paths import ProjectManifestError, ProjectNotFoundError


def test_open_refuses_an_empty_folder_and_leaves_it_untouched(tmp_path: Path):
    with pytest.raises(ProjectNotFoundError):
        Project.open(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_open_refuses_a_missing_folder_without_creating_it(tmp_path: Path):
    target = tmp_path / "Nowhere"

    with pytest.raises(ProjectNotFoundError):
        Project.open(target)

    assert not target.exists()


def test_not_found_is_a_manifest_error(tmp_path: Path):
    """Les appelants qui refusent déjà un dossier ambigu attrapent ce cas aussi."""
    with pytest.raises(ProjectManifestError):
        Project.open(tmp_path)


def test_open_still_reads_a_created_project(tmp_path: Path):
    created = Project.create(tmp_path / "Game", "Game")

    reopened = Project.open(created.root)

    assert [scene.name for scene in reopened.scenes] == ["Scene_01"]
