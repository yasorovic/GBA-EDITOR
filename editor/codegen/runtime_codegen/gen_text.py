"""codegen/runtime_codegen/gen_text.py — l'émetteur du domaine texte/police.

Extrait de `main_gen` (A3), au-dessus de la couche de requêtes. Trois familles :
  - l'ANALYSE des fonds de conteneur et zones (scene_color_fills/image_fills,
    region_is_composited, scene_region_*, region_ink_bank) ;
  - la RÉSERVATION VRAM du texte (scene_text_reservation) et son placement OBJ
    (obj_text_alloc), source de vérité unique lue par le placement et le budget ;
  - l'ÉMISSION du C (fonts_and_texts_lines, _emit_font_subsets, gen_ui_texts).

Dépend vers le bas : `font_emit`, `gen_scene_query` (scene_ui_images), `gen_ui`
(region_actor_index/ui_element_index), `gen_palette` (palettes_lines),
`oam_alloc` (layout_obj_budget_resolved) et le modèle. Aucun n'importe ce module — pas de
cycle. `_declared_lang_codes`/`_emit_font_subsets` restent privés (consommés que
d'ici). `region_ink_bank`/`region_is_composited` sont relus par l'éditeur
(inspecteur, canvas), d'où leur nom public.
"""
from __future__ import annotations

from core.project import Project
from core.models.ui_region import region_fill_container
from codegen.c_names import sym as c_sym
from codegen.oam_alloc import layout_obj_budget_resolved
from codegen.font_emit import project_fonts, encodable_project_fonts
from codegen.runtime_codegen.gen_scene_query import scene_ui_images
from codegen.runtime_codegen.gen_ui import region_actor_index, ui_element_index
from codegen.runtime_codegen.gen_palette import palettes_lines


def scene_text_colors(p, scene, font_name: str) -> list:
    """Couleurs à charger pour cette police dans cette scène, variante 0 d'abord.

    La variante 0 est l'encre d'ORIGINE : une police à plusieurs teintes garde
    les siennes tant qu'aucun slot ne demande de couleur. Les autres sont les
    index réclamés par les slots, chacun coûtant une copie des glyphes — d'où le
    tri, pour que l'ordre ne dépende pas de l'itération.

    Un slot qui ne DÉCLARE pas de police écrit avec la police courante, que le
    build ne connaît pas : sa couleur compte alors pour toutes les polices de la
    scène. Une copie de trop coûte des tuiles ; une de moins ferait tomber la
    couleur en silence."""
    from core.models.ui_region import KIND_SLOTS, KIND_LIST
    colors: set = set()
    for _lay, el in p.scene_ui_elements(scene):
        # Une LISTE réclame la couleur de sa rangée choisie, au même titre qu'un
        # slot réclame la sienne : le moteur la résout en VARIANTE au rendu
        # (`text_var_for`), et une variante non chargée fait retomber la rangée
        # sur son encre sans que rien ne le dise. La liste ne déclare pas de
        # police — sa couleur compte donc pour toutes celles de la scène, même
        # règle qu'un slot qui n'en déclare pas.
        if getattr(el, "kind", "") == KIND_LIST:
            c = int(getattr(el, "selected_text_color", 0) or 0)
            if 1 <= c <= 15:
                colors.add(c)
            continue
        if getattr(el, "kind", "") not in KIND_SLOTS:
            continue
        c = int(getattr(el, "text_color", 0) or 0)
        if not 1 <= c <= 15:
            continue
        declared = getattr(el, "font_name", "")
        if not declared or declared == font_name:
            colors.add(c)
    return [0] + sorted(colors)


def _declared_lang_codes(p) -> list[str]:
    """Codes des langues déclarées, source en tête — `[""]` si le projet n'en
    déclare aucune.

    Un point unique parce que DEUX lecteurs doivent voir la même liste : le
    sous-ensemble de glyphes ÉMIS pour une scène (`_emit_font_subsets`) et la
    place RÉSERVÉE pour l'accueillir (`scene_text_reservation`). Les laisser
    calculer leur liste chacun de son côté est exactement ce qui a produit le
    décalage réparé en phase 5.1 : le runtime chargeait l'union, le build
    réservait la source."""
    langs = p.settings.all_languages() if hasattr(p, "settings") else []
    return [l.code for l in langs] or [""]


