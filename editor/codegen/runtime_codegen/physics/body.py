"""Requêtes sur les corps physiques, sans état runtime supplémentaire."""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID,
    CollisionShapeComponent, PhysicsBodyComponent, owner_effective_boxes,
)


def physics_body(owner) -> PhysicsBodyComponent | None:
    """Composant physique actif, sans le repli Character des scènes héritées."""
    return next((c for c in getattr(owner, "components", [])
                 if isinstance(c, PhysicsBodyComponent) and c.active), None)


def physics_collider_entries(owner, sprite=None) -> list[tuple[int, CollisionShapeComponent]]:
    """Les formes du corps dans la table runtime.

    Une relation explicite désigne exactement une CollisionShape par son id. Une
    relation vide conserve provisoirement les boîtes `solid` historiques afin
    que les projets existants ne changent pas de comportement au chargement.
    """
    boxes = [box for box in getattr(owner, "components", [])
             if isinstance(box, CollisionShapeComponent)][:4]
    body = physics_body(owner)
    if body is not None and body.collider_id:
        return [(rank, box) for rank, box in enumerate(boxes)
                if box.id == body.collider_id][:1]
    legacy = [(rank, box) for rank, box in enumerate(boxes)
              if box.solid]
    if legacy:
        return legacy
    actual = list(enumerate(boxes))
    return actual if body is not None and len(boxes) == 1 else []


def physics_collider_mask(owner, sprite=None, *, map_only: bool = False) -> int:
    """Masque ROM des boîtes du corps, sans ajouter d'état à Actor."""
    return sum(1 << rank for rank, box in physics_collider_entries(owner, sprite)
               if not map_only or box.solid)


def physics_blocker_entries(owner, sprite=None) -> list[tuple[int, CollisionShapeComponent]]:
    """Boîtes Block offertes aux autres corps, restreintes par la relation explicite."""
    body = physics_body(owner)
    boxes = (physics_collider_entries(owner, sprite)
             if body is not None and body.collider_id
             else list(enumerate(owner_effective_boxes(owner, sprite))))
    return [(rank, box) for rank, box in boxes
            if isinstance(box, CollisionShapeComponent) and box.active
            and box.response == COLLISION_RESPONSE_BLOCK]


def has_map_collider(owner, sprite=None) -> bool:
    return bool(physics_collider_mask(owner, sprite, map_only=True))


def physics_body_mode(owner) -> str | None:
    """Mode physique effectif, avec repli compatible pour les scènes héritées."""
    body = physics_body(owner)
    if body is not None:
        return body.mode
    if has_map_collider(owner):
        return PHYSICS_BODY_CHARACTER
    return None


def is_character_body(owner) -> bool:
    return physics_body_mode(owner) == PHYSICS_BODY_CHARACTER


def uses_body_collider(owner, sprite=None) -> bool:
    """Un corps mobile possédant au moins une forme de résolution."""
    return physics_body_mode(owner) in (
        PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID,
    ) and bool(physics_collider_mask(owner, sprite))


def uses_character_solver(owner, sprite=None) -> bool:
    """Les corps mobiles qui utilisent la résolution actuelle contre la carte."""
    return physics_body_mode(owner) in (
        PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID,
    ) and has_map_collider(owner, sprite)


def physics_body_needs_motion(owner) -> bool:
    """Kinematic et Rigid déplacent leur vélocité sans appel Lua explicite."""
    return physics_body_mode(owner) in (PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID)
