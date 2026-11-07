"""Le composant Interactive, côté C : les aides de détection et le bloc que la boucle de scène émet.

Le composant est un système AUTOMATISÉ : il ne génère aucune logique propre à un acteur. Il se compile
en code de SCÈNE, comme le déclencheur `SoundFx` : par geste, trois tables indexées par TYPE d'emplacement
(`Actor.model`, cf. `model_desc`) : le tag de la zone (255 : ce type n'est pas un consommateur de ce geste), la
visée, l'action (`on_interact`, son). Le geste (`input_pressed`, tenue de `n` frames, `input_released`) est testé
UNE fois, et seulement sur la frame où il a lieu chaque interacteur cherche le consommateur atteint le plus proche.

Un type entre dans les tables s'il a un handler `on_interact` ou un SoundFx déclenché à l'interaction.

L'interacteur est un acteur portant le tag d'acteur `Player` (`Actor.is_player`) : `ModelDesc.interactor`.

Un seul chemin pour les posés et les nés : `interact_pick` parcourt les posés de la scène puis le pool partagé, et
lit la ligne du type de chaque emplacement. La zone se cherche au runtime par son tag (la première boîte qui le
porte), comme le build la choisissait : le tag est un champ d'emplacement, deux variantes d'un prefab peuvent
différer par lui.
"""
from __future__ import annotations

