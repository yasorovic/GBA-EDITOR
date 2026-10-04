"""
editor/scripting/parser.py — Parse un script Lua et retourne un AST normalisé.

On utilise luaparser (luaparser.ast) pour obtenir l'AST brut, puis on
l'enveloppe dans nos propres noeuds (ScriptAST) pour isoler le reste
du pipeline de la lib externe. Si luaparser change d'API, seul ce
fichier doit changer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Import luaparser ──────────────────────────────────────────────
try:
    from luaparser import ast as _lua_ast
    from luaparser import astnodes as _lua_nodes
    _LUAPARSER_OK = True
except ImportError:
    _LUAPARSER_OK = False


# ─── Noeuds AST normalisés ─────────────────────────────────────────
# On ne ré-exporte pas les noeuds luaparser ; les autres modules
# ne dépendent que de ces classes.

@dataclass
class LuaScript:
    """Racine : liste de déclarations top-level."""
    functions:  list[LuaFunction] = field(default_factory=list)   # handlers d'event
    locals:     list[LuaLocal]    = field(default_factory=list)    # local x = val
    # Table de module d'un behavior : le `M` de `local M = {}` … `function
    # M.update(actor)` … `return M`. C'est une FORME, pas une donnée — elle ne
    # produit rien en C, les fonctions étant inlinées une à une
    # (codegen._emit_inlined_behaviors). Sans ce repérage, `{}` était lu comme
    # un tableau vide : le template de behavior qu'écrit l'éditeur lui-même
    # récoltait « un tableau vide n'a pas de taille », et le codegen émettait un
    # `static int M = 0;` que personne ne lit.
    module_names: list[str]       = field(default_factory=list)
    # Statements written at the top level that are neither a `local`, an
    # `exports = {...}` table, a function nor the `return M` of a module:
    # (luaparser node name, line). They are CARRIED, not dropped: the checker
    # refuses them, so that `local x = 0; ADFZ = 5` cannot be swallowed.
    stray_statements: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class LuaFunction:
    name:   str                           # "on_start", "on_collide"…
    params: list[str]                     # ["other"] pour on_collide, [] pour on_start
    body:   list[Any]                     # liste de noeuds Statement


@dataclass
class LuaLocal:
    name:    str
    value:   Any      # noeud Expr (peut être None si pas initialisé)
    # Type déclaré dans la table `exports` ("int", "string", "actor_ref"…) —
    # None pour un vrai `local`, dont le type C est alors déduit de la valeur.
    # Cf. scripting/exports_parser.KNOWN_TYPES et codegen._local_decl.
    export_type: Optional[str] = None
    # Choix d'un export `enum` (étiquettes, dans l'ordre déclaré) — l'index d'une
    # étiquette est sa valeur entière au runtime. Vide pour tout autre type. Capté
    # ICI, avec le reste de la déclaration, pour que la résolution des valeurs
    # d'instance (lua_compiler._export_inits) reste sur le MÊME arbre que le
    # codegen — pas un second parseur (cf. chantier « Les exports de script »).
    export_values: list = field(default_factory=list)


# ── Statements ────────────────────────────────────────────────────

@dataclass
class StmtCall:
    """Appel de fonction / méthode."""
    call: Any   # noeud Expr (ExprInvoke, ExprCall…)
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtAssign:
    target: Any   # ExprName ou ExprIndex
    value:  Any
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtLocalAssign:
    name:  str
    value: Any
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtIf:
    cond:     Any
    then:     list[Any]
    elseifs:  list[tuple[Any, list[Any]]] = field(default_factory=list)
    else_:    list[Any]                   = field(default_factory=list)
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtWhile:
    cond: Any
    body: list[Any]
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtReturn:
    values: list[Any]
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtForNum:
    var:   str
    start: Any
    stop:  Any
    step:  Any          # peut être None (défaut 1)
    body:  list[Any]
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtBreak:
    line: int = field(default=0, compare=False)   # ligne du script (0 = inconnue)


@dataclass
class StmtUnsupported:
    """Un statement que ce sous-ensemble ne traduit pas — `repeat`, `for … in`,
    `goto`, une fonction imbriquée…

    Il est PORTÉ et non jeté. Le rendre `None` (« noeud non géré, silencieux en
    v1 ») faisait disparaître le bloc du jeu sans un mot : ni erreur de checker,
    ni avertissement gcc, juste un corps de boucle qui n'existe plus. Ce que
    l'auteur écrit se retrouve donc dans l'AST, et c'est le checker qui refuse —
    avec la phrase de `lua_subset`. Le parser décrit, il ne juge pas."""
    node: str      # nom du noeud luaparser ("Repeat", "Forin", "Function"…)
    line: int


# ── Expressions ───────────────────────────────────────────────────

@dataclass
class ExprNumber:
    value: int


@dataclass
class ExprBool:
    value: bool


@dataclass
class ExprNil:
    pass


@dataclass
class ExprString:
    value: str


@dataclass
class ExprName:
    name: str


@dataclass
class ExprIndex:
    """module.champ — notation POINTÉE uniquement.

    L'indexation par crochets a son propre noeud (`ExprIndexAt`) : les deux
    s'écrivent pareil en Lua mais ne veulent pas dire la même chose ici. Un
    champ est un NOM connu à l'écriture (`screen.width`, `data.Objets`), un
    index est une EXPRESSION calculée."""
    obj:   Any
    field: str


@dataclass
class ExprIndexAt:
    """t[i] — indexation par une expression, notation CROCHETS.

    Deux niveaux imbriqués pour un tableau à deux dimensions : `g[y][x]` est
    `ExprIndexAt(ExprIndexAt(g, y), x)`, exactement comme le C qu'il produit."""
    obj:   Any
    index: Any


