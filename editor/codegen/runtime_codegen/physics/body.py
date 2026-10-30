"""Requêtes sur les corps physiques, sans état runtime supplémentaire."""
from __future__ import annotations

from core.models.components import (
    PHYSICS_BODY_CHARACTER, CollisionBoxComponent, PhysicsBodyComponent,
)


def has_map_collider(owner) -> bool:
    """Une boîte participant à la carte de collision, sous son nom historique `solid`."""
    return any(isinstance(c, CollisionBoxComponent) and c.solid
               for c in getattr(owner, "components", []))


def physics_body_mode(owner) -> str | None:
    """Mode physique effectif, avec repli compatible pour les scènes héritées."""
    body = next((c for c in getattr(owner, "components", [])
                 if isinstance(c, PhysicsBodyComponent) and c.active), None)
    if body is not None:
        return body.mode
    if has_map_collider(owner):
        return PHYSICS_BODY_CHARACTER
    return None


def is_character_body(owner) -> bool:
    return physics_body_mode(owner) == PHYSICS_BODY_CHARACTER


def uses_character_solver(owner) -> bool:
    """Le seul prédicat qui autorise la résolution Character contre la carte."""
    return is_character_body(owner) and has_map_collider(owner)
