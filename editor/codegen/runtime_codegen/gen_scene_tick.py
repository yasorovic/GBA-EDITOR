"""runtime_codegen/gen_scene_tick.py : le `scene_tick_<scène>` : les quatre phases du tick d'une scène (hooks, physique,
late, rendu) et le répartiteur qui les appelle.

Les phases sont celles d'`iwram_plan.TICK_PHASES` ; chacune peut être placée en IWRAM par le build."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.iwram_plan import TICK_PHASES
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen import shared_pool_gen
from codegen.runtime_codegen.physics.blocks import block_tick_lines
from codegen.runtime_codegen.gen_camera import camera_follow_lines
from codegen.runtime_codegen.gen_actor_hierarchy import link_depth
from codegen.runtime_codegen.gen_pool import dispatch_sym
from codegen.runtime_codegen.gen_scene_query import (
    scene_anim_descriptors, scene_has_cmap,
)
from codegen.runtime_codegen.gen_sprite import anim_oam_pass_lines, resolve_initial_appearance
from codegen.runtime_codegen.interact_gen import interact_tick_lines
from codegen.runtime_codegen.model_desc import hook_pass_lines, model_desc_lines, sfx_input_pass_lines
from codegen.runtime_codegen.physics.areas import area_contact_lines, area_parent_lines, area_update_lines
from codegen.runtime_codegen.physics.audio_emitters import emitter_tick_lines
from codegen.runtime_codegen.physics.contacts import contact_tick_lines
from codegen.runtime_codegen.physics.body import project_has_one_way, project_sets_gravity
from codegen.runtime_codegen.physics.character import physics_tile_lines
from codegen.runtime_codegen.physics.impulses import impulse_tick_lines
from codegen.runtime_codegen.physics.kinematic import kinematic_tick_parts
from codegen.runtime_codegen.physics.motion import physics_motion_lines, physics_sleep_lines
from codegen.runtime_codegen.physics.floor import floor_tick_lines
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
    def _def(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    # Le code Lua de chaque posé : celui de son modèle pour une instance liée (`_dsym`), None sans script.
    placed_scripts = [_dsym(scene.name, actor.name) if actor_offset + j in lua_idx else None
                      for j, (actor, _sprite) in enumerate(scene_actors)]
    # Le symbole du code de chaque posé, script ou non : les événements de frame de son sprite l'appellent.
    placed_syms = [_dsym(scene.name, actor.name) for actor, _sprite in scene_actors]

    # on_update scène
    if getattr(scene, "script", ""):
        L += [f"    {sym}_scene_on_update();"]

    # on_update des acteurs, posés puis nés : le crochet se lit au descripteur de modèle.
    L += hook_pass_lines(scene, pi, placed_scripts, _def, "on_update")
    # on_update des scripts d'Area, après ceux des acteurs.
    L += area_update_lines(p, scene, _def)

    # Hiérarchie : APRÈS les scripts — un `on_update` peut avoir déplacé le
    # parent, et l'enfant doit suivre DANS la même frame — et AVANT la
    # collision et l'émission OAM, qui lisent la position monde recomposée.
    L = phases["physics"]
    kinematic_before, kinematic_after, kinematic_crush = kinematic_tick_parts(
        p, scene_actors, scene, pi, resolve_initial_appearance)
    L += kinematic_before
    L += physics_motion_lines(scene, p.settings, scene_actors, pi, project_sets_gravity(p), _lay)
    if link_depth(scene_actors, pi):
        L.append("    slot_compose_all();   /* actor hierarchy, posed and spawned: parents before children */")
    L += area_parent_lines(scene, scene_actors, actor_offset)
    L += emitter_tick_lines(p, scene)

    # Blocage entre acteurs : un mobile est repoussé hors des boîtes de réponse `block`, AVANT la carte de
    # collision (les murs ont le dernier mot).
    L += block_tick_lines(p, scene, scene_actors, pi, resolve_initial_appearance)

    # Le trajet final de la plateforme doit être connu avant de transporter ce qui repose dessus.
    # La carte et les Static peuvent avoir raccourci le mouvement demandé.
    has_cmap = scene_has_cmap(scene)
    if has_cmap:
        L += physics_tile_lines(scene, scene_actors, pi, kinematic=True)

    L += kinematic_after
    L += kinematic_crush
    L += impulse_tick_lines(p, scene, scene_actors, pi, resolve_initial_appearance)

    # Résolution contre la carte de collision — pour TOUTE box solide, et non
    # plus seulement pour les acteurs qui définissent `on_tile_collide` : la
    # résolution DÉPLACE l'acteur, le hook ne fait que prévenir. C'est aussi ce
    # que le modèle promet depuis toujours (« solid=True → résolution physique »).
    # Rien n'est émis si la scène n'a pas de carte : il n'y aurait rien à heurter.
    if has_cmap:
        L += physics_tile_lines(scene, scene_actors, pi, kinematic=False, carry=bool(kinematic_after))

    L += floor_tick_lines(p, scene_actors, scene, pi, resolve_initial_appearance)

    # `physics_body:drop_through(n)` : un compteur par emplacement, lu par les faces à sens unique de cette phase
    # puis décompté ici, après elles : appelé pendant `on_update`, il compte donc cette frame-ci.
    if project_has_one_way(p):
        L.append("    if(g_drop_live){ g_drop_live=0; for(int _d=0;_d<G_ACTOR_COUNT;_d++) "
                 "if(g_drop_through[_d]&&--g_drop_through[_d]) g_drop_live=1; }")

    L += physics_sleep_lines(scene, p.settings, scene_actors, pi)

    # Contacts entre acteurs, posés ou nés : les crochets se lisent au descripteur de modèle.
    L += contact_tick_lines(p, scene, scene_actors, pi, resolve_initial_appearance, placed_scripts, _def)

    # Areas à déclencheur : chaque emplacement actif dont le type répond à une Area, posé ou né, par le même pas.
    L += area_contact_lines(p, scene, scene_actors, pi, placed_scripts, _def)

    # Déclencheurs SoundFx par nom d'input : un SoundFxComponent répond à un bouton sans script (cf. `model_desc`).
    L += sfx_input_pass_lines(p, scene, scene_actors, pi, input_layout)

    # Interactive : le geste sur l'entrée `interact`, puis l'interacteur atteint le plus proche
    L += interact_tick_lines(p, scene, scene_actors, pi, placed_scripts, _def, input_layout, resolve_initial_appearance)

    # on_late_update des acteurs, posés puis nés
    L = phases["late"]
    L += hook_pass_lines(scene, pi, placed_scripts, _def, "on_late_update")

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
    # L'animation et l'écriture OAM : une boucle sur les emplacements, posés puis nés, le code du type de chacun.
    L += anim_oam_pass_lines(p, scene_actors, actor_offset, pi, _lay, placed_syms, set(affine_info or {}),
                             sprite_offsets)

    # Après les scripts, avant le flush OAM : une lecture démarrée pendant le tick avance dès cette frame, et les
    # sprites des glyphes animés sont posés avant d'être copiés en OAM. La navigation vient AVANT le rendu d'UI : le
    # script a déjà tourné, l'index bouge dans la même frame que l'appui. Cette fin est la même pour toutes les
    # scènes : `scene_render_end` (cf. `gen_globals`) la porte en un seul exemplaire.
    L.append("    scene_render_end(_oamn);")
    # Le descripteur de modèle, lu par les passes migrées (mouvement, sommeil, carte, crochets, SoundFx, interaction) :
    # défini avant les phases.
    out: list[str] = (model_desc_lines(p, scene, scene_actors, pi, placed_scripts, _def, input_layout)
                      + iwram_macros(sym, phases))
    for name in TICK_PHASES:
        out += [f"BS_ATTR_{sym}_{name} static void scene_tick_{sym}_{name}(void) {{", *phases[name], "}", ""]
    out += [f"static void scene_tick_{sym}(void) {{",
            *[f"    scene_tick_{sym}_{name}();" for name in TICK_PHASES], "}", ""]
    return out