@dataclass
class ExprTable:
    """{1, 2, 3} — constructeur de tableau.

    `items` porte des ExprTable quand le tableau est à deux dimensions
    (`{{1,2},{3,4}}`). `has_keys` retient qu'une entrée était NOMMÉE
    (`{a = 1}`) : c'est un enregistrement et non un tableau, donc une erreur —
    mais elle se dit dans le checker, pas ici. Le parser décrit ce qui est
    écrit, il ne juge pas."""
    items:    list[Any] = field(default_factory=list)
    has_keys: bool      = False
    # Nom de la clé de chaque entrée, ou None si positionnelle — parallèle à
    # `items`. Retenu pour la table d'exports d'`actor:spawn("X", pos, {k=v})`
    # (chantier « Les exports de script », tranche poolé) ; les tableaux ordinaires
    # n'ont que des entrées positionnelles (keys = [None, …]).
    keys:     list[Any] = field(default_factory=list)


@dataclass
class ExprInvoke:
    """self:method(args)"""
    obj:    Any          # ExprName("self") en pratique
    method: str
    args:   list[Any]


@dataclass
class ExprCall:
    """func(args), `module:func(args)` ou `math.func(args)`.

    Un appel de module s'écrit avec « : » (`input:pressed("A")`) : le parseur le ramène à
    la forme `ExprIndex(ExprName(module), func)`, la même que l'ancien point, pour que
    checker, codegen et refactor n'aient qu'une forme à traduire. `dotted` retient que
    l'auteur a écrit un POINT sur un module qui s'appelle avec « : » — le checker le refuse
    en disant quoi écrire."""
    func: Any            # ExprName ou ExprIndex
    args: list[Any]
    dotted: bool = False


@dataclass
class ExprBinop:
    op:    str           # "+", "-", "*", "/", "%", "==", "~=", "<", "<=", ">", ">=", "and", "or"
    left:  Any
    right: Any


@dataclass
class ExprUnop:
    op:    str           # "-", "not"
    operand: Any


@dataclass
class ExprUnsupported:
    """Une expression que ce sous-ensemble ne traduit pas — `..`, `^`, `//`,
    une fonction anonyme, un opérateur binaire…

    Même rôle que `StmtUnsupported` côté expressions. Elle remplace le
    `ExprName("__unsupported_<Type>")` d'avant, qui partait tel quel dans le C
    et n'échouait qu'au `make`, sur un identifiant inconnu, à la ligne
    générée."""
    node: str      # nom du noeud luaparser ("Concat", "ExpoOp"…)
    line: int


# ─── Erreur de parse ───────────────────────────────────────────────

class LuaParseError(Exception):
    """Une faute de SYNTAXE — le seul refus qui précède le checker.

    Porte sa `line` quand on a su la retrouver (cf. `_syntax_message`), pour
    que le build la cite comme le reste (`Titre.lua:2 : …`) au lieu de nommer
    le fichier entier."""

    def __init__(self, message: str, line: Optional[int] = None):
        super().__init__(message)
        self.line = line


# ─── Opérateurs traduits ──────────────────────────────────────────
# Deux tables, et elles font LISTE : un opérateur qui n'y est pas n'est pas dans
# le sous-ensemble (cf. lua_subset.REFUSED, qui porte la phrase correspondante).
# Les noms sont ceux de luaparser, capitale finale de `ULengthOP` comprise.
# Le C est déjà écrit ici (`and` → `&&`) : l'AST porte l'opérateur cible, comme
# depuis l'origine.

_BINOP_MAP: dict[str, str] = {
    "AddOp": "+", "SubOp": "-", "MultOp": "*", "FloatDivOp": "/",
    "ModOp": "%", "EqToOp": "==", "NotEqToOp": "!=", "LessThanOp": "<",
    "GreaterThanOp": ">", "LessOrEqThanOp": "<=", "GreaterOrEqThanOp": ">=",
    "AndLoOp": "&&", "OrLoOp": "||",
}

_UNOP_MAP: dict[str, str] = {
    "UMinusOp": "-", "ULNotOp": "not", "ULengthOP": "#",
}


# ─── Convertisseur AST luaparser → nos noeuds ─────────────────────

