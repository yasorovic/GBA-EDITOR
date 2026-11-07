"""Les émetteurs sonores d'Area (`AudioEmitterComponent`) : un effet joué en continu tant que l'écouteur, le centre de la caméra,
est dans la zone audible (la forme de l'Area plus la marge `falloff`).

Une Area est fixe ou suit un acteur POSÉ : il n'y a donc qu'un chemin, une table `const` par scène et un pas par émetteur,
`audio_emitter_step`. Ce pas appelle `sfx_*`, que l'en-tête généré définit APRÈS `runtime_api_inline.h` : il est donc émis dans
cet en-tête (`emitter_function_lines`), et seulement quand le projet a un émetteur."""
from __future__ import annotations

from codegen.c_names import c_ident


def scene_emitters(p, scene) -> list[tuple[int, object, object, object]]:
    """(rang dans `g_areas`, Area, composant, Sfx) des Areas à émetteur actif : une forme, et un effet qui existe dans le projet."""
    sfx_by_name = {s.name: s for s in getattr(p, "sfx", [])}
    from core.models.components import AudioEmitterComponent
    rows = []
    for i, area in enumerate(scene.areas):
        comp = area.effect(AudioEmitterComponent)
        if comp is not None and comp.sfx_name in sfx_by_name and area.shape() is not None:
            rows.append((i, area, comp, sfx_by_name[comp.sfx_name]))
    return rows


def project_has_emitters(p) -> bool:
    return any(scene_emitters(p, scene) for scene in getattr(p, "scenes", []) or [])


def emitter_globals_lines(p, all_scene_data: list[dict]) -> list[str]:
    """`g_snd_h` : la référence de l'effet en cours de chaque émetteur, dimensionnée sur la scène la plus fournie."""
    n = max((len(scene_emitters(p, d["scene"])) for d in all_scene_data), default=0)
    return [f"int g_snd_h[{max(1, n)}] EWRAM_BSS;   /* l'effet en cours de chaque émetteur de la scène (0 = rien) */"]


def emitter_init_lines(p, scene) -> list[str]:
    """À l'entrée de la scène : les effets de la scène précédente sont coupés, la mémoire repart à zéro."""
    if not project_has_emitters(p):
        return []
    return ["    for(unsigned _i=0;_i<sizeof(g_snd_h)/sizeof(g_snd_h[0]);_i++){ if(g_snd_h[_i]) sfx_stop(g_snd_h[_i]); g_snd_h[_i]=0; }"]


def emitter_tick_lines(p, scene) -> list[str]:
    """La table `const` des émetteurs de la scène et la boucle qui les parcourt. Vide sans émetteur."""
    from core.models.audio import volume_to_effect
    rows = scene_emitters(p, scene)
    if not rows:
        return []
    table = [f"        {{&g_areas[{i}],SFX_{c_ident(comp.sfx_name)},{volume_to_effect(round(sfx.volume * comp.volume / 100))},"
             f"{comp.falloff},{1 if comp.panning else 0}}}," for i, _a, comp, sfx in rows]
    return ["    /* Émetteurs sonores des Areas */",
            f"    static const AudioEmitter _snd[{len(rows)}]={{", *table, "    };",
            f"    for(u8 _k=0;_k<{len(rows)};_k++) audio_emitter_step(&_snd[_k],&g_snd_h[_k]);"]


def emitter_function_lines() -> list[str]:
    """Le type et le pas d'un émetteur (C), émis dans l'en-tête généré après les fonctions `sfx_*`."""
    return [
        "/* Émetteurs sonores d'Area. `volume` : 0-255 (échelle des effets) ; `falloff` : pixels hors de la forme. L'écouteur est",
        "   le centre de la caméra. Plein volume dans la forme, puis linéaire jusqu'à 0 à `falloff` pixels (distance de Tchebychev).",
        "   Hors de la zone l'effet est coupé. Une fois fini, il repart à la frame suivante tant que l'écouteur est dans la zone. */",
        "typedef struct { Area* area; s16 sfx; u8 volume; u8 falloff; u8 pan; } AudioEmitter;",
        "static void __attribute__((unused)) audio_emitter_step(const AudioEmitter* e, int* h) {",
        "    const Area* ar = e->area;",
        "    int vol = 0;",
        "    int lx = cam_x + 120, ly = cam_y + 80;",
        "    int x0 = (ar->x >> 8) + ar->box.x, y0 = (ar->y >> 8) + ar->box.y;",
        "    if (ar->active && !ar->held && ar->box.active) {",
        "        int x1 = x0 + ar->box.w, y1 = y0 + ar->box.h;",
        "        int dx = lx < x0 ? x0 - lx : (lx > x1 ? lx - x1 : 0);",
        "        int dy = ly < y0 ? y0 - ly : (ly > y1 ? ly - y1 : 0);",
        "        int d = dx > dy ? dx : dy;",
        "        debug_sound_emitter_test();",
        "        if (d == 0) vol = e->volume;",
        "        else if (d < e->falloff) vol = (e->volume * (e->falloff - d)) / e->falloff;",
        "    }",
        "    if (vol <= 0) { if (*h) { sfx_stop(*h); *h = 0; } return; }",
        "    if (*h && sfx_is_playing(*h)) sfx_set_volume(*h, vol);",
        "    else *h = sfx_play(e->sfx, vol, 1);",
        "    if (*h && e->pan) {",
        "        int p = ((x0 + ((ar->box.w) >> 1)) - lx) * 127 / 120;",
        "        sfx_set_panning(*h, 128 + (p < -127 ? -127 : (p > 127 ? 127 : p)));",
        "    }",
        "}",
    ]
