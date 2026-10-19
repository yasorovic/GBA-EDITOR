"""Créer un asset dans un test : le geste *Create asset* de l'auteur, sans interface.

Un fichier qui apparaît sous `assets/` n'est plus un asset : un test qui pose un PNG ou un son et attend un asset
doit le créer, comme l'auteur (cf. `core.asset_creation`)."""
from __future__ import annotations

from pathlib import Path

from core import asset_creation
from core.history import store_asset


def create_now(project, family: str, path, name: str | None = None) -> asset_creation.Creation:
    """`build_from_source` puis rangement, sans historique : l'asset naît tout de suite, ou `error` dit pourquoi non."""
    creation = asset_creation.build_from_source(project, family, Path(path), name)
    if creation.error is None:
        store_asset(creation.store, creation.item, creation.folder)
    return creation


def create(project, family: str, path, name: str | None = None):
    """L'asset de type `family` créé à côté de `path`, qui le pointe. Échoue si la création est refusée."""
    result = create_now(project, family, path, name)
    assert result.error is None, result.error
    return result.item


def create_all(project, *pairs):
    """`create_all(p, ("sprites", path), ("sfx", path))` : plusieurs assets, dans l'ordre."""
    return [create(project, family, path) for family, path in pairs]
