"""runtime_codegen/model_desc.py : la table du DESCRIPTEUR DE MODÈLE d'une scène (`ModelDesc`, cf. actor_types_static.h).

Une ligne par type d'emplacement (`Actor.type_id`) : le type 0, ceux du pool partagé (`root_type_id`, puis `root_type_id + k`
pour la partie k), puis ceux des acteurs posés (`OamLayout.placed_type_ids`). Le runtime lit la ligne de l'emplacement,
qu'il soit posé ou né : c'est ce qui permet d'écrire un module une seule fois (règle « posé = spawné »).

La table porte le mouvement automatique et le sommeil (`physics.motion`), la résolution contre la carte de collision
(`physics.character`), les crochets d'image et de contact des scripts (`physics.contacts`), le SoundFx déclenché par
l'input et l'interacteur (`interact_gen`) ; chaque module migré y ajoute ses champs. Le plan mémoire peut la placer en IWRAM pour accélérer les lectures."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.iwram_plan import iwram_table
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.physics.body import (
    physics_body, physics_body_mode, physics_collider_mask, uses_character_solver,
)
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import (
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID, SFX_AUTO_TRIGGERS,
)

# Les valeurs de `ModelDesc.body_mode` (enum `BODY_MODE_*` d'actor_types_static.h).
BODY_MODE_CHARACTER = 1
BODY_MODE_RIGID = 3
# Les crochets de contact du script d'un type, dans l'ordre de `ModelDesc.on_contact`.
CONTACT_EVENTS = ("on_collision_enter", "on_collide", "on_collision_exit")
_BODY_MODE = {PHYSICS_BODY_CHARACTER: BODY_MODE_CHARACTER, PHYSICS_BODY_KINEMATIC: 2, PHYSICS_BODY_RIGID: BODY_MODE_RIGID}


def model_desc_sym(scene) -> str:
    return f"g_model_desc_{c_sym(scene.name)}"


def body_desc(owner) -> tuple[int, int, int]:
    """(body_mode, can_sleep, gravity_scale Q8) d'un porteur. Character et Kinematic ignorent la gravité de scène sans
    `use_scene_gravity` (un acteur sans corps, Character par repli, l'ignore aussi) ; un Rigid la suit toujours."""
    mode = physics_body_mode(owner)
    body = physics_body(owner)
    if mode in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC) and not (body and body.use_scene_gravity):
        scale = 0
    else:
        scale = round((body.gravity_scale if body else 1.0) * 256)
    return _BODY_MODE.get(mode, 0), 1 if body is None or body.can_sleep else 0, scale


def tile_mask(owner) -> int:
    """Les rangs des boîtes d'un porteur résolues contre la carte de collision, 0 s'il ne la rencontre pas."""
    return physics_collider_mask(owner, map_only=True) if uses_character_solver(owner) else 0


def scene_owners(scene_actors, pi) -> list:
    """Les porteurs que le descripteur décrit : les acteurs posés, puis les racines des modèles du pool partagé."""
    return [actor for actor, _sprite in scene_actors] + [m["prefab"] for m in shared_models(pi)]


def scene_has_moving_bodies(scene_actors, pi) -> bool:
    """Un corps de la scène, posé ou modèle du pool, reçoit le mouvement automatique : la table et la passe existent."""
    return any(physics_body_mode(o) in _BODY_MODE for o in scene_owners(scene_actors, pi))


def each_slot(step: str) -> list[str]:
    """`step` (qui lit `_a`) pour chaque emplacement actif de la scène, posé ou né : un seul parcours (`SLOT_EACH`)."""
    return ["    SLOT_EACH(_k){", "        Actor* _a=&g_actors[_k];", f"        if(_a->active) {step}", "    }"]


def sfx_input_desc(p, owner, input_layout) -> tuple[str, int, str] | None:
    """(effet, volume, masque C) du SoundFxComponent d'un porteur déclenché par un bouton ou une action nommée, ou None.
    Les déclencheurs automatiques (`on_spawn`, `on_destroy`, `on_interact`) et `manual` ont leur propre site."""
    from scripting.api import key_constant
    sfx_sym, sfx_vol, trigger = sfx_trigger_info(p, owner)
    if not sfx_sym or trigger == "manual" or trigger in SFX_AUTO_TRIGGERS:
        return None
    return sfx_sym, sfx_vol, input_layout.masks.get(trigger, key_constant(trigger))


def hook_pass_lines(scene, pi, placed_scripts, has_event, event: str) -> list[str]:
    """`event` (`on_update` ou `on_late_update`) de chaque emplacement actif dont le type le définit, posé ou né : le
    crochet se lit dans la ligne du type. Rien si aucun script de la scène ne le définit."""
    if not (any(s and has_event(s, event) for s in placed_scripts)
            or any(has_event(m["sym"], event) for m in shared_models(pi))):
        return []
    return each_slot(f"{{ const ModelDesc* _d=&{model_desc_sym(scene)}[_a->type_id]; if(_d->{event}) _d->{event}(_a); }}")


