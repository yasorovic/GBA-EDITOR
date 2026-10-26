"""editor/scripting/expr_types.py : de quel TYPE est une expression Lua.

Le sous-ensemble ne connaît que des scalaires, à deux
exceptions près, et ce module répond pour les deux : les VALEURS COMPOSÉES
(`vec2`, `vec3`, `rect`) et les RÉFÉRENCES rendues par un appel (`sfx.play`).
Il s'appelait `vec_types.py` tant qu'il n'y en avait qu'une.

Une valeur composée se COPIE, une référence DÉSIGNE un slot pris dans un pool
du matériel : les deux ne se confondent pas, mais checker.py et codegen.py se
posent la même question sur les deux, « quel type porte ce nom ? », et deux
modules auraient fini par y répondre différemment.

── Les valeurs composées ────────────────────────────────────────────────

`vec2(x, y)`, `vec3(x, y, z)` et `rect(x, y, w, h)` sont des CONSTRUCTEURS DE
LANGAGE, pas des entrées `RUNTIME_API` : ils ne traduisent pas un appel C, ils
déclarent une valeur composée (des entiers, jamais de virgule flottante : cf.
runtime/include/actor_types_static.h). checker.py (valider) et codegen.py
(émettre) ont chacun besoin de savoir si une expression EST un vec2/vec3/rect :
ce module est le seul endroit qui répond, pour que les deux ne divergent jamais
sur ce qu'est le type d'une expression.

Le module répond aussi à la deuxième famille de valeurs composées : les
PROPRIÉTÉS (`self.position`, `camera.bound`, `scene.size`…). Un accès pointé
`self.position` a bien un type, lu dans `RUNTIME_PROPS` (api.py) : c'est lui
qui fait que `local pos = self.position` donne une variable vec2, et que
`self.position.x` est un accès de champ valide.

Chaque consommateur garde sa propre table nom → type (`self._vec_types`),
remplie au fil de son propre parcours (une seule passe, de haut en bas :
même approximation, volontairement grossière, que `self._arrays` dans les
deux fichiers : un nom réutilisé avec deux types différents n'est pas
démêlé, il retombe sur `None`)."""

from __future__ import annotations
from typing import NamedTuple, Optional

from .parser import (ExprName, ExprIndex, ExprIndexAt, ExprCall, ExprInvoke, ExprBinop,
                     ExprString, DATA_NS, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile,
                     StmtForNum)

from .api import RUNTIME_API, RUNTIME_PROPS, REF_TYPES, REF_ACTOR, ApiProp, ref_member

# Champs valides par type : l'ordre est celui du constructeur.
VEC_FIELDS: dict[str, tuple[str, ...]] = {
    "vec2": ("x", "y"),
    "vec3": ("x", "y", "z"),
    "rect": ("x", "y", "w", "h"),
}

# Les types qui portent de l'ARITHMÉTIQUE (+ - *) : le C n'a pas d'opérateur
# sur les structs, et le checker/codegen traduisent ces opérateurs par les
# fonctions vec2_*/vec3_*. Un rect n'a rien à faire dans un calcul.
ARITH_TYPES: frozenset[str] = frozenset({"vec2", "vec3"})

# Constructeur → nombre d'arguments attendus. Dérivé de VEC_FIELDS : un seul
# endroit à tenir à jour pour ajouter un jour un autre type composé.
VEC_CONSTRUCTORS: dict[str, int] = {name: len(fields) for name, fields in VEC_FIELDS.items()}

# Fonctions de langage sur deux vecteurs : `dot(a, b)` rend un ENTIER (la somme des
# produits composante par composante). Comme les constructeurs, ce ne sont pas des
# entrées RUNTIME_API : leur type de retour est scalaire, le type des arguments
# décide de la fonction C (`vec2_dot` / `vec3_dot`).
VEC_FUNCTIONS: frozenset[str] = frozenset({"dot"})

# Constructeur → type C émis (littéral composé, pas un appel de fonction).
C_TYPES: dict[str, str] = {
    "vec2": "Vec2",
    "vec3": "Vec3",
    "rect": "Rect",
}


