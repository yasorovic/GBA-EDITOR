"""Le composant Interactive, côté C : les aides de détection et le bloc que la boucle de scène émet.

Le composant est un système AUTOMATISÉ : il ne génère aucune logique propre à un acteur. Il se compile
en code de SCÈNE, comme le déclencheur `SoundFx` : une table par geste (indice de l'acteur, rang de sa
zone, mode de visée, fonction `on_interact`), un test du geste (`input_pressed`, tenue de `n` frames,
`input_released`) évalué UNE fois pour tous les consommateurs, et seulement sur la frame où le geste a
lieu, une recherche du consommateur atteint le plus proche pour chaque interacteur.

Un acteur sans `on_interact` dans son script n'entre dans aucune table : il ne coûte rien.

L'interacteur est un acteur de scène portant le tag d'acteur `Player` (`Actor.is_player`).
"""
from __future__ import annotations

from core.models.components import (
    InteractiveComponent, interactive_box_index, owner_effective_boxes,
)

# Une tenue de `n` frames se lit sur des compteurs `u8` qui saturent à 255 : `n` reste en dessous.
_MAX_HOLD = 254


def owner_boxes(owner, sprite) -> list:
    """Les boîtes posées sur ce porteur (cf. `owner_effective_boxes`) — la fonction que le build utilise
    pour l'init des boîtes ET pour numéroter les zones des tables, afin que les deux ne divergent pas."""
    return owner_effective_boxes(owner, sprite)


def project_has_interactive(p) -> bool:
    """Un composant Interactive actif quelque part (scène ou prefab) : seul cas où les aides C sont émises."""
    owners = [a for sc in getattr(p, "scenes", []) or [] for a in sc.actors]
    owners += list(getattr(p, "prefabs", []) or [])
    return any(isinstance(c, InteractiveComponent) and c.active
               for o in owners for c in getattr(o, "components", []))


def interact_helper_lines() -> list[str]:
    """Les aides C, émises après les aides de tuiles dont elles dépendent (`tile_wall_at`)."""
    return [
        "/* ── Interactive : trouver ce que l'interacteur atteint ─────────────────────────────",
        "   Rectangles en PIXELS MONDE, bornes droite/basse exclues, comme `box_overlap`. */",
        "typedef struct { int l, t, r, b; } IaRect;",
        "static void __attribute__((unused)) ia_box_rect(const Actor* a, const CollisionBox* b, IaRect* o){",
        "    o->l=(a->x>>8)+b->x; o->t=(a->y>>8)+b->y; o->r=o->l+b->w; o->b=o->t+b->h;",
        "}",
        "/* La boîte de l'interacteur : la première boîte solide active, sinon la première active, sinon",
        "   le cadre de son sprite (16x16 sans sprite). Elle existe donc toujours. */",
        "static void __attribute__((unused)) ia_who_rect(const Actor* who, IaRect* o){",
        "    for(int i=0;i<who->collision.box_count;i++)",
        "        if(who->collision.boxes[i].active&&who->collision.boxes[i].solid){",
        "            ia_box_rect(who,&who->collision.boxes[i],o); return; }",
        "    for(int i=0;i<who->collision.box_count;i++)",
        "        if(who->collision.boxes[i].active){ ia_box_rect(who,&who->collision.boxes[i],o); return; }",
        "    int w=16,h=16;",
        "    if(who->oam_entry>=0){",
        "        if(g_oam_entries[who->oam_entry].frame_w) w=g_oam_entries[who->oam_entry].frame_w;",
        "        if(g_oam_entries[who->oam_entry].frame_h) h=g_oam_entries[who->oam_entry].frame_h;",
        "    }",
        "    o->l=who->x>>8; o->t=who->y>>8; o->r=o->l+w; o->b=o->t+h;",
        "}",
        "/* Un mur de la carte de collision entre deux points ? Échantillonné tous les 4 px. */",
        "static int __attribute__((unused)) ia_line_blocked(int x0,int y0,int x1,int y1){",
        "    int dx=x1-x0, dy=y1-y0, ax=dx<0?-dx:dx, ay=dy<0?-dy:dy, n=(ax>ay?ax:ay)/4;",
        "    for(int i=0;i<=n;i++){",
        "        int x=n?x0+dx*i/n:x0, y=n?y0+dy*i/n:y0;",
        "        if(tile_wall_at(x,y)) return 1;",
        "    }",
        "    return 0;",
        "}",
        "/* Parmi les `n` consommateurs (acteur `idx[k]`, zone `box[k]`, `aim[k]` = visée au lieu du",
        "   recouvrement), celui que `who` atteint, le plus proche de son centre ; -1 si aucun.",
        "   hover  : la boîte de `who` recouvre la zone.",
        "   facing : la boîte de `who`, étendue de `reach` px dans son regard, touche la zone sans mur",
        "            entre les deux ; un regard nul n'atteint rien. */",
        "static int __attribute__((unused)) interact_pick(const Actor* who,const u16* idx,const u8* box,",
        "                                                  const u8* aim,int n,int reach){",
        "    IaRect w; ia_who_rect(who,&w);",
        "    int fx=who->facing_x, fy=who->facing_y;",
        "    IaRect s=w;",
        "    if(fx>0) s.r+=reach; else if(fx<0) s.l-=reach;",
        "    if(fy>0) s.b+=reach; else if(fy<0) s.t-=reach;",
        "    int wcx=(w.l+w.r)>>1, wcy=(w.t+w.b)>>1, best=-1, bd=0x7fffffff;",
        "    for(int k=0;k<n;k++){",
        "        const Actor* t=&g_actors[idx[k]];",
        "        if(!t->active||t==who||box[k]>=t->collision.box_count) continue;",
        "        const CollisionBox* zb=&t->collision.boxes[box[k]];",
        "        if(!zb->active) continue;",
        "        IaRect z; ia_box_rect(t,zb,&z);",
        "        const IaRect* q=aim[k]?&s:&w;",
        "        if(aim[k]&&!fx&&!fy) continue;",
        "        if(q->l>=z.r||q->r<=z.l||q->t>=z.b||q->b<=z.t) continue;",
        "        int zcx=(z.l+z.r)>>1, zcy=(z.t+z.b)>>1;",
        "        if(aim[k]&&ia_line_blocked(wcx,wcy,zcx,zcy)) continue;",
        "        int ddx=zcx-wcx, ddy=zcy-wcy, d=ddx*ddx+ddy*ddy;",
        "        if(d<bd){ bd=d; best=k; }",
        "    }",
        "    return best;",
        "}",
        "",
    ]


