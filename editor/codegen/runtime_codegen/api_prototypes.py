"""codegen/runtime_codegen/api_prototypes.py — les prototypes de l'API, GÉNÉRÉS.

Le « 4e lecteur » : `checker`, `codegen` et `refactor` lisent `scripting/api.py`
(source unique de ce qui est exposé), mais les PROTOTYPES C que les unités de
scène/acteur voyaient vivaient à la main dans `runtime_api_inline.h`, seulement
SURVEILLÉS. Une fonction exposée et non redéclarée passait le checker, s'émettait,
et échouait au `make` sur un « implicit declaration ».

Ici, ils ne sont plus surveillés mais DÉRIVÉS : `api.py` dit QUELLES fonctions
sont exposées, `gba_engine.h` porte LEUR signature exacte, et ce module recopie
la signature du sous-ensemble exposé. La signature reste au seul endroit qui la
possède déjà (le moteur) ; personne ne la ressaisit.

Une fonction exposée mais résolue AILLEURS (méthode d'acteur, `scene_switch`,
`sfx_play`, helpers de globals — générés dans `runtime_api.h`) n'est pas dans
`gba_engine.h` : elle est simplement absente du résultat, sans erreur, exactement
comme l'ancienne surveillance ne l'exigeait pas.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Un identifiant C précédé de non-mot, suivi d'une parenthèse ouvrante.
_CALL = r"(?<![\w])%s\s*\("
# Le même motif pour N'IMPORTE QUEL identifiant : un identifiant entier suivi de `(`, donc les mêmes occurrences que `_CALL`.
_ANY_CALL = re.compile(r"(?<![\w])(\w+)\s*\(")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def _norm(s: str) -> str:
    """Espaces réduits, et pas d'espace avant la parenthèse — pour comparer et
    émettre une forme stable."""
    return re.sub(r"\s+", " ", s).replace(" (", "(").strip()


def _declaration_at(engine_src: str, start: int, name: str) -> str | None:
    """`ret name(params)` si l'occurrence de `name` à `start` est une DÉCLARATION, None si c'est un appel au milieu de
    code. Les parenthèses sont équilibrées : un paramètre qui contient une parenthèse (rare) ne coupe pas la capture."""
    i = engine_src.index("(", start)
    depth, j = 0, i
    while j < len(engine_src):
        c = engine_src[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    params = engine_src[i + 1:j]
    line_start = engine_src.rfind("\n", 0, start) + 1
    pre = engine_src[line_start:start]
    pre = re.sub(r"\b(static|inline|GBA_ENGINE_IMPL)\b", "", pre).strip()
    # Un vrai en-tête de déclaration/définition : un type de retour nu. Un
    # `;`/`{`/`}`/`=`/`,` dans `pre` trahit un APPEL au milieu de code (corps
    # de fonction, affectation, argument) et non une déclaration.
    if not pre or any(ch in pre for ch in ";{}=,"):
        return None
    return _norm(f"{pre} {name}({params})")


def extract_prototype(engine_src: str, name: str) -> str | None:
    """`ret name(params)` extrait de `engine_src` (déjà sans commentaires), ou
    None si `name` n'y est pas DÉCLARÉ (absent, ou seulement appelé/défini
    ailleurs)."""
    for m in re.finditer(_CALL % re.escape(name), engine_src):
        decl = _declaration_at(engine_src, m.start(), name)
        if decl:
            return decl
    return None


def build_prototype_block(engine_src: str, names) -> tuple[list[str], list[str]]:
    """(lignes `extern ...;`, noms non extractibles).

    `names` : les `c_func`/`c_getter`/`c_setter` exposés par le catalogue. Le
    deuxième retour liste les noms PRÉSENTS dans le moteur mais que l'extracteur
    n'a pas su lire — un cas qui ne doit pas exister (0 aujourd'hui), et que le
    build signale plutôt que d'émettre un header incomplet."""
    decls, unparsed = _prototype_block(engine_src, tuple(sorted(set(names))))
    return list(decls), list(unparsed)


