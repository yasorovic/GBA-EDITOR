"""Émission des Areas d'une scène : la table `g_areas` posée à l'entrée de la scène, et les contacts avec les acteurs qui les
touchent.

Une Area n'a pas de script : seul l'acteur qui la touche apprend le contact (`on_area_enter/collide/exit`). Les acteurs posés
passent par une table `const` de couples, ceux du pool par une boucle sur leurs emplacements : les deux appellent le même
`area_contact_step` du runtime, avec leur propre mémoire du recouvrement de la frame précédente.

Une Area sans déclencheur (`TriggerComponent`) n'entre dans aucun test : elle est dans `g_areas` pour ce qui la lira, et ne coûte
rien par frame."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.runtime_codegen.gen_pool import world_to_local_offset
from codegen.runtime_codegen.gen_scene_query import actor_collision_shapes
from core.models.field_value import FieldValue as _FV, var_names_from_project
from core.models.settings import tags_collide
from scripting.api import AREA_EVENTS


def trigger_areas(scene) -> list[tuple[int, object]]:
    """(rang dans `g_areas`, Area) des Areas qui préviennent les scripts : un déclencheur actif ET une forme."""
    return [(i, a) for i, a in enumerate(scene.areas) if a.is_trigger() and a.shape() is not None]


def area_mask(area, owner, settings) -> int:
    """Les rangs de boîtes de `owner` (acteur ou prefab) dont le tag rencontre celui de la forme de l'Area, cuits au build.

    Le rang est canonique, comme dans `collision_pair_mask` : deux boîtes de même tag comptent pour une (la première)."""
    shape = area.shape()
    if shape is None:
        return 0
    area_tag = shape.tag or "body"
    boxes = actor_collision_shapes(owner)
    mask = 0
    for j, box in enumerate(boxes):
        tag = box.tag or "body"
        canonical = next(k for k, prior in enumerate(boxes[:j + 1]) if (prior.tag or "body") == tag)
        if tags_collide(settings, area_tag, tag):
            mask |= 1 << canonical
    return mask


def area_globals_lines(p, all_scene_data: list[dict]) -> list[str]:
    """`g_areas` : dimensionné sur la scène la plus fournie (une seule est vivante), une entrée au moins pour que le runtime
    s'y réfère toujours. `g_area_prev` : la mémoire des couples posés (un u16 par couple), au plus Areas à déclencheur ×
    acteurs posés."""
    n_areas = max((len(d["scene"].areas) for d in all_scene_data), default=0)
    n_prev = max((len(trigger_areas(d["scene"])) * len(d["scene_actors"]) for d in all_scene_data), default=0)
    return [f"Area g_areas[{max(1, n_areas)}] EWRAM_BSS;",
            f"u16 g_area_prev[{max(1, n_prev)}] EWRAM_BSS;   /* le recouvrement de la frame précédente, par couple posé */"]


def _parent_slots(scene, scene_actors: list, actor_offset: int) -> dict:
    """{rang de l'Area dans `g_areas`: emplacement de son parent dans `g_actors`} : les Areas dont le parent nomme un acteur posé
    de la scène (un parent inconnu est refusé avant, par le validateur)."""
    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    return {i: idx_of[a.parent] for i, a in enumerate(scene.areas) if a.parent and a.parent in idx_of}


def area_init_lines(p, scene, scene_actors: list, actor_offset: int) -> list[str]:
    """Pose les Areas de la scène dans `g_areas` à son entrée, et remet à zéro la mémoire des contacts."""
    if not scene.areas:
        return []
    names = var_names_from_project(p)
    parents = _parent_slots(scene, scene_actors, actor_offset)
    L = ["    for(unsigned _i=0;_i<sizeof(g_areas)/sizeof(g_areas[0]);_i++) g_areas[_i]=(Area){0};",
         "    for(unsigned _i=0;_i<sizeof(g_area_prev)/sizeof(g_area_prev[0]);_i++) g_area_prev[_i]=0;"]
    for i, area in enumerate(scene.areas):
        a = f"g_areas[{i}]"
        L.append(f"    {a}.x=({int(area.x)})<<8; {a}.y=({int(area.y)})<<8; {a}.active={1 if area.active else 0};"
                 + (f" {a}.parent={parents[i] + 1};" if i in parents else ""))
        shape = area.shape()
        if shape is None:
            continue         # `box.active` reste 0 : l'Area ne touche personne
        tag = "BOXTAG_" + c_sym(shape.tag or "body").upper()
        x, y = _FV.parse(shape.x, names).c_expr(), _FV.parse(shape.y, names).c_expr()
        w, h = _FV.parse(shape.w, names).c_expr(), _FV.parse(shape.h, names).c_expr()
        L += [f"    {a}.box.x=(s8){x}; {a}.box.y=(s8){y}; {a}.box.w=(u8){w}; {a}.box.h=(u8){h};",
              f"    {a}.box.solid=0; {a}.box.active=1; {a}.box.tag={tag};"]
    return L


def area_parent_lines(scene, scene_actors: list, actor_offset: int) -> list[str]:
    """Recompose, chaque frame, la position des Areas qui suivent un acteur : la formule des acteurs enfants
    (`parent_compose_lines` : position = parent + R(rotation)·S(échelle)·local), sans rotation ni échelle propres. Appelée APRÈS
    la composition des acteurs, qui a mis à jour les parents (et les parents de parents). Une Area dont le parent est inactif ou
    détruit est tenue (`held`) : elle ne touche personne. Le local est une constante du build, tirée de la pose authorée."""
    parents = _parent_slots(scene, scene_actors, actor_offset)
    if not parents:
        return []
    by_slot = {actor_offset + j: a for j, (a, _) in enumerate(scene_actors)}
    L = ["    /* Areas that follow an actor — after the actors' own composition. */"]
    for i, slot in sorted(parents.items()):
        area, par = scene.areas[i], by_slot[slot]
        ox, oy = world_to_local_offset(par, area.x, area.y)
        L += [f"    {{   /* {area.name} in the frame of {par.name} */",
              f"        int _pr = g_actors[{slot}].rotation;",
              f"        int _px = g_actors[{slot}].scale_x, _py = g_actors[{slot}].scale_y;",
              f"        int _co, _si; gba_sincos(_pr, &_si, &_co);",
              f"        int _lx = ({ox} * _px) >> 8, _ly = ({oy} * _py) >> 8;",
              f"        g_areas[{i}].x = g_actors[{slot}].x + ((_lx * _co - _ly * _si) >> 8);",
              f"        g_areas[{i}].y = g_actors[{slot}].y + ((_lx * _si + _ly * _co) >> 8);",
              f"        g_areas[{i}].held = !(g_actors[{slot}].active && g_actors[{slot}].alive);",
              "    }"]
    return L


def area_pair_lines(p, scene, scene_actors: list, actor_offset: int, lua_idx: set, has_event, dispatch_sym,
                    areas: list) -> list[str]:
    """Les contacts des Areas à déclencheur avec les acteurs POSÉS dont le script répond : une table `const` de couples et une
    boucle. Un couple sans handler d'un côté comme de l'autre, ou dont aucun tag ne se rencontre, n'est pas émis du tout."""
    rows = []
    for ai, area in areas:
        for j, (actor, _sprite) in enumerate(scene_actors):
            idx = actor_offset + j
            if idx not in lua_idx:
                continue
            s = dispatch_sym(scene.name, actor.name)
            handlers = [f"{s}_{ev}" if has_event(s, ev) else "0" for ev in AREA_EVENTS]
            allowed = area_mask(area, actor, p.settings)
            if allowed and any(h != "0" for h in handlers):
                rows.append((ai, idx, allowed, handlers))
    if not rows:
        return []
    return [f"    static const AreaContact _area_pairs[{len(rows)}]={{",
            *[f"        {{&g_areas[{ai}],{idx},{allowed},{{{','.join(h)}}}}}," for ai, idx, allowed, h in rows],
            "    };",
            f"    for(u16 _k=0;_k<{len(rows)};_k++){{ debug_physics_area_test(); "
            "area_contact_run(&_area_pairs[_k],&g_area_prev[_k]); }"]
