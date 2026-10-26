"""runtime_codegen/gen_scene_init.py — le `scene_init_<scène>` : tout ce qu'une scène pose à son activation.

Une section par fonction, dans l'ordre où le C est émis : l'ordre compte (les registres d'affichage après le
texte, les windows après DISPCNT, les `on_start` en dernier). Le texte et l'interface vivent dans `gen_ui_scene`,
les registres d'affichage dans `gen_scene_display`."""
from __future__ import annotations

from codegen.actor_appearance import owner_appearances
from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.palette_alloc import scene_bank_layout
from codegen.runtime_codegen.gen_appearance import (
    appearance_init_lines, appearance_layout, appearance_table_lines,
)
from codegen.runtime_codegen.gen_camera import scene_camera_index
from codegen.runtime_codegen.gen_palette import resolve_backdrop_color
from codegen.runtime_codegen.gen_pool import dispatch_sym, placed_parent_table
from codegen.runtime_codegen.gen_scene_display import scene_display_lines
from codegen.runtime_codegen.gen_scene_query import scene_anim_descriptors, scene_has_cmap, scene_world_size
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.gen_sprite import initial_state_rank, shown
from codegen.runtime_codegen.gen_ui_scene import scene_ui_lines
from codegen.runtime_codegen.gen_vram_layout import layer_base_bank
from codegen.runtime_codegen.interact_gen import owner_boxes
from codegen.runtime_codegen.sound_emit import scene_music_lines
from core.models.field_value import (
    FieldValue as _FV, number_c as _number_c, var_names_from_project as _var_names,
)
from core.models.palette import OWN_PAL_BANK
from core.models.scene import Scene
from core.project import Project


