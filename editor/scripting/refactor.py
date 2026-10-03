"""
editor/scripting/refactor.py — références d'assets dans les scripts Lua.

Renommer une scène, un sfx, un prefab… dans l'éditeur doit mettre à jour les
scripts qui citent l'ancien nom. `Project.rename_*` répare déjà les références
côté DONNÉES (composants, layers de scène) ; ce module fait la même chose côté
SCRIPTS.

Le repérage est **structurel**, jamais textuel : on relit l'AST luaparser et on
ne retient que les arguments dont `RUNTIME_API` déclare le domaine (cf.
api.Param.domain). Conséquence directe : un commentaire qui mentionne "PONG",
ou un `local titre = "PONG"` sans rapport, ne sont pas touchés — seul
`scene:switch("PONG")` l'est. C'est la même table que celle qui pilote le
checker et le codegen : ajouter un domaine profite aux trois.

La réécriture remplace les littéraux par leur position exacte dans le texte
source (offsets luaparser), de droite à gauche — le reste du fichier, y compris
la mise en forme et les commentaires, est préservé octet pour octet.

Usage :
    refs = find_refs_in_project(project, DOMAIN_SCENE, "Arène")
    n    = rename_in_project(project, DOMAIN_SCENE, "Arène", "PONG")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import re

from .api import (RUNTIME_API, RUNTIME_PROPS, REF_TYPES, REF_ACTOR, PARAM_STR, DOMAIN_UI_ELEMENT,
                  MODULE_CALLS)

from .parser import DATA_NS

try:
    from luaparser import ast as _lua_ast, astnodes as _nodes
    _LUAPARSER_OK = True
except ImportError:                       # même repli que scripting/parser.py
    _LUAPARSER_OK = False


# ── Table domaine → sites d'appel ─────────────────────────────────
# Construite une fois depuis RUNTIME_API : {clé API: {index arg: domaine}}.
# Aucune liste de fonctions codée en dur ici — déclarer un `domain` sur un
# paramètre suffit à le rendre renommable.

def _reference_sites() -> dict[str, dict[int, str]]:
    sites: dict[str, dict[int, str]] = {}
    for key, fn in RUNTIME_API.items():
        for i, p in enumerate(fn.params):
            if p.ptype == PARAM_STR and p.domain:
                sites.setdefault(key, {})[i] = p.domain
    return sites


_SITES = _reference_sites()


@dataclass(frozen=True)
class LuaRef:
    """Un littéral de script qui référence un asset nommé."""
    path:    Path
    domain:  str
    value:   str
    line:    int
    start:   int   # offset du littéral dans le texte source, guillemets INCLUS
    stop:    int   # offset du dernier caractère (inclusif, convention luaparser)
    api_key: str   # "scene.switch", "sfx.play"… — pour l'affichage


# ── Repérage ──────────────────────────────────────────────────────

def _call_key(node) -> Optional[str]:
    """Clé RUNTIME_API d'un noeud d'appel luaparser, ou None.

    Reproduit la résolution du checker (`Checker._call_key`) sur l'AST brut :
    `Name` → "array", `Index(Name, field)` → "sfx.play", `Invoke` →
    "self:play_anim"."""
    if isinstance(node, _nodes.Invoke):
        method = getattr(node.func, "id", None)
        # `sfx:play(…)`, `interface:get(…)` : la méthode d'un MODULE du moteur est l'entrée
        # `module.fonction` du catalogue (cf. `api.MODULE_CALLS`).
        source = node.source
        if method and isinstance(source, _nodes.Name) and source.id in MODULE_CALLS:
            return f"{source.id}.{method}"
        return f"{REF_ACTOR}:{method}" if method else None
    if isinstance(node, _nodes.Call):
        func = node.func
        if isinstance(func, _nodes.Name):
            return func.id
        if isinstance(func, _nodes.Index) and isinstance(func.value, _nodes.Name):
            field = getattr(func.idx, "id", None)
            return f"{func.value.id}.{field}" if field else None
    return None


def _element_of_source(source, elems: dict) -> Optional[str]:
    """Le nom de l'élément d'interface qu'un récepteur désigne : `interface:get("Menu")`
    lui-même, ou un `local` qui n'en a tenu qu'un seul (`elems`)."""
    if isinstance(source, (_nodes.Call, _nodes.Invoke)) and _call_key(source) == "interface.get":
        args = source.args or []
        return args[0].raw if args and isinstance(args[0], _nodes.String) else None
    if isinstance(source, _nodes.Name):
        return elems.get(source.id)
    return None


def _element_locals(tree) -> dict[str, Optional[str]]:
    """{variable: élément d'interface} — `local menu = interface:get("Menu")`. Un local
    réaffecté à un AUTRE élément vaut None : on ne conclut rien."""
    out: dict[str, Optional[str]] = {}
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.LocalAssign, _nodes.Assign)):
            continue
        for target, value in zip(node.targets or [], node.values or []):
            if (isinstance(target, _nodes.Name) and isinstance(value, (_nodes.Call, _nodes.Invoke))
                    and _call_key(value) == "interface.get"):
                element = _element_of_source(value, {})
                out[target.id] = None if target.id in out and out[target.id] != element else element
    return out


def _node_key(node, elems: dict) -> Optional[str]:
    """`_call_key`, plus les méthodes d'un ÉLÉMENT d'interface : `box:draw("k")` sur
    `interface:get("Box")` (ou un local qui le tient) est l'entrée `text_region:draw`.
    Le repérage est structurel, comme le reste : la méthode se cherche dans le
    catalogue, sur les types de référence, jamais dans une liste écrite ici."""
    if isinstance(node, _nodes.Invoke):
        method = getattr(node.func, "id", None)
        if isinstance(node.source, _nodes.Name) and node.source.id in MODULE_CALLS:
            return _call_key(node)            # `interface:get(…)` : la fonction d'un module
        if method and _element_of_source(node.source, elems) is not None:

            for ref in REF_TYPES:
                if f"{ref}:{method}" in RUNTIME_API:
                    return f"{ref}:{method}"
        return f"{REF_ACTOR}:{method}" if method else None
    return _call_key(node)


def _ref_locals(tree) -> dict[str, str]:
    """{variable: type de référence} — `local hb = self:collision_box("x")` fait
    de `hb` une `collision_box`. Même relevé que le checker, sur l'AST brut."""
    out: dict[str, str] = {}
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.LocalAssign, _nodes.Assign)):
            continue
        for target, value in zip(node.targets or [], node.values or []):
            if isinstance(target, _nodes.Name) and isinstance(value, (_nodes.Call, _nodes.Invoke)):
                api = RUNTIME_API.get(_call_key(value) or "")
                if api and api.ret in REF_TYPES:
                    out[target.id] = api.ret
    return out


