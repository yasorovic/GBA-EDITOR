"""scripting/api_snippets.py — fabrique le Lua que l'éditeur INSÈRE, depuis `RUNTIME_API`.

Point unique de fabrication des snippets. Tant qu'ils étaient écrits en dur dans
la sidebar, ils pourrissaient à chaque changement de signature sans que rien ne
le signale : la sidebar proposait encore `scene_goto("X")` et
`instantiate("X", x, y)`, deux noms qui n'ont **jamais** existé dans le
catalogue — donc, au clic, du code que le checker refuse. Et l'utilisateur, lui,
conclut que l'API est cassée, pas que le bouton est périmé.

Dériver du catalogue rend cette dérive impossible : une signature qui change
change le snippet, une fonction qui disparaît fait disparaître son bouton.
C'est aussi ce qui fait que le réordonnancement d'arguments à venir
(`text:draw(x, y, contenu)`) n'aura à toucher que `api.py`.

Deux entrées distinctes, parce que les deux usages ne veulent pas la même chose :

  `bare()`    — section API : le nom seul, sans argument ni exemple — ce que
                le clic insère, à l'auteur de compléter.
  `call()`    — section RÉFÉRENCES : l'utilisateur a cliqué sur UN asset précis,
                donc le nom vient de lui et l'exemple du `doc` serait un
                contresens (il citerait un autre asset).
"""
from __future__ import annotations

from scripting.api import (
    RUNTIME_API, RUNTIME_PROPS, PARAM_STR, PARAM_STR_LITERAL, PARAM_ACTOR, ApiFunc,
    HARDWARE_ENUMS, REF_TYPE_TABLE, module_call_form,
)

from scripting.expr_types import VEC_FIELDS, VEC_CONSTRUCTORS, C_TYPES

# Marqueur d'exemple dans les `doc` d'api.py. Convention déjà en place là-bas ;
# la nommer ici évite qu'un troisième lecteur la redevine.
_EX = "Ex:"


def _fn(name: str) -> ApiFunc | None:
    return RUNTIME_API.get(name)


# Une référence s'écrit sur une VARIABLE, pas sur le nom de son type : le libellé
# du bouton dit le type (`collision_box:overlaps`), le snippet inséré montre
# l'usage (`hb:overlaps(other)`). Même convention que le JSON pour `sfx`
# (`sfx:stop()` → `pas:stop()`). La variable se DÉCLARE avec le type
# (`api.REF_TYPE_TABLE`) : pas de seconde liste ici.


def _on_variable(name: str) -> str:
    """`collision_box:overlaps` / `collision_box.solid` → `hb:overlaps` / `hb.solid`.
    Une FONCTION de module (`collision_box.get_tile`) garde son nom : le point ne
    dit une propriété que si le catalogue la connaît comme telle."""
    for ref, decl in REF_TYPE_TABLE.items():
        if name.startswith(f"{ref}:") or (name.startswith(f"{ref}.") and name in RUNTIME_PROPS):
            return decl.variable + name[len(ref):]
    # La fonction d'un MODULE s'écrit avec « : » (`input:pressed`) : la clé du catalogue reste
    # `input.pressed`, seule sa forme écrite change (`api.module_call_form`).
    return module_call_form(name)


