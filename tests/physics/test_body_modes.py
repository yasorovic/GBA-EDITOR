"""Contrat d'intégration des modes physiques dans le C émis."""

from types import SimpleNamespace

from core.models.components import CollisionShapeComponent, PhysicMaterialComponent, PhysicsBodyComponent
from core.models.scene import Actor


def _actor(name: str, solid: bool = True, mode: str | None = None) -> Actor:
    actor = Actor(name=name, components=[CollisionShapeComponent(solid=solid)])
    if mode is not None:
        actor.components.append(PhysicsBodyComponent(mode=mode))
    return actor


def test_les_scenes_heritent_du_character_et_les_modes_explicites_l_emportent():
    from codegen.runtime_codegen.physics.body import physics_body_mode, uses_character_solver

    assert physics_body_mode(_actor("Legacy")) == "CharacterBody"
    assert physics_body_mode(_actor("Hero", mode="CharacterBody")) == "CharacterBody"
    assert physics_body_mode(_actor("Wall", mode="StaticBody")) == "StaticBody"
    assert physics_body_mode(_actor("Sensor", solid=False)) is None
    assert uses_character_solver(_actor("Lift", mode="KinematicBody"))
    assert uses_character_solver(_actor("Crate", mode="RigidBody"))


def test_static_body_n_emet_ni_mouvement_ni_sommeil():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
    from core.models.scene import Scene

    static = _actor("Wall", mode="StaticBody")
    scene = Scene(name="Static")
    settings = SimpleNamespace(physics_gravity_x=0.0, physics_gravity_y=0.5)
    actors = [(static, None)]

    assert physics_motion_lines(scene, settings, actors, 0, []) == []
    assert physics_sleep_lines(scene, settings, actors, 0, []) == []


def test_le_tick_du_pool_n_emet_le_solveur_de_carte_que_pour_les_characters():
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.physics.body import physics_collider_mask, uses_character_solver

    legacy = _actor("Legacy")
    character = _actor("Hero", mode="CharacterBody")
    static = _actor("Wall", mode="StaticBody")
    models = [
        {"shared": True, "model_id": 1, "sym": "legacy", "prefab": legacy},
        {"shared": True, "model_id": 2, "sym": "hero", "prefab": character},
        {"shared": True, "model_id": 3, "sym": "wall", "prefab": static},
    ]
    lines = "\n".join(shared_pool_gen.tile_lines(
        models, lambda *_: False,
        lambda owner: (physics_collider_mask(owner, map_only=True)
                       if uses_character_solver(owner) else 0)))

    assert "case 1: resolve_actor_tiles(_a, 1," in lines
    assert "case 2: resolve_actor_tiles(_a, 1," in lines
    assert "case 3: resolve_actor_tiles" not in lines


def test_une_valeur_inconnue_est_refusee_au_lieu_d_etre_remplacee():
    import pytest
    from core.models.components import components_from_list

    with pytest.raises(ValueError, match="physics body mode"):
        PhysicsBodyComponent(mode="orbital")
    with pytest.raises(ValueError, match="collision response"):
        CollisionShapeComponent(response="trigger")
    with pytest.raises(ValueError, match="collision response"):
        components_from_list([{"component_type": "collision_shape", "response": "trigger"}])
    with pytest.raises(ValueError, match="mass"):
        PhysicsBodyComponent(mode="RigidBody", mass=0)
    with pytest.raises(ValueError, match="gravity scale"):
        PhysicsBodyComponent(mode="RigidBody", gravity_scale=9)
    with pytest.raises(ValueError, match="restitution"):
        PhysicMaterialComponent(restitution=1.1)
    with pytest.raises(ValueError, match="friction"):
        PhysicMaterialComponent(friction=-0.1)


def test_le_materiau_physique_est_un_composant_designe_par_la_forme():
    from core.models.components import components_from_list, components_to_list, shape_material

    owner = SimpleNamespace(components=[
        CollisionShapeComponent(id="body", material_id="rubber"),
        PhysicMaterialComponent(id="rubber", restitution=0.75, friction=0.25)])
    shape, material = components_from_list(components_to_list(owner.components))

    assert shape.material_id == "rubber"
    assert (material.restitution, material.friction) == (0.75, 0.25)
    assert shape_material(owner, shape) is owner.components[1]
    assert shape_material(owner, CollisionShapeComponent()).restitution == 0.0
    owner.components[1].active = False
    assert shape_material(owner, shape).friction == 0.0


def test_une_ancienne_boite_avec_materiau_est_scindee_a_la_lecture():
    from core.models.components import components_from_list

    material, shape = components_from_list([
        {"component_type": "collision_box", "id": "body", "restitution": 0.5, "friction": 0.25}])

    assert isinstance(shape, CollisionShapeComponent) and shape.material_id == material.id
    assert (material.restitution, material.friction) == (0.5, 0.25)
    (plain,) = components_from_list([{"component_type": "collision_box", "id": "body"}])
    assert isinstance(plain, CollisionShapeComponent) and plain.material_id == ""


