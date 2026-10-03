"""
runtime_codegen/sound_emit.py — Les trois boîtes sonores en C.

Émet, dans `main.c` :

    g_sound_box_action[] / _vol[]   l'état courant DÉVELOPPÉ des actions
    g_sound_box_state_map[][]       vers quoi chaque action pointe, par état
    sound_box_set_state(i)          recopie une ligne dans l'état courant
    (les mêmes pour la JingleBox)
    g_music_box_tr[][]              les arêtes de la MusicBox
    music_box_trigger(i)            cherche l'arête et joue la transition

Le développement de l'état courant est délibéré : au déclenchement d'un pas, le
runtime lit `g_sound_box_action[action]` — une indirection — au lieu de
`g_sound_box_state_map[état][action]` — deux. Changer d'état coûte alors une
recopie de quelques octets, ce qui arrive mille fois moins souvent qu'un pas.

Les symboles portent le nom de leur BOÎTE, comme les appels Lua : `sound_box`,
`jingle_box`, `music_box`. Un même concept ne s'écrit pas d'une façon en Lua et
d'une autre en C.

Tout est résolu au BUILD : le runtime ne connaît ni les noms, ni la notion de
graphe. Il lit des tables et compare des entiers.
"""
from __future__ import annotations

from core.models.audio import volume_to_effect, volume_to_module
from core.models.sound_box import KIND_SOUND, KIND_JINGLE, TRANSITION_CUT
from codegen.c_names import sym as c_sym


def _sfx_const(name: str) -> str:
    from scripting.api import sfx_constant
    return sfx_constant(name)


def _music_const(name: str) -> str:
    """La constante de module telle que `soundbank.h` la définit.

    `MOD_*` et non `MUSIC_*` : ces tables vivent dans `main.c`, qui inclut le
    header de mmutil. `MUSIC_*` est un alias que le transpileur Lua pose dans
    les fichiers de script, et qui n'existe pas ici.
    """
    return f"MOD_{c_sym(name).upper()}"


def collect(p) -> dict:
    """Ce que le build doit savoir des trois boîtes, résolu une fois.

    UNE boîte active par famille — la première par ordre de nom. L'espace des
    ACTIONS, lui, est commun au projet (`Project.sound_action_names`) : une
    frame d'animation cite une action sans savoir quelle boîte sera chargée,
    donc `pas` doit désigner la même action partout.
    """
    def first(store):
        boxes = sorted(getattr(p, store, []), key=lambda b: b.name)
        return boxes[0] if boxes else None

    return {
        "music_box":  first("music_boxes"),
        "sound_box":  first("sound_boxes"),
        "jingle_box": first("jingle_boxes"),
        "sound_actions":  p.sound_action_names(KIND_SOUND),
        "jingle_actions": p.sound_action_names(KIND_JINGLE),
    }


def _action_box_lines(kind: str, box, actions: list[str], p) -> list[str]:
    """Les tables et le commutateur d'UNE boîte d'actions."""
    if not actions:
        return []
    states = list(getattr(box, "states", []) or []) if box else []
    n_actions = len(actions)

    def resolve(state, action) -> tuple[str, int]:
        """(constante C, volume) de ce vers quoi l'action pointe."""
        name = (state.mapping.get(action, "") or "") if state else ""
        if not name:
            return "-1", 0
        if kind == KIND_SOUND:
            res = next((s for s in getattr(p, "sfx", []) if s.name == name), None)
            if res is None:
                return "-1", 0
            return _sfx_const(name), volume_to_effect(getattr(res, "volume", 100))
        res = next((m for m in getattr(p, "music", []) if m.name == name), None)
        if res is None:
            return "-1", 0
        return _music_const(name), volume_to_module(getattr(res, "volume", 100))

    rows_id, rows_vol = [], []
    for st in states:
        pairs = [resolve(st, a) for a in actions]
        rows_id.append("    {" + ",".join(i for i, _v in pairs) + f"}},   /* {st.name} */")
        rows_vol.append("    {" + ",".join(str(v) for _i, v in pairs) + "},")

    # L'état de départ, développé dès la ROM : sans lui, rien ne sonnerait
    # avant le premier appel à `<boîte>_set_state`.
    start_idx = next((i for i, s in enumerate(states)
                      if s.name == getattr(box, "start", "")), 0 if states else -1)
    if start_idx >= 0 and states:
        init_pairs = [resolve(states[start_idx], a) for a in actions]
    else:
        init_pairs = [("-1", 0)] * n_actions

    n_states = max(1, len(states))
    L = [
        f"/* ── {kind} — {n_actions} action(s), {len(states)} state(s) (ROADMAP v0.8.7) ── */",
        f"#define {kind.upper()}_ACTIONS {n_actions}",
        f"#define {kind.upper()}_STATES {n_states}",
    ]
    if states:
        L += [f"static const s16 g_{kind}_state_map[{n_states}][{n_actions}] = {{"] + rows_id + ["};"]
        L += [f"static const u8  g_{kind}_state_vol[{n_states}][{n_actions}] = {{"] + rows_vol + ["};"]
    # Non statiques : le stepper d'animation vit dans main.c, mais les scripts
    # d'acteur sont d'autres unités de compilation et appellent le commutateur.
    L += [
        f"s16 g_{kind}_action[{n_actions}]     = {{{','.join(i for i, _v in init_pairs)}}};",
        f"u8  g_{kind}_action_vol[{n_actions}] = {{{','.join(str(v) for _i, v in init_pairs)}}};",
        f"void {kind}_set_state(int s){{",
    ]
    if states:
        L += [
            f"    if(s<0||s>={n_states}) return;",
            f"    for(int i=0;i<{n_actions};i++){{",
            f"        g_{kind}_action[i]     = g_{kind}_state_map[s][i];",
            f"        g_{kind}_action_vol[i] = g_{kind}_state_vol[s][i];",
            "    }",
        ]
    else:
        L.append("    (void)s;")
    L += ["}", ""]
    return L


