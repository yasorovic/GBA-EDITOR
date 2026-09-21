"""
editor/scripting/checker.py — Vérification sémantique d'un LuaScript.

Reçoit le LuaScript produit par parser.py et une description du contexte
de build (nom de l'actor, sprites disponibles, sfx disponibles…).
Retourne une liste de CheckError ; si vide, le script peut être compilé.

Vérifications en v1 :
  - Toutes les fonctions top-level sont des handlers connus (KNOWN_EVENTS)
  - Les appels self:method correspondent à l'API (RUNTIME_API)
  - Les appels module.func correspondent à l'API
  - Les noms d'animation passés à play_anim existent dans le SpriteAsset
  - Les noms de sfx existent dans le projet
  - Les noms de music existent dans le projet
  - Les boutons passés à input.held / input.pressed sont valides
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .parser import (
    LuaScript, LuaFunction,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile, StmtForNum, StmtReturn,
    StmtUnsupported, ExprUnsupported,
    ExprInvoke, ExprCall, ExprIndex, ExprIndexAt, ExprTable, ExprName, ExprString,
    ExprNumber, ExprUnop, ExprBool, ExprBinop, ExprNil,
    ARRAY_CTOR, array_dims, DATA_NS, REQUIRE_FN, require_target, local_names,
    assigned_names, sequence_name, wait_call, WAIT_FN, WAIT_UNTIL_FN, WAIT_FNS,
    SEQUENCE_PREFIX,
)
from . import lua_subset
# Les 10 boutons GBA — source unique dans le SOCLE (core.models). `scripting`
# a le droit d'importer `core.models` (cf. check_architecture, INTERDITS) ; c'est
# `core.models` qui ne peut pas remonter vers `scripting`, d'où le sens de
# l'import (et non une seconde liste tenue ici).
from core.models.settings import BUTTON_NAMES
from .api import (RUNTIME_API, RUNTIME_PROPS, REMOVED_API, KNOWN_EVENTS, DOMAIN_ANIM, DOMAIN_SFX,
                  DOMAIN_SOUND_BOX_STATE, DOMAIN_JINGLE_BOX_STATE,
                  DOMAIN_MUSIC_BOX_TRIGGER,
                  DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_SCENE, DOMAIN_CAMERA, DOMAIN_TEXT, DOMAIN_FONT,
                  DOMAIN_LANG,
                  DOMAIN_PALETTE,
                  DOMAIN_REGION, DOMAIN_IMAGE, DOMAIN_IMAGE_STATE, DOMAIN_UI_ELEMENT,
                  DOMAIN_UI_LIST,
                  DOMAIN_TAG, DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL,
                  DOMAIN_SEQUENCE,
                  DOMAIN_OBJ_MODE, DOMAIN_DIRECTION, DOMAIN_WIN_REGION,
                  DOMAIN_BLEND_MODE, DOMAIN_BLEND_SIDE, DOMAIN_EASE, HARDWARE_ENUMS,
                  API_MODULES, module_members, REF_TYPES)
from .expr_types import (VEC_FIELDS, VEC_CONSTRUCTORS, ARITH_TYPES,
                         infer_vec_type, infer_ref_type, resolve_prop)


# Ce à quoi ressemble une CLÉ et pas un libellé : minuscules, chiffres, au
# moins un tiret bas, ni espace ni accent. « village_garde_01 » oui, « Appuyez
# sur A » non — de quoi voir la faute de frappe sans suspecter chaque littéral
# (cf. Checker._check_text).
_KEY_SHAPED = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")


# ─── Résultat ─────────────────────────────────────────────────────

@dataclass
class CheckError:
    level:   str   # "error" | "warning"
    message: str


@dataclass
class BuildContext:
    """
    Informations fournies par build.py pour la validation contextuelle.
    Tous les champs sont optionnels ; si absent, la vérification est relâchée.
    """
    actor_name:   str        = ""
    anim_names:   list[str]  = None    # noms d'anim définis dans le SpriteAsset lié
    # `AnimFrame.event_name` cités par le sprite lié (ROADMAP v0.8.9) — une
    # fonction de premier niveau portant l'un de ces noms est un EventCall,
    # pas une fonction inconnue : cf. `_check_function`.
    frame_event_names: list[str] = None
    sfx_names:    list[str]  = None    # noms de Sfx dans le projet
    music_names:  list[str]  = None    # noms de Music dans le projet
    scene_names:  list[str]  = None    # noms de scènes du projet
    # Codes des langues DÉCLARÉES (ROADMAP v0.9, phase 4). `lua_compiler` pose
    # toujours une LISTE, `[]` dans un projet monolingue — lang.set/lang.get
    # n'ont alors aucun code valide, donc tout appel est refusé, sans cas
    # spécial à écrire ici. `None` (l'absence) relâche la vérification, comme
    # tout le reste de ce contexte.
    lang_codes:   list[str]  = None
    camera_names: list[str]  = None    # noms de caméras du projet (pour camera.switch)
    window_names: list[str]  = None    # noms de WindowSlot du projet (pour window.*)
    sound_box_state_names: list[str]  = None  # états des SoundBox du projet
    jingle_box_state_names: list[str] = None  # états des JingleBox du projet
    music_box_trigger_names: list[str] = None  # déclencheurs des MusicBox
    actor_names:  list[str]  = None    # noms des actors de la scène (pour get_actor)
    prefab_names: list[str]  = None    # noms de Prefab du projet (pour actor.spawn)
    # Exports réglables par prefab (tranche poolé D2) : nom de prefab → { export →
    # {"type", "values"} }. Sert à valider la table d'`actor.spawn("X", pos, {k=v})`.
    spawn_exports: dict      = None
    global_names: list[str]  = None    # noms de GlobalVar déclarées dans le projet
    global_types: dict[str, str] = None  # nom -> type ("int"/"bool"/"u8"/"u16"/"s8"/"s16")
    # nom -> nombre de cases (ROADMAP v0.20). 1 = scalaire, ce qu'était toute
    # variable avant cette version ; au-delà, `global.nom[i]` l'indexe.
    global_counts: dict[str, int] = None
    # nom -> `persist` (ROADMAP v0.22). Sert UNIQUEMENT `save.read` : un nom
    # qui existe mais n'est pas coché persist ne figure dans aucun fichier de
    # sauvegarde — l'appel rendrait toujours le défaut, en silence.
    global_persist: dict[str, bool] = None
    # Noms des conteneurs marqués LISTE (ROADMAP v0.22).
    ui_list_names: list = None
    # Les enfants du propriétaire de ce script (ROADMAP v0.23) : `self.bras`
    # n'est valide que si « bras » en est un. None = information absente
    # (appel hors build), et la vérification ne s'applique pas.
    child_names: list = None
    const_names:  list[str]  = None    # noms de Constant déclarées dans le projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    text_keys:    list[str]  = None    # clés de la table de textes du projet
    font_names:   list[str]  = None    # noms des polices encodables
    palette_names: list[str] = None    # palettes du catalogue de couleurs
    region_names: list[str]  = None    # emplacements de texte (toutes mises en page)
    image_names:  list[str]  = None    # images d'interface (toutes mises en page)
    # TOUS les éléments d'UI, tous types confondus (pour ui.get) — texte, container
    # et image y figurent, contrairement à region_names/image_names qui ne
    # couvrent que ce qui dessine.
    element_names: list[str] = None
    # {nom d'image: [états de SON sprite]} — un état n'existe que dans un
    # sprite, et c'est l'image qui dit lequel (cf. `_check_image_state`).
    image_states: dict = None
    save_slots:   Optional[int] = None # emplacements de sauvegarde déclarés au projet
    # Tables de données : {nom: (noms de colonnes, nombre de lignes)}. Ce que le
    # checker en fait : refuser une table ou une colonne qui n'existe pas, borner
    # un index écrit en clair, et refuser l'écriture (elles sont `const` en ROM).
    data_tables:  dict = None
    # Y a-t-il seulement quelque chose à sauver ? Sauver sans variable
    # persistante n'échoue pas, ça ne fait simplement RIEN — le genre de silence
    # qu'on ne diagnostique pas en regardant son script.
    has_persistent: Optional[bool] = None
    # « Affine transform » est-il coché sur le SpriteComponent de cet
    # actor/prefab ? C'est ce qui lui réserve un slot de matrice affine au
    # build. self.rotation/self.scale s'écrivent et se relisent sans lui — ce
    # sont des champs de la struct Actor — mais rien ne les AFFICHE : d'où un
    # avertissement, et non le refus de build que c'était jusqu'au 2026-08-25.
    affine_transform: bool = False
    # Actions déclarées dans Project Settings. Elles partagent le paramètre
    # `btn` avec les boutons matériels : un script reste donc lisible et les
    # anciens `input.held("a")` restent valides.
    input_names: list[str] = None

    VALID_KEYS = frozenset(BUTTON_NAMES)   # dérivé du socle, jamais redéclaré


# Plage valide par type C généré (cf. scripting/globals.py) — "int" n'a pas
# de plage restreinte (entier natif ARM 32 bits), donc absent de la table.
_TYPE_RANGES = {
    "bool": (0, 1),
    "u8":   (0, 255),
    "s8":   (-128, 127),
    "u16":  (0, 65535),
    "s16":  (-32768, 32767),
}


# ─── Checker ──────────────────────────────────────────────────────

class Checker:

    def __init__(self, ctx: BuildContext):
        self.ctx    = ctx
        self.errors: list[CheckError] = []
        # Tableaux du script : nom → dimensions, ou None quand le même nom est
        # déclaré deux fois avec des tailles différentes. Une table PLATE, sans
        # portée lexicale : approximer large ne peut que taire un contrôle,
        # jamais en inventer un — et une erreur de bornes est bloquante, donc
        # elle ne doit jamais porter sur le mauvais tableau.
        self._arrays: dict[str, Optional[tuple[int, ...]]] = {}
        # Locals vec2/vec3 du script : nom → type, ou None si le même nom a
        # servi avec deux types différents. Même approximation, à plat, que
        # `_arrays` ci-dessus — cf. scripting/expr_types.py.
        self._vec_types: dict[str, Optional[str]] = {}
        # Locals qui tiennent une RÉFÉRENCE : nom → type de référence
        # (`local pas = sfx.play("Pas")` → "sfx"). C'est ce qui dit à quel
        # catalogue de méthodes un `pas:...` doit être confronté — sans quoi il
        # serait jugé comme une méthode d'actor, et refusé.
        self._ref_types: dict[str, str] = {}
        # Les deux espaces de noms qu'un script peut appeler en plus du
        # catalogue : l'alias d'un behavior importé (`local AI =
        # require("behaviors/ai")` → `AI.update(self)`) et, dans un behavior, sa
        # propre table de module (`M.aide(x)`). Sans eux, refuser les appels
        # inconnus refuserait aussi les seuls appels légitimes hors catalogue.
        self._require_aliases: set[str] = set()
        self._module_functions: dict[str, list[str]] = {}
        # Fonctions privées du script : des helpers nommés au premier niveau,
        # différents des handlers, séquences et EventCall de frame. Elles ne
        # quittent jamais ce fichier Lua ; le codegen leur passe `self` en
        # premier argument C.
        self._helpers: dict[str, LuaFunction] = {}
        self._current_function: str = ""
        # Tout ce qu'un nom NU a le droit d'être : un `local` (où qu'il soit
        # déclaré), un paramètre de fonction, une variable de boucle. Ce
        # langage n'a pas de variable de script implicite — une globale
        # s'écrit `global.nom` —, donc un nom hors de cet ensemble ne désigne
        # rien et le C émis citerait un identifiant qui n'existe pas.
        self._local_names: set[str] = set()
        # Un nom inconnu se dit UNE fois par script, pas une fois par
        # occurrence : `curpos = curpos + 1` le rencontre trois fois (la cible,
        # la cible relue comme expression, l'opérande) et trois lignes
        # identiques donneraient à chercher trois fautes.
        self._bare_said: set[str] = set()
        # Remplis par `check()` — cf. les commentaires là-bas.
        self._sequences: list[str] = []
        self._assigned:  set[str]  = set()
        # `id()` des appels `actor.spawn(...)` en position STATEMENT (début de
        # ligne ou `local x = …`), les seules où le codegen sait écrire la table
        # d'exports (tranche poolé D2). Rempli par `_check_stmt`, lu par
        # `_check_spawn_table`.
        self._spawn_stmt_ok: set = set()

    def check(self, script: LuaScript, check_event_names: bool = True) -> list[CheckError]:
        if check_event_names:
            helper_list = [
                fn for fn in script.functions
                if ("." not in fn.name
                    and sequence_name(fn.name) is None
                    and fn.name not in KNOWN_EVENTS
                    and fn.name not in (self.ctx.frame_event_names or ()))
            ]
            self._helpers = {fn.name: fn for fn in helper_list}
            self._check_helpers(helper_list)
        self._collect_arrays(script)
        self._collect_local_types(script)
        self._collect_namespaces(script)
        self._collect_local_names(script)
        # Les séquences déclarées par CE script : l'espace de noms de
        # `sequence.start` est le script, pas le projet (cf. DOMAIN_SEQUENCE).
        # Et les noms qu'aucune ligne n'assigne, pour le refus du `wait_until`
        # dont la condition ne peut jamais devenir vraie.
        self._sequences = [s for s in (sequence_name(fn.name) for fn in script.functions)
                           if s is not None]
        self._assigned = assigned_names(script)
        for loc in script.locals:
            self._check_array_decl(loc.name, loc.value)
        self._check_export_names(script)
        for fn in script.functions:
            self._check_function(fn, check_event_names)
        return self.errors

    _EXPORT_WIRED_TYPES = frozenset({"int", "float", "bool", "enum"})

    def _check_export_names(self, script: LuaScript) -> None:
        """Un export est émis comme variable C à NOM NU (chantier « Les exports de
        script, câblés au jeu »). Son nom ne doit donc rien masquer : ni un champ
        FIXE de la struct Actor (`self.position`…), ni un global du projet, ni un
        namespace/fonction de l'API — sinon le C émis casse ou trompe l'auteur.
        C'est la contrepartie du choix du nom nu (pas de préfixe `export.`).

        Signale aussi, en avertissement, un export d'un type dont la valeur
        d'instance n'est pas ENCORE câblée au build (le premier jet ne règle par
        instance que int/bool/float/enum) : le défaut du script s'applique alors.
        """
        from .expr_types import _ACTOR_PROP_FIELDS
        globals_ = set(self.ctx.global_names or [])
        reserved = self._NAMESPACES | frozenset(RUNTIME_API) | frozenset(VEC_CONSTRUCTORS)
        for loc in script.locals:
            if not loc.export_type:
                continue
            name = loc.name
            if name in _ACTOR_PROP_FIELDS:
                why = f"un champ de la struct Actor (self.{name})"
            elif name in globals_:
                why = "une variable globale du projet"
            elif name in reserved:
                why = "un mot réservé du langage ou de l'API"
            else:
                why = None
            if why:
                self.errors.append(CheckError(
                    "error",
                    f"export « {name} » : ce nom est déjà {why} — choisis-en un autre."))
            if loc.export_type not in self._EXPORT_WIRED_TYPES:
                self.errors.append(CheckError(
                    "warning",
                    f"export « {name} » de type '{loc.export_type}' : la valeur réglée "
                    f"par instance n'est pas encore appliquée au build ; le défaut du "
                    f"script s'applique."))

    def _check_helpers(self, helpers: list[LuaFunction]):
        """Contrat volontairement petit des fonctions privées.

        Le runtime ne porte pas de type dynamique : un helper reçoit et rend
        des entiers (un booléen est aussi un entier). `self` est ajouté par le
        compilateur, il ne doit donc pas apparaître dans ses paramètres Lua.
        """
        counts: dict[str, int] = {}
        for fn in helpers:
            counts[fn.name] = counts.get(fn.name, 0) + 1
            if fn.name in RUNTIME_API or fn.name in VEC_CONSTRUCTORS:
                self.errors.append(CheckError(
                    "error", f"Fonction privée '{fn.name}' : ce nom appartient déjà à l'API."))
            if "self" in fn.params:
                self.errors.append(CheckError(
                    "error", f"Fonction privée '{fn.name}' : `self` est implicite ; ne le mets pas en paramètre."))
        for name, n in counts.items():
            if n > 1:
                self.errors.append(CheckError("error", f"Fonction privée '{name}' déclarée {n} fois."))

        # Un appel de helper est direct ; un cycle ne peut donc ni se dérouler
        # ni être transformé en machine d'états. Le refuser ici évite un stack
        # overflow C sur une GBA.
        graph = {name: self._helper_calls(fn.body) for name, fn in self._helpers.items()}
        visiting, done = set(), set()
        def visit(name):
            if name in visiting:
                self.errors.append(CheckError("error", f"Récursion interdite : '{name}' s'appelle directement ou par une autre fonction privée."))
                return
            if name in done:
                return
            visiting.add(name)
            for called in graph[name]:
                visit(called)
            visiting.remove(name)
            done.add(name)
        for name in graph:
            visit(name)

    def _helper_calls(self, stmts) -> set[str]:
        found: set[str] = set()
        def expr(e):
            if isinstance(e, ExprCall):
                if isinstance(e.func, ExprName) and e.func.name in self._helpers:
                    found.add(e.func.name)
                expr(e.func)
                for arg in e.args: expr(arg)
            elif isinstance(e, ExprInvoke):
                expr(e.obj)
                for arg in e.args: expr(arg)
            elif isinstance(e, ExprIndex): expr(e.obj)
            elif isinstance(e, ExprIndexAt): expr(e.obj); expr(e.index)
            elif isinstance(e, ExprBinop): expr(e.left); expr(e.right)
            elif isinstance(e, ExprUnop): expr(e.operand)
            elif isinstance(e, ExprTable):
                for item in e.items: expr(item)
        for s in stmts:
            if isinstance(s, StmtCall): expr(s.call)
            elif isinstance(s, (StmtAssign, StmtLocalAssign)): expr(s.value)
            elif isinstance(s, StmtIf):
                expr(s.cond); found.update(self._helper_calls(s.then))
                for cond, body in s.elseifs: expr(cond); found.update(self._helper_calls(body))
                found.update(self._helper_calls(s.else_))
            elif isinstance(s, (StmtWhile, StmtForNum)):
                found.update(self._helper_calls(s.body))
            elif isinstance(s, StmtReturn):
                for value in s.values: expr(value)
        return found

    # ── Tableaux ──────────────────────────────────────────────────

    def _collect_arrays(self, script: LuaScript):
        """Relève toutes les déclarations de tableau du script, où qu'elles
        soient — les locals de tête comme celles d'un corps de handler."""
        def note(name: str, value):
            dims = array_dims(value)
            if dims is None:
                return
            if name in self._arrays and self._arrays[name] != dims:
                self._arrays[name] = None      # deux tailles : on ne conclut rien
            else:
                self._arrays[name] = dims

        def walk(stmts):
            for s in stmts:
                if isinstance(s, StmtLocalAssign):
                    note(s.name, s.value)
                elif isinstance(s, StmtIf):
                    walk(s.then)
                    for _, b in s.elseifs:
                        walk(b)
                    walk(s.else_)
                elif isinstance(s, (StmtWhile, StmtForNum)):
                    walk(s.body)

        for loc in script.locals:
            note(loc.name, loc.value)
        for fn in script.functions:
            walk(fn.body)

    def _collect_local_types(self, script: LuaScript):
        """Relève le type de chaque `local` du script, où qu'il soit déclaré —
        même parcours à plat que `_collect_arrays`, dans le même ordre que le
        script : au moment de noter `n = pos + vel`, `pos` et `vel` ont déjà
        été vus si le script les déclare avant.

        Deux tables remplies par le MÊME parcours : les valeurs composées
        (vec2/vec3/rect) et les références rendues par un appel (`sfx.play`).
        Deux natures, mais une seule question — « quel type porte ce nom ? » —
        et deux traversées auraient fini par répondre à des endroits différents.
        """
        def note(name: str, value):
            rt = infer_ref_type(value)
            if rt is not None:
                self._ref_types[name] = rt
            vt = infer_vec_type(value, self._vec_types)
            if vt is None:
                return
            if name in self._vec_types and self._vec_types[name] != vt:
                self._vec_types[name] = None   # deux types : on ne conclut rien
            else:
                self._vec_types[name] = vt

        def walk(stmts):
            for s in stmts:
                if isinstance(s, StmtLocalAssign):
                    note(s.name, s.value)
                elif isinstance(s, StmtIf):
                    walk(s.then)
                    for _, b in s.elseifs:
                        walk(b)
                    walk(s.else_)
                elif isinstance(s, (StmtWhile, StmtForNum)):
                    walk(s.body)

        for loc in script.locals:
            note(loc.name, loc.value)
        for fn in script.functions:
            walk(fn.body)

    def _collect_local_names(self, script: LuaScript):
        """Les noms qu'un nom NU a le droit de porter — locals (où qu'ils soient
        déclarés), table de module, paramètres de handler, variables de boucle.

        La lecture vit dans `parser.local_names` : à plat, sans portée, cette
        liste sert à REFUSER, donc trop large ne fait que taire un refus, jamais
        en inventer un. L'autocomplétion la PROPOSE depuis la même source (ROADMAP
        v0.27, phase 2) — d'où l'extraction, pour qu'un seul parcours nourrisse
        les deux."""
        self._local_names |= local_names(script)

    # ── Espaces de noms appelables ────────────────────────────────

    def _collect_namespaces(self, script: LuaScript):
        """Les alias de behavior et la table de module de ce script.

        Même parcours à plat que `_collect_arrays` : un `require` s'écrit en
        tête par convention, mais rien ne l'y oblige."""
        def note(name: str, value):
            if require_target(value) is not None:
                self._require_aliases.add(name)

        def walk(stmts):
            for s in stmts:
                if isinstance(s, StmtLocalAssign):
                    note(s.name, s.value)
                elif isinstance(s, StmtIf):
                    walk(s.then)
                    for _, b in s.elseifs:
                        walk(b)
                    walk(s.else_)
                elif isinstance(s, (StmtWhile, StmtForNum)):
                    walk(s.body)

        for loc in script.locals:
            note(loc.name, loc.value)
        for fn in script.functions:
            walk(fn.body)

        for module in script.module_names:
            prefix = f"{module}."
            self._module_functions[module] = [
                fn.name[len(prefix):] for fn in script.functions
                if fn.name.startswith(prefix)]

    def _check_array_decl(self, name: str, value):
        """Ce qui rend une déclaration de tableau invalide, et le dit sur la
        ligne fautive plutôt que sur le C généré."""
        dims = array_dims(value)

        if isinstance(value, ExprCall) and isinstance(value.func, ExprName) \
                and value.func.name == ARRAY_CTOR and dims is None:
            self.errors.append(CheckError(
                "error",
                f"{ARRAY_CTOR}() pour '{name}' : une ou deux tailles attendues, "
                f"écrites en clair et strictement positives — "
                f"{ARRAY_CTOR}(8) ou {ARRAY_CTOR}(20, 12). La taille fait partie "
                f"du type, elle doit être connue au build."))
            return

        if isinstance(value, ExprTable):
            if dims is None:
                if value.has_keys:
                    raison = "une entrée nommée — c'est un enregistrement, pas un tableau"
                elif not value.items:
                    raison = ("aucun élément — un tableau vide n'a pas de taille, "
                              f"écris {ARRAY_CTOR}(n)")
                else:
                    raison = "des lignes de longueurs différentes"
                self.errors.append(CheckError("error", f"'{name}' : {raison}."))
                return
            if len(dims) == 2:
                elements = [v for row in value.items for v in row.items]
            else:
                elements = list(value.items)
            if any(isinstance(v, ExprString) for v in elements):
                self.errors.append(CheckError(
                    "error",
                    f"'{name}' : un tableau ne contient que des entiers — le "
                    f"moteur n'a pas de chaîne manipulable. Pour du texte "
                    f"affichable, une colonne 'text' d'une table de données."))
                return


    def _array_chain(self, e: ExprIndexAt):
        """Vérifie `t[i]` et `t[i][j]` : le nom indexé, le nombre de dimensions
        employées, et les bornes quand l'index est écrit en clair."""
        indices = []
        cur = e
        while isinstance(cur, ExprIndexAt):
            indices.append(cur.index)
            cur = cur.obj
        indices.reverse()
        # `data.Objets[i]` : la base n'est pas un nom mais une table du projet,
        # et sa « dimension » est son nombre de lignes.
        table = self._data_table_ref(cur)
        if table is not None:
            self._check_data_rows(table, indices)
            return
        if not isinstance(cur, ExprName):
            return
        name = cur.name
        if name not in self._arrays:
            self.errors.append(CheckError(
                "warning",
                f"'{name}[…]' : '{name}' n'est pas un tableau déclaré dans ce "
                f"script."))
            return
        dims = self._arrays[name]
        if dims is None:
            return
        if len(indices) > len(dims):
            self.errors.append(CheckError(
                "error",
                f"'{name}' a {len(dims)} dimension(s), {len(indices)} index "
                f"employé(s)."))
            return
        for level, idx in enumerate(indices):
            k = self._literal_int(idx)
            if k is None:
                continue          # index calculé : borné par personne, assumé
            if not (1 <= k <= dims[level]):
                self.errors.append(CheckError(
                    "error",
                    f"'{name}[{k}]' : hors bornes — ce tableau va de 1 à "
                    f"{dims[level]} (les tableaux sont indexés à partir de 1, "
                    f"comme partout en Lua)."))

    # ── Tables de données ─────────────────────────────────────────

    @staticmethod
    def _data_table_ref(e) -> Optional[str]:
        """`data.Objets` → "Objets", sinon None."""
        if (isinstance(e, ExprIndex) and isinstance(e.obj, ExprName)
                and e.obj.name == DATA_NS):
            return e.field
        return None

    def _check_data_table(self, name: str) -> bool:
        """La table existe-t-elle ? Une table inconnue est une ERREUR : le
        `g_data_*` émis n'existerait pas, et gcc échouerait sur la ligne générée
        — même sévérité et même raison qu'une scène ou une palette inconnue."""
        if self.ctx.data_tables is None:
            return True
        if name in self.ctx.data_tables:
            return True
        near = ", ".join(sorted(self.ctx.data_tables)[:5]) or "aucune table dans le projet"
        self.errors.append(CheckError(
            "error", f"data.{name} : table de données introuvable ({near})."))
        return False

    def _check_global_scalar(self, name: str) -> None:
        """`global.nom` cité SEUL — comme valeur lue, ou comme cible d'une
        assignation (chantier global/const, remplace global.get/set). Un tableau ne
        s'y prête pas : il n'existe qu'indexé, cf. `_check_global_indexed`."""
        counts = self.ctx.global_counts
        if counts is None:
            return
        n = counts.get(name)
        if n is None:
            near = ", ".join(sorted(counts)[:5])
            self.errors.append(CheckError(
                "error",
                f"global.{name} : variable globale introuvable"
                + (f" (déclarées dans le projet : {near})." if near
                   else " — aucune variable globale déclarée dans ce projet.")))
            return
        if n > 1:
            self.errors.append(CheckError(
                "error",
                f"global.{name} est un TABLEAU ({n} cases) : il se lit et "
                f"s'écrit indexé, jamais nu — global.{name}[i]."))

    def _check_const_scalar(self, name: str) -> None:
        """`const.nom` cité seul — la seule forme qui existe, une constante ne
        s'indexe jamais (chantier global/const, remplace const.get)."""
        names = self.ctx.const_names
        if names is None:
            return
        if name not in names:
            near = ", ".join(sorted(names)[:5])
            self.errors.append(CheckError(
                "error",
                f"const.{name} : constante introuvable"
                + (f" (déclarées dans le projet : {near})." if near
                   else " — aucune constante déclarée dans ce projet.")))

    # Ce qu'un nom NU peut être SANS être une variable : un espace de noms.
    # `_check_expr` visite `e.obj` en fin de branche `ExprIndex`, donc le
    # `global` de `global.score` et le `camera` de `camera.bound` passent par
    # là. `API_MODULES` porte les modules du catalogue ; les quatre autres sont
    # des espaces résolus hors catalogue (accès pointé du chantier global/const,
    # tables de données, constantes d'écran) et `self`/`other` sont des
    # récepteurs. Un nom d'ACTEUR est légitime aussi (`paddle.position`) : il
    # vient du projet, donc du contexte de build.
    _NAMESPACES: frozenset = frozenset(API_MODULES) | frozenset({
        "global", "const", "data", "screen", "self", "other",
    })

    def _known_bare_name(self, name: str) -> bool:
        if name in self._local_names or name in self._NAMESPACES:
            return True
        if name in self._require_aliases or name in self._module_functions:
            return True
        for liste in (self.ctx.actor_names, self.ctx.prefab_names):
            if liste and name in liste:
                return True
        return False

    def _check_bare_name(self, name: str, ecrit: bool) -> None:
        """Un nom nu qui ne désigne rien (2026-09-02).

        Ce langage n'a pas de variable de script implicite : une valeur qui
        traverse les frames est un `local` de tête, une valeur partagée est
        `global.nom`. Un nom hors des deux ne désignait RIEN et traversait le
        checker sans un mot — le codegen émettait `curpos = (curpos + 1);`,
        et gcc parlait d'un identifiant inexistant dans un fichier que l'auteur
        n'a jamais écrit. C'est le piège le plus coûteux de cette chaîne.

        AVERTISSEMENT et non erreur, pour l'instant : le contrôle s'applique à
        tous les scripts de tous les projets, et un cas légitime oublié
        bloquerait un build qui marche. À durcir en erreur une fois éprouvé."""
        if self._known_bare_name(name) or name in self._bare_said:
            return
        self._bare_said.add(name)
        geste = ("s'écrit" if ecrit else "se lit")
        self.errors.append(CheckError(
            "warning",
            f"« {name} » ne désigne rien : ce nom n'est ni un `local` de ce "
            f"script, ni un paramètre. Une valeur qui traverse les frames "
            f"{geste} `local {name} = 0` en tête de fichier ; une valeur "
            f"partagée entre scripts s'écrit `global.{name}` (déclare-la dans "
            f"l'écran Variables)."))

    # ── Références d'élément d'interface ──────────────────────────
    # `ui.get("X")` rend une référence qui sait DEUX choses, et rien d'autre :
    # se montrer et se cacher. Elle n'a AUCUN champ — la position d'une image
    # se pose par `ui.image_move` (cf. ROADMAP v0.22), et la géométrie d'une
    # zone ou d'un conteneur ne s'ouvre pas au runtime.
    _UI_ELEMENT_METHODS: tuple = ("show", "hide")

    def _is_ui_element(self, e) -> bool:
        """`ui.get(...)` — la seule expression qui rende une référence
        d'élément. Reconnue par sa FORME et non par `REF_TYPES` : l'y inscrire
        ferait chercher les méthodes sous la clé `ui_element:show`, alors
        qu'elles vivent sous `self:show` — et casserait le `ui.get("x"):show()`
        qui marche aujourd'hui."""
        from .parser import ExprCall
        return isinstance(e, ExprCall) and self._call_key(e.func) == "ui.get"

    def _check_ui_element_field(self, e) -> None:
        """`ui.get("Cursor").y` — accepté en silence jusqu'ici, et produisant
        `UIELEM_CURSOR.y` en C : `.y` sur un `#define` entier, refusé par gcc
        sur une ligne que l'auteur n'a pas écrite."""
        self.errors.append(CheckError(
            "warning",
            f"ui.get(...).{e.field} : une référence d'élément d'interface n'a "
            f"pas de champ — elle sait seulement :show() et :hide(). Pour "
            f"déplacer une image, ui.image_move(nom, dx, dy) ; la géométrie "
            f"d'une zone de texte ou d'un conteneur, elle, est authorée."))

    def _check_const_write(self, target) -> None:
        """`const.nom = …` — une constante ne s'écrit jamais, c'est ce qui la
        distingue d'une variable globale. `_check_expr(target)` valide déjà le
        NOM (via `_check_const_scalar`) ; ne reste que l'écriture elle-même."""
        if (isinstance(target, ExprIndex) and isinstance(target.obj, ExprName)
                and target.obj.name == "const"):
            self.errors.append(CheckError(
                "error",
                f"const.{target.field} = … : une constante ne s'écrit jamais "
                f"— déclare une variable globale si elle doit changer."))

    def _check_global_indexed(self, name: str, index) -> None:
        """`global.nom[i]` — la base d'un tableau (ROADMAP v0.20). Trois
        fautes à dire ici plutôt que sur la ligne C générée : un nom qui
        n'existe pas, un SCALAIRE indexé (`g_score[0]` ne compile pas), et un
        rang hors bornes quand il est écrit en clair. Un index calculé ne se
        vérifie pas au build : il n'est pas plus contrôlé ici qu'ailleurs dans
        le langage."""
        counts = self.ctx.global_counts
        if counts is None:
            return
        n = counts.get(name)
        if n is None:
            near = ", ".join(sorted(k for k, v in counts.items() if v > 1)[:5])
            self.errors.append(CheckError(
                "error",
                f"global.{name} : variable globale introuvable"
                + (f" (tableaux du projet : {near})." if near
                   else " — aucun tableau déclaré dans ce projet.")))
            return
        if n <= 1:
            self.errors.append(CheckError(
                "error",
                f"global.{name} est une variable SIMPLE, pas un tableau : elle "
                f"se lit et s'écrit sans crochets — global.{name} / "
                f"global.{name} = …. La forme indexée est réservée aux "
                f"variables déclarées avec plusieurs cases."))
            return
        k = self._literal_int(index)
        if k is None:
            return
        if not (1 <= k <= n):
            self.errors.append(CheckError(
                "error",
                f"global.{name}[{k}] : hors bornes — ce tableau va de 1 à {n} "
                f"(les cases sont numérotées à partir de 1)."))

    def _check_ui_list(self, call_key: str, name: str):
        """Le nom désigne-t-il une LISTE d'interface ?

        Une erreur et non un avertissement : `UILIST_<NOM>` n'existerait pas, et
        gcc échouerait sur la ligne générée — même sévérité et même raison qu'un
        élément d'interface inconnu."""
        known = self.ctx.ui_list_names
        if known is None:
            return
        if name in known:
            return
        near = ", ".join(sorted(known)[:5]) or "aucune liste dans le projet"
        self.errors.append(CheckError(
            "error",
            f"{call_key}('{name}') : aucune liste de ce nom ({near}). Une liste "
            f"est un élément d'interface de type Liste, posé dans une mise en "
            f"page."))

    def _check_data_rows(self, table: str, indices: list):
        """Une table s'indexe sur UNE dimension — ses lignes — et le rang est
        borné comme celui d'un tableau, quand il est écrit en clair."""
        if not self._check_data_table(table) or self.ctx.data_tables is None:
            return
        _columns, rows = self.ctx.data_tables[table]
        if len(indices) > 1:
            self.errors.append(CheckError(
                "error",
                f"data.{table} s'indexe par sa LIGNE et rien d'autre : "
                f"data.{table}[i].colonne."))
            return
        k = self._literal_int(indices[0]) if indices else None
        if k is None:
            return
        if not (1 <= k <= rows):
            borne = (f"de 1 à {rows}" if rows else "vide — aucune ligne")
            self.errors.append(CheckError(
                "error",
                f"data.{table}[{k}] : hors bornes — cette table va {borne} "
                f"(les lignes sont numérotées à partir de 1)."))

    def _check_data_column(self, table: str, column: str):
        if self.ctx.data_tables is None or table not in self.ctx.data_tables:
            return
        columns, _rows = self.ctx.data_tables[table]
        if column not in columns:
            self.errors.append(CheckError(
                "error",
                f"data.{table}[…].{column} : cette table n'a pas de colonne "
                f"'{column}' ({', '.join(columns) or 'aucune colonne'})."))

    def _check_data_write(self, target):
        """Une table authorée est `const` en ROM : l'écriture ne compilerait
        pas. Autant le dire sur la ligne Lua fautive que sur la ligne générée."""
        node = target
        while isinstance(node, (ExprIndex, ExprIndexAt)):
            name = self._data_table_ref(node)
            if name is not None:
                self.errors.append(CheckError(
                    "error",
                    f"data.{name} ne s'écrit pas : une table de données est "
                    f"constante, cuite dans la ROM. Pour une valeur qui change "
                    f"en jeu, une variable globale ou un tableau de travail."))
                return
            node = node.obj

    def _check_prop_write(self, target, value):
        """Une propriété s'ÉCRIT par assignation de la valeur entière —
        `self.position = vec2(x, y)`. Un CHAMP d'une valeur composée ne
        s'écrit pas (`self.position.x = 5`) : la valeur est immuable, on
        réassigne l'objet entier. Et une propriété en lecture seule
        (`scene.size`) n'admet aucune écriture."""
        prop = resolve_prop(target)
        if prop is not None:
            receiver, p = prop
            nom = _prop_label(receiver, p)
            if p.read_only or p.c_setter is None:
                self.errors.append(CheckError(
                    "error",
                    f"{nom} est en lecture seule — on ne peut pas l'assigner."))
                return
            named = p.domain is not None
            if named and isinstance(value, ExprString):
                # Forme NOMMÉE — la seule écriture possible d'une propriété à
                # domaine scalaire, et l'une des deux de `self.direction`.
                self._check_prop_domain_value(receiver, p, value, "=")
            elif p.ptype in VEC_CONSTRUCTORS:
                vt = infer_vec_type(value, self._vec_types)
                if vt != p.ptype:
                    fields = ", ".join(VEC_FIELDS[p.ptype])
                    what = "un scalaire" if vt is None else f"un {vt}"
                    formes = f"{nom} = {p.ptype}({fields})"
                    exemple = _domain_example(p.domain)
                    if exemple:
                        formes += f' ou {nom} = "{exemple}"'
                    self.errors.append(CheckError(
                        "error",
                        f"{nom} attend un {p.ptype} — {formes} — "
                        f"et reçoit {what}."))
            elif named:
                self._check_prop_domain_value(receiver, p, value, "=")
            return
        # Un accès pointé EN DESSOUS d'un champ écrit : `self.position.x = 5`
        node = target
        while isinstance(node, ExprIndex):
            base = resolve_prop(node.obj)
            if base is not None:
                receiver, p = base
                nom = _prop_label(receiver, p)
                self.errors.append(CheckError(
                    "error",
                    f"impossible d'écrire dans {nom}.{node.field} : "
                    f"{nom} est une valeur composée immuable — on "
                    f"réassigne tout l'objet : {nom} = ..."))
                return
            node = node.obj

    def _check_prop_domain_value(self, receiver: str, p, value, op: str):
        """La valeur d'une propriété À DOMAINE s'écrit par son NOM
        (`self.obj_mode = "window"`, `other.tag == "Ball"`), jamais par le
        nombre correspondant.

        Le NOM est jugé par la table de domaine, exactement comme un ARGUMENT du
        même domaine (`_check_args`) : le domaine décide, pas la position ni la
        nature de ce qui le porte. C'est ce qui fait qu'une énumération
        matérielle et un espace de noms du projet — `TAG_*`, les acteurs et les
        prefabs — se valident du même geste.

        Une expression qui n'est ni un nombre ni une chaîne littérale (une
        variable) passe sans un mot : mêmes limites qu'ailleurs, on ne valide
        que ce qui est écrit en clair."""
        nom = _prop_label(receiver, p)
        if p.domain in _RECEIVER_DOMAINS and receiver != "self":
            # Même piège que pour un ARGUMENT du même domaine (_check_args,
            # plus haut) : le nom cité appartient au sprite du RÉCEPTEUR, que
            # ce script ne connaît pas — et le codegen le résout quand même
            # contre l'acteur courant (`anim_constant(ctx.actor_sym, ...)`),
            # produisant une constante crédible et fausse. Erreur ici, plutôt
            # qu'une comparaison à l'animation d'un autre acteur qui mentirait
            # en silence.
            self.errors.append(CheckError(
                "error",
                f"{nom} {op} ... : « {p.lua_name.split('.', 1)[1]} » nomme un "
                f"élément du sprite de « {receiver} », et il est résolu "
                f"contre celui de l'acteur qui exécute ce script. Cette "
                f"comparaison ne se fait que sur self."))
            return
        if isinstance(value, ExprNumber):
            valides = HARDWARE_ENUMS.get(p.domain)
            fin = (f" Valeurs valides : {', '.join(sorted(valides))}."
                   if valides else "")
            self.errors.append(CheckError(
                "error",
                f"{nom} {op} {value.value} : cette valeur s'écrit par son "
                f"nom, pas par un nombre.{fin}"))
            return
        if not isinstance(value, ExprString):
            return
        check = _DOMAIN_CHECKS.get(p.domain)
        if check:
            check(self, nom, value.value, p, [])

    def _check_prop_enum_compare(self, e: ExprBinop) -> bool:
        """`blend.mode == "alpha"`, `other.tag == "Ball"` — une propriété qui
        s'ÉCRIT par un nom se COMPARE par un nom, et une propriété en lecture
        seule qui en porte un ne se lit utilement que comme ça.

        Sans ça, la moitié LECTURE retomberait sur l'entier que l'écriture vient
        justement de supprimer — c'est l'asymétrie qu'avaient `self:set_dir
        ("north")` et `self:get_dir()` rendant un 0-8 nu.

        Rend True quand ce nœud est JUGÉ ici, pour que le contrôle vec ne rejoue
        pas dessus : `self.direction` est un vec2, et comparer un vec2 n'a
        effectivement pas de sens — sauf justement sous cette forme-là."""
        if e.op not in ("==", "!="):
            return False
        for side, other in ((e.left, e.right), (e.right, e.left)):
            prop = resolve_prop(side)
            if prop is None:
                continue
            receiver, p = prop
            if p.domain is not None and isinstance(other, (ExprString, ExprNumber)):
                self._check_prop_domain_value(receiver, p, other, e.op)
                return True
            return False
        return False

    def _check_prop_read(self, prop):
        """Contrôles portant sur la LECTURE d'une propriété. Le CHAMP qui suit
        (`self.position.x`) est validé par l'accès vec de `_check_expr`."""
        _, p = prop
        if (p.lua_name.startswith("self.")
                and p.lua_name.split(".")[1] in
                ("rotation", "scale", "sprite_rotation", "sprite_scale", "sprite_offset")
                and not self.ctx.affine_transform):
            self.errors.append(CheckError(
                "warning",
                f"{p.lua_name} : le sprite de cet actor n'a pas « Affine transform » "
                "coché — aucun slot de matrice affine n'est réservé au build. La "
                "valeur s'écrit et se relit, mais rien ne l'affiche à l'écran."))

    # ── Fonctions ─────────────────────────────────────────────────

    def _check_function(self, fn: LuaFunction, check_event_names: bool = True):
        # check_event_names=False pour les modules de behavior : leurs
        # fonctions top-level sont des noms de méthode arbitraires (M.update),
        # pas des handlers d'événement actor/scène — seul le corps est validé.
        seq = sequence_name(fn.name)
        is_frame_event = fn.name in (self.ctx.frame_event_names or ())
        is_helper = fn.name in self._helpers
        if check_event_names and not is_helper and seq is None and fn.name not in KNOWN_EVENTS and not is_frame_event:
            # ERREUR et non avertissement : le C émis pour un nom inconnu est
            # `static void <Acteur>_<nom>(Actor* self)`, qu'aucun appel Lua ne
            # peut atteindre (`nom()` s'émet `nom()`, sans le préfixe). Donc du
            # code mort au mieux, un « implicit declaration » au `make` au pire
            # — jamais ce que l'auteur croyait écrire.
            #
            # Exception : un nom cité par `AnimFrame.event_name` sur LE sprite
            # de cet actor (`frame_event_names`) EST atteint — pas par un appel
            # Lua, par le stepper d'anim de `main.c` (ROADMAP v0.8.9, EventCall,
            # cf. `codegen._emit_function` / `gen_sprite.actor_frame_event_lines`).
            self.errors.append(CheckError(
                "error",
                f"Fonction '{fn.name}' inconnue : une fonction de premier niveau "
                f"est un handler d'événement ({', '.join(KNOWN_EVENTS[:5])}…), "
                f"une séquence ({SEQUENCE_PREFIX}<nom>), ou un EventCall cité par "
                f"une frame du sprite de cet actor. "
                f"Pour du code partagé, un behavior — un fichier de "
                f"scripts/behaviors/, importé par require(\"behaviors/nom\").",
            ))
        if seq is not None:
            self._check_sequence_waits(fn, seq)
        if is_helper:
            self._check_helper_returns(fn)
        # `seq_top` : les attentes ne sont légales qu'ici, au premier niveau
        # d'une séquence. Partout ailleurs `_check_stmt` les refuse.
        previous, self._current_function = self._current_function, fn.name
        self._check_block(fn.body, seq_top=seq is not None)
        self._current_function = previous

    def _check_helper_returns(self, fn: LuaFunction):
        """Les helpers ont un ABI C volontairement réduit : retour scalaire.

        Sans ce garde-fou, `return vec2(...)` deviendrait un `return Vec2` dans
        une fonction C qui rend un int, et gcc nommerait une ligne générée.
        """
        def walk(stmts):
            for stmt in stmts:
                if isinstance(stmt, StmtReturn):
                    if len(stmt.values) > 1:
                        self.errors.append(CheckError(
                            "error", f"{fn.name}() : une fonction privée rend au plus une valeur entière."))
                    elif stmt.values:
                        value = stmt.values[0]
                        vector = infer_vec_type(value, self._vec_types)
                        ref = infer_ref_type(value)
                        array = isinstance(value, ExprName) and value.name in self._arrays
                        if vector or ref or array or isinstance(value, (ExprString, ExprTable)):
                            self.errors.append(CheckError(
                                "error", f"{fn.name}() : une fonction privée ne rend qu'un entier ou un booléen."))
                elif isinstance(stmt, StmtIf):
                    walk(stmt.then)
                    for _cond, body in stmt.elseifs: walk(body)
                    walk(stmt.else_)
                elif isinstance(stmt, (StmtWhile, StmtForNum)):
                    walk(stmt.body)
        walk(fn.body)

    # ── Séquences ─────────────────────────────────────────────────

    def _check_sequence_waits(self, fn: LuaFunction, seq: str):
        """Ce qui rend une attente invalide, dit sur sa ligne.

        Deux contrôles, et ils ne portent pas sur la même chose : la FORME de
        l'appel (un argument, du bon genre), et la question de fond — cette
        condition peut-elle seulement devenir vraie un jour ?"""
        # Les attentes d'une boucle bornée comptent autant que celles du premier
        # niveau (ROADMAP v0.23) : leur forme se vérifie de la même façon, sans
        # quoi `wait(x)` dans une boucle passerait sans être relu.
        def _waits(stmts):
            for st in stmts:
                if wait_call(st) is not None:
                    yield st
                elif isinstance(st, StmtForNum):
                    yield from _waits(st.body)

        for stmt in _waits(fn.body):
            w = wait_call(stmt)
            if w is None:
                continue
            kind, arg = w
            n_args = len(stmt.call.args)
            if n_args != 1:
                self.errors.append(CheckError(
                    "error",
                    f"{kind}() attend exactement un argument, {n_args} fourni(s) — "
                    f"une durée en frames pour {WAIT_FN}, une condition pour "
                    f"{WAIT_UNTIL_FN}."))
                continue
            if kind == WAIT_FN:
                if not isinstance(arg, ExprNumber) or arg.value < 0:
                    self.errors.append(CheckError(
                        "error",
                        f"{WAIT_FN}() : une durée en frames écrite en clair et "
                        f"positive — {WAIT_FN}(30). Pour attendre autre chose "
                        f"qu'une durée, {WAIT_UNTIL_FN}(condition)."))
            elif self._condition_is_frozen(arg):
                self.errors.append(CheckError(
                    "error",
                    f"{WAIT_UNTIL_FN}() dans '{fn.name}' : cette condition ne peut "
                    f"pas changer — elle ne lit que des valeurs qu'aucune ligne du "
                    f"script n'assigne. La séquence s'arrêterait là définitivement, "
                    f"sans rien signaler en jeu."))

    def _condition_is_frozen(self, e) -> bool:
        """La valeur de cette expression est-elle gravée pour toute la partie ?

        Vrai seulement quand on en est SÛR : littéraux, et noms de variables
        qu'aucune ligne du script n'assigne. Tout le reste — un appel d'API, un
        global, une propriété, une indexation — rend faux, parce qu'on ne sait
        pas ce que ça vaudra à la frame suivante. Le contrôle ferme la faute
        bête sans jamais accuser à tort (cf. ROADMAP v0.7.7)."""
        if isinstance(e, (ExprNumber, ExprBool, ExprNil, ExprString)):
            return True
        if isinstance(e, ExprName):
            return e.name not in self._assigned
        if isinstance(e, ExprUnop):
            return self._condition_is_frozen(e.operand)
        if isinstance(e, ExprBinop):
            return (self._condition_is_frozen(e.left)
                    and self._condition_is_frozen(e.right))
        return False

    # ── Statements ────────────────────────────────────────────────

    def _check_block(self, stmts: list, seq_top: bool = False):
        for s in stmts:
            self._check_stmt(s, seq_top)

    def _check_stmt(self, s, seq_top: bool = False):
        if isinstance(s, StmtCall):
            # Une attente n'est pas un appel : elle coupe la séquence en deux,
            # et le découpage n'a de sens qu'en LIGNE DROITE. `seq_top` est vrai
            # au seul endroit où elle est légale ; sa forme y a déjà été validée
            # par `_check_sequence_waits`, il n'y a plus rien à faire ici.
            if wait_call(s) is not None:
                if not seq_top:
                    self._refuse_misplaced_wait(s)
                return
            # `_check_expr` et non `_check_call_expr` : posé seul, un appel doit
            # descendre exactement comme en expression — ses arguments, et le
            # RÉCEPTEUR d'un `:méthode()` quand c'en est un autre
            # (`ui.get("Cusor"):show()` ne validait rien du tout).
            self._mark_spawn_stmt(s.call)
            self._check_expr(s.call)
        elif isinstance(s, StmtLocalAssign):
            self._check_array_decl(s.name, s.value)
            self._mark_spawn_stmt(s.value)
            self._check_expr(s.value)
        elif isinstance(s, StmtAssign):
            self._check_data_write(s.target)
            self._check_prop_write(s.target, s.value)
            self._check_const_write(s.target)
            self._check_global_write_value(s.target, s.value)
            if isinstance(s.target, ExprName):
                self._check_bare_name(s.target.name, ecrit=True)
            self._check_expr(s.target)     # `t[i] = v` : la CIBLE aussi s'indexe
            self._check_expr(s.value)
        elif isinstance(s, StmtIf):
            self._check_expr(s.cond)
            self._check_block(s.then)
            for _, b in s.elseifs:
                self._check_block(b)
            self._check_block(s.else_)
        elif isinstance(s, StmtWhile):
            self._check_expr(s.cond)
            self._check_block(s.body)
        elif isinstance(s, StmtForNum):
            self._check_for_step(s)
            self._check_expr(s.start)
            self._check_expr(s.stop)
            # ROADMAP v0.23 : une boucle BORNÉE laisse passer l'attente, parce
            # qu'elle se découpe sans continuation — un compteur de plus dans
            # l'état, et une tranche qui revient en arrière. `if` et `while`
            # gardent leur refus : eux demanderaient la transformation que la
            # v0.7.7 a chiffrée puis écartée, et son prix n'a pas changé.
            self._check_block(s.body, seq_top)
        elif isinstance(s, StmtUnsupported):
            # Un `Function` n'arrive ici que s'il est IMBRIQUÉ : au premier
            # niveau, c'est un handler, et `convert_chunk` le prend. Le nœud est
            # le même, seule sa place change — d'où le seul refus qui ne
            # s'indexe pas par le nom du nœud (cf. lua_subset.NESTED_FUNCTION).
            refusal = (lua_subset.NESTED_FUNCTION if s.node == "Function"
                       else lua_subset.refusal_for_node(s.node))
            self._refuse(refusal, s.node, s.line)

    def _refuse_misplaced_wait(self, s):
        """Une attente ailleurs qu'au premier niveau d'une séquence.

        Un seul message pour les deux fautes, parce que la réponse est la même
        des deux côtés : hors d'une séquence il n'y a rien à découper ; dans un
        `if` ou une boucle, il y aurait quelque chose à découper mais le
        `switch` émis ne saurait pas où reprendre. C'est la limite assumée du
        découpage en ligne droite, et le message nomme les deux issues."""
        kind, _arg = wait_call(s)
        self.errors.append(CheckError(
            "error",
            f"{kind}() s'écrit dans une séquence ({SEQUENCE_PREFIX}<nom>), au "
            f"premier niveau ou dans une boucle BORNÉE (`for i = 1, n`) — pas "
            f"dans un `if`, pas dans un `while`, pas dans un autre handler. "
            f"Une boucle bornée se découpe parce qu'on sait d'avance combien de "
            f"tours elle fait ; un `if` demanderait de se souvenir d'où "
            f"reprendre. Pour attendre sous condition, mettre la condition DANS "
            f"l'attente ({WAIT_UNTIL_FN}), ou déclarer une deuxième séquence et "
            f"la démarrer depuis le `if`."))

    def _check_for_step(self, s: StmtForNum):
        """Le SENS de la comparaison est décidé au build (`i <= stop` ou
        `i >= stop`), donc le pas doit être écrit en clair. Un pas calculé
        obligerait à tester son signe à chaque tour de boucle, dans un moteur
        qui ne teste rien ailleurs."""
        if s.step is not None and self._literal_int(s.step) is None:
            self.errors.append(CheckError(
                "error",
                "for … do : le pas doit être un nombre écrit en clair — c'est "
                "lui qui dit si la boucle monte ou descend, et ça se décide à "
                "la compilation."))

    def _refuse(self, refusal, node: str, line: int):
        """Dit un refus du sous-ensemble, situé sur sa ligne.

        `refusal` vaut None quand `lua_subset` ne classe pas ce nœud — ce que
        `validator._check_lua_subset` rend impossible au build. Le message de
        secours nomme quand même le nœud : mieux vaut un mot brut que le silence
        d'avant, qui faisait disparaître le code."""
        if refusal is None:
            message = (f"« {node} » n'est pas traduit par ce compilateur "
                       f"(nœud non classé dans lua_subset.py).")
        else:
            message = refusal.message
        where = f"ligne {line} : " if line else ""
        self.errors.append(CheckError("error", f"{where}{message}"))

    def _check_expr(self, e):
        """Descend dans TOUTE l'expression. Le parcours s'arrêtait aux appels
        posés seuls : ni les opérandes d'un calcul, ni les arguments d'un appel
        n'étaient visités, si bien qu'un appel imbriqué échappait à la
        validation. Une erreur de bornes ne peut pas se permettre le même
        angle mort — `t[9] + 1` doit se voir."""
        if e is None:
            return
        if isinstance(e, ExprUnsupported):
            self._refuse(lua_subset.refusal_for_node(e.node), e.node, e.line)
        elif isinstance(e, ExprIndexAt):
            self._array_chain(e)
            cur = e
            while isinstance(cur, ExprIndexAt):
                self._check_expr(cur.index)
                cur = cur.obj
            # `global.coffres[i]` — nom, tableau-ness et rang, tout d'un coup
            # (ROADMAP v0.20 pour les tableaux, chantier global/const pour
            # l'accès pointé). `_check_global_indexed` remplace ici ce
            # que la branche ExprIndex ci-dessous ferait pour un accès NU —
            # d'où le `is_global_index` qui l'empêche de repasser dessus.
            is_global_index = (isinstance(e.obj, ExprIndex)
                               and isinstance(e.obj.obj, ExprName)
                               and e.obj.obj.name == "global")
            if is_global_index:
                self._check_global_indexed(e.obj.field, e.index)
            # La BASE est déjà traitée : par `_array_chain` pour un tableau de
            # script ou une table de données, par `_check_global_indexed`
            # ci-dessus pour `global.nom[i]`. La revisiter dirait deux fois la
            # même erreur sur la même ligne.
            if (not is_global_index and not isinstance(cur, ExprName)
                    and self._data_table_ref(cur) is None):
                self._check_expr(cur)
        elif isinstance(e, (ExprInvoke, ExprCall)):
            self._check_call_expr(e)
            for a in e.args:
                self._check_expr(a)
            # Le RÉCEPTEUR d'un `:méthode()`, quand ce n'est pas un simple nom.
            # `ui.get("Cusor"):show()` ne validait rien du tout : ni le nom de
            # l'élément (que la même expression posée seule refuse pourtant),
            # ni la méthode. `_check_call_expr` s'arrête à un récepteur
            # `ExprName`, et personne ne descendait dans le reste.
            if isinstance(e, ExprInvoke) and not isinstance(e.obj, ExprName):
                self._check_expr(e.obj)
        elif isinstance(e, ExprBinop):
            self._check_expr(e.left)
            self._check_expr(e.right)
            if not self._check_prop_enum_compare(e):
                self._check_vec_binop(e)
        elif isinstance(e, ExprUnop):
            if e.op == "#":
                self._check_length(e.operand)
            self._check_expr(e.operand)
        elif isinstance(e, ExprTable):
            for v in e.items:
                self._check_expr(v)
        elif isinstance(e, ExprName):
            # La branche qui manquait : un nom nu ne rencontrait AUCUN cas et
            # traversait le checker sans un mot. Elle est atteinte aussi par le
            # `_check_expr(e.obj)` qui clôt la branche `ExprIndex` ci-dessous —
            # d'où les espaces de noms dans `_known_bare_name`.
            self._check_bare_name(e.name, ecrit=False)
        elif isinstance(e, ExprIndex):
            # `data.Objets` seul, ou la COLONNE de `data.Objets[i].prix` : les
            # deux formes sont un accès pointé, et c'est ce qu'il y a DESSOUS
            # qui les distingue.
            table = self._data_table_ref(e)
            if table is not None:
                self._check_data_table(table)
            elif isinstance(e.obj, ExprName) and e.obj.name == "global":
                self._check_global_scalar(e.field)
            elif isinstance(e.obj, ExprName) and e.obj.name == "const":
                self._check_const_scalar(e.field)
            elif (isinstance(e.obj, ExprName) and e.obj.name == "self"
                  and self.ctx.child_names is not None
                  and resolve_prop(e) is None
                  and e.field in self.ctx.child_names):
                pass          # `self.bras` — un enfant de cet acteur (v0.23)
            elif self._is_ui_element(e.obj):
                self._check_ui_element_field(e)
                self._check_expr(e.obj)      # les ARGUMENTS de ui.get(...)
                return
            elif isinstance(e.obj, ExprIndexAt):
                owner = self._data_table_ref(e.obj.obj)
                if owner is not None:
                    self._check_data_column(owner, e.field)
            else:
                prop = resolve_prop(e)
                if prop is not None:
                    # `self.position`, `camera.bound`… — un accès de propriété.
                    # Le champ qui suit est validé à l'étage d'au-dessus.
                    self._check_prop_read(prop)
                elif (isinstance(e.obj, ExprName) and e.obj.name == "self"
                      and self.ctx.child_names is not None):
                    # Ni une propriété, ni un enfant : le dire ici plutôt que de
                    # laisser gcc parler d'un champ de struct que l'auteur n'a
                    # jamais écrit (ROADMAP v0.23).
                    offre = ", ".join(self.ctx.child_names) or "aucun"
                    self.errors.append(CheckError(
                        "error",
                        f"self.{e.field} : ni une propriété d'acteur, ni un "
                        f"enfant de celui-ci. Enfants disponibles : {offre}."))
                else:
                    vt = infer_vec_type(e.obj, self._vec_types)
                    if vt is not None and e.field not in VEC_FIELDS[vt]:
                        label = e.obj.name if isinstance(e.obj, ExprName) else f"({vt})"
                        self.errors.append(CheckError(
                            "error",
                            f"{label}.{e.field} : {vt} n'a pas de champ '{e.field}' "
                            f"(seulement {', '.join(VEC_FIELDS[vt])})."))
            self._check_expr(e.obj)

    def _check_vec_binop(self, e: ExprBinop):
        """+ et - veulent le MÊME type vec2/vec3 des deux côtés ; * veut un
        vecteur d'un côté et un entier de l'autre. Tout le reste (comparer,
        diviser, mélanger vec2 et vec3…) n'a pas de sens ici — vec2/vec3 ne
        portent aucun opérateur en dehors de ces trois-là. Un rect, lui, n'est
        jamais un opérande de calcul."""
        lt = infer_vec_type(e.left, self._vec_types)
        rt = infer_vec_type(e.right, self._vec_types)
        if lt is None and rt is None:
            return
        # `None` = un SCALAIRE, pas un type fautif : le mélange vecteur/entier
        # est jugé plus bas (seul `*` l'accepte). Ce qu'on écarte ici, c'est un
        # composite qui ne calcule pas — un rect. Tester `not in ARITH_TYPES`
        # attrapait aussi None, donc annonçait « un None n'est pas un nombre »
        # sur `pos + 3` et rendait le dernier message de cette fonction mort.
        bad = next((t for t in (lt, rt) if t is not None and t not in ARITH_TYPES), None)
        if bad is not None:
            self.errors.append(CheckError(
                "error",
                f"un {bad} n'est pas un nombre : '{e.op}' n'est pas défini "
                f"dessus (seuls les vec2/vec3 et les entiers se calculent)."))
            return
        if e.op not in ("+", "-", "*"):
            self.errors.append(CheckError(
                "error",
                f"'{e.op}' n'est pas défini sur un vec2/vec3 — seuls +, - et "
                f"* (par un entier) le sont."))
            return
        if lt and rt:
            if e.op == "*":
                self.errors.append(CheckError(
                    "error",
                    "vec2/vec3 * vec2/vec3 n'existe pas — multiplier deux "
                    "vecteurs composante à composante n'a pas de sens ici. "
                    "Un entier d'un côté, oui."))
            elif lt != rt:
                self.errors.append(CheckError(
                    "error", f"{lt} {e.op} {rt} : les deux côtés doivent être du même type."))
        elif e.op != "*":
            self.errors.append(CheckError(
                "error",
                f"{e.op} entre un {lt or rt} et un scalaire n'existe pas — "
                f"seule la multiplication par un entier mélange les deux."))

    def _check_length(self, operand):
        """`#x` est une constante de compilation : elle n'a de valeur que sur un
        tableau dont ce script connaît la taille, ou sur une table du projet."""
        base = operand
        while isinstance(base, ExprIndexAt):
            base = base.obj
        if isinstance(base, ExprName) and base.name in self._arrays:
            return
        if self._data_table_ref(base) is not None:
            return          # `#data.Objets` — validée par ailleurs
        self.errors.append(CheckError(
            "error",
            "'#' ne s'applique qu'à un tableau déclaré dans ce script ou à une "
            "table de données — sa valeur est calculée au build, pas rangée en "
            "mémoire."))

    # ── Appels ────────────────────────────────────────────────────

    def _check_call_expr(self, e):
        if isinstance(e, ExprInvoke):
            # `récepteur:method(args)`. Les méthodes d'actor sont indexées sous
            # `self:` dans le catalogue, mais s'appellent sur n'importe quel
            # Actor* nommé (`other`, une variable de get_actor) — exactement
            # comme les PROPRIÉTÉS (cf. expr_types.resolve_prop). Ne valider que
            # `self` laissait tout le reste traverser sans un mot, alors que
            # `codegen._invoke` émettait quand même du C : `other:set_position(p)`
            # devenait `actor_set_position(other, p)`, qui compile et marche,
            # donc une API retirée qui survit tant qu'on ne l'écrit pas sur
            # `self`.
            if self._is_ui_element(e.obj):
                # Récepteur = `ui.get(...)`. `_check_call_expr` s'arrêtait à un
                # récepteur `ExprName`, donc la méthode n'était jamais jugée :
                # `ui.get("X"):bouge()` traversait, et `codegen._invoke` émettait
                # `actor_bouge(UIELEM_X)` — du C qui ne compile pas, sur une
                # ligne que l'auteur n'a pas écrite.
                if e.method not in self._UI_ELEMENT_METHODS:
                    self.errors.append(CheckError(
                        "warning",
                        f"ui.get(...):{e.method}() : une référence d'élément "
                        f"d'interface ne sait que "
                        f"{', '.join(':' + m + '()' for m in self._UI_ELEMENT_METHODS)}. "
                        f"Pour déplacer une image, ui.image_move(nom, dx, dy) ; "
                        f"pour changer son état, ui.image_set(nom, état)."))
            elif isinstance(e.obj, ExprName):
                receiver = e.obj.name
                # Un récepteur qui tient une RÉFÉRENCE (`local pas =
                # sfx.play(...)`) a son propre jeu de méthodes : la clé porte
                # alors le type de la référence et non `self`. Sans ça un
                # `pas:set_volume(80)` serait jugé — et refusé — comme une
                # méthode d'actor.
                ref = self._ref_types.get(receiver)
                key = f"{ref}:{e.method}" if ref else f"self:{e.method}"
                shown = f"{receiver}:{e.method}"
                api = RUNTIME_API.get(key)
                if api is None and ref:
                    self.errors.append(CheckError(
                        "error",
                        f"Méthode inconnue sur une référence d'effet : "
                        f"{shown}() — `{receiver}` tient ce que `sfx.play` a "
                        f"rendu, et les cinq méthodes sont :stop(), "
                        f":playing(), :set_volume(), :set_pitch() et "
                        f":set_panning()."))
                elif api is None:
                    # Une méthode RETIRÉE est une erreur guidée. Un nom
                    # simplement inconnu l'est AUSSI, contrairement à un
                    # `module.func()` : celui-là peut être un helper écrit par
                    # l'utilisateur, alors qu'un `:` ne peut désigner qu'une
                    # méthode d'actor, et il n'y en a pas d'autres que celles du
                    # catalogue. En avertissement, `codegen._invoke` inventait
                    # quand même `actor_<méthode>(récepteur, ...)` — qui tombait
                    # pile sur une fonction C existante pour toute ancienne
                    # orthographe (`self:set_sprite_rotation`), donc du code non
                    # documenté qui marche, ou sinon un `implicit declaration`
                    # au `make`. Les deux issues valent moins qu'un message ici.
                    removed = REMOVED_API.get(key)
                    if removed:
                        # Le message du catalogue parle de `self` (c'est là que
                        # la clé vit) ; sur un autre récepteur on le préfixe
                        # plutôt que de le réécrire — une propriété d'actor
                        # s'écrit sur n'importe quel acteur nommé.
                        if receiver != "self":
                            removed = (f"{shown}() : {removed} La même propriété "
                                       f"s'accède sur tout acteur nommé "
                                       f"({receiver}.<champ>).")
                        self.errors.append(CheckError("error", removed))
                    else:
                        self.errors.append(CheckError(
                            "error",
                            f"Méthode inconnue : {shown}() — un « : » ne peut "
                            f"désigner qu'une méthode d'actor du catalogue. "
                            f"Vérifiez l'orthographe, ou consultez l'API : "
                            f"l'ÉTAT s'écrit en propriété ({receiver}.champ), "
                            f"seule une ACTION est une méthode.",
                        ))
                else:
                    self._check_args(key, api, e.args, receiver=receiver)
                    if (key == "self:play_sfx" and receiver == "self"
                            and not self.ctx.sfx_component_name):
                        self.errors.append(CheckError(
                            "warning",
                            "self:play_sfx() : cet actor n'a pas de component SoundFX "
                            "(ou son champ Sfx est vide) — l'appel ne jouera rien.",
                        ))

        elif isinstance(e, ExprCall):
            # module.func(args) ou func(args)
            key = self._call_key(e.func)
            if key is None:
                return
            if key in WAIT_FNS:
                # Atteint seulement quand l'attente est écrite comme une
                # EXPRESSION (`local n = wait(3)`) : posée seule, `_check_stmt`
                # l'a déjà traitée. Une attente ne rend rien, elle coupe.
                self.errors.append(CheckError(
                    "error",
                    f"{key}() ne rend aucune valeur : c'est une attente, elle "
                    f"s'écrit seule sur sa ligne, au premier niveau d'une "
                    f"séquence ({SEQUENCE_PREFIX}<nom>)."))
                return
            if key in VEC_CONSTRUCTORS:
                # vec2(x, y) / vec3(x, y, z) : constructeur de langage, pas une
                # entrée RUNTIME_API — la seule chose à vérifier est le nombre
                # d'arguments, les arguments eux-mêmes le sont par `_check_expr`.
                dims = VEC_CONSTRUCTORS[key]
                if len(e.args) != dims:
                    self.errors.append(CheckError(
                        "error",
                        f"{key}() attend {dims} nombres ({', '.join(VEC_FIELDS[key])}), "
                        f"{len(e.args)} fourni(s)."))
                return
            # Les NOMS cités (scène, prefab, actor, global, constante) sont
            # vérifiés par leur domaine dans `_check_args`, comme tout autre
            # argument nommé — ces appels n'ont donc plus de chemin à part.
            # Ne restent ici que les contrôles qui portent sur autre chose que
            # le nom : le numéro d'emplacement d'un `save.*` (la valeur d'un
            # `global.nom = v` est vérifiée à l'ASSIGNATION, pas ici — cf.
            # `_check_global_write_value`, chantier global/const). Aucun `return` : le
            # reste des vérifications (nombre d'arguments compris) doit suivre.
            if key.startswith("save."):
                self._check_save(key, e.args)
                # pas de `return` : le nombre d'arguments reste à vérifier
            api = RUNTIME_API.get(key)
            if api is None:
                self._check_unknown_call(key, e.args)
            else:
                self._check_args(key, api, e.args)
            if key == "actor.spawn":
                self._check_spawn_table(e)

    def _check_unknown_call(self, key: str, args: list | None = None):
        """Un appel qui n'est pas dans le catalogue.

        Il était TOLÉRÉ, au motif que ce pouvait être un helper écrit par
        l'utilisateur. Le motif ne tenait pas : un script ne déclare pas de
        fonction (cf. lua_subset), et le codegen émettait l'appel tel quel — donc
        `math.floor(x)` partait en C avec son point, et la faute ne remontait
        qu'au `make`, sur la ligne générée. Le pendant, côté `.`, de ce que la
        v0.7.4 a fait pour le `:`."""
        helper = self._helpers.get(key)
        if helper is not None:
            expected = len(helper.params)
            # Le helper reçoit `self` automatiquement côté C : l'auteur ne
            # compte donc que les paramètres qu'il a écrits lui-même.
            if self._current_function == key:
                # Le graphe complet est aussi vérifié dans `_check_helpers` ;
                # ce diagnostic local rend le cas le plus courant immédiat.
                self.errors.append(CheckError(
                    "error", f"Récursion interdite : '{key}' ne peut pas s'appeler elle-même."))
            got = len(args or [])
            if got != expected:
                self.errors.append(CheckError(
                    "error", f"{key}() : {expected} argument(s) attendu(s), {got} fourni(s)."))
            return

        removed = REMOVED_API.get(key)
        if removed:
            self.errors.append(CheckError("error", removed))
            return
        if key == REQUIRE_FN:
            return                       # l'import d'un behavior, résolu au build
        if key in RUNTIME_PROPS:
            self.errors.append(CheckError(
                "error",
                f"{key} est une PROPRIÉTÉ, pas une fonction : elle se lit et "
                f"s'écrit comme un champ ({key} = …), sans parenthèses."))
            return

        module = key.split(".", 1)[0] if "." in key else ""
        if module == "self":
            self.errors.append(CheckError(
                "error",
                f"{key}() : une méthode d'actor s'appelle avec DEUX POINTS — "
                f"self:{key.split('.', 1)[1]}(…). Un point désigne une "
                f"propriété, qui elle ne s'appelle pas."))
            return
        if module in self._require_aliases:
            return                       # méthode d'un behavior importé
        if module in self._module_functions:
            offered = self._module_functions[module]
            if key.split(".", 1)[1] not in offered:
                self.errors.append(CheckError(
                    "error",
                    f"{key}() : ce module ne définit pas cette fonction "
                    f"({', '.join(offered) or 'aucune'})."))
            return

        refusal = lua_subset.refusal_for_call(key)
        if refusal is not None:
            self.errors.append(CheckError("error", refusal.message))
            return
        if module in API_MODULES:
            self.errors.append(CheckError(
                "error",
                lua_subset.unknown_member_message(
                    module, key.split(".", 1)[1], module_members(module))))
            return
        self.errors.append(CheckError("error", lua_subset.unknown_call_message(key)))

    def _call_key(self, func_expr) -> Optional[str]:
        """Reconstruit la clé API depuis l'expression de la fonction appelée."""
        if isinstance(func_expr, ExprName):
            return func_expr.name                    # ex: "get_actor", fonction helper user
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"   # ex: "sfx.play"
        return None

    def _check_args(self, key: str, api, args: list, receiver: str = "self"):
        """Vérifie le nombre d'arguments et les valeurs string si possible.

        `receiver` ne sert qu'aux domaines dont le nom appartient à l'objet
        APPELÉ et non au script courant (`_RECEIVER_DOMAINS`) : le contexte de
        build décrit l'acteur qui EXÉCUTE, il ne sait rien du sprite d'un
        `other`."""
        expected = len(api.params)
        got      = len(args)
        if api.variadic:
            if got < expected:
                self.errors.append(CheckError(
                    "error",
                    f"{key}() : au moins {expected} argument(s) attendu(s), {got} fourni(s).",
                ))
                return
        elif got != expected:
            self.errors.append(CheckError(
                "error",
                f"{key}() : {expected} argument(s) attendu(s), {got} fourni(s).",
            ))
            return

        for i, (param, arg) in enumerate(zip(api.params, args)):
            # Un NOMBRE là où une énumération matérielle est attendue : c'est
            # l'ancienne forme de l'API (`blend.set_layer("top", ...)` devenu
            # un entier nu), qui restait silencieuse — le codegen émettait
            # l'entier tel quel, donc du C valide au comportement arbitraire.
            # La rupture doit se voir ici, sur l'appel, et pas se découvrir en
            # jouant.
            if param.ptype in VEC_CONSTRUCTORS:
                vt = infer_vec_type(arg, self._vec_types)
                if vt != param.ptype:
                    self.errors.append(CheckError(
                        "error",
                        f"{key}() : l'argument « {param.name} » attend un {param.ptype}"
                        + (f", reçu un {vt}." if vt else " (nombre ou variable de ce type).")))
                continue

            if isinstance(arg, ExprNumber) and param.domain in HARDWARE_ENUMS:
                valid = HARDWARE_ENUMS[param.domain]
                self.errors.append(CheckError(
                    "error",
                    f"{key}() : l'argument « {param.name} » s'écrit par son nom, "
                    f"pas par un nombre ({arg.value}). Valeurs valides : "
                    f"{', '.join(sorted(valid))}.",
                ))
                continue

            if param.domain in _RECEIVER_DOMAINS and receiver != "self":
                # Le nom cité appartient au sprite du RÉCEPTEUR, que ce script
                # ne connaît pas — et le codegen, lui, le résout quand même
                # contre l'acteur courant (`anim_constant(ctx.actor_sym, ...)`),
                # produisant une constante crédible et fausse. Erreur ici,
                # plutôt qu'une animation d'un autre acteur jouée en silence.
                self.errors.append(CheckError(
                    "error",
                    f"{receiver}:{key.split(':')[1]}() : « {param.name} » nomme "
                    f"un élément du sprite de « {receiver} », et il est résolu "
                    f"contre celui de l'acteur qui exécute ce script — le C émis "
                    f"citerait la mauvaise ressource. Cet appel ne se fait que "
                    f"sur self."))
                continue

            if not isinstance(arg, ExprString):
                continue   # on ne valide les strings que si elles sont littérales

            check = _DOMAIN_CHECKS.get(param.domain)
            if check:
                check(self, key, arg.value, param, args)
            if key in ("text.draw", "text.draw_in") and param.domain == DOMAIN_TEXT:
                self._check_text_literal_locals(arg.value)

    def _check_text_literal_locals(self, text: str):
        """Valide les `$locale` d'un littéral `text.draw`.

        Une clé de table reste une donnée traduisible et ne peut pas dépendre
        d'une locale. Seul un littéral anonyme porte ce raccourci de HUD.
        """
        if self.ctx.text_keys is not None and text in self.ctx.text_keys:
            return
        from core.text_markup import parse, KIND_VALUE
        globals_ = set(self.ctx.global_names or [])
        constants = set(self.ctx.const_names or [])
        names = []
        for marker in parse(text).markers:
            if marker.kind != KIND_VALUE or marker.value in constants:
                continue
            if marker.value not in self._local_names and marker.value not in globals_:
                self.errors.append(CheckError(
                    "error", f'texte littéral : « ${marker.value} » n’est ni une locale, ni une globale, ni une constante.'))
            elif marker.value not in names:
                names.append(marker.value)
        if len(names) > 4:
            self.errors.append(CheckError(
                "error", "texte littéral : au plus 4 valeurs interpolées dans un littéral."))

    def _check_anim(self, call_key: str, name: str):
        if self.ctx.anim_names is not None and name not in self.ctx.anim_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : animation '{name}' introuvable dans le "
                f"sprite lié ({', '.join(self.ctx.anim_names) or 'aucune'}).",
            ))

    def _check_sfx(self, call_key: str, name: str):
        if self.ctx.sfx_names is not None and name not in self.ctx.sfx_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : sfx '{name}' introuvable dans le projet.",
            ))

    def _check_box_state(self, call_key: str, name: str, known):
        """Un état inconnu est une ERREUR : le codegen n'émettrait aucun appel,
        et la scène resterait muette sans que rien ne l'ait dit.

        La liste est celle de la boîte VISÉE par l'appel — un état de SoundBox
        ne répond pas à `jingle_box.set_state`, et le message le montre en
        n'énumérant que les états recevables."""
        if known is not None and name not in known:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : aucun état de ce nom dans cette boîte. "
                f"États disponibles : {', '.join(known) or 'aucun'}.",
            ))

    def _check_sound_trigger(self, call_key: str, name: str):
        """Un déclencheur qu'aucune arête n'écoute ne mène nulle part.

        AVERTISSEMENT et non erreur : écrire l'appel avant de dessiner l'arête
        est un ordre de travail légitime, et le jeu tourne — il ne change
        simplement pas de musique."""
        known = self.ctx.music_box_trigger_names
        if known is not None and name not in known:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : aucune transition musicale n'écoute ce "
                f"déclencheur — l'appel ne fera rien.",
            ))

    def _check_music(self, call_key: str, name: str):
        if self.ctx.music_names is not None and name not in self.ctx.music_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : music '{name}' introuvable dans le projet.",
            ))

    def _check_text(self, call_key: str, key: str, literal_ok: bool = False):
        """Une clé de texte inconnue est une ERREUR, pas un avertissement : le
        #define n'existerait pas et la compilation C échouerait de toute façon,
        avec un message bien moins clair.

        Sauf là où un littéral est permis (`text.draw`) : la chaîne résout vers
        une clé si elle en matche une, sinon elle EST le texte. Reste le piège
        de la faute de frappe — `villag_garde_01` s'afficherait tel quel au
        joueur. On ne le signale que si la chaîne a la FORME d'une clé : aucun
        vrai libellé ne ressemble à ça, donc la faute se voit sans faire de
        bruit sur les littéraux légitimes. Même compromis que le silence sur
        les crochets en prose, côté balisage."""
        if self.ctx.text_keys is None or key in self.ctx.text_keys:
            return
        if literal_ok:
            if _KEY_SHAPED.match(key):
                self.errors.append(CheckError(
                    "warning",
                    f"{call_key}('{key}') : aucune entrée de ce nom dans la "
                    f"table — le texte « {key} » sera affiché tel quel. Faute "
                    f"de frappe sur une clé, ou littéral volontaire ?",
                ))
            return
        near = ", ".join(sorted(self.ctx.text_keys)[:5]) or "aucun texte dans le projet"
        self.errors.append(CheckError(
            "error",
            f"{call_key}('{key}') : texte '{key}' introuvable dans la table du "
            f"projet ({near}).",
        ))

    def _check_font(self, call_key: str, name: str):
        if self.ctx.font_names is not None and name not in self.ctx.font_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : police '{name}' introuvable ou sans glyphes "
                f"({', '.join(self.ctx.font_names) or 'aucune police utilisable'}).",
            ))

    def _check_palette(self, call_key: str, name: str):
        """Une palette inconnue est une ERREUR : le nom devient un `#define
        PAL_*`, et sans lui le C généré ne compile pas — autant le dire ici,
        avec la liste, plutôt qu'au `make` sur un identifiant indéfini."""
        if self.ctx.palette_names is not None and name not in self.ctx.palette_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : palette '{name}' introuvable dans le "
                f"catalogue de couleurs "
                f"({', '.join(self.ctx.palette_names) or 'catalogue vide'}).",
            ))

    def _check_region(self, call_key: str, name: str):
        """Une zone inconnue est une ERREUR, pas un avertissement : le
        `#define REGION_*` n'existerait pas et la faute ne remonterait qu'en
        « implicit declaration » à la compilation C, qui ne dit pas quoi
        écrire. Même sévérité que pour une clé de texte, pour la même raison."""
        if self.ctx.region_names is not None and name not in self.ctx.region_names:
            near = ", ".join(sorted(self.ctx.region_names)[:5]) or                 "aucune zone dans le projet — dessines-en une dans le canvas de scène"
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : zone de texte '{name}' introuvable ({near}).",
            ))

    def _check_image(self, call_key: str, name: str):
        """Même sévérité et même raison que `_check_region` : sans l'élément, le
        `#define IMAGE_*` n'existe pas et la faute ne remonte qu'en « implicit
        declaration » à la compilation C. L'ÉTAT a son propre contrôle, qui a
        besoin de l'image pour savoir dans quel sprite chercher —
        cf. `_check_image_state`."""
        if self.ctx.image_names is not None and name not in self.ctx.image_names:
            near = ", ".join(sorted(self.ctx.image_names)[:5]) or                 "aucune image dans le projet — dessines-en une dans le canvas de scène"
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : image d'interface '{name}' introuvable ({near}).",
            ))

    def _check_ui_element(self, call_key: str, name: str):
        """Même sévérité et même raison que `_check_region`/`_check_image` :
        sans l'élément, le `#define UIELEM_*` n'existerait pas. Espace de noms
        plus large que les deux autres — tout élément d'une mise en page, pas
        seulement ce qui dessine (un container-groupe pur y figure aussi)."""
        if self.ctx.element_names is not None and name not in self.ctx.element_names:
            near = (", ".join(sorted(self.ctx.element_names)[:5])
                    or "aucun élément d'interface dans le projet — dessines-en un "
                       "dans le canvas de scène")
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : élément d'interface '{name}' introuvable ({near}).",
            ))

    def _check_image_state(self, call_key: str, state: str, args: list):
        """Le seul contrôle qui a besoin d'un AUTRE argument de l'appel.

        Un état n'existe pas dans l'absolu : il est nommé dans le SpriteAsset
        que porte cette image-là (`IMGST_{image}_{état}`, cf.
        api.image_state_constant). Deux images de sprites différents peuvent
        donc citer légitimement des états différents, et l'ensemble valide se
        lit sur l'image, jamais sur le projet entier — d'où l'accès à `args`.

        Erreur bloquante, comme partout dans cette famille : le `#define`
        n'existerait pas, et la faute ne remonterait qu'en « undeclared » sur la
        ligne générée."""
        if self.ctx.image_states is None:
            return
        image = args[0].value if args and isinstance(args[0], ExprString) else None
        if image is None:
            return                     # image non littérale : rien à quoi comparer
        etats = self.ctx.image_states.get(image)
        if etats is None:
            return                     # image inconnue : déjà dit par _check_image
        if state not in etats:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{image}', '{state}') : l'image '{image}' n'a pas "
                f"d'état '{state}'. États de son sprite : "
                f"{', '.join(etats) or 'aucun'}.",
            ))

    def _check_global(self, call_key: str, name: str):
        if self.ctx.global_names is not None and name not in self.ctx.global_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : variable globale '{name}' non déclarée dans le projet. "
                f"Ajoutez-la dans le conteneur Globals de l'éditeur.",
            ))

    def _check_global_write_value(self, target, value) -> None:
        """La VALEUR d'un `global.nom = v` — ce que la cible seule ne dit pas
        (chantier global/const, remplace la valeur d'un `global.set`).

        Seule la forme SCALAIRE est bornée ici : une case de tableau
        (`global.nom[i] = v`) ne l'a jamais été — même geste que le reste du
        langage, où un index calculé n'est pas plus contrôlé qu'ailleurs. Le
        nom, lui, est vérifié par `_check_global_scalar` (appelé sur cette
        même cible via `_check_expr(s.target)`) ; un nom inconnu n'a pas de
        type déclaré, donc `_check_global_range` se tait de lui-même."""
        if not (isinstance(target, ExprIndex) and isinstance(target.obj, ExprName)
                and target.obj.name == "global"):
            return
        if self.ctx.global_types is None:
            return
        self._check_global_range(target.field, self.ctx.global_types.get(target.field), value)

    @staticmethod
    def _literal_int(expr) -> Optional[int]:
        """Valeur entière d'un littéral connu à la compilation, sinon None
        (variable, expression calculée, etc. — pas de vérif possible)."""
        if isinstance(expr, ExprNumber):
            return expr.value
        if isinstance(expr, ExprUnop) and expr.op == "-" and isinstance(expr.operand, ExprNumber):
            return -expr.operand.value
        if isinstance(expr, ExprBool):
            return 1 if expr.value else 0
        return None

    def _check_global_range(self, name: str, typ: Optional[str], value_expr):
        rng = _TYPE_RANGES.get(typ)
        if rng is None:
            return
        val = self._literal_int(value_expr)
        if val is None:
            return
        lo, hi = rng
        if not (lo <= val <= hi):
            self.errors.append(CheckError(
                "warning",
                f"global.{name} = {val} : valeur hors plage pour le type '{typ}' "
                f"({lo} à {hi}) — sera tronquée/wrap au build (comportement natif GBA/C), "
                f"pas d'erreur mais probablement pas ce que tu voulais.",
            ))

    def _check_save(self, call_key: str, args: list):
        """Le numéro d'emplacement, quand il est écrit en clair.

        Un emplacement hors capacité ne casse rien au runtime — les fonctions
        rendent 0 — mais un `save.write(1)` dans un projet à un seul emplacement
        est une sauvegarde qui n'a jamais lieu et ne dit rien. Vérifié seulement
        sur un littéral : un slot calculé (un menu qui compte les emplacements)
        est un usage légitime que le moteur borne déjà."""
        if self.ctx.has_persistent is False:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}() : aucune variable globale n'est marquée "
                f"persistante dans ce projet — l'appel ne sauvera rien. Cocher "
                f"« persist » sur les variables à conserver."))
        slots = self.ctx.save_slots
        if args:
            val = self._literal_int(args[0])
            if val is not None and slots is not None and not (0 <= val < slots):
                self.errors.append(CheckError(
                    "error",
                    f"{call_key}({val}) : le projet déclare {slots} emplacement(s) "
                    f"de sauvegarde, numérotés de 0 à {slots - 1}."))
        # save.read('nom') cite une variable qui n'est pas cochée persist : le
        # nom existe (sinon `_check_global` l'aurait déjà signalé), mais aucun
        # fichier de sauvegarde ne la contiendra jamais — l'appel rendrait
        # toujours son défaut, un silence du même genre que `save.write` sans
        # variable persistante du tout.
        if call_key == "save.read" and len(args) >= 2 and isinstance(args[1], ExprString):
            name = args[1].value
            persist = self.ctx.global_persist
            if persist is not None and name in persist and not persist[name]:
                self.errors.append(CheckError(
                    "warning",
                    f"save.read(..., '{name}') : '{name}' n'est pas cochée "
                    f"« persist » — elle ne sera jamais dans une sauvegarde, "
                    f"l'appel rendra toujours sa valeur par défaut."))

    def _check_scene(self, call_key: str, name: str):
        """Une scène inconnue est une ERREUR, pas un avertissement : le
        #define SCENE_IDX_* n'existerait pas et gcc échouerait de toute façon,
        avec un message bien moins clair (même raison que _check_text).
        Rappel : on attend le nom de la SCÈNE, pas celui de son script."""
        if self.ctx.scene_names is not None and name not in self.ctx.scene_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : scène '{name}' introuvable dans le projet. "
                f"Scènes disponibles : {', '.join(self.ctx.scene_names) or 'aucune'}.",
            ))

    def _check_lang(self, call_key: str, name: str):
        """Même raison que la scène : sans cette langue, le #define LANG_*
        n'existe pas et gcc échoue sur la ligne générée. Une liste VIDE (projet
        monolingue) refuse tout code — il n'y a rien à choisir."""
        if self.ctx.lang_codes is not None and name not in self.ctx.lang_codes:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : langue '{name}' introuvable dans le "
                f"projet. Langues disponibles : "
                f"{', '.join(self.ctx.lang_codes) or 'aucune'}.",
            ))

    def _check_camera(self, call_key: str, name: str):
        """Même raison que la scène : sans caméra de ce nom, le #define CAM_*
        n'existe pas et gcc échoue sur la ligne générée. `(default)` n'est pas
        acceptée ici — la caméra par défaut n'a pas de nom, un script qui veut
        y revenir écrit camera.switch sur une caméra qu'il a nommée."""
        if self.ctx.camera_names is not None and name not in self.ctx.camera_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : caméra '{name}' introuvable dans le projet. "
                f"Caméras disponibles : {', '.join(self.ctx.camera_names) or 'aucune'}.",
            ))

    def _check_window(self, call_key: str, name: str):
        """DOMAIN_WIN_REGION (réglé le 2026-08-25) : "object"/"outside" sont
        deux mots-clés fixes, jamais disputés (cf. api.WIN_REGIONS) ; tout
        autre nom doit être un `WindowSlot` du projet — même raison qu'une
        caméra inconnue, le #define WIN_* n'existerait pas et gcc échouerait
        sur la ligne générée plutôt que sur sa cause."""
        if name.lower() in ("object", "outside"):
            return
        if self.ctx.window_names is not None and name not in self.ctx.window_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : ni \"object\"/\"outside\", ni une window "
                f"'{name}' du projet. Windows disponibles : "
                f"{', '.join(self.ctx.window_names) or 'aucune'}.",
            ))

    def _check_sequence(self, call_key: str, name: str):
        """Une séquence est locale à SON script : la liste de référence est
        celle qu'on vient de collecter, pas une table du projet. Erreur et non
        avertissement, même raison que partout ailleurs — le codegen émettrait
        une écriture dans une variable d'état qui n'existe pas."""
        if name not in self._sequences:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : ce script ne déclare pas de séquence "
                f"'{name}'. Une séquence est une fonction de premier niveau "
                f"`{SEQUENCE_PREFIX}{name}()`. Déclarées ici : "
                f"{', '.join(self._sequences) or 'aucune'}.",
            ))

    def _check_prefab(self, call_key: str, name: str):
        """Un prefab inconnu est une ERREUR, même raison que la scène : le
        codegen émet `spawn_<Nom>(...)` sans rien vérifier, donc la faute ne se
        voyait qu'à la compilation C, sur un « implicit declaration of
        function » qui pointe la ligne générée."""
        if self.ctx.prefab_names is not None and name not in self.ctx.prefab_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : prefab '{name}' introuvable dans le projet. "
                f"Prefabs disponibles : {', '.join(self.ctx.prefab_names) or 'aucun'}.",
            ))

    @staticmethod
    def _spawn_call_table(call):
        """La table d'exports d'un `actor.spawn(...)` (3ᵉ arg à clés), ou None."""
        args = getattr(call, "args", None) or []
        if (len(args) >= 3 and isinstance(args[2], ExprTable) and args[2].keys):
            return args[2]
        return None

    def _mark_spawn_stmt(self, call) -> None:
        """Note qu'un `actor.spawn(...)` occupe une position STATEMENT autorisée
        (début de ligne ou `local x = …`) — la table d'exports n'y est permise
        que là (tranche poolé D2)."""
        if (isinstance(call, ExprCall) and self._call_key(call.func) == "actor.spawn"
                and self._spawn_call_table(call) is not None):
            self._spawn_stmt_ok.add(id(call))

    def _check_spawn_table(self, e) -> None:
        """Valide la table facultative d'`actor.spawn("X", pos, { clé = valeur })` :
        position statement, entrées nommées, clés = exports réglables du prefab,
        valeurs littérales (tranche poolé D2)."""
        args = getattr(e, "args", None) or []
        if len(args) < 3:
            return                      # forme historique à deux arguments
        tbl = args[2]
        if not isinstance(tbl, ExprTable) or not tbl.keys:
            self.errors.append(CheckError(
                "error",
                "actor.spawn : le 3e argument est une table de valeurs "
                "« { vitesse = 8 } », pas un tableau."))
            return
        if id(e) not in self._spawn_stmt_ok:
            self.errors.append(CheckError(
                "error",
                "actor.spawn avec des valeurs ne s'écrit qu'en début de ligne ou "
                "« local x = actor.spawn(...) », pas au milieu d'une expression."))
        if not isinstance(args[0], ExprString):
            return                      # prefab non littéral — signalé par ailleurs
        prefab = args[0].value
        meta = (self.ctx.spawn_exports or {}).get(prefab) \
            if self.ctx.spawn_exports is not None else None
        for key, val in zip(tbl.keys, tbl.items):
            if key is None:
                self.errors.append(CheckError(
                    "error",
                    "actor.spawn : la table de valeurs n'accepte que des entrées "
                    "nommées, « { vitesse = 8 } »."))
                continue
            if meta is None:
                continue                # contexte relâché : on ne juge pas les clés
            if key not in meta:
                near = ", ".join(sorted(meta)) or "aucun"
                self.errors.append(CheckError(
                    "error",
                    f"actor.spawn(\"{prefab}\", …) : « {key} » n'est pas un export "
                    f"réglable de {prefab} ({near})."))
                continue
            if not isinstance(val, (ExprNumber, ExprBool, ExprString)):
                self.errors.append(CheckError(
                    "error",
                    f"actor.spawn : la valeur de « {key} » doit être un littéral "
                    f"(nombre, booléen, ou étiquette d'enum entre guillemets)."))

    def _check_actor(self, call_key: str, name: str):
        if self.ctx.actor_names is not None and name not in self.ctx.actor_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : aucun actor nommé '{name}' dans la scène "
                f"({', '.join(self.ctx.actor_names) or 'aucun'}).",
            ))

    def _check_tag(self, call_key: str, name: str):
        """L'IDENTITÉ d'un acteur : le nom d'un acteur de la scène ou d'un
        prefab poolé, les deux seuls à recevoir un `#define TAG_*`
        (cf. codegen/runtime_codegen/headers.py).

        Erreur bloquante, comme la scène ou le prefab : sans ce `#define`, le C
        généré cite un identifiant qui n'existe pas. À ne pas confondre avec
        `BOXTAG_*`, qui vient du champ libre `CollisionBoxComponent.tag` et
        n'est, lui, contraint par aucune liste."""
        connus = list(self.ctx.actor_names or []) + list(self.ctx.prefab_names or [])
        if self.ctx.actor_names is None and self.ctx.prefab_names is None:
            return
        if name not in connus:
            self.errors.append(CheckError(
                "error",
                f"{call_key} == '{name}' : aucun acteur ni prefab nommé "
                f"'{name}'. Identités connues : {', '.join(connus) or 'aucune'}.",
            ))

    def _check_key(self, call_key: str, name: str):
        actions = set(self.ctx.input_names or [])
        if name.lower() not in BuildContext.VALID_KEYS and name not in actions:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : input inconnu. Boutons : "
                f"{', '.join(sorted(BuildContext.VALID_KEYS))}. Actions : "
                f"{', '.join(sorted(actions)) or 'aucune'}.",
            ))

    def _check_hw_enum(self, call_key: str, name: str, domain: str):
        """Valeur d'une énumération matérielle FIXE (mode OAM, direction, mode
        et côté de mélange, décroissance). DOMAIN_WIN_REGION n'en fait PAS
        partie depuis le 2026-08-25 — cf. `_check_window`.

        L'ensemble valide vient de `HARDWARE_ENUMS`, donc du catalogue : cette
        fonction n'énumère rien elle-même et ne périme pas quand une valeur
        s'ajoute. Erreur bloquante et non avertissement — une valeur inconnue
        produirait du C qui ne compile pas, et la panne apparaîtrait sur la
        ligne générée au lieu de sa cause."""
        valid = HARDWARE_ENUMS.get(domain, {})
        if name.lower() not in valid:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : valeur '{name}' inconnue. "
                f"Valeurs valides : {', '.join(sorted(valid))}.",
            ))


