"""codegen/runtime_codegen/gen_scene_query.py — la couche de REQUÊTES du codegen.

Extrait de `main_gen` (A3). Les émetteurs de domaine (`gen_sprite`, `gen_affine`,
`gen_ui`…) et l'orchestrateur `generate_main` partagent des fonctions d'ANALYSE
qui rendent de la donnée (profondeur d'un arbre d'acteurs, tags de collision, si
un acteur a une box physique…). Les tenir ici, SOUS les émetteurs, rompt les
dépendances croisées : un émetteur importe la requête (vers le bas), la requête
n'importe jamais un émetteur.

Ce module ne rend que de la donnée — jamais des lignes de C. Il n'importe que le
modèle, d'autres requêtes, et des utilitaires de codegen SANS état et orientés
vers le bas (dérivation de symbole, géométrie de map) : `grit_conversion` et
`bg_anim` ne réimportent jamais un émetteur, donc l'invariant tient — cette
couche reste à la base (cf. TodoTechnique, A3).
"""
from __future__ import annotations

from core.models.components import CollisionBoxComponent
from codegen.grit_conversion import (bg_layer_sym, bg_layer_sym_for,
                                     bg_map_geometry, bg_map_sbb_count,
                                     count_frames)


def parent_depths(scene_actors: list) -> tuple[dict, list]:
    """(profondeur de chaque acteur par son nom, erreurs bloquantes).

    Profondeur 0 = pas de parent. C'est ELLE qui donne l'ordre d'émission —
    parents avant enfants — et c'est ce tri au build qui remplace
    l'ordonnanceur, le drapeau de salissure et l'invalidation qu'une hiérarchie
    au runtime aurait demandés (ROADMAP v0.23). L'ordre d'une frame continue de
    se lire en clair dans le C émis, ce qui était la seule chose à protéger.

    Deux fautes sont bloquantes, et pour la même raison : sans profondeur, il
    n'y a pas d'ordre, donc pas de composition possible.
      - un parent qui ne nomme aucun acteur de CETTE scène ;
      - un cycle, nommé en clair — « A → B → A » se corrige tout de suite,
        « parenté invalide » ne se corrige pas."""
    by_name = {a.name: a for a, _ in scene_actors}
    depths: dict = {}
    errors: list = []
    for a, _ in scene_actors:
        cur, chain = a, []
        while True:
            chain.append(cur.name)
            par = getattr(cur, "parent", None)
            if not par:
                break
            if par not in by_name:
                errors.append(
                    f"actor \"{a.name}\" has parent \"{par}\", which is not an actor of "
                    "this scene. A parent is chosen within the same scene.")
                chain = []
                break
            # Contre la CHAÎNE et non contre un ensemble à part : le cycle est
            # alors nommé au moment où il se referme (« A → B → A ») et non un
            # cran plus loin, ce qui donnait un chemin qui repassait deux fois.
            if par in chain:
                errors.append(
                    f"circular parenting: {' → '.join(chain)} → {par}. An actor cannot descend "
                    "from itself.")
                chain = []
                break
            cur = by_name[par]
        if chain:
            depths[a.name] = len(chain) - 1
    return depths, errors


def actor_box_tags(owner) -> list[str]:
    """Les tags des boxes d'un acteur (ou d'un prefab), inactives comprises :
    « Active » de l'inspecteur n'est que l'état de DÉPART, un script peut
    l'allumer (`hb:activate()`). « body » par défaut, comme partout ailleurs
    dans le build."""
    return [c.tag or "body" for c in getattr(owner, "components", [])
            if isinstance(c, CollisionBoxComponent)]


def actors_can_collide(p, a, b) -> bool:
    """Ces deux acteurs ont-ils UNE SEULE combinaison de tags qui se rencontre ?

    Si non, la paire n'est pas émise du tout (ROADMAP v0.23) : ni bloc de C, ni
    entrée dans `_col_prev`, ni test par frame. Le gain est donc en ROM autant
    qu'en cycles — c'est la raison de filtrer au BUILD plutôt qu'au runtime.

    Sans box d'un côté, il n'y a rien à filtrer : on laisse passer, et le reste
    du build décide comme avant. Ne rien dire vaut mieux que deviner."""
    from core.models.settings import tags_collide
    ta, tb = actor_box_tags(a), actor_box_tags(b)
    if not ta or not tb:
        return True
    return any(tags_collide(p.settings, x, y) for x in ta for y in tb)


