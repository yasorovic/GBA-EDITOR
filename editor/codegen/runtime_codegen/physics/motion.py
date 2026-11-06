"""Mouvement automatique : gravité de scène des Character et Kinematic qui la suivent, intégration des Kinematic et Rigid."""
from __future__ import annotations

from codegen.runtime_codegen.physics.areas import effect_areas, effect_table_lines, effects_affect_characters
from codegen.runtime_codegen.physics.body import physics_body, physics_body_mode, physics_collider_entries
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import (
    PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID, ForceFieldComponent, GravityOverrideComponent,
)


def _move_lines(target: str, mode: str, gravity_x: int | str, gravity_y: int | str,
                damping_retain: int, max_fall: int, sleep_frames: int,
                indent: str, effects: tuple | None = None) -> list[str]:
    """`effects` : (nombre de zones, rang de la boîte de physique, drapeaux du corps, échelle de gravité Q8) quand le corps passe par
    `area_effects_apply`. La fonction ajuste la vélocité (force, traînée, turbulence) et la gravité `_gx/_gy` du corps avant
    qu'elle soit ajoutée : le reste du pas est celui d'un corps sans zone. Elle précède la garde de sommeil des Rigid, pour
    qu'une force réveille un corps endormi."""
    if effects is None:
        return _body_move_lines(target, mode, gravity_x, gravity_y, damping_retain, max_fall, sleep_frames, indent)
    count, rank, body_flags, scale = effects
    follows = bool(body_flags & 1)
    # Un corps qui ne suit pas la gravité de scène n'en reçoit pas non plus de la zone : `_gx/_gy` restent à zéro.
    inner = _body_move_lines(target, mode, "_gx" if follows else 0, "_gy" if follows else 0,
                             damping_retain, max_fall, sleep_frames, indent + "  ")
    return [f"{indent}{{ int _gx={gravity_x if follows else 0}, _gy={gravity_y if follows else 0};",
            f"{indent}  area_effects_apply(_fx,{count},{target},{rank},{body_flags},{scale},&_gx,&_gy);",
            *inner, f"{indent}}}"]


def _body_move_lines(target: str, mode: str, gravity_x: int | str, gravity_y: int | str,
                     damping_retain: int, max_fall: int, sleep_frames: int, indent: str) -> list[str]:
    if mode in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC):
        # gravity_x et gravity_y valent 0 quand le corps ignore la gravité de scène.
        body = []
        if gravity_x != 0 or gravity_y != 0:
            body.append(f"{indent}({target})->vx+={gravity_x}; ({target})->vy+={gravity_y};")
            if max_fall:
                body.append(f"{indent}if(({target})->vy>{max_fall}) ({target})->vy={max_fall};")
        if mode == PHYSICS_BODY_KINEMATIC:
            body.append(f"{indent}actor_apply_velocity({target});")
        return body
    if mode == PHYSICS_BODY_RIGID:
        body = [f"{indent}({target})->vx+={gravity_x}; ({target})->vy+={gravity_y};"]
        if damping_retain == 0:
            body.append(f"{indent}({target})->vx=0; ({target})->vy=0;")
        elif damping_retain != 256:
            body.append(f"{indent}({target})->vx=(({target})->vx*{damping_retain})/256; "
                        f"({target})->vy=(({target})->vy*{damping_retain})/256;")
        if max_fall:
            body.append(f"{indent}if(({target})->vy>{max_fall}) ({target})->vy={max_fall};")
        body.append(f"{indent}actor_apply_velocity({target});")
        if sleep_frames:
            # Le compteur ne se remet pas à zéro ici : une vitesse résiduelle sous le seuil ne doit pas empêcher le sommeil.
            # `physics_sleep_lines` le remet à zéro quand la vitesse dépasse le seuil, et l'API de script quand elle l'écrit.
            return [f"{indent}if(({target})->physics_sleep<{sleep_frames}||({target})->vx||({target})->vy){{",
                    *[f"    {line}" for line in body], f"{indent}}}"]
        return body
    return []


