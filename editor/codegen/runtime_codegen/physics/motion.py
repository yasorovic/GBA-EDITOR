"""Mouvement automatique des KinematicBody et RigidBody."""
from __future__ import annotations

from codegen.runtime_codegen.physics.body import physics_body_mode
from codegen.runtime_codegen.shared_pool_gen import shared_models
from core.models.components import PHYSICS_BODY_KINEMATIC, PHYSICS_BODY_RIGID


def _move_lines(target: str, mode: str, gravity_x: int, gravity_y: int, indent: str) -> list[str]:
    if mode == PHYSICS_BODY_KINEMATIC:
        return [f"{indent}actor_apply_velocity({target});"]
    if mode == PHYSICS_BODY_RIGID:
        return [f"{indent}({target})->vx+={gravity_x}; ({target})->vy+={gravity_y};",
                f"{indent}actor_apply_velocity({target});"]
    return []


def physics_motion_lines(scene, scene_actors, actor_offset: int, pi: list[dict]) -> list[str]:
    """Le pas automatique, après les scripts et avant toute résolution de collision."""
    gx = round(float(getattr(scene, "physics_gravity_x", 0.0)) * 256)
    gy = round(float(getattr(scene, "physics_gravity_y", 0.0)) * 256)
    lines: list[str] = []
    for index, (actor, _sprite) in enumerate(scene_actors):
        mode = physics_body_mode(actor)
        move = _move_lines(f"&g_actors[{actor_offset + index}]", mode, gx, gy, "        ")
        if move:
            lines += [f"    if(g_actors[{actor_offset + index}].active){{", *move, "    }"]

    cases = []
    for model in shared_models(pi):
        mode = physics_body_mode(model["prefab"])
        move = _move_lines("_a", mode, gx, gy, "            ")
        if move:
            cases += [f"        case {model['model_id']}: {{", *move, "        } break;"]
    if cases:
        lines += ["    POOL_EACH(_pm){", "        Actor* _a=&g_actors[_pm];",
                  "        if(!_a->active) continue;", "        switch(_a->model){",
                  *cases, "        default: break;", "        }", "    }"]
    if lines:
        lines.insert(0, "    /* Kinematic/Rigid : mouvement avant les collisions */")
    return lines
