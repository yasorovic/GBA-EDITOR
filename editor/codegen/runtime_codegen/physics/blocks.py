"""Le blocage entre acteurs, côté C : une boîte de réponse `block` arrête les acteurs en mouvement.

Un MOBILE est un acteur actif dont la vitesse n'est pas nulle (le critère de la résolution contre la
carte : l'acteur déplacé par `body.velocity` est « conduit », un acteur téléporté ne l'est pas) et qui
porte une box `solid`. Un BLOQUEUR est une box de réponse `block` d'un autre acteur. Le mobile est repoussé
hors de la box qu'il recouvre sur l'axe de plus faible pénétration, et sa vitesse est annulée sur cet axe ;
il glisse donc le long d'un obstacle quand il le heurte en diagonale. Exception : un bloqueur KINEMATIC en mouvement
pousse aussi un acteur immobile, dès le premier pixel de recouvrement ; sans cela la plateforme glisserait sur lui, et
au premier pas du joueur le recouvrement serait déjà plus profond que sa boîte de pieds : l'axe vertical l'emporterait
et le joueur serait enfoncé dans le sol.

Émis AVANT la résolution contre la carte : les murs ont le dernier mot, le mobile ne peut pas être poussé
dans un mur. La matrice de collision filtre au build (un couple de tags qui ne se rencontrent pas se
traverse). Rien n'est émis sans mobile ni bloqueur ; les aides C ne le sont que si le projet a une box
bloquante.

Posés et nés passent par le même chemin : les tables sont indexées par TYPE d'emplacement (`Actor.type_id`), et l'aide
C parcourt les emplacements vivants de la scène (`SLOT_EACH`).
"""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC, CollisionShapeComponent,
)
from core.models.settings import tags_collide
from codegen.iwram_plan import iwram_table
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body_mode, physics_collider_entries,
    physics_collider_mask, shape_one_way_dir, uses_body_collider, uses_character_solver,
)
from codegen.runtime_codegen.physics.oneway import oneway_common_lines
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_scene_query import scene_has_cmap
from codegen.runtime_codegen.model_desc import each_slot
from codegen.runtime_codegen.shared_pool_gen import shared_models


# Bit haut du rang de boîte d'un bloqueur dans les tables C : un bloqueur Kinematic en mouvement pousse un mobile même
# immobile, les autres (Static, Rigid, Character) ne repoussent qu'un mobile en mouvement. Le rang tient dans les 7 bits bas.
BLOCKER_MOVING = 0x80

# Au-delà de ce nombre de bloqueurs possibles (4 octets chacun), la liste de l'image passe de l'IWRAM à l'EWRAM.
_LIST_IWRAM = 128


