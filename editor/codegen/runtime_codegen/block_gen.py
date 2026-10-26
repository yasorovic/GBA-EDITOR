"""Le blocage entre acteurs, côté C : une boîte `blocks_actors` arrête les acteurs en mouvement.

Un MOBILE est un acteur actif dont la vitesse n'est pas nulle (le critère de la résolution contre la
carte : l'acteur déplacé par `self.velocity` est « conduit », un acteur téléporté ne l'est pas) et qui
porte une box `solid`. Un BLOQUEUR est une box `blocks_actors` d'un autre acteur. Le mobile est repoussé
hors de la box qu'il recouvre, sur l'axe de plus faible pénétration ; il glisse donc le long d'un
obstacle quand il le heurte en diagonale.

Émis AVANT la résolution contre la carte : les murs ont le dernier mot, le mobile ne peut pas être poussé
dans un mur. La matrice de collision filtre au build (un couple de tags qui ne se rencontrent pas se
traverse). Rien n'est émis sans mobile ni bloqueur ; les aides C ne le sont que si le projet a une box
bloquante.

Les instances du pool PARTAGÉ (cf. `shared_pool_gen`) ne sont pas à des emplacements connus du build :
une table y désigne des MODÈLES (`Actor.model`) et des rangs de boîte, et l'aide C parcourt les emplacements
utilisés du pool pour trouver ceux qui en sont. Un mobile né dans le pool est traité par le cas de son modèle.
"""
from __future__ import annotations

from core.models.components import CollisionBoxComponent
from core.models.settings import tags_collide
from codegen.runtime_codegen.gen_scene_query import has_solid_box
from codegen.runtime_codegen.interact_gen import owner_boxes
from codegen.runtime_codegen.shared_pool_gen import shared_models


