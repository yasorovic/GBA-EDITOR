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


def test_scene_graph_leads_a_calculated_target_to_its_own_computed_node(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    source = scripts / "title.lua"
    source.write_text('scene:switch(levels[i])\nscene:switch(levels[i])', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"
    project.scenes[1].script = "assets/scripts/scenes/title.lua"

    graph = scene_graph(project)
    # Jamais une fausse scène : une arête « calculée » qui porte l'expression, un
    # nœud par scène (deux scènes, même texte, deux sorties distinctes).
    assert {(e.source, e.target, e.computed, e.count) for e in graph.edges} == {
        ("Title", "levels[i]", True, 2), ("Arena", "levels[i]", True, 2)}
    assert {e.target_key for e in graph.edges} == {"Title::levels[i]", "Arena::levels[i]"}
    ref = graph.edges[0].refs[0]
    assert source.read_text(encoding="utf-8")[ref.start:ref.stop + 1] == "levels[i]"
    assert {n.name: n.has_dynamic_exit for n in graph.nodes} == {
        "Title": True, "Arena": True, "Victory": False}


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


_DOOR = ('exports = {\n'
         '    next_scene = { type = "scene_ref", default = "Victory", label = "Next Scene" },\n'
         '}\n'
         'function on_update()\n'
         '    scene:switch(next_scene)\n'
         'end\n')


def _door(name, values=None):
    from core.models.scene import Actor
    from core.models.components import ScriptComponent
    actor = Actor(name=name)
    actor.components = [ScriptComponent(script="assets/scripts/door.lua", exports_values=dict(values or {}))]
    return actor


def test_scene_graph_draws_one_edge_per_door_from_its_scene_ref_export(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (project.root / "assets" / "scripts" / "door.lua").write_text(_DOOR, encoding="utf-8")
    # Deux portes réglées sur Arena, une laissée au `default` du script (Victory).
    project.scenes[0].actors = [_door("DoorA", {"next_scene": "Arena"}), _door("DoorB", {"next_scene": "Arena"}),
                                _door("DoorC")]

    graph = scene_graph(project)

    edges = {(e.source, e.target): e for e in graph.edges}
    assert set(edges) == {("Title", "Arena"), ("Title", "Victory")}
    assert [(link.owner, link.export) for link in edges["Title", "Arena"].links] == [
        ("DoorA", "next_scene"), ("DoorB", "next_scene")]
    assert edges["Title", "Arena"].refs == () and edges["Title", "Arena"].count == 2
    assert edges["Title", "Victory"].calls()[0].line == 5
    # La cible est connue : ce n'est pas une sortie calculée.
    assert not any(node.has_dynamic_exit for node in graph.nodes)


def test_scene_graph_keeps_a_reassigned_or_empty_export_as_a_calculated_exit(tmp_path):
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (project.root / "assets" / "scripts" / "door.lua").write_text(
        _DOOR.replace("    scene:switch", "    next_scene = \"Arena\"\n    scene:switch"), encoding="utf-8")
    project.scenes[0].actors = [_door("Door")]
    empty = project.root / "assets" / "scripts" / "empty.lua"
    empty.write_text(_DOOR.replace('default = "Victory"', 'default = ""'), encoding="utf-8")
    project.scenes[1].actors = [_door("Door")]
    project.scenes[1].actors[0].components[0].script = "assets/scripts/empty.lua"

    graph = scene_graph(project)

    # Réassigné : une expression comme une autre, à remplacer dans le script. Vide : l'export garde la main, le
    # rebranchement réglera l'instance.
    edges = {e.source: e for e in graph.edges}
    assert {(e.source, e.target, e.computed) for e in graph.edges} == {
        ("Title", "next_scene", True), ("Arena", "next_scene", True)}
    assert len(edges["Title"].refs) == 1 and edges["Title"].links == ()
    assert edges["Arena"].refs == () and [link.owner for link in edges["Arena"].links] == ["Door"]
    assert {n.name: n.has_dynamic_exit for n in graph.nodes} == {
        "Title": True, "Arena": True, "Victory": False}


def test_a_computed_edge_is_neither_a_broken_nor_a_resolved_exit(tmp_path):
    from scripting.scene_graph import ExitState

    project, scripts = _project(tmp_path)
    (scripts / "arena.lua").write_text('scene:switch(wherever)', encoding="utf-8")
    project.scenes[1].script = "assets/scripts/scenes/arena.lua"

    diag = _diag(project)
    assert diag["Arena"].exit is ExitState.DYNAMIC


def test_an_area_door_gives_its_edge_like_an_actor(tmp_path):
    """Une Area porte ses valeurs d'export au build comme un acteur posé : le graphe les lit pareil. Un acteur et une
    Area du même nom restent deux sorties distinctes."""
    from core.models.components import ScriptComponent
    from core.models.scene import Area
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (project.root / "assets" / "scripts" / "door.lua").write_text(_DOOR, encoding="utf-8")
    area = Area(name="Door")
    area.components.append(ScriptComponent(script="assets/scripts/door.lua", exports_values={"next_scene": "Arena"}))
    project.scenes[0].areas = [area]
    project.scenes[0].actors = [_door("Door")]

    edges = {(e.source, e.target): e for e in scene_graph(project).edges}
    assert [(l.owner, l.owner_kind) for l in edges["Title", "Arena"].links] == [("Door", "area")]
    assert [(l.owner, l.owner_kind) for l in edges["Title", "Victory"].links] == [("Door", "actor")]


def test_a_prefab_script_counts_only_where_the_prefab_can_be_born(tmp_path):
    """Le graphe lit les scripts que le build compile pour la scène : celui d'un prefab n'y compte que si le prefab y a
    un modèle. Ici Title le spawne par son nom, Arena le pose, Victory ne l'a pas : ni arête ni nœud calculé là."""
    from core.models.components import ScriptComponent
    from core.models.scene import Actor, Prefab
    from scripting.scene_graph import scene_graph

    project, scripts = _project(tmp_path)
    (project.root / "assets" / "scripts" / "warp.lua").write_text(
        'scene:switch("Victory")\nscene:switch(levels[i])\n', encoding="utf-8")
    warp = Prefab(name="Warp", actor=Actor(name="Warp"))
    warp.actor.components = [ScriptComponent(script="assets/scripts/warp.lua")]
    project.prefabs.append(warp)
    (scripts / "title.lua").write_text('actor:spawn("Warp", vec2(0, 0))', encoding="utf-8")
    project.scenes[0].script = "assets/scripts/scenes/title.lua"
    placed = Actor(name="Warp", prefab_name="Warp")
    project.scenes[1].actors = [placed]

    graph = scene_graph(project)

    assert {(e.source, e.target, e.computed) for e in graph.edges} == {
        ("Title", "Victory", False), ("Title", "levels[i]", True),
        ("Arena", "Victory", False), ("Arena", "levels[i]", True)}
    assert {n.name: n.has_dynamic_exit for n in graph.nodes} == {
        "Title": True, "Arena": True, "Victory": False}
