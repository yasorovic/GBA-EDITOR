"""runtime_codegen/gen_pool.py — le C des instances d'un modèle de prefab : le spawn, la composition de la hiérarchie
(parent, enfant) et le nom du symbole qui répond d'un acteur.

`scene_pi` est la liste des pools d'une scène, lue de `oam_alloc.scene_oam_layout`."""
from __future__ import annotations

from codegen.c_names import scene_actor_sym, sym as c_sym
from codegen.oam_alloc import scene_oam_layout
from codegen.runtime_codegen.gen_appearance import appearance_layout
from codegen.runtime_codegen.gen_scene_query import parent_depths
from codegen.runtime_codegen.interact_gen import owner_boxes
from core.models.components import CollisionBoxComponent
from core.models.field_value import (
    FieldValue as _FV, number_value as _number_value, var_names_from_project as _var_names,
)
from core.models.palette import OWN_PAL_BANK
from core.models.scene import Scene
from core.project import Project
import math
from codegen.runtime_codegen.gen_affine import affine_init_lines, pool_affine
from codegen.runtime_codegen.gen_appearance import appearance_init_lines
from codegen.runtime_codegen.gen_sfx_trigger import sfx_trigger_info
from codegen.runtime_codegen.gen_sprite import initial_state_rank, shown


def scene_pi(p: Project, scene: Scene) -> list[dict]:
    """La géométrie des pools de CETTE scène, lue de `scene_oam_layout` (source
    de vérité unique). `sym` est PRÉFIXÉ PAR LA SCÈNE
    (`<Scène>_<Prefab>`) : chaque scène compile ses unités de prefab contre sa
    propre plage, donc les appels `{sym}_pool_init`/`{sym}_on_update` du main.c
    ciblent bien `actor_<Scène>_<Prefab>.c`."""
    lay = scene_oam_layout(p, scene)
    sh = lay.shared
    spool = ({"start": sh.start, "end": sh.end, "entry_start": sh.entry_start, "entries": sh.entries}
             if sh else None)
    return [
        {"prefab": pl.prefab, "sym": pl.sym, "prefab_sym": pl.prefab_sym,
         # Un modèle que la scène fait naître : il vit dans `spool` et se reconnaît à `Actor.model`
         # (= `model_id`, ou `model_id + k` pour sa partie k).
         "shared": pl.shared, "model_id": pl.model_id, "spool": spool,
         "member_entries": pl.member_entries, "group": pl.group,
         # Les acteurs POSÉS qui sont des instances de ce modèle (indices dans `scene_actors`), chacun
         # avec son entrée d'état d'affichage. Premières lignes de la table du modèle ; ils gardent leur
         # emplacement et leur entrée de scène.
         "members": list(pl.members),
         "member_entries_of": [lay.placed_entry[j] for j in pl.members]}
        for pl in lay.pools
    ]


def dispatch_sym(scene, scene_actors: list, pi: list[dict]):
    """Le symbole C dont le code d'un acteur posé s'appelle : le sien, ou celui de son MODÈLE s'il en est
    une instance (un membre n'a pas de code à lui). Seuls les APPELS de scripts (événements,
    collisions, interaction) passent par ici ; `ACTOR_*` et les tables par acteur gardent le nom propre."""
    models = {scene_actors[j][0].name: pl["sym"] for pl in pi for j in pl["members"]}

    def sym_of(scene_name: str, actor_name: str) -> str:
        return models.get(actor_name) or scene_actor_sym(scene_name, actor_name)
    return sym_of


