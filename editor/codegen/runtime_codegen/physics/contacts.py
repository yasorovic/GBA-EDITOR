"""Les contacts entre acteurs (`on_collision_enter`, `on_collide`, `on_collision_exit`), posés ou nés.

Un contact est un couple de tags de boîtes qui se recouvrent entre deux acteurs (`actors_overlap_mask`). Les couples
autorisés se lisent par couple de TYPES d'emplacement (`Actor.type_id`), cuits au build par la matrice des tags ; les
crochets, dans le descripteur de modèle (`ModelDesc.on_contact`). Le runtime relève une fois par image l'instantané des
acteurs concernés, écarte les paires dont les rectangles ne se touchent pas, et compare la liste des contacts de l'image
à celle de l'image précédente : un contact qui naît appelle enter, un qui dure collide, un qui se défait exit. Il ne
demande jamais si un emplacement est posé ou né (règle « posé = spawné »).

La liste a une capacité (`CONTACT_CAPACITY`, réduite au nombre de paires possibles de la scène). Les contacts
déjà suivis restent prioritaires tant qu'ils durent ; au-delà de la capacité, les nouveaux attendent. Un emplacement réoccupé (`Actor.gen`) repart de zéro, sans exit pour l'ancien
occupant ; un acteur détruit n'apprend rien et son partenaire non plus ; un acteur désactivé perd ses contacts et seul
le partenaire resté actif apprend exit.
"""
from __future__ import annotations

from codegen.iwram_plan import iwram_table
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_scene_query import collision_pair_mask, has_col_event
from codegen.runtime_codegen.model_desc import model_desc_sym
from codegen.runtime_codegen.shared_pool_gen import owners as model_owners, shared_models

# Les contacts suivis à la fois, au plus, dans une scène.
CONTACT_CAPACITY = 128
# Au-delà de ce nombre d'acteurs possibles (14 octets chacun), l'instantané passe de l'IWRAM à l'EWRAM.
_SNAPSHOT_IWRAM = 64


