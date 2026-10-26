"""runtime_codegen/gen_sfx_trigger.py — les déclencheurs SoundFx d'un acteur ou d'un prefab (`on_spawn`, `on_destroy`)."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from core.project import Project
from typing import Optional


def sfx_trigger_info(p: Project, owner) -> tuple[Optional[str], int, str]:
    """(constante SFX_*, volume effet, trigger) depuis le SoundFxComponent
    d'un actor/prefab, si présent et résolu vers un Sfx du projet.

    Rend (None, 0, "manual") si rien n'est configuré — l'appelant n'a alors
    rien à émettre. Les triggers AUTOMATIQUES ("on_spawn"/"on_destroy"/un nom
    de bouton ou d'action) sont injectés au site d'appel connu au build par CE
    module, indépendamment de tout script sur l'actor : c'est ce qui fait
    marcher un déclencheur sur un actor SANS ScriptComponent (menu, decor
    déclencheur…), là où `self:play_sfx()` (trigger="manual") reste résolu
    côté scripting/codegen.py puisqu'il exige un script pour être appelé."""
    comp = owner.get_component("sound_fx")
    if not comp or not comp.active or not comp.sfx_name:
        return None, 0, "manual"
    from codegen.c_names import c_ident
    from core.models.audio import volume_to_effect
    sfx = next((s for s in getattr(p, "sfx", []) if s.name == comp.sfx_name), None)
    if sfx is None:
        return None, 0, comp.trigger
    return f"SFX_{c_ident(comp.sfx_name)}", volume_to_effect(sfx.volume), comp.trigger


def sfx_on_destroy_table(p: Project, all_scene_data: list[dict],
                           scene_pis: list[list[dict]]) -> list[str]:
    """Le SFX à jouer juste avant qu'un actor de tel TAG soit désactivé, indexé
    par TAG — mais PAR SCÈNE. On émet donc un couple
    de tables constantes par scène (id, -1 = aucun ; volume) et DEUX pointeurs
    globaux que chaque scene_init fait pointer sur les siens (comme
    `g_active_cmap`, cf. `gen_scene_init`).

    Même base de TAG que `headers.generate_actor_types` : acteurs actifs de la
    scène numérotés 0..N-1 dans l'ordre de `scene.actors`, puis chaque modèle du pool partagé à sa
    place (toutes les instances d'un modèle PARTAGENT ce TAG, posé au spawn)."""
    out = [
        "const s16 *g_sfx_on_destroy_id  = 0;",
        "const u8  *g_sfx_on_destroy_vol = 0;",
    ]
    for d, spi in zip(all_scene_data, scene_pis):
        sym = c_sym(d["scene"].name)
        n = max([len(d["scene_actors"])]
                + [p2["spool"]["start"] + p2["model_id"] for p2 in spi if p2["shared"]] + [1])
        ids  = ["-1"] * n
        vols = ["0"]  * n
        for tag, (actor, _sprite) in enumerate(d["scene_actors"]):
            sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, actor)
            if sfx_sym and sfx_trig == "on_destroy":
                ids[tag], vols[tag] = sfx_sym, str(sfx_vol)
        for p2 in spi:
            if not p2["shared"]:
                continue        # un modèle sans spawn n'a pas d'acteur de ce nom
            tag = p2["spool"]["start"] + p2["model_id"] - 1
            sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, p2["prefab"])
            if sfx_sym and sfx_trig == "on_destroy":
                ids[tag], vols[tag] = sfx_sym, str(sfx_vol)
        out += [
            f"static const s16 g_sfx_on_destroy_id_{sym}[{n}]  = {{{', '.join(ids)}}};",
            f"static const u8  g_sfx_on_destroy_vol_{sym}[{n}] = {{{', '.join(vols)}}};",
        ]
    out.append("")
    return out
