"""Créer un asset dans un test : le geste *Create asset* de l'auteur, sans interface.

Un fichier qui apparaît sous `assets/` n'est plus un asset : un test qui pose un PNG ou un son et attend un asset
doit le créer, comme l'auteur (cf. `core.asset_creation`)."""
from __future__ import annotations

from pathlib import Path

from core import asset_creation


def create(project, family: str, path, name: str | None = None):
    """L'asset de type `family` créé à côté de `path`, qui le pointe. Échoue si la création est refusée."""
    result = asset_creation.create_from_source(project, family, Path(path), name)
    assert result.error is None, result.error
    return result.item


def create_all(project, *pairs):
    """`create_all(p, ("sprites", path), ("sfx", path))` : plusieurs assets, dans l'ordre."""
    return [create(project, family, path) for family, path in pairs]