def has_solid_box(owner) -> bool:
    """Cet acteur (ou prefab) a-t-il une box PHYSIQUE ?

    C'est ce qui lui donne droit à la résolution contre la carte de collision —
    la définition que le modèle donne déjà de `solid` (cf. components.py)."""
    return any(getattr(c, "solid", False) and hasattr(c, "w")
               for c in getattr(owner, "components", []))


def scene_has_cmap(scene) -> bool:
    """Carte de collision réellement peuplée — une grille de zéros n'est pas une
    carte, et n'a rien à faire heurter."""
    cmap = getattr(scene, "collision_map", None) or []
    return any(v != 0 for row in cmap for v in row)


def has_col_event(defined, sym: str) -> bool:
    """Ce script réagit-il à une collision ? `defined` est le prédicat local
    `_def(symbole, événement)` de la génération de scène (il rend True quand le
    script n'a pas été analysé, cf. `_gen_scene_tick`)."""
    return bool(defined(sym, "on_collision_enter") or defined(sym, "on_collide")
                or defined(sym, "on_collision_exit"))


def bg_info(p, scene) -> list[dict]:
    """Un CBB (16 Ko) par layer = bg_slot ; sa map occupe les derniers SBB de ce
    CBB. Chaque layer de la scène référence une image ; sa compression vient du
    BackgroundAsset (sidecar) keyé par ce nom. cf. pipeline._check_bg_tile_budget.

    Requête PURE de géométrie : le `sbb` rendu ici est la valeur initiale
    (`bg_slot*8 + …`). La pose définitive par l'allocateur — qui dépend de ce que
    le texte réserve — est appliquée séparément par `_apply_vram_layout`, en
    dehors de cette couche (cf. la soudure BG↔texte rompue, A3)."""
    result = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name:
            continue
        ba = p.get_background(layer.background_name)
        # Fond bitmap (Mode 4) : non supporté au build (increment 2) — ignoré ici
        # (sinon il serait traité comme un fond tuilé legacy → symbole manquant).
        if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
            continue
        bg_slot = layer.bg_slot
        speed = int(layer.scroll_speed * 256)
        sym = bg_layer_sym(layer.background_name, bg_slot)
        if ba and ba.tileset:
            # Fond COMPRESSÉ (métadonnées) — 16 palettes via g_pal_bg, tuiles/map
            # depuis le C émis par pipeline._emit_encoded_bg. Un axe >64 tuiles
            # dépasse la fenêtre hardware -> streaming (map résidente 64 sur cet axe).
            # Symbole PROPRE À LA SCÈNE si le layer est peint (map d'overrides,
            # cf. bg_layer_sym_for / pipeline._emit_encoded_bg).
            sym = bg_layer_sym_for(scene, layer)
            tw, th = ba.tiles_w, ba.tiles_h
            stream_h = tw > 64
            stream_v = th > 64
            win_w = 64 if stream_h else tw
            win_h = 64 if stream_v else th
            ms = (1 if win_w > 32 else 0) | (2 if win_h > 32 else 0)
            map_sbb_count = bg_map_sbb_count(ms)
            result.append({
                "bg": bg_slot, "stem": ba.name, "sym": sym,
                "tw": tw, "th": th, "sbb": bg_slot * 8 + (8 - map_sbb_count),
                "map_size": ms, "map_sbb_count": map_sbb_count,
                "speed": speed, "pal_bank": layer.pal_bank, "compressed": True,
                "stream": stream_h or stream_v, "stream_h": stream_h, "stream_v": stream_v,
                "win_w": win_w, "win_h": win_h,
                "bpp8": getattr(ba, "bpp", 4) == 8,   # BGxCNT bit 7 (256/1)
            })
        else:
            # Image non compressée -> taille depuis le PNG (chemin legacy).
            ap = p.background_images_dir / (ba.asset if ba and ba.asset else f"{layer.background_name}.png")
            try:
                from PIL import Image
                with Image.open(ap) as img:
                    w, h = img.size
            except Exception:  # tolerated: unreadable PNG: the validator reports it, default size kept
                w, h = 240, 160
            tw, th, ms = bg_map_geometry(w, h)
            map_sbb_count = bg_map_sbb_count(ms)
            result.append({
                "bg": bg_slot, "stem": ap.stem, "sym": sym,
                "tw": tw, "th": th, "sbb": bg_slot * 8 + (8 - map_sbb_count),
                "map_size": ms, "map_sbb_count": map_sbb_count,
                "speed": speed, "pal_bank": layer.pal_bank,
            })
    return result