class _Converter:
    """Traverse l'AST luaparser et produit nos noeuds."""

    def __init__(self, source: str = ""):
        # Le source, pour situer un noeud refusé sur SA ligne. Il est recompté
        # depuis l'offset et non lu dans `node.line` : celui de luaparser lève
        # dès que le noeud n'a pas conservé ses tokens (même contrainte que
        # `refactor.iter_call_sites`, qui compte déjà les sauts de ligne).
        self._source = source

    def _line(self, node) -> int:
        """Ligne 1-indexée du noeud, ou 0 si son offset est inconnu."""
        off = getattr(node, "start_char", None)
        if off is None or not self._source:
            return 0
        return self._source.count("\n", 0, off) + 1

    def convert_chunk(self, node) -> LuaScript:
        block = node.body
        functions = []
        locals_   = []
        stray     = []

        for stmt in block.body:
            t = type(stmt).__name__
            if t in ("SemiColon", "Return"):
                continue             # `;` is a separator; `return M` closes a module
            if t == "Function":
                fn = self._func(stmt)
                functions.append(fn)
            elif t == "LocalAssign":
                for name, val in self._local_pairs(stmt.targets, stmt.values):
                    locals_.append(LuaLocal(name=name, value=val))
            elif t == "Assign" and not (
                    getattr(getattr(stmt, "targets", [None])[0], "id", None) == "exports"):
                stray.append((t, self._line(stmt)))
            elif t == "Assign":
                # exports = { key = { default=N, ... }, ... }  → variables C statiques
                targets = stmt.targets if hasattr(stmt, "targets") else []
                values  = stmt.values  if hasattr(stmt, "values")  else []
                if (targets and getattr(targets[0], "id", None) == "exports"
                        and values and type(values[0]).__name__ == "Table"):
                    for field_node in values[0].fields:
                        key = getattr(field_node.key, "id", None)
                        if key is None:
                            continue
                        # chercher default ET type dans la sous-table : le type
                        # déclaré pilote le type C émis (une string exportée ne
                        # doit pas devenir un `int`), cf. codegen._local_decl.
                        default_val = None
                        decl_type   = None
                        enum_values: list = []
                        if type(field_node.value).__name__ == "Table":
                            for sub in field_node.value.fields:
                                sub_key = getattr(sub.key, "id", None)
                                if sub_key == "default" and sub.value is not None:
                                    default_val = self._expr(sub.value)
                                elif sub_key == "type" and sub.value is not None:
                                    typ_expr = self._expr(sub.value)
                                    if isinstance(typ_expr, ExprString):
                                        decl_type = typ_expr.value
                                elif sub_key == "values" and \
                                        type(sub.value).__name__ == "Table":
                                    # Les étiquettes d'un enum, dans l'ordre : leur
                                    # index EST leur valeur entière au runtime.
                                    for v in sub.value.fields:
                                        lbl = self._expr(v.value)
                                        if isinstance(lbl, ExprString):
                                            enum_values.append(lbl.value)
                        locals_.append(LuaLocal(name=key, value=default_val,
                                                export_type=decl_type,
                                                export_values=enum_values))
            else:
                stray.append((t, self._line(stmt)))

        # Le nom d'un module de behavior se lit sur les DEUX bouts : `local M =
        # {}` d'un côté, `function M.update(…)` de l'autre. Exiger les deux
        # évite de prendre pour un module un `local t = {}` que l'auteur voulait
        # tableau — celui-là reste refusé, avec la phrase qui dit `array(n)`.
        qualifiers = {fn.name.split(".", 1)[0] for fn in functions if "." in fn.name}
        modules = [loc.name for loc in locals_
                   if loc.name in qualifiers
                   and isinstance(loc.value, ExprTable)
                   and not loc.value.items and not loc.value.has_keys]

        return LuaScript(
            functions    = functions,
            locals       = [loc for loc in locals_ if loc.name not in modules],
            module_names = modules,
            stray_statements = stray,
        )

    def _func(self, node) -> LuaFunction:
        if hasattr(node.name, "id"):
            name = node.name.id                                    # simple: on_update
        elif hasattr(node.name, "idx") and node.name.idx is not None:
            name = f"{node.name.value.id}.{node.name.idx.id}"     # M.update
        else:
            name = str(node.name)
        params = [a.id for a in (node.args or [])]
        body   = self._block(node.body, set(params))
        return LuaFunction(name=name, params=params, body=body)

    def _block(self, block, local_scope: set[str]) -> list:
        stmts = []
        for s in (block.body if block else []):
            st = self._stmt(s, local_scope)
            if st is None:
                continue
            # La ligne du script suit le statement jusqu'au C (`#line`, cf. codegen) : une
            # erreur de gcc cite alors le script, pas le `.c` généré.
            line = self._line(s)
            for one in (st if isinstance(st, list) else [st]):
                if not getattr(one, "line", 0):
                    one.line = line
            # Un `local a, b, c` s'étend en PLUSIEURS statements : `_stmt` rend
            # alors une liste, aplatie ici. Tout l'aval (checker, codegen) ne voit
            # que des `local` mono-nom, comme avant ce correctif.
            stmts.extend(st) if isinstance(st, list) else stmts.append(st)
        return stmts

    def _local_pairs(self, targets, values) -> list:
        """(nom, valeur|None) pour chaque cible d'un `local a, b, c = …`, la
        valeur appariée PAR POSITION, None au-delà de la liste fournie : `local
        a, b, c = 1` donne (a, 1), (b, None), (c, None). Un seul appariement pour
        le top-level et pour les corps de handler — c'est ce qui manquait en
        corps, où seule la première cible était lue."""
        vals = values or []
        return [
            (t.id, self._expr(vals[i]) if i < len(vals) and vals[i] is not None else None)
            for i, t in enumerate(targets)
        ]

    def _stmt(self, node, local_scope: set[str]):
        t = type(node).__name__
        match t:
            case "Assign":
                tgt = self._expr(node.targets[0])
                val = self._expr(node.values[0])
                return StmtAssign(target=tgt, value=val)
            case "LocalAssign":
                out = []
                for name, val in self._local_pairs(node.targets, node.values):
                    local_scope.add(name)
                    out.append(StmtLocalAssign(name=name, value=val))
                return out
            case "Call":
                return StmtCall(call=self._expr_call(node))
            case "Invoke":
                return StmtCall(call=self._expr_invoke(node))
            case "If":
                return self._if(node, local_scope)
            case "While":
                return StmtWhile(
                    cond = self._expr(node.test),
                    body = self._block(node.body, set(local_scope)),
                )
            case "Fornum":
                # luaparser expose EXACTEMENT (target, start, stop, step, body).
                # Ces champs étaient lus décalés d'un cran — `start` pris pour la
                # variable, `stop` pour la borne de départ, `step` pour la borne
                # d'arrivée, et le pas jeté. `for i = 1, 10, 2` produisait donc
                # `for (int i = 10; i <= 2; i += 1)` : un corps de boucle qui ne
                # s'exécute jamais, sans une erreur de checker ni un
                # avertissement gcc pour le dire.
                var = getattr(node.target, "id", "i")
                inner = set(local_scope)
                inner.add(var)
                # Pas omis : luaparser ne pose pas None mais l'ENTIER Python 1,
                # que `_expr` ne sait pas lire (il attend un noeud) et traduisait
                # en `__unsupported_int`.
                raw_step = node.step
                if raw_step is None:
                    step = None
                elif isinstance(raw_step, int):
                    step = ExprNumber(raw_step)
                else:
                    step = self._expr(raw_step)
                return StmtForNum(
                    var   = var,
                    start = self._expr(node.start),
                    stop  = self._expr(node.stop),
                    step  = step,
                    body  = self._block(node.body, inner),
                )
            case "Return":
                vals = [self._expr(v) for v in (node.values or [])]
                return StmtReturn(values=vals)
            case "Break":
                return StmtBreak()
            case "SemiColon":
                return None          # `;` separates statements and produces nothing
            case _:
                # Tout le reste est PORTÉ jusqu'au checker, qui le refuse en
                # nommant l'issue (cf. StmtUnsupported). Un `Function` arrive
                # ici quand il est imbriqué dans un corps — au premier niveau,
                # c'est `convert_chunk` qui le prend, et il est légitime.
                return StmtUnsupported(node=t, line=self._line(node))

    def _if(self, node, local_scope) -> StmtIf:
        then = self._block(node.body, set(local_scope))
        elseifs = []
        else_ = []
        cur = node.orelse
        while cur:
            if type(cur).__name__ == "ElseIf":
                elseifs.append((
                    self._expr(cur.test),
                    self._block(cur.body, set(local_scope)),
                ))
                cur = cur.orelse
            else:
                else_ = self._block(cur, set(local_scope))
                break
        return StmtIf(
            cond    = self._expr(node.test),
            then    = then,
            elseifs = elseifs,
            else_   = else_,
        )

    def _expr(self, node) -> Any:
        if node is None:
            return ExprNil()
        t = type(node).__name__
        match t:
            case "Number":
                return ExprNumber(int(node.n))
            case "TrueExpr":
                return ExprBool(True)
            case "FalseExpr":
                return ExprBool(False)
            case "Nil":
                return ExprNil()
            case "String":
                return ExprString(node.raw)
            case "Name":
                return ExprName(node.id)
            case "Index":
                obj = self._expr(node.value)
                # La NOTATION décide, pas la forme de l'index. Lue de `hasattr
                # (node.idx, "id")`, elle rendait `t[i]` indiscernable de `t.i`
                # (le C émis lisait un champ) et `t[1]` indiscernable de rien du
                # tout (le repr Python du noeud partait dans le C).
                if node.notation == _lua_nodes.IndexNotation.SQUARE:
                    return ExprIndexAt(obj=obj, index=self._expr(node.idx))
                field = node.idx.id if hasattr(node.idx, "id") else str(node.idx)
                return ExprIndex(obj=obj, field=field)
            case "Table":
                fields_ = node.fields or []
                items = [self._expr(f.value) for f in fields_]
                return ExprTable(
                    items    = items,
                    has_keys = any(f.key is not None for f in fields_),
                    keys     = [getattr(f.key, "id", None) for f in fields_],
                )
            case "Invoke":
                return self._expr_invoke(node)
            case "Call":
                return self._expr_call(node)
            # Noms EXACTS de luaparser — `ULNotOp` et `ULengthOP` (capitale
            # finale comprise), pas `NotOp`/`LenOp`. Écrits de mémoire, ils ne
            # matchaient rien : `not x` retombait sur la branche binaire et
            # levait « 'ULNotOp' object has no attribute 'left' », un message
            # qui ne dit ni le nom de l'opérateur ni la ligne fautive.
            case n if n in _UNOP_MAP:
                return ExprUnop(op=_UNOP_MAP[n], operand=self._expr(node.operand))
            case n if n in _BINOP_MAP:
                return ExprBinop(op=_BINOP_MAP[n],
                                 left=self._expr(node.left),
                                 right=self._expr(node.right))
            case _:
                # Les deux tables ci-dessus sont la LISTE des opérateurs
                # traduits. Le test qui les remplaçait — « le nom du noeud finit
                # par Op » — acceptait aussi `^`, `//`, `&`, `<<`, dont le nom
                # de classe partait alors tel quel dans le C : `(a ExpoOp b)`.
                return ExprUnsupported(node=t, line=self._line(node))

    def _expr_invoke(self, node) -> ExprInvoke:
        obj    = self._expr(node.source)
        method = node.func.id if hasattr(node.func, "id") else str(node.func)
        args   = [self._expr(a) for a in (node.args or [])]
        # `sfx:play("Bip")`, `input:pressed("A")` : la méthode d'un MODULE du moteur. Elle
        # rejoint la forme d'appel de module — le reste du pipeline ne juge qu'elle.
        if isinstance(obj, ExprName) and obj.name in _module_calls():
            return ExprCall(func=ExprIndex(obj=obj, field=method), args=args)
        return ExprInvoke(obj=obj, method=method, args=args)

    def _expr_call(self, node) -> ExprCall:
        func = self._expr(node.func)
        args = [self._expr(a) for a in (node.args or [])]
        dotted = (isinstance(func, ExprIndex) and isinstance(func.obj, ExprName)
                  and func.obj.name in _module_calls())
        return ExprCall(func=func, args=args, dotted=dotted)


