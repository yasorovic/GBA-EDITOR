"""Solveur d'impulsions minimal pour les corps Rigid poses dans une scene.

Le solveur applique la normale et le tangent du contact, avec une masse configurable par Rigid. La restitution
et la friction des PhysicMaterial des CollisionShape sont combinees au build. Static, Character et Kinematic ont une masse inverse
nulle. Les paires sont connues au build, filtrees par les tags et parcourues plusieurs fois pour stabiliser les
petites piles.
"""
from __future__ import annotations

import math

from core.models.components import (
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
    CollisionShapeComponent,
    collision_shapes_collide,
    shape_material,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body, physics_body_mode, physics_collider_entries,
    shape_one_way_dir,
)


# Pixels dont la première passe élargit les rectangles : une paire proche mais pas encore en contact reste dans la liste
# des passes suivantes, qui la verront se toucher après les corrections de la première.
RIGID_PAIR_MARGIN = 2


def impulse_helper_lines() -> list[str]:
    """Aide C du solveur : correction de position, impulsion normale et friction."""
    return [
        "typedef struct { u16 a,b,inv_mass_a,inv_mass_b,restitution,friction; u8 box_a,box_b; } RigidPair;",
        "static void __attribute__((unused)) rigid_pair_resolve(const RigidPair* p){",
        "    Actor* a=&g_actors[p->a]; Actor* b=&g_actors[p->b];",
        "    if(!a->active||!b->active||p->box_a>=a->collision.box_count||p->box_b>=b->collision.box_count) return;",
        "    const CollisionShape* ca=&a->collision.boxes[p->box_a];",
        "    const CollisionShape* cb=&b->collision.boxes[p->box_b];",
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
        "        int impulse=(-relative*(256+p->restitution))/256;",
        "        int impulse_a=(impulse*p->inv_mass_a)/total, impulse_b=impulse-impulse_a;",
        "        if(axis_x){ a->vx+=impulse_a*normal; b->vx-=impulse_b*normal; }",
        "        else { a->vy+=impulse_a*normal; b->vy-=impulse_b*normal; }",
        "    }",
        "    int tangent=axis_x?a->vy-b->vy:a->vx-b->vx;",
        "    int friction=(tangent*p->friction)/256;",
        "    int friction_a=(-friction*p->inv_mass_a)/total, friction_b=-friction-friction_a;",
        "    if(axis_x){ a->vy+=friction_a; b->vy-=friction_b; }",
        "    else { a->vx+=friction_a; b->vx-=friction_b; }",
        "}",
        "/* Rectangle monde d'un côté de paire {gauche, haut, droite, bas, repos}, relevé une fois par frame. Un côté",
        "   absent ou inactif rend un rectangle vide : il est rejeté contre tout. `repos` vaut 1 pour un StaticBody et",
        "   pour un Rigid endormi (`sleep_frames` > 0) : une paire dont les deux côtés sont au repos ne bouge pas. */",
        "#define RIGID_SIDE_STATIC 2",
        "#define RIGID_SIDE_RIGID 1",
        "static void __attribute__((unused)) rigid_side_rect(u16 actor,u8 box,u8 kind,u16 sleep_frames,s16* r){",
        "    const Actor* a=&g_actors[actor];",
        "    r[4]=0;",
        "    if(!a->active||box>=a->collision.box_count||!a->collision.boxes[box].active){",
        "        r[0]=r[1]=32767; r[2]=r[3]=-32768; return;",
        "    }",
        "    const CollisionShape* c=&a->collision.boxes[box];",
        "    r[0]=(a->x>>8)+c->x; r[1]=(a->y>>8)+c->y; r[2]=r[0]+c->w; r[3]=r[1]+c->h;",
        "    r[4]=kind==RIGID_SIDE_STATIC||(kind==RIGID_SIDE_RIGID&&sleep_frames&&a->physics_sleep>=sleep_frames);",
        "}",
        "/* Première passe : rejette chaque paire sur les rectangles (au repos des deux côtés, ou à plus de la marge),",
        "   résout les autres et rend leur nombre; `live` en garde les rangs pour les passes suivantes. Un Rigid endormi",
        "   (`physics_sleep` >= `sleep_frames`) que touche un corps éveillé dont le compteur est sous 1/8 du délai (il vient",
        "   de sortir de son rayon de repos) se réveille avant la résolution : un corps qui bouge le pousse, un voisin",
        "   qui se stabilise depuis plus longtemps non, sinon les réveils se propageraient sans fin dans une pile.",
        "   Elle tourne à chaque image sur toutes les paires : en IWRAM, ARM, sans temps d'attente. */",
        "BS_ATTR_IWRAM",
        "static u16 rigid_pairs_scan(const RigidPair* pairs,const u16 (*sides)[2],s16 (*rect)[5],u16 n,u16* live,u16 sleep_frames){",
        "    u16 live_n=0;",
        "    for(u16 k=0;k<n;k++){",
        "        const s16* ra=rect[sides[k][0]]; const s16* rb=rect[sides[k][1]];",
        "        if(ra[4]&&rb[4]) continue;",
        f"        if(ra[0]>=rb[2]+{RIGID_PAIR_MARGIN}||ra[2]+{RIGID_PAIR_MARGIN}<=rb[0]"
        f"||ra[1]>=rb[3]+{RIGID_PAIR_MARGIN}||ra[3]+{RIGID_PAIR_MARGIN}<=rb[1]) continue;",
        "        if(sleep_frames){",
        "            Actor* a=&g_actors[pairs[k].a]; Actor* b=&g_actors[pairs[k].b];",
        "            u8 sleeps_a=a->physics_sleep>=sleep_frames, sleeps_b=b->physics_sleep>=sleep_frames;",
        "            if(sleeps_a!=sleeps_b){",
        "                Actor* sleeper=sleeps_a?a:b; const Actor* other=sleeps_a?b:a;",
        "                if(other->physics_sleep<(sleep_frames>>3)) sleeper->physics_sleep=0;",
        "            }",
        "        }",
        "        live[live_n++]=k;",
        "        rigid_pair_resolve(&pairs[k]);",
        "    }",
        "    return live_n;",
        "}",
        "",
    ]


