"""scripting/completion.py — le modèle d'autocomplétion du Script Editor.

Une seule question, et sans une ligne de Qt : « curseur ici, texte de la ligne
avant lui → quels candidats ? ». L'UI (`ui/script_editor/completer.py`) pose la
question et affiche la réponse ; ce fichier se teste seul, sans écran, comme
`text_layout` ou le checker.

Tout ce qui suit est **dérivé du catalogue** (`api.py`), jamais une liste écrite
à la main — même règle et même raison mesurée que `api_snippets` : une liste en
dur a proposé pendant des mois `scene_goto` et `instantiate`, deux noms qui n'ont
jamais existé. Une fonction ajoutée à `api.py` obtient sa complétion
gratuitement ; une fonction retirée perd la sienne, et la complétion ne peut donc
pas proposer une fonction morte — le seul bug qui compte ici.

L'infobulle est celle de la sidebar : `make_tooltip()` rend le même HTML des deux
côtés (cf. ROADMAP v0.27).

Périmètre — phase 1, « le catalogue seul » :
  - membres après `X.` / `X:` (fonctions, propriétés) ;
  - modules, fonctions globales, constructeurs de langage, mots-clés, handlers ;
  - valeurs d'énumération matérielle dans un argument chaîne (`"alpha"`).
Les `local`/paramètres en portée (phase 2, l'AST) et les noms d'assets du projet
dans les arguments chaîne (phase 3) viendront s'y brancher — cf. `_string_arg`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from scripting.api import (
    RUNTIME_API, RUNTIME_PROPS, HARDWARE_ENUMS,
    KNOWN_EVENTS, KNOWN_EVENTS_BY_KIND, EVENT_REGISTRY,
    STATELESS_MODULES, canonical_key,
)

from scripting.expr_types import VEC_CONSTRUCTORS
from scripting import api_snippets
from scripting.api_reference import make_tooltip
from ui.common.tooltip import tooltip


# ─── Nature d'un candidat ─────────────────────────────────────────
# L'UI la traduit en couleur/icône ; le modèle n'en connaît que le nom.
KIND_FUNCTION    = "function"
KIND_PROPERTY    = "property"
KIND_MODULE      = "module"
KIND_KEYWORD     = "keyword"
KIND_EVENT       = "event"
KIND_CONSTRUCTOR = "constructor"
KIND_ENUM        = "enum"
KIND_LOCAL       = "local"
KIND_REF         = "ref"      # un nom d'asset du projet, dans un argument chaîne


@dataclass(frozen=True)
class Candidate:
    """Un candidat de complétion.

    `insert` est ce qui remplace le mot en cours de frappe (le membre seul,
    `play_anim`) — volontairement léger : l'infobulle porte déjà la signature.
    `label` est ce que la liste affiche (`play_anim(name)`)."""
    insert:  str
    label:   str
    kind:    str
    tooltip: str


# ─── Vues dérivées du catalogue (calculées une fois) ───────────────
# `text.draw` → module `text`, membre `draw` ; `self:move` → self, `move`.

def _split(key: str) -> tuple[str, str, str]:
    """(module, séparateur, membre). `sfx.play` → (sfx, ., play) ;
    `self:move` → (self, :, move) ; `array` → ('', '', array)."""
    if ":" in key:
        mod, member = key.split(":", 1)
        return mod, ":", member
    if "." in key:
        mod, member = key.split(".", 1)
        return mod, ".", member
    return "", "", key


def _dotted_index(keys) -> dict[str, list[str]]:
    """{module: [membres]}, pour les clés POINTÉES seulement (`text.draw`), dans
    l'ordre du catalogue. Les clés à DEUX-POINTS en sont exclues à dessein :
    `sfx:stop` n'est pas un membre du module `sfx`, c'est une méthode du TYPE de
    référence rendu par `sfx.play` — elle ne s'appelle que sur un `local` qui
    tient ce handle (phase 2), pas derrière `sfx.`."""
    out: dict[str, list[str]] = {}
    for key in keys:
        mod, sep, member = _split(key)
        if mod and sep == ".":
            out.setdefault(mod, []).append(member)
    return out


_MODULE_FUNCS = _dotted_index(RUNTIME_API)   # sfx → [play], text → [draw, draw_in, …]
_MODULE_PROPS = _dotted_index(RUNTIME_PROPS)  # scene → [size, frame], camera → [bound, …]
# `self:` (méthode) et `self.` (champ) sont deux espaces distincts — la
# distinction de Lua, celle que le checker fait déjà. Les méthodes viennent des
# clés à deux-points de `RUNTIME_API` ; les propriétés des clés `self.` de
# `RUNTIME_PROPS`, rangées ci-dessus.
_SELF_METHODS = [_split(k)[2] for k in RUNTIME_API if k.startswith("actor:")]
# Les champs d'un acteur sont sous `actor.` dans le catalogue — et NE sont pas ceux du module
# `actor` (`actor:get`) : on les sort de `_MODULE_PROPS`.
_SELF_PROPS   = _MODULE_PROPS.pop("actor", [])

# Les modules du catalogue, source unique aussi pour la coloration syntaxique
# (`lua_editor.py` la lit d'ici, au lieu d'une liste tenue à la main qui citait
# encore `display`/`send`, disparus, et ignorait la moitié des modules vivants).
MODULES: tuple[str, ...] = tuple(sorted(set(_MODULE_FUNCS) | set(_MODULE_PROPS)))

# Fonctions globales — sans module (`array`).
_GLOBAL_FUNCS = [k for k in RUNTIME_API if _split(k)[0] == ""]

# Constructeurs de valeurs composées (`vec2`, `vec3`, `rect`) — leur arité vit
# dans `expr_types`, la seule chose à en dire ici est qu'ils se complètent.
_CONSTRUCTORS = tuple(VEC_CONSTRUCTORS)

# Les mots-clés proposables. Ce sont ceux du sous-ensemble ACCEPTÉ : `repeat`,
# `until`, `goto` en sont volontairement absents — `lua_subset` les REFUSE en le
# disant, et une complétion qui les proposerait enseignerait l'erreur. `require`
# vit ici : ce n'est pas un mot-clé Lua, mais c'est la seule forme d'import, et
# on la tape comme un.
KEYWORDS: tuple[str, ...] = (
    "and", "break", "do", "else", "elseif", "end", "false", "for",
    "function", "if", "in", "local", "nil", "not", "or", "require",
    "return", "then", "true", "while",
)


# ─── Infobulles ───────────────────────────────────────────────────

def _catalog_tooltip(name: str) -> str:
    """L'infobulle d'un nom du catalogue — même entrée et même rendu que la
    sidebar (`api_snippets` + `make_tooltip`)."""
    is_prop = name in RUNTIME_PROPS
    entry = (api_snippets.prop_entry_dict(name) if is_prop
             else api_snippets.entry_dict(name))
    return make_tooltip(entry)


def _event_tooltip(ev: str) -> str:
    meta = EVENT_REGISTRY.get(ev, {})
    params = meta.get("params", [])
    entry = {
        "label":       f"{ev}({', '.join(p['name'] for p in params)})",
        "description": meta.get("desc", ""),
        "params":      params,
    }
    return make_tooltip(entry)


def _plain_tooltip(sig: str, desc: str) -> str:
    """Une infobulle courte pour ce qui n'est pas dans le catalogue (module,
    mot-clé, constructeur) — même charpente visuelle que `make_tooltip`."""
    return tooltip(title=sig, body=desc)


# ─── Fabrique de candidats ────────────────────────────────────────

def _member_label(name: str) -> str:
    """Le libellé montré dans la liste : la signature, sans son préfixe de
    module — `self:play_anim(name)` → `play_anim(name)`, `text:draw(...)` →
    `draw(...)`."""
    is_prop = name in RUNTIME_PROPS
    entry = (api_snippets.prop_entry_dict(name) if is_prop
             else api_snippets.entry_dict(name))
    label = entry["label"]              # "self:play_anim(name)" / "draw(x, y, id)"
    # `entry_dict` porte le nom entier ; `prop_entry_dict` déjà juste le membre.
    head, sep, tail = label.partition("(")
    return f"{_split(head)[2]}{sep}{tail}" if sep else _split(head)[2]


def _catalog_candidate(name: str) -> Candidate:
    member = _split(name)[2]
    return Candidate(
        insert=member,
        label=_member_label(name),
        kind=KIND_PROPERTY if name in RUNTIME_PROPS else KIND_FUNCTION,
        tooltip=_catalog_tooltip(name),
    )


# ─── Analyse du contexte au curseur ───────────────────────────────
# `line_prefix` = le texte de la ligne courante jusqu'au curseur. Il suffit à la
# phase 1 : le contexte d'un membre ou d'un argument tient sur sa ligne.

_QUAL = re.compile(r"([A-Za-z_]\w*)\s*([.:])\s*(\w*)$")
_WORD = re.compile(r"(\w*)$")


def _in_comment(s: str) -> bool:
    """Le curseur est-il après un `--` de commentaire sur cette ligne ? Un `--`
    à l'intérieur d'une chaîne n'en ouvre pas un."""
    instr, esc, quote = False, False, ""
    for i, ch in enumerate(s):
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                instr = False
        elif ch in "\"'":
            instr, quote = True, ch
        elif ch == "-" and i + 1 < len(s) and s[i + 1] == "-":
            return True
    return False


