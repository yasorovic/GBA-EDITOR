"""runtime_codegen/gen_scene_tick.py — le `scene_tick_<scène>` : les quatre phases du tick d'une scène (hooks, physique,
late, rendu) et le répartiteur qui les appelle.

Les phases sont celles d'`iwram_plan.TICK_PHASES` ; chacune peut être placée en IWRAM par le build."""
from __future__ import annotations

from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.iwram_plan import TICK_PHASES
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen import shared_pool_gen
from codegen.runtime_codegen.block_gen import block_tick_lines
from codegen.runtime_codegen.gen_affine import pool_affine
from codegen.runtime_codegen.gen_camera import camera_follow_lines
from codegen.runtime_codegen.gen_pool import dispatch_sym, parent_compose_lines, pool_compose_lines
from codegen.runtime_codegen.gen_scene_query import (
    actors_can_collide, has_col_event, has_solid_box, scene_anim_descriptors, scene_has_cmap,
)
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.gen_sprite import (
    anim_tick_variants, anim_variants, appearances, oam_write_lines, shown,
)
from codegen.runtime_codegen.interact_gen import box_contact_lines, interact_tick_lines
from core.models.components import affine_sprite_component
from core.models.scene import Scene
from core.project import Project
from codegen.iwram_plan import iwram_macros


