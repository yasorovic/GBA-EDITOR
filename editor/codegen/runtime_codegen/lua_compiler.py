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
from core.models.components import affine_sprite_component
from codegen.actor_appearance import owner_appearances
from core.models.scene import Actor, Scene
from core.project import Project
from core import lua_scripts
from core.diagnostic import build_error, build_warning
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals
from scripting.constants import write_constants
from scripting.project_names import ui_ref_kinds, data_column_kinds
from scripting.api import LAYERS_BY_MODE, LAYER_NUMBERS, SpriteLibrary

from codegen.c_names import sym as c_sym, scene_actor_sym
import codegen.build_output as build_output
from codegen.oam_alloc import scene_has_model, scene_oam_layout
from codegen.runtime_codegen.input_layout import compute_input_layout


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


# Types d'export câblés jusqu'au C — tous réglables par instance. Miroir de
# codegen._EXPORT_SETTABLE (les deux doivent lister le même ensemble : ici on
# décide QUOI résoudre, là-bas COMMENT le déclarer).
_SETTABLE_EXPORTS = frozenset({
    "int", "float", "bool", "enum",
    "string", "actor_ref", "scene_ref", "sfx_ref",
    "vec2", "vec3", "rect",
})
_COMPOSITE_ARITY = {"vec2": 2, "vec3": 3, "rect": 4}


def _default_pyval(expr):
    """La valeur Python d'un défaut d'export lu sur l'arbre (`loc.value`) :
    scalaire pour un littéral, liste de nombres pour une table `{x, y}` (vec/
    rect). None si le défaut n'est pas un littéral exploitable — le résolveur
    tombera alors sur le neutre du type."""
    from scripting.parser import ExprNumber, ExprBool, ExprString, ExprTable
    if isinstance(expr, (ExprNumber, ExprBool, ExprString)):
        return expr.value
    if isinstance(expr, ExprTable):
        return [it.value for it in expr.items
                if isinstance(it, ExprNumber)]
    return None


def _make_export_resolver(p, scene_name: str, text_keys: list):
    """Un callable `literal(typ, pyval, values) -> str` : la valeur d'un export
    (venue de l'éditeur ou du défaut de source) → son initialiseur C, résolu
    DANS `scene_name` (c'est là qu'un nom d'acteur a un sens). Les scalaires
    tombent sur un entier ou une constante symbolique en portée dans le `.c`
    généré (SFX_*, SCENE_IDX_*, ACTOR_*, TEXT_*) ; les composites sur un littéral
    `{ x, y }`. Chantier « Les exports de script », types non-entiers."""
    from scripting.api import (sfx_constant, scene_constant, text_constant,
                               anon_text_key)
    from codegen.c_names import scene_actor_sym

    def ref_or_text(typ, name):
        name = "" if name is None else str(name)
        if not name:
            return "0"
        if typ == "sfx_ref":
            return sfx_constant(name)
        if typ == "scene_ref":
            return scene_constant(name)
        if typ == "actor_ref":
            return f"ACTOR_{scene_actor_sym(scene_name, name).upper()}"
        # string → index de texte : clé réelle du projet, sinon entrée anonyme
        # (le littéral aura été collecté par project_texts.collect_literal_texts).
        key = name if name in text_keys else anon_text_key(name)
        return text_constant(key)

    def literal(typ, pyval, values):
        if typ in ("sfx_ref", "scene_ref", "actor_ref", "string"):
            return ref_or_text(typ, pyval)
        if typ in _COMPOSITE_ARITY:
            n = _COMPOSITE_ARITY[typ]
            seq = list(pyval) if isinstance(pyval, (list, tuple)) else []
            seq = (seq + [0] * n)[:n]
            return "{ " + ", ".join(str(int(v)) for v in seq) + " }"
        return _export_c_literal(typ, pyval, values)

    return literal


def _export_inits(owner, script, resolver) -> dict:
    """Map nom d'export → initialiseur C, en préférant la valeur d'INSTANCE
    (`ScriptComponent.exports_values`) au `default` déclaré dans le script
    (chantier « Les exports de script, câblés au jeu »).

    `owner` est un acteur POSÉ (init au build) ou un `Prefab` template (init du
    pool) — les deux portent un ScriptComponent, donc `exports_values`. Tous les
    types câblés sont couverts (scalaires entiers, `string`, `*_ref`, vec/rect) ;
    `resolver` sait résoudre chacun DANS la scène de compilation. On lit le MÊME
    arbre (`script.locals`) que le codegen — jamais un second parseur du fichier
    — et le défaut de source sert de repli quand l'éditeur n'a rien réglé."""
    comp = owner.get_component("script")
    overrides = (getattr(comp, "exports_values", None) or {}) if comp else {}
    out: dict = {}
    for loc in script.locals:
        typ = loc.export_type
        if typ not in _SETTABLE_EXPORTS:
            continue
        val = overrides[loc.name] if loc.name in overrides else _default_pyval(loc.value)
        out[loc.name] = resolver(typ, val, loc.export_values)
    return out