def _in_string(s: str) -> bool:
    """Le curseur est-il à l'intérieur d'une chaîne ouverte sur cette ligne ?
    Un nombre impair de guillemets non échappés le dit."""
    count, esc = 0, False
    for ch in s:
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch in "\"'":
            count += 1
    return count % 2 == 1


def _value_candidates(domain: str | None, project_names: dict | None) -> list[Candidate]:
    """Les valeurs valides pour un argument de ce `domain`. Une énumération
    MATÉRIELLE (ensemble fixe du catalogue) ou un nom d'asset du PROJET — la même
    question (« que peut valoir cette chaîne ? »), deux sources. Proposer
    exactement ce que le checker accepte tient à ce que `project_names` vienne de
    `project_names.names_by_domain`, sa source à lui aussi (phase 3)."""
    if not domain:
        return []
    if domain in HARDWARE_ENUMS:
        return [
            Candidate(insert=v, label=v, kind=KIND_ENUM,
                      tooltip=_plain_tooltip(f'"{v}"', f"Valeur de « {domain} »."))
            for v in HARDWARE_ENUMS[domain]
        ]
    return [
        Candidate(insert=n, label=n, kind=KIND_REF,
                  tooltip=_plain_tooltip(f'"{n}"', f"« {domain} » du projet."))
        for n in (project_names or {}).get(domain, [])
    ]


