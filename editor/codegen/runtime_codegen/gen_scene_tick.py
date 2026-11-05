"""runtime_codegen/gen_scene_tick.py — le `scene_tick_<scène>` : les quatre phases du tick d'une scène (hooks, physique,
late, rendu) et le répartiteur qui les appelle.

Les phases sont celles d'`iwram_plan.TICK_PHASES` ; chacune peut être placée en IWRAM par le build."""
from __future__ import annotations

from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.iwram_plan import TICK_PHASES
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen import shared_pool_gen
from codegen.runtime_codegen.physics.blocks import block_tick_lines
from codegen.runtime_codegen.gen_affine import pool_affine
from codegen.runtime_codegen.gen_camera import camera_follow_lines
from codegen.runtime_codegen.gen_pool import dispatch_sym, parent_compose_lines, pool_compose_lines
from codegen.runtime_codegen.gen_scene_query import (
    actors_can_collide, collision_pair_mask, has_col_event, scene_anim_descriptors, scene_has_cmap,
)
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.gen_sprite import (
    anim_tick_variants, anim_variants, appearances, oam_write_lines, shown,
)
from codegen.runtime_codegen.interact_gen import interact_tick_lines
from codegen.runtime_codegen.physics.areas import area_mask, area_pair_lines, area_parent_lines, trigger_areas
from codegen.runtime_codegen.physics.contacts import box_contact_lines
from scripting.api import AREA_EVENTS
from codegen.runtime_codegen.physics.body import (
    physics_body_mode, physics_collider_mask, project_has_one_way, project_sets_gravity, uses_character_solver,
)
from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
from codegen.runtime_codegen.physics.kinematic import kinematic_crush_pairs, kinematic_tick_parts, pool_carried_models
from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
from codegen.runtime_codegen.physics.floor import floor_tick_lines
from core.models.components import PHYSICS_BODY_CHARACTER, PHYSICS_BODY_KINEMATIC, affine_sprite_component
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
    kinematic_before, kinematic_after, kinematic_deltas = kinematic_tick_parts(
        p, scene_actors, actor_offset, scene, pi, shown)
    L += kinematic_before
    L += physics_motion_lines(scene, p.settings, scene_actors, actor_offset, pi, project_sets_gravity(p))
    L += parent_compose_lines(scene_actors, actor_offset, _lay.placed_entry)
    L += pool_compose_lines(pi)
    L += area_parent_lines(scene, scene_actors, actor_offset)

    # Blocage entre acteurs : un mobile est repoussé hors des boîtes de réponse `block`, AVANT la carte de
    # collision (les murs ont le dernier mot).
    L += block_tick_lines(p, scene, scene_actors, actor_offset, pi, shown)

    # Le trajet final de la plateforme doit être connu avant de transporter ce qui repose dessus.
    # La carte et les Static peuvent avoir raccourci le mouvement demandé.
    if scene_has_cmap(scene):
        for j, (actor, _sprite) in enumerate(scene_actors):
            if physics_body_mode(actor) != PHYSICS_BODY_KINEMATIC:
                continue
            idx = actor_offset + j
            s = _dsym(scene.name, actor.name)
            cb = f"{s}_on_tile_collide" if (idx in lua_idx and _def(s, "on_tile_collide")) else "NULL"
            mask = physics_collider_mask(actor, _sprite, map_only=True)
            if mask:
                L.append(f"    if(g_actors[{idx}].active) resolve_actor_tiles(&g_actors[{idx}], {mask}, {cb});")

    L += kinematic_after
    crush_pairs = kinematic_crush_pairs(p, scene_actors, actor_offset)
    crush_handlers = {}
    for idx in kinematic_deltas:
        actor, _sprite = scene_actors[idx - actor_offset]
        s = _dsym(scene.name, actor.name)
        if (physics_body_mode(actor) != PHYSICS_BODY_CHARACTER
                or not (idx in lua_idx and _def(s, "on_crushed"))):
            continue
        L.append(f"    u8 _kin_crushed_{idx}=0;")
        crush_handlers[idx] = s
    for idx, pairs in crush_pairs.items():
        if idx not in crush_handlers:
            continue
        dx, dy = kinematic_deltas[idx]
        s = crush_handlers[idx]
        for cb, si, sb in pairs:
            L += [f"    if(!_kin_crushed_{idx}&&({dx}||{dy})&&g_actors[{idx}].active&&g_actors[{si}].active",
                  f"       &&g_actors[{idx}].collision.boxes[{cb}].active&&g_actors[{si}].collision.boxes[{sb}].active",
                  f"       &&box_overlap(g_actors[{idx}].x>>8,g_actors[{idx}].y>>8,&g_actors[{idx}].collision.boxes[{cb}],",
                  f"                      g_actors[{si}].x>>8,g_actors[{si}].y>>8,&g_actors[{si}].collision.boxes[{sb}])){{",
                  f"        {s}_on_crushed(&g_actors[{idx}],&g_actors[{si}]); _kin_crushed_{idx}=1;",
                  "    }"]
    L += impulse_tick_lines(p, scene, scene_actors, actor_offset, pi, shown)

    # Résolution contre la carte de collision — pour TOUTE box solide, et non
    # plus seulement pour les acteurs qui définissent `on_tile_collide` : la
    # résolution DÉPLACE l'acteur, le hook ne fait que prévenir. C'est aussi ce
    # que le modèle promet depuis toujours (« solid=True → résolution physique »).
    # Rien n'est émis si la scène n'a pas de carte : il n'y aurait rien à heurter.
    if scene_has_cmap(scene):
        for j in range(len(scene_actors)):
            actor, sprite = scene_actors[j]
            if not uses_character_solver(actor, sprite):
                continue
            mask = physics_collider_mask(actor, sprite, map_only=True)
            if physics_body_mode(actor) == PHYSICS_BODY_KINEMATIC:
                continue
            idx = actor_offset + j
            s = _dsym(scene.name, actor.name)
            cb = f"{s}_on_tile_collide" if (idx in lua_idx and _def(s, "on_tile_collide")) else "NULL"
            if idx not in kinematic_deltas:
                L.append(f"    if(g_actors[{idx}].active) resolve_actor_tiles(&g_actors[{idx}], {mask}, {cb});")
                continue
            dx, dy = kinematic_deltas[idx]
            crushed = idx in crush_handlers
            L += [
                f"    if(g_actors[{idx}].active){{",
                f"        int _kin_ovx=g_actors[{idx}].vx,_kin_ovy=g_actors[{idx}].vy;",
                f"        int _kin_ivx=_kin_ovx+{dx},_kin_ivy=_kin_ovy+{dy};",
                f"        g_actors[{idx}].vx=_kin_ivx; g_actors[{idx}].vy=_kin_ivy;",
                f"        resolve_actor_tiles(&g_actors[{idx}], {mask}, {cb});",
                *([f"        if(!_kin_crushed_{idx}&&(({dx}&&!g_actors[{idx}].vx)||({dy}&&!g_actors[{idx}].vy))) "
                   f"{s}_on_crushed(&g_actors[{idx}],0);"] if crushed else []),
                f"        g_actors[{idx}].vx=(_kin_ivx&&!g_actors[{idx}].vx)?0:_kin_ovx;",
                f"        g_actors[{idx}].vy=(_kin_ivy&&!g_actors[{idx}].vy)?0:_kin_ovy;",
                "    }",
            ]

        L += shared_pool_gen.tile_lines(
            pi, _def, lambda owner: (physics_collider_mask(owner, map_only=True)
                                     if uses_character_solver(owner) else 0),
            pool_carried_models(p, scene_actors, actor_offset, pi, shown))

    L += floor_tick_lines(p, scene_actors, actor_offset, scene, pi, shown)

    # `physics_body:drop_through(n)` : un compteur par emplacement, lu par les faces à sens unique de cette phase
    # puis décompté ici, après elles : appelé pendant `on_update`, il compte donc cette frame-ci.
    if project_has_one_way(p):
        L.append("    if(g_drop_live){ g_drop_live=0; for(int _d=0;_d<G_ACTOR_COUNT;_d++) "
                 "if(g_drop_through[_d]&&--g_drop_through[_d]) g_drop_live=1; }")

    L += physics_sleep_lines(scene, p.settings, scene_actors, actor_offset, pi)

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
            scene.name, box_contact_lines,
            lambda pf, a: collision_pair_mask(pf, a, p.settings))

    # AABB collisions scène
    # Une table de paires et une boucle : le code des contacts (`contact_pair_run`) n'est pas recopié par paire.
    if col_pairs:
        evs = ("on_collision_enter", "on_collide", "on_collision_exit")

        def handlers(k: int) -> str:
            s = _dsym(scene.name, scene_actors[k - actor_offset][0].name)
            return "{" + ",".join(f"{s}_{ev}" if k in lua_idx and _def(s, ev) else "0" for ev in evs) + "}"

        # Une paire dont aucun côté n'a de handler ne produit rien (et `g_col_prev` n'est lu que par `contact_pair_run`) : elle
        # n'entre pas dans la table. La mémoire des contacts est une globale que chaque `scene_init` remet à zéro : un `static`
        # d'ici survivait à une sortie de scène, et le retour y voyait des `collide` ou des `exit` sans `enter`.
        rows = [(i, j, collision_pair_mask(scene_actors[i - actor_offset][0],
                                            scene_actors[j - actor_offset][0], p.settings),
                 handlers(i), handlers(j)) for i, j in col_pairs]
        rows = [r for r in rows if r[3] != "{0,0,0}" or r[4] != "{0,0,0}"]
        if rows:
            L.append(f"    static const ContactPair _col_pairs[{len(rows)}]={{")
            L += [f"        {{{i},{j},{allowed},{a},{b}}}," for i, j, allowed, a, b in rows]
            L += ["    };",
                  f"    for(u16 _k=0;_k<{len(rows)};_k++) contact_pair_run(&_col_pairs[_k],&g_col_prev[_k]);"]

    # Areas à déclencheur : les acteurs posés (table de couples) puis ceux du pool (boucle sur les emplacements), le même
    # `area_contact_step` des deux côtés.
    _areas = trigger_areas(scene)
    if _areas:
        L += area_pair_lines(p, scene, scene_actors, actor_offset, lua_idx, _def, _dsym, _areas)
        if _sh:
            L += shared_pool_gen.area_lines(
                pi, _sh["spool"]["end"] - _sh["spool"]["start"], _areas,
                lambda pf, area: area_mask(area, pf, p.settings), _def, AREA_EVENTS)

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

    # Après les scripts, avant le flush OAM : une lecture démarrée pendant le tick avance dès cette frame, et les
    # sprites des glyphes animés sont posés avant d'être copiés en OAM. La navigation vient AVANT le rendu d'UI : le
    # script a déjà tourné, l'index bouge dans la même frame que l'appui. Cette fin est la même pour toutes les
    # scènes : `scene_render_end` (cf. `gen_globals`) la porte en un seul exemplaire.
    L.append("    scene_render_end(_oamn);")
    out: list[str] = iwram_macros(sym, phases)
    for name in TICK_PHASES:
        out += [f"BS_ATTR_{sym}_{name} static void scene_tick_{sym}_{name}(void) {{", *phases[name], "}", ""]
    out += [f"static void scene_tick_{sym}(void) {{",
            *[f"    scene_tick_{sym}_{name}();" for name in TICK_PHASES], "}", ""]
    return out