def _shared_spawn_head(s: str, pi: dict, grouped: bool) -> list[str]:
    """La tête du spawn d'un modèle du pool PARTAGÉ : l'emplacement d'une de ses instances posées
    détruite (le même modèle, donc le même code d'affichage), sinon le premier emplacement libre du
    pool de la scène, ou la première SÉRIE libre de la taille du groupe pour un modèle à parties (le script
    atteint la partie k par `self + k`). Le corps qui suit est celui des autres modèles : `if(_i >= 0) { … }`.

    `grouped` : la scène a un modèle à parties dans son pool. Une partie détruite dont la racine vit encore
    garde alors son emplacement (`spool_slot_free`), et pas seulement un `alive` nul."""
    nmem = len(pi["members"])
    group = pi["group"]
    busy = "!spool_slot_free(_k)" if grouped else "g_actors[_k].alive"
    L = [
        f"    int _i = -1, _e = -1, _n = {nmem};",
        *([f"    for(int _m=0; _m<{nmem}; _m++)",
           f"        if(!g_actors[g_model_{s}[_m].slot].alive) {{",
           f"            _n=_m; _i=g_model_{s}[_m].slot; _e=g_model_{s}[_m].entry; break;",
           "        }"] if nmem else []),
        "    if(_i < 0) {",
        "        int _k=g_spool_free;                      /* aucun libre en dessous du curseur */",
        f"        while(_k<g_spool_end && {busy}) _k++;",
        "        g_spool_free=_k;",
    ]
    if group > 1:
        L += [
            "        for(;;) {                                 /* la première série libre de la taille du groupe */",
            f"            if(_k+{group}>g_spool_end) {{ _k=g_spool_end; break; }}",
            "            int _j=0;",
            f"            while(_j<{group} && spool_slot_free(_k+_j)) _j++;",
            f"            if(_j=={group}) break;",
            "            _k+=_j+1;",
            "        }",
        ]
    L += [
        "        if(_k<g_spool_end) {",
        "            _i=_k; _e=(g_spool_entry>=0)?g_spool_entry+(_k-g_spool_start):-1;",
        f"            if(_k+{group}>g_spool_hw) g_spool_hw=_k+{group};",
        *(["            g_spool_free=_k+1;"] if group == 1 else []),
        "        }",
        "    }",
        "    (void)_e; (void)_n;",
        "    {",
        "        if(_i >= 0) {",
    ]
    return L


