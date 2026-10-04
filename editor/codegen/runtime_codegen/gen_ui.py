"""codegen/runtime_codegen/gen_ui.py — l'émetteur des tables d'interface au niveau PROJET.

Extrait de `main_gen` (A3), au-dessus de la couche de requêtes (il consomme
`ui_item_geometry` de `gen_scene_query`, vers le bas). Les tables PARTAGÉES par
toutes les scènes : `g_ui_images` (images d'interface), `g_ui_lists` + son état
vivant (navigation, ROADMAP v0.22), `g_ui_elements` (visibilité). Plus les deux
index qui font le lien nom→index avec le C de script : `ui_element_index`
(`UIELEM_*`) et `region_actor_index` (zones ancrées sur un acteur).

Ce qui touche à la COMPOSITION de texte (region_is_composited, scene_region_*,
_gen_ui_texts, _obj_text_alloc) reste dans main_gen, en attendant `gen_text` :
c'est de l'analyse texte, pas de la table d'interface. `_ui_images_lines` reste
aussi côté main_gen — c'est de la glue qui a besoin de `_obj_text_alloc`, et qui
appelle `emit_ui_images_c` d'ici.
"""
from __future__ import annotations

from core.project import Project
from core.diagnostic import build_warning
from codegen.c_names import sym as c_sym
from codegen.runtime_codegen.gen_scene_query import ui_item_geometry


def emit_ui_images_c(p: Project, sprite_offsets: dict, obj_place: dict,
                     actor_index: dict | None = None,
                     elem_index: dict | None = None, emit=None) -> list[str]:
    """Table `g_ui_images` — une entrée par image du projet, dans l'ordre de
    `Project.all_images()`, qui fait l'index (donc la constante `IMAGE_*`).

    Ce que l'entrée porte, et ce qu'elle NE porte pas : la géométrie, la cible,
    l'état de départ, et des POINTEURS vers les tables d'animation du sprite —
    les mêmes que celles des acteurs (`sprite_X_anim_dirs`, `_state_start`,
    `_state_speed`, `_state_loop`). Ni vitesse ni liste de frames recopiées :
    l'image désigne un sprite, elle ne le redéfinit pas.

    La base de tuiles est celle de l'OBJ VRAM (`sprite_offsets`), valable pour
    une image en cible OBJ. Une image BG lit une AUTRE base, posée par
    `scene_init` (`ui_image_set_bg_base`) : elle dépend du charblock alloué à la
    scène, et la table, elle, est partagée par toutes les scènes.

    Une image sans sprite résoluble sort une entrée NEUTRE plutôt que d'être
    omise : l'index doit rester celui de `all_images()`, sinon `IMAGE_*` désigne
    l'élément d'à côté. Le runtime la voit `n_states == 0` et ne dessine rien."""
    rows: list[str] = []
    images = p.all_images() if hasattr(p, "all_images") else []
    for lay, im in images:
        sprite = p.get_buildable_sprite(getattr(im, "sprite_name", "") or "")
        eff_anchor, eff_actor = lay.effective_anchor(im)
        from core.models.ui_region import ANCHORS, TARGET_OBJ
        target_obj = lay.resolved_target(im) == TARGET_OBJ
        # Position SOMMÉE à travers les parents, sans le socle acteur (le runtime
        # l'ajoute) — cf. `emit_ui_regions_c`. En OBJ aussi : un enfant sans cette
        # somme ignorait l'offset de son conteneur et se posait au mauvais endroit.
        x, y, _res = lay.absolute_origin(im, None)
        if not target_obj:
            x -= x % 8
            y -= y % 8
        elem = (elem_index or {}).get(im.name, -1)
        if sprite is None or not sprite.asset:
            rows.append(f"    {{ {x}, {y}, {im.w}, {im.h}, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, "
                        f"0, 0, 0, 1, 1, 0, {elem} }},  /* {im.name} — no sprite */")
            if emit:
                emit("log_line", f"[ui] image '{im.name}': no sprite — nothing will be drawn"
                                 " at this place.")
            continue
        ss = f"sprite_{c_sym(sprite.name)}"
        n_states = max(1, len(getattr(sprite, "states", []) or []))
        st0 = im.state_index(sprite)
        base = sprite_offsets.get(sprite.name, 0)
        pl = obj_place.get(im.name) if target_obj else None
        oam_rel = pl["oam_rel"] if pl else 0
        # `w`/`h` de la table sont ceux de la FRAME, pas du rectangle : c'est ce
        # que le matériel dessine, et le pavage se dit en `cols`/`rows`. Pour un
        # UIImage les deux coïncident (cf. sync_size_from) ; pour un conteneur non.
        g = ui_item_geometry(im, sprite, 1)
        # Priorité HÉRITÉE : -1 (défaut / fond de container) devient 255, la
        # sentinelle que `ui_obj_prio` résout à la volée sur l'acteur ancré ;
        # 0-3 restent une surcharge explicite. Cf. `UIImage.priority`.
        prio = 255 if int(getattr(im, "priority", -1)) < 0 else (im.priority & 3)
        rows.append(
            f"    {{ {x}, {y}, {g['frame_w']}, {g['frame_h']}, "
            f"{1 if target_obj else 0}, "
            f"{ANCHORS.index(eff_anchor)}, {(actor_index or {}).get(im.name, -1)}, "
            f"{ss}_anim_dirs, {ss}_state_start, {ss}_state_speed, {ss}_state_loop, "
            f"{n_states}, {st0}, {1 if im.playing else 0}, "
            f"{base}, {sprite.tiles_per_frame}, {oam_rel}, {prio}, "
            f"{g['cols']}, {g['rows']}, {int(getattr(im, 'anim_speed', 0) or 0)}, "
            f"{elem} }},"
            f"  /* {im.name} — {sprite.name}"
            + (f", pavage {g['cols']}×{g['rows']}"
               if g['cols'] * g['rows'] > 1 else "") + " */")
        if emit and eff_anchor == "actor" and (actor_index or {}).get(im.name, -1) < 0:
            # Même angle mort que pour une zone de texte : sans acteur résolu,
            # l'image se pose à l'origine de l'écran, ce qui ressemble à un bug
            # de placement plutôt qu'à une référence introuvable.
            emit("diagnostic", build_warning(
                f"image '{im.name}': anchored on actor '{eff_actor or '(none)'}', which was not found in"
                " the scene — it will be placed at the screen origin.", "ui"))
    L = ["/* ── Images d'interface (UILayout) ─────────────── */"]
    L.append(f"const UIImageInfo g_ui_images[{max(1, len(rows))}] = {{")
    L += rows or ["    { 0, 0, 8, 8, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1,"
                  " 0, -1 },   /* no image */"]
    L.append("};")
    L.append(f"const int g_ui_image_count = {len(rows)};")
    L.append("")
    return L


