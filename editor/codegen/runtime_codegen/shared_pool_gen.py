"""runtime_codegen/shared_pool_gen.py — le C qui parcourt le pool PARTAGÉ d'une scène.

Un emplacement du pool accueille n'importe quel modèle simple (`oam_alloc.is_plain_model`) : le build ne
peut donc plus dérouler, modèle par modèle, des boucles sur des emplacements qu'il connaît. Chaque
passe du tick (mise à jour, tuiles, collisions, écriture OAM) devient UNE boucle sur les emplacements
utilisés (`POOL_EACH` : de `g_spool_start` à `g_spool_hw`, le plus haut utilisé, en sautant les blocs de 32
emplacements sans vivant), avec un `switch` sur `Actor.model` : le code du modèle est appelé, ou ses constantes
de sprite sont écrites, par le cas qui le concerne.

Un modèle à PARTIES occupe un groupe d'emplacements contigus : `Actor.model` y est un TYPE d'emplacement, la
racine portant l'identité du modèle (`model_id`) et sa partie k cette identité + k. Les scripts, la résolution
contre la carte et le Sfx ne concernent que la racine ; l'animation, l'affichage et les collisions ont un cas
par type (une partie réagit avec le script de sa racine, comme dans une réserve à part).

`pi` est la liste des pools de la scène (`gen_pool.scene_pi`) ; seuls ceux qui portent `shared`
comptent ici. Les fonctions reçoivent les générateurs de `main_gen` dont elles ont besoin plutôt que de
l'importer : ce module est sa dépendance, pas l'inverse."""
from __future__ import annotations


def shared_models(pi: list[dict]) -> list[dict]:
    """Les modèles du pool partagé, dans l'ordre de leur identité (`model_id`)."""
    return sorted((p2 for p2 in pi if p2.get("shared")), key=lambda p2: p2["model_id"])


def owners(m: dict) -> list:
    """Les porteurs d'un modèle, dans l'ordre des emplacements de son groupe : la racine, puis ses parties."""
    return [m["prefab"], *(getattr(m["prefab"], "children", None) or [])]


def _loop(body: list[str], *, active_only: bool = True) -> list[str]:
    """Une boucle sur les emplacements utilisés du pool, `_a` étant l'acteur courant."""
    head = ["    POOL_EACH(_pk){",
            "        Actor* _a=&g_actors[_pk];"]
    if active_only:
        head.append("        if(!_a->active) continue;")
    return head + ["        switch(_a->model){", *body, "        default: break;", "        }", "    }"]


def trim_lines(pi: list[dict]) -> list[str]:
    """Rabat le plus haut emplacement utilisé sur le dernier occupé : après une pluie de balles, les boucles
    du tick ne parcourent plus des emplacements vides."""
    if not shared_models(pi):
        return []
    return ["    while(g_spool_hw>g_spool_start && !g_actors[g_spool_hw-1].alive) g_spool_hw--;"]


def hook_lines(pi: list[dict], event: str, has_event) -> list[str]:
    """`on_update` / `on_late_update` des modèles du pool partagé qui le définissent."""
    cases = [f"        case {m['model_id']}: {m['sym']}_{event}(_a); break;"
             for m in shared_models(pi) if has_event(m["sym"], event)]
    return _loop(cases) if cases else []


def tile_lines(pi: list[dict], has_event, has_solid_box) -> list[str]:
    """La résolution contre la carte de collision, pour les modèles qui ont une boîte solide."""
    cases = []
    for m in shared_models(pi):
        if not has_solid_box(m["prefab"]):
            continue
        cb = f"{m['sym']}_on_tile_collide" if has_event(m["sym"], "on_tile_collide") else "NULL"
        cases.append(f"        case {m['model_id']}: resolve_actor_tiles(_a, {cb}); break;")
    return _loop(cases) if cases else []


