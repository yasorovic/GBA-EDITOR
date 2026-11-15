"""
Parse la table `exports` d'un script Lua actor.

Convention dans le .lua :

    exports = {
        speed   = { type = "int",    default = 5,        label = "Speed",     min = 0, max = 20 },
        name    = { type = "string", default = "Hero",   label = "Name" },
        active  = { type = "bool",   default = true,     label = "Active" },
        gravity = { type = "float",  default = 9.8,      label = "Gravity",   min = 0.0, max = 100.0 },
        pos     = { type = "vec2",   default = {0, 0},   label = "Position" },
        bounds  = { type = "rect",   default = {0,0,16,16}, label = "Bounds" },
        dir     = { type = "enum",   default = "LEFT",   label = "Direction", values = {"LEFT","RIGHT","UP","DOWN"} },
        sfx     = { type = "sfx_ref",   default = "",   label = "Sound" },
        next    = { type = "scene_ref", default = "",   label = "Next Scene" },
        target  = { type = "actor_ref", default = "",   label = "Target" },
        jump    = { type = "int", unit = "px/f", default = 4, label = "Jump", min = 0, max = 8 },
    }

`unit` (entiers seulement) dit ce que la valeur mesure : le champ se saisit dans
cette unité, le build multiplie vers l'unité du matériel, et le script continue de
lire l'unité de base (`-jump` vaut -1024). Cf. `EXPORT_UNITS` plus bas ; `default`,
`min` et `max` sont alors dans l'unité déclarée.

Retourne une liste ordonnée de dicts :
    { name, type, default, label, min, max, values, unit }
"""
from __future__ import annotations
import re
from core.resources.resource_store import atomic_write
from pathlib import Path
from typing import Any


# ── Types reconnus ─────────────────────────────────────────────────

KNOWN_TYPES = {
    "int", "float", "string", "bool",
    "vec2", "vec3", "rect",
    "enum",
    "actor_ref", "scene_ref", "sfx_ref",
}


# ── Unités déclarables (clé `unit`) ────────────────────────────────
#
# Une unité ne convertit rien par elle-même : elle DIT ce que l'entier mesure.
# L'éditeur en tire le facteur vers l'unité du MATÉRIEL (l'unité de base), montre
# la lecture dans l'autre unité, et le build multiplie une seule fois
# (`lua_compiler._export_inits`). Le script, lui, lit toujours l'unité de base :
# `move_dir * move_speed`, jamais `* 256`.
#
# L'éditeur ne manipule que des entiers : une unité ne sert pas à saisir une
# fraction, elle sert à saisir le même entier dans l'unité qui se lit. Un auteur
# qui veut la valeur fine la pose dans l'unité de base, en la voyant traduite.
#
#   unité déclarée -> (facteur vers l'unité de base, nom de l'unité de base)
EXPORT_UNITS: dict[str, tuple[int, str]] = {
    "px":    (1,   "px"),    # une distance : aucune conversion, l'unité se lit seulement
    "tile":  (8,   "px"),
    "px/f":  (256, "Q8"),    # une vitesse : 256 = 1 pixel par frame
    "px/f²": (256, "Q8"),    # une accélération : même échelle Q8
    "s":     (60,  "f"),     # une durée : le tick du matériel est la frame
}

# Deux formes lues, une seule écrite (même règle que `core/models/field_value.py`) :
# `px/f2` s'écrit au clavier sans peine, `px/f²` est ce que le fichier garde.
_UNIT_ALIASES = {"px/f2": "px/f²"}

# Les types qui acceptent une unité : un entier, et rien d'autre. Une unité sur une
# string ou un enum ne voudrait rien dire ; sur un vec2, elle attend que le besoin
# existe (cf. la fiche « Déclarer l'unité d'un export de script »).
UNIT_TYPES = frozenset({"int"})


def normalize_unit(unit: Any) -> str:
    """L'unité canonique d'une déclaration, ou "" si elle est absente ou inconnue."""
    u = str(unit or "").strip()
    u = _UNIT_ALIASES.get(u, u)
    return u if u in EXPORT_UNITS else ""


def unit_factor(unit: Any) -> int:
    """Combien d'unités de base vaut une unité de l'auteur (1 si elle est inconnue)."""
    return EXPORT_UNITS.get(normalize_unit(unit), (1, ""))[0]