def _call_key(func_expr) -> Optional[str]:
    """Même règle que Checker._call_key / CodeGen._call_key : nom nu
    (`vec2`) ou `module.func` (`math.abs`). Ne rejoue pas la
    résolution complète (behaviors, cas spéciaux) : seul le nom compte ici,
    pour retrouver un `ret` dans RUNTIME_API ou un nom de constructeur."""
    if isinstance(func_expr, ExprName):
        return func_expr.name
    if isinstance(func_expr, ExprIndex) and isinstance(func_expr.obj, ExprName):
        return f"{func_expr.obj.name}.{func_expr.field}"
    return None


# Les noms qui précèdent un point sans désigner un acteur : les modules à propriétés propres (`camera`, `scene`) et les espaces de
# noms du projet (`global.<variable>`, `const.<constante>`, `data.<table>`, `screen.<mesure>`).
_NOT_ACTORS = frozenset({"camera", "scene", "global", "const", "data", "screen"})


def resolve_prop(expr, ref_types: Optional[dict[str, str]] = None,
                 ref_kinds: Optional[dict[str, str]] = None
                 ) -> Optional[tuple[str, ApiProp]]:
    """`self.position`, `camera.bound`, `scene.size`, ou une propriété d'ACTOR
    sur un récepteur quelconque (`other.velocity`, `paddle.position`) →
    `(récepteur, ApiProp)`. None si `expr` n'est pas un accès de propriété connu.

    Les propriétés d'actor vivent sous la clé `self.<champ>` dans
    RUNTIME_PROPS, mais s'accèdent sur n'importe quel `Actor*` nommé : un
    `other.velocity` est le même champ, avec un autre récepteur. Les propriétés
    de caméra/scène, elles, n'existent que sur `camera`/`scene`.

    Un récepteur qui tient une RÉFÉRENCE (`hb = self:collision_box("hitbox")`,
    d'où `hb.solid`) a les propriétés de son TYPE, clés `collision_box.solid` :
    `ref_types` (nom → type, tenu par le checker et le codegen) le dit. Et il n'a
    QUE celles-là : jamais le repli sur les champs d'actor, sans quoi `hb.tag`
    se lirait comme le tag de l'actor. Un type HÉRITE de son parent (`menu.visible`,
    d'un `list`, est une propriété de `ui_element`) : cf. `api.ref_member`.

    `ref_kinds` (nom d'élément → type, lu dans la mise en page) sert le récepteur
    chaîné `interface:get("Menu").index`, dont le type dépend du nom."""
    if not isinstance(expr, ExprIndex):
        return None
    if not isinstance(expr.obj, ExprName):
        return _resolve_chained_prop(expr, ref_kinds, ref_types)
    receiver, field = expr.obj.name, expr.field
    ref = (ref_types or {}).get(receiver)
    if ref is not None:
        found = ref_member(ref, field, ".")
        return (receiver, found[1]) if found is not None else None
    if receiver in REF_TYPES:
        # `actor.position` : `actor` est ici le MODULE (`actor:get`, `actor:spawn`), pas un acteur.
        # Les propriétés d'un type ne se lisent que sur une référence de ce type.
        return None
    prop = RUNTIME_PROPS.get(f"{receiver}.{field}")
    if prop is not None:
        return receiver, prop
    # Tout autre nom est un ACTEUR : `self`, `other`, un acteur de la scène. Ses champs sont
    # ceux du type `actor` (`_ACTOR_PROP_FIELDS`), sauf pour les espaces de noms qui n'en sont pas :
    # `global.frame`, `global.parent` sont des globales du projet, pas des propriétés d'un acteur.
    if receiver not in _NOT_ACTORS:
        prop = _ACTOR_PROP_FIELDS.get(field)
        if prop is not None:
            return receiver, prop
    return None


# Les propriétés d'acteur qui rendent un AUTRE acteur de la même instance (`a.parent`, `a.root`), ou nil : celles du catalogue
# qui déclarent `ref = acteur`. Une seule source, le catalogue.
ACTOR_NAV_PROPS = frozenset(name.rsplit(".", 1)[1] for name, prop in RUNTIME_PROPS.items()
                            if name.startswith(f"{REF_ACTOR}.") and prop.ref == REF_ACTOR)


def is_actor_call(expr, actor_names=frozenset()) -> bool:
    """`actor:get("X")` / `actor:spawn(...)` / `a.parent` / `a.root` : une expression qui REND un acteur. `a.parent` ne se
    reconnaît qu'à son récepteur : `self`, `other`, `who`, un nom que le script tient pour un acteur (`actor_names`), ou
    une autre expression qui rend un acteur ; `global.parent` ou `data.Table[1].parent` n'en sont pas."""
    if isinstance(expr, ExprIndex):
        if expr.field not in ACTOR_NAV_PROPS:
            return False
        obj = expr.obj
        if isinstance(obj, ExprName):
            return obj.name in ("self", "other", "who") or obj.name in actor_names
        return is_actor_call(obj, actor_names)
    return (isinstance(expr, ExprCall)
            and _call_key(expr.func) in ("actor.get", "actor.spawn"))


