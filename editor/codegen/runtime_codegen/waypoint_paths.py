"""Emission runtime des Paths de scene.

Un Path est immuable pendant la scene : ses points restent donc en ROM. Seule
son origine devient vivante lorsqu'il est parent d'un acteur pose.
"""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.runtime_codegen.gen_actor_hierarchy import local_transform


def path_data_lines(scene) -> list[str]:
    """Les tableaux ROM de points, un par Path de la scene."""
    lines: list[str] = []
    scene_sym = c_sym(scene.name)
    for rank, path in enumerate(scene.paths):
        points = path.points or [(0, 0)]
        lines.append(f"static const Vec2 g_path_points_{scene_sym}_{rank}[{len(points)}] = {{")
        lines.extend(f"    {{{int(x)}, {int(y)}}}," for x, y in points)
        lines.append("};")
    if lines:
        lines.append("")
    return lines


def path_init_lines(scene, scene_actors: list, actor_offset: int) -> list[str]:
    """Pose les descripteurs de la scene et remet les curseurs d'acteurs a zero."""
    if not scene.paths:
        return []
    scene_sym = c_sym(scene.name)
    slots = {actor.name: actor_offset + index for index, (actor, _sprite) in enumerate(scene_actors)}
    actors = {actor.name: actor for actor, _sprite in scene_actors}
    lines = ["    for(unsigned _i=0; _i<sizeof(g_paths)/sizeof(g_paths[0]); _i++) g_paths[_i]=(Path){0};",
             "    for(unsigned _i=0; _i<sizeof(g_path_follow)/sizeof(g_path_follow[0]); _i++) g_path_follow[_i]=(PathFollow){0};"]
    for rank, path in enumerate(scene.paths):
        x, y = int(path.x) * 256, int(path.y) * 256
        parent = 0
        if path.parent in slots:
            x, y = local_transform(path, int(actors[path.parent].x), int(actors[path.parent].y))
            parent = slots[path.parent] + 1
        mode = {"once": 0, "loop": 1, "ping_pong": 2}.get(path.mode, 1)
        count = min(255, len(path.points))
        lines.append(
            f"    g_paths[{rank}] = (Path){{{x}, {y}, g_path_points_{scene_sym}_{rank}, {count}, {mode}, {parent}}};"
        )
    return lines


def path_globals_lines(all_scene_data: list[dict], n_actors: int) -> list[str]:
    """Tables mutualisees : une seule scene est vivante a la fois."""
    count = max((len(data["scene"].paths) for data in all_scene_data), default=0)
    return [f"Path g_paths[{max(1, count)}] EWRAM_BSS;",
            f"PathFollow g_path_follow[{n_actors}] EWRAM_BSS;"]