def prefab_lua_script(p, pf):
    """Le chemin du script Lua d'un prefab, ou None s'il n'en a pas (ou s'il n'est pas du Lua). Seul un prefab
    qui en a un est transpilé en `actor_<Scène>_<Prefab>.c`, donc seul lui définit `<sym>_pool_init`."""
    sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
    if not sc or not sc.script:
        return None
    path = p.asset_abs(sc.script)
    if not path or not path.exists() or path.suffix.lower() != ".lua":
        return None
    return path


def script_exports(p, script_path) -> dict:
    """Les exports RÉGLABLES d'un script : nom -> {"type", "values"}. Lus sur l'arbre du script
    (même source que le reste). Vide si le script manque, n'est pas du Lua ou ne se parse pas."""
    from scripting.parser import parse as lua_parse
    if not script_path:
        return {}
    sp = p.asset_abs(script_path)
    if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
        return {}
    try:
        ast = lua_parse(sp.read_text(encoding="utf-8"))
    except Exception:  # tolerated: a syntax error is reported by the script validator
        return {}
    return {loc.name: {"type": loc.export_type, "values": loc.export_values}
            for loc in ast.locals
            if loc.export_type in _SETTABLE_EXPORTS}


def _spawn_exports_meta(p, prefabs) -> dict:
    """Métadonnées des exports RÉGLABLES de chaque prefab, pour la table de
    `actor:spawn("X", pos, {k=v})` (tranche poolé D2) : nom de prefab → { nom
    d'export → {"type", "values"} }. Servie à TOUS les scripts : n'importe lequel peut
    spawner. Tous les types câblés sont réglables au spawn (scalaires, refs, vec/rect)."""
    out: dict = {}
    for pf in prefabs:
        sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
        meta = script_exports(p, sc.script) if sc and sc.script else {}
        if meta:
            out[pf.name] = meta
    return out


def _state_sizes_path(p) -> Path:
    return p.src_dir / "obj_state_sizes.json"


def write_state_sizes(p, scene, sizes: dict) -> None:
    """Range les tailles d'état de script (octets par instance) des modèles de CETTE scène. Le bloc d'état
    d'un emplacement doit contenir le plus gros : `main_gen` lit toutes les scènes (`read_state_stride`) et
    fixe `OBJ_STATE_STRIDE` une fois, pour tout le projet. La scène remplace sa propre entrée."""
    import json
    path = _state_sizes_path(p)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:  # tolerated: a corrupt cache is rebuilt from the scenes compiled after it
        data = {}
    data[scene.name] = sizes
    build_output.write(path, json.dumps(data, indent=1, sort_keys=True))


def _read_state_sizes(p) -> dict:
    """{scène: {symbole du modèle: octets d'état par instance}} de tout le projet, tel que `write_state_sizes` l'a rangé."""
    import json
    path = _state_sizes_path(p)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:  # tolerated: a corrupt cache reads as no state, the C compiler then refuses a too big one
        return {}


