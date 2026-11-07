"""Émission des Areas d'une scène : la table `g_areas` posée à l'entrée de la scène, et les contacts avec les acteurs qui les
touchent.

Une Area n'a pas de script : seul l'acteur qui la touche apprend le contact (`on_area_enter/collide/exit`). Un seul parcours des
emplacements (`SLOT_EACH`), posés ou nés, lit par type d'emplacement (`Actor.type_id`) les crochets et les rangs de boîtes que la
matrice des tags laisse toucher chaque Area, et appelle `area_contact_step` avec la mémoire du recouvrement de la frame précédente,
rangée par emplacement (règle « posé = spawné »).

Une Area sans déclencheur (`TriggerComponent`) n'entre dans aucun test : elle est dans `g_areas` pour ce qui la lira, et ne coûte
rien par frame."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_actor_hierarchy import local_transform
from codegen.runtime_codegen.gen_scene_query import actor_collision_shapes
from codegen.runtime_codegen.model_desc import BODY_MODE_CHARACTER, body_desc
from codegen.runtime_codegen.physics.body import physics_collider_entries
from codegen.runtime_codegen.shared_pool_gen import owners as model_owners, shared_models
from core.models.components import ForceFieldComponent, GravityOverrideComponent
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


def area_globals_lines(p, all_scene_data: list[dict], n_actors: int) -> list[str]:
    """`g_areas` : dimensionné sur la scène la plus fournie (une seule est vivante), une entrée au moins pour que le runtime
    s'y réfère toujours. `g_area_prev` : la mémoire des contacts, un u16 par emplacement et par Area à déclencheur ; `g_area_gen` :
    l'occupant à qui elle appartient (`Actor.gen`), pour qu'un emplacement réoccupé reparte de zéro."""
    n_areas = max((len(d["scene"].areas) for d in all_scene_data), default=0)
    n_trigger = max((len(trigger_areas(d["scene"])) for d in all_scene_data), default=0)
    return [f"Area g_areas[{max(1, n_areas)}] EWRAM_BSS;",
            f"u16 g_area_prev[{n_actors}][{max(1, n_trigger)}] EWRAM_BSS;   /* le recouvrement de la frame précédente, par emplacement */",
            f"u16 g_area_gen[{n_actors}] EWRAM_BSS;   /* à quel occupant appartient la mémoire de l'emplacement */"]


def effect_areas(scene) -> list[tuple[int, object]]:
    """(rang dans `g_areas`, Area) des Areas qui ont un effet physique : une forme, et un GravityOverrideComponent ou un
    ForceFieldComponent actif. Leur ordre est celui de la table `_fx` ; la dernière zone de gravité l'emporte."""
    return [(i, a) for i, a in enumerate(scene.areas) if a.shape() is not None
            and (a.effect(GravityOverrideComponent) or a.effect(ForceFieldComponent))]


def effects_affect_characters(scene) -> bool:
    """Une zone de la scène agit-elle sur les CharacterBody ? Sans cela, ils ne passent jamais par `area_effects_apply` pour
    la force (la gravité de zone, elle, les atteint s'ils suivent la gravité de scène)."""
    return any(a.effect(ForceFieldComponent).affects_characters
               for _i, a in effect_areas(scene) if a.effect(ForceFieldComponent))


def effect_table_lines(scene) -> list[str]:
    """La table `const` `_fx` des zones d'effet de la scène (Q8), posée en tête du bloc de mouvement. Vide sans zone : le C émis
    d'une scène sans effet reste celui d'avant."""
    rows = effect_areas(scene)
    if not rows:
        return []
    out = []
    for i, area in rows:
        gravity, force = area.effect(GravityOverrideComponent), area.effect(ForceFieldComponent)
        flags = (("AREAFX_GRAVITY" if gravity else "0"),
                 ("AREAFX_CHARACTER" if force and force.affects_characters else "0"))
        gx, gy = (round(gravity.gravity_x * 256), round(gravity.gravity_y * 256)) if gravity else (0, 0)
        fx, fy = (round(force.force_x * 256), round(force.force_y * 256)) if force else (0, 0)
        buoyancy = round(force.buoyancy * 256) if force else 0
        turbulence = round(force.turbulence * 256) if force else 0
        retain = round((1.0 - force.drag) * 256) if force else 256
        out.append(f"        {{&g_areas[{i}],{gx},{gy},{fx},{fy},{buoyancy},{turbulence},{retain},"
                   f"{'|'.join(f for f in flags if f != '0') or '0'}}},")
    return [f"    static const AreaEffect _fx[{len(rows)}]={{", *out, "    };"]


def type_owners(lay, scene_actors, pi, placed_scripts=None, parts: bool = True) -> dict[int, tuple[object, str | None]]:
    """{type d'emplacement: (porteur, symbole du script)} : les copies d'un type ont les mêmes boîtes et le même code, le premier
    porteur les représente. `placed_scripts` : le symbole du code Lua de chaque posé (None sans script), aligné sur
    `scene_actors` ; un modèle du pool a le sien. `parts` : inclure les parties d'un modèle (`root_type_id + k`), qui ont leurs
    boîtes propres et réagissent avec le script de leur racine."""
    out: dict[int, tuple[object, str | None]] = {}
    scripts = placed_scripts or [None] * len(scene_actors)
    for (actor, _sprite), kind, script in zip(scene_actors, lay.placed_type_ids, scripts):
        out.setdefault(kind, (actor, script))
    for m in shared_models(pi):
        for k, owner in enumerate(model_owners(m)[:m["group"] if parts else 1]):
            out.setdefault(m["root_type_id"] + k, (owner, m["sym"]))
    return out