def test_les_anciens_champs_layer_et_mask_sont_perdus_a_la_lecture():
    from core.models.components import components_from_list, components_to_list

    (relu,) = components_from_list([{"component_type": "collision_shape", "id": "b", "layer": 2, "mask": 4}])
    assert not hasattr(relu, "layer") and not hasattr(relu, "mask")
    assert "layer" not in components_to_list([relu])[0]


def test_les_anciens_noms_sont_relus_puis_serialises_avec_les_noms_canoniques():
    from core.models.components import components_from_list, components_to_list

    for ancien, canonique in (("static", "StaticBody"), ("character", "CharacterBody"),
                              ("kinematic", "KinematicBody"), ("rigid", "RigidBody")):
        (body,) = components_from_list([{"component_type": "physics_body", "mode": ancien}])
        assert body.mode == canonique
        assert components_to_list([body])[0]["mode"] == canonique


def test_les_proprietes_rigid_ont_des_defauts_neutres_et_sont_serialisees():
    from core.models.components import components_from_list, components_to_list

    body = PhysicsBodyComponent(mode="RigidBody", mass=2.5, gravity_scale=0.5, can_sleep=False)
    data = components_to_list([body])[0]
    (reloaded,) = components_from_list([data])

    assert PhysicsBodyComponent(mode="RigidBody").mass == 1.0
    assert PhysicsBodyComponent(mode="RigidBody").gravity_scale == 1.0
    assert PhysicsBodyComponent(mode="RigidBody").can_sleep is True
    assert (reloaded.mass, reloaded.gravity_scale, reloaded.can_sleep) == (2.5, 0.5, False)


def test_le_body_serialise_sa_relation_de_collider_et_n_utilise_qu_elle():
    from codegen.runtime_codegen.physics.body import physics_collider_mask
    from core.models.components import components_from_list, components_to_list

    actor = Actor(name="Hero", components=[
        CollisionShapeComponent(id="hurt", solid=True),
        CollisionShapeComponent(id="feet", solid=True),
        PhysicsBodyComponent(mode="CharacterBody", collider_id="feet"),
    ])
    body = actor.components[-1]
    data = components_to_list([body])[0]
    (reloaded,) = components_from_list([data])

    assert reloaded.collider_id == "feet"
    assert physics_collider_mask(actor) == 2
    assert physics_collider_mask(actor, map_only=True) == 2


def test_une_relation_de_collider_absente_est_refusee_par_la_validation():
    from types import SimpleNamespace
    from core.validator import _check_physics_body

    actor = Actor(name="Hero", components=[
        CollisionShapeComponent(id="body"),
        PhysicsBodyComponent(collider_id="missing"),
    ])
    errors = []
    _check_physics_body(SimpleNamespace(error=lambda owner, message: errors.append(message)),
                        actor, actor.components[-1])

    assert len(errors) == 1
    assert "missing" in errors[0] and "unique CollisionShape" in errors[0]


def test_kinematic_et_rigid_emettent_un_mouvement_automatique_et_la_gravite():
    from types import SimpleNamespace
    from codegen.runtime_codegen.model_desc import body_desc
    from codegen.runtime_codegen.physics.motion import physics_motion_lines
    from core.models.scene import Scene

    character = _actor("Hero", mode="CharacterBody")
    kinematic = _actor("Lift", mode="KinematicBody")
    rigid = _actor("Crate", mode="RigidBody")
    scene = Scene(name="Platform")
    settings = SimpleNamespace(physics_gravity_x=0.25, physics_gravity_y=0.5)
    lines = "\n".join(physics_motion_lines(
        scene, settings, [(character, None), (kinematic, None), (rigid, None)], 3, []))

    # Un seul pas pour tous les emplacements posés, avec la gravité de la scène en Q8 ; le mode vient du descripteur.
    assert "for(int _k=3; _k<6; _k++)" in lines
    assert "body_motion_step(_a,&g_model_desc_Platform[_a->model],64,128," in lines
    assert "POOL_EACH" not in lines                               # aucun modèle ne naît dans cette scène
    assert body_desc(character) == (1, 1, 256)                    # Character : gravité seule, son script l'applique
    assert body_desc(kinematic) == (2, 1, 256)
    assert body_desc(rigid) == (3, 1, 256)