def unit_base(unit: Any) -> str:
    """Le nom de l'unité du matériel derrière une unité déclarée ("" si inconnue)."""
    return EXPORT_UNITS.get(normalize_unit(unit), (1, ""))[1]


def base_value(raw: Any, unit: Any) -> int:
    """L'entier dans l'unité de BASE, quelle que soit la forme stockée.

    Deux formes lues : un entier nu est déjà dans l'unité de base (c'est la forme
    historique, et celle que le bouton de mode écrit quand l'auteur saisit en Q8),
    `{"unit": u, "n": n}` est une saisie dans l'unité `u`. C'est la forme STOCKÉE
    qui dit son unité, pas la déclaration : un script qui change d'unité ne doit
    pas réinterpréter en silence ce qu'une scène garde."""
    if isinstance(raw, dict):
        return int(raw.get("n", 0)) * unit_factor(raw.get("unit") or unit)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def parse_exports(lua_path: Path) -> list[dict]:
    """Lit le fichier .lua et retourne les variables exportées."""
    if not lua_path or not lua_path.exists():
        return []
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    return _parse_exports_table(text)


# ── Parser interne ─────────────────────────────────────────────────

def _find_exports_block(text: str) -> tuple[int, int] | None:
    """Span (start, end) du contenu INTERNE de `exports = { ... }` (bornes
    exclusives des accolades), ou None si la table est absente. Partagé par
    le parsing (ci-dessous) et l'écriture (add_export/remove_export)."""
    m = re.search(r'\bexports\s*=\s*\{', text)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    return start, i - 1


def _parse_exports_table(text: str) -> list[dict]:
    block_range = _find_exports_block(text)
    if block_range is None:
        return []
    start, end = block_range
    block = text[start:end]
    return [v for v in (_parse_entry(e) for e in _split_entries(block)) if v]


def _split_entries(block: str) -> list[str]:
    """Découpe le bloc en entrées de niveau 0 (séparées par ',')."""
    entries, current, depth = [], [], 0
    for ch in block:
        if ch == '{':
            depth += 1
            current.append(ch)
        elif ch == '}':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            s = ''.join(current).strip()
            if s:
                entries.append(s)
            current = []
        else:
            current.append(ch)
    s = ''.join(current).strip()
    if s:
        entries.append(s)
    return entries


def _parse_entry(entry: str) -> dict | None:
    """Parse une entrée   key = { type=..., default=..., ... }"""
    m = re.match(r'^(\w+)\s*=\s*\{(.+)\}$', entry, re.DOTALL)
    if not m:
        return None

    name  = m.group(1)
    inner = m.group(2)

    var: dict = {
        "name":    name,
        "type":    "string",
        "default": "",
        "label":   name,
        "min":     None,
        "max":     None,
        "values":  [],
        "unit":    "",
    }

    # type
    t = re.search(r'\btype\s*=\s*"(\w+)"', inner)
    if t and t.group(1) in KNOWN_TYPES:
        var["type"] = t.group(1)

    # unit : ce que l'entier mesure. Une unité inconnue est ignorée ici (le champ
    # reste un entier nu) ; c'est le checker qui la dit à l'auteur, avec le reste
    # des erreurs de son script.
    u = re.search(r'\bunit\s*=\s*"([^"]*)"', inner)
    if u:
        var["unit"] = normalize_unit(u.group(1))

    # label
    lb = re.search(r'\blabel\s*=\s*"([^"]*)"', inner)
    if lb:
        var["label"] = lb.group(1)

    # default : tout ce qui suit jusqu'à la prochaine clé connue ou fin
    df = re.search(r'\bdefault\s*=\s*((?:\{[^}]*\}|"[^"]*"|[^,]+))', inner)
    if df:
        var["default"] = _parse_value(df.group(1).strip(), var["type"])

    # min / max
    mn = re.search(r'\bmin\s*=\s*(-?[\d.]+)', inner)
    if mn:
        raw = mn.group(1)
        var["min"] = float(raw) if '.' in raw else int(raw)

    mx = re.search(r'\bmax\s*=\s*(-?[\d.]+)', inner)
    if mx:
        raw = mx.group(1)
        var["max"] = float(raw) if '.' in raw else int(raw)

    # values (enum)
    vl = re.search(r'\bvalues\s*=\s*\{([^}]*)\}', inner)
    if vl:
        var["values"] = [v.strip().strip('"\'')
                         for v in vl.group(1).split(',') if v.strip()]

    return var