def contact_helper_lines() -> list[str]:
    """Aides C : l'instantané des acteurs concernés, la liste des contacts de l'image et ses événements."""
    return [
        "/* L'instantané d'un acteur concerné par les contacts : emplacement, rang compact de son type, génération (un",
        "   emplacement réoccupé repart de zéro) et rectangle monde de ses boîtes actives. */",
        "typedef struct { u16 slot; u8 kind; u8 pad; u16 gen; s16 l, t, r, b; } ContactBody;",
        "/* Un contact en cours entre deux emplacements (`a` < `b`) : leurs générations et un bit par couple de tags. */",
        "typedef struct { u16 a, b, gen_a, gen_b, mask; } Contact;",
        "static inline __attribute__((always_inline)) void contact_body_add(int s,const u8* ki,ContactBody* out,int* n){",
        "    const Actor* a=&g_actors[s]; u8 j=ki[a->type_id];",
        "    if(j==255||!a->active) return;",
        "    int l=32767,top=32767,r=-32768,b=-32768,x=a->x>>8,y=a->y>>8;",
        "    for(int k=0;k<a->collision.box_count;k++){",
        "        const CollisionShape* c=&a->collision.boxes[k];",
        "        if(!c->active) continue;",
        "        if(x+c->x<l) l=x+c->x; if(y+c->y<top) top=y+c->y;",
        "        if(x+c->x+c->w>r) r=x+c->x+c->w; if(y+c->y+c->h>b) b=y+c->y+c->h;",
        "    }",
        "    if(r<l) return;",
        "    ContactBody* e=&out[(*n)++]; e->slot=s; e->kind=j; e->gen=a->gen; e->l=l; e->t=top; e->r=r; e->b=b;",
        "}",
        "static inline int contact_occupants_match(const Contact* c,const Actor* a,const Actor* b){",
        "    return a->alive&&b->alive&&a->gen==c->gen_a&&b->gen==c->gen_b;",
        "}",
        "/* Les événements d'une paire, d'une image à l'autre : `prv` et `cur`, un bit par couple de tags (cf.",
        "   `actors_overlap_mask`). Un détruit n'apprend rien et son partenaire non plus ; un désactivé n'apprend pas exit. */",
        "static void __attribute__((unused)) contact_events(const ModelDesc* desc,const Contact* c,u16 prv,u16 cur){",
        "    Actor* a=&g_actors[c->a]; Actor* b=&g_actors[c->b];",
        "    if(!contact_occupants_match(c,a,b)) return;",
        "    for(u8 bi=0;bi<MAX_BOXES;bi++) for(u8 bj=0;bj<MAX_BOXES;bj++){",
        "        u16 m=(u16)(1u<<(bi*MAX_BOXES+bj));",
        "        u8 now=(cur&m)!=0, was=(prv&m)!=0;",
        "        if(!now&&!was) continue;",
        "        u8 event=now?(was?1:0):2;            /* enter : naît ; collide : dure ; exit : se défait */",
        "        u8 ta=a->collision.boxes[bi].tag, tb=b->collision.boxes[bj].tag;",
        "        void (*fa)(Actor*,Actor*,u8,u8)=desc[a->type_id].on_contact[event];",
        "        void (*fb)(Actor*,Actor*,u8,u8)=desc[b->type_id].on_contact[event];",
        "        if(fa&&(event!=2||a->active)){",
        "            fa(a,b,ta,tb);",
        "            if(!contact_occupants_match(c,a,b)) return;",
        "        }",
        "        if(fb&&(event!=2||b->active)){",
        "            fb(b,a,tb,ta);",
        "            if(!contact_occupants_match(c,a,b)) return;",
        "        }",
        "    }",
        "}",
        "static inline u32 contact_key(const Contact* c){ return ((u32)c->a<<16)|c->b; }",
        "/* Collecte en ordre d'emplacements. Au-delà de cap, le premier vrai recouvrement signale la saturation. */",
        "BS_ATTR_IWRAM",
        "static int contact_collect(const ContactBody* list,int n,const u16* allowed,int width,",
        "        Contact* cur,int kept,int cap){",
        "    int cn=kept, k=0;",
        "    for(int i=0;i<n;i++){",
        "        const ContactBody* A=&list[i]; const u16* row=allowed+A->kind*width;",
        "        for(int j=i+1;j<n;j++){",
        "            const ContactBody* B=&list[j]; u16 al=row[B->kind];",
        "            if(!al||A->l>=B->r||A->r<=B->l||A->t>=B->b||A->b<=B->t) continue;",
        "            if(k<kept){",
        "                u32 key=((u32)A->slot<<16)|B->slot;",
        "                while(k<kept&&contact_key(&cur[k])<key) k++;",
        "                if(k<kept&&contact_key(&cur[k])==key) continue;",
        "            }",
        "            debug_physics_contact_test();",
        "            u16 m=actors_overlap_mask(&g_actors[A->slot],&g_actors[B->slot],al);",
        "            if(!m) continue;",
        "            if(cn==cap) return cap+1;",
        "            cur[cn++]=(Contact){A->slot,B->slot,A->gen,B->gen,m};",
        "        }",
        "    }",
        "    return cn;",
        "}",
        "/* Quand la liste est pleine, réserver d'abord la place des contacts encore actifs. */",
        "static int contact_retain(const Contact* prev,int pn,Contact* cur,const u8* ki,const u16* allowed,int width){",
        "    int kept=0;",
        "    for(int i=0;i<pn;i++){",
        "        const Contact* c=&prev[i]; Actor* a=&g_actors[c->a]; Actor* b=&g_actors[c->b];",
        "        if(!contact_occupants_match(c,a,b)||!a->active||!b->active) continue;",
        "        u8 ai=ki[a->type_id], bi=ki[b->type_id];",
        "        if(ai==255||bi==255) continue;",
        "        u16 al=allowed[ai*width+bi];",
        "        if(!al) continue;",
        "        debug_physics_contact_test();",
        "        u16 mask=actors_overlap_mask(a,b,al);",
        "        if(mask){ cur[kept]=*c; cur[kept++].mask=mask; }",
        "    }",
        "    return kept;",
        "}",
        "/* Fusion sur place des deux suites triées, limitée à cap contacts et au cas saturé. */",
        "static void contact_merge_retained(Contact* cur,int kept,int cn){",
        "    for(int i=kept;i<cn;i++){",
        "        Contact c=cur[i]; int j=i;",
        "        while(j>0&&contact_key(&cur[j-1])>contact_key(&c)){ cur[j]=cur[j-1]; j--; }",
        "        cur[j]=c;",
        "    }",
        "}",
        "static void __attribute__((unused)) contacts_run(const ModelDesc* desc,const u8* ki,const u16* allowed,int width,",
        "        ContactBody* list,Contact* prev,int* prev_n,Contact* cur,int cap){",
        "    int n=0, pn=*prev_n;",
        "    SLOT_EACH(s) contact_body_add(s,ki,list,&n);",
        "    int kept=pn==cap?contact_retain(prev,pn,cur,ki,allowed,width):0;",
        "    int cn=contact_collect(list,n,allowed,width,cur,kept,cap);",
        "    if(cn>cap){",
        "        debug_physics_contact_overflow();",
        "        if(pn&&pn<cap){",
        "            kept=contact_retain(prev,pn,cur,ki,allowed,width);",
        "            cn=contact_collect(list,n,allowed,width,cur,kept,cap);",
        "        }",
        "        if(cn>cap) cn=cap;",
        "    }",
        "    if(kept&&kept<cn) contact_merge_retained(cur,kept,cn);",
        "    int p=0, q=0;",
        "    while(p<pn||q<cn){",
        "        u32 kp=p<pn?contact_key(&prev[p]):0xFFFFFFFFu, kc=q<cn?contact_key(&cur[q]):0xFFFFFFFFu;",
        "        if(kp<kc){                          /* le contact s'est défait (ou un emplacement a changé d'occupant) */",
        "            const Contact* c=&prev[p++];",
        "            contact_events(desc,c,c->mask,0);",
        "        } else {",
        "            const Contact* c=&cur[q++]; u16 was=0;",
        "            if(kp==kc){ const Contact* o=&prev[p++]; if(o->gen_a==c->gen_a&&o->gen_b==c->gen_b) was=o->mask; }",
        "            contact_events(desc,c,was,c->mask);",
        "        }",
        "    }",
        "    for(int k=0;k<cn;k++) prev[k]=cur[k];",
        "    *prev_n=cn;",
        "}",
        "",
    ]


