"""Le composant Interactive, côté C : les aides de détection et le bloc que la boucle de scène émet.

Le composant est un système AUTOMATISÉ : il ne génère aucune logique propre à un acteur. Il se compile
en code de SCÈNE, comme le déclencheur `SoundFx` : une table par geste (indice de l'acteur, rang de sa
zone, mode de visée, fonction `on_interact`), un test du geste (`input_pressed`, tenue de `n` frames,
`input_released`) évalué UNE fois pour tous les consommateurs, et seulement sur la frame où le geste a
lieu, une recherche du consommateur atteint le plus proche pour chaque interacteur.

Un acteur sans `on_interact` dans son script n'entre dans aucune table : il ne coûte rien.

L'interacteur est un acteur de scène portant le tag d'acteur `Player` (`Actor.is_player`).

Les instances du pool PARTAGÉ (cf. `shared_pool_gen`) n'ont pas d'emplacement connu du build : un interacteur
né y est reconnu à son modèle (`Actor.model`), et un consommateur né y est décrit par deux tables indexées par
modèle (rang de la zone, visée), que `interact_pick` parcourt après les consommateurs d'emplacement connu.
"""
from __future__ import annotations

from codegen.runtime_codegen.gen_sprite import follow_facing_lines
from codegen.runtime_codegen.shared_pool_gen import shared_models
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
        "/* Un mur de la carte de collision entre deux points ? Échantillonné tous les 4 px. Les points",
        "   dans la zone visée `z` ne comptent pas : une zone posée sur un mur (panneau encastré) reste",
        "   atteignable, seul un mur ENTRE l'interacteur et elle l'arrête. */",
        "static int __attribute__((unused)) ia_line_blocked(int x0,int y0,int x1,int y1,const IaRect* z){",
        "    int dx=x1-x0, dy=y1-y0, ax=dx<0?-dx:dx, ay=dy<0?-dy:dy, n=(ax>ay?ax:ay)/4;",
        "    for(int i=0;i<=n;i++){",
        "        int x=n?x0+dx*i/n:x0, y=n?y0+dy*i/n:y0;",
        "        if(x>=z->l&&x<z->r&&y>=z->t&&y<z->b) continue;",
        "        if(tile_wall_at(x,y)) return 1;",
        "    }",
        "    return 0;",
        "}",
        "/* Le consommateur `t` (zone de rang `box`, `aim` = visée au lieu du recouvrement) est-il atteint par",
        "   `who` ? Si oui, `*dist` est le carré de la distance entre les centres. `w` : la boîte de `who`,",
        "   `s` : cette boîte étendue dans son regard (fx, fy). */",
        "static int __attribute__((unused)) ia_reach(const IaRect* w,const IaRect* s,int fx,int fy,",
        "                                             const Actor* t,int box,int aim,int* dist){",
        "    if(box>=t->collision.box_count) return 0;",
        "    const CollisionBox* zb=&t->collision.boxes[box];",
        "    if(!zb->active) return 0;",
        "    IaRect z; ia_box_rect(t,zb,&z);",
        "    const IaRect* q=aim?s:w;",
        "    if(aim&&!fx&&!fy) return 0;",
        "    if(q->l>=z.r||q->r<=z.l||q->t>=z.b||q->b<=z.t) return 0;",
        "    int wcx=(w->l+w->r)>>1, wcy=(w->t+w->b)>>1, zcx=(z.l+z.r)>>1, zcy=(z.t+z.b)>>1;",
        "    if(aim&&ia_line_blocked(wcx,wcy,zcx,zcy,&z)) return 0;",
        "    int ddx=zcx-wcx, ddy=zcy-wcy;",
        "    *dist=ddx*ddx+ddy*ddy;",
        "    return 1;",
        "}",
        "/* Parmi les `n` consommateurs (acteur `idx[k]`, zone `box[k]`, `aim[k]` = visée au lieu du",
        "   recouvrement), puis parmi les instances du pool PARTAGÉ (`pbox[modèle]` = rang de la zone, 255 = ce",
        "   modèle n'en est pas un ; `paim[modèle]` = visée ; `pbox` nul = aucun), celui que `who` atteint, le",
        "   plus proche de son centre. Rend son rang k, ou -2 - emplacement pour un consommateur du pool ;",
        "   -1 si aucun.",
        "   hover  : la boîte de `who` recouvre la zone.",
        "   facing : la boîte de `who`, étendue de `reach` px dans son regard, touche la zone sans mur",
        "            entre les deux ; un regard nul n'atteint rien. */",
        "static int __attribute__((unused)) interact_pick(const Actor* who,const u16* idx,const u8* box,",
        "                                                  const u8* aim,int n,const u8* pbox,const u8* paim,",
        "                                                  int reach){",
        "    IaRect w; ia_who_rect(who,&w);",
        "    int fx=who->facing_x, fy=who->facing_y;",
        "    IaRect s=w;",
        "    if(fx>0) s.r+=reach; else if(fx<0) s.l-=reach;",
        "    if(fy>0) s.b+=reach; else if(fy<0) s.t-=reach;",
        "    int best=-1, bd=0x7fffffff, d=0;",
        "    for(int k=0;k<n;k++){",
        "        const Actor* t=&g_actors[idx[k]];",
        "        if(!t->active||t==who) continue;",
        "        if(ia_reach(&w,&s,fx,fy,t,box[k],aim[k],&d)&&d<bd){ bd=d; best=k; }",
        "    }",
        "    if(pbox)",
        "        for(int sl=g_spool_start;sl<g_spool_hw;sl++){",
        "            const Actor* t=&g_actors[sl];",
        "            if(!t->active||t==who||pbox[t->model]==255) continue;",
        "            if(ia_reach(&w,&s,fx,fy,t,pbox[t->model],paim[t->model],&d)&&d<bd){ bd=d; best=-2-sl; }",
        "        }",
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
    """Les consommateurs de la scène : (composant, indice d'acteur, rang de zone, symbole C).

    Un acteur n'en est un que si son script définit `on_interact`. Pour un modèle du pool PARTAGÉ, l'indice
    est l'identité du modèle (`model_id`) : ses instances ne sont connues qu'à l'exécution."""
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
        if not p2.get("shared"):
            continue            # ses instances posées sont des acteurs de la scène, vus plus haut
        pf = p2["prefab"]
        comp = next((c for c in getattr(pf, "components", [])
                     if isinstance(c, InteractiveComponent) and c.active), None)
        if comp is None or not _def(p2["sym"], "on_interact"):
            continue
        sprite = shown(p, pf)[1]
        box = interactive_box_index(owner_boxes(pf, sprite), comp)
        if box >= 0:
            out.append((comp, p2["model_id"], box, p2["sym"]))      # un MODÈLE : ses instances se trouvent à l'exécution
    return out


