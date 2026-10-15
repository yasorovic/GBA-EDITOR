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
from core.music_structure import music_info_row   # une seule définition, que l'aperçu lit aussi
from core.models.sound_box import KIND_SOUND, KIND_JINGLE, TRANSITION_CUT
from codegen.c_names import module_constant


def _sfx_const(name: str) -> str:
    from scripting.api import sfx_constant
    return sfx_constant(name)


def _music_const(name: str) -> str:
    """La constante de module telle que `soundbank.h` la définit.

    `MOD_*` et non `MUSIC_*` : ces tables vivent dans `main.c`, qui inclut le
    header de mmutil. `MUSIC_*` est un alias que le transpileur Lua pose dans
    les fichiers de script, et qui n'existe pas ici.
    """
    return module_constant(name)


def sfx_default_tables(sound_assets: dict | None) -> list[str]:
    """Ce avec quoi chaque effet DÉMARRE : sa hauteur (facteur 6.10), son panoramique (0–255) et la variation aléatoire
    de sa hauteur (± %) — `Sfx.pitch`, `Sfx.panning`, `Sfx.pitch_variation` convertis vers l'échelle du matériel. Un rang par
    effet, dans l'ordre du soundbank — celui de `SFX_*`, que `sfx_play` reçoit en `id`. Au moins une case : un projet sans
    effet (de la musique seule) garde des tables que `sfx_play` ne lira jamais.

    Et la graine du tirage de cette variation : un générateur À LUI, défini ici et partagé par tous les fichiers C (comme
    la graine de la secousse de caméra). Il ne touche jamais celui de `math.rand` : régler la variation d'un effet ne doit
    pas changer ce que le jeu tire au hasard. La graine est fixe, donc une partie rejouée refait les mêmes sons."""
    from core.models.audio import SFX_PITCH_VARIATION_MAX, panning_to_hardware, pitch_to_rate
    sfx_rows = [sfx for sfx, _path in (sound_assets or {}).get("sfx", [])] or [None]
    rates = [pitch_to_rate(getattr(sfx, "pitch", 100)) for sfx in sfx_rows]
    pans = [panning_to_hardware(getattr(sfx, "panning", 0)) for sfx in sfx_rows]
    spreads = [max(0, min(SFX_PITCH_VARIATION_MAX, int(getattr(sfx, "pitch_variation", 0) or 0))) for sfx in sfx_rows]
    protected = [1 if getattr(sfx, "protected", False) else 0 for sfx in sfx_rows]
    return [f"const mm_hword g_sfx_default_rate[{len(rates)}] = {{{','.join(map(str, rates))}}};",
            f"const mm_byte  g_sfx_default_pan[{len(pans)}] = {{{','.join(map(str, pans))}}};",
            f"const mm_byte  g_sfx_default_spread[{len(spreads)}] = {{{','.join(map(str, spreads))}}};",
            f"const mm_byte  g_sfx_default_protected[{len(protected)}] = {{{','.join(map(str, protected))}}};",
            "mm_word g_sfx_seed = 1013904223u;", ""]


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
        res = next((j for j in getattr(p, "jingles", []) if j.name == name), None)
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


# ── Les réglages d'une musique, au runtime (ROADMAP « L'asset .music ») ──────
#
# Une ligne par module : la section de boucle (en positions d'ordre), le tempo et la
# hauteur (facteurs Q10 de maxmod), les deux fondus (en frames). ZÉRO PARTOUT = le
# fichier tel qu'il est : un module sans réglage n'a pas de ligne, et la table ne
# pèse que ce que l'auteur a réglé.

