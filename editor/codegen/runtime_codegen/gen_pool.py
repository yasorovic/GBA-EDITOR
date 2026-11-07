"""runtime_codegen/gen_pool.py : allocation, spawn et symboles de script des instances de prefab.

`scene_pi` est la liste des pools d'une scène, lue de `oam_alloc.scene_oam_layout`."""
from __future__ import annotations

from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_actor_init import actor_init_lines
from codegen.runtime_codegen.gen_appearance import appearance_layout
from codegen.runtime_codegen.gen_actor_hierarchy import part_link_lines
from codegen.runtime_codegen.physics.body import without_scene_physics
from core.models.scene import Scene
from core.project import Project
from codegen.runtime_codegen.gen_affine import pool_affine
from codegen.runtime_codegen.gen_sfx_trigger import sfx_on_spawn_lines


def scene_pi(p: Project, scene: Scene) -> list[dict]:
    """La géométrie des pools de CETTE scène, lue de `scene_oam_layout` (source
    de vérité unique). `sym` est PRÉFIXÉ PAR LA SCÈNE
    (`<Scène>_<Prefab>`) : chaque scène compile ses unités de prefab contre sa
    propre plage, donc les appels `{sym}_init_script_state`/`{sym}_on_update` du main.c
    ciblent bien `actor_<Scène>_<Prefab>.c`."""
    lay = scene_oam_layout(p, scene)
    sh = lay.shared
    spool = ({"start": sh.start, "end": sh.end, "entry_start": sh.entry_start, "entries": sh.entries}
             if sh else None)
    return [
        {"prefab": pl.prefab if scene.physics_enabled else without_scene_physics(pl.prefab),
         "sym": pl.sym, "prefab_sym": pl.prefab_sym,
         # Un modèle que la scène fait naître : il vit dans `spool` et se reconnaît à `Actor.type_id`
         # (= `root_type_id`, ou `root_type_id + k` pour sa partie k).
         "shared": pl.shared, "root_type_id": pl.root_type_id, "spool": spool,
         "member_entries": pl.member_entries, "group": pl.group,
         # Les acteurs POSÉS qui sont des instances de ce modèle (indices dans `scene_actors`), chacun
         # avec son entrée d'état d'affichage. Premières lignes de la table du modèle ; ils gardent leur
         # emplacement et leur entrée de scène.
         "members": list(pl.members),
         "member_entries_of": [lay.placed_entry[j] for j in pl.members]}
        for pl in lay.pools
    ]


def dispatch_sym(scene, scene_actors: list, pi: list[dict]):
    """Le symbole C dont le code d'un acteur posé s'appelle : le sien, ou celui de son MODÈLE s'il en est
    une instance (un membre n'a pas de code à lui). Seuls les APPELS de scripts (événements,
    collisions, interaction) passent par ici ; `ACTOR_*` et les tables par acteur gardent le nom propre."""
    models = {scene_actors[j][0].name: pl["sym"] for pl in pi for j in pl["members"]}

    def sym_of(scene_name: str, actor_name: str) -> str:
        return models.get(actor_name) or scene_actor_sym(scene_name, actor_name)
    return sym_of