def scene_world_size(p, scene) -> tuple[int, int]:
    """Taille du monde de la scène en pixels — le canvas : le plus grand des
    fonds posés, 240×160 par défaut. C'est ce que `scene.size.w/.h` expose aux
    scripts (posé au runtime par scene_init dans g_scene_w/g_scene_h)."""
    w, h = 240, 160
    for bi in bg_info(p, scene):
        tw, th = bi.get("tw") or 0, bi.get("th") or 0
        if tw:
            w = max(w, tw * 8)
        if th:
            h = max(h, th * 8)
    return min(w, 32767), min(h, 32767)


def scene_anim_descriptors(p, scene, bgi: list[dict]) -> list[dict]:
    """Placements de fonds animés de la scène, enrichis de ce que seul le codegen
    connaît : le screenblock et la taille de la carte du calque hôte.

    L'ordre est celui de `bg_anim.scene_animations`, le même que `pipeline` a
    utilisé pour nommer les tables — les deux le recalculent séparément, ils
    doivent tomber d'accord (cf. bg_anim.anim_table_sym)."""
    from codegen.bg_anim import scene_animations, anim_table_sym, shared_table_sym
    by_slot = {bi["bg"]: bi for bi in bgi}
    out = []
    seen_shared: set[int] = set()
    for a in scene_animations(p, scene):
        bi = by_slot.get(a["layer"].bg_slot)
        if bi is None:
            continue    # calque non émis (bitmap, image manquante) : rien à animer
        g = a["geom"]
        if a["shared"]:
            # UN descripteur par fusion, pas par copie : le bloc de pixels est
            # partagé, deux descripteurs y écriraient la même chose deux fois.
            if a["table_index"] in seen_shared:
                continue
            seen_shared.add(a["table_index"])
            out.append({
                "shared": True,
                "table": shared_table_sym(scene, a["table_index"]),
                # 8 mots de 32 bits par tuile 4bpp = 16 u16.
                "cbb": bi["bg"], "vram_ofs": a["block"].tile_base * 16,
                "words": g.cells * 8,
                "frames": g.frames, "speed": g.speed, "loop": 1 if g.loop else 0,
            })
            continue
        f0, t0 = g.start_state()
        out.append({
            "shared": False,
            "table": anim_table_sym(scene, a["table_index"]),
            "sbb": bi["sbb"], "ms": bi["map_size"],
            "col": g.col, "row": g.row, "cols": g.cols, "rows": g.rows,
            "frames": g.frames, "speed": g.speed, "loop": 1 if g.loop else 0,
            "f0": f0, "t0": t0,
        })
    return out


# ─── requêtes sprite / image d'UI (packing VRAM OBJ, géométrie) ─────────────────

def sprite_offsets_for(p, sprites: list) -> tuple[dict, dict]:
    """Calcule tile_offset et nframes pour une liste (actor, sprite), sans doublons."""
    offsets, nframes = {}, {}
    tile_offset = 0
    for _, sprite in sprites:
        if not sprite or not sprite.asset or sprite.name in offsets:
            continue
        nf = count_frames(p, sprite)
        offsets[sprite.name] = tile_offset
        nframes[sprite.name] = nf
        tile_offset += sprite.tiles_per_frame * nf
    return offsets, nframes


