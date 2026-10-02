"""La disposition runtime des inputs du projet (ROADMAP « Les inputs
personnalisés ») : les masques des accords, les tables C des séquences, la
profondeur de l'anneau, le bitset `buffered` et les masques des axes —
calculés UNE FOIS depuis les `InputBinding`/`InputSequence`/`InputAxis`/
`InputMovement` déclarés (et, pour la profondeur liée à `buffered`, les
littéraux trouvés dans les scripts).

Décision de l'auteur (2026-09-27, après coup) : un ACCORD (`InputBinding`,
cases à cocher) et une SÉQUENCE (`InputSequence`, mini-langage complet) sont
deux espaces de noms séparés — `held`/`pressed`/`released`/`buffered` ne
lisent jamais une séquence, `get_sequence` ne lit jamais un accord.

Source unique pour `main_gen.py` (les globales et les tables C) et
`lua_compiler.py` (le `BuildContext` passé au checker/codegen par script) : un
calcul différent aux deux endroits aurait pu diverger sans qu'aucun test ne le
voie — exactement le défaut que `text_layout` et sa sonde existent pour éviter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.models.input_expression import InputExpressionError, parse_input_expression

# Anneau minimal : `released` lit le frame précédent, il en faut donc au moins
# deux (le courant et celui d'avant).
_MIN_RING_DEPTH = 2
_MAX_RING_DEPTH = 255


def _btn_c(name: str) -> str:
    return f"BTN_{name.upper()}"


def _mask_c(buttons) -> str:
    return " | ".join(_btn_c(b) for b in sorted(buttons)) if buttons else "0"


@dataclass
class InputLayout:
    # Accords (`InputBinding`) : nom → masque C. Un bouton nu n'y est pas —
    # il se résout par `key_constant`, comme avant ce chantier.
    masks: dict = field(default_factory=dict)
    # Séquences (`InputSequence`) : nom → (symboles de table C, longueurs,
    # fenêtre). Plusieurs symboles si l'expression utilise une alternance.
    sequences: dict = field(default_factory=dict)
    sequence_names: frozenset = frozenset()
    seq_table_defs: dict = field(default_factory=dict)   # symbole C → [masques C] (à émettre)
    buffered_bits: dict = field(default_factory=dict)    # nom d'accord → index de bit
    ring_depth: int = _MIN_RING_DEPTH
    axis_names: list = field(default_factory=list)
    axes: dict = field(default_factory=dict)             # nom → (masque négatif, masque positif)


def _iter_script_paths(p):
    """Même couverture que la collecte d'events de `rom_build.py`
    (`_write_project_globals._collect_events`) : acteurs de scène, script de
    scène, prefabs poolés. Les behaviors et caméras n'y sont pas non plus —
    limitation partagée, pas une nouvelle."""
    from core.models.components import ScriptComponent

    for scene in getattr(p, "scenes", []) or []:
        for actor in getattr(scene, "actors", []) or []:
            comp = actor.get_component("script") if hasattr(actor, "get_component") else None
            if comp and getattr(comp, "active", True) and getattr(comp, "script", ""):
                yield p.asset_abs(comp.script)
        scene_script = getattr(scene, "script", "")
        if scene_script:
            yield p.asset_abs(scene_script)
    for pf in getattr(p, "prefabs", []) or []:
        sc = next((c for c in getattr(pf, "components", []) or []
                  if isinstance(c, ScriptComponent)), None)
        if sc and getattr(sc, "script", ""):
            yield p.asset_abs(sc.script)


def _scan_buffered(p):
    """Chaque `input:buffered(nom, frames)` littéral du projet : le plus grand
    `frames` (pour la profondeur de l'anneau) et l'ensemble des NOMS
    d'accord interrogés (pour n'allouer un bit `buffered` qu'à ceux-là —
    ROADMAP, « les autres n'en paient pas »).

    Parcours GÉNÉRIQUE par introspection des dataclasses du parseur (`fields`) :
    une visite qui énumérerait les attributs à la main serait un second arbre
    à tenir d'accord avec `parser.py` — un noeud oublié y redeviendrait le
    silence que ce chantier répare partout ailleurs."""
    import dataclasses
    from scripting.parser import (parse as _parse, LuaParseError,
                                  ExprCall, ExprIndex, ExprName, ExprNumber, ExprString)

    def _walk(node, best: list, names: set):
        if isinstance(node, ExprCall):
            func = node.func
            key = (f"{func.obj.name}.{func.field}"
                  if isinstance(func, ExprIndex) and isinstance(func.obj, ExprName) else None)
            if key == "input.buffered" and len(node.args) == 2:
                if isinstance(node.args[1], ExprNumber):
                    best[0] = max(best[0], int(node.args[1].value))
                if isinstance(node.args[0], ExprString):
                    names.add(node.args[0].value)
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                _walk(getattr(node, f.name), best, names)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item, best, names)

    best, names = [0], set()
    for sp in _iter_script_paths(p):
        if not (sp and sp.exists() and sp.suffix.lower() == ".lua"):
            continue
        try:
            ast = _parse(sp.read_text(encoding="utf-8"))
        except LuaParseError:
            continue
        _walk(ast, best, names)
    return best[0], names


def compute_input_layout(p) -> InputLayout:
    settings = getattr(p, "settings", None)
    bindings = list(getattr(settings, "inputs", []) or [])
    seq_decls = list(getattr(settings, "sequences", []) or [])
    axes_decl = list(getattr(settings, "axes", []) or [])
    custom_movements = {m.name: m.steps for m in getattr(settings, "movements", []) or []
                        if m.name and m.steps}

    layout = InputLayout()

    # ── Accords (InputBinding) — un ET direct des boutons, pas de parseur ──
    seen_names = set()
    for binding in bindings:
        name = str(getattr(binding, "name", "") or "").strip()
        buttons = list(getattr(binding, "buttons", []) or [])
        if not name or not buttons or name in seen_names:
            continue
        seen_names.add(name)
        layout.masks[name] = _mask_c(buttons)

    # ── Séquences (InputSequence) — le mini-langage complet ─────────────
    for seq in seq_decls:
        name = str(getattr(seq, "name", "") or "").strip()
        expr_text = str(getattr(seq, "expression", "") or "").strip()
        if not name or not expr_text or name in layout.sequences:
            continue
        try:
            alternatives = parse_input_expression(expr_text, custom_movements)
        except InputExpressionError:
            # Une séquence mal formée ne bloque pas le reste : l'écran refuse
            # la saisie AVANT qu'elle n'arrive ici (même contrat que « Un seul
            # type de script »). Elle disparaît silencieusement du catalogue
            # plutôt que de casser le build.
            continue
        layout.sequence_names = layout.sequence_names | {name}
        tables, lens = [], []
        for i, e in enumerate(alternatives):
            steps = [_mask_c(s.buttons) for s in e.steps]
            symbol = f"_SEQ_{name}" if len(alternatives) == 1 else f"_SEQ_{name}_{i}"
            layout.seq_table_defs[symbol] = steps
            tables.append(symbol)
            lens.append(len(steps))
        layout.sequences[name] = (tables, lens, seq.window)
        span = max(lens) * max(1, seq.window) + 1
        layout.ring_depth = max(layout.ring_depth, span)

    buffered_max, buffered_names = _scan_buffered(p)
    if buffered_max:
        layout.ring_depth = max(layout.ring_depth, buffered_max + 1)
    # Le bit `buffered` n'est alloué QU'AUX accords interrogés par
    # `buffered()` — un jeu sans tampon, ou un accord jamais bufferisé, n'en
    # paie pas l'octet (ROADMAP, décision de l'auteur).
    for i, name in enumerate(n for n in layout.masks if n in buffered_names):
        layout.buffered_bits[name] = i

    layout.ring_depth = min(layout.ring_depth, _MAX_RING_DEPTH)

    # Axes : "horizontal"/"vertical" (la croix) toujours présents en premier,
    # jamais stockés dans `settings.axes` — cf. InputAxis. Un côté d'axe est
    # un bouton ou un ACCORD (jamais une séquence, absente de `layout.masks`).
    layout.axes["horizontal"] = (_btn_c("left"), _btn_c("right"))
    layout.axes["vertical"] = (_btn_c("up"), _btn_c("down"))
    layout.axis_names = ["horizontal", "vertical"]
    for axis in axes_decl:
        name = str(getattr(axis, "name", "") or "").strip()
        if not name or name in layout.axes:
            continue
        neg_mask = layout.masks.get(axis.negative, _mask_c([axis.negative]))
        pos_mask = layout.masks.get(axis.positive, _mask_c([axis.positive]))
        layout.axes[name] = (neg_mask, pos_mask)
        layout.axis_names.append(name)

    return layout