# Les exports qu'une AUTRE instance peut lire et écrire. Trois familles, trois façons de s'écrire :
# un SCALAIRE est un entier (un `bool` et un `enum` en sont, l'étiquette devient son rang) ; un
# COMPOSITE se donne par son constructeur (`vec2(1, 2)`) et se lit champ par champ ; un NOM
# (`actor_ref`, `scene_ref`, `sfx_ref`, `string`) s'écrit et se compare par son nom entre guillemets.
EXPORT_SCALARS = frozenset({"int", "float", "bool", "enum"})
EXPORT_COMPOSITES = frozenset({"vec2", "vec3", "rect"})
EXPORT_NAMED = frozenset({"string", "actor_ref", "scene_ref", "sfx_ref"})
EXPORT_ACCESSIBLE = EXPORT_SCALARS | EXPORT_COMPOSITES | EXPORT_NAMED


class ChildRef(NamedTuple):
    """Une partie nommée depuis une référence : `kind` ("spawn" : prefab, "get" : acteur posé), `owner` (le prefab ou l'acteur),
    `name` (la partie) et `spec` : son rang dans le groupe pour un prefab (int), l'expression C de son adresse pour un acteur
    posé (str, une constante du build)."""
    kind: str
    owner: str
    name: str
    spec: object


class RefEnv(dict):
    """L'environnement de typage : nom -> type de référence (`ref_types`), tenu par le checker et par le codegen. Il porte aussi
    `child_of`, le prédicat « cette expression est-elle une partie d'une instance connue (`boss.Canon`) ? » : seuls ces deux
    modules savent quel acteur une variable désigne, et c'est ce qui fait de `boss.Canon` un acteur pour `infer_ref_type`
    (donc pour ses propriétés et ses méthodes : `boss.Canon.position`, `boss.Canon:hide()`). None hors build."""
    child_of = None


def child_of_ref(expr, target_of, prefab_children, actor_children=None):
    """`boss.Canon` -> ChildRef quand `boss` désigne par un littéral une instance d'un PREFAB (une variable qui tient
    `actor:spawn("Boss")` ou `actor:get("Boss", i)`, ou l'appel lui-même) ou un acteur POSÉ de la scène (`actor:get("Boss")`)
    qui a une partie de ce nom. Rien pour `self` (ses enfants sont ceux du script courant) ni pour un acteur dont on ne connaît
    pas l'identité (`other`, `actor:get(i)`). `target_of(obj)` rend ("get" | "spawn", nom) ou None ; `prefab_children`,
    {prefab: {partie: rang}} ; `actor_children`, {acteur posé: {enfant: expression C}}."""
    if not isinstance(expr, ExprIndex) or isinstance(expr.obj, ExprName) and expr.obj.name in ("self", "other", "who"):
        return None
    target = target_of(expr.obj)
    if not target:
        return None
    kind, name = target
    if kind == "spawn":
        rank = ((prefab_children or {}).get(name) or {}).get(expr.field)
        return ChildRef("spawn", name, expr.field, rank) if rank else None
    ref = ((actor_children or {}).get(name) or {}).get(expr.field)
    return ChildRef("get", name, expr.field, ref) if ref else None


def literal_actor_target(expr):
    """("get" | "spawn", nom) quand `expr` est `actor:get("X")` / `actor:spawn("X", ...)` avec
    un littéral, sinon None. C'est l'identité de l'acteur désigné ; ses sprites et ses exports
    s'en déduisent."""
    if not (isinstance(expr, ExprCall) and expr.args and isinstance(expr.args[0], ExprString)):
        return None
    key = _call_key(expr.func)
    if key == "actor.get":
        # `actor:get("Bullet", i)` : une instance d'un MODÈLE (un prefab), pas l'acteur posé
        # qui porte ce nom.
        return ("spawn" if len(expr.args) >= 2 else "get", expr.args[0].value)
    if key == "actor.spawn":
        return ("spawn", expr.args[0].value)
    return None


