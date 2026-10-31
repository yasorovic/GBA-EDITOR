"""Transport des corps poses sur un KinematicBody place dans la scene."""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import physics_body_mode, physics_collider_entries


def project_has_kinematic(p) -> bool:
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any(physics_body_mode(owner) == PHYSICS_BODY_KINEMATIC for owner in owners)


def kinematic_helper_lines() -> list[str]:
    """Aide C : applique une seule fois le déplacement réel de la plateforme au passager."""
    return [
        "static void __attribute__((unused)) kinematic_carry(Actor* k,Actor* a,u8 kb,u8 ab,",
        "        int old_x,int old_y,u8* carried,int* carry_x,int* carry_y,u8* ground_mask){",
        "    if(*carried||!k->active||!a->active||kb>=k->collision.box_count||ab>=a->collision.box_count) return;",
        "    const CollisionBox* p=&k->collision.boxes[kb]; const CollisionBox* b=&a->collision.boxes[ab];",
        "    if(!p->active||!b->active) return;",
        "    int dx=k->x-old_x,dy=k->y-old_y; if(!dx&&!dy) return;",
        "    int pl=(old_x>>8)+p->x,pr=pl+p->w,pt=(old_y>>8)+p->y;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,abottom=(a->y>>8)+b->y+b->h;",
        "    if(abottom!=pt||al>=pr||ar<=pl||a->vy<0) return;",
        "    a->x+=dx; a->y+=dy; *carry_x+=dx; *carry_y+=dy; *ground_mask|=(u8)(1u<<ab); *carried=1;",
        "    a->collision.grounded=1; a->collision.boxes[ab].grounded=1;",
        "}",
        "",
    ]


def _block_boxes(owner, sprite) -> list[tuple[int, str]]:
    return [(rank, box.tag or "body") for rank, box in physics_collider_entries(owner, sprite)
            if box.active
            and box.response == COLLISION_RESPONSE_BLOCK]


def _body_boxes(owner, sprite) -> list[tuple[int, str]]:
    return [(rank, box.tag or "body") for rank, box in physics_collider_entries(owner, sprite)
            if box.active]


def kinematic_tick_parts(
        p, scene_actors, actor_offset: int,
) -> tuple[list[str], list[str], dict[int, tuple[str, str, str]]]:
    """Instantanés avant mouvement, transport après résolution, puis deltas par passager."""
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for ki, (kinematic, kinematic_sprite) in enumerate(scene_actors):
        if physics_body_mode(kinematic) != PHYSICS_BODY_KINEMATIC:
            continue
        for ti, (target, target_sprite) in enumerate(scene_actors):
            if ti == ki or physics_body_mode(target) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
                continue
            pairs = [(kb, ab) for kb, ktag in _block_boxes(kinematic, kinematic_sprite)
                     for ab, atag in _body_boxes(target, target_sprite)
                     if tags_collide(p.settings, ktag, atag)]
            if pairs:
                groups[(actor_offset + ki, actor_offset + ti)] = pairs
    if not groups:
        return [], [], {}

    kinematic_indices = sorted({ki for ki, _ in groups})
    target_indices = sorted({ti for _, ti in groups})
    before = [line for ki in kinematic_indices for line in (
        f"    int _kin_old_x_{ki}=g_actors[{ki}].x;",
        f"    int _kin_old_y_{ki}=g_actors[{ki}].y;",
    )]
    after = [line for ti in target_indices for line in (
        f"    int _kin_dx_{ti}=0,_kin_dy_{ti}=0;",
        f"    u8 _kin_ground_{ti}=0;",
    )]
    for (ki, ti), pairs in groups.items():
        carried = f"_kin_carried_{ki}_{ti}"
        after.append(f"    u8 {carried}=0;")
        for kb, ab in pairs:
            after.append(
                f"    kinematic_carry(&g_actors[{ki}],&g_actors[{ti}],{kb},{ab},"
                f"_kin_old_x_{ki},_kin_old_y_{ki},&{carried},&_kin_dx_{ti},&_kin_dy_{ti},"
                f"&_kin_ground_{ti});")
    deltas = {ti: (f"_kin_dx_{ti}", f"_kin_dy_{ti}", f"_kin_ground_{ti}")
              for ti in target_indices}
    return before, after, deltas
