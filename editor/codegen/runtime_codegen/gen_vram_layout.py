"""runtime_codegen/gen_vram_layout.py — le placement VRAM des fonds d'une scène, posé une fois sur la scène.

`scene_init` et `scene_tick` relisent ce placement (posé par `apply_vram_layout`), ils ne le recalculent pas."""
from __future__ import annotations

from codegen.palette_alloc import effective_palette_colors
from core.models.palette import OWN_PAL_BANK


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


def apply_vram_layout(p, scene, bgi: list[dict], res: dict) -> None:
    """Remplace le placement historique des maps par celui de l'allocateur.

    Écrit `sbb` sur place, et mémorise le placement du texte sur la scène pour
    que `gen_scene_init` le retrouve — les deux doivent voir EXACTEMENT la même
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
    scene._vram_layout = lay   # consommé par gen_scene_init
    scene._ui_fills = res["fills"]
    scene._ui_fill_indices = res["fill_indices"]
    scene._ui_mono_tiles = res["mono_tiles"]
    scene._ui_needs_surface = res["needs_surface"]
    scene._ui_img_fills = res["img_fills"]
    scene._ui_img_assets = res["img_assets"]
    scene._ui_images = res["ui_images"]
    scene._ui_image_layout = res["img_layout"]
    scene._ui_reservation = res   # relu par le log de build


def log_vram_layout(scene, emit) -> None:
    """Dit où l'allocateur a posé le bloc du texte, et pourquoi le cas échéant.

    Émis à CHAQUE build et pas seulement en repli : c'est la première chose
    qu'on cherche quand un fond ne rentre plus."""
    lay = getattr(scene, "_vram_layout", None)
    if lay is None or emit is None:
        return
    budget = ", ".join(f"BG{s}:{n}" for s, n in sorted(lay.budget.items()))
    emit("log_line",
         f"[vram] scene '{scene.name}': text in CBB{lay.text_cbb} base {lay.text_base}, map SBB{lay.text_sbb} — {lay.note}"
         + (f" — tile budget {budget}" if budget else ""))

    # Sur quelle base la place a été réservée : un repli sur tout le projet est
    # un choix de l'outil, sinon on cherche pourquoi le décor a moins de tuiles.
    res = getattr(scene, "_ui_reservation", None)
    if not res:
        return
    names = res.get("font_names")
    if names is None:
        why = ("all the project fonts — a font is chosen at run time (non-literal "
               "text.set_font) or a script could not be analysed")
    else:
        why = "fonts" + (", ".join(sorted(names)) if names else "(none)")
    # Nommer la police par défaut : c'est elle qui est chargée même dans une
    # scène sans une ligne de texte, et un `Scene.font_name` introuvable retombe
    # en silence sur la première du projet. Relue depuis la réservation, pas
    # recalculée — le log doit dire ce qui a RÉELLEMENT servi à réserver.
    _dn = res.get("default_font") or ""
    emit("log_line",
         f"[vram] scene '{scene.name}': {res['total']} tile(s) reserved for text ({res['mono_tiles']} of glyphs — {why}"
         + (f" — default {_dn}" if _dn else "") + ")")


def layer_base_bank(p, scene, bi: dict, bg_layout) -> int:
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
    png = p.background_image_path(ba, bi['stem'])
    colors = effective_palette_colors(p, OWN_PAL_BANK, png, scene.active_bg_palettes)
    return bg_layout.bank_index(OWN_PAL_BANK, colors) or 0
