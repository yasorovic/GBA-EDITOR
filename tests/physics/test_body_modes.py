"""Contrat d'intégration des modes physiques dans le C émis."""

from core.models.components import CollisionBoxComponent, PhysicsBodyComponent
from core.models.scene import Actor


def _actor(name: str, solid: bool = True, mode: str | None = None) -> Actor:
    actor = Actor(name=name, components=[CollisionBoxComponent(solid=solid)])
    if mode is not None:
        actor.components.append(PhysicsBodyComponent(mode=mode))
    return actor


def test_les_scenes_heritent_du_character_et_les_modes_explicites_l_emportent():
    from codegen.runtime_codegen.physics.body import is_character_body, uses_character_solver

    assert is_character_body(_actor("Legacy"))
    assert is_character_body(_actor("Hero", mode="character"))
    assert not is_character_body(_actor("Wall", mode="static"))
    assert not is_character_body(_actor("Sensor", solid=False))
    assert uses_character_solver(_actor("Lift", mode="kinematic"))
    assert uses_character_solver(_actor("Crate", mode="rigid"))


def test_le_tick_du_pool_n_emet_le_solveur_de_carte_que_pour_les_characters():
    from codegen.runtime_codegen import shared_pool_gen
    from codegen.runtime_codegen.physics.body import uses_character_solver

    legacy = _actor("Legacy")
    character = _actor("Hero", mode="character")
    static = _actor("Wall", mode="static")
    models = [
        {"shared": True, "model_id": 1, "sym": "legacy", "prefab": legacy},
        {"shared": True, "model_id": 2, "sym": "hero", "prefab": character},
        {"shared": True, "model_id": 3, "sym": "wall", "prefab": static},
    ]
    lines = "\n".join(shared_pool_gen.tile_lines(
        models, lambda *_: False,
        uses_character_solver))

    assert "case 1: resolve_actor_tiles" in lines
    assert "case 2: resolve_actor_tiles" in lines
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


def test_kinematic_et_rigid_emettent_un_mouvement_automatique_et_la_gravite():
    from types import SimpleNamespace
    from codegen.runtime_codegen.physics.motion import physics_motion_lines
    from core.models.scene import Scene

    character = _actor("Hero", mode="character")
    kinematic = _actor("Lift", mode="kinematic")
    rigid = _actor("Crate", mode="rigid")
    scene = Scene(name="Platform")
    settings = SimpleNamespace(physics_gravity_x=0.25, physics_gravity_y=0.5)
    lines = "\n".join(physics_motion_lines(
        scene, settings, [(character, None), (kinematic, None), (rigid, None)], 3, []))

    assert "g_actors[3]" not in lines       # Character reste piloté explicitement par son script.
    assert "actor_apply_velocity(&g_actors[4]);" in lines
    assert "(&g_actors[5])->vx+=64; (&g_actors[5])->vy+=128;" in lines
    assert "actor_apply_velocity(&g_actors[5]);" in lines