def literal_actor_library(expr, actor_sprites, prefab_sprites):
    """Les sprites de l'acteur que `actor:get("X")` ou `actor:spawn("X")` désigne par un
    littéral, sinon None. Un prefab est un acteur : la bibliothèque est de même nature, seul
    change l'endroit où on la cherche (acteurs de la scène pour `get`, prefabs pour `spawn` et
    `get("X", i)`). Un nom calculé ou un indice (`actor:get(i)`) ne désigne rien que le Build
    connaisse."""
    target = literal_actor_target(expr)
    if target is None:
        return None
    kind, name = target
    return ((actor_sprites if kind == "get" else prefab_sprites) or {}).get(name)


def held_actor_refs(script) -> dict:
    """Les variables de TÊTE de script qui reçoivent un acteur (`last = actor:spawn(...)` dans
    un handler) : nom -> les expressions `actor:get/spawn` qu'on leur affecte. Ce sont elles dont
    la valeur survit à l'image, donc elles qui rangent une RÉFÉRENCE (cf. `actor_ref_make`) et non
    un pointeur. Une variable du même nom déclarée `local` dans un handler n'en est pas une."""
    top = {loc.name for loc in script.locals}
    declared: set = set()
    assigned: dict = {}
    holders: set = set()        # les noms que le script voit tenir un acteur : `other.root` ne se reconnaît qu'avec eux

    def walk(stmts):
        for s in stmts or []:
            if isinstance(s, StmtLocalAssign):
                declared.add(s.name)
                if is_actor_call(s.value, holders):
                    holders.add(s.name)
            elif (isinstance(s, StmtAssign) and isinstance(s.target, ExprName)
                  and is_actor_call(s.value, holders)):
                assigned.setdefault(s.target.name, []).append(s.value)
                holders.add(s.target.name)
            elif isinstance(s, StmtIf):
                walk(s.then)
                for _cond, body in s.elseifs:
                    walk(body)
                walk(s.else_)
            elif isinstance(s, (StmtWhile, StmtForNum)):
                walk(s.body)

    for fn in script.functions:
        walk(fn.body)
    return {name: values for name, values in assigned.items()
            if name in top and name not in declared}


def chain_label(obj) -> str:
    """Comment un récepteur CHAÎNÉ s'annonce dans un message : `actor:get(…)`,
    `collision_box(…)`. Ce que l'auteur a écrit ne tient pas dans une phrase, et
    les arguments n'aident pas à comprendre la faute."""
    cell = _data_cell(obj)
    if cell:
        return f"data.{cell[0]}[…].{cell[1]}"
    if isinstance(obj, ExprInvoke):
        return f"{obj.method}(…)"
    if isinstance(obj, ExprIndex):
        base = obj.obj.name if isinstance(obj.obj, ExprName) else chain_label(obj.obj)
        return f"{base}.{obj.field}"

    key = _call_key(obj.func) if isinstance(obj, ExprCall) else None
    return f"{key or '…'}(…)"


def _resolve_chained_prop(expr, ref_kinds=None, ref_types=None) -> Optional[tuple[str, ApiProp]]:
    """`actor:get("Foe").velocity`, `self:collision_box("hb").solid` : la même
    propriété que sur un nom, avec pour récepteur une EXPRESSION.

    Sans cette branche, `resolve_prop` rendait None faute d'un `ExprName`, le
    checker ne jugeait rien, et le codegen retombait sur un accès de champ brut
    (`runtime_get_actor(…).velocity`) que gcc refuse sur une ligne que l'auteur
    n'a pas écrite. Le récepteur rendu est un LIBELLÉ : le C se tire de
    l'expression elle-même, par `expr.obj`."""
    obj, field = expr.obj, expr.field
    if not isinstance(obj, (ExprCall, ExprInvoke, ExprIndex)):
        return None
    ref = infer_ref_type(obj, ref_kinds, ref_types)

    if ref is not None:
        found = ref_member(ref, field, ".")
        prop = found[1] if found is not None else None
    elif is_actor_call(obj):
        prop = _ACTOR_PROP_FIELDS.get(field)
    elif child_name(obj) is not None:
        prop = _ACTOR_PROP_FIELDS.get(field)
        return (f"self.{child_name(obj)}", prop) if prop is not None else None
    else:
        return None
    return (chain_label(obj), prop) if prop is not None else None