def _shared_spawn_head(s: str, pi: dict, grouped: bool) -> list[str]:
    """La tête du spawn d'un modèle du pool PARTAGÉ : l'emplacement d'une de ses instances posées
    détruite (le même modèle, donc le même code d'affichage), sinon le premier emplacement libre du
    pool de la scène, ou la première SÉRIE libre de la taille du groupe pour un modèle à parties (le script
    atteint la partie k par `self + k`). Le corps qui suit est celui des autres modèles : `if(_i >= 0) { … }`.

    `grouped` : la scène a un modèle à parties dans son pool. Une partie détruite dont la racine vit encore
    garde alors son emplacement (`spool_slot_free`), et pas seulement un `alive` nul."""
    nmem = len(pi["members"])
    group = pi["group"]
    busy = "!spool_slot_free(_k)" if grouped else "g_actors[_k].alive"
    L = [
        f"    int _i = -1, _e = -1, _n = {nmem};",
        *([f"    for(int _m=0; _m<{nmem}; _m++)",
           f"        if(!g_actors[g_model_{s}[_m].slot].alive) {{",
           f"            _n=_m; _i=g_model_{s}[_m].slot; _e=g_model_{s}[_m].entry; break;",
           "        }"] if nmem else []),
        "    if(_i < 0) {",
        "        int _k=g_spool_free;                      /* aucun libre en dessous du curseur */",
        f"        while(_k<g_spool_end && {busy}) _k++;",
        "        g_spool_free=_k;",
    ]
    if group > 1:
        L += [
            "        for(;;) {                                 /* la première série libre de la taille du groupe */",
            f"            if(_k+{group}>g_spool_end) {{ _k=g_spool_end; break; }}",
            "            int _j=0;",
            f"            while(_j<{group} && spool_slot_free(_k+_j)) _j++;",
            f"            if(_j=={group}) break;",
            "            _k+=_j+1;",
            "        }",
        ]
    L += [
        "        if(_k<g_spool_end) {",
        "            _i=_k; _e=(g_spool_entry>=0)?g_spool_entry+(_k-g_spool_start):-1;",
        f"            if(_k+{group}>g_actor_slot_end) g_actor_slot_end=_k+{group};",
        *(["            g_spool_free=_k+1;"] if group == 1 else []),
        "        }",
        "    }",
        "    (void)_e; (void)_n;",
        "    {",
        "        if(_i >= 0) {",
    ]
    return L


