"""Le graphe des scènes est une projection des scripts, jamais un état à sauver."""
from __future__ import annotations


def _project(tmp_path):
    from core.project import Project
    from core.models.scene import Scene

    project = Project(tmp_path / "jeu")
    scripts = project.root / "assets" / "scripts" / "scenes"
    scripts.mkdir(parents=True)
    for name in ("Title", "Arena", "Victory"):
        project.scenes.append(Scene(name=name))
    project.settings.start_scene = "Title"
    return project, scripts


def test_scene_graph_derives_nodes_edges_and_call_locations(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    source = scripts / "title.lua"
    source.write_text(
        '-- scene:switch("Victory") is only a comment\n'
        'scene:switch("Arena")\n'
        'scene:switch("Arena")\n', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"

    graph = scene_graph(project)

    assert [(node.name, node.is_start) for node in graph.nodes] == [
        ("Title", True), ("Arena", False), ("Victory", False)]
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.source, edge.target) == ("Title", "Arena")
    assert [ref.line for ref in edge.refs] == [2, 3]
    assert all(ref.path == source and ref.api_key == "scene.switch" for ref in edge.refs)


def test_scene_graph_keeps_a_missing_target_as_an_edge_not_a_fake_scene(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (scripts / "arena.lua").write_text('scene:switch("Missing")', encoding="utf-8")
    project.scenes[1].script = "assets/scripts/scenes/arena.lua"

    graph = scene_graph(project)

    assert [node.name for node in graph.nodes] == ["Title", "Arena", "Victory"]
    assert [(edge.source, edge.target) for edge in graph.edges] == [("Arena", "Missing")]


def test_scene_graph_never_invents_an_edge_for_a_calculated_target(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (scripts / "title.lua").write_text('scene:switch(next_scene)', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"

    graph = scene_graph(project)
    # Pas d'arête, mais le fait est retenu sur le nœud : la scène a une sortie
    # qu'on ne sait pas résoudre.
    assert graph.edges == ()
    assert {n.name: n.has_dynamic_exit for n in graph.nodes} == {
        "Title": True, "Arena": False, "Victory": False}


def _diag(project):
    from scripting.scene_graph import node_diagnostics, scene_graph
    return node_diagnostics(scene_graph(project))


def test_node_diagnostics_reports_entry_and_exit_states(tmp_path):
    from scripting.scene_graph import EntryState, ExitState

    project, scripts = _project(tmp_path)
    # Title (départ) → Arena littéral ; Arena → cible calculée ; Victory : rien.
    (scripts / "title.lua").write_text('scene:switch("Arena")', encoding="utf-8")
    (scripts / "arena.lua").write_text('scene:switch(wherever)', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"
    project.scenes[1].script = "assets/scripts/scenes/arena.lua"

    diag = _diag(project)
    # Title : atteignable car départ (aucune arête entrante), sortie résolue.
    assert diag["Title"].entry is EntryState.REACHABLE
    assert diag["Title"].exit is ExitState.LITERAL
    # Arena : atteignable (Title y mène), sortie calculée = vigilance.
    assert diag["Arena"].entry is EntryState.REACHABLE
    assert diag["Arena"].exit is ExitState.DYNAMIC
    # Victory : inatteignable et cul-de-sac.
    assert diag["Victory"].entry is EntryState.UNREACHABLE
    assert diag["Victory"].exit is ExitState.NONE


def test_node_diagnostics_flags_a_broken_target_over_a_resolved_one(tmp_path):
    from scripting.scene_graph import ExitState

    project, scripts = _project(tmp_path)
    # Arena cite une scène résolue ET un nom inexistant : la sortie doit signaler
    # le problème (cassée prime sur résolue).
    (scripts / "arena.lua").write_text(
        'scene:switch("Victory")\nscene:switch("Nope")', encoding="utf-8")
    project.scenes[1].script = "assets/scripts/scenes/arena.lua"

    assert _diag(project)["Arena"].exit is ExitState.BROKEN
