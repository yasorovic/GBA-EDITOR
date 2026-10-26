"""runtime_codegen/gen_globals.py — les variables globales de main.c : acteurs, entrées OAM, états de script,
entrées manette, caméra, scène courante, pool partagé."""
from __future__ import annotations

from codegen.runtime_codegen.gen_affine import scene_has_affine
from codegen.runtime_codegen.gen_sfx_trigger import sfx_on_destroy_table


def globals_lines(p, all_scene_data: list[dict], scene_pis: list, n_actors: int, n_oam_entries: int,
                  input_layout) -> list[str]:
    """Les définitions des globales du moteur. `input_layout` est celui de `compute_input_layout`, aussi lu par le tick."""
    L: list[str] = []
    # ── Globals ───────────────────────────────────────────────────
    # `g_actors` est réutilisé d'une scène à l'autre (base 0) : dimensionné sur la scène la plus gourmande, il porte à tout instant
    # les acteurs de la SEULE scène vivante. C'est un état volumineux, jamais une
    # routine chaude ; EWRAM_BSS évite de consommer les 32 Kio d'IWRAM réservés
    # au code et aux petits états runtime.
    L += [
        f"Actor g_actors[{n_actors}] EWRAM_BSS;",
        # Un bit par emplacement : les blocs de 32 sans vivant sont sautés par POOL_EACH (actor_types_static.h).
        f"u32 g_alive_bits[{max(1, (n_actors + 31) // 32)}];",
        # Époque des changements de vie et curseur de `actor:get(nom, i)` (actor_types_static.h).
        "u32 g_alive_epoch;",
        "PoolCursor g_nth;",
        # L'état de script de chaque emplacement : un bloc de `OBJ_STATE_STRIDE` octets (obj_state.h).
        f"u32 g_obj_state[{n_actors} * OBJ_STATE_STRIDE / 4] EWRAM_BSS;",
        f"OamEntry g_oam_entries[{n_oam_entries}] EWRAM_BSS;",
        # Le calcul affine mémoïsé par entrée d'affichage (cf. `AffCache`), pour les seuls projets qui ont un sprite affine.
        *([f"AffCache g_aff_cache[{n_oam_entries}] EWRAM_BSS;"]
          if any(scene_has_affine(d["scene_actors"], spi) for d, spi in zip(all_scene_data, scene_pis)) else []),
        "const AppearanceInit* g_appearance_init;   /* activation constants of the "
        "active scene */",
    ]
    # SoundFxComponent en trigger="on_destroy" — tables PAR SCÈNE indexées par
    # TAG, plus un pointeur que chaque scene_init fait pointer sur la sienne
    # (comme `g_active_cmap`). Depuis que les TAG repartent de 0 par scène
    # (T3), une table globale unique ne pourrait plus les distinguer. Lues par
    # `actor_destroy_with_sfx()` — le SEUL point commun à `self:destroy()` et
    # `other:destroy()` (scripting/codegen.py, `_emit_destroy`), la cible n'y
    # étant pas toujours un symbole connu au build.
    L += sfx_on_destroy_table(p, all_scene_data, scene_pis)
    # Anneau + compteurs d'input :
    # profondeur et bitset `buffered` calculés depuis les actions RÉELLEMENT
    # déclarées et interrogées par le projet — 0 action bufferisée, 0 octet
    # payé (`computeinput_layout`, seule source, la même que `lua_compiler.py`
    # pour le catalogue de chaque script).
    _buffered_bytes = max(1, (len(input_layout.buffered_bits) + 7) // 8)
    for _symbol, _steps in input_layout.seq_table_defs.items():
        # NON static : `runtime_api.h` en déclare l'extern pour les unités de
        # scène/acteur qui appellent `input_seq_pressed` sur cette action.
        L.append(f"const u16 {_symbol}[] = {{{', '.join(_steps)}}};")
    L += [
        "u32   _g_keys_held    = 0;",
        "u32   _g_keys_pressed = 0;",
        f"u16   _g_input_ring[{input_layout.ring_depth}];",
        "int   _g_input_ring_pos = 0;",
        f"const int g_input_ring_depth = {input_layout.ring_depth};",
        "u8    _g_key_hold_frames[10];",
        f"u8    _g_input_buffered_consumed[{_buffered_bytes}];",
        "int   cam_x = 0, cam_y = 0;",
        "int   g_bounds_x = 0, g_bounds_y = 0, g_bounds_w = 0, g_bounds_h = 0;",
        "int   g_cam_active = 0;",
        # Zone morte du suivi et cadre écran de la caméra ACTIVE : recopiés de sa
        # ligne de table par camera_switch(), réglables par `camera.margin` et
        # `camera.frame` (cf. runtime_api_inline.h).
        "int   g_cam_margin_x = 0, g_cam_margin_y = 0;",
        "int   g_cam_frame_w = 240, g_cam_frame_h = 160;",
        # État de la secousse — un événement en cours, pas un réglage : il vit
        # ici et non dans la table des caméras (cf. runtime_api_inline.h).
        "int   g_shake_amp = 0, g_shake_left = 0, g_shake_total = 1;",
        "int   g_shake_dx = 0, g_shake_dy = 0;",
        "u32   g_shake_seed = 2463534242u;",
        # Transition musicale en cours — un événement, comme la secousse : il
        # vit ici, pas dans un réglage d'asset (cf. headers.py pour les deux
        # modes et pourquoi il n'y en a pas un troisième).
        "int   g_mtr_mode = 0, g_mtr_id = 0, g_mtr_loop = 1, g_mtr_vol = 255;",
        "int   g_mtr_i = 0, g_mtr_n = 1, g_mtr_row = 0;",
        "int   _g_frame = 0;",
        # Graine de `math_rand`, UNE pour tout le jeu : `static` dans le header,
        # chaque unité de script avait la sienne et tirait la même suite.
        "u32   _g_rand_seed = 73244475u;",
        # Brassée une fois, au premier bouton pressé (cf. la boucle principale) : sans ça, chaque mise sous tension
        # rejouait la même suite de tirages.
        "u32   _g_rand_ticks = 0;",
        "int   _g_rand_seeded = 0;",
        # Taille du monde de la scène courante, lue par `scene.size` : déclarée
        # `extern` dans runtime_api_inline.h et posée par chaque scene_init — il
        # manquait sa DÉFINITION, et le lien échouait sur tout projet.
        "int   g_scene_w = 0, g_scene_h = 0;",
        # Défilement autorisé par la scène courante — lu par `scene.scroll_h/v`.
        "int   g_scene_scroll_h = 1, g_scene_scroll_v = 0;",
        "int   g_scene_collision_layer = 0;",
        "int   g_current_scene = -1;",
        "int   g_scene_placed = 0;   /* actors placed in the active scene "
        "(actor:get(i)) */",
        "const s16 *g_placed_parent = 0;   /* scene parent slot of each placed actor, -1 = none (a:parent) */",
        # Le pool PARTAGÉ de la scène courante (cf. runtime_api_inline.h) : posé par chaque scene_init.
        "int   g_spool_start = 0, g_spool_end = 0, g_spool_hw = 0, g_spool_entry = -1, g_spool_free = 0;",
        "const u8 *g_spool_grp = 0, *g_spool_part = 0, *g_spool_parent = 0;",
        "int   g_affine_dropped = 0;   /* instances affines dessinées sans matrice (les 32 sont prises) */",
        "int   g_next_scene    = -1;",
        "",
    ]
    return L