def _module_calls() -> frozenset:
    """Les modules du moteur qui s'appellent avec « : » (`api.MODULE_CALLS`). Import local :
    ce fichier ne dépend du catalogue que pour cette liste, et le catalogue n'importe pas ce
    fichier."""
    from .api import MODULE_CALLS
    return MODULE_CALLS


# ─── Déclaration d'un tableau ─────────────────────────────────────

# Deux façons de déclarer, parce que ce sont deux besoins : `{1, 2, 4, 8}`
# donne le CONTENU et en déduit la taille, `array(20, 12)` donne la TAILLE et
# remplit de zéros. La reconnaissance vit ici, avec la forme d'AST qu'elle lit,
# et le checker comme le codegen l'appellent — ils ont chacun besoin des mêmes
# dimensions, pour en faire deux choses différentes.

ARRAY_CTOR = "array"

# L'import d'un behavior. La forme est reconnue ICI, avec l'AST qu'elle lit,
# et ses deux consommateurs l'appellent : le checker (pour savoir qu'un alias
# de module n'est pas un nom inconnu) et le codegen (pour inliner le fichier).
# Elle était écrite deux fois dans codegen.py, à quinze lignes d'écart.
REQUIRE_FN = "require"


def require_target(expr) -> Optional[str]:
    """`require("behaviors/paddle_ai")` → "behaviors/paddle_ai", sinon None."""
    if (isinstance(expr, ExprCall)
            and isinstance(expr.func, ExprName)
            and expr.func.name == REQUIRE_FN
            and expr.args
            and isinstance(expr.args[0], ExprString)):
        return expr.args[0].value
    return None