def _gesture_test(mode: str, frames: int, mask: str) -> str:
    """Le test C du geste, évalué une fois par frame pour tous les consommateurs de ce geste."""
    if mode == "hold":
        n = max(1, min(frames, _MAX_HOLD))
        # « exactement n » : le plus petit compteur des boutons vaut n, donc le geste ne se répète pas.
        return f"input_held_n({mask},{n})&&!input_held_n({mask},{n + 1})"
    if mode == "released":
        return f"input_released({mask})"
    return f"input_pressed({mask})"


def _consumers(p, scene, scene_actors, actor_offset, pi, lua_idx, _def, scene_actor_sym, shown):
    """Les consommateurs de la scène : (geste, indice d'acteur, rang de zone, visée, fonction C).

    Un acteur n'en est un que si son script définit `on_interact`."""
    out = []
    for j, (actor, sprite) in enumerate(scene_actors):
        comp = next((c for c in actor.components
                     if isinstance(c, InteractiveComponent) and c.active), None)
        sym = scene_actor_sym(scene.name, actor.name)
        if comp is None or (actor_offset + j) not in lua_idx or not _def(sym, "on_interact"):
            continue
        box = interactive_box_index(owner_boxes(actor, sprite), comp)
        if box >= 0:
            out.append((comp, actor_offset + j, box, sym))
    for p2 in pi:
        pf = p2["prefab"]
        comp = next((c for c in getattr(pf, "components", [])
                     if isinstance(c, InteractiveComponent) and c.active), None)
        if comp is None or not _def(p2["sym"], "on_interact"):
            continue
        sprite = shown(p, pf)[1]
        box = interactive_box_index(owner_boxes(pf, sprite), comp)
        if box < 0:
            continue
        step = p2.get("group", 1)
        for slot in range(p2["start"], p2["start"] + p2["size"], step):
            out.append((comp, slot, box, p2["sym"]))
    return out


