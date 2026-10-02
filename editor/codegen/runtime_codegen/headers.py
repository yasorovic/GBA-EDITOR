"""
runtime_codegen/headers.py — Génération de actor_types.h et runtime_api.h.

Entrées  : Project, liste (Actor, SpriteAsset), présence audio
Sorties  : fichiers écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from typing import Optional

from core.app_info import APP_NAME
from core.models.sprite import AnimState, SpriteAsset
from core.models.scene import Actor
from core.project import Project
from codegen.c_names import sym as c_sym, scene_actor_sym
from core.app_paths import RUNTIME_DIR
import codegen.build_output as build_output
from codegen.runtime_codegen.gen_camera import project_cameras
from codegen.oam_alloc import scene_oam_layout, project_actor_count, project_oam_entry_count


def actorname_ids(p: Project) -> dict:
    """Id de LOOKUP par SYMBOLE de nom d'acteur, distinct, dans l'ordre de
    première rencontre à travers les scènes.

    C'est la clé du `runtime_get_actor` d'un script partagé (« L'acteur
    appartient à sa scène », décision C) : une dimension de recherche GLOBALE,
    distincte des symboles C qualifiés par scène. « Cursor » de la scène A et
    « Cursor » de la scène B partagent cet id — c'est justement ce qui permet à
    une caméra partagée de demander « le Cursor de la scène active » — sans
    partager pour autant leur `TAG_<Scène>_Cursor`."""
    ids: dict[str, int] = {}
    for sc in p.scenes:
        for a in sc.actors:
            if getattr(a, "active", True):
                ids.setdefault(c_sym(a.name), len(ids))
    return ids


def generate_actor_types(p: Project) -> None:
    """Écrit actor_types_static.h (copie) et actor_types.h (généré).

    TAG_* et POOL_* sont émis PAR SCÈNE (ROADMAP v0.17, T1) : chaque scène
    repart de la base OAM 0, ses acteurs actifs numérotés 0..N-1, puis les pools
    qu'elle déclare. Les symboles de pool sont préfixés par la scène
    (`<Scène>_<Prefab>`), car chaque scène compile ses propres unités de prefab
    contre SA géométrie — plus de plage project-wide unique. La géométrie n'est
    pas recalculée ici : elle est LUE de `scene_oam_layout`."""
    _types_static = RUNTIME_DIR / "include" / "actor_types_static.h"
    if _types_static.exists():
        build_output.copy(_types_static, p.src_dir / "actor_types_static.h")

    h = [
        "/* actor_types.h — struct Actor partagée entre main.c et les scripts */",
        f"/* Généré par {APP_NAME} */",
        "#ifndef ACTOR_TYPES_H",
        "#define ACTOR_TYPES_H",
        "#include <gba_types.h>",
        "",
    ]

    # Tags de boxes de collision — `Project.collision_tags()`, la même liste que
    # le sélecteur de tag du CollisionEditor et la matrice de Project Settings.
    # Project-wide (une box porte le même tag quelle que soit la scène) : c'est
    # la seule définition de « quels tags de collision existent ».
    box_tags = list(p.collision_tags()) or ["body"]

    for ti, tag in enumerate(box_tags):
        h.append(f"#define BOXTAG_{c_sym(tag).upper()} {ti}")
    h.append("")
    h.append('#include "actor_types_static.h"')
    h.append("")

    # Un bloc par scène. TAG_<Actor> pour ses acteurs ACTIFS (même ordre et même
    # base 0 que ce que `main_gen` pose dans `g_actors` au scene_init), puis
    # TAG_<Scène>_<Prefab> et la géométrie de la plage — POOL_<Scène>_<Prefab>_
    # START/_SIZE/_GROUP/_INSTANCES. Le script transpilé en a besoin pour
    # dimensionner son état par instance et retrouver le slot d'un `self`
    # (`self - &g_actors[START]`) ; compilé PAR scène, il lit ces bornes-ci.
    for sc in p.scenes:
        lay = scene_oam_layout(p, sc)
        h.append(f"/* ── Scène {sc.name} ─────────────────────────────── */")
        i = 0
        for actor in sc.actors:
            if not getattr(actor, "active", True):
                continue
            h.append(f"#define TAG_{scene_actor_sym(sc.name, actor.name).upper()} {i}")
            i += 1
        for pl in lay.pools:
            u = pl.sym.upper()
            h.append(f"#define TAG_{u} {pl.start}  /* prefab pool début */")
            h.append(f"#define POOL_{u}_START {pl.start}")
            # ROADMAP v0.23 : le pool se dit en INSTANCES, le build multiplie par
            # les parties. _SIZE = entrées de `g_actors` réellement payées ; les
            # trois autres constantes permettent au C émis de passer de l'une à
            # l'autre sans recalculer.
            h.append(f"#define POOL_{u}_SIZE {pl.size}")
            h.append(f"#define POOL_{u}_GROUP {pl.group}")
            h.append(f"#define POOL_{u}_INSTANCES {pl.instances}")

    # ACTORNAME_* — id de lookup par nom logique (runtime_get_actor, décision C).
    _names = actorname_ids(p)
    if _names:
        h.append("/* ── Noms d'acteurs : clé de lookup runtime (scripts partagés) ── */")
        for s, i in _names.items():
            h.append(f"#define ACTORNAME_{s.upper()} {i}")

    h += ["", "#endif /* ACTOR_TYPES_H */", ""]
    build_output.write(p.src_dir / "actor_types.h", "\n".join(h))


def generate_runtime_api(
    p: Project,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    has_sound: bool,
    all_scenes=None,   # liste de Scene — pour SCENE_IDX_* et scene_switch()
) -> None:
    """Écrit runtime_api_inline.h (copie) et runtime_api.h (généré)."""
    # gba_font.h retiré : police 1bpp dont le consommateur (`text_init()`)
    # n'existe plus depuis l'asset Font — elle était encore recopiée dans
    # chaque build sans qu'aucune ligne ne la lise.
    for static_h in ("runtime_api_inline.h", "gba_engine.h", "gba_debug.h"):
        src_h = RUNTIME_DIR / "include" / static_h
        if src_h.exists():
            build_output.copy(src_h, p.src_dir / static_h)
    _api_static = RUNTIME_DIR / "include" / "runtime_api_inline.h"

    # Taille de `g_actors[]` : la scène la plus gourmande (MAX, pas somme) —
    # chaque scène repart de la base 0 et réutilise la même RAM (ROADMAP v0.17).
    total_actors = project_actor_count(p)
    total_oam_entries = project_oam_entry_count(p)

    # Prototypes de l'API, DÉRIVÉS de gba_engine.h pour le sous-ensemble exposé
    # par le catalogue (cf. api_prototypes — le « 4e lecteur »). Émis AVANT
    # runtime_api_inline.h : les impls inline de celui-ci les voient. Un nom exposé
    # présent dans le moteur mais illisible casserait le build en silence — on
    # le refuse tout de suite, à voix haute.
    from codegen.runtime_codegen.api_prototypes import (
        build_prototype_block, exposed_engine_names, build_enum_defines,
        build_window_region_defines,
    )
    engine_src = (RUNTIME_DIR / "include" / "gba_engine.h").read_text(
        encoding="utf-8", errors="ignore")
    proto_decls, proto_unparsed = build_prototype_block(engine_src, exposed_engine_names())
    enum_defines = build_enum_defines()
    winr_defines = build_window_region_defines(engine_src)
    if proto_unparsed:
        raise RuntimeError(
            "Prototypes d'API illisibles dans gba_engine.h : "
            f"{', '.join(sorted(proto_unparsed))}. Le header d'API serait "
            "incomplet — signature à simplifier, ou extracteur à étendre "
            "(codegen/runtime_codegen/api_prototypes.py).")

    a = [
        "/* runtime_api.h — l'API C que voient les scripts (généré) */",
        f"/* Généré par {APP_NAME} */",
        "#ifndef RUNTIME_API_H",
        "#define RUNTIME_API_H",
        '#include "actor_types.h"',
        "",
        f"#define G_ACTOR_COUNT {total_actors}",
        f"#define G_OAM_ENTRY_COUNT {total_oam_entries}",
        "",
        "/* Énumérations matérielles — générées depuis api.py (api_prototypes.py). */",
        *enum_defines,
        "",
        "/* Régions de window — extraites de gba_engine.h (pas une énum du catalogue). */",
        *winr_defines,
        "",
        "/* Prototypes de l'API exposée — dérivés de gba_engine.h (api_prototypes.py). */",
        *proto_decls,
        "/* Support interne des `$locale` dans les littéraux text.draw. */",
        "extern void text_args_clear(void);",
        "extern void text_arg_set(int n, int value);",
        "",
        '#include "runtime_api_inline.h"',
        "",
    ]

    if has_sound:
        a += [
            "#include <maxmod.h>",
            "/* API audio — miroir direct des fonctions maxmod (mm_sound_effect, mmEffectEx,",
            "   mmEffectVolume/Panning/Cancel, mmStart/Pause/Resume/Stop/Active, mmSet*Volume). */",
            "/* Une référence d'effet vaut 0 quand maxmod n'en a pas donné : soit",
            "   aucun des 8 canaux n'était libre (l'effet ne sonne pas), soit les 16",
            "   handles étaient pris (il sonne, sans référence). Deux plafonds, et",
            "   un seul zéro — mesuré au désassemblage, cf. ROADMAP v0.8.6.",
            "   Un handle PÉRIMÉ ne fait rien : maxmod range un compteur dans le",
            "   handle et le relit à chaque appel, donc les cinq réglages ci-dessous",
            "   deviennent des non-opérations silencieuses. Rien à garder ici. */",
            "static inline int sfx_slot(mm_sfxhand h){return (int)(h & 0xFF) - 1;}",
            "/* La hauteur COURANTE de chaque effet, en facteur 6.10 (1024 = normale).",
            "   mmEffectRate n'est pas un facteur — il écrit la fréquence brute du",
            "   mixeur, inutilisable sans le taux d'origine de l'échantillon. Le seul",
            "   réglage relatif, mmEffectScaleRate, est CUMULATIF : sans mémoire du",
            "   facteur courant, set_pitch(120) appelé deux fois monterait deux fois.",
            "   16 entrées, comme le pool de handles de maxmod. Défini dans main.c. */",
            "extern mm_hword g_sfx_rate[16];",
            "/* `hold` dit si l'appelant TIENT cet effet (ROADMAP v0.8.8).",
            "   Mesuré dans mmAllocChannel : un canal libre est pris d'abord, sinon",
            "   le canal d'ARRIÈRE-PLAN le plus faible est volé, et un canal CUSTOM",
            "   ne l'est JAMAIS. Demander une référence (handle = 0) fait un canal",
            "   CUSTOM ; ne pas en vouloir (handle = 255) laisse le canal volable.",
            "   D'où la règle : ce qu'on tient est protégé, ce qu'on lâche peut céder",
            "   la place — au lieu que le neuvième bruitage d'une frame chargée soit",
            "   perdu en silence. */",
            "static inline mm_sfxhand sfx_play(int id, int volume, int hold){",
            "    mm_sound_effect ex;",
            "    ex.id = (mm_word)id; ex.rate = (mm_hword)1024;",
            "    ex.handle = (mm_hword)(hold ? 0 : 255);",
            "    ex.volume = (mm_byte)volume; ex.panning = (mm_byte)128;",
            "    mm_sfxhand h = mmEffectEx(&ex);",
            "    int s = sfx_slot(h);",
            "    if(s >= 0 && s < 16) g_sfx_rate[s] = 1024;",
            "    return h;",
            "}",
            "static inline void sfx_set_volume(mm_sfxhand h, int volume){mmEffectVolume(h,(mm_word)volume);}",
            "static inline void sfx_set_panning(mm_sfxhand h, int panning){mmEffectPanning(h,(mm_byte)panning);}",
            "static inline void sfx_stop(mm_sfxhand h){mmEffectCancel(h);}",
            "static inline int  sfx_is_playing(mm_sfxhand h){return (int)mmEffectActive(h);}",
            "static inline void sfx_set_pitch(mm_sfxhand h, int rate){",
            "    int s = sfx_slot(h);",
            "    if(s < 0 || s >= 16 || rate <= 0) return;",
            "    mmEffectScaleRate(h, (mm_word)(((mm_word)rate << 10) / g_sfx_rate[s]));",
            "    g_sfx_rate[s] = (mm_hword)rate;",
            "}",
            "static inline void sfx_set_effects_volume(int volume){mmSetEffectsVolume((mm_word)volume);}",
            "static inline void music_play(int id, int loop, int volume){",
            "    mmStart((mm_word)id, loop ? MM_PLAY_LOOP : MM_PLAY_ONCE);",
            "    mmSetModuleVolume((mm_word)volume);",
            "}",
            "static inline void music_stop(void){mmStop();}",
            "static inline void music_pause(void){mmPause();}",
            "static inline void music_resume(void){mmResume();}",
            "static inline int  music_is_playing(void){return mmActive();}",
            "static inline void music_set_volume(int volume){mmSetModuleVolume((mm_word)volume);}",
            "",
            "/* ── Jingle — la SEULE superposition de la console ──────────────── */",
            "/* mmJingle() est la deuxième couche de module de maxmod, avec son propre",
            "   scaler. C'est le seul endroit où deux sources musicales sonnent",
            "   ensemble — donc le seul endroit où un duck a un sens ici.",
            "   Trois contraintes matérielles, à respecter et non à contourner :",
            "     - il NE BOUCLE PAS : c'est une fanfare, jamais un thème ;",
            "     - il est plafonné à 4 canaux (doc maxmod), pris sur les 8 ;",
            "     - il n'y en a qu'UN à la fois. */",
            "static inline void music_jingle(int id, int volume){",
            "    mmJingle((mm_word)id);",
            "    mmSetJingleVolume((mm_word)volume);",
            "}",
            "static inline void music_jingle_volume(int volume){mmSetJingleVolume((mm_word)volume);}",
            "static inline int  music_jingle_playing(void){return mmActiveSub();}",
            "",
            "/* ── Boîtes à état sonores (ROADMAP v0.8.7) ─────────────────────── */",
            "/* Définies dans main.c, appelées depuis les scripts — qui sont d'autres",
            "   unités de compilation. Les tables, elles, restent privées à main.c :",
            "   seul son stepper d'animation les lit. */",
            "void sound_box_set_state(int state);",
            "void jingle_box_set_state(int state);",
            "void music_box_trigger(int trigger);",
            "",
            "/* ── Transitions musicales (ROADMAP v0.8.3) ─────────────────────── */",
            "/* DEUX transitions, et deux seulement, parce que le matériel n'en tient",
            "   pas plus : maxmod n'a qu'une couche de module qui boucle (mmJingle ne",
            "   boucle pas, par construction). Aucun fondu ENCHAÎNÉ n'est possible sur",
            "   cette console ; ne pas en reproposer un.",
            "     mode 1 — fondu traversant : le volume tombe à 0, on change, il remonte.",
            "              Marche entre deux morceaux quelconques ; laisse un creux.",
            "     mode 2 — coupe à la position : on attend la frontière de motif, puis on",
            "              démarre l'autre module au MÊME index d'ordre. Sans creux, en",
            "              mesure — c'est ce qui enchaîne deux variantes d'un morceau.",
            "   L'état vit dans main.c (une seule unité de compilation le porte). */",
            "extern int g_mtr_mode, g_mtr_id, g_mtr_loop, g_mtr_vol;",
            "extern int g_mtr_i, g_mtr_n, g_mtr_row;",
            "static inline void music_fade_to(int id, int loop, int volume, int frames){",
            "    /* Sous deux frames il n'y a pas de fondu à jouer : on bascule sec",
            "       plutôt que de faire semblant. */",
            "    if(frames < 2){ music_play(id, loop, volume); return; }",
            "    g_mtr_mode = 1; g_mtr_id = id; g_mtr_loop = loop; g_mtr_vol = volume;",
            "    g_mtr_i = 0; g_mtr_n = frames;",
            "}",
            "static inline void music_cut_to(int id, int loop, int volume){",
            "    /* Rien ne joue : il n'y a aucune position à respecter. */",
            "    if(!mmActive()){ music_play(id, loop, volume); return; }",
            "    g_mtr_mode = 2; g_mtr_id = id; g_mtr_loop = loop; g_mtr_vol = volume;",
            "    g_mtr_row = (int)mmGetPositionRow();",
            "}",
        ]
    else:
        a += [
            # Le type de la référence existe même sans son : un script qui
            # écrit `local pas = sfx:play(...)` se compile dans un projet où
            # aucun asset audio n'est encore importé, et échouerait sinon sur
            # un type inconnu plutôt que sur ce qui manque vraiment.
            "typedef int mm_sfxhand;",
            "static inline int  sfx_play(int id, int volume, int hold)"
            "{(void)id;(void)volume;(void)hold;return 0;}",
            "static inline void sfx_set_volume(int h, int volume){(void)h;(void)volume;}",
            "static inline void sfx_set_panning(int h, int panning){(void)h;(void)panning;}",
            "static inline void sfx_stop(int h){(void)h;}",
            "static inline int  sfx_is_playing(int h){(void)h;return 0;}",
            "static inline void sfx_set_pitch(int h, int rate){(void)h;(void)rate;}",
            "static inline void sfx_set_effects_volume(int volume){(void)volume;}",
            "static inline void music_play(int id, int loop, int volume){(void)id;(void)loop;(void)volume;}",
            "static inline void music_stop(void){}",
            "static inline void music_pause(void){}",
            "static inline void music_resume(void){}",
            "static inline int  music_is_playing(void){return 0;}",
            "static inline void music_set_volume(int volume){(void)volume;}",
            "static inline void music_jingle(int id, int volume){(void)id;(void)volume;}",
            "static inline void music_jingle_volume(int volume){(void)volume;}",
            "static inline int  music_jingle_playing(void){return 0;}",
            "static inline void sound_box_set_state(int s){(void)s;}",
            "static inline void jingle_box_set_state(int s){(void)s;}",
            "static inline void music_box_trigger(int t){(void)t;}",
            "static inline void music_fade_to(int id, int loop, int volume, int frames)"
            "{(void)id;(void)loop;(void)volume;(void)frames;}",
            "static inline void music_cut_to(int id, int loop, int volume)"
            "{(void)id;(void)loop;(void)volume;}",
        ]

    # ── destroy() + SoundFxComponent("on_destroy") ─────────────────────
    # `actor_destroy_internal` (runtime_api_inline.h) ne connaît que le
    # matériel : désactiver l'actor. Le SFX déclaré sur le trigger
    # "on_destroy" est une donnée PAR PROJET (quel Sfx, pour quel TAG), donc
    # elle vit ici, pas dans le fichier statique partagé entre tous les
    # projets. Les deux tableaux sont DÉFINIS dans main.c (même patron que
    # g_sfx_rate), indexés par `Actor.tag` — même TAG que actor_types.h,
    # cf. main_gen._sfx_on_destroy_table. `self:destroy()` ET `other:destroy()`
    # passent tous les deux par ce wrapper (scripting/codegen.py,
    # `_emit_destroy`) : c'est le SEUL endroit commun aux deux, la cible d'un
    # `other:destroy()` n'étant pas un symbole connu au build.
    a += [
        "",
        # Tables PAR SCÈNE indexées par TAG, `main_gen` les pose au scene_init
        # (comme `g_active_cmap`) : depuis que les TAG repartent de 0 par scène
        # (ROADMAP v0.17, T3), un tableau global unique ne pourrait plus les
        # distinguer. D'où un POINTEUR vers la table de la scène courante.
        "extern const s16 *g_sfx_on_destroy_id;",
        "extern const u8  *g_sfx_on_destroy_vol;",
        # `sfx_play` existe dans les deux branches ci-dessus (réel ou stub
        # sans effet) : ce wrapper n'a donc pas à distinguer has_sound — les
        # deux tableaux, définis dans main.c, sont tout -1 quand il n'y a
        # aucun SoundFxComponent en on_destroy dans le projet.
        "static inline void actor_destroy_with_sfx(Actor* s){",
        "    int id = g_sfx_on_destroy_id[s->tag];",
        "    if(id >= 0) sfx_play(id, g_sfx_on_destroy_vol[s->tag], 0);",
        "    actor_destroy_internal(s);",
        "}",
    ]

    # spawn_<Scène>_<Prefab>() — défini dans main.c, un par (scène, prefab
    # déclaré). Per-scène depuis la compilation par scène (ROADMAP v0.17, T1) :
    # deux scènes qui poolent le même prefab ont chacune leur plage OAM, donc
    # leur propre fonction. `scene_oam_layout` est la source des couples.
    spawn_protos: list[str] = []
    for sc in p.scenes:
        for pl in scene_oam_layout(p, sc).pools:
            spawn_protos.append(f"extern Actor* spawn_{pl.sym}(int x, int y);")
    if spawn_protos:
        a.append("")
        a.append("/* spawn_<Scène>_<Prefab>() — défini dans main.c, vu par les scripts.")
        a.append("   Rend un Actor* sur l'instance née, ou NULL si le pool est plein")
        a.append("   (ROADMAP v0.17 T6) — un handle directement utilisable, et un")
        a.append("   `if not b then` qui marche vraiment (un -1 était toujours vrai). */")
        a += spawn_protos

    # Constantes ANIM_* par SpriteAsset — résolues à la compile par le transpileur
    done_sprites: set[str] = set()
    for _, sprite in scene_actors:
        if sprite and sprite.states and sprite.name not in done_sprites:
            done_sprites.add(sprite.name)
            a.append("")
            a.append(f"/* Animations : {sprite.name} */")
            for i, st in enumerate(sprite.states):
                a.append(f"#define ANIM_{c_sym(st.name).upper()} {i}")

    if all_scenes:
        a.append("")
        a.append("/* Indices de scènes — utilisés par scene:switch() */")
        for i, sc in enumerate(all_scenes):
            a.append(f"#define SCENE_IDX_{c_sym(sc.name).upper()} {i}")
        a += [
            "",
            "extern int g_next_scene;",
            "static inline void scene_switch(int idx){ g_next_scene = idx; }",
        ]

    # Constantes LAYER_* — un fond posé dans une scène (bg_slot 0-3), adressable
    # depuis un script (layer.set_scroll(LAYER_X, ...)) sans littéral magique.
    # `sym` (bg_layer_sym_for) inclut déjà le bg_slot → pas de collision entre
    # deux layers de la même scène référençant le même asset à des slots
    # différents. Dédupliquée : un layer partagé (même asset+slot) entre
    # plusieurs scènes ne produit qu'une seule constante.
    if all_scenes:
        from codegen.runtime_codegen.gen_scene_query import bg_info
        seen_layer_syms: set[str] = set()
        layer_lines: list[str] = []
        for sc in all_scenes:
            for bi in bg_info(p, sc):
                sym_u = bi["sym"].upper()
                if sym_u in seen_layer_syms:
                    continue
                seen_layer_syms.add(sym_u)
                layer_lines.append(f"#define LAYER_{sym_u} {bi['bg']}")
        if layer_lines:
            a.append("")
            a.append("/* Fonds posés dans les scènes — un par (asset, bg_slot) unique */")
            a += layer_lines

    # Constantes CAM_* — l'index d'une caméra dans la table du runtime, tel que
    # `camera:switch(CAM_X)` l'attend. Même ordre que `project_cameras`, qui
    # émet la table : les deux dérivent de la même liste, sinon un script
    # activerait la mauvaise caméra.
    _cams = project_cameras(p)
    if len(_cams) > 1:
        a.append("")
        a.append("/* Caméras du projet — utilisées par camera:switch() */")
        a.append("#define CAM_DEFAULT 0")
        for i, cam in enumerate(_cams):
            if cam is not None:
                a.append(f"#define CAM_{c_sym(cam.name).upper()} {i}")

    # Constantes WIN_* — le rang matériel (WINR_0/WINR_1) d'un WindowSlot,
    # décidé par l'allocateur (`window_alloc.py`, cf. ARCHITECTURE.md
    # « Windows — le pochoir »). Une window n'appartient qu'à une scène, mais
    # son nom est unique au PROJET (même contrainte que les caméras) : une
    # seule passe sur toutes les scènes suffit à émettre le `#define`.
    from codegen.window_alloc import scene_window_layout
    _win_lines: list[str] = []
    for _sc in getattr(p, "scenes", []):
        _layout = scene_window_layout(p, _sc)
        for _name, _slot in _layout.slots.items():
            _win_lines.append(f"#define WIN_{c_sym(_name).upper()} {_slot}")
    if _win_lines:
        a.append("")
        a.append("/* Windows nommées du projet — utilisées par window.* */")
        a += _win_lines

    # Tables de séquences d'input (ROADMAP « Les inputs personnalisés ») :
    # DÉFINIES (non `static`) dans main.c par `main_gen` — chaque unité de
    # scène/acteur qui appelle `input_seq_pressed` sur cette action a besoin
    # de la voir, comme `g_sfx_on_destroy_id` ci-dessus.
    from codegen.runtime_codegen.input_layout import compute_input_layout
    _seq_symbols = sorted(compute_input_layout(p).seq_table_defs)
    if _seq_symbols:
        a.append("")
        a.append("/* Séquences d'input du projet — définies dans main.c */")
        a += [f"extern const u16 {sym}[];" for sym in _seq_symbols]

    a += ["", "#endif /* RUNTIME_API_H */", ""]
    build_output.write(p.src_dir / "runtime_api.h", "\n".join(a))
