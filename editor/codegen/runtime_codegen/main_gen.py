"""
runtime_codegen/main_gen.py — Génération de main.c.

Entrées  : Project, Scene, bg_pairs, scene_actors, sound_assets, prefab_sprites
Sortie   : p.src_dir/main.c
"""
from __future__ import annotations

import math
import shutil
from typing import Optional

from core.models.palette import OWN_PAL_BANK
from core.models.components import (CollisionBoxComponent, SpriteComponent,
                                    affine_sprite_component)
from core.models.sprite import SpriteAsset
from core.models.scene import Actor, Scene
from core.project import Project
from core.models.field_value import (FieldValue as _FV,
                                     var_names_from_project as _var_names)
# `region_fill_container` vit dans le modèle (règle de mise en page pure) et se
# réexporte ici : `palette_alloc` l'importe de ce module depuis toujours, et
# ROADMAP le cite sous ce nom. Cf. `core.models.ui_region`.
from core.models.ui_region import region_fill_container
from codegen.palette_alloc import scene_bank_layout, effective_palette_colors
# Les requêtes de police vivent désormais dans font_emit (leur domaine) — main_gen
# les CONSOMME. Import de haut niveau : font_emit ne remonte plus vers main_gen,
# le cycle d'autrefois est rompu (cf. TodoTechnique).
from codegen.font_emit import project_fonts, encodable_project_fonts
# Émission de la sauvegarde (SRAM) — extraite dans son sous-module (A3). main_gen
# n'en consomme que le contrôle bloquant et les tables.
from codegen.runtime_codegen.gen_save import save_fatal, save_lines
# Table des caméras et suivi — extraite (A3). `project_cameras` est RÉ-EXPORTÉ ici :
# data_tables.py et headers.py l'importent depuis main_gen (l'ordre de vérité de la
# table runtime). `camera_target_index` reste privé à gen_camera.
from codegen.runtime_codegen.headers import actorname_ids
from codegen.runtime_codegen.gen_camera import (
    camera_sym, project_cameras, scene_camera_index, camera_follow_lines)
# Palettes en RAM (scène) + catalogue — extraites (A3). `_layout_palette_words`
# reste privé à gen_palette.
from codegen.runtime_codegen.gen_palette import (
    resolve_backdrop_color, scene_obj_palette_words, scene_bg_palette_words,
    palettes_lines)
# Couche de REQUÊTES partagée (A3) — analyse d'acteurs/collision/arbre, rendue de
# la donnée, jamais du C. Base des couches : les émetteurs de domaine (affine,
# sprite, ui…) l'importeront aussi, vers le bas, sans cycle.
from codegen.runtime_codegen.gen_scene_query import (
    parent_depths, actors_can_collide, has_solid_box, scene_has_cmap,
    has_col_event,
    bg_info, scene_world_size, scene_anim_descriptors,
    sprite_offsets_for, obj_tiles_used, ui_image_sprites, scene_ui_images,
    ui_item_geometry)
# Slots de matrice affine OAM — extraits (A3), au-dessus de la couche de requêtes.
# `affine_oam_lines_dynamic` émet du C ; les deux autres rendent de la donnée.
from codegen.runtime_codegen.gen_affine import (
    affine_entry, compute_affine_info, affine_oam_lines_dynamic)
# Domaine sprite/animation — extrait (A3), au-dessus des requêtes (n'en dépend pas).
# `frame_action_ids`/`frame_sfx_syms` rendent la donnée par frame ; les trois autres
# émettent le C des tables et du tick.
from codegen.runtime_codegen.gen_appearance import appearance_layout, appearance_table_lines
from codegen.runtime_codegen.gen_sprite import (
    frame_action_ids, frame_sfx_syms, actor_frame_event_lines,
    anim_tables_for, anim_tick_lines, anim_tick_variants, oam_write_lines, Appearance)
# Tables d'interface au niveau PROJET — extraites (A3), au-dessus des requêtes.
# `_ui_images_lines` reste ici (glue vers `obj_text_alloc`) et appelle
# `emit_ui_images_c` d'ici ; `region_actor_index`/`ui_element_index` sont aussi
# consommés par `fonts_and_texts_lines` (domaine texte, resté).
from codegen.runtime_codegen.gen_ui import (
    emit_ui_images_c, emit_ui_lists_c, emit_ui_elements_c,
    region_actor_index, ui_element_index)
# Géométrie OAM per-scène (ROADMAP v0.17, T1+T2+T3) : source de vérité des plages
# de pool et de la taille de `g_actors`. main_gen en est un LECTEUR.
from codegen.oam_alloc import (scene_oam_layout, project_actor_count, project_oam_entry_count, scene_obj_ui_slots,
                               owner_appearances, initial_appearance)
# Domaine texte/police — extrait (A3). Réservation VRAM du texte, analyse des
# fonds de conteneur, émission des tables de polices/textes/zones. `main_gen`
# n'en consomme que ce que son orchestration et ses émetteurs de scène relisent.
from codegen.runtime_codegen.gen_text import (
    scene_text_reservation, obj_text_alloc, fonts_and_texts_lines,
    scene_region_colors, scene_region_backdrops, gen_ui_texts)
from codegen.window_alloc import scene_window_layout
# `prefab_group` est réexporté : `headers.py` l'importe depuis ce module depuis
# toujours, et sa définition a rejoint le budget d'acteurs (v0.17) — l'éditeur
# en a besoin pour afficher les slots bien avant qu'un build existe.
from codegen.actor_budget import prefab_group
from codegen.grit_conversion import (
    count_frames, sprite_unique_frames, seq_key,
)
from codegen.c_names import sym as c_sym, scene_actor_sym
from core.app_paths import RUNTIME_DIR
import codegen.build_output as build_output


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def _sfx_trigger_info(p: Project, owner) -> tuple[Optional[str], int, str]:
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


def _sfx_on_destroy_table(p: Project, all_scene_data: list[dict],
                           scene_pis: list[list[dict]]) -> list[str]:
    """Le SFX à jouer juste avant qu'un actor de tel TAG soit désactivé, indexé
    par TAG — mais PAR SCÈNE (ROADMAP v0.17, T3 : les TAG repartent de 0 par
    scène, un tableau global ne les distinguerait plus). On émet donc un couple
    de tables constantes par scène (id, -1 = aucun ; volume) et DEUX pointeurs
    globaux que chaque scene_init fait pointer sur les siens (comme
    `g_active_cmap`, cf. `_gen_scene_init`).

    Même base de TAG que `headers.generate_actor_types` : acteurs actifs de la
    scène numérotés 0..N-1 dans l'ordre de `scene.actors`, puis chaque pool à son
    `start` (toutes les instances d'un pool PARTAGENT ce TAG, posé au spawn)."""
    out = [
        "const s16 *g_sfx_on_destroy_id  = 0;",
        "const u8  *g_sfx_on_destroy_vol = 0;",
    ]
    for d, spi in zip(all_scene_data, scene_pis):
        sym = c_sym(d["scene"].name)
        n = max([len(d["scene_actors"])]
                + [p2["start"] + p2["size"] for p2 in spi] + [1])
        ids  = ["-1"] * n
        vols = ["0"]  * n
        for tag, (actor, _sprite) in enumerate(d["scene_actors"]):
            sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, actor)
            if sfx_sym and sfx_trig == "on_destroy":
                ids[tag], vols[tag] = sfx_sym, str(sfx_vol)
        for p2 in spi:
            sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, p2["prefab"])
            if sfx_sym and sfx_trig == "on_destroy":
                ids[p2["start"]], vols[p2["start"]] = sfx_sym, str(sfx_vol)
        out += [
            f"static const s16 g_sfx_on_destroy_id_{sym}[{n}]  = {{{', '.join(ids)}}};",
            f"static const u8  g_sfx_on_destroy_vol_{sym}[{n}] = {{{', '.join(vols)}}};",
        ]
    out.append("")
    return out


def _layer_tiles_used(p, bi: dict) -> int:
    """Tuiles réellement générées pour un layer. Deux sources selon le chemin :
    le sidecar pour un fond compressé (connu sans grit), l'en-tête grit sinon."""
    ba = p.get_background(bi["stem"]) if bi.get("stem") else None
    if bi.get("compressed") and ba is not None and ba.tileset:
        # Les animés posés partagent le charblock de leur hôte : leurs tuiles
        # comptent dans ce que le calque charge (cf. codegen/bg_anim).
        from codegen.bg_anim import layer_tile_count
        return layer_tile_count(p, ba)
    header = p.grit_out_dir / f"{bi['sym']}.h"
    if header.exists():
        import re
        m = re.search(rf"{bi['sym']}TilesLen\s+(\d+)", header.read_text())
        if m:
            return int(m.group(1)) // 32
    # Inconnu (grit pas encore passé) : on suppose le pire pour ne pas
    # sur-promettre de la place à un voisin.
    return 512


def _apply_vram_layout(p, scene, bgi: list[dict], res: dict) -> None:
    """Remplace le placement historique des maps par celui de l'allocateur.

    Écrit `sbb` sur place, et mémorise le placement du texte sur la scène pour
    que `_gen_scene_init` le retrouve — les deux doivent voir EXACTEMENT la même
    allocation, sinon les tuiles et la map du texte partent à des adresses qui
    ne se correspondent plus.

    `res` (la réservation de texte) est CALCULÉE PAR L'APPELANT et passée ici :
    la place vidéo dépend de ce que le texte réserve, mais ce module ne connaît
    pas le domaine texte. C'est ce qui garde `bg_info` (une requête pure de
    géométrie) et cette pose VRAM à l'écart de `scene_text_reservation` et de
    tout le sous-système d'analyse UI qu'il tire — la soudure BG↔texte est
    rompue au profit d'une dépendance explicite, orchestrée d'en haut."""
    from codegen.vram_alloc import scene_layout
    slots = {bi["bg"]: _layer_tiles_used(p, bi) for bi in bgi}
    maps  = {bi["bg"]: bi["map_sbb_count"] for bi in bgi}
    lay = scene_layout(slots, maps, p.scene_ui_bg_slot(scene), res["total"],
                       ui_slots=p.scene_ui_bg_slots(scene))
    for bi in bgi:
        bi["sbb"] = lay.map_sbb[bi["bg"]]
    scene._vram_layout = lay   # consommé par _gen_scene_init
    scene._ui_fills = res["fills"]
    scene._ui_fill_indices = res["fill_indices"]
    scene._ui_mono_tiles = res["mono_tiles"]
    scene._ui_needs_surface = res["needs_surface"]
    scene._ui_img_fills = res["img_fills"]
    scene._ui_img_assets = res["img_assets"]
    scene._ui_images = res["ui_images"]
    scene._ui_image_layout = res["img_layout"]
    scene._ui_reservation = res   # relu par le log de build


def _log_vram_layout(scene, emit) -> None:
    """Dit où l'allocateur a posé le bloc du texte, et pourquoi le cas échéant.

    Émis à CHAQUE build et pas seulement en repli : c'est la première chose
    qu'on cherche quand un fond ne rentre plus."""
    lay = getattr(scene, "_vram_layout", None)
    if lay is None or emit is None:
        return
    budget = ", ".join(f"BG{s}:{n}" for s, n in sorted(lay.budget.items()))
    emit("log_line",
         f"[vram] scène '{scene.name}' : texte en CBB{lay.text_cbb} "
         f"base {lay.text_base}, map SBB{lay.text_sbb} — {lay.note}"
         + (f" — budget tuiles {budget}" if budget else ""))

    # Sur quelle base la place a été réservée : un repli sur tout le projet est
    # un choix de l'outil, sinon on cherche pourquoi le décor a moins de tuiles.
    res = getattr(scene, "_ui_reservation", None)
    if not res:
        return
    names = res.get("font_names")
    if names is None:
        why = ("toutes les polices du projet — une police est choisie au "
               "runtime (text.set_font non littéral) ou un script n'a pas pu "
               "être analysé")
    else:
        why = "polices " + (", ".join(sorted(names)) if names else "(aucune)")
    # Nommer la police par défaut : c'est elle qui est chargée même dans une
    # scène sans une ligne de texte, et un `Scene.font_name` introuvable retombe
    # en silence sur la première du projet. Relue depuis la réservation, pas
    # recalculée — le log doit dire ce qui a RÉELLEMENT servi à réserver.
    _dn = res.get("default_font") or ""
    emit("log_line",
         f"[vram] scène '{scene.name}' : {res['total']} tuile(s) réservée(s) au "
         f"texte ({res['mono_tiles']} de glyphes — {why}"
         + (f" — défaut {_dn}" if _dn else "") + ")")


def _scene_pi(p: Project, scene: Scene) -> list[dict]:
    """La géométrie des pools de CETTE scène, lue de `scene_oam_layout` (source
    de vérité unique, ROADMAP v0.17). `sym` est PRÉFIXÉ PAR LA SCÈNE
    (`<Scène>_<Prefab>`) : chaque scène compile ses unités de prefab contre sa
    propre plage, donc les appels `{sym}_pool_init`/`{sym}_on_update` du main.c
    ciblent bien `actor_<Scène>_<Prefab>.c`. `size` compte les ENTRÉES réservées
    (instances × parties, ROADMAP v0.23), `start` repart de la base OAM 0 de la
    scène (après ses acteurs posés)."""
    return [
        {"prefab": pl.prefab, "sym": pl.sym, "prefab_sym": pl.prefab_sym,
         "start": pl.start, "size": pl.size,
         "entry_start": pl.entry_start, "member_entries": pl.member_entries,
         "entries_per_instance": pl.entries_per_instance,
         "instances": pl.instances, "group": pl.group}
        for pl in scene_oam_layout(p, scene).pools
    ]


# ─── sections du main.c ───────────────────────────────────────────────────────


