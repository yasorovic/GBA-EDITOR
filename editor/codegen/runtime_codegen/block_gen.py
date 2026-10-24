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
"""
from __future__ import annotations

from core.models.components import CollisionBoxComponent
from core.models.settings import tags_collide
from codegen.runtime_codegen.gen_scene_query import has_solid_box
from codegen.runtime_codegen.interact_gen import owner_boxes


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
        "            int ml=(a->x>>8)+m->x, mt=(a->y>>8)+m->y, mr=ml+m->w, mb=mt+m->h;",
        "            int bl=(t->x>>8)+b->x, bt=(t->y>>8)+b->y, br=bl+b->w, bb=bt+b->h;",
        "            if(ml>=br||mr<=bl||mt>=bb||mb<=bt) continue;",
        "            int left=mr-bl, right=br-ml, up=mb-bt, down=bb-mt;",
        "            int px=left<right?-left:right, py=up<down?-up:down;",
        "            int apx=px<0?-px:px, apy=py<0?-py:py;",
        "            if(apx<=apy) a->x+=px<<8; else a->y+=py<<8;",
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
    """Les appels de la boucle de scène : pour chaque mobile, la table des boîtes qui peuvent l'arrêter."""
    # Les bloqueurs : (indice d'acteur, rang de boîte, tag de la boîte).
    blockers = []
    for j, (actor, sprite) in enumerate(scene_actors):
        for rank, tag in _blocking_boxes(actor, sprite):
            blockers.append((actor_offset + j, rank, tag))
    for p2 in pi:
        pf = p2["prefab"]
        for rank, tag in _blocking_boxes(pf, shown(p, pf)[1]):
            for slot in range(p2["start"], p2["start"] + p2["size"], p2.get("group", 1)):
                blockers.append((slot, rank, tag))
    if not blockers:
        return []

    def table(mover_owner, mover_sprite):
        """Les boîtes qui peuvent arrêter ce mobile : celles dont le tag rencontre un des siens dans la
        matrice de collision (le tag de la boîte propre d'un Interactive compris)."""
        mine = _solid_tags(mover_owner, mover_sprite)
        return [(i, r) for i, r, tag in blockers if any(tags_collide(p.settings, m, tag) for m in mine)]

    L: list[str] = []

    def emit(target: str, entries: list, loop: tuple | None):
        if not entries:
            return
        idx = ",".join(str(i) for i, _ in entries)
        box = ",".join(str(r) for _, r in entries)
        L.append("    {")
        L.append(f"        static const u16 _bk_idx[]={{{idx}}};")
        L.append(f"        static const u8 _bk_box[]={{{box}}};")
        if loop is None:
            L.append(f"        actors_resolve_blocks(&g_actors[{target}],_bk_idx,_bk_box,{len(entries)});")
        else:
            first, stop, step = loop
            L.append(f"        for(int _bi={first};_bi<{stop};_bi+={step})")
            L.append(f"            actors_resolve_blocks(&g_actors[_bi],_bk_idx,_bk_box,{len(entries)});")
        L.append("    }")

    for j, (actor, sprite) in enumerate(scene_actors):
        if has_solid_box(actor):
            emit(str(actor_offset + j), table(actor, sprite), None)
    for p2 in pi:
        if has_solid_box(p2["prefab"]):
            emit("", table(p2["prefab"], shown(p, p2["prefab"])[1]),
                 (p2["start"], p2["start"] + p2["size"], p2.get("group", 1)))
    if L:
        L.insert(0, "    /* Blocage entre acteurs : avant la carte de collision, qui a le dernier mot */")
    return L