def music_runtime_lines(p, sound_assets) -> list[str]:
    """Le C de la couche musique : la table des réglages et les fonctions qui les lisent.

    `music_play`, `music_stop` et `music_set_volume` vivent ICI et non plus en `static
    inline` dans l'en-tête : ils doivent lire la table, et l'état (module en cours,
    section de boucle) tient dans `main.c`. Les scripts, qui sont d'autres unités de
    compilation, les appellent par leur prototype.

    Un seul point d'écriture du volume de module, comme pour les transitions : les
    deux fondus d'un module (entrée, sortie) sont des MODES de `music_transition_tick`
    (3 et 4), pas un second mécanisme qui écrirait le même registre.

    Les appels de script (`music.set_tempo`, `fade_in`, `set_section`…) SURCHARGENT ces
    réglages pour la lecture en cours : `music_begin` et `music_end` sont l'unique chemin
    de `music_play` / `music_stop` ET de leurs variantes à fondu explicite, et
    `music_apply` réapplique les réglages de l'asset à chaque nouveau module — une
    surcharge ne survit pas à la piste suivante."""
    from core.models.audio import Jingle
    from core.music_structure import music_section_names, music_section_rows
    musics = [(m, path) for m, path in (sound_assets or {}).get("music", []) if not isinstance(m, Jingle)]
    rows = []
    for m, path in (sound_assets or {}).get("music", []):
        if isinstance(m, Jingle):
            continue        # un jingle joue par `mmJingle`, sur sa propre couche : aucun de ces réglages
        row = music_info_row(m, path)
        if any(row):
            rows.append(f"    [{_music_const(m.name)}] = {{ {', '.join(str(v) for v in row)} }},"
                        f"   /* {m.name} */")

    # Les sections qu'un script peut choisir : (module, rang du NOM, début, fin). Le rang est
    # celui de `music_section_names` — la même liste que les `MSEC_*` du script.
    names = music_section_names(getattr(p, "music", [m for m, _path in musics]) if p is not None
                                else [m for m, _path in musics])
    section_rows = []
    for m, path in musics:
        for name, start, end in music_section_rows(m, path):
            section_rows.append(f"    {{ {_music_const(m.name)}, {names.index(name)}, {start}, {end} }},"
                                f"   /* {m.name} / {name} */")
    cue_rows, cue_kinds = _music_cue_rows(p, musics)
    jingles = [j for j, _path in (sound_assets or {}).get("music", []) if isinstance(j, Jingle)]
    jingle_rows, jingle_kinds = _jingle_cue_rows(p, jingles)
    cue_reset = ["    g_cue_last = -1;   /* a module that starts again fires its first cue again */"] if cue_rows else []
    return [
        "/* ── Music settings per module (ROADMAP « L'asset .music ») ──────────── */",
        "/* {loop start, loop end, tempo, pitch, fade in, fade out}. Zero = the file as it",
        "   is: only a module with a setting has a row. The loop is in ORDER POSITIONS,",
        "   end excluded; 0 = no loop section. Tempo and pitch are maxmod's Q10 factors. */",
        "typedef struct { s16 loop_start, loop_end; u16 tempo, pitch, fade_in, fade_out; } MusicInfo;",
        "static const MusicInfo g_music_info[MSL_NSONGS + 1] = {",
        *(rows or ["    { 0, 0, 0, 0, 0, 0 },"]),
        "};",
        "/* The sections a script can pick (music.set_section): {module, section, start, end}.",
        "   `section` is the rank of the NAME among the project's section names — the same",
        "   rank as the MSEC_* constants of the scripts. */",
        "typedef struct { s16 music, section, start, end; } MusicSection;",
        f"#define MUSIC_SECTION_COUNT {len(section_rows)}",
        "static const MusicSection g_music_sec[MUSIC_SECTION_COUNT + 1] = {",
        *(section_rows or ["    { 0, 0, 0, 0 },"]),
        "};",
        "int g_music_cur = -1;                 /* the module playing, -1 = none */",
        "int g_music_vol = 0;                  /* its volume, on maxmod's 0-1024 scale */",
        "",
        "/* ── The module volume has ONE writer ─────────────────────────────── */",
        "/* Every volume a script or a fade asks for goes through music_write_volume(), which",
        "   scales it by the DUCK: 0-1024, 1024 = no duck. A jingle with a duck policy lowers",
        "   it while it sounds. Two writers of the same register that do not know about each",
        "   other is the defect the camera had (v0.6.1). */",
        "static int g_duck = 1024, g_duck_to = 1024, g_duck_step = 1024;",
        "static int g_jingle_watch = 0, g_jingle_release = 0, g_jingle_paused = 0;",
        "static int g_jingle_cur = -1, g_jingle_frame = 0;   /* the jingle sounding, and the frames since it started */",
        "static void music_write_volume(int volume){",
        "    mmSetModuleVolume((mm_word)(volume * g_duck / 1024));",
        "}",
        "/* A level already on its way: only the fades (modes 3 and 4) and the crossfade write",
        "   the volume on their own, every frame, with the duck of the moment. */",
        "static void music_rewrite_volume(void){",
        "    if(g_mtr_mode == 0 || g_mtr_mode == 2) music_write_volume(g_music_vol);",
        "}",
        "static int g_mloop_start = 0, g_mloop_end = 0, g_mloop_in = 0;",
        "static int g_mloop_rel = 0, g_mloop_last = 0;   /* a released loop: plays on to the end, then stops */",
        *(["static int g_cue_last = -1;                  /* the order position seen on the previous frame */"]
          if cue_rows else []),
        "",
        "/* A module with a loop section must LOOP, whatever its `loop` flag: the section",
        "   is what makes it loop, and a module played once would simply end. */",
        "static int music_mode(int id, int loop){",
        "    return (loop || (id >= 0 && id < MSL_NSONGS && g_music_info[id].loop_end > 0))",
        "           ? MM_PLAY_LOOP : MM_PLAY_ONCE;",
        "}",
        "/* Applies the settings of the module that has JUST started — after mmStart, which",
        "   would otherwise reset them. Measured on ROM: tempo and pitch take effect there. */",
        "static void music_apply(int id){",
        "    const MusicInfo *m;",
        "    g_mloop_in = 0; g_mloop_rel = 0;",
        "    if(id < 0 || id >= MSL_NSONGS){ g_music_cur = -1; g_mloop_end = 0; return; }",
        "    m = &g_music_info[id];",
        "    g_music_cur = id;",
        "    mmSetModuleTempo((mm_word)(m->tempo ? m->tempo : 1024));",
        "    mmSetModulePitch((mm_word)(m->pitch ? m->pitch : 1024));",
        "    g_mloop_start = m->loop_start; g_mloop_end = m->loop_end;",
        *cue_reset,
        "    if(g_jingle_paused) mmPause();   /* a jingle that pauses the music keeps a NEW module waiting too */",
        "}",
        "/* `fade_in` < 0 = the fade in of the asset; otherwise the call's own. */",
        "static void music_begin(int id, int loop, int volume, int fade_in){",
        "    if(id < 0) return;     /* a music whose file is gone: nothing to play */",
        "    mmStart((mm_word)id, (mm_pmode)music_mode(id, loop));",
        "    music_apply(id);",
        "    if(g_mtr_mode >= 3) g_mtr_mode = 0;   /* a new play supersedes a fade in or out */",
        "    g_music_vol = volume;",
        "    if(fade_in < 0) fade_in = (id < MSL_NSONGS) ? g_music_info[id].fade_in : 0;",
        "    if(fade_in > 1){",
        "        music_write_volume(0);",
        "        g_mtr_mode = 3; g_mtr_vol = volume; g_mtr_i = 0; g_mtr_n = fade_in;",
        "    } else {",
        "        music_write_volume(volume);",
        "    }",
        "}",
        "/* `fade_out` < 0 = the fade out of the asset; otherwise the call's own. */",
        "static void music_end(int fade_out){",
        "    if(fade_out < 0)",
        "        fade_out = (g_music_cur >= 0 && g_music_cur < MSL_NSONGS)",
        "                   ? g_music_info[g_music_cur].fade_out : 0;",
        "    if(g_mtr_mode == 4) return;           /* already fading out */",
        "    if(fade_out > 1 && mmActive()){",
        "        g_mtr_mode = 4; g_mtr_vol = g_music_vol; g_mtr_i = 0; g_mtr_n = fade_out;",
        "        return;",
        "    }",
        "    if(g_mtr_mode == 3) g_mtr_mode = 0;",
        "    mmStop(); g_music_cur = -1; g_mloop_end = 0; g_mloop_rel = 0;",
        "}",
        "void music_play(int id, int loop, int volume){ music_begin(id, loop, volume, -1); }",
        "/* ── The jingle and the music under it ─────────────────────────────── */",
        "/* policy 0 = mix (the music goes on), 1 = duck (the music drops to `level`, 0-1024, at",
        "   once, and climbs back over `release` frames when the jingle ends), 2 = pause (the",
        "   music waits, then goes on where it was). One jingle sounds at a time, so a new one",
        "   replaces the old one AND its policy. The end is read from maxmod's second layer. */",
        "void music_jingle(int id, int volume, int policy, int level, int release){",
        "    if(id < 0) return;",
        "    mmJingle((mm_word)id);",
        "    g_jingle_cur = id; g_jingle_frame = 0;   /* a new jingle counts from its own start */",
        "    mmSetJingleVolume((mm_word)volume);",
        "    if(g_jingle_paused){ mmResume(); g_jingle_paused = 0; }",
        "    g_jingle_release = release;",
        "    g_jingle_watch = 1;",
        "    if(policy == 1){",
        "        g_duck = g_duck_to = level;",
        "    } else {",
        "        g_duck_to = 1024;",
        "        g_duck_step = (release > 1) ? (1024 - g_duck + release - 1) / release : 1024;",
        "        if(g_duck_step < 1) g_duck_step = 1;",
        "        if(release <= 1) g_duck = 1024;   /* no climb asked: the old duck ends with its jingle */",
        "    }",
        "    if(policy == 2 && mmActive()){ mmPause(); g_jingle_paused = 1; }",
        "    music_rewrite_volume();",
        "}",
        "/* Once per frame: the jingle's end gives the music back, and the climb goes on. */",
        "static void music_jingle_tick(void){",
        "    if(g_jingle_watch && !mmActiveSub()){",
        "        g_jingle_watch = 0;",
        "        if(g_jingle_paused){ mmResume(); g_jingle_paused = 0; }",
        "        g_duck_to = 1024;",
        "        g_duck_step = (g_jingle_release > 1) ? (1024 - g_duck + g_jingle_release - 1) / g_jingle_release : 1024;",
        "        if(g_duck_step < 1) g_duck_step = 1;",
        "    }",
        "    if(g_duck < g_duck_to){",
        "        g_duck += g_duck_step;",
        "        if(g_duck > g_duck_to) g_duck = g_duck_to;",
        "        music_rewrite_volume();",
        "    }",
        "}",
        "void music_fade_in(int id, int loop, int volume, int frames){",
        "    music_begin(id, loop, volume, frames < 0 ? 0 : frames);",
        "}",
        "void music_stop(void){ music_end(-1); }",
        "void music_fade_out(int frames){ music_end(frames < 0 ? 0 : frames); }",
        "void music_set_volume(int volume){",
        "    g_music_vol = volume;",
        "    if(g_mtr_mode >= 3) g_mtr_vol = volume;   /* the fade now aims at this level */",
        "    music_write_volume(volume);",
        "}",
        "/* Tempo and pitch of the PLAYING module, on maxmod's Q10 scale (0x200-0x800 = 0.5x-2x).",
        "   They last until the next module starts, which re-applies its asset's own. */",
        "void music_set_tempo(int tempo){",
        "    mmSetModuleTempo((mm_word)(tempo < 0x200 ? 0x200 : tempo > 0x800 ? 0x800 : tempo));",
        "}",
        "void music_set_pitch(int pitch){",
        "    mmSetModulePitch((mm_word)(pitch < 0x200 ? 0x200 : pitch > 0x800 ? 0x800 : pitch));",
        "}",
        "/* Loop on another section OF THE PLAYING MODULE; nothing if it has none by this name. */",
        "void music_set_section(int section){",
        "    int i;",
        "    if(g_music_cur < 0) return;",
        "    for(i = 0; i < MUSIC_SECTION_COUNT; i++){",
        "        if(g_music_sec[i].music == g_music_cur && g_music_sec[i].section == section){",
        "            g_mloop_start = g_music_sec[i].start; g_mloop_end = g_music_sec[i].end;",
        "            g_mloop_in = 0; g_mloop_rel = 0;",
        "            return;",
        "        }",
        "    }",
        "}",
        "/* Leave the loop section: the module plays on through the outro, then stops. */",
        "void music_leave_loop(void){",
        "    if(g_mloop_end <= 0) return;",
        "    g_mloop_end = 0;",
        "    g_mloop_rel = 1; g_mloop_last = (int)mmGetPosition();",
        "}",
        "/* The loop section, once per frame. The position only moves at a row boundary, so",
        "   this lands within a frame of the end. A loop that reaches the END of the song is",
        "   caught by its backward wrap: the module restarts at its own restart position,",
        "   below the section start, and we send it back. */",
        "static void music_loop_tick(void){",
        "    int pos;",
        "    if(!mmActive()) return;",
        "    pos = (int)mmGetPosition();",
        "    if(g_mloop_rel){",
        "        /* Released: the module was started in MM_PLAY_LOOP, so it wraps at the end of",
        "           the song. A position that goes BACK is that end — we stop there. */",
        "        if(pos < g_mloop_last){ mmStop(); g_music_cur = -1; g_mloop_rel = 0; return; }",
        "        g_mloop_last = pos;",
        "        return;",
        "    }",
        "    if(g_mloop_end <= 0) return;",
        "    if(pos >= g_mloop_end){ mmPosition((mm_word)g_mloop_start); g_mloop_in = 1; }",
        "    else if(pos >= g_mloop_start){ g_mloop_in = 1; }",
        "    else if(g_mloop_in){ mmPosition((mm_word)g_mloop_start); }",
        "}",
        *_music_cue_runtime_lines(cue_rows, jingle_rows, cue_kinds | jingle_kinds, sound_assets),
        "",
    ]