def section_spawn(pool_info: list[dict], p: Project, obj_layout,
                   actor_defined_events: dict[str, set[str]] | None = None) -> list[str]:
    """`pool_info` : les pools de LA scène courante (`scene_pi`), symboles
    déjà préfixés `<Scène>_<Prefab>`. `obj_layout` : le layout OBJ de CETTE
    scène — chaque scène résout l'index de banque de ses prefabs poolés dans son
    propre layout (plus de « scène d'ancrage »)."""
    if not pool_info:
        return []

    def _def(sym, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    L = ["/* ── Spawn helpers (pooled prefabs) ────────────────────── */"]
    _alay = appearance_layout(p, [], pool_info, obj_layout)   # mêmes numéros que scene_init
    for pi in pool_info:
        s, pf = pi["sym"], pi["prefab"]
        # L'entrée OAM du membre k de l'instance (0 = racine), ou None : un membre
        # sans sprite — marqueur, point de tir — n'a ni entrée ni écriture d'affichage.
        _ranks = pi["member_entries"]
        # Dans le pool partagé, chaque emplacement a son entrée d'état : celle de la partie k est `_e + k`.
        _E = lambda k: (("_e" if k == 0 else f"group_entry(_e, {k})") if _ranks[k] >= 0 else None)
        _e0 = _E(0)
        sp, sprite = shown(p, pf)      # l'apparence de départ fixe les constantes d'init
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(pf, "pal_bank", OWN_PAL_BANK), own) if obj_layout else 0
        if pal is None:
            pal = 0
        boxes = owner_boxes(pf, sprite)

        # `pool_init` sort du script Lua du prefab : sans script, il n'y a rien à initialiser ni à lier.
        from codegen.runtime_codegen.lua_compiler import prefab_lua_script
        has_script = prefab_lua_script(p, pf) is not None
        if has_script:
            L.append(f"extern void {s}_pool_init(Actor* self);")
        # Les instances POSÉES du modèle reçoivent leurs valeurs d'export à l'entrée de scène, par les
        # setters du modèle (comme une instance née d'un spawn avec une table).
        if pi["members"]:
            from codegen.runtime_codegen.lua_compiler import script_exports
            from core.models.components import ScriptComponent
            _sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
            for _name, _meta in (script_exports(p, _sc.script) if _sc and _sc.script else {}).items():
                from scripting.codegen import export_setter_c_type
                L.append(f"extern void {s}_set_{_name}(Actor* self, {export_setter_c_type(_meta['type'])} v);")
        for ev, sig in [
            ("on_start",           f"extern void {s}_on_start(Actor* self);"),
            ("on_update",          f"extern void {s}_on_update(Actor* self);"),
            ("on_late_update",     f"extern void {s}_on_late_update(Actor* self);"),
            ("on_collide",         f"extern void {s}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_enter", f"extern void {s}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_exit",  f"extern void {s}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_tile_collide",    f"extern void {s}_on_tile_collide(Actor* self, int normal_x, int normal_y);"),
            ("on_interact",        f"extern void {s}_on_interact(Actor* self, Actor* who);"),
        ]:
            if _def(s, ev):
                L.append(sig)

        # La table du modèle : l'emplacement et l'entrée d'état de ses instances POSÉES. Le spawn la parcourt
        # avant le pool, `actor:count/get("M", i)` aussi.
        L.append(f"const ModelSlot g_model_{s}[{max(1, len(pi['members']))}] = {{")
        for _j, _ent in zip(pi["members"], pi["member_entries_of"]):
            L.append(f"    {{{_j}, {_ent}}},   /* posé */")
        if not pi["members"]:
            L.append("    {0, -1},   /* aucune instance posée : la table n'est pas lue */")
        L.append("};")
        if not pi["shared"]:
            continue            # aucun script de la scène ne le fait naître : pas de spawn
        L += [
            # Rend un Actor* sur l'instance née : un handle
            # directement chaînable côté script, et NULL quand le pool est plein —
            # là où l'ancien -1, un entier, ressortait TOUJOURS vrai dans un test.
            f"Actor* spawn_{s}(int x, int y) {{",
            *_shared_spawn_head(s, pi, any(m["shared"] and m["group"] > 1 for m in pool_info)),
        ]

        # Transform affine : `(Actor){0}` remet TOUT à zéro, y compris le slot de
        # matrice posé par scene_init et les échelles neutres (256 = ×1). Un
        # prefab affine spawné repartait donc avec une échelle de ZÉRO — matrice
        # dégénérée, sprite illisible — et avec le slot 0, celui d'un autre actor.
        # Le slot appartient à la SCÈNE (il change d'une scène à l'autre) : on le
        # préserve. L'échelle et la rotation appartiennent au PREFAB : on les
        # repose comme au scene_init, c'est-à-dire à l'état neutre du template.
        _sp_aff = pool_affine(p, pf, pf) if sp else None
        _sp_aff = _sp_aff if _e0 else None    # sans entrée, aucun transform d'affichage
        # L'acteur ET son entrée repartent de zéro ; le lien se repose (-1 : sans sprite).
        # La génération survit à la remise à zéro et avance : une référence rangée sur l'occupant
        # précédent de cet emplacement ne désigne plus la nouvelle instance.
        L.append(f"            {{ u16 _g = g_actors[_i].gen; g_actors[_i] = (Actor){{0}}; "
                 f"g_actors[_i].gen = _g + 1; }} g_actors[_i].oam_entry = {_e0 or -1};")
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
                f"            g_actors[_i].rotation     = {_sp_aff['rotation']};",
                f"            g_actors[_i].scale_x      = {_sp_aff['scale_x']};",
                f"            g_actors[_i].scale_y      = {_sp_aff['scale_y']};",
                *affine_init_lines(_sp_aff, _e0, "            "),
            ]
        elif _e0:
            L.append(f"            g_oam_entries[{_e0}].affine_slot = -1;")
        L += [
            # x/y en Q8 en interne. `x`/`y` ici sont les entiers
            # pixels passés à actor:spawn() par le script — <<8 à l'entrée.
            f"            g_actors[_i].x = x<<8; g_actors[_i].y = y<<8;",
            f"            g_actors[_i].active   = 1; g_actors[_i].alive = 1; g_actors[_i].inst = _i;",
            "            pool_bit_set(_i);",
            f"            g_actors[_i].model    = {pi['model_id']};",
            *([f"            g_oam_entries[{_e0}].visible = 1;",
               f"            g_oam_entries[{_e0}].pal_bank = {pal};",
               f"            g_oam_entries[{_e0}].frame_w  = {sprite.frame_w if sprite else 0};",
               f"            g_oam_entries[{_e0}].frame_h  = {sprite.frame_h if sprite else 0};",
               f"            g_oam_entries[{_e0}].anim_state = {initial_state_rank(*shown(p, pf))};",
               # Le regard d'une instance suit son mouvement comme celui d'un acteur de scène
               # (`facing_auto` du sprite affiché) : un prefab « Player » vise dans son regard.
               f"            g_oam_entries[{_e0}].facing_auto = {1 if getattr(sp, 'facing_auto', True) else 0};",
               *appearance_init_lines(p, pf, _e0, "            ",
                                       _alay.member_base.get((pi["sym"], 0)))]
              if _e0 else []),
            # Une instance de la réserve porte l'identité du modèle (début de sa plage) ; l'emplacement
            # d'un acteur posé, qu'un spawn reprend, garde l'identité de la scène (son indice).
            (f"            g_actors[_i].name      = _n < {len(pi['members'])} ? _i : ACTOR_{s.upper()};"
             if pi["members"] else f"            g_actors[_i].name      = ACTOR_{s.upper()};"),
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
        # frame courante (cf. `pool_compose_lines`), et l'écrire deux fois
        # laisserait croire qu'elle vient d'ici.
        for k, part in enumerate(getattr(pf, "children", []) or [], start=1):
            p_sc, p_spr = shown(p, part)
            p_own = list(p_spr.own_palette) if (p_spr and getattr(p_spr, "own_palette", None)) else []
            p_pal = (obj_layout.bank_index(getattr(part, "pal_bank", OWN_PAL_BANK), p_own)
                     if obj_layout else 0) or 0
            p_boxes = [c for c in part.components
                       if isinstance(c, CollisionBoxComponent)][:4]
            _ek = _E(k)      # None : la partie est un marqueur, sans entrée OAM
            L += [
                f"            int _s{k} = group_slot(_i, {k});",
                # Le slot de matrice appartient à la SCÈNE (scene_init le
                # pose) ; `(Actor){0}` l'effacerait, comme il effaçait celui de
                # la racine avant que le même garde-fou soit écrit pour elle.
                *(["            {"] if _ek else []),
                f"            {{ u16 _g = g_actors[_s{k}].gen; g_actors[_s{k}] = (Actor){{0}}; "
                f"g_actors[_s{k}].gen = _g + 1; }} g_actors[_s{k}].oam_entry = {_ek or -1};",
                *([f"            g_oam_entries[{_ek}] = (OamEntry){{0}};",
                   f"            g_oam_entries[{_ek}].affine_slot = -1; }}"] if _ek else []),
                # Échelle neutre avant la première composition : `(Actor){0}`
                # laisse un scale de ZÉRO, donc une matrice dégénérée si l'OAM
                # sortait avant le tick qui recompose.
                f"            g_actors[_s{k}].scale_x = 256; g_actors[_s{k}].scale_y = 256;",
                f"            g_actors[_s{k}].active   = 1; g_actors[_s{k}].alive = 1; g_actors[_s{k}].inst = _s{k};",
                f"            pool_bit_set(_s{k});",
                f"            g_actors[_s{k}].model    = {pi['model_id'] + k};",
                *([f"            g_oam_entries[{_ek}].visible = {1 if getattr(part, 'visible', True) else 0};",
                   f"            g_oam_entries[{_ek}].pal_bank = {p_pal};",
                   f"            g_oam_entries[{_ek}].frame_w  = {p_spr.frame_w if p_spr else 0};",
                   f"            g_oam_entries[{_ek}].frame_h  = {p_spr.frame_h if p_spr else 0};",
                   f"            g_oam_entries[{_ek}].anim_state = {initial_state_rank(p_sc, p_spr)};",
                   *appearance_init_lines(p, part, _ek, "            ",
                                           _alay.member_base.get((pi["sym"], k))),
                   *(affine_init_lines(_pa, _ek, "            ") if (_pa := pool_affine(p, pf, part)) else [])]
                  if _ek else []),
                # La partie porte le tag de sa RACINE : un bras de boss touché,
                # c'est le boss qui est touché. Elle n'est pas un autre type
                # d'acteur, elle est un enfant de celui-là.
                f"            g_actors[_s{k}].name      = ACTOR_{s.upper()};",
                f"            g_actors[_s{k}].collision.box_count = {len(p_boxes)};",
            ]
            for bi, cb in enumerate(p_boxes):
                tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
                _vn = _var_names(p)
                bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
                bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
                L += [
                    f"            g_actors[_s{k}].collision.boxes[{bi}].x=(s8){bx}; g_actors[_s{k}].collision.boxes[{bi}].y=(s8){by};",
                    f"            g_actors[_s{k}].collision.boxes[{bi}].w=(u8){bw};  g_actors[_s{k}].collision.boxes[{bi}].h=(u8){bh};",
                    f"            g_actors[_s{k}].collision.boxes[{bi}].solid={1 if cb.solid else 0}; "
                    f"g_actors[_s{k}].collision.boxes[{bi}].active={1 if cb.active else 0}; "
                    f"g_actors[_s{k}].collision.boxes[{bi}].tag={tag_s};",
                ]
        if has_script:
            L.append(f"            {s}_pool_init(&g_actors[_i]);")
        # SoundFxComponent en trigger="on_spawn" — comme pour les actors de
        # scène ci-dessus, indépendant de tout script sur le prefab.
        sfx_sym, sfx_vol, sfx_trig = sfx_trigger_info(p, pf)
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


def parent_compose_lines(scene_actors: list, actor_offset: int,
                          placed_entry: list[int]) -> list[str]:
    """Recompose, chaque frame, le transform monde des acteurs qui ont un parent.

    La formule n'est PAS nouvelle : c'est celle que le modèle affine applique
    déjà entre un acteur et son sprite,
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

    Tout est en Q8 et l'arrondi reste à l'émission OAM : un
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
    L = ["    /* Actor hierarchy — parents before children, depth",
         "       computed at build. Same composition as that of",
         "       an actor and its sprite, one level up. */"]
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
        p_rot = float(_number_value(getattr(par, "rotation", 0)) or 0)
        p_sx = float(_number_value(getattr(par, "scale_x", 1.0), ref_divisor=100) or 1.0) or 1.0
        p_sy = float(_number_value(getattr(par, "scale_y", 1.0), ref_divisor=100) or 1.0) or 1.0
        dx = float(int(a.x) - int(par.x))
        dy = float(int(a.y) - int(par.y))
        th = math.radians(-p_rot)
        ux = dx * math.cos(th) - dy * math.sin(th)
        uy = dx * math.sin(th) + dy * math.cos(th)
        ox = int(round((ux / p_sx) * 256))
        oy = int(round((uy / p_sy) * 256))
        rot = int(_number_value(getattr(a, "rotation", 0)) or 0) - int(round(p_rot))
        sx = int(round(float(_number_value(getattr(a, "scale_x", 1.0), ref_divisor=100) or 1.0) / p_sx * 256))
        sy = int(round(float(_number_value(getattr(a, "scale_y", 1.0), ref_divisor=100) or 1.0) / p_sy * 256))
        L += [
            f"    {{   /* {a.name} in the frame of {a.parent} */",
            f"        int _pr = g_actors[{p}].rotation;",
            f"        int _px = g_actors[{p}].scale_x, _py = g_actors[{p}].scale_y;",
            f"        int _co, _si; gba_sincos(_pr, &_si, &_co);",
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


def placed_parent_table(scene_actors: list, actor_offset: int):
    """La table `g_placed_parent` d'une scène : pour chaque emplacement de `g_actors[]`, l'emplacement du parent de scène de
    l'acteur posé qui l'occupe, ou -1. Mêmes acteurs que `parent_compose_lines` (un parent inconnu ou un cycle ont été
    refusés avant). None quand aucun acteur n'a de parent : la scène n'émet alors aucune table."""
    depths, _errs = parent_depths(scene_actors)
    idx_of = {a.name: actor_offset + j for j, (a, _) in enumerate(scene_actors)}
    table = [-1] * (actor_offset + len(scene_actors))
    for j, (a, _) in enumerate(scene_actors):
        if getattr(a, "parent", None) and a.name in depths and a.parent in idx_of:
            table[actor_offset + j] = idx_of[a.parent]
    return table if any(v >= 0 for v in table) else None


def _pool_entry_expr(rank: int):
    """Entrée OAM d'un membre de pool dans `pool_compose_lines` : `_eb` est la
    1re entrée de l'instance, `rank` le rang du membre. -1 = aucune."""
    if rank < 0:
        return -1
    return f"group_entry(_eb, {rank})" if rank else "_eb"


def pool_compose_lines(pi: list[dict]) -> list[str]:
    """La composition des enfants d'un prefab segmenté, chaque frame.

    Même formule que pour les acteurs de scène (`parent_compose_lines`), mais
    déroulée sur le POOL : une boucle par instance, et les enfants d'une
    instance sont à un décalage constant de sa racine — le groupe est contigu
    et sa taille est une constante du build.

    Un enfant ÉTEINT ne se compose pas, et il n'est PAS rallumé par sa racine :
    sa vie lui appartient. Un boss qui
    perd un bras appelle `MonBras:destroy()`, et le bras disparaît pour de bon —
    plus d'OAM, plus de collision. Écrire `enfant.active = racine.active` à
    chaque frame, comme la première version le faisait, annulait cet appel dès
    la frame suivante et sans un mot. La racine, elle, éteint tout en mourant :
    c'est la branche du dessus, et les deux règles ne se marchent pas dessus.

    Comme pour un acteur de scène, la pose authorée d'un enfant est du MONDE
    (elle a été placée par rapport au template posé à l'origine) : le local en
    est dérivé ici, une fois, au build."""
    L: list[str] = []
    for p2 in pi:
        pf = p2["prefab"]
        parts = list(getattr(pf, "children", []) or [])
        if not parts or not p2["shared"]:
            continue
        ranks = p2["member_entries"]      # rang d'entrée de chaque membre, -1 si aucun
        by_name = {pt.name: pt for pt in parts}
        rank = {pt.name: k for k, pt in enumerate(parts, start=1)}
        # La partie k est à l'entrée `_eb + k` (une par emplacement du pool), et un groupe mort est déjà rendu
        # (`actor_destroy_internal`) : la boucle ne parcourt que les racines vivantes.
        ranks = [k if r >= 0 else -1 for k, r in enumerate(ranks)]
        L += [f"    /* {pf.name} — subtree of each instance */",
              "    POOL_EACH(_b) {",
              f"        if(g_actors[_b].model!={p2['model_id']}||!g_actors[_b].alive) continue;",
              *(["        int _eb = g_spool_entry + (_b - g_spool_start);"] if p2["spool"]["entries"] else []),
              # Les deux règles du sous-arbre : « détruire la racine détruit le sous-arbre » (le groupe est RENDU AU
              # POOL par `actor_destroy_internal`), et « désactiver la racine désactive le sous-arbre » (il reste
              # occupé, mais n'est ni dessiné ni en collision), ici. Sans cette branche, un boss désactivé
              # laisserait ses bras actifs. Les parties ne suivent pas une RÉACTIVATION de la racine : une partie
              # se réactive elle-même (`self.Bras:activate()`).
              f"        if(!g_actors[_b].active) {{",
              f"            for(int _k=1; _k<{p2['group']}; _k++) g_actors[group_slot(_b, _k)].active = 0;",
              f"            continue;",
              f"        }}",
              "        int " + ", ".join(f"_s{k} = group_slot(_b, {k})" for k in range(1, len(parts) + 1)) + ";"]
        for k, pt in enumerate(parts, start=1):
            par = by_name.get(getattr(pt, "parent", None) or "")
            # Parent = une autre partie, sinon la racine du groupe (décalage 0).
            p_off = rank.get(par.name, 0) if par is not None else 0
            ref = par if par is not None else pf
            p_rot = float(_number_value(getattr(ref, "rotation", 0)) or 0)
            p_sx = float(_number_value(getattr(ref, "scale_x", 1.0), ref_divisor=100) or 1.0) or 1.0
            p_sy = float(_number_value(getattr(ref, "scale_y", 1.0), ref_divisor=100) or 1.0) or 1.0
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
            rot = int(_number_value(getattr(pt, "rotation", 0)) or 0) - int(round(p_rot))
            sx = int(round(float(_number_value(getattr(pt, "scale_x", 1.0), ref_divisor=100) or 1.0) / p_sx * 256))
            sy = int(round(float(_number_value(getattr(pt, "scale_y", 1.0), ref_divisor=100) or 1.0) / p_sy * 256))
            src = f"_s{p_off}" if p_off else "_b"
            L += [
                f"        if(g_actors[_s{k}].active) {{   /* {pt.name} in the frame of "
                f"{par.name if par is not None else pf.name} */",
                f"            int _pr = g_actors[{src}].rotation;",
                f"            int _px = g_actors[{src}].scale_x, _py = g_actors[{src}].scale_y;",
                f"            int _co, _si; gba_sincos(_pr, &_si, &_co);",
                f"            int _lx = ({ox} * _px) >> 8, _ly = ({oy} * _py) >> 8;",
                f"            g_actors[_s{k}].x = g_actors[{src}].x + ((_lx * _co - _ly * _si) >> 8);",
                f"            g_actors[_s{k}].y = g_actors[{src}].y + ((_lx * _si + _ly * _co) >> 8);",
                f"            g_actors[_s{k}].rotation = _pr + {rot};",
                f"            g_actors[_s{k}].scale_x  = (_px * {sx}) >> 8;",
                f"            g_actors[_s{k}].scale_y  = (_py * {sy}) >> 8;",
                *_visible_line("            ",
                               _pool_entry_expr(ranks[k]), _pool_entry_expr(ranks[p_off]),
                               getattr(pt, "visible", True)),
                f"        }}",
            ]
        L.append("    }")
    return L