@lru_cache(maxsize=4)
def _prototype_block(engine_src: str, names: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Le calcul de `build_prototype_block`, gardé par CONTENU (le moteur et les noms décident seuls du résultat) : il
    coûtait environ 1,6 s à chaque build pour un bloc qui ne change qu'avec `gba_engine.h`."""
    src = _strip_comments(engine_src)
    # Une seule passe sur le moteur : les positions de tout identifiant suivi d'une parenthèse, par nom. Une regex par
    # nom exposé relisait l'en-tête entier 211 fois ; la règle de sélection de l'occurrence reste celle d'`extract_prototype`.
    calls: dict[str, list[int]] = {}
    for m in _ANY_CALL.finditer(src):
        calls.setdefault(m.group(1), []).append(m.start())
    decls: list[str] = []
    unparsed: list[str] = []
    for name in names:
        starts = calls.get(name)
        if not starts:
            continue
        d = next((d for d in (_declaration_at(src, s, name) for s in starts) if d), None)
        if d:
            decls.append(f"extern {d};")
        else:
            unparsed.append(name)
    return tuple(decls), tuple(unparsed)


def build_enum_defines() -> list[str]:
    """`#define <constante> <valeur>` de toutes les énumérations matérielles,
    GÉNÉRÉS depuis `api.py` (source unique de leur valeur — cf.
    `hardware_enum_defines`). Émis dans `runtime_api.h`, ils ne sont plus redéclarés
    à la main dans `runtime_api_inline.h`. Alignés en colonnes pour rester lisibles.

    Ne couvre PAS `WINR_*` : les régions de window ne sont pas une énumération du
    catalogue (un nom de `WindowSlot` est propre au projet), elles restent où
    elles sont."""
    from scripting.api import hardware_enum_defines
    pairs = hardware_enum_defines()
    width = max((len(sym) for sym, _ in pairs), default=0)
    return [f"#define {sym.ljust(width)} {value}" for sym, value in pairs]


def build_window_region_defines(engine_src: str) -> list[str]:
    """`#define WINR_* <valeur>` extraits de `gba_engine.h`.

    Les régions de window ne sont PAS une énumération du catalogue (un nom de
    `WindowSlot` est propre au projet) : leur valeur vit dans le moteur, qui
    l'utilise (`case WINR_0:` …). On la recopie pour les unités de script — comme
    les prototypes — au lieu de la redéclarer à la main dans `runtime_api_inline.h`.
    Le moteur reste la source unique ; rien à comparer, la valeur ne vit qu'ici."""
    pairs = re.findall(r"^\s*#\s*define\s+(WINR_\w+)\s+(-?\d+)\b", engine_src, re.M)
    width = max((len(s) for s, _ in pairs), default=0)
    return [f"#define {s.ljust(width)} {v}" for s, v in pairs]


def exposed_engine_names() -> set[str]:
    """Les noms C exposés en Lua — fonctions de module et getters/setters de
    propriété. La méthode d'acteur (`self:`) et les cas résolus par un émetteur
    dédié n'y sont pas déclarés dans le moteur : ils tombent d'eux-mêmes."""
    from scripting.api import RUNTIME_API, RUNTIME_PROPS, REF_TYPE_TABLE
    names: set[str] = set()
    # La conversion d'un type de référence vers son parent (`RefType.to_base`) : le C émis
    # l'appelle sans qu'aucune entrée du catalogue la nomme.
    for decl in REF_TYPE_TABLE.values():
        if decl.to_base:
            names.add(decl.to_base)
    for f in RUNTIME_API.values():
        if f.c_func:
            names.add(f.c_func)
    for p in RUNTIME_PROPS.values():
        for fn in (p.c_getter, p.c_setter):
            if fn:
                names.add(fn)
    return names
