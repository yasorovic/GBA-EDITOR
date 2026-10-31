"""Solveur d'impulsions minimal pour les corps Rigid poses dans une scene.

Cette tranche ne gere que la normale du contact, avec une masse configurable par Rigid, sans
restitution ni friction. Static, Character et Kinematic ont une masse inverse nulle. Les paires sont connues au
build, filtrees par les tags et parcourues plusieurs fois pour stabiliser les petites piles.
"""
from __future__ import annotations

from core.models.components import (
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
    CollisionBoxComponent,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body, physics_body_mode, physics_collider_entries,
)


def impulse_helper_lines() -> list[str]:
    """Aide C du solveur : correction de position puis impulsion normale."""
    return [
        "typedef struct { u16 a,b,inv_mass_a,inv_mass_b; u8 box_a,box_b; } RigidPair;",
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
        "    int total=p->inv_mass_a+p->inv_mass_b;",
        "    int correction_a=(correction*p->inv_mass_a)/total, correction_b=correction-correction_a;",
        "    if(axis_x){ a->x+=correction_a; b->x-=correction_b; }",
        "    else { a->y+=correction_a; b->y-=correction_b; }",
        "    int normal=push<0?-1:1;",
        "    int va=axis_x?a->vx:a->vy, vb=axis_x?b->vx:b->vy;",
        "    int relative=(va-vb)*normal;",
        "    if(relative<0){",
        "        int impulse_a=(-relative*p->inv_mass_a)/total, impulse_b=-relative-impulse_a;",
        "        if(axis_x){ a->vx+=impulse_a*normal; b->vx-=impulse_b*normal; }",
        "        else { a->vy+=impulse_a*normal; b->vy-=impulse_b*normal; }",
        "    }",
        "}",
        "",
    ]


def _physical_boxes(owner, sprite) -> list[tuple[int, CollisionBoxComponent]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active]


def impulse_tick_lines(p, scene, scene_actors, actor_offset: int) -> list[str]:
    """Contraintes d'un Rigid contre les corps poses qui ne recoivent pas son impulsion."""
    rows: list[tuple[int, int, int, int, int, int]] = []
    for ia, (actor_a, sprite_a) in enumerate(scene_actors):
        mode_a = physics_body_mode(actor_a)
        for ib in range(ia + 1, len(scene_actors)):
            actor_b, sprite_b = scene_actors[ib]
            mode_b = physics_body_mode(actor_b)
            if PHYSICS_BODY_RIGID not in (mode_a, mode_b):
                continue
            supported = (PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC,
                         PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC)
            if mode_a not in supported:
                continue
            if mode_b not in supported:
                continue
            body_a = physics_body(actor_a)
            body_b = physics_body(actor_b)
            inv_mass_a = max(1, round(256 / body_a.mass)) if mode_a == PHYSICS_BODY_RIGID else 0
            inv_mass_b = max(1, round(256 / body_b.mass)) if mode_b == PHYSICS_BODY_RIGID else 0
            pairs: dict[tuple[int, int], tuple[CollisionBoxComponent, CollisionBoxComponent]] = {}
            if mode_a == PHYSICS_BODY_RIGID:
                for rank_a, box_a in _physical_boxes(actor_a, sprite_a):
                    for rank_b, box_b in physics_blocker_entries(actor_b, sprite_b):
                        pairs[(rank_a, rank_b)] = (box_a, box_b)
            if mode_b == PHYSICS_BODY_RIGID:
                for rank_a, box_a in physics_blocker_entries(actor_a, sprite_a):
                    for rank_b, box_b in _physical_boxes(actor_b, sprite_b):
                        pairs[(rank_a, rank_b)] = (box_a, box_b)
            for (rank_a, rank_b), (box_a, box_b) in pairs.items():
                if tags_collide(p.settings, box_a.tag or "body", box_b.tag or "body"):
                    rows.append((actor_offset + ia, actor_offset + ib,
                                 inv_mass_a, inv_mass_b, rank_a, rank_b))
    if not rows:
        return []
    iterations = scene.effective_physics_simulation(p.settings)[0]
    lines = [
        "    /* Impulsions Rigid : masses Q8, sans rebond ni friction. */",
        f"    static const RigidPair _rigid_pairs[{len(rows)}]={{",
        *[f"        {{{a},{b},{ma},{mb},{ba},{bb}}}," for a, b, ma, mb, ba, bb in rows],
        "    };",
        f"    for(u8 _it=0;_it<{iterations};_it++)",
        f"        for(u8 _k=0;_k<{len(rows)};_k++) rigid_pair_resolve(&_rigid_pairs[_k]);",
    ]
    return lines
