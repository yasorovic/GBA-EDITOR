"""scene_sources — la `source` des membres d'une scène : l'id de l'asset dont ils sont l'instance.

En mémoire, un membre garde le NOM de son asset (`Actor.prefab_name`, `BackgroundLayer.background_name`,
`InterfaceNode.layout_name`) : c'est ce que le build, les inspecteurs et les scripts lisent. Sur disque, la
référence qui fait foi est `source`, l'id. Ce module synchronise les deux, et seulement lui :

- `resolve_scene_sources`, à l'ouverture : l'id l'emporte. Un prefab renommé hors de l'éditeur est retrouvé par
  son id, et un acteur d'avant l'en-tête commun, qui ne nommait que son prefab, reçoit son id.
- `stamp_scene_sources`, avant chaque écriture de la scène : le nom que le membre porte est converti en id.

Un fond ne se retrouve que s'il est déjà chargé : le catalogue des fonds est paresseux, et lire tous leurs
sidecars à l'ouverture défairait ce chargement. Un calque garde donc aussi `background_name` dans le fichier.
Une `source` qui ne désigne plus aucun asset n'est jamais effacée : le validateur la nomme.
"""
from __future__ import annotations


def _by_id(store, asset_id: str):
    return next((item for item in store if item.id == asset_id), None) if asset_id else None


def _members(project, scene):
    """(membres, attribut du nom, collection) pour chaque sorte de membre qui a une origine."""
    return ((scene.actors, "prefab_name", project.prefabs, True),
            (scene.background_layers, "background_name", project.backgrounds, False),
            (scene.ui_layouts, "layout_name", project.ui_layouts, True))


def resolve_scene_sources(project, scene) -> None:
    for members, name_attr, store, complete in _members(project, scene):
        for member in members:
            origin = _by_id(store, member.source)
            if origin is not None:
                setattr(member, name_attr, origin.name)
            elif complete and member.source == "" and getattr(member, name_attr, None):
                named = store.get(getattr(member, name_attr))
                if named is not None:
                    member.source = named.id


def stamp_scene_sources(project, scene) -> None:
    for members, name_attr, store, complete in _members(project, scene):
        for member in members:
            name = getattr(member, name_attr, None)
            if name:
                origin = next((i for i in store if i.name == name), None)
                if origin is not None and origin.id:
                    member.source = origin.id
            elif complete and _by_id(store, member.source) is not None:
                member.source = ""          # délié exprès (`prefab_name` vidé) : plus d'origine
