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
    shape_material,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body, physics_body_mode, physics_collider_entries,
    shape_one_way_dir,
)
from codegen.runtime_codegen.shared_pool_gen import shared_models


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
        "/* Les paires dont un côté est une instance du pool PARTAGÉ : le build ne connaît pas son emplacement, il désigne",
        "   un MODÈLE (`Actor.model`) et les emplacements utilisés sont parcourus. Même règle que `rigid_pairs_scan` (marge,",
        "   repos des deux côtés, réveil), même résolution : `rigid_pair_resolve`. `kind` : RIGID_SIDE_STATIC, RIGID_SIDE_RIGID",
        "   ou 0. */",
        "typedef struct { u16 a,inv_mass_a,inv_mass_b,restitution,friction; u8 model,box_a,box_b,kind_a,kind_b; } RigidPlacedPoolPair;",
        "typedef struct { u16 inv_mass_a,inv_mass_b,restitution,friction; u8 model_a,model_b,box_a,box_b,kind_a,kind_b; } RigidPoolPair;",
        "static void __attribute__((unused)) rigid_slot_pair_run(u16 a,u16 b,u8 box_a,u8 box_b,u8 kind_a,u8 kind_b,",
        "        u16 inv_mass_a,u16 inv_mass_b,u16 restitution,u16 friction,u16 sleep_frames){",
        "    Actor* A=&g_actors[a]; Actor* B=&g_actors[b];",
        "    if(!A->active||!B->active||box_a>=A->collision.box_count||box_b>=B->collision.box_count) return;",
        "    const CollisionShape* ca=&A->collision.boxes[box_a]; const CollisionShape* cb=&B->collision.boxes[box_b];",
        "    if(!ca->active||!cb->active) return;",
        "    int al=(A->x>>8)+ca->x, at=(A->y>>8)+ca->y, bl=(B->x>>8)+cb->x, bt=(B->y>>8)+cb->y;",
        f"    if(al>=bl+cb->w+{RIGID_PAIR_MARGIN}||al+ca->w+{RIGID_PAIR_MARGIN}<=bl"
        f"||at>=bt+cb->h+{RIGID_PAIR_MARGIN}||at+ca->h+{RIGID_PAIR_MARGIN}<=bt) return;",
        "    if(sleep_frames){",
        "        u8 sleeps_a=A->physics_sleep>=sleep_frames, sleeps_b=B->physics_sleep>=sleep_frames;",
        "        if((kind_a==RIGID_SIDE_STATIC||(kind_a==RIGID_SIDE_RIGID&&sleeps_a))",
        "         &&(kind_b==RIGID_SIDE_STATIC||(kind_b==RIGID_SIDE_RIGID&&sleeps_b))) return;",
        "        if(sleeps_a!=sleeps_b){",
        "            Actor* sleeper=sleeps_a?A:B; const Actor* other=sleeps_a?B:A;",
        "            if(other->physics_sleep<(sleep_frames>>3)) sleeper->physics_sleep=0;",
        "        }",
        "    }",
        "    RigidPair p={a,b,inv_mass_a,inv_mass_b,restitution,friction,box_a,box_b};",
        "    rigid_pair_resolve(&p);",
        "}",
        "static void __attribute__((unused)) rigid_pool_pass(const RigidPlacedPoolPair* pp,u16 np,const RigidPoolPair* qq,u16 nq,u16 sleep_frames){",
        "    for(u16 k=0;k<np;k++){",
        "        POOL_EACH(s){",
        "            if(g_actors[s].model!=pp[k].model) continue;",
        "            rigid_slot_pair_run(pp[k].a,s,pp[k].box_a,pp[k].box_b,pp[k].kind_a,pp[k].kind_b,",
        "                pp[k].inv_mass_a,pp[k].inv_mass_b,pp[k].restitution,pp[k].friction,sleep_frames);",
        "        }",
        "    }",
        "    for(u16 k=0;k<nq;k++){",
        "        POOL_EACH(s){",
        "            if(g_actors[s].model!=qq[k].model_a) continue;",
        "            POOL_EACH(t){",
        "                if(g_actors[t].model!=qq[k].model_b||(qq[k].model_a==qq[k].model_b&&t<=s)) continue;",
        "                rigid_slot_pair_run(s,t,qq[k].box_a,qq[k].box_b,qq[k].kind_a,qq[k].kind_b,",
        "                    qq[k].inv_mass_a,qq[k].inv_mass_b,qq[k].restitution,qq[k].friction,sleep_frames);",
        "            }",
        "        }",
        "    }",
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


def _side_kind(mode: str | None) -> int:
    """2 StaticBody, 1 RigidBody, 0 Character ou Kinematic (jamais au repos)."""
    return 2 if mode == PHYSICS_BODY_STATIC else 1 if mode == PHYSICS_BODY_RIGID else 0