def _iter_prop_refs(tree, text: str, path, domain, value) -> Iterator[LuaRef]:
    """Les littéraux qu'une PROPRIÉTÉ à domaine se compare à — `hb.tag ==
    "hitbox"`. Ils citent le nom du projet exactement comme l'argument d'une
    fonction, et un renommage qui les oubliait laisserait une comparaison que le
    checker refuse. Seul le type de la variable dit de quelle propriété il
    s'agit (`self.tag` est l'acteur, `hb.tag` la boîte), d'où `_ref_locals`."""
    refs = _ref_locals(tree)
    # `self` est aussi un récepteur : `self.anim == "walk"`, `self.active_sprite ==
    # "blesse"` citent un nom du projet comme `hb.tag == "hitbox"`. Le type est
    # « self » : la clé RUNTIME_PROPS est `self.<propriété>`. (`other.anim` n'y
    # figure pas : son nom appartient à un autre acteur, le checker le refuse.)
    refs.setdefault("self", REF_ACTOR)
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.EqToOp, _nodes.NotEqToOp)):
            continue
        for side, other in ((node.left, node.right), (node.right, node.left)):
            if not (isinstance(side, _nodes.Index) and isinstance(side.value, _nodes.Name)
                    and isinstance(other, _nodes.String)):
                continue
            ref = refs.get(side.value.id)
            prop = RUNTIME_PROPS.get(f"{ref}.{getattr(side.idx, 'id', '')}") if ref else None
            if prop is None or not prop.domain:
                continue
            if domain is not None and prop.domain != domain:
                continue
            if value is not None and other.raw != value:
                continue
            yield LuaRef(
                path=path or Path(""), domain=prop.domain, value=other.raw,
                line=text.count("\n", 0, other.start_char) + 1,
                start=other.start_char, stop=other.stop_char,
                api_key=f"{ref}.{side.idx.id}",
            )


