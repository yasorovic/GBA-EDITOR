"""
core/models/unique_name.py — la règle unique du nom libre.

Un nom déjà pris est suffixé : `coin`, puis `coin_2`, `coin_3`… Toute création ou
tout renommage automatique de l'éditeur passe par cette fonction, jamais par une
boucle écrite à la main : deux règles voisines finissent par donner, pour le même
objet, deux suites différentes selon le geste qui l'a créé.
"""
from __future__ import annotations


def unique_name(base: str, existing) -> str:
    """`base` s'il est libre, sinon le premier `base_N` (N ≥ 2) absent de `existing`."""
    existing = set(existing)
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"
