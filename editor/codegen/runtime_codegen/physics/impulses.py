"""Solveur d'impulsions minimal pour les corps Rigid poses dans une scene.

Cette premiere tranche ne gere que la normale du contact, avec une masse identique pour tous les
Rigid, sans restitution ni friction. Un Static a une masse inverse nulle. Les paires sont connues au
build, filtrees par les tags et parcourues plusieurs fois pour stabiliser les petites piles.
"""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
    CollisionBoxComponent,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.interact_gen import owner_boxes
from codegen.runtime_codegen.physics.body import physics_body_mode


IMPULSE_ITERATIONS = 4


def impulse_helper_lines() -> list[str]:
    """Aide C du solveur : correction de position puis impulsion normale."""
    return [
        "typedef struct { u16 a,b; u8 box_a,box_b,rigid; } RigidPair;",
        "static void __attribute__((unused)) rigid_pair_resolve(const RigidPair* p){",
        "    Actor* a=&g_actors[p->a]; Actor* b=&g_actors[p->b];",
        "    if(!a->active||!b->active||p->box_a>=a->collision.box_count||p->box_b>=b->collision.box_count) return;",
        "    const CollisionBox* ca=&a->collision.boxes[p->box_a];",
        "    const CollisionBox* cb=&b->collision.boxes[p->box_b];",
        "    if(!ca->active||!cb->active) return;",
        "    int al=(a->x>>8)+ca->x, at=(a->y>>8)+ca->y, ar=al+ca->w, ab=at+ca->h;",
        "    int bl=(b->x>>8)+cb->x, bt=(b->y>>8)+cb->y, br=bl+cb->w, bb=bt+cb->h;",
        "    if(al>=br||ar<=bl||at>=bb||ab<=bt) return;",
        "    int left=ar-bl, right=br-al, up=ab-bt, down=bb-at;",
        "    int px=left<right?-left:right, py=up<down?-up:down;",
        "    int apx=px<0?-px:px, apy=py<0?-py:py;",
        "    int axis_x=apx<=apy, push=axis_x?px:py, correction=push<<8;",
        "    int both=(p->rigid&3)==3;",
        "    if(both){ int half=correction/2; if(axis_x){ a->x+=half; b->x-=correction-half; }",
        "              else { a->y+=half; b->y-=correction-half; } }",
        "    else if(p->rigid&1){ if(axis_x) a->x+=correction; else a->y+=correction; }",
        "    else { if(axis_x) b->x-=correction; else b->y-=correction; }",
        "    int normal=push<0?-1:1;",
        "    int va=axis_x?a->vx:a->vy, vb=axis_x?b->vx:b->vy;",
        "    int relative=(va-vb)*normal;",
        "    if(relative<0){",
        "        int impulse=(-relative)/(both?2:1);",
        "        if(p->rigid&1){ if(axis_x) a->vx+=impulse*normal; else a->vy+=impulse*normal; }",
        "        if(p->rigid&2){ if(axis_x) b->vx-=impulse*normal; else b->vy-=impulse*normal; }",
        "    }",
        "}",
        "",
    ]


def _boxes(owner, sprite) -> list[tuple[int, CollisionBoxComponent]]:
    return [(rank, box) for rank, box in enumerate(owner_boxes(owner, sprite))
            if isinstance(box, CollisionBoxComponent) and box.active]


def impulse_tick_lines(p, scene_actors, actor_offset: int) -> list[str]:
    """Table des contraintes Rigid/Static et Rigid/Rigid d'une scene."""
    rows: list[tuple[int, int, int, int, int]] = []
    for ia, (actor_a, sprite_a) in enumerate(scene_actors):
        mode_a = physics_body_mode(actor_a)
        for ib in range(ia + 1, len(scene_actors)):
            actor_b, sprite_b = scene_actors[ib]
            mode_b = physics_body_mode(actor_b)
            if PHYSICS_BODY_RIGID not in (mode_a, mode_b):
                continue
            if mode_a not in (PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC):
                continue
            if mode_b not in (PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC):
                continue
            rigid = (1 if mode_a == PHYSICS_BODY_RIGID else 0) | (2 if mode_b == PHYSICS_BODY_RIGID else 0)
            for rank_a, box_a in _boxes(actor_a, sprite_a):
                for rank_b, box_b in _boxes(actor_b, sprite_b):
                    a_hits_b = (mode_a == PHYSICS_BODY_RIGID and box_a.solid
                                and box_b.response == COLLISION_RESPONSE_BLOCK)
                    b_hits_a = (mode_b == PHYSICS_BODY_RIGID and box_b.solid
                                and box_a.response == COLLISION_RESPONSE_BLOCK)
                    if not (a_hits_b or b_hits_a):
                        continue
                    if not tags_collide(p.settings, box_a.tag or "body", box_b.tag or "body"):
                        continue
                    rows.append((actor_offset + ia, actor_offset + ib, rank_a, rank_b, rigid))
    if not rows:
        return []
    lines = [
        "    /* Impulsions Rigid : masses egales, sans rebond ni friction. */",
        f"    static const RigidPair _rigid_pairs[{len(rows)}]={{",
        *[f"        {{{a},{b},{ba},{bb},{rigid}}}," for a, b, ba, bb, rigid in rows],
        "    };",
        f"    for(u8 _it=0;_it<{IMPULSE_ITERATIONS};_it++)",
        f"        for(u8 _k=0;_k<{len(rows)};_k++) rigid_pair_resolve(&_rigid_pairs[_k]);",
    ]
    return lines
