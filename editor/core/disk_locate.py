"""disk_locate — de l'élément d'une scène au fichier qui le porte dans `assets/`.

Le clic-droit « Localiser dans Disk » (canvas, arbre de scène) part d'un acteur
ou d'une interface et veut savoir QUEL fichier montrer. Deux étapes, toutes deux
pures (pas de Qt) : `target_of` dit quel asset représente l'élément, `file_of`
dit où il vit. Le chemin rendu est celui que l'arbre Disk classe en ASSET
(`store.path_of`), donc il s'y retrouve toujours."""

from __future__ import annotations

from pathlib import Path

from core.models.components import displayed_sprite_component


def target_of(actor) -> tuple[str, str] | None:
    """`(famille, nom)` de l'asset que cet acteur représente : son prefab s'il en est une
    instance, sinon le sprite qu'il affiche. `None` si l'acteur n'a ni l'un ni l'autre
    (un acteur de pur script)."""
    if actor.prefab_name:
        return "prefabs", actor.prefab_name
    comp = displayed_sprite_component(actor)
    return ("sprites", comp.sprite_name) if comp is not None else None


def file_of(project, family: str, name: str) -> Path | None:
    """Le fichier d'asset de `(famille, nom)`, ou `None` si le projet ne le connaît pas.
    Parcourt les deux tables de familles du projet (adossées à des sources, ou créées dans l'éditeur)."""
    stores = {f: store for f, store, _sources in project.source_families()}
    stores.update(project.authored_families())
    store = stores.get(family)
    item = store.get(name) if store is not None else None
    return store.path_of(item) if item is not None else None
