"""Contrat d'intégration des modes physiques dans le C émis."""

from core.models.components import CollisionBoxComponent, PhysicsBodyComponent
from core.models.scene import Actor


def _actor(name: str, solid: bool = True, mode: str | None = None) -> Actor:
    actor = Actor(name=name, components=[CollisionBoxComponent(solid=solid)])
    if mode is not None:
        actor.components.append(PhysicsBodyComponent(mode=mode))
    return actor


def test_les_scenes_heritent_du_character_et_les_modes_explicites_l_emportent():
    from codegen.runtime_codegen.physics.body import (
        is_character_body, physics_body_needs_motion, uses_character_solver,
    )

    assert is_character_body(_actor("Legacy"))
    assert is_character_body(_actor("Hero", mode="CharacterBody"))
    assert not is_character_body(_actor("Wall", mode="StaticBody"))
    assert not physics_body_needs_motion(_actor("Wall", mode="StaticBody"))
    assert not is_character_body(_actor("Sensor", solid=False))
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
        CollisionBoxComponent(response="trigger")
    with pytest.raises(ValueError, match="collision response"):
        components_from_list([{"component_type": "collision_box", "response": "trigger"}])
    with pytest.raises(ValueError, match="mass"):
        PhysicsBodyComponent(mode="RigidBody", mass=0)
    with pytest.raises(ValueError, match="gravity scale"):
        PhysicsBodyComponent(mode="RigidBody", gravity_scale=9)


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
        CollisionBoxComponent(id="hurt", solid=True),
        CollisionBoxComponent(id="feet", solid=True),
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
        CollisionBoxComponent(id="body"),
        PhysicsBodyComponent(collider_id="missing"),
    ])
    errors = []
    _check_physics_body(SimpleNamespace(error=lambda owner, message: errors.append(message)),
                        actor, actor.components[-1])

    assert len(errors) == 1
    assert "missing" in errors[0] and "unique CollisionBox" in errors[0]


def test_kinematic_et_rigid_emettent_un_mouvement_automatique_et_la_gravite():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.motion import physics_motion_lines
    from core.models.scene import Scene

    character = _actor("Hero", mode="CharacterBody")
    kinematic = _actor("Lift", mode="KinematicBody")
    rigid = _actor("Crate", mode="RigidBody")
    scene = Scene(name="Platform")
    settings = SimpleNamespace(physics_gravity_x=0.25, physics_gravity_y=0.5)
    lines = "\n".join(physics_motion_lines(
        scene, settings, [(character, None), (kinematic, None), (rigid, None)], 3, []))

    assert "g_actors[3]" not in lines       # Character reste piloté explicitement par son script.
    assert "actor_apply_velocity(&g_actors[4]);" in lines
    assert "(&g_actors[5])->vx+=64; (&g_actors[5])->vy+=128;" in lines
    assert "actor_apply_velocity(&g_actors[5]);" in lines


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

    assert "physics_sleep<20" in motion
    assert "->vy+=128" in motion
    assert "->vy*192" in motion
    assert "->vy>768" in motion
    assert "physics_sleep++" in sleep
    assert "->vy<= 13" in sleep


def test_un_rigid_module_sa_gravite_et_peut_refuser_le_sommeil():
    from types import SimpleNamespace
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

    assert "->vx+=-32;" in motion and "->vy+=-64;" in motion
    assert "physics_sleep" not in motion
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
    assert deltas == {5: ("_kin_dx_5", "_kin_dy_5", "_kin_ground_5")}