def section_spawn(pool_info: list[dict], p: Project, obj_layout,
                   actor_defined_events: dict[str, set[str]] | None = None) -> list[str]:
    """`pool_info` : les pools de LA scène courante (`scene_pi`), symboles
    déjà préfixés `<Scène>_<Prefab>`. `obj_layout` : le layout OBJ de CETTE
    scène — chaque scène résout l'index de banque de ses prefabs poolés dans son
    propre layout (plus de « scène d'ancrage »)."""
    if not pool_info:
        return []

    def _def(sym, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    L = ["/* ── Spawn helpers (pooled prefabs) ────────────────────── */"]
    _alay = appearance_layout(p, [], pool_info, obj_layout)   # mêmes numéros que scene_init
    for pi in pool_info:
        s, pf = pi["sym"], pi["prefab"]
        # `pool_init` sort du script Lua du prefab : sans script, il n'y a rien à initialiser ni à lier.
        from codegen.runtime_codegen.lua_compiler import prefab_lua_script, script_exports
        has_script = prefab_lua_script(p, pf) is not None
        script = pf.get_component("script")
        exports = script_exports(p, script.script) if script else {}
        if has_script:
            L.append(f"extern void {s}_init_script_state(Actor* self);")
        # Les instances POSÉES du modèle reçoivent leurs valeurs d'export à l'entrée de scène, par les
        # setters du modèle (comme une instance née d'un spawn avec une table).
        if pi["members"]:
            for _name, _meta in exports.items():
                from scripting.codegen import export_setter_c_type
                L.append(f"extern void {s}_set_{_name}(Actor* self, {export_setter_c_type(_meta['type'])} v);")
        for ev, sig in [
            ("on_start",           f"extern void {s}_on_start(Actor* self);"),
            ("on_update",          f"extern void {s}_on_update(Actor* self);"),
            ("on_late_update",     f"extern void {s}_on_late_update(Actor* self);"),
            ("on_collide",         f"extern void {s}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_enter", f"extern void {s}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_exit",  f"extern void {s}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_area_enter",      f"extern void {s}_on_area_enter(Actor* self, Area* area, u8 my_box);"),
            ("on_area_collide",    f"extern void {s}_on_area_collide(Actor* self, Area* area, u8 my_box);"),
            ("on_area_exit",       f"extern void {s}_on_area_exit(Actor* self, Area* area, u8 my_box);"),
            ("on_tile_collide",    f"extern void {s}_on_tile_collide(Actor* self, int normal_x, int normal_y);"),
            ("on_interact",        f"extern void {s}_on_interact(Actor* self, Actor* who);"),
            ("on_crushed",         f"extern void {s}_on_crushed(Actor* self, Actor* obstacle);"),
        ]:
            if _def(s, ev):
                L.append(sig)

        # La table du modèle : l'emplacement et l'entrée d'état de ses instances POSÉES. Le spawn la parcourt
        # avant le pool, `actor:count/get("M", i)` aussi.
        L.append(f"const ModelSlot g_model_{s}[{max(1, len(pi['members']))}] = {{")
        for _j, _ent in zip(pi["members"], pi["member_entries_of"]):
            L.append(f"    {{{_j}, {_ent}}},   /* posé */")
        if not pi["members"]:
            L.append("    {0, -1},   /* aucune instance posée : la table n'est pas lue */")
        L.append("};")
        if not pi["shared"]:
            continue            # aucun script de la scène ne le fait naître : pas de spawn
        init = f"actor_spawn_init_{s}" if exports else f"spawn_{s}"
        L += [
            # Rend un Actor* sur l'instance née : un handle
            # directement chaînable côté script, et NULL quand le pool est plein —
            # là où l'ancien -1, un entier, ressortait TOUJOURS vrai dans un test.
            f"Actor* {init}(int x, int y) {{",
            *_shared_spawn_head(s, pi, any(m["shared"] and m["group"] > 1 for m in pool_info)),
        ]

        identity = f"ACTOR_{s.upper()}"
        # Un spawn qui reprend un posé conserve son identité dans la scène.
        root_name = f"_n < {len(pi['members'])} ? _i : {identity}" if pi["members"] else identity
        L += actor_init_lines(
            p, pf, obj_layout, slot="_i", entry="_e" if pi["member_entries"][0] >= 0 else -1,
            name=root_name, type_id=pi["root_type_id"], position=("x", "y"), active=True,
            appearance_base=_alay.member_base.get((s, 0)), affine=pool_affine(p, pf, pf),
            indent="            ",
        )
        # Les parties prennent leur transform monde à la première composition, par leur lien.
        for k, part in enumerate(pf.children, start=1):
            entry = f"group_entry(_e, {k})" if pi["member_entries"][k] >= 0 else -1
            L += actor_init_lines(
                p, part, obj_layout, slot=f"group_slot(_i, {k})", entry=entry,
                name=identity, type_id=pi["root_type_id"] + k, position=(0, 0), active=True,
                appearance_base=_alay.member_base.get((s, k)), affine=pool_affine(p, pf, part),
                indent="            ", composed=True,
            )
        L += part_link_lines(pf, "_i", "            ")
        if has_script:
            L.append(f"            {s}_init_script_state(&g_actors[_i]);")
        if not exports:
            L += sfx_on_spawn_lines(p, pf, "            ")
            if _def(s, "on_start"):
                L.append(f"            actor_start(actor_ref_make(&g_actors[_i]), {s}_on_start);")
        L += [
            f"            return &g_actors[_i];",
            f"        }}",
            f"    }}",
            f"    return NULL;",
            f"}}",
            "",
        ]
        if exports:
            # Avec une table Lua, le script pose les exports entre ces deux appels.
            L += [f"void actor_spawn_start_{s}(Actor* actor) {{", "    if (!actor) return;"]
            L += sfx_on_spawn_lines(p, pf, "    ")
            if _def(s, "on_start"):
                L.append(f"    actor_start(actor_ref_make(actor), {s}_on_start);")
            L += ["}", f"Actor* spawn_{s}(int x, int y) {{",
                  f"    Actor* actor = {init}(x, y);",
                  f"    actor_spawn_start_{s}(actor);",
                  "    return actor;", "}", ""]
    return L
