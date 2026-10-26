"""runtime_codegen/gen_main_loop.py — le `main()` de main.c : démarrage du matériel, du son, puis la boucle de frame."""
from __future__ import annotations

from codegen.c_names import sym as c_sym


def main_lines(p, sprite_offsets: dict, start_idx: int, start_scene: str, n_scenes: int, has_sound: bool,
               soundbank_h, has_transitions: bool) -> list[str]:
    """`int main(void)` : init, copie des tuiles de sprites en VRAM, boucle (fondu, son, entrées, tick de la scène)."""
    L: list[str] = []
    L.append("int main(void){")
    L.append("    irqInit(); irqEnable(IRQ_VBLANK);")
    # Ouvre le canal de log mGBA : sans ce `0xC0DE`, mGBA traite les écritures de `debug:log`
    # comme des accès E/S inconnus (« Stub I/O register write: FFF700 »). Stub vide hors build debug.
    L.append("    debug_init();")
    # Temps d'accès de la SRAM et de la ROM, posés avant toute lecture. Inconditionnel : c'est une
    # écriture de registre, et la rendre conditionnelle ferait dépendre le
    # démarrage d'un état du projet pour économiser un cycle.
    from codegen.memory_timing import waitcnt_value
    _s = p.settings
    L.append(f"    memory_timing_init(0x{waitcnt_value(_s.rom_wait_first, _s.rom_wait_second, _s.rom_prefetch, _s.cartridge_mib):04X});")

    if has_sound and soundbank_h.exists():
        # mmVBlank() DOIT être lié à l'IRQ vblank (doc maxmod.h) — sans ça le
        # mixeur n'avance jamais et le son ne sort qu'en grésillement/silence.
        L.append("    irqSet(IRQ_VBLANK, mmVBlank);")
        # Les canaux logiciels, partagés par la musique et les effets — un
        # réglage de projet depuis la v0.8.8 (défaut 8, la valeur qui était en
        # dur). `mmInitDefault()` attend un NOMBRE de canaux, pas une taille :
        # MM_SIZEOF_MODLIST n'existe pas dans maxmod.h. Ce qu'elle alloue est
        # chiffré par `audio.sound_channels_bytes`.
        from core.models.audio import sound_channels_bytes
        _ch = int(getattr(p.settings, "sound_channels", 8))
        L.append(f"    mmInitDefault((mm_addr)soundbank_bin, {_ch});   /* {_ch} channels —"
                 f" {sound_channels_bytes(_ch)} B of heap */")
        from codegen.runtime_codegen.sound_emit import music_start_lines
        L += music_start_lines(p)
        # Plus de mmStart au boot. Il démarrait la PREMIÈRE musique du projet,
        # quelle qu'elle soit — un emplacement réservé qui rendait un bref
        # éclat de la mauvaise piste avant que la scène de départ ne pose la
        # sienne. C'est `Scene.music` qui décide maintenant.

    # Sprites VRAM (une seule fois au démarrage — toutes scènes). Les
    # palettes OBJ ne sont PLUS copiées ici : chaque scene_init_X() charge
    # déjà la sienne (g_pal_obj_{sym}) au bon moment, y compris pour la
    # scène de départ (appelée juste après, cf. boucle principale ci-dessous).
    if sprite_offsets:
        L.append("    /* Sprite tiles → OBJ VRAM (all scenes) */")
        for name, base in sprite_offsets.items():
            ss = f"sprite_{c_sym(name)}"
            L.append(f"    copy16(OBJ_VRAM+{base}*16, {ss}Tiles, {ss}TilesLen);")

    L.append(f"    g_next_scene = {start_idx};   /* {start_scene} */")
    L.append("    while(1){")
    if has_transitions:
        L += [
            "        /* Language reload (phase 4): forces the safeguard below",
            "           to reinitialise the SAME scene, like a real change. The "
            "CLOSING",
            "           fade does not play this time (g_current_scene forced to -1,",
            "           hence \"no outgoing scene\" on the transition side) — a "
            "lang:set()",
            "           and a scene:switch() on the same frame would lose that fade, "
            "a case",
            "           rare enough not to be handled separately. */",
            "        if(g_lang_reload){ g_lang_reload=0; g_current_scene=-1; }",
            "        /* Closing: the scene being LEFT decides the fade, and freezes",
            "           during it. Nothing to play → immediate switch. */",
            "        if(g_trans_phase==0 && g_next_scene!=g_current_scene){",
            "            int m = (g_current_scene>=0 && g_current_scene<"
            f"{n_scenes}) ? g_scene_vtable[g_current_scene].trans_mode : 0;",
            "            if(m){",
            "                g_trans_phase = 1; g_trans_i = 0;",
            "                g_trans_n = g_scene_vtable[g_current_scene].trans_frames;",
            "                transition_begin(m); transition_fade(0);",
            "            } else scene_enter();",
            "        }",
        ]
    else:
        L += [
            "        /* Language reload (phase 4): forces the safeguard just",
            "           below to reinitialise the SAME scene. */",
            "        if(g_lang_reload){ g_lang_reload=0; g_current_scene=-1; }",
            "        if(g_next_scene != g_current_scene){",
            "            g_current_scene = g_next_scene;",
            f"            if(g_current_scene>=0 && g_current_scene<{n_scenes})",
            "                g_scene_vtable[g_current_scene].init();",
            "        }",
        ]
    L.append("        VBlankIntrWait();")
    # la fenêtre mesurée est EXACTEMENT le travail d'une frame —
    # de la reprise après ce VBlankIntrWait() à l'entrée du suivant. Hors build
    # debug, `debug_budget_start` est un stub vide éliminé à l'inlining (-O2) :
    # aucun coût, pas un drapeau testé à chaque frame.
    L.append("        debug_budget_start();")
    if has_sound and soundbank_h.exists():
        L.append("        mmFrame();   /* maxmod.h doc: _must_ be called every frame "
                 "*/")
        L.append("        music_jingle_tick();")        # avant le pas des fondus : ils écrivent le volume avec le duck déjà à jour
        L.append("        music_transition_tick();")
        L.append("        music_loop_tick();")
        L.append("        music_cue_tick();")          # après la boucle : la fin d'une section de boucle n'est jamais jouée
    L += [
        "        _g_frame++;",
        "        scanKeys();",
        "        _g_keys_held    = keysHeld();",
        "        _g_keys_pressed = keysDown();",
        "        _input_ring_push(_g_keys_held);",
        "        _input_update_hold_frames(_g_keys_held);",
        # Premier bouton pressé : le nombre de frames écoulées, qui dépend du joueur, brasse la graine.
        "        _g_rand_ticks++;",
        "        if(!_g_rand_seeded && _g_keys_pressed){ _g_rand_seed ^= _g_rand_ticks * 2654435761u; _g_rand_seeded = 1; }",
    ]
    if has_transitions:
        # La musique et le compteur de frames continuent pendant le fondu : une
        # transition est un effet d'affichage, pas une pause du moteur. Seul le
        # tick de la scène s'arrête, et seulement à la fermeture.
        L += [
            "        if(g_trans_phase==1){",
            "            g_trans_i++;",
            "            transition_fade((16*g_trans_i)/g_trans_n);",
            "            if(g_trans_i>=g_trans_n) scene_enter();",
            "            continue;   /* the outgoing scene is frozen */",
            "        }",
            "        if(g_trans_phase==2){",
            "            g_trans_i--;",
            "            transition_fade((16*g_trans_i)/g_trans_n);",
            "            if(g_trans_i<=0){ transition_end(); g_trans_phase = 0; }",
            "        }",
        ]
    L += [
        f"        if(g_current_scene>=0 && g_current_scene<{n_scenes})",
        "            g_scene_vtable[g_current_scene].tick();",
        # Compté après tick() : oam_update() (fin de scene_tick_*) vient de
        # copier shadow_oam vers l'OAM réel — c'est l'état FINAL de la frame,
        # pas un instantané pris en cours d'écriture. Bit 9 seul (0x0200,
        # sans bit 8) = sprite désactivé (cf. gba_engine.h, oam_hide_all).
        # Boucle éliminée à -O2 quand debug_budget_report ne fait rien (hors
        # build debug) : son résultat n'est alors utilisé nulle part.
        "        { int _dbg_oam = 0;",
        "          for (int _i = 0; _i < 128; _i++)",
        "              if ((shadow_oam[_i].attr0 & 0x0300) != 0x0200) _dbg_oam++;",
        "          debug_budget_report(_dbg_oam); }",
        "    }",
        "    return 0;",
        "}",
    ]
    return L
