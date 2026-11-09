"""Contact au sol final d'un CharacterBody ou d'un RigidBody sur les corps sous lui, posés ou nés.

Tout se lit par TYPE d'emplacement (`Actor.type_id`) : pour un type de corps et un type d'appui, la suite des couples de
boîtes qui peuvent porter, filtrée au build (matrice des tags, modes des deux corps, faces à sens unique). Le runtime
ne demande jamais si un emplacement est posé ou né (règle « posé = spawné »)."""
from __future__ import annotations

from core.models.collision_tiles import ONEWAY_NONE, ONEWAY_UP
from core.models.components import (
    ONE_WAY_GRAVITY,
    ONE_WAY_OFF,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
)
from core.models.settings import tags_collide
from codegen.iwram_plan import iwram_table
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.model_desc import each_slot
from codegen.runtime_codegen.shared_pool_gen import shared_models
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries,
    physics_body_mode,
    physics_collider_entries,
    project_sets_gravity,
    shape_one_way_dir,
    support_normal,
)

# Au-delà de ce nombre d'appuis possibles (12 octets chacun), l'instantané de l'image passe de l'IWRAM à l'EWRAM.
_SNAPSHOT_IWRAM = 64


def project_has_floors(p) -> bool:
    """Le projet peut produire un contact au sol entre acteurs."""
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    modes = {physics_body_mode(owner) for owner in owners}
    if PHYSICS_BODY_RIGID in modes:
        return True
    return PHYSICS_BODY_CHARACTER in modes and bool(
        modes & {PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC})


def floor_helper_lines() -> list[str]:
    """Teste un contact final exact, sans refaire la résolution physique, puis la passe d'un corps contre ses appuis."""
    return [
        "/* Le contact d'une boîte de corps sur une boîte d'appui, pour un côté d'appui `n` : 1 bas, 2 haut, 3 droite,",
        "   4 gauche. Le corps ne doit pas s'éloigner de son appui (vitesse de sens contraire). Le premier appui qui porte",
        "   l'emporte. */",
        "static inline __attribute__((always_inline, unused)) void actor_floor_test_n(Actor* a,u8 ab,const Actor* s,u8 sb,u8 n){",
        "    if(g_actor_floor[a->slot_index]||!s->active) return;",
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
        "    if(hit) g_actor_floor[a->slot_index]=(u16)(s->slot_index+1);",
        "}",
        "/* Un couple de boîtes (corps, appui) d'un couple de types. `guard` : la face à sens unique de direction fixe ne",
        "   porte que tant que le côté d'appui lu à l'exécution est le sien (0 : toujours) ; `one_way` : elle ne porte plus",
        "   pendant `drop_through`. */",
        "typedef struct { u8 body_box, support_box, guard, one_way; } FloorPair;",
        "static inline __attribute__((always_inline)) int floor_run(Actor* a,u8 cb,const Actor* t,const FloorPair* p,",
        "        u8 n,u8 side,int drop){",
        "    for(int k=0;k<n;k++){",
        "        if(p[k].body_box!=cb||(p[k].guard&&g_support_normal!=p[k].guard)||(p[k].one_way&&drop)) continue;",
        "        actor_floor_test_n(a,cb,t,p[k].support_box,side);",
        "        if(g_actor_floor[a->slot_index]) return 1;",
        "    }",
        "    return 0;",
        "}",
        "/* L'instantané des appuis de l'image : chaque emplacement vivant dont le type porte (`si[model]` != 255),",
        "   posé ou né, dans l'ordre des emplacements (`SLOT_EACH`), avec le rectangle monde de ses boîtes",
        "   actives. Relevé une fois après toutes les corrections de position : les corps ne relisent plus `g_actors` pour",
        "   les appuis qu'ils ne touchent pas. */",
        "typedef struct { u16 slot; u8 kind; u8 pad; s16 l, t, r, b; } FloorSupport;",
        "static inline __attribute__((always_inline)) void floor_support_add(int s,const u8* si,FloorSupport* out,int* n){",
        "    const Actor* t=&g_actors[s]; u8 j=si[t->type_id];",
        "    if(j==255||!t->active) return;",
        "    int l=32767,top=32767,r=-32768,b=-32768,x=t->x>>8,y=t->y>>8;",
        "    for(int k=0;k<t->collision.box_count;k++){",
        "        const CollisionShape* c=&t->collision.boxes[k];",
        "        if(!c->active) continue;",
        "        if(x+c->x<l) l=x+c->x;",
        "        if(y+c->y<top) top=y+c->y;",
        "        if(x+c->x+c->w>r) r=x+c->x+c->w;",
        "        if(y+c->y+c->h>b) b=y+c->y+c->h;",
        "    }",
        "    if(r<l) return;",
        "    FloorSupport* f=&out[(*n)++]; f->slot=s; f->kind=j; f->l=l; f->t=top; f->r=r; f->b=b;",
        "}",
        "BS_ATTR_IWRAM",
        "static int __attribute__((unused)) floor_supports(const u8* si,FloorSupport* out){",
        "    int n=0;",
        "    SLOT_EACH(s) floor_support_add(s,si,out,&n);",
        "    return n;",
        "}",
        "/* Le contact au sol d'un corps contre les appuis de l'instantané, chaque boîte de corps (`mask`) à son tour : un",
        "   appui dont le rectangle ne touche pas la boîte est écarté sans relire l'acteur. `runs` est la ligne du type du",
        "   corps, indexée par le rang compact du type de l'appui. `normal` : le côté d'appui de la scène, 0 = lu dans",
        "   `g_support_normal` (un script écrit `scene.gravity`). En IWRAM, ARM : elle tourne pour chaque corps. */",
        "BS_ATTR_IWRAM",
        "static void __attribute__((unused)) actors_floor(Actor* a,u8 mask,const PairRun* runs,const FloorSupport* list,",
        "        int count,const FloorPair* pairs,u8 normal){",
        "    if(!g_actor_floor) return;",
        "    g_actor_floor[a->slot_index]=0;",
        "    if(!a->active) return;",
        "    u8 side=normal?normal:g_support_normal;",
        "    int drop=g_drop_through&&g_drop_through[a->slot_index];",
        "    int x=a->x>>8,y=a->y>>8;",
        "    for(int cb=0;cb<a->collision.box_count;cb++){",
        "        const CollisionShape* m=&a->collision.boxes[cb];",
        "        if(!(mask&(1u<<cb))||!m->active) continue;",
        "        int l=x+m->x,t=y+m->y,r=l+m->w,b=t+m->h;",
        "        for(int k=0;k<count;k++){",
        "            const FloorSupport* f=&list[k];",
        "            if(l>f->r||r<f->l||t>f->b||b<f->t) continue;",
        "            const Actor* s=&g_actors[f->slot]; const PairRun* run=&runs[f->kind];",
        "            if(s==a||!run->n) continue;",
        "            if(floor_run(a,cb,s,pairs+run->first,run->n,side,drop)) return;",
        "        }",
        "    }",
        "}",
        "",
    ]