def iter_refs(text: str, path: Path | None = None,
              domain: str | None = None,
              value: str | None = None) -> Iterator[LuaRef]:
    """Parcourt les références d'un script. `domain`/`value` filtrent ;
    sans filtre, retourne toute la surface de référence du fichier (c'est
    la base d'un futur graphe de dépendances)."""
    if not _LUAPARSER_OK:
        return
    try:
        tree = _lua_ast.parse(text)
    except Exception:  # tolerated: unparsable script: the validator reports it, nothing is rewritten
        return   # script non parsable : aucune réécriture (cf. rename_in_text)

    yield from _iter_prop_refs(tree, text, path, domain, value)

    elems = _element_locals(tree)
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.Call, _nodes.Invoke)):
            continue
        key = _node_key(node, elems)
        arg_domains = _SITES.get(key or "")
        if not arg_domains:
            continue
        for i, arg in enumerate(node.args or []):
            dom = arg_domains.get(i)
            if dom is None or not isinstance(arg, _nodes.String):
                continue
            if domain is not None and dom != domain:
                continue
            if value is not None and arg.raw != value:
                continue
            # Ligne recalculée depuis l'offset : `String.line` de luaparser
            # lève dès que le noeud n'a pas conservé ses tokens.
            yield LuaRef(
                path=path or Path(""), domain=dom, value=arg.raw,
                line=text.count("\n", 0, arg.start_char) + 1,
                start=arg.start_char, stop=arg.stop_char,
                api_key=key or "",
            )


# ── Réécriture ────────────────────────────────────────────────────

def rename_in_text(text: str, domain: str, old: str, new: str) -> tuple[str, int]:
    """(texte réécrit, nombre de remplacements). Texte inchangé si le script
    ne parse pas — mieux vaut une référence non mise à jour, signalée par le
    checker au build, qu'un fichier corrompu par une substitution à l'aveugle."""
    refs = sorted(iter_refs(text, domain=domain, value=old),
                  key=lambda r: r.start, reverse=True)
    if not refs:
        return text, 0
    out = text
    for r in refs:
        # On ne réécrit que le CONTENU : les guillemets d'origine (" ou ')
        # et l'échappement restent ceux de l'auteur.
        literal = out[r.start:r.stop + 1]
        quote   = literal[0]
        out = out[:r.start] + f"{quote}{new}{quote}" + out[r.stop + 1:]
    return out, len(refs)


# ── Portée projet ─────────────────────────────────────────────────

def script_paths(project) -> list[Path]:
    """Tous les .lua du projet, où qu'ils soient rangés sous `scripts_dir`.

    Un dossier par famille de propriétaire faisait oublier des scripts : ceux de CAMÉRA
    manquaient à la liste, donc un `scene:switch("Arène")` écrit dans l'un d'eux n'était
    pas réécrit par un renommage de scène, et la faute ne remontait qu'au build suivant.
    Parcourir `scripts_dir` d'un bloc ne peut plus rien oublier."""
    scripts_dir = getattr(project, "scripts_dir", None)
    if not scripts_dir or not Path(scripts_dir).exists():
        return []
    return sorted(Path(scripts_dir).rglob("*.lua"))


def find_refs_in_project(project, domain: str, name: str) -> dict[Path, list[LuaRef]]:
    """{script: références} — pour une vue « utilisations » ou un aperçu de
    renommage. N'écrit rien."""
    found: dict[Path, list[LuaRef]] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        refs = list(iter_refs(text, path=p, domain=domain, value=name))
        if refs:
            found[p] = refs
    return found


@dataclass(frozen=True)
class LuaCallSite:
    """Un appel d'API et les littéraux qu'il pose, RANGÉS PAR DOMAINE.

    `iter_refs` rend les références une par une : de quoi renommer, pas de quoi
    confronter deux arguments du même appel — or « ce texte tient-il dans cette
    zone ? » est exactement une question sur la PAIRE."""
    path:    Path
    api_key: str
    line:    int
    values:  dict     # domaine → littéral (le premier de ce domaine)