def project_has_blockers(p) -> bool:
    """Une boîte bloquante quelque part : celle d'un auteur, ou la boîte propre d'un Interactive en
    `facing` (un obstacle par défaut)."""
    from core.models.components import InteractiveComponent
    owners = [a for sc in getattr(p, "scenes", []) or [] for a in sc.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any((isinstance(c, CollisionShapeComponent) and c.active and c.response == COLLISION_RESPONSE_BLOCK)
               or (isinstance(c, InteractiveComponent) and c.active and c.interaction == "facing"
                   and not c.box_tag)
               for o in owners for c in getattr(o, "components", []))


def block_helper_lines(one_way: bool = False) -> list[str]:
    """L'aide C, pure : ne dépend que d'`Actor` et de `g_actors` (et de `g_drop_through` avec `one_way`)."""
    return _block_lines() + (_one_way_block_lines() if one_way else [])


def _one_way_block_lines() -> list[str]:
    """Les faces à sens unique : variantes des deux boucles de blocage qui lisent, pour chaque bloqueur, le sens de
    sa face (`ow[k]` : 0 aucun, 1 haut, 2 bas, 3 gauche, 4 droite)."""
    return [
        *oneway_common_lines(),
        "/* ── Face à sens unique : n'arrête un mobile que s'il était ENTIÈREMENT du côté de la normale avant le",
        "   déplacement de cette frame, pour lui comme pour le porteur de la face (une plateforme Kinematic qui",
        "   monte le porte). Il est repoussé le long de la normale seule : jamais de côté, la pénétration minimale",
        "   n'a pas de sens pour une face qu'on franchit. `dir` : 1 haut, 2 bas, 3 gauche, 4 droite. */",
        "extern u8 *g_drop_through;",
        "static inline __attribute__((always_inline, unused)) void block_push_one_way(Actor* a,const CollisionShape* m,const Actor* t,const CollisionShape* b,u8 dir){",
        "    int ml=(a->x>>8)+m->x, mt=(a->y>>8)+m->y, mr=ml+m->w, mb=mt+m->h;",
        "    int bl=(t->x>>8)+b->x, bt=(t->y>>8)+b->y, br=bl+b->w, bb=bt+b->h;",
        "    if(ml>=br||mr<=bl||mt>=bb||mb<=bt) return;",
        "    int ol=((a->x-a->vx)>>8)+m->x, ot=((a->y-a->vy)>>8)+m->y;",
        "    int pl=((t->x-t->vx)>>8)+b->x, pt=((t->y-t->vy)>>8)+b->y;",
        "    if(!oneway_open(dir,oneway_edge(dir,ol,ot,ol+m->w,ot+m->h),oneway_face(dir,pl,pt,pl+b->w,pt+b->h))) return;",
        "    int d=oneway_face(dir,bl,bt,br,bb)-oneway_edge(dir,ml,mt,mr,mb);   /* met le bord de la boîte sur la face */",
        "    if(dir<=2){ a->y+=d<<8; if(dir&1?a->vy>0:a->vy<0) a->vy=0; }",
        "    else { a->x+=d<<8; if(dir&1?a->vx>0:a->vx<0) a->vx=0; }",
        "}",
        "/* `drop_through` : tant que le compteur du mobile n'est pas nul, ses faces à sens unique sont ignorées. */",
        *_typed_lines(one_way=True),
    ]


def _block_lines() -> list[str]:
    return [
        "/* ── Blocage entre acteurs : repousser un mobile hors des boîtes qui bloquent ───────",
        "   `idx[k]` / `box[k]` : l'acteur et le rang de la k-ième boîte bloquante. Un mobile (actif, vitesse",
        "   non nulle) est repoussé, pour chacune de ses boîtes de carte, de la pénétration minimale, sur",
        "   l'axe le plus court (l'horizontal en cas d'égalité). La position garde sa fraction (Q8) et la",
        "   composante de vitesse sur cet axe est annulée. */",
        "static inline __attribute__((always_inline, unused)) void block_push(Actor* a,const CollisionShape* m,const Actor* t,const CollisionShape* b){",
        "    int ml=(a->x>>8)+m->x, mt=(a->y>>8)+m->y, mr=ml+m->w, mb=mt+m->h;",
        "    int bl=(t->x>>8)+b->x, bt=(t->y>>8)+b->y, br=bl+b->w, bb=bt+b->h;",
        "    if(ml>=br||mr<=bl||mt>=bb||mb<=bt) return;",
        "    int left=mr-bl, right=br-ml, up=mb-bt, down=bb-mt;",
        "    int px=left<right?-left:right, py=up<down?-up:down;",
        "    int apx=px<0?-px:px, apy=py<0?-py:py;",
        "    if(apx<=apy){ a->x+=px<<8; a->vx=0; }",
        "    else { a->y+=py<<8; a->vy=0; }",
        "}",
        "/* Les boîtes qui peuvent arrêter un mobile se lisent par COUPLE DE TYPES (`Actor.type_id`), que le mobile et le",
        "   bloqueur soient posés ou nés : un `PairRun` (actor_types_static.h) désigne, dans `box` (rang, bit haut",
        "   BLOCKER_MOVING), la suite des boîtes bloquantes du type du bloqueur que ce type de mobile rencontre. */",
        "/* La liste des bloqueurs de l'image, relevée avant la passe : emplacement et rang compact de son type, dans",
        "   l'ordre des emplacements. Sans position : un mobile qui est aussi un bloqueur bouge pendant la passe, ses",
        "   boîtes se relisent en direct. Elle évite de relire le type de chaque emplacement pour chaque mobile. */",
        "typedef struct { u16 slot; u8 kind; u8 pad; } BlockTarget;",
        "static inline __attribute__((always_inline)) void block_target_add(int s,const u8* bi,BlockTarget* out,int* n){",
        "    const Actor* t=&g_actors[s]; u8 j=bi[t->type_id];",
        "    if(j==255||!t->active) return;",
        "    BlockTarget* e=&out[(*n)++]; e->slot=s; e->kind=j;",
        "}",
        "static int __attribute__((unused)) block_targets(const u8* bi,BlockTarget* out){",
        "    int n=0;",
        "    SLOT_EACH(s) block_target_add(s,bi,out,&n);",
        "    return n;",
        "}",
        *_typed_lines(one_way=False),
    ]


def _typed_lines(one_way: bool) -> list[str]:
    """Le blocage d'un mobile contre les bloqueurs de la liste de l'image (`list`, `n`), chaque boîte du mobile à son
    tour. `runs` est la ligne du type du mobile, indexée par le rang compact du type du bloqueur."""
    sfx = "_ow" if one_way else ""
    ow_param = ",const u8* ow" if one_way else ""
    ow_arg = ",ow+run->first" if one_way else ""
    push = (["            if(!ow[k]) block_push(a,m,t,b);",
             "            else if(!drop) block_push_one_way(a,m,t,b,ow[k]);"]
            if one_way else ["            block_push(a,m,t,b);"])
    target = [
        "            const Actor* t=&g_actors[list[k].slot]; const PairRun* run=&runs[list[k].kind];",
        "            if(t==a||!run->n) continue;",
        f"            block_run{sfx}(a,m,t,box+run->first{ow_arg},run->n,idle"
        f"{',drop' if one_way else ''});",
    ]
    return [
        f"static inline __attribute__((always_inline)) void block_run{sfx}(Actor* a,const CollisionShape* m,"
        f"const Actor* t,const u8* box{ow_param},u8 n,int idle{',int drop' if one_way else ''}){{",
        "    for(int k=0;k<n;k++){",
        "        if((box[k]&0x7F)>=t->collision.box_count) continue;",
        "        if(idle&&!((box[k]&0x80)&&(t->vx||t->vy))) continue;",
        "        const CollisionShape* b=&t->collision.boxes[box[k]&0x7F];",
        "        if(!b->active) continue;",
        "        debug_physics_block_test();",
        *[line[4:] for line in push],
        "    }",
        "}",
        "/* Parcourt tous les bloqueurs pour chaque mobile : en IWRAM, ARM, sans temps d'attente. */",
        "BS_ATTR_IWRAM",
        f"static void __attribute__((unused)) actors_resolve_blocks{sfx}(Actor* a,u8 body_mask,const PairRun* runs,"
        f"const BlockTarget* list,int n,const u8* box{ow_param}){{",
        "    if(!a->active) return;",
        "    int idle=!a->vx&&!a->vy;",
        *(["    int drop=g_drop_through&&g_drop_through[a->slot_index];"] if one_way else []),
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionShape* m=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!m->active) continue;",
        "        for(int k=0;k<n;k++){",
        *target,
        "        }",
        "    }",
        "}",
        "",
    ]


