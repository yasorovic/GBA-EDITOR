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
    "Nil":          "nil  (vaut 0 dans le C émis)",
    "Name":         "x",
    "Index":        "self.position  /  data.Objets  /  t[i]",
    "Table":        "{1, 2, 4, 8}  — un tableau, et rien d'autre",
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
        "`for … in` n'existe pas : un itérateur générique suppose des valeurs "
        "de première classe et un état d'itération, c'est-à-dire les tables "
        "Lua que ce moteur n'a pas. Un tableau se parcourt par son index : "
        "`for i = 1, #t do`."),

    "Repeat": Refusal(
        "repeat … until c",
        "`repeat … until` n'existe pas : la seule boucle à condition est "
        "`while`, testée en tête. Pour un corps qui doit tourner au moins une "
        "fois : `while true do … if c then break end end`."),

    "Goto": Refusal(
        "goto etiquette",
        "`goto` n'existe pas. `break` sort d'une boucle, `return` sort du "
        "handler — au-delà, c'est le `if` qui porte la structure."),

    "Label": Refusal(
        "::etiquette::",
        "une étiquette n'existe pas, faute de `goto` pour y sauter."),

    "Do": Refusal(
        "do … end",
        "un bloc `do … end` nu n'existe pas : il ne sert qu'à ouvrir une "
        "portée locale, et ici une variable vit dans la fonction où elle est "
        "déclarée. Écris son contenu directement."),

    # ── Fonctions ─────────────────────────────────────────────────
    # Les helpers privés s'écrivent `function f() … end` au premier niveau.
    # Les trois formes ci-dessous restent volontairement hors du sous-ensemble :
    # fonction locale/imbriquée, méthode, ou fonction-valeur.

    "LocalFunction": Refusal(
        "local function f() … end",
        "une fonction privée s'écrit `function f() … end` au premier niveau, "
        "pas `local function`. Elle reçoit `self` implicitement et reste "
        "privée au script."),

    "Method": Refusal(
        "function objet:methode() … end",
        "le sous-ensemble n'a ni table ni objet à qui attacher une méthode. "
        "Les seules méthodes sont celles d'un acteur "
        "(`self:play_anim(\"walk\")`), fournies par le moteur ; le code "
        'partagé passe par un behavior (`require("behaviors/nom")`).'),

    "AnonymousFunction": Refusal(
        "local f = function() … end",
        "une fonction n'est pas une valeur ici : elle ne se range ni dans une "
        "variable, ni dans un argument, ni dans un tableau — qui ne porte que "
        "des entiers. Donc pas de rappel ni de fermeture ; ce qui doit se "
        "déclencher plus tard s'écrit avec un état et le `if` qui le lit."),

    "Dots": Refusal(
        "...",
        "`...` n'existe pas : les fonctions privées ont des paramètres écrits "
        "en clair. Les seules fonctions variadiques sont "
        "celles du catalogue, et leurs arguments s'écrivent en clair."),

    "Varargs": Refusal(
        "...",
        "les arguments variables n'existent pas dans ce sous-ensemble : une "
        "fonction privée déclare tous ses paramètres."),

    # ── Chaînes ───────────────────────────────────────────────────
    "Concat": Refusal(
        'a .. b',
        "`..` n'existe pas : le moteur n'a pas de chaîne manipulable, et "
        "composer du texte à l'exécution demanderait un tampon et une "
        "allocation. Pour un HUD ponctuel, un littéral de text.draw accepte "
        'déjà « Score : $score » ; `$score` lit une locale visible ou une '
        "globale. Une entrée de la table de textes, elle, reste traduisible et "
        "n'interpole que les globals."),

    # ── Arithmétique absente ──────────────────────────────────────
    "ExpoOp": Refusal(
        "a ^ b",
        "`^` n'existe pas : le moteur est entier. Une puissance s'écrit en "
        "multipliant (`x * x`), et la racine a `math.sqrt(x)`."),

    "FloorDivOp": Refusal(
        "a // b",
        "`//` n'existe pas — et n'a rien à faire ici : `/` est DÉJÀ une "
        "division entière, tronquée vers zéro comme en C."),

    # ── Opérateurs binaires ───────────────────────────────────────
    # Six nœuds, une seule raison : ils ne sont pas dans le sous-ensemble, et
    # rien ne les a réclamés. Le matériel ne s'y oppose pas — ils se
    # traduiraient terme à terme —, c'est donc un refus daté et pas définitif
    # (cf. ROADMAP v0.7.5, « Ouvert »). Un message par opérateur : celui qui
    # écrit `<<` cherche `<<`, pas « opérateur binaire ».

    "BAndOp": Refusal(
        "a & b",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Un drapeau se range dans une variable globale, et "
        "les registres du matériel se pilotent par l'API (`layer`, `window`, "
        "`blend`)."),
    "BOrOp": Refusal(
        "a | b",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Un drapeau se range dans une variable globale, et "
        "les registres du matériel se pilotent par l'API (`layer`, `window`, "
        "`blend`)."),
    "BXorOp": Refusal(
        "a ~ b",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Attention au piège de lecture : ici `~=` est bien "
        "la différence, c'est `~` SEUL qui n'existe pas."),
    "BShiftLOp": Refusal(
        "a << b",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Un décalage vers la gauche se multiplie, un "
        "décalage vers la droite se divise — les deux sont entiers."),
    "BShiftROp": Refusal(
        "a >> b",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Un décalage vers la gauche se multiplie, un "
        "décalage vers la droite se divise — les deux sont entiers."),
    "UBNotOp": Refusal(
        "~a",
        "les opérateurs binaires (`&`, `|`, `~`, `<<`, `>>`) ne sont pas dans "
        "le sous-ensemble. Pour inverser une condition, c'est `not`."),
}