def _section_spawn(pool_info: list[dict], p: Project, obj_layout,
                   actor_defined_events: dict[str, set[str]] | None = None) -> list[str]:
    """`pool_info` : les pools de LA scène courante (`_scene_pi`), symboles
    déjà préfixés `<Scène>_<Prefab>`. `obj_layout` : le layout OBJ de CETTE
    scène — chaque scène résout l'index de banque de ses prefabs poolés dans son
    propre layout (fin de la « scène d'ancrage », ROADMAP v0.17, T1)."""
    if not pool_info:
        return []

    def _def(sym, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    L = ["/* ── Spawn helpers (prefabs poolés) ────────────────────── */"]
    _alay = appearance_layout(p, [], pool_info, obj_layout)   # mêmes numéros que scene_init
    for pi in pool_info:
        s, start, size, pf = pi["sym"], pi["start"], pi["size"], pi["prefab"]
        _epi = pi["entries_per_instance"]
        # L'entrée OAM du membre k de l'instance (0 = racine), ou None : un membre
        # sans sprite — marqueur, point de tir — n'a ni entrée ni écriture d'affichage.
        _ranks = pi["member_entries"]
        _E = lambda k: f"_e+{_ranks[k]}" if _ranks[k] >= 0 else None
        _e0 = _E(0)
        sp, sprite = _shown(p, pf)      # l'apparence de départ fixe les constantes d'init
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(pf, "pal_bank", OWN_PAL_BANK), own) if obj_layout else 0
        if pal is None:
            pal = 0
        boxes = [c for c in pf.components if isinstance(c, CollisionBoxComponent)][:4]

        # pool_init est toujours généré par le transpileur, extern inconditionnel
        L.append(f"extern void {s}_pool_init(Actor* self);")
        for ev, sig in [
            ("on_start",           f"extern void {s}_on_start(Actor* self);"),
            ("on_update",          f"extern void {s}_on_update(Actor* self);"),
            ("on_late_update",     f"extern void {s}_on_late_update(Actor* self);"),
            ("on_collide",         f"extern void {s}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_enter", f"extern void {s}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_exit",  f"extern void {s}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_tile_collide",    f"extern void {s}_on_tile_collide(Actor* self, int normal_x, int normal_y);"),
        ]:
            if _def(s, ev):
                L.append(sig)

        group = pi.get("group", 1)
        L += [
            # Rend un Actor* sur l'instance née (ROADMAP v0.17 T6) : un handle
            # directement chaînable côté script, et NULL quand le pool est plein —
            # là où l'ancien -1, un entier, ressortait TOUJOURS vrai dans un test.
            f"Actor* spawn_{s}(int x, int y) {{",
            # Le pas est le GROUPE, pas 1 (ROADMAP v0.23) : une instance
            # occupe la racine PUIS ses enfants, contiguës. Chercher de un en
            # un tomberait sur l'enfant libre d'une instance vivante et
            # écrirait une racine au milieu d'un boss. Un prefab plat a un
            # groupe de 1 : la boucle est alors exactement celle d'avant.
            # `_e` avance du nombre d'ENTRÉES de l'instance : les deux espaces
            # (acteurs, entrées OAM) n'ont pas le même pas.
            f"    for(int _i={start}, _e={pi['entry_start']}; _i<{start+size}; _i+={group}, _e+={_epi}) {{",
            f"        if(!g_actors[_i].active) {{",
        ]

        # Transform affine : `(Actor){0}` remet TOUT à zéro, y compris le slot de
        # matrice posé par scene_init et les échelles neutres (256 = ×1). Un
        # prefab affine spawné repartait donc avec une échelle de ZÉRO — matrice
        # dégénérée, sprite illisible — et avec le slot 0, celui d'un autre actor.
        # Le slot appartient à la SCÈNE (il change d'une scène à l'autre) : on le
        # préserve. L'échelle et la rotation appartiennent au PREFAB : on les
        # repose comme au scene_init, c'est-à-dire à l'état neutre du template.
        _sp_aff = affine_entry(pf, sp, 0) if sp else None
        _sp_aff = _sp_aff if _e0 else None    # sans entrée, aucun transform d'affichage
        if _sp_aff:
            L.append(f"            int _aff = g_oam_entries[{_e0}].affine_slot;")
        # L'acteur ET son entrée repartent de zéro ; le lien se repose (-1 : sans sprite).
        L.append(f"            g_actors[_i] = (Actor){{0}}; g_actors[_i].oam_entry = {_e0 or -1};")
        if _e0:
            L.append(f"            g_oam_entries[{_e0}] = (OamEntry){{0}};")
        # Échelle neutre par défaut, comme pour les PARTIES plus bas : `(Actor){0}`
        # laisse scale à ZÉRO. Pour un prefab racine non-affine servant de parent,
        # ce zéro écraserait ses enfants à la composition (même règle d'héritage
        # que côté scène). La branche affine ci-dessous la remplace au besoin par
        # l'échelle authorée du template.
        L.append(f"            g_actors[_i].scale_x = 256; g_actors[_i].scale_y = 256;")
        if _sp_aff:
            L += [
                f"            g_oam_entries[{_e0}].affine_slot = _aff;",
                f"            g_actors[_i].rotation     = {_sp_aff['rotation']};",
                f"            g_actors[_i].scale_x      = {_sp_aff['scale_x']};",
                f"            g_actors[_i].scale_y      = {_sp_aff['scale_y']};",
                f"            g_oam_entries[{_e0}].rotation   = {_sp_aff['sprite_rotation']};",
                f"            g_oam_entries[{_e0}].scale_x = {_sp_aff['sprite_scale_x']};",
                f"            g_oam_entries[{_e0}].scale_y = {_sp_aff['sprite_scale_y']};",
                f"            g_oam_entries[{_e0}].offset_x     = {_sp_aff['offset_x']};",
                f"            g_oam_entries[{_e0}].offset_y     = {_sp_aff['offset_y']};",
            ]
        L += [
            # ROADMAP v0.19 : x/y en Q8 en interne. `x`/`y` ici sont les entiers
            # pixels passés à actor:spawn() par le script — <<8 à l'entrée.
            f"            g_actors[_i].x = x<<8; g_actors[_i].y = y<<8;",
            f"            g_actors[_i].active   = 1;",
            *([f"            g_oam_entries[{_e0}].visible = 1;",
               f"            g_oam_entries[{_e0}].pal_bank = {pal};",
               f"            g_oam_entries[{_e0}].frame_w  = {sprite.frame_w if sprite else 0};",
               f"            g_oam_entries[{_e0}].frame_h  = {sprite.frame_h if sprite else 0};",
               *_appearance_init_lines(p, pf, _e0, "            ",
                                       _alay.member_base.get((pi["sym"], 0)))]
              if _e0 else []),
            f"            g_actors[_i].tag      = TAG_{s.upper()};",
            f"            g_actors[_i].collision.box_count = {len(boxes)};",
        ]
        for bi, cb in enumerate(boxes):
            tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
            _vn = _var_names(p)
            bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
            bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
            L += [
                f"            g_actors[_i].collision.boxes[{bi}].x=(s8){bx}; g_actors[_i].collision.boxes[{bi}].y=(s8){by};",
                f"            g_actors[_i].collision.boxes[{bi}].w=(u8){bw};  g_actors[_i].collision.boxes[{bi}].h=(u8){bh};",
                f"            g_actors[_i].collision.boxes[{bi}].solid={1 if cb.solid else 0}; g_actors[_i].collision.boxes[{bi}].active={1 if cb.active else 0}; g_actors[_i].collision.boxes[{bi}].tag={tag_s};",
            ]
        # ── Les ENFANTS de l'instance ─────────────────────────────
        # Posées juste après la racine, dans l'ordre du template. Leur position
        # n'est pas écrite ici : elle est recomposée depuis la racine dès la
        # frame courante (cf. `_pool_compose_lines`), et l'écrire deux fois
        # laisserait croire qu'elle vient d'ici.
        for k, part in enumerate(getattr(pf, "children", []) or [], start=1):
            p_sc, p_spr = _shown(p, part)
            p_own = list(p_spr.own_palette) if (p_spr and getattr(p_spr, "own_palette", None)) else []
            p_pal = (obj_layout.bank_index(getattr(part, "pal_bank", OWN_PAL_BANK), p_own)
                     if obj_layout else 0) or 0
            p_boxes = [c for c in part.components
                       if isinstance(c, CollisionBoxComponent)][:4]
            _ek = _E(k)      # None : la partie est un marqueur, sans entrée OAM
            L += [
                # Le slot de matrice appartient à la SCÈNE (scene_init le
                # pose) ; `(Actor){0}` l'effacerait, comme il effaçait celui de
                # la racine avant que le même garde-fou soit écrit pour elle.
                *([f"            {{ int _affk = g_oam_entries[{_ek}].affine_slot;"] if _ek else []),
                f"            g_actors[_i+{k}] = (Actor){{0}}; g_actors[_i+{k}].oam_entry = {_ek or -1};",
                *([f"            g_oam_entries[{_ek}] = (OamEntry){{0}};",
                   f"            g_oam_entries[{_ek}].affine_slot = _affk; }}"] if _ek else []),
                # Échelle neutre avant la première composition : `(Actor){0}`
                # laisse un scale de ZÉRO, donc une matrice dégénérée si l'OAM
                # sortait avant le tick qui recompose.
                f"            g_actors[_i+{k}].scale_x = 256; g_actors[_i+{k}].scale_y = 256;",
                f"            g_actors[_i+{k}].active   = 1;",
                *([f"            g_oam_entries[{_ek}].visible = {1 if getattr(part, 'visible', True) else 0};",
                   f"            g_oam_entries[{_ek}].pal_bank = {p_pal};",
                   f"            g_oam_entries[{_ek}].frame_w  = {p_spr.frame_w if p_spr else 0};",
                   f"            g_oam_entries[{_ek}].frame_h  = {p_spr.frame_h if p_spr else 0};",
                   *_appearance_init_lines(p, part, _ek, "            ",
                                           _alay.member_base.get((pi["sym"], k)))]
                  if _ek else []),
                # La partie porte le tag de sa RACINE : un bras de boss touché,
                # c'est le boss qui est touché. Elle n'est pas un autre type
                # d'acteur, elle est un enfant de celui-là.
                f"            g_actors[_i+{k}].tag      = TAG_{s.upper()};",
                f"            g_actors[_i+{k}].collision.box_count = {len(p_boxes)};",
            ]
            for bi, cb in enumerate(p_boxes):
                tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
                _vn = _var_names(p)
                bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
                bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
                L += [
                    f"            g_actors[_i+{k}].collision.boxes[{bi}].x=(s8){bx}; g_actors[_i+{k}].collision.boxes[{bi}].y=(s8){by};",
                    f"            g_actors[_i+{k}].collision.boxes[{bi}].w=(u8){bw};  g_actors[_i+{k}].collision.boxes[{bi}].h=(u8){bh};",
                    f"            g_actors[_i+{k}].collision.boxes[{bi}].solid={1 if cb.solid else 0}; "
                    f"g_actors[_i+{k}].collision.boxes[{bi}].active={1 if cb.active else 0}; "
                    f"g_actors[_i+{k}].collision.boxes[{bi}].tag={tag_s};",
                ]
        L.append(f"            {s}_pool_init(&g_actors[_i]);")
        # SoundFxComponent en trigger="on_spawn" — comme pour les actors de
        # scène ci-dessus, indépendant de tout script sur le prefab.
        sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, pf)
        if sfx_sym and sfx_trig == "on_spawn":
            L.append(f"            sfx_play({sfx_sym}, {sfx_vol}, 0);"
                     f"   /* SoundFxComponent : {pf.name} */")
        if _def(s, "on_start"):
            L.append(f"            {s}_on_start(&g_actors[_i]);")
        L += [
            f"            return &g_actors[_i];",
            f"        }}",
            f"    }}",
            f"    return NULL;",
            f"}}",
            "",
        ]
    return L


def _gen_tile_helpers() -> list[str]:
    """Lecture de la carte de collision, et résolution d'un acteur contre elle.

    La table de profils est ÉMISE depuis `core.models.collision_tiles`, la même
    géométrie que celle dont le canvas tire ses polygones : la physique du jeu
    et le dessin de l'éditeur ne peuvent pas diverger."""
    from core.models.collision_tiles import (
        TILE_COUNT, kind_of, column_surfaces, speed_scale,
    )
    L = [
        "static const u8 *g_active_cmap = NULL;",
        "static int g_cmap_w = 0, g_cmap_h = 0;",
        "#define TILE_SIZE 8",
        "",
        "/* Profil des types de tuiles — ÉMIS depuis core/models/collision_tiles.py,",
        "   jamais écrit à la main ici : c'est la même géométrie que celle que",
        "   l'éditeur dessine. `surface` porte l'ordonnée de la surface dans",
        "   chacune des 8 colonnes de pixels ; pour un SOL la matière va de là au",
        "   bas de la tuile (8 = colonne vide), pour un PLAFOND du haut jusque-là",
        "   (0 = colonne vide). */",
        "#define TK_EMPTY 0",
        "#define TK_SOLID 1",
        "#define TK_FLOOR 2",
        "#define TK_CEIL  3",
    ]
    kinds = ", ".join(str(kind_of(t)) for t in range(TILE_COUNT))
    L.append(f"static const u8 g_tile_kind[{TILE_COUNT}] = {{ {kinds} }};")
    # Cosinus de la pente en virgule fixe 8 bits — 256 à plat. Un pas horizontal
    # sur une pente parcourt √(1+p²) fois plus de distance qu'à plat ; c'est ce
    # facteur qui le ramène à la distance demandée. Précalculé ici : pas de
    # racine carrée à l'exécution, et la table est la même géométrie que le reste.
    # u16 et non u8 : « plat » vaut 256, qui ne tient pas dans un octet.
    scales = ", ".join(str(speed_scale(t)) for t in range(TILE_COUNT))
    L.append(f"static const u16 g_tile_scale[{TILE_COUNT}] = {{ {scales} }};")
    L.append(f"static const u8 g_tile_surface[{TILE_COUNT}][TILE_SIZE] = {{")
    for t in range(TILE_COUNT):
        row = ", ".join(f"{v}" for v in column_surfaces(t))
        L.append(f"    {{ {row} }},")
    L += [
        "};",
        "",
        "int collision_map_tile(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 0;",
        "    return (int)g_active_cmap[ty*g_cmap_w+tx];",
        "}",
        "/* Le seul type qui REPOUSSE horizontalement. Une pente n'est pas un mur,",
        "   sinon personne ne la gravirait : on y monte par la surface. */",
        "static int tile_wall_at(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 1;",
        "    return g_active_cmap[ty*g_cmap_w+tx]==TK_SOLID;",
        "}",
        "/* Ordonnée monde du DESSUS de la matière portant la colonne px.",
        "",
        "   Trois tuiles balayées de haut en bas, la PREMIÈRE trouvée gagnant : celle",
        "   au-dessus des pieds, celle des pieds, celle du dessous. La tuile du DESSUS",
        "   est indispensable — sur une pente, la matière de la colonne suivante vit",
        "   dans la tuile d'au-dessus, et s'arrêter aux pieds fait décrocher l'acteur",
        "   en pleine montée. Une surface plus haute que la box est écartée (`>=top`) :",
        "   elle ne touche pas l'acteur, et l'y hisser le téléporterait sur une",
        "   plateforme qu'il passait dessous.",
        "",
        "   Hors carte par le bas = plein : le monde est une boîte close, comme avant",
        "   que la résolution ne connaisse les pentes. Sans ça un acteur qui rate une",
        "   plateforme tombe indéfiniment — et son sprite reboucle en haut de l'écran,",
        "   l'OAM ne codant Y que sur 8 bits. -1 = rien à portée. */",
        "/* Type de la tuile qui a fourni la dernière surface rendue par",
        "   tile_floor_at — c'est elle qui porte l'acteur, donc elle qui dit à",
        "   quelle pente il marche. Rendu à côté plutôt qu'en valeur de retour :",
        "   un seul appelant s'en sert, et le balayage n'est pas fait deux fois. */",
        "static u8 g_floor_tile = 0;",
        "static int tile_floor_at(int px,int top,int bot){",
        "    g_floor_tile=0;",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=-1;i<2;i++){",
        "        int ty=bot/TILE_SIZE+i;",
        "        if(ty<0) continue;",
        "        if(ty>=g_cmap_h) return g_cmap_h*TILE_SIZE;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID){ if(ty*TILE_SIZE>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE;} continue; }",
        "        if(g_tile_kind[t]==TK_FLOOR){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s<TILE_SIZE && ty*TILE_SIZE+s>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE+s;}",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "/* Symétrique : ordonnée du DESSOUS de la matière au-dessus de la tête.",
        "   Le balayage part de la tête et MONTE — jamais vers le bas, sinon le sol",
        "   sur lequel l'acteur repose serait pris pour un plafond et le pousserait",
        "   dedans. Hors carte par le haut = plein, même boîte close. */",
        "static int tile_ceil_at(int px,int py){",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=0;i<2;i++){",
        "        int ty=py/TILE_SIZE-i;",
        "        if(ty>=g_cmap_h) continue;",
        "        if(ty<0) return 0;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID) return ty*TILE_SIZE+TILE_SIZE;",
        "        if(g_tile_kind[t]==TK_CEIL){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s>0) return ty*TILE_SIZE+s;",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "typedef void (*TileCollideCb)(Actor*,int,int);",
        "/* Résolution d'un acteur contre la carte (cf. ROADMAP v0.6.3).",
        "   L'ordre est la règle : X d'abord — les pentes n'y font pas obstacle —",
        "   puis Y, où la surface est cherchée en TROIS points (les deux coins bas",
        "   et le centre), la plus haute l'emportant : un acteur large ne s'enfonce",
        "   pas dans la pente et franchit une arête proprement.",
        "   `cb` ne fait que PRÉVENIR : la vitesse est annulée dans tous les cas,",
        "   écrire le hook ne désactive donc pas la physique. */",
        "static void __attribute__((unused)) resolve_actor_tiles(Actor*a, TileCollideCb cb){",
        "    if(!g_active_cmap) return;",
        "    /* ROADMAP v0.19 : x/y de l'Actor sont en Q8 (256 = 1 px), mais TOUTE la",
        "       géométrie ci-dessous (tuiles, boxes, pentes) est en pixels, inchangée",
        "       depuis la v0.6.3 — l'arrondi se fait UNE fois à l'entrée (_px/_py) et",
        "       UNE fois à la sortie. _fx/_fy portent le sous-pixel à travers la",
        "       fonction : une frame sans collision sur un axe lui rend EXACTEMENT",
        "       sa position Q8 d'entrée (x == (x>>8)<<8 | x&255, arithmétique deux's",
        "       complément) ; une frame qui clampe (mur, sol, plafond) réémet la",
        "       fraction d'AVANT le clamp — approximation délibérée plutôt qu'une",
        "       remise à zéro par branche, dont le gain serait imperceptible ici. */",
        "    int _px=a->x>>8, _py=a->y>>8, _fx=a->x&255, _fy=a->y&255;",
        "    int was_grounded=a->collision.grounded, dx=_px-a->collision.last_x;",
        "    int moved=dx<0?-dx:dx;",
        "    /* ── Vitesse constante LE LONG du sol ─────────────────────",
        "       Un pas horizontal sur une pente parcourt √(1+p²) fois plus de",
        "       distance qu'à plat : 114 % à 26°, 141 % à 45°, 224 % à 63°. Sans",
        "       correction, plus la pente est raide plus le personnage paraît",
        "       rapide. On ramène donc le pas au cosinus de la pente qu'il",
        "       gravit, lu dans g_tile_scale.",
        "",
        "       Deux garde-fous, parce que le moteur DÉFAIT ici un enfant de ce",
        "       que le script a demandé :",
        "         - il faut être au sol à la frame précédente — un saut, une",
        "           chute ou un vol ne sont pas une marche ;",
        "         - le pas doit tenir dans une tuile. Au-delà, la résolution ne",
        "           prétend déjà plus rien (la sonde ne porte qu'à une tuile), et",
        "           c'est là qu'un script téléporte plutôt qu'il ne marche.",
        "       Le reste (1/256 de pixel) est REPORTÉ : sans lui, un pas de 2 px",
        "       à 45° tomberait toujours sur 1 px, et le personnage ramperait au",
        "       lieu d'aller 1,41 fois moins vite. */",
        "    if(was_grounded && dx && moved<=TILE_SIZE){",
        "        for(int i=0;i<a->collision.box_count;i++){",
        "            CollisionBox*b=&a->collision.boxes[i];",
        "            if(!b->solid||!b->active) continue;",
        "            int l=a->collision.last_x+(int)b->x, r=l+(int)b->w-1;",
        "            int t=_py+(int)b->y;",
        "            tile_floor_at((l+r)>>1, t, t+(int)b->h-1);",
        "            int sc=g_tile_scale[g_floor_tile];",
        "            if(sc<256){",
        "                int want=dx*sc+a->collision.slope_acc;",
        "                int step=want/256;",
        "                a->collision.slope_acc=want-step*256;",
        "                _px=a->collision.last_x+step;",
        "            }",
        "            break;",
        "        }",
        "    }else a->collision.slope_acc=0;",
        "    a->collision.grounded=0;",
        "    for(int i=0;i<a->collision.box_count;i++) a->collision.boxes[i].grounded=0;",
        "    for(int i=0;i<a->collision.box_count;i++){",
        "        CollisionBox*b=&a->collision.boxes[i];",
        "        if(!b->solid||!b->active) continue;",
        "        int left,right,top,bot;",
        "        /* ── X : seuls les blocs pleins repoussent ───────────── */",
        "        if(a->vx!=0){",
        "            left=_px+(int)b->x; right=left+(int)b->w-1;",
        "            top =_py+(int)b->y; bot  =top +(int)b->h-1;",
        "            int hit=0;",
        "            if(a->vx>0){",
        "                for(int cpy=top;cpy<=bot&&!hit;cpy+=TILE_SIZE) hit=tile_wall_at(right,cpy);",
        "                if(!hit) hit=tile_wall_at(right,bot);",
        "                if(hit){_px=(right/TILE_SIZE)*TILE_SIZE-(int)b->x-(int)b->w;",
        "                    a->vx=0; if(cb)cb(a,1,0);}",
        "            }else{",
        "                for(int cpy=top;cpy<=bot&&!hit;cpy+=TILE_SIZE) hit=tile_wall_at(left,cpy);",
        "                if(!hit) hit=tile_wall_at(left,bot);",
        "                if(hit){_px=(left/TILE_SIZE+1)*TILE_SIZE-(int)b->x;",
        "                    a->vx=0; if(cb)cb(a,-1,0);}",
        "            }",
        "        }",
        "        /* ── Plafond : la surface la plus BASSE arrête la tête ─ */",
        "        left=_px+(int)b->x; right=left+(int)b->w-1;",
        "        top =_py+(int)b->y; bot  =top +(int)b->h-1;",
        "        if(a->vy<0){",
        "            int c=-1;",
        "            for(int k=0;k<3;k++){",
        "                int cpx=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "                int cy=tile_ceil_at(cpx,top);",
        "                if(cy>c) c=cy;",
        "            }",
        "            if(c>=0&&top<c){_py=c-(int)b->y; a->vy=0; if(cb)cb(a,0,-1);}",
        "        }",
        "        /* ── Sol : la surface la plus HAUTE porte l'acteur ───── */",
        "        top=_py+(int)b->y; bot=top+(int)b->h-1;",
        "        int g=-1;",
        "        for(int k=0;k<3;k++){",
        "            int cpx=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "            int gy=tile_floor_at(cpx,top,bot);",
        "            if(gy>=0&&(g<0||gy<g)) g=gy;",
        "        }",
        "        if(g>=0){",
        "            int feet=bot+1;",
        "            if(feet>g){",
        "                /* Pénétration : on remonte sur la surface. Aucun plafond",
        "                   de marche — l'auteur a peint une pente, on la gravit. */",
        "                _py=g-(int)b->y-(int)b->h;",
        "                if(a->vy>0) a->vy=0;",
        "                a->collision.grounded=b->grounded=1; if(cb)cb(a,0,1);",
        "            }else if(feet==g){",
        "                /* Pile sur la surface : au sol, et une vitesse vers le",
        "                   bas n'a plus de sens — sans ça elle survit une frame",
        "                   de plus et l'acteur retraverse le sol avant d'être",
        "                   repoussé. */",
        "                if(a->vy>0) a->vy=0;",
        "                a->collision.grounded=b->grounded=1;",
        "            }else if(was_grounded&&a->vy>=0&&g-feet<=moved*2+1){",
        "                /* Collage en descente : l'écart maximal qu'une pente à",
        "                   63° peut creuser pour ce déplacement. Sans lui, toute",
        "                   descente décolle et retombe, donc tressaute. */",
        "                _py=g-(int)b->y-(int)b->h;",
        "                a->collision.grounded=b->grounded=1;",
        "            }",
        "        }",
        "    }",
        "    a->collision.last_x=_px;",
        "    a->x=(_px<<8)|_fx; a->y=(_py<<8)|_fy;",
        "}",
        "",
    ]
    return L


