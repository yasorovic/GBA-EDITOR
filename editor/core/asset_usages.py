"""
core/asset_usages.py — ce qui cite encore un asset, pour prévenir avant de le supprimer.

Un avertissement, pas un refus : supprimer reste possible et annulable. La liste dit où l'asset est cité, sans prétendre
être exhaustive — elle couvre ce que le projet référence par NOM : composants de sprite, calques de fond, prefabs posés,
palettes (cf. `Project.palette_usages`), scène de départ, et les scripts, où un nom entre guillemets désigne un asset
(`sfx.play("boom")`, `scene:switch("Level")`, `data.Items`).
"""
from __future__ import annotations

import re
from pathlib import Path

_MAX_SCRIPT_READS = 400          # un projet démesuré ne doit pas bloquer la boîte de confirmation


def _script_texts(project) -> list[tuple[Path, str]]:
    from core.lua_scripts import lua_files
    texts = []
    for path in lua_files(project)[:_MAX_SCRIPT_READS]:
        try:
            texts.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return texts


def _quoted(name: str) -> re.Pattern:
    return re.compile(r"""["']""" + re.escape(name) + r"""["']""")


def usages_of(project, obj) -> list[str]:
    """Ce qui cite encore `obj`, sans que l'appelant connaisse sa famille : un script (un `Path`) se retrouve par ses
    attaches, tout autre asset par le catalogue qui le contient."""
    if isinstance(obj, Path):
        from core.script_owners import script_attachments
        owners = script_attachments(project).get(project.asset_rel(obj), {})
        return [f"{family}: {owner}" for family, names in owners.items() for owner in names]
    stores = [(family, store) for family, store, _paths in project.source_families()] + list(project.authored_families())
    for family, store in stores:
        if any(item is obj for item in store):
            return usages(project, family, obj)
    return []


def usages(project, family: str, item) -> list[str]:
    """Des lignes lisibles (« scene "Level": actor "Hero" »), vides si rien ne cite cet asset."""
    name = item.name
    found: list[str] = []

    if family == "sprites":
        for scene in project.scenes:
            for actor in scene.actors:
                comp = actor.get_component("sprite")
                if comp is not None and comp.sprite_name == name:
                    found.append(f'scene "{scene.name}": actor "{actor.name}"')
        for prefab in project.prefabs:
            comp = prefab.get_component("sprite")
            if comp is not None and comp.sprite_name == name:
                found.append(f'prefab "{prefab.name}"')
    elif family == "backgrounds":
        for scene in project.scenes:
            for layer in scene.background_layers:
                if layer.background_name == name:
                    found.append(f'scene "{scene.name}": background layer {layer.bg_slot}')
    elif family == "prefabs":
        for scene in project.scenes:
            for actor in scene.actors:
                if getattr(actor, "prefab_name", None) == name:
                    found.append(f'scene "{scene.name}": actor "{actor.name}"')
    elif family == "palettes":
        found += [f'{u.kind} "{u.name}": {u.detail}' for u in project.palette_usages(name)]
    elif family == "scenes":
        if getattr(project.settings, "start_scene", "") == name:
            found.append("project start scene")

    if family in ("sfx", "music", "jingles", "scenes", "prefabs", "sprites", "data_tables", "music_boxes",
                  "jingle_boxes", "sound_boxes", "ui_layouts"):
        pattern = (re.compile(r"\bdata\." + re.escape(name) + r"\b") if family == "data_tables" else _quoted(name))
        for path, text in _script_texts(project):
            if pattern.search(text):
                found.append(f"script {path.name}")
    return found
