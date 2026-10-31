"""Mouvement automatique des KinematicBody et RigidBody."""
from __future__ import annotations

from codegen.runtime_codegen.physics.body import physics_body_mode
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID


def _move_lines(target: str, mode: str, gravity_x: int, gravity_y: int,
                damping_retain: int, max_fall: int, sleep_frames: int,
                indent: str) -> list[str]:
    if mode == PHYSICS_BODY_KINEMATIC:
        return [f"{indent}actor_apply_velocity({target});"]
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
            return [f"{indent}if(({target})->physics_sleep<{sleep_frames}||({target})->vx||({target})->vy){{",
                    f"{indent}    if(({target})->vx||({target})->vy) ({target})->physics_sleep=0;",
                    *[f"    {line}" for line in body], f"{indent}}}"]
        return body
    return []


def physics_motion_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict]) -> list[str]:
    """Le pas automatique, après les scripts et avant toute résolution de collision."""
    gravity_x, gravity_y = scene.effective_physics_gravity(project_settings)
    gx = round(gravity_x * 256)
    gy = round(gravity_y * 256)
    _iterations, max_fall_speed, damping, sleep_enabled, _sleep_threshold, sleep_delay = (
        scene.effective_physics_simulation(project_settings))
    damping_retain = round((1.0 - damping) * 256)
    max_fall = round(max_fall_speed * 256)
    sleep_frames = sleep_delay if sleep_enabled else 0
    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        mode = physics_body_mode(actor)
        move = _move_lines(f"&g_actors[{actor_offset + index}]", mode, gx, gy,
                           damping_retain, max_fall, sleep_frames, "        ")
        if move:
            lines += [f"    if(g_actors[{actor_offset + index}].active){{", *move, "    }"]

    cases = []
    for model in shared_models(pi):
        mode = physics_body_mode(model["prefab"])
        move = _move_lines("_a", mode, gx, gy, damping_retain, max_fall, sleep_frames, "            ")
        if move:
            cases += [f"        case {model['model_id']}: {{", *move, "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_pm){", "        Actor* _a=&g_actors[_pm];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Kinematic/Rigid : mouvement avant les collisions */")
    return lines


def physics_sleep_lines(scene, project_settings, scene_actors, actor_offset: int, pi: list[dict]) -> list[str]:
    """Endort les Rigid restés sous le seuil après toutes les résolutions."""
    _iterations, _max_fall, _damping, enabled, sleep_threshold, frames = (
        scene.effective_physics_simulation(project_settings))
    if not enabled:
        return []
    threshold = round(sleep_threshold * 256)

    def update(target: str, indent: str) -> list[str]:
        return [
            f"{indent}if(({target})->vx<= {threshold}&&({target})->vx>=-{threshold}&&"
            f"({target})->vy<= {threshold}&&({target})->vy>=-{threshold}){{",
            f"{indent}    if(({target})->physics_sleep<{frames}) ({target})->physics_sleep++;",
            f"{indent}    if(({target})->physics_sleep>={frames}) "
            f"{{ ({target})->vx=0; ({target})->vy=0; }}",
            f"{indent}}}else ({target})->physics_sleep=0;",
        ]

    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        if physics_body_mode(actor) == PHYSICS_BODY_RIGID:
            target = f"&g_actors[{actor_offset + index}]"
            lines += [f"    if(({target})->active){{", *update(target, "        "), "    }"]

    cases = []
    for model in shared_models(pi):
        if physics_body_mode(model["prefab"]) == PHYSICS_BODY_RIGID:
            cases += [f"        case {model['model_id']}: {{", *update("_a", "            "), "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_ps){", "        Actor* _a=&g_actors[_ps];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Sommeil Rigid : mesure apres toutes les resolutions */")
    return lines