def ui_element_index(p: Project) -> dict:
    """{nom d'élément : index dans `Project.all_elements()`} — l'index de la
    table de visibilité plate (`UIELEM_*`, `g_ui_elements`). Même ordre que
    celui utilisé par `codegen.py` pour les `#define` de script, donc la
    même constante des deux côtés du link."""
    return {e.name: i for i, (_lay, e) in enumerate(
        p.all_elements() if hasattr(p, "all_elements") else [])}


def project_lists(p: Project) -> list:
    """[(mise en page, liste)] des `UIList` du projet, ordre stable.

    Le même ordre que `all_elements` — mises en page, puis éléments — donc
    l'index d'une liste est une constante du build, `UILIST_<NOM>`."""
    from core.models.ui_region import KIND_LIST
    return [(lay, e) for lay, e in
            (p.all_elements() if hasattr(p, "all_elements") else [])
            if getattr(e, "kind", "") == KIND_LIST]


def list_rows_of(lay, lst) -> list:
    """Les RANGÉES d'une liste : ses zones de texte enfants, dans l'ordre de la
    mise en page. Rien à déclarer — ce qu'on voit dans l'éditeur est ce que la
    liste parcourt (ROADMAP v0.22)."""
    from core.models.ui_region import KIND_TEXT
    return [e for e in lay.elements
            if getattr(e, "parent", "") == lst.name
            and getattr(e, "kind", "") == KIND_TEXT]


