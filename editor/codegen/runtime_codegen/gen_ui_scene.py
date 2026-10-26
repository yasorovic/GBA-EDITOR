"""runtime_codegen/gen_ui_scene.py — l'interface d'une scène dans `scene_init` : images, routage de rendu par nœud.

Colle `gen_ui` (tables projet) à `gen_text` (allocation OBJ) ; à part de `gen_ui`, que `gen_text` importe déjà."""
from __future__ import annotations

from codegen.c_names import sym as c_sym
from codegen.font_emit import project_fonts
from codegen.oam_alloc import scene_oam_layout
from codegen.palette_alloc import scene_bank_layout
from codegen.runtime_codegen.gen_scene_query import scene_ui_images
from codegen.runtime_codegen.gen_text import (
    gen_ui_texts, obj_text_alloc, scene_region_backdrops, scene_region_colors,
)
from codegen.runtime_codegen.gen_ui import emit_ui_images_c, region_actor_index, ui_element_index
from core.diagnostic import build_warning
from core.models.palette import OWN_PAL_BANK
from core.project import Project


def ui_images_lines(p, sprite_offsets: dict, emit=None) -> list[str]:
    """Table des images + leurs constantes. Séparée de `fonts_and_texts_lines`
    parce qu'elle a besoin de `sprite_offsets`, qui n'est connu qu'une fois
    l'union des sprites faite — donc bien plus tard dans le pipeline."""
    images = p.all_images() if hasattr(p, "all_images") else []
    if emit and images:
        from core.models.ui_region import can_fill
        n_bound = sum(1 for _l, im in images if getattr(im, "sprite_name", ""))
        n_fill = sum(1 for _l, im in images if can_fill(im))
        emit("log_line", f"[ui] {len(images)} interface sprite(s) (including {n_fill} container "
                         f"background(s)), {n_bound} bound to a sprite")
    return emit_ui_images_c(p, sprite_offsets, obj_text_alloc(p),
                            actor_index=region_actor_index(p),
                            elem_index=ui_element_index(p), emit=emit)


