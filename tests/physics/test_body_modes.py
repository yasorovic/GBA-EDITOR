"""Contrat d'intégration des modes physiques dans le C émis."""

from core.models.components import CollisionBoxComponent, PhysicsBodyComponent
from core.models.scene import Actor


def _actor(name: str, solid: bool = True, mode: str | None = None) -> Actor:
    actor = Actor(name=name, components=[CollisionBoxComponent(solid=solid)])
    if mode is not None:
        actor.components.append(PhysicsBodyComponent(mode=mode))
    return actor


def test_les_scenes_heritent_du_character_et_les_modes_explicites_l_emportent():
    from codegen.runtime_codegen.physics.body import is_character_body

    assert is_character_body(_actor("Legacy"))
    assert is_character_body(_actor("Hero", mode="character"))
    assert not is_character_body(_actor("Wall", mode="static"))
    assert not is_character_body(_actor("Sensor", solid=False))


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