# ─── Validation par domaine ───────────────────────────────────────
# Un domaine → comment vérifier que le nom cité existe. Table et non chaîne
# d'`elif` : elle se compare à `ALL_DOMAINS` au build
# (`validator._check_api_domains`). Un domaine sans entrée ici n'était validé
# par RIEN, en silence — l'erreur n'apparaissait qu'à la compilation C.
#
# Signature uniforme (checker, clé d'appel, valeur, param) : seul `_check_text`
# lit le `param`, mais une signature à géométrie variable redonnerait une table
# qu'on ne peut pas parcourir.
#
# Signature : (checker, clé d'appel, littéral, Param, args de l'appel). Le
# dernier n'intéresse qu'`image_state`, dont la validité dépend d'un AUTRE
# argument — mais il est passé à tous plutôt que réservé à celui-là : un
# contrôle qui aurait besoin du contexte de son appel ne devrait pas avoir à
# changer le contrat de la table pour l'obtenir.
_DOMAIN_CHECKS: dict = {
    DOMAIN_ANIM:    lambda c, key, val, p, a: c._check_anim(key, val),
    DOMAIN_SFX:     lambda c, key, val, p, a: c._check_sfx(key, val),
    DOMAIN_MUSIC:   lambda c, key, val, p, a: c._check_music(key, val),
    DOMAIN_KEY:     lambda c, key, val, p, a: c._check_key(key, val),
    DOMAIN_TEXT:    lambda c, key, val, p, a: c._check_text(key, val, p.literal_ok),
    DOMAIN_FONT:    lambda c, key, val, p, a: c._check_font(key, val),
    DOMAIN_PALETTE: lambda c, key, val, p, a: c._check_palette(key, val),
    DOMAIN_REGION:  lambda c, key, val, p, a: c._check_region(key, val),
    DOMAIN_IMAGE:   lambda c, key, val, p, a: c._check_image(key, val),
    DOMAIN_UI_ELEMENT: lambda c, key, val, p, a: c._check_ui_element(key, val),
    DOMAIN_UI_LIST:    lambda c, key, val, p, a: c._check_ui_list(key, val),
    DOMAIN_IMAGE_STATE: lambda c, key, val, p, a: c._check_image_state(key, val, a),
    DOMAIN_SCENE:   lambda c, key, val, p, a: c._check_scene(key, val),
    DOMAIN_LANG:    lambda c, key, val, p, a: c._check_lang(key, val),
    DOMAIN_CAMERA:  lambda c, key, val, p, a: c._check_camera(key, val),
    DOMAIN_SOUND_BOX_STATE:  lambda c, key, val, p, a: c._check_box_state(
        key, val, c.ctx.sound_box_state_names),
    DOMAIN_JINGLE_BOX_STATE: lambda c, key, val, p, a: c._check_box_state(
        key, val, c.ctx.jingle_box_state_names),
    DOMAIN_MUSIC_BOX_TRIGGER: lambda c, key, val, p, a: c._check_sound_trigger(key, val),
    DOMAIN_PREFAB:  lambda c, key, val, p, a: c._check_prefab(key, val),
    DOMAIN_ACTOR:   lambda c, key, val, p, a: c._check_actor(key, val),
    DOMAIN_TAG:     lambda c, key, val, p, a: c._check_tag(key, val),
    DOMAIN_GLOBAL:  lambda c, key, val, p, a: c._check_global(key, val),
    DOMAIN_SEQUENCE: lambda c, key, val, p, a: c._check_sequence(key, val),
    # Énumérations matérielles : une seule vérification pour les six, puisque
    # `HARDWARE_ENUMS` porte déjà l'ensemble valide de chacune. Un domaine
    # d'énumération ajouté à `api.py` est donc contrôlé sans qu'on touche ici.
    DOMAIN_OBJ_MODE:   lambda c, key, val, p, a: c._check_hw_enum(key, val, DOMAIN_OBJ_MODE),
    DOMAIN_DIRECTION:  lambda c, key, val, p, a: c._check_hw_enum(key, val, DOMAIN_DIRECTION),
    DOMAIN_WIN_REGION: lambda c, key, val, p, a: c._check_window(key, val),
    DOMAIN_BLEND_MODE: lambda c, key, val, p, a: c._check_hw_enum(key, val, DOMAIN_BLEND_MODE),
    DOMAIN_BLEND_SIDE: lambda c, key, val, p, a: c._check_hw_enum(key, val, DOMAIN_BLEND_SIDE),
    DOMAIN_EASE:       lambda c, key, val, p, a: c._check_hw_enum(key, val, DOMAIN_EASE),
}

