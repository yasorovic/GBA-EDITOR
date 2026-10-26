"""runtime_codegen/shared_pool_gen.py — le C qui parcourt le pool PARTAGÉ d'une scène.

Un emplacement du pool accueille n'importe quel modèle simple (`oam_alloc.is_plain_model`) : le build ne
peut donc plus dérouler, modèle par modèle, des boucles sur des emplacements qu'il connaît. Chaque
passe du tick (mise à jour, tuiles, collisions, écriture OAM) devient UNE boucle sur les emplacements
utilisés (de `g_spool_start` à `g_spool_hw`, le plus haut utilisé), avec un `switch` sur `Actor.model` :
le code du modèle est appelé, ou ses constantes de sprite sont écrites, par le cas qui le concerne.

Un modèle à PARTIES occupe un groupe d'emplacements contigus : `Actor.model` y est un TYPE d'emplacement, la
racine portant l'identité du modèle (`model_id`) et sa partie k cette identité + k. Les scripts, la résolution
contre la carte et le Sfx ne concernent que la racine ; l'animation, l'affichage et les collisions ont un cas
par type (une partie réagit avec le script de sa racine, comme dans une réserve à part).

`pi` est la liste des pools de la scène (`main_gen._scene_pi`) ; seuls ceux qui portent `shared`
comptent ici. Les fonctions reçoivent les générateurs de `main_gen` dont elles ont besoin plutôt que de
l'importer : ce module est sa dépendance, pas l'inverse."""
from __future__ import annotations


def shared_models(pi: list[dict]) -> list[dict]:
    """Les modèles du pool partagé, dans l'ordre de leur identité (`model_id`)."""
    return sorted((p2 for p2 in pi if p2.get("shared")), key=lambda p2: p2["model_id"])


def owners(m: dict) -> list:
    """Les porteurs d'un modèle, dans l'ordre des emplacements de son groupe : la racine, puis ses parties."""
    return [m["prefab"], *(getattr(m["prefab"], "children", None) or [])]


def _loop(body: list[str], *, active_only: bool = True, entry: bool = False) -> list[str]:
    """Une boucle sur les emplacements utilisés du pool, `_a` étant l'acteur courant (et `_pe` son état
    d'affichage si `entry`)."""
    head = ["    for(int _pk=g_spool_start; _pk<g_spool_hw; _pk++){",
            "        Actor* _a=&g_actors[_pk];"]
    if active_only:
        head.append("        if(!_a->active) continue;")
    if entry:
        head.append("        int _pe=g_spool_entry+(_pk-g_spool_start);")
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
        f"        static u8 _pcol_gen[{size}] EWRAM_BSS;          /* à quel occupant il appartient */",
        "        for(int _pk=g_spool_start; _pk<g_spool_hw; _pk++){",
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
    return [f"        for(int _pi=g_spool_start; _pi<g_spool_hw; _pi++)",
            f"            if(g_actors[_pi].active && g_actors[_pi].model=={model['model_id']}) "
            f"sfx_play({sfx_sym}, {sfx_vol}, 0);   /* SoundFxComponent : {model['prefab'].name} */"]


def anim_lines(pi: list[dict], anim_variants, anim_tick_variants) -> list[str]:
    """Le tick d'animation des instances du pool partagé : une boucle, et les tables de sprite de chaque
    type d'emplacement dans son cas. `_pk` est l'acteur, `_pe` son état d'affichage (un par emplacement).
    Un porteur dont aucune apparence n'a d'état à animer n'a pas de cas."""
    cases = []
    for m in shared_models(pi):
        for k, owner in enumerate(owners(m)):
            if m["member_entries"][k] < 0:
                continue
            variants = anim_variants(owner, m["sym"])
            if not any(v is not None for v in variants):
                continue
            cases += [f"        case {m['model_id'] + k}: {{", *anim_tick_variants("_pk", "_pe", variants),
                      "        } break;"]
    if not cases:
        return []
    return _loop(cases, entry=True)


def oam_lines(pi: list[dict], appearances, oam_write_lines, affine_of=None) -> list[str]:
    """L'écriture OAM des instances du pool partagé : une boucle, et les constantes de sprite de chaque
    type d'emplacement dans son cas. `_pk` est l'acteur, `_pe` son état d'affichage (un par emplacement).
    `affine_of(modèle, porteur)` : l'entrée affine DYNAMIQUE du porteur (une matrice prise à la frame), ou None."""
    cases = []
    for m in shared_models(pi):
        for k, owner in enumerate(owners(m)):
            if m["member_entries"][k] < 0:
                continue                # ce porteur n'affiche rien
            apps = appearances(owner)
            if not apps:
                continue
            aff = affine_of(m, owner) if affine_of else None
            cases += [f"        case {m['model_id'] + k}: {{", *oam_write_lines("_pk", "_pe", apps, aff=aff),
                      "        } break;"]
    if not cases:
        return []
    return ["    for(int _pk=g_spool_start; _pk<g_spool_hw; _pk++){",
            "        int _pe=g_spool_entry+(_pk-g_spool_start);",
            "        switch(g_actors[_pk].model){", *cases, "        default: break;", "        }", "    }"]
