"""
core/models/unique_name.py — la règle unique du nom libre.

Un nom déjà pris est suffixé : `coin`, puis `coin_2`, `coin_3`… Toute création ou
tout renommage automatique de l'éditeur passe par cette fonction, jamais par une
boucle écrite à la main : deux règles voisines finissent par donner, pour le même
objet, deux suites différentes selon le geste qui l'a créé.

Dupliquer est un cas à part : la copie d'un `coin_2` doit redonner `coin_3`, pas
`coin_2_2`. `copy_name` porte cette règle, pour que toutes les duplications
(assets, acteurs, prefabs, éléments d'interface…) suivent la même suite.
"""
from __future__ import annotations

import re

# `coin_2` : la forme que `unique_name` écrit. Dupliquer `coin_2` continue sur `coin`.
_NUMBERED = re.compile(r"^(?P<base>.+)_\d+$")


def unique_name(base: str, existing) -> str:
    """`base` s'il est libre, sinon le premier `base_N` (N ≥ 2) absent de `existing`."""
    existing = set(existing)
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def copy_name(base: str, existing) -> str:
    """Le nom de la copie de `base` : `base_2`, `base_3`… Si `base` est lui-même un `x_N` dont `x` est déjà pris (la
    copie d'une copie), la suite reprend sur `x` plutôt que de s'empiler en `x_2_2`. Un `x_N` dont `x` n'existe pas
    n'est pas une copie : son `_N` est gardé (un `Level_1` seul donne `Level_1_2`)."""
    existing = set(existing)
    numbered = _NUMBERED.match(base)
    root = numbered.group("base") if numbered and numbered.group("base") in existing else base
    return unique_name(root, existing | {root})