# ─── Helpers affine / origine ─────────────────────────────────────────────────

def _appearances(p, owner, sprite_offsets: dict) -> list:
    """Les `Appearance` d'un porteur, pour l'émission du writer OAM."""
    return [Appearance(sp, sprite_offsets.get(sp.name, 0),
                       getattr(c, "origin_x", 0), getattr(c, "origin_y", 0))
            for c, sp in owner_appearances(p, owner)]


def _shown(p, owner):
    """(composant, sprite) de l'apparence dont les constantes d'INITIALISATION
    valent pour l'entrée : l'apparence affichée au départ, à défaut la première.
    (None, None) sans apparence. Les autres apparences reposent leurs propres
    constantes à leur activation (3c)."""
    apps = owner_appearances(p, owner)
    if not apps:
        return None, None
    n = initial_appearance(p, owner)
    return apps[max(n, 0)]


def _appearance_init_lines(p, owner, entry_expr: str, indent: str, base=None) -> list[str]:
    """Ce que l'init pose pour choisir l'apparence de départ : son rang quand ce
    n'est pas 0 (la RAM démarre à 0), l'entrée CACHÉE si aucune n'est active, et la
    1re ligne de ses constantes d'activation (`base`, cf. gen_appearance) pour un
    porteur à plusieurs apparences."""
    apps = owner_appearances(p, owner)
    n = initial_appearance(p, owner)
    out = []
    if base is not None:
        # `base + 1` : 0 = « rien à activer » (un porteur mono-apparence, dont
        # `actor_set_appearance` doit rester sans effet).
        out.append(f"{indent}g_oam_entries[{entry_expr}].appearance_base = {base + 1};")
    if len(apps) > 1 and n > 0:
        out.append(f"{indent}g_oam_entries[{entry_expr}].appearance = {n};")
    if apps and n < 0:
        out.append(f"{indent}g_oam_entries[{entry_expr}].visible = 0;")
    return out


def _visible_line(indent: str, entry, parent_entry, own_visible) -> list[str]:
    """`visible` d'un enfant = celui de son parent ET le sien. Une entrée OAM
    n'existe que pour un porteur de sprite : un enfant sans sprite n'a rien à
    montrer (aucune ligne), et un parent sans sprite ne masque personne — son
    « visible » vaut vrai. `entry`/`parent_entry` : indices d'entrée, -1 si aucune."""
    if entry == -1:
        return []
    own = 1 if own_visible else 0
    if parent_entry == -1:
        return [f"{indent}g_oam_entries[{entry}].visible = {own};"]
    return [f"{indent}g_oam_entries[{entry}].visible = g_oam_entries[{parent_entry}].visible && {own};"]


def _parent_compose_lines(scene_actors: list, actor_offset: int,
                          placed_entry: list[int]) -> list[str]:
    """Recompose, chaque frame, le transform monde des acteurs qui ont un parent.

    La formule n'est PAS nouvelle : c'est celle que le modèle affine applique
    déjà entre un acteur et son sprite (ARCHITECTURE.md, « Le modèle affine »),
    d'un cran plus haut — l'`Actor` parent tenant la place que tenait l'acteur.
        rotation = somme des degrés
        scale    = produit Q8
        position = parent + R(rotation_parent)·S(scale_parent)·offset_local
    Aucune règle nouvelle à apprendre, et c'est ce qui rend le chantier petit.

    Le transform LOCAL est une CONSTANTE du build : la parenté est authorée, et
    la tranche A n'ouvre pas l'accès script aux parties. Un enfant ne porte donc
    aucun champ de plus dans `g_actors` — le coût annoncé de 144 octets par
    acteur ne bouge pas.

    **L'auteur pose en coordonnées MONDE ; c'est le build qui en tire le
    local.** x/y/rotation/scale gardent donc exactement le sens qu'ils avaient
    au canvas, et un bras se place là où il doit apparaître à l'écran plutôt
    qu'à un offset qu'il faudrait calculer de tête. La conséquence est que la
    scène dessinée dans l'éditeur est EXACTEMENT la frame 0 du jeu : le local
    dérivé ici, recomposé au runtime avec la pose authorée du parent, redonne
    la position authorée de l'enfant.

    La conversion faite ici est réversible, et le canvas s'en sert désormais :
    déplacer un parent y recompose son sous-arbre, et les enfants suivent à
    l'écran comme au runtime. L'auteur voit donc la même hiérarchie vivante des
    deux côtés. (Le champ Position de l'inspecteur reflète aussi ce déplacement
    depuis 2026-09-05 — cf. actor_inspector `_sync_transform_from_canvas`.)

    Tout est en Q8 (ROADMAP v0.19) et l'arrondi reste à l'émission OAM : un
    arrondi par niveau ferait dériver un bras d'un pixel par cran de
    profondeur.

    `visible` se propage ici aussi : cacher un boss cache ses bras, comme un
    conteneur d'UI caché cache son sous-arbre (v0.15). Deux endroits du logiciel,
    une seule règle."""
    depths, _errs = parent_depths(scene_actors)
    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    kids = [(a, j) for j, (a, _) in enumerate(scene_actors)
            if getattr(a, "parent", None) and a.name in depths]
    if not kids:
        return []
    kids.sort(key=lambda t: depths[t[0].name])   # parents avant enfants
    L = ["    /* Hiérarchie d'acteurs — parents avant enfants, profondeur",
         "       calculée au build (ROADMAP v0.23). Même composition que celle",
         "       d'un acteur et de son sprite, d'un cran plus haut. */"]
    import math
    by_name = {a.name: a for a, _ in scene_actors}
    for a, _j in kids:
        c = idx_of[a.name]
        p = idx_of[a.parent]
        par = by_name[a.parent]
        # ── Du MONDE authoré vers le LOCAL ────────────────────────
        # L'inverse exact de la composition émise juste en dessous, appliqué
        # à la POSE AUTHORÉE du parent : on défait sa rotation puis son
        # échelle. Le résultat, recomposé au runtime avec cette même pose,
        # redonne la position que l'auteur a vue au canvas.
        p_rot = float(getattr(par, "rotation", 0) or 0)
        p_sx = float(getattr(par, "scale_x", 1.0) or 1.0) or 1.0
        p_sy = float(getattr(par, "scale_y", 1.0) or 1.0) or 1.0
        dx = float(int(a.x) - int(par.x))
        dy = float(int(a.y) - int(par.y))
        th = math.radians(-p_rot)
        ux = dx * math.cos(th) - dy * math.sin(th)
        uy = dx * math.sin(th) + dy * math.cos(th)
        ox = int(round((ux / p_sx) * 256))
        oy = int(round((uy / p_sy) * 256))
        rot = int(getattr(a, "rotation", 0) or 0) - int(round(p_rot))
        sx = int(round(float(getattr(a, "scale_x", 1.0) or 1.0) / p_sx * 256))
        sy = int(round(float(getattr(a, "scale_y", 1.0) or 1.0) / p_sy * 256))
        L += [
            f"    {{   /* {a.name} dans le repère de {a.parent} */",
            f"        int _pr = g_actors[{p}].rotation;",
            f"        int _px = g_actors[{p}].scale_x, _py = g_actors[{p}].scale_y;",
            f"        int _co = gba_cos(_pr), _si = gba_sin(_pr);",
            f"        int _lx = ({ox} * _px) >> 8, _ly = ({oy} * _py) >> 8;",
            f"        g_actors[{c}].x = g_actors[{p}].x + ((_lx * _co - _ly * _si) >> 8);",
            f"        g_actors[{c}].y = g_actors[{p}].y + ((_lx * _si + _ly * _co) >> 8);",
            f"        g_actors[{c}].rotation = _pr + {rot};",
            f"        g_actors[{c}].scale_x  = (_px * {sx}) >> 8;",
            f"        g_actors[{c}].scale_y  = (_py * {sy}) >> 8;",
            *_visible_line("        ", placed_entry[c - actor_offset], placed_entry[p - actor_offset],
                           getattr(a, "visible", True)),
            f"    }}",
        ]
    return L


def _pool_entry_expr(rank: int):
    """Entrée OAM d'un membre de pool dans `_pool_compose_lines` : `_eb` est la
    1re entrée de l'instance, `rank` le rang du membre. -1 = aucune."""
    return f"_eb+{rank}" if rank >= 0 else -1


def _pool_compose_lines(pi: list[dict]) -> list[str]:
    """La composition des enfants d'un prefab segmenté, chaque frame.

    Même formule que pour les acteurs de scène (`_parent_compose_lines`), mais
    déroulée sur le POOL : une boucle par instance, et les enfants d'une
    instance sont à un décalage constant de sa racine — le groupe est contigu
    et sa taille est une constante du build.

    Un enfant ÉTEINT ne se compose pas, et il n'est PAS rallumé par sa racine :
    sa vie lui appartient (ROADMAP v0.23, tranché le 2026-08-21). Un boss qui
    perd un bras appelle `MonBras:destroy()`, et le bras disparaît pour de bon —
    plus d'OAM, plus de collision. Écrire `enfant.active = racine.active` à
    chaque frame, comme la première version le faisait, annulait cet appel dès
    la frame suivante et sans un mot. La racine, elle, éteint tout en mourant :
    c'est la branche du dessus, et les deux règles ne se marchent pas dessus.

    Comme pour un acteur de scène, la pose authorée d'un enfant est du MONDE
    (elle a été placée par rapport au template posé à l'origine) : le local en
    est dérivé ici, une fois, au build."""
    import math
    L: list[str] = []
    for p2 in pi:
        pf = p2["prefab"]
        parts = list(getattr(pf, "children", []) or [])
        if not parts:
            continue
        group, start, size = p2["group"], p2["start"], p2["size"]
        ranks = p2["member_entries"]      # rang d'entrée de chaque membre, -1 si aucun
        by_name = {pt.name: pt for pt in parts}
        rank = {pt.name: k for k, pt in enumerate(parts, start=1)}
        L += [f"    /* {pf.name} — sous-arbre de chaque instance (ROADMAP v0.23) */",
              f"    for(int _b={start}, _eb={p2['entry_start']}; _b<{start+size}; "
              f"_b+={group}, _eb+={p2['entries_per_instance']}) {{",
              # Racine éteinte = groupe RENDU AU POOL. C'est ici, en un seul
              # endroit, que se tiennent les deux règles : « détruire la racine
              # détruit le sous-arbre », et « active = false libère tout le
              # groupe ». Sans cette branche, un boss tué laisserait ses bras
              # actifs — donc dessinés, et en collision — jusqu'à la fin de la
              # scène. Le spawn, lui, ne regarde que la racine (il avance d'un
              # groupe à la fois) : la libérer suffit à rendre l'instance.
              f"        if(!g_actors[_b].active) {{",
              f"            for(int _k=1; _k<{group}; _k++) {{",
              # `active = 0` suffit à cacher : le writer OAM teste `active && visible`.
              f"                g_actors[_b+_k].active = 0;",
              f"            }}",
              f"            continue;",
              f"        }}"]
        for k, pt in enumerate(parts, start=1):
            par = by_name.get(getattr(pt, "parent", None) or "")
            # Parent = une autre partie, sinon la racine du groupe (décalage 0).
            p_off = rank.get(par.name, 0) if par is not None else 0
            ref = par if par is not None else pf
            p_rot = float(getattr(ref, "rotation", 0) or 0)
            p_sx = float(getattr(ref, "scale_x", 1.0) or 1.0) or 1.0
            p_sy = float(getattr(ref, "scale_y", 1.0) or 1.0) or 1.0
            # La racine d'un prefab n'a pas de pose authorée — le template est
            # posé à l'origine, et c'est `spawn(x, y)` qui décide où. Le monde
            # d'un enfant se lit donc directement comme un offset au template.
            rx = int(getattr(ref, "x", 0) or 0) if par is not None else 0
            ry = int(getattr(ref, "y", 0) or 0) if par is not None else 0
            dx, dy = float(int(pt.x) - rx), float(int(pt.y) - ry)
            th = math.radians(-p_rot)
            ux = dx * math.cos(th) - dy * math.sin(th)
            uy = dx * math.sin(th) + dy * math.cos(th)
            ox, oy = int(round(ux / p_sx * 256)), int(round(uy / p_sy * 256))
            rot = int(getattr(pt, "rotation", 0) or 0) - int(round(p_rot))
            sx = int(round(float(getattr(pt, "scale_x", 1.0) or 1.0) / p_sx * 256))
            sy = int(round(float(getattr(pt, "scale_y", 1.0) or 1.0) / p_sy * 256))
            src = f"_b+{p_off}" if p_off else "_b"
            L += [
                f"        if(g_actors[_b+{k}].active) {{"
                f"   /* {pt.name} dans le repère de "
                f"{par.name if par is not None else pf.name} */",
                f"            int _pr = g_actors[{src}].rotation;",
                f"            int _px = g_actors[{src}].scale_x, _py = g_actors[{src}].scale_y;",
                f"            int _co = gba_cos(_pr), _si = gba_sin(_pr);",
                f"            int _lx = ({ox} * _px) >> 8, _ly = ({oy} * _py) >> 8;",
                f"            g_actors[_b+{k}].x = g_actors[{src}].x + ((_lx * _co - _ly * _si) >> 8);",
                f"            g_actors[_b+{k}].y = g_actors[{src}].y + ((_lx * _si + _ly * _co) >> 8);",
                f"            g_actors[_b+{k}].rotation = _pr + {rot};",
                f"            g_actors[_b+{k}].scale_x  = (_px * {sx}) >> 8;",
                f"            g_actors[_b+{k}].scale_y  = (_py * {sy}) >> 8;",
                *_visible_line("            ",
                               _pool_entry_expr(ranks[k]), _pool_entry_expr(ranks[p_off]),
                               getattr(pt, "visible", True)),
                f"        }}",
            ]
        L.append("    }")
    return L


def _ui_images_lines(p, sprite_offsets: dict, emit=None) -> list[str]:
    """Table des images + leurs constantes. Séparée de `fonts_and_texts_lines`
    parce qu'elle a besoin de `sprite_offsets`, qui n'est connu qu'une fois
    l'union des sprites faite — donc bien plus tard dans le pipeline."""
    images = p.all_images() if hasattr(p, "all_images") else []
    if emit and images:
        from core.models.ui_region import can_fill
        n_bound = sum(1 for _l, im in images if getattr(im, "sprite_name", ""))
        n_fill = sum(1 for _l, im in images if can_fill(im))
        emit("log_line", f"[ui] {len(images)} sprite(s) d'interface "
                         f"(dont {n_fill} fond(s) de conteneur), "
                         f"{n_bound} relié(s) à un sprite")
    return emit_ui_images_c(p, sprite_offsets, obj_text_alloc(p),
                            actor_index=region_actor_index(p),
                            elem_index=ui_element_index(p), emit=emit)


def _gen_scene_blend(scene, emit=None) -> list[str]:
    """Configuration du mélange de couleurs d'une scène.

    Les mêmes fonctions que l'API Lua `blend.*` : un script peut reconfigurer
    ensuite, dernier écrivain gagne — pas de second mécanisme.

    L'ordre suit le matériel : les CIBLES d'abord (BLDCNT bits 0-5 et 8-13),
    le MODE ensuite (bits 6-7), les coefficients en dernier. `blend_set_mode`
    n'écrase que son champ, donc l'ordre n'est pas critique — mais le lire dans
    l'ordre du registre évite de se demander s'il l'est.

    Rien n'est émis en mode « aucun » : `display_reset()` a déjà tout remis à
    zéro. Une scène sans mélange ne paie donc pas une instruction."""
    from core.models.scene import (BLEND_NONE, BLEND_ALPHA, BLEND_TOP,
                                   BLEND_BOTTOM, BLEND_NEEDS_BOTTOM,
                                   blend_role_of)
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    if mode == BLEND_NONE:
        return []
    L: list[str] = []
    sides = {BLEND_TOP: 0, BLEND_BOTTOM: 1}
    for layer in getattr(scene, "background_layers", []):
        role = blend_role_of(layer)
        if role:
            L.append(f"    blend_set_layer({sides[role]}, {layer.bg_slot}, 1);"
                     f"   /* BG{layer.bg_slot} — {'dessus' if role == BLEND_TOP else 'dessous'} */")
    for attr, fn in (("blend_obj_role", "blend_set_obj"),
                     ("blend_backdrop_role", "blend_set_backdrop")):
        role = getattr(scene, attr, "")
        if role in sides:
            L.append(f"    {fn}({sides[role]}, 1);")
    L.append(f"    blend_set_mode({mode});")
    if mode == BLEND_ALPHA:
        L.append(f"    blend_set_alpha({int(scene.blend_eva)}, {int(scene.blend_evb)});")
    else:
        # Les modes 2 et 3 n'emploient QUE le dessus, et leur intensité vient de
        # BLDY — écrire BLDALPHA ici ne ferait rien du tout.
        L.append(f"    blend_set_fade({int(scene.blend_evy)});")
    if emit:
        names = {1: "alpha", 2: "éclaircir", 3: "assombrir"}
        tops = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_TOP)]
        bots = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_BOTTOM)]
        if getattr(scene, "blend_obj_role", "") == BLEND_TOP: tops.append("OBJ")
        if getattr(scene, "blend_obj_role", "") == BLEND_BOTTOM: bots.append("OBJ")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_TOP: tops.append("backdrop")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_BOTTOM: bots.append("backdrop")
        detail = f"dessus {', '.join(tops) or '(aucun)'}"
        if mode in BLEND_NEEDS_BOTTOM:
            detail += f", dessous {', '.join(bots) or '(aucun)'}"
        emit("log_line", f"[blend] scène '{scene.name}' : {names.get(mode, mode)} "
                         f"— {detail}")
    return L


