"""Canvas → onglet Disk : un acteur lâché sur un dossier y devient un prefab ; l'instance d'un prefab en fait une copie."""
from contextlib import nullcontext
from types import SimpleNamespace

from core.command_dispatcher import get_dispatcher
from core.models.scene import Actor
from core.project import Project


def _dispatcher(tmp_path):
    project = Project.open(Project.create(tmp_path / "Jeu", "Jeu").root)
    get_dispatcher().setup(project, SimpleNamespace(suspended=nullcontext))
    folder = project.user_library_dir / "Rangement"
    folder.mkdir()
    return get_dispatcher(), project, folder


def test_a_plain_actor_becomes_a_prefab_in_the_folder_and_is_linked_to_it(tmp_path):
    dispatcher, project, folder = _dispatcher(tmp_path)
    actor = Actor(name="Hero")
    project.scenes[0].actors.append(actor)

    prefab = dispatcher.export_actor_to_folder(actor, folder)

    assert prefab.name == "Hero" and actor.prefab_name == "Hero"
    assert (folder / f"Hero{prefab.sidecar_extension}").is_file()


def test_the_instance_of_a_prefab_copies_that_prefab_under_a_free_name(tmp_path):
    dispatcher, project, folder = _dispatcher(tmp_path)
    actor = Actor(name="Hero")
    project.scenes[0].actors.append(actor)
    original = dispatcher.export_actor_to_folder(actor, project.user_library_dir)
    count = len(list(project.prefabs))

    copy = dispatcher.export_actor_to_folder(actor, folder)

    assert copy is not original and copy.name == "Hero_2" and copy.id != original.id
    assert len(list(project.prefabs)) == count + 1
    assert actor.prefab_name == "Hero"                                   # l'instance reste liée à l'original
    assert (folder / f"Hero_2{copy.sidecar_extension}").is_file()
    assert (project.user_library_dir / f"Hero{original.sidecar_extension}").is_file()