def scene_text_reservation(p, scene) -> dict:
    """Tuiles à réserver au texte dans le charblock d'UI de CETTE scène.

    Un seul calcul pour deux lecteurs : le placement (`_apply_vram_layout`) et
    le garde-fou de budget (`pipeline._scene_tile_budgets`). Les laisser
    diverger validerait un budget que le placement ne tient pas.

    **Dimensionnée sur l'UNION des langues déclarées** (ROADMAP v0.9, phase
    5.1), parce que c'est ce que le RUNTIME charge : `text_set_font` copie
    `n_var × n_load` tuiles depuis le `FontSubset` de la scène, et ce
    sous-ensemble est l'union (`_emit_font_subsets`, décision 4 de la phase
    3.3) — quelle que soit la valeur de `g_lang`. Compter la seule langue
    source réservait la moitié du bloc dans le cas mesuré (12 tuiles pour 24
    chargées) et laissait le chargement écraser ce qui suit : les bases des
    polices voisines, le bloc de surface composée, les sprites en cible BG.
    Un projet monolingue n'en voit rien — l'union d'une seule langue est
    cette langue.

    Quatre postes, dans l'ordre où ils occupent le charblock :
    - les fonds COULEUR puis les fonds IMAGE (nine-slice, background) — ils
      précèdent les glyphes, qui se décalent d'autant ;
    - les GLYPHES, restreints aux polices que cette scène peut charger
      (`font_emit.scene_font_names`) ;
    - la SURFACE composée : un bloc PROPRE par zone, à la taille de son
      rectangle, plus les 240 tuiles de la surface partagée SI la scène peut
      écrire librement (`text.draw`). Jamais à l'adresse des glyphes (cf.
      runtime `g_surf_tile_base`, `RegionSurf`) ;
    - les SPRITES des images en cible BG, TOUTES frames comprises : un script
      peut changer d'état à n'importe quelle frame, et recopier depuis la ROM à
      cet instant-là ferait clignoter l'image. En dernier parce que c'est le
      poste le plus récent, donc celui dont l'absence ne doit rien décaler dans
      un projet qui n'emploie pas d'image."""
    from codegen.font_emit import (scene_text_tiles, scene_font_names,
                                   scene_codepoints_union, mono_vram_tiles,
                                   scene_default_font, TEXT_SURF_TILES)
    fonts = project_fonts(p)
    # `scene_init` émet toujours un `text_set_font` : la police par défaut de la
    # scène est en VRAM même si la scène n'écrit pas une lettre.
    _, default_font = scene_default_font(p, scene)
    names = scene_font_names(p, scene, default_font)

    fills, fill_indices = scene_color_fills(p, scene)
    img_fills, img_assets = scene_image_fills(p, scene)
    scene_slots = p.scene_ui_slots(scene)     # (nœud, slot) sur les N `Interface`
    # Trois raisons de composer, donc de réserver un bloc de surface : la zone
    # a un FOND (l'aplat d'un conteneur couleur, ou la carte d'un conteneur
    # nine-slice/background) ou elle est SURLIGNÉE. Dans les trois cas le texte
    # se compose même en police mono — poser une tuile de glyphe percerait ce
    # qu'il y a dessous. Les mêmes fonctions que l'émetteur, sinon la
    # réservation et le placement ne parleraient pas de la même scène.
    needs_surface = bool(scene_region_colors(p, scene, fills)) \
        or bool(scene_region_backdrops(p, scene, img_fills)) \
        or any(int(getattr(r, "highlight_color", 0) or 0)
               for _l, r in scene_slots)

    # Ce que la scène AFFICHE borne ce qu'elle charge. `None` = indécidable,
    # donc la police entière (et pas de sous-ensemble émis non plus). Le MÊME
    # appel que `_emit_font_subsets`, avec les mêmes langues : la réservation
    # et le sous-ensemble émis sont deux lectures d'un seul calcul.
    cps = scene_codepoints_union(p, scene, _declared_lang_codes(p))

    # ── Où chaque police se charge ────────────────────────────────
    # Chacune a SA base : un titre et un corps de texte coexistent à l'écran, et
    # la réservation devient une SOMME (abordable grâce au sous-ensemble).
    #
    # Si l'ensemble des polices est indécidable, on ne sait pas lesquelles
    # coexistent et sommer tout le projet réserverait un charblock pour rien :
    # repli sur le modèle « une seule résidente, base 0 », donc le MAXIMUM.
    from codegen.font_emit import render_composited
    scene_fonts = [(i, f) for i, f in enumerate(fonts)
                   if names is None or f.name in names]
    font_layout: list[dict] = []
    if names is not None:
        base = 0
        for i, f in scene_fonts:
            if render_composited(f):
                continue          # ne charge aucun glyphe : c'est la surface qui coûte
            n = mono_vram_tiles(f, cps)
            colors = scene_text_colors(p, scene, f.name)
            font_layout.append({"index": i, "name": f.name, "base": base,
                                "tiles": n * len(colors), "colors": colors})
            base += n * len(colors)
        mono_tiles = base
    else:
        mono_tiles = scene_text_tiles(fonts, names, cps)

    # Une police COMPOSÉE range ses pixels dans la surface, comme une zone à
    # fond : sans ça `blit_use_bg_surface` retombe sur la base des glyphes et
    # écrase la police mono voisine.
    needs_surface = needs_surface or any(render_composited(f) for _i, f in scene_fonts)

    img_tiles = sum(a["tiles"] for a in img_assets)

    # ── Où chaque ZONE compose ────────────────────────────────────
    # Un bloc PROPRE par zone composée, à la taille de son rectangle, plutôt
    # que la surface partagée adressée modulo : celle-ci ne couvre que
    # TEXT_SURF_H rangées sur 20, donc deux boîtes éloignées à l'écran s'y
    # écrasaient (un titre en haut, un dialogue en bas — une mise en page
    # banale). Cf. `RegionSurf` dans gba_engine.h.
    #
    # Même motif que `font_layout` juste au-dessus et `img_layout` juste en
    # dessous : une base RELATIVE au bloc de la scène, dans l'ordre de la
    # mise en page.
    from codegen.font_emit import scene_writes_free
    from core.models.ui_region import KIND_TEXT, TARGET_BG
    rm = int(getattr(scene, "render_mode", 0) or 0)
    slot_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    surf_layout: list[dict] = []
    base = 0
    if needs_surface:
        for lay_ui, el in scene_slots:
            if getattr(el, "kind", "") != KIND_TEXT or el.name not in slot_idx:
                continue
            if lay_ui.resolved_target(el, rm) != TARGET_BG:
                continue      # une bande OBJ a déjà son bloc propre
            if not region_is_composited(p, lay_ui, el, default_font):
                continue      # chemin tilemap : pas de surface du tout
            _tx, _ty, tw, th = lay_ui.absolute_tile_rect(el, lambda _n: None)
            surf_layout.append({"region": slot_idx[el.name], "name": el.name,
                                "base": base, "w": tw, "h": th})
            base += tw * th
    region_surf_tiles = base

    # La surface PARTAGÉE ne subsiste que pour l'écriture libre, qui n'a pas de
    # rectangle à qui donner un bloc. Une scène qui n'écrit que dans ses zones
    # ne la paie plus.
    shared_surf_tiles = (TEXT_SURF_TILES
                         if needs_surface and scene_writes_free(p, scene) else 0)
    surf_tiles = shared_surf_tiles + region_surf_tiles

    # Images en cible BG : chacune sa base RELATIVE au bloc, dans l'ordre de la
    # mise en page. Relative comme le reste (glyphes, surface) — la base absolue
    # est celle que l'allocateur donne à la scène, et une même mise en page sert
    # plusieurs scènes qui ne l'ont pas au même endroit.
    ui_images = scene_ui_images(p, scene)
    img_layout: list[dict] = []
    base = 0
    for info in ui_images:
        if not info["bg"]:
            continue
        img_layout.append({"index": info["index"], "name": info["el"].name,
                           "base": base, "tiles": info["tiles"],
                           "sprite": info["sprite"].name,
                           "tiles_per_frame": info["tiles_per_frame"]})
        base += info["tiles"]
    sprite_tiles = base

    return {
        "fills": fills, "fill_indices": fill_indices,
        "img_fills": img_fills, "img_assets": img_assets,
        "mono_tiles": mono_tiles, "needs_surface": needs_surface,
        "surf_layout": surf_layout, "shared_surf_tiles": shared_surf_tiles,
        # Tuiles RÉELLEMENT occupées par la surface : le bloc partagé (0 si la
        # scène n'écrit pas librement) PLUS les blocs propres des zones. C'est ce
        # qui sépare le texte des images ; l'émission doit lire CE nombre, pas le
        # plafond `TEXT_SURF_TILES` (cf. `_gen_ui_images`).
        "surf_tiles": surf_tiles,
        "font_names": names, "codepoints": cps, "font_layout": font_layout,
        "default_font": default_font,
        "ui_images": ui_images, "img_layout": img_layout,
        "sprite_tiles": sprite_tiles,
        "total": (len(fill_indices) + img_tiles + mono_tiles + surf_tiles
                  + sprite_tiles),
    }