def physics_motion_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict],
                         dynamic_gravity: bool = False) -> list[str]:
    """Le pas automatique, après les scripts et avant toute résolution de collision.

    `dynamic_gravity` : un script écrit `scene.gravity` (cf. `project_sets_gravity`), la gravité se lit donc dans
    `g_gravity_x/y` au lieu d'être une constante de la scène."""
    gravity_x, gravity_y = scene.effective_physics_gravity(project_settings)
    gx = round(gravity_x * 256)
    gy = round(gravity_y * 256)

    def gravity_terms(body, mode):
        if mode in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC) and not (body and body.use_scene_gravity):
            return 0, 0
        scale = body.gravity_scale if body else 1.0
        if not dynamic_gravity:
            return round(gx * scale), round(gy * scale)
        if scale == 1.0:
            return "g_gravity_x", "g_gravity_y"
        k = round(scale * 256)
        return f"(g_gravity_x*{k})/256", f"(g_gravity_y*{k})/256"

    _iterations, max_fall_speed, damping, sleep_enabled, _sleep_threshold, sleep_delay = (
        scene.effective_physics_simulation(project_settings))
    damping_retain = round((1.0 - damping) * 256)
    max_fall = round(max_fall_speed * 256)
    sleep_frames = sleep_delay if sleep_enabled else 0
    zones = effect_areas(scene)
    has_gravity_zone = any(a.effect(GravityOverrideComponent) for _i, a in zones)
    has_force_zone = any(a.effect(ForceFieldComponent) for _i, a in zones)
    characters_affected = effects_affect_characters(scene)

    def effects_of(owner, mode, body):
        """Le tuple `effects` de `_move_lines` si ce corps subit une zone de la scène, sinon None (le C émis est alors celui
        d'une scène sans zone). Le rang est celui de sa boîte de physique : pas de boîte, pas de recouvrement possible."""
        if not zones or mode not in (PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID):
            return None
        colliders = physics_collider_entries(owner)
        if not colliders:
            return None
        follows = mode == PHYSICS_BODY_RIGID or bool(body and body.use_scene_gravity)
        is_character = mode == PHYSICS_BODY_CHARACTER
        if not ((has_gravity_zone and follows) or (has_force_zone and (characters_affected or not is_character))):
            return None
        flags = (1 if follows else 0) | (2 if is_character else 0)
        return len(zones), colliders[0][0], flags, round((body.gravity_scale if body else 1.0) * 256)

    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        mode = physics_body_mode(actor)
        body = physics_body(actor)
        body_gx, body_gy = gravity_terms(body, mode)
        body_sleep = sleep_frames if body is None or body.can_sleep else 0
        move = _move_lines(f"&g_actors[{actor_offset + index}]", mode, body_gx, body_gy,
                           damping_retain, max_fall, body_sleep, "        ", effects_of(actor, mode, body))
        if move:
            lines += [f"    if(g_actors[{actor_offset + index}].active){{", *move, "    }"]

    cases = []
    for model in shared_models(pi):
        mode = physics_body_mode(model["prefab"])
        body = physics_body(model["prefab"])
        body_gx, body_gy = gravity_terms(body, mode)
        body_sleep = sleep_frames if body is None or body.can_sleep else 0
        move = _move_lines("_a", mode, body_gx, body_gy, damping_retain, max_fall, body_sleep, "            ",
                           effects_of(model["prefab"], mode, body))
        if move:
            cases += [f"        case {model['model_id']}: {{", *move, "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_pm){", "        Actor* _a=&g_actors[_pm];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        table = effect_table_lines(scene) if any("_fx," in line for line in lines) else []
        lines = ["    /* Kinematic/Rigid : mouvement avant les collisions */", *table, *lines]
    return lines


def physics_sleep_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict]) -> list[str]:
    """Endort les Rigid qui sont restés dans un rayon de `seuil x délai` autour d'une position d'ancrage.

    Le repos se lit sur la position, pas sur la vitesse : une pile de corps garde une vitesse résiduelle (la gravité
    ajoutée à chaque frame) que la correction de position, en pixels entiers, annule par à-coups, et ni la vitesse ni le
    déplacement d'une frame à l'autre ne la verraient au repos. L'ancre vit dans `g_rigid_rest`, indexée par emplacement;
    elle est reprise à la position courante dès que le corps en sort, ce qui remet le compteur à zéro."""
    _iterations, _max_fall, _damping, enabled, sleep_threshold, frames = (
        scene.effective_physics_simulation(project_settings))
    if not enabled:
        return []
    radius = round(sleep_threshold * 256) * frames

    def update(target: str, indent: str) -> list[str]:
        return [
            f"{indent}{{ int* _r=g_rigid_rest[({target})->inst]; int _dx=({target})->x-_r[0], _dy=({target})->y-_r[1];",
            f"{indent}  if(_dx<= {radius}&&_dx>=-{radius}&&_dy<= {radius}&&_dy>=-{radius}){{",
            f"{indent}      if(({target})->physics_sleep<{frames}) ({target})->physics_sleep++;",
            f"{indent}      if(({target})->physics_sleep>={frames}) "
            f"{{ ({target})->vx=0; ({target})->vy=0; }}",
            f"{indent}  }}else {{ _r[0]=({target})->x; _r[1]=({target})->y; ({target})->physics_sleep=0; }} }}",
        ]

    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        body = physics_body(actor)
        if physics_body_mode(actor) == PHYSICS_BODY_RIGID and (body is None or body.can_sleep):
            target = f"&g_actors[{actor_offset + index}]"
            lines += [f"    if(({target})->active){{", *update(target, "        "), "    }"]

    cases = []
    for model in shared_models(pi):
        body = physics_body(model["prefab"])
        if (physics_body_mode(model["prefab"]) == PHYSICS_BODY_RIGID
                and (body is None or body.can_sleep)):
            cases += [f"        case {model['model_id']}: {{", *update("_a", "            "), "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_ps){", "        Actor* _a=&g_actors[_ps];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Sommeil Rigid : mesure apres toutes les resolutions */")
    return lines