# Les natures d'un repère, dans l'ordre de `core.models.audio.CUE_KINDS` : c'est le `kind` que porte chaque ligne de la table.
def _cue_resolver(p):
    """`resolve(cue) -> (cible C, volume)` ou None : ce que le build met dans la table pour un repère.

    La cible est résolue ICI : l'index d'une action (la boîte dit à l'exécution vers quoi elle pointe), la constante d'un effet
    ou d'un jingle avec son volume (lu sur la ressource comme `music.jingle` et `sfx.play`). Un repère qui ne vise rien de
    résolu n'a pas de ligne — le validateur le dit, silencieux ici plutôt que faux."""
    from core.models.audio import CUE_JINGLE, CUE_JINGLE_ACTION, CUE_SFX, CUE_SOUND_ACTION
    actions = {CUE_SOUND_ACTION: list(p.sound_action_names(KIND_SOUND)),
               CUE_JINGLE_ACTION: list(p.sound_action_names(KIND_JINGLE))}
    sfx_by_name = {s.name: s for s in getattr(p, "sfx", [])}
    jingle_by_name = {j.name: j for j in getattr(p, "jingles", [])}

    def resolve(cue):
        if cue.kind in actions:
            return (actions[cue.kind].index(cue.target), 0) if cue.target in actions[cue.kind] else None
        if cue.kind == CUE_SFX and cue.target in sfx_by_name:
            return _sfx_const(cue.target), volume_to_effect(sfx_by_name[cue.target].volume)
        if cue.kind == CUE_JINGLE and cue.target in jingle_by_name:
            return _music_const(cue.target), volume_to_module(jingle_by_name[cue.target].volume)
        return None
    return resolve


