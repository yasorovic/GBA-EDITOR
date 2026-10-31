"""Le bilan physique reflète les capacités réservées par la scène."""
from types import SimpleNamespace

from core.models.components import CollisionBoxComponent, PhysicsBodyComponent
from core.models.scene import Actor


def _actor(name, *, mode=None, response="sensor"):
    box = CollisionBoxComponent()
    box.response = response
    components = [box]
    if mode:
        components.append(PhysicsBodyComponent(mode=mode))
    return Actor(name=name, components=components)


def test_le_bilan_compte_les_capacites_du_pool_et_les_contacts(monkeypatch):
    from codegen.runtime_codegen.physics import budget

    hero = _actor("Hero", mode="CharacterBody")
    wall = _actor("Wall", mode="StaticBody", response="block")
    bullet = _actor("Bullet", mode="CharacterBody")
    scene = SimpleNamespace(name="Level", actors=[hero, wall])
    layout = SimpleNamespace(placed=2, pool_slots=5, actors=7,
                             pools=[SimpleNamespace(prefab=bullet, shared=True)])
    project = SimpleNamespace(settings=SimpleNamespace(collision_disabled_pairs=[], collision_tags=[]))
    monkeypatch.setattr(budget, "scene_oam_layout", lambda _p, _s: layout)

    result = budget.scene_physics_budget(project, scene)

    assert result.actor_slots == 7 and result.collider_slots == 28
    assert result.character_slots == 6       # Hero + les 5 slots qu'une Bullet peut occuper
    assert result.placed_contact_masks == 1
    assert result.pool_contact_masks == 10   # 5 slots × Hero/Wall
    assert result.contact_bytes == 22 and result.blocker_boxes == 1
    assert "contacts 11 masks (22 B)" in budget.physics_budget_line(project, scene)
    assert "debug work: Character≤6, contact≤11" in budget.physics_budget_line(project, scene)