def iter_call_sites(text: str, path: Path | None = None,
                    *domains: str) -> Iterator[LuaCallSite]:
    """Appels dont les littéraux couvrent TOUS les `domains` demandés.

    Le repérage reste structurel, comme `iter_refs` : la position des arguments
    vient de `RUNTIME_API`, jamais d'un ordre écrit ici. C'est ce qui a fait que
    le réordonnancement de la famille `text.*` n'a rien eu à déclarer, et ce qui
    fera qu'une future primitive « zone + clé » sera couverte sans y toucher."""
    if not _LUAPARSER_OK:
        return
    try:
        tree = _lua_ast.parse(text)
    except Exception:  # tolerated: unparsable script: the validator reports it, nothing is rewritten
        return

    elems = _element_locals(tree)
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.Call, _nodes.Invoke)):
            continue
        key = _node_key(node, elems)
        arg_domains = _SITES.get(key or "")
        if not arg_domains:
            continue
        values: dict = {}
        # L'ÉLÉMENT sur lequel la méthode s'appelle est lui aussi un littéral du projet :
        # `box:draw("k")` pose la paire (zone, texte) exactement comme `draw_text("box", "k")`.
        if isinstance(node, _nodes.Invoke):
            element = _element_of_source(node.source, elems)
            if element is not None:
                values[DOMAIN_UI_ELEMENT] = element
        first_at = None
        for i, arg in enumerate(node.args or []):
            dom = arg_domains.get(i)
            if dom is None or not isinstance(arg, _nodes.String):
                continue
            values.setdefault(dom, arg.raw)
            if first_at is None:
                first_at = arg.start_char
        if domains and not all(d in values for d in domains):
            continue
        yield LuaCallSite(
            path=path or Path(""), api_key=key or "",
            line=text.count("\n", 0, first_at) + 1 if first_at is not None else 0,
            values=values,
        )


def domain_args_in_text(text: str, domain: str) -> tuple[set[str], bool]:
    """({noms littéralement cités dans ce domaine}, y a-t-il un argument CALCULÉ ?)

    Le second booléen est ce qui manque à `iter_refs`, qui ne voit que les
    chaînes littérales : « ce script ne cite aucune police » et « ce script
    choisit sa police au runtime » y sont indiscernables. Pour un renommage
    l'amalgame est sans conséquence — il n'y a rien à réécrire dans les deux cas.
    Pour une RÉSERVATION de VRAM il est dangereux : on réserverait trop peu, et
    le texte irait écrire dans les tuiles du décor sans que rien ne le dise.

    Un script illisible ou non analysable rend `True` pour la même raison :
    l'ignorance doit se propager, jamais se confondre avec une réponse vide.
    C'est aussi le comportement quand luaparser est absent."""
    if not _LUAPARSER_OK:
        return set(), True
    try:
        tree = _lua_ast.parse(text)
    except Exception:  # tolerated: unparsable script: the validator reports it, nothing is rewritten
        return set(), True

    names: set[str] = set()
    dynamic = False
    elems = _element_locals(tree)
    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.Call, _nodes.Invoke)):
            continue
        arg_domains = _SITES.get(_node_key(node, elems) or "")
        if not arg_domains:
            continue
        args = node.args or []
        for i, dom in arg_domains.items():
            if dom != domain:
                continue
            if i >= len(args):
                dynamic = True          # appel mal formé : on ne conclut rien
            elif isinstance(args[i], _nodes.String):
                names.add(args[i].raw)
            else:
                dynamic = True
    return names, dynamic


def find_call_sites_in_project(project, *domains: str) -> list[LuaCallSite]:
    """Tous les appels du projet couvrant `domains`, en un seul parcours."""
    out: list[LuaCallSite] = []
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out += list(iter_call_sites(text, p, *domains))
    return out


def index_refs_in_project(project, domain: str) -> dict[str, dict[Path, int]]:
    """{valeur référencée: {script: nombre d'occurrences}} pour tout un domaine.

    Un SEUL parcours des scripts couvre toutes les valeurs du domaine, là où
    `find_refs_in_project` reparse tout pour un seul nom. C'est ce qu'il faut à
    une vue « utilisé par » posée sur une table entière : l'utilisateur passe
    d'une entrée à l'autre sans relancer luaparser à chaque sélection."""
    index: dict[str, dict[Path, int]] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for ref in iter_refs(text, path=p, domain=domain):
            index.setdefault(ref.value, {}).setdefault(p, 0)
            index[ref.value][p] += 1
    return index