def collision_lines(pi: list[dict], size: int, col_scene: list, can_collide, has_event, has_col_event,
                    dispatch_sym, lua_idx: set, scene_name: str, contact_lines) -> list[str]:
    """Les contacts des instances du pool partagé avec les acteurs posés qui ont une boîte.

    Une collision a DEUX côtés, et chacun apprend la nouvelle dans son propre script (comme la boucle
    pool↔scène des réserves à part). Le souvenir du recouvrement de la frame précédente est rangé par
    emplacement ; il appartient à l'occupant, donc il repart de zéro dès que l'emplacement change de
    main (`Actor.gen`)."""
    evs = ("on_collision_enter", "on_collide", "on_collision_exit")
    cases, width = [], 0
    for m in shared_models(pi):
        s = m["sym"]
        partners = [(idx, a) for idx, a in col_scene if can_collide(m["prefab"], a)]
        pool_reacts = has_col_event(has_event, s)
        body = []
        for ci, (sidx, sactor) in enumerate(partners):
            ss = dispatch_sym(scene_name, sactor.name)
            s_lua = (sidx in lua_idx) and has_col_event(has_event, ss)
            if not pool_reacts and not s_lua:
                continue
            ev_pool = [(ev, s) for ev in evs if has_event(s, ev)]
            ev_scene = [(ev, ss) for ev in evs if s_lua and has_event(ss, ev)]
            body += contact_lines(
                "_a", f"&g_actors[{sidx}]", f"g_actors[{sidx}].active", f"_pcol[_sl][{ci}]",
                [(ev, f"{fn}_{ev}") for ev, fn in ev_pool],
                [(ev, f"{fn}_{ev}") for ev, fn in ev_scene],
                "                ")
            width = max(width, ci + 1)
        if body:
            labels = " ".join(f"case {m['model_id'] + k}:" for k in range(m["group"]))
            cases += [f"            {labels} {{", *body, "            } break;"]
    if not cases:
        return []
    return [
        "    {",
        f"        static u16 _pcol[{size}][{width}] EWRAM_BSS;   /* recouvrement de la frame précédente */",
        f"        static u16 _pcol_gen[{size}] EWRAM_BSS;          /* à quel occupant il appartient */",
        "        POOL_EACH(_pk){",
        "            Actor* _a=&g_actors[_pk];",
        "            if(!_a->active) continue;",
        "            int _sl=_pk-g_spool_start;",
        f"            if(_pcol_gen[_sl]!=_a->gen){{ _pcol_gen[_sl]=_a->gen; for(int _c=0;_c<{width};_c++) _pcol[_sl][_c]=0; }}",
        "            switch(_a->model){",
        *cases,
        "            default: break;",
        "            }",
        "        }",
        "    }",
    ]


def sfx_lines(model: dict, sfx_sym, sfx_vol) -> list[str]:
    """Le Sfx d'un modèle du pool partagé, joué pour chacune de ses instances actives."""
    return [f"        POOL_EACH(_pi)",
            f"            if(g_actors[_pi].active && g_actors[_pi].model=={model['model_id']}) "
            f"sfx_play({sfx_sym}, {sfx_vol}, 0);   /* SoundFxComponent : {model['prefab'].name} */"]


def anim_oam_lines(pi: list[dict], anim_variants, anim_tick_variants, appearances, oam_write_lines,
                   affine_of=None) -> list[str]:
    """L'animation puis l'écriture OAM des instances du pool partagé : UNE boucle, et dans chaque cas d'un type
    d'emplacement le tick d'animation de son porteur, puis ses constantes de sprite. `_pk` est l'acteur, `_pe` son
    état d'affichage (un par emplacement). Un porteur dont aucune apparence n'a d'état à animer n'a pas de tick, un
    porteur qui n'affiche rien n'écrit rien ; un type sans l'un ni l'autre n'a pas de cas.

    Les deux passes tenaient dans deux boucles successives ; les fusionner ne change rien parce que chacune ne lit et
    n'écrit que l'état de son propre emplacement (l'écriture OAM lit la frame que l'animation vient de poser, du même
    emplacement) : l'ordre des entrées de `shadow_oam` reste celui des emplacements. L'écriture OAM est déjà gardée
    par `active`, donc le `continue` d'un acteur inactif ne retire rien.

    `anim_variants(porteur, symbole)` : les apparences à animer, ou `[None]` si aucune n'a d'état ; `appearances(porteur)`
    : les apparences à écrire ; `affine_of(modèle, porteur)` : l'entrée affine DYNAMIQUE du porteur (une matrice prise à
    la frame), ou None."""
    cases: dict[int, list[str]] = {}
    for m in shared_models(pi):
        for k, owner in enumerate(owners(m)):
            if m["member_entries"][k] < 0:
                continue                # ce porteur n'a pas d'entrée : ni animation ni affichage
            body: list[str] = []
            variants = anim_variants(owner, m["sym"])
            if any(v is not None for v in variants):
                body += ["        {", *anim_tick_variants("_pk", "_pe", variants), "        }"]
            apps = appearances(owner)
            if apps:
                aff = affine_of(m, owner) if affine_of else None
                body += ["        {", *oam_write_lines("_pk", "_pe", apps, aff=aff), "        }"]
            if body:
                cases[m["model_id"] + k] = body
    if not cases:
        return []
    lines: list[str] = []
    for type_id in sorted(cases):
        lines += [f"        case {type_id}: {{", *cases[type_id], "        } break;"]
    return ["    POOL_EACH(_pk){",
            "        Actor* _a=&g_actors[_pk];",
            "        if(!_a->active) continue;",
            "        int _pe=g_spool_entry+(_pk-g_spool_start);",
            "        switch(_a->model){", *lines, "        default: break;", "        }", "    }"]