def gen_scene_init(
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
    obj_layout = scene_bank_layout(p, scene, "obj")
    bg_layout  = scene_bank_layout(p, scene, "bg")
    # Constantes d'activation des apparences de la scène (marche 3c) : la table est
    # ROM, avant la fonction ; le pointeur est repointé par scene_init.
    alay = appearance_layout(p, scene_actors, pi, obj_layout)
    # Fonds animés posés sur les calques : un descripteur par placement, avec son
    # propre compteur — c'est ce qui permet à deux copies du même animé d'être à
    # des moments différents de leur boucle (mode `instance`).
    anims = [a for a in scene_anim_descriptors(p, scene, bgi) if not a["shared"]]
    tanims = [a for a in scene_anim_descriptors(p, scene, bgi) if a["shared"]]
    L: list[str] = []
    L += appearance_table_lines(sym, alay)
    L += _image_data_lines(scene, sym)
    L += _bg_anim_data_lines(sym, anims, tanims)
    if L:
        L.append("")
    L.append(f"static void scene_init_{sym}(void) {{")
    L += _reset_lines(p, scene, sym, scene_actors, actor_offset, alay)
    cam_idx = scene_camera_index(p, scene)
    L += _scene_state_lines(scene, sym, cam_idx)
    L += _background_lines(p, scene, sym, bgi, scene_actors, sprite_offsets, obj_layout, bg_layout, anims, tanims)
    L += scene_ui_lines(p, scene, sym, sprite_offsets, obj_text_oam, obj_text_tile, emit)
    L += scene_display_lines(p, scene, dispcnt, cam_idx, emit)
    L += _placed_actor_lines(p, scene, scene_actors, actor_offset, obj_layout, alay, affine_info)
    L += _shared_pool_lines(pi)
    L += _start_lines(p, scene, sym, scene_actors, actor_offset, lua_idx, pi, has_sound, sound_assets,
                      actor_defined_events)
    L.append("}")
    L.append("")
    return L


def _image_data_lines(scene, sym: str) -> list[str]:
    """Données des fonds IMAGE, en amont de la fonction : tuiles de l'asset source et carte de screen entries."""
    L: list[str] = []
    # ── Données des fonds IMAGE, en amont de la fonction ───────────
    # Les tuiles de l'asset source et la carte de screen entries de chaque
    # conteneur sont des CONSTANTES : calculées par l'éditeur (cf.
    # `scene_image_fills`), elles n'ont aucune raison d'être reconstruites au
    # runtime. `scene_init` ne fait plus qu'une copie et une écriture de map.
    for _a in (getattr(scene, "_ui_img_assets", []) or []):
        _w = _a["words"]
        L.append(f"static const unsigned int {sym}_{_a['sym']}[] = {{   /* background "
                 f"'{_a['name']}': {_a['tiles']} tiles */")
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
    return L


def _bg_anim_data_lines(sym: str, anims: list[dict], tanims: list[dict]) -> list[str]:
    """Un descripteur par fond animé posé, avec son propre compteur."""
    L: list[str] = []
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
    return L


def _reset_lines(p, scene, sym: str, scene_actors: list, actor_offset: int, alay) -> list[str]:
    """Taille du monde, acteurs posés, remise à zéro des acteurs, des entrées OAM et des tables de la scène précédente."""
    L: list[str] = []
    # Taille du monde (canvas) — lue par scene.size.w/.h côté script. Posée à
    # chaque activation, une scène peut donc faire avancer son monde.
    # Taille du monde (canvas) — lue par scene.size.w/.h côté script. Posée à
    # chaque activation, une scène peut donc faire avancer son monde.
    _sw, _sh = scene_world_size(p, scene)
    L.append(f"    g_scene_w = {_sw}; g_scene_h = {_sh};")
    L.append(f"    g_scene_scroll_h = {int(bool(scene.scroll_h))}; g_scene_scroll_v = {int(bool(scene.scroll_v))};")
    L.append(f"    g_scene_collision_layer = {int(scene.collision_layer)};")
    # Acteurs POSÉS de cette scène, dans l'ordre d'authoring — la borne de
    # `actor:get(i)`/`actor:count()`. Les slots [0, placed) tiennent exactement ces
    # acteurs ; les pools spawnés vivent après et ne sont pas comptés ici.
    L.append(f"    g_scene_placed = {len(scene_actors)};")
    # La hiérarchie des acteurs posés, lue par `a.parent` / `a.root` (runtime_api_inline.h).
    _ppar = placed_parent_table(scene_actors, actor_offset)
    if _ppar:
        L.append(f"    {{ static const s16 _ppar[{len(_ppar)}] = {{{','.join(map(str, _ppar))}}}; g_placed_parent = _ppar; }}")
    else:
        L.append("    g_placed_parent = 0;")
    # Tout acteur repart SANS entrée OAM (-1) ; le lien est posé plus bas, pour les
    # seuls acteurs qui affichent un sprite (posés ci-dessous, pools à leur init).
    # La génération survit à la remise à zéro et avance : une référence rangée par la scène
    # précédente ne résout dans aucun emplacement de celle-ci.
    L.append("    for(int _i=0; _i<G_ACTOR_COUNT; _i++) { u16 _g=g_actors[_i].gen; g_actors[_i]=(Actor){0}; "
             "g_actors[_i].gen=_g+1; g_actors[_i].oam_entry=-1; g_actors[_i].inst=_i; }")
    L.append("    for(int _i=0; _i<(G_ACTOR_COUNT+31)/32; _i++) g_alive_bits[_i]=0;")
    L.append("    g_alive_epoch++;")
    L.append("    for(int _i=0; _i<G_OAM_ENTRY_COUNT; _i++) g_oam_entries[_i]=(OamEntry){0};")
    if alay.rows:
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
    # plus rien à voir avec elle (cf. `gen_scene_init`, plus bas, pour les
    # `text_set_region_backdrop` qui la repeuplent).
    L.append("    text_clear_region_fills();")
    L.append("    text_clear_region_surfs();")
    # Visibilité des éléments d'interface : table PROJET-GLOBALE elle aussi,
    # même raison que `text_read_reset_all` juste au-dessus — reposer les bits
    # AUTHORÉS de départ à chaque scène, sinon un élément caché par un script
    # dans la scène précédente resterait caché ici.
    L.append("    ui_elements_reset();")
    return L


def _scene_state_lines(scene, sym: str, cam_idx: int) -> list[str]:
    """Caméra de départ, tables SFX on_destroy et carte de collision de la scène."""
    L: list[str] = []
    # Caméra de démarrage. L'activation pose cadrage ET bornes, et rejoue le
    # on_start de la caméra : une scène n'hérite donc jamais du cadrage de la
    # précédente, et un script peut basculer ailleurs ensuite (camera.switch).
    # Le WIN0 qu'elle pose ici (cf. camera_switch()) sera effacé par
    # dispcnt_set() plus bas et reposé après — voir ce commentaire-là.
    _cam_name = getattr(scene, "camera", "") or "(default)"
    L.append(f"    camera_switch({cam_idx});   /* {_cam_name} */")
    # SFX on_destroy : pointe les tables de CETTE scène (per-scène depuis T3,
    # cf. `sfx_on_destroy_table`). `actor_destroy_with_sfx` lit ces pointeurs.
    L.append(f"    g_sfx_on_destroy_id  = g_sfx_on_destroy_id_{sym};")
    L.append(f"    g_sfx_on_destroy_vol = g_sfx_on_destroy_vol_{sym};")
    # Cmap dispatch
    if scene_has_cmap(scene):
        L.append(f"    g_active_cmap = g_cmap_{sym};")
        L.append(f"    g_cmap_w = CMAP_W_{sym.upper()};")
        L.append(f"    g_cmap_h = CMAP_H_{sym.upper()};")
    else:
        L.append("    g_active_cmap = NULL; g_cmap_w = 0; g_cmap_h = 0;")
    return L


def _background_lines(p, scene, sym: str, bgi: list[dict], scene_actors: list, sprite_offsets: dict,
                      obj_layout, bg_layout, anims: list[dict], tanims: list[dict]) -> list[str]:
    """Les fonds (tuiles, cartes, registres BGxCNT), les tuiles OBJ en VRAM, les palettes et le backdrop."""
    L: list[str] = []
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
            L.append(f"    layer_set_pal_bank({bg}, {layer_base_bank(p, scene, bi, bg_layout)});")
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
    return L


def _placed_actor_lines(p, scene, scene_actors: list, actor_offset: int, obj_layout, alay,
                        affine_info: dict | None) -> list[str]:
    """L'état de départ de chaque acteur posé, puis ses déclencheurs Sfx `on_spawn`."""
    L: list[str] = []
    _lay = scene_oam_layout(p, scene)
    # Init actors
    # Les acteurs posés qui sont des instances d'un modèle : leur rang dans le modèle (l'indice de leur
    # état de script). Les membres sont les premières instances ; la réserve du spawn suit.
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        _e = _lay.placed_entry[j]   # son entrée OAM, -1 = sans sprite : rien à afficher
        s = scene_actor_sym(scene.name, actor.name)
        boxes = owner_boxes(actor, sprite)
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(actor, "pal_bank", OWN_PAL_BANK), own)
        _lines = [
            # x/y en Q8 en interne, l'auteur place l'acteur en pixels.
            f"    g_actors[{idx}].x       = ({_FV.parse(actor.x, _var_names(p)).c_expr()})<<8;",
            f"    g_actors[{idx}].y       = ({_FV.parse(actor.y, _var_names(p)).c_expr()})<<8;",
            f"    g_actors[{idx}].active  = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].alive   = 1;",
            f"    g_oam_entries[{_e}].visible = {1 if actor.visible else 0};",
            f"    g_oam_entries[{_e}].flip_h  = {1 if actor.flip_h else 0};",
            f"    g_oam_entries[{_e}].flip_v  = {1 if actor.flip_v else 0};",
            f"    g_actors[{idx}].dir_x   = {getattr(actor,'dir_x',0)};",
            f"    g_actors[{idx}].dir_y   = {getattr(actor,'dir_y',0)};",
            f"    g_oam_entries[{_e}].pal_bank= {pal if pal is not None else 0};",
            f"    g_oam_entries[{_e}].obj_mode= {int(getattr(actor, 'obj_mode', 0)) & 3};",
            f"    g_oam_entries[{_e}].priority= {_number_c(getattr(actor, 'priority', 0), _var_names(p), mask=3)};",
            f"    g_oam_entries[{_e}].facing_auto= {1 if getattr(shown(p, actor)[0], 'facing_auto', True) else 0};",
            # Le regard de départ est la direction posée dans l'inspecteur.
            f"    g_actors[{idx}].facing_x= {getattr(actor,'dir_x',0)};",
            f"    g_actors[{idx}].facing_y= {getattr(actor,'dir_y',0)};",
            # L'état de départ choisi dans l'inspecteur (`initial_state`) : rang dans
            # les états du sprite AFFICHÉ, 0 si le nom n'existe plus.
            f"    g_oam_entries[{_e}].anim_state={initial_state_rank(*shown(p, actor))};",
            # self.frame_w/frame_h : posées une fois ici depuis le sprite,
            # jamais recalculées — un acteur sans sprite (rare, cf. `sprite`
            # potentiellement None plus haut) rend 0 des deux côtés.
            f"    g_oam_entries[{_e}].frame_w = {sprite.frame_w if sprite else 0};",
            f"    g_oam_entries[{_e}].frame_h = {sprite.frame_h if sprite else 0};",
            f"    g_actors[{idx}].name     = ACTOR_{s.upper()};",
            # Transform MONDE : émise pour TOUT acteur, affine ou non. Un acteur
            # non-affine ne l'AFFICHE pas (aucun slot de matrice), mais un enfant
            # en HÉRITE par la composition parent→enfant — un enfant hérite des
            # propriétés de son parent direct, puis les override. Sans ça, un
            # parent non-affine restait à scale 0 (le zéro-init) et écrasait la
            # position ET l'échelle affine de ses enfants (matrice dégénérée).
            # Défaut 256 = ×1 ; la branche affine ci-dessous ne rajoute que le
            # slot et la transform LOCALE du sprite.
            f"    g_actors[{idx}].rotation     = {_number_c(getattr(actor, 'rotation', 0), _var_names(p))};",
            f"    g_actors[{idx}].scale_x      = {_number_c(getattr(actor, 'scale_x', 1.0), _var_names(p), q8=True)};",
            f"    g_actors[{idx}].scale_y      = {_number_c(getattr(actor, 'scale_y', 1.0), _var_names(p), q8=True)};",
            f"    g_oam_entries[{_e}].screen_space = {1 if getattr(actor, 'screen_space', False) else 0};",
            f"    g_actors[{idx}].collision.box_count = {len(boxes)};",
        ]
        # Les lignes d'AFFICHAGE portent `g_oam_entries[-1]` quand l'acteur n'a pas
        # de sprite : on les écarte, et le lien reste à -1 (posé par le reset).
        L += [l for l in _lines if _e >= 0 or "g_oam_entries[-1]" not in l]
        if _e >= 0:
            L.append(f"    g_actors[{idx}].oam_entry = {_e};")
            L += appearance_init_lines(p, actor, str(_e), "    ", alay.actor_base.get(j))
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
                f"    g_oam_entries[{_e}].pivot_x      = {_aff_i['pivot_x']};",
                f"    g_oam_entries[{_e}].pivot_y      = {_aff_i['pivot_y']};",
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
    # scriptés ou non : c'est une donnée du component, pas du script. Émis ici plutôt que dans le on_start généré (ancien
    # comportement) pour qu'un actor sans ScriptComponent en bénéficie aussi.
    for j, (actor, _sprite) in enumerate(scene_actors):
        sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, actor)
        if sfx_sym and sfx_trig == "on_spawn":
            L.append(f"    sfx_play({sfx_sym}, {sfx_vol}, 0);"
                     f"   /* SoundFxComponent : {actor.name} */")
    return L