# Un `function f() … end` écrit DANS un corps de handler : le nœud est le même
# que celui d'un handler de premier niveau (`Function`, rangé plus haut dans
# ACCEPTED), seule sa PLACE change. Son refus ne peut donc pas être indexé par
# le nom du nœud — c'est le seul de ce cas, et il vit ici plutôt que de forcer
# la table à porter une notion de position pour une entrée.
NESTED_FUNCTION = Refusal(
    "function f() … end, dans un corps",
    "une fonction privée se déclare au premier niveau du script, jamais dans "
    "un handler ou une autre fonction.")


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
        "il n'y a pas de bibliothèque `string` : le moteur n'a pas de chaîne "
        "manipulable. Le texte affiché vit dans la table de textes, avec son "
        "balisage et ses valeurs (« PV : $vie »), et `text.draw` l'affiche."),
    "table": Refusal(
        "table.insert(t, v)",
        "il n'y a pas de bibliothèque `table` : un tableau a une taille fixe, "
        "décidée au build (`local t = array(8)`), donc rien à insérer ni à "
        "retirer. `#t` est une constante de compilation, pas une longueur "
        "rangée en mémoire."),
    "os": Refusal(
        "os.time()",
        "il n'y a pas de module `os` : une ROM n'a ni horloge système ni "
        "processus. Le temps se compte en frames (`scene.frame`), et ce qui "
        "doit survivre à l'extinction passe par la sauvegarde (`save.write`)."),
    "io": Refusal(
        "io.open(…)",
        "il n'y a pas de module `io` : une ROM n'a pas de système de fichiers. "
        "La seule mémoire inscriptible est la sauvegarde (`save.write` / "
        "`save.load`), et les ressources sont cuites dans la cartouche."),
    "coroutine": Refusal(
        "coroutine.create(f)",
        "il n'y a pas de coroutine : le moteur appelle `on_update` une fois "
        "par frame et reprend la main. Une action étalée dans le temps s'écrit "
        "avec un état — un compteur dans une variable, et le `if` qui le lit."),
    # `debug` n'est plus ici : ROADMAP v0.14 en fait un vrai module, avec un
    # seul membre (`debug.log`). Un autre membre Lua (`debug.traceback()`
    # notamment) retombe désormais sur `unknown_member_message` — « le
    # module `debug` n'a pas de `traceback`. Il offre : log. » — plus
    # précis qu'un refus générique, et ça vient gratuitement du catalogue
    # (api.py) une fois `debug.log` déclaré là.
    "utf8": Refusal(
        "utf8.char(…)",
        "il n'y a pas de module `utf8` : le moteur n'a pas de chaîne "
        "manipulable. L'encodage des textes est décidé au build, par la police "
        "et la table de textes."),
    "package": Refusal(
        "package.path",
        "il n'y a pas de module `package` : rien n'est chargé à l'exécution. "
        '`require("behaviors/nom")` est la seule forme d\'import, et elle est '
        "résolue au build."),
}