# ── Tables de données, globals, constantes — le second type de site ──
#
# Tout ce qui précède repère une référence dans un ARGUMENT littéral d'appel,
# et sa table de sites dérive de `RUNTIME_API`. Une table de données, une
# variable globale ou une constante, elles, se citent comme du CODE :
# `data.Objets[i].prix`, `global.score`, `const.max` — sans guillemets et sans
# appel (ROADMAP v0.20 pour les tableaux, chantier global/const pour l'accès
# pointé qui a remplacé global.get/set et const.get). Invisibles à
# `iter_refs`, un renommage les laisserait derrière.
#
# Le repérage reste STRUCTUREL — c'est l'AST qui dit quelles occurrences sont
# des citations, jamais une recherche de texte. Mais la réécriture ne peut pas
# s'appuyer sur la position du NOM : dans cette version de luaparser, un noeud
# `Name` ne porte pas d'offsets (`start_char` vaut None). Seuls les noeuds
# `Index` en ont, et leur tranche se termine par le nom cherché. On relit donc
# cette tranche et on ne réécrit que si elle finit bien par `.<nom>` — repérage
# par l'arbre, écriture vérifiée sur le texte.


@dataclass(frozen=True)
class DataRef:
    """Une citation de table de données dans un script."""
    path:   Path
    table:  str
    column: Optional[str]   # None → c'est la TABLE qui est citée
    line:   int
    start:  int             # offset du nom lui-même
    stop:   int             # offset du dernier caractère (inclusif)


def _table_of(node) -> Optional[str]:
    """`data.Objets` → "Objets", pour tout autre noeud → None."""
    if (isinstance(node, _nodes.Index)
            and node.notation == _nodes.IndexNotation.DOT
            and isinstance(node.value, _nodes.Name)
            and node.value.id == DATA_NS):
        return getattr(node.idx, "id", None)
    return None


def _tail_span(text: str, node, name: str) -> Optional[tuple[int, int]]:
    """Position du `name` final dans la tranche source de `node`, ou None si la
    tranche ne se termine pas par `.name` — auquel cas on n'écrit rien."""
    start, stop = getattr(node, "start_char", None), getattr(node, "stop_char", None)
    if start is None or stop is None:
        return None
    m = re.search(r"\.\s*(" + re.escape(name) + r")\s*$", text[start:stop + 1])
    return (start + m.start(1), start + m.end(1) - 1) if m else None


def iter_data_refs(text: str, path: Path | None = None,
                   table: str | None = None,
                   column: str | None = None) -> Iterator[DataRef]:
    """Citations de tables de données. `table` filtre la table ; `column`
    demande les citations de CETTE colonne au lieu de celles de la table."""
    if not _LUAPARSER_OK:
        return
    try:
        tree = _lua_ast.parse(text)
    except Exception:  # tolerated: unparsable script: the validator reports it, nothing is rewritten
        return

    def _line(off: int) -> int:
        return text.count("\n", 0, off) + 1

    for node in _lua_ast.walk(tree):
        if not isinstance(node, _nodes.Index):
            continue

        # `data.Objets` — la table elle-même.
        if column is None:
            name = _table_of(node)
            if name and (table is None or name == table):
                span = _tail_span(text, node, name)
                if span:
                    yield DataRef(path=path or Path(""), table=name, column=None,
                                  line=_line(span[0]), start=span[0], stop=span[1])
            continue

        # `data.Objets[…].prix` — la colonne. Le noeud porte le `.prix` ; sous
        # lui, une indexation par crochets, et sous elle la table.
        if node.notation != _nodes.IndexNotation.DOT:
            continue
        field = getattr(node.idx, "id", None)
        if field != column or not isinstance(node.value, _nodes.Index):
            continue
        if node.value.notation != _nodes.IndexNotation.SQUARE:
            continue
        owner = _table_of(node.value.value)
        if owner is None or (table is not None and owner != table):
            continue
        span = _tail_span(text, node, field)
        if span:
            yield DataRef(path=path or Path(""), table=owner, column=field,
                          line=_line(span[0]), start=span[0], stop=span[1])


def _rewrite_data_refs(text: str, refs: list[DataRef], new: str) -> tuple[str, int]:
    """Remplace chaque nom repéré, de droite à gauche — le reste du fichier,
    mise en forme et commentaires compris, est préservé octet pour octet."""
    out = text
    for r in sorted(refs, key=lambda r: r.start, reverse=True):
        out = out[:r.start] + new + out[r.stop + 1:]
    return out, len(refs)


def rename_data_table_in_project(project, old: str, new: str) -> dict[Path, int]:
    """Réécrit `data.<old>` en `data.<new>` dans tous les scripts."""
    return _rename_by_position(project, new,
                               lambda text, p: list(iter_data_refs(text, p, table=old)))


def rename_data_column_in_project(project, table: str,
                                  old: str, new: str) -> dict[Path, int]:
    """Réécrit `data.<table>[…].<old>` en `.<new>`. La table est exigée : deux
    tables peuvent avoir une colonne du même nom sans rapport l'une avec
    l'autre."""
    return _rename_by_position(project, new,
                               lambda text, p: list(iter_data_refs(text, p, table=table,
                                                                   column=old)))