def emit_ui_lists_c(p: Project, emit=None) -> list[str]:
    """Tables des listes d'interface + leur état vivant (ROADMAP v0.22).

    Émises MÊME VIDES : `gba_engine.h` les déclare `extern` sans condition, et
    un projet sans liste doit tout de même se lier — c'est `g_ui_list_count`
    qui dit au moteur qu'il n'y a rien à parcourir. Même règle que les tables
    de sauvegarde.

    `g_ui_list_total` initial = le nombre de RANGÉES authorées, pas 0 — sinon
    un menu STATIQUE (un sélecteur de langue, un menu principal : items ==
    rangées, jamais de défilement) resterait figé tant que le script n'a pas
    répété une information déjà posée dans le canvas. `list.set_count` garde
    tout son sens dès que le total dépasse les rangées visibles (inventaire
    qui défile) : il écrase ce défaut, il ne comble plus un zéro."""
    from core.models.ui_region import KIND_IMAGE, NAV_ROW, CURSOR_SLIDE
    lists = project_lists(p)
    L = ["", "/* Interface lists — navigation, not layout */"]
    regions = {name: i for i, name in enumerate(p.region_names())}
    # Index d'IMAGE, celui de `g_ui_images` et donc de `IMAGE_*` : c'est par là
    # que la liste désigne son curseur. Le même ordre que `emit_ui_images_c`,
    # sans quoi elle en déplacerait un autre.
    images = {im.name: i for i, (_l, im) in
              enumerate(p.all_images() if hasattr(p, "all_images") else [])}
    # Index d'ÉLÉMENT (celui de `g_ui_elements`, donc de `UIELEM_*`) : c'est ce que la
    # liste rend quand on la traite comme un simple élément — `menu:hide()`.
    elements = {el.name: i for i, (_l, el) in enumerate(
        p.all_elements() if hasattr(p, "all_elements") else [])}
    rows_flat: list[int] = []
    row_counts: list[int] = []
    actives: list[int] = []
    infos: list[str] = []
    # Cadence par DÉFAUT du projet, qu'une liste peut surcharger — même
    # politique d'héritage que la transition de scène (v0.6.2). Trois listes à
    # trois cadences est une incohérence qu'un joueur sent.
    d_delay = int(getattr(p.settings, "list_repeat_delay", 10) or 10)
    d_rate = int(getattr(p.settings, "list_repeat_rate", 4) or 4)
    for lay, lst in lists:
        rows = list_rows_of(lay, lst)
        row0 = len(rows_flat)
        rows_flat += [regions.get(r.name, -1) for r in rows]
        row_counts.append(len(rows))
        actives.append(1 if getattr(lst, "active", True) else 0)
        delay = int(getattr(lst, "repeat_delay", 0) or 0) or d_delay
        rate = int(getattr(lst, "repeat_rate", 0) or 0) or d_rate
        # Le curseur est un `UIImage` de LA MÊME mise en page : une liste qui
        # bougerait l'image d'une autre page déplacerait quelque chose que
        # l'auteur ne voit pas à côté d'elle. -1 = pas de curseur, la sélection
        # se lit alors au surlignement.
        cur_name = str(getattr(lst, "cursor_image", "") or "")
        cur_el = lay.get(cur_name) if cur_name else None
        cursor = images.get(cur_name, -1) \
            if getattr(cur_el, "kind", "") == KIND_IMAGE else -1
        if emit and cur_name and cursor < 0:
            emit("diagnostic", build_warning(
                f"list '{lst.name}': cursor '{cur_name}' not found in layout '{lay.name}' — the "
                "list navigates without a cursor.", "ui"))
        infos.append(
            "{" + f"{len(rows)}, "
            f"{max(1, min(255, int(getattr(lst, 'nav_columns', 1) or 1)))}, "
            f"{1 if getattr(lst, 'nav_major', '') == NAV_ROW else 0}, "
            f"{1 if getattr(lst, 'wrap', True) else 0}, "
            f"{max(0, min(255, delay))}, {max(0, min(255, rate))}, {row0}, "
            f"{cursor}, "
            f"{1 if getattr(lst, 'cursor_mode', '') == CURSOR_SLIDE else 0}, "
            f"{max(1, min(255, int(getattr(lst, 'cursor_speed', 2) or 2)))}, "
            f"{int(getattr(lst, 'selected_text_color', 0) or 0)}, "
            f"{int(getattr(lst, 'selected_highlight_color', 0) or 0)}, "
            f"{elements.get(lst.name, -1)}"
            + "}" + f"   /* {lst.name} — {len(rows)} row(s) */")
        if emit and not rows:
            emit("diagnostic", build_warning(
                f"list '{lst.name}': no child text zone, hence no row to display. A "
                "list walks the text zones placed INSIDE its container.", "ui"))
    n = len(lists)
    L.append("const UIListInfo g_ui_lists[] = {"
             + (", ".join(infos) if infos else "{0,1,0,0,0,0,0,-1,0,1,0,0,-1}") + "};")
    L.append("const short g_ui_list_rows[] = {"
             + (", ".join(str(r) for r in rows_flat) if rows_flat else "0") + "};")
    L.append(f"const int g_ui_list_count = {n};")
    z = ", ".join(["0"] * n) if n else "0"
    one = ", ".join(["1"] * n) if n else "0"
    act = ", ".join(str(a) for a in actives) if actives else "0"
    # Le total démarre au compte de RANGÉES authorées, pas à 0 : un menu
    # STATIQUE (items == rangées, jamais de défilement — un sélecteur de
    # langue, un menu principal) navigue alors sans une ligne de script.
    # `list.set_count` reste le seul moyen de dire un total PLUS GRAND que
    # les rangées visibles (un inventaire qui défile) — il écrase ce défaut
    # au lieu de partir de zéro, jamais un cas spécial à distinguer ici.
    totals = ", ".join(str(n) for n in row_counts) if row_counts else "0"
    L.append(f"int g_ui_list_index[] = {{{one}}};")
    L.append(f"int g_ui_list_first[] = {{{one}}};")
    L.append(f"int g_ui_list_total[] = {{{totals}}};")
    L.append(f"int g_ui_list_timer[] = {{{z}}};")
    # `active` est un état VIVANT comme l'index : la valeur authorée n'est que
    # son point de départ, `list.set_active` décide ensuite. Une liste inactive
    # reste dessinée — c'est la sélection qu'on coupe, pas l'affichage.
    L.append(f"int g_ui_list_active[] = {{{act}}};")
    # Rangée affichée qui porte la sélection au dernier restyle, 0 = aucune :
    # `ui_list_sync_style` s'en sert pour rendre l'ancienne à son style. Zéro au
    # départ, la première frame posant le style de la rangée courante.
    L.append(f"int g_ui_list_shown[] = {{{z}}};")
    # Le texte posé sur chaque rangée, à plat comme `g_ui_list_rows` (-1 = rien
    # d'écrit). Rempli par `text_draw_in` — c'est ce qui permet à la liste de
    # redessiner une rangée quand la sélection la quitte ou l'atteint.
    L.append("short g_ui_list_row_text[] = {"
             + (", ".join(["-1"] * len(rows_flat)) if rows_flat else "-1") + "};")
    for i, (_lay, container) in enumerate(lists):
        L.append(f"#define UILIST_{c_sym(container.name).upper()} {i}")
    if emit and n:
        L.insert(1, "")
        emit("log_line", f"[ui] {n} liste(s) de navigation")
    L.append("")
    return L


