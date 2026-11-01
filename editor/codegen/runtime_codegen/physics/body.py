"""Requêtes sur les corps physiques, sans état runtime supplémentaire."""
from __future__ import annotations

from core.models.collision_tiles import (
    ONEWAY_DOWN, ONEWAY_LEFT, ONEWAY_NONE, ONEWAY_RIGHT, ONEWAY_UP,
)
from core.models.components import (
    COLLISION_RESPONSE_BLOCK, ONE_WAY_GRAVITY, ONE_WAY_OFF,
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


_ONE_WAY_FIXED = {"up": ONEWAY_UP, "down": ONEWAY_DOWN, "left": ONEWAY_LEFT, "right": ONEWAY_RIGHT}


def gravity_normal(scene, project_settings) -> int:
    """La normale d'une surface qui PORTE sous la gravité de la scène : l'opposé de son axe dominant
    (`ONEWAY_*`). 0 sans gravité."""
    gx, gy = scene.effective_physics_gravity(project_settings)
    if gx == 0 and gy == 0:
        return ONEWAY_NONE
    if abs(gx) > abs(gy):
        return ONEWAY_LEFT if gx > 0 else ONEWAY_RIGHT
    return ONEWAY_DOWN if gy < 0 else ONEWAY_UP


def support_normal(scene, project_settings) -> int:
    """Le côté du contact qui produit `grounded` et `floor`, pour toute la scène.

    La gravité du moteur ne touche que les Rigid : un Character écrit sa propre vélocité, donc ses projets laissent
    la gravité de la scène à zéro. Sans gravité déclarée, l'appui reste donc le bas (le comportement d'avant)."""
    return gravity_normal(scene, project_settings) or ONEWAY_UP


def shape_one_way_dir(box, scene, project_settings) -> int:
    """Le sens de la face d'une forme (`ONEWAY_*` : 1 haut, 2 bas, 3 gauche, 4 droite), 0 sans sens unique.

    `gravity` est la normale d'appui de LA SCÈNE (`support_normal`) : connue au build, donc cuite, et la même forme
    change de face d'une scène à l'autre si leur gravité diffère. Sans gravité, le haut."""
    mode = getattr(box, "one_way", ONE_WAY_OFF)
    if mode == ONE_WAY_OFF:
        return ONEWAY_NONE
    if mode != ONE_WAY_GRAVITY:
        return _ONE_WAY_FIXED[mode]
    return support_normal(scene, project_settings)


def project_has_one_way(p) -> bool:
    """Une forme à sens unique quelque part : les aides C n'en sont émises que dans ce cas."""
    owners = [a for sc in getattr(p, "scenes", []) or [] for a in sc.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any(isinstance(c, CollisionShapeComponent) and c.active and c.one_way != ONE_WAY_OFF
               for o in owners for c in getattr(o, "components", []))


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