def sfx_input_pass_lines(p, scene, scene_actors, pi, input_layout) -> list[str]:
    """Le SoundFx déclenché par un bouton ou une action, pour TOUS les acteurs, scriptés ou non (c'est ce qui permet à
    un item de menu de répondre à un bouton sans une ligne de Lua). Un test par masque distinct ; sur la frame de
    l'appui seulement, chaque emplacement actif dont le type a ce masque joue son effet, une fois par instance.
    `trigger` porte un nom de bouton OU d'accord déclaré (la liste de `input:pressed(nom)`) : deux types sur le même
    masque partagent le même test."""
    placed = [sfx_input_desc(p, actor, input_layout) for actor, _sprite in scene_actors]
    pool = [sfx_input_desc(p, m["prefab"], input_layout) for m in shared_models(pi)]
    out = []
    for mask in dict.fromkeys(d[2] for d in placed + pool if d):
        step = (f"{{ const ModelDesc* _d=&{model_desc_sym(scene)}[_a->type_id]; "
                f"if(_d->sfx_input==({mask})) sfx_play(_d->sfx,_d->sfx_vol,0); }}")
        out += [f"    if(input_pressed({mask})){{", *("    " + line for line in each_slot(step)), "    }"]
    return out


def model_desc_lines(p, scene, scene_actors, pi, placed_scripts=None, has_event=None, input_layout=None) -> list[str]:
    """La définition C de `g_model_desc_<Scène>`, ou rien si la scène n'a ni acteur posé ni modèle du pool.

    `placed_scripts` : le symbole du code Lua de chaque posé (None sans script), aligné sur `scene_actors` ; un modèle du
    pool a le sien (`sym`). `has_event(symbole, événement)` dit si le script définit le crochet. Sans eux, aucun crochet.
    `input_layout` donne les masques des déclencheurs SoundFx par l'input ; sans lui, aucun.

    Les posés d'un même type (variantes d'un prefab) peuvent différer par `solid` : leur `tile_mask` est l'union des
    leurs, la résolution relit `solid` boîte par boîte. Une ligne s'écrit en initialiseurs désignés, ses champs nuls omis."""
    if not scene_owners(scene_actors, pi):
        return []
    has_event = has_event or (lambda _s, _ev: False)
    lay = scene_oam_layout(p, scene)

    def row(owner, script, has_entry: bool) -> dict:
        mode, sleep, scale = body_desc(owner)
        out = {"body_mode": mode, "can_sleep": sleep, "tile_mask": tile_mask(owner), "gravity_scale": scale}
        if getattr(owner, "is_player", False):
            out["interactor"] = 1 if has_entry else 2
        sfx = sfx_input_desc(p, owner, input_layout) if input_layout is not None else None
        if sfx:
            out["sfx"], out["sfx_vol"], out["sfx_input"] = sfx
        for event, field in (("on_tile_collide", "on_tile"), ("on_update", "on_update"),
                             ("on_late_update", "on_late_update")):
            if script and has_event(script, event):
                out[field] = f"{script}_{event}"
        if script and physics_body_mode(owner) == PHYSICS_BODY_CHARACTER and has_event(script, "on_crushed"):
            out["on_crushed"] = f"{script}_on_crushed"
        contact = [f"{script}_{ev}" if script and has_event(script, ev) else "0" for ev in CONTACT_EVENTS]
        if any(fn != "0" for fn in contact):
            out["on_contact"] = "{" + ",".join(contact) + "}"
        return out

    rows: list = [({}, "aucun type")] * lay.type_table_size
    for m in shared_models(pi):
        # Une partie suit sa racine : ni mouvement, ni résolution, ni script propres...
        rows[m["root_type_id"]] = (row(m["prefab"], m["sym"], m["member_entries"][0] >= 0), f"né : {m['prefab'].name}")
        # ... sauf pour les contacts : une partie réagit avec le script de sa racine (`physics.contacts`).
        contact = rows[m["root_type_id"]][0].get("on_contact")
        for k in range(1, m["group"]):
            rows[m["root_type_id"] + k] = ({"on_contact": contact} if contact else {}, f"partie {k} : {m['prefab'].name}")
    # Une copie posée identique au prefab porte le `root_type_id` du modèle né (`pool_model.placed_types`) : sa ligne est
    # celle du modèle, au masque de carte près (union, `solid` est un champ d'emplacement).
    scripts = placed_scripts or [None] * len(scene_actors)
    masks: dict[int, int] = {m["root_type_id"]: tile_mask(m["prefab"]) for m in shared_models(pi)}
    for (actor, _sprite), kind in zip(scene_actors, lay.placed_type_ids):
        masks[kind] = masks.get(kind, 0) | tile_mask(actor)
    for (actor, _sprite), kind, script, entry in zip(scene_actors, lay.placed_type_ids, scripts, lay.placed_entry):
        label = rows[kind][1] if rows[kind][0] else f"posé : {actor.name}"
        rows[kind] = (dict(row(actor, script, entry >= 0), tile_mask=masks[kind]), label)
    body = [f"    {{{','.join(f'.{k}={v}' for k, v in values.items() if v not in (0, '0')) or '0'}}},   /* {kind} {label} */"
            for kind, (values, label) in enumerate(rows)]
    return [f"/* Descripteur de modèle de la scène {scene.name} : une ligne par type d'emplacement (`Actor.type_id`), "
            "lue à chaque image. */",
            *iwram_table(scene, "_model_desc",
                         f"static const ModelDesc {model_desc_sym(scene)}[{lay.type_table_size}] __attribute__((unused)) = {{"),
            *body, "};", ""]