# ─── Séquences ────────────────────────────────────────────────────
# Une séquence est une fonction de premier niveau `on_sequence_<nom>`, découpée
# au build à chaque attente. La FORME est reconnue ici, comme celle du tableau
# et du require, et ses trois consommateurs l'appellent : le checker (admettre
# ce nom-là et refuser une attente ailleurs), le codegen (découper), et
# `rom_build` (savoir qu'un script sans `on_update` a quand même quelque chose
# à faire à chaque frame).
SEQUENCE_PREFIX = "on_sequence_"
WAIT_FN         = "wait"
WAIT_UNTIL_FN   = "wait_until"
WAIT_FNS        = (WAIT_FN, WAIT_UNTIL_FN)


def sequence_name(fn_name: str) -> Optional[str]:
    """`on_sequence_intro` → "intro", sinon None."""
    if fn_name.startswith(SEQUENCE_PREFIX) and len(fn_name) > len(SEQUENCE_PREFIX):
        return fn_name[len(SEQUENCE_PREFIX):]
    return None


def wait_call(stmt) -> Optional[tuple[str, Any]]:
    """`wait(30)` → ("wait", ExprNumber(30)) ; `wait_until(c)` → ("wait_until", c).

    Une attente n'est un appel que par sa SYNTAXE — la source doit rester du Lua
    valide. Elle ne produit aucun appel C : elle coupe la séquence en deux.
    Rend None (et non une erreur) sur un nombre d'arguments fautif : c'est au
    checker de le dire avec les mots qui vont bien."""
    if not isinstance(stmt, StmtCall) or not isinstance(stmt.call, ExprCall):
        return None
    f = stmt.call.func
    if not isinstance(f, ExprName) or f.name not in WAIT_FNS:
        return None
    return f.name, (stmt.call.args[0] if stmt.call.args else None)