def _music_cue_rows(p, musics) -> tuple[list[str], set]:
    """Les lignes de la table des repères d'ORDRE, et les natures qu'elles emploient : `{module, ordre, nature, cible, volume}`."""
    if p is None or not any(music.cues for music, _path in musics):
        return [], set()           # sans repère, il n'y a rien à résoudre (ni boîtes, ni effets) : rien d'émis
    from core.models.audio import CUE_KINDS
    from core.music_structure import music_cue_rows
    resolve = _cue_resolver(p)
    rows, kinds = [], set()
    for music, path in musics:
        for order, cue in music_cue_rows(music, path):
            resolved = resolve(cue)
            if resolved is None:
                continue
            kinds.add(cue.kind)
            rows.append(f"    {{ {_music_const(music.name)}, {order}, {CUE_KINDS.index(cue.kind)}, {resolved[0]}, {resolved[1]} }},"
                        f"   /* {music.name} @ {order}: {cue.kind} {cue.target} */")
    return rows, kinds


def _jingle_cue_rows(p, jingles) -> tuple[list[str], set]:
    """Les lignes de la table des repères de JINGLE : même forme, mais le second champ est une IMAGE depuis le début du jingle,
    pas un ordre (cf. `jingle_cue_frames` : maxmod ne donne aucune position sur la couche jingle)."""
    if p is None or not any(j.cues for j in jingles):
        return [], set()
    from core.models.audio import CUE_KINDS
    from core.music_structure import jingle_cue_frames
    resolve = _cue_resolver(p)
    rows, kinds = [], set()
    for jingle in jingles:
        for frame, cue in jingle_cue_frames(jingle):
            resolved = resolve(cue)
            if resolved is None:
                continue
            kinds.add(cue.kind)
            rows.append(f"    {{ {_music_const(jingle.name)}, {frame}, {CUE_KINDS.index(cue.kind)}, {resolved[0]}, {resolved[1]} }},"
                        f"   /* {jingle.name} @ frame {frame}: {cue.kind} {cue.target} */")
    return rows, kinds