def _parse_value(raw: str, typ: str) -> Any:
    raw = raw.strip().rstrip(',').strip()

    if typ == "bool":
        return raw.lower() == "true"

    if typ == "int":
        try:    return int(float(raw))
        except (ValueError, OverflowError): return 0

    if typ == "float":
        try:    return float(raw)
        except ValueError: return 0.0

    if typ == "vec2":
        nums = re.findall(r'-?[\d.]+', raw)
        return [float(nums[0]), float(nums[1])] if len(nums) >= 2 else [0.0, 0.0]

    if typ == "vec3":
        nums = re.findall(r'-?[\d.]+', raw)
        return [float(n) for n in nums[:3]] if len(nums) >= 3 else [0.0, 0.0, 0.0]

    if typ == "rect":
        nums = re.findall(r'-?[\d.]+', raw)
        if len(nums) >= 4:
            return [float(n) for n in nums[:4]]
        return [0.0, 0.0, 16.0, 16.0]

    # string, enum, *_ref : déséchappe les retours-ligne (strings multi-lignes)
    return raw.strip('"\'').replace('\\n', '\n')


# ── Écriture : ajout/retrait d'une déclaration ──────────────────────
#  Utilisé par le Script Inspector (section VARIABLES EXPOSÉES) : add_export
#  écrit une déclaration minimale, valeur par défaut neutre selon le type :
#  l'utilisateur affine ensuite min/max/values/default à la main dans le
#  script si besoin (même esprit que les autres inspecteurs : l'éditeur pose
#  la structure, pas chaque détail).

_DEFAULTS: dict[str, Any] = {
    "int": 0, "float": 0.0, "bool": False, "string": "",
    "vec2": [0, 0], "vec3": [0, 0, 0], "rect": [0, 0, 16, 16],
    "enum": "", "actor_ref": "", "scene_ref": "", "sfx_ref": "",
}


def default_value(typ: str) -> Any:
    """Valeur par défaut neutre pour un type (utilisé par l'UI au changement
    de type)."""
    d = _DEFAULTS.get(typ, "")
    return list(d) if isinstance(d, list) else d


def _num(v: Any) -> str:
    """Formate un nombre sans .0 superflu quand c'est un entier."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _lua_literal(value: Any, typ: str) -> str:
    if typ == "bool":
        return "true" if value else "false"
    if typ in ("int", "float"):
        return _num(value)
    if typ in ("vec2", "vec3", "rect"):
        seq = value if isinstance(value, (list, tuple)) else []
        return "{" + ", ".join(_num(v) for v in seq) + "}"
    # string, enum, *_ref : échappe les retours-ligne pour rester un littéral
    # Lua sur une ligne (déséchappé au parse). Les guillemets nus restent une
    # limite préexistante (non échappés).
    return '"' + str(value).replace('\n', '\\n') + '"'


def add_export(lua_path: Path, name: str, typ: str, label: str | None = None) -> None:
    """Ajoute une nouvelle variable à la table `exports` (la crée si absente,
    juste après un éventuel bloc @note : cf. scripting/script_notes.py)."""
    if typ not in KNOWN_TYPES:
        raise ValueError(f"Unknown variable type: {typ}")
    text = lua_path.read_text(encoding="utf-8", errors="ignore") if lua_path.exists() else ""
    label = label or name
    default_repr = _lua_literal(_DEFAULTS.get(typ, ""), typ)
    new_entry = f'{name} = {{ type = "{typ}", default = {default_repr}, label = "{label}" }}'

    block_range = _find_exports_block(text)
    if block_range is None:
        from scripting.script_notes import note_block_span
        insert_at = span[1] if (span := note_block_span(text)) else 0
        table = f"exports = {{\n    {new_entry},\n}}\n\n"
        text = text[:insert_at] + table + text[insert_at:]
    else:
        start, end = block_range
        entries = _split_entries(text[start:end])
        if any(re.match(rf'^{re.escape(name)}\s*=', e) for e in entries):
            return   # nom déjà exporté : l'appelant (UI) vérifie l'unicité en amont
        entries.append(new_entry)
        new_inner = "\n" + ",\n".join(f"    {e.strip()}" for e in entries) + ",\n"
        text = text[:start] + new_inner + text[end:]
    atomic_write(lua_path, text)


def _entry_key(entry: str) -> str | None:
    m = re.match(r'^(\w+)\s*=', entry)
    return m.group(1) if m else None


def _rewrite_entry(lua_path: Path, name: str, transform) -> bool:
    """Applique `transform(entry_str) -> entry_str` à l'entrée `name` de la
    table exports et réécrit le fichier. Retourne True si une entrée a changé.
    Préserve toutes les autres clés de l'entrée (min/max/default/label/values)."""
    if not lua_path.exists():
        return False
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    block_range = _find_exports_block(text)
    if block_range is None:
        return False
    start, end = block_range
    entries = _split_entries(text[start:end])
    out, changed = [], False
    for e in entries:
        if _entry_key(e) == name:
            new_e = transform(e)
            if new_e != e:
                changed = True
            out.append(new_e)
        else:
            out.append(e)
    if not changed:
        return False
    new_inner = ("\n" + ",\n".join(f"    {x.strip()}" for x in out) + ",\n") if out else "\n"
    atomic_write(lua_path, text[:start] + new_inner + text[end:])
    return True


