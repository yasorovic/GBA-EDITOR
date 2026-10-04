"""
editor/core/models/field_value.py — valeur d'un champ numérique de composant
qui peut être, au choix :

  • un littéral en PIXELS      → stocké tel quel en `int`   (forme historique)
  • un littéral en TILES       → stocké `{"unit": "t", "n": <int>}`
  • une RÉFÉRENCE de variable   → stocké `{"var": <id>, "src": "global"|"const"}`

Une référence cite l'**id opaque** de la variable, pas son nom : c'est un
fichier de DONNÉES, il doit survivre à un renommage sans que personne ne le
réécrive (cf. models/ids.py). Le nom, lui, est résolu à la lecture pour
l'affichage et pour l'expression C.

Deux formes lues, une seule écrite : un champ nu (`x: 0`) est un littéral pixel,
et `{"var": <id>}` est la référence telle que l'éditeur la sauvegarde. La forme
par NOM (`{"var": "score_joueur"}`) reste acceptée en lecture — c'est celle qui
s'écrit à la main dans un sidecar, l'id étant illisible — et se résout par nom.
Elle repasse en id dès que l'éditeur réécrit le fichier.

Ce module ne dépend pas de Qt : il est partagé par l'UI (aperçu pixel),
le canvas (rendu) et le codegen (expression C). Les noms de symboles C
DOIVENT rester alignés sur scripting/globals.py (`g_<nom>`) et
scripting/constants.py (`CONST_<NOM en MAJUSCULES>`).
"""

from __future__ import annotations
from typing import Callable, Optional, Union

TILE_SIZE = 8   # px par tile (GBA)

Raw = Union[int, dict]                    # forme sérialisée telle qu'en JSON
Resolver = Callable[[str, str], Optional[int]]   # (src, name) -> valeur ou None


