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

Les instances du pool PARTAGÉ (cf. `shared_pool_gen`) ne sont pas à des emplacements connus du build :
une table y désigne des MODÈLES (`Actor.model`) et des rangs de boîte, et l'aide C parcourt les emplacements
utilisés du pool pour trouver ceux qui en sont. Un mobile né dans le pool est traité par le cas de son modèle.
"""
from __future__ import annotations

from core.models.components import (
    COLLISION_RESPONSE_BLOCK, PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID,
    PHYSICS_BODY_STATIC, CollisionShapeComponent,
)
from core.models.settings import tags_collide
from codegen.runtime_codegen.physics.body import (
    physics_blocker_entries, physics_body_mode, physics_collider_entries,
    physics_collider_mask, shape_one_way_dir, uses_body_collider, uses_character_solver,
)
from codegen.runtime_codegen.physics.oneway import oneway_common_lines
from codegen.runtime_codegen.gen_scene_query import scene_has_cmap
from codegen.runtime_codegen.shared_pool_gen import shared_models


# Bit haut du rang de boîte d'un bloqueur dans les tables C : un bloqueur Kinematic en mouvement pousse un mobile même
# immobile, les autres (Static, Rigid, Character) ne repoussent qu'un mobile en mouvement. Le rang tient dans les 7 bits bas.
BLOCKER_MOVING = 0x80


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
        "static void __attribute__((unused)) block_push_one_way(Actor* a,const CollisionShape* m,const Actor* t,const CollisionShape* b,u8 dir){",
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
        "static void __attribute__((unused)) actors_resolve_blocks_ow(Actor* a,u8 body_mask,const u16* idx,const u8* box,const u8* ow,int n){",
        "    if(!a->active) return;",
        "    int idle=!a->vx&&!a->vy;",
        "    int drop=g_drop_through&&g_drop_through[a->inst];",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionShape* m=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!m->active) continue;",
        "        for(int k=0;k<n;k++){",
        "            const Actor* t=&g_actors[idx[k]];",
        "            if(t==a||!t->active||(box[k]&0x7F)>=t->collision.box_count) continue;",
        "            if(idle&&!((box[k]&0x80)&&(t->vx||t->vy))) continue;",
        "            const CollisionShape* b=&t->collision.boxes[box[k]&0x7F];",
        "            if(!b->active) continue;",
        "            debug_physics_block_test();",
        "            if(!ow[k]) block_push(a,m,t,b);",
        "            else if(!drop) block_push_one_way(a,m,t,b,ow[k]);",
        "        }",
        "    }",
        "}",
        "static void __attribute__((unused)) actors_resolve_blocks_pool_ow(Actor* a,u8 body_mask,const u8* model,const u8* box,const u8* ow,int n){",
        "    if(!a->active) return;",
        "    int idle=!a->vx&&!a->vy;",
        "    int drop=g_drop_through&&g_drop_through[a->inst];",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionShape* m=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!m->active) continue;",
        "        POOL_EACH(s){",
        "            const Actor* t=&g_actors[s];",
        "            if(t==a||!t->active) continue;",
        "            for(int k=0;k<n;k++){",
        "                if(t->model!=model[k]||(box[k]&0x7F)>=t->collision.box_count) continue;",
        "                if(idle&&!((box[k]&0x80)&&(t->vx||t->vy))) continue;",
        "                const CollisionShape* b=&t->collision.boxes[box[k]&0x7F];",
        "                if(!b->active) continue;",
        "                debug_physics_block_test();",
        "                if(!ow[k]) block_push(a,m,t,b);",
        "                else if(!drop) block_push_one_way(a,m,t,b,ow[k]);",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]


def _block_lines() -> list[str]:
    return [
        "/* ── Blocage entre acteurs : repousser un mobile hors des boîtes qui bloquent ───────",
        "   `idx[k]` / `box[k]` : l'acteur et le rang de la k-ième boîte bloquante. Un mobile (actif, vitesse",
        "   non nulle) est repoussé, pour chacune de ses boîtes de carte, de la pénétration minimale, sur",
        "   l'axe le plus court (l'horizontal en cas d'égalité). La position garde sa fraction (Q8) et la",
        "   composante de vitesse sur cet axe est annulée. */",
        "static void __attribute__((unused)) block_push(Actor* a,const CollisionShape* m,const Actor* t,const CollisionShape* b){",
        "    int ml=(a->x>>8)+m->x, mt=(a->y>>8)+m->y, mr=ml+m->w, mb=mt+m->h;",
        "    int bl=(t->x>>8)+b->x, bt=(t->y>>8)+b->y, br=bl+b->w, bb=bt+b->h;",
        "    if(ml>=br||mr<=bl||mt>=bb||mb<=bt) return;",
        "    int left=mr-bl, right=br-ml, up=mb-bt, down=bb-mt;",
        "    int px=left<right?-left:right, py=up<down?-up:down;",
        "    int apx=px<0?-px:px, apy=py<0?-py:py;",
        "    if(apx<=apy){ a->x+=px<<8; a->vx=0; }",
        "    else { a->y+=py<<8; a->vy=0; }",
        "}",
        "static void __attribute__((unused)) actors_resolve_blocks(Actor* a,u8 body_mask,const u16* idx,const u8* box,int n){",
        "    if(!a->active) return;",
        "    int idle=!a->vx&&!a->vy;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionShape* m=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!m->active) continue;",
        "        for(int k=0;k<n;k++){",
        "            const Actor* t=&g_actors[idx[k]];",
        "            if(t==a||!t->active||(box[k]&0x7F)>=t->collision.box_count) continue;",
        "            if(idle&&!((box[k]&0x80)&&(t->vx||t->vy))) continue;",
        "            const CollisionShape* b=&t->collision.boxes[box[k]&0x7F];",
        "            if(!b->active) continue;",
        "            debug_physics_block_test();",
        "            block_push(a,m,t,b);",
        "        }",
        "    }",
        "}",
        "/* Le même blocage contre les instances du pool PARTAGÉ : `model[k]` / `box[k]` désignent un modèle et",
        "   le rang de sa k-ième boîte bloquante ; les emplacements utilisés du pool sont parcourus. */",
        "static void __attribute__((unused)) actors_resolve_blocks_pool(Actor* a,u8 body_mask,const u8* model,const u8* box,int n){",
        "    if(!a->active) return;",
        "    int idle=!a->vx&&!a->vy;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionShape* m=&a->collision.boxes[i];",
        "        if(!(body_mask&(1u<<i))||!m->active) continue;",
        "        POOL_EACH(s){",
        "            const Actor* t=&g_actors[s];",
        "            if(t==a||!t->active) continue;",
        "            for(int k=0;k<n;k++){",
        "                if(t->model!=model[k]||(box[k]&0x7F)>=t->collision.box_count) continue;",
        "                if(idle&&!((box[k]&0x80)&&(t->vx||t->vy))) continue;",
        "                const CollisionShape* b=&t->collision.boxes[box[k]&0x7F];",
        "                if(b->active){ debug_physics_block_test(); block_push(a,m,t,b); }",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]


def _blocking_boxes(owner, sprite) -> list[tuple[int, CollisionShapeComponent]]:
    """(rang, tag) de chacune des boîtes bloquantes de ce porteur, parmi les boîtes que le build pose
    dessus (la boîte propre d'un Interactive en `facing` comprise)."""
    return [(rank, box)
            for rank, box in physics_blocker_entries(owner, sprite)]


def _body_colliders(owner, sprite) -> list[CollisionShapeComponent]:
    return [box for _rank, box in physics_collider_entries(owner, sprite)]


def block_tick_lines(p, scene, scene_actors, actor_offset, pi, shown) -> list[str]:
    """Les appels de la boucle de scène : pour chaque mobile, la table des boîtes qui peuvent l'arrêter.

    `pi` : les modèles de la scène. Ceux du pool PARTAGÉ (`p2["shared"]`) n'ont pas d'emplacement connu du build :
    leurs bloqueurs et leurs mobiles se décident à l'exécution, par modèle."""
    shared = shared_models(pi)
    # Les bloqueurs : (indice d'acteur, rang de boîte, tag de la boîte, mode du porteur).
    blockers = []
    for j, (actor, sprite) in enumerate(scene_actors):
        for rank, box in _blocking_boxes(actor, sprite):
            blockers.append((actor_offset + j, rank, box, physics_body_mode(actor),
                             shape_one_way_dir(box, scene, p.settings)))
    # Les bloqueurs du pool partagé : (identité du modèle, rang de boîte, tag, mode du porteur).
    pool_blockers = [(m["model_id"], rank, box, physics_body_mode(m["prefab"]),
                      shape_one_way_dir(box, scene, p.settings)) for m in shared
                     for rank, box in _blocking_boxes(m["prefab"], shown(p, m["prefab"])[1])]
    if not blockers and not pool_blockers:
        return []

    def can_stop(mover_owner, mover_sprite, blocker):
        return any(tags_collide(p.settings, mover.tag or "body", blocker.tag or "body")
                   for mover in _body_colliders(mover_owner, mover_sprite))

    def moving_flag(blocker_mode) -> int:
        """Le bit haut du rang d'un bloqueur Kinematic : il pousse même un mobile immobile (cf. `block_helper_lines`)."""
        return BLOCKER_MOVING if blocker_mode == PHYSICS_BODY_KINEMATIC else 0

    def table(mover_owner, mover_sprite):
        """Les boîtes qui peuvent arrêter ce mobile : celles dont le tag rencontre un des siens dans la
        matrice de collision (le tag de la boîte propre d'un Interactive compris)."""
        mode = physics_body_mode(mover_owner)
        return [(i, r | moving_flag(blocker_mode), ow) for i, r, blocker, blocker_mode, ow in blockers
                if (mode != PHYSICS_BODY_KINEMATIC or blocker_mode == PHYSICS_BODY_STATIC)
                and can_stop(mover_owner, mover_sprite, blocker)]

    def pool_table(mover_owner, mover_sprite):
        mode = physics_body_mode(mover_owner)
        return [(m, r | moving_flag(blocker_mode), ow) for m, r, blocker, blocker_mode, ow in pool_blockers
                if (mode != PHYSICS_BODY_KINEMATIC or blocker_mode == PHYSICS_BODY_STATIC)
                and can_stop(mover_owner, mover_sprite, blocker)]

    L: list[str] = []

    def tables(entries: list, pool_entries: list, pad: str) -> list[str]:
        """Les tables statiques d'un mobile : ses bloqueurs d'emplacement connu, puis ceux du pool."""
        out = []
        if entries:
            out += [f"{pad}static const u16 _bk_idx[]={{{','.join(str(i) for i, _, _ in entries)}}};",
                    f"{pad}static const u8 _bk_box[]={{{','.join(str(r) for _, r, _ in entries)}}};"]
            if any(ow for _, _, ow in entries):
                out.append(f"{pad}static const u8 _bk_ow[]={{{','.join(str(ow) for _, _, ow in entries)}}};")
        if pool_entries:
            out += [f"{pad}static const u8 _bk_pm[]={{{','.join(str(m) for m, _, _ in pool_entries)}}};",
                    f"{pad}static const u8 _bk_pb[]={{{','.join(str(r) for _, r, _ in pool_entries)}}};"]
            if any(ow for _, _, ow in pool_entries):
                out.append(f"{pad}static const u8 _bk_pw[]={{{','.join(str(ow) for _, _, ow in pool_entries)}}};")
        return out

    def calls(entries: list, pool_entries: list, target: str, mask: int, pad: str) -> list[str]:
        out = []
        if entries and any(ow for _, _, ow in entries):
            out.append(f"{pad}actors_resolve_blocks_ow({target},{mask},_bk_idx,_bk_box,_bk_ow,{len(entries)});")
        elif entries:
            out.append(f"{pad}actors_resolve_blocks({target},{mask},_bk_idx,_bk_box,{len(entries)});")
        if pool_entries and any(ow for _, _, ow in pool_entries):
            out.append(f"{pad}actors_resolve_blocks_pool_ow({target},{mask},_bk_pm,_bk_pb,_bk_pw,{len(pool_entries)});")
        elif pool_entries:
            out.append(f"{pad}actors_resolve_blocks_pool({target},{mask},_bk_pm,_bk_pb,{len(pool_entries)});")
        return out

    def map_mask_of(owner, sprite) -> int:
        """Les boîtes que la carte résout pour ce mobile (celles de `gen_scene_tick`), 0 sans carte ni résolution."""
        if not scene_has_cmap(scene) or physics_body_mode(owner) not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_RIGID):
            return 0
        return physics_collider_mask(owner, sprite, map_only=True) if uses_character_solver(owner, sprite) else 0

    def pushed(ref: str, map_mask: int, pad: str) -> tuple[list[str], list[str]]:
        """Avant et après les appels de blocage d'un mobile que la carte résout.

        La résolution contre la carte ne bouge un acteur que d'après sa VITESSE : à vitesse nulle elle le prend pour un
        téléport et le laisse où il est, et le blocage annule la vitesse sur l'axe qu'il repousse. Sans garde, un mobile
        poussé par un bloqueur traversait donc le mur, le sol ou le plafond derrière lui. Un déplacement qui le ferait
        entrer dans un mur est refusé : le mobile reste où il était, la carte garde bien le dernier mot."""
        if not map_mask:
            return [], []
        return ([f"{pad}int _bx={ref}->x,_by={ref}->y;"],
                [f"{pad}if(({ref}->x!=_bx||{ref}->y!=_by)&&mover_in_wall({ref},{map_mask})){{ {ref}->x=_bx; {ref}->y=_by; }}"])

    def emit(target: str, entries: list, pool_entries: list, mask: int, map_mask: int = 0):
        if not entries and not pool_entries:
            return
        before, after = pushed(f"(&g_actors[{target}])", map_mask, "        ")
        L.append("    {")
        L.extend(tables(entries, pool_entries, "        "))
        L.extend(before)
        L.extend(calls(entries, pool_entries, f"&g_actors[{target}]", mask, "        "))
        L.extend(after)
        L.append("    }")

    def not_rigid_pairs(owner, entries: list) -> list:
        """Les paires d'un Rigid (posé ou né) appartiennent au solveur d'impulsions, posé ou pool, sauf les faces à
        sens unique : un Rigid y est posé sans rebond, par le blocage (cf. `block_push_one_way`)."""
        return [e for e in entries if e[2]] if physics_body_mode(owner) == PHYSICS_BODY_RIGID else entries

    for j, (actor, sprite) in enumerate(scene_actors):
        if uses_body_collider(actor, sprite):
            emit(str(actor_offset + j), not_rigid_pairs(actor, table(actor, sprite)),
                 not_rigid_pairs(actor, pool_table(actor, sprite)), physics_collider_mask(actor, sprite),
                 map_mask_of(actor, sprite))
    # Les mobiles du pool partagé : une boucle sur les emplacements utilisés, les tables de chaque modèle dans son cas.
    cases = []
    for m in shared:
        sp = shown(p, m["prefab"])[1]
        if not uses_body_collider(m["prefab"], sp):
            continue
        mask = physics_collider_mask(m["prefab"], sp)
        entries = not_rigid_pairs(m["prefab"], table(m["prefab"], sp))
        pool_entries = not_rigid_pairs(m["prefab"], pool_table(m["prefab"], sp))
        if entries or pool_entries:
            before, after = pushed("_a", map_mask_of(m["prefab"], sp), "            ")
            cases += [f"        case {m['model_id']}: {{", *tables(entries, pool_entries, "            "), *before,
                      *calls(entries, pool_entries, "_a", mask, "            "), *after, "        } break;"]
    if cases:
        L += ["    POOL_EACH(_bm){",
              "        Actor* _a=&g_actors[_bm];",
              "        switch(_a->model){", *cases, "        default: break;", "        }", "    }"]
    if L:
        L.insert(0, "    /* Blocage entre acteurs : avant la carte de collision, qui a le dernier mot */")
    return L
