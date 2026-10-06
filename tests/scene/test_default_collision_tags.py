"""Les tags de collision d'un projet neuf, et le dispatch de collision du générateur."""
from pathlib import Path

from core.models.components import CollisionBoxComponent, ScriptComponent
from core.models.scene import Actor
from core.project import Project


def test_new_project_declares_player_and_body(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    assert project.settings.collision_tags == ["Player", "body"]
    # Écrits sur disque, relus tels quels.
    reopened = Project.open(tmp_path / "Game")
    assert set(reopened.settings.collision_tags) == {"Player", "body"}


def test_existing_project_without_declared_tags_keeps_none(tmp_path):
    project = Project.create(tmp_path / "Game", "Game")
    project.settings.collision_tags = []
    project.save()
    assert Project.open(tmp_path / "Game").settings.collision_tags == []


def test_collision_enter_is_dispatched_to_scene_actor_script(tmp_path):
    """Régression : le dispatch de paire cherchait `Ball` au lieu de `<Scène>_Ball`
    dans les handlers définis, et n'appelait jamais `on_collision_enter`."""
    from core.toolchain import Toolchain
    from codegen import BuildWorker

    project = Project.create(tmp_path / "Game", "Game")
    scene = project.scenes[0]
    scripts = project.scripts_dir
    (scripts / "Hit.lua").write_text(
        "function on_collision_enter(other, my_box, other_box)\nend\n", encoding="utf-8")
    for name in ("A", "B"):
        actor = Actor(name=name)
        actor.components = [CollisionBoxComponent(w=8, h=8),
                            ScriptComponent(script="assets/scripts/Hit.lua")]
        scene.actors.append(actor)
    project.save()

    worker = BuildWorker(Project.open(tmp_path / "Game"), Toolchain())
    worker._step_make = lambda _p: True
    worker._step_launch_mgba = lambda _p: True
    worker.run()

    main_c = (Path(project.root) / "build" / "src" / "main.c").read_text(encoding="utf-8")
    assert f"{scene.name}_A_on_collision_enter(&g_actors[0],&g_actors[1]" in main_c
    assert f"{scene.name}_B_on_collision_enter(&g_actors[1],&g_actors[0]" in main_c
