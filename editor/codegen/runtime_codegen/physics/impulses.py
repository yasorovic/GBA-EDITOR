"""Solveur d'impulsions minimal pour les corps Rigid d'une scène, posés ou nés.

Le solveur applique la normale et le tangent du contact, avec une masse configurable par Rigid. La restitution et la
friction des PhysicMaterial des CollisionShape sont combinées au build. Static, Character et Kinematic ont une masse
inverse nulle. Les couples de boîtes se lisent par couple de TYPES d'emplacement (`Actor.model`), filtrés par les tags ;
le runtime relève une fois par image l'instantané des corps (rectangle, repos), écarte les paires éloignées, puis
parcourt plusieurs fois les paires retenues pour stabiliser les petites piles. Il ne demande jamais si un emplacement
est posé ou né (règle « posé = spawné »).
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
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body, physics_body_mode, physics_collider_entries,
    shape_one_way_dir,
)
from codegen.runtime_codegen.shared_pool_gen import shared_models


# Pixels dont la première passe élargit les rectangles : une paire proche mais pas encore en contact reste dans la liste
# des passes suivantes, qui la verront se toucher après les corrections de la première.
RIGID_PAIR_MARGIN = 2
# Les tables sont lues à chaque paire testée : rangées en IWRAM, comme le descripteur de modèle.
_IW = ' __attribute__((section(".data.model_desc")))'
# Au-delà de ce nombre de corps possibles (12 octets chacun), l'instantané passe de l'IWRAM à l'EWRAM.
_SNAPSHOT_IWRAM = 64
# Les paires retenues par la première passe, gardées pour les suivantes ; au-delà, les passes suivantes rebalayent toutes
# les paires sur l'instantané (le même ensemble : les rectangles ne changent pas pendant l'image).
_LIVE_CAPACITY = 1024


def impulse_helper_lines() -> list[str]:
    """Aides C du solveur : correction de position, impulsion normale et friction, puis la passe de l'image."""
    return [
        "/* Un couple de boîtes d'un couple de types : rangs, restitution et friction Q8 combinées au build. */",
        "typedef struct { u8 box_a, box_b; u16 restitution, friction; } RigidBox;",
        "/* La résolution d'un couple de boîtes. En IWRAM, ARM : appelée pour chaque couple de chaque passe, une seule copie. */",
        "BS_ATTR_IWRAM",
        "static void __attribute__((unused)) rigid_contact(Actor* a,Actor* b,u8 box_a,u8 box_b,",
        "        int inv_mass_a,int inv_mass_b,int restitution,int friction_q8){",
        "    if(!a->active||!b->active||box_a>=a->collision.box_count||box_b>=b->collision.box_count) return;",
        "    const CollisionShape* ca=&a->collision.boxes[box_a];",
        "    const CollisionShape* cb=&b->collision.boxes[box_b];",
        "    if(!ca->active||!cb->active) return;",
        "    int al=(a->x>>8)+ca->x, at=(a->y>>8)+ca->y, ar=al+ca->w, ab=at+ca->h;",
        "    int bl=(b->x>>8)+cb->x, bt=(b->y>>8)+cb->y, br=bl+cb->w, bb=bt+cb->h;",
        "    if(al>=br||ar<=bl||at>=bb||ab<=bt) return;",
        "    int left=ar-bl, right=br-al, up=ab-bt, down=bb-at;",
        "    int px=left<right?-left:right, py=up<down?-up:down;",
        "    int apx=px<0?-px:px, apy=py<0?-py:py;",
        "    int axis_x=apx<=apy, push=axis_x?px:py, correction=push<<8;",
        "    int total=inv_mass_a+inv_mass_b;",
        "    int correction_a=(correction*inv_mass_a)/total, correction_b=correction-correction_a;",
        "    if(axis_x){ a->x+=correction_a; b->x-=correction_b; }",
        "    else { a->y+=correction_a; b->y-=correction_b; }",
        "    int normal=push<0?-1:1;",
        "    int va=axis_x?a->vx:a->vy, vb=axis_x?b->vx:b->vy;",
        "    int relative=(va-vb)*normal;",
        "    if(relative<0){",
        "        int impulse=(-relative*(256+restitution))/256;",
        "        int impulse_a=(impulse*inv_mass_a)/total, impulse_b=impulse-impulse_a;",
        "        if(axis_x){ a->vx+=impulse_a*normal; b->vx-=impulse_b*normal; }",
        "        else { a->vy+=impulse_a*normal; b->vy-=impulse_b*normal; }",
        "    }",
        "    int tangent=axis_x?a->vy-b->vy:a->vx-b->vx;",
        "    int friction=(tangent*friction_q8)/256;",
        "    int friction_a=(-friction*inv_mass_a)/total, friction_b=-friction-friction_a;",
        "    if(axis_x){ a->vy+=friction_a; b->vy-=friction_b; }",
        "    else { a->vx+=friction_a; b->vx-=friction_b; }",
        "}",
        "/* L'instantané d'un corps de l'image : emplacement, rang compact de son type, repos (StaticBody, ou Rigid",
        "   endormi : `physics_sleep` >= `sleep_frames`) et rectangle monde de ses boîtes actives. */",
        "#define RIGID_SIDE_STATIC 2",
        "#define RIGID_SIDE_RIGID 1",
        "typedef struct { u16 slot; u8 kind, rest; s16 l, t, r, b; } RigidBody;",
        "static inline __attribute__((always_inline)) void rigid_body_add(int s,const u8* ki,const u8* side,",
        "        u16 sleep_frames,RigidBody* out,int* n){",
        "    const Actor* a=&g_actors[s]; u8 j=ki[a->model];",
        "    if(j==255||!a->active) return;",
        "    int l=32767,top=32767,r=-32768,b=-32768,x=a->x>>8,y=a->y>>8;",
        "    for(int k=0;k<a->collision.box_count;k++){",
        "        const CollisionShape* c=&a->collision.boxes[k];",
        "        if(!c->active) continue;",
        "        if(x+c->x<l) l=x+c->x; if(y+c->y<top) top=y+c->y;",
        "        if(x+c->x+c->w>r) r=x+c->x+c->w; if(y+c->y+c->h>b) b=y+c->y+c->h;",
        "    }",
        "    if(r<l) return;",
        "    RigidBody* e=&out[(*n)++]; e->slot=s; e->kind=j; e->l=l; e->t=top; e->r=r; e->b=b;",
        "    e->rest=side[j]==RIGID_SIDE_STATIC||(side[j]==RIGID_SIDE_RIGID&&sleep_frames&&a->physics_sleep>=sleep_frames);",
        "}",
        "/* Les couples de boîtes d'une paire de corps. À la première passe (`wake`), un Rigid endormi que touche un corps",
        "   éveillé dont le compteur est sous 1/8 du délai (il vient de sortir de son rayon de repos) se réveille avant la",
        "   résolution : un corps qui bouge le pousse, un voisin qui se stabilise depuis plus longtemps non, sinon les",
        "   réveils se propageraient sans fin dans une pile. */",
        "static inline __attribute__((always_inline)) void rigid_pair_run(const RigidBody* A,const RigidBody* B,",
        "        const PairRun* run,const RigidBox* pairs,const u16* mass,int wake,u16 sleep_frames){",
        "    Actor* a=&g_actors[A->slot]; Actor* b=&g_actors[B->slot];",
        "    if(wake&&sleep_frames){",
        "        u8 sleeps_a=a->physics_sleep>=sleep_frames, sleeps_b=b->physics_sleep>=sleep_frames;",
        "        if(sleeps_a!=sleeps_b){",
        "            Actor* sleeper=sleeps_a?a:b; const Actor* other=sleeps_a?b:a;",
        "            if(other->physics_sleep<(sleep_frames>>3)) sleeper->physics_sleep=0;",
        "        }",
        "    }",
        "    const RigidBox* p=pairs+run->first;",
        "    for(int q=0;q<run->n;q++)",
        "        rigid_contact(a,b,p[q].box_a,p[q].box_b,mass[A->kind],mass[B->kind],p[q].restitution,p[q].friction);",
        "}",
        "/* La passe de l'image. Instantané des corps (posés `[lo,hi)` puis nés du pool si `pool`) ; première passe sur",
        "   toutes les paires, écartées au repos des deux côtés ou à plus de la marge, les autres résolues et gardées dans",
        "   `live` ; puis `iterations - 1` passes sur `live` (ou, si elle a débordé, sur toutes les paires de l'instantané :",
        "   le même ensemble). `runs` : `width` entrées par type, indexées par le rang compact du type du partenaire.",
        "   Un rejet repose sur les positions du début de l'image ; une pénétration plus grande, créée par une correction,",
        "   est reprise à l'image suivante. En IWRAM, ARM : elle parcourt toutes les paires de corps. */",
        "BS_ATTR_IWRAM",
        "static void __attribute__((unused)) rigid_solve(const u8* ki,const u16* mass,const u8* side,const PairRun* runs,",
        "        int width,const RigidBox* pairs,RigidBody* list,u32* live,int live_cap,int lo,int hi,int pool,",
        "        int iterations,u16 sleep_frames){",
        "    int n=0;",
        "    for(int s=lo;s<hi;s++) rigid_body_add(s,ki,side,sleep_frames,list,&n);",
        "    if(pool){ POOL_EACH(s) rigid_body_add(s,ki,side,sleep_frames,list,&n); }",
        "    int live_n=0, full=0;",
        "    for(int i=0;i<n;i++){",
        "        const RigidBody* A=&list[i]; const PairRun* row=runs+A->kind*width;",
        "        for(int j=i+1;j<n;j++){",
        "            const RigidBody* B=&list[j]; const PairRun* run=&row[B->kind];",
        "            if(!run->n||(A->rest&&B->rest)) continue;",
        f"            if(A->l>=B->r+{RIGID_PAIR_MARGIN}||A->r+{RIGID_PAIR_MARGIN}<=B->l"
        f"||A->t>=B->b+{RIGID_PAIR_MARGIN}||A->b+{RIGID_PAIR_MARGIN}<=B->t) continue;",
        "            if(live_n<live_cap) live[live_n++]=((u32)i<<16)|j; else full=1;",
        "            rigid_pair_run(A,B,run,pairs,mass,1,sleep_frames);",
        "        }",
        "    }",
        "    for(int it=1;it<iterations;it++){",
        "        if(!full){",
        "            for(int k=0;k<live_n;k++){",
        "                const RigidBody* A=&list[live[k]>>16]; const RigidBody* B=&list[live[k]&0xFFFF];",
        "                rigid_pair_run(A,B,&runs[A->kind*width+B->kind],pairs,mass,0,sleep_frames);",
        "            }",
        "            continue;",
        "        }",
        "        for(int i=0;i<n;i++){",
        "            const RigidBody* A=&list[i]; const PairRun* row=runs+A->kind*width;",
        "            for(int j=i+1;j<n;j++){",
        "                const RigidBody* B=&list[j]; const PairRun* run=&row[B->kind];",
        "                if(!run->n||(A->rest&&B->rest)) continue;",
        f"                if(A->l>=B->r+{RIGID_PAIR_MARGIN}||A->r+{RIGID_PAIR_MARGIN}<=B->l"
        f"||A->t>=B->b+{RIGID_PAIR_MARGIN}||A->b+{RIGID_PAIR_MARGIN}<=B->t) continue;",
        "                rigid_pair_run(A,B,run,pairs,mass,0,sleep_frames);",
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


def _inverse_mass(owner) -> int:
    """Masse inverse Q8 d'un Rigid ; 0 (masse infinie) pour tout autre corps."""
    return max(1, round(256 / physics_body(owner).mass)) if physics_body_mode(owner) == PHYSICS_BODY_RIGID else 0


def _pair_contacts(p, scene, actor_a, sprite_a, actor_b, sprite_b) -> list[tuple[int, int, int, int]]:
    """Les couples de boîtes que le solveur résout entre deux porteurs, dans cet ordre : (rang a, rang b, restitution,
    friction). Vide si aucun des deux n'est Rigid ou si un mode n'est pas pris en charge."""
    mode_a, mode_b = physics_body_mode(actor_a), physics_body_mode(actor_b)
    if PHYSICS_BODY_RIGID not in (mode_a, mode_b):
        return []
    supported = (PHYSICS_BODY_RIGID, PHYSICS_BODY_STATIC, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC)
    if mode_a not in supported or mode_b not in supported:
        return []
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
            rows.append((rank_a, rank_b, restitution, friction))
    return rows


def impulse_tick_lines(p, scene, scene_actors, actor_offset: int, pi, shown) -> list[str]:
    """La passe d'impulsions de la scène : chaque paire de corps, posés ou nés, dont un au moins est Rigid. Les couples
    de boîtes se lisent par couple ordonné de types (le corps de plus petit rang dans l'instantané est le côté « a »)."""
    lay = scene_oam_layout(p, scene)
    shared = shared_models(pi) if shown else []
    owners: dict[int, tuple] = {}       # type -> (porteur, sprite) ; les copies d'un type ont les mêmes rôles de boîtes
    for (actor, sprite), kind in zip(scene_actors, lay.placed_model):
        owners.setdefault(kind, (actor, sprite))
    for m in shared:
        owners.setdefault(m["model_id"], (m["prefab"], shown(p, m["prefab"])[1]))
    kinds = sorted(owners)
    contacts = {(a, b): _pair_contacts(p, scene, *owners[a], *owners[b]) for a in kinds for b in kinds}
    bodies = [k for k in kinds if any(contacts[(k, o)] or contacts[(o, k)] for o in kinds)]
    if not bodies:
        return []
    iterations, _max_fall, _damping, sleep_enabled, _threshold, sleep_delay = scene.effective_physics_simulation(p.settings)
    sleep_frames = sleep_delay if sleep_enabled else 0

    flat: list[str] = []
    run_rows = []
    for a in bodies:
        row = []
        for b in bodies:
            run = contacts[(a, b)]
            row.append(f"{{{len(flat)},{len(run)}}}")
            flat += [f"{{{ra},{rb},{re},{fr}}}" for ra, rb, re, fr in run]
        run_rows.append("{" + ",".join(row) + "}")
    index = {k: i for i, k in enumerate(bodies)}
    placed_kinds = set(lay.placed_model)
    pool_kinds = {m["model_id"] for m in shared}
    hi = actor_offset + len(scene_actors) if placed_kinds & set(bodies) else actor_offset
    pool = 1 if pool_kinds & set(bodies) else 0
    spool = shared[0]["spool"]["end"] - shared[0]["spool"]["start"] if pool else 0
    capacity = sum(1 for kind in lay.placed_model if kind in index) + spool
    live = min(_LIVE_CAPACITY, capacity * (capacity - 1) // 2) or 1
    where = "" if capacity <= _SNAPSHOT_IWRAM else " EWRAM_BSS"
    by_kind = ",".join(str(index.get(k, 255)) for k in range(lay.kinds))
    return [
        "    /* Impulsions Rigid, par couple de types : masses et matériaux Q8 */",
        "    {",
        f"        static u8 _ri_ki[{lay.kinds}]{_IW}={{{by_kind}}};",
        f"        static u16 _ri_mass[{len(bodies)}]{_IW}={{{','.join(str(_inverse_mass(owners[k][0])) for k in bodies)}}};",
        f"        static u8 _ri_side[{len(bodies)}]{_IW}="
        f"{{{','.join(str(_side_kind(physics_body_mode(owners[k][0]))) for k in bodies)}}};",
        f"        static PairRun _ri_run[{len(bodies)}][{len(bodies)}]{_IW}={{{','.join(run_rows)}}};",
        f"        static RigidBox _ri_pair[{max(1, len(flat))}]{_IW}={{{','.join(flat) or '{0}'}}};",
        f"        static RigidBody _ri_list[{capacity}]{where};",
        f"        static u32 _ri_live[{live}] EWRAM_BSS;",
        f"        rigid_solve(_ri_ki,_ri_mass,_ri_side,&_ri_run[0][0],{len(bodies)},_ri_pair,_ri_list,_ri_live,{live},"
        f"{actor_offset},{hi},{pool},{iterations},{sleep_frames});",
        "    }",
    ]