def rename_export(lua_path: Path, old_name: str, new_name: str) -> bool:
    """Renomme la clé d'une variable exposée (préserve le reste de sa
    déclaration). Retourne False si `new_name` est déjà pris ou introuvable."""
    if not lua_path.exists() or old_name == new_name:
        return False
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    block_range = _find_exports_block(text)
    if block_range is None:
        return False
    start, end = block_range
    names = {_entry_key(e) for e in _split_entries(text[start:end])}
    if new_name in names:
        return False
    return _rewrite_entry(
        lua_path, old_name,
        lambda e: re.sub(r'^\w+', new_name, e, count=1))


def _format_entry(name: str, var: dict) -> str:
    """Régénère la déclaration `name = { … }` depuis un dict (type/default/
    label/min/max/values). Robuste : remplace l'édition regex clé par clé."""
    typ = var.get("type", "int")
    if typ not in KNOWN_TYPES:
        typ = "int"
    default = var.get("default")
    if default is None:
        default = default_value(typ)
    parts = [f'type = "{typ}"']
    if normalize_unit(var.get("unit")):
        parts.append(f'unit = "{normalize_unit(var["unit"])}"')
    parts += [
        f'default = {_lua_literal(default, typ)}',
        f'label = "{var.get("label") or name}"',
    ]
    if var.get("min") is not None:
        parts.append(f'min = {_num(var["min"])}')
    if var.get("max") is not None:
        parts.append(f'max = {_num(var["max"])}')
    if typ == "enum" and var.get("values"):
        vals = ", ".join(f'"{v}"' for v in var["values"])
        parts.append(f'values = {{{vals}}}')
    return f'{name} = {{ ' + ", ".join(parts) + ' }'


def update_export(lua_path: Path, name: str, var: dict) -> bool:
    """Réécrit intégralement la déclaration de la variable `name` depuis `var`
    (le dict issu de parse_exports, avec les champs modifiés). Préserve donc
    tout ce que l'UI a relu : appeler avec le dict complet, pas partiel."""
    return _rewrite_entry(lua_path, name, lambda _e: _format_entry(name, var))


def remove_export(lua_path: Path, name: str) -> None:
    """Retire une variable de la table `exports` par son nom (no-op si absente
    ou si la table elle-même n'existe pas)."""
    if not lua_path.exists():
        return
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    block_range = _find_exports_block(text)
    if block_range is None:
        return
    start, end = block_range
    entries = _split_entries(text[start:end])
    kept = [e for e in entries if not re.match(rf'^{re.escape(name)}\s*=', e)]
    if len(kept) == len(entries):
        return
    new_inner = ("\n" + ",\n".join(f"    {e.strip()}" for e in kept) + ",\n") if kept else "\n"
    text = text[:start] + new_inner + text[end:]
    atomic_write(lua_path, text)