def child_name(expr) -> Optional[str]:
    """`self.Canon` → "Canon" : un accès à un champ de `self` qui n'est PAS une propriété
    d'acteur, donc l'enfant du propriétaire de ce nom (le checker juge s'il existe)."""
    if (isinstance(expr, ExprIndex) and isinstance(expr.obj, ExprName)
            and expr.obj.name == "self"
            and f"{REF_ACTOR}.{expr.field}" not in RUNTIME_PROPS
            and f"self.{expr.field}" not in RUNTIME_PROPS
            and expr.field not in _ACTOR_PROP_FIELDS):
        return expr.field
    return None


def _actor_prop_fields() -> dict[str, ApiProp]:
    """Champ (`position`, `velocity`, `rotation`, `scale`) → ApiProp, pour les
    propriétés d'actor consultées sur un récepteur autre que self."""
    out: dict[str, ApiProp] = {}
    for name, prop in RUNTIME_PROPS.items():
        if name.startswith(f"{REF_ACTOR}."):

            out[name.rsplit(".", 1)[1]] = prop
    return out


_ACTOR_PROP_FIELDS = _actor_prop_fields()


def infer_vec_type(expr, local_types: dict[str, Optional[str]],
                   ref_types: Optional[dict[str, str]] = None,
                   ref_kinds: Optional[dict[str, str]] = None) -> Optional[str]:
    """Rend "vec2" / "vec3" / "rect" si `expr` est de ce type, None sinon
    (scalaire, ou type que ce sous-ensemble ne suit pas : le défaut reste
    toujours scalaire, jamais composite par supposition)."""
    if expr is None:
        return None

    if isinstance(expr, ExprName):
        return local_types.get(expr.name)

    if isinstance(expr, ExprCall):
        key = _call_key(expr.func)
        if key in VEC_CONSTRUCTORS:
            return key
        # `get_axis` est scalaire à 1 argument, vec2 à 2 : le seul appel de
        # l'API dont le type suit le NOMBRE d'arguments plutôt qu'être fixe
        # dans le catalogue.
        if key == "input.get_axis":
            return "vec2" if len(expr.args) >= 2 else None
        api = RUNTIME_API.get(key) if key else None
        return api.ret if (api and api.ret in VEC_CONSTRUCTORS) else None

    if isinstance(expr, ExprInvoke):
        api = RUNTIME_API.get(f"{REF_ACTOR}:{expr.method}")
        return api.ret if (api and api.ret in VEC_CONSTRUCTORS) else None

    if isinstance(expr, ExprBinop) and expr.op in ("+", "-", "*", "/"):
        lt = infer_vec_type(expr.left, local_types, ref_types, ref_kinds)
        rt = infer_vec_type(expr.right, local_types, ref_types, ref_kinds)
        if lt and rt:
            return lt if lt == rt else None
        return lt or rt   # un seul côté composite (l'autre un scalaire, cf. * ) : ce type-là

    if isinstance(expr, ExprIndex):
        prop = resolve_prop(expr, ref_types, ref_kinds)
        if prop is not None:
            _, p = prop
            return p.ptype if (p.ptype in VEC_CONSTRUCTORS) else None

    return None


# ─── Les références ───────────────────────────────────────────────
# Ce qu'un appel REND et sur quoi s'écrivent des méthodes : un slot pris dans
# un pool dimensionné par le matériel. Le catalogue déclare le type (`ret`), ce
# module dit si une expression en porte un. Ce que le C écrit pour la tenir, comme
# tout le reste d'un type, se déclare dans `api.REF_TYPE_TABLE` : une seule fois.


def data_column_key(table: str, column: str) -> str:
    """La clé, dans `ref_kinds`, du TYPE de référence que stocke une colonne de données :
    `data_column_key("Dialogue", "boite")` → `"data.Dialogue.boite"`. `ref_kinds` dit ce que rend
    une chose NOMMÉE du projet : un élément d'interface par son nom, une cellule de table par
    son chemin : sans un second paramètre à faire traverser tout le pipeline."""
    return f"{DATA_NS}.{table}.{column}"


def _data_cell(expr) -> Optional[tuple[str, str]]:
    """`data.Dialogue[i].boite` → `("Dialogue", "boite")`, sinon None."""
    if not (isinstance(expr, ExprIndex) and isinstance(expr.obj, ExprIndexAt)):
        return None
    row = expr.obj.obj
    if (isinstance(row, ExprIndex) and isinstance(row.obj, ExprName)
            and row.obj.name == DATA_NS):
        return row.field, expr.field
    return None