def contact_tick_lines(p, scene, scene_actors, pi, resolve_initial_appearance, placed_scripts, has_event) -> list[str]:
    """La passe de contacts de la scène, ou rien si aucun couple de types n'a de contact qui prévient un script.

    `placed_scripts` : le symbole du code Lua de chaque posé (None sans script), aligné sur `scene_actors` ; un modèle
    du pool a le sien. `has_event(symbole, événement)` dit si le script définit le crochet."""
    lay = scene_oam_layout(p, scene)
    shared = shared_models(pi) if resolve_initial_appearance else []
    owners: dict[int, object] = {}      # type -> porteur ; les copies d'un type ont les mêmes boîtes et le même code
    reacts: dict[int, bool] = {}        # type -> son script répond à un contact
    for (actor, _sprite), kind, script in zip(scene_actors, lay.placed_type_ids, placed_scripts):
        owners.setdefault(kind, actor)
        reacts[kind] = reacts.get(kind, False) or bool(script and has_col_event(has_event, script))
    for m in shared:
        # Une partie (`root_type_id + k`) a ses propres boîtes et réagit avec le script de sa racine.
        for k, owner in enumerate(model_owners(m)[:m["group"]]):
            owners.setdefault(m["root_type_id"] + k, owner)
            reacts[m["root_type_id"] + k] = reacts.get(m["root_type_id"] + k, False) or has_col_event(has_event, m["sym"])
    kinds = sorted(owners)
    allowed = {(a, b): collision_pair_mask(owners[a], owners[b], p.settings) if reacts[a] or reacts[b] else 0
               for a in kinds for b in kinds}
    bodies = [k for k in kinds if any(allowed[(k, o)] or allowed[(o, k)] for o in kinds)]
    if not bodies:
        return []
    index = {k: i for i, k in enumerate(bodies)}
    pool = any(m["root_type_id"] + k in index for m in shared for k in range(m["group"]))
    spool = shared[0]["spool"]["end"] - shared[0]["spool"]["start"] if pool else 0
    capacity = sum(1 for kind in lay.placed_type_ids if kind in index) + spool
    cap = max(1, min(CONTACT_CAPACITY, capacity * (capacity - 1) // 2))
    where = "" if capacity <= _SNAPSHOT_IWRAM else " EWRAM_BSS"
    rows = ",".join("{" + ",".join(str(allowed[(a, b)]) for b in bodies) + "}" for a in bodies)
    by_kind = ",".join(str(index.get(k, 255)) for k in range(lay.type_table_size))
    return [
        "    /* Contacts entre acteurs, par couple de types : enter, collide, exit (crochets lus au descripteur) */",
        "    {",
        *iwram_table(scene, "_ct_type_to_index",
                     f"        static const u8 _ct_type_to_index[{lay.type_table_size}]={{{by_kind}}};"),
        *iwram_table(scene, "_ct_allowed",
                     f"        static const u16 _ct_allowed[{len(bodies)}][{len(bodies)}]={{{rows}}};"),
        f"        static ContactBody _ct_list[{capacity}]{where};",
        f"        static Contact _ct_prev[{cap}] EWRAM_BSS, _ct_cur[{cap}] EWRAM_BSS;",
        "        static int _ct_prev_n;",
        f"        contacts_run({model_desc_sym(scene)},_ct_type_to_index,&_ct_allowed[0][0],{len(bodies)},_ct_list,_ct_prev,"
        f"&_ct_prev_n,_ct_cur,{cap});",
        "    }",
    ]
