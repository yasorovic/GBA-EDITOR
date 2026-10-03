"""
editor/scripting/codegen.py — Transpileur AST normalisé → C.

Reçoit un LuaScript (parser.py) et un CodegenContext (informations de
build) et produit le source C d'un fichier actor_<Name>.c.

Règles de génération :
  - Variables locales top-level  → static <type> <name>; (scope fichier)
  - … sauf dans un prefab poolé, où celles que le script ÉCRIT deviennent un
    champ de g_state_<sym>[], une entrée par instance du pool
  - Variables globales (globals.h) → accès direct par nom
  - self:method(args)  → actor_method(self, args) via RUNTIME_API
  - module.func(args)  → func_c(args) via RUNTIME_API
  - Opérateurs Lua     → opérateurs C (and→&&, or→||, ~=→!=, not→!)
  - Strings d'args API → constantes entières (ANIM_*, SFX_*, BTN_*, TAG_*)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .parser import (
    LuaScript, LuaFunction, LuaLocal,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile,
    StmtForNum, StmtReturn, StmtBreak, StmtUnsupported,
    ExprNumber, ExprBool, ExprNil, ExprString, ExprName, ExprUnsupported,
    ExprIndex, ExprIndexAt, ExprTable, ExprInvoke, ExprCall, ExprBinop, ExprUnop,
    array_dims, require_target, DATA_NS,
    assigned_names, sequence_name, wait_call, WAIT_FN, WAIT_UNTIL_FN,
    local_names,
)
# Les volumes du modèle sont des POURCENTAGES ; chaque appel maxmod a sa
# propre échelle, et c'est ici qu'on convertit (cf. models/audio.py).
from core.app_info import APP_NAME
from core.models.audio import (
    volume_to_effect, volume_to_module, pitch_to_rate, panning_to_hardware,
    volume_to_effect_expr, volume_to_module_expr, pitch_to_rate_expr,
    panning_to_hardware_expr,
)
from .api import (
    RUNTIME_API, EVENT_C_SIGNATURES, KNOWN_EVENTS, ApiFunc, REF_TYPE_TABLE,
    KNOWN_EVENTS_BY_KIND, OWNER_KINDS_WITH_SELF, scene_event_sig,
    DOMAIN_OBJ_MODE, DOMAIN_DIRECTION, DOMAIN_WIN_REGION,
    DOMAIN_BLEND_MODE, DOMAIN_BLEND_SIDE, DOMAIN_EASE,
    hardware_enum_constant,
    DOMAIN_ANIM, DOMAIN_SPRITE_ID, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_AXIS,
    DOMAIN_INPUT_SEQUENCE,
    DOMAIN_TAG, DOMAIN_SCENE, DOMAIN_LANG,
    DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE, DOMAIN_MUSIC_BOX_TRIGGER,
    DOMAIN_CAMERA, camera_constant, DOMAIN_BOX_TAG, box_tag_constant,
    window_region_constant,
    DOMAIN_TEXT, DOMAIN_FONT, DOMAIN_IMAGE_STATE,
    DOMAIN_PALETTE, DOMAIN_UI_ELEMENT, ui_list_constant,
    ref_member, ref_upcast, ref_constant, REF_ACTOR, REF_UI_ELEMENT, REF_TEXT_REGION,
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL, DOMAIN_SEQUENCE,
    anim_constant, sprite_id_constant, sfx_constant, music_constant, key_constant, tag_constant, scene_constant,
    text_constant, font_constant, region_constant, anon_text_key, palette_constant,
    lang_constant,
    image_constant, image_state_constant, ui_element_constant,
    SCREEN_CONSTANTS,
)
from .checker import check as _lua_check, BuildContext as _BuildContext
from .expr_types import (VEC_CONSTRUCTORS, C_TYPES,
                         infer_vec_type, infer_ref_type, resolve_prop, element_of)


# ─── Types C des variables exposées (table `exports`) ─────────────
# Le type déclaré dans le .lua pilote la déclaration C émise. Le moteur est
# entièrement entier — aucun float dans runtime/ — donc `float` devient un int
# (le parser tronque déjà les littéraux, cf. ExprNumber). TOUS les types
# scalaires tombent sur un `int` : un `*_ref` est un index/handle (SFX_*,
# SCENE_IDX_*, TAG_*) et une `string` est un index de la table de textes
# (TEXT_*, entrée anonyme) — la résolution éditeur/spawn → valeur d'instance
# est câblée par le résolveur de lua_compiler (chantier « Les exports de
# script »). Rien n'est plus déclaré `const char *` : une string qui reste
# brute ne pourrait alimenter aucun appel du moteur (text.draw prend un index).
_EXPORT_C_TYPE: dict[str, str] = {
    "int":       "int",
    "float":     "int",
    "bool":      "int",
    "enum":      "int",
    "actor_ref": "int",
    "scene_ref": "int",
    "sfx_ref":   "int",
    "string":    "int",
}
# Types composites : pas de scalaire C, mais un type composé du moteur (Vec2/
# Vec3/Rect, cf. expr_types.C_TYPES). Déclarés dès qu'une valeur d'instance les
# résout (export_inits), sinon laissés en commentaire.
_EXPORT_COMPOSITE = ("vec2", "vec3", "rect")

# Types d'export réglables par instance (au build pour un posé, au spawn pour un
# poolé). Tous les types câblés : les scalaires tombent sur un `int`, les
# composites sur un Vec2/Vec3/Rect. Cf. chantier « Les exports de script ».
_EXPORT_SETTABLE = frozenset({
    "int", "float", "bool", "enum",
    "string", "actor_ref", "scene_ref", "sfx_ref",
    "vec2", "vec3", "rect",
})

# Ce qu'un champ d'état pèse par instance. Tout est aligné sur 4 octets côté
# ARM, donc la somme des champs est la taille de la structure — ce que le build
# annonce pour un prefab poolé (cf. CodeGen._emit_pool_state).
_STATE_BYTES = {"vec2": 8, "vec3": 12, "rect": 16}


def _export_setter_c_type(export_type: str) -> str:
    """Type C de l'argument d'un setter de spawn pour cet export : un scalaire
    câblé passe un `int` (index/handle ou entier), un composite passe son
    Vec2/Vec3/Rect. Un seul endroit, partagé par la DÉFINITION du setter (dans
    le `.c` du prefab) et son EXTERN (dans le `.c` du spawner) — sinon les deux
    déclarations divergeraient sur le type et le C ne lierait pas."""
    return C_TYPES.get(export_type, "int") if export_type in _EXPORT_COMPOSITE else "int"


# ─── Séquences : découpage ────────────────────────────────────────

@dataclass
class _Step:
    """Une tranche de séquence : soit du code, soit une attente."""
    kind:  str          # "body" | WAIT_FN | WAIT_UNTIL_FN
    stmts: list = field(default_factory=list)   # kind == "body"
    arg:   Any = None                            # l'attente : durée ou condition
    # Dernière tranche du corps d'une boucle bornée (ROADMAP v0.23) : au lieu
    # de passer à la tranche suivante, on incrémente le compteur et on REVIENT
    # en arrière tant qu'il reste des tours. Porté par la tranche plutôt que
    # par une tranche à part, pour que la boucle ne coûte PAS une frame de
    # plus par tour — un `case` rend la main, donc un `case` de bouclage se
    # paierait à chaque itération.
    loop_back: Any = None    # _LoopBack | None


@dataclass
class _LoopBack:
    """De quoi refermer une boucle bornée : `for var = start, stop [, step]`.

    `stop` est soit un entier écrit en clair (replié à l'émission), soit le
    nom du champ d'état où sa valeur a été rangée AU DÉBUT de la boucle — Lua
    n'évalue la borne qu'une fois, et la ré-évaluer à chaque tour donnerait un
    comportement différent le jour où elle change en cours de route."""
    var:   str          # champ d'état du compteur
    stop:  Any          # int littéral, ou nom de champ d'état
    step:  int          # le pas, écrit en clair (cf. checker._check_for_step)
    back:  int          # rang de la tranche où reprendre


@dataclass
class _SequencePlan:
    name:    str                # "intro"
    steps:   list               # list[_Step], numérotées 1..N à l'émission
    lifted:  list               # noms des locals qui traversent une attente
    timer:   bool               # au moins un wait(n) → un compteur partagé


def referenced_names(nodes) -> set[str]:
    """Tous les noms LUS ou ÉCRITS dans ces statements/expressions.

    Sert à une seule question : ce `local` est-il encore regardé APRÈS une
    attente ? Si oui il doit survivre, donc vivre dans l'état de la séquence."""
    found: set[str] = set()

    def expr(e):
        if e is None:
            return
        if isinstance(e, ExprName):
            found.add(e.name)
        elif isinstance(e, ExprIndex):
            expr(e.obj)
        elif isinstance(e, ExprIndexAt):
            expr(e.obj); expr(e.index)
        elif isinstance(e, ExprBinop):
            expr(e.left); expr(e.right)
        elif isinstance(e, ExprUnop):
            expr(e.operand)
        elif isinstance(e, ExprCall):
            expr(e.func)
            for a in e.args:
                expr(a)
        elif isinstance(e, ExprInvoke):
            expr(e.obj)
            for a in e.args:
                expr(a)
        elif isinstance(e, ExprTable):
            for it in e.items:
                expr(it)

    def walk(stmts):
        for s in stmts:
            if isinstance(s, StmtCall):
                expr(s.call)
            elif isinstance(s, StmtLocalAssign):
                expr(s.value)
            elif isinstance(s, StmtAssign):
                expr(s.target); expr(s.value)
            elif isinstance(s, StmtIf):
                expr(s.cond); walk(s.then)
                for c, b in s.elseifs:
                    expr(c); walk(b)
                walk(s.else_)
            elif isinstance(s, StmtWhile):
                expr(s.cond); walk(s.body)
            elif isinstance(s, StmtForNum):
                expr(s.start); expr(s.stop); expr(s.step); walk(s.body)
            elif isinstance(s, StmtReturn):
                for v in s.values:
                    expr(v)

    walk(nodes)
    return found



# ─── Contexte de génération ───────────────────────────────────────

@dataclass
class CodegenContext:
    """
    Informations fournies par build.py pour la génération du C.
    Permet de résoudre les constantes (ANIM_*, SFX_*…) à la compilation.
    """
    actor_name:   str            # "Hero" — utilisé comme préfixe C
    actor_sym:    str            # "Hero" nettoyé pour C (ex: "Mon_Hero")
    anim_names:   list[str]      # ["idle", "walk", "attack"] — depuis SpriteAsset
    sfx_names:    list[str]      # noms des Sfx du projet
    music_names:  list[str]      # noms des Music du projet
    global_names: set[str]       # noms des variables globales (depuis globals.h)
    const_names:  set[str]       # noms des constantes (depuis constants.h)
    all_actor_syms: list[str]    # tous les acteurs de la scène
    # Les ENFANTS de ce propriétaire, nom Lua → expression C qui les désigne
    # (ROADMAP v0.23). `self.bras` s'y lit : pour un acteur de scène c'est
    # une constante `&g_actors[TAG_*]`, pour la racine d'un prefab poolé un
    # décalage constant dans son groupe (`self + 2`). Résolu au BUILD dans
    # les deux cas — un enfant se NOMME, il ne se construit pas.
    child_refs: dict = field(default_factory=dict)
    # Fonctions citées par une frame de sprite : elles sont appelées depuis
    # main.c et doivent donc rester publiques, pas devenir des helpers static.
    frame_event_names: list[str] = field(default_factory=list)
    # `id` des composants sprite de ce propriétaire (ses apparences), dans l'ordre :
    # SPRITE_<ACTEUR>_<ID> = le rang que `OamEntry.appearance` désigne.
    sprite_ids: list[str] = field(default_factory=list)
    # Porteur à PLUSIEURS apparences : `anim_names` est l'UNION des noms d'état de
    # leurs sprites, et `anim_maps[a][k]` le rang de l'état `anim_names[k]` dans le
    # sprite de l'apparence `a` (255 = cet état n'existe pas dans ce sprite). Vide
    # pour un porteur à une apparence : `anim_names` est alors ses états, tels quels.
    anim_maps: list[list[int]] = field(default_factory=list)
    # Famille du PROPRIÉTAIRE du script : "actor" | "prefab" | "scene" | "camera". Elle
    # décide de tout ce qui dépend d'où le script est attaché — l'existence de `self`
    # (`has_self`), les événements admis (`KNOWN_EVENTS_BY_KIND`) et, sans `self`, le mot
    # du symbole C émis (`<sym>_scene_on_update` / `<sym>_camera_on_update`). Une caméra a
    # les mêmes points d'entrée qu'une scène et emprunte donc le même chemin.
    owner_kind: str = "actor"
    scripts_dir: Path | None = None  # racine project/scripts/ pour résoudre les require()
    # Prefab poolé : les variables de tête que le script ÉCRIT deviennent un
    # champ de `g_state_<sym>[]`, une entrée par instance (cf. _emit_pool_state).
    # `pool_size` ne sert qu'à CHIFFRER ce que cet état coûte — le C émis, lui,
    # se dimensionne sur `POOL_<SYM>_INSTANCES` (headers.py), pour qu'un écart
    # avec la boucle de pool de main.c soit impossible.
    is_pooled: bool = False
    pool_size: int = 0
    # Valeurs d'export résolues PAR INSTANCE (chantier « Les exports de script »).
    # nom d'export → initialiseur C déjà prêt, calculé par lua_compiler : l'override
    # d'instance (`ScriptComponent.exports_values`) s'il existe, sinon le `default`
    # du script, résolu selon le type (bool/enum → entier). Ne couvre que les types
    # entiers du premier jet (int/bool/float/enum) ; vide pour un prefab poolé
    # (D2 = tranche suivante). `_local_decl` s'en sert comme initialiseur prioritaire.
    export_inits: dict = field(default_factory=dict)
    # Exports RÉGLABLES d'un prefab, pour la table d'`actor:spawn("X", pos, {k=v})`
    # (chantier « Les exports de script », tranche poolé). nom de prefab → { nom
    # d'export → {"type": t, "values": [...]} }. Sert au spawner à résoudre une
    # valeur (bool→0/1, enum→index) et à nommer le setter. Rempli par lua_compiler.
    spawn_exports: dict = field(default_factory=dict)
    # Symbole C de la scène qui compile ce script (ROADMAP v0.17, T1). Les pools
    # étant per-scène, `actor:spawn("Bullet")` cible `spawn_<Scène>_Bullet` : il
    # faut donc savoir DANS QUELLE scène on compile. "" pour les unités partagées
    # (caméras) qui ne peuvent pas résoudre une scène — spawn y est refusé.
    scene_sym: str = ""
    scene_names: list[str] = field(default_factory=list)  # noms de scènes du projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    # Les triggers AUTOMATIQUES (on_spawn/on_destroy/un nom de bouton ou
    # d'action) ne passent plus par ici : `main_gen.py` les injecte directement au site d'appel
    # connu au build, pour qu'ils marchent aussi sur un actor SANS script (cf.
    # `SFX_AUTO_TRIGGERS`, core/models/components.py). Seul `self:play_sfx()`
    # (déclenchement manuel depuis un script) reste résolu ici.
    sfx_volumes: dict = field(default_factory=dict)  # {nom Sfx: volume EN %} — converti à l'émission
    music_info: dict = field(default_factory=dict)
    # {nom d'état: rang dans SA boîte}, par famille, et {déclencheur: rang}
    sound_box_states: dict = field(default_factory=dict)
    jingle_box_states: dict = field(default_factory=dict)
    music_box_triggers: dict = field(default_factory=dict)
    text_keys:  list[str] = field(default_factory=list)  # clés de la table de textes (ordre = index C)
    lang_codes: list[str] = field(default_factory=list)  # langues déclarées (ordre = index g_lang), [] en monolingue
    font_names: list[str] = field(default_factory=list)  # polices encodables (ordre = index dans g_fonts)
    palette_names: list[str] = field(default_factory=list)  # catalogue de couleurs (ordre = index dans g_palettes)
    region_names: list[str] = field(default_factory=list)  # emplacements de texte (ordre = index dans g_ui_regions)
    # Panneaux marqués LISTE (ordre = index dans g_ui_lists) — ROADMAP v0.22
    ui_list_names: list[str] = field(default_factory=list)
    image_names:  list[str] = field(default_factory=list)  # images d'interface (ordre = index dans g_ui_images)
    # TOUS les éléments d'UI, tous types confondus (ordre = index dans la table
    # de visibilité plate, UIELEM_*) — cf. Project.all_elements.
    element_names: list[str] = field(default_factory=list)
    # nom d'élément → type de référence que `interface:get(nom)` rend (`list`, `image`,
    # `text_region`, `ui_element`) — le même dictionnaire que `BuildContext.ref_kinds` :
    # le type jugé par le checker et la constante émise par le codegen parlent du même élément.
    ref_kinds: Optional[dict] = None
    # {nom d'image: [noms d'état de SON sprite]} — un état n'a de sens que dans
    # un sprite, et c'est l'image que le script nomme (cf. api.image_state_constant).
    image_states: dict = field(default_factory=dict)
    # Tables de données : {nom: (noms de colonnes, nombre de lignes)}. Le nombre
    # de lignes sert à `#data.X`, qui est une constante de compilation comme
    # `#t` sur un tableau — la taille est connue, elle n'est rangée nulle part.
    data_tables: dict = field(default_factory=dict)
    # Sauvegarde — deux faits du projet, portés jusqu'ici pour que le checker des
    # BEHAVIORS (relancé depuis ce contexte-ci) voie ce que voit celui des
    # acteurs. Sans eux, `save:write(7)` passerait dans un behavior et pas dans
    # un script d'acteur, ce qui serait incompréhensible.
    save_slots: Optional[int] = None
    has_persistent: Optional[bool] = None
    # {nom d'accord : masque C}, dérivé des `InputBinding` du projet — un
    # simple ET de boutons (cases à cocher), plus de mini-langage ici depuis
    # la décision de l'auteur du 2026-09-27. Les boutons physiques restent
    # résolus par `key_constant`.
    input_masks: dict = field(default_factory=dict)
    # {nom de séquence : (tables C, longueurs, fenêtre)} — le mini-langage
    # complet reste réservé aux séquences (`InputSequence`), lu par
    # `get_sequence` (cf. `codegen/runtime_codegen/input_layout.py`).
    input_sequences: dict = field(default_factory=dict)
    # Nom d'accord interrogé par `buffered()` → index de bit dans le bitset
    # `_g_input_buffered_consumed`. Absent = jamais bufferisé, aucun coût.
    input_buffered_bits: dict = field(default_factory=dict)
    # Nom d'axe (built-in "horizontal"/"vertical" ou `InputAxis` déclaré) →
    # (masque C négatif, masque C positif), pour `get_axis`.
    input_axes: dict = field(default_factory=dict)
    # Pour que gcc cite le SCRIPT et non le `.c` généré : `lua_file` est le script source,
    # `c_file` le fichier C qu'on écrit. Vides, aucune directive `#line` n'est émise (le C
    # d'un test unitaire reste tel quel).
    lua_file: str = ""
    c_file:   str = ""

    @property
    def has_self(self) -> bool:
        """Ce script a-t-il une instance attachée à désigner ? Un acteur ou un prefab, oui ;
        une scène ou une caméra, non — le C émis n'a alors pas de paramètre `Actor* self`."""
        return self.owner_kind in OWNER_KINDS_WITH_SELF


# ─── Générateur ───────────────────────────────────────────────────

# Marqueur d'une ligne à remplacer, à la toute fin, par `#line <n> "<fichier .c>"`. Le numéro
# n'est connu qu'une fois le texte final assemblé (l'état par instance est inséré après coup).
_LINE_RESET = "/*@@line-reset@@*/"


def _c_file_name(name: str) -> str:
    """Un nom de fichier sûr dans une chaîne C de directive `#line`."""
    return name.replace("\\", "/").replace('"', "")


def _resolve_line_resets(code: str, c_file: str) -> str:
    """Remplace chaque marqueur par une directive qui rend gcc à son vrai fichier, à sa vraie
    ligne : la directive occupe la ligne i+1, la suivante est donc i+2."""
    if _LINE_RESET not in code:
        return code
    lines = code.split("\n")
    for i, text in enumerate(lines):
        if text == _LINE_RESET:
            lines[i] = f'#line {i + 2} "{_c_file_name(c_file)}"'
    return "\n".join(lines)


class CodeGen:

    def __init__(self, ctx: CodegenContext):
        self.ctx   = ctx
        self._lines: list[str] = []
        self._indent = 0
        self._lua_file = ctx.lua_file   # le script dont on émet les statements (un behavior le change)
        self._block_depth = 0
        self._required_behaviors: dict[str, str] = {}  # alias Lua → sym C
        self._helpers: dict[str, LuaFunction] = {}
        self._in_helper = False
        # Prefab poolé — état par instance : nom Lua → champ de `<sym>State`.
        # C'est `_state_ref` qui en fait un accès (`_st->fx`), pour que la
        # forme vive à UN endroit. Vide pour un propriétaire unique.
        self._pool_state: dict[str, str] = {}
        self._pool_state_init: str = ""   # « .fx = FX_POP, .fx_t = 0 »
        self.pool_state_bytes: int = 0
        # Séquences — remplis par `_plan_sequences`, avant toute émission.
        self._seq_plans: list = []                 # list[_SequencePlan], ordre source
        self._plan_of: dict[str, _SequencePlan] = {}   # nom de handler → plan
        # (type C, champ, init) de l'état des séquences. Champs de `<sym>State`
        # pour un prefab poolé, statiques de fichier sinon.
        self._state_extra: list[tuple[str, str, str]] = []
        # Actif pendant l'émission d'UNE séquence : ses locals qui traversent
        # une attente, et le champ d'état où ils vivent (cf. _emit_sequence).
        self._local_state: dict[str, str] = {}
        # Le corps en cours d'émission a-t-il touché l'état de l'instance ?
        # C'est ce qui décide de poser `_st` en tête (cf. _close_state_scope).
        self._state_touched: bool = False
        # Tableaux déclarés dans ce script : nom → dimensions. Sert à `#t`, qui
        # est une constante de compilation — la taille fait partie du type, donc
        # elle n'est rangée nulle part à l'exécution.
        self._arrays: dict[str, tuple[int, ...]] = {}
        # Locals vec2/vec3 : nom → type. Rempli au fil de l'émission (comme
        # `_arrays` ci-dessus), pour que `_expr` sache émettre `vec2_add(...)`
        # plutôt que `+` sur un `a + b` dont les deux côtés sont des vecteurs.
        # Cf. scripting/vec_types.py — même règle que checker.py.
        self._vec_types: dict[str, str] = {}
        # Locals qui tiennent une référence : nom → type (cf. expr_types).
        self._ref_types: dict[str, str] = {}
        # Le nom de l'élément d'interface qu'un local tient (cf. expr_types.element_of),
        # ou None s'il en tient plusieurs : l'état d'une image se nomme dans SON sprite.
        self._ref_elements: dict[str, Optional[str]] = {}
        self._local_names: set[str] = set()
        self.warnings: list[str] = []  # diagnostics non bloquants (ex: behavior manquant/invalide)

    @property
    def _kinds(self):
        """Nom d'élément d'interface → type de référence (`CodegenContext.ref_kinds`), lu
        dans la mise en page : le même dictionnaire que celui du checker, sans quoi le
        type jugé et la constante émise ne parleraient pas du même élément."""
        return self.ctx.ref_kinds

    def _note_ref(self, name: str, value) -> Optional[str]:
        """Retient le type d'une référence tenue par un `local`, et l'élément d'interface
        qu'elle désigne. Rend le type (None si `value` n'en rend pas une)."""
        rt = infer_ref_type(value, self._kinds, self._ref_types) if value is not None else None
        if rt:
            self._ref_types[name] = rt
            element = element_of(value)
            if name in self._ref_elements and self._ref_elements[name] != element:
                self._ref_elements[name] = None
            else:
                self._ref_elements[name] = element
        return rt

    # ── API publique ──────────────────────────────────────────────

    def generate(self, script: LuaScript) -> str:
        """Retourne le source C complet pour ce script."""
        # Le découpage des séquences vient d'abord : il dit quel état déclarer,
        # et `_emit_locals` en a besoin pour le poser au bon endroit (champ de
        # la structure de pool, ou statique de fichier).
        self._script = script
        self._plan_sequences(script)
        self._local_names = local_names(script)
        self._helpers = {fn.name: fn for fn in script.functions
                         if self._is_internal_helper(fn)}
        self._emit_header()
        self._emit_locals(script)
        # Inline des behaviors requis (collectés pendant _emit_locals via StmtLocalAssign)
        self._emit_inlined_behaviors(script)
        self._emit_helper_declarations()
        for fn in self._helpers.values():
            self._emit_helper(fn)
        # Remise à l'état de départ du slot, pour les prefabs poolés (avant les handlers)
        if self.ctx.is_pooled:
            self._emit_pool_init()
        defined = set()
        for fn in script.functions:
            if fn.name in self._helpers:
                continue
            plan = self._plan_of.get(fn.name)
            if plan is not None:
                self._emit_sequence(plan)
            else:
                self._emit_function(fn)
                defined.add(fn.name)
        # Stubs vides pour les events non définis (évite les erreurs de linker)
        known = self._known_hooks()
        for event in known:
            if event not in defined:
                self._emit_stub(event)
        return _resolve_line_resets("\n".join(self._lines) + "\n", self.ctx.c_file)

    def _is_internal_helper(self, fn: LuaFunction) -> bool:
        known = self._known_hooks()
        return ("." not in fn.name
                and fn.name not in known
                and fn.name not in (self.ctx.frame_event_names or ())
                and sequence_name(fn.name) is None)

    def _helper_signature(self, fn: LuaFunction) -> str:
        params = [f"int {p}" for p in fn.params]
        if self.ctx.has_self:
            params.insert(0, "Actor* self")
        return f"static int {self.ctx.actor_sym}_{fn.name}({', '.join(params) or 'void'})"

    def _emit_helper_declarations(self):
        if not self._helpers:
            return
        self._w("/* Private functions of the script */")
        for fn in self._helpers.values():
            self._w(self._helper_signature(fn) + ";")
        self._w("")

    def _emit_helper(self, fn: LuaFunction):
        self._w(self._helper_signature(fn) + " {")
        self._indent += 1
        mark = self._open_state_scope()
        self._in_helper = True
        self._emit_block(fn.body)
        self._in_helper = False
        # Un helper rend toujours un entier. Ignorer sa valeur est permis et
        # `return` nu reste une sortie valide, avec 0 comme valeur neutre.
        self._w("return 0;")
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")

    # ── Séquences ─────────────────────────────────────────────────

    @staticmethod
    def _literal_int(e) -> Any:
        """La valeur d'un littéral entier, signe compris, sinon None. Même
        lecture que `checker._literal_int` — un `-1` est un moins unaire posé
        sur un nombre, pas un nombre négatif, et les deux doivent en tirer la
        même conclusion sous peine de se contredire."""
        if isinstance(e, ExprNumber):
            return e.value
        if (isinstance(e, ExprUnop) and e.op == "-"
                and isinstance(e.operand, ExprNumber)):
            return -e.operand.value
        return None

    @staticmethod
    def _block_has_wait(stmts) -> bool:
        """Une attente quelque part dans ce bloc, si profond soit-elle. C'est
        ce qui distingue une boucle ORDINAIRE — émise telle quelle dans une
        tranche — d'une boucle qu'il faut dérouler en tranches."""
        for s in stmts:
            if wait_call(s) is not None:
                return True
            for sub in (getattr(s, "body", None), getattr(s, "then", None),
                        getattr(s, "else_", None)):
                if sub and CodeGen._block_has_wait(sub):
                    return True
            for _c, b in getattr(s, "elseifs", []) or []:
                if CodeGen._block_has_wait(b):
                    return True
        return False

    def _slice_block(self, stmts, seq: str, steps: list, loop_fields: list):
        """Découpe un bloc en tranches, en descendant dans les boucles bornées.

        Récursif, et c'est ce qui rend une boucle imbriquée gratuite : chaque
        niveau referme la sienne sur la dernière tranche de son corps. Une
        boucle SANS attente n'est pas touchée — elle reste un `for` C ordinaire
        au milieu d'une tranche, comme avant la v0.23."""
        buf: list = []

        def flush():
            if buf:
                steps.append(_Step("body", stmts=list(buf)))
                buf.clear()

        for stmt in stmts:
            w = wait_call(stmt)
            if w is not None:
                flush()
                steps.append(_Step(w[0], arg=w[1]))
                continue
            if isinstance(stmt, StmtForNum) and self._block_has_wait(stmt.body):
                # Le compteur (et la borne, si elle n'est pas écrite en clair)
                # traversent des attentes : ils vivent dans l'état de la
                # séquence, comme n'importe quel `local` qui survit.
                var_field = stmt.var
                loop_fields.append(var_field)
                init = [StmtAssign(target=ExprName(stmt.var), value=stmt.start)]
                stop_lit = self._literal_int(stmt.stop)
                if stop_lit is None:
                    bound = f"{stmt.var}_bound_{len(loop_fields)}"
                    loop_fields.append(bound)
                    init.append(StmtAssign(target=ExprName(bound), value=stmt.stop))
                    stop_ref: Any = bound
                else:
                    stop_ref = int(stop_lit)
                # L'initialisation rejoint la tranche EN COURS : elle ne coûte
                # pas une frame, elle prépare celle qui suit.
                buf.extend(init)
                flush()
                first = len(steps) + 1          # rang 1-based de la 1re tranche du corps
                self._slice_block(stmt.body, seq, steps, loop_fields)
                if len(steps) < first:
                    # Corps vide après découpage : rien à répéter.
                    continue
                step_val = 1
                if stmt.step is not None:
                    lit = self._literal_int(stmt.step)
                    if lit is not None:
                        step_val = int(lit)
                # Une CHAÎNE et non une seule refermeture : deux boucles
                # imbriquées se referment sur la même tranche — celle de
                # l'attente la plus profonde — et c'est la plus INTÉRIEURE qui
                # doit être testée en premier. Écraser au lieu d'empiler
                # laissait la boucle intérieure sans fin de course.
                steps[-1].loop_back = (steps[-1].loop_back or []) + [
                    _LoopBack(var=stmt.var, stop=stop_ref,
                              step=step_val, back=first)]
                continue
            buf.append(stmt)
        flush()

    def _plan_sequences(self, script: LuaScript):
        """Découpe chaque séquence à ses attentes, et dit quel état elle demande.

        Rien n'est émis ici : le résultat sert d'abord à DÉCLARER l'état (au bon
        endroit selon que le propriétaire est poolé ou non), et seulement
        ensuite à écrire le `switch`."""
        for fn in script.functions:
            name = sequence_name(fn.name)
            if name is None:
                continue
            steps: list = []
            loop_fields: list[str] = []
            self._slice_block(fn.body, name, steps, loop_fields)
            if not steps:
                # Une séquence vide garde une tranche : elle démarre et
                # s'arrête, plutôt que de rester sur une étape que rien ne fait
                # avancer.
                steps.append(_Step("body", stmts=[]))

            # Un `local` de la séquence encore regardé après une attente doit
            # survivre : il devient un champ de l'état. Ceux qui vivent et
            # meurent dans leur tranche restent des locals C.
            lifted, plus_tard = [], set()
            for i in range(len(steps) - 1, -1, -1):
                st = steps[i]
                if st.kind == "body":
                    for s in st.stmts:
                        if isinstance(s, StmtLocalAssign) and s.name in plus_tard:
                            if s.name not in lifted:
                                lifted.append(s.name)
                    plus_tard |= referenced_names(st.stmts)
                else:
                    plus_tard |= referenced_names([StmtCall(call=ExprCall(
                        func=ExprName(st.kind), args=[st.arg] if st.arg else []))])
            lifted.reverse()
            # Le compteur d'une boucle bornée (et sa borne calculée) traversent
            # forcément une attente — c'est la définition même du chantier
            # v0.23. Ils rejoignent donc l'état, sans passer par l'analyse
            # ci-dessus : celle-ci ne voit que les `local`, et un compteur de
            # `for` n'en est pas un.
            for f in loop_fields:
                if f not in lifted:
                    lifted.append(f)

            plan = _SequencePlan(
                name=name, steps=steps, lifted=lifted,
                timer=any(st.kind == WAIT_FN for st in steps))
            self._seq_plans.append(plan)
            self._plan_of[fn.name] = plan

            # L'état demandé par cette séquence : l'étape, le compteur s'il y a
            # une durée à décompter, et les locals qui traversent.
            self._state_extra.append(("int", f"seq_{name}_step", "0"))
            if plan.timer:
                self._state_extra.append(("int", f"seq_{name}_timer", "0"))
            for loc in lifted:
                self._state_extra.append(("int", f"seq_{name}_{loc}", "0"))

    def _state_ref(self, field: str) -> str:
        """Où vit ce morceau d'état — dans le slot de l'instance pour un prefab
        poolé, dans une statique de fichier pour un propriétaire unique.

        Côté poolé, l'accès passe par `_st`, un pointeur posé en tête de la
        fonction qui en a besoin (cf. `_close_state_scope`). Écrire
        `g_state_Ball[Ball_pool_slot(self)].fx` à chaque site rendait le C
        illisible — 38 caractères de machinerie autour du nom que l'auteur a
        écrit — et laissait gcc recalculer le slot plus souvent que nécessaire
        (`sizeof(Actor)` ne vaut pas une puissance de deux : la soustraction de
        pointeurs coûte une division)."""
        if self.ctx.is_pooled:
            self._state_touched = True
            return f"_st->{field}"
        return f"{self.ctx.actor_sym}_{field}"

    # ── Le pointeur d'état d'un prefab poolé ──────────────────────

    def _open_state_scope(self) -> int:
        """Retient où insérer `_st`, et repart d'un corps qui n'y a pas encore
        touché. À appeler juste après l'accolade ouvrante d'une fonction."""
        self._state_touched = False
        return len(self._lines)

    def _close_state_scope(self, mark: int, receiver: str = "self"):
        """Pose `_st` en tête du corps, s'il y a servi.

        S'il n'a pas servi, ne rien poser : un pointeur déclaré et jamais lu,
        c'est un `-Wunused-variable` à chaque build."""
        if not self._state_touched:
            return
        sym = self.ctx.actor_sym
        self._lines.insert(
            mark,
            "    " * self._indent
            + f"{sym}State* _st = &g_state_{sym}[{sym}_pool_slot({receiver})];")
        self._state_touched = False

    def _emit_sequence_statics(self):
        """L'état des séquences d'un propriétaire NON poolé — une statique par
        champ. Pour un prefab poolé, ces mêmes champs sont déjà entrés dans
        `<sym>State` (cf. _emit_pool_state)."""
        if not self._state_extra or self.ctx.is_pooled:
            return
        sym = self.ctx.actor_sym
        self._w("/* Sequence state — 0 = stopped, 1..N = the current step */")
        for c_type, field, init in self._state_extra:
            self._w(f"static {c_type} {sym}_{field} = {init};")
        self._w("")

    def _emit_sequence_decls(self):
        """Déclarations avancées des tranches : `on_update` les appelle, et il
        peut être écrit avant elles dans le fichier Lua."""
        if not self._seq_plans:
            return
        arg = "Actor* self" if self.ctx.has_self else "void"
        for plan in self._seq_plans:
            self._w(f"static void {self._sequence_sym(plan)}({arg});")
        self._w("")

    def _sequence_sym(self, plan: _SequencePlan) -> str:
        kind = "" if self.ctx.has_self else f"_{self.ctx.owner_kind}"
        return f"{self.ctx.actor_sym}{kind}_sequence_{plan.name}"

    def _emit_sequence(self, plan: _SequencePlan):
        """Le `switch` d'une séquence : un `case` par tranche, dans l'ordre de
        la source, et une tranche par frame.

        Pas de boucle autour du `switch` — chaque case rend la main. Une
        séquence à N attentes coûte donc N frames de plus qu'une exécution en
        ligne droite, et ne peut structurellement pas tourner en rond."""
        arg  = "Actor* self" if self.ctx.has_self else "void"
        # Les locals qui traversent une attente sont lus et écrits dans l'état
        # pour toute la durée de l'émission de cette séquence — y compris leur
        # `local x = …`, qui devient une simple affectation.
        self._local_state = {loc: f"seq_{plan.name}_{loc}" for loc in plan.lifted}
        self._w(f"/* Sequence \"{plan.name}\" — one slice per wait, in source order.")
        if plan.lifted:
            self._w(f"   Survive the wait: {', '.join(plan.lifted)}. */")
        else:
            self._w("   No variable crosses a wait. */")
        self._w(f"static void {self._sequence_sym(plan)}({arg}) {{")
        self._indent += 1
        mark = self._open_state_scope()
        step_ref = self._state_ref(f"seq_{plan.name}_step")
        self._w(f"switch ({step_ref}) {{")
        for i, st in enumerate(plan.steps, start=1):
            suivant = i + 1 if i < len(plan.steps) else 0
            fin = "   /* last slice: the sequence stops */" if suivant == 0 else ""
            if st.kind == "body":
                self._w(f"case {i}: {{")
            elif st.kind == WAIT_FN:
                self._w(f"case {i}: {{   /* {WAIT_FN}({self._expr(st.arg)}) */")
            else:
                self._w(f"case {i}: {{   /* {WAIT_UNTIL_FN} */")
            self._indent += 1
            if st.kind == "body":
                self._emit_block(st.stmts)
            elif st.kind == WAIT_FN:
                timer = self._state_ref(f"seq_{plan.name}_timer")
                self._w(f"if (++{timer} < {self._expr(st.arg)}) break;")
                self._w(f"{timer} = 0;")
            else:
                self._w(f"if (!({self._expr(st.arg)})) break;")
            if not st.loop_back:
                self._w(f"{step_ref} = {suivant};{fin}")
            else:
                # Refermeture des boucles bornées qui finissent sur cette
                # tranche (ROADMAP v0.23) : on incrémente le compteur puis on
                # décide où reprendre. Le SENS de la comparaison vient du signe
                # du pas, écrit en clair — même règle que pour un `for`
                # ordinaire (checker._check_for_step), et pour la même raison :
                # rien n'est testé à l'exécution qui puisse l'être au build.
                # De la plus INTÉRIEURE à la plus extérieure : la boucle du
                # dessus ne reprend que lorsque celle du dessous a fini.
                depth = 0
                for lb in st.loop_back:
                    counter = self._state_ref(f"seq_{plan.name}_{lb.var}")
                    stop = (str(lb.stop) if isinstance(lb.stop, int)
                            else self._state_ref(f"seq_{plan.name}_{lb.stop}"))
                    cmp_op = "<=" if lb.step >= 0 else ">="
                    delta = f"+ {lb.step}" if lb.step >= 0 else f"- {-lb.step}"
                    self._w(f"{counter} = {counter} {delta};")
                    self._w(f"if ({counter} {cmp_op} {stop}) {{ "
                            f"{step_ref} = {lb.back}; }} else {{")
                    self._indent += 1
                    depth += 1
                self._w(f"{step_ref} = {suivant};{fin}")
                for _ in range(depth):
                    self._indent -= 1
                    self._w("}")
            self._indent -= 1
            self._w("} break;")
        self._w("}")
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")
        self._local_state = {}

    def _emit_sequence_pump(self):
        """Les séquences avancent à la FIN de `on_update`, dans l'ordre de
        déclaration. Un seul endroit, visible dans le C émis, et rien à ajouter
        à la boucle de frame de `main.c` — elle appelle déjà `on_update` pour
        chaque propriétaire. Le test sur l'étape évite l'appel quand la
        séquence est arrêtée."""
        if not self._seq_plans:
            return
        arg = "self" if self.ctx.has_self else ""
        self._w("/* Sequences — in declaration order */")
        for plan in self._seq_plans:
            step_ref = self._state_ref(f"seq_{plan.name}_step")
            self._w(f"if ({step_ref}) {self._sequence_sym(plan)}({arg});")

    def _emit_pool_init(self):
        """Génère void SYM_pool_init(Actor* self) — appelée par spawn avant
        on_start. Une seule affectation de structure : elle couvre les tableaux
        et les vecteurs, qu'un champ à la fois ne saurait pas réinitialiser."""
        sym = self.ctx.actor_sym
        self._w(f"void {sym}_pool_init(Actor* self) {{")
        self._indent += 1
        mark = self._open_state_scope()
        if self._pool_state_init:
            # Littéral composé, et non un `static const` de fichier : l'état de
            # départ cite les constantes du script (`.fx = FX_POP`), qui sont
            # des variables C — le C n'accepte pas une variable dans
            # l'initialiseur d'un objet statique, même déclarée `const`.
            self._state_touched = True
            self._w(f"*_st = ({sym}State){{ {self._pool_state_init} }};")
        else:
            self._w("(void)self;")
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_inlined_behaviors(self, script: LuaScript):
        """Parse et transpile les behaviors requis en fonctions C statiques inline."""
        from .parser import parse as lua_parse, LuaParseError
        if not self._required_behaviors or not self.ctx.scripts_dir:
            return
        self._w("/* ── Inlined behaviors ── */")
        for alias, sym in self._required_behaviors.items():
            stem = sym[len("beh_"):]          # "paddle_ai"
            beh_path = self.ctx.scripts_dir / "behaviors" / f"{stem}.lua"
            if not beh_path.exists():
                msg = f"behavior '{stem}' not found: {beh_path}"
                self._w(f"/* {msg} */")
                self.warnings.append(msg)
                continue
            beh_src = beh_path.read_text(encoding="utf-8")
            try:
                beh_ast = lua_parse(beh_src)
            except LuaParseError as ex:
                ou = f"{stem}.lua:{ex.line}" if ex.line else f"behavior '{stem}'"
                msg = f"{ou} : {ex}"
                self._w(f"/* {msg} */")
                self.warnings.append(msg)
                continue
            # Validation basique (mêmes vérifs que les scripts actor/scène/prefab,
            # avec le contexte de l'actor qui inline ce behavior — pas de vérif de
            # plage sur les globals ici, cf. ARCHITECTURE.md pour les limites connues).
            check_ctx = _BuildContext(
                actor_name   = self.ctx.actor_name,
                owner_kind   = "behavior",
                anim_names   = self.ctx.anim_names,
                sprite_ids   = self.ctx.sprite_ids,
                sfx_names    = self.ctx.sfx_names,
                music_names  = self.ctx.music_names,
                scene_names  = self.ctx.scene_names,
                global_names = list(self.ctx.global_names) if self.ctx.global_names else None,
                const_names  = list(self.ctx.const_names) if self.ctx.const_names else None,
                sfx_component_name = self.ctx.sfx_component_name,
                save_slots   = self.ctx.save_slots,
                has_persistent = self.ctx.has_persistent,
                data_tables  = self.ctx.data_tables or None,
                ref_kinds    = self.ctx.ref_kinds,
                image_states = self.ctx.image_states or None,
            )
            for err in _lua_check(beh_ast, check_ctx, check_event_names=False):
                self.warnings.append(f"behavior '{stem}': {err.message}")
            # Émettre chaque fonction du module comme helper C statique préfixé
            for fn in beh_ast.functions:
                # Ignore le nom de module (M.update → beh_paddle_ai_update)
                func_name = fn.name.split(".")[-1] if "." in fn.name else fn.name
                c_name    = f"{sym}_{func_name}"
                # Signature : premier param est l'actor receveur (conventionnellement "actor" ou "self")
                params_c  = ", ".join(
                    f"Actor* {p}" if i == 0 else f"int {p}"
                    for i, p in enumerate(fn.params)
                )
                self._w(f"static void {c_name}({params_c}) {{")
                self._indent += 1
                # Le receveur d'un behavior n'est pas forcément nommé `self` :
                # si son corps touche l'état de l'hôte (un homonyme d'une
                # variable de tête), c'est SON premier paramètre qui donne
                # l'instance. Cf. ARCHITECTURE.md pour la limite connue de
                # cette substitution par nom.
                mark = self._open_state_scope()
                host_file, self._lua_file = self._lua_file, (
                    beh_path.name if self._lua_file else "")
                self._emit_block(fn.body)
                self._lua_file = host_file
                if fn.params:
                    self._close_state_scope(mark, receiver=fn.params[0])
                self._state_touched = False
                self._indent -= 1
                self._w("}")
                self._w("")

    # ── En-tête ───────────────────────────────────────────────────

    def _known_hooks(self) -> list:
        """Les points d'entrée admis pour ce propriétaire — une scène en a
        trois, une caméra deux, un acteur ou un prefab tous ceux de l'acteur (cf. KNOWN_EVENTS_BY_KIND)."""
        return KNOWN_EVENTS_BY_KIND[self.ctx.owner_kind]

    def _emit_header(self):
        sym = self.ctx.actor_sym
        if not self.ctx.has_self:
            kind = self.ctx.owner_kind
            self._w(f"/* {sym}.c — {kind} script, generated by {APP_NAME} (do not edit) */")
        else:
            self._w(f"/* actor_{sym}.c — generated by {APP_NAME} (do not edit) */")
        # `runtime_api.h` et non `runtime.h` : c'est l'en-tête généré qui porte
        # la vraie struct Actor et l'API. Le C émis l'incluait autrefois sous le
        # nom `runtime.h`, que chaque appelant remplaçait ensuite par celui-ci —
        # un détour dont il ne restait que le nom.
        self._w('#include "runtime_api.h"')
        self._w('#include "globals.h"')
        self._w('#include "constants.h"')
        self._w('#include "gba_debug.h"')   # debug.log — ROADMAP v0.14
        # Toujours inclus, même sans table : l'en-tête est toujours généré, et
        # un include conditionnel serait un second chemin pour un cas vide.
        self._w('#include "data_tables.h"')
        # Setters d'exports des prefabs que CE script spawne avec une table de
        # valeurs (tranche poolé D2) : ils sont définis dans le `.c` du prefab
        # visé, on les forward-déclare ici pour compiler l'appel.
        externs = self._spawn_setter_externs(getattr(self, "_script", None))
        if externs:
            self._w("")
            for e in externs:
                self._w(e)
        # Forward declarations pour éviter les erreurs d'ordre (ex: destroy appelle on_destroy)
        if self.ctx.has_self:
            self._w("")
            known = KNOWN_EVENTS
            for event in known:
                sig_tpl = EVENT_C_SIGNATURES.get(event)
                if sig_tpl:
                    self._w(sig_tpl.format(prefix=sym) + ";")
        # Constantes d'animation pour cet acteur
        if self.ctx.anim_names:
            self._w("")
            self._w(f"/* Animations de {self.ctx.actor_name} */")
            if self.ctx.anim_maps:
                # Plusieurs apparences : le rang d'un état dépend du sprite AFFICHÉ,
                # inconnu à la compile. La constante est donc une expression qui lit
                # l'apparence de `self` — `self` existe dans tout script d'acteur, et
                # `other:play_anim` est refusé par le checker (domaine du récepteur).
                rows = ",".join("{" + ",".join(str(v) for v in m) + "}" for m in self.ctx.anim_maps)
                self._w(f"static const unsigned char {sym}_anim_map"
                        f"[{len(self.ctx.anim_maps)}][{len(self.ctx.anim_names)}] = {{{rows}}};")
                for i, name in enumerate(self.ctx.anim_names):
                    self._w(f"#define {anim_constant(sym, name)} "
                            f"((int){sym}_anim_map[actor_get_appearance(self)][{i}])")
            else:
                for i, name in enumerate(self.ctx.anim_names):
                    self._w(f"#define {anim_constant(sym, name)} {i}")
        # Constantes des apparences (composants sprite) de cet acteur
        if self.ctx.sprite_ids:
            self._w("")
            self._w(f"/* Sprites (apparences) de {self.ctx.actor_name} */")
            for i, sid in enumerate(self.ctx.sprite_ids):
                self._w(f"#define {sprite_id_constant(sym, sid)} {i}")
        # Constantes SFX
        if self.ctx.sfx_names:
            self._w("")
            self._w("/* SFX */")
            for i, name in enumerate(self.ctx.sfx_names):
                self._w(f"#define {sfx_constant(name)} {i}")
        # Constantes Music
        if self.ctx.music_names:
            self._w("")
            self._w("/* Music */")
            for i, name in enumerate(self.ctx.music_names):
                self._w(f"#define {music_constant(name)} {i}")
        # Constantes Texte — index dans la table g_texts émise par main_gen
        if self.ctx.text_keys:
            self._w("")
            self._w("/* Textes */")
            for i, key in enumerate(self.ctx.text_keys):
                self._w(f"#define {text_constant(key)} {i}")
        # Constantes Langue — même index que g_texts[lang]/g_lang_font[lang]
        # (source en 0, puis settings.languages dans l'ordre déclaré). Absent
        # d'un projet monolingue : lang.set/lang.get n'y compilent alors plus,
        # ce qui est le comportement voulu (ROADMAP v0.9, phase 4).
        if self.ctx.lang_codes:
            self._w("")
            self._w("/* Langues */")
            for i, code in enumerate(self.ctx.lang_codes):
                self._w(f"#define {lang_constant(code)} {i}")
        # Constantes Police — index dans g_fonts (même ordre que main_gen)
        if self.ctx.font_names:
            self._w("")
            self._w("/* Fonts */")
            for i, name in enumerate(self.ctx.font_names):
                self._w(f"#define {font_constant(name)} {i}")
        # Constantes Palette — index dans g_palettes. Le catalogue ENTIER y
        # passe : une palette pèse 32 octets en ROM, là où la réservation des
        # polices coûtait de la mémoire vidéo. Rien à dériver des scripts, donc
        # aucun risque de réserver trop peu — le piège que `scene_font_names`
        # doit désamorcer n'existe pas ici.
        if self.ctx.palette_names:
            self._w("")
            self._w("/* Palettes */")
            for i, name in enumerate(self.ctx.palette_names):
                self._w(f"#define {palette_constant(name)} {i}")
        # Constantes Zone de texte — index dans g_ui_regions. L'espace de noms
        # est le PROJET, pas la mise en page (cf. models/ui_region.py) : c'est
        # ce qui permet à cette table d'être plate, comme celle des textes.
        if self.ctx.region_names:
            self._w("")
            self._w("/* Text slots */")
            for i, name in enumerate(self.ctx.region_names):
                self._w(f"#define {region_constant(name)} {i}")
        # Constantes de LISTE — index dans g_ui_lists (ROADMAP v0.22). Espace
        # séparé de REGION_*/UIELEM_* : une liste est un panneau, mais son rang
        # est celui des LISTES, pas celui de tous les éléments.
        if self.ctx.ui_list_names:
            self._w("")
            self._w("/* Listes d'interface (navigation) */")
            for i, name in enumerate(self.ctx.ui_list_names):
                self._w(f"#define {ui_list_constant(name)} {i}")
        # Constantes Image — index dans g_ui_images, même espace de noms projet
        # et même raison. Les ÉTATS suivent, indexés par IMAGE : un nom d'état
        # n'existe que dans un sprite, et c'est l'image que le script nomme.
        if self.ctx.image_names:
            self._w("")
            self._w("/* Images d'interface */")
            for i, name in enumerate(self.ctx.image_names):
                self._w(f"#define {image_constant(name)} {i}")
                for k, st in enumerate(self.ctx.image_states.get(name, [])):
                    self._w(f"#define {image_state_constant(name, st)} {k}")
        # Constantes d'élément d'UI — index dans la table de visibilité plate,
        # espace SÉPARÉ de REGION_*/IMAGE_* : elle couvre aussi les panels-
        # groupes purs, qui n'y figurent dans aucune des deux autres tables.
        if self.ctx.element_names:
            self._w("")
            self._w("/* Interface elements (visibility) */")
            for i, name in enumerate(self.ctx.element_names):
                self._w(f"#define {ui_element_constant(name)} {i}")
        self._w("")

    # ── Variables locales top-level (static = scope fichier) ──────

    def _emit_locals(self, script: LuaScript):
        # Pré-enregistrer les require() et les exclure des déclarations C. La
        # FORME est reconnue par `parser.require_target`, où vit déjà celle du
        # tableau — elle était réécrite ici, et une deuxième fois plus bas.
        non_require = []
        for loc in script.locals:
            target = require_target(loc.value)
            if target is None:
                non_require.append(loc)
            else:
                self._required_behaviors[loc.name] = f"beh_{Path(target).stem}"
        # Ce qui change appartient à l'INSTANCE, ce qui ne change pas appartient
        # au PREFAB. Un `local FX_POP = 1` qu'aucune ligne n'assigne est une
        # constante : la recopier dans chaque slot du pool ferait payer seize
        # fois une valeur qui ne bouge jamais, et ferait mentir la mesure du
        # build — qui annoncerait la longueur de l'en-tête du fichier au lieu de
        # l'état. Un acteur de scène n'a qu'une instance : tout y reste partagé.
        #
        # EXCEPTION (chantier « Les exports de script », tranche poolé) : un export
        # de type réglable est TOUJOURS par instance, même lu seulement — deux
        # spawns du même prefab peuvent lui donner des valeurs différentes. On
        # renonce donc à le fondre en constante (uniformisation décidée avec
        # l'auteur : quelques octets par instance contre un scan inter-script).
        if self.ctx.is_pooled:
            written = assigned_names(script)
            def _instance(loc):
                return loc.name in written or loc.export_type in _EXPORT_SETTABLE
            state  = [loc for loc in non_require if _instance(loc)]
            shared = [loc for loc in non_require if not _instance(loc)]
        else:
            state, shared = [], non_require

        if shared:
            self._w("/* Script constants — never assigned, hence shared by all "
                    "instances */" if self.ctx.is_pooled
                    else "/* Local variables of this actor */")
            for loc in shared:
                self._emit_shared_local(loc)
            self._w("")
        if state or (self.ctx.is_pooled and self._state_extra):
            self._emit_pool_state(state)
        self._emit_sequence_statics()
        self._emit_sequence_decls()

    def _emit_shared_local(self, loc: LuaLocal):
        """Un local de tête déclaré au scope FICHIER : une seule copie pour
        tout le programme."""
        # Export composite (Vec2/Vec3/Rect) AVANT le test tableau : son défaut de
        # source est une table `{x, y}`, que `array_dims` prendrait pour un
        # tableau `int[2]`. La valeur d'instance (export_inits) a déjà résolu le
        # littéral ; on note le type pour que `_expr` reconnaisse ses usages
        # ultérieurs comme un vec, puis `_local_decl` rend le type composé.
        if (loc.export_type in _EXPORT_COMPOSITE
                and self.ctx.export_inits.get(loc.name) is not None):
            self._vec_types[loc.name] = loc.export_type
            c_type, init, _note = self._local_decl(loc)
            self._w(f"static {c_type} {self._unused_attr(loc)}{loc.name} = {init};")
            return
        dims = array_dims(loc.value)
        if dims:
            self._arrays[loc.name] = dims
            self._w(f"static {self._array_decl(loc.name, dims)} = "
                    f"{self._array_init(loc.value, dims)};")
            return
        vt = infer_vec_type(loc.value, self._vec_types, self._ref_types, self._kinds) if loc.value is not None else None
        if vt:
            self._vec_types[loc.name] = vt
            self._w(f"static {C_TYPES[vt]} {loc.name} = {self._expr(loc.value)};")
            return
        c_type, init, note = self._local_decl(loc)
        if c_type is None:
            self._w(f"/* {loc.name} : {note} */")
            return
        suffix = f"   /* {note} */" if note else ""
        self._w(f"static {c_type} {self._unused_attr(loc)}{loc.name} = {init};{suffix}")

    def _emit_pool_state(self, locals_: list[LuaLocal]):
        """L'état par instance d'un prefab poolé : une structure par slot du
        pool, un champ par variable de tête que le script écrit.

        Le pool est une plage contiguë de `g_actors[]` dont les bornes sont des
        constantes de build (`POOL_<SYM>_START/SIZE/GROUP/INSTANCES`, émises par
        headers.py) : le slot d'une instance est donc une soustraction de
        pointeurs, et rien n'a besoin d'être rangé dans la struct `Actor`.

        La taille vient du #define et non d'un littéral recalculé ici : un écart
        avec la boucle de pool de `main.c` serait un débordement de tableau
        silencieux. C'est `_INSTANCES` qui la donne, pas `_SIZE` — `_SIZE` compte
        les entrées de `g_actors` réservées, et une instance segmentée en occupe
        un GROUPE tout en n'exécutant qu'un script (ROADMAP v0.23)."""
        sym      = self.ctx.actor_sym
        struct_t = f"{sym}State"
        fields, inits, per_instance = [], [], 0
        export_fields: list[tuple[str, str]] = []   # (nom, type) réglables → un setter chacun
        for loc in locals_:
            if loc.export_type in _EXPORT_SETTABLE:
                export_fields.append((loc.name, loc.export_type))
            if (loc.export_type in _EXPORT_COMPOSITE
                    and self.ctx.export_inits.get(loc.name) is not None):
                # Export composite d'un prefab poolé : type Vec2/Vec3/Rect, valeur
                # résolue par le template (export_inits). AVANT le test tableau —
                # le défaut de source `{0,0}` passerait pour un `int[2]`. L'init
                # n'est pas `infer_vec_type(loc.value)` (qui ne reconnaît pas une
                # table nue) mais le littéral « { x, y } » déjà résolu.
                ex_typ = loc.export_type
                self._vec_types[loc.name] = ex_typ
                fields.append(f"{C_TYPES[ex_typ]} {loc.name};")
                inits.append(f".{loc.name} = {self.ctx.export_inits[loc.name]}")
                per_instance += _STATE_BYTES[ex_typ]
                self._pool_state[loc.name] = loc.name
                continue
            dims = array_dims(loc.value)
            if dims:
                self._arrays[loc.name] = dims
                count = 1
                for d in dims:
                    count *= d
                fields.append(f"{self._array_decl(loc.name, dims)};")
                inits.append(f".{loc.name} = {self._array_init(loc.value, dims)}")
                per_instance += 4 * count
            else:
                vt = infer_vec_type(loc.value, self._vec_types, self._ref_types, self._kinds) if loc.value is not None else None
                if vt:
                    self._vec_types[loc.name] = vt
                    fields.append(f"{C_TYPES[vt]} {loc.name};")
                    inits.append(f".{loc.name} = {self._expr(loc.value)}")
                    per_instance += _STATE_BYTES[vt]
                else:
                    c_type, init, note = self._local_decl(loc)
                    if c_type is None:
                        self._w(f"/* {loc.name} : {note} */")
                        continue
                    fields.append(f"{c_type} {loc.name};")
                    inits.append(f".{loc.name} = {init}")
                    per_instance += 4
            self._pool_state[loc.name] = loc.name

        # L'état des séquences rejoint la même structure : une séquence d'un
        # prefab poolé avance indépendamment dans chaque instance, exactement
        # comme ses variables de tête.
        for c_type, field_name, init in self._state_extra:
            fields.append(f"{c_type} {field_name};")
            inits.append(f".{field_name} = {init}")
            per_instance += 4

        if not fields:
            return
        self.pool_state_bytes = per_instance
        self._pool_state_init = ", ".join(inits)
        total = per_instance * self.ctx.pool_size
        self._w("/* Per-instance state — one field per top-level variable the script")
        self._w(f"   writes, plus the step of each sequence. {per_instance} bytes × "
                f"{self.ctx.pool_size} instance(s) = {total} bytes. */")
        self._w(f"typedef struct {{")
        self._indent += 1
        for f in fields:
            self._w(f)
        self._indent -= 1
        self._w(f"}} {struct_t};")
        # Un état par INSTANCE, pas par entrée de `g_actors` (ROADMAP v0.23) :
        # une instance de prefab segmenté occupe un GROUPE d'entrées — la
        # racine puis ses parties — mais n'exécute qu'un script, celui de la
        # racine. Diviser par le groupe ramène `self` à son rang d'instance ;
        # pour un prefab plat, GROUP vaut 1 et le C émis est mot pour mot celui
        # d'avant.
        self._w(f"static {struct_t} g_state_{sym}[POOL_{sym.upper()}_INSTANCES];")
        self._w(f"static inline int {sym}_pool_slot(Actor* self) {{ "
                f"return ((int)(self - g_actors) - POOL_{sym.upper()}_START) "
                f"/ POOL_{sym.upper()}_GROUP; }}")
        # Un setter par export réglable : c'est le SEUL point d'accès de l'état
        # depuis un autre `.c` (le script qui spawne). `g_state`/`pool_slot`
        # restent privés — le setter, lui, est extern (le spawner le forward-
        # déclare, cf. `_emit_spawn_setter_externs`). Chantier « Les exports de
        # script », tranche poolé (D2).
        for name, ex_typ in export_fields:
            arg_t = _export_setter_c_type(ex_typ)
            self._w(f"void {sym}_set_{name}(Actor* self, {arg_t} v) {{ "
                    f"g_state_{sym}[{sym}_pool_slot(self)].{name} = v; }}")
        self._w("")

    @staticmethod
    def _unused_attr(loc: LuaLocal) -> str:
        """Une variable exposée est déclarée pour l'éditeur : elle peut
        légitimement n'être lue par aucune ligne du script (-Wunused-variable
        à chaque build sinon). Un vrai `local` inutilisé reste signalé."""
        return "__attribute__((unused)) " if loc.export_type else ""

    def _local_decl(self, loc: LuaLocal) -> tuple[Optional[str], str, str]:
        """(type C, initialiseur, commentaire) pour un local top-level ou une
        variable exposée. Type C = None → rien à déclarer (composite).

        Le type déclaré dans `exports` fait foi ; pour un vrai `local`, il est
        déduit de la valeur d'initialisation (une string littérale n'est pas
        un int)."""
        typ = (loc.export_type or "").strip()

        # Valeur d'INSTANCE prioritaire (chantier « Les exports de script ») :
        # lua_compiler a déjà résolu l'override ou le défaut en un initialiseur C
        # — un entier pour un scalaire (bool/enum → index, string/*_ref → TEXT_*/
        # SFX_*/…), un littéral composé « { x, y } » pour un vec2/vec3/rect. Elle
        # prime sur le défaut déduit ci-dessous — c'est ce qui donne à CET acteur
        # posé sa valeur propre. Absente = pas un export câblé, ou un prefab poolé
        # sans init (map vide) : on retombe sur le défaut.
        override = self.ctx.export_inits.get(loc.name)
        if override is not None:
            if typ in _EXPORT_COMPOSITE:
                return C_TYPES[typ], override, ""
            return _EXPORT_C_TYPE.get(typ, "int"), override, ""

        # Pas de valeur résolue : un composite reste non déclaré (un `local`
        # vec2 sans init ne sait pas s'écrire en scalaire), un scalaire retombe
        # sur son défaut de source.
        if typ in _EXPORT_COMPOSITE:
            return None, "", (f"type '{typ}' cannot be represented as a C scalar — not "
                              "declared")

        init = self._expr(loc.value) if loc.value is not None else None

        if typ in _EXPORT_C_TYPE:
            c_type = _EXPORT_C_TYPE[typ]   # tous scalaires câblés → "int"
            if init is None:
                return c_type, "0", ""
            # Un défaut string/nom (string, actor_ref…) non résolu ne peut pas
            # initialiser un int : on repart de 0. (Chemin quasi mort — le
            # résolveur remplit désormais export_inits pour tout export câblé.)
            if isinstance(loc.value, ExprString):
                return c_type, "0", f"value '{loc.value.value or 'empty'}' not resolved at build"
            # Les littéraux flottants sont déjà tronqués par le parser
            # (ExprNumber(int(...)) — le moteur n'a pas de flottants).
            return c_type, init, ""

        if typ:
            self.warnings.append(
                f"exports: unknown type '{typ}' for '{loc.name}' — declared as int."
            )

        # Vrai `local` (ou export de type inconnu) : déduction depuis la valeur.
        if isinstance(loc.value, ExprString):
            return "const char *", init, ""
        return "int", init if init is not None else "0", ""

    # ── Tableaux ──────────────────────────────────────────────────

    @staticmethod
    def _array_decl(name: str, dims: tuple[int, ...]) -> str:
        """`grille`, (20, 12) → « int grille[20][12] ». Le premier argument
        d'`array` est le premier index, en Lua comme en C."""
        return f"int {name}" + "".join(f"[{d}]" for d in dims)

    def _array_init(self, value, dims: tuple[int, ...]) -> str:
        """L'initialiseur C. `{1, 2, 4, 8}` recopie les valeurs écrites ;
        `array(n)` remplit de zéros."""
        if isinstance(value, ExprTable):
            if len(dims) == 2:
                return "{" + ", ".join(
                    "{" + ", ".join(self._expr(v) for v in row.items) + "}"
                    for row in value.items) + "}"
            return "{" + ", ".join(self._expr(v) for v in value.items) + "}"
        return "{0}" if len(dims) == 1 else "{{0}}"

    @staticmethod
    def _data_table_ref(e) -> Optional[str]:
        """`data.Objets` → "Objets", sinon None."""
        if (isinstance(e, ExprIndex) and isinstance(e.obj, ExprName)
                and e.obj.name == DATA_NS):
            return e.field
        return None

    def _array_length(self, operand) -> Optional[int]:
        """La valeur de `#x`, connue au build. `#t` est le nombre d'éléments,
        `#t[i]` la longueur d'une ligne d'un tableau à deux dimensions, et
        `#data.X` le nombre de lignes de la table."""
        name = self._data_table_ref(operand)
        if name is not None:
            entry = self.ctx.data_tables.get(name)
            return entry[1] if entry else None
        if isinstance(operand, ExprName):
            dims = self._arrays.get(operand.name)
            return dims[0] if dims else None
        if isinstance(operand, ExprIndexAt) and isinstance(operand.obj, ExprName):
            dims = self._arrays.get(operand.obj.name)
            return dims[1] if dims and len(dims) == 2 else None
        return None

    def _index(self, e) -> str:
        """Lua indexe à partir de 1, le C à partir de 0 — la traduction se fait
        ici, une fois. Un index littéral est replié tout de suite : `t[1]`
        devient `t[0]` et non `t[(1) - 1]`."""
        if isinstance(e, ExprNumber):
            return str(e.value - 1)
        return f"({self._expr(e)}) - 1"

    # ── Fonctions / handlers ──────────────────────────────────────

    def _emit_function(self, fn: LuaFunction):
        if not self.ctx.has_self:
            sym = self.ctx.actor_sym
            if fn.name in self._known_hooks():
                sig = scene_event_sig(sym, fn.name, self.ctx.owner_kind)   # "void PONG_scene_on_start(void)"
            else:
                sig = f"static void {sym}_scene_{fn.name}(void)"
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(fn.name)
            if sig_tpl is None:
                # PAS static : une fonction personnalisée (ni un hook connu, ni
                # `EVENT_C_SIGNATURES`) est le point d'entrée d'un EventCall —
                # une frame d'animation du sprite de CET actor peut l'appeler
                # depuis `main.c`, une autre unité de compilation (ROADMAP
                # v0.8.9 ; cf. `actor_frame_event_lines` dans gen_sprite.py).
                # Rien ne distingue ici « appelée par une frame » de « jamais
                # appelée » : les deux cas restent corrects avec une liaison
                # externe, et le linker élague ce qui ne sert à personne.
                sig = f"void {self.ctx.actor_sym}_{fn.name}(Actor* self)"
            else:
                sig = sig_tpl.format(prefix=self.ctx.actor_sym)
        self._w(sig + " {")
        self._indent += 1
        mark = self._open_state_scope()
        self._emit_block(fn.body)
        if fn.name == "on_update":
            self._emit_sequence_pump()
        self._close_state_scope(mark)
        self._indent -= 1
        self._w("}")
        self._w("")

    # ── Blocs et statements ───────────────────────────────────────

    def _emit_block(self, stmts: list):
        self._block_depth += 1
        for s in stmts:
            self._emit_stmt(s)
        self._block_depth -= 1
        if self._block_depth == 0 and self._lua_file:
            # Le corps d'une fonction est fini : ce qui suit (accolade, tranche suivante)
            # est du C généré, pas du script.
            self._lines.append(_LINE_RESET)

    def _mark_source(self, s):
        """`#line N "Script.lua"` avant un statement : une erreur de gcc sur le C émis cite
        alors la ligne du script. Une directive commence en colonne 0, d'où l'écriture directe."""
        line = getattr(s, "line", 0)
        if self._lua_file and line:
            self._lines.append(f'#line {line} "{_c_file_name(self._lua_file)}"')

    def _emit_stmt(self, s):
        self._mark_source(s)
        if isinstance(s, StmtCall):
            # `sfx:play(...)` posé SEUL ne tient pas sa référence : son canal
            # reste volable par l'effet suivant quand tout est plein (cf.
            # `hold` dans headers.py, ROADMAP v0.8.8). C'est la seule décision
            # de tout le générateur qui dépend de la POSITION de l'appel et non
            # de ce qu'il contient — d'où ce test ici, et pas dans l'émetteur.
            if (isinstance(s.call, ExprCall)
                    and self._call_key(s.call.func) == "sfx.play"):
                self._w(self._emit_sfx_play(s.call.args, hold=False) + ";")
            elif (isinstance(s.call, ExprCall)
                    and self._call_key(s.call.func) == "actor.spawn"
                    and self._spawn_table(s.call.args) is not None
                    and isinstance(s.call.args[0], ExprString)):
                # `actor:spawn("X", pos, {k=v})` posé seul : on tient l'instance
                # dans un temporaire le temps d'écrire ses exports, puis on la
                # lâche (chantier « Les exports de script », tranche poolé).
                tmp = f"_spawn{self._next_spawn_tmp()}"
                self._w(f"Actor* {tmp} = {self._emit_actor_spawn(s.call.args)};")
                self._emit_spawn_setters(tmp, s.call.args[0].value,
                                         self._spawn_table(s.call.args))
            else:
                self._w(self._call_expr(s.call) + ";")

        elif isinstance(s, StmtAssign):
            prop = resolve_prop(s.target, self._ref_types, self._kinds)
            if prop is not None:
                receiver, p = prop
                receiver = self._prop_receiver_c(s.target, receiver, p)
                if p.c_setter is None:
                    # lecture seule — le checker a déjà refusé ; on trace plutôt
                    # que d'émettre du C qui ne compile pas.
                    self.warnings.append(
                        f"{p.lua_name} is read-only — the assignment is ignored.")
                    return
                setter, value = self._prop_write(p, s.value, s.target)
                c_args = [receiver] if p.self_first else []
                c_args.append(value)
                self._w(f"{setter}({', '.join(c_args)});")
                return
            tgt = self._expr(s.target)
            val = self._expr(s.value)
            self._w(f"{tgt} = {val};")

        elif isinstance(s, StmtLocalAssign):
            # local M = require("behaviors/foo") → enregistre l'alias, pas de
            # déclaration C : le behavior est inliné dans l'en-tête.
            target = require_target(s.value)
            if target is not None:
                self._required_behaviors[s.name] = f"beh_{Path(target).stem}"
                return
            # Une variable de séquence qui traverse une attente est DÉJÀ
            # déclarée, dans l'état : son `local` n'est plus qu'une affectation.
            # Sans ça, le C redéclarerait un homonyme local à la tranche, et la
            # valeur ne survivrait pas à l'attente qui suit.
            lifted = self._local_state.get(s.name)
            if lifted is not None:
                val = self._expr(s.value) if s.value is not None else "0"
                # Le type de la référence se note même quand la variable est
                # HISSÉE dans l'état d'une séquence : c'est le même nom, et
                # `pas:set_volume(…)` doit rester un réglage d'effet après
                # l'attente qui l'a fait monter là.
                self._note_ref(s.name, s.value)
                self._w(f"{self._state_ref(lifted)} = {val};")
                return
            dims = array_dims(s.value)
            if dims:
                # Un tableau déclaré DANS un handler est reconstruit à chaque
                # appel, comme n'importe quel `local` de Lua.
                self._arrays[s.name] = dims
                self._w(f"{self._array_decl(s.name, dims)} = "
                        f"{self._array_init(s.value, dims)};")
                return
            vt = infer_vec_type(s.value, self._vec_types, self._ref_types, self._kinds) if s.value is not None else None
            if vt:
                self._vec_types[s.name] = vt
                self._w(f"{C_TYPES[vt]} {s.name} = {self._expr(s.value)};")
                return
            val = self._expr(s.value) if s.value is not None else "0"
            # Détecte local var = actor:get("...") → Actor* au lieu de int
            is_actor_ref = (
                s.value is not None
                and isinstance(s.value, ExprCall)
                and self._call_key(s.value.func) == "actor.get"
            ) or (
                # `local b = actor:spawn("X", pos)` tient l'instance née — un
                # `Actor*` (ROADMAP v0.17 T6), donc `b:set_velocity(...)` chaîne
                # et `if not b then` teste vraiment le pool plein (NULL).
                s.value is not None
                and isinstance(s.value, ExprCall)
                and self._call_key(s.value.func) == "actor.spawn"
            ) or (
                # `local bras = self.bras` tient un acteur, exactement comme
                # `actor:get(...)` — donc un `Actor*` et non un `int`, sans quoi
                # `bras:destroy()` ne compilerait pas (ROADMAP v0.23).
                isinstance(s.value, ExprIndex)
                and isinstance(s.value.obj, ExprName)
                and s.value.obj.name == "self"
                and s.value.field in (self.ctx.child_refs or {})
            )
            # Une RÉFÉRENCE rendue par un appel (`sfx.play`) porte le type C du
            # handle, et le nom est retenu : c'est lui qui dira à `_invoke` que
            # `pas:set_volume(80)` est un réglage d'effet et non d'acteur.
            rt = self._note_ref(s.name, s.value)
            ctype = "Actor*" if is_actor_ref else (REF_TYPE_TABLE[rt].c_type if rt else "int")
            self._w(f"{ctype} {s.name} = {val};")
            # `local b = actor:spawn("X", pos, {k=v})` : écrire les exports de
            # l'instance née juste après (tranche poolé D2).
            if (isinstance(s.value, ExprCall)
                    and self._call_key(s.value.func) == "actor.spawn"
                    and self._spawn_table(s.value.args) is not None
                    and isinstance(s.value.args[0], ExprString)):
                self._emit_spawn_setters(s.name, s.value.args[0].value,
                                         self._spawn_table(s.value.args))

        elif isinstance(s, StmtIf):
            cond = self._expr(s.cond)
            self._w(f"if ({cond}) {{")
            self._indent += 1
            self._emit_block(s.then)
            self._indent -= 1
            for elif_cond, elif_body in s.elseifs:
                self._w(f"}} else if ({self._expr(elif_cond)}) {{")
                self._indent += 1
                self._emit_block(elif_body)
                self._indent -= 1
            if s.else_:
                self._w("} else {")
                self._indent += 1
                self._emit_block(s.else_)
                self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtWhile):
            self._w(f"while ({self._expr(s.cond)}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtForNum):
            # for i = start, stop[, step] do
            start = self._expr(s.start)
            stop  = self._expr(s.stop) if s.stop else "0"
            step  = self._expr(s.step) if s.step else "1"
            v     = s.var
            # Le SENS de la comparaison se décide au build, donc le pas doit
            # être un littéral (le checker le refuse autrement) : un pas calculé
            # obligerait à tester son signe à chaque tour, dans un moteur qui ne
            # teste rien ailleurs.
            descend = ((isinstance(s.step, ExprUnop) and s.step.op == "-")
                       or (isinstance(s.step, ExprNumber) and s.step.value < 0))
            cmp     = ">=" if descend else "<="
            self._w(f"for (int {v} = {start}; {v} {cmp} {stop}; {v} += {step}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtReturn):
            if s.values:
                self._w(f"return {self._expr(s.values[0])};")
            elif self._in_helper:
                self._w("return 0;")
            else:
                self._w("return;")

        elif isinstance(s, StmtBreak):
            self._w("break;")

        elif isinstance(s, StmtUnsupported):
            # Le checker a déjà refusé, et une erreur bloque le build : on
            # n'arrive ici que par le chemin des behaviors, où ses erreurs sont
            # relayées en avertissements. Le trou est alors ÉCRIT dans le C
            # plutôt que laissé invisible — c'est tout ce que ce fichier peut
            # faire d'honnête avec un code qu'il ne sait pas traduire.
            self._w(f"/* not translated: {s.node} (line {s.line}) */")

    # ── Expressions ───────────────────────────────────────────────

    def _expr(self, e) -> str:
        if e is None:
            return "0"
        if isinstance(e, ExprNumber):
            return str(e.value)
        if isinstance(e, ExprBool):
            return "1" if e.value else "0"
        if isinstance(e, ExprNil):
            return "0"
        if isinstance(e, ExprUnsupported):
            # Même chemin que StmtUnsupported ci-dessus : refusé par le checker,
            # atteint seulement depuis un behavior. `0` et le nœud en commentaire
            # valent mieux que l'ancien `__unsupported_Concat`, identifiant C
            # inexistant qui n'échouait qu'au `make`.
            return f"0 /* not translated: {e.node} (line {e.line}) */"
        if isinstance(e, ExprString):
            # String littérale en dehors d'un appel API → chaîne C (rare en v1)
            return f'"{e.value}"'
        if isinstance(e, ExprName):
            # Une variable d'une séquence qui traverse une attente vit dans
            # l'état de cette séquence — et masque un éventuel homonyme de tête,
            # comme un `local` masque en Lua.
            field = self._local_state.get(e.name)
            if field is not None:
                return self._state_ref(field)
            # Prefab poolé : une variable de tête écrite par le script vit dans
            # le slot de CETTE instance, pas au scope fichier.
            field = self._pool_state.get(e.name)
            if field is not None:
                return self._state_ref(field)
            return e.name
        if isinstance(e, ExprIndex):
            # screen.width / screen.height / etc. → littéral C
            if isinstance(e.obj, ExprName) and e.obj.name == "screen":
                val = SCREEN_CONSTANTS.get(e.field)
                if val is not None:
                    return str(val)
            # PROPRIÉTÉ : self.position, camera.bound, other.velocity, scene.size…
            # Un accès pointé se traduit par le GETTER (appel C, ou expression
            # synthétique pour scene.size). Le champ qui suit (`self.position.x`)
            # se compose tout seul sur le résultat, comme en Lua.
            prop = resolve_prop(e, self._ref_types, self._kinds)
            if prop is not None:
                receiver, p = prop
                return self._prop_read(self._prop_receiver_c(e, receiver, p), p)
            # `data.Objets` → le tableau const émis par data_tables.c. Ce qui
            # suit (l'indexation puis la colonne) se compose tout seul : le
            # `.champ` ci-dessous et `ExprIndexAt` s'appliquent au résultat,
            # exactement comme en Lua.
            table = self._data_table_ref(e)
            if table is not None:
                return f"g_data_{table}"
            # `global.nom` → la variable C émise par globals.c — NU (scalaire,
            # chantier global/const) ou base d'une indexation qui se compose toute
            # seule via `ExprIndexAt` (tableau, ROADMAP v0.20), exactement
            # comme pour une table de données. Le nom du projet se cite en
            # clair : c'est la grammaire déjà LIVRÉE pour `data.Objets[i].prix`,
            # pas une forme inventée ici. Le checker a déjà refusé un nom
            # inconnu (`_check_global_scalar`/`_check_global_indexed`).
            if (isinstance(e.obj, ExprName) and e.obj.name == "global"
                    and e.field in self.ctx.global_names):
                return f"g_{e.field}"
            # `const.nom` → le symbole émis par constants.h — toujours nu, une
            # constante ne s'indexe jamais. Même geste, même garde côté
            # checker (`_check_const_scalar`).
            if (isinstance(e.obj, ExprName) and e.obj.name == "const"
                    and self.ctx.const_names and e.field in self.ctx.const_names):
                return f"CONST_{e.field.upper()}"
            # `self.bras` → l'enfant, désigné par une expression CONSTANTE
            # (ROADMAP v0.23). Même geste que dans Godot : on tient son parent,
            # on nomme l'enfant. Rien n'est construit, rien n'est cherché au
            # runtime — c'est un `&g_actors[...]` ou un décalage de groupe.
            if (isinstance(e.obj, ExprName) and e.obj.name == "self"
                    and e.field in (self.ctx.child_refs or {})):
                return self.ctx.child_refs[e.field]
            # module.field — retourne le nom composé pour la résolution ultérieure
            return f"{self._expr(e.obj)}.{e.field}"
        if isinstance(e, ExprIndexAt):
            return f"{self._expr(e.obj)}[{self._index(e.index)}]"
        if isinstance(e, ExprTable):
            # Un constructeur n'a de sens que comme initialiseur de déclaration
            # (`_array_init`) : ailleurs, il n'y a pas de tableau à écrire dedans.
            self.warnings.append("a { } constructor can only initialise an array "
                                 "declared with `local`.")
            return "0"
        if isinstance(e, (ExprInvoke, ExprCall)):
            return self._call_expr(e)
        if isinstance(e, ExprBinop):
            enum_cmp = self._prop_enum_compare(e)
            if enum_cmp is not None:
                return enum_cmp
            lt = infer_vec_type(e.left, self._vec_types, self._ref_types, self._kinds)
            rt = infer_vec_type(e.right, self._vec_types, self._ref_types, self._kinds)
            vt = lt or rt
            if vt and e.op in ("+", "-", "*"):
                # Pas d'opérateur `+`/`-`/`*` sur les structs en C : ce sont
                # les fonctions vec2_*/vec3_* de runtime_api_inline.h qui portent
                # l'opération (checker.py a déjà refusé vec2+vec3, vec*vec…).
                left, right = self._expr(e.left), self._expr(e.right)
                if e.op == "*":
                    vecexpr, scalar = (left, right) if lt else (right, left)
                    return f"{vt}_scale({vecexpr}, {scalar})"
                fn = "add" if e.op == "+" else "sub"
                return f"{vt}_{fn}({left}, {right})"
            return f"({self._expr(e.left)} {e.op} {self._expr(e.right)})"
        if isinstance(e, ExprUnop):
            if e.op == "#":
                n = self._array_length(e.operand)
                if n is None:
                    self.warnings.append("`#` applied to something other than an "
                                         "array declared in this script.")
                    return "0"
                return str(n)
            op = "!" if e.op == "not" else e.op
            return f"({op}{self._expr(e.operand)})"
        return "0"

    # ── Propriétés à domaine ──────────────────────────────────────
    # `self.obj_mode = "window"`, `blend.mode == "alpha"`, `other.tag == "Ball"`.
    # Le C reste un entier ; ce qui change est ce que l'auteur écrit, et la
    # constante émise (`OBJ_MODE_WINDOW` plutôt que `2`, `TAG_BALL` plutôt
    # qu'un index de scène). La résolution passe par `_DOMAIN_CONSTANT`, la même
    # table que pour un ARGUMENT du même domaine : le domaine décide, pas ce
    # qui le porte.

    def _prop_constant(self, p, name: str, access=None) -> str:
        if p.domain == DOMAIN_IMAGE_STATE and access is not None:
            # L'état se nomme dans le sprite de l'image que le RÉCEPTEUR désigne
            # (`IMGST_{image}_{état}`) : le checker a déjà refusé une image inconnue.
            image = element_of(access.obj, self._ref_elements)
            if image:
                return image_state_constant(image, name)
        make = _DOMAIN_CONSTANT.get(p.domain)
        return make(self, name) if make else f'"{name}"'

    def _prop_write(self, p, value, access=None) -> tuple[str, str]:
        """(fonction C d'écriture, valeur C) pour une assignation de propriété.

        Le nom d'une énumération devient sa constante — et, quand la propriété
        a une porte NOMMÉE distincte (`self.direction`, un vec2 côté calcul mais
        une boussole côté nom), c'est elle qu'on emprunte : `actor_set_dir` prend
        un index 0-8, `actor_set_direction` prend un Vec2. Une propriété, deux
        écritures, deux fonctions — l'état atteint est le même."""
        if p.domain is not None and isinstance(value, ExprString):
            return ((p.c_setter_named or p.c_setter),
                    self._prop_constant(p, value.value, access))
        return p.c_setter, self._expr(value)

    def _prop_receiver_c(self, access, receiver: str, p=None) -> str:
        """Le récepteur C d'un accès de propriété. Un NOM s'émet tel quel ; un
        récepteur CHAÎNÉ (`actor:get("Foe").velocity`) s'émet par son expression :
        `resolve_prop` n'en rend qu'un libellé, bon pour un message du checker."""
        c = receiver if isinstance(access.obj, ExprName) else self._expr(access.obj)
        # Une propriété HÉRITÉE (`menu.visible`, de `ui_element`) attend le récepteur de
        # son parent — la même conversion que pour une méthode héritée.
        if p is not None and "." in p.lua_name:
            owner = p.lua_name.split(".", 1)[0]
            ref = (self._ref_types.get(access.obj.name) if isinstance(access.obj, ExprName)
                   else infer_ref_type(access.obj, self._kinds, self._ref_types))
            if ref and owner in REF_TYPE_TABLE and owner != ref:
                c = ref_upcast(ref, owner, c)
        return c

    def _prop_read(self, receiver: str, p, named: bool = False) -> str:
        """Lecture d'une propriété, par sa porte ordinaire ou par sa porte
        nommée quand la comparaison porte sur un nom."""
        if not named and p.getter_expr is not None:
            return p.getter_expr
        fn = (p.c_getter_named or p.c_getter) if named else p.c_getter
        return f"{fn}({receiver})" if p.self_first else f"{fn}()"

    def _prop_enum_compare(self, e) -> Optional[str]:
        """`blend.mode == "alpha"` → `(blend_get_mode() == BLD_MODE_ALPHA)`, et
        `self.direction == "west"` → `(actor_get_dir(self) == DIR_WEST)`.

        Sans ça, la comparaison partirait sur une chaîne C là où le getter rend
        un entier : gcc accepterait le pointeur, et le test serait toujours
        faux. Pire pour `self.direction`, dont le getter ordinaire rend un
        `Vec2` — que le C ne sait pas comparer du tout. La lecture passe donc
        par la même porte que l'écriture."""
        if e.op not in ("==", "!="):
            return None
        for prop_side in (e.left, e.right):
            prop = resolve_prop(prop_side, self._ref_types, self._kinds)
            if prop is None or prop[1].domain is None:
                continue
            receiver, p = prop
            receiver, p = prop
            receiver = self._prop_receiver_c(prop_side, receiver, p)
            other = e.right if prop_side is e.left else e.left
            if not isinstance(other, ExprString):
                continue
            const = self._prop_constant(p, other.value, prop_side)
            read  = self._prop_read(receiver, p, named=True)
            left  = read  if prop_side is e.left else const
            right = const if prop_side is e.left else read
            return f"({left} {e.op} {right})"
        return None

    # ── Résolution des appels API ──────────────────────────────────

    def _call_expr(self, e) -> str:
        """Génère le C pour un appel de fonction/méthode."""
        if isinstance(e, ExprInvoke):
            return self._invoke(e)
        if isinstance(e, ExprCall):
            return self._call(e)
        return "/* unhandled call */"

    def _invoke(self, e: ExprInvoke) -> str:
        """var:method(args) — var peut être self, une variable Actor*/référence,
        OU une expression qui rend directement un actor (`actor:get("X")`,
        `actor:spawn(...)`, `self.<enfant>`) ou une référence (`sfx:play(...)`).
        Ce dernier cas évite d'imposer un local intermédiaire pour chaîner :
        `actor:get("Foe"):move_to(p, 2)` marche sans `local u = actor:get(...)`."""
        if isinstance(e.obj, ExprName):
            name = e.obj.name          # "self", "other", "paddle", ...
            ref  = self._ref_types.get(name)
        else:
            # Chaîne directe : on ne l'accepte que si l'expression réceptrice a un
            # type connu — un actor ou une référence. Sinon le repli `actor_*`
            # plus bas inventerait un appel sur n'importe quelle expression.
            name = None
            ref  = infer_ref_type(e.obj, self._kinds, self._ref_types)
            if not (ref or self._is_actor_expr(e.obj)):
                return "/* invoke on complex expression ignored */"
        # Le NOM écrit sert de clé (type de référence, tables de dispatch) ; ce
        # qui est ÉMIS passe par `_expr`, parce qu'une variable peut vivre
        # ailleurs que sous son nom — hissée dans l'état d'une séquence qui
        # traverse une attente, ou dans le slot d'un prefab poolé. Une expression
        # réceptrice, elle, s'émet directement.
        receiver = self._expr(e.obj)
        # Les méthodes d'actor sont indexées sous "self:" ; celles d'une
        # référence sous le type qu'elle porte (`sfx:`). Le repli `actor_*`
        # plus bas ne doit surtout pas s'appliquer à une référence : il
        # inventerait un `actor_set_volume(pas, …)` qui ne compile pas.
        # Un type HÉRITE de son parent : `menu:hide()` est une méthode de `ui_element`, dont
        # le C attend l'index d'ÉLÉMENT, pas celui de la liste (cf. `RefType.to_base`).
        found = ref_member(ref, e.method, ":") if ref else None
        if found is not None:
            key = f"{found[0]}:{e.method}"
            receiver = ref_upcast(ref, found[0], receiver)
        else:
            key = f"{ref}:{e.method}" if ref else f"{REF_ACTOR}:{e.method}"
        custom = _INVOKE_CUSTOM.get(key)
        if custom:
            return custom(self, e.args, receiver)
        api = RUNTIME_API.get(key)
        if api is None:
            if ref:
                return f"/* {name or '?'}:{e.method}(): unknown on a {ref} reference */"
            args = ", ".join(self._expr(a) for a in e.args)
            return f"actor_{e.method}({receiver}, {args})"
        return self._emit_api_call(api, e.args, receiver=receiver)

    def _is_actor_expr(self, expr) -> bool:
        """L'expression rend-elle un `Actor*` ? Mêmes cas que la détection de
        type d'un `local` (actor.get, actor.spawn, `self.<enfant>` d'un prefab
        segmenté — cf. StmtLocal dans `_emit_block`)."""
        if isinstance(expr, ExprCall):
            if self._call_key(expr.func) == "actor.get":
                return True
            if self._call_key(expr.func) == "actor.spawn":
                return True
        return (isinstance(expr, ExprIndex)
                and isinstance(expr.obj, ExprName)
                and expr.obj.name == "self"
                and expr.field in (self.ctx.child_refs or {}))

    def _call(self, e: ExprCall) -> str:
        """func(args) ou module.func(args)"""
        key = self._call_key(e.func)

        if key in VEC_CONSTRUCTORS:
            # vec2(x, y) / vec3(x, y, z) / rect(x, y, w, h) → littéral composé
            # C, pas un appel : aucune fonction `vec2`/`rect` n'existe côté runtime.
            args = ", ".join(self._expr(a) for a in e.args)
            return f"({C_TYPES[key]}){{{args}}}"

        if key in self._helpers:
            args = [self._expr(a) for a in e.args]
            if self.ctx.has_self:
                args.insert(0, "self")
            return f"{self.ctx.actor_sym}_{key}({', '.join(args)})"

        # Appel sur un behavior requis : AI.update(self, x) → beh_foo_update(self, x)
        if (isinstance(e.func, ExprIndex)
                and isinstance(e.func.obj, ExprName)
                and e.func.obj.name in self._required_behaviors):
            sym  = self._required_behaviors[e.func.obj.name]
            func = f"{sym}_{e.func.field}"
            args = ", ".join(self._expr(a) for a in e.args)
            return f"{func}({args})"

        # Cas spéciaux résolus directement par le codegen (table de dispatch,
        # cf. _CALL_CUSTOM en bas de fichier — pas d'appel de fonction C simple,
        # ou arguments C synthétisés depuis le contexte de build).
        custom = _CALL_CUSTOM.get(key) if key else None
        if custom:
            return custom(self, e.args)

        api = RUNTIME_API.get(key) if key else None
        if api is None:
            # Appel à une fonction helper interne ou inconnue
            func_c = key or self._expr(e.func)
            args   = ", ".join(self._expr(a) for a in e.args)
            return f"{func_c}({args})"
        return self._emit_api_call(api, e.args, with_self=False)

    def _call_key(self, func_expr) -> Optional[str]:
        if isinstance(func_expr, ExprName):
            return func_expr.name
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"
        return None

    def _emit_api_call(self, api: ApiFunc, lua_args: list,
                       with_self: bool = False, receiver: str | None = None) -> str:
        """Génère l'appel C en résolvant les args string → constantes."""
        c_args = []
        if receiver is not None:
            c_args.append(receiver)
        elif with_self:
            c_args.append("self")
        for param, arg in zip(api.params, lua_args):
            c_args.append(self._resolve_arg(param, arg))
        # Args variadiques : tous ceux qui dépassent les params déclarés
        if api.variadic:
            for extra in lua_args[len(api.params):]:
                c_args.append(self._expr(extra))
        c_args.extend(str(a) for a in api.fixed_args)
        return f"{api.c_func}({', '.join(c_args)})"

    def _emit_text_literal(self, api_key: str, args: list, text_arg: int,
                           receiver: Optional[str] = None) -> str:
        """Un littéral texte pose ses `$locale` puis appelle l'API.

        Les textes nommés, et les littéraux qui ne citent que globals/constantes,
        gardent l'appel direct historique. Une locale est reconnue dans le
        littéral par le même parseur de balisage que la table de textes : aucune
        seconde grammaire cachée dans le codegen.
        """
        api = RUNTIME_API[api_key]
        call = self._emit_api_call(api, args, receiver=receiver)
        if len(args) <= text_arg or not isinstance(args[text_arg], ExprString):
            return call
        literal = args[text_arg].value
        if literal in (self.ctx.text_keys or []):
            return call
        from core.text_markup import parse, KIND_VALUE
        globals_ = set(self.ctx.global_names or [])
        constants = set(self.ctx.const_names or [])
        names = []
        for marker in parse(literal).markers:
            # Les constantes sont cuites dans l'entrée anonyme par font_emit.
            # Toute autre valeur — locale OU globale — passe par son rang de
            # tampon, afin qu'une locale homonyme puisse masquer la globale.
            if marker.kind == KIND_VALUE and marker.value not in constants \
                    and marker.value not in names:
                names.append(marker.value)
        if not names:
            return call
        setters = ["text_args_clear()"]
        values = []
        for name in names:
            # Même règle que Lua : une locale visible masque une globale. Les
            # globals passaient autrefois directement par la table de textes ;
            # un littéral passe désormais uniformément par son site d'appel,
            # afin que les deux cas restent distinguables.
            values.append(self._expr(ExprName(name)) if name in self._local_names
                          else f"g_{name}" if name in globals_ else "0")
        setters += [f"text_arg_set({i}, {value})"
                    for i, value in enumerate(values)]
        return "(" + ", ".join(setters + [call]) + ")"

    def _emit_text_draw(self, args: list) -> str:
        return self._emit_text_literal("text.draw", args, 2)

    def _emit_text_region_draw(self, args: list, receiver: str) -> str:
        return self._emit_text_literal(f"{REF_TEXT_REGION}:draw", args, 0, receiver)

    def _resolve_arg(self, param, arg) -> str:
        """Convertit un arg Lua en expression C, résolvant les strings → constantes."""
        from .api import PARAM_STR_LITERAL
        if param.ptype == PARAM_STR_LITERAL:
            # Chaîne littérale → guillemets C, sans résolution de constante
            val = arg.value if isinstance(arg, ExprString) else self._expr(arg)
            return f'"{val}"' if isinstance(arg, ExprString) else val
        if not isinstance(arg, ExprString) or param.domain is None:
            return self._expr(arg)
        name = arg.value
        make_constant = _DOMAIN_CONSTANT.get(param.domain)
        if make_constant is None:
            # Domaine sans constante générique : la chaîne part telle quelle.
            # Légitime pour les domaines résolus par un émetteur dédié
            # (_DOMAIN_EMITTED_ELSEWHERE), qui n'arrivent pas jusqu'ici — et
            # c'est `validator._check_api_domains` qui garantit qu'aucun autre
            # domaine ne tombe dans ce cas par oubli.
            return f'"{name}"'
        return make_constant(self, name)

    # ── Cas spéciaux ──────────────────────────────────────────────

    def _emit_play_sfx(self, args: list, receiver: str) -> str:
        """self:play_sfx() → sfx_play(SFX_X, volume) où X/volume viennent du SoundFxComponent."""
        if not self.ctx.sfx_component_name:
            return ("(void)0 /* self:play_sfx(): no SoundFX configured on this actor "
                    "*/")
        name   = self.ctx.sfx_component_name
        volume = volume_to_effect(self.ctx.sfx_volumes.get(name, 100))
        return f"sfx_play({sfx_constant(name)}, {volume}, 0)"

    def _emit_destroy(self, args: list, receiver: str) -> str:
        """`self:destroy()` → appelle on_destroy() (le hook SCRIPTÉ) puis
        `actor_destroy_with_sfx()`, qui joue le SoundFxComponent en
        `trigger="on_destroy"` DE LA CIBLE (table indexée par tag, cf.
        `main_gen._sfx_on_destroy_table`) avant de désactiver l'actor.

        Sur QUELQU'UN D'AUTRE — `other:destroy()`, ou `MonBras:destroy()` depuis
        la v0.23 — le hook SCRIPTÉ n'est pas appelé, et c'est le seul choix
        honnête : le symbole du script de la cible n'est pas connu à ce site
        d'appel (`other` peut être n'importe quel acteur, et un enfant n'a pas
        de script propre). Le C émis appelait jusqu'ici le `on_destroy` de
        CELUI QUI DÉTRUIT en lui passant l'acteur d'autrui — donc le mauvais
        handler, sur la mauvaise cible. Ne rien appeler laisse le hook scripté
        de la cible muet, ce qui est une limite ; appeler le mauvais était un
        bug. Le SoundFxComponent, lui, JOUE dans les deux cas — c'est piloté
        par la donnée du tag, pas par un symbole résolu au build."""
        if receiver != "self":
            return f"actor_destroy_with_sfx({receiver})"
        sym = self.ctx.actor_sym
        return f"{sym}_on_destroy({receiver}); actor_destroy_with_sfx({receiver})"

    def _emit_sfx_play(self, args: list, hold: bool = True) -> str:
        """sfx:play("Name") → sfx_play(SFX_NAME, volume, hold).

        Volume lu depuis la ressource Sfx. `hold` dit si l'appelant garde la
        référence : vrai quand l'appel est une VALEUR (`local h = sfx.play…`),
        faux quand il est posé seul — c'est `_emit_stmt` qui le sait."""
        if not args or not isinstance(args[0], ExprString):
            return "/* sfx:play() : argument invalide */"
        name   = args[0].value
        volume = volume_to_effect(self.ctx.sfx_volumes.get(name, 100))
        return f"sfx_play({sfx_constant(name)}, {volume}, {1 if hold else 0})"

    def _percent_arg(self, args: list, fold, to_expr, default: int = 100) -> str:
        """Un pourcentage écrit DANS l'appel → la graduation du registre visé.

        Plié au build quand c'est un littéral — le C reste lisible et l'arrondi
        est exact — et converti à l'exécution sinon, parce qu'un niveau peut
        venir d'une variable (`global.Volume`). Les deux formes de
        conversion vivent côte à côte dans `models/audio.py`, pour qu'aucune ne
        dérive de l'autre.
        """
        if not args:
            return str(fold(default))
        a = args[0]
        # `-50` est un moins UNAIRE sur un littéral, pas un littéral négatif :
        # sans ce cas, le seul panning qu'on écrit vraiment (« à gauche »)
        # partirait en arithmétique C au lieu d'être plié.
        if isinstance(a, ExprUnop) and a.op == "-" and isinstance(a.operand, ExprNumber):
            return str(fold(-int(a.operand.value)))
        if isinstance(a, ExprNumber):
            return str(fold(int(a.value)))
        return to_expr(self._expr(a))

    def _emit_box_overlaps(self, args: list, receiver: str) -> str:
        """`hb:overlaps(x)` — `x` est un acteur OU une autre boîte, et le C en a
        deux versions : le langage ne type pas ses variables, c'est donc le type
        de référence relevé sur le `local` (ou rendu par l'appel) qui tranche."""
        other = args[0]
        is_box = (infer_ref_type(other, self._kinds, self._ref_types) == "collision_box"
                  or (isinstance(other, ExprName)
                      and self._ref_types.get(other.name) == "collision_box"))
        fn = "collision_box_overlaps_box" if is_box else "collision_box_overlaps_actor"
        return f"{fn}({receiver}, {self._expr(other)})"

    def _emit_sfx_set_volume(self, args: list, receiver: str) -> str:
        return (f"sfx_set_volume({receiver}, "
                f"{self._percent_arg(args, volume_to_effect, volume_to_effect_expr)})")

    def _emit_sfx_set_pitch(self, args: list, receiver: str) -> str:
        return (f"sfx_set_pitch({receiver}, "
                f"{self._percent_arg(args, pitch_to_rate, pitch_to_rate_expr)})")

    def _emit_sfx_set_panning(self, args: list, receiver: str) -> str:
        """Le panning s'écrit −100..+100 et le registre prend 0–255 : ce n'est
        pas une mise à l'échelle mais un décalage autour du centre."""
        return (f"sfx_set_panning({receiver}, "
                f"{self._percent_arg(args, panning_to_hardware, panning_to_hardware_expr, 0)})")

    def _emit_music_set_volume(self, args: list) -> str:
        return (f"music_set_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_sound_box_set_volume(self, args: list) -> str:
        return (f"sfx_set_effects_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_jingle_box_set_volume(self, args: list) -> str:
        return (f"music_jingle_volume("
                f"{self._percent_arg(args, volume_to_module, volume_to_module_expr)})")

    def _emit_music_play(self, args: list) -> str:
        """music:play("Name") → music_play(MUSIC_NAME, loop, volume) — loop/volume lus depuis la ressource Music."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music:play() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 100))
        return (f"music_play({music_constant(name)}, {1 if loop else 0}, "
                f"{volume_to_module(volume)})")

    def _emit_music_transition(self, args: list, c_func: str, extra: str = "") -> str:
        """Les deux transitions se traduisent pareil : loop et volume viennent
        de la RESSOURCE, comme pour `music.play` — un fondu ne change pas ce
        qu'est la piste d'arrivée, seulement la façon d'y aller."""
        if not args or not isinstance(args[0], ExprString):
            return f"/* {c_func}() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 100))
        tail = f", {extra}" if extra else ""
        return (f"{c_func}({music_constant(name)}, {1 if loop else 0}, "
                f"{volume_to_module(volume)}{tail})")

    def _emit_box_set_state(self, kind: str, index: dict, args: list) -> str:
        """`<boîte>.set_state("sable")` → `<boîte>_set_state(1)`.

        L'index est le RANG de l'état dans SA boîte : chaque boîte a son propre
        espace de noms, donc deux boîtes peuvent porter « sable » sans que
        l'appel devienne ambigu — c'est l'appel qui nomme la boîte.
        """
        if not args or not isinstance(args[0], ExprString):
            return f"/* {kind}.set_state() : argument invalide */"
        name = args[0].value
        idx = index.get(name, -1)
        if idx < 0:
            return f"/* {kind}.set_state(\"{name}\"): unknown state */"
        return f"{kind}_set_state({idx})"

    def _emit_sound_box_set_state(self, args: list) -> str:
        return self._emit_box_set_state("sound_box", self.ctx.sound_box_states, args)

    def _emit_jingle_box_set_state(self, args: list) -> str:
        return self._emit_box_set_state("jingle_box", self.ctx.jingle_box_states, args)

    def _emit_sound_trigger(self, args: list) -> str:
        """music_box:trigger("combat_start") → music_box_trigger(0)."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music_box:trigger() : argument invalide */"
        name = args[0].value
        idx = self.ctx.music_box_triggers.get(name, -1)
        if idx < 0:
            return f"/* music_box:trigger(\"{name}\"): no edge on this trigger */"
        return f"music_box_trigger({idx})"

    def _emit_music_jingle(self, args: list) -> str:
        """music:jingle("Fanfare") → music_jingle(MUSIC_X, volume).

        `mmSetJingleVolume` partage l'échelle 0–1024 de `mmSetModuleVolume` :
        c'est bien la conversion « module », pas celle d'un effet.
        """
        if not args or not isinstance(args[0], ExprString):
            return "/* music:jingle() : argument invalide */"
        name = args[0].value
        _loop, volume = self.ctx.music_info.get(name, (True, 100))
        return f"music_jingle({music_constant(name)}, {volume_to_module(volume)})"

    def _emit_music_fade_to(self, args: list) -> str:
        frames = self._expr(args[1]) if len(args) > 1 else "30"
        return self._emit_music_transition(args, "music_fade_to", frames)

    def _emit_music_cut_to(self, args: list) -> str:
        return self._emit_music_transition(args, "music_cut_to")

    def _emit_array_misuse(self, args: list) -> str:
        """`array(n)` DÉCLARE un tableau : il est lu à l'endroit du `local`
        (cf. `_emit_locals`), et n'arrive ici que s'il a été écrit ailleurs —
        dans un calcul, un argument. Il n'y a rien à émettre pour ça."""
        self.warnings.append("array() declares an array and can only be written in a "
                             "`local`: local bag = array(8).")
        return "0 /* array() outside a declaration */"

    def _emit_debug_log(self, args: list) -> str:
        """`debug:log("hp=", hp, " x=", x)` → une séquence d'appels C, un par
        argument (`debug_write_str`/`debug_write_int`), fermée par
        `debug_flush()` — jamais un unique appel variadique : le moteur
        n'émet pas de printf (ROADMAP v0.14). L'opérateur virgule enchaîne
        les appels dans une seule expression, valide en position de
        statement comme n'importe quel autre appel de l'API.

        Le C émis ne change pas entre build debug et release : c'est
        `gba_debug.h` qui décide, en fournissant soit les vraies fonctions
        (canal mGBA), soit des stubs `inline` vides hors GBA_DEBUG_BUILD.
        À -O2 un appel à un stub vide disparaît par inlining — retiré à la
        compilation, sans qu'aucun drapeau ne soit testé au runtime."""
        calls = []
        for arg in args:
            if isinstance(arg, ExprString):
                escaped = arg.value.replace("\\", "\\\\").replace('"', '\\"')
                calls.append(f'debug_write_str("{escaped}")')
            else:
                calls.append(f"debug_write_int({self._expr(arg)})")
        calls.append("debug_flush()")
        return "(" + ", ".join(calls) + ")"

    def _input_mask_arg(self, args: list) -> str:
        """Le nom cité par `held`/`buffered` (1er arg) : un bouton nu ou un
        accord déclaré (`InputBinding`) — jamais une séquence, qui n'a plus le
        même espace de noms depuis la décision de l'auteur du 2026-09-27."""
        if not args:
            return "0"
        if not isinstance(args[0], ExprString):
            # Nom non littéral : comme tout autre domaine (cf. `_resolve_arg`),
            # l'expression part telle quelle — ce système est résolu au build,
            # un nom calculé n'a jamais été un cas supporté.
            return self._expr(args[0])
        name = args[0].value
        return self.ctx.input_masks.get(name, key_constant(name))

    def _emit_input_held(self, args: list) -> str:
        """`held(nom)` / `held(nom, frames)`."""
        mask = self._input_mask_arg(args)
        if len(args) > 1:
            return f"input_held_n({mask}, {self._expr(args[1])})"
        return f"input_held({mask})"

    def _emit_input_buffered(self, args: list) -> str:
        mask = self._input_mask_arg(args)
        name = args[0].value if args and isinstance(args[0], ExprString) else None
        bit = self.ctx.input_buffered_bits.get(name, 0)
        frames = self._expr(args[1]) if len(args) > 1 else "1"
        return f"input_buffered({bit}, {mask}, {frames})"

    def _emit_get_sequence(self, args: list) -> str:
        """`get_sequence(nom)` — une alternance dans l'expression de la
        séquence développe PLUSIEURS tables (une par alternative), réunies
        par un OU : n'importe laquelle qui matche suffit."""
        name = args[0].value if args and isinstance(args[0], ExprString) else None
        entry = self.ctx.input_sequences.get(name)
        if entry is None:
            return "0"
        tables, lens, window = entry
        calls = [f"input_seq_pressed({sym}, {n}, {window})" for sym, n in zip(tables, lens)]
        return calls[0] if len(calls) == 1 else "(" + " || ".join(calls) + ")"

    def _emit_get_axis(self, args: list) -> str:
        """`get_axis(x)` → scalaire (`input_get_axis`, ROADMAP : masque
        négatif/positif) ; `get_axis(x, y)` → vec2 (`input_get_vector`)."""
        def axis_masks(arg):
            name = arg.value if isinstance(arg, ExprString) else None
            return self.ctx.input_axes.get(name, ("0", "0"))

        neg_x, pos_x = axis_masks(args[0]) if args else ("0", "0")
        if len(args) < 2:
            return f"input_get_axis({neg_x}, {pos_x})"
        neg_y, pos_y = axis_masks(args[1])
        return f"input_get_vector({neg_x}, {pos_x}, {neg_y}, {pos_y})"

    def _emit_get_actor(self, args: list) -> str:
        """
        Deux formes :

        actor:get("PADDLE_AUTO")  →  &g_actors[TAG_<Scène>_PADDLE_AUTO]
            Nom LITTÉRAL, résolu à la compilation. Le nom est sanitisé avec la
            même fonction que celle qui définit les macros TAG_*
            (headers.py::generate_actor_types, via codegen.c_names.sym).

        actor:get(i)  →  actor_at((i) - 1)
            Index DYNAMIQUE (« L'acteur appartient à sa scène ») : l'auteur
            compte à partir de 1 comme partout dans le langage (data.T[1],
            global.x[1]) ; `_index` replie vers le 0-based du C. `actor_at`
            borne à la scène et filtre les détruits (nil sinon).
        """
        from codegen.c_names import sym as c_sym
        if not args:
            return "/* actor:get() : argument invalide */"
        if not isinstance(args[0], ExprString):
            # Index dynamique 1-based → slot 0-based, borné par actor_at.
            return f"actor_at({self._index(args[0])})"
        sym = c_sym(args[0].value)
        # Un acteur appartient à sa scène : le TAG est qualifié par la scène qui
        # compile ce script (« L'acteur appartient à sa scène »). Le nom reste
        # local — actor:get("curseur") vise LE curseur de CETTE scène.
        scene = self.ctx.scene_sym
        if scene:
            # `actor_live` rend nil si l'acteur a été détruit au runtime
            # (décision C') — le TAG reste résolu à la compilation.
            return f"actor_live(&g_actors[TAG_{scene.upper()}_{sym.upper()}])"
        # Script PARTAGÉ (caméra, sans scène connue au build) : résolution à
        # l'exécution, dans la scène active, nullable (décisions C/C'). Le NOM
        # est une clé de lookup GLOBALE (ACTORNAME_*), distincte des TAG_ qualifiés.
        return f"runtime_get_actor(ACTORNAME_{sym.upper()})"

    def _emit_actor_count(self, args: list) -> str:
        """actor:count() → g_scene_placed : les acteurs posés de la scène active,
        la borne de actor:get(i) (« L'acteur appartient à sa scène »)."""
        return "g_scene_placed"

    def _emit_layer_get(self, args: list) -> str:
        """layer:get(2) → 2 : le numéro EST la référence (un fond n'a pas d'autre identité que
        son rang matériel). Une expression passe telle quelle — `for i = 0, 3` sur les fonds
        est légitime — ; le numéro écrit en clair a déjà été borné par le checker."""
        if not args:
            return "0 /* layer:get(): missing number */"
        return self._expr(args[0])

    def _emit_window_get(self, args: list) -> str:
        """window:get("Panneau") → WINR_PANNEAU : le rang de la région, résolu au build."""
        if not args or not isinstance(args[0], ExprString):
            return "0 /* window:get(): invalid name */"
        return self._resolve_arg(RUNTIME_API["window.get"].params[0], args[0])

    def _emit_ui_get(self, args: list) -> str:
        """interface:get("alerte") → UIELEM_ALERTE, ou UILIST_/IMAGE_/REGION_ selon la
        NATURE de l'élément — résolu à la compilation, comme actor.get. Pas de fonction
        runtime : l'index est la même constante que celle émise en tête de fichier, et
        c'est le type que le checker a jugé (`ref_kinds`) qui dit laquelle : une liste
        est tenue par son index de LISTE, ce que ses propriétés (`menu.index`) attendent."""
        if not args or not isinstance(args[0], ExprString):
            return "/* interface:get() : argument invalide */"
        name = args[0].value
        return ref_constant((self._kinds or {}).get(name, REF_UI_ELEMENT), name)

    def _sequence_step_arg(self, args: list, call: str) -> Optional[str]:
        """L'accès à l'étape de la séquence nommée, ou None si le nom n'est pas
        un littéral (le checker l'a déjà refusé)."""
        if not args or not isinstance(args[0], ExprString):
            self.warnings.append(f"{call}: sequence name is not a literal.")
            return None
        return self._state_ref(f"seq_{args[0].value}_step")

    def _emit_sequence_start(self, args: list) -> str:
        """`sequence:start("intro")` → l'étape passe à 1. Aucune fonction C :
        démarrer une séquence, c'est écrire 1 dans son entier d'état."""
        ref = self._sequence_step_arg(args, "sequence.start")
        return f"{ref} = 1" if ref else "0"

    def _emit_sequence_stop(self, args: list) -> str:
        """0 = arrêtée. Une séquence relancée repart de sa première tranche —
        l'étape est la seule chose qui dise où elle en était."""
        ref = self._sequence_step_arg(args, "sequence.stop")
        return f"{ref} = 0" if ref else "0"

    def _emit_sequence_running(self, args: list) -> str:
        ref = self._sequence_step_arg(args, "sequence.running")
        return f"({ref} != 0)" if ref else "0"

    def _emit_actor_spawn(self, args: list) -> str:
        """actor:spawn("PrefabName", pos) → spawn_<Scène>_PrefabName(pos.x, pos.y)

        Le pool est per-scène (ROADMAP v0.17, T1) : la fonction de spawn appartient
        à la scène qui compile ce script, d'où le préfixe. Une unité partagée
        (caméra, `scene_sym` vide) n'a pas de scène à cibler — refusé."""
        if len(args) < 2 or not isinstance(args[0], ExprString):
            return "/* actor.spawn: non-literal prefab name */"
        if not self.ctx.scene_sym:
            self.warnings.append(
                "actor.spawn outside a scene (shared script): the pool is per-scene, "
                "there is no spawn function to target.")
            return "/* actor.spawn: no scene (shared script) */"
        from codegen.c_names import sym as c_sym
        sym = f"{self.ctx.scene_sym}_{c_sym(args[0].value)}"
        pos = args[1]
        # vec2(x, y) littéral → ses deux composantes une fois, pas d'expression
        # dupliquée ; toute autre expression vec2 (variable, get_position()…)
        # → composantes déréférencées, comme le ferait l'appelant.
        if (isinstance(pos, ExprCall)
                and self._call_key(pos.func) == "vec2"
                and len(pos.args) == 2):
            px, py = self._expr(pos.args[0]), self._expr(pos.args[1])
        else:
            e = self._expr(pos)
            px, py = f"({e}).x", f"({e}).y"
        return f"spawn_{sym}({px}, {py})"

    def _spawn_setter_externs(self, script) -> list[str]:
        """Les `extern void <Scène>_<Prefab>_set_<clé>(Actor*, int);` de tous les
        `actor:spawn("X", pos, {k=v})` du script — dédupliqués. Walk sur les
        statements (une table de spawn n'est valide qu'au niveau statement, cf.
        checker), y compris dans les blocs if/while/for."""
        if script is None or not self.ctx.scene_sym:
            return []
        from codegen.c_names import sym as c_sym
        seen: set = set()
        out: list[str] = []

        def look(call):
            if not (isinstance(call, ExprCall)
                    and self._call_key(call.func) == "actor.spawn"):
                return
            tbl = self._spawn_table(call.args)
            if tbl is None or not isinstance(call.args[0], ExprString):
                return
            prefab = call.args[0].value
            sym = f"{self.ctx.scene_sym}_{c_sym(prefab)}"
            meta = self.ctx.spawn_exports.get(prefab) or {}
            for key in tbl.keys:
                # Seules les clés RÉGLABLES du prefab ont un setter défini : une
                # clé inconnue (signalée en erreur par le checker) n'en a pas, et
                # la forward-déclarer référencerait un symbole qui n'existe pas.
                if not key or key not in meta or (sym, key) in seen:
                    continue
                seen.add((sym, key))
                arg_t = _export_setter_c_type(meta[key].get("type"))
                out.append(f"extern void {sym}_set_{key}(Actor* self, {arg_t} v);")

        def visit(stmts):
            for s in stmts or []:
                if isinstance(s, StmtCall):
                    look(s.call)
                elif isinstance(s, (StmtLocalAssign, StmtAssign)):
                    look(getattr(s, "value", None))
                visit(getattr(s, "then", None))
                visit(getattr(s, "body", None))
                visit(getattr(s, "else_", None))
                for _cond, body in getattr(s, "elseifs", None) or []:
                    visit(body)

        for fn in script.functions:
            visit(fn.body)
        return out

    def _next_spawn_tmp(self) -> int:
        n = getattr(self, "_spawn_tmp_n", 0)
        self._spawn_tmp_n = n + 1
        return n

    @staticmethod
    def _spawn_table(args: list):
        """La table d'exports d'`actor:spawn("X", pos, {k=v})` (3ᵉ argument), ou
        None. Une table à clés seulement — un tableau positionnel n'en est pas une."""
        if len(args) >= 3 and isinstance(args[2], ExprTable) and args[2].keys:
            return args[2]
        return None

    def _emit_spawn_setters(self, dest: str, prefab_name: str, table) -> None:
        """Écrit les exports fournis dans l'instance née, via les setters extern
        du prefab (`<Scène>_<Prefab>_set_<clé>`). Seules les clés fournies sont
        posées ; les autres gardent le défaut du pool (repli template, T1)."""
        from codegen.c_names import sym as c_sym
        sym = f"{self.ctx.scene_sym}_{c_sym(prefab_name)}"
        calls = []
        for key, val in zip(table.keys, table.items):
            if key is None:
                continue
            cval = self._spawn_export_value(prefab_name, key, val)
            if cval is None:
                continue   # clé inconnue / type non réglable — signalé par le checker
            calls.append(f"{sym}_set_{key}({dest}, {cval});")
        if not calls:
            return
        self._w(f"if ({dest}) {{")
        self._indent += 1
        for c in calls:
            self._w(c)
        self._indent -= 1
        self._w("}")

    def _spawn_export_value(self, prefab_name: str, key: str, value_expr) -> Optional[str]:
        """La valeur d'une clé de table de spawn, en littéral C. Résolue DANS la
        scène du spawner (c'est là que le nom d'un acteur a un sens) :
          - enum → index de l'étiquette ; bool → 0/1 ; int/float → l'entier ;
          - sfx_ref/scene_ref → SFX_*/SCENE_IDX_* ; actor_ref → TAG_* qualifié
            par la scène du spawner ; string → index de texte (TEXT_*, anonyme) ;
          - vec2/vec3/rect → le littéral composé `(Vec2){x, y}` (via _expr).
        None si la clé n'est pas un export réglable du prefab (checker l'aura
        signalé). Les *_ref/string vides tombent sur 0 — pas de référence."""
        meta = (self.ctx.spawn_exports.get(prefab_name) or {}).get(key)
        if not meta:
            return None
        typ = meta.get("type")
        if typ == "enum":
            if isinstance(value_expr, ExprString):
                vals = meta.get("values") or []
                return str(vals.index(value_expr.value)) if value_expr.value in vals else "0"
            return self._expr(value_expr)
        if typ == "bool" and isinstance(value_expr, ExprBool):
            return "1" if value_expr.value else "0"
        if typ in ("sfx_ref", "scene_ref", "actor_ref", "string"):
            name = value_expr.value if isinstance(value_expr, ExprString) else ""
            return self._ref_or_text_literal(typ, name)
        return self._expr(value_expr)

    def _ref_or_text_literal(self, typ: str, name: str) -> str:
        """Un nom d'export `*_ref`/`string` → sa constante C, dans le contexte de
        CE fichier (le posé, le template poolé, ou le spawner). Vide → « 0 ». Les
        macros émises (SFX_*, SCENE_IDX_*, TAG_*, TEXT_*) sont toutes en portée
        ici — l'en-tête du fichier les #define (cf. _emit_header)."""
        if not name:
            return "0"
        if typ == "sfx_ref":
            return sfx_constant(name)
        if typ == "scene_ref":
            return scene_constant(name)
        if typ == "actor_ref":
            from codegen.c_names import sym as c_sym
            return f"TAG_{(self.ctx.scene_sym + '_' + c_sym(name)).upper()}"
        # string → entrée de texte : une clé réelle du projet garde son rang,
        # sinon c'est un littéral, entré comme texte ANONYME au build (même
        # chemin que text:draw("…"), cf. project_texts.collect_literal_texts).
        key = name if name in self.ctx.text_keys else anon_text_key(name)
        return text_constant(key)

    def _emit_save_read(self, args: list) -> str:
        """save:read(slot, "nom") → save_read_var(slot, GLOBAL_NOM) — le nom
        reste un second argument LITTÉRAL ici (pas un accès pointé comme
        `global.nom`) : le premier argument est l'emplacement, pas le
        récepteur, et c'est GLOBAL_NOM (l'id de sauvegarde) qu'il faut, pas
        g_nom (la variable en mémoire vive)."""
        if len(args) >= 2 and isinstance(args[1], ExprString):
            slot = self._expr(args[0])
            return f"save_read_var({slot}, GLOBAL_{args[1].value.upper()})"
        return "/* save.read: non-literal name */"

    def _emit_stub(self, event_name: str):
        """Stub vide pour un event non défini dans le script.

        Sauf `on_update` quand le script déclare des séquences : c'est là
        qu'elles avancent, et un script peut très bien n'écrire QUE des
        séquences — le stub porte alors le pompage."""
        if event_name == "on_update" and self._seq_plans:
            if not self.ctx.has_self:
                sig = scene_event_sig(self.ctx.actor_sym, "on_update", self.ctx.owner_kind)
            else:
                sig = EVENT_C_SIGNATURES["on_update"].format(prefix=self.ctx.actor_sym)
            self._w(sig + " {")
            self._indent += 1
            mark = self._open_state_scope()
            self._emit_sequence_pump()
            self._close_state_scope(mark)
            self._indent -= 1
            self._w("}")
            self._w("")
            return
        if not self.ctx.has_self:
            if event_name not in self._known_hooks():
                return
            sig = scene_event_sig(self.ctx.actor_sym, event_name, self.ctx.owner_kind)
            self._w(sig + " {}")
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(event_name)
            if sig_tpl is None:
                return
            sig = sig_tpl.format(prefix=self.ctx.actor_sym)
            sig = sig.replace("Actor* self", "Actor* self __attribute__((unused))")
            sig = sig.replace("Actor* other", "Actor* other __attribute__((unused))")
            sig = sig.replace("int event_id", "int event_id __attribute__((unused))")
            sig = sig.replace("int value", "int value __attribute__((unused))")
            sig = sig.replace("u8 my_box", "u8 my_box __attribute__((unused))")
            sig = sig.replace("u8 other_box", "u8 other_box __attribute__((unused))")
            sig = sig.replace("int normal_x", "int normal_x __attribute__((unused))")
            sig = sig.replace("int normal_y", "int normal_y __attribute__((unused))")
            self._w(sig + " {}")
        self._w("")

    # ── Émission de lignes ────────────────────────────────────────

    def _w(self, line: str):
        self._lines.append("    " * self._indent + line)


# ─── Tables de dispatch — fonctions Lua qui ne se traduisent pas par un
# simple appel de fonction C (expression brute, args synthétisés depuis le
# contexte de build, émission multi-instructions...). Chaque clé existe
# aussi dans RUNTIME_API (scripting/api.py) pour la validation/doc — cette
# table ne gère que la traduction C, à un seul endroit plutôt qu'éparpillée
# en if/elif dans _invoke/_call.

_INVOKE_CUSTOM: dict = {
    # Les trois réglages d'une référence d'effet qui portent un POURCENTAGE :
    # ils passent par un émetteur parce que la valeur change de graduation
    # entre le script et le registre. `:stop()` et `:playing()` n'en ont pas
    # besoin — ils se traduisent terme à terme depuis le catalogue.
    "sfx:set_volume":  CodeGen._emit_sfx_set_volume,
    "sfx:set_pitch":   CodeGen._emit_sfx_set_pitch,
    "sfx:set_panning": CodeGen._emit_sfx_set_panning,
    "collision_box:overlaps": CodeGen._emit_box_overlaps,
    "actor:destroy":  CodeGen._emit_destroy,
    "actor:play_sfx": CodeGen._emit_play_sfx,
    # Le littéral d'un texte pose ses `$locale` avant l'appel (cf. `_emit_text_literal`).
    f"{REF_TEXT_REGION}:draw": CodeGen._emit_text_region_draw,
}

# ── Résolution des domaines : un domaine → la constante C ──────────
# Une table et non un `match` : elle se compare à `ALL_DOMAINS` au build
# (`validator._check_api_domains`), ce qu'une suite de `case` ne permet pas.
# Un domaine ajouté sans entrée ici partait en littéral C, silencieusement.
_DOMAIN_CONSTANT: dict = {
    DOMAIN_ANIM:    lambda g, name: anim_constant(g.ctx.actor_sym, name),
    DOMAIN_SPRITE_ID: lambda g, name: sprite_id_constant(g.ctx.actor_sym, name),
    DOMAIN_SFX:     lambda g, name: sfx_constant(name),
    DOMAIN_MUSIC:   lambda g, name: music_constant(name),
    # `pressed`/`released` (accord simple, jamais une séquence depuis la
    # décision de l'auteur du 2026-09-27) passent par ce chemin générique ;
    # `held`/`buffered` ont leur propre émetteur (`_input_mask_arg`) pour
    # l'argument optionnel/le bit de tampon, mais lisent le MÊME dict.
    DOMAIN_KEY:     lambda g, name: g.ctx.input_masks.get(name, key_constant(name)),
    DOMAIN_TAG:     lambda g, name: tag_constant(name),
    DOMAIN_BOX_TAG: lambda g, name: box_tag_constant(name),
    DOMAIN_SCENE:   lambda g, name: scene_constant(name),
    DOMAIN_LANG:    lambda g, name: lang_constant(name),
    DOMAIN_CAMERA:  lambda g, name: camera_constant(name),
    # Pas `hardware_enum_constant` : depuis le 2026-08-25 la moitié des noms
    # valides (les WindowSlot du projet) n'existe dans aucune table statique
    # — même mécanique que DOMAIN_CAMERA, dérivée du nom, pas d'une table.
    DOMAIN_WIN_REGION: lambda g, name: window_region_constant(name),
    # Une chaîne qui ne matche aucune clé est un LITTÉRAL (`text.draw` seul le
    # permet, cf. Param.literal_ok) : il a sa propre entrée de table, donc le C
    # ne voit qu'un index comme pour tout texte.
    DOMAIN_TEXT:    lambda g, name: text_constant(
        name if name in g.ctx.text_keys else anon_text_key(name)),
    DOMAIN_FONT:    lambda g, name: font_constant(name),
    DOMAIN_PALETTE: lambda g, name: palette_constant(name),
    # Énumérations matérielles : la constante C vient de `HARDWARE_ENUMS`, la
    # même table que celle où le checker a validé le nom. Le C généré porte donc
    # `WINR_OBJ` et non `2` — lisible pour qui relit le build.
    DOMAIN_OBJ_MODE:   lambda g, name: hardware_enum_constant(DOMAIN_OBJ_MODE, name),
    DOMAIN_DIRECTION:  lambda g, name: hardware_enum_constant(DOMAIN_DIRECTION, name),
    DOMAIN_BLEND_MODE: lambda g, name: hardware_enum_constant(DOMAIN_BLEND_MODE, name),
    DOMAIN_BLEND_SIDE: lambda g, name: hardware_enum_constant(DOMAIN_BLEND_SIDE, name),
    DOMAIN_EASE:       lambda g, name: hardware_enum_constant(DOMAIN_EASE, name),
}

# Domaines SANS constante générique : leur argument est résolu par un émetteur
# dédié de `_CALL_CUSTOM` (nom de prefab poolé, actor résolu à la compilation,
# variable C nommée) et n'atteint donc jamais `_resolve_arg`. Les déclarer est
# ce qui distingue « traité ailleurs » de « oublié ».
_DOMAIN_EMITTED_ELSEWHERE: frozenset = frozenset({
    # Résolus par les émetteurs des trois boîtes : l'index est le RANG de
    # l'état dans sa boîte, pas une constante par nom.
    DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE, DOMAIN_MUSIC_BOX_TRIGGER,
    DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL,
    # Une séquence n'a pas de constante C : son nom désigne une variable
    # d'état, que `_emit_sequence_start/stop/running` écrit ou teste.
    DOMAIN_SEQUENCE,
    # L'état d'une image se résout avec l'image du RÉCEPTEUR (`IMGST_{image}_{état}`),
    # donc pas depuis le seul littéral — cf. `_prop_constant`.
    DOMAIN_IMAGE_STATE,
    # interface:get("nom") résout directement en UIELEM_<NOM>, comme actor.get résout
    # DOMAIN_ACTOR — cf. `_emit_ui_get`.
    DOMAIN_UI_ELEMENT,
    # `get_axis` n'a pas de constante par nom : chaque argument devient une
    # PAIRE d'expressions (masque négatif/positif), assemblées par l'émetteur
    # dédié (`_emit_get_axis`, ROADMAP « Les inputs personnalisés »).
    DOMAIN_AXIS,
    # `get_sequence` n'a pas de constante par nom : une alternance dans
    # l'expression développe plusieurs tables C, réunies par un OU — cf.
    # `_emit_get_sequence`.
    DOMAIN_INPUT_SEQUENCE,
})


def covered_domains() -> frozenset:
    """Domaines dont le codegen sait quoi faire — constante générique, ou
    émetteur dédié. Pendant exact de `checker.covered_domains()`."""
    return frozenset(_DOMAIN_CONSTANT) | _DOMAIN_EMITTED_ELSEWHERE


_CALL_CUSTOM: dict = {
    "array":       CodeGen._emit_array_misuse,
    "actor.get":   CodeGen._emit_get_actor,
    # `pressed`/`released` n'ont plus de cas particulier depuis que les
    # séquences ont quitté leur espace de noms (2026-09-27) : un simple
    # accord, résolu par `_DOMAIN_CONSTANT[DOMAIN_KEY]` comme n'importe quel
    # bouton — le chemin générique (`_emit_api_call`) suffit.
    "input.held":         CodeGen._emit_input_held,
    "input.buffered":     CodeGen._emit_input_buffered,
    "input.get_sequence": CodeGen._emit_get_sequence,
    "input.get_axis":     CodeGen._emit_get_axis,
    "actor.count": CodeGen._emit_actor_count,
    "save.read":   CodeGen._emit_save_read,
    "actor.spawn": CodeGen._emit_actor_spawn,
    "text.draw": CodeGen._emit_text_draw,
    "sequence.start":   CodeGen._emit_sequence_start,
    "sequence.stop":    CodeGen._emit_sequence_stop,
    "sequence.running": CodeGen._emit_sequence_running,
    "sfx.play":    CodeGen._emit_sfx_play,
    "music.play":    CodeGen._emit_music_play,
    "music.set_volume":      CodeGen._emit_music_set_volume,
    "sound_box.set_volume":  CodeGen._emit_sound_box_set_volume,
    "jingle_box.set_volume": CodeGen._emit_jingle_box_set_volume,
    "sound_box.set_state":  CodeGen._emit_sound_box_set_state,
    "jingle_box.set_state": CodeGen._emit_jingle_box_set_state,
    "music_box.trigger":    CodeGen._emit_sound_trigger,
    "music.jingle":  CodeGen._emit_music_jingle,
    "music.fade_to": CodeGen._emit_music_fade_to,
    "music.cut_to":  CodeGen._emit_music_cut_to,
    "interface.get":       CodeGen._emit_ui_get,
    "layer.get":           CodeGen._emit_layer_get,
    "window.get":          CodeGen._emit_window_get,

    "debug.log":    CodeGen._emit_debug_log,
}


# ─── Point d'entrée public ────────────────────────────────────────

def generate(script: LuaScript, ctx: CodegenContext) -> tuple[str, list[str], int]:
    """Retourne (code C, warnings, octets d'état par instance).

    `warnings` couvre les behaviors requis manquants/invalides, non bloquants
    mais à faire remonter à l'utilisateur. Le troisième terme est ce que
    l'état de ce script coûte dans UNE instance d'un prefab poolé — 0 partout
    ailleurs, un acteur de scène n'ayant qu'une instance et rangeant tout au
    scope fichier. C'est le chiffre que le build annonce."""
    gen = CodeGen(ctx)
    code = gen.generate(script)
    return code, gen.warnings, gen.pool_state_bytes