def _music_box_lines(box, p, triggers: list[str]) -> list[str]:
    """La MusicBox : ses états, ses arêtes, et `music_box_trigger`."""
    states = list(getattr(box, "states", []) or []) if box else []
    if not states:
        return []
    trans = list(getattr(box, "transitions", []) or [])
    idx = {s.name: i for i, s in enumerate(states)}

    rows = []
    for s in states:
        res = next((m for m in getattr(p, "music", []) if m.name == s.music), None)
        mid = _music_const(s.music) if res is not None else "-1"
        vol = volume_to_module(getattr(s, "level", 100)) if res is not None else 0
        rows.append(f"    {{ {mid}, {1 if s.loop else 0}, {vol} }},   /* {s.name} */")

    edges = []
    for tr in trans:
        if tr.dst not in idx or tr.trigger not in triggers:
            continue
        # `src` vide = depuis N'IMPORTE QUEL état : -1, et la recherche
        # l'accepte quel que soit l'état courant.
        src = idx.get(tr.src, -1) if tr.src else -1
        edges.append(f"    {{ {src}, {idx[tr.dst]}, {triggers.index(tr.trigger)}, "
                     f"{1 if tr.kind == TRANSITION_CUT else 0}, "
                     f"{max(2, min(255, int(tr.frames)))} }},"
                     f"   /* {tr.src or '*'} --{tr.trigger}--> {tr.dst} */")

    start = idx.get(getattr(box, "start", ""), 0)
    L = [
        f"/* ── music_box — {len(states)} state(s), {len(edges)} edge(s) ── */",
        f"static const s16 g_music_box_state[{len(states)}][3] = {{",
        *rows, "};",
        f"int g_music_box_state_cur = {start};",
    ]
    if edges:
        L += [
            "/* {src, dst, trigger, cut?, frames} — src -1 = from anywhere */",
            f"static const s16 g_music_box_tr[{len(edges)}][5] = {{",
            *edges, "};",
        ]
    L += [
        "static void _music_box_enter(int s, int cut, int frames){",
        f"    if(s<0||s>={len(states)}) return;",
        "    g_music_box_state_cur = s;",
        "    int id = g_music_box_state[s][0];",
        "    if(id < 0){ music_stop(); return; }",
        # Les deux transitions du matériel, et elles seules (cf. v0.8.3).
        "    if(cut) music_cut_to(id, g_music_box_state[s][1], g_music_box_state[s][2]);",
        "    else    music_fade_to(id, g_music_box_state[s][1], g_music_box_state[s][2], frames);",
        "}",
        "void music_box_trigger(int t){",
    ]
    if edges:
        L += [
            f"    for(int i=0;i<{len(edges)};i++){{",
            "        if(g_music_box_tr[i][2]!=t) continue;",
            "        if(g_music_box_tr[i][0]>=0 && g_music_box_tr[i][0]!=g_music_box_state_cur) continue;",
            "        _music_box_enter(g_music_box_tr[i][1], g_music_box_tr[i][3], g_music_box_tr[i][4]);",
            "        return;",
            "    }",
        ]
    else:
        L.append("    (void)t;")
    L += ["}", ""]
    return L


def emit(p) -> list[str]:
    """Tout le C des trois boîtes, ou rien si le projet n'en a aucune."""
    info = collect(p)
    if (info["music_box"] is None and not info["sound_actions"]
            and not info["jingle_actions"]):
        return []
    L = ["", "/* ═══ Sound boxes (ROADMAP v0.8.7) ═══════════════════════ */"]
    L += _action_box_lines(KIND_SOUND, info["sound_box"], info["sound_actions"], p)
    L += _action_box_lines(KIND_JINGLE, info["jingle_box"], info["jingle_actions"], p)
    L += _music_box_lines(info["music_box"], p, p.sound_trigger_names())
    return L


def music_start_lines(p) -> list[str]:
    """L'état musical de départ, joué au démarrage du jeu.

    Séparé de `emit` parce qu'il ne s'agit pas d'une table mais d'un appel, et
    qu'il doit tomber dans `main()` après `mmInitDefault`.
    """
    box = collect(p)["music_box"]
    states = list(getattr(box, "states", []) or []) if box else []
    if not states:
        return []
    return [
        "    /* Starting state of the MusicBox. */",
        "    if(g_music_box_state[g_music_box_state_cur][0] >= 0)",
        "        music_play(g_music_box_state[g_music_box_state_cur][0],",
        "                   g_music_box_state[g_music_box_state_cur][1],",
        "                   g_music_box_state[g_music_box_state_cur][2]);",
    ]