def _string_arg(line_prefix: str, project_names: dict | None) -> list[Candidate]:
    """Candidats pour une CHAÎNE en cours de frappe, dans les deux endroits où une
    valeur nommée s'écrit : un argument d'appel (`sfx:play("…`, `layer.set_blend
    ("…`) et l'affectation ou la comparaison d'une propriété (`self.obj_mode ==
    "…`). La valeur peut être un enum matériel ou un nom du projet — cf.
    `_value_candidates`."""
    open_paren = _enclosing_paren(line_prefix)
    if open_paren >= 0:
        head = line_prefix[:open_paren]
        m = re.search(r"([A-Za-z_][\w.:]*)\s*$", head)
        fn = RUNTIME_API.get(canonical_key(m.group(1))) if m else None

        if fn is None:
            return []
        idx = _arg_index(line_prefix[open_paren + 1:])
        if idx >= len(fn.params):
            return []
        return _value_candidates(fn.params[idx].domain, project_names)
    # Hors parenthèses : une propriété dont la valeur est un NOM d'énumération
    # (`self.obj_mode = "window"`, ou la comparaison `== "window"`).
    m = re.search(r"([A-Za-z_][\w.:]*)\s*==?\s*[\"'][^\"']*$", line_prefix)
    p = RUNTIME_PROPS.get(canonical_key(m.group(1))) if m else None

    return _value_candidates(p.domain, project_names) if p is not None else []


