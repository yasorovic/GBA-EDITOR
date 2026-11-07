"""Transport des corps posés sur un KinematicBody, et écrasement d'un Character transporté contre un StaticBody.

Plateformes, passagers et murs sont posés ou nés : leurs couples se lisent par TYPE d'emplacement (`Actor.model`). Le
runtime ne demande jamais si un emplacement est posé ou né (règle « posé = spawné »)."""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC,
)
from core.models.settings import tags_collide
from core.models.collision_tiles import ONEWAY_UP
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.model_desc import each_slot, model_desc_sym
from codegen.runtime_codegen.physics.body import (
    physics_body_mode, physics_collider_entries, project_sets_gravity, support_normal,
)
from codegen.runtime_codegen.shared_pool_gen import shared_models

# Les tables sont lues à chaque couple testé : rangées en IWRAM, comme le descripteur de modèle.
_IW = ' __attribute__((section(".data.model_desc")))'
# Au-delà de ce nombre de plateformes possibles, l'instantané d'avant mouvement passe de l'IWRAM à l'EWRAM.
_SNAPSHOT_IWRAM = 32


def project_has_kinematic(p) -> bool:
    owners = [actor for scene in getattr(p, "scenes", []) or [] for actor in scene.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any(physics_body_mode(owner) == PHYSICS_BODY_KINEMATIC for owner in owners)


def kinematic_helper_lines() -> list[str]:
    """Aides C : le transport d'un passager par une plateforme, la passe de toutes les plateformes, l'écrasement."""
    return [
        "/* Le passager repose sur la face de la plateforme qui regarde la gravité, telle qu'elle était AVANT son",
        "   déplacement, et ne s'en éloigne pas (vitesse de sens contraire) ; il reçoit une seule fois le déplacement réel",
        "   de la plateforme. Côté d'appui `n` : 1 bas, 2 haut, 3 droite, 4 gauche. */",
        "static inline __attribute__((always_inline, unused)) void kinematic_carry_n(Actor* k,Actor* a,u8 kb,u8 ab,",
        "        int old_x,int old_y,u8* carried,int* carry_x,int* carry_y,u8 n){",
        "    if(*carried||!k->active||!a->active||kb>=k->collision.box_count||ab>=a->collision.box_count) return;",
        "    const CollisionShape* p=&k->collision.boxes[kb]; const CollisionShape* b=&a->collision.boxes[ab];",
        "    if(!p->active||!b->active) return;",
        "    int dx=k->x-old_x,dy=k->y-old_y; if(!dx&&!dy) return;",
        "    int pl=(old_x>>8)+p->x,pr=pl+p->w,pt=(old_y>>8)+p->y,pb=pt+p->h;",
        "    int al=(a->x>>8)+b->x,ar=al+b->w,at=(a->y>>8)+b->y,abt=at+b->h;",
        "    int rests;",
        "    if(n==1) rests=abt==pt&&al<pr&&ar>pl&&a->vy>=0;",
        "    else if(n==2) rests=at==pb&&al<pr&&ar>pl&&a->vy<=0;",
        "    else if(n==3) rests=ar==pl&&at<pb&&abt>pt&&a->vx>=0;",
        "    else rests=al==pr&&at<pb&&abt>pt&&a->vx<=0;",
        "    if(!rests) return;",
        "    a->x+=dx; a->y+=dy; *carry_x+=dx; *carry_y+=dy; *carried=1;",
        "}",
        "/* Un couple de boîtes (plateforme, passager) ou (corps, mur) d'un couple de types. */",
        "typedef struct { u8 box_a, box_b; } BoxPair;",
        "/* L'instantané des plateformes, relevé AVANT le mouvement : emplacement, rang compact de son type, position. */",
        "typedef struct { u16 slot; u8 kind; u8 pad; int x, y; } CarryPlatform;",
        "static inline __attribute__((always_inline)) void kinematic_platform_add(int s,const u8* pi,CarryPlatform* out,int* n){",
        "    const Actor* k=&g_actors[s]; u8 j=pi[k->model];",
        "    if(j==255||!k->active) return;",
        "    CarryPlatform* c=&out[(*n)++]; c->slot=s; c->kind=j; c->x=k->x; c->y=k->y;",
        "}",
        "static int __attribute__((unused)) kinematic_platforms(const u8* pi,CarryPlatform* out){",
        "    int n=0;",
        "    SLOT_EACH(s) kinematic_platform_add(s,pi,out,&n);",
        "    return n;",
        "}",
        "/* La liste des passagers possibles de l'image : emplacement et rang compact de son type, sans position (un",
        "   passager porté par une plateforme bouge avant que la suivante le teste). */",
        "typedef struct { u16 slot; u8 kind; u8 pad; } CarryRider;",
        "static inline __attribute__((always_inline)) void kinematic_rider_add(int s,const u8* ri,CarryRider* out,int* n){",
        "    const Actor* a=&g_actors[s]; u8 j=ri[a->model];",
        "    if(j==255||!a->active) return;",
        "    CarryRider* r=&out[(*n)++]; r->slot=s; r->kind=j;",
        "}",
        "static int __attribute__((unused)) kinematic_riders(const u8* ri,CarryRider* out){",
        "    int n=0;",
        "    SLOT_EACH(s) kinematic_rider_add(s,ri,out,&n);",
        "    return n;",
        "}",
        "/* Le transport de l'image : chaque plateforme qui a bougé, puis chaque passager de la liste (ordre des",
        "   emplacements). `runs` : `width` entrées par type de plateforme, indexées par le rang compact du type",
        "   du passager. `kin_d` reçoit le déplacement porté de chaque emplacement. `normal` : le côté d'appui de la",
        "   scène, 0 = lu dans `g_support_normal`. En IWRAM, ARM. */",
        "BS_ATTR_IWRAM",
        "static void __attribute__((unused)) kinematic_carry_all(const CarryPlatform* list,int count,const PairRun* runs,",
        "        int width,const CarryRider* riders,int nr,const BoxPair* pairs,int (*kin_d)[3],u8 normal){",
        "    u8 side=normal?normal:g_support_normal;",
        "    for(int i=0;i<count;i++){",
        "        const CarryPlatform* c=&list[i]; Actor* k=&g_actors[c->slot];",
        "        if(!k->active||(k->x==c->x&&k->y==c->y)) continue;",
        "        const PairRun* row=runs+c->kind*width;",
        "        for(int r=0;r<nr;r++){",
        "            const PairRun* run=&row[riders[r].kind]; int s=riders[r].slot;",
        "            if(!run->n||s==c->slot) continue;",
        "            Actor* a=&g_actors[s]; u8 carried=0; const BoxPair* p=pairs+run->first;",
        "            for(int q=0;q<run->n;q++)",
        "                kinematic_carry_n(k,a,p[q].box_a,p[q].box_b,c->x,c->y,&carried,&kin_d[s][0],&kin_d[s][1],side);",
        "        }",
        "    }",
        "}",
        "/* L'écrasement : un Character transporté (déplacement porté non nul, pas encore signalé) dont une boîte de corps",
        "   recouvre un mur d'un StaticBody appelle le `on_crushed` de son type (descripteur), une fois par image. Les",
        "   murs : tous les emplacements vivants (`SLOT_EACH`), rang compact de leur type dans `wi`. */",
        "static inline __attribute__((always_inline)) int kinematic_crush_one(Actor* a,u8 cb,int s,const PairRun* row,",
        "        const u8* wi,const BoxPair* pairs){",
        "    const Actor* w=&g_actors[s]; u8 j=wi[w->model];",
        "    if(j==255||!w->active||!row[j].n) return 0;",
        "    const BoxPair* p=pairs+row[j].first;",
        "    for(int q=0;q<row[j].n;q++){",
        "        if(p[q].box_a!=cb||p[q].box_b>=w->collision.box_count) continue;",
        "        const CollisionShape* ab=&a->collision.boxes[cb]; const CollisionShape* wb=&w->collision.boxes[p[q].box_b];",
        "        if(!wb->active) continue;",
        "        int al=(a->x>>8)+ab->x,at=(a->y>>8)+ab->y,wl=(w->x>>8)+wb->x,wt=(w->y>>8)+wb->y;",
        "        if(al<wl+wb->w&&al+ab->w>wl&&at<wt+wb->h&&at+ab->h>wt) return 1;",
        "    }",
        "    return 0;",
        "}",
        "static void __attribute__((unused)) kinematic_crush(Actor* a,const ModelDesc* d,u8 mask,const PairRun* row,",
        "        const u8* wi,const BoxPair* pairs,int* kin_d){",
        "    if(!d->on_crushed||kin_d[2]||(!kin_d[0]&&!kin_d[1])) return;",
        "    for(int cb=0;cb<a->collision.box_count;cb++){",
        "        if(!(mask&(1u<<cb))||!a->collision.boxes[cb].active) continue;",
        "        SLOT_EACH(s)",
        "            if(kinematic_crush_one(a,cb,s,row,wi,pairs)){ d->on_crushed(a,&g_actors[s]); kin_d[2]=1; return; }",
        "    }",
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


def _carry_pairs(p, kinematic, kinematic_sprite, target, target_sprite) -> list[tuple[int, int]]:
    """Les couples (rang de la boîte de la plateforme, rang de celle du passager) qui peuvent se porter."""
    if physics_body_mode(target) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
        return []
    return [(kb, ab) for kb, kbox in _block_boxes(kinematic, kinematic_sprite)
            for ab, abox in _body_boxes(target, target_sprite)
            if tags_collide(p.settings, kbox.tag or "body", abox.tag or "body")]


def _crush_pairs(p, character, character_sprite, wall, wall_sprite) -> list[tuple[int, int]]:
    """Les couples (boîte de corps du Character, boîte du StaticBody) qui peuvent le coincer."""
    if physics_body_mode(character) != PHYSICS_BODY_CHARACTER or physics_body_mode(wall) != PHYSICS_BODY_STATIC:
        return []
    return [(cb, sb) for cb, cbox in _body_boxes(character, character_sprite)
            for sb, sbox in _block_boxes(wall, wall_sprite)
            if tags_collide(p.settings, cbox.tag or "body", sbox.tag or "body")]


def _pair_table(owners: dict, pairs_of, prefix: str) -> tuple[dict, dict, list[str], int] | None:
    """La table d'un module de paires entre types : (rang compact des types « a », rang compact des types « b », lignes C
    des `PairRun` et des `BoxPair`, largeur d'une ligne), ou None sans aucun couple."""
    kinds = sorted(owners)
    rows = {a: [pairs_of(owners[a], owners[b]) for b in kinds] for a in kinds}
    a_kinds = [a for a in kinds if any(rows[a])]
    b_kinds = [b for i, b in enumerate(kinds) if any(rows[a][i] for a in a_kinds)]
    if not a_kinds:
        return None
    flat: list[tuple[int, int]] = []
    run_rows = []
    for a in a_kinds:
        row = []
        for b in b_kinds:
            run = rows[a][kinds.index(b)]
            row.append(f"{{{len(flat)},{len(run)}}}")
            flat += run
        run_rows.append("{" + ",".join(row) + "}")
    lines = [f"    static PairRun {prefix}_run[{len(a_kinds)}][{len(b_kinds)}]{_IW}={{{','.join(run_rows)}}};",
             f"    static BoxPair {prefix}_pair[{len(flat)}]{_IW}={{{','.join(f'{{{x},{y}}}' for x, y in flat)}}};"]
    return {k: i for i, k in enumerate(a_kinds)}, {k: i for i, k in enumerate(b_kinds)}, lines, len(b_kinds)


def kinematic_tick_parts(
        p, scene_actors, scene=None, pi=(), shown=None,
) -> tuple[list[str], list[str], list[str]]:
    """L'instantané des plateformes avant le mouvement, le transport après la résolution, puis l'écrasement contre un
    StaticBody.

    Le passager repose sur la face de la plateforme qui regarde la gravité de la scène (`support_normal`) : le dessus
    sous la gravité habituelle, le dessous sous une gravité vers le haut, un côté sous une gravité latérale.

    Le déplacement porté vit dans `_kin_d`, une ligne par emplacement de `g_actors` (x, y, puis l'écrasement déjà
    signalé), remise à zéro à chaque image pour tous les emplacements vivants : la résolution contre la
    carte l'ajoute à la vitesse de l'emplacement, quel qu'il soit (`physics.character.body_tile_step`)."""
    normal = support_normal(scene, p.settings) if scene is not None else ONEWAY_UP
    # Un script écrit `scene.gravity` : le côté d'appui se lit à l'exécution, quel que soit celui du départ.
    dynamic = project_sets_gravity(p)
    lay = scene_oam_layout(p, scene)
    shared = shared_models(pi) if shown else []
    owners: dict[int, tuple] = {}       # type -> (porteur, sprite) ; les copies d'un type ont les mêmes rôles de boîtes
    for (actor, sprite), kind in zip(scene_actors, lay.placed_model):
        owners.setdefault(kind, (actor, sprite))
    for m in shared:
        owners.setdefault(m["model_id"], (m["prefab"], shown(p, m["prefab"])[1]))

    carry = _pair_table(owners, lambda a, b: _carry_pairs(p, a[0], a[1], b[0], b[1])
                        if physics_body_mode(a[0]) == PHYSICS_BODY_KINEMATIC else [], "_kin")
    if carry is None:
        return [], [], []
    platform_index, rider_index, carry_lines, width = carry
    spool = shared[0]["spool"]["end"] - shared[0]["spool"]["start"] if shared else 0

    def capacity_of(kinds: dict) -> int:
        """La taille d'une liste d'instantané : les posés de ces types, puis tout le pool s'il en fait naître."""
        return (sum(1 for kind in lay.placed_model if kind in kinds)
                + (spool if any(m["model_id"] in kinds for m in shared) else 0))

    def by_kind(index: dict) -> str:
        return ",".join(str(index.get(k, 255)) for k in range(lay.kinds))

    capacity = capacity_of(platform_index)
    where = "" if capacity <= _SNAPSHOT_IWRAM else " EWRAM_BSS"
    before = ["    /* Transport : les plateformes et leur position d'avant mouvement, par couple de types */",
              f"    static u8 _kin_pi[{lay.kinds}]{_IW}={{{by_kind(platform_index)}}};",
              f"    static u8 _kin_ri[{lay.kinds}]{_IW}={{{by_kind(rider_index)}}};",
              *carry_lines,
              f"    static CarryPlatform _kin_list[{capacity}]{where};",
              "    int _kin_n=kinematic_platforms(_kin_pi,_kin_list);"]

    after = ["    static int _kin_d[G_ACTOR_COUNT][3] EWRAM_BSS;   /* déplacement porté et écrasement, par emplacement */"]
    after.append("    SLOT_EACH(_kz) _kin_d[_kz][0]=_kin_d[_kz][1]=_kin_d[_kz][2]=0;")
    riders = capacity_of(rider_index)
    where_r = "" if riders <= _SNAPSHOT_IWRAM else " EWRAM_BSS"
    after += [f"    static CarryRider _kin_riders[{riders}]{where_r};",
              "    int _kin_nr=kinematic_riders(_kin_ri,_kin_riders);",
              f"    kinematic_carry_all(_kin_list,_kin_n,&_kin_run[0][0],{width},_kin_riders,_kin_nr,_kin_pair,_kin_d,"
              f"{0 if dynamic else normal});"]

    crush = _pair_table(owners, lambda a, b: _crush_pairs(p, a[0], a[1], b[0], b[1]), "_kc")
    crush_lines: list[str] = []
    if crush is not None:
        body_index, wall_index, table, _width = crush
        masks = {kind: sum(1 << cb for cb, _box in _body_boxes(*owners[kind])) for kind in body_index}
        step = (f"{{ u8 _ci=_kc_ci[_a->model]; if(_ci!=255) kinematic_crush(_a,&{model_desc_sym(scene)}[_a->model],"
                "_kc_mask[_ci],_kc_run[_ci],_kc_wi,_kc_pair,_kin_d[_a->inst]); }")
        crush_lines = [
            "    /* L'écrasement d'un Character transporté contre un StaticBody (la carte, elle, écrase par",
            "       `body_tile_step`) : `_kin_d[i][2]` retient qu'il est signalé, pour ne pas le refaire à la carte. */",
            "    {",
            f"        static u8 _kc_ci[{lay.kinds}]{_IW}={{{by_kind(body_index)}}};",
            f"        static u8 _kc_wi[{lay.kinds}]{_IW}={{{by_kind(wall_index)}}};",
            f"        static u8 _kc_mask[{len(body_index)}]{_IW}={{{','.join(str(masks[k]) for k in body_index)}}};",
            *("    " + line for line in table),
            *("    " + line for line in each_slot(step)),
            "    }",
        ]
    return before, after, crush_lines
