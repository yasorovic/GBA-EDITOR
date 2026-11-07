"""runtime_codegen/gen_pool.py : le C des instances d'un modèle de prefab : le spawn, les liens de la hiérarchie
(parent, enfant, `actor_link_slot`) et le nom du symbole qui répond d'un acteur.

`scene_pi` est la liste des pools d'une scène, lue de `oam_alloc.scene_oam_layout`."""
from __future__ import annotations

from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_actor_init import actor_init_lines
from codegen.runtime_codegen.gen_appearance import appearance_layout
from codegen.runtime_codegen.gen_scene_query import parent_depths
from codegen.runtime_codegen.physics.body import without_scene_physics
from core.models.field_value import (
    number_value as _number_value,
)
from core.models.scene import Scene
from core.project import Project
import math
from codegen.runtime_codegen.gen_affine import pool_affine
from codegen.runtime_codegen.gen_sfx_trigger import sfx_on_spawn_lines


def scene_pi(p: Project, scene: Scene) -> list[dict]:
    """La géométrie des pools de CETTE scène, lue de `scene_oam_layout` (source
    de vérité unique). `sym` est PRÉFIXÉ PAR LA SCÈNE
    (`<Scène>_<Prefab>`) : chaque scène compile ses unités de prefab contre sa
    propre plage, donc les appels `{sym}_pool_init`/`{sym}_on_update` du main.c
    ciblent bien `actor_<Scène>_<Prefab>.c`."""
    lay = scene_oam_layout(p, scene)
    sh = lay.shared
    spool = ({"start": sh.start, "end": sh.end, "entry_start": sh.entry_start, "entries": sh.entries}
             if sh else None)
    return [
        {"prefab": pl.prefab if scene.physics_enabled else without_scene_physics(pl.prefab),
         "sym": pl.sym, "prefab_sym": pl.prefab_sym,
         # Un modèle que la scène fait naître : il vit dans `spool` et se reconnaît à `Actor.model`
         # (= `model_id`, ou `model_id + k` pour sa partie k).
         "shared": pl.shared, "model_id": pl.model_id, "spool": spool,
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
        f"            if(_k+{group}>g_spool_hw) g_spool_hw=_k+{group};",
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
            L.append(f"extern void {s}_pool_init(Actor* self);")
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
            name=root_name, model=pi["model_id"], position=("x", "y"), active=True,
            appearance_base=_alay.member_base.get((s, 0)), affine=pool_affine(p, pf, pf),
            indent="            ",
        )
        # Les parties prennent leur transform monde à la première composition, par leur lien.
        for k, part in enumerate(pf.children, start=1):
            entry = f"group_entry(_e, {k})" if pi["member_entries"][k] >= 0 else -1
            L += actor_init_lines(
                p, part, obj_layout, slot=f"group_slot(_i, {k})", entry=entry,
                name=identity, model=pi["model_id"] + k, position=(0, 0), active=True,
                appearance_base=_alay.member_base.get((s, k)), affine=pool_affine(p, pf, part),
                indent="            ", composed=True,
            )
        L += part_link_lines(pf, "_i", "            ")
        if has_script:
            L.append(f"            {s}_pool_init(&g_actors[_i]);")
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


def _local_transform(child, ref, ref_x: int, ref_y: int) -> tuple[int, int, int, int, int]:
    """Le transform LOCAL de `child` dans le repère de `ref` : (ox, oy Q8, rotation en degrés, sx, sy Q8).

    L'auteur pose en coordonnées MONDE ; le build en tire le local, et la composition du runtime (`slot_compose`), appliquée
    à la pose authorée du parent, redonne exactement la pose authorée de l'enfant : la scène de l'éditeur est la frame 0 du
    jeu. C'est l'inverse de la composition : on défait la rotation du parent, puis son échelle. `ref_x`, `ref_y` : la
    position du parent (0, 0 pour la racine d'un prefab, posée à l'origine du template). Tout reste en Q8 jusqu'à l'OAM :
    un arrondi par niveau ferait dériver un bras d'un pixel par cran de profondeur."""
    p_rot = float(_number_value(getattr(ref, "rotation", 0)) or 0)
    p_sx = float(_number_value(getattr(ref, "scale_x", 1.0), ref_divisor=100) or 1.0) or 1.0
    p_sy = float(_number_value(getattr(ref, "scale_y", 1.0), ref_divisor=100) or 1.0) or 1.0
    dx, dy = float(int(child.x) - ref_x), float(int(child.y) - ref_y)
    th = math.radians(-p_rot)
    ux = dx * math.cos(th) - dy * math.sin(th)
    uy = dx * math.sin(th) + dy * math.cos(th)
    rot = int(_number_value(getattr(child, "rotation", 0)) or 0) - int(round(p_rot))
    sx = int(round(float(_number_value(getattr(child, "scale_x", 1.0), ref_divisor=100) or 1.0) / p_sx * 256))
    sy = int(round(float(_number_value(getattr(child, "scale_y", 1.0), ref_divisor=100) or 1.0) / p_sy * 256))
    return int(round(ux / p_sx * 256)), int(round(uy / p_sy * 256)), rot, sx, sy


def _link_line(indent: str, slot, parent, depth: int, child, local) -> str:
    vis = 1 if getattr(child, "visible", True) else 0
    return f"{indent}actor_link_slot({slot}, {parent}, {depth}, {vis}, {', '.join(map(str, local))});"


def _part_parents(pf) -> list[tuple]:
    """Les parties d'un prefab : (rang k, partie, rang de sa partie parente (0 = la racine), profondeur)."""
    parts = list(getattr(pf, "children", []) or [])
    rank = {pt.name: k for k, pt in enumerate(parts, start=1)}
    par_of = {k: rank.get(getattr(pt, "parent", None) or "", 0) for k, pt in enumerate(parts, start=1)}
    out = []
    for k, pt in enumerate(parts, start=1):
        depth, cur = 0, k
        while cur and depth <= len(parts):       # borne : une chaîne de parties ne revient pas sur elle-même
            depth, cur = depth + 1, par_of[cur]
        out.append((k, pt, par_of[k], depth))
    return out


def part_link_lines(pf, root: str, indent: str) -> list[str]:
    """Les liens des parties d'un modèle né à l'emplacement `root` (une expression C), après leur construction : le
    parent est une autre partie, sinon la racine, et le local se tire de la pose authorée de la partie, dans le monde du
    template posé à l'origine (la racine d'un prefab n'a pas de pose : `spawn(x, y)` décide où)."""
    by_rank = {k: pt for k, pt in enumerate(pf.children, start=1)}
    L = []
    for k, part, p_off, depth in _part_parents(pf):
        ref = by_rank.get(p_off, pf)
        ref_xy = (int(ref.x), int(ref.y)) if p_off else (0, 0)
        L.append(_link_line(indent, f"group_slot({root}, {k})", f"group_slot({root}, {p_off})" if p_off else root,
                            depth, part, _local_transform(part, ref, *ref_xy)))
    return L


def link_depth(scene_actors: list, pi: list[dict]) -> int:
    """La profondeur maximale de la hiérarchie d'une scène, posés et parties des modèles qui y naissent : le nombre de
    passes de `slot_compose_all` (`g_slot_depth`). 0 : aucune hiérarchie, ni composition ni cascade."""
    depths, _errs = parent_depths(scene_actors)
    d = max(depths.values(), default=0)
    for m in pi:
        if m["shared"]:
            d = max([d] + [dep for *_, dep in _part_parents(m["prefab"])])
    return d


def placed_link_lines(scene_actors: list, actor_offset: int) -> list[str]:
    """Les liens des acteurs POSÉS qui ont un parent de scène, après leur construction (`scene_init`) : le parent,
    la profondeur et le local, tiré de la pose authorée (`_local_transform`). Un parent inconnu ou un cycle ont été
    refusés avant (`parent_depths`)."""
    depths, _errs = parent_depths(scene_actors)
    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    by_name = {a.name: a for a, _ in scene_actors}
    L = []
    for j, (a, _) in enumerate(scene_actors):
        par = by_name.get(getattr(a, "parent", None) or "")
        if par is None or a.name not in depths:
            continue
        L.append(_link_line("    ", actor_offset + j, idx_of[par.name], depths[a.name], a,
                            _local_transform(a, par, int(par.x), int(par.y))))
    return L