def _enclosing_paren(s: str) -> int:
    """Index de la `(` ouvrante encore ouverte au curseur (la plus interne), ou
    -1. Les parenthèses à l'intérieur d'une chaîne sont ignorées."""
    stack: list[int] = []
    instr, esc, quote = False, False, ""
    for i, ch in enumerate(s):
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                instr = False
            continue
        if ch in "\"'":
            instr, quote = True, ch
        elif ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            stack.pop()
    return stack[-1] if stack else -1


def _arg_index(seg: str) -> int:
    """Le rang de l'argument courant : le nombre de virgules de premier niveau
    entre la `(` ouvrante et le curseur (chaînes et sous-appels ignorés)."""
    depth, instr, esc, quote, n = 0, False, False, "", 0
    for ch in seg:
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                instr = False
            continue
        if ch in "\"'":
            instr, quote = True, ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


def _member_candidates(qual: str, sep: str, project_names: dict | None,
                       context: str = "unknown") -> list[Candidate]:
    """Les membres d'un qualificateur. `self` a deux espaces (méthode `:` /
    champ `.`) ; un module n'a que le point ; `global.`/`const.` sont des accès
    pointés aux scalaires DÉCLARÉS du projet. Un qualificateur inconnu ne rend
    rien : c'est le plus souvent un `local` porteur de référence, que la phase 2
    (l'AST) saura reconnaître."""
    if qual == "self":
        # `self` est l'instance à laquelle le script est attaché : une scène et une
        # caméra n'en ont pas, le build le refuserait — on ne le propose donc pas.
        if context in ("scene", "camera"):
            return []
        members = _SELF_METHODS if sep == ":" else _SELF_PROPS
        pfx = "actor:" if sep == ":" else "actor."       # clés du catalogue ; s'écrit `self`
        return [_catalog_candidate(pfx + m) for m in members]
    if qual in MODULES:
        # Un module du moteur : ses ACTIONS derrière « : » (`sfx:play`), son ÉTAT derrière
        # « . » (`camera.bound`) ; une bibliothèque sans état (`math`) n'a que le point.
        if qual in STATELESS_MODULES:
            names = _MODULE_FUNCS.get(qual, []) if sep == "." else []
        else:
            names = _MODULE_FUNCS.get(qual, []) if sep == ":" else _MODULE_PROPS.get(qual, [])
        return sorted((_catalog_candidate(f"{qual}.{m}") for m in names),
                      key=lambda c: c.insert)
    # `global.nom` / `const.nom` — variables et constantes du projet, lues dans
    # `names_by_domain` sous la clé qui EST le qualificateur écrit.
    if sep == "." and qual in ("global", "const"):
        kind_word = "Variable" if qual == "global" else "Constante"
        return [
            Candidate(insert=n, label=n, kind=KIND_REF,
                      tooltip=_plain_tooltip(f"{qual}.{n}", f"{kind_word} « {n} » du projet."))
            for n in (project_names or {}).get(qual, [])
        ]
    return []


def _bare_candidates(context: str) -> list[Candidate]:
    """Un mot nu : modules, fonctions globales, constructeurs, mots-clés, et les
    handlers du contexte (un script de caméra n'a pas d'`on_late_update`)."""
    out: list[Candidate] = []
    for mod in MODULES:
        out.append(Candidate(insert=mod, label=mod, kind=KIND_MODULE,
                             tooltip=_plain_tooltip(mod, f"Module « {mod} » de l'API.")))
    out += [_catalog_candidate(name) for name in _GLOBAL_FUNCS]
    for ctor in _CONSTRUCTORS:
        n = VEC_CONSTRUCTORS[ctor]
        out.append(Candidate(insert=ctor, label=f"{ctor}(…)", kind=KIND_CONSTRUCTOR,
                             tooltip=_plain_tooltip(f"{ctor}(…)",
                                 f"Construit une valeur à {n} composantes.")))
    for kw in KEYWORDS:
        out.append(Candidate(insert=kw, label=kw, kind=KIND_KEYWORD,
                             tooltip=_plain_tooltip(kw, "Mot-clé du langage.")))
    for ev in KNOWN_EVENTS_BY_KIND.get(context, KNOWN_EVENTS):
        out.append(Candidate(insert=ev, label=ev, kind=KIND_EVENT,
                             tooltip=_event_tooltip(ev)))
    return out