# Cinq de ces domaines étaient auparavant vérifiés par un contrôle accroché au
# NOM DE L'APPEL (`scene.switch`, `get_actor`, `global.*`, `const.get`) : une
# seconde fonction prenant le même domaine n'aurait rien déclenché, et
# `actor.spawn` n'était vérifié nulle part. Ils sont maintenant vérifiés par
# leur domaine, comme les autres. Ce qui reste accroché à un appel précis dans
# `_check_call_expr` ne porte plus sur un nom : le numéro d'emplacement d'un
# `save.*` (`global.get`/`set` et `const.get` ont depuis quitté RUNTIME_API,
# remplacés par l'accès pointé — chantier global/const).

# Domaines connus mais délibérément NON validés — la troisième case du contrôle
# de couverture (`validator._check_api_domains`), qui distingue « traité
# ailleurs » de « oublié ». Vide aujourd'hui : `tag` l'occupait au motif que
# `TAG_*` serait un espace ouvert, ce qui était faux — l'espace est celui des
# acteurs de scène et des prefabs, parfaitement énumérable, et c'est `BOXTAG_*`
# (champ libre d'une box de collision) qui ne l'est pas. La case reste, elle
# n'est pas un oubli : le prochain domaine sans liste de référence s'y range.
_DOMAINS_UNCHECKED: frozenset = frozenset()


