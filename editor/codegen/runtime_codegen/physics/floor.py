"""Contact au sol final d'un CharacterBody sur un StaticBody ou KinematicBody pose."""
from __future__ import annotations

from core.models.components import (
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_STATIC,
    collision_shapes_collide,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries,
    physics_body_mode,
    physics_collider_entries,
)


def project_has_floors(p) -> bool:
    """Le projet peut produire un contact au sol entre acteurs poses."""
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    modes = {physics_body_mode(owner) for owner in owners}
    return PHYSICS_BODY_CHARACTER in modes and bool(
        modes & {PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC})


def floor_helper_lines() -> list[str]:
    """Teste un contact final exact, sans refaire la resolution physique."""
    return [
        "static void __attribute__((unused)) actor_floor_test(Actor* a,u8 ab,Actor* s,u8 sb){",
        "    if(!g_actor_floor||g_actor_floor[a->inst]||!a->active||!s->active) return;",
        "    if(ab>=a->collision.box_count||sb>=s->collision.box_count||a->vy<0) return;",
        "    const CollisionShape* b=&a->collision.boxes[ab]; const CollisionShape* p=&s->collision.boxes[sb];",
        "    if(!b->active||!p->active) return;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,bottom=(a->y>>8)+b->y+b->h;",
        "    int pl=(s->x>>8)+p->x,pr=pl+p->w,top=(s->y>>8)+p->y;",
        "    if(bottom==top&&al<pr&&ar>pl) g_actor_floor[a->inst]=(u16)(s->inst+1);",
        "}",
        "",
    ]


def floor_tick_lines(p, scene_actors, actor_offset: int) -> list[str]:
    """Actualise le contact au sol apres toutes les corrections de position de la frame."""
    floors = []
    for si, (owner, sprite) in enumerate(scene_actors):
        if physics_body_mode(owner) not in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC):
            continue
        for sb, box in physics_blocker_entries(owner, sprite):
            floors.append((actor_offset + si, sb, box))

    lines: list[str] = []
    for ci, (owner, sprite) in enumerate(scene_actors):
        if physics_body_mode(owner) != PHYSICS_BODY_CHARACTER:
            continue
        idx = actor_offset + ci
        lines.append(f"    g_actor_floor[{idx}]=0;")
        pairs = [(cb, si, sb) for cb, box in physics_collider_entries(owner, sprite)
                 for si, sb, floor in floors
                 if si != idx and tags_collide(p.settings, box.tag or "body", floor.tag or "body")
                 and collision_shapes_collide(box, floor)]
        lines.extend(
            f"    actor_floor_test(&g_actors[{idx}],{cb},&g_actors[{si}],{sb});"
            for cb, si, sb in pairs
        )
    if lines:
        lines.insert(0, "    /* Contact au sol final des CharacterBody sur StaticBody et KinematicBody poses */")
    return lines