def _rename_by_position(project, new: str, find) -> dict[Path, int]:
    """Cherche puis réécrit, script par script — commun à tout ce qui se
    renomme par POSITION plutôt que par littéral (tables de données, globals,
    constantes : `find` rend une liste d'objets `.start`/`.stop`, peu importe
    leur type exact)."""
    changed: dict[Path, int] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        refs = find(text, p)
        if not refs:
            continue
        new_text, n = _rewrite_data_refs(text, refs, new)
        p.write_text(new_text, encoding="utf-8")
        changed[p] = n
    return changed


# ── Globals et constantes — même second type de site ──────────────
#
# `global.nom` / `global.nom[i]` / `const.nom` (chantier global/const) : le même
# repérage que `data.Objets`, un seul niveau de namespace en moins. `_ns_field`
# est `_table_of` généralisé au namespace ("global" ou "const" au lieu de
# `DATA_NS` figé) ; `iter_var_refs` couvre les TROIS formes d'un coup, parce
# que `global.nom[i]` porte le même noeud `Index(global, nom)` QUE `global.nom`
# nu — seul ce qui l'ENTOURE diffère, pas le noeud à renommer.

@dataclass(frozen=True)
class VarRef:
    """Une citation de variable globale ou de constante, par IDENTIFIANT."""
    path: Path
    ns:   str    # "global" | "const"
    name: str
    line: int
    start: int
    stop:  int


def _ns_field(node, ns: str) -> Optional[str]:
    """`ns.nom` (ex: global.score) → "score", pour tout autre noeud → None."""
    if (isinstance(node, _nodes.Index)
            and node.notation == _nodes.IndexNotation.DOT
            and isinstance(node.value, _nodes.Name)
            and node.value.id == ns):
        return getattr(node.idx, "id", None)
    return None


def iter_var_refs(text: str, path: Path | None = None,
                  ns: str = "global", name: str | None = None) -> Iterator[VarRef]:
    """Citations de `ns.<name>` (`ns` = "global" ou "const"). `name` filtre le
    nom ; sans lui, toutes les citations de ce namespace."""
    if not _LUAPARSER_OK:
        return
    try:
        tree = _lua_ast.parse(text)
    except Exception:  # tolerated: unparsable script: the validator reports it, nothing is rewritten
        return

    def _line(off: int) -> int:
        return text.count("\n", 0, off) + 1

    for node in _lua_ast.walk(tree):
        found = _ns_field(node, ns)
        if not found or (name is not None and found != name):
            continue
        span = _tail_span(text, node, found)
        if span:
            yield VarRef(path=path or Path(""), ns=ns, name=found,
                        line=_line(span[0]), start=span[0], stop=span[1])


def rename_var_in_project(project, ns: str, old: str, new: str) -> dict[Path, int]:
    """Réécrit `global.<old>` (ou `const.<old>`) en `<new>` dans tous les
    scripts, quelle que soit la forme (nue, indexée). `Project.rename_variable`
    l'appelle EN PLUS de `rename_lua_refs(DOMAIN_GLOBAL, …)` — celui-ci reste
    nécessaire pour `save:read(slot, "nom")`, qui cite le nom en chaîne."""
    return _rename_by_position(project, new,
                               lambda text, p: list(iter_var_refs(text, p, ns=ns, name=old)))


def rename_in_project(project, domain: str, old: str, new: str) -> dict[Path, int]:
    """Réécrit toutes les références `old` → `new` du domaine donné dans les
    scripts du projet. Retourne {script: nombre de remplacements} (vide si
    rien n'a bougé). Sans effet si old == new."""
    return rename_in_files(script_paths(project), domain, old, new)


def rename_in_files(paths, domain: str, old: str, new: str) -> dict[Path, int]:
    """Comme `rename_in_project`, mais sur les seuls scripts donnés : un nom qui
    n'a de sens que pour UN propriétaire (l'`id` d'un composant sprite d'un acteur)
    ne se réécrit pas chez les autres, qui peuvent avoir le leur, identique."""
    if not old or not new or old == new:
        return {}
    changed: dict[Path, int] = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, n = rename_in_text(text, domain, old, new)
        if n:
            p.write_text(new_text, encoding="utf-8")
            changed[p] = n
    return changed
