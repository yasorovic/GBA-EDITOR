"""
editor/scripting/lua_subset.py — ce que le sous-ensemble Lua accepte, et ce
qu'il refuse EN LE DISANT.

Le compilateur ne traduit qu'une partie de Lua. C'était vrai depuis le premier
jour ; ce qui manquait, c'est que la partie non traduite se voie. `parser.py`
rendait `None` pour tout statement non géré (le corps de boucle disparaissait du
jeu, sans un mot) et `ExprName("__unsupported_<Type>")` pour toute expression
non gérée (du C qui ne compile pas, sur la ligne générée, jamais sur sa cause).

Ce fichier est la LISTE, et il n'y en a qu'une : le checker s'en sert pour
refuser, `docs/scripting-reference.md` pour expliquer, et `validator._check_lua_subset` vérifie
qu'aucun nœud de luaparser n'y manque. Deux listes auraient divergé — c'est
exactement ce qui est arrivé entre `api.py` et `api_reference.json`, et le
remède est le même : une source, des consommateurs.

Trois cases, et le choix entre elles fait partie de l'ajout d'un nœud :

  ACCEPTED    traduit — la forme Lua est celle qu'on écrit
  REFUSED     non traduit, et la phrase qui dit quoi écrire à la place
  STRUCTURAL  jamais dispatché : lu en place par le nœud qui le porte
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── Un refus ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Refusal:
    """`lua` est la forme ÉCRITE (ce que le document montre), `message` la
    phrase dite à l'auteur sur sa ligne. Les deux se lisent seuls : un message
    qui ne dirait que « non supporté » obligerait à chercher ailleurs ce qu'il
    faut écrire, et c'est ce « ailleurs » qui n'existait pas."""
    lua:     str
    message: str


# ─── Ce qui se traduit ────────────────────────────────────────────
# Nœud luaparser → la forme Lua correspondante. Le VOCABULAIRE du sous-ensemble,
# au complet : ce qui n'est pas ici ne se traduit pas.

ACCEPTED: dict[str, str] = {
    # Déclarations et affectations
    "Function":     "function on_update() … end — un handler d'événement",
    "LocalAssign":  "local x = 0",
    "Assign":       "x = 1  /  self.position = p  /  t[i] = v",
    # Contrôle
    "If":           "if … then … end",
    "ElseIf":       "elseif … then",
    "While":        "while … do … end",
    "Fornum":       "for i = 1, n do … end  (pas écrit en clair : for i = n, 1, -1)",
    "Break":        "break",
    "Return":       "return  /  return v",
    "SemiColon":    ";  — ne produit rien, comme en Lua",
    # Appels
    "Call":         'sfx:play("Bip")  /  vec2(x, y)  /  array(8)',
    "Invoke":       'self:play_anim("walk")',
    # Valeurs
    "Number":       "12  (entier — un littéral à virgule est tronqué)",
    "String":       '"un_nom"  — un nom cité du projet ; `text.draw` accepte aussi un texte littéral',
    "TrueExpr":     "true",
    "FalseExpr":    "false",
    "Nil":          "nil  (vaut 0 dans le C émis — cf. « La vérité » ci-dessous)",
    "Name":         "x",
    "Index":        "self.position  /  data.Objets  /  t[i]",
    "Table":        "{1, 2, 4, 8}  — un tableau, et rien d'autre",

    # ── La vérité — décision volontaire (2026-09-27), PAS le vrai Lua ──
    # En vrai Lua, seuls `nil` et `false` sont faux ; `0` est VRAI. Ici,
    # `if`/`while`/`and`/`or`/`not` se traduisent tels quels vers leurs
    # équivalents C (`if`/`while`/`&&`/`||`/`!`) : `0` y est FAUX, comme
    # partout ailleurs dans ce moteur entièrement entier. Assumé pour que
    # `if not hp then` marche comme on l'attend d'un `hp` qui peut valoir 0 —
    # sans ça, un auteur qui connaît le vrai Lua se ferait piéger par un test
    # qui « marche toujours », `0` y étant vrai. `nil` compile vers `0` pour
    # la même raison : une seule notion de « rien/faux », pas deux.
    # Opérateurs
    "AddOp":              "a + b",
    "SubOp":              "a - b",
    "MultOp":             "a * b",
    "FloatDivOp":         "a / b  (division ENTIÈRE — le C tronque vers zéro)",
    "ModOp":              "a % b",
    "EqToOp":             "a == b",
    "NotEqToOp":          "a ~= b",
    "LessThanOp":         "a < b",
    "GreaterThanOp":      "a > b",
    "LessOrEqThanOp":     "a <= b",
    "GreaterOrEqThanOp":  "a >= b",
    "AndLoOp":            "a and b",
    "OrLoOp":             "a or b",
    "UMinusOp":           "-a",
    "ULNotOp":            "not a",
    "ULengthOP":          "#t  — constante de compilation, pas une lecture",
}


# ─── Ce qui ne se traduit pas ─────────────────────────────────────
# Chaque entrée dit POURQUOI (une raison du moteur, jamais « pas implémenté »
# tout court quand il y en a une) et QUOI ÉCRIRE à la place quand il y a une
# issue. Là où il n'y en a pas, le refus le dit aussi — croire à une issue
# qu'on n'a pas nommée coûte plus cher qu'un « non » clair.

REFUSED: dict[str, Refusal] = {

    # ── Boucles et sauts ──────────────────────────────────────────
    "Forin": Refusal(
        "for k, v in pairs(t) do … end",
        "`for … in` does not exist: a generic iterator assumes first-class values and"
        " an iteration state, that is, the Lua tables this engine does not have. An "
        "array is walked by its index: `for i = 1, #t do`."),

    "Repeat": Refusal(
        "repeat … until c",
        "`repeat … until` does not exist: the only conditional loop is `while`, "
        "tested at the top. For a body that must run at least once: `while true do … "
        "if c then break end end`."),

    "Goto": Refusal(
        "goto etiquette",
        "`goto` does not exist. `break` leaves a loop, `return` leaves the handler — "
        "beyond that, the `if` carries the structure."),

    "Label": Refusal(
        "::etiquette::",
        "a label does not exist, for lack of a `goto` to jump to it."),

    "Do": Refusal(
        "do … end",
        "a bare `do … end` block does not exist: it only opens a local scope, and "
        "here a variable lives in the function where it is declared. Write its "
        "content directly."),

    # ── Fonctions ─────────────────────────────────────────────────
    # Les helpers privés s'écrivent `function f() … end` au premier niveau.
    # Les trois formes ci-dessous restent volontairement hors du sous-ensemble :
    # fonction locale/imbriquée, méthode, ou fonction-valeur.

    "LocalFunction": Refusal(
        "local function f() … end",
        "a private function is written `function f() … end` at the top level, not "
        "`local function`. It receives `self` implicitly and stays private to the "
        "script."),

    "Method": Refusal(
        "function objet:methode() … end",
        "the subset has no table or object to attach a method to. The only methods "
        "are those of an actor (`self:play_anim(\"walk\")`), provided by the engine; "
        "shared code goes through a behavior (`require(\"behaviors/name\")`)."),

    "AnonymousFunction": Refusal(
        "local f = function() … end",
        "a function is not a value here: it is stored neither in a variable, nor in "
        "an argument, nor in an array — which only holds integers. So no callbacks "
        "and no closures; what must trigger later is written with a state and the "
        "`if` that reads it."),

    "Dots": Refusal(
        "...",
        "`...` does not exist: private functions have parameters written in full. The"
        " only variadic functions are those of the catalogue, and their arguments are"
        " written in full."),

    "Varargs": Refusal(
        "...",
        "variable arguments do not exist in this subset: a private function declares "
        "all its parameters."),

    # ── Chaînes ───────────────────────────────────────────────────
    "Concat": Refusal(
        'a .. b',
        "`..` does not exist: the engine has no string it can manipulate, and "
        "composing text at run time would need a buffer and an allocation. For a "
        "one-off HUD, a text.draw literal already accepts \"Score: $score\"; `$score` "
        "reads a visible local or a global. An entry of the text table stays "
        "translatable and only interpolates globals."),

    # ── Arithmétique absente ──────────────────────────────────────
    "ExpoOp": Refusal(
        "a ^ b",
        "`^` does not exist: the engine is integer-only. A power is written by "
        "multiplying (`x * x`), and the root has `math.sqrt(x)`."),

    "FloorDivOp": Refusal(
        "a // b",
        "`//` does not exist — and has no business here: `/` is ALREADY an integer "
        "division, truncated toward zero as in C."),

    # ── Opérateurs binaires ───────────────────────────────────────
    # Six nœuds, une seule raison : ils ne sont pas dans le sous-ensemble, et
    # rien ne les a réclamés. Le matériel ne s'y oppose pas — ils se
    # traduiraient terme à terme —, c'est donc un refus daté et pas définitif
    # (cf. ROADMAP v0.7.5, « Ouvert »). Un message par opérateur : celui qui
    # écrit `<<` cherche `<<`, pas « opérateur binaire ».

    "BAndOp": Refusal(
        "a & b",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. A "
        "flag is stored in a global variable, and the hardware registers are driven "
        "through the API (`layer`, `window`, `blend`)."),
    "BOrOp": Refusal(
        "a | b",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. A "
        "flag is stored in a global variable, and the hardware registers are driven "
        "through the API (`layer`, `window`, `blend`)."),
    "BXorOp": Refusal(
        "a ~ b",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. "
        "Mind the reading trap: here `~=` is indeed \"not equal\", it is `~` ALONE that"
        " does not exist."),
    "BShiftLOp": Refusal(
        "a << b",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. A "
        "left shift is a multiplication, a right shift is a division — both are "
        "integer."),
    "BShiftROp": Refusal(
        "a >> b",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. A "
        "left shift is a multiplication, a right shift is a division — both are "
        "integer."),
    "UBNotOp": Refusal(
        "~a",
        "the bitwise operators (`&`, `|`, `~`, `<<`, `>>`) are not in the subset. To "
        "invert a condition, use `not`."),
}


# Un `function f() … end` écrit DANS un corps de handler : le nœud est le même
# que celui d'un handler de premier niveau (`Function`, rangé plus haut dans
# ACCEPTED), seule sa PLACE change. Son refus ne peut donc pas être indexé par
# le nom du nœud — c'est le seul de ce cas, et il vit ici plutôt que de forcer
# la table à porter une notion de position pour une entrée.
NESTED_FUNCTION = Refusal(
    "function f() … end, inside a body",
    "a private function is declared at the top level of the script, never inside a "
    "handler or another function.")


# ─── Ce qui n'est jamais dispatché ────────────────────────────────

STRUCTURAL: dict[str, str] = {
    # Une entrée de constructeur `{ }` : lue en place par `parser.array_dims`
    # via `Table.fields`, jamais visitée comme une expression à part entière.
    "Field": "une entrée de { } — lue avec le constructeur qui la porte",
}


# ─── La bibliothèque standard de Lua ──────────────────────────────
# Elle n'existe pas ici : le script devient du C, dans une ROM sans allocateur,
# sans système de fichiers et sans machine virtuelle. Chaque nom courant reçoit
# donc sa propre phrase — un « fonction inconnue » générique laisserait croire à
# une faute de frappe, alors que le nom est juste et que c'est le monde qui
# diffère.

STDLIB_MODULES: dict[str, Refusal] = {
    "string": Refusal(
        "string.format(…)",
        "there is no `string` library: the engine has no string it can manipulate. "
        "Displayed text lives in the text table, with its markup and its values (\"HP:"
        " $life\"), and `text.draw` displays it."),
    "table": Refusal(
        "table.insert(t, v)",
        "there is no `table` library: an array has a fixed size, decided at build "
        "(`local t = array(8)`), so there is nothing to insert or remove. `#t` is a "
        "compile-time constant, not a length stored in memory."),
    "os": Refusal(
        "os.time()",
        "there is no `os` module: a ROM has neither a system clock nor processes. "
        "Time is counted in frames (`scene.frame`), and what must survive power-off "
        "goes through the save (`save.write`)."),
    "io": Refusal(
        "io.open(…)",
        "there is no `io` module: a ROM has no file system. The only writable memory "
        "is the save (`save.write` / `save.load`), and resources are baked into the "
        "cartridge."),
    "coroutine": Refusal(
        "coroutine.create(f)",
        "there are no coroutines: the engine calls `on_update` once per frame and "
        "takes control back. An action spread over time is written with a state — a "
        "counter in a variable, and the `if` that reads it."),
    # `debug` n'est plus ici : ROADMAP v0.14 en fait un vrai module, avec un
    # seul membre (`debug.log`). Un autre membre Lua (`debug.traceback()`
    # notamment) retombe désormais sur `unknown_member_message` — « le
    # module `debug` n'a pas de `traceback`. Il offre : log. » — plus
    # précis qu'un refus générique, et ça vient gratuitement du catalogue
    # (api.py) une fois `debug.log` déclaré là.
    "utf8": Refusal(
        "utf8.char(…)",
        "there is no `utf8` module: the engine has no string it can manipulate. The "
        "encoding of texts is decided at build, by the font and the text table."),
    "package": Refusal(
        "package.path",
        "there is no `package` module: nothing is loaded at run time. "
        "`require(\"behaviors/name\")` is the only form of import, and it is resolved "
        "at build."),
}


STDLIB: dict[str, Refusal] = {

    # ── Le seul qu'on tape par réflexe ────────────────────────────
    "print": Refusal(
        "print(x)",
        "`print` does not exist: the GBA has no console. Writing to the PLAYER is "
        "done with `text.draw` (a font, an entry of the text table, hence "
        "translatable). A trace for the DEVELOPER is `debug:log(...)` — it goes out "
        "through the mGBA log, not the game screen, and disappears from release "
        "builds."),

    # ── Itération ─────────────────────────────────────────────────
    "pairs": Refusal(
        "pairs(t)",
        "`pairs` does not exist: there is no Lua table to walk. An array is walked by"
        " its index — `for i = 1, #t do`."),
    "ipairs": Refusal(
        "ipairs(t)",
        "`ipairs` does not exist: an array is walked by its index — `for i = 1, #t "
        "do`, and `#t` is known at build."),
    "next": Refusal(
        "next(t)",
        "`next` does not exist: there is no Lua table to walk."),
    "select": Refusal(
        "select(n, ...)",
        "`select` does not exist: nothing has variable arguments, since a script does"
        " not declare functions of its own."),
    "unpack": Refusal(
        "unpack(t)",
        "`unpack` does not exist: an array is not spread into arguments, for lack of "
        "a variable-arity call."),

    # ── Types et conversions ──────────────────────────────────────
    "type": Refusal(
        "type(x)",
        "`type` does not exist: there is nothing to query. A value is an integer, a "
        "vec2/vec3, or an array of integers — and its type is known at build, never "
        "at run time."),
    "tostring": Refusal(
        "tostring(x)",
        "`tostring` does not exist: the engine has no string it can manipulate. To "
        "display a number, put a value marker in the text entry (\"Score: $my_global\")"
        " and call `text.draw`."),
    "tonumber": Refusal(
        "tonumber(s)",
        "`tonumber` does not exist: there is no string to convert. The only strings "
        "in a script are project NAMES, resolved at build."),

    # ── Erreurs ───────────────────────────────────────────────────
    "pcall": Refusal(
        "pcall(f)",
        "there are no exceptions: the generated C has neither an unwinding stack nor "
        "a handler. A condition that must be true is tested with an `if`."),
    "xpcall": Refusal(
        "xpcall(f, h)",
        "there are no exceptions: the generated C has neither an unwinding stack nor "
        "a handler."),
    "error": Refusal(
        "error(msg)",
        "`error` does not exist: there is no exception to raise, and no console to "
        "read it. What must be true is checked with an `if`, and what must be true AT"
        " BUILD is the checker's job."),
    "assert": Refusal(
        "assert(c)",
        "`assert` does not exist: no exception, no console. An `if` that fixes the "
        "faulty value is better than a halt nobody would see."),

    # ── Tables et métatables ──────────────────────────────────────
    "setmetatable": Refusal(
        "setmetatable(t, mt)",
        "there is no metatable: there is no Lua table. An array of the language is a "
        "block of integers of fixed size, with no behaviour."),
    "getmetatable": Refusal(
        "getmetatable(t)",
        "there is no metatable: there is no Lua table."),
    "rawget": Refusal("rawget(t, k)", "there is no Lua table."),
    "rawset": Refusal("rawset(t, k, v)", "there is no Lua table."),
    "rawequal": Refusal("rawequal(a, b)", "there is no Lua table."),
    "rawlen": Refusal(
        "rawlen(t)",
        "there is no Lua table. The size of an array is `#t`, a compile-time "
        "constant."),

    # ── Exécution ─────────────────────────────────────────────────
    "collectgarbage": Refusal(
        "collectgarbage()",
        "there is no garbage collector: nothing is allocated at run time. All memory "
        "is decided at build, which is what makes its cost visible."),
    "load": Refusal(
        "load(src)",
        "code is not loaded at run time: everything is transpiled to C and baked into"
        " the ROM. `require(\"behaviors/name\")` is the only form of import, resolved "
        "at build."),
    "loadstring": Refusal(
        "loadstring(src)",
        "code is not loaded at run time: everything is transpiled to C and baked into"
        " the ROM."),
    "dofile": Refusal(
        "dofile(chemin)",
        "there is no file system in a ROM. `require(\"behaviors/name\")` imports a "
        "behavior, at build."),
    "loadfile": Refusal(
        "loadfile(chemin)",
        "there is no file system in a ROM. `require(\"behaviors/name\")` imports a "
        "behavior, at build."),

    # ── `math`, le faux ami ───────────────────────────────────────
    # Le module existe, sous le même nom, avec un AUTRE contenu — le pire cas
    # possible : celui où l'auteur a raison de ne pas vérifier. Les membres
    # absents qui ont une issue sont nommés ici ; les autres tombent sur
    # `unknown_member_message`, qui liste ce que le module offre vraiment.
    "math.floor": Refusal(
        "math.floor(x)",
        "`math.floor` does not exist, and has no business here: the engine is "
        "entirely integer, there is nothing to round. `/` already truncates toward "
        "zero."),
    "math.ceil": Refusal(
        "math.ceil(x)",
        "`math.ceil` does not exist: the engine is entirely integer. To round a "
        "division up, use `(a + b - 1) / b`."),
    "math.random": Refusal(
        "math.random(a, b)",
        "random draws are written `math.rand(lo, hi)` — this `math` is the engine's, "
        "not Lua's."),
    "math.randomseed": Refusal(
        "math.randomseed(n)",
        "the seed is not exposed: `math.rand(lo, hi)` is enough for the script, and "
        "the engine owns its sequence."),
    "math.pi": Refusal(
        "math.pi",
        "there is no floating point in the engine, hence no π. Angles are written in "
        "DEGREES: `math.sin(90)`, `math.cos(180)`."),
    "math.huge": Refusal(
        "math.huge",
        "there is no infinity: values are 32-bit integers. A bound is written in "
        "full."),
    "math.pow": Refusal(
        "math.pow(x, n)",
        "`math.pow` does not exist: an integer power is written by multiplying (`x * "
        "x`)."),
    "math.fmod": Refusal(
        "math.fmod(a, b)",
        "`math.fmod` does not exist: the integer remainder is the `%` operator."),
    "math.modf": Refusal(
        "math.modf(x)",
        "`math.modf` does not exist: there is no fractional part, all values are "
        "integers."),
}


# ─── Ce que le checker demande à ce fichier ───────────────────────

def refusal_for_node(node_name: str) -> Optional[Refusal]:
    """Le refus attaché à un type de nœud luaparser, ou None s'il se traduit."""
    return REFUSED.get(node_name)