class FieldValue:
    """Wrapper léger autour de la forme sérialisée (`int` ou `dict`).

    On ne stocke JAMAIS une instance de FieldValue dans le modèle : le champ
    du composant garde sa forme sérialisable (`int`/`dict`). On enveloppe à la
    volée via `FieldValue.parse(raw)` puis on relit `to_raw()` pour ré-stocker.
    """

    __slots__ = ("mode", "n", "var_name", "var_src", "var_id")

    def __init__(self, mode: str, n: int = 0, var_name: str = "",
                 var_src: str = "global", var_id: int = 0):
        self.mode = mode            # "px" | "tile" | "ref"
        self.n = n                  # nombre (px ou tiles) pour px/tile
        self.var_name = var_name    # nom résolu — affichage et expression C
        self.var_src = var_src      # "global" | "const"
        self.var_id = var_id        # id opaque — CE QUI EST STOCKÉ

    # ── Construction ──────────────────────────────────────────────
    @classmethod
    def parse(cls, raw: Raw, names: Optional[dict] = None) -> "FieldValue":
        """`names` : `{(src, id): nom}`, cf. `var_names_from_project`. Sans lui,
        une référence par id reste résoluble comme donnée (l'id est là) mais son
        NOM est inconnu — `c_expr()` le dit alors dans le C émis plutôt que de
        rendre un `0` muet."""
        if isinstance(raw, bool):           # bool est un int en Python — normaliser
            return cls("px", int(raw))
        if isinstance(raw, int):
            return cls("px", raw)
        if isinstance(raw, dict):
            if "var" in raw:
                src = raw.get("src", "global")
                src = src if src in ("global", "const") else "global"
                var = raw.get("var", "")
                if isinstance(var, str):
                    # Forme ancienne : le nom EST la référence. Gardée lisible
                    # tant que la migration n'est pas passée.
                    return cls("ref", var_name=var, var_src=src)
                vid = int(var or 0)
                return cls("ref", var_src=src, var_id=vid,
                           var_name=(names or {}).get((src, vid), ""))
            if raw.get("unit") == "t":
                try:
                    return cls("tile", int(raw.get("n", 0)))
                except (TypeError, ValueError):
                    return cls("tile", 0)
        return cls("px", 0)             # forme inconnue → repli neutre

    @classmethod
    def pixels(cls, n: int) -> "FieldValue":
        return cls("px", int(n))

    @classmethod
    def tiles(cls, n: int) -> "FieldValue":
        return cls("tile", int(n))

    @classmethod
    def ref(cls, name: str, src: str, var_id: int = 0) -> "FieldValue":
        return cls("ref", var_name=name, var_id=var_id,
                   var_src=src if src in ("global", "const") else "global")

    # ── Sérialisation ─────────────────────────────────────────────
    def to_raw(self) -> Raw:
        if self.mode == "tile":
            return {"unit": "t", "n": int(self.n)}
        if self.mode == "ref":
            # L'id dès qu'on en a un ; le nom seulement pour une référence
            # ancienne que la migration n'a pas encore vue — la réécrire en id
            # sans savoir lequel inventerait un lien.
            return {"var": self.var_id or self.var_name, "src": self.var_src}
        return int(self.n)          # px → int nu (fichiers propres, rétro-compat)

    # ── Interrogation ─────────────────────────────────────────────
    @property
    def is_ref(self) -> bool:
        return self.mode == "ref"

    @property
    def is_tile(self) -> bool:
        return self.mode == "tile"

    # ── Aperçu pixel (UI / canvas) ────────────────────────────────
    def px(self, resolver: Optional[Resolver] = None, fallback: int = 0) -> int:
        """Valeur en pixels pour l'affichage.
        - px   : la valeur telle quelle
        - tile : n * TILE_SIZE
        - ref  : valeur fournie par `resolver(src, name)` (ex : défaut de la
                 variable) ; `fallback` si non résolue."""
        if self.mode == "tile":
            return int(self.n) * TILE_SIZE
        if self.mode == "ref":
            if resolver is not None:
                # Par NOM d'abord (référence ancienne, ou nom déjà résolu),
                # par ID ensuite : le résolveur connaît les deux clés, ce qui
                # évite d'avoir à passer la table de noms aux dizaines
                # d'endroits qui ne veulent qu'un aperçu en pixels.
                v = resolver(self.var_src, self.var_name) if self.var_name else None
                if v is None and self.var_id:
                    v = resolver(self.var_src, self.var_id)
                if v is not None:
                    return int(v)
            return fallback
        return int(self.n)

    # ── Expression C (codegen) ────────────────────────────────────
    def c_expr(self) -> str:
        """Rvalue C. px→littéral, tile→n*8, ref→symbole (g_<nom> / CONST_<NOM>)."""
        if self.mode == "tile":
            return str(int(self.n) * TILE_SIZE)
        if self.mode == "ref":
            if not self.var_name:
                # Visible dans le C émis plutôt que silencieusement nul : une
                # référence qui ne se résout plus est une donnée cassée, pas un
                # zéro légitime.
                return f"0 /* variable #{self.var_id} introuvable */" if self.var_id else "0"
            if self.var_src == "const":
                return f"CONST_{self.var_name.upper()}"
            return f"g_{self.var_name}"
        return str(int(self.n))

    # ── Libellé court (puce UI) ───────────────────────────────────
    def label(self) -> str:
        if self.mode == "tile":
            return f"{self.n}t"
        if self.mode == "ref":
            return self.var_name or "?"
        return str(self.n)


# ── Helpers projet ─────────────────────────────────────────────────
# Les variables référençables d'un projet = ses globals + constantes. Ces
# trois fonctions évitent de recopier la même dérivation à chaque point
# d'usage (éditeurs de composant → liste ; canvas → résolveur). `project`
# est duck-typé (.globals / .constants) pour garder ce module sans import.

def var_names_from_project(project) -> dict:
    """Map `(src, id) -> nom`, la résolution d'une RÉFÉRENCE stockée.
    C'est l'argument `names` de `FieldValue.parse`."""
    if not project:
        return {}
    d: dict = {}
    for g in project.globals:
        d[("global", g.id)] = g.name
    for c in project.constants:
        d[("const", c.id)] = c.name
    return d