def read_state_stride(p) -> int:
    """La taille d'un bloc d'état de script : le plus gros état des modèles compilés, arrondi au mot, 4
    octets au moins (un tableau de taille nulle ne compile pas)."""
    biggest = max((b for sizes in _read_state_sizes(p).values() for b in sizes.values()), default=0)
    return max(4, (biggest + 3) // 4 * 4)


def state_cost_line(p, slots: int) -> str | None:
    """La ligne de journal qui dit ce que l'état de script COÛTE vraiment : le bloc de chaque emplacement a la taille du plus
    gros état du projet, et les `slots` emplacements le paient tous. `[ewram] prefab X: … per instance` ne dit que le
    prix d'une instance, ce qui sous-estime le total d'un facteur `slots`. Dit aussi quel modèle fixe la taille et ce que
    les autres demandent, pour que l'auteur sache ce qu'un seul gros état fait payer aux autres. None sans aucun état."""
    entries = [(b, scene, sym) for scene, sizes in _read_state_sizes(p).items() for sym, b in sizes.items() if b]
    if not entries:
        return None
    biggest, scene, sym = max(entries)
    others = max((b for b, s, y in entries if (s, y) != (scene, sym)), default=0)
    prefix = f"{c_sym(scene)}_"
    name = sym[len(prefix):] if sym.startswith(prefix) else sym
    stride = read_state_stride(p)
    return (f"[ewram] script state: {stride} bytes x {slots} slots = {stride * slots / 1024:.1f} KiB, "
            f"set by prefab {name} (scene {scene}); the other prefabs need at most {others} bytes")


def member_export_inits(p, scene, actor) -> list:
    """Les valeurs d'export d'un acteur posé MEMBRE d'un modèle : [(nom, type, initialiseur C)].
    Le membre n'a pas de code à lui : son état est celui du modèle, posé à l'entrée de scène par les
    setters du modèle. La valeur d'INSTANCE (`exports_values`) prime sur le défaut du script, comme
    pour un acteur compilé seul (`_export_inits`)."""
    script = _actor_script(actor)
    sp = p.asset_abs(script) if script else None
    if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
        return []
    try:
        ast = lua_parse(sp.read_text(encoding="utf-8"))
    except LuaParseError:  # tolerated: a syntax error is reported by the script validator
        return []
    text_keys = ([t.key for t in p.build_texts()] if hasattr(p, "build_texts")
                 else [t.key for t in getattr(p, "texts", [])])
    inits = _export_inits(actor, ast, _make_export_resolver(p, scene.name, text_keys))
    types = {loc.name: loc.export_type for loc in ast.locals}
    return [(name, types[name], literal) for name, literal in inits.items()]


def _actor_exports_meta(p, scene_actors) -> dict:
    """Les exports de chaque acteur POSÉ de la scène : nom -> { nom d'export -> {"type",
    "values"} }, vide pour un acteur sans export. Un acteur absent du dictionnaire n'est pas
    dans la scène : c'est ce qui distingue « aucun export » de « acteur inconnu »."""
    return {a.name: script_exports(p, _actor_script(a)) for a, _ in scene_actors}


def _export_c_literal(typ: str, val, values: list) -> str:
    """La valeur d'un export ENTIER, en littéral C. bool → 0/1 ; enum → l'index de
    l'étiquette dans `values` (0 si introuvable — le moteur est entièrement entier,
    cf. codegen._EXPORT_C_TYPE) ; int/float → entier (pas de flottant au runtime).
    Les types non-entiers (string/refs/vec) passent par `_make_export_resolver`,
    qui délègue ici pour ce sous-ensemble entier."""
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
    un nom de bouton ou d'action) ne passent plus par ici : `main_gen.py` les
    injecte directement, cf. `core.models.components.SFX_AUTO_TRIGGERS`."""
    comp = owner.get_component("sound_fx")
    if not comp or not comp.active or not comp.sfx_name:
        return None
    return comp.sfx_name


def _sprite_ids(p, owner) -> list[str]:
    """Les `id` des composants sprite d'un propriétaire, dans l'ordre de ses
    apparences (`OamEntry.appearance` en est le rang) : ce que `self:activate_sprite`
    peut citer. Même source que le writer OAM, `owner_appearances`."""
    return [c.id for c, _sprite in owner_appearances(p, owner)]


def _anim_union(p, owner, sprite) -> tuple[list[str], list[list[int]]]:
    """(noms d'état, correspondances) d'un propriétaire de script.

    Une apparence : ses états, sans correspondance (le C émis est celui d'avant).
    Plusieurs : l'UNION des noms d'état de leurs sprites, dans l'ordre de première
    apparition, et pour chaque apparence le rang de chacun dans SON sprite (255 =
    absent). Un état `walk` peut être le 1 d'un sprite et le 3 d'un autre."""
    apps = owner_appearances(p, owner)
    if len(apps) <= 1:
        return ([st.name for st in sprite.states] if sprite and sprite.states else []), []
    names: list[str] = []
    for _c, sp in apps:
        for st in sp.states:
            if st.name not in names:
                names.append(st.name)
    maps = [[next((i for i, st in enumerate(sp.states) if st.name == n), 255) for n in names]
            for _c, sp in apps]
    return names, maps


def _affine_reserved(owner) -> bool:
    """Cet actor/prefab réserve-t-il un slot de matrice affine ? La case vit sur
    le SpriteComponent ; sans sprite,
    rien n'est réservé. Le checker s'en sert pour avertir qu'un `self.rotation`
    ne se verra pas — il ne refuse plus le build : la valeur, elle, s'écrit et
    se relit."""
    comp = affine_sprite_component(owner)
    return bool(comp and comp.affine_transform)


def _compile_script(sp: Path, ctx_check: "BuildContext", emit, owner: str = ""):
    """
    Parse + valide un script Lua (actor, scène ou prefab — même traitement
    pour les trois, contrairement à avant où seuls les actors étaient
    validés). Retourne (ast, ok) : ast est None si le parse échoue ; ok est
    False sur erreur bloquante (parse ou check), quel que soit le type de
    script — un prefab avec une faute de syntaxe bloque désormais le build
    au lieu d'être silencieusement sauté.

    `owner` nomme le propriétaire quand il n'est pas évident par le fichier (« prefab Ball »,
    « camera Cam ») ; la ligne manque quand la faute est LEXICALE et qu'aucun faux ami connu
    ne l'explique (cf. `parser._syntax_message`) : le fichier reste alors le seul repère.
    """
    try:
        script = lua_parse(sp.read_text(encoding="utf-8"))
    except LuaParseError as e:
        emit("diagnostic", build_error(str(e), "script", sp.name, e.line or 0, owner))
        return None, False
    errors = lua_check(script, ctx_check)
    for err in errors:
        make = build_error if err.level == "error" else build_warning
        emit("diagnostic", make(err.message, "checker", sp.name, err.line, owner))
    if any(e.level == "error" for e in errors):
        return script, False
    return script, True


def _child_refs_for_actor(actor, scene_actors, scene_name) -> dict:
    """Les enfants d'un acteur de SCÈNE, nom Lua → expression C.

    Un enfant est un acteur de la même scène dont `parent` nomme celui-ci ; il
    a donc son propre ACTOR_*, qualifié par la scène comme tout acteur posé
    (« L'acteur appartient à sa scène »), et le désigner ne coûte qu'un `#define`."""
    return {a.name: f"&g_actors[ACTOR_{scene_actor_sym(scene_name, a.name).upper()}]"
            for a, _ in scene_actors
            if getattr(a, "parent", None) == actor.name}


def _child_refs_for_prefab(pf) -> dict:
    """Les enfants d'un PREFAB : la partie k du groupe de l'instance, la racine étant la partie 0
    (`group_part`, runtime_api_inline.h ; le rang est une constante du build)."""
    return {c.name: f"group_part(self, {k})"
            for k, c in enumerate(getattr(pf, "children", []) or [], start=1)}


def _child_ranks_for_prefab(pf) -> dict:
    """Le rang de chaque partie d'un PREFAB dans le groupe de l'instance (la racine est le rang 0) : nom -> rang. C'est ce qui
    permet à `boss.Canon` d'atteindre la partie depuis une RÉFÉRENCE au prefab, là où `self.Canon` n'existe que dans son script."""
    return {c.name: k for k, c in enumerate(getattr(pf, "children", []) or [], start=1)}


def _child_sprites(p, children) -> dict:
    """Les sprites de chaque enfant, nom Lua → `SpriteLibrary` : ce que le checker juge et
    ce que le codegen range quand un parent pilote un enfant (`self.Canon:play_anim`).
    `children` : les acteurs enfants (modèle `Actor`)."""
    out = {}
    for c in children:
        apps = owner_appearances(p, c)
        names, maps = _anim_union(p, c, apps[0][1] if apps else None)
        out[c.name] = SpriteLibrary(tuple(names), tuple(tuple(m) for m in maps),
                                    tuple(_sprite_ids(p, c)))
    return out


def _scene_children(actor, scene_actors) -> list:
    return [a for a, _ in scene_actors if getattr(a, "parent", None) == actor.name]


def _project_lists(p):
    """Les panneaux marqués LISTE — import local, `main_gen` important déjà ce
    module par ailleurs."""
    from codegen.runtime_codegen.gen_ui import project_lists
    return project_lists(p)


# `_project_inputs` (masque OR direct depuis `InputBinding.buttons`) est
# remplacé par `compute_input_layout` : les noms restent résolus au build, mais l'expression passe par le
# parseur unique — plus de seconde grammaire pour les combos.


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
        music_items = list(p.audio_modules()) if hasattr(p, "audio_modules") else list(getattr(p, "music", []))
    sfx_names   = [s.name for s in sfx_items]
    sfx_volumes = {s.name: getattr(s, "volume", 100) for s in sfx_items}
    music_names = [m.name for m in music_items]
    # Les jingles aussi : `music.jingle` lit leur volume ici.
    music_info  = ({m.name: (getattr(m, "loop", True), getattr(m, "volume", 100))
                    for m in p.audio_modules()}
                   if hasattr(p, "audio_modules") else {})
    # Parmi les modules ci-dessus, ceux qui vivent dans assets/jingles/.
    jingle_names = [j.name for j in getattr(p, "jingles", [])]
    jingle_policy = {j.name: j.runtime_policy() for j in getattr(p, "jingles", [])}
    # Les noms de section des musiques : l'index est la constante `MSEC_*`, et la même liste clé
    # la table de main.c (cf. core/music_structure.music_section_names).
    from core.music_structure import music_section_names
    music_section_list = music_section_names(getattr(p, "music", []))
    # Textes et polices : l'ORDRE fait foi (il devient l'index dans les tables C
    # émises par main_gen). project_fonts() est la source unique côté polices.
    from codegen.font_emit import project_fonts
    # `build_texts()` et non `texts` : les littéraux de `text.draw` deviennent
    # des entrées anonymes, et leurs `#define TEXT_*` doivent exister aussi.
    text_keys   = ([t.key for t in p.build_texts()] if hasattr(p, "build_texts")
                   else [t.key for t in getattr(p, "texts", [])])
    font_names  = [f.name for f in project_fonts(p)]
    # Langues : source en index 0 puis `settings.languages` dans l'ordre
    # déclaré — même ordre que `g_texts[lang]`/`g_lang_font[lang]`. [] dans un projet monolingue, jamais None : lang.set /
    # lang.get n'ont alors aucun code valide, refusés comme n'importe quel
    # nom absent — pas un cas spécial.
    lang_codes  = ([l.code for l in getattr(p.settings, "_script_languages",
                                          p.settings.all_languages())]
                   if hasattr(p, "settings") else [])
    input_layout = compute_input_layout(p)
    input_names = list(input_layout.masks)
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
    # visibilité plate (UIELEM_*), pour interface:get().
    element_names = (p.ui_element_names() if hasattr(p, "ui_element_names") else [])
    # Le TYPE de chaque élément (liste, image, zone de texte, conteneur), lu dans la
    # mise en page : c'est ce qui type `interface:get("X")` dans le script.
    # Ce que rend une chose NOMMÉE : un élément d'interface par son nom, une cellule de
    # colonne `region`/`image` par son chemin `data.Table.colonne`.
    ref_kinds = {**ui_ref_kinds(p), **data_column_kinds(p)}
    # Les fonds que CETTE scène a : `layer:get(n)` est borné dessus (`api.LAYERS_BY_MODE`).
    layer_numbers = LAYERS_BY_MODE.get(int(getattr(scene, "render_mode", 0) or 0), LAYER_NUMBERS)
    # Les états que chaque image peut prendre, lus dans SON sprite : c'est le
    # seul endroit du build qui tienne les deux bouts (l'élément et l'asset).
    image_states = {}
    for _lay, _im in (p.all_images() if hasattr(p, "all_images") else []):
        _spr = p.get_buildable_sprite(getattr(_im, "sprite_name", "") or "")
        image_states[_im.name] = [st.name for st in (getattr(_spr, "states", []) or [])]
    all_syms    = [c_sym(a.name) for a, _ in scene_actors]
    _actor_names = [a.name for a, _ in scene_actors]
    _scene_names = scene_names or []
    _camera_names = sorted(p.camera_names()) if hasattr(p, "camera_names") else []
    _box_tag_names = list(p.collision_tags()) if hasattr(p, "collision_tags") else []
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
    # Les prefabs sont poolés au niveau PROJET : `actor:spawn("X")` vise la
    # liste entière, pas ce que la scène courante contient.
    _prefab_names = [pf.name for pf in prefabs]
    # `other.name == "X"` vise `ACTOR_<scène>_X`, qui n'existe que si la scène poole X.
    _pooled_prefab_names = [pf.name for pf in prefabs if scene_has_model(p, scene, pf)]
    # Exports réglables par prefab (tranche poolé D2) : servis à tous les scripts
    # (ctx codegen ET ctx_check du checker), n'importe lequel peut spawner.
    _spawn_meta = _spawn_exports_meta(p, prefabs)
    # Les sprites de chaque acteur désignable par un littéral : `actor:get("X")` (acteur de la scène)
    # et `actor:spawn("X")` (prefab). Un prefab est un acteur, donc une seule sorte de bibliothèque.
    _actor_libs  = _child_sprites(p, [a for a, _ in scene_actors])
    _prefab_libs = _child_sprites(p, prefabs)
    _prefab_child_ranks = {pf.name: _child_ranks_for_prefab(pf) for pf in prefabs if getattr(pf, "children", None)}
    _prefab_child_libs = {pf.name: _child_sprites(p, pf.children) for pf in prefabs if getattr(pf, "children", None)}
    # Les enfants de scène de chaque acteur posé : `actor:get("Boss").Canon` s'y résout au build (adresse constante).
    _actor_children = {a.name: _child_refs_for_actor(a, scene_actors, scene.name)
                       for a, _ in scene_actors if _scene_children(a, scene_actors)}
    _actor_child_libs = {a.name: _child_sprites(p, _scene_children(a, scene_actors))
                         for a, _ in scene_actors if _scene_children(a, scene_actors)}
    _actor_exports = _actor_exports_meta(p, scene_actors)
    # Résolveur des valeurs d'export → initialiseur C, scopé à CETTE scène : un
    # `actor_ref` se résout en ACTOR_* de la scène de compilation (cf. « L'acteur
    # appartient à sa scène »), une `string` en TEXT_* de la table du build.
    _export_resolver = _make_export_resolver(p, scene.name, text_keys)
    # Tables de données : {nom: (colonnes, nombre de lignes)}. Le checker en
    # tire ses refus (table ou colonne inconnue, index hors bornes, écriture sur
    # une const) et le codegen la taille pour `#data.X`. Une seule lecture du
    # registre pour tous les scripts de la scène.
    _data_tables = {t.name: ([c.name for c in t.columns], len(t.rows))
                    for t in getattr(p, "data_tables", [])}

    # Les globales de type string : `global.x = "texte"` s'y résout en index de texte.
    _string_globals = frozenset(g.name for g in p.globals if g.type == "string")

    # Globals résolus en avance (nécessaire pour le BuildContext du checker)
    if precomputed_global_names is not None:
        global_names = precomputed_global_names
    else:
        global_names = write_globals(p.src_dir, p.globals, text_keys)
        if global_names:
            emit("log_line", f"[lua] globals: {', '.join('g_'+n for n in global_names)}")

    # Constants résolues en avance, même principe que les globals
    if precomputed_const_names is not None:
        const_names = precomputed_const_names
    else:
        const_names = write_constants(p.src_dir, p.constants, text_keys)
        if const_names:
            emit("log_line", f"[lua] constants: {', '.join('CONST_'+n.upper() for n in const_names)}")

    # Sauvegarde — deux faits du PROJET, les mêmes pour tous les scripts : le
    # nombre d'emplacements déclaré, et s'il y a seulement quelque chose à
    # sauver. Le checker s'en sert pour refuser un emplacement inexistant et
    # signaler un save:write() qui ne sauverait rien.
    _save_slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    _has_persist = any(getattr(g, "persist", False) for g in p.globals)

    parsed_scripts = []

    # Les acteurs posés qui sont des INSTANCES d'un modèle (cf. `pool_model.model_members`) n'ont pas de
    # code à eux : le modèle est compilé une fois (plus bas, avec les prefabs), le membre n'apporte
    # que ses valeurs. Nom de l'acteur -> symbole du modèle.
    _lay = scene_oam_layout(p, scene)
    _posed = [a for a in scene.actors if getattr(a, "active", True)]
    _actor_models = {_posed[i].name: pl.sym for pl in _lay.pools for i in pl.members}

    for actor, sprite in scene_actors:
        if actor.name in _actor_models:
            continue
        script_path = _actor_script(actor)
        if not script_path:
            continue
        sp = p.asset_abs(script_path)
        if not sp or not sp.exists():
            continue

        if sp.suffix.lower() == ".c":
            build_output.copy(sp, p.src_dir / sp.name)
            emit("log_line", f"[script] {sp.name} copied (native C)")
            continue

        if sp.suffix.lower() != ".lua":
            continue

        anim_names, _anim_maps = _anim_union(p, actor, sprite)
        # EventCall : les `event_name` cités par CE sprite —
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
            owner_kind   = "actor",
            input_names  = input_names,
            input_sequence_names = input_layout.sequence_names,
            axis_names   = input_layout.axis_names,
            anim_names   = anim_names,
            sprite_ids   = _sprite_ids(p, actor),
            frame_event_names = frame_event_names,
            affine_transform = _rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            box_tag_names = _box_tag_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            pooled_prefab_names = _pooled_prefab_names,
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            # sert le checker de save:read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            child_names  = list(_child_refs_for_actor(actor, scene_actors, scene.name).keys()),
            child_sprites = _child_sprites(p, _scene_children(actor, scene_actors)),
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
            element_names = element_names,
            image_states = image_states,
            ref_kinds    = ref_kinds,
            layer_numbers = layer_numbers,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
        )
        script, ok = _compile_script(sp, ctx_check, emit)
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
                owner_kind   = "scene",
                input_names  = input_names,
            input_sequence_names = input_layout.sequence_names,
            axis_names   = input_layout.axis_names,
                sfx_names    = sfx_names,
                music_names  = music_names,
                jingle_names = jingle_names,
                music_section_names = music_section_list,
                scene_names  = _scene_names,
                camera_names = _camera_names,
                box_tag_names = _box_tag_names,
                window_names = _window_names,
                sound_box_state_names   = _snd_names,
                jingle_box_state_names  = _jgl_names,
                music_box_trigger_names = _snd_triggers,
                actor_names  = _actor_names,
            prefab_names = _prefab_names,
            pooled_prefab_names = _pooled_prefab_names,
                global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            # sert le checker de save:read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # 1 = scalaire, au-delà = tableau indexable par
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
                element_names = element_names,
                image_states = image_states,
                ref_kinds    = ref_kinds,
                layer_numbers = layer_numbers,
                save_slots   = _save_slots,
                has_persistent = _has_persist,
                data_tables  = _data_tables,
                spawn_exports = _spawn_meta,
                actor_sprites = _actor_libs,
                prefab_sprites = _prefab_libs,
                prefab_children = _prefab_child_ranks,
                prefab_child_sprites = _prefab_child_libs,
                actor_children = _actor_children,
                actor_child_sprites = _actor_child_libs,
                actor_exports = _actor_exports,
            )
            scene_script_ast, ok = _compile_script(sp, ctx_check, emit)
            if not ok:
                return False
            scene_script_file = sp

    # Génération C — actors de scène
    for actor, sprite, script, sp in parsed_scripts:
        s    = scene_actor_sym(scene.name, actor.name)
        anims, anim_maps = _anim_union(p, actor, sprite)
        frame_events = sorted({
            getattr(fr, "event_name", "") or ""
            for state in (sprite.states if sprite else [])
            for direction in state.directions
            for fr in direction.frames
        } - {""})
        sfx_comp_name = _sfx_component_name(actor)
        ctx  = CodegenContext(
            lua_file      = sp.name,
            c_file        = f"actor_{s}.c",
            child_refs    = _child_refs_for_actor(actor, scene_actors, scene.name),
            child_sprites = _child_sprites(p, _scene_children(actor, scene_actors)),
            actor_name    = actor.name,
            actor_sym     = s,
            scene_sym     = c_sym(scene.name),
            input_masks   = input_layout.masks,
            input_sequences = input_layout.sequences,
            input_buffered_bits = input_layout.buffered_bits,
            input_axes    = input_layout.axes,
            anim_names    = anims,
            anim_maps     = anim_maps,
            sprite_ids    = _sprite_ids(p, actor),
            sfx_names     = sfx_names,
            music_names   = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            global_names  = set(global_names),
            string_globals = _string_globals,
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            frame_event_names = frame_events,
            behavior_paths = lua_scripts.behavior_paths(p),
            scene_names   = _scene_names,
            sfx_component_name = sfx_comp_name,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            jingle_policy = jingle_policy,
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
            ref_kinds     = ref_kinds,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            export_inits  = _export_inits(actor, script, _export_resolver),
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
            actor_models = _actor_models,
        )
        c_code, gen_warnings, _ = lua_generate(script, ctx)
        for w in gen_warnings:
            emit("diagnostic", build_warning(w, "codegen", sp.name))
        out = p.src_dir / f"actor_{s}.c"
        build_output.write(out, c_code)
        emit("log_line", f"[lua->c] {sp.name} -> {out.name}")

    # Génération C — prefabs poolés, RECOMPILÉS PAR SCÈNE.
    # Chaque scène ne compile QUE les prefabs qu'elle déclare, contre SA
    # géométrie : le symbole est préfixé par la scène (`<Scène>_<Prefab>`), donc
    # `actor_<Scène>_<Prefab>.c`, `POOL_<Scène>_<Prefab>_*` et `spawn_<Scène>_
    # <Prefab>` concordent. Le total EWRAM ci-dessous est celui de CETTE scène.
    scene_sym = c_sym(scene.name)
    state_sizes: dict = {}
    for pf in prefabs:
        # Un prefab qu'aucune scène ne fait naître n'émet rien, mais son script est quand même
        # VÉRIFIÉ — une fois, par la première scène : sinon ses fautes sémantiques (un nom qui
        # ne désigne rien, un appel inconnu) ne sortiraient qu'au jour où une scène le fait naître.
        check_only = not scene_has_model(p, scene, pf)
        if check_only and not (scene is p.scenes[0] and
                               not any(scene_has_model(p, s, pf) for s in p.scenes)):
            continue
        pf_sym = f"{scene_sym}_{c_sym(pf.name)}"
        sp_path = prefab_lua_script(p, pf)
        if sp_path is None:
            continue
        # Les états viennent des SpriteAsset que les composants citent, comme pour un acteur :
        # un SpriteComponent ne porte pas `states`, il référence un asset.
        pf_apps = owner_appearances(p, pf)
        pf_anim, pf_anim_maps = _anim_union(p, pf, pf_apps[0][1] if pf_apps else None)
        pf_sfx_comp_name = _sfx_component_name(pf)
        _pf_rt_transform = _affine_reserved(pf)
        ctx_check = BuildContext(
            actor_name   = pf.name,
            owner_kind   = "prefab",
            input_names  = input_names,
            input_sequence_names = input_layout.sequence_names,
            axis_names   = input_layout.axis_names,
            anim_names   = pf_anim,
            sprite_ids   = _sprite_ids(p, pf),
            affine_transform = _pf_rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            box_tag_names = _box_tag_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            pooled_prefab_names = _pooled_prefab_names,
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            # sert le checker de save:read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            child_names  = list(_child_refs_for_prefab(pf).keys()),
            child_sprites = _child_sprites(p, pf.children or []),
            const_names  = list(const_names),
            sfx_component_name = pf_sfx_comp_name,
            element_names = element_names,
            image_states = image_states,
            ref_kinds    = ref_kinds,
            layer_numbers = layer_numbers,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
        )
        pf_ast, ok = _compile_script(sp_path, ctx_check, emit, f"prefab {pf.name}")
        if not ok:
            return False
        if check_only:
            continue
        ctx_pf  = CodegenContext(
            lua_file      = sp_path.name,
            c_file        = f"actor_{pf_sym}.c",
            child_refs    = _child_refs_for_prefab(pf),
            child_sprites = _child_sprites(p, pf.children or []),
            actor_name    = pf.name,
            actor_sym     = pf_sym,
            scene_sym     = scene_sym,
            input_masks   = input_layout.masks,
            input_sequences = input_layout.sequences,
            input_buffered_bits = input_layout.buffered_bits,
            input_axes    = input_layout.axes,
            anim_names    = pf_anim,
            anim_maps     = pf_anim_maps,
            sprite_ids    = _sprite_ids(p, pf),
            sfx_names     = sfx_names,
            music_names   = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            global_names  = set(global_names),
            string_globals = _string_globals,
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            behavior_paths = lua_scripts.behavior_paths(p),
            owner_kind    = "prefab",
            is_pooled     = True,
            scene_names   = _scene_names,
            sfx_component_name = pf_sfx_comp_name,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            jingle_policy = jingle_policy,
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
            ref_kinds     = ref_kinds,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            # Le repli ÉDITEUR d'un export poolé (D2) : `Prefab.exports_values`
            # réglé sur le template, sinon le `default` du script. Un `Prefab` EST
            # son acteur racine, donc `get_component("script")` rend ses valeurs.
            # C'est l'init du pool ; la table de spawn (tranche 2) l'écrasera par
            # instance.
            export_inits  = _export_inits(pf, pf_ast, _export_resolver),
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
            actor_models = _actor_models,
        )
        pf_c, pf_warnings, pf_state_bytes = lua_generate(pf_ast, ctx_pf)
        for w in pf_warnings:
            emit("diagnostic", build_warning(w, "codegen", sp_path.name, actor=f"prefab {pf.name}"))
        out_pf = p.src_dir / f"actor_{pf_sym}.c"
        build_output.write(out_pf, pf_c)
        emit("log_line", f"[lua->c] prefab {pf.name} -> {out_pf.name}")
        # Ce que l'état de script de ce modèle pèse PAR INSTANCE. Le bloc d'état de chaque emplacement
        # prend la taille du plus gros (cf. `write_state_sizes`) : le total se dit au `main.c` (`state_cost_line`).
        if pf_state_bytes:
            state_sizes[pf_sym] = pf_state_bytes
            emit("log_line", f"[ewram] prefab {pf.name}: script state {pf_state_bytes} bytes per instance")

    write_state_sizes(p, scene, state_sizes)

    # Génération C — script de scène
    if scene_script_ast and scene_script_file:
        scene_s = c_sym(scene.name)
        ctx_sc  = CodegenContext(
            lua_file      = scene_script_file.name,
            c_file        = f"{scene_s}_scene.c",
            actor_name    = scene.name,
            actor_sym     = scene_s,
            scene_sym     = scene_s,
            input_masks   = input_layout.masks,
            input_sequences = input_layout.sequences,
            input_buffered_bits = input_layout.buffered_bits,
            input_axes    = input_layout.axes,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            global_names  = set(global_names),
            string_globals = _string_globals,
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            owner_kind    = "scene",
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            jingle_policy = jingle_policy,
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
            ref_kinds     = ref_kinds,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
            actor_models = _actor_models,
        )
        c_code, sc_warnings, _ = lua_generate(scene_script_ast, ctx_sc)
        for w in sc_warnings:
            emit("diagnostic", build_warning(w, "codegen", scene_script_file.name))
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
    # scène — `owner_kind="camera"` ne change que le mot dans le symbole C émis.
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
            owner_kind   = "camera",
            input_names  = input_names,
            input_sequence_names = input_layout.sequence_names,
            axis_names   = input_layout.axis_names,
            sfx_names    = sfx_names,
            music_names  = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            box_tag_names = _box_tag_names,
            window_names = _window_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            # Aucun `actor_names` : le script d'une caméra n'a pas de `self`
            # (même contrat qu'un script de scène), donc rien à valider contre
            # une liste d'acteurs ici — `actor:get("Nom")` reste un appel
            # générique, non typé par domaine.
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            # sert le checker de save:read('nom') — un nom
            # qui existe mais n'est pas persist ne sera jamais dans un fichier
            # de sauvegarde.
            global_persist = {g.name: bool(getattr(g, "persist", False)) for g in p.globals},
            # 1 = scalaire, au-delà = tableau indexable par
            # `global.nom[i]`. C'est ce que le checker lit pour distinguer un
            # tableau d'un scalaire et borner un index écrit en clair.
            global_counts = {g.name: max(1, int(getattr(g, "count", 1) or 1))
                             for g in p.globals},
            const_names  = list(const_names),
            text_keys    = text_keys,
            font_names   = font_names,
            lang_codes   = lang_codes,
            palette_names = palette_names,
            element_names = element_names,
            image_states = image_states,
            ref_kinds    = ref_kinds,
            layer_numbers = layer_numbers,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
        )
        cam_ast, ok = _compile_script(sp, ctx_check, emit, f"camera {cam.name}")
        if not ok:
            return False
        ctx_cam = CodegenContext(
            lua_file      = sp.name,
            c_file        = f"{cam_sym}.c",
            actor_name    = cam.name,
            actor_sym     = cam_sym,
            input_masks   = input_layout.masks,
            input_sequences = input_layout.sequences,
            input_buffered_bits = input_layout.buffered_bits,
            input_axes    = input_layout.axes,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            jingle_names = jingle_names,
            music_section_names = music_section_list,
            global_names  = set(global_names),
            string_globals = _string_globals,
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            owner_kind    = "camera",
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            jingle_policy = jingle_policy,
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
            ref_kinds     = ref_kinds,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
            spawn_exports = _spawn_meta,
            actor_sprites = _actor_libs,
            prefab_sprites = _prefab_libs,
            prefab_children = _prefab_child_ranks,
            prefab_child_sprites = _prefab_child_libs,
            actor_children = _actor_children,
            actor_child_sprites = _actor_child_libs,
            actor_exports = _actor_exports,
            actor_models = _actor_models,
        )
        cam_c, cam_warnings, _ = lua_generate(cam_ast, ctx_cam)
        for w in cam_warnings:
            emit("diagnostic", build_warning(w, "codegen", sp.name, actor=f"camera {cam.name}"))
        out_cam = p.src_dir / f"{cam_sym}.c"
        build_output.write(out_cam, cam_c)
        emit("log_line", f"[lua->c] {sp.name} -> {out_cam.name}")

    return True