def _music_cue_runtime_lines(rows: list[str], jingle_rows: list[str], kinds: set, sound_assets) -> list[str]:
    """Le C des repères : les tables, ce qui les joue, et `music_cue_tick` (une fois par frame).

    Deux observations : la musique par POSITION D'ORDRE (`mmGetPosition`), le jingle par IMAGES comptées depuis `mmJingle`
    (maxmod ne donne aucune position sur sa couche). Sans repère, `music_cue_tick` existe quand même, vide : la boucle
    principale l'appelle sans savoir s'il y en a."""
    if not rows and not jingle_rows:
        return ["static void music_cue_tick(void){}"]
    from core.models.audio import CUE_JINGLE, CUE_JINGLE_ACTION, CUE_KINDS, CUE_SFX, CUE_SOUND_ACTION, Jingle
    code = {kind: CUE_KINDS.index(kind) for kind in CUE_KINDS}
    L = [
        "/* ── Music cues (ROADMAP « Des déclencheurs sur la musique ») ──────────── */",
        "/* {module, position, kind, target, volume}. Kinds: 0 SoundBox action, 1 JingleBox action, 2 effect,",
        "   3 jingle. An action's target is its INDEX: the box says, at run time, what it points to. The position",
        "   is an ORDER for a music, a FRAME since the jingle started for a jingle. */",
        "typedef struct { s16 music, order, kind, id, vol; } MusicCue;",
    ]
    if rows:
        L += [f"#define MUSIC_CUE_COUNT {len(rows)}",
              "static const MusicCue g_music_cue[MUSIC_CUE_COUNT] = {", *rows, "};"]
    if jingle_rows:
        L += [f"#define JINGLE_CUE_COUNT {len(jingle_rows)}",
              "static const MusicCue g_jingle_cue[JINGLE_CUE_COUNT] = {", *jingle_rows, "};"]
    if kinds & {CUE_JINGLE, CUE_JINGLE_ACTION}:
        # La politique envers la musique est celle de l'ASSET (cf. `music:jingle`), une ligne par module-jingle.
        policy = [f"    [{_music_const(m.name)}] = {{ {', '.join(str(v) for v in m.runtime_policy())} }},   /* {m.name} */"
                  for m, _path in (sound_assets or {}).get("music", []) if isinstance(m, Jingle)]
        L += [
            "/* {policy, duck level, release} of each jingle, by module. */",
            "static const s16 g_jingle_policy[MSL_NSONGS + 1][3] = {",
            *policy,
            "};",
            "static void music_cue_jingle(int id, int volume){",
            "    if(id < 0 || id > MSL_NSONGS) return;",
            "    music_jingle(id, volume, g_jingle_policy[id][0], g_jingle_policy[id][1], g_jingle_policy[id][2]);",
            "}",
        ]
    L += ["static void music_cue_fire(const MusicCue *c){", "    switch(c->kind){"]
    if CUE_SOUND_ACTION in kinds:
        L += [f"    case {code[CUE_SOUND_ACTION]}:",
              "        if(g_sound_box_action[c->id] >= 0)",
              "            sfx_play(g_sound_box_action[c->id], g_sound_box_action_vol[c->id], 0);",
              "        break;"]
    if CUE_JINGLE_ACTION in kinds:
        L += [f"    case {code[CUE_JINGLE_ACTION]}:",
              "        if(g_jingle_box_action[c->id] >= 0)",
              "            music_cue_jingle(g_jingle_box_action[c->id], g_jingle_box_action_vol[c->id]);",
              "        break;"]
    if CUE_SFX in kinds:
        L += [f"    case {code[CUE_SFX]}: if(c->id >= 0) sfx_play(c->id, c->vol, 0); break;"]
    if CUE_JINGLE in kinds:
        L += [f"    case {code[CUE_JINGLE]}: music_cue_jingle(c->id, c->vol); break;"]
    L += ["    default: break;", "    }", "}"]
    ticks = []
    if rows:
        L += [
            "/* The music: a position is a cue's when the module ENTERS it, so every lap of a loop fires it again. The",
            "   end of a loop section is never played (the loop sends the module back). */",
            "static void music_cue_music_tick(void){",
            "    int pos, i;",
            "    if(g_music_cur < 0 || !mmActive()){ g_cue_last = -1; return; }",
            "    pos = (int)mmGetPosition();",
            "    if(pos == g_cue_last) return;",
            "    g_cue_last = pos;",
            "    if(g_mloop_end > 0 && pos >= g_mloop_end) return;",
            "    for(i = 0; i < MUSIC_CUE_COUNT; i++)",
            "        if(g_music_cue[i].music == g_music_cur && g_music_cue[i].order == pos) music_cue_fire(&g_music_cue[i]);",
            "}",
        ]
        ticks.append("music_cue_music_tick();")
    if jingle_rows:
        L += [
            "/* The jingle: maxmod reads no position on its layer, so the frames are COUNTED from `music_jingle`.",
            "   The watch is cleared by music_jingle_tick when the jingle ends: no later cue fires. */",
            "static void music_cue_jingle_tick(void){",
            "    int i;",
            "    if(!g_jingle_watch) return;",
            "    for(i = 0; i < JINGLE_CUE_COUNT; i++)",
            "        if(g_jingle_cue[i].music == g_jingle_cur && g_jingle_cue[i].order == g_jingle_frame) music_cue_fire(&g_jingle_cue[i]);",
            "    g_jingle_frame++;",
            "}",
        ]
        ticks.append("music_cue_jingle_tick();")
    L += ["static void music_cue_tick(void){", *[f"    {t}" for t in ticks], "}"]
    return L


def music_runtime_stub_lines() -> list[str]:
    """Le même contrat, sans soundbank : un projet dont l'audio n'a pas pu être construit
    doit encore LIER — les scripts appellent ces fonctions."""
    return [
        "void music_play(int id, int loop, int volume){(void)id;(void)loop;(void)volume;}",
        "void music_fade_in(int id, int loop, int volume, int frames)"
        "{(void)id;(void)loop;(void)volume;(void)frames;}",
        "void music_stop(void){}",
        "void music_fade_out(int frames){(void)frames;}",
        "void music_set_volume(int volume){(void)volume;}",
        "void music_set_tempo(int tempo){(void)tempo;}",
        "void music_set_pitch(int pitch){(void)pitch;}",
        "void music_set_section(int section){(void)section;}",
        "void music_leave_loop(void){}",
        "void music_jingle(int id, int volume, int policy, int level, int release)"
        "{(void)id;(void)volume;(void)policy;(void)level;(void)release;}",
        "",
    ]


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