def _prop_label(receiver: str, p) -> str:
    """`self.tag` lu sur `other` s'annonce « other.tag ».

    Le catalogue range les propriétés d'actor sous la clé `self.<champ>` — une
    clé, pas une restriction (cf. expr_types.resolve_prop) — et un message qui
    reprendrait la clé telle quelle citerait à l'auteur une ligne qu'il n'a pas
    écrite."""
    return f"{receiver}.{p.lua_name.split('.', 1)[1]}"


def _domain_example(domain: Optional[str]) -> Optional[str]:
    """Une valeur à MONTRER dans un message, pour un domaine qui en a une liste
    fixe. Rien pour un espace de noms du projet : citer un acteur au hasard
    ferait passer un exemple pour une valeur attendue."""
    valides = HARDWARE_ENUMS.get(domain or "")
    return next(iter(valides)) if valides else None

# Domaines dont le nom appartient au RÉCEPTEUR de l'appel, pas au script qui
# l'écrit. `BuildContext` décrit l'acteur qui EXÉCUTE : ses animations, son
# SoundFX. Un `other:play_anim("walk")` cite donc une ressource que ce script
# ne peut ni vérifier ni résoudre — cf. `_check_args`.
_RECEIVER_DOMAINS: frozenset = frozenset({DOMAIN_ANIM})


def covered_domains() -> frozenset:
    """Domaines dont le checker sait quoi faire — validés, ou explicitement
    laissés de côté.

    Rendus par une fonction et non par les tables elles-mêmes : le contrôle
    (`validator._check_api_domains`) demande « ce domaine t'est-il connu ? »,
    pas la mécanique interne. Les tables restent privées."""
    return frozenset(_DOMAIN_CHECKS) | _DOMAINS_UNCHECKED


# ─── Point d'entrée public ────────────────────────────────────────

def check(script: LuaScript, ctx: BuildContext, check_event_names: bool = True) -> list[CheckError]:
    return Checker(ctx).check(script, check_event_names)
