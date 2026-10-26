"""runtime_codegen/gen_scene_switch.py — le passage d'une scène à l'autre dans main.c : la table des scènes
(`g_scene_vtable`), la recherche d'un acteur par nom dans la scène active, et la transition de fondu."""
from __future__ import annotations

from codegen.c_names import sym as c_sym, scene_actor_sym
from codegen.runtime_codegen.headers import actorname_ids
from core.models.scene import TRANSITION_MODES, transition_of


def scene_transitions(p, all_scene_data: list[dict]) -> list[tuple]:
    """Par scène : (mode BLDCNT, durée d'une moitié, nom du genre). L'héritage projet→scène est résolu ici :
    le runtime ne connaît pas la notion.

    `trans_mode`/`trans_frames` : la transition de CETTE scène, employée aussi bien quand on la quitte
    (fermeture) que quand on l'ouvre (ouverture) — chaque scène décrit sa propre disparition et sa propre
    apparition."""
    trans = []   # (mode BLDCNT, durée d'une moitié) par scène
    for d in all_scene_data:
        kind, frames = transition_of(d["scene"], p.settings)
        trans.append((TRANSITION_MODES.get(kind, 0), min(255, max(1, frames)), kind))
    return trans


def vtable_lines(all_scene_data: list[dict], trans: list[tuple], has_transitions: bool) -> list[str]:
    """`g_scene_vtable` : init et tick de chaque scène, et sa transition quand le projet en a une."""
    L: list[str] = []
    n_scenes = len(all_scene_data)
    if has_transitions:
        L += [
            "typedef struct { void(*init)(void); void(*tick)(void);",
            "                 u8 trans_mode; u8 trans_frames; } _SceneVtable;",
        ]
    else:
        L.append("typedef struct { void(*init)(void); void(*tick)(void); } _SceneVtable;")
    L.append(f"static const _SceneVtable g_scene_vtable[{n_scenes}] = {{")
    for d, (mode, frames, kind) in zip(all_scene_data, trans):
        sym = c_sym(d["scene"].name)
        entry = f"    {{ scene_init_{sym}, scene_tick_{sym}"
        entry += f", {mode}, {frames} }},   /* transition : {kind} */" if has_transitions else " },"
        L.append(entry)
    L += ["};", ""]
    return L


def actor_lookup_lines(p, all_scene_data: list[dict]) -> list[str]:
    """`runtime_get_actor(name_id)` : l'acteur de ce nom DANS la scène active."""
    L: list[str] = []
    # actor.get par NOM résolu à l'exécution (« L'acteur appartient à sa scène »,
    # décision C) : la porte d'un script PARTAGÉ (caméra), qui n'a pas de scène
    # au build. Un script de SCÈNE, lui, résout son TAG à la compilation et ne
    # passe jamais par ici. On rend l'acteur du nom demandé DANS la scène active
    # (g_current_scene indexe g_scene_vtable), filtré par `actor_live` — donc nil
    # si le slot a été détruit (décision C'). Le TAG per-scène VAUT le slot (une
    # seule scène vit à la fois, g_actors repart de 0), d'où le renvoi direct.
    _an = actorname_ids(p)
    L.append("Actor* runtime_get_actor(int name_id){")
    if _an:
        L.append("    switch(g_current_scene){")
        for si, d in enumerate(all_scene_data):
            cases, seen = [], set()
            for actor, _s in d["scene_actors"]:
                if not getattr(actor, "active", True):
                    continue
                nsym = c_sym(actor.name)
                nid = _an.get(nsym)
                if nid is None or nid in seen:   # doublon dans la scène : le 1er gagne
                    continue
                seen.add(nid)
                tag = scene_actor_sym(d["scene"].name, actor.name).upper()
                cases.append(
                    f"        case ACTORNAME_{nsym.upper()}: "
                    f"return actor_live(&g_actors[ACTOR_{tag}]);")
            if not cases:
                continue
            L.append(f"    case {si}:   /* {d['scene'].name} */")
            L.append("        switch(name_id){")
            L += cases
            L.append("        default: break; }")
            L.append("        break;")
        L.append("    default: break; }")
    L.append("    return (Actor*)0;")
    L.append("}")
    L.append("")
    return L


def scene_enter_lines(n_scenes: int) -> list[str]:
    """Le fondu : l'état de la transition et `scene_enter()`, la bascule réelle. À émettre si une scène a une transition."""
    return [
        "/* ── Scene transition ──────────────────── */",
        "/* Phase 0 = none, 1 = closing (the outgoing scene is frozen),",
        "   2 = opening. The intensity goes from 0 (sharp) to 16 (off). */",
        "static int g_trans_phase = 0, g_trans_i = 0, g_trans_n = 1;",
        "",
        "/* Actual switch. The screen is already off when scene_init runs:",
        "   its display_reset() only writes to the shadows while the",
        "   transition owns the registers, so the incoming scene does not",
        "   burst out in full light in the middle of its loading. */",
        "static void scene_enter(void){",
        "    int m = 0, n = 1;",
        f"    if(g_next_scene>=0 && g_next_scene<{n_scenes}){{",
        "        m = g_scene_vtable[g_next_scene].trans_mode;",
        "        n = g_scene_vtable[g_next_scene].trans_frames;",
        "    }",
        "    if(m){ transition_begin(m); transition_fade(16); }",
        "    g_current_scene = g_next_scene;",
        f"    if(g_current_scene>=0 && g_current_scene<{n_scenes})",
        "        g_scene_vtable[g_current_scene].init();",
        "    if(m){ g_trans_i = n; g_trans_n = n; g_trans_phase = 2; }",
        "    else { transition_end(); g_trans_phase = 0; }",
        "}",
        "",
    ]