def refusal_for_call(key: str) -> Optional[Refusal]:
    """Le refus attaché à un appel — par son nom entier (`math.floor`), sinon
    par son MODULE (`string.format` → `string`). Rendre None ne veut pas dire
    « autorisé » : ça veut dire que ce n'est pas un nom de Lua, et c'est alors à
    `unknown_call_message` de le dire."""
    exact = STDLIB.get(key)
    if exact is not None:
        return exact
    module = key.split(".", 1)[0] if "." in key else ""
    return STDLIB_MODULES.get(module)


def unknown_member_message(module: str, member: str, offered: list[str]) -> str:
    """Un module du catalogue existe, ce membre non. Lister ce qu'il offre est
    ce qui distingue une faute de frappe d'une fonction de Lua qu'on croyait
    trouver ici — le cas `math`, où le nom du module est le même et le contenu
    différent."""
    liste = ", ".join(sorted(offered)) or "rien"
    return (f"the module `{module}` has no `{member}`. It offers: {liste}. (These are the engine's "
            "functions, not Lua's.)")


def unknown_call_message(key: str) -> str:
    """Un appel qui n'est ni du catalogue, ni un constructeur du langage, ni un
    behavior importé. Il était TOLÉRÉ jusqu'ici, au motif que ce pouvait être un
    helper écrit par l'utilisateur — sauf que le codegen l'émettait tel quel
    (`math.floor(x)` partait en C avec son point), donc la faute ne remontait
    qu'au `make`, sur la ligne générée."""
    if "." in key:
        module = key.split(".", 1)[0]
        return (f"`{key}()`: the module `{module}` does not exist. The available modules are "
                "those of the catalogue (API panel of the Script Editor); a behavior "
                "is imported with `require(\"behaviors/name\")` and called through its "
                "alias.")
    return (f"`{key}()`: unknown function. A script has no functions of its own — the "
            "possible calls are those of the catalogue, the language constructors "
            "(`vec2`, `vec3`, `rect`, `array`), `require`, and the methods of an "
            "imported behavior.")


# ─── Contrôle de couverture ───────────────────────────────────────

def covered_nodes() -> frozenset:
    """Les nœuds que ce fichier classe — traduits, refusés ou structurels.

    Rendu par une fonction et non par les tables : le contrôle
    (`validator._check_lua_subset`) demande « ce nœud t'est-il connu ? », pas la
    mécanique interne. Pendant exact de `checker.covered_domains()`."""
    return frozenset(ACCEPTED) | frozenset(REFUSED) | frozenset(STRUCTURAL)