def _physical_boxes(owner, sprite) -> list[tuple[int, CollisionShapeComponent]]:
    return [(rank, box) for rank, box in physics_collider_entries(owner, sprite)
            if box.active]


def _contact_material(owner_a, a: CollisionShapeComponent, owner_b, b: CollisionShapeComponent) -> tuple[int, int]:
    """Les coefficients Q8 d'un contact, cuits plutôt que recombinés en ROM."""
    material_a, material_b = shape_material(owner_a, a), shape_material(owner_b, b)
    restitution = round(max(material_a.restitution, material_b.restitution) * 256)
    friction = math.isqrt(round(material_a.friction * 256) * round(material_b.friction * 256))
    return restitution, friction


def impulse_tick_lines(p, scene, scene_actors, actor_offset: int) -> list[str]:
    """Contraintes d'un Rigid contre les corps poses qui ne recoivent pas son impulsion."""
    rows: list[tuple[int, int, int, int, int, int, int, int]] = []
    kinds: dict[int, int] = {}      # indice d'acteur -> 2 StaticBody, 1 RigidBody, 0 Character ou Kinematic (jamais au repos)
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
            pairs: dict[tuple[int, int], tuple[CollisionShapeComponent, CollisionShapeComponent]] = {}
            if mode_a == PHYSICS_BODY_RIGID:
                for rank_a, box_a in _physical_boxes(actor_a, sprite_a):
                    for rank_b, box_b in physics_blocker_entries(actor_b, sprite_b):
                        if not shape_one_way_dir(box_b, scene, p.settings):     # une face à sens unique n'a pas de rebond
                            pairs[(rank_a, rank_b)] = (box_a, box_b)
            if mode_b == PHYSICS_BODY_RIGID:
                for rank_a, box_a in physics_blocker_entries(actor_a, sprite_a):
                    if shape_one_way_dir(box_a, scene, p.settings):
                        continue
                    for rank_b, box_b in _physical_boxes(actor_b, sprite_b):
                        pairs[(rank_a, rank_b)] = (box_a, box_b)
            for (rank_a, rank_b), (box_a, box_b) in pairs.items():
                if (tags_collide(p.settings, box_a.tag or "body", box_b.tag or "body")
                        and collision_shapes_collide(box_a, box_b)):
                    restitution, friction = _contact_material(actor_a, box_a, actor_b, box_b)
                    rows.append((actor_offset + ia, actor_offset + ib,
                                 inv_mass_a, inv_mass_b, restitution, friction, rank_a, rank_b))
                    for index, mode in ((actor_offset + ia, mode_a), (actor_offset + ib, mode_b)):
                        kinds[index] = (2 if mode == PHYSICS_BODY_STATIC else 1 if mode == PHYSICS_BODY_RIGID else 0)
    if not rows:
        return []
    iterations, _max_fall, _damping, sleep_enabled, _threshold, sleep_delay = scene.effective_physics_simulation(p.settings)
    sleep_frames = sleep_delay if sleep_enabled else 0
    # Chaque côté (acteur, rang de boîte) a un rectangle relevé une fois par frame : une paire qui ne se touche pas
    # est rejetée sur ces rectangles, sans relire les deux acteurs. Un rejet repose sur les positions du début de frame
    # (marge `RIGID_PAIR_MARGIN`); une pénétration plus grande, créée par une correction, est reprise à la frame suivante.
    sides: dict[tuple[int, int], int] = {}
    for a, b, _ma, _mb, _re, _fr, ba, bb in rows:
        sides.setdefault((a, ba), len(sides))
        sides.setdefault((b, bb), len(sides))
    lines = [
        "    /* Impulsions Rigid : masses et materiaux Q8. */",
        f"    static const RigidPair _rigid_pairs[{len(rows)}]={{",
        *[f"        {{{a},{b},{ma},{mb},{re},{fr},{ba},{bb}}},"
          for a, b, ma, mb, re, fr, ba, bb in rows],
        "    };",
        f"    static const u16 _rigid_sides[{len(sides)}][3]={{",
        *[f"        {{{actor},{box},{kinds[actor]}}}," for actor, box in sides],
        "    };",
        f"    static const u16 _rigid_pair_sides[{len(rows)}][2]={{",
        *[f"        {{{sides[(a, ba)]},{sides[(b, bb)]}}}," for a, b, _ma, _mb, _re, _fr, ba, bb in rows],
        "    };",
        f"    static s16 _rigid_rect[{len(sides)}][5];",
        f"    static u16 _rigid_live[{len(rows)}];",
        f"    for(u16 _s=0;_s<{len(sides)};_s++) rigid_side_rect(_rigid_sides[_s][0],_rigid_sides[_s][1],_rigid_sides[_s][2],{sleep_frames},_rigid_rect[_s]);",
        # Première passe : toutes les paires, rejetées sur les rectangles élargis de la marge; celles qui restent sont
        # retenues pour les passes suivantes, qui ne parcourent plus que cette liste.
        f"    u16 _live_n=rigid_pairs_scan(_rigid_pairs,_rigid_pair_sides,_rigid_rect,{len(rows)},_rigid_live,{sleep_frames});",
        f"    for(u8 _it=1;_it<{iterations};_it++)",
        "        for(u16 _l=0;_l<_live_n;_l++) rigid_pair_resolve(&_rigid_pairs[_rigid_live[_l]]);",
    ]
    return lines
