"""editor/codegen/actor_appearance.py — les apparences d'un porteur (acteur, prefab, partie de prefab).

Une apparence est un composant sprite dont le sprite existe et a une image. C'est le fait
unique que lisent le budget OAM, le writer OAM, le chargement des tuiles en VRAM et les
noms d'état des scripts : ils ne recalculent jamais chacun le leur."""
from __future__ import annotations

from core.models.components import displayed_sprite_component, sprite_components


def owner_appearances(project, owner) -> list[tuple]:
    """Les apparences RÉELLES d'un porteur (acteur, prefab, partie de prefab) :
    [(SpriteComponent, SpriteAsset)] dans l'ordre de ses composants, pour ceux
    dont le sprite existe et a une image. Un composant vide ou orphelin n'est pas
    une apparence — il n'a rien à afficher, donc rien à charger en VRAM."""
    out = []
    for c in sprite_components(owner):
        sprite = project.get_sprite(c.sprite_name) if c.sprite_name else None
        if sprite and sprite.asset:
            out.append((c, sprite))
    return out


def initial_appearance(project, owner) -> int:
    """Rang (dans `owner_appearances`) de l'apparence affichée au départ, ou -1 si
    aucun composant n'est actif : l'entrée existe alors, mais cachée."""
    shown = displayed_sprite_component(owner)
    for n, (c, _sprite) in enumerate(owner_appearances(project, owner)):
        if c is shown:
            return n
    return -1


def has_oam_entry(project, owner) -> bool:
    """Ce porteur peut-il afficher un sprite ? Seul un porteur d'AU MOINS UNE
    apparence occupe une entrée de `g_oam_entries[]` (marche 0b) : un contrôleur,
    un déclencheur ou un marqueur (point de tir, ancre de hitbox) n'en réserve
    aucune. Un porteur dont aucune apparence n'est active en réserve une, cachée
    (marche 3) : activer une apparence plus tard ne doit pas demander de slot.
    Le writer OAM et le budget lisent CE prédicat — jamais chacun le sien."""
    return bool(owner_appearances(project, owner))


def sprite_key(owner) -> list:
    """Les sprites qu'un acteur ou un prefab affiche, dans l'ordre de ses composants : ce que ses
    noms d'état (`play_anim("walk")`) résolvent en constantes, donc ce qui décide du C."""
    return [c.sprite_name for c in sprite_components(owner)]