def project_has_blockers(p) -> bool:
    """Une boîte bloquante quelque part : celle d'un auteur, ou la boîte propre d'un Interactive en
    `facing` (un obstacle par défaut)."""
    from core.models.components import InteractiveComponent
    owners = [a for sc in getattr(p, "scenes", []) or [] for a in sc.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any((isinstance(c, CollisionBoxComponent) and c.active and c.blocks_actors)
               or (isinstance(c, InteractiveComponent) and c.active and c.interaction == "facing"
                   and not c.box_tag)
               for o in owners for c in getattr(o, "components", []))


def block_helper_lines() -> list[str]:
    """L'aide C, pure : ne dépend que d'`Actor` et de `g_actors`."""
    return [
        "/* ── Blocage entre acteurs : repousser un mobile hors des boîtes qui bloquent ───────",
        "   `idx[k]` / `box[k]` : l'acteur et le rang de la k-ième boîte bloquante. Un mobile (actif, vitesse",
        "   non nulle) est repoussé, pour chacune de ses boîtes solid, de la pénétration minimale, sur",
        "   l'axe le plus court (l'horizontal en cas d'égalité). La position garde sa fraction (Q8). */",
        "static void __attribute__((unused)) block_push(Actor* a,const CollisionBox* m,const Actor* t,const CollisionBox* b){",
        "    int ml=(a->x>>8)+m->x, mt=(a->y>>8)+m->y, mr=ml+m->w, mb=mt+m->h;",
        "    int bl=(t->x>>8)+b->x, bt=(t->y>>8)+b->y, br=bl+b->w, bb=bt+b->h;",
        "    if(ml>=br||mr<=bl||mt>=bb||mb<=bt) return;",
        "    int left=mr-bl, right=br-ml, up=mb-bt, down=bb-mt;",
        "    int px=left<right?-left:right, py=up<down?-up:down;",
        "    int apx=px<0?-px:px, apy=py<0?-py:py;",
        "    if(apx<=apy) a->x+=px<<8; else a->y+=py<<8;",
        "}",
        "static void __attribute__((unused)) actors_resolve_blocks(Actor* a,const u16* idx,const u8* box,int n){",
        "    if(!a->active||(!a->vx&&!a->vy)) return;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionBox* m=&a->collision.boxes[i];",
        "        if(!m->active||!m->solid) continue;",
        "        for(int k=0;k<n;k++){",
        "            const Actor* t=&g_actors[idx[k]];",
        "            if(t==a||!t->active||box[k]>=t->collision.box_count) continue;",
        "            const CollisionBox* b=&t->collision.boxes[box[k]];",
        "            if(!b->active) continue;",
        "            block_push(a,m,t,b);",
        "        }",
        "    }",
        "}",
        "/* Le même blocage contre les instances du pool PARTAGÉ : `model[k]` / `box[k]` désignent un modèle et",
        "   le rang de sa k-ième boîte bloquante ; les emplacements utilisés du pool sont parcourus. */",
        "static void __attribute__((unused)) actors_resolve_blocks_pool(Actor* a,const u8* model,const u8* box,int n){",
        "    if(!a->active||(!a->vx&&!a->vy)) return;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        const CollisionBox* m=&a->collision.boxes[i];",
        "        if(!m->active||!m->solid) continue;",
        "        for(int s=g_spool_start;s<g_spool_hw;s++){",
        "            const Actor* t=&g_actors[s];",
        "            if(t==a||!t->active) continue;",
        "            for(int k=0;k<n;k++){",
        "                if(t->model!=model[k]||box[k]>=t->collision.box_count) continue;",
        "                const CollisionBox* b=&t->collision.boxes[box[k]];",
        "                if(b->active) block_push(a,m,t,b);",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]


def _blocking_boxes(owner, sprite) -> list[tuple[int, str]]:
    """(rang, tag) de chacune des boîtes bloquantes de ce porteur, parmi les boîtes que le build pose
    dessus (la boîte propre d'un Interactive en `facing` comprise)."""
    return [(i, b.tag or "body") for i, b in enumerate(owner_boxes(owner, sprite))
            if isinstance(b, CollisionBoxComponent) and b.active and b.blocks_actors]


def _solid_tags(owner, sprite) -> list[str]:
    """Les tags des boîtes solid d'un mobile possible : ce sont elles que le blocage repousse."""
    return [b.tag or "body" for b in owner_boxes(owner, sprite)
            if isinstance(b, CollisionBoxComponent) and b.solid]


def block_tick_lines(p, scene, scene_actors, actor_offset, pi, shown) -> list[str]:
    """Les appels de la boucle de scène : pour chaque mobile, la table des boîtes qui peuvent l'arrêter.

    `pi` : les modèles de la scène. Ceux du pool PARTAGÉ (`p2["shared"]`) n'ont pas d'emplacement connu du build :
    leurs bloqueurs et leurs mobiles se décident à l'exécution, par modèle."""
    shared = shared_models(pi)
    # Les bloqueurs : (indice d'acteur, rang de boîte, tag de la boîte).
    blockers = []
    for j, (actor, sprite) in enumerate(scene_actors):
        for rank, tag in _blocking_boxes(actor, sprite):
            blockers.append((actor_offset + j, rank, tag))
    # Les bloqueurs du pool partagé : (identité du modèle, rang de boîte, tag).
    pool_blockers = [(m["model_id"], rank, tag) for m in shared
                     for rank, tag in _blocking_boxes(m["prefab"], shown(p, m["prefab"])[1])]
    if not blockers and not pool_blockers:
        return []

    def can_stop(mover_owner, mover_sprite, tag):
        return any(tags_collide(p.settings, m, tag) for m in _solid_tags(mover_owner, mover_sprite))

    def table(mover_owner, mover_sprite):
        """Les boîtes qui peuvent arrêter ce mobile : celles dont le tag rencontre un des siens dans la
        matrice de collision (le tag de la boîte propre d'un Interactive compris)."""
        return [(i, r) for i, r, tag in blockers if can_stop(mover_owner, mover_sprite, tag)]

    def pool_table(mover_owner, mover_sprite):
        return [(m, r) for m, r, tag in pool_blockers if can_stop(mover_owner, mover_sprite, tag)]

    L: list[str] = []

    def tables(entries: list, pool_entries: list, pad: str) -> list[str]:
        """Les tables statiques d'un mobile : ses bloqueurs d'emplacement connu, puis ceux du pool."""
        out = []
        if entries:
            out += [f"{pad}static const u16 _bk_idx[]={{{','.join(str(i) for i, _ in entries)}}};",
                    f"{pad}static const u8 _bk_box[]={{{','.join(str(r) for _, r in entries)}}};"]
        if pool_entries:
            out += [f"{pad}static const u8 _bk_pm[]={{{','.join(str(m) for m, _ in pool_entries)}}};",
                    f"{pad}static const u8 _bk_pb[]={{{','.join(str(r) for _, r in pool_entries)}}};"]
        return out

    def calls(entries: list, pool_entries: list, target: str, pad: str) -> list[str]:
        out = []
        if entries:
            out.append(f"{pad}actors_resolve_blocks({target},_bk_idx,_bk_box,{len(entries)});")
        if pool_entries:
            out.append(f"{pad}actors_resolve_blocks_pool({target},_bk_pm,_bk_pb,{len(pool_entries)});")
        return out

    def emit(target: str, entries: list, pool_entries: list):
        if not entries and not pool_entries:
            return
        L.append("    {")
        L.extend(tables(entries, pool_entries, "        "))
        L.extend(calls(entries, pool_entries, f"&g_actors[{target}]", "        "))
        L.append("    }")

    for j, (actor, sprite) in enumerate(scene_actors):
        if has_solid_box(actor):
            emit(str(actor_offset + j), table(actor, sprite), pool_table(actor, sprite))
    # Les mobiles du pool partagé : une boucle sur les emplacements utilisés, les tables de chaque modèle dans son cas.
    cases = []
    for m in shared:
        if not has_solid_box(m["prefab"]):
            continue
        sp = shown(p, m["prefab"])[1]
        entries, pool_entries = table(m["prefab"], sp), pool_table(m["prefab"], sp)
        if entries or pool_entries:
            cases += [f"        case {m['model_id']}: {{", *tables(entries, pool_entries, "            "),
                      *calls(entries, pool_entries, "_a", "            "), "        } break;"]
    if cases:
        L += ["    for(int _bm=g_spool_start;_bm<g_spool_hw;_bm++){",
              "        Actor* _a=&g_actors[_bm];",
              "        switch(_a->model){", *cases, "        default: break;", "        }", "    }"]
    if L:
        L.insert(0, "    /* Blocage entre acteurs : avant la carte de collision, qui a le dernier mot */")
    return L