STDLIB: dict[str, Refusal] = {

    # ── Le seul qu'on tape par réflexe ────────────────────────────
    "print": Refusal(
        "print(x)",
        "`print` n'existe pas : la GBA n'a pas de console. Écrire au JOUEUR se "
        "fait avec `text.draw` (une police, une entrée de la table de textes, "
        "donc traduisible). Une trace pour le DÉVELOPPEUR, c'est `debug:log(...)` "
        "— elle sort par le journal mGBA, pas par l'écran du jeu, et disparaît "
        "des builds release."),

    # ── Itération ─────────────────────────────────────────────────
    "pairs": Refusal(
        "pairs(t)",
        "`pairs` n'existe pas : il n'y a pas de table Lua à parcourir. Un "
        "tableau se parcourt par son index — `for i = 1, #t do`."),
    "ipairs": Refusal(
        "ipairs(t)",
        "`ipairs` n'existe pas : un tableau se parcourt par son index — "
        "`for i = 1, #t do`, et `#t` est connu au build."),
    "next": Refusal(
        "next(t)",
        "`next` n'existe pas : il n'y a pas de table Lua à parcourir."),
    "select": Refusal(
        "select(n, ...)",
        "`select` n'existe pas : rien n'a d'arguments variables, un script ne "
        "déclarant pas de fonction."),
    "unpack": Refusal(
        "unpack(t)",
        "`unpack` n'existe pas : un tableau ne se répand pas en arguments, "
        "faute d'appel à arité variable."),

    # ── Types et conversions ──────────────────────────────────────
    "type": Refusal(
        "type(x)",
        "`type` n'existe pas : il n'y a rien à interroger. Une valeur est un "
        "entier, un vec2/vec3, ou un tableau d'entiers — et son type est connu "
        "au build, jamais à l'exécution."),
    "tostring": Refusal(
        "tostring(x)",
        "`tostring` n'existe pas : le moteur n'a pas de chaîne manipulable. "
        "Pour afficher un nombre, mets un marqueur de valeur dans l'entrée de "
        "texte (« Score : $mon_global ») et appelle `text.draw`."),
    "tonumber": Refusal(
        "tonumber(s)",
        "`tonumber` n'existe pas : il n'y a pas de chaîne à convertir. Les "
        "seules chaînes d'un script sont des NOMS cités du projet, résolus au "
        "build."),

    # ── Erreurs ───────────────────────────────────────────────────
    "pcall": Refusal(
        "pcall(f)",
        "il n'y a pas d'exception : le C généré n'a ni pile de déroulement ni "
        "gestionnaire. Une condition qui doit être vraie se teste avec un "
        "`if`."),
    "xpcall": Refusal(
        "xpcall(f, h)",
        "il n'y a pas d'exception : le C généré n'a ni pile de déroulement ni "
        "gestionnaire."),
    "error": Refusal(
        "error(msg)",
        "`error` n'existe pas : il n'y a pas d'exception à lever, et pas de "
        "console où la lire. Ce qui doit être vrai se vérifie avec un `if`, et "
        "ce qui doit être vrai AU BUILD est le métier du checker."),
    "assert": Refusal(
        "assert(c)",
        "`assert` n'existe pas : pas d'exception, pas de console. Un `if` qui "
        "corrige la valeur fautive vaut mieux qu'un arrêt qu'on ne verrait "
        "pas."),

    # ── Tables et métatables ──────────────────────────────────────
    "setmetatable": Refusal(
        "setmetatable(t, mt)",
        "il n'y a pas de métatable : il n'y a pas de table Lua. Un tableau du "
        "langage est un bloc d'entiers de taille fixe, sans comportement."),
    "getmetatable": Refusal(
        "getmetatable(t)",
        "il n'y a pas de métatable : il n'y a pas de table Lua."),
    "rawget": Refusal("rawget(t, k)", "il n'y a pas de table Lua."),
    "rawset": Refusal("rawset(t, k, v)", "il n'y a pas de table Lua."),
    "rawequal": Refusal("rawequal(a, b)", "il n'y a pas de table Lua."),
    "rawlen": Refusal(
        "rawlen(t)",
        "il n'y a pas de table Lua. La taille d'un tableau est `#t`, une "
        "constante de compilation."),

    # ── Exécution ─────────────────────────────────────────────────
    "collectgarbage": Refusal(
        "collectgarbage()",
        "il n'y a pas de ramasse-miettes : rien n'est alloué à l'exécution. "
        "Toute la mémoire est décidée au build, et c'est ce qui rend son coût "
        "visible."),
    "load": Refusal(
        "load(src)",
        "on ne charge pas de code à l'exécution : tout est transpilé en C et "
        'cuit dans la ROM. `require("behaviors/nom")` est la seule forme '
        "d'import, résolue au build."),
    "loadstring": Refusal(
        "loadstring(src)",
        "on ne charge pas de code à l'exécution : tout est transpilé en C et "
        "cuit dans la ROM."),
    "dofile": Refusal(
        "dofile(chemin)",
        "il n'y a pas de système de fichiers dans une ROM. "
        '`require("behaviors/nom")` importe un behavior, au build.'),
    "loadfile": Refusal(
        "loadfile(chemin)",
        "il n'y a pas de système de fichiers dans une ROM. "
        '`require("behaviors/nom")` importe un behavior, au build.'),

    # ── `math`, le faux ami ───────────────────────────────────────
    # Le module existe, sous le même nom, avec un AUTRE contenu — le pire cas
    # possible : celui où l'auteur a raison de ne pas vérifier. Les membres
    # absents qui ont une issue sont nommés ici ; les autres tombent sur
    # `unknown_member_message`, qui liste ce que le module offre vraiment.
    "math.floor": Refusal(
        "math.floor(x)",
        "`math.floor` n'existe pas, et n'a rien à faire : le moteur est "
        "entièrement entier, il n'y a rien à arrondir. `/` tronque déjà vers "
        "zéro."),
    "math.ceil": Refusal(
        "math.ceil(x)",
        "`math.ceil` n'existe pas : le moteur est entièrement entier. Pour "
        "arrondir au-dessus d'une division, `(a + b - 1) / b`."),
    "math.random": Refusal(
        "math.random(a, b)",
        "le tirage aléatoire s'écrit `math.rand(lo, hi)` — ce `math`-ci est "
        "celui du moteur, pas celui de Lua."),
    "math.randomseed": Refusal(
        "math.randomseed(n)",
        "la graine n'est pas exposée : `math.rand(lo, hi)` suffit au script, "
        "et le moteur possède sa suite."),
    "math.pi": Refusal(
        "math.pi",
        "il n'y a pas de flottant dans le moteur, donc pas de π. Les angles "
        "s'écrivent en DEGRÉS : `math.sin(90)`, `math.cos(180)`."),
    "math.huge": Refusal(
        "math.huge",
        "il n'y a pas d'infini : les valeurs sont des entiers 32 bits. Une "
        "borne s'écrit en clair."),
    "math.pow": Refusal(
        "math.pow(x, n)",
        "`math.pow` n'existe pas : une puissance entière s'écrit en "
        "multipliant (`x * x`)."),
    "math.fmod": Refusal(
        "math.fmod(a, b)",
        "`math.fmod` n'existe pas : le reste entier est l'opérateur `%`."),
    "math.modf": Refusal(
        "math.modf(x)",
        "`math.modf` n'existe pas : il n'y a pas de partie fractionnaire, "
        "toutes les valeurs sont entières."),
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
    return (f"le module `{module}` n'a pas de `{member}`. Il offre : {liste}. "
            f"(Ce sont les fonctions du moteur, pas celles de Lua.)")


def unknown_call_message(key: str) -> str:
    """Un appel qui n'est ni du catalogue, ni un constructeur du langage, ni un
    behavior importé. Il était TOLÉRÉ jusqu'ici, au motif que ce pouvait être un
    helper écrit par l'utilisateur — sauf que le codegen l'émettait tel quel
    (`math.floor(x)` partait en C avec son point), donc la faute ne remontait
    qu'au `make`, sur la ligne générée."""
    if "." in key:
        module = key.split(".", 1)[0]
        return (f"`{key}()` : le module `{module}` n'existe pas. Les modules "
                f"disponibles sont ceux du catalogue (panneau API du Script "
                f"Editor) ; un behavior s'importe par "
                f'`require("behaviors/nom")` et s\'appelle par son alias.')
    return (f"`{key}()` : fonction inconnue. Un script n'a pas de fonction à "
            f"lui — les appels possibles sont ceux du catalogue, les "
            f"constructeurs du langage (`vec2`, `vec3`, `rect`, `array`), "
            f"`require`, et les méthodes d'un behavior importé.")


# ─── Contrôle de couverture ───────────────────────────────────────

def covered_nodes() -> frozenset:
    """Les nœuds que ce fichier classe — traduits, refusés ou structurels.

    Rendu par une fonction et non par les tables : le contrôle
    (`validator._check_lua_subset`) demande « ce nœud t'est-il connu ? », pas la
    mécanique interne. Pendant exact de `checker.covered_domains()`."""
    return frozenset(ACCEPTED) | frozenset(REFUSED) | frozenset(STRUCTURAL)