def _shared_pool_lines(pi: list[dict]) -> list[str]:
    """Le pool PARTAGÉ : sa fenêtre d'emplacements, ses modèles à parties, ses entrées d'état."""
    L: list[str] = []
    # Le pool PARTAGÉ : les emplacements que tout modèle qui naît prend. Posés ici, puisque les
    # globales survivent à la scène : une scène sans pool partagé le dit aussi (début = fin = 0).
    _spool = next((p2["spool"] for p2 in pi if p2.get("shared")), None)
    if _spool:
        L.append(f"    g_spool_start = {_spool['start']}; g_spool_end = {_spool['end']}; "
                 f"g_spool_hw = g_spool_free = {_spool['start']}; "
                 f"g_spool_entry = {_spool['entry_start'] if _spool['entries'] else -1};")
        # Les modèles à parties : taille du groupe (pour la racine) et rang de la partie, par type d'emplacement.
        _grouped = [m for m in pi if m.get("shared") and m["group"] > 1]
        if _grouped:
            _kinds = max(m["model_id"] + m["group"] for m in pi if m.get("shared"))
            _grp, _part, _par = [0] * _kinds, [0] * _kinds, [0] * _kinds
            for m in _grouped:
                _grp[m["model_id"]] = m["group"]
                _parts = list(getattr(m["prefab"], "children", []) or [])
                _rank = {pt.name: k for k, pt in enumerate(_parts, start=1)}
                for k, pt in enumerate(_parts, start=1):
                    _part[m["model_id"] + k] = k
                    # La partie parente : une autre partie nommée par `parent`, sinon la racine (rang 0).
                    _par[m["model_id"] + k] = _rank.get(getattr(pt, "parent", None) or "", 0)
            L.append(f"    {{ static const u8 _g[{_kinds}]={{{','.join(map(str, _grp))}}}; "
                     f"static const u8 _pt[{_kinds}]={{{','.join(map(str, _part))}}}; "
                     f"static const u8 _pr[{_kinds}]={{{','.join(map(str, _par))}}}; "
                     f"g_spool_grp = _g; g_spool_part = _pt; g_spool_parent = _pr; }}")
        else:
            L.append("    g_spool_grp = g_spool_part = g_spool_parent = 0;")
        if _spool["entries"]:
            L.append(f"    for(int _k={_spool['start']}; _k<{_spool['end']}; _k++) {{")
            L.append(f"        int _e = {_spool['entry_start']} + (_k - {_spool['start']});")
            L.append("        g_actors[_k].oam_entry = _e; g_oam_entries[_e].affine_slot = -1;")
            L.append("    }")
    else:
        L.append("    g_spool_start = g_spool_end = g_spool_hw = g_spool_free = 0; g_spool_entry = -1;")
        L.append("    g_spool_grp = g_spool_part = g_spool_parent = 0;")
    return L


