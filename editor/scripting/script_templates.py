"""
scripting/script_templates.py — Génère le contenu initial d'un nouveau
script Lua selon son contexte (scène / actor / behavior / générique).

Point d'entrée unique utilisé par les endroits de l'UI qui créent un script
(SceneInspector, ScriptEditor du component, Script finder, Assets finder) —
avant, chacun réimplémentait son propre template de façon indépendante,
avec des résultats incohérents entre eux (ex: noms d'event en camelCase au
lieu de snake_case, jamais reconnus par KNOWN_EVENTS). L'écriture disque
reste du ressort de l'UI ; ce module ne produit que du texte.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from codegen.c_names import c_ident


@dataclass
class ScriptTemplateContext:
    """kind: "scene" | "camera" | "actor" | "behavior" | "empty" """
    kind: str = "empty"
    name: str = ""                 # nom du script (sans .lua)
    scene_name: str = ""           # pour kind="scene"
    camera_name: str = ""          # pour kind="camera"
    actor_name: str = ""           # pour kind="actor"
    component_labels: list[str] = field(default_factory=list)
    has_sprite: bool = False
    has_sfx: bool = False
    # Tags des CollisionBox de l'actor — pas un handler par box : le runtime
    # n'appelle qu'une paire de handlers par actor, qui reçoit le tag touché.
    collision_tags: list[str] = field(default_factory=list)


def generate_script_template(ctx: ScriptTemplateContext) -> str:
    if ctx.kind == "scene":
        return _generate_scene_template(ctx)
    if ctx.kind == "camera":
        return _generate_camera_template(ctx)
    if ctx.kind == "actor":
        return _generate_actor_template(ctx)
    if ctx.kind == "behavior":
        return _generate_behavior_template(ctx)
    return ""   # "empty" : fichier vide


def _generate_scene_template(ctx: ScriptTemplateContext) -> str:
    return (
        f"-- Scene script: {ctx.scene_name}\n\n"
        "function on_start()\nend\n\n"
        "function on_update()\nend\n\n"
        "function on_late_update()\nend\n"
    )


def _generate_camera_template(ctx: ScriptTemplateContext) -> str:
    """Deux points d'entrée seulement, et l'ordre dit dans le commentaire : le
    suivi déclaratif a déjà écrit la position quand `on_update` s'exécute, donc
    ce qu'on écrit ici l'ajuste au lieu de se battre avec lui."""
    return (
        f"-- Camera script: {ctx.camera_name}\n"
        "-- The declarative settings (follow, dead zone) are computed BEFORE\n"
        "-- this script; the world bounds are applied AFTER.\n\n"
        "function on_start()\nend\n\n"
        "function on_update()\nend\n"
    )


def _generate_behavior_template(ctx: ScriptTemplateContext) -> str:
    return (
        f"-- Behavior: {ctx.name}\n"
        f"-- Reusable module. Usage: local M = require('behaviors/{ctx.name}')\n\n"
        "local M = {}\n\n"
        "function M.update(actor)\nend\n\n"
        "return M\n"
    )


def _generate_actor_template(ctx: ScriptTemplateContext) -> str:
    lines = [
        f"-- Actor script : {ctx.name}",
        f"-- Actor       : {ctx.actor_name or '?'}",
        f"-- Components  : {', '.join(ctx.component_labels) or 'aucun'}",
        "",
        "-- Declare here the variables configurable from the editor:",
        "-- exports = {",
        "--     speed  = { type = \"int\",  default = 5,       label = \"Speed\", min = 0, max = 20 },",
        "--     name   = { type = \"string\", default = \"Hero\", label = \"Name\" },",
        "--     active = { type = \"bool\",   default = true,    label = \"Active\" },",
        "-- }",
        "",
        "function on_start()",
    ]
    if ctx.has_sprite: lines += ["    -- self:play_anim('Idle')"]
    lines += ["end", "", "function on_update()"]
    if ctx.has_sprite: lines += ["    -- self:play_anim('Run')"]
    if ctx.has_sfx:    lines += ["    -- self:play_sfx()"]
    lines += ["end", ""]

    if ctx.collision_tags:
        boxtags = ", ".join("BOXTAG_" + c_ident(t or "body") for t in ctx.collision_tags)
        lines += [f"-- my_box / other_box : {boxtags}",
                  "function on_collision_enter(other, my_box, other_box)", "end", "",
                  "function on_collision_exit(other, my_box, other_box)", "end", ""]

    if not (ctx.has_sprite or ctx.collision_tags or ctx.has_sfx):
        lines += ["-- Add components in the inspector to unlock the API.", ""]
    return "\n".join(lines)