def _gen_ui_images(p: Project, scene, text_cbb: int, sprite_offsets: dict,
                   emit=None) -> list[str]:
    """Init des images d'interface d'une scène.

    Trois choses, et rien de plus : remettre l'état des images à leur état
    DÉCLARÉ (une scène quittée laisse ses animations où elles en étaient),
    désigner la banque de palette de chacune, et — pour les images en cible BG
    seulement — recopier les tuiles du sprite dans le charblock d'UI.

    La recopie est ici et pas au démarrage parce que la base dépend du charblock
    alloué à CETTE scène : la même mise en page servie par deux scènes n'a pas
    la même adresse. C'est le raisonnement de `text_set_font_base`, appliqué à
    des tuiles de sprite.

    TOUTES les frames sont copiées, pas seulement celles de l'état déclaré : un
    script peut basculer d'état à n'importe quelle frame, et recopier depuis la
    ROM à cet instant-là ferait clignoter l'image."""
    images = getattr(scene, "_ui_images", None)
    if images is None:
        images = scene_ui_images(p, scene)
    L: list[str] = ["    ui_images_reset();"]
    # Banques : la même que le texte côté BG (les images d'UI partagent la
    # palette de l'interface), et le slot OBJ de la scène côté sprites.
    layout = {d["index"]: d for d in (getattr(scene, "_ui_image_layout", []) or [])}
    text_base = getattr(scene, "_vram_layout", None)
    base0 = getattr(text_base, "text_base", 0) if text_base is not None else 0
    res = getattr(scene, "_ui_reservation", {}) or {}
    # Les images viennent APRÈS tous les autres postes du bloc de texte — cf.
    # `scene_text_reservation`, dont l'ordre fait foi. La surface compte pour ce
    # qu'elle OCCUPE (`surf_tiles`, comme le placement des zones et le total
    # réservé), pas pour le plafond `TEXT_SURF_TILES` : réserver 240 tuiles pour
    # une scène qui n'en compose que 58 poussait l'image hors du charblock (au-
    # delà de la SBB de sa tilemap), et l'image disparaissait sans une erreur.
    head = (len(res.get("fill_indices", []))
            + sum(a["tiles"] for a in res.get("img_assets", []))
            + res.get("mono_tiles", 0)
            + res.get("surf_tiles", 0))
    # Banque de palette par image, résolue par l'allocateur du POOL de sa cible
    # — les deux pools sont disjoints sur GBA. Sans ça l'image lisait la banque
    # d'interface, celle de la POLICE : une silhouette aux couleurs du texte.
    from codegen.palette_alloc import scene_bank_layout
    from core.models.palette import OWN_PAL_BANK
    bg_layout = obj_layout = None
    for info in images:
        sprite = info["sprite"]
        if info["bg"]:
            bg_layout = bg_layout or scene_bank_layout(p, scene, "bg")
            bank_layout = bg_layout
        else:
            obj_layout = obj_layout or scene_bank_layout(p, scene, "obj")
            bank_layout = obj_layout
        bank = bank_layout.bank_index(
            int(getattr(sprite, "pal_bank", OWN_PAL_BANK)),
            list(getattr(sprite, "own_palette", None) or []))
        L.append(f"    ui_image_set_bank({info['index']}, {bank if bank is not None else 0});"
                 f"   /* '{info['el'].name}' : palette de {sprite.name} */")
        if bank is None and emit:
            emit("log_line",
                 f"[warn] image '{info['el'].name}' : aucune banque libre pour la "
                 f"palette de '{sprite.name}' — elle s'affichera avec les "
                 f"couleurs de la banque 0.")
        if not info["bg"]:
            continue
        pl = layout.get(info["index"])
        if pl is None:
            continue
        base = base0 + head + pl["base"]
        ss = f"sprite_{c_sym(sprite.name)}"
        L.append(f"    ui_image_set_bg_base({info['index']}, {base});")
        L.append(f"    copy16(TILE_RAM({text_cbb}) + {base} * 16, "
                 f"{ss}Tiles, {ss}TilesLen);"
                 f"   /* image '{info['el'].name}' : {info['frames']} frame(s) */")
    return L


def _scene_music_lines(p: Project, scene: Scene, sound_assets: dict | None) -> list[str]:
    """L'appel musical de `scene_init`, ou rien du tout.

    Les trois valeurs de `Scene.music` (cf. models/scene.py) :
      - `MUSIC_INHERIT` — **rien n'est émis**. « Ne touche pas à ce qui joue »
        doit être littéralement gratuit, c'est le cas par défaut et de loin le
        plus fréquent.
      - `MUSIC_NONE`    — silence déclaré.
      - un nom          — la piste.

    Pas de « ne redémarre pas si c'est déjà la même ». La tentation est réelle
    (douze salles qui nomment le même thème le relanceraient douze fois), mais
    `MUSIC_INHERIT` répond DÉJÀ à ce besoin : on nomme le thème dans la salle où
    il commence, les autres héritent. Retenir la piste courante en plus
    demanderait un état que `music:play()` appelé depuis un script ne mettrait
    pas à jour — il suffirait d'un script pour le désynchroniser, et la scène
    déclarative se tairait alors sans raison visible. Un second mécanisme pour
    un problème déjà résolu, et faux par-dessus le marché.
    """
    from core.models.scene import MUSIC_INHERIT, MUSIC_NONE
    want = getattr(scene, "music", MUSIC_INHERIT) or MUSIC_INHERIT
    if want == MUSIC_INHERIT:
        return []
    if want == MUSIC_NONE:
        return ["    music_stop();   /* silence déclaré par la scène */"]
    in_rom = {m.name: m for m, _ in (sound_assets or {}).get("music", [])}
    music = in_rom.get(want)
    if music is None:
        # Le validateur a déjà nommé le problème ; ici on ne PEUT pas émettre
        # MOD_X, la constante n'existe pas dans soundbank.h et la compilation C
        # échouerait sur un message bien moins clair.
        return [f"    /* musique « {want} » absente de la ROM — scène muette */"]
    from core.models.audio import volume_to_module
    loop = 1 if getattr(music, "loop", True) else 0
    # `volume` est un POURCENTAGE ; mmSetModuleVolume attend 0–1024.
    vol  = volume_to_module(int(getattr(music, "volume", 100)))
    return [f"    music_play(MOD_{c_sym(want).upper()}, {loop}, {vol});"]


def _gen_ui_routes(p: Project, scene) -> list[str]:
    """Routage de rendu par scène (ROADMAP v0.12) : pour chaque zone/image rendue
    en Background par un nœud `Interface`, son slot BG. Le rendu (`text_draw_in`,
    `ui_image_update`…) l'utilise au lieu du layer global, ce qui permet à un
    layout partagé de vivre sur BG0 dans une scène et BG2 dans une autre.

    Les index sont les index PROJET-GLOBAUX (`all_regions`/`all_images`), les mêmes
    que ceux qu'émettent les tables de contenu et que citent `REGION_*`/`IMAGE_*`.
    Le slot vient du `bg_slot` de CHAQUE nœud (per-scène), non du slot unique de la
    réservation VRAM."""
    from core.models.ui_region import TARGET_BG
    rm = int(getattr(scene, "render_mode", 0) or 0)
    reg_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    img_idx = {im.name: i for i, (_l, im) in enumerate(p.all_images())}
    L: list[str] = ["    scene_routes_reset();"]
    for lay, el in p.scene_ui_slots(scene):
        if lay.resolved_target(el, rm) == TARGET_BG and el.name in reg_idx:
            L.append(f"    scene_route_region({reg_idx[el.name]}, {lay.bg_slot});"
                     f"   /* {el.name} → BG{lay.bg_slot} */")
    for lay, im in p.scene_ui_images(scene):
        if lay.resolved_target(im, rm) == TARGET_BG and im.name in img_idx:
            L.append(f"    scene_route_image({img_idx[im.name]}, {lay.bg_slot});"
                     f"   /* {im.name} → BG{lay.bg_slot} */")
    return L


def _layer_base_bank(p, scene, bi: dict, bg_layout) -> int:
    """Banque de palette de BASE d'un fond, telle que le build la grave dans sa map.

    Une banque choisie (0-15) est elle-même. « Palette propre » : le premier slot du bloc
    alloué au fond compressé (ses sous-palettes occupent des banques contiguës), ou le slot
    alloué à sa palette. Un fond dont les tuiles ont des banques peintes différentes rend
    ici sa banque de base, pas toutes celles en usage."""
    if bi["pal_bank"] != OWN_PAL_BANK:
        return bi["pal_bank"]
    ba = p.get_background(bi["stem"])
    if bi.get("compressed"):
        return (bg_layout.bg_block_offset(ba) if ba else None) or 0
    png = p.background_images_dir / (ba.asset if ba and ba.asset else f"{bi['stem']}.png")
    colors = effective_palette_colors(p, OWN_PAL_BANK, png, scene.active_bg_palettes)
    return bg_layout.bank_index(OWN_PAL_BANK, colors) or 0