def obj_text_alloc(p: Project) -> dict:
    """Placement OBJ de chaque zone : {nom: {oam_rel, tile_rel, ...}}.

    Relatif à sa MISE EN PAGE, pas au projet : deux mises en page se partagent
    la même plage réservée puisqu'une seule est active par scène. Sans ça, cinq
    boîtes de dialogue dans cinq mises en page réserveraient cinq fois la place
    alors qu'on n'en voit jamais qu'une."""
    out = {}
    for lay in getattr(p, "ui_layouts", []):
        for name, place in layout_obj_budget_resolved(p, lay)["place"].items():
            out[name] = place
    return out


def _emit_font_subsets(p, encoded: list, emit=None) -> list[str]:
    """Tableaux C des sous-ensembles de glyphes, une entrée par (scène, police).

    Émis ici parce que c'est le seul endroit qui tient les polices ENCODÉES : un
    sous-ensemble parle en index de glyphe encodé, pas en glyphe de la planche.
    Le nom des descripteurs est mémorisé sur la scène, relu par
    `_gen_scene_init` pour poser les `text_set_subset`.

    Pas de sous-ensemble pour une police composée (elle ne charge aucun glyphe)
    ni pour une scène indécidable (police entière, déjà réservée).

    Le sous-ensemble ÉMIS couvre TOUTES les langues déclarées, UNIES
    (`scene_codepoints_union`, ROADMAP v0.9 décision 4) : c'est ce qui permet
    à `lang.set` (phase 4) de recharger une scène dans une autre langue sans
    reconstruire la police en VRAM. La RÉSERVATION (`scene_text_reservation`)
    compte la même union, sur la même liste de langues
    (`_declared_lang_codes`) — depuis la phase 5.1, où les deux divergeaient :
    le runtime chargeait l'union, le build réservait la source."""
    from codegen.font_emit import (build_font_subset, scene_codepoints_union,
                                   scene_font_names, scene_default_font)
    from codegen.c_names import c_ident
    fonts = project_fonts(p)
    if not fonts or not encoded:
        return []
    by_name = {name: (i, e) for i, (name, e) in enumerate(encoded)}
    lang_codes = _declared_lang_codes(p)

    L: list[str] = ["/* ── Sous-ensembles de glyphes (par scène) ───────── */"]
    any_line = False
    for scene in p.scenes:
        scene._ui_font_subsets = {}
        cps = scene_codepoints_union(p, scene, lang_codes)
        if cps is None:
            if emit:
                emit("log_line",
                     f"[font] scene '{scene.name}': fonts loaded WHOLE — what it displays "
                     "cannot be determined at build")
            continue
        names = scene_font_names(p, scene, scene_default_font(p, scene)[1])
        for fname in sorted(names or [f.name for f in fonts]):
            if fname not in by_name:
                continue
            fi, e = by_name[fname]
            sub = build_font_subset(e, cps)
            if sub is None or not sub["load"]:
                continue
            colors = scene_text_colors(p, scene, fname)
            sym = f"g_fsub_{c_ident(scene.name)}_{c_ident(fname)}"
            L.append(f"static const unsigned short {sym}_slot[{len(sub['slot'])}] = {{"
                     + ",".join(str(v) for v in sub["slot"]) + "};")
            L.append(f"static const unsigned short {sym}_load[{len(sub['load'])}] = {{"
                     + ",".join(str(v) for v in sub["load"]) + "};")
            L.append(f"static const unsigned char {sym}_var[{len(colors)}] = {{"
                     + ",".join(str(c) for c in colors) + "};")
            L.append(f"static const FontSubset {sym} = {{ {sym}_slot, {sym}_load, "
                     f"{len(sub['load'])}, {len(colors)}, {sym}_var }};")
            scene._ui_font_subsets[fi] = sym
            any_line = True
            if emit:
                extra = ("" if len(colors) == 1 else
                         f", ×{len(colors)} colours {colors[1:]}")
                emit("log_line",
                     f"[font] scene '{scene.name}': '{fname}' reduced to {len(sub['load'])} tile(s) out of "
                     f"{e['n_tiles']}{extra}")
    return L + [""] if any_line else []


