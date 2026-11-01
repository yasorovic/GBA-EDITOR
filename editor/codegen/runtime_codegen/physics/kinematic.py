"""Transport des corps poses sur un KinematicBody place dans la scene."""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
    collision_shapes_collide,
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
        "        int old_x,int old_y,u8* carried,int* carry_x,int* carry_y){",
        "    if(*carried||!k->active||!a->active||kb>=k->collision.box_count||ab>=a->collision.box_count) return;",
        "    const CollisionShape* p=&k->collision.boxes[kb]; const CollisionShape* b=&a->collision.boxes[ab];",
        "    if(!p->active||!b->active) return;",
        "    int dx=k->x-old_x,dy=k->y-old_y; if(!dx&&!dy) return;",
        "    int pl=(old_x>>8)+p->x,pr=pl+p->w,pt=(old_y>>8)+p->y;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,abottom=(a->y>>8)+b->y+b->h;",
        "    if(abottom!=pt||al>=pr||ar<=pl||a->vy<0) return;",
        "    a->x+=dx; a->y+=dy; *carry_x+=dx; *carry_y+=dy; *carried=1;",
        "}",
        "",
    ]


def _block_boxes(owner, sprite) -> list[tuple[int, object]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active
            and box.response == COLLISION_RESPONSE_BLOCK]


def _body_boxes(owner, sprite) -> list[tuple[int, object]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active]


def kinematic_tick_parts(
        p, scene_actors, actor_offset: int,
) -> tuple[list[str], list[str], dict[int, tuple[str, str]]]:
    """Instantanés avant mouvement, transport après résolution, puis deltas par passager."""
    groups: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for ki, (kinematic, kinematic_sprite) in enumerate(scene_actors):
        if physics_body_mode(kinematic) != PHYSICS_BODY_KINEMATIC:
            continue
        for ti, (target, target_sprite) in enumerate(scene_actors):
            if ti == ki or physics_body_mode(target) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
                continue
            pairs = [(kb, ab) for kb, kbox in _block_boxes(kinematic, kinematic_sprite)
                     for ab, abox in _body_boxes(target, target_sprite)
                     if (tags_collide(p.settings, kbox.tag or "body", abox.tag or "body")
                         and collision_shapes_collide(kbox, abox))]
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
    )]
    for (ki, ti), pairs in groups.items():
        carried = f"_kin_carried_{ki}_{ti}"
        after.append(f"    u8 {carried}=0;")
        for kb, ab in pairs:
            after.append(
                f"    kinematic_carry(&g_actors[{ki}],&g_actors[{ti}],{kb},{ab},"
                f"_kin_old_x_{ki},_kin_old_y_{ki},&{carried},&_kin_dx_{ti},&_kin_dy_{ti});")
    deltas = {ti: (f"_kin_dx_{ti}", f"_kin_dy_{ti}")
              for ti in target_indices}
    return before, after, deltas


def kinematic_crush_pairs(p, scene_actors, actor_offset: int) -> dict[int, list[tuple[int, int, int]]]:
    """Les StaticBody qui peuvent coincer un Character transporte."""
    statics = []
    for si, (owner, sprite) in enumerate(scene_actors):
        if physics_body_mode(owner) == PHYSICS_BODY_STATIC:
            statics.extend((actor_offset + si, sb, box)
                           for sb, box in _block_boxes(owner, sprite))

    pairs: dict[int, list[tuple[int, int, int]]] = {}
    for ci, (character, sprite) in enumerate(scene_actors):
        if physics_body_mode(character) != PHYSICS_BODY_CHARACTER:
            continue
        for cb, cbox in _body_boxes(character, sprite):
            for si, sb, sbox in statics:
                if (tags_collide(p.settings, cbox.tag or "body", sbox.tag or "body")
                        and collision_shapes_collide(cbox, sbox)):
                    pairs.setdefault(actor_offset + ci, []).append((cb, si, sb))
    return pairs