def gen_ui_images(p: Project, scene, text_cbb: int, sprite_offsets: dict,
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
        L.append(f"    ui_image_set_bank({info['index']}, {bank if bank is not None else 0});   /* '{info['el'].name}': palette of "
                 f"{sprite.name} */")
        if bank is None and emit:
            emit("diagnostic", build_warning(
                f"image '{info['el'].name}': no free bank for the palette of '{sprite.name}' — it will"
                " display with the colours of bank 0.", "ui"))
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


def gen_ui_routes(p: Project, scene) -> list[str]:
    """Routage de rendu par scène : pour chaque zone/image rendue
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


def scene_ui_lines(p, scene, sym: str, sprite_offsets: dict, obj_text_oam: int, obj_text_tile: int,
                   emit=None) -> list[str]:
    """Le texte et l'interface d'une scène dans `scene_init` : BGxCNT des calques d'UI, routage de rendu, fonds
    des conteneurs, polices, surface composée, textes authorés, puis images d'interface.

    En DERNIER des postes de texte, les textes authorés lisent tout ce qui précède (police, base de tuiles,
    surface composée, couleurs de fond, base OBJ) ; les images viennent après eux."""
    L: list[str] = []
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
    L += gen_ui_routes(p, scene)
    # Remis à 0 (= pas de surface dédiée) à CHAQUE scène : `g_surf_tile_base`
    # est un global qui, sans ce reset, garderait la valeur de la scène
    # précédente pour une scène qui n'a elle-même aucune zone à fond.
    L.append("    text_set_surf_base(0);")
    # Fonds COULEUR des conteneurs : les tuiles pleines occupent le DÉBUT du
    # bloc UI (le texte se décale de `len(indices)`), puis on les repose sur le
    # rectangle de chaque container. Statique : posé une fois, avant le texte.
    for i, idx in enumerate(fill_indices):
        L.append(f"    ui_fill_load_solid({text_cbb}, {text_base + i}, {idx});   /* solid tile, index {idx} "
                 "*/")
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
        L.append(f"    copy16(TILE_RAM({text_cbb}) + {_cur} * 16, {sym}_{a['sym']}, {a['tiles'] * 32});   /* tiles of "
                 f"background '{a['name']}' */")
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
            L.append(f"    text_set_font_base({_fl['index']}, {_fl['base']});   /* {_fl['name']}: {_fl['tiles']} tile(s) */")
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
    # Chaque fond est posé AVEC l'index de son conteneur (`g_ui_elements`) : le moteur le retient pour que
    # `hide()` l'efface et `show()` le repose, et un conteneur caché dès le départ ne le dessine pas.
    from codegen.runtime_codegen.gen_ui import ui_element_index as _ui_element_index
    _elem_of = _ui_element_index(p)
    for f in fills:
        L.append(
            f"    ui_fill_rect_tracked({_elem_of.get(f['name'], -1)}, {f.get('slot', text_bg)}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, "
            f"{text_base + fill_indices.index(f['index'])}, {f['bank']});   /* colour background '{f['name']}' → BG{f.get('slot', text_bg)} */")
    for f in img_fills:
        L.append(
            f"    ui_fill_map_tracked({_elem_of.get(f['name'], -1)}, {f.get('slot', text_bg)}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, {sym}_uimap_{c_sym(f['name'])}, "
            f"{asset_base[f['asset']]});   /* image background '{f['name']}' → BG{f.get('slot', text_bg)} */")
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
            f"    text_set_region_backdrop({rb['region']}, {sym}_uimap_{c_sym(f['name'])}, {f['w']}, {rb['dx']}, {rb['dy']}, "
            f"{asset_base[f['asset']]}, {f['bank']});   /* '{rb['name']}' recomposes the background '{f['name']}' */")
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
        L.append(f"    text_set_region_color({rc['region']}, {rc['index']}, {rc['bank']});   /* '{rc['name']}' on the "
                 f"background of '{rc['container']}' */")
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
        L.append(f"    text_set_surf_base({surf_base});   /* shared surface (free writing), "
                 "after the mono glyphs */")
        # Puis un bloc PROPRE par zone composée, à la suite. C'est ce qui
        # permet à deux boîtes de coexister où qu'elles soient à l'écran : la
        # surface partagée, elle, est adressée modulo TEXT_SURF_H rangées.
        _shared = int(_res.get("shared_surf_tiles", 0) or 0)
        for _sl in _res.get("surf_layout", []):
            L.append(
                f"    text_set_region_surf({_sl['region']}, {surf_base + _shared + _sl['base']}, {_sl['w']}, {_sl['h']});   /* '{_sl['name']}': "
                f"{_sl['w']}×{_sl['h']} tiles */")
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
    L += gen_ui_images(p, scene, text_cbb, sprite_offsets, emit)
    return L


def text_actor_accessor_lines() -> list[str]:
    """Position et profondeur d'un acteur pour les zones de texte ancrées. À émettre dès qu'UNE scène a de l'UI OBJ.

    `gba_engine.h` ignore la structure Actor (elle est déclarée dans runtime_api_inline.h, qui inclut le moteur
    et non l'inverse), d'où ces accesseurs passés par pointeur de fonction plutôt qu'une dépendance inversée."""
    return [
        "/* ── Actor position and depth for the anchored UI ─── */",
        "static int _txt_actor_x(int i) { return g_actors[i].x>>8; }",
        "static int _txt_actor_y(int i) { return g_actors[i].y>>8; }",
        "static int _txt_actor_prio(int i) { return actor_oam_entry(&g_actors[i])->priority; }",
        "",
    ]


def obj_text_band(p, scene, obj_text_tile: int, emit=None) -> int:
    """Base OBJ de la bande d'interface de CETTE scène : le DÉBUT de l'OAM. Les sprites d'acteurs prennent les
    emplacements qui suivent, à la frame (cf. `oam_window_open`) ; la bande ne bouge donc pas, quel que soit
    le nombre d'acteurs à l'écran. -1 si la scène n'a aucune UI en sprites."""
    lay = scene_oam_layout(p, scene)
    base = 0 if lay.ui else -1
    if emit and lay.ui:
        emit("log_line",
             f"[text] scene '{scene.name}': OBJ OAM band "
             f"{base}..{base + lay.ui - 1} (out of 128), tiles from {obj_text_tile}")
    return base
