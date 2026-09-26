"""Fabriques partagées des tests de géométrie OAM.

Depuis la marche 0b de « La struct Actor allégée », seul un porteur de SPRITE
occupe une entrée OAM (`oam_alloc.has_oam_entry`). Un test qui compte des
entrées doit donc dire lesquels des acteurs affichent quelque chose."""
from __future__ import annotations

from core.models.components import SpriteComponent
from core.models.sprite import SpriteAsset

SPRITE = "TestSprite"


def donner_un_sprite(project, owner):
    """Fait afficher `owner` (Actor, Prefab ou partie de prefab) : un composant
    sprite pointant sur un SpriteAsset réel du projet. Rend `owner`."""
    if project.get_sprite(SPRITE) is None:
        project.sprites.append(SpriteAsset(name=SPRITE, asset="test.png"))
    if not any(isinstance(c, SpriteComponent) for c in owner.components):
        owner.components.append(SpriteComponent(sprite_name=SPRITE))
    return owner


def tout_afficher(project) -> None:
    """Chaque acteur posé, chaque prefab et chaque partie de prefab affiche un sprite."""
    for sc in project.scenes:
        for a in sc.actors:
            donner_un_sprite(project, a)
    for pf in project.prefabs:
        donner_un_sprite(project, pf)
        for part in getattr(pf, "children", []) or []:
            donner_un_sprite(project, part)