def effect_rank_lines(scene, lay, scene_actors, pi) -> list[str]:
    """`_fx_rank` : par type d'emplacement, le rang de la boîte de physique du corps qui subit une zone, 255 pour un type qui n'en
    subit pas (sans corps, sans boîte de physique, ou qu'aucune zone de la scène n'atteint). Vide si aucun type n'en subit : la
    passe de mouvement émise est alors celle d'une scène sans zone. Les parties d'un modèle suivent leur racine et n'ont pas de
    corps (cf. `model_desc`)."""
    zones = effect_areas(scene)
    if not zones:
        return []
    has_gravity_zone = any(a.effect(GravityOverrideComponent) for _i, a in zones)
    has_force_zone = any(a.effect(ForceFieldComponent) for _i, a in zones)
    characters_affected = effects_affect_characters(scene)
    ranks = [255] * lay.type_table_size
    for kind, (owner, _script) in type_owners(lay, scene_actors, pi, parts=False).items():
        mode, _sleep, scale = body_desc(owner)
        colliders = physics_collider_entries(owner)
        if not mode or not colliders:
            continue
        follows, is_character = scale != 0, mode == BODY_MODE_CHARACTER
        if (has_gravity_zone and follows) or (has_force_zone and (characters_affected or not is_character)):
            ranks[kind] = colliders[0][0]
    if all(r == 255 for r in ranks):
        return []
    return [f"    static const u8 _fx_rank[{len(ranks)}]={{{','.join(map(str, ranks))}}};"]


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
    L = ["    g_fx_rng=1;","    for(unsigned _i=0;_i<sizeof(g_areas)/sizeof(g_areas[0]);_i++) g_areas[_i]=(Area){0};",
         "    for(unsigned _i=0;_i<sizeof(g_area_prev)/sizeof(u16);_i++) ((u16*)g_area_prev)[_i]=0;"]
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
    (`slot_compose` : position = parent + R(rotation)·S(échelle)·local), sans rotation ni échelle propres. Appelée APRÈS
    la composition des acteurs (`slot_compose_all`), qui a mis à jour les parents (et les parents de parents). Une Area dont le parent est inactif ou
    détruit est tenue (`held`) : elle ne touche personne. Le local est une constante du build, tirée de la pose authorée."""
    parents = _parent_slots(scene, scene_actors, actor_offset)
    if not parents:
        return []
    by_slot = {actor_offset + j: a for j, (a, _) in enumerate(scene_actors)}
    L = ["    /* Areas that follow an actor — after the actors' own composition. */"]
    for i, slot in sorted(parents.items()):
        area, par = scene.areas[i], by_slot[slot]
        ox, oy, *_ = local_transform(area, par, int(par.x), int(par.y))
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


def area_contact_lines(p, scene, scene_actors: list, pi: list[dict], placed_scripts: list, has_event) -> list[str]:
    """Les contacts des Areas à déclencheur avec les emplacements dont le script répond, posés ou nés : un parcours des
    emplacements, et par type une ligne de crochets et les rangs de boîtes que la matrice des tags laisse toucher chaque Area
    (cuits au build). Un type sans crochet d'Area, ou dont aucun tag ne rencontre celui d'une Area, n'est pas émis du tout.

    `placed_scripts` : le symbole du code Lua de chaque posé (None sans script), aligné sur `scene_actors` ; un modèle du pool a
    le sien. `has_event(symbole, événement)` dit si le script définit le crochet."""
    areas = trigger_areas(scene)
    if not areas:
        return []
    lay = scene_oam_layout(p, scene)
    kinds, handlers, allowed = [], [], []
    for kind, (owner, script) in sorted(type_owners(lay, scene_actors, pi, placed_scripts).items()):
        on = [f"{script}_{ev}" if script and has_event(script, ev) else "0" for ev in AREA_EVENTS]
        masks = [area_mask(area, owner, p.settings) for _ai, area in areas]
        if any(h != "0" for h in on) and any(masks):
            kinds.append(kind)
            handlers.append("{" + ",".join(on) + "}")
            allowed.append("{" + ",".join(map(str, masks)) + "}")
    if not kinds:
        return []
    index = {k: i for i, k in enumerate(kinds)}
    by_kind = ",".join(str(index.get(k, 255)) for k in range(lay.type_table_size))
    steps = [f"            if(_ar_allowed[_i][{c}]){{ debug_physics_area_test(); "
             f"area_contact_step(&g_areas[{ai}],_a,_ar_allowed[_i][{c}],_ar_on[_i],&g_area_prev[_k][{c}]); }}"
             for c, (ai, _area) in enumerate(areas)]
    return ["    /* Areas à déclencheur : un parcours des emplacements, posés ou nés, crochets et masques lus par type */",
            "    {",
            f"        static const u8 _ar_type[{lay.type_table_size}]={{{by_kind}}};",
            f"        static const AreaFn _ar_on[{len(kinds)}][3]={{{','.join(handlers)}}};",
            f"        static const u16 _ar_allowed[{len(kinds)}][{len(areas)}]={{{','.join(allowed)}}};",
            "        SLOT_EACH(_k){",
            "            Actor* _a=&g_actors[_k]; u8 _i=_ar_type[_a->type_id];",
            "            if(_i==255) continue;",
            f"            if(g_area_gen[_k]!=_a->gen){{ g_area_gen[_k]=_a->gen; "
            f"for(int _c=0;_c<{len(areas)};_c++) g_area_prev[_k][_c]=0; }}",
            *steps,
            "        }",
            "    }"]
