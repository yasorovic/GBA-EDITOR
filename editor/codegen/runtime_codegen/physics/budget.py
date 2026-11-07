"""Bilan des capacités physiques réservées par scène."""
from __future__ import annotations

from dataclasses import dataclass

from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.physics.contacts import CONTACT_CAPACITY
from codegen.runtime_codegen.physics.body import uses_character_solver
from core.models.components import CollisionShapeComponent, MAX_COLLISION_SHAPES


@dataclass(frozen=True)
class PhysicsBudget:
    placed_actors: int
    pool_slots: int
    actor_slots: int
    collider_slots: int
    character_slots: int
    contact_pairs: int
    blocker_boxes: int

    @property
    def contact_slots(self) -> int:
        """Les contacts suivis à la fois : la liste du C émis, bornée par `CONTACT_CAPACITY`."""
        return min(CONTACT_CAPACITY, self.contact_pairs)

    @property
    def contact_bytes(self) -> int:
        """Deux listes (l'image et la précédente) de `Contact`, 10 octets chacun, dans le C émis."""
        return self.contact_slots * 20


def _has_collider(owner) -> bool:
    return any(isinstance(c, CollisionShapeComponent) for c in getattr(owner, "components", []))


def _blocker_count(owner) -> int:
    return sum(1 for c in getattr(owner, "components", [])
               if isinstance(c, CollisionShapeComponent) and c.active and c.response == "block")


def scene_physics_budget(project, scene) -> PhysicsBudget:
    """Capacité maximale de physique de `scene`, pas une allocation supplémentaire.

    Le pool est partagé entre ses modèles : n'importe lequel peut remplir tous
    ses emplacements. Les paires de contacts possibles sont donc comptées sur tous
    les emplacements du pool dès qu'un modèle a une boîte (pool contre pool compris) :
    un majorant des paires que la passe de contacts peut tester.
    """
    layout = scene_oam_layout(project, scene)
    placed = [a for a in scene.actors if getattr(a, "active", True)]
    collidable = [a for a in placed if _has_collider(a)]
    shared = [slot.prefab for slot in layout.pools if slot.shared]
    bodies = len(collidable) + (layout.pool_slots if any(_has_collider(prefab) for prefab in shared) else 0)
    character_slots = sum(1 for actor in placed if uses_character_solver(actor))
    if any(uses_character_solver(prefab) for prefab in shared):
        character_slots += layout.pool_slots

    owners = [*placed, *shared]
    return PhysicsBudget(
        placed_actors=len(placed),
        pool_slots=layout.pool_slots,
        actor_slots=layout.actors,
        collider_slots=layout.actors * MAX_COLLISION_SHAPES,
        character_slots=character_slots,
        contact_pairs=bodies * (bodies - 1) // 2,
        blocker_boxes=sum(_blocker_count(owner) for owner in owners),
    )


def physics_budget_line(project, scene) -> str:
    """Une ligne compacte pour le journal du build."""
    b = scene_physics_budget(project, scene)
    return (f"[physics] {scene.name}: actors {b.actor_slots} ({b.placed_actors} placed + {b.pool_slots} pool), "
            f"colliders {b.collider_slots} max, Characters {b.character_slots}, "
            f"contacts {b.contact_slots} tracked ({b.contact_bytes} B), blocks {b.blocker_boxes}; "
            f"debug work: Character≤{b.character_slots}, contact≤{b.contact_pairs}")