def _spriteless_facing_lines(first: int, stop: int, step: int) -> list[str]:
    """Le regard d'un interacteur SANS sprite : il n'a pas de tick d'animation (c'est là que le regard
    d'un acteur se suit), donc la même règle (`gen_sprite.follow_facing_lines`) est posée ici, sans la
    condition `facing_auto` (portée par l'entrée OAM qu'il n'a pas)."""
    body = " ".join(s.strip() for s in follow_facing_lines("(*_a)"))
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
    shared = shared_models(pi)
    # Les modèles du pool partagé marqués Player : reconnus à l'exécution, par `Actor.model`.
    pool_players = [m["model_id"] for m in shared if getattr(m["prefab"], "is_player", False)]
    pool_spriteless = [m["model_id"] for m in shared
                       if getattr(m["prefab"], "is_player", False) and m["member_entries"][0] < 0]
    consumers = _consumers(p, scene, scene_actors, actor_offset, pi, lua_idx, _def, scene_actor_sym, shown)
    if not (interactors or pool_players) or not consumers:
        return []
    shared_ids = {m["model_id"] for m in shared}
    mask = input_layout.masks["interact"]
    reach = int(getattr(p.settings, "interact_reach", 4))
    gestures: dict = {}
    for comp, idx, box, sym in consumers:
        key = (comp.input_mode, comp.hold_frames if comp.input_mode == "hold" else 0)
        gestures.setdefault(key, []).append((comp, idx, box, sym))

    def is_pool(item) -> bool:
        return item[3] in {m["sym"] for m in shared}

    def model_is(ids: list[int], var: str) -> str:
        return "(" + "||".join(f"{var}.model=={i}" for i in ids) + ")"

    def dispatch(who: str, pad: str, n: int, has_pool: bool) -> list[str]:
        """La recherche pour l'interacteur `who` (une expression `Actor*`), puis l'appel de ce qu'il atteint."""
        pa = "_ia_pbox,_ia_paim" if has_pool else "0,0"
        out = [f"{pad}int _k=interact_pick({who},_ia_idx,_ia_box,_ia_aim,{n},{pa},{reach});"]
        if n:
            out.append(f"{pad}if(_k>=0) _ia_fn[_k](&g_actors[_ia_idx[_k]],{who});")
        if has_pool:
            out += [f"{pad}if(_k<-1){{ Actor* _t=&g_actors[-2-_k]; _ia_pfn[_t->model](_t,{who}); }}"]
        return out

    L = []
    if spriteless or pool_spriteless:
        L.append("    /* Interactive : un interacteur sans sprite suit son regard ici (pas de tick d'animation) */")
        for first, stop, step in spriteless:
            L += _spriteless_facing_lines(first, stop, step)
        if pool_spriteless:
            body = " ".join(s.strip() for s in follow_facing_lines("(*_a)"))
            L += ["    for(int _w=g_spool_start;_w<g_spool_hw;_w++){",
                  f"        Actor* _a=&g_actors[_w]; if(!{model_is(pool_spriteless, '(*_a)')}) continue;",
                  f"        {body}", "    }"]
    L.append("    /* Interactive : une table par geste, la recherche seulement quand le geste a lieu */")
    for (mode, frames), items in gestures.items():
        static_items = [i for i in items if not is_pool(i)]
        pool_items = [i for i in items if is_pool(i)]
        n = len(static_items)
        top = max(shared_ids) + 1 if pool_items else 0
        L += [f"    if({_gesture_test(mode, frames, mask)}){{"]
        # Sans consommateur d'emplacement connu, les tables gardent une case morte : un tableau C n'est pas vide.
        L += [
            f"        static const u16 _ia_idx[]={{{','.join(str(i[1]) for i in static_items) or '0'}}};",
            f"        static const u8 _ia_box[]={{{','.join(str(i[2]) for i in static_items) or '0'}}};",
            f"        static const u8 _ia_aim[]={{{','.join('1' if i[0].interaction == 'facing' else '0' for i in static_items) or '0'}}};",
        ]
        if n:
            L.append(f"        static void (*const _ia_fn[])(Actor*,Actor*)="
                     f"{{{','.join(i[3] + '_on_interact' for i in static_items)}}};")
        if pool_items:
            by_model = {i[1]: i for i in pool_items}
            L += [
                f"        static const u8 _ia_pbox[{top}]={{{','.join(str(by_model[m][2]) if m in by_model else '255' for m in range(top))}}};",
                f"        static const u8 _ia_paim[{top}]={{{','.join('1' if m in by_model and by_model[m][0].interaction == 'facing' else '0' for m in range(top))}}};",
                f"        static void (*const _ia_pfn[{top}])(Actor*,Actor*)="
                f"{{{','.join(by_model[m][3] + '_on_interact' if m in by_model else '0' for m in range(top))}}};",
            ]
        for first, stop, step in interactors:
            if stop - first == 1:
                L += [f"        if(g_actors[{first}].active){{",
                      *dispatch(f"&g_actors[{first}]", "            ", n, bool(pool_items)), "        }"]
            else:
                L += [f"        for(int _w={first};_w<{stop};_w+={step}){{",
                      "            if(!g_actors[_w].active) continue;",
                      *dispatch("&g_actors[_w]", "            ", n, bool(pool_items)), "        }"]
        if pool_players:
            L += ["        for(int _w=g_spool_start;_w<g_spool_hw;_w++){",
                  f"            if(!g_actors[_w].active||!{model_is(pool_players, 'g_actors[_w]')}) continue;",
                  *dispatch("&g_actors[_w]", "            ", n, bool(pool_items)), "        }"]
        L.append("    }")
    return L