def _is_actor_receiver(obj, ref_kinds, ref_types) -> bool:
    """Le récepteur d'un `.parent` / `.root` est-il un acteur ? `self`, `other`, `who`, une variable typée acteur, ou une expression
    qui en rend un (`actor:get("Boss")`, `boss.Canon`, `other.parent`)."""
    if isinstance(obj, ExprName):
        return obj.name in ("self", "other", "who") or (ref_types or {}).get(obj.name) == REF_ACTOR
    return infer_ref_type(obj, ref_kinds, ref_types) == REF_ACTOR


def infer_ref_type(expr, ref_kinds: Optional[dict[str, str]] = None,
                   ref_types: Optional[dict[str, str]] = None) -> Optional[str]:
    """Le type de référence que rend `expr`, ou None.

    Un seul producteur possible : un appel du catalogue dont le `ret` est un
    type de référence. Une référence ne se calcule pas : on ne l'additionne
    pas, on n'en prend pas de champ :, donc il n'y a rien d'autre à parcourir,
    contrairement aux valeurs composées.

    Un appel dont le type dépend du NOM qu'il cite (`interface.get`, cf.
    `ApiFunc.ret_by_name`) le lit dans `ref_kinds` : la nature de l'élément, connue
    de la mise en page. Sans ce dictionnaire (appel hors build), c'est le `ret`
    déclaré, le type de base.
    """
    if isinstance(expr, ExprIndex):
        # Une cellule de table de données d'une colonne de RÉFÉRENCE (`region`, `image`) : son
        # entier est l'index de la zone ou de l'image, donc exactement le handle du type.
        cell = _data_cell(expr)
        if cell:
            return (ref_kinds or {}).get(data_column_key(*cell))
        if expr.field in ACTOR_NAV_PROPS and _is_actor_receiver(expr.obj, ref_kinds, ref_types):
            return REF_ACTOR                                 # `other.parent`, `boss.Canon.root`
        child_of = getattr(ref_types, "child_of", None)
        return REF_ACTOR if child_of is not None and child_of(expr) else None
    if isinstance(expr, ExprInvoke):
        # Une méthode qui s'écrit sur une RÉFÉRENCE peut en rendre une autre :
        # `interface:get("Menu"):row(1)` est une zone de texte, `menu:row(1)` aussi quand
        # `menu` tient une liste (`ref_types`). Le type du récepteur dit dans quel jeu de
        # méthodes chercher : celui d'un ancêtre compris.
        receiver = ((ref_types or {}).get(expr.obj.name) if isinstance(expr.obj, ExprName)
                    else infer_ref_type(expr.obj, ref_kinds, ref_types))
        if receiver:
            found = ref_member(receiver, expr.method, ":")
            return found[1].ret if (found and found[1].ret in REF_TYPES) else None
        # `self:collision_box("hitbox")` : un constructeur de référence qui
        # s'écrit comme une méthode d'actor, faute de module à qui le rattacher.
        api = RUNTIME_API.get(f"{REF_ACTOR}:{expr.method}")
        return api.ret if (api and api.ret in REF_TYPES) else None
    if not isinstance(expr, ExprCall):
        return None
    api = RUNTIME_API.get(_call_key(expr.func) or "")
    if not (api and api.ret in REF_TYPES):
        return None
    if api.ret_by_name and ref_kinds and expr.args and isinstance(expr.args[0], ExprString):
        return ref_kinds.get(expr.args[0].value, api.ret)
    return api.ret


def element_of(expr, ref_elements: Optional[dict[str, Optional[str]]] = None) -> Optional[str]:
    """Le NOM de l'élément d'interface qu'`expr` désigne, quand le build le connaît :
    `interface:get("Heart")` lui-même, ou un `local` qui en tient un (`ref_elements`,
    tenu par le checker et le codegen comme `ref_types`). None sinon : un local
    réaffecté, un paramètre, un calcul.

    Ce que ce nom débloque : l'état d'une image se nomme dans le sprite de CETTE image
    (`heart.state = "vide"`), et ce nom ne se lit sur aucun autre argument."""
    if isinstance(expr, ExprName):
        return (ref_elements or {}).get(expr.name)
    if (isinstance(expr, ExprCall) and _call_key(expr.func) == "interface.get"
            and expr.args and isinstance(expr.args[0], ExprString)):
        return expr.args[0].value
    return None
