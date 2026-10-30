"""Bilan des capacités physiques réservées par scène."""
from __future__ import annotations

from dataclasses import dataclass

from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_scene_query import actors_can_collide
from codegen.runtime_codegen.physics.body import uses_character_solver
from core.models.components import CollisionBoxComponent, MAX_COLLISION_BOXES


@dataclass(frozen=True)
class PhysicsBudget:
    placed_actors: int
    pool_slots: int
    actor_slots: int
    collider_slots: int
    character_slots: int
    placed_contact_masks: int
    pool_contact_masks: int
    blocker_boxes: int

    @property
    def contact_masks(self) -> int:
        return self.placed_contact_masks + self.pool_contact_masks

    @property
    def contact_bytes(self) -> int:
        """Un masque de paires de boxes est un `u16` dans le C émis."""
        return self.contact_masks * 2


def _has_collider(owner) -> bool:
    return any(isinstance(c, CollisionBoxComponent) for c in getattr(owner, "components", []))


def _blocker_count(owner) -> int:
    return sum(1 for c in getattr(owner, "components", [])
               if isinstance(c, CollisionBoxComponent) and c.active and c.response == "block")


def scene_physics_budget(project, scene) -> PhysicsBudget:
    """Capacité maximale de physique de `scene`, pas une allocation supplémentaire.

    Le pool est partagé entre ses modèles : n'importe lequel peut remplir tous
    ses emplacements. Les masques pool→scène sont donc comptés sur le partenaire
    le plus coûteux, comme la table `_pcol` réellement émise.
    """
    layout = scene_oam_layout(project, scene)
    placed = [a for a in scene.actors if getattr(a, "active", True)]
    collidable = [a for a in placed if _has_collider(a)]
    placed_masks = sum(
        1 for i, actor in enumerate(collidable)
        for other in collidable[i + 1:]
        if actors_can_collide(project, actor, other))

    shared = [slot.prefab for slot in layout.pools if slot.shared]
    partners = max((sum(1 for actor in collidable if actors_can_collide(project, prefab, actor))
                    for prefab in shared), default=0)
    pool_masks = layout.pool_slots * partners
    character_slots = sum(1 for actor in placed if uses_character_solver(actor))
    if any(uses_character_solver(prefab) for prefab in shared):
        character_slots += layout.pool_slots

    owners = [*placed, *shared]
    return PhysicsBudget(
        placed_actors=len(placed),
        pool_slots=layout.pool_slots,
        actor_slots=layout.actors,
        collider_slots=layout.actors * MAX_COLLISION_BOXES,
        character_slots=character_slots,
        placed_contact_masks=placed_masks,
        pool_contact_masks=pool_masks,
        blocker_boxes=sum(_blocker_count(owner) for owner in owners),
    )


def physics_budget_line(project, scene) -> str:
    """Une ligne compacte pour le journal du build."""
    b = scene_physics_budget(project, scene)
    return (f"[physics] {scene.name}: actors {b.actor_slots} ({b.placed_actors} placed + {b.pool_slots} pool), "
            f"colliders {b.collider_slots} max, Characters {b.character_slots}, "
            f"contacts {b.contact_masks} masks ({b.contact_bytes} B), blocks {b.blocker_boxes}")