def test_character_et_kinematic_peuvent_ignorer_la_gravite_de_scene():
    from codegen.runtime_codegen.model_desc import body_desc
    from core.models.components import components_from_list, components_to_list

    assert PhysicsBodyComponent(mode="CharacterBody").use_scene_gravity is True
    assert PhysicsBodyComponent(mode="KinematicBody").use_scene_gravity is True
    off = PhysicsBodyComponent(mode="KinematicBody", use_scene_gravity=False)
    assert components_from_list(components_to_list([off]))[0].use_scene_gravity is False

    character = _actor("Hero", mode="CharacterBody")
    character.components[-1].use_scene_gravity = False
    kinematic = _actor("Lift", mode="KinematicBody")
    kinematic.components[-1].use_scene_gravity = False
    assert body_desc(character) == (1, 1, 0)                      # aucune part de gravité
    assert body_desc(kinematic) == (2, 1, 0)                      # la vitesse s'intègre, sans gravité


def test_un_rigid_applique_damping_vitesse_maximale_et_sommeil_de_scene():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
    from core.models.scene import Scene

    rigid = _actor("Crate", mode="RigidBody")
    scene = Scene(name="Inherited")
    settings = SimpleNamespace(
        physics_gravity_x=0.0, physics_gravity_y=0.5,
        physics_linear_damping=0.25, physics_max_fall_speed=3.0,
        physics_sleep_enabled=True, physics_sleep_threshold=0.05,
        physics_sleep_frames=20, physics_solver_iterations=4,
    )
    motion = "\n".join(physics_motion_lines(scene, settings, [(rigid, None)], 2, []))
    sleep = "\n".join(physics_sleep_lines(scene, settings, [(rigid, None)], 2, []))

    # gravité (0, 128), part de vitesse gardée 192 / 256, chute max 768, sommeil après 20 images.
    assert "body_motion_step(_a,&g_model_desc_Inherited[_a->model],0,128,192,768,20);" in motion
    assert "physics_sleep++" in sleep
    # Le repos se lit sur la position : rayon = seuil (13 en Q8) x délai (20 frames), autour d'une ancre par emplacement.
    assert "_dy<= 260&&_dy>=-260" in sleep
    assert "g_rigid_rest[(&g_actors[2])->inst]" in sleep
    assert "_r[0]=(&g_actors[2])->x; _r[1]=(&g_actors[2])->y; (&g_actors[2])->physics_sleep=0;" in sleep
    assert "->vy<= 13" not in sleep


def test_un_rigid_module_sa_gravite_et_peut_refuser_le_sommeil():
    from types import SimpleNamespace
    from codegen.runtime_codegen.model_desc import body_desc
    from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
    from core.models.scene import Scene

    rigid = _actor("Balloon", mode="RigidBody")
    body = next(c for c in rigid.components if isinstance(c, PhysicsBodyComponent))
    body.gravity_scale = -0.5
    body.can_sleep = False
    scene = Scene(name="Air")
    settings = SimpleNamespace(
        physics_gravity_x=0.25, physics_gravity_y=0.5,
        physics_linear_damping=0.0, physics_max_fall_speed=8.0,
        physics_sleep_enabled=True, physics_sleep_threshold=0.05,
        physics_sleep_frames=30, physics_solver_iterations=4,
    )

    motion = "\n".join(physics_motion_lines(scene, settings, [(rigid, None)], 0, []))
    sleep = physics_sleep_lines(scene, settings, [(rigid, None)], 0, [])

    assert "body_motion_step(_a,&g_model_desc_Air[_a->model],64,128,256,2048,30);" in motion
    assert body_desc(rigid) == (3, 0, -128)                       # gravité x -0,5, ne dort pas
    assert sleep == []


def test_le_transport_kinematic_est_prepare_sans_etat_runtime():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts

    platform = _actor("Platform", mode="KinematicBody")
    platform.components[0].response = "block"
    rider = _actor("Rider", mode="CharacterBody")
    project = SimpleNamespace(settings=SimpleNamespace(
        collision_disabled_pairs=[], collision_tags=[]))

    before, after, deltas = kinematic_tick_parts(
        project, [(platform, None), (rider, None)], 4)
    code = "\n".join(before + after)

    assert "_kin_old_x_4=g_actors[4].x" in code
    assert "kinematic_carry(&g_actors[4],&g_actors[5]" in code
    assert "_kin_ground" not in code
    assert deltas == {5: ("_kin_dx_5", "_kin_dy_5")}


def test_un_character_transporte_ne_declenche_l_ecrasement_que_sur_un_static():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.kinematic import kinematic_crush_pairs

    platform = _actor("Platform", mode="KinematicBody")
    platform.components[0].response = "block"
    rider = _actor("Rider", mode="CharacterBody")
    wall = _actor("Wall", mode="StaticBody")
    wall.components[0].response = "block"
    project = SimpleNamespace(settings=SimpleNamespace(
        collision_disabled_pairs=[], collision_tags=[]))

    assert kinematic_crush_pairs(project, [(platform, None), (rider, None), (wall, None)], 4) == {
        5: [(0, 6, 0)],
    }