def _lua_str(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def signature(name: str) -> str:
    """`interface.draw_text(region, id)` — la forme, pour un libellé de bouton."""
    f = _fn(name)
    if f is None:
        return name
    parts = [p.name for p in f.params]
    if f.variadic:
        parts.append("...")
    return f"{module_call_form(name)}({', '.join(parts)})"



def call(name: str, **by_domain: str) -> str:
    """Appel Lua prêt à insérer, les arguments NOMMÉS remplis par domaine.

    Les clés de `by_domain` sont des `DOMAIN_*` : c'est le domaine, et non la
    position, qui dit où va le nom d'un asset — donc réordonner les paramètres
    dans `api.py` n'invalide aucun appelant. Un paramètre non fourni devient un
    gabarit : son propre nom, entre guillemets s'il attend une chaîne, pour que
    le snippet reste du Lua valide et visiblement à compléter."""
    f = _fn(name)
    if f is None:
        return name
    args: list[str] = []
    for p in f.params:
        if p.domain and p.domain in by_domain:
            args.append(_lua_str(by_domain[p.domain]))
        elif p.domain in HARDWARE_ENUMS:
            # Énumération matérielle : l'ensemble est FIXE et connu ici, donc on
            # propose une vraie valeur plutôt qu'un gabarit. Un gabarit
            # (`layer.set_blend("mode", ...)`) serait refusé par le checker à
            # la seconde même où l'utilisateur vient de cliquer pour
            # l'insérer. DOMAIN_WIN_REGION n'y figure PAS depuis le
            # 2026-08-25 (noms de WindowSlot propres au projet, pas un enum
            # fixe) — il retombe sur le gabarit générique ci-dessous, même
            # traitement que DOMAIN_CAMERA.
            args.append(_lua_str(next(iter(HARDWARE_ENUMS[p.domain]))))
        elif p.ptype in (PARAM_STR, PARAM_STR_LITERAL):
            args.append(_lua_str(p.name))
        elif p.ptype == PARAM_ACTOR:
            args.append(p.name)
        else:
            args.append(p.name)
    if f.variadic:
        args.append("...")
    return f"{_on_variable(name)}({', '.join(args)})"


def element_call(element: str, name: str, **by_domain: str) -> str:
    """Le snippet d'une méthode d'ÉLÉMENT d'interface, écrite sur son acquisition :
    `text_region:draw` sur « boite_bas » → `interface:get("boite_bas"):draw("texte")`.
    Les arguments de la méthode se remplissent par domaine, comme pour `call`."""
    inner = call(name, **by_domain)
    method = name.split(":", 1)[1]
    return f"interface:get({_lua_str(element)}):{method}{inner[inner.index('('):]}"


def description(name: str) -> str:
    """Le `doc` sans sa queue d'exemple — celle-ci se montre à part."""
    f = _fn(name)
    if f is None:
        return ""
    return (f.doc or "").split(_EX)[0].strip()


def bare(name: str) -> str:
    """Ce que le bouton INSÈRE dans le script : le nom, sans exemple.

    `actor:spawn()`, `self:move()`, `hb:overlaps()`, et pour une propriété son nom
    seul (`self.active`). Ni argument d'illustration ni valeur d'écriture : le
    clic pose de quoi écrire, l'auteur complète. Un exemple inséré est un exemple
    à effacer (`actor:spawn("Bullet", vec2(116, 76))` — un acteur qui n'existe
    pas dans son projet), et la doc d'un appel dit déjà comment l'appeler."""
    name = _on_variable(name)
    return name if name in _PROP_NAMES else f"{name}()"


_PROP_NAMES = frozenset(_on_variable(k) for k in RUNTIME_PROPS)


def _param_type(p) -> str:
    """Type affiché d'un paramètre — « string »/« number » pour les scalaires,
    mais un vec2/vec3 garde son type composé : dire « number » pour une
    position tromperait (il faut écrire vec2(x, y))."""
    if p.ptype in (PARAM_STR, PARAM_STR_LITERAL):
        return "string"
    if p.ptype == "vec2" or p.ptype == "vec3":
        return p.ptype
    return "number"


def _short_type(p, enum) -> str:
    """Type affiché entre parenthèses dans le libellé court d'une propriété,
    et dans sa bulle : le nom C pour un composite (Vec2/Rect — reconnaissable
    d'un coup d'œil), « string » pour une énumération matérielle (elle se lit/
    s'écrit par son NOM, cf. `enum` dans l'appelant), le scalaire brut sinon."""
    if enum:
        return "string"
    return C_TYPES.get(p.ptype, p.ptype)


def prop_entry_dict(name: str) -> dict:
    """Entrée au format d'`api_reference.json` pour une PROPRIÉTÉ
    (`RUNTIME_PROPS`) — même forme que `entry_dict`, pour que `tooltip_parts`
    n'ait pas à savoir d'où vient l'entrée qu'il affiche.

    Le `label` reste COURT (`position(Vec2)`) : le préfixe (`self.`/`camera.`)
    et la forme d'écriture complète (`self.position = vec2(x, y)`) ne
    manquent pas — ils vivent dans le `snippet` (inséré au clic) et dans la
    bulle, pas dans le nom du bouton qu'on scanne dans la sidebar."""
    p = RUNTIME_PROPS.get(name)
    fields = VEC_FIELDS.get(p.ptype, ()) if p is not None else ()
    # Une propriété COMPOSITE qui porte aussi des noms (`self.direction`) rend un
    # vec2 : c'est ça qu'il faut annoncer, les noms étant une seconde écriture
    # décrite dans sa doc — pas son type de retour.
    enum = (HARDWARE_ENUMS.get(p.domain)
            if p is not None and p.ptype not in VEC_CONSTRUCTORS else None)
    read_only = p is None or p.read_only or p.c_setter is None
    snippet = bare(name)
    short = name.rsplit(".", 1)[-1]
    typ = _short_type(p, enum) if p is not None else ""
    return {
        "label":       f"{short}({typ})" if typ else short,
        "snippet":     snippet,
        "description": p.doc if p is not None else "",
        # Ce que le label court ne dit plus (peut-on ÉCRIRE cette propriété)
        # devient son propre champ — `tooltip_parts` l'affiche en badge.
        "access":      "Read Only" if read_only else "Read and Write",
        "params": [
            {"name": f, "type": "number", "description": ""} for f in fields
        ],
        # Une propriété d'énumération ne rend pas « int » côté script : elle
        # rend l'un de ces noms, et c'est ce qu'il faut lire dans l'infobulle —
        # plus précis que le « string » du libellé court, qui n'a pas la place.
        "returns":     " | ".join(f'"{v}"' for v in enum) if enum else typ,
        "doc_anchor":  name.replace(":", "-").replace(".", "-"),
    }


def entry_dict(name: str) -> dict:
    """Entrée au format d'`api_reference.json`, pour une fonction que le JSON
    ne décrit pas. Même forme exactement : c'est ce qui permet à `tooltip_parts`
    de ne pas savoir d'où vient l'entrée qu'il affiche."""
    f = _fn(name)
    ret = "" if f is None or f.ret == "void" else f.ret
    return {
        "label":       signature(name),
        "snippet":     bare(name),
        "description": description(name),
        "params": [
            {"name": p.name,
             "type": _param_type(p),
             "description": ""}
            for p in (f.params if f else [])
        ],
        "returns":     ret,
        "doc_anchor":  name.replace(":", "-").replace(".", "-"),
    }