def emit_ui_elements_c(p: Project) -> list[str]:
    """Table `g_ui_elements` — un `{parent, visible}` par élément du projet,
    dans l'ordre de `Project.all_elements()`, qui fait l'index (`UIELEM_*`).

    `parent` référence un AUTRE index de CETTE MÊME table (-1 = racine) : la
    visibilité effective se recalcule au runtime en la remontant
    (`ui_element_is_visible`), elle n'est jamais stockée — même règle que le
    modèle Python (`UILayout.is_visible`, jamais propagée aux enfants)."""
    elements = p.all_elements() if hasattr(p, "all_elements") else []
    index = ui_element_index(p)
    rows: list[str] = []
    for lay, e in elements:
        parent = getattr(e, "parent", "") or ""
        parent_idx = index.get(parent, -1) if lay.get(parent) is not None else -1
        rows.append(f"    {{ {parent_idx}, {1 if getattr(e, 'visible', True) else 0} }},"
                    f"  /* {e.name} */")
    L = ["/* ── Interface element visibility (UILayout) ───────── */"]
    L.append(f"const UIElementInfo g_ui_elements[{max(1, len(rows))}] = {{")
    L += rows or ["    { -1, 1 },   /* no element */"]
    L.append("};")
    L.append(f"const int g_ui_element_count = {len(rows)};")
    L.append("")
    return L


def region_actor_index(p: Project) -> dict:
    """{nom de zone: index global dans g_actors} pour les zones ancrées actor.

    Résolu contre la PREMIÈRE scène qui référence la mise en page. Une mise en
    page partagée par deux scènes où l'acteur n'a pas le même index global
    donnerait deux réponses ; on prend la première et on le signale, plutôt que
    d'ajouter une indirection par scène pour un cas qui n'existe pas encore
    (une bulle est en pratique dans la mise en page de sa scène)."""
    out: dict = {}
    offset = 0
    for scene in p.scenes:
        actors = [a for a in getattr(scene, "actors", [])]
        names = {a.name: offset + i for i, a in enumerate(actors)}
        # Textes ET images de TOUS les nœuds `Interface` de la scène : toutes deux
        # se posent au pixel quand elles suivent un acteur, et un second index les
        # ferait diverger.
        for lay, r in p.scene_ui_slots(scene) + p.scene_ui_images(scene):
            # L'ancrage vient du NŒUD (un enfant en hérite), plus de l'élément
            # lui-même — cohérent avec l'éditeur.
            eff_anchor, eff_actor = lay.effective_anchor(r)
            if eff_anchor == "actor" and r.name not in out:
                out[r.name] = names.get(eff_actor, -1)
        offset += len(actors)
    return out
