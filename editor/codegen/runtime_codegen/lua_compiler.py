"""
runtime_codegen/lua_compiler.py — Transpilation Lua -> C pour acteurs, prefabs et scènes.

Entrées  : Project, Scene, liste (Actor, SpriteAsset)
Sorties  : fichiers actor_*.c et scene.c écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from core.models.components import ScriptComponent
from core.models.sprite import SpriteAsset
from core.models.scene import Actor, Scene
from core.project import Project
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals
from scripting.constants import write_constants
from codegen.c_names import sym as c_sym, scene_actor_sym
import codegen.build_output as build_output
from codegen.oam_alloc import scene_pool_instances


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def _export_inits(actor: Actor, script) -> dict:
    """Pour un acteur POSÉ : map nom d'export → initialiseur C, en préférant la
    valeur d'INSTANCE (`ScriptComponent.exports_values`) au `default` déclaré dans
    le script (chantier « Les exports de script, câblés au jeu »).

    Ne couvre que les types entiers du premier jet — int / float / bool / enum,
    qui tombent tous sur un entier au runtime. `string`, les `*_ref` et les
    composites (`vec2`/`rect`) sont reportés : ils gardent le traitement par défaut
    du codegen (`_local_decl`). On lit le MÊME arbre (`script.locals`) que le
    codegen — jamais un second parseur du fichier, qui pourrait en diverger (les
    `values` d'un enum sont désormais captées sur le `LuaLocal`, cf. parser)."""
    from scripting.parser import ExprNumber, ExprBool, ExprString
    comp = actor.get_component("script")
    overrides = (getattr(comp, "exports_values", None) or {}) if comp else {}
    out: dict = {}
    for loc in script.locals:
        typ = loc.export_type
        if typ not in ("int", "float", "bool", "enum"):
            continue
        if loc.name in overrides:
            val = overrides[loc.name]
        elif isinstance(loc.value, (ExprNumber, ExprBool, ExprString)):
            val = loc.value.value
        else:
            val = None
        out[loc.name] = _export_c_literal(typ, val, loc.export_values)
    return out


def _spawn_exports_meta(p, prefabs) -> dict:
    """Métadonnées des exports RÉGLABLES de chaque prefab, pour la table de
    `actor.spawn("X", pos, {k=v})` (tranche poolé D2) : nom de prefab → { nom
    d'export → {"type", "values"} }. Lue sur l'arbre du script (même source que
    le reste), et servie à TOUS les scripts — n'importe lequel peut spawner."""
    from scripting.parser import parse as lua_parse
    out: dict = {}
    for pf in prefabs:
        sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
        if not sc or not sc.script:
            continue
        sp = p.asset_abs(sc.script)
        if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
            continue
        try:
            ast = lua_parse(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = {loc.name: {"type": loc.export_type, "values": loc.export_values}
                for loc in ast.locals
                if loc.export_type in ("int", "float", "bool", "enum")}
        if meta:
            out[pf.name] = meta
    return out


def _export_c_literal(typ: str, val, values: list) -> str:
    """La valeur d'un export entier, en littéral C. bool → 0/1 ; enum → l'index de
    l'étiquette dans `values` (0 si introuvable — le moteur est entièrement entier,
    cf. codegen._EXPORT_C_TYPE) ; int/float → entier (pas de flottant au runtime)."""
    if typ == "bool":
        return "1" if val else "0"
    if typ == "enum":
        try:
            return str(values.index(val))
        except ValueError:
            return "0"
    try:
        return str(int(val))
    except (TypeError, ValueError):
        return "0"


def _sfx_component_name(owner) -> Optional[str]:
    """Le Sfx du SoundFxComponent d'un actor/prefab, si présent — ce que
    `self:play_sfx()` joue. Les triggers AUTOMATIQUES (on_spawn/on_destroy/
    on_button_*) ne passent plus par ici : `main_gen.py` les injecte
    directement, cf. `core.models.components.SFX_AUTO_TRIGGERS`."""
    comp = owner.get_component("sound_fx")
    if not comp or not comp.active or not comp.sfx_name:
        return None
    return comp.sfx_name


def _affine_reserved(owner) -> bool:
    """Cet actor/prefab réserve-t-il un slot de matrice affine ? La case vit sur
    le SpriteComponent (cf. ARCHITECTURE.md « Le modèle affine ») ; sans sprite,
    rien n'est réservé. Le checker s'en sert pour avertir qu'un `self.rotation`
    ne se verra pas — il ne refuse plus le build : la valeur, elle, s'écrit et
    se relit."""
    comp = owner.get_component("sprite")
    return bool(comp and comp.affine_transform)


def _compile_script(sp: Path, ctx_check: "BuildContext", emit, label: str):
    """
    Parse + valide un script Lua (actor, scène ou prefab — même traitement
    pour les trois, contrairement à avant où seuls les actors étaient
    validés). Retourne (ast, ok) : ast est None si le parse échoue ; ok est
    False sur erreur bloquante (parse ou check), quel que soit le type de
    script — un prefab avec une faute de syntaxe bloque désormais le build
    au lieu d'être silencieusement sauté.
    """
    try:
        script = lua_parse(sp.read_text(encoding="utf-8"))
    except LuaParseError as e:
        # `fichier:ligne`, comme les messages qui citent une ligne ailleurs
        # (`_check_literal_texts`) — la ligne manque quand la faute est
        # LEXICALE et qu'aucun faux ami connu ne l'explique (cf. `parser.
        # _syntax_message`) ; le nom du fichier reste alors le seul repère.
        ou = f"{label}:{e.line}" if e.line else label
        emit("error_line", f"[error] {ou} : {e}")
        return None, False
    errors = lua_check(script, ctx_check)
    for err in errors:
        prefix = "[error]" if err.level == "error" else "[warn] "
        emit("log_line", f"{prefix} {label}: {err.message}")
    if any(e.level == "error" for e in errors):
        return script, False
    return script, True


def _child_refs_for_actor(actor, scene_actors, scene_name) -> dict:
    """Les enfants d'un acteur de SCÈNE, nom Lua → expression C (ROADMAP v0.23).

    Un enfant est un acteur de la même scène dont `parent` nomme celui-ci ; il
    a donc son propre TAG_*, qualifié par la scène comme tout acteur posé
    (« L'acteur appartient à sa scène »), et le désigner ne coûte qu'un `#define`."""
    return {a.name: f"&g_actors[TAG_{scene_actor_sym(scene_name, a.name).upper()}]"
            for a, _ in scene_actors
            if getattr(a, "parent", None) == actor.name}


def _child_refs_for_prefab(pf) -> dict:
    """Les enfants d'un PREFAB : un décalage constant dans le groupe de
    l'instance, la racine étant à l'offset 0 (cf. main_gen, `prefab_group`)."""
    return {c.name: f"(self + {k})"
            for k, c in enumerate(getattr(pf, "children", []) or [], start=1)}


def _project_lists(p):
    """Les panneaux marqués LISTE — import local, `main_gen` important déjà ce
    module par ailleurs."""
    from codegen.runtime_codegen.gen_ui import project_lists
    return project_lists(p)


def _project_inputs(p) -> tuple[list[str], dict[str, str]]:
    """Noms et masques C des actions définies dans Project Settings.

    Les noms sont délibérément résolus au build : une action ne demande aucun
    état ni table en RAM. Un combo est simplement le masque OR de ses boutons,
    que `input_held` teste déjà en entier.
    """
    bindings = list(getattr(getattr(p, "settings", None), "inputs", []) or [])
    names: list[str] = []
    masks: dict[str, str] = {}
    for binding in bindings:
        name = str(getattr(binding, "name", "") or "").strip()
        buttons = list(getattr(binding, "buttons", []) or [])
        if not name or not buttons or name in names:
            continue
        names.append(name)
        masks[name] = " | ".join(f"BTN_{button.upper()}" for button in buttons)
    return names, masks


def transpile_all(
    p: Project,
    scene: Scene,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    emit,
    scene_names: list[str] | None = None,
    precomputed_global_names: list[str] | None = None,
    precomputed_const_names: list[str] | None = None,
    compiled_cameras: set[str] | None = None,
    sound_assets: dict | None = None,
) -> bool:
    """
    Compile tous les scripts Lua de la scène en C.

    Retourne False si une erreur bloquante est trouvée.
    """
    # L'ORDRE fait foi ici aussi, mais il ne nous appartient PAS : c'est mmutil
    # qui numérote les sons, dans l'ordre où le build les lui passe. `SFX_X` et
    # `MUSIC_X` doivent donc être des rangs dans les listes RÉELLEMENT émises
    # (`sound_assets`), jamais dans le catalogue du projet.
    #
    # Le piège s'est refermé le jour où le build a cessé de tout émettre : tant
    # que les 105 musiques partaient dans l'ordre du projet, les deux
    # numérotations coïncidaient par accident et `music.play` fonctionnait.
    # Filtrer sur ce qui est référencé a désaligné les deux, sans qu'aucun
    # symbole ne manque — la ROM compilait et jouait le mauvais module.
    if sound_assets is not None:
        sfx_items   = [s for s, _ in sound_assets.get("sfx", [])]
        music_items = [m for m, _ in sound_assets.get("music", [])]
    else:
        sfx_items   = list(getattr(p, "sfx", []))
        music_items = list(getattr(p, "music", []))
    sfx_names   = [s.name for s in sfx_items]
    sfx_volumes = {s.name: getattr(s, "volume", 100) for s in sfx_items}
    music_names = [m.name for m in music_items]
    music_info  = ({m.name: (getattr(m, "loop", True), getattr(m, "volume", 100)) for m in p.music}
                   if hasattr(p, "music") else {})
    # Textes et polices : l'ORDRE fait foi (il devient l'index dans les tables C
    # émises par main_gen). project_fonts() est la source unique côté polices.
    from codegen.font_emit import project_fonts
    # `build_texts()` et non `texts` : les littéraux de `text.draw` deviennent
    # des entrées anonymes, et leurs `#define TEXT_*` doivent exister aussi.
    text_keys   = ([t.key for t in p.build_texts()] if hasattr(p, "build_texts")
                   else [t.key for t in getattr(p, "texts", [])])
    font_names  = [f.name for f in project_fonts(p)]
    # Langues : source en index 0 puis `settings.languages` dans l'ordre
    # déclaré — même ordre que `g_texts[lang]`/`g_lang_font[lang]` (ROADMAP
    # v0.9, phase 4). [] dans un projet monolingue, jamais None : lang.set /
    # lang.get n'ont alors aucun code valide, refusés comme n'importe quel
    # nom absent — pas un cas spécial.
    lang_codes  = ([l.code for l in p.settings.all_languages()]
                   if hasattr(p, "settings") else [])
    input_names, input_masks = _project_inputs(p)
    # Palettes : le catalogue ENTIER, dans son ordre. L'ordre devient
    # l'index dans g_palettes (main_gen), comme pour les textes et les
    # polices. Pas de dérivation depuis les scripts : la ROM est assez
    # large pour toutes les porter (32 octets pièce).
    palette_names = [b.name for b in getattr(p, "palettes", [])]
    # Zones de texte : l'ordre de `all_regions()` devient l'index dans
    # g_ui_regions, comme pour les textes et les polices.
    region_names = (p.region_names() if hasattr(p, "region_names") else [])
    image_names  = (p.image_names()  if hasattr(p, "image_names")  else [])
    # TOUS les éléments d'UI, tous types confondus — l'index de la table de
    # visibilité plate (UIELEM_*), pour ui.get().
    element_names = (p.ui_element_names() if hasattr(p, "ui_element_names") else [])
    # Les états que chaque image peut prendre, lus dans SON sprite : c'est le
    # seul endroit du build qui tienne les deux bouts (l'élément et l'asset).
    image_states = {}
    for _lay, _im in (p.all_images() if hasattr(p, "all_images") else []):
        _spr = p.get_sprite(getattr(_im, "sprite_name", "") or "")
        image_states[_im.name] = [st.name for st in (getattr(_spr, "states", []) or [])]
    all_syms    = [c_sym(a.name) for a, _ in scene_actors]
    _actor_names = [a.name for a, _ in scene_actors]
    _scene_names = scene_names or []
    _camera_names = sorted(p.camera_names()) if hasattr(p, "camera_names") else []
    _window_names = sorted(p.window_names()) if hasattr(p, "window_names") else []
    # Une famille, un espace de noms — depuis que les trois boîtes sont trois
    # assets, rien n'oblige leurs états à se distinguer entre familles.
    from core.models.sound_box import KIND_SOUND, KIND_JINGLE
    _snd_names = (p.sound_state_names(KIND_SOUND)
                  if hasattr(p, "sound_state_names") else [])
    _jgl_names = (p.sound_state_names(KIND_JINGLE)
                  if hasattr(p, "sound_state_names") else [])
    _snd_triggers = p.sound_trigger_names() if hasattr(p, "sound_trigger_names") else []
    # Le rang d'un état est celui qu'il occupe DANS SA boîte — c'est ce que les
    # tables C indexent.
    _trigger_index = {n: i for i, n in enumerate(_snd_triggers)}
    _snd_index: dict = {}
    _jgl_index: dict = {}
    for _store, _index in ((getattr(p, "sound_boxes", []), _snd_index),
                           (getattr(p, "jingle_boxes", []), _jgl_index)):
        for _b in sorted(_store, key=lambda b: b.name):
            for _i, _st in enumerate(_b.states):
                _index.setdefault(_st.name, _i)
    # Les prefabs sont poolés au niveau PROJET : `actor.spawn("X")` vise la
    # liste entière, pas ce que la scène courante contient.
    _prefab_names = [pf.name for pf in prefabs]
    # Exports réglables par prefab (tranche poolé D2) : servis à tous les scripts
    # (ctx codegen ET ctx_check du checker), n'importe lequel peut spawner.
    _spawn_meta = _spawn_exports_meta(p, prefabs)
    # Tables de données : {nom: (colonnes, nombre de lignes)}. Le checker en
    # tire ses refus (table ou colonne inconnue, index hors bornes, écriture sur
    # une const) et le codegen la taille pour `#data.X`. Une seule lecture du
    # registre pour tous les scripts de la scène.
    _data_tables = {t.name: ([c.name for c in t.columns], len(t.rows))
                    for t in getattr(p, "data_tables", [])}

    # Globals résolus en avance (nécessaire pour le BuildContext du checker)
    if precomputed_global_names is not None:
        global_names = precomputed_global_names
    else:
        global_names = write_globals(p.src_dir, p.globals)
        if global_names:
            emit("log_line", f"[lua] globals: {', '.join('g_'+n for n in global_names)}")

    # Constants résolues en avance, même principe que les globals
    if precomputed_const_names is not None:
        const_names = precomputed_const_names
    else:
        const_names = write_constants(p.src_dir, p.constants)
        if const_names:
            emit("log_line", f"[lua] constants: {', '.join('CONST_'+n.upper() for n in const_names)}")

    # Sauvegarde — deux faits du PROJET, les mêmes pour tous les scripts : le
    # nombre d'emplacements déclaré, et s'il y a seulement quelque chose à
    # sauver. Le checker s'en sert pour refuser un emplacement inexistant et
    # signaler un save.write() qui ne sauverait rien.
    _save_slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    _has_persist = any(getattr(g, "persist", False) for g in p.globals)

    parsed_scripts = []

    for actor, sprite in scene_actors:
        script_path = _actor_script(actor)
        if not script_path:
            continue
        sp = p.asset_abs(script_path)
        if not sp or not sp.exists():
            continue

        if sp.suffix.lower() == ".c":
            build_output.copy(sp, p.src_dir / sp.name)
            emit("log_line", f"[script] {sp.name} copié (C natif)")
            continue

        if sp.suffix.lower() != ".lua":
            continue

        anim_names = [st.name for st in sprite.states] if sprite and sprite.states else []
        # EventCall (ROADMAP v0.8.9) : les `event_name` cités par CE sprite —
        # une fonction de premier niveau qui porte l'un de ces noms est un
        # point d'entrée légitime (cf. `checker._check_function`), pas une
        # fonction inconnue.
        frame_event_names = sorted({
            getattr(fr, "event_name", "") or ""
            for stt in (sprite.states if sprite else [])
            for sd in stt.directions
            for fr in sd.frames
        } - {""})
        sfx_comp_name = _sfx_component_name(actor)
        _rt_transform = _affine_reserved(actor)
        ctx_check = BuildContext(
            actor_name   = actor.name,
            input_names  = input_names,
            anim_names   = anim_names,
            frame_event_names = frame_event_names,
            affine_transform = _rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            global_names = list(global_names) if global_names else None,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            global_types = {g.name: g.type for g in p.globals},
            # ROADMAP v0.22 : sert le checker de save.read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # ROADMAP v0.20 : 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            child_names  = list(_child_refs_for_actor(actor, scene_actors, scene.name).keys()),
            # Une LISTE même vide, jamais None : depuis que `const.nom` est un
            # accès pointé (chantier global/const), c'est le checker seul qui
            # juge de l'existence d'une constante — `None` voudrait dire
            # « je ne sais pas », et un projet sans aucune constante déclarée
            # laisserait alors passer `const.max` jusqu'au `make`, sur une
            # erreur de syntaxe C nommant le mot-clé `const`. `global_counts`,
            # juste au-dessus, est un dict même vide pour la même raison.
            const_names  = list(const_names),
            sfx_component_name = sfx_comp_name,
            text_keys    = text_keys,
            font_names   = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
        )
        script, ok = _compile_script(sp, ctx_check, emit, sp.name)
        if not ok:
            return False

        parsed_scripts.append((actor, sprite, script, sp))

    # Script de scène — parse
    scene_script_ast  = None
    scene_script_file = None
    scene_script_path = getattr(scene, "script", "")
    if scene_script_path:
        sp = p.asset_abs(scene_script_path)
        if sp and sp.exists() and sp.suffix.lower() == ".lua":
            ctx_check = BuildContext(
                actor_name   = scene.name,
                input_names  = input_names,
                sfx_names    = sfx_names,
                music_names  = music_names,
                scene_names  = _scene_names,
                camera_names = _camera_names,
                window_names = _window_names,
                sound_box_state_names   = _snd_names,
                jingle_box_state_names  = _jgl_names,
                music_box_trigger_names = _snd_triggers,
                actor_names  = _actor_names,
            prefab_names = _prefab_names,
                global_names = list(global_names) if global_names else None,
                ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            global_types = {g.name: g.type for g in p.globals},
            # ROADMAP v0.22 : sert le checker de save.read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # ROADMAP v0.20 : 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
                const_names  = list(const_names),
                # Un script de SCÈNE cite textes et polices autant qu'un script
                # d'actor : sans ces deux-là le checker se tait, et une clé
                # inconnue n'échoue qu'au `make`, sur un `TEXT_*` indéfini.
                text_keys    = text_keys,
                font_names   = font_names,
                lang_codes   = lang_codes,
                palette_names = palette_names,
                region_names = region_names,
                image_names  = image_names,
                element_names = element_names,
                image_states = image_states,
                save_slots   = _save_slots,
                has_persistent = _has_persist,
                data_tables  = _data_tables,
                spawn_exports = _spawn_meta,
            )
            scene_script_ast, ok = _compile_script(sp, ctx_check, emit, sp.name)
            if not ok:
                return False
            scene_script_file = sp

    # Génération C — actors de scène
    for actor, sprite, script, sp in parsed_scripts:
        s    = scene_actor_sym(scene.name, actor.name)
        anims = [st.name for st in sprite.states] if sprite and sprite.states else []
        frame_events = sorted({
            getattr(fr, "event_name", "") or ""
            for state in (sprite.states if sprite else [])
            for direction in state.directions
            for fr in direction.frames
        } - {""})
        sfx_comp_name = _sfx_component_name(actor)
        ctx  = CodegenContext(
            child_refs    = _child_refs_for_actor(actor, scene_actors, scene.name),
            actor_name    = actor.name,
            actor_sym     = s,
            scene_sym     = c_sym(scene.name),
            input_masks   = input_masks,
            anim_names    = anims,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            frame_event_names = frame_events,
            scripts_dir   = p.scripts_dir,
            scene_names   = _scene_names,
            sfx_component_name = sfx_comp_name,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names  = region_names,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            export_inits  = _export_inits(actor, script),
            spawn_exports = _spawn_meta,
        )
        c_code, gen_warnings, _ = lua_generate(script, ctx)
        for w in gen_warnings:
            emit("log_line", f"[warn] {sp.name}: {w}")
        out = p.src_dir / f"actor_{s}.c"
        build_output.write(out, c_code)
        emit("log_line", f"[lua->c] {sp.name} -> {out.name}")

    # Génération C — prefabs poolés, RECOMPILÉS PAR SCÈNE (ROADMAP v0.17, T1).
    # Chaque scène ne compile QUE les prefabs qu'elle déclare, contre SA
    # géométrie : le symbole est préfixé par la scène (`<Scène>_<Prefab>`), donc
    # `actor_<Scène>_<Prefab>.c`, `POOL_<Scène>_<Prefab>_*` et `spawn_<Scène>_
    # <Prefab>` concordent. Le total EWRAM ci-dessous est celui de CETTE scène.
    scene_sym = c_sym(scene.name)
    pool_state_total = 0
    for pf in prefabs:
        pf_instances = scene_pool_instances(scene, pf)
        if pf_instances <= 0:
            continue
        pf_sym = f"{scene_sym}_{c_sym(pf.name)}"
        sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
        if not sc or not sc.script:
            continue
        sp_path = p.asset_abs(sc.script)
        if not sp_path or not sp_path.exists() or sp_path.suffix.lower() != ".lua":
            continue
        pf_spr  = next((c for c in pf.components if hasattr(c, "states")), None)
        pf_anim = [st.name for st in pf_spr.states] if pf_spr and hasattr(pf_spr, "states") else []
        pf_sfx_comp_name = _sfx_component_name(pf)
        _pf_rt_transform = _affine_reserved(pf)
        ctx_check = BuildContext(
            actor_name   = pf.name,
            input_names  = input_names,
            anim_names   = pf_anim,
            affine_transform = _pf_rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            global_names = list(global_names) if global_names else None,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            global_types = {g.name: g.type for g in p.globals},
            # ROADMAP v0.22 : sert le checker de save.read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # ROADMAP v0.20 : 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            child_names  = list(_child_refs_for_prefab(pf).keys()),
            const_names  = list(const_names),
            sfx_component_name = pf_sfx_comp_name,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
        )
        pf_ast, ok = _compile_script(sp_path, ctx_check, emit, f"prefab {pf.name} ({sp_path.name})")
        if not ok:
            return False
        ctx_pf  = CodegenContext(
            child_refs    = _child_refs_for_prefab(pf),
            actor_name    = pf.name,
            actor_sym     = pf_sym,
            scene_sym     = scene_sym,
            input_masks   = input_masks,
            anim_names    = pf_anim,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            scripts_dir   = p.scripts_dir,
            is_pooled     = True,
            pool_size     = pf_instances,
            scene_names   = _scene_names,
            sfx_component_name = pf_sfx_comp_name,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names  = region_names,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            # Le repli ÉDITEUR d'un export poolé (D2) : `Prefab.exports_values`
            # réglé sur le template, sinon le `default` du script. Un `Prefab` EST
            # son acteur racine, donc `get_component("script")` rend ses valeurs.
            # C'est l'init du pool ; la table de spawn (tranche 2) l'écrasera par
            # instance.
            export_inits  = _export_inits(pf, pf_ast),
            spawn_exports = _spawn_meta,
        )
        pf_c, pf_warnings, pf_state_bytes = lua_generate(pf_ast, ctx_pf)
        for w in pf_warnings:
            emit("log_line", f"[warn] prefab {pf.name}: {w}")
        out_pf = p.src_dir / f"actor_{pf_sym}.c"
        build_output.write(out_pf, pf_c)
        emit("log_line", f"[lua->c] prefab {pf.name} -> {out_pf.name}")
        # Ce que l'état de script de ce prefab occupe en EWRAM. Le chiffre est
        # dit et non plafonné (cf. ROADMAP v0.7.6) : le plafond de huit entiers
        # qu'il remplace était arbitraire, et la ressource ici est arbitrable.
        pool_state_total += pf_state_bytes * pf_instances
        if pf_state_bytes:
            emit("log_line",
                 f"[ewram] prefab {pf.name} : état de script {pf_state_bytes} "
                 f"octets × {pf_instances} instance(s) = "
                 f"{pf_state_bytes * pf_instances} octets")

    if pool_state_total:
        emit("log_line",
             f"[ewram] état de script des prefabs poolés : {pool_state_total} octets")

    # Génération C — script de scène
    if scene_script_ast and scene_script_file:
        scene_s = c_sym(scene.name)
        ctx_sc  = CodegenContext(
            actor_name    = scene.name,
            actor_sym     = scene_s,
            scene_sym     = scene_s,
            input_masks   = input_masks,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            is_scene      = True,
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names  = region_names,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            spawn_exports = _spawn_meta,
        )
        c_code, sc_warnings, _ = lua_generate(scene_script_ast, ctx_sc)
        for w in sc_warnings:
            emit("log_line", f"[warn] {scene_script_file.name}: {w}")
        out_name = f"{scene_s}_scene.c"
        out = p.src_dir / out_name
        build_output.write(out, c_code)
        emit("log_line", f"[lua->c] {scene_script_file.name} -> {out_name}")

    # Génération C — scripts de CAMÉRA
    #
    # Une caméra n'appartient qu'à UNE scène (révisé 2026-08-24), mais son
    # script est compilé comme n'importe quel script de projet : la garde
    # `compiled_cameras` reste par précaution (même mécanique que les prefabs
    # poolés) plutôt que par nécessité. Mêmes points d'entrée qu'un script de
    # scène — `hook_kind="camera"` ne change que le mot dans le symbole C émis.
    for cam in (c for s in p.scenes for c in s.cameras):
        if not getattr(cam, "script", ""):
            continue
        cam_sym = f"camera_{c_sym(cam.name)}"
        if compiled_cameras is not None:
            if cam_sym in compiled_cameras:
                continue
            compiled_cameras.add(cam_sym)
        sp = p.asset_abs(cam.script)
        if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
            continue
        ctx_check = BuildContext(
            actor_name   = cam.name,
            input_names  = input_names,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            # Aucun `actor_names` : le script d'une caméra n'a pas de `self`
            # (même contrat qu'un script de scène), donc rien à valider contre
            # une liste d'acteurs ici — `get_actor("Nom")` reste un appel
            # générique, non typé par domaine.
            global_names = list(global_names) if global_names else None,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            global_types = {g.name: g.type for g in p.globals},
            # ROADMAP v0.22 : sert le checker de save.read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # ROADMAP v0.20 : 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            const_names  = list(const_names),
            text_keys    = text_keys,
            font_names   = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
        )
        cam_ast, ok = _compile_script(sp, ctx_check, emit, f"camera {cam.name} ({sp.name})")
        if not ok:
            return False
        ctx_cam = CodegenContext(
            actor_name    = cam.name,
            actor_sym     = cam_sym,
            input_masks   = input_masks,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            is_scene      = True,
            hook_kind     = "camera",
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            region_names  = region_names,
            ui_list_names = [pn.name for _l, pn in _project_lists(p)],
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            spawn_exports = _spawn_meta,
        )
        cam_c, cam_warnings, _ = lua_generate(cam_ast, ctx_cam)
        for w in cam_warnings:
            emit("log_line", f"[warn] camera {cam.name}: {w}")
        out_cam = p.src_dir / f"{cam_sym}.c"
        build_output.write(out_cam, cam_c)
        emit("log_line", f"[lua->c] {sp.name} -> {out_cam.name}")

    return True
