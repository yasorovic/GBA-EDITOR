"""runtime_codegen/shared_pool_gen.py : le C qui parcourt le pool PARTAGÉ d'une scène.

Un emplacement du pool accueille n'importe quel modèle simple (`oam_alloc.is_plain_model`) : le build ne
peut donc plus dérouler, modèle par modèle, des boucles sur des emplacements qu'il connaît. Chaque
passe qui lui reste propre (contacts avec les posés) devient UNE boucle sur les emplacements
utilisés (`POOL_EACH` : de `g_spool_start` à `g_spool_hw`, le plus haut utilisé, en sautant les blocs de 32
emplacements sans vivant), avec un `switch` sur `Actor.model` : le code du modèle est appelé, ou ses constantes
de sprite sont écrites, par le cas qui le concerne.

Un modèle à PARTIES occupe un groupe d'emplacements contigus : `Actor.model` y est un TYPE d'emplacement, la
racine portant l'identité du modèle (`model_id`) et sa partie k cette identité + k. Les collisions ont un cas par
type (une partie réagit avec le script de sa racine, comme dans une réserve à part).
Les passes déjà communes aux posés et aux nés lisent le descripteur de modèle (`model_desc`) et ne vivent plus ici.

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


def trim_lines(pi: list[dict]) -> list[str]:
    """Rabat le plus haut emplacement utilisé sur le dernier occupé : après une pluie de balles, les boucles
    du tick ne parcourent plus des emplacements vides."""
    if not shared_models(pi):
        return []
    return ["    while(g_spool_hw>g_spool_start && !g_actors[g_spool_hw-1].alive) g_spool_hw--;"]


def collision_lines(pi: list[dict], size: int, col_scene: list, can_collide, has_event, has_col_event,
                    dispatch_sym, lua_idx: set, scene_name: str, contact_lines, collision_mask=None) -> list[str]:
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
                "                ",
                collision_mask(m["prefab"], sactor) if collision_mask else 0xFFFF)
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