def _spriteless_facing_lines(first: int, stop: int, step: int) -> list[str]:
    """Le regard d'un interacteur SANS sprite : il n'a pas de tick d'animation (c'est là que le regard
    d'un acteur se suit, cf. `gen_sprite.direction_lines`), donc la même règle est posée ici —
    trajectoire depuis la vitesse, regard = dernière direction non nulle."""
    body = ("_a->dir_x=(_a->vx>0)-(_a->vx<0); _a->dir_y=(_a->vy>0)-(_a->vy<0); "
            "if(_a->dir_x||_a->dir_y){ _a->facing_x=_a->dir_x; _a->facing_y=_a->dir_y; }")
    if stop - first == 1:
        return [f"    {{ Actor* _a=&g_actors[{first}]; {body} }}"]
    return [f"    for(int _w={first};_w<{stop};_w+={step}){{ Actor* _a=&g_actors[_w]; {body} }}"]


def interact_tick_lines(p, scene, scene_actors, actor_offset, pi, lua_idx, _def, scene_actor_sym,
                        input_layout, shown, entry_of) -> list[str]:
    """Le bloc de la boucle de scène : un test de geste par (mode, durée), et pour chaque interacteur
    la recherche du consommateur atteint. Rien n'est émis sans interacteur ni consommateur."""
    # Les interacteurs : les acteurs de scène marqués Player (un indice), et les prefabs marqués Player
    # (une plage : chaque instance libre ou vivante de leur pool, une racine tous les `group`).
    # `entry_of(j)` : l'entrée OAM de l'acteur posé n° j (-1 = sans sprite).
    interactors, spriteless = [], []
    for j, (a, _s) in enumerate(scene_actors):
        if getattr(a, "is_player", False):
            interactors.append((actor_offset + j, actor_offset + j + 1, 1))
            if entry_of(j) < 0:
                spriteless.append(interactors[-1])
    for p2 in pi:
        if getattr(p2["prefab"], "is_player", False):
            interactors.append((p2["start"], p2["start"] + p2["size"], p2.get("group", 1)))
            if p2["member_entries"][0] < 0:
                spriteless.append(interactors[-1])
    consumers = _consumers(p, scene, scene_actors, actor_offset, pi, lua_idx, _def, scene_actor_sym, shown)
    if not interactors or not consumers:
        return []
    mask = input_layout.masks["interact"]
    reach = int(getattr(p.settings, "interact_reach", 4))
    gestures: dict = {}
    for comp, idx, box, sym in consumers:
        key = (comp.input_mode, comp.hold_frames if comp.input_mode == "hold" else 0)
        gestures.setdefault(key, []).append((comp, idx, box, sym))

    L = []
    if spriteless:
        L.append("    /* Interactive : un interacteur sans sprite suit son regard ici (pas de tick d'animation) */")
        for first, stop, step in spriteless:
            L += _spriteless_facing_lines(first, stop, step)
    L.append("    /* Interactive : une table par geste, la recherche seulement quand le geste a lieu */")
    for (mode, frames), items in gestures.items():
        n = len(items)
        L += [
            f"    if({_gesture_test(mode, frames, mask)}){{",
            f"        static const u16 _ia_idx[]={{{','.join(str(i[1]) for i in items)}}};",
            f"        static const u8 _ia_box[]={{{','.join(str(i[2]) for i in items)}}};",
            f"        static const u8 _ia_aim[]={{{','.join('1' if i[0].interaction == 'facing' else '0' for i in items)}}};",
            f"        static void (*const _ia_fn[])(Actor*,Actor*)={{{','.join(i[3] + '_on_interact' for i in items)}}};",
        ]
        for first, stop, step in interactors:
            if stop - first == 1:
                L += [
                    f"        if(g_actors[{first}].active){{",
                    f"            int _k=interact_pick(&g_actors[{first}],_ia_idx,_ia_box,_ia_aim,{n},{reach});",
                    f"            if(_k>=0) _ia_fn[_k](&g_actors[_ia_idx[_k]],&g_actors[{first}]);",
                    "        }",
                ]
            else:
                L += [
                    f"        for(int _w={first};_w<{stop};_w+={step}){{",
                    "            if(!g_actors[_w].active) continue;",
                    f"            int _k=interact_pick(&g_actors[_w],_ia_idx,_ia_box,_ia_aim,{n},{reach});",
                    "            if(_k>=0) _ia_fn[_k](&g_actors[_ia_idx[_k]],&g_actors[_w]);",
                    "        }",
                ]
        L.append("    }")
    return L