# L'espace de noms des tables AUTHORÉES du projet : `data.Objets[i].prix`.
# Un nom réservé plutôt qu'un nom global par table — sans lui, une table
# nommée `score` masquerait un `local score` du script, et l'auteur n'aurait
# aucun moyen de savoir lequel des deux il lit.
DATA_NS = "data"


def assigned_names(script: LuaScript) -> set[str]:
    """Les noms que le script ÉCRIT quelque part, à travers tous ses handlers.

    Ce qui compte est le nom à la BASE de la cible : `trajet[i] = 3` et
    `vitesse.x = 0` écrivent bien `trajet` et `vitesse`. Deux consommateurs :
    le codegen sépare l'état d'un prefab poolé (par instance) de ses constantes
    (partagées) ; le checker refuse un `wait_until` dont la condition ne lit que
    des noms absents d'ici — elle ne pourra jamais devenir vraie."""
    names: set[str] = set()

    def base(target) -> Optional[str]:
        while isinstance(target, (ExprIndex, ExprIndexAt)):
            target = target.obj
        return target.name if isinstance(target, ExprName) else None

    def walk(stmts):
        for s in stmts:
            if isinstance(s, StmtAssign):
                n = base(s.target)
                if n is not None:
                    names.add(n)
            elif isinstance(s, StmtIf):
                walk(s.then)
                for _cond, body in s.elseifs:
                    walk(body)
                walk(s.else_)
            elif isinstance(s, StmtWhile):
                walk(s.body)
            elif isinstance(s, StmtForNum):
                walk(s.body)

    for fn in script.functions:
        walk(fn.body)
    return names


def local_names(script: LuaScript) -> set[str]:
    """Tout ce qu'un identifiant NU a le droit de désigner dans ce script : les
    `local` (où qu'ils soient déclarés), la table de module d'un behavior, les
    paramètres de handler et les variables de boucle.

    Parcours À PLAT, sans portée lexicale : un `local` déclaré dans un `if`
    compte pour tout le script. C'est la lecture que le checker fait pour REFUSER
    un nom nu (une liste trop large ne fait que taire un refus, jamais en
    inventer un) ; elle vit ici pour que l'autocomplétion PROPOSE ces mêmes noms
    à partir de la même source, sans la redécrire."""
    names: set[str] = set()

    def walk(stmts):
        for s in stmts:
            if isinstance(s, StmtLocalAssign):
                names.add(s.name)
            elif isinstance(s, StmtIf):
                walk(s.then)
                for _cond, body in s.elseifs:
                    walk(body)
                walk(s.else_)
            elif isinstance(s, StmtWhile):
                walk(s.body)
            elif isinstance(s, StmtForNum):
                names.add(s.var)
                walk(s.body)

    for loc in script.locals:
        names.add(loc.name)
    names |= set(script.module_names or [])
    for fn in script.functions:
        names |= set(fn.params or [])
        walk(fn.body)
    return names


def array_dims(expr) -> Optional[tuple[int, ...]]:
    """Dimensions déclarées par cette expression d'initialisation, ou None si
    ce n'en est pas une (ou si sa forme est fautive — c'est alors au checker de
    dire laquelle, avec les mots qui vont bien).

    L'ORDRE DES ARGUMENTS EST L'ORDRE DES INDEX : `array(20, 12)` se lit
    `t[1..20][1..12]` et devient `int t[20][12]`. Aucune notion de largeur, de
    hauteur, de ligne ni de colonne — la déclaration montre déjà l'ordre."""
    if (isinstance(expr, ExprCall)
            and isinstance(expr.func, ExprName)
            and expr.func.name == ARRAY_CTOR):
        dims = []
        for a in expr.args:
            if not isinstance(a, ExprNumber) or a.value <= 0:
                return None
            dims.append(a.value)
        return tuple(dims) if 1 <= len(dims) <= 2 else None

    if isinstance(expr, ExprTable):
        if expr.has_keys or not expr.items:
            return None
        rows = [it for it in expr.items if isinstance(it, ExprTable)]
        if not rows:
            return (len(expr.items),)
        if len(rows) != len(expr.items):
            return None                       # mélange de lignes et de valeurs
        widths = {len(r.items) for r in rows}
        if len(widths) != 1 or 0 in widths or any(r.has_keys for r in rows):
            return None                       # lignes de longueurs différentes
        return (len(rows), widths.pop())

    return None