def obj_tiles_used(p, sprites: list) -> int:
    """Tuiles de VRAM OBJ occupées par les sprites — donc la 1re tuile libre.

    Recalcule l'accumulation de `sprite_offsets_for` plutôt que de lui faire
    rendre un total de plus : les deux doivent packer à l'identique, et un
    second compteur à tenir à jour finirait par diverger."""
    seen, total = set(), 0
    for _, sprite in sprites:
        if not sprite or not sprite.asset or sprite.name in seen:
            continue
        seen.add(sprite.name)
        total += sprite.tiles_per_frame * count_frames(p, sprite)
    return total


def ui_image_sprites(p) -> list:
    """[(None, SpriteAsset)] des sprites que les IMAGES d'UI réclament.

    Rendu sous la forme de paires `(actor, sprite)` pour se verser tel quel dans
    `all_sprite_pairs` : les tuiles d'un sprite d'interface arrivent alors en
    VRAM OBJ par le même chemin que celles d'un acteur, et `sprite_offsets_for`
    lui donne une base dans la même numérotation. Un chemin de chargement à part
    aurait dupliqué le packing — donc, tôt ou tard, l'aurait fait diverger.

    Vaut aussi pour une image en cible BG : ses tuiles sont recopiées dans le
    charblock d'UI, mais le sprite reste résident en OBJ. Le doublon est assumé
    — il n'y a pas de « désallouer une plage OBJ » dans ce packing, et une image
    de HUD partage presque toujours son sprite avec un acteur."""
    out, seen = [], set()
    for _lay, im in (p.all_images() if hasattr(p, "all_images") else []):
        name = getattr(im, "sprite_name", "") or ""
        if not name or name in seen:
            continue
        sprite = p.get_buildable_sprite(name)
        if sprite is None or not sprite.asset:
            continue
        seen.add(name)
        out.append((None, sprite))
    return out


def scene_ui_images(p, scene) -> list[dict]:
    """Ce que chaque image de la mise en page d'une scène demande au build.

    Un dict par image RÉSOLUE (sprite existant) : index global dans
    `g_ui_images`, sprite, nombre de frames, cible, et le nombre de tuiles à
    réserver dans le charblock d'UI si elle s'écrit dans la tilemap.

    Les images NON résolues (aucun sprite, ou nom cassé) sont omises et non pas
    réservées à zéro : elles n'existent pas à l'écran, et le validateur le dit
    déjà. Réserver pour elles décalerait la base des suivantes à chaque frappe
    dans le champ « Sprite »."""
    from core.models.ui_region import TARGET_BG
    rm = int(getattr(scene, "render_mode", 0) or 0)
    index = {im.name: i for i, (_l, im) in enumerate(p.all_images())}
    out: list[dict] = []
    for lay, im in p.scene_ui_images(scene):
        sprite = p.get_buildable_sprite(getattr(im, "sprite_name", "") or "")
        if sprite is None or not sprite.asset or im.name not in index:
            continue
        frames = count_frames(p, sprite)
        g = ui_item_geometry(im, sprite, frames)
        out.append({
            "el": im, "index": index[im.name], "sprite": sprite,
            "frames": frames, "tiles": g["tiles"],
            "tiles_per_frame": sprite.tiles_per_frame,
            "map_tiles": g["map_tiles"],
            "cols": g["cols"], "rows": g["rows"],
            "frame_w": g["frame_w"], "frame_h": g["frame_h"],
            "bg": lay.resolved_target(im, rm) == TARGET_BG,
        })
    return out


def ui_item_geometry(el, sprite, frames: int = 1) -> dict:
    """Géométrie d'un élément qui pose un sprite, image ou fond de conteneur.

    Le modèle ne résout pas les noms d'asset : c'est ici qu'on lui donne la
    taille de frame, seule inconnue qui sépare un `UIImage` (dont le rectangle
    EST la frame) d'un `UIContainer` à fond sprite (dont le rectangle se pave)."""
    from core.models.ui_region import image_geometry
    return image_geometry(el, frames,
                          int(getattr(sprite, "frame_w", 0) or 0),
                          int(getattr(sprite, "frame_h", 0) or 0))
