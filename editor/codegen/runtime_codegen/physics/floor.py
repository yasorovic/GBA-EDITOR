"""Contact au sol final d'un CharacterBody ou d'un RigidBody sur les corps poses sous lui."""
from __future__ import annotations

from core.models.collision_tiles import ONEWAY_NONE, ONEWAY_UP
from core.models.components import (
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
    collision_shapes_collide,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries,
    physics_body_mode,
    physics_collider_entries,
    shape_one_way_dir,
    support_normal,
)


def project_has_floors(p) -> bool:
    """Le projet peut produire un contact au sol entre acteurs poses."""
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    modes = {physics_body_mode(owner) for owner in owners}
    if PHYSICS_BODY_RIGID in modes:
        return True
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
        "/* Le même contact pour un côté d'appui `n` quelconque : 1 bas, 2 haut, 3 droite, 4 gauche. Le corps ne doit pas",
        "   s'éloigner de son appui (vitesse de sens contraire), comme `a->vy<0` ci-dessus pour le bas. */",
        "static void __attribute__((unused)) actor_floor_test_n(Actor* a,u8 ab,Actor* s,u8 sb,u8 n){",
        "    if(!g_actor_floor||g_actor_floor[a->inst]||!a->active||!s->active) return;",
        "    if(ab>=a->collision.box_count||sb>=s->collision.box_count) return;",
        "    const CollisionShape* b=&a->collision.boxes[ab]; const CollisionShape* p=&s->collision.boxes[sb];",
        "    if(!b->active||!p->active) return;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,at=(a->y>>8)+b->y,abt=at+b->h;",
        "    int pl=(s->x>>8)+p->x,pr=pl+p->w,pt=(s->y>>8)+p->y,pb=pt+p->h;",
        "    int hit;",
        "    if(n==1) hit=a->vy>=0&&abt==pt&&al<pr&&ar>pl;",
        "    else if(n==2) hit=a->vy<=0&&at==pb&&al<pr&&ar>pl;",
        "    else if(n==3) hit=a->vx>=0&&ar==pl&&at<pb&&abt>pt;",
        "    else hit=a->vx<=0&&al==pr&&at<pb&&abt>pt;",
        "    if(hit) g_actor_floor[a->inst]=(u16)(s->inst+1);",
        "}",
        "",
    ]


def floor_tick_lines(p, scene_actors, actor_offset: int, scene=None) -> list[str]:
    """Actualise le contact au sol apres toutes les corrections de position de la frame.

    Un CharacterBody repose sur un StaticBody ou un KinematicBody. Un RigidBody repose aussi sur un Character ou un
    autre Rigid : le solveur d'impulsions le laisse exactement au contact, sans produire lui-meme de contact au sol."""
    n = support_normal(scene, p.settings) if scene is not None else ONEWAY_UP
    floors = []
    for si, (owner, sprite) in enumerate(scene_actors):
        mode = physics_body_mode(owner)
        if mode not in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            continue
        for sb, box in physics_blocker_entries(owner, sprite):
            # Une face à sens unique ne porte que par sa face d'appui : les autres ne sont pas un sol.
            if scene is not None and shape_one_way_dir(box, scene, p.settings) not in (ONEWAY_NONE, n):
                continue
            floors.append((actor_offset + si, sb, box, mode))

    lines: list[str] = []
    for ci, (owner, sprite) in enumerate(scene_actors):
        mode = physics_body_mode(owner)
        if mode not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            continue
        idx = actor_offset + ci
        lines.append(f"    g_actor_floor[{idx}]=0;")
        pairs = [(cb, si, sb) for cb, box in physics_collider_entries(owner, sprite)
                 for si, sb, floor, floor_mode in floors
                 if si != idx
                 and (mode == PHYSICS_BODY_RIGID or floor_mode in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC))
                 and tags_collide(p.settings, box.tag or "body", floor.tag or "body")
                 and collision_shapes_collide(box, floor)]
        lines.extend(
            f"    actor_floor_test(&g_actors[{idx}],{cb},&g_actors[{si}],{sb});" if n == ONEWAY_UP else
            f"    actor_floor_test_n(&g_actors[{idx}],{cb},&g_actors[{si}],{sb},{n});"
            for cb, si, sb in pairs
        )
    if lines:
        lines.insert(0, "    /* Contact au sol final des CharacterBody et RigidBody sur les corps poses */")
    return lines