def test_le_tick_emet_on_crushed_pour_un_obstacle_static(tmp_path):
    from codegen.c_names import scene_actor_sym
    from codegen.runtime_codegen.gen_scene_tick import gen_scene_tick
    from core.project import Project

    project = Project.create(tmp_path / "Crush", "Crush")
    scene = project.active_scene
    platform = _actor("Platform", mode="KinematicBody")
    platform.components[0].response = "block"
    rider = _actor("Rider", mode="CharacterBody")
    wall = _actor("Wall", mode="StaticBody")
    wall.components[0].response = "block"
    scene.actors = [platform, rider, wall]
    actors = [(actor, None) for actor in scene.actors]
    symbol = scene_actor_sym(scene.name, rider.name)

    code = "\n".join(gen_scene_tick(
        project, scene, 0, [], actors, {1}, [], {}, {}, [],
        actor_defined_events={symbol: {"on_crushed"}},
    ))

    assert f"{symbol}_on_crushed(&g_actors[1],&g_actors[2])" in code


def test_le_tick_emet_on_crushed_pour_la_carte_sans_static(tmp_path):
    from codegen.c_names import scene_actor_sym
    from codegen.runtime_codegen.gen_scene_tick import gen_scene_tick
    from core.project import Project

    project = Project.create(tmp_path / "CrushMap", "CrushMap")
    scene = project.active_scene
    scene.collision_map = [[1]]
    platform = _actor("Platform", mode="KinematicBody")
    platform.components[0].response = "block"
    rider = _actor("Rider", mode="CharacterBody")
    scene.actors = [platform, rider]
    actors = [(actor, None) for actor in scene.actors]
    symbol = scene_actor_sym(scene.name, rider.name)

    code = "\n".join(gen_scene_tick(
        project, scene, 0, [], actors, {1}, [], {}, {}, [],
        actor_defined_events={symbol: {"on_crushed"}},
    ))

    assert f"{symbol}_on_crushed(&g_actors[1],0)" in code


def test_le_floor_final_relit_static_et_kinematic():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.floor import floor_tick_lines

    character = _actor("Hero", mode="CharacterBody")
    static = _actor("Floor", mode="StaticBody")
    static.components[0].response = "block"
    platform = _actor("Platform", mode="KinematicBody")
    platform.components[0].response = "block"
    project = SimpleNamespace(settings=SimpleNamespace(
        collision_disabled_pairs=[], collision_tags=[]))

    code = "\n".join(floor_tick_lines(
        project, [(character, None), (static, None), (platform, None)], 3))

    assert "g_actor_floor[3]=0" in code
    assert "actor_floor_test(&g_actors[3],0,&g_actors[4],0)" in code
    assert "actor_floor_test(&g_actors[3],0,&g_actors[5],0)" in code


def test_le_floor_final_d_un_rigid_relit_static_character_et_rigid():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.floor import floor_tick_lines

    crate = _actor("Crate", mode="RigidBody")
    static = _actor("Floor", mode="StaticBody")
    static.components[0].response = "block"
    hero = _actor("Hero", mode="CharacterBody")
    hero.components[0].response = "block"
    other = _actor("Other", mode="RigidBody")
    other.components[0].response = "block"
    project = SimpleNamespace(settings=SimpleNamespace(
        collision_disabled_pairs=[], collision_tags=[]))

    code = "\n".join(floor_tick_lines(
        project, [(crate, None), (static, None), (hero, None), (other, None)], 0))

    assert "g_actor_floor[0]=0" in code
    assert "actor_floor_test(&g_actors[0],0,&g_actors[1],0)" in code
    assert "actor_floor_test(&g_actors[0],0,&g_actors[2],0)" in code
    assert "actor_floor_test(&g_actors[0],0,&g_actors[3],0)" in code
    # Le Character ne se pose toujours pas sur un Rigid ni sur un autre Character.
    assert "actor_floor_test(&g_actors[2],0,&g_actors[0],0)" not in code
    assert "actor_floor_test(&g_actors[2],0,&g_actors[3],0)" not in code


def test_l_etat_de_floor_est_en_ewram_sans_grossir_actor(tmp_path):
    from types import SimpleNamespace
    from core.project import Project
    from codegen.runtime_codegen.gen_globals import globals_lines

    project = Project.create(tmp_path / "Floor", "Floor")
    character = _actor("Hero", mode="CharacterBody")
    static = _actor("Floor", mode="StaticBody")
    project.active_scene.actors = [character, static]
    lines = globals_lines(project, [], [], 6, 1, SimpleNamespace(
        buffered_bits={}, seq_table_defs={}, ring_depth=1))
    code = "\n".join(lines)

    assert "u16 g_actor_floor_store[6] EWRAM_BSS;" in code
    assert "u16 *g_actor_floor=g_actor_floor_store;" in code