def fonts_and_texts_lines(p, emit=None) -> list[str]:
    """Tables C des polices, des textes et des zones (cf. codegen/font_emit)."""
    from codegen.font_emit import (encode_font, emit_fonts_c, emit_texts_c,
                                   emit_lang_fonts_c, emit_ui_regions_c)

    kept = project_fonts(p)
    if emit:
        kept_names = {f.name for f in kept}
        skipped = [f.name for f in encodable_project_fonts(p) if f.name not in kept_names]
        if skipped:
            emit("log_line", f"[font] {len(skipped)} unused font(s) left out of the ROM: "
                             f"{', '.join(skipped)}")

    encoded = []
    for f in kept:
        try:
            e = encode_font(f, p.asset_abs(f.asset) if f.asset else None)
        except Exception as exc:
            if emit:
                emit("error_line", f"[font] {f.name} : encodage impossible ({exc})")
            continue
        if e.get("warning") and emit:
            emit("log_line", f"[font] {e['warning']}")
        if emit:
            # Le CHEMIN de rendu autant que le coût VRAM : une police composée
            # ne charge aucune tuile, c'est la surface qui coûte. Sans ça un
            # basculement automatique (police trop grosse) passe inaperçu.
            from codegen.font_emit import render_composited, font_vram_tiles
            mode = "composition" if render_composited(f) else "tilemap"
            emit("log_line", f"[font] {f.name} -> {e['n_tiles']} tiles, {len(e['codepoints'])} glyphs, {mode} rendering, "
                             f"{font_vram_tiles(f)} VRAM tiles")
        encoded.append((f.name, e))

    # Même liste que celle dont `lua_compiler` dérive les `#define` : l'ordre
    # fait l'index.
    texts = list(p.build_texts() if hasattr(p, "build_texts")
                 else getattr(p, "texts", []))
    if emit and texts:
        emit("log_line", f"[text] {len(texts)} text entry(ies)")

    regions = p.all_regions() if hasattr(p, "all_regions") else []
    if emit and regions:
        from core.models.ui_region import KIND_TEXT
        n_auth = sum(1 for _l, r in regions if getattr(r, "kind", "") == KIND_TEXT)
        detail = f", including {n_auth} authored text(s)" if n_auth else ""
        emit("log_line", f"[text] {len(regions)} text slot(s){detail} ({len(p.ui_layouts)} layout(s))")
    font_names = [f.name for f in project_fonts(p)]
    subset_lines = _emit_font_subsets(p, encoded, emit)
    # Une entrée par langue déclarée, source en index 0 — `[""]` pour un
    # projet monolingue (aucune langue déclarée), qui retrouve alors
    # exactement les tables d'avant la v0.9 phase 3, à une dimension de plus
    # qui vaut 1 (cf. `emit_texts_c`).
    all_langs = p.settings.all_languages() if hasattr(p, "settings") else []
    lang_codes = [l.code for l in all_langs] or [""]
    content_fn = p.text_content if hasattr(p, "text_content") else (lambda t, c: t.content)
    return (emit_fonts_c(encoded) + subset_lines
            + emit_texts_c(texts, lang_codes, content_fn, p.globals, p.constants,
                           emit, fonts=project_fonts(p))
            + emit_lang_fonts_c(font_names, all_langs,
                                getattr(p.settings, "default_font", ""))
            + emit_ui_regions_c(regions, font_names, emit,
                                obj_place=obj_text_alloc(p),
                                actor_index=region_actor_index(p),
                                elem_index=ui_element_index(p))
            + palettes_lines(p, emit))