def _pair_contacts(p, scene, actor_a, sprite_a, actor_b, sprite_b) -> list[tuple[int, int, int, int, int, int]]:
    """Les couples de boîtes que le solveur résout entre deux porteurs : (rang a, rang b, masse inverse a, masse
    inverse b, restitution, friction). Vide si aucun des deux n'est Rigid ou si un mode n'est pas pris en charge."""
    mode_a, mode_b = physics_body_mode(actor_a), physics_body_mode(actor_b)
    if PHYSICS_BODY_RIGID not in (mode_a, mode_b):
        return []
    supported = (PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC)
    if mode_a not in supported or mode_b not in supported:
        return []
    inv_mass_a = max(1, round(256 / physics_body(actor_a).mass)) if mode_a == PHYSICS_BODY_RIGID else 0
    inv_mass_b = max(1, round(256 / physics_body(actor_b).mass)) if mode_b == PHYSICS_BODY_RIGID else 0
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
    rows = []
    for (rank_a, rank_b), (box_a, box_b) in pairs.items():
        if tags_collide(p.settings, box_a.tag or "body", box_b.tag or "body"):
            restitution, friction = _contact_material(actor_a, box_a, actor_b, box_b)
            rows.append((rank_a, rank_b, inv_mass_a, inv_mass_b, restitution, friction))
    return rows


def impulse_tick_lines(p, scene, scene_actors, actor_offset: int, pi, shown) -> list[str]:
    """Contraintes d'un Rigid contre les corps poses qui ne recoivent pas son impulsion, puis contre les instances du
    pool partage (par modele : leur emplacement n'est connu qu'a l'execution)."""
    rows: list[tuple[int, int, int, int, int, int, int, int]] = []
    kinds: dict[int, int] = {}      # indice d'acteur -> _side_kind
    for ia, (actor_a, sprite_a) in enumerate(scene_actors):
        for ib in range(ia + 1, len(scene_actors)):
            actor_b, sprite_b = scene_actors[ib]
            for rank_a, rank_b, ma, mb, re, fr in _pair_contacts(p, scene, actor_a, sprite_a, actor_b, sprite_b):
                rows.append((actor_offset + ia, actor_offset + ib, ma, mb, re, fr, rank_a, rank_b))
                kinds[actor_offset + ia] = _side_kind(physics_body_mode(actor_a))
                kinds[actor_offset + ib] = _side_kind(physics_body_mode(actor_b))
    shared = shared_models(pi)
    shared_owners = [(m, m["prefab"], shown(p, m["prefab"])[1]) for m in shared]
    placed_pool = [(actor_offset + ia, _side_kind(physics_body_mode(actor)), m["model_id"], _side_kind(physics_body_mode(m["prefab"])), contact)
                   for ia, (actor, sprite) in enumerate(scene_actors) for m, owner, owner_sprite in shared_owners
                   for contact in _pair_contacts(p, scene, actor, sprite, owner, owner_sprite)]
    pool_pool = [(m1["model_id"], _side_kind(physics_body_mode(m1["prefab"])), m2["model_id"],
                  _side_kind(physics_body_mode(m2["prefab"])), contact)
                 for i, (m1, owner1, sprite1) in enumerate(shared_owners)
                 for m2, owner2, sprite2 in shared_owners[i:]
                 for contact in _pair_contacts(p, scene, owner1, sprite1, owner2, sprite2)]
    if not rows and not placed_pool and not pool_pool:
        return []
    iterations, _max_fall, _damping, sleep_enabled, _threshold, sleep_delay = scene.effective_physics_simulation(p.settings)
    sleep_frames = sleep_delay if sleep_enabled else 0
    pool_lines: list[str] = []
    if placed_pool or pool_pool:
        pool_lines = [
            "    /* Impulsions Rigid contre le pool partage : une rangee par modele et par couple de boites. */",
            *([f"    static const RigidPlacedPoolPair _rigid_pp[{len(placed_pool)}]={{",
               *[f"        {{{a},{ma},{mb},{re},{fr},{model},{ba},{bb},{ka},{kb}}},"
                 for a, ka, model, kb, (ba, bb, ma, mb, re, fr) in placed_pool],
               "    };"] if placed_pool else []),
            *([f"    static const RigidPoolPair _rigid_qq[{len(pool_pool)}]={{",
               *[f"        {{{ma},{mb},{re},{fr},{model_a},{model_b},{ba},{bb},{ka},{kb}}},"
                 for model_a, ka, model_b, kb, (ba, bb, ma, mb, re, fr) in pool_pool],
               "    };"] if pool_pool else []),
            f"    for(u8 _pit=0;_pit<{iterations};_pit++)",
            f"        rigid_pool_pass({'_rigid_pp' if placed_pool else '0'},{len(placed_pool)},"
            f"{'_rigid_qq' if pool_pool else '0'},{len(pool_pool)},{sleep_frames});",
        ]
    if not rows:
        return pool_lines
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
    return lines + pool_lines