def _gen_scene_init(
    p: Project,
    scene: Scene,
    actor_offset: int,
    bgi: list[dict],
    scene_actors: list,
    lua_idx: set,
    pi: list[dict],
    sprite_offsets: dict,
    dispcnt: int,
    has_sound: bool,
    sound_assets: dict | None,
    actor_defined_events: dict[str, set[str]] | None = None,
    obj_text_oam: int = -1,
    obj_text_tile: int = 0,
    emit=None,
    affine_info: dict | None = None,
) -> list[str]:
    """Génère void scene_init_{sym}(void) { ... }"""
    sym = c_sym(scene.name)
    _lay = scene_oam_layout(p, scene)
    obj_layout = scene_bank_layout(p, scene, "obj")
    bg_layout  = scene_bank_layout(p, scene, "bg")
    L: list[str] = []
    # Constantes d'activation des apparences de la scène (marche 3c) : la table est
    # ROM, avant la fonction ; le pointeur est repointé par scene_init.
    _alay = appearance_layout(p, scene_actors, pi, obj_layout)
    L += appearance_table_lines(sym, _alay)
    # ── Données des fonds IMAGE, en amont de la fonction ───────────
    # Les tuiles de l'asset source et la carte de screen entries de chaque
    # conteneur sont des CONSTANTES : calculées par l'éditeur (cf.
    # `scene_image_fills`), elles n'ont aucune raison d'être reconstruites au
    # runtime. `scene_init` ne fait plus qu'une copie et une écriture de map.
    for _a in (getattr(scene, "_ui_img_assets", []) or []):
        _w = _a["words"]
        L.append(f"static const unsigned int {sym}_{_a['sym']}[] = {{"
                 f"   /* fond '{_a['name']}' : {_a['tiles']} tuiles */")
        for i in range(0, len(_w), 8):
            L.append("    " + " ".join(f"0x{v:08X}," for v in _w[i:i + 8]))
        L.append("};")
    for _f in (getattr(scene, "_ui_img_fills", []) or []):
        _se = _f["se"]
        L.append(f"static const unsigned short {sym}_uimap_{c_sym(_f['name'])}[] = {{"
                 f"   /* {_f['w']}x{_f['h']} cases */")
        for i in range(0, len(_se), 12):
            L.append("    " + " ".join(f"0x{v:04X}," for v in _se[i:i + 12]))
        L.append("};")
    # Fonds animés posés sur les calques : un descripteur par placement, avec son
    # propre compteur — c'est ce qui permet à deux copies du même animé d'être à
    # des moments différents de leur boucle (mode `instance`).
    anims = [a for a in scene_anim_descriptors(p, scene, bgi) if not a["shared"]]
    tanims = [a for a in scene_anim_descriptors(p, scene, bgi) if a["shared"]]
    if anims:
        L.append(f"static BgAnim g_bganim_{sym}[{len(anims)}] = {{")
        for a in anims:
            L.append(f"    {{ {a['table']}, {a['sbb']}, {a['ms']}, "
                     f"{a['col']}, {a['row']}, {a['cols']}, {a['rows']}, "
                     f"{a['frames']}, {a['speed']}, {a['loop']}, "
                     f"{a['f0']}, {a['t0']}, {a['f0']}, {a['t0']} }},")
        L.append("};")
    if tanims:
        L.append(f"static BgTileAnim g_bgtileanim_{sym}[{len(tanims)}] = {{")
        for a in tanims:
            L.append(f"    {{ {a['table']}, {a['cbb']}, {a['vram_ofs']}, {a['words']}, "
                     f"{a['frames']}, {a['speed']}, {a['loop']}, 0, 0 }},")
        L.append("};")
    if L:
        L.append("")
    L.append(f"static void scene_init_{sym}(void) {{")
    # Taille du monde (canvas) — lue par scene.size.w/.h côté script. Posée à
    # chaque activation, une scène peut donc faire avancer son monde.
    _sw, _sh = scene_world_size(p, scene)
    L.append(f"    g_scene_w = {_sw}; g_scene_h = {_sh};")
    L.append(f"    g_scene_scroll_h = {int(bool(scene.scroll_h))}; g_scene_scroll_v = {int(bool(scene.scroll_v))};")
    L.append(f"    g_scene_collision_layer = {int(scene.collision_layer)};")
    # Acteurs POSÉS de cette scène, dans l'ordre d'authoring — la borne de
    # `actor:get(i)`/`actor:count()` (ROADMAP « L'acteur appartient à sa scène »,
    # adressage dynamique). Les slots [0, placed) tiennent exactement ces
    # acteurs ; les pools spawnés vivent après et ne sont pas comptés ici.
    L.append(f"    g_scene_placed = {len(scene_actors)};")
    # Tout acteur repart SANS entrée OAM (-1) ; le lien est posé plus bas, pour les
    # seuls acteurs qui affichent un sprite (posés ci-dessous, pools à leur init).
    L.append("    for(int _i=0; _i<G_ACTOR_COUNT; _i++) { g_actors[_i]=(Actor){0}; g_actors[_i].oam_entry=-1; }")
    L.append("    for(int _i=0; _i<G_OAM_ENTRY_COUNT; _i++) g_oam_entries[_i]=(OamEntry){0};")
    if _alay.rows:
        L.append(f"    g_appearance_init = {sym}_appearance_init;")
    L.append("    oam_hide_all();")
    L.append("    bg_maps_clear();")
    L.append("    display_reset();")
    # Ferme les lectures de la scène PRÉCÉDENTE. `g_reads` est global et ses
    # index sont projet-globaux : sans ce reset, `text_update` continue de
    # rendre — chaque frame — une zone appartenant à la mise en page d'une
    # autre scène (son texte réapparaît, son tempo se rejoue).
    L.append("    text_read_reset_all();")
    # Fonds nine-slice/background des zones composées : table scène-locale elle
    # aussi (la base VRAM de l'asset source change d'une scène à l'autre), donc
    # même reset — sans lui une zone de la scène PRÉCÉDENTE resterait
    # enregistrée sous le même index et prêterait sa carte à une zone qui n'a
    # plus rien à voir avec elle (cf. `_gen_scene_init`, plus bas, pour les
    # `text_set_region_backdrop` qui la repeuplent).
    L.append("    text_clear_region_fills();")
    L.append("    text_clear_region_surfs();")
    # Visibilité des éléments d'interface : table PROJET-GLOBALE elle aussi,
    # même raison que `text_read_reset_all` juste au-dessus — reposer les bits
    # AUTHORÉS de départ à chaque scène, sinon un élément caché par un script
    # dans la scène précédente resterait caché ici.
    L.append("    ui_elements_reset();")
    # Caméra de démarrage. L'activation pose cadrage ET bornes, et rejoue le
    # on_start de la caméra : une scène n'hérite donc jamais du cadrage de la
    # précédente, et un script peut basculer ailleurs ensuite (camera.switch).
    # Le WIN0 qu'elle pose ici (cf. camera_switch()) sera effacé par
    # dispcnt_set() plus bas et reposé après — voir ce commentaire-là.
    _cam_idx = scene_camera_index(p, scene)
    _cam_name = getattr(scene, "camera", "") or "(default)"
    L.append(f"    camera_switch({_cam_idx});   /* {_cam_name} */")
    # SFX on_destroy : pointe les tables de CETTE scène (per-scène depuis T3,
    # cf. `_sfx_on_destroy_table`). `actor_destroy_with_sfx` lit ces pointeurs.
    L.append(f"    g_sfx_on_destroy_id  = g_sfx_on_destroy_id_{sym};")
    L.append(f"    g_sfx_on_destroy_vol = g_sfx_on_destroy_vol_{sym};")
    # Cmap dispatch
    if scene_has_cmap(scene):
        L.append(f"    g_active_cmap = g_cmap_{sym};")
        L.append(f"    g_cmap_w = CMAP_W_{sym.upper()};")
        L.append(f"    g_cmap_h = CMAP_H_{sym.upper()};")
    else:
        L.append("    g_active_cmap = NULL; g_cmap_w = 0; g_cmap_h = 0;")
    # BG layers — chaque layer a son propre CBB (= bg_slot) pour ses tuiles,
    # sa map vit dans les derniers SBB de ce même CBB (cf. bg_info).
    if bgi:
        for bi in bgi:
            L.append(f"    copy16(TILE_RAM({bi['bg']}), {bi['sym']}Tiles, {bi['sym']}TilesLen);")
        for bi in bgi:
            if bi.get("stream"):
                # Streaming : charger la fenêtre résidente initiale depuis la map
                # complète en ROM ; les bords se rechargent au scroll (tick).
                L.append(f"    bg_stream_init(MAP_RAM({bi['sbb']}), {bi['sym']}Map, "
                         f"{bi['tw']}, {bi['th']}, {bi['win_w']}, {bi['win_h']});")
            else:
                ms = bi["map_size"]
                gcols = 64 if (ms & 1) else 32
                grows = 64 if (ms & 2) else 32
                L.append(f"    load_map(MAP_RAM({bi['sbb']}), {bi['sym']}Map, {bi['tw']}, {bi['th']}, {gcols}, {grows});")
        for bi in bgi:
            # Priorité GBA = bg_slot directement (bg_slot 0 = priorité 0 =
            # premier plan). Même convention que l'éditeur (scene_editor.py
            # GbaScene.set_bg : z = 3 - bg_index, donc bg_slot 0 = zValue le
            # plus HAUT = dessiné devant dans le canvas Qt) — bg_slot 0 doit
            # rester devant sur les deux. Or en registre BGxCNT, priorité 0 =
            # dessiné DEVANT (l'inverse d'un zValue Qt) : `pri = bg` (pas
            # `3 - bg`) est donc la formule qui fait correspondre les deux.
            bg = bi["bg"]; sbb = bi["sbb"]; pri = bg; ms = bi["map_size"]
            val = (pri & 3) | (bg & 3) << 2 | (sbb & 0x1F) << 8 | ms << 14
            if bi.get("bpp8"):
                val |= 0x0080   # bit 7 : couleurs 256/1 (8bpp) au lieu de 16/16
            # bg_cnt_set plutôt qu'une écriture directe : le registre est
            # write-only, la shadow permet ensuite de changer priorité /
            # screenblock au runtime sans perdre les autres bits.
            L.append(f"    bg_cnt_set({bg}, 0x{val:04X});")
            # Vitesse de parallax de départ (Q8) : display_reset() l'a remise à 256 ;
            # `layer.scroll_speed` la change ensuite sans regénérer le tick.
            L.append(f"    layer_set_speed({bg}, {bi['speed']});")
            # Banque de palette de BASE, résolue comme le build la pose dans la map : lue par
            # `layer.pal_bank`, pour alimenter `palette:set_bg` sans coder le numéro en dur.
            L.append(f"    layer_set_pal_bank({bg}, {_layer_base_bank(p, scene, bi, bg_layout)});")
    # APRÈS le chargement des cartes, qu'ils recouvrent : un animé n'existe pas
    # dans la carte en ROM, il est toujours posé par-dessus.
    if anims:
        L.append(f"    bg_anim_init(g_bganim_{sym}, {len(anims)});")
    if tanims:
        L.append(f"    bg_tileanim_init(g_bgtileanim_{sym}, {len(tanims)});")
    # Sprites VRAM
    # Tout résident (marche 3) : chaque apparence de chaque acteur a ses tuiles en VRAM.
    all_sprites = ([(a, sp) for a, _ in scene_actors for _c, sp in owner_appearances(p, a)]
                   + (p._prefab_sprites_cache if hasattr(p, "_prefab_sprites_cache") else []))
    done_vram: set[str] = set()
    for _, sprite in all_sprites:
        if not sprite or not sprite.asset or sprite.name in done_vram:
            continue
        done_vram.add(sprite.name)
        bt = sprite_offsets.get(sprite.name, 0)
        ss = f"sprite_{c_sym(sprite.name)}"
        L.append(f"    copy16(OBJ_VRAM+{bt}*16, {ss}Tiles, {ss}TilesLen);")
    # Palettes OBJ — chaque banque occupée du layout (référencée OU palette
    # propre auto-allouée, cf. palette_alloc) est copiée dans PAL_OBJ_RAM.
    for i, colors in enumerate(obj_layout.slot_colors):
        if colors:
            L.append(f"    copy16(PAL_OBJ_RAM+{i}*16, g_pal_obj_{sym}+{i}*16, 32);")
    # Palette BG — chaque banque occupée du layout (référencée, bloc de fond
    # compressé, ou palette propre auto-allouée, cf. palette_alloc) est copiée
    # dans PAL_BG_RAM.
    for i, colors in enumerate(bg_layout.slot_colors):
        if colors:
            L.append(f"    copy16(PAL_BG_RAM+{i}*16, g_pal_bg_{sym}+{i}*16, 32);")
    # Backdrop — écrit inconditionnellement (indépendant de bgi/de
    # l'occupation du slot 0 ci-dessus, qui ne copie que les slots occupés :
    # une scène sans aucune palette BG active doit quand même pouvoir
    # afficher une couleur de fond).
    L.append(f"    PAL_BG_RAM[0] = 0x{resolve_backdrop_color(p, scene):04X};")
    # Texte (text.*) — le layer d'UI porte les glyphes ; la 1ère police du
    # projet est chargée par défaut, `text:set_font()` en change.
    #
    # Plus d'init TTE ici : libtonc est sorti du workflow. TTE chargeait SA
    # police à partir de la tuile 1 de ce même charblock, là où text_set_font
    # pose la nôtre — les deux s'écrasaient. Un seul système de texte, donc un
    # seul occupant du charblock (cf. gba_engine.h, section TTE retiré).
    text_bg = p.scene_ui_bg_slot(scene)
    lay = getattr(scene, "_vram_layout", None)
    text_cbb = (lay.text_cbb if lay else text_bg) if text_bg in {0, 1, 2, 3} else -1
    text_base = lay.text_base if lay else 1
    fills = getattr(scene, "_ui_fills", []) or []
    fill_indices = getattr(scene, "_ui_fill_indices", []) or []
    # BGxCNT de CHAQUE slot d'UI (v0.12 : une scène peut en poser plusieurs). Un
    # slot d'UI ne porte pas d'image, donc la boucle des fonds ne l'a pas
    # configuré — sans cette ligne le registre reste à 0 (CBB 0 ET SBB 0), et les
    # entrées de map du texte atterrissent PILE sur ses tuiles de glyphes.
    #
    # Tous les slots partagent le charblock des glyphes (`text_cbb`) mais ont
    # CHACUN leur map (`ui_sbb[slot]`) : plusieurs calques d'UI, un seul jeu de
    # tuiles (cf. codegen/vram_alloc.py). Purge inutile ici : `bg_maps_clear()`,
    # en tête de scene_init, a déjà vidé les 32 screenblocks.
    ui_slots = p.scene_ui_bg_slots(scene)
    ui_sbb = getattr(lay, "ui_sbb", None) or {}
    if text_bg in {0, 1, 2, 3}:
        for us in ui_slots:
            sbb = ui_sbb.get(us, us * 8 + 7)
            cnt = (us & 3) | (text_cbb & 3) << 2 | (sbb & 0x1F) << 8
            L.append(f"    bg_cnt_set({us}, 0x{cnt:04X});"
                     f"   /* layer UI BG{us} : CBB{text_cbb}, SBB{sbb} */")
    L.append(f"    text_set_layer({text_bg if text_bg in {0,1,2,3} else -1});")
    # Routage de rendu par scène : le slot BG de CHAQUE zone/image (per-nœud),
    # posé AVANT tout `text_draw_in`/`ui_image_*` pour que le rendu route au bon
    # calque. `text_set_layer` ci-dessus ne fixe plus que le défaut de l'écriture
    # libre (`text.draw` aux coordonnées).
    L += _gen_ui_routes(p, scene)
    # Remis à 0 (= pas de surface dédiée) à CHAQUE scène : `g_surf_tile_base`
    # est un global qui, sans ce reset, garderait la valeur de la scène
    # précédente pour une scène qui n'a elle-même aucune zone à fond.
    L.append("    text_set_surf_base(0);")
    # Fonds COULEUR des conteneurs : les tuiles pleines occupent le DÉBUT du
    # bloc UI (le texte se décale de `len(indices)`), puis on les repose sur le
    # rectangle de chaque container. Statique : posé une fois, avant le texte.
    for i, idx in enumerate(fill_indices):
        L.append(f"    ui_fill_load_solid({text_cbb}, {text_base + i}, {idx});"
                 f"   /* tuile pleine, index {idx} */")
    # Fonds IMAGE (nine-slice, background) : les tuiles de chaque asset source
    # sont copiées dans le charblock d'UI, JUSTE APRÈS les tuiles pleines et
    # AVANT les glyphes — chaque bloc a son adresse propre, aucun ne recouvre
    # l'autre. `ui_fill_map` recale ensuite les index de la carte sur cette base.
    img_fills = getattr(scene, "_ui_img_fills", []) or []
    img_assets = getattr(scene, "_ui_img_assets", []) or []
    img_base = text_base + len(fill_indices)
    asset_base: list[int] = []
    _cur = img_base
    for a in img_assets:
        asset_base.append(_cur)
        L.append(f"    copy16(TILE_RAM({text_cbb}) + {_cur} * 16, "
                 f"{sym}_{a['sym']}, {a['tiles'] * 32});"
                 f"   /* tuiles du fond '{a['name']}' */")
        _cur += a["tiles"]
    glyph_base = _cur
    if project_fonts(p):
        # APRÈS text_set_layer (qui repose le charblock par défaut) et AVANT
        # text_set_font (qui copie les glyphes à cette adresse) ; décalé après
        # les tuiles pleines des fonds.
        L.append(f"    text_set_charblock({text_cbb if text_cbb >= 0 else text_bg});")
        L.append(f"    text_set_tile_base({glyph_base});")
        # Chaque police à SA base : charger la seconde n'écrase plus la
        # première. Rien d'émis = tout à la base 0, une seule résidente.
        for _fl in getattr(scene, "_ui_reservation", {}).get("font_layout", []):
            L.append(f"    text_set_font_base({_fl['index']}, {_fl['base']});"
                     f"   /* {_fl['name']} : {_fl['tiles']} tuile(s) */")
        # Sous-ensembles AVANT text_set_font : c'est lui qui copie les glyphes,
        # il doit déjà savoir lesquels. Une police sans sous-ensemble déclaré se
        # charge entière.
        L.append("    text_clear_subsets();")
        for _fi, _sub_sym in sorted(getattr(scene, "_ui_font_subsets", {}).items()):
            L.append(f"    text_set_subset({_fi}, &{_sub_sym});")
        # Banque d'encre de CHAQUE police (text_set_font_pal), après le clear qui
        # les remet au défaut. `own=1` = la police charge sa palette propre dans
        # une banque allouée (usage libre, comme un sprite) ; `own=0` = elle lit
        # une palette de scène (override) ou n'a que des usages imbriqués — le
        # conteneur possède alors la banque (cf. text_set_region_*). Une police
        # absente de la table garde le défaut historique (sa palette en banque 15).
        from codegen.palette_alloc import scene_font_runtime_banks
        _fpb = scene_font_runtime_banks(p, scene)
        for _fi, _f in enumerate(project_fonts(p)):
            _bo = _fpb.get(_f.name)
            if _bo is not None:
                L.append(f"    text_set_font_pal({_fi}, {_bo[0]}, {_bo[1]});"
                         f"   /* {_f.name} */")
        # Police par défaut de la SCÈNE — le même calcul que la réservation
        # VRAM et les sous-ensembles (cf. font_emit.scene_default_font).
        # Réserver pour une police et en charger une autre écrirait le texte
        # dans le décor sans une erreur avant l'exécution.
        from codegen.font_emit import scene_default_font as _sdf
        _fi_def, _fn_def = _sdf(p, scene)
        L.append(f"    text_set_font({max(0, _fi_def)});"
                 + (f"   /* {_fn_def} */" if _fn_def else ""))
    # Le fond va sur la map du slot de SON nœud (`f['slot']`, v0.12), plus un slot
    # d'UI unique : deux HUD sur deux BG posent chacun leur fond sur son calque.
    for f in fills:
        L.append(
            f"    ui_fill_rect({f.get('slot', text_bg)}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, "
            f"{text_base + fill_indices.index(f['index'])}, {f['bank']});"
            f"   /* fond couleur '{f['name']}' → BG{f.get('slot', text_bg)} */")
    for f in img_fills:
        L.append(
            f"    ui_fill_map({f.get('slot', text_bg)}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, "
            f"{sym}_uimap_{c_sym(f['name'])}, {asset_base[f['asset']]});"
            f"   /* fond image '{f['name']}' → BG{f.get('slot', text_bg)} */")
    # ── Le FOND des zones de texte ────────────────────────────────
    # Un texte prend le fond de son conteneur : sans ça, écrire remplace la
    # cellule par une tuile de glyphe (index 0 transparent) et perce le fond.
    # Deux formes, une table côté runtime (`RegionFill`/`text_surf_seed`).
    #
    # IMAGE d'abord : la carte déjà émise ci-dessus pour le conteneur est
    # réutilisée telle quelle, jamais dupliquée pour la zone.
    region_backdrops = scene_region_backdrops(p, scene, img_fills)
    for rb in region_backdrops:
        f = img_fills[rb["fill"]]
        L.append(
            f"    text_set_region_backdrop({rb['region']}, "
            f"{sym}_uimap_{c_sym(f['name'])}, {f['w']}, {rb['dx']}, {rb['dy']}, "
            f"{asset_base[f['asset']]}, {f['bank']});"
            f"   /* '{rb['name']}' recompose le fond '{f['name']}' */")
    # COULEUR ensuite. `scene_region_colors` DÉRIVE de `fills`, la liste que le
    # build émet réellement : un conteneur écarté (palette non active, ancrage,
    # cible) ne peut donc plus teinter le texte qu'il contient.
    #
    # Le texte enfant PREND la banque du conteneur (`text_set_region_color` la
    # porte) : `index` est celui de l'aplat DANS cette banque, sans plus loger la
    # couleur chez la police — c'est le comportement par défaut du chantier
    # « la police, une palette d'asset ».
    region_colors = scene_region_colors(p, scene, fills)
    for rc in region_colors:
        L.append(f"    text_set_region_color({rc['region']}, {rc['index']}, {rc['bank']});"
                 f"   /* '{rc['name']}' sur le fond de '{rc['container']}' */")
    # La SURFACE composée : réclamée par un fond comme par un surlignement,
    # puisque les deux font composer le texte même en police mono — et par une
    # police composée, qui n'a nulle part ailleurs où ranger ses pixels. Bloc
    # PROPRE, APRÈS les glyphes mono — à la même adresse, composer une zone
    # écraserait les glyphes que ses voisines mono lisent encore.
    #
    # `needs_surface` est relu de la RÉSERVATION et non recalculé : réserver
    # pour une raison et placer pour une autre, c'est écrire hors du bloc.
    _res = getattr(scene, "_ui_reservation", {}) or {}
    compose = bool(_res.get("needs_surface"))
    if compose and text_bg in {0, 1, 2, 3}:
        mono_tiles = getattr(scene, "_ui_mono_tiles", 0)
        surf_base = glyph_base + mono_tiles
        L.append(f"    text_set_surf_base({surf_base});"
                 f"   /* surface partagée (écriture libre), après les glyphes mono */")
        # Puis un bloc PROPRE par zone composée, à la suite. C'est ce qui
        # permet à deux boîtes de coexister où qu'elles soient à l'écran : la
        # surface partagée, elle, est adressée modulo TEXT_SURF_H rangées.
        _shared = int(_res.get("shared_surf_tiles", 0) or 0)
        for _sl in _res.get("surf_layout", []):
            L.append(
                f"    text_set_region_surf({_sl['region']}, "
                f"{surf_base + _shared + _sl['base']}, {_sl['w']}, {_sl['h']});"
                f"   /* '{_sl['name']}' : {_sl['w']}×{_sl['h']} tuiles */")
    # Bande de sprites du texte : après les sprites d'acteurs (tuiles) et après
    # tous les slots d'acteurs et de pools (OAM). -1 = aucune zone en cible OBJ.
    if obj_text_oam >= 0:
        L.append(f"    text_obj_set_actor_fn(_txt_actor_x, _txt_actor_y, _txt_actor_prio);")
        L.append(f"    text_obj_set_base({obj_text_oam}, {obj_text_tile});")
    # Textes AUTHORÉS de la mise en page. En DERNIER des postes de texte : le
    # rendu lit la police, la base de tuiles, la surface composée, les couleurs
    # de fond et la base OBJ — tout ce qui précède. Avant dispcnt_set, qui
    # n'écrit que des registres d'affichage.
    L += gen_ui_texts(p, scene, text_bg, emit)
    # Images de l'interface, APRÈS les postes de texte : elles réutilisent la
    # même base OAM (`text_obj_set_base`, dont l'allocation chaîne les deux) et
    # se logent après les glyphes dans le charblock d'UI.
    L += _gen_ui_images(p, scene, text_cbb, sprite_offsets, emit)
    # DISPCNT
    L.append(f"    dispcnt_set(0x{dispcnt:04X});")
    # Mélange de couleurs (BLDCNT/BLDALPHA/BLDY) — rien d'émis en mode « aucun » :
    # `display_reset()` a déjà remis les trois registres à zéro, et le défaut
    # doit rester littéralement gratuit.
    L += _gen_scene_blend(scene, emit)
    # Windows (WIN0/WIN1/fenêtre-objet) — mêmes fonctions runtime que l'API Lua
    # window.* : un script peut reconfigurer/désactiver ensuite (dernier écrivain
    # gagne, pas de mécanisme séparé). Rien n'est émis si la scène n'a aucune
    # window authorée (display_reset() a déjà tout remis à « aucune window active »).
    #
    # Rang matériel décidé par l'allocateur (`window_alloc.scene_window_layout`,
    # cf. ARCHITECTURE.md « Windows — le pochoir ») — ni la caméra ni un
    # WindowSlot ne nomme WIN0/WIN1 lui-même. Le validateur fait échouer le
    # build si la scène demande plus de deux intentions ; ce code suppose donc
    # `layout.overflow` vide (déjà vérifié avant d'arriver ici).
    #
    # IMPÉRATIVEMENT APRÈS dispcnt_set : window_show() pose un bit DISPCNT
    # (13=WIN0, 14=WIN1, 15=OBJWIN) dans la shadow, alors que dispcnt_set()
    # REMPLACE la shadow entière (g_dispcnt_sh = val). Émis avant, l'activation
    # des windows serait silencieusement effacée — la window resterait invisible
    # en jeu alors que tous ses autres registres sont corrects. Ça vaut aussi
    # pour le cadre de la caméra, posé une première fois par camera_switch()
    # PLUS HAUT (avant dispcnt_set) : on le repose ici, sans rappeler
    # camera_switch() en entier (ça rejouerait aussi son on_start).
    _layout = scene_window_layout(p, scene)
    if _layout.camera_slot is not None:
        _start_cam = project_cameras(p)[_cam_idx]
        _fw = _start_cam.frame_w if _start_cam else 240
        _fh = _start_cam.frame_h if _start_cam else 160
        L.append(f"    window_set({_layout.camera_slot}, 0, 0, {_fw}, {_fh});")
        L.append(f"    window_show({_layout.camera_slot}, 1);")
    for ws in getattr(scene, "windows", []):
        # Fenêtre-objet : pas de rectangle, sa forme vient des pixels opaques
        # des sprites en obj_mode=2. Toujours WINR_OBJ (2), jamais disputée.
        # Surtout, window_set() fait `n &= 1` — l'appeler avec 2 écraserait
        # le rectangle de WIN0.
        if ws.is_obj:
            region = 2
        else:
            region = _layout.slot_for(ws.name)
            if region is None:
                continue   # en overflow — jamais censé arriver, cf. validateur
            L.append(f"    window_set({region}, {int(ws.x)}, {int(ws.y)}, {int(ws.w)}, {int(ws.h)});")
        layers = list(getattr(ws, "layers_shown", [True, True, True, True]))
        for bg in range(4):
            on = 1 if (bg < len(layers) and layers[bg]) else 0
            L.append(f"    window_set_layer({region}, {bg}, {on});")
        L.append(f"    window_set_obj({region}, {1 if ws.obj_shown else 0});")
        L.append(f"    window_show({region}, {1 if ws.visible else 0});")
    # Init actors
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        _e = _lay.placed_entry[j]   # son entrée OAM, -1 = sans sprite : rien à afficher
        s = scene_actor_sym(scene.name, actor.name)
        boxes = [c for c in actor.components if isinstance(c, CollisionBoxComponent)][:4]
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(actor, "pal_bank", OWN_PAL_BANK), own)
        _lines = [
            # ROADMAP v0.19 : x/y en Q8 en interne, l'auteur place l'acteur en pixels.
            f"    g_actors[{idx}].x       = ({_FV.parse(actor.x, _var_names(p)).c_expr()})<<8;",
            f"    g_actors[{idx}].y       = ({_FV.parse(actor.y, _var_names(p)).c_expr()})<<8;",
            f"    g_actors[{idx}].active  = {1 if actor.visible else 0};",
            f"    g_oam_entries[{_e}].visible = {1 if actor.visible else 0};",
            f"    g_oam_entries[{_e}].flip_h  = {1 if actor.flip_h else 0};",
            f"    g_oam_entries[{_e}].flip_v  = {1 if actor.flip_v else 0};",
            f"    g_actors[{idx}].dir_x   = {getattr(actor,'dir_x',0)};",
            f"    g_actors[{idx}].dir_y   = {getattr(actor,'dir_y',0)};",
            f"    g_oam_entries[{_e}].pal_bank= {pal if pal is not None else 0};",
            f"    g_oam_entries[{_e}].obj_mode= {int(getattr(actor, 'obj_mode', 0)) & 3};",
            f"    g_oam_entries[{_e}].priority= {int(getattr(actor, 'priority', 0)) & 3};",
            f"    g_oam_entries[{_e}].auto_dir= {1 if getattr(_shown(p, actor)[0], 'auto_dir', True) else 0};",
            f"    g_oam_entries[{_e}].anim_state=0;",
            # self.frame_w/frame_h : posées une fois ici depuis le sprite,
            # jamais recalculées — un acteur sans sprite (rare, cf. `sprite`
            # potentiellement None plus haut) rend 0 des deux côtés.
            f"    g_oam_entries[{_e}].frame_w = {sprite.frame_w if sprite else 0};",
            f"    g_oam_entries[{_e}].frame_h = {sprite.frame_h if sprite else 0};",
            f"    g_actors[{idx}].tag     = TAG_{s.upper()};",
            # Transform MONDE : émise pour TOUT acteur, affine ou non. Un acteur
            # non-affine ne l'AFFICHE pas (aucun slot de matrice), mais un enfant
            # en HÉRITE par la composition parent→enfant — un enfant hérite des
            # propriétés de son parent direct, puis les override. Sans ça, un
            # parent non-affine restait à scale 0 (le zéro-init) et écrasait la
            # position ET l'échelle affine de ses enfants (matrice dégénérée).
            # Défaut 256 = ×1 ; la branche affine ci-dessous ne rajoute que le
            # slot et la transform LOCALE du sprite.
            f"    g_actors[{idx}].rotation     = {int(round(getattr(actor, 'rotation', 0) or 0))};",
            f"    g_actors[{idx}].scale_x      = {int(round(float(getattr(actor, 'scale_x', 1.0) or 1.0) * 256))};",
            f"    g_actors[{idx}].scale_y      = {int(round(float(getattr(actor, 'scale_y', 1.0) or 1.0) * 256))};",
            f"    g_oam_entries[{_e}].screen_space = {1 if getattr(actor, 'screen_space', False) else 0};",
            f"    g_actors[{idx}].collision.box_count = {len(boxes)};",
        ]
        # Les lignes d'AFFICHAGE portent `g_oam_entries[-1]` quand l'acteur n'a pas
        # de sprite : on les écarte, et le lien reste à -1 (posé par le reset).
        L += [l for l in _lines if _e >= 0 or "g_oam_entries[-1]" not in l]
        if _e >= 0:
            L.append(f"    g_actors[{idx}].oam_entry = {_e};")
            L += _appearance_init_lines(p, actor, str(_e), "    ", _alay.actor_base.get(j))
        _aff_i = (affine_info or {}).get(idx)
        if _aff_i and _e >= 0:
            _aslot = _aff_i["slot"]
            L += [
                f"    g_oam_entries[{_e}].affine_slot = {_aslot};",
                f"    g_oam_entries[{_e}].rotation   = {_aff_i['sprite_rotation']};",
                f"    g_oam_entries[{_e}].scale_x = {_aff_i['sprite_scale_x']};",
                f"    g_oam_entries[{_e}].scale_y = {_aff_i['sprite_scale_y']};",
                f"    g_oam_entries[{_e}].offset_x     = {_aff_i['offset_x']};",
                f"    g_oam_entries[{_e}].offset_y     = {_aff_i['offset_y']};",
            ]
        elif _e >= 0:
            L.append(f"    g_oam_entries[{_e}].affine_slot = -1;")
        for bi2, cb in enumerate(boxes):
            tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
            _vn = _var_names(p)
            bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
            bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
            L += [
                f"    g_actors[{idx}].collision.boxes[{bi2}].x=(s8){bx}; g_actors[{idx}].collision.boxes[{bi2}].y=(s8){by};",
                f"    g_actors[{idx}].collision.boxes[{bi2}].w=(u8){bw};  g_actors[{idx}].collision.boxes[{bi2}].h=(u8){bh};",
                f"    g_actors[{idx}].collision.boxes[{bi2}].solid={1 if cb.solid else 0}; g_actors[{idx}].collision.boxes[{bi2}].active={1 if cb.active else 0}; g_actors[{idx}].collision.boxes[{bi2}].tag={tag_s};",
            ]
    # SoundFxComponent en trigger="on_spawn" — TOUS les actors de la scène,
    # scriptés ou non : c'est une donnée du component, pas du script (ROADMAP,
    # 2026-08-24). Émis ici plutôt que dans le on_start généré (ancien
    # comportement) pour qu'un actor sans ScriptComponent en bénéficie aussi.
    for j, (actor, _sprite) in enumerate(scene_actors):
        sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, actor)
        if sfx_sym and sfx_trig == "on_spawn":
            L.append(f"    sfx_play({sfx_sym}, {sfx_vol}, 0);"
                     f"   /* SoundFxComponent : {actor.name} */")

    # Pool init
    for p2 in pi:
        for slot in range(p2["start"], p2["start"] + p2["size"]):
            _inst, _member = divmod(slot - p2["start"], p2["group"])
            _rank = p2["member_entries"][_member]
            # Son entrée OAM : la 1re de l'instance + son rang ; -1 pour un marqueur.
            _e = (p2["entry_start"] + _inst * p2["entries_per_instance"] + _rank
                  if _rank >= 0 else -1)
            L.append(f"    g_actors[{slot}].oam_entry = {_e};")
            L.append(f"    g_actors[{slot}].tag = TAG_{p2['sym'].upper()};")
            L.append(f"    g_actors[{slot}].active = 0;")
            _aff_p = (affine_info or {}).get(slot)
            if _aff_p and _e >= 0:
                _aslot = _aff_p["slot"]
                L += [
                    f"    g_oam_entries[{_e}].affine_slot = {_aslot};",
                    f"    g_actors[{slot}].rotation     = {_aff_p['rotation']};",
                    f"    g_actors[{slot}].scale_x      = {_aff_p['scale_x']};",
                    f"    g_actors[{slot}].scale_y      = {_aff_p['scale_y']};",
                    f"    g_oam_entries[{_e}].rotation   = {_aff_p['sprite_rotation']};",
                    f"    g_oam_entries[{_e}].scale_x = {_aff_p['sprite_scale_x']};",
                    f"    g_oam_entries[{_e}].scale_y = {_aff_p['sprite_scale_y']};",
                    f"    g_oam_entries[{_e}].offset_x     = {_aff_p['offset_x']};",
                    f"    g_oam_entries[{_e}].offset_y     = {_aff_p['offset_y']};",
                ]
            elif _e >= 0:
                L.append(f"    g_oam_entries[{_e}].affine_slot = -1;")
    # ── Musique de la scène (ROADMAP v0.8.2) ───────────────────────
    # Posée AVANT les on_start : le réglage déclaratif passe en premier et le
    # script ajuste ensuite, exactement comme pour la caméra (v0.6.1). Un
    # `music:play()` dans on_start gagne donc, ce qui est ce qu'on attend.
    if has_sound:
        L += _scene_music_lines(p, scene, sound_assets)

    # on_start actors (seulement si défini dans le script Lua)
    def _def_init(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    for j in sorted(lua_idx):
        actor, _ = scene_actors[j - actor_offset]
        s = scene_actor_sym(scene.name, actor.name)
        if _def_init(s, "on_start"):
            L.append(f"    {s}_on_start(&g_actors[{j}]);")
    # on_start scene
    if getattr(scene, "script", ""):
        L.append(f"    {sym}_scene_on_start();")
    L.append("}")
    L.append("")
    return L


def _gen_scene_tick(
    p: Project,
    scene: Scene,
    actor_offset: int,
    bgi: list[dict],
    scene_actors: list,
    lua_idx: set,
    pi: list[dict],
    sprite_offsets: dict,
    sprite_nframes: dict,
    col_pairs: list,
    actor_defined_events: dict[str, set[str]] | None = None,
    affine_info: dict | None = None,
    input_layout=None,
) -> list[str]:
    """Génère void scene_tick_{sym}(void) { ... }"""
    from codegen.runtime_codegen.input_layout import compute_input_layout as _cil
    if input_layout is None:
        input_layout = _cil(p)
    sym = c_sym(scene.name)
    _lay = scene_oam_layout(p, scene)
    L = [f"static void scene_tick_{sym}(void) {{"]

    def _def(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    # on_update scène
    if getattr(scene, "script", ""):
        L += [f"    {sym}_scene_on_update();"]

    # on_update actors
    if lua_idx:
        for j in sorted(lua_idx):
            actor, _ = scene_actors[j - actor_offset]
            s = scene_actor_sym(scene.name, actor.name)
            if _def(s, "on_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_update(&g_actors[{j}]);")

    # on_update prefabs poolés
    for p2 in pi:
        if _def(p2["sym"], "on_update"):
            # Le pas est le GROUPE : ces trois hooks sont ceux de la RACINE,
            # et un enfant n'a pas de script propre dans cette tranche (le
            # dimensionnement de son état attend la réponse de la v0.17).
            # `resolve_actor_tiles` en particulier DÉPLACE l'acteur : le lancer
            # sur un enfant se battrait avec la composition qui vient de la
            # poser. Groupe = 1 pour un prefab plat, boucle inchangée.
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi+={p2.get('group', 1)})")
            L.append(f"        if(g_actors[_pi].active) {p2['sym']}_on_update(&g_actors[_pi]);")

    # Hiérarchie : APRÈS les scripts — un `on_update` peut avoir déplacé le
    # parent, et l'enfant doit suivre DANS la même frame — et AVANT la
    # collision et l'émission OAM, qui lisent la position monde recomposée.
    L += _parent_compose_lines(scene_actors, actor_offset, _lay.placed_entry)
    L += _pool_compose_lines(pi)

    # Résolution contre la carte de collision — pour TOUTE box solide, et non
    # plus seulement pour les acteurs qui définissent `on_tile_collide` : la
    # résolution DÉPLACE l'acteur, le hook ne fait que prévenir. C'est aussi ce
    # que le modèle promet depuis toujours (« solid=True → résolution physique »).
    # Rien n'est émis si la scène n'a pas de carte : il n'y aurait rien à heurter.
    if scene_has_cmap(scene):
        for j in range(len(scene_actors)):
            actor, _ = scene_actors[j]
            if not has_solid_box(actor):
                continue
            idx = actor_offset + j
            s = scene_actor_sym(scene.name, actor.name)
            cb = f"{s}_on_tile_collide" if (idx in lua_idx and _def(s, "on_tile_collide")) else "NULL"
            L.append(f"    if(g_actors[{idx}].active) resolve_actor_tiles(&g_actors[{idx}], {cb});")

        for p2 in pi:
            if not has_solid_box(p2["prefab"]):
                continue
            cb = f"{p2['sym']}_on_tile_collide" if _def(p2["sym"], "on_tile_collide") else "NULL"
            # Le pas est le GROUPE : ces trois hooks sont ceux de la RACINE,
            # et un enfant n'a pas de script propre dans cette tranche (le
            # dimensionnement de son état attend la réponse de la v0.17).
            # `resolve_actor_tiles` en particulier DÉPLACE l'acteur : le lancer
            # sur un enfant se battrait avec la composition qui vient de la
            # poser. Groupe = 1 pour un prefab plat, boucle inchangée.
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi+={p2.get('group', 1)})")
            L.append(f"        if(g_actors[_pi].active) resolve_actor_tiles(&g_actors[_pi], {cb});")

    # Pool→scene collisions
    col_scene = [
        (actor_offset + j, scene_actors[j][0])
        for j in range(len(scene_actors))
        if any(hasattr(c, "w") for c in scene_actors[j][0].components)
    ]
    if pi and col_scene:
        for p2 in pi:
            s, start, size = p2["sym"], p2["start"], p2["size"]
            # Même filtre que pour les paires de scène (ROADMAP v0.23) : un
            # prefab dont aucun tag ne rencontre ceux d'un acteur n'a pas de
            # ligne dans sa table `_pcol_*`, donc pas de test par frame et par
            # instance. C'est le poste qui grandit le plus vite — pool × acteurs.
            col_scene_pf = [(idx, a) for idx, a in col_scene
                            if actors_can_collide(p, p2["prefab"], a)]
            if not col_scene_pf:
                continue
            np = len(col_scene_pf)
            L += [
                f"    {{",
                f"        static u8 _pcol_{s}[{size}][{np}]={{{{0}}}};",
                f"        for(int _pi={start}; _pi<{start+size}; _pi++){{",
                f"            if(!g_actors[_pi].active) continue;",
                f"            int _sl=_pi-{start};",
            ]
            # Une collision a DEUX côtés, et chacun apprend la nouvelle dans son
            # propre script : c'est déjà ce que fait la boucle scène↔scène plus
            # bas. Ici seul le prefab était prévenu — un actor de scène heurté
            # par un projectile poolé n'avait donc aucun moyen de réagir, et
            # devait passer par une variable globale que la balle posait pour
            # lui. Les deux appels partagent le même test de recouvrement et le
            # même souvenir de frame (`_pcol_`), avec les boxes échangées : la
            # `my_box` de l'un est la `other_box` de l'autre.
            pool_reacts = has_col_event(_def, s)
            for ci, (sidx, sactor) in enumerate(col_scene_pf):
                ss = scene_actor_sym(scene.name, sactor.name)
                s_lua = (sidx in lua_idx) and has_col_event(_def, ss)
                if not pool_reacts and not s_lua:
                    continue
                L += [
                    f"            {{ u8 _bx=0,_bo=0;",
                    f"              u8 _c=(g_actors[{sidx}].active&&actors_overlap_boxes(&g_actors[_pi],&g_actors[{sidx}],&_bx,&_bo))?1:0;",
                    f"              u8 _p=_pcol_{s}[_sl][{ci}];",
                ]
                if _def(s, "on_collision_enter"):
                    L.append(f"              if(_c&&!_p) {s}_on_collision_enter(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                if s_lua and _def(ss, "on_collision_enter"):
                    L.append(f"              if(_c&&!_p) {ss}_on_collision_enter(&g_actors[{sidx}],&g_actors[_pi],_bo,_bx);")
                if _def(s, "on_collide"):
                    L.append(f"              if(_c&&_p)  {s}_on_collide(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                if s_lua and _def(ss, "on_collide"):
                    L.append(f"              if(_c&&_p)  {ss}_on_collide(&g_actors[{sidx}],&g_actors[_pi],_bo,_bx);")
                if _def(s, "on_collision_exit"):
                    L.append(f"              if(!_c&&_p) {s}_on_collision_exit(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                if s_lua and _def(ss, "on_collision_exit"):
                    L.append(f"              if(!_c&&_p) {ss}_on_collision_exit(&g_actors[{sidx}],&g_actors[_pi],_bo,_bx);")
                L.append(f"              _pcol_{s}[_sl][{ci}]=_c; }}")
            L += [f"        }}", f"    }}"]

    # AABB collisions scène
    if col_pairs:
        L.append(f"    static u8 _col_prev[{len(col_pairs)}]={{0}};")
        for pair_idx, (i, j) in enumerate(col_pairs):
            i_lua = i in lua_idx; j_lua = j in lua_idx
            si = c_sym(scene_actors[i - actor_offset][0].name)
            sj = c_sym(scene_actors[j - actor_offset][0].name)
            L += [
                f"    {{ u8 _bx_i=0,_bx_j=0;",
                f"        u8 _cur=(g_actors[{i}].active&&g_actors[{j}].active&&"
                f"actors_overlap_boxes(&g_actors[{i}],&g_actors[{j}],&_bx_i,&_bx_j))?1:0;",
                f"        if(_cur&&!_col_prev[{pair_idx}]){{",
            ]
            if i_lua and _def(si, "on_collision_enter"): L.append(f"            {si}_on_collision_enter(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collision_enter"): L.append(f"            {sj}_on_collision_enter(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L.append(f"        }}")
            L.append(f"        if(_cur&&_col_prev[{pair_idx}]){{")
            if i_lua and _def(si, "on_collide"): L.append(f"            {si}_on_collide(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collide"): L.append(f"            {sj}_on_collide(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L.append(f"        }}")
            L.append(f"        if(!_cur&&_col_prev[{pair_idx}]){{")
            if i_lua and _def(si, "on_collision_exit"): L.append(f"            {si}_on_collision_exit(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collision_exit"): L.append(f"            {sj}_on_collision_exit(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L += [f"        }}", f"        _col_prev[{pair_idx}]=_cur; }}"]

    # Déclencheurs SoundFx par nom d'input — ROADMAP « Les inputs
    # personnalisés », tranche finale (2026-09-27) : les events de script
    # on_button_* ont disparu (un script écrit `if input:pressed(nom) then`
    # dans on_update) ; seul le SoundFxComponent garde un déclenchement
    # AUTOMATIQUE — TOUS les actors de la scène, scriptés ou non, c'est ce qui
    # permet à un item de menu de répondre à un bouton sans une ligne de Lua.
    # `trigger` porte un nom de bouton OU d'accord déclaré (même liste que
    # `input:pressed(nom)`, jamais une séquence) : un nom, pas un bouton
    # physique — deux composants sur le même bouton partagent le même `if`.
    from scripting.api import key_constant as _key_constant
    sfx_by_trigger: dict = {}
    for j, (actor, _spr) in enumerate(scene_actors, start=actor_offset):
        sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, actor)
        if sfx_sym and sfx_trig not in ("manual", "on_spawn", "on_destroy"):
            sfx_by_trigger.setdefault(sfx_trig, []).append(("actor", j, sfx_sym, sfx_vol))
    for p2 in pi:
        sfx_sym, sfx_vol, sfx_trig = _sfx_trigger_info(p, p2["prefab"])
        if sfx_sym and sfx_trig not in ("manual", "on_spawn", "on_destroy"):
            sfx_by_trigger.setdefault(sfx_trig, []).append(("prefab", p2, sfx_sym, sfx_vol))

    for trig_name, entries in sfx_by_trigger.items():
        mask = input_layout.masks.get(trig_name, _key_constant(trig_name))
        L.append(f"    if(input_pressed({mask})){{")
        for kind, ref, sfx_sym, sfx_vol in entries:
            if kind == "actor":
                j = ref
                L.append(f"        if(g_actors[{j}].active) sfx_play({sfx_sym}, {sfx_vol}, 0);"
                         f"   /* SoundFxComponent : {scene_actors[j - actor_offset][0].name} */")
            else:
                p2 = ref
                L.append(f"        for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi+={p2.get('group', 1)})")
                L.append(f"            if(g_actors[_pi].active) sfx_play({sfx_sym}, {sfx_vol}, 0);"
                         f"   /* SoundFxComponent : {p2['prefab'].name} */")
        L.append("    }")

    # on_late_update actors
    if lua_idx:
        for j in sorted(lua_idx):
            actor, _ = scene_actors[j - actor_offset]
            s = scene_actor_sym(scene.name, actor.name)
            if _def(s, "on_late_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_late_update(&g_actors[{j}]);")

    # on_late_update prefabs
    for p2 in pi:
        if _def(p2["sym"], "on_late_update"):
            # Le pas est le GROUPE : ces trois hooks sont ceux de la RACINE,
            # et un enfant n'a pas de script propre dans cette tranche (le
            # dimensionnement de son état attend la réponse de la v0.17).
            # `resolve_actor_tiles` en particulier DÉPLACE l'acteur : le lancer
            # sur un enfant se battrait avec la composition qui vient de la
            # poser. Groupe = 1 pour un prefab plat, boucle inchangée.
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi+={p2.get('group', 1)})")
            L.append(f"        if(g_actors[_pi].active) {p2['sym']}_on_late_update(&g_actors[_pi]);")

    # on_late_update scène
    if getattr(scene, "script", ""):
        L.append(f"    {sym}_scene_on_late_update();")

    # Caméra — l'ordre est la règle, et il tient en quatre lignes :
    #   1. la secousse de la frame précédente est retirée, pour que le suivi
    #      raisonne sur la vraie position et non sur une position tremblée ;
    #   2. le DÉCLARATIF est calculé (suivi par zone morte, si la caméra active
    #      est en mode suivi et que sa cible existe dans cette scène) ;
    #   3. le SCRIPT de la caméra s'exécute ensuite — il peut donc ajuster ce
    #      que le déclaratif vient de poser, ce qui rend l'usage purement
    #      déclaratif, purement scripté ou hybride sans réglage de bascule ;
    #   4. les bornes clampent en dernier, peu importe qui a écrit cam_x/cam_y,
    #      puis la secousse se pose PAR-DESSUS le clamp — trembler au bord du
    #      monde doit se voir.
    # Le tout lit `g_cam_active` : c'est ce qui permet à un script de changer de
    # caméra en cours de partie (camera.switch) sans que le tick soit regénéré.
    L.append("    camera_shake_undo();")
    L += camera_follow_lines(p, scene, scene_actors, actor_offset)
    L.append("    if(g_cam_table[g_cam_active].on_update) g_cam_table[g_cam_active].on_update();")
    L.append("    camera_apply_bounds();")
    L.append("    camera_shake_apply();")

    # BG scroll offset H+V (+ streaming des bords pour un grand niveau)
    if bgi:
        for bi in bgi:
            if bi.get("stream"):
                L.append(f"    bg_stream_update(MAP_RAM({bi['sbb']}), {bi['sym']}Map, "
                         f"{bi['tw']}, {bi['th']}, {bi['win_w']}, {bi['win_h']}, "
                         f"{int(bi['stream_h'])}, {int(bi['stream_v'])}, cam_x, cam_y);")
            # Scroll = caméra × vitesse de parallax + décalage propre au layer
            # (layer_set_scroll / layer_scroll_by depuis Lua).
            L.append(f"    BGOFS({bi['bg']})=(u16)(((cam_x*layer_get_speed({bi['bg']}))>>8)+layer_get_scroll_x({bi['bg']}));")
            L.append(f"    BGVOFS({bi['bg']})=(u16)(((cam_y*layer_get_speed({bi['bg']}))>>8)+layer_get_scroll_y({bi['bg']}));")

    # Fonds animés : APRÈS le streaming, qui recharge des colonnes/lignes
    # entières de la carte en ROM — un animé recouvert par une colonne entrante
    # se redessinerait avec un cycle de retard.
    _all = scene_anim_descriptors(p, scene, bgi)
    _anims = [a for a in _all if not a["shared"]]
    _tanims = [a for a in _all if a["shared"]]
    if _anims:
        L.append(f"    bg_anim_update(g_bganim_{sym}, {len(_anims)});")
    if _tanims:
        L.append(f"    bg_tileanim_update(g_bgtileanim_{sym}, {len(_tanims)});")

    # Animation (state machine + direction)
    for j, (actor, _shown_sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        variants = []
        for _c, sprite in owner_appearances(p, actor):
            if not sprite.states:
                variants.append(None)        # une apparence fixe : rien à animer
                continue
            # Le test d'effet par frame n'est émis que si le sprite en porte —
            # même source de vérité que la table, `sprite_unique_frames`.
            _has_fx = any(a >= 0 for a in frame_action_ids(p, sprite))
            _has_dfx = any(s != "-1" for s, _v in frame_sfx_syms(p, sprite))
            _evt_lines, _has_evt = actor_frame_event_lines(p, actor, sprite)
            variants.append(dict(
                sym=f"sprite_{c_sym(sprite.name)}", has_frame_sfx=_has_fx,
                has_frame_direct_sfx=_has_dfx, event_lines=_evt_lines,
                has_frame_events=_has_evt, actor_sym=scene_actor_sym(scene.name, actor.name)))
        if any(v is not None for v in variants):
            L += anim_tick_variants(idx, _lay.placed_entry[j], variants)

    _aff = affine_info or {}

    # OAM actors scène
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        _e = _lay.placed_entry[j]   # entrée OAM de l'acteur (>= 0 dès qu'il a un sprite)
        if not actor.visible:
            continue
        apps = _appearances(p, actor, sprite_offsets)
        if apps:
            # UI en sprite : x/y SONT déjà des pixels d'écran, la caméra ne les
            # touche pas. Décidé ici, au build — un acteur de monde émet
            # exactement le C qu'il émettait avant (cf. Actor.screen_space).
            L += oam_write_lines(
                idx, _e, apps, aff=_aff.get(idx),
                screen_space=bool(getattr(actor, "screen_space", False)))

    # OAM prefab pool
    for p2 in pi:
        pf = p2["prefab"]
        group = p2.get("group", 1)
        # Les MEMBRES d'un groupe, dans l'ordre où le spawn les pose : la
        # racine puis ses enfants (ROADMAP v0.23). Chacun a son propre sprite —
        # un bras n'est pas dessiné avec l'image du corps. Un prefab plat n'a
        # qu'un membre, et le C émis est alors mot pour mot celui d'avant.
        members = [pf] + list(getattr(pf, "children", []) or [])
        for a_idx in range(p2["start"], p2["start"] + p2["size"]):
            _inst, _member = divmod(a_idx - p2["start"], group)
            owner = members[_member]
            _rank = p2["member_entries"][_member]
            if _rank < 0:
                # Un marqueur (point de tir, ancre de hitbox) n'a pas d'entrée OAM :
                # rien à écrire, rien à cacher.
                continue
            oam_slot = p2["entry_start"] + _inst * p2["entries_per_instance"] + _rank
            L += oam_write_lines(a_idx, oam_slot, _appearances(p, owner, sprite_offsets),
                                 aff=_aff.get(a_idx))

    # Après les scripts, avant le flush OAM : une lecture démarrée pendant le
    # tick avance dès cette frame, et les sprites des glyphes animés sont posés
    # avant d'être copiés en OAM.
    # La navigation AVANT le rendu d'UI : le script a déjà tourné, il a pu
    # poser le nombre d'items ; l'index bouge donc dans la même frame que
    # l'appui, et les rangées se dessinent ensuite avec le bon curseur.
    L.append("    ui_list_tick();")
    L.append("    ui_image_update();")
    L.append("    text_update();")
    L.append("    oam_update();")
    L.append("}")
    L.append("")
    return L


# ─── point d'entrée ───────────────────────────────────────────────────────────

def generate_main(
    p: Project,
    all_scene_data: list[dict],   # list of {scene, bg_pairs, scene_actors, prefab_sprites}
    sound_assets: dict | None,
    prefab_actor_sprites: list,
    prefabs,
    emit,
    actor_defined_events: dict[str, set[str]] | None = None,
) -> bool:
    """Génère main.c multi-scène et le copie dans p.src_dir/."""
    prefab_actor_sprites = prefab_actor_sprites or []
    has_sound   = bool(sound_assets and (sound_assets.get("sfx") or sound_assets.get("music")))
    soundbank_h = p.build_dir / "soundbank.h"
    all_scenes  = [d["scene"] for d in all_scene_data]
    scene_names = [s.name for s in all_scenes]
    start_scene = (getattr(p.settings, "start_scene", None) or
                   (scene_names[0] if scene_names else ""))
    start_idx   = next((i for i, n in enumerate(scene_names) if n == start_scene), 0)

    # Copier gba_engine.h
    _src = RUNTIME_DIR / "include" / "gba_engine.h"
    if _src.exists():
        build_output.copy(_src, p.src_dir / "gba_engine.h")

    # ── Calcul des offsets globaux des actors ─────────────────────
    # Chaque scène reçoit une tranche de g_actors[].
    # La pool de prefabs commence après tous les actors de scène.
    # Chaque scène repart de la base OAM 0 (ROADMAP v0.17, T3) : une seule est
    # vivante à la fois, le scene_init efface `g_actors` et repose ses acteurs
    # depuis 0. Les offsets sont donc tous nuls, et `g_actors` est dimensionné
    # sur la scène la plus gourmande (max, pas somme).
    n_actors = project_actor_count(p)
    n_oam_entries = project_oam_entry_count(p)
    scene_offsets = [0] * len(all_scene_data)
    # `pi` par scène : plages de pool per-scène (symboles `<Scène>_<Prefab>`),
    # lues de `scene_oam_layout`. Chaque scène ne porte que les pools qu'elle
    # déclare, à leur place dans SA fenêtre.
    scene_pis = [_scene_pi(p, d["scene"]) for d in all_scene_data]

    # ── Sprites : union de toutes les scènes ──────────────────────
    all_sprite_pairs: list = []
    for d in all_scene_data:
        all_sprite_pairs += d["scene_actors"] + d["extra_sprites"]
    all_sprite_pairs += prefab_actor_sprites
    # Un sprite qui ne sert QU'à une image d'interface n'est porté par aucun
    # acteur : sans ceci, ses tuiles ne partiraient jamais en VRAM.
    all_sprite_pairs += ui_image_sprites(p)

    sprite_offsets, sprite_nframes = sprite_offsets_for(p, all_sprite_pairs)

    # Bande de texte OBJ. La base de SLOTS OAM est PAR SCÈNE — juste après les
    # acteurs, avant les pools (ordre acteurs → UI → pools, ROADMAP v0.17 T4) :
    # elle vaut `placed`, calculée dans la boucle scene_init. La base de TUILES,
    # elle, reste l'union projet : les tuiles des sprites sont résidentes et
    # partagées, donc la 1re tuile OBJ libre est la queue de TOUS les sprites.
    _obj_alloc = obj_text_alloc(p)
    obj_text_tile = obj_tiles_used(p, all_sprite_pairs)
    _any_obj_ui = any(scene_obj_ui_slots(p, d["scene"]) > 0 for d in all_scene_data)

    # Débordement : BLOQUANT, et calculé même sans `emit` — sinon la ROM se
    # construit avec des slots hors des 128 du matériel, rien à l'écran et
    # aucune erreur (le fond de conteneur en sprites rend le cas trivial : un
    # conteneur 224×48 pavé d'une frame 8×8 réclame 168 slots à lui seul).
    _fatal: list[str] = []
    # Le débordement OAM par scène (acteurs + UI + pools > 128) est la faute du
    # BUDGET, gardée en un SEUL endroit : le validateur (`_check_actor_budget`,
    # ERREUR bloquante, même source `scene_oam_layout`). `generate_main` n'est
    # atteint qu'après une validation sans erreur (cf. rom_build) — le
    # re-contrôler ici dédoublait la règle. Reste la faute des TUILES (VRAM),
    # qui n'est pas dans le budget OAM.
    # Tuiles OBJ (VRAM) : union projet, cap selon le mode bitmap le plus
    # contraint (la VRAM BG y empiète sur l'espace sprite : 512 au lieu de 1024).
    if _any_obj_ui:
        _tiles_need = max((pl["tile_rel"] + pl["tiles"] for pl in _obj_alloc.values()),
                          default=0)
        _cap = 512 if any(getattr(sc, "render_mode", 0) in (3, 4, 5)
                          for sc in p.scenes) else 1024
        if obj_text_tile + _tiles_need > _cap:
            _fatal.append(
                f"[error] les zones de texte en sprites demandent "
                f"{_tiles_need} tuiles OBJ après {obj_text_tile} de sprites, "
                f"soit plus que les {_cap} disponibles.")
    # Débordement de la SRAM, ou deux variables persistantes indiscernables :
    # même règle que ci-dessus, ça bloque. Une sauvegarde qui déborde ne se
    # verrait qu'à l'exécution, chez le joueur.
    _fatal += save_fatal(p)
    # Parenté (ROADMAP v0.23) : un parent inconnu ou un cycle empêchent de
    # calculer une profondeur, donc d'ordonner la frame. Bloquant comme le
    # budget de tuiles, et pour la même raison — ça ne se verrait qu'en jouant.
    for _d in all_scene_data:
        _fatal += parent_depths(_d["scene_actors"])[1]
    # Un enfant hérite de la rotation et de l'échelle de son parent — mais il
    # ne peut les AFFICHER que s'il a un slot affine, le sien ou celui du
    # parent partagé. Il n'en partage pas quand il a un transform propre, et
    # il n'en réserve pas sans « Affine transform » : la composition serait
    # alors calculée puis ignorée à l'écran. Un avertissement et non une
    # erreur — le jeu tourne, c'est l'affichage qui ment.
    if emit:
        for _d in all_scene_data:
            _sa = _d["scene_actors"]
            _aff = compute_affine_info(0, _sa, [])
            _by = {a.name: a for a, _ in _sa}
            for _j, (_a, _sp) in enumerate(_sa):
                _par = _by.get(getattr(_a, "parent", None) or "")
                if not _par or _j in _aff or not affine_sprite_component(_a):
                    continue
                _par_sc = affine_sprite_component(_par)
                if not bool(getattr(_par_sc, "affine_transform", False)):
                    continue
                emit("log_line",
                     f"[warn] acteur '{_a.name}' : son parent '{_par.name}' peut "
                     f"tourner ou changer d'échelle, mais '{_a.name}' n'a pas de "
                     f"slot affine — il ne partage pas celui du parent (il a sa "
                     f"propre rotation ou échelle) et n'en réserve pas. Cocher "
                     f"« Affine transform » sur le sprite de '{_a.name}' pour "
                     f"qu'il suive.")
    if _fatal:
        for _m in _fatal:
            if emit:
                emit("error_line", _m)
        return False

    # ── Génération des includes (union de toutes les scènes) ──────
    L: list[str] = []
    seen_incs: set[str] = set()

    def _add_inc(line: str):
        if line not in seen_incs:
            seen_incs.add(line)
            L.append(line)

    _add_inc('#define GBA_ENGINE_IMPL')
    _add_inc('#include "gba_engine.h"')
    _add_inc('#include "runtime_api.h"')
    _add_inc('#include "globals.h"')
    _add_inc('#include "constants.h"')
    _add_inc('#include "gba_debug.h"')   # mesure de budget par frame — ROADMAP v0.14
    if has_sound and soundbank_h.exists():
        _add_inc('#include <maxmod.h>')
        _add_inc(f'#include "{soundbank_h.name}"')
        _add_inc('#include "soundbank.bin.h"')

    for d in all_scene_data:
        bgi_d = bg_info(p, d["scene"])
        _apply_vram_layout(p, d["scene"], bgi_d, scene_text_reservation(p, d["scene"]))
        _log_vram_layout(d["scene"], emit)
        for bi in bgi_d:
            _add_inc(f'#include "{bi["sym"]}.h"')
        # Tables d'images des fonds animés — un header par scène, toujours émis
        # (vide si la scène n'en pose aucun), pour que l'include ne dépende pas
        # d'un état que le générateur devrait deviner.
        from codegen.bg_anim import scene_anim_sym, shared_anim_sym
        _add_inc(f'#include "{scene_anim_sym(d["scene"])}.h"')
        _add_inc(f'#include "{shared_anim_sym(d["scene"])}.h"')
        for _, sprite in d["scene_actors"]:
            if sprite and sprite.asset:
                _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    for _, sprite in prefab_actor_sprites:
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    # Les sprites des IMAGES d'interface ne sont portés par aucun acteur ni
    # prefab, mais leurs tuiles partent en VRAM OBJ par le même chemin (cf.
    # `ui_image_sprites`) : leur header grit doit être inclus au même titre.
    # Sans ça, un sprite utilisé UNIQUEMENT par une image d'UI compilait sur
    # « 'sprite_XTiles' undeclared » — le cas restait masqué tant qu'un acteur
    # partageait le sprite et amenait l'include avec lui.
    for _, sprite in ui_image_sprites(p):
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    # Externs actors + scènes (filtrés sur les events réellement implémentés)
    def _def(sym, ev):
        """True si l'event est défini dans le script Lua de cet actor."""
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    for d in all_scene_data:
        sc = d["scene"]
        sc_sym = c_sym(sc.name)
        for actor, _ in d["scene_actors"]:
            s = scene_actor_sym(sc.name, actor.name)
            script_path = _actor_script(actor)
            if script_path:
                abs_sp = p.asset_abs(script_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    for ev in ("on_start", "on_update", "on_late_update", "on_tile_collide",
                               "on_collision_enter", "on_collide", "on_collision_exit"):
                        if _def(s, ev):
                            if ev == "on_tile_collide":
                                L.append(f"extern void {s}_{ev}(Actor*,int,int);")
                            elif ev in ("on_collision_enter", "on_collide", "on_collision_exit"):
                                L.append(f"extern void {s}_{ev}(Actor*,Actor*,u8,u8);")
                            else:
                                L.append(f"extern void {s}_{ev}(Actor*);")
        if getattr(sc, "script", ""):
            L += [
                f"extern void {sc_sym}_scene_on_start(void);",
                f"extern void {sc_sym}_scene_on_update(void);",
                f"extern void {sc_sym}_scene_on_late_update(void);",
            ]
    L.append("")

    # ── Caméras du projet ────────────────────────────────────────
    # Une caméra est une DONNÉE : la table ci-dessous en est la forme runtime,
    # l'entrée 0 étant toujours la caméra par défaut (fixe à l'origine, sans
    # bornes) — celle qu'obtient une scène qui n'en désigne aucune, sans
    # qu'aucun fichier n'ait à exister.
    cams = project_cameras(p)
    for cam in cams[1:]:
        if getattr(cam, "script", ""):
            cs = camera_sym(cam.name)
            L += [
                f"extern void {cs}_camera_on_start(void);",
                f"extern void {cs}_camera_on_update(void);",
            ]
    L.append(f"const Camera g_cam_table[{len(cams)}] = {{")
    for cam in cams:
        if cam is None:
            # 240,160 = plein écran = WIN0 éteinte (frame_w/h), pas 0,0 qui
            # donnerait un cadre nul — cf. Camera.frame_w/h.
            L.append("    { 0, 40, 20, 0, 0, 0, 0, 0, 0, 240, 160, NULL, NULL },   /* (default) */")
            continue
        cs = camera_sym(cam.name)
        hooks = (f"{cs}_camera_on_start, {cs}_camera_on_update"
                 if getattr(cam, "script", "") else "NULL, NULL")
        L.append(f"    {{ {cam.mode_id()}, {int(cam.margin_x)}, {int(cam.margin_y)}, "
                 f"{int(cam.x)}, {int(cam.y)}, "
                 f"{int(cam.bounds_x or 0)}, {int(cam.bounds_y or 0)}, "
                 f"{int(cam.bounds_w or 0)}, {int(cam.bounds_h or 0)}, "
                 f"{int(cam.frame_w)}, {int(cam.frame_h)}, {hooks} }},"
                 f"   /* {cam.name} — {cam.mode} */")
    L += ["};", ""]

    # ── Polices + table des textes ───────────────────────────────
    L += fonts_and_texts_lines(p, emit)

    # ── Tables d'animation par SpriteAsset (dédupliquées) ────────
    # Les sprites des IMAGES d'interface en font partie : `g_ui_images` pointe
    # ces tables-là, donc elles doivent exister — et être émises AVANT.
    _all_sprites_flat = [
        pair
        for d in all_scene_data
        for pair in d["scene_actors"]
    ] + (prefab_actor_sprites or []) + ui_image_sprites(p)
    done_anim: set[str] = set()
    for _, sprite in _all_sprites_flat:
        if sprite and sprite.asset and sprite.name not in done_anim:
            done_anim.add(sprite.name)
            L += anim_tables_for(p, sprite)
            L.append("")

    # ── Images d'interface ────────────────────────────────────────
    L += _ui_images_lines(p, sprite_offsets, emit)

    # ── Visibilité des éléments d'interface ──────────────────────
    # APRÈS g_ui_regions/g_ui_images : les deux référencent un index de
    # CETTE table (`elem`), mais la lecture est par nom aux deux endroits
    # (`ui_element_index`), l'ordre d'émission n'a donc pas à être contraint
    # — placée ici pour rester avec le reste de l'UI.
    L += emit_ui_elements_c(p)
    L += emit_ui_lists_c(p, emit)

    # ── Sauvegarde ────────────────────────────────────────────────
    # Après globals.h (inclus plus haut) : les tables citent les index
    # GLOBAL_*, et le pilote appelle global_read/global_write.
    L += save_lines(p, emit)

    # ── Tile helpers (dispatch via pointeur) ──────────────────────
    L += _gen_tile_helpers()

    # ── Cmap flat arrays par scène ────────────────────────────────
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        cmap = sc.collision_map or []
        if cmap and any(v != 0 for row in cmap for v in row):
            rows = len(cmap)
            cols = max(len(row) for row in cmap)
            flat = []
            for row in cmap:
                flat += list(row) + [0] * (cols - len(row))
            L += [
                f"#define CMAP_W_{sym.upper()} {cols}",
                f"#define CMAP_H_{sym.upper()} {rows}",
                f"static const u8 g_cmap_{sym}[{rows*cols}] = {{",
                "    " + ", ".join(str(v) for v in flat),
                "};",
                "",
            ]

    # ── Palettes OBJ actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_obj_palettes -> project.palettes) ────────────
    # Émis uniquement si au moins un slot est réellement occupé — sinon la
    # boucle copy16 correspondante dans _gen_scene_init ne référence jamais
    # ce tableau ("defined but not used", en plus de gaspiller 512 octets
    # de ROM par scène sans palette OBJ active, ex. INTRO/VICTORY).
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        if scene_bank_layout(p, sc, "obj").bank_count() > 0:
            words = scene_obj_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_obj_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
                "};",
                "",
            ]

    # ── Palettes BG actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_bg_palettes -> project.palettes) ──────────────
    # Même garde qu'OBJ ci-dessus — le backdrop (PAL_BG_RAM[0]) est écrit à
    # part comme constante littérale (resolve_backdrop_color), pas depuis
    # ce tableau, donc rien ne le référence si aucun slot BG n'est occupé.
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
        # Émis si un slot BG est occupé (référencé, bloc de fond compressé, ou
        # palette propre) ; le backdrop (PAL_BG_RAM[0]) est écrit séparément.
        if scene_bank_layout(p, sc, "bg").bank_count() > 0:
            words = scene_bg_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_bg_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
                "};",
                "",
            ]

    # ── Globals ───────────────────────────────────────────────────
    # `g_actors` est réutilisé d'une scène à l'autre (base 0, ROADMAP v0.17,
    # T3) : dimensionné sur la scène la plus gourmande, il porte à tout instant
    # les acteurs de la SEULE scène vivante. C'est un état volumineux, jamais une
    # routine chaude ; EWRAM_DATA évite de consommer les 32 Kio d'IWRAM réservés
    # au code et aux petits états runtime.
    L += [
        f"Actor g_actors[{n_actors}] EWRAM_DATA;",
        f"OamEntry g_oam_entries[{n_oam_entries}] EWRAM_DATA;",
        "const AppearanceInit* g_appearance_init;   /* constantes d'activation de la scène active */",
    ]
    # SoundFxComponent en trigger="on_destroy" — tables PAR SCÈNE indexées par
    # TAG, plus un pointeur que chaque scene_init fait pointer sur la sienne
    # (comme `g_active_cmap`). Depuis que les TAG repartent de 0 par scène
    # (T3), une table globale unique ne pourrait plus les distinguer. Lues par
    # `actor_destroy_with_sfx()` — le SEUL point commun à `self:destroy()` et
    # `other:destroy()` (scripting/codegen.py, `_emit_destroy`), la cible n'y
    # étant pas toujours un symbole connu au build.
    L += _sfx_on_destroy_table(p, all_scene_data, scene_pis)
    # Anneau + compteurs d'input (ROADMAP « Les inputs personnalisés ») :
    # profondeur et bitset `buffered` calculés depuis les actions RÉELLEMENT
    # déclarées et interrogées par le projet — 0 action bufferisée, 0 octet
    # payé (`compute_input_layout`, seule source, la même que `lua_compiler.py`
    # pour le catalogue de chaque script).
    from codegen.runtime_codegen.input_layout import compute_input_layout
    _input_layout = compute_input_layout(p)
    _buffered_bytes = max(1, (len(_input_layout.buffered_bits) + 7) // 8)
    for _symbol, _steps in _input_layout.seq_table_defs.items():
        # NON static : `runtime_api.h` en déclare l'extern pour les unités de
        # scène/acteur qui appellent `input_seq_pressed` sur cette action.
        L.append(f"const u16 {_symbol}[] = {{{', '.join(_steps)}}};")
    L += [
        "u32   _g_keys_held    = 0;",
        "u32   _g_keys_pressed = 0;",
        f"u16   _g_input_ring[{_input_layout.ring_depth}];",
        "int   _g_input_ring_pos = 0;",
        f"const int g_input_ring_depth = {_input_layout.ring_depth};",
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
        # Taille du monde de la scène courante, lue par `scene.size` : déclarée
        # `extern` dans runtime_api_inline.h et posée par chaque scene_init — il
        # manquait sa DÉFINITION, et le lien échouait sur tout projet.
        "int   g_scene_w = 0, g_scene_h = 0;",
        # Défilement autorisé par la scène courante — lu par `scene.scroll_h/v`.
        "int   g_scene_scroll_h = 1, g_scene_scroll_v = 0;",
        "int   g_scene_collision_layer = 0;",
        "int   g_current_scene = -1;",
        "int   g_scene_placed = 0;   /* acteurs posés de la scène active (actor:get(i)) */",
        "int   g_next_scene    = -1;",
        "",
    ]

    # Spawn helpers — un jeu par scène (`spawn_<Scène>_<Prefab>`), chacun contre
    # SA plage OAM et SA banque de palette OBJ. Fin de la « scène d'ancrage »
    # figée : chaque scène résout l'index de banque de ses prefabs poolés dans
    # son propre layout (ROADMAP v0.17, T1).
    for d, spi in zip(all_scene_data, scene_pis):
        _obj_layout = scene_bank_layout(p, d["scene"], "obj")
        L += _section_spawn(spi, p, _obj_layout,
                            actor_defined_events=actor_defined_events)

    # Position d'un acteur pour les zones de texte ancrées : `gba_engine.h`
    # ignore la structure Actor (elle est déclarée dans runtime_api_inline.h, qui
    # inclut le moteur et non l'inverse), d'où ces deux accesseurs passés par
    # pointeur de fonction plutôt qu'une dépendance inversée. Émis dès qu'UNE
    # scène a de l'UI OBJ (le pointeur est projet-global, posé par scene_init).
    if _any_obj_ui:
        L += [
            "/* ── Position et profondeur d'acteur pour l'UI ancrée ─── */",
            "static int _txt_actor_x(int i) { return g_actors[i].x>>8; }",
            "static int _txt_actor_y(int i) { return g_actors[i].y>>8; }",
            "static int _txt_actor_prio(int i) { return actor_oam_entry(&g_actors[i])->priority; }",
            "",
        ]

    # ── Boîtes à état sonores ─────────────────────────────────────
    # Avant les scene_init et les scene_tick : le stepper d'animation lit
    # `g_sound_box_action[]` pour résoudre l'action d'une frame.
    if has_sound and soundbank_h.exists():
        # La hauteur courante de chaque effet — déclarée `extern` dans
        # runtime_api.h, définie ici comme les autres états d'un événement en
        # cours. 1024 = hauteur normale ; `sfx_play` la repose à chaque
        # lecture (cf. headers.py, et ROADMAP v0.8.6 pour la mesure qui
        # oblige à la retenir).
        L += ["mm_hword g_sfx_rate[16] = {1024,1024,1024,1024,1024,1024,1024,1024,"
              "1024,1024,1024,1024,1024,1024,1024,1024};", ""]
        from codegen.runtime_codegen.sound_emit import emit as _emit_sound_boxes
        L += _emit_sound_boxes(p)

    # ── scene_init_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc         = d["scene"]
        act_off    = scene_offsets[i]
        bgi_d      = bg_info(p, d["scene"])
        _apply_vram_layout(p, sc, bgi_d, scene_text_reservation(p, sc))
        sa         = d["scene_actors"]

        # lua_idx local (indices GLOBAUX)
        lua_idx_d: set[int] = set()
        for j, (actor, _) in enumerate(sa):
            sp_path = _actor_script(actor)
            if sp_path:
                abs_sp = p.asset_abs(sp_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    lua_idx_d.add(act_off + j)

        # DISPCNT — activer CHAQUE slot d'UI de la scène (v0.12 : plusieurs
        # possibles), plus les slots des fonds ci-dessous.
        bg_bits = {0: 0x0100, 1: 0x0200, 2: 0x0400, 3: 0x0800}
        dispcnt = 0
        for us in p.scene_ui_bg_slots(sc):
            dispcnt |= bg_bits.get(us, 0)
        if bgi_d:
            for bi in bgi_d:
                dispcnt |= bg_bits.get(bi["bg"], 0)
        if sprite_offsets:
            dispcnt |= 0x1040

        # Base OBJ de la bande d'interface de CETTE scène : juste après ses
        # acteurs (ordre acteurs → UI → pools, ROADMAP v0.17 T4). -1 si la scène
        # n'a aucune UI en sprites. Les pools de `scene_oam_layout` démarrent à
        # `placed + ui`, donc la bande ne les chevauche jamais.
        _sc_lay = scene_oam_layout(p, sc)
        sc_obj_oam = _sc_lay.ui_start if _sc_lay.ui else -1
        if emit and _sc_lay.ui:
            emit("log_line",
                 f"[text] scène '{sc.name}' : bande OBJ OAM "
                 f"{sc_obj_oam}..{sc_obj_oam + _sc_lay.ui - 1} (sur 128), "
                 f"tuiles depuis {obj_text_tile}")

        L += _gen_scene_init(
            p, sc, act_off, bgi_d, sa, lua_idx_d, scene_pis[i],
            sprite_offsets, dispcnt, has_sound, sound_assets,
            actor_defined_events=actor_defined_events,
            obj_text_oam=sc_obj_oam, obj_text_tile=obj_text_tile,
            emit=emit,
            affine_info=compute_affine_info(act_off, sa, scene_pis[i]),
        )

    # ── scene_tick_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc      = d["scene"]
        act_off = scene_offsets[i]
        bgi_d   = bg_info(p, d["scene"])
        _apply_vram_layout(p, sc, bgi_d, scene_text_reservation(p, sc))
        sa      = d["scene_actors"]

        lua_idx_d: set[int] = set()
        for j, (actor, _) in enumerate(sa):
            sp_path = _actor_script(actor)
            if sp_path:
                abs_sp = p.asset_abs(sp_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    lua_idx_d.add(act_off + j)

        # La matrice de collision (ROADMAP v0.23) retire ici les paires qui ne
        # peuvent PAS se rencontrer — « les projectiles du joueur ignorent ceux
        # du boss ». Elles ne coûtent alors plus rien : c'était le seul poste
        # qui grandissait en CARRÉ, en taille de ROM comme en temps de frame,
        # et précisément dans la salle la plus chargée.
        col_pairs_d = [
            (act_off + ii, act_off + jj)
            for ii in range(len(sa))
            for jj in range(ii + 1, len(sa))
            if ((act_off + ii) in lua_idx_d or (act_off + jj) in lua_idx_d)
            and actors_can_collide(p, sa[ii][0], sa[jj][0])
        ]

        affine_d = compute_affine_info(act_off, sa, scene_pis[i])
        L += _gen_scene_tick(
            p, sc, act_off, bgi_d, sa, lua_idx_d, scene_pis[i],
            sprite_offsets, sprite_nframes, col_pairs_d,
            actor_defined_events=actor_defined_events,
            affine_info=affine_d,
            input_layout=_input_layout,
        )

    # ── Dispatch table ────────────────────────────────────────────
    # `trans_mode`/`trans_frames` : la transition de CETTE scène, employée
    # aussi bien quand on la quitte (fermeture) que quand on l'ouvre
    # (ouverture) — chaque scène décrit sa propre disparition et sa propre
    # apparition, cf. ROADMAP v0.6.2. L'héritage projet→scène est résolu ici :
    # le runtime ne connaît pas la notion.
    from core.models.scene import TRANSITION_MODES, transition_of
    n_scenes = len(all_scene_data)
    trans = []   # (mode BLDCNT, durée d'une moitié) par scène
    for d in all_scene_data:
        kind, frames = transition_of(d["scene"], p.settings)
        trans.append((TRANSITION_MODES.get(kind, 0), min(255, max(1, frames)), kind))
    # Aucune scène n'a de transition → rien de tout ceci n'est émis : un projet
    # qui n'en veut pas garde la bascule sèche d'avant, au bit près.
    has_transitions = any(m for m, _, _ in trans)

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
                    f"return actor_live(&g_actors[TAG_{tag}]);")
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

    if has_transitions:
        L += [
            "/* ── Transition de scène (cf. ROADMAP v0.6.2) ──────────────────── */",
            "/* Phase 0 = aucune, 1 = fermeture (la scène sortante est gelée),",
            "   2 = ouverture. L'intensité va de 0 (net) à 16 (éteint). */",
            "static int g_trans_phase = 0, g_trans_i = 0, g_trans_n = 1;",
            "",
            "/* Bascule effective. L'écran est déjà éteint quand scene_init tourne :",
            "   son display_reset() n'écrit que dans les shadows tant que la",
            "   transition possède les registres, donc la scène entrante ne",
            "   surgit pas en pleine lumière au milieu de son chargement. */",
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

    # ── Transitions musicales (ROADMAP v0.8.3) ────────────────────
    # Le pas par frame des deux transitions. Un seul point d'écriture du
    # volume de module et de la bascule, comme la caméra n'a qu'un seul point
    # d'écriture de sa position (v0.6.1) : deux mécanismes qui écrivent le même
    # registre sans se coordonner, c'est le défaut qu'on a déjà corrigé une fois.
    if has_sound and soundbank_h.exists():
        L += [
            "static void music_transition_tick(void){",
            "    if(!g_mtr_mode) return;",
            "    if(g_mtr_mode == 1){",
            "        /* Fondu traversant. La bascule tombe à la moitié, quand le",
            "           volume est à zéro : c'est là qu'un changement s'entend le",
            "           moins. */",
            "        int half = g_mtr_n / 2;",
            "        g_mtr_i++;",
            "        if(g_mtr_i < half){",
            "            mmSetModuleVolume((mm_word)(g_mtr_vol * (half - g_mtr_i) / half));",
            "        } else if(g_mtr_i == half){",
            "            mmStart((mm_word)g_mtr_id, g_mtr_loop ? MM_PLAY_LOOP : MM_PLAY_ONCE);",
            "            mmSetModuleVolume(0);",
            "        } else if(g_mtr_i >= g_mtr_n){",
            "            mmSetModuleVolume((mm_word)g_mtr_vol);",
            "            g_mtr_mode = 0;",
            "        } else {",
            "            int k = g_mtr_i - half, n = g_mtr_n - half;",
            "            mmSetModuleVolume((mm_word)(g_mtr_vol * k / n));",
            "        }",
            "        return;",
            "    }",
            "    /* Coupe à la position. On guette le retour en arrière de la LIGNE :",
            "       c'est la frontière de motif, et ça marche aussi pour un module",
            "       d'un seul motif, dont l'index d'ordre ne changerait jamais.",
            "       mmPosition() ne sait viser qu'un motif — couper en cours de motif",
            "       rejouerait donc les lignes déjà passées, ce qui s'entend. */",
            "    {",
            "        int row = (int)mmGetPositionRow();",
            "        if(row < g_mtr_row){",
            "            mm_word pat = mmGetPosition();",
            "            mmStart((mm_word)g_mtr_id, g_mtr_loop ? MM_PLAY_LOOP : MM_PLAY_ONCE);",
            "            mmPosition(pat);",
            "            mmSetModuleVolume((mm_word)g_mtr_vol);",
            "            g_mtr_mode = 0;",
            "        } else {",
            "            g_mtr_row = row;",
            "        }",
            "    }",
            "}",
            "",
        ]

    # ── main() ────────────────────────────────────────────────────
    L.append("int main(void){")
    L.append("    irqInit(); irqEnable(IRQ_VBLANK);")
    # Waitstates SRAM, posés avant toute lecture. Inconditionnel : c'est une
    # écriture de registre, et la rendre conditionnelle ferait dépendre le
    # démarrage d'un état du projet pour économiser un cycle.
    L.append("    sram_init();")

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
        L.append(f"    mmInitDefault((mm_addr)soundbank_bin, {_ch});"
                 f"   /* {_ch} canaux — {sound_channels_bytes(_ch)} o de tas */")
        from codegen.runtime_codegen.sound_emit import music_start_lines
        L += music_start_lines(p)
        # Plus de mmStart au boot. Il démarrait la PREMIÈRE musique du projet,
        # quelle qu'elle soit — un emplacement réservé qui rendait un bref
        # éclat de la mauvaise piste avant que la scène de départ ne pose la
        # sienne. C'est `Scene.music` qui décide maintenant (ROADMAP v0.8.2).

    # Sprites VRAM (une seule fois au démarrage — toutes scènes). Les
    # palettes OBJ ne sont PLUS copiées ici : chaque scene_init_X() charge
    # déjà la sienne (g_pal_obj_{sym}) au bon moment, y compris pour la
    # scène de départ (appelée juste après, cf. boucle principale ci-dessous).
    if sprite_offsets:
        L.append("    /* Tiles sprites → OBJ VRAM (toutes scènes) */")
        for name, base in sprite_offsets.items():
            ss = f"sprite_{c_sym(name)}"
            L.append(f"    copy16(OBJ_VRAM+{base}*16, {ss}Tiles, {ss}TilesLen);")

    L.append(f"    g_next_scene = {start_idx};   /* {start_scene} */")
    L.append("    while(1){")
    if has_transitions:
        L += [
            "        /* Rechargement de langue (phase 4) : force le garde-fou ci-dessous",
            "           à réinitialiser la MÊME scène, comme un vrai changement. Le fondu",
            "           de FERMETURE ne joue pas cette fois (g_current_scene forcé à -1,",
            "           donc « pas de scène sortante » côté transition) — un lang:set()",
            "           et un scene:switch() la même frame perdraient ce fondu-là, cas",
            "           assez rare pour ne pas le traiter à part. */",
            "        if(g_lang_reload){ g_lang_reload=0; g_current_scene=-1; }",
            "        /* Fermeture : la scène qu'on QUITTE décide du fondu, et gèle",
            "           pendant celui-ci. Rien à jouer → bascule immédiate. */",
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
            "        /* Rechargement de langue (phase 4) : force le garde-fou juste",
            "           en-dessous à réinitialiser la MÊME scène. */",
            "        if(g_lang_reload){ g_lang_reload=0; g_current_scene=-1; }",
            "        if(g_next_scene != g_current_scene){",
            "            g_current_scene = g_next_scene;",
            f"            if(g_current_scene>=0 && g_current_scene<{n_scenes})",
            "                g_scene_vtable[g_current_scene].init();",
            "        }",
        ]
    L.append("        VBlankIntrWait();")
    # ROADMAP v0.14 : la fenêtre mesurée est EXACTEMENT le travail d'une frame —
    # de la reprise après ce VBlankIntrWait() à l'entrée du suivant. Hors build
    # debug, `debug_budget_start` est un stub vide éliminé à l'inlining (-O2) :
    # aucun coût, pas un drapeau testé à chaque frame.
    L.append("        debug_budget_start();")
    if has_sound and soundbank_h.exists():
        L.append("        mmFrame();   /* doc maxmod.h : _doit_ être appelée chaque frame */")
        L.append("        music_transition_tick();")
    L += [
        "        _g_frame++;",
        "        scanKeys();",
        "        _g_keys_held    = keysHeld();",
        "        _g_keys_pressed = keysDown();",
        "        _input_ring_push(_g_keys_held);",
        "        _input_update_hold_frames(_g_keys_held);",
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
            "            continue;   /* la scène sortante est gelée */",
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

    out = p.src_dir / "main.c"
    build_output.write(out, "\n".join(L) + "\n")
    emit("log_line", f"[gen] {out.relative_to(p.root)}")
    return True