def region_is_composited(p: Project, lay, el, default_font_name: str) -> bool:
    """Cette zone compose-t-elle pixel à pixel (surface) plutôt que de poser
    des tuiles ? MÊME règle que `text_is_composited()` côté runtime
    (gba_engine.h) : surlignée, posée dans un conteneur à FOND, ou police
    composée — le fond/surlignement forcent la composition même en police
    MONO, pour se poser SUR ce qui est dessous sans le percer (cf.
    `region_fill_container`).

    Un seul endroit pour cette règle, lu par le canvas (`SceneRegionItem.
    _composited`) et le validateur (`_check_ui_text_surf_alias`) : les
    laisser diverger, c'est risquer qu'un aperçu dise « pas de conflit » sur
    un cas que le build compose bel et bien."""
    if int(getattr(el, "highlight_color", 0) or 0):
        return True
    if region_fill_container(lay, el) is not None:
        return True
    from codegen.font_emit import (render_composited, text_markup_font_names)
    # Une portée [font] force la surface, même si la police de la zone est mono:
    # la composition doit rester un seul chemin pendant les deux passes de mise
    # en page, et le runtime peut rencontrer une police proportionnelle dans le
    # segment. Les traductions sont incluses : changer de langue ne doit jamais
    # faire écrire les pixels dans les tuiles de glyphes mono.
    key = getattr(el, "text_key", "") or ""
    text = p.get_text(key) if key and hasattr(p, "get_text") else None
    if text is not None:
        contents = [getattr(text, "content", "") or ""]
        for lang in getattr(getattr(p, "settings", None), "languages", []):
            raw = getattr(p, "translations", {}).get(lang.code, {}).get(text.id, "")
            if raw:
                contents.append(raw)
        if any(text_markup_font_names(content) for content in contents):
            return True
    fname = getattr(el, "font_name", "") or default_font_name
    from codegen.font_emit import encodable_project_fonts
    fonts_by_name = {item.name: item for item in encodable_project_fonts(p)}

    # `text_set_font()` remappe la police PAR DÉFAUT DU PROJET quand la langue
    # change. Cette zone doit donc réserver une surface si *l'une* de ces
    # polices effectives est composée, même si l'anglais reste en Font8x8
    # tilemap. Oublier ce second nom créait précisément une ROM qui décidait
    # correctement de composer Misaki au runtime, mais sans bloc propre où
    # écrire ses pixels.
    effective_names = {fname}
    project_default = getattr(getattr(p, "settings", None), "default_font", "") or ""
    if fname == project_default:
        effective_names |= {
            getattr(lang, "default_font", "") or ""
            for lang in getattr(getattr(p, "settings", None), "languages", [])
        }
        effective_names.discard("")
    return any(render_composited(fonts_by_name[name])
               for name in effective_names if name in fonts_by_name)


def scene_region_colors(p: Project, scene, fills: list[dict]) -> list[dict]:
    """Zones de texte composées sur l'APLAT d'un container couleur.

    `fills` est ce que `scene_color_fills` a retenu pour CETTE scène — donc
    déjà filtré par toutes les conditions d'émission (cible BG, root ancré
    écran, palette active, calque d'UI). Dériver d'elle plutôt que de refaire la
    recherche est la correction de fond de ce chantier : deux calculs
    indépendants avaient produit un conteneur écarté du build dont la couleur
    apparaissait quand même dans la boîte de son texte enfant.

    Renvoie `{region, name, container, index, color, bank}` — `index` est l'index
    de l'aplat dans la palette du conteneur, `bank` la banque de ce conteneur
    (le texte enfant y lit son encre, il PREND la palette du conteneur), `color`
    la valeur BGR555 (pour l'aperçu éditeur)."""
    from core.models.ui_region import KIND_TEXT, FILL_COLOR
    if not fills:
        return []
    by_container = {f["name"]: f for f in fills}
    slot_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    out: list[dict] = []
    for lay, el in p.scene_ui_slots(scene):
        if getattr(el, "kind", "") != KIND_TEXT or el.name not in slot_idx:
            continue
        container = region_fill_container(lay, el)
        if container is None or getattr(container, "fill_kind", "") != FILL_COLOR:
            continue
        if container.name not in by_container:
            continue          # conteneur écarté du build : rien à teinter
        pal = p.get_palette(getattr(container, "fill_palette", "") or "")
        idx = int(getattr(container, "fill_index", 0) or 0)
        if not pal or not 0 <= idx < len(pal.colors):
            continue
        out.append({"region": slot_idx[el.name], "name": el.name,
                    "container": container.name, "index": idx,
                    "color": int(pal.colors[idx]),
                    # Banque du conteneur (sa place dans active_bg_palettes) — le
                    # texte enfant y lit son encre. `scene_color_fills` l'a déjà
                    # calculée ; on la reprend plutôt que de la refaire.
                    "bank": by_container[container.name]["bank"]})
    return out