def _start_lines(p, scene, sym: str, scene_actors: list, actor_offset: int, lua_idx: set, pi: list[dict],
                 has_sound: bool, sound_assets: dict | None,
                 actor_defined_events: dict[str, set[str]] | None) -> list[str]:
    """La musique de la scène, l'état des instances d'un modèle, puis les `on_start` (acteurs, scène)."""
    L: list[str] = []
    # Les acteurs posés qui sont des instances d'un modèle : leur rang dans le modèle (l'indice de leur
    # état de script). Les membres sont les premières instances ; la réserve du spawn suit.
    _member_rank = {j: r for pl in pi for r, j in enumerate(pl["members"])}
    # ── Musique de la scène ───────────────────────
    # Posée AVANT les on_start : le réglage déclaratif passe en premier et le
    # script ajuste ensuite, exactement comme pour la caméra (v0.6.1). Un
    # `music:play()` dans on_start gagne donc, ce qui est ce qu'on attend.
    if has_sound:
        L += scene_music_lines(p, scene, sound_assets)

    # on_start actors (seulement si défini dans le script Lua)
    def _def_init(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    _dsym = dispatch_sym(scene, scene_actors, pi)
    # L'état des instances POSÉES d'un modèle, AVANT tout on_start : l'un peut lire l'autre. Le modèle
    # remet l'état de départ de son script, puis chaque valeur d'export propre au membre y est posée.
    if _member_rank:
        from codegen.runtime_codegen.lua_compiler import member_export_inits
        from scripting.codegen import export_setter_c_type
        for j in sorted(lua_idx):
            if j not in _member_rank:
                continue
            actor, _ = scene_actors[j - actor_offset]
            s = _dsym(scene.name, actor.name)
            L.append(f"    {s}_pool_init(&g_actors[{j}]);")
            for name, typ, literal in member_export_inits(p, scene, actor):
                arg = f"({export_setter_c_type(typ)}){literal}" if literal.startswith("{") else literal
                L.append(f"    {s}_set_{name}(&g_actors[{j}], {arg});")
    for j in sorted(lua_idx):
        actor, _ = scene_actors[j - actor_offset]
        s = _dsym(scene.name, actor.name)
        if _def_init(s, "on_start"):
            L.append(f"    {s}_on_start(&g_actors[{j}]);")
    # on_start scene
    if getattr(scene, "script", ""):
        L.append(f"    {sym}_scene_on_start();")
    return L