def block_tick_lines(p, scene, scene_actors, pi, resolve_initial_appearance) -> list[str]:
    """La passe de blocage de la scène : chaque mobile, posé ou né, contre chaque bloqueur, posé ou né.

    Tout se décide par TYPE d'emplacement (`Actor.type_id`, `OamLayout.placed_type_ids` pour les posés, `root_type_id` pour le
    pool partagé) : un type mobile a ses boîtes de corps (`_bk_mask`) et, pour chaque type bloqueur, la suite des boîtes
    qui peuvent l'arrêter (`_bk_run`), filtrée au build par la matrice des tags, le mode des deux corps et la règle du
    Rigid. Le runtime ne demande jamais si un emplacement est posé ou né (règle « posé = spawné »)."""
    lay = scene_oam_layout(p, scene)
    shared = shared_models(pi)
    owners: dict[int, tuple] = {}       # type -> (porteur, sprite) ; les copies d'un type ont les mêmes rôles de boîtes
    for (actor, sprite), kind in zip(scene_actors, lay.placed_type_ids):
        owners.setdefault(kind, (actor, sprite))
    for m in shared:
        owners.setdefault(m["root_type_id"], (m["prefab"], resolve_initial_appearance(p, m["prefab"])[1]))

    # Les boîtes bloquantes de chaque type : (rang | BLOCKER_MOVING, sens unique, boîte, mode du porteur).
    blocking = {}
    for kind, (owner, sprite) in owners.items():
        mode = physics_body_mode(owner)
        flag = BLOCKER_MOVING if mode == PHYSICS_BODY_KINEMATIC else 0
        if rows := [(rank | flag, shape_one_way_dir(box, scene, p.settings), box, mode)
                    for rank, box in physics_blocker_entries(owner, sprite)]:
            blocking[kind] = rows
    if not blocking:
        return []

    def stops(owner, sprite, rows) -> list:
        """Les boîtes de `rows` qui arrêtent ce mobile : un tag qui rencontre un des siens ; un Kinematic n'est arrêté
        que par un Static ; les paires d'un Rigid sont au solveur d'impulsions, sauf les faces à sens unique (un Rigid y
        est posé sans rebond, cf. `block_push_one_way`)."""
        mode = physics_body_mode(owner)
        colliders = [box for _rank, box in physics_collider_entries(owner, sprite)]
        return [(rank, ow) for rank, ow, box, blocker_mode in rows
                if (mode != PHYSICS_BODY_KINEMATIC or blocker_mode == PHYSICS_BODY_STATIC)
                and (mode != PHYSICS_BODY_RIGID or ow)
                and any(tags_collide(p.settings, c.tag or "body", box.tag or "body") for c in colliders)]

    def wall_mask(owner, sprite) -> int:
        """Les boîtes que la carte résout pour ce mobile, 0 sans carte ni résolution (cf. la garde de `mover_in_wall`).

        La résolution contre la carte ne bouge un acteur que d'après sa VITESSE : à vitesse nulle elle le prend pour un
        téléport et le laisse où il est, et le blocage annule la vitesse sur l'axe qu'il repousse. Sans garde, un mobile
        poussé par un bloqueur traversait donc le mur derrière lui : un déplacement qui le ferait entrer dans un mur est
        refusé, la carte garde le dernier mot.

        Refuser la poussée ne suffit pas : le mobile resterait DANS le bloqueur, et le solveur d'impulsions écarterait
        alors un Rigid (masse inverse nulle du Character) : le joueur au sol, que sa gravité enfonce d'un pixel dans le
        sol une image sur quelques-unes, poussait les Rigid. Le mobile renonce donc aussi à son propre pas de l'image sur
        l'axe que le blocage a arrêté (vitesse annulée) : il reste où il était, contre le bloqueur, sans le pousser."""
        if not scene_has_cmap(scene) or physics_body_mode(owner) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            return 0
        return physics_collider_mask(owner, sprite, map_only=True) if uses_character_solver(owner, sprite) else 0

    blocker_kinds = sorted(blocking)
    movers = []         # (type, masque de corps, masque de carte, [suite de boîtes par type bloqueur])
    for kind in sorted(owners):
        owner, sprite = owners[kind]
        if not uses_body_collider(owner, sprite):
            continue
        runs = [stops(owner, sprite, blocking[b]) for b in blocker_kinds]
        if any(runs):
            movers.append((kind, physics_collider_mask(owner, sprite), wall_mask(owner, sprite), runs))
    if not movers:
        return []

    box: list[int] = []
    ow: list[int] = []
    run_rows = []
    for _kind, _mask, _wall, runs in movers:
        row = []
        for run in runs:
            row.append(f"{{{len(box)},{len(run)}}}")
            box += [rank for rank, _ow in run]
            ow += [d for _rank, d in run]
        run_rows.append("{" + ",".join(row) + "}")
    type_table_size = lay.type_table_size
    mover_index = {kind: i for i, (kind, *_rest) in enumerate(movers)}
    blocker_index = {kind: i for i, kind in enumerate(blocker_kinds)}
    one_way = any(ow)
    walls = any(wall for _k, _m, wall, _r in movers)

    call = (f"actors_resolve_blocks{'_ow' if one_way else ''}(_a,_bk_mask[_mi],_bk_run[_mi],_bk_list,_bk_n,"
            f"_bk_box{',_bk_ow' if one_way else ''});")
    # La taille de la liste des bloqueurs : les posés d'un type bloqueur, puis tout le pool partagé s'il en fait naître.
    pool = any(m["root_type_id"] in blocking for m in shared)
    spool = shared[0]["spool"]["end"] - shared[0]["spool"]["start"] if pool else 0
    capacity = sum(1 for kind in lay.placed_type_ids if kind in blocking) + spool
    where = "" if capacity <= _LIST_IWRAM else " EWRAM_BSS"
    if walls:
        step = ("{ u8 _mi=_bk_mi[_a->type_id]; if(_mi!=255){ int _bx=_a->x,_by=_a->y,_bvx=_a->vx,_bvy=_a->vy; " + call
                + " if(_bk_wall[_mi]&&(_a->x!=_bx||_a->y!=_by)&&mover_in_wall(_a,_bk_wall[_mi])){"
                " _a->x=_bx; _a->y=_by; if(!_a->vx) _a->x-=_bvx; if(!_a->vy) _a->y-=_bvy; } } }")
    else:
        step = "{ u8 _mi=_bk_mi[_a->type_id]; if(_mi!=255) " + call + " }"

    def by_kind(index: dict) -> str:
        return ",".join(str(index.get(k, 255)) for k in range(type_table_size))

    return [
        "    /* Blocage entre acteurs, par couple de types : avant la carte de collision, qui a le dernier mot. */",
        "    {",
        *iwram_table(scene, "_bk_mi", f"        static const u8 _bk_mi[{type_table_size}]={{{by_kind(mover_index)}}};"),
        *iwram_table(scene, "_bk_bi", f"        static const u8 _bk_bi[{type_table_size}]={{{by_kind(blocker_index)}}};"),
        *iwram_table(scene, "_bk_mask",
                     f"        static const u8 _bk_mask[{len(movers)}]={{{','.join(str(m) for _k, m, _w, _r in movers)}}};"),
        *([*iwram_table(scene, "_bk_wall", f"        static const u8 _bk_wall[{len(movers)}]={{{','.join(str(w) for _k, _m, w, _r in movers)}}};")]
          if walls else []),
        *iwram_table(scene, "_bk_run",
                     f"        static const PairRun _bk_run[{len(movers)}][{len(blocker_kinds)}]={{{','.join(run_rows)}}};"),
        *iwram_table(scene, "_bk_box", f"        static const u8 _bk_box[{len(box)}]={{{','.join(map(str, box))}}};"),
        *([*iwram_table(scene, "_bk_ow", f"        static const u8 _bk_ow[{len(ow)}]={{{','.join(map(str, ow))}}};")] if one_way else []),
        f"        static BlockTarget _bk_list[{capacity}]{where};",
        "        int _bk_n=block_targets(_bk_bi,_bk_list);",
        *("    " + line for line in each_slot(step)),
        "    }",
    ]