def variables_from_project(project) -> list[tuple[str, str, int]]:
    """Liste ordonnée `(src, nom, id)` prête pour `ValueField(variables=…)`.

    Le NOM est ce que l'utilisateur choisit dans le menu, l'ID ce qui part dans
    la donnée — le widget a besoin des deux au même moment."""
    if not project:
        return []
    # Une string n'est pas un nombre : ni pixels, ni tuiles, ni durée.
    return ([("global", g.name, g.id) for g in project.globals if g.type != "string"]
            + [("const", c.name, c.id) for c in project.constants if c.type != "string"])


def var_defaults_from_project(project) -> dict:
    """Map `(src, clé) -> valeur par défaut`, où la clé est le NOM **et** l'ID.

    Les deux, parce que les deux circulent : une référence stockée porte l'id,
    une référence ancienne ou déjà résolue porte le nom. Indexer les deux évite
    de faire remonter la table de noms jusqu'aux appelants qui ne veulent qu'un
    aperçu en pixels."""
    if not project:
        return {}
    d: dict = {}
    for g in project.globals:
        if g.type == "string":
            continue
        d[("global", g.name)] = g.default
        d[("global", g.id)] = g.default
    for c in project.constants:
        if c.type == "string":
            continue
        d[("const", c.name)] = c.value
        d[("const", c.id)] = c.value
    return d


def make_resolver(project) -> Resolver:
    """Résolveur `(src, name) -> valeur|None` prêt pour `FieldValue.px(resolver)`."""
    defaults = var_defaults_from_project(project)
    return lambda src, name: defaults.get((src, name))


# ── Nombres sans unité (rotation, échelle, priorité) ──────────────────
# Ces champs ne sont ni des pixels ni des tiles : un littéral (`int` ou
# `float` nu dans le fichier) OU une référence de variable (même dict
# `{"var": <id>, "src": …}` que ci-dessus). Pas de forme tile.
#
# Unité d'une variable : le NOMBRE du champ tel que le script le lit
# (`self.rotation` en degrés, `self.priority` 0-3, `self.scale` en POURCENT —
# 100 = normal, comme l'API Lua), jamais l'unité interne Q8 du moteur.

def is_ref_raw(raw) -> bool:
    return isinstance(raw, dict) and "var" in raw


def number_raw(raw, cast):
    """Forme à STOCKER pour un champ numérique : la référence telle quelle,
    sinon le littéral converti par `cast` (`int` ou `float`)."""
    return raw if is_ref_raw(raw) else cast(raw)


def number_value(raw, resolver: Optional[Resolver] = None, default=0,
                 ref_divisor: int = 1):
    """Valeur numérique d'un champ pour l'aperçu/les calculs de l'éditeur.
    Une référence vaut le défaut de sa variable (`resolver`), divisé par
    `ref_divisor` (100 pour une échelle en pourcent) ; non résolue → `default`.
    """
    if is_ref_raw(raw):
        fv = FieldValue.parse(raw)
        v = fv.px(resolver, fallback=None) if resolver else None
        return default if v is None else v / ref_divisor
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, (int, float)):
        return raw
    return default


def number_c(raw, names: Optional[dict] = None, *, q8: bool = False,
             mask: Optional[int] = None):
    """Rvalue C d'un champ numérique : `int` pour un littéral, expression pour
    une variable. `q8` : l'échelle est stockée ×256 côté moteur (littéral
    `round(f*256)`, variable en pourcent `(v)*256/100`). `mask` : `& mask`."""
    if is_ref_raw(raw):
        e = FieldValue.parse(raw, names).c_expr()
        if q8:
            e = f"(({e})*256/100)"
        return f"(({e})&{mask})" if mask is not None else e
    v = number_value(raw)
    n = int(round(v * 256)) if q8 else int(round(v))
    return n & mask if mask is not None else n