# ─── What a syntax error must say ─────────────────────────────────
#
# luaparser raises `SyntaxException`; antlr's own exception sits in
# `__context__`. Depending on the version it carries either the real exception
# (offending token, expected tokens) or only a string "line L:C: message". Both
# are read here, so the log always names a line.
#
# The line antlr reports is where it GAVE UP, which is often below the mistake
# (`x = 1; ADFZ` fails on the following `end`). When the message quotes the
# offending text, the line is moved up to the one that contains it.


def _antlr_detail(exc) -> tuple[Optional[int], str]:
    """(line, expected token) from the exception chain, `(None, "")` when the
    chain holds no token object."""
    ctx = getattr(exc, "__context__", None)
    inner = ctx.args[0] if (ctx is not None and getattr(ctx, "args", None)) else None
    tok = getattr(inner, "offendingToken", None)
    if tok is None:
        return None, ""
    attendu = ""
    try:
        reco = inner.recognizer
        attendu = inner.getExpectedTokens().toString(
            reco.literalNames, reco.symbolicNames).strip("{} ")
    except Exception:  # tolerated: optional detail: the message stays valid without it
        pass
    return getattr(tok, "line", None), attendu


def _message_detail(exc) -> tuple[Optional[int], str]:
    """(line, antlr message) read from "line L:C: message" in the exception text."""
    import re
    ctx = getattr(exc, "__context__", None)
    for source in (ctx, exc):
        m = re.search(r"line (\d+):\d+:? (.*)", str(source or ""), re.DOTALL)
        if m:
            return int(m.group(1)), m.group(2).strip()
    return None, ""


# False friends of an author coming from ANOTHER language. They are not in
# `lua_subset.REFUSED`: that one lists AST nodes, and none of these produces
# one — they prevent the AST from existing. Scanned only AFTER a failure, so
# never run on a valid script, and never alone: they complete antlr's line.
_FALSE_FRIENDS: tuple = (
    (r"^\s*(?:if|elseif)\b.*:\s*(?:--.*)?$",
     "in Lua an `if` ends with `then`, never with a colon"),
    (r"^\s*(?:for|while)\b.*:\s*(?:--.*)?$",
     "in Lua a loop ends with `do`, never with a colon"),
    (r"[+\-*/%.]=(?!=)",
     "Lua has no compound assignment: `x += 1` is written `x = x + 1`"),
    (r"\+\+", "Lua has no `++`: write `x = x + 1`"),
    (r"!=",   "\"not equal\" is written `~=`, not `!=`"),
    (r"&&",   "\"and\" is written `and`, not `&&`"),
    (r"\|\|", "\"or\" is written `or`, not `||`"),
    (r"(?<![~=<>!])!(?!=)",
     "\"not\" is written `not`, not `!`"),
    (r"^\s*elif\b",
     "\"else if\" is written `elseif`, as a single word"),
    (r"^\s*else\s+if\b",
     "`else if` opens a SECOND block that needs its own `end` — "
     "`elseif`, as a single word, does not"),
    # A condition that neither ends on an operator nor a comma (it would continue
    # on the next line) and holds no `then`: `if x == 0 self:play_anim("idle")`.
    (r"^\s*(?:if|elseif)\b(?!.*\bthen\b)(?!.*(?:\band|\bor|\bnot|[(,+\-*/%=<>~.{])\s*$)",
     "this `if` / `elseif` has no `then`: the condition must be followed by `then`"),
    (r"^\s*(?:for|while)\b(?!.*\bdo\b)(?!.*(?:\band|\bor|\bnot|[(,+\-*/%=<>~.{])\s*$)",
     "this `for` / `while` has no `do`: the header must be followed by `do`"),
    (r"^\s*#",
     "a comment starts with `--`; `#` is the length operator"),
    (r"^\s*//", "a comment starts with `--`, not `//`"),
)


def _code_lines(source: str) -> list[str]:
    """The source lines with strings and comments removed: a `!=` inside a line
    of dialogue is not a syntax error, and a `#` in a comment is a hash. The
    patterns for a line that is ENTIRELY a comment (`^\\s*#`, `^\\s*//`) are not
    concerned — those are not Lua comments, precisely."""
    import re

    def _code(l: str) -> str:
        l = re.sub(r"""\"[^\"]*\"|'[^']*'""", '""', l)
        return re.split(r"--", l, maxsplit=1)[0] if not l.lstrip().startswith("--") else ""

    return [_code(l) for l in source.splitlines()]


def _locals_in_exports(lignes: list[str]) -> set[int]:
    """Lines of a `local` declaration written INSIDE `exports = { ... }`: the
    block is a table, so each entry is `name = { type = ... }`, never `local`."""
    import re
    found, depth = set(), 0
    for n, texte in enumerate(lignes, start=1):
        if depth == 0:
            if not re.match(r"^\s*exports\s*=\s*\{", texte):
                continue
            texte_apres = texte[texte.index("{"):]
        else:
            texte_apres = texte
            if re.match(r"^\s*local\b", texte):
                found.add(n)
        depth += texte_apres.count("{") - texte_apres.count("}")
        depth = max(depth, 0)
    return found