def scene_region_backdrops(p: Project, scene, img_fills: list[dict]) -> list[dict]:
    """Zones de texte composées SOUS un container nine-slice/background : sans
    ça, `text_surf_prepare` composerait sur du transparent et effacerait le
    cadre à cet endroit au lieu de le garder sous l'encre. Une couleur n'y
    suffirait pas — ce sont les VRAIS pixels du cadre qu'il faut à cet endroit.

    Renvoie une entrée par zone concernée : `{region, fill, dx, dy}` — `fill`
    est l'INDEX de son container ancêtre dans `img_fills` (déjà émis par
    `scene_image_fills`, réutilisé tel quel, jamais dupliqué) ; `dx, dy` le
    coin de la zone DANS la carte de ce container, en tuiles. Le runtime lit
    directement la carte du container avec cet offset (cf. `RegionFill` dans
    `gba_engine.h`) plutôt que de recevoir une carte à la taille de la zone :
    une donnée, pas deux à tenir d'accord."""
    from core.models.ui_region import KIND_TEXT, FILL_NINE, FILL_BG
    if not img_fills:
        return []
    by_container = {f["name"]: i for i, f in enumerate(img_fills)}
    slot_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    out: list[dict] = []
    for lay, el in p.scene_ui_slots(scene):
        if getattr(el, "kind", "") != KIND_TEXT or el.name not in slot_idx:
            continue
        container = region_fill_container(lay, el)
        if container is None or getattr(container, "fill_kind", "") not in (FILL_NINE, FILL_BG):
            continue
        if container.name not in by_container:
            continue
        fi = by_container[container.name]
        f = img_fills[fi]
        rx, ry, _ = lay.absolute_origin(el, lambda _n: None)
        rx -= rx % 8
        ry -= ry % 8
        rtx, rty = rx // 8, ry // 8
        rw = max(1, (el.w + 7) // 8)
        rh = max(1, (el.h + 7) // 8)
        dx, dy = rtx - f["tx"], rty - f["ty"]
        # Zone qui déborde de son container (authoring incohérent) : rien à
        # enregistrer — le texte retombe alors sur la banque de sa police.
        if dx < 0 or dy < 0 or dx + rw > f["w"] or dy + rh > f["h"]:
            continue
        out.append({"region": slot_idx[el.name], "name": el.name,
                    "fill": fi, "dx": dx, "dy": dy})
    return out


def region_ink_bank(p: Project, scene, el) -> "tuple[int, str] | None":
    """La banque HW (0-15) où l'encre ET le surlignement de CETTE zone
    s'indexent quand le build la lie à un conteneur à fond, avec le nom du
    conteneur — ou None si la zone lit la banque de sa police (texte libre).

    C'est `RegionFill.bank` du runtime, exposé pour ses relecteurs de l'éditeur
    (l'inspecteur et l'aperçu du canvas) : plutôt que de reconstruire les
    conditions d'émission (cible BG, ancrage écran, palette active, 8bpp,
    débordement de zone), on lit ce que `scene_region_colors` /
    `scene_region_backdrops` émettent VRAIMENT pour elle. Une seule vérité,
    celle de la ROM."""
    name = el.name
    cfills, _ = scene_color_fills(p, scene)
    for rc in scene_region_colors(p, scene, cfills):
        if rc["name"] == name:
            return rc["bank"], rc["container"]
    ifills, _ = scene_image_fills(p, scene)
    for rb in scene_region_backdrops(p, scene, ifills):
        if rb["name"] == name:
            fi = ifills[rb["fill"]]
            return fi["bank"], fi["name"]
    return None


def gen_ui_texts(p: Project, scene, text_bg: int, emit=None) -> list[str]:
    """Appels `text_draw_in` des textes AUTHORÉS de la mise en page d'une scène.

    Le build émet exactement l'appel que l'auteur aurait tapé — même fonction,
    même table, même index. Pas de chemin de rendu « statique » séparé : un
    script peut réécrire le même slot ensuite (`interface.draw_text`), dernier
    écrivain gagne.

    Posé une seule fois, à l'init : un texte qui doit CHANGER est le travail
    d'un script.
    """
    from core.models.ui_region import KIND_TEXT, ANCHOR_ACTOR, TARGET_OBJ

    # Index PROJET-GLOBAUX : `g_ui_regions` suit l'ordre de `all_regions()`,
    # `g_texts` celui de `build_texts()`. Recalculés ici plutôt que reçus, pour
    # lire les mêmes listes que les émetteurs de tables — deux vues divergentes
    # écriraient le bon texte dans la mauvaise zone, sans casser le link.
    slot_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    text_idx = {t.key: i for i, t in enumerate(
        p.build_texts() if hasattr(p, "build_texts") else getattr(p, "texts", []))}
    rm = int(getattr(scene, "render_mode", 0) or 0)

    L: list[str] = []
    for lay, el in p.scene_ui_slots(scene):
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        key = getattr(el, "text_key", "") or ""
        if not key:
            continue          # le validateur le signale déjà, et mieux
        if key not in text_idx or el.name not in slot_idx:
            if emit:
                emit("log_line", f"[warn] text '{el.name}': key '{key}' not found in the table"
                                 " — nothing will be written.")
            continue
        target = lay.resolved_target(el, rm)
        # Cible BG sans layer de texte : `text_set_layer(-1)` fait sortir le
        # rendu sans un mot, et l'élément disparaît entre le canvas et la ROM.
        if target != TARGET_OBJ and text_bg not in (0, 1, 2, 3):
            if emit:
                emit("log_line",
                     f"[warn] text '{el.name}': scene '{scene.name}' has no text layer (Text BG), it "
                     "will not be displayed.")
            continue
        if lay.effective_anchor(el)[0] == ANCHOR_ACTOR:
            if emit:
                emit("log_line",
                     f"[warn] text '{el.name}': anchored on an actor but placed only once at"
                     " init — it will not follow the actor. Use a zone and a script "
                     "for that.")
        L.append(f"    text_draw_in({slot_idx[el.name]}, {text_idx[key]});"
                 f"   /* texte authoré '{el.name}' = '{key}' */")
    if L and emit:
        emit("log_line", f"[text] scene '{scene.name}': {len(L)} authored text(s) written at init")
    return L


def scene_color_fills(p: Project, scene) -> tuple[list[dict], list[int]]:
    """Fonds COULEUR des conteneurs d'une scène → (fills, indices).

    1re tranche : uniquement les conteneurs à fond `color`, cible BG, root ancré
    ÉCRAN (position fixe — le monde défile, l'OBJ n'a pas de tilemap). Chaque
    fond : rectangle en TUILES (résolu écran), index de couleur, banque de
    palette (= sa place dans `scene.active_bg_palettes`). `indices` = index
    distincts, un par tuile pleine à graver dans le charblock UI."""
    from core.models.ui_region import (
        can_fill, FILL_COLOR, ANCHOR_SCREEN, TARGET_BG)
    if p.scene_ui_bg_slot(scene) not in (0, 1, 2, 3):
        return [], []
    rm = int(getattr(scene, "render_mode", 0) or 0)
    active = list(getattr(scene, "active_bg_palettes", []) or [])
    fills: list[dict] = []
    indices: list[int] = []
    for lay, el in p.scene_ui_elements(scene):
        if not can_fill(el):                                continue
        if getattr(el, "fill_kind", "") != FILL_COLOR:       continue
        if lay.resolved_target(el, rm) != TARGET_BG:         continue
        if lay.effective_anchor(el)[0] != ANCHOR_SCREEN:     continue
        pal = getattr(el, "fill_palette", "")
        if pal not in active:                                continue  # non active
        x, y, _ = lay.absolute_origin(el, lambda _n: None)
        tx, ty = x // 8, y // 8
        tw = max(1, (x - tx * 8 + el.w + 7) // 8)
        th = max(1, (y - ty * 8 + el.h + 7) // 8)
        idx = int(getattr(el, "fill_index", 0) or 0) & 0xF
        if idx not in indices:
            indices.append(idx)
        fills.append({"name": el.name, "tx": tx, "ty": ty, "w": tw, "h": th,
                      "index": idx, "bank": active.index(pal),
                      "slot": int(lay.bg_slot)})   # slot BG du nœud (routage v0.12)
    return fills, indices


# Cellule « rien à dessiner » d'un fond image. Doit rester égale à UI_SE_EMPTY
# de gba_engine.h : le runtime y reconnaît la sentinelle AVANT d'ajouter la base
# de tuiles, et pose une case vide.
UI_SE_EMPTY = 0xFFFF


def scene_image_fills(p: Project, scene) -> tuple[list[dict], list[dict]]:
    """Fonds IMAGE (nine-slice, background) des conteneurs d'une scène.

    Renvoie (fills, assets) :
      fills  — un par conteneur : rectangle en TUILES + la liste des screen
               entries à écrire (palette déjà rebasée sur les banques HW).
      assets — les BackgroundAsset sources, dédupliqués et ORDONNÉS ; le codegen
               leur attribue une base de tuiles dans le charblock d'UI, dans cet
               ordre, et les `se` citent des index LOCAUX que le runtime décale
               de cette base.

    Même périmètre que `scene_color_fills` (cible BG, root écran) : le monde
    défile et l'OBJ n'a pas de tilemap. Les marges d'un nine-slice sont ramenées
    à la TUILE — une tilemap ne sait pas couper un cadre à 3 px."""
    from core.models.ui_region import (
        can_fill, FILL_NINE, FILL_BG, ANCHOR_SCREEN, TARGET_BG)
    from core.nine_slice import nine_slice_rects
    from core.models.tile_codec import unpack_se, pack_se
    from codegen.palette_alloc import scene_bank_layout

    if p.scene_ui_bg_slot(scene) not in (0, 1, 2, 3):
        return [], []
    rm = int(getattr(scene, "render_mode", 0) or 0)
    bank_layout = scene_bank_layout(p, scene, "bg")
    fills: list[dict] = []
    assets: list[dict] = []
    by_name: dict[str, int] = {}      # nom d'asset -> index dans `assets`

    for lay, el in p.scene_ui_elements(scene):
        if not can_fill(el):                                continue
        fk = getattr(el, "fill_kind", "")
        if fk not in (FILL_NINE, FILL_BG):                   continue
        if lay.resolved_target(el, rm) != TARGET_BG:         continue
        if lay.effective_anchor(el)[0] != ANCHOR_SCREEN:     continue

        # Source : le fond cité, dans les deux modes. Un cadre étirable est un
        # BackgroundAsset de kind `ui` qui porte ses propres marges de découpe —
        # il n'y a plus d'asset de cadre à déréférencer entre les deux.
        src_name = getattr(el, "fill_asset", "")
        ba = p.get_background(src_name) if src_name else None
        if ba is None or not getattr(ba, "tileset", None):    continue
        if getattr(ba, "bpp", 4) == 8:                        continue  # cf. layers 8bpp
        pal_offset = bank_layout.bg_block_offset(ba)
        if pal_offset is None:                                continue  # pas de banques

        x, y, _ = lay.absolute_origin(el, lambda _n: None)
        tx, ty = x // 8, y // 8
        w = max(1, (x - tx * 8 + el.w + 7) // 8)
        h = max(1, (y - ty * 8 + el.h + 7) // 8)
        sw, sh = max(1, ba.tiles_w), max(1, ba.tiles_h)
        src_map = ba.effective_tilemap()

        def src_se(sc: int, sr: int) -> int:
            """SE source rebasée sur les banques HW, ou UI_SE_EMPTY hors image.

            Sentinelle plutôt que 0 : le runtime AJOUTE la base de tuiles de
            l'asset, donc un 0 y désignerait sa PREMIÈRE tuile au lieu de
            « rien à dessiner »."""
            if not (0 <= sc < sw and 0 <= sr < sh):
                return UI_SE_EMPTY
            cell = sr * sw + sc
            if cell >= len(src_map):
                return UI_SE_EMPTY
            tid, pb, fh, fv = unpack_se(src_map[cell])
            return pack_se(tid, pb + pal_offset, fh, fv)

        se = [UI_SE_EMPTY] * (w * h)
        if fk == FILL_BG:
            # Image posée en haut-gauche, ROGNÉE bas/droite — une fenêtre sur le
            # fond, jamais un étirement (même règle que l'aperçu éditeur).
            for r in range(h):
                for c in range(w):
                    se[r * w + c] = src_se(c, r)
        else:
            # Coins fixes, bords/centre RÉPÉTÉS. La géométrie est celle de
            # `core.nine_slice`, en unités de TUILE plutôt qu'en pixels.
            ml, mr, mt, mb = ba.slice_margins_tiles()
            for z in nine_slice_rects(sw, sh, ml, mr, mt, mb, w, h):
                sx, sy, s_w, s_h = z["src"]
                dx, dy, d_w, d_h = z["dst"]
                for r in range(d_h):
                    for c in range(d_w):
                        cc = (c % s_w) if z["tile"] else min(c, s_w - 1)
                        rr = (r % s_h) if z["tile"] else min(r, s_h - 1)
                        se[(dy + r) * w + (dx + c)] = src_se(sx + cc, sy + rr)

        if ba.name not in by_name:
            from codegen.bg_emit import tileset_words
            words = tileset_words(ba.tileset, 4)   # 8 mots u32 = 1 tuile 4bpp
            by_name[ba.name] = len(assets)
            assets.append({"name": ba.name, "sym": f"ui_bg_{c_sym(ba.name)}",
                           "words": words, "tiles": len(words) // 8})
        fills.append({"name": el.name, "tx": tx, "ty": ty, "w": w, "h": h,
                      "asset": by_name[ba.name], "se": se, "bank": pal_offset,
                      "slot": int(lay.bg_slot)})   # slot BG du nœud (routage v0.12)
    return fills, assets