# ─── Les noms déclarés par le script (phase 2) ────────────────────
# Un nom nu ne se complète que s'il désigne vraiment quelque chose : les `local`,
# paramètres et variables de boucle du script courant.
#
# La lecture est TEXTUELLE, pas l'AST — et à dessein. `parser.local_names` (celle
# du checker) demanderait `luaparser.parse`, ~30 ms sur un petit script et ~190 ms
# sur un gros ; appelé à chaque frappe, il rendait tout l'éditeur poussif. Une
# complétion est une SUGGESTION, pas une validation : le balayage ci-dessous coûte
# des microsecondes et repère les mêmes déclarations. Il peut sur-capturer (un
# `local` cité dans un commentaire) — une suggestion de trop, sans conséquence —,
# mais depuis le correctif multi-`local` il ne propose jamais un nom que le checker
# refuse. Le checker, lui, garde l'AST : c'est lui qui JUGE, pas la complétion.
#
# `local a, b, c` déclare les TROIS noms, capturés jusqu'au `=` ou la fin de
# ligne ; au-delà ce sont des valeurs, pas des noms.
_RE_LOCAL  = re.compile(r"\blocal\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)")
_RE_FOR    = re.compile(r"\bfor\s+([A-Za-z_]\w*)")
_RE_PARAMS = re.compile(r"\bfunction\s+[A-Za-z_][\w.:]*\s*\(([^)]*)\)")
_RE_HELPER = re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\(")


def _script_locals(source: str, cursor_line: int | None) -> set[str]:
    lines = source.split("\n")
    if cursor_line is not None and 0 <= cursor_line < len(lines):
        lines[cursor_line] = ""          # la ligne en cours de frappe n'en est pas une
    text = "\n".join(lines)
    out: set[str] = set()
    for m in _RE_LOCAL.finditer(text):
        out |= {n.strip() for n in m.group(1).split(",")}
    out |= {m.group(1) for m in _RE_FOR.finditer(text)}
    # Les helpers privés sont appelables comme les fonctions du catalogue ;
    # les proposer évite qu'ils soient les seuls noms du script invisibles à
    # l'autocomplétion. Les handlers sont inoffensifs dans cette liste : ils
    # restent filtrés par le préfixe au moment de l'insertion.
    out |= {m.group(1) for m in _RE_HELPER.finditer(text)
            if not m.group(1).startswith("on_")}
    for m in _RE_PARAMS.finditer(text):
        out |= {p.strip() for p in m.group(1).split(",")}
    return {n for n in out if n.isidentifier()}


def _local_candidates(source: str | None, line: int | None) -> list[Candidate]:
    if not source:
        return []
    return [
        Candidate(insert=n, label=n, kind=KIND_LOCAL,
                  tooltip=_plain_tooltip(n, "Variable locale ou paramètre du script."))
        for n in sorted(_script_locals(source, line))
    ]


def candidates_at(line_prefix: str, *, context: str = "unknown",
                  source: str | None = None, line: int | None = None,
                  project_names: dict | None = None) -> list[Candidate]:
    """Les candidats de complétion pour le texte de ligne `line_prefix`, dans un
    script de type `context` (actor/scene/behavior/camera/unknown).

    Trois apports facultatifs, chacun d'une phase : `source` + `line` (le script
    entier et l'index 0-based de la ligne du curseur) ajoutent à un mot nu les
    noms que le script DÉCLARE (phase 2) ; `project_names` (de
    `project_names.names_by_domain`) remplit les arguments chaîne d'un domaine
    projet (phase 3). Absents, la complétion reste celle du catalogue seul.

    Rend la liste ENTIÈRE du contexte au curseur ; c'est l'UI qui la restreint au
    préfixe déjà tapé (le `QCompleter` filtre)."""
    if _in_comment(line_prefix):
        return []
    if _in_string(line_prefix):
        return _string_arg(line_prefix, project_names)
    qual = _QUAL.search(line_prefix)
    if qual:
        return _member_candidates(qual.group(1), qual.group(2), project_names, context)
    # Mot nu : les locals d'abord (les plus proches), puis le catalogue.
    return _local_candidates(source, line) + _bare_candidates(context)