def gen_scene_tick(
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
    """Génère le tick d'une scène : QUATRE fonctions de phase (`scene_tick_<scène>_<phase>`) et le répartiteur
    `scene_tick_<scène>` qui les appelle dans l'ordre.

      hooks    les `on_update` (scène, posés, pool)
      physics  composition, blocage, tuiles, collisions, Sfx par bouton, interaction
      late     les `on_late_update`, la caméra, le défilement et l'animation des fonds
      render   l'animation et l'écriture OAM des posés et du pool, puis l'interface

    Chaque phase peut être placée seule en IWRAM (cf. `iwram_plan`) : le moteur est exécuté depuis la ROM, dont
    chaque accès coûte des états d'attente, et le code chaud va plus vite dans la mémoire interne. Les phases ne
    se passent rien par des locales : `_oamn` et `_affn` naissent et meurent dans `render`."""
    from codegen.runtime_codegen.input_layout import compute_input_layout as _cil
    if input_layout is None:
        input_layout = _cil(p)
    sym = c_sym(scene.name)
    _lay = scene_oam_layout(p, scene)
    _dsym = dispatch_sym(scene, scene_actors, pi)
    # Les instances posées d'un modèle sont des acteurs de la scène, appelés par leur indice avec le code du
    # modèle (`_dsym`) ; celles qui naissent vivent dans le pool partagé, parcouru par modèle.
    phases: dict[str, list[str]] = {name: [] for name in TICK_PHASES}
    L = phases["hooks"]
    L += shared_pool_gen.trim_lines(pi)
    # Les matrices affines : celles des acteurs posés sont fixes, au début ; les instances nées prennent les suivantes, à la
    # frame, quand elles sont dessinées (cf. `gen_affine.affine_oam_lines_dynamic`).
    _born_affine = any((lambda sc: bool(sc and sc.affine_transform))(affine_sprite_component(m["prefab"]))
                       for m in pi if m["shared"])

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
            s = _dsym(scene.name, actor.name)
            if _def(s, "on_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_update(&g_actors[{j}]);")

    # Le pool partagé : une boucle sur les emplacements utilisés, le modèle de chacun choisit son code.
    L += shared_pool_gen.hook_lines(pi, "on_update", _def)

    # Hiérarchie : APRÈS les scripts — un `on_update` peut avoir déplacé le
    # parent, et l'enfant doit suivre DANS la même frame — et AVANT la
    # collision et l'émission OAM, qui lisent la position monde recomposée.
    L = phases["physics"]
    L += parent_compose_lines(scene_actors, actor_offset, _lay.placed_entry)
    L += pool_compose_lines(pi)

    # Blocage entre acteurs : un mobile est repoussé hors des boîtes `blocks_actors`, AVANT la carte de
    # collision (les murs ont le dernier mot).
    L += block_tick_lines(p, scene, scene_actors, actor_offset, pi, shown)

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
            s = _dsym(scene.name, actor.name)
            cb = f"{s}_on_tile_collide" if (idx in lua_idx and _def(s, "on_tile_collide")) else "NULL"
            L.append(f"    if(g_actors[{idx}].active) resolve_actor_tiles(&g_actors[{idx}], {cb});")

        L += shared_pool_gen.tile_lines(pi, _def, has_solid_box)

    # Pool→scene collisions
    col_scene = [
        (actor_offset + j, scene_actors[j][0])
        for j in range(len(scene_actors))
        if any(hasattr(c, "w") for c in scene_actors[j][0].components)
    ]
    _sh = next((m for m in shared_pool_gen.shared_models(pi)), None)
    if _sh and col_scene:
        L += shared_pool_gen.collision_lines(
            pi, _sh["spool"]["end"] - _sh["spool"]["start"], col_scene,
            lambda pf, a: actors_can_collide(p, pf, a), _def, has_col_event, _dsym, lua_idx,
            scene.name, box_contact_lines)

    # AABB collisions scène
    if col_pairs:
        L.append(f"    static u16 _col_prev[{len(col_pairs)}]={{0}};")
        for pair_idx, (i, j) in enumerate(col_pairs):
            i_lua = i in lua_idx; j_lua = j in lua_idx
            si = _dsym(scene.name, scene_actors[i - actor_offset][0].name)
            sj = _dsym(scene.name, scene_actors[j - actor_offset][0].name)
            evs = ("on_collision_enter", "on_collide", "on_collision_exit")
            L += box_contact_lines(
                f"&g_actors[{i}]", f"&g_actors[{j}]",
                f"g_actors[{i}].active&&g_actors[{j}].active", f"_col_prev[{pair_idx}]",
                [(ev, f"{si}_{ev}") for ev in evs if i_lua and _def(si, ev)],
                [(ev, f"{sj}_{ev}") for ev in evs if j_lua and _def(sj, ev)],
                "    ")

    # Déclencheurs SoundFx par nom d'input (2026-09-27) : les events de script
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
        sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, actor)
        if sfx_sym and sfx_trig not in ("manual", "on_spawn", "on_destroy"):
            sfx_by_trigger.setdefault(sfx_trig, []).append(("actor", j, sfx_sym, sfx_vol))
    for p2 in pi:
        sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, p2["prefab"])
        if sfx_sym and sfx_trig not in ("manual", "on_spawn", "on_destroy"):
            if p2["shared"]:
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
                L += shared_pool_gen.sfx_lines(ref, sfx_sym, sfx_vol)
        L.append("    }")

    # Interactive : le geste sur l'entrée `interact`, puis l'interacteur atteint le plus proche
    L += interact_tick_lines(p, scene, scene_actors, actor_offset, pi, lua_idx, _def,
                             _dsym, input_layout, shown,
                             lambda j: _lay.placed_entry[j])

    # on_late_update actors
    L = phases["late"]
    if lua_idx:
        for j in sorted(lua_idx):
            actor, _ = scene_actors[j - actor_offset]
            s = _dsym(scene.name, actor.name)
            if _def(s, "on_late_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_late_update(&g_actors[{j}]);")

    L += shared_pool_gen.hook_lines(pi, "on_late_update", _def)

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
    L = phases["render"]
    # Prochain emplacement OAM libre : après la bande d'interface. Les sprites d'acteurs le
    # consomment dans l'ordre d'écriture (posés, puis pools), seuls ceux à l'écran en prennent un.
    L.append(f"    int _oamn = {_lay.ui};")
    if _born_affine:
        L.append(f"    int _affn = {max((e['slot'] for e in (affine_info or {}).values()), default=-1) + 1};")
    for j, (actor, _shown_sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        variants = anim_variants(p, actor, scene_actor_sym(scene.name, actor.name))
        if any(v is not None for v in variants):
            L += anim_tick_variants(idx, _lay.placed_entry[j], variants)

    _aff = affine_info or {}

    # OAM actors scène
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        _e = _lay.placed_entry[j]   # entrée OAM de l'acteur (>= 0 dès qu'il a un sprite)
        if not actor.visible:
            continue
        apps = appearances(p, actor, sprite_offsets)
        if apps:
            # UI en sprite : x/y SONT déjà des pixels d'écran, la caméra ne les
            # touche pas. Décidé ici, au build — un acteur de monde émet
            # exactement le C qu'il émettait avant (cf. Actor.screen_space).
            L += oam_write_lines(
                idx, _e, apps, aff=_aff.get(idx),
                screen_space=bool(getattr(actor, "screen_space", False)))

    # Les instances NÉES du pool partagé animent leur sprite comme les posées (sans ce tick, un projectile spawné
    # restait figé sur sa première frame), puis l'écrivent en OAM : une boucle, le tick et les constantes de sprite
    # de chaque modèle dans son cas. APRÈS les posés, dont les entrées OAM précèdent celles du pool ; un emplacement
    # mort n'est pas parcouru.
    L += shared_pool_gen.anim_oam_lines(
        pi, lambda owner, sym: anim_variants(p, owner, sym), anim_tick_variants,
        lambda owner: appearances(p, owner, sprite_offsets), oam_write_lines,
        lambda m, owner: pool_affine(p, m["prefab"], owner))

    # Après les scripts, avant le flush OAM : une lecture démarrée pendant le
    # tick avance dès cette frame, et les sprites des glyphes animés sont posés
    # avant d'être copiés en OAM.
    # La navigation AVANT le rendu d'UI : le script a déjà tourné, il a pu
    # poser le nombre d'items ; l'index bouge donc dans la même frame que
    # l'appui, et les rangées se dessinent ensuite avec le bon curseur.
    L += [
        "    oam_hide_from(_oamn);",
        # Des sprites visibles sans place : dit au log debug (retiré en release), une fois par seconde.
        "    if(g_oam_dropped){",
        "        if((_g_frame & 63)==0){",
        '            debug_write_str("warning: ");',
        "            debug_write_int(g_oam_dropped);",
        '            debug_write_str(" sprite(s) not drawn, the OAM is full");',
        "            debug_flush();",
        "        }",
        "        g_oam_dropped = 0;",
        "    }",
        *([
            # Des instances affines sans matrice (les 32 sont prises) : dessinées SANS rotation ni échelle.
            "    if(g_affine_dropped){",
            "        if((_g_frame & 63)==0){",
            '            debug_write_str("warning: ");',
            "            debug_write_int(g_affine_dropped);",
            '            debug_write_str(" sprite(s) drawn without rotation or scale, the 32 affine matrices are taken");',
            "            debug_flush();",
            "        }",
            "        g_affine_dropped = 0;",
            "    }",
        ] if _born_affine else []),
    ]
    L.append("    ui_list_tick();")
    L.append("    ui_image_update();")
    L.append("    text_update();")
    L.append("    oam_update();")
    out: list[str] = iwram_macros(sym, phases)
    for name in TICK_PHASES:
        out += [f"BS_ATTR_{sym}_{name} static void scene_tick_{sym}_{name}(void) {{", *phases[name], "}", ""]
    out += [f"static void scene_tick_{sym}(void) {{",
            *[f"    scene_tick_{sym}_{name}();" for name in TICK_PHASES], "}", ""]
    return out
