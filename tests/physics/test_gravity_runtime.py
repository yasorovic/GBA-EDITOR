"""`scene.gravity` : la gravité et le côté d'appui deviennent des variables du runtime quand un script les écrit.

Sans écriture, le C émis reste celui d'avant (gravité et côté d'appui cuits par scène). Le comportement C du setter
(axe dominant, réveil des Rigid endormis) est vérifié par la sonde native `tests/native/actor_box_probe.c`.
"""
from __future__ import annotations

from types import SimpleNamespace

from core.models.components import CollisionShapeComponent, PhysicsBodyComponent
from core.models.scene import Actor, Scene


def _actor(name: str, mode: str, response: str = "block", one_way: str = "off", gravity_scale: float = 1.0) -> Actor:
    return Actor(name=name, components=[
        CollisionShapeComponent(id="body", solid=True, response=response, one_way=one_way),
        PhysicsBodyComponent(mode=mode, gravity_scale=gravity_scale),
    ])


def _project(directory, script: str | None):
    directory.mkdir(exist_ok=True)
    if script is not None:
        (directory / "Hero.lua").write_text(script, encoding="utf-8")
    return SimpleNamespace(user_library_dir=directory, scenes=[], prefabs=[], settings=SimpleNamespace(
        collision_disabled_pairs=[], collision_tags=[], physics_gravity_x=0.0, physics_gravity_y=0.0))


def test_seule_une_ecriture_de_scene_gravity_rend_la_gravite_dynamique(tmp_path):
    from codegen.runtime_codegen.physics.body import project_sets_gravity
    assert not project_sets_gravity(_project(tmp_path / "none", None))
    assert not project_sets_gravity(_project(tmp_path / "read", "local g = scene.gravity\n"))    # une lecture ne suffit pas
    assert project_sets_gravity(_project(tmp_path / "write", "function on_update()\n  scene.gravity = vec2(0, 64)\nend\n"))


def test_un_projet_sans_dossier_de_scripts_reste_statique():
    from codegen.runtime_codegen.physics.body import project_sets_gravity
    assert not project_sets_gravity(SimpleNamespace())


def test_le_rigid_lit_la_gravite_du_runtime_selon_son_gravity_scale():
    from codegen.runtime_codegen.model_desc import body_desc
    from codegen.runtime_codegen.physics.motion import physics_motion_lines
    scene = Scene(name="S")
    settings = SimpleNamespace(physics_gravity_x=0.25, physics_gravity_y=0.5)
    plain, flipped = _actor("Crate", "RigidBody"), _actor("Balloon", "RigidBody", gravity_scale=-2.0)
    actors = [(plain, None), (flipped, None)]

    # La gravité de la scène est passée au pas ; la part de chaque corps vient de son descripteur.
    dynamic = "\n".join(physics_motion_lines(scene, settings, actors, 0, [], dynamic_gravity=True))
    assert "body_motion_step(_a,&g_model_desc_S[_a->model],g_gravity_x,g_gravity_y," in dynamic
    assert body_desc(plain)[2] == 256 and body_desc(flipped)[2] == -512

    static = "\n".join(physics_motion_lines(scene, settings, actors, 0, []))
    assert "g_gravity_x" not in static
    assert "body_motion_step(_a,&g_model_desc_S[_a->model],64,128," in static


def test_le_transport_kinematic_lit_le_cote_d_appui_du_runtime(tmp_path):
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
    from core.project import Project

    def apres(dossier, script):
        platform, rider = _actor("Lift", "KinematicBody"), _actor("Rider", "CharacterBody")
        scene = Scene(name="S", actors=[platform, rider], physics_enabled=True)
        project = Project(dossier)
        project.scenes.items = [scene]
        if script is not None:
            project.user_library_dir.mkdir(parents=True, exist_ok=True)
            (project.user_library_dir / "Hero.lua").write_text(script, encoding="utf-8")
        _before, after, _crush = kinematic_tick_parts(project, [(platform, None), (rider, None)], 0, scene)
        return "\n".join(after)

    # Le dernier argument est le côté d'appui : 0 = lu dans `g_support_normal`, sinon cuit (1 : le bas).
    assert "_kin_pair,_kin_d,0);" in apres(tmp_path / "write", "scene.gravity = vec2(0, 1)\n")
    assert "_kin_pair,_kin_d,1);" in apres(tmp_path / "none", None)


def test_le_sol_lit_le_cote_d_appui_du_runtime_et_garde_les_faces_a_sens_unique_fixes(tmp_path):
    from codegen.runtime_codegen.physics.floor import floor_tick_lines
    from core.project import Project

    def emet(dossier, script):
        hero = _actor("Hero", "CharacterBody")
        ground = _actor("Ground", "StaticBody")
        shelf = _actor("Shelf", "StaticBody", one_way="up")
        scene = Scene(name="S", actors=[hero, ground, shelf], physics_enabled=True)
        project = Project(dossier)
        project.scenes.items = [scene]
        if script is not None:
            project.user_library_dir.mkdir(parents=True, exist_ok=True)
            (project.user_library_dir / "Hero.lua").write_text(script, encoding="utf-8")
        return "\n".join(floor_tick_lines(project, [(a, None) for a in scene.actors], 0, scene))

    # Le Hero (type 1) repose sur le sol (type 2) et sur l'étagère à sens unique (type 3).
    code = emet(tmp_path / "write", "scene.gravity = vec2(0, 1)\n")
    assert "_fl_pair[2]" in code and "={{0,0,0,0},{0,0,1,1}};" in code     # l'étagère : garde « haut », sens unique
    assert "_fl_pair,0); }" in code                                   # côté d'appui lu dans g_support_normal

    sans = emet(tmp_path / "none", None)
    assert "={{0,0,0,0},{0,0,0,1}};" in sans                                # côté cuit : pas de garde
    assert "_fl_pair,1); }" in sans


def test_un_script_ecrit_et_lit_scene_gravity_en_q8():
    from scripting.codegen import CodegenContext, generate
    from scripting.parser import parse
    src = ("function on_update()\n"
           "  local g = scene.gravity\n"
           "  scene.gravity = vec2(g.x, 0 - 64)\n"
           "end\n")
    ctx = CodegenContext(actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[], music_names=[],
                         global_names=set(), const_names=set(), all_actor_syms=[], owner_kind="scene")
    code, _, _ = generate(parse(src), ctx)
    assert "scene_get_gravity()" in code
    assert "scene_set_gravity(" in code
