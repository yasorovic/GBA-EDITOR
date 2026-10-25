"""Contenu initial, volontairement minimal, des nouveaux scripts Lua.

Les scripts créés par l'interface passent tous ici. Le runtime connaît déjà
le propriétaire, ses composants et ses boîtes de collision au build : ces
détails ne doivent pas devenir du texte à supprimer avant d'écrire du code.
L'écriture disque reste du ressort de l'UI ; ce module ne produit que du texte.
"""
from __future__ import annotations
from dataclasses import dataclass, field


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
    # Tags des CollisionBox de l'actor : pas un handler par box : le runtime
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
    return "function on_update()\nend\n"


def _generate_camera_template(ctx: ScriptTemplateContext) -> str:
    return "function on_update()\nend\n"


def _generate_behavior_template(ctx: ScriptTemplateContext) -> str:
    from core.lua_scripts import BEHAVIOR_MARKER
    return (
        f"{BEHAVIOR_MARKER}\n"
        "local M = {}\n\n"
        "function M.update(actor)\nend\n\n"
        "return M\n"
    )


def _generate_actor_template(ctx: ScriptTemplateContext) -> str:
    return "function on_update()\nend\n"