def floor_tick_lines(p, scene_actors, scene=None, pi=(), resolve_initial_appearance=None) -> list[str]:
    """Actualise le contact au sol après toutes les corrections de position de la frame.

    Un CharacterBody repose sur un StaticBody ou un KinematicBody. Un RigidBody repose aussi sur un Character ou un
    autre Rigid : le solveur d'impulsions le laisse exactement au contact, sans produire lui-même de contact au sol.

    Corps et appuis sont posés ou nés dans le pool partagé (`pi`, `resolve_initial_appearance`) : leurs couples se lisent par type. Les
    appuis se parcourent dans l'ordre des emplacements ; le premier qui porte l'emporte."""
    n = support_normal(scene, p.settings) if scene is not None else ONEWAY_UP
    # Un script écrit `scene.gravity` : le côté d'appui se lit à l'exécution (`g_support_normal`). Une face à sens
    # unique de direction fixe ne compte alors que tant que le côté d'appui est le sien ; une face en mode `gravity`
    # garde la direction cuite au départ de la scène (ses blocages le sont aussi), donc reste un sol.
    dynamic = project_sets_gravity(p)
    lay = scene_oam_layout(p, scene)
    shared = shared_models(pi) if resolve_initial_appearance else []
    owners: dict[int, tuple] = {}       # type -> (porteur, sprite) ; les copies d'un type ont les mêmes rôles de boîtes
    for (actor, sprite), kind in zip(scene_actors, lay.placed_type_ids):
        owners.setdefault(kind, (actor, sprite))
    for m in shared:
        owners.setdefault(m["root_type_id"], (m["prefab"], resolve_initial_appearance(p, m["prefab"])[1]))

    def supports(owner, sprite) -> list[tuple[int, object, int, bool]]:
        """(rang de boîte, boîte, garde, sens unique) de chaque face qui peut porter, ou rien."""
        if physics_body_mode(owner) not in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_CHARACTER,
                                            PHYSICS_BODY_RIGID):
            return []
        out = []
        for sb, box in physics_blocker_entries(owner, sprite):
            guard = 0
            face = ONEWAY_NONE
            if scene is not None:
                face = shape_one_way_dir(box, scene, p.settings)
                if dynamic and box.one_way not in (ONE_WAY_OFF, ONE_WAY_GRAVITY):
                    guard = face
                # Une face à sens unique ne porte que par sa face d'appui : les autres ne sont pas un sol.
                elif face not in (ONEWAY_NONE, n):
                    continue
            out.append((sb, box, guard, face != ONEWAY_NONE))
        return out

    floors = {kind: rows for kind, (owner, sprite) in owners.items() if (rows := supports(owner, sprite))}
    if not floors:
        return []

    def pairs(owner, sprite, support_kind) -> list[tuple[int, int, int, int]]:
        """Les couples (boîte de corps, boîte d'appui, garde, sens unique) de ce corps sur ce type d'appui. Un Character
        ne repose que sur un Static ou un Kinematic ; un Rigid sur tout corps."""
        mode = physics_body_mode(owner)
        support_mode = physics_body_mode(owners[support_kind][0])
        if not (mode == PHYSICS_BODY_RIGID or support_mode in (PHYSICS_BODY_STATIC, PHYSICS_BODY_KINEMATIC)):
            return []
        return [(cb, sb, guard, int(oneway)) for cb, box in physics_collider_entries(owner, sprite)
                for sb, floor, guard, oneway in floors[support_kind]
                if tags_collide(p.settings, box.tag or "body", floor.tag or "body")]

    support_kinds = sorted(floors)
    bodies = []         # (type, masque des boîtes de corps, [couples par type d'appui])
    for kind in sorted(owners):
        owner, sprite = owners[kind]
        if physics_body_mode(owner) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            continue
        runs = [pairs(owner, sprite, s) for s in support_kinds]
        if any(runs):
            bodies.append((kind, sum(1 << cb for cb in {c for run in runs for c, *_ in run}), runs))
    if not bodies:
        return []

    table: list[str] = []
    run_rows = []
    for _kind, _mask, runs in bodies:
        row = []
        for run in runs:
            row.append(f"{{{len(table)},{len(run)}}}")
            table += [f"{{{cb},{sb},{guard},{oneway}}}" for cb, sb, guard, oneway in run]
        run_rows.append("{" + ",".join(row) + "}")
    body_index = {kind: i for i, (kind, *_rest) in enumerate(bodies)}
    support_index = {kind: i for i, kind in enumerate(support_kinds)}
    pool = any(m["root_type_id"] in floors for m in shared)
    # La taille de l'instantané : les posés d'un type d'appui, puis tout le pool partagé s'il en fait naître. Petit, il
    # reste en IWRAM (.bss) ; au-delà, en EWRAM.
    capacity = sum(1 for kind in lay.placed_type_ids if kind in floors) + (
        shared[0]["spool"]["end"] - shared[0]["spool"]["start"] if pool else 0)
    where = "" if capacity <= _SNAPSHOT_IWRAM else " EWRAM_BSS"
    step = (f"{{ u8 _fi=_fl_bi[_a->type_id]; if(_fi!=255) actors_floor(_a,_fl_mask[_fi],_fl_run[_fi],_fl_list,_fl_n,"
            f"_fl_pair,{0 if dynamic else n}); }}")

    def by_kind(index: dict) -> str:
        return ",".join(str(index.get(k, 255)) for k in range(lay.type_table_size))

    return [
        "    /* Contact au sol final des CharacterBody et RigidBody, par couple de types (corps, appui) */",
        "    {",
        *iwram_table(scene, "_fl_bi", f"        static const u8 _fl_bi[{lay.type_table_size}]={{{by_kind(body_index)}}};"),
        *iwram_table(scene, "_fl_si",
                     f"        static const u8 _fl_si[{lay.type_table_size}]={{{by_kind(support_index)}}};"),
        *iwram_table(scene, "_fl_mask",
                     f"        static const u8 _fl_mask[{len(bodies)}]={{{','.join(str(m) for _k, m, _r in bodies)}}};"),
        *iwram_table(scene, "_fl_run",
                     f"        static const PairRun _fl_run[{len(bodies)}][{len(support_kinds)}]={{{','.join(run_rows)}}};"),
        *iwram_table(scene, "_fl_pair", f"        static const FloorPair _fl_pair[{len(table)}]={{{','.join(table)}}};"),
        f"        static FloorSupport _fl_list[{capacity}]{where};",
        "        int _fl_n=floor_supports(_fl_si,_fl_list);",
        *("    " + line for line in each_slot(step)),
        "    }",
    ]