from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_sprite import follow_facing_lines
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.model_desc import each_slot, model_desc_sym
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import (
    INTERACTIVE_COLLISION_TAG, InteractiveComponent, interactive_box_index, owner_effective_boxes,
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
        "typedef struct { void (*handler)(Actor*,Actor*); s16 sfx; u8 volume; } IaAction;",
        "static void __attribute__((unused)) interact_run(Actor* target,Actor* who,const IaAction* action){",
        "    if(action->sfx>=0) sfx_play(action->sfx,action->volume,0);",
        "    if(action->handler) action->handler(target,who);",
        "}",
        "/* ── Interactive : trouver ce que l'interacteur atteint ─────────────────────────────",
        "   Rectangles en PIXELS MONDE, bornes droite/basse exclues, comme `box_overlap`. */",
        "typedef struct { int l, t, r, b; } IaRect;",
        "static void __attribute__((unused)) ia_box_rect(const Actor* a, const CollisionShape* b, IaRect* o){",
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
        "/* Le consommateur `t` (zone : sa première boîte de tag `tag`, `aim` = visée au lieu du recouvrement)",
        "   est-il atteint par `who` ? Si oui, `*dist` est le carré de la distance entre les centres. `w` : la",
        "   boîte de `who`, `s` : cette boîte étendue dans son regard (fx, fy). */",
        "static int __attribute__((unused)) ia_reach(const IaRect* w,const IaRect* s,int fx,int fy,",
        "                                             const Actor* t,int tag,int aim,int* dist){",
        "    int box=0;",
        "    while(box<t->collision.box_count&&t->collision.boxes[box].tag!=tag) box++;",
        "    if(box>=t->collision.box_count) return 0;",
        "    const CollisionShape* zb=&t->collision.boxes[box];",
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
        "/* Parmi les emplacements actifs de la scène, posés ou nés (`SLOT_EACH`), celui que `who` atteint, le plus",
        "   proche de son centre ; -1 si aucun. Un emplacement compte si son",
        "   type est un consommateur de ce geste : `tag[type]` est le tag de sa zone (255 : il n'en est pas un),",
        "   `aim[type]` la visée au lieu du recouvrement.",
        "   hover  : la boîte de `who` recouvre la zone.",
        "   facing : la boîte de `who`, étendue de `reach` px dans son regard, touche la zone sans mur",
        "            entre les deux ; un regard nul n'atteint rien. */",
        "static int __attribute__((unused)) interact_pick(const Actor* who,const u8* tag,const u8* aim,int reach){",
        "    IaRect w; ia_who_rect(who,&w);",
        "    int fx=who->facing_x, fy=who->facing_y;",
        "    IaRect s=w;",
        "    if(fx>0) s.r+=reach; else if(fx<0) s.l-=reach;",
        "    if(fy>0) s.b+=reach; else if(fy<0) s.t-=reach;",
        "    int best=-1, bd=0x7fffffff, d=0;",
        "    SLOT_EACH(k){",
        "        const Actor* t=&g_actors[k];",
        "        if(!t->active||t==who||tag[t->model]==255) continue;",
        "        if(ia_reach(&w,&s,fx,fy,t,tag[t->model],aim[t->model],&d)&&d<bd){ bd=d; best=k; }",
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


def _consumers(p, scene_actors, pi, placed_scripts, _def, shown, layout) -> dict[int, tuple]:
    """Les consommateurs, par type d'emplacement : (composant, tag de la zone, action C).

    Une action a un handler, un son, ou les deux. Un posé prend le type de son layout (`placed_model`), un modèle du
    pool partagé son identité (`model_id`) ; les variantes d'un même type ont le même composant et le même code."""
    tags = list(p.collision_tags()) or ["body"]
    candidates = [(a, sprite, kind, script)
                  for (a, sprite), kind, script in zip(scene_actors, layout.placed_model, placed_scripts)]
    candidates += [(m["prefab"], shown(p, m["prefab"])[1], m["model_id"], m["sym"]) for m in shared_models(pi)]
    out = {}
    for owner, sprite, kind, script in candidates:
        comp = next((c for c in getattr(owner, "components", [])
                     if isinstance(c, InteractiveComponent) and c.active), None)
        handler = f"{script}_on_interact" if script and _def(script, "on_interact") else "0"
        sfx, volume, trigger = sfx_trigger_info(p, owner)
        if trigger != "on_interact":
            sfx = None
        if comp is None or (handler == "0" and sfx is None):
            continue
        tag = comp.box_tag or INTERACTIVE_COLLISION_TAG
        if interactive_box_index(owner_boxes(owner, sprite), comp) >= 0 and tag in tags:
            out[kind] = (comp, tags.index(tag), f"{{{handler},{sfx or '-1'},{volume if sfx else 0}}}")
    return out


def interact_tick_lines(p, scene, scene_actors, pi, placed_scripts, _def, input_layout,
                        shown) -> list[str]:
    """Le bloc de la boucle de scène : le regard des interacteurs sans sprite, puis un test de geste par (mode, durée)
    et, sur la frame du geste, pour chaque interacteur la recherche du consommateur atteint. Posés et nés passent par
    les mêmes boucles (`model_desc.each_slot`). Rien n'est émis sans interacteur ni consommateur.

    `placed_scripts` : le symbole du code Lua de chaque posé (None sans script), cf. `model_desc_lines`."""
    layout = scene_oam_layout(p, scene)
    shared = shared_models(pi)
    players = [a for a, _s in scene_actors if getattr(a, "is_player", False)]
    pool_players = [m for m in shared if getattr(m["prefab"], "is_player", False)]
    consumers = _consumers(p, scene_actors, pi, placed_scripts, _def, shown, layout)
    if not (players or pool_players) or not consumers:
        return []
    desc = model_desc_sym(scene)
    mask = input_layout.masks["interact"]
    reach = int(getattr(p.settings, "interact_reach", 4))
    gestures: dict = {}
    for kind, item in consumers.items():
        comp = item[0]
        gestures.setdefault((comp.input_mode, comp.hold_frames if comp.input_mode == "hold" else 0), {})[kind] = item

    L = []
    # Le regard d'un interacteur SANS sprite : il n'a pas de tick d'animation (c'est là que le regard d'un acteur se
    # suit), donc la même règle (`gen_sprite.follow_facing_lines`) est posée ici, sans la condition `facing_auto`.
    placed_blind = any(getattr(a, "is_player", False) and e < 0
                       for (a, _s), e in zip(scene_actors, layout.placed_entry))
    pool_blind = any(m["member_entries"][0] < 0 for m in pool_players)
    if placed_blind or pool_blind:
        body = " ".join(line.strip() for line in follow_facing_lines("(*_a)"))
        L.append("    /* Interactive : un interacteur sans sprite suit son regard ici (pas de tick d'animation) */")
        L += each_slot(f"if({desc}[_a->model].interactor==2){{ {body} }}")
    L.append("    /* Interactive : trois tables par geste, indexées par type ; la recherche quand le geste a lieu */")
    for (mode, frames), items in gestures.items():
        kinds = layout.kinds
        tag = ",".join(str(items[k][1]) if k in items else "255" for k in range(kinds))
        aim = ",".join("1" if k in items and items[k][0].interaction == "facing" else "0" for k in range(kinds))
        action = ",".join(items[k][2] if k in items else "{0,-1,0}" for k in range(kinds))
        step = (f"if({desc}[_a->model].interactor){{ "
                f"int _t=interact_pick(_a,_ia_tag,_ia_aim,{reach}); "
                "if(_t>=0) interact_run(&g_actors[_t],_a,&_ia_action[g_actors[_t].model]); }")
        L += [f"    if({_gesture_test(mode, frames, mask)}){{",
              f"        static const u8 _ia_tag[{kinds}]={{{tag}}};",
              f"        static const u8 _ia_aim[{kinds}]={{{aim}}};",
              f"        static const IaAction _ia_action[{kinds}]={{{action}}};",
              *("    " + line for line in each_slot(step)),
              "    }"]
    return L