_LOCAL_IN_EXPORTS = ("`local` has no place inside `exports = { ... }`: "
                     "write the entry as `name = { type = ... }`")


def _false_friend(source: str, line: Optional[int]) -> tuple[str, Optional[int]]:
    """(sentence, line where it was found) — searched first ON the line antlr
    gives, then in the whole file. The line is returned because it is THE one
    reported: antlr names where it gave up, often below the mistake."""
    import re
    lignes = _code_lines(source)
    locaux = _locals_in_exports(lignes)
    ordre = []
    if line and 1 <= line <= len(lignes):
        ordre.append((line, lignes[line - 1]))
    ordre += [(i, l) for i, l in enumerate(lignes, start=1) if i != line]
    for n, texte in ordre:
        if n in locaux:
            return _LOCAL_IN_EXPORTS, n
        for motif, phrase in _FALSE_FRIENDS:
            if re.search(motif, texte):
                return phrase, n
    return "", None


def _offending_line(source: str, reported: int, quoted: str) -> int:
    """The line, at or above `reported`, where the quoted offending text begins."""
    import re
    first = quoted.split("\\n")[0].strip().strip("'")
    if not first:
        return reported
    word = re.escape(first.split()[0]) if first.split() else ""
    lignes = _code_lines(source)
    for n in range(min(reported, len(lignes)), 0, -1):
        if word and re.search(word, lignes[n - 1]):
            return n
    return reported


def _syntax_message(source: str, exc) -> tuple[str, Optional[int]]:
    """The message of a syntax error, and its line."""
    import re
    line, attendu = _antlr_detail(exc)
    msg_line, antlr_msg = _message_detail(exc)
    if line is None:
        line = msg_line
    indice, indice_line = _false_friend(source, line)

    # A false friend is said ALONE, and on ITS line: strings and comments having
    # been set aside, what remains is code, so a `&&` or a `!=` is a mistake, not
    # a lead. Two sentences for one mistake would send the author looking for two.
    if indice:
        return indice, (indice_line or line)

    quoted = re.search(r"input '(.*)'$", antlr_msg, re.DOTALL)
    if attendu == "'end'":
        # The most frequent case, and the one whose line says the least: antlr
        # stumbles on the END OF THE FILE, not on the block left open.
        msg = ("missing `end`: an `if`, a loop or a `function` is never closed")
    elif attendu:
        msg = f"`{attendu.strip(chr(39))}` expected here"
    elif antlr_msg.startswith("token recognition error"):
        char = re.search(r"at: '(.*)'", antlr_msg)
        msg = (f"unexpected character `{char.group(1)}`" if char
               else "unexpected character")
    elif quoted and "\\n" in quoted.group(1):
        # The quote starts at the first token of the statement that failed.
        line = _offending_line(source, line or 1, quoted.group(1))
        # La ligne citée par antlr peut finir par un commentaire : il n'a rien à faire ici.
        token = re.split(r"\s*--", quoted.group(1).split("\\n")[0])[0].strip()
        msg = f"unexpected `{token}`: this is not a valid statement or expression"
    elif quoted:
        # A lone token: antlr gave up HERE, so the statement BEFORE it is the one
        # left incomplete. That line is reported, with its text.
        token = quoted.group(1).strip()
        lignes = source.splitlines()
        code = _code_lines(source)
        precedente = next((n for n in range(min((line or 1) - 1, len(lignes)), 0, -1)
                           if code[n - 1].strip()), None)
        if precedente:
            line = precedente
            msg = (f"this statement is incomplete or malformed (`{lignes[precedente - 1].strip()}`): "
                   f"the parser stopped at the next `{token}`")
        else:
            msg = f"unexpected `{token}` at the start of the script"
    elif line:
        msg = "this line is not valid Lua"
    else:
        msg = "syntax error"

    return msg, line


# ─── Point d'entrée public ────────────────────────────────────────

def parse(source: str) -> LuaScript:
    """
    Parse le source Lua et retourne un LuaScript normalisé.
    Lève LuaParseError en cas d'erreur de syntaxe.
    """
    if not _LUAPARSER_OK:
        raise LuaParseError("luaparser is not installed (pip install luaparser)")
    try:
        raw = _lua_ast.parse(source)
    except Exception as e:
        msg, line = _syntax_message(source, e)
        raise LuaParseError(msg, line) from e
    # La CONVERSION, elle, n'est pas une faute de syntaxe : une exception ici
    # est un noeud que `_Converter` ne sait pas traiter, pas un script mal
    # écrit. Le message d'origine reste le plus utile — le déguiser en erreur
    # de syntaxe enverrait l'auteur corriger un fichier qui n'a rien.
    try:
        return _Converter(source).convert_chunk(raw)
    except Exception as e:
        raise LuaParseError(f"unreadable script: {e}") from e
