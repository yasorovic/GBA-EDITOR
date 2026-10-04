"""Components — briques attachables à un Actor (système type ECS).
Un Actor a une liste de composants ; plusieurs instances du même
type sont autorisées (ex: CollisionBox "ground_check" + "sword_hitbox").
Chaque composant a un `id` (label libre, unique au sein de l'actor)
et un flag `active` pour le désactiver sans le retirer."""

import dataclasses
from dataclasses import dataclass, field, fields
from typing import Optional

from core.models.field_value import FieldValue, Raw, number_raw


@dataclass
class CollisionBoxComponent:
    """
    Boîte de collision AABB attachée à un Actor.

    `solid` décide d'UNE chose et d'une seule : cette box est-elle arrêtée par la
    CARTE DE COLLISION de la scène (murs, pentes, plafonds) ?

        solid=True  → l'acteur est repoussé par les tuiles, se pose sur les
                      pentes, se cogne aux plafonds (cf. ROADMAP v0.6.3)
        solid=False → la carte l'ignore : à un script de gérer les tuiles s'il
                      le veut, via `collision_box.get_tile`

    Les collisions acteur-contre-acteur ne le consultent PAS : les callbacks
    ci-dessous se déclenchent au recouvrement, quelle que soit la valeur. La
    docstring a longtemps prétendu que `solid` « repoussait les autres actors
    solides » — aucune ligne du runtime ne l'a jamais fait, et la v0.6.3 l'a
    découvert en cherchant qui avait droit à la résolution.

    Handlers Lua appelés par le runtime C. Ils n'appartiennent PAS à ce
    composant : ce sont des fonctions globales du script de l'actor, et le
    codegen se contente de regarder lesquelles le .lua définit.

        on_collision_enter(other, my_box, other_box)  — premier frame de contact
        on_collision_exit(other, my_box, other_box)   — premier frame sans contact
        on_collide(other, my_box, other_box)          — chaque frame de contact
        on_tile_collide(normal_x, normal_y)           — choc contre la carte

    `other` est une référence d'actor (pas un index) ; `my_box`/`other_box`
    valent une constante `BOXTAG_<TAG>` dérivée du champ `tag` ci-dessous —
    c'est ainsi qu'un script distingue quelle box a touché, y compris entre
    boxes solides et boxes trigger : il n'existe pas de handler trigger séparé.

    tag : label libre pour que le script distingue plusieurs colliders
          sur un même actor (ex: "body", "sword_hitbox", "ground_check").
    """
    id: str = "collision"
    active: bool = True
    solid: bool = True      # arrêté par la carte de collision (cf. docstring)
    tag: str = "body"       # ex: "body", "ground_check", "hitbox", "hurtbox"
    x: int = 0              # offset relatif au pivot du sprite (pixels)
    y: int = 0
    w: int = 16
    h: int = 16


@dataclass
class SpriteComponent:
    id: str = "sprite"
    active: bool = True
    sprite_name: Optional[str] = None   # référence SpriteAsset.name
    initial_state: str = "Idle"         # nom de l'AnimState joué au démarrage
    auto_dir: bool = True               # calcule dir depuis vélocité automatiquement
    # Réserve un des 32 slots de matrice affine OAM de la scène pour ce sprite
    # (cf. ARCHITECTURE.md « Le modèle affine »), même si rotation/scale valent
    # leur défaut. C'est une capacité de RENDU : elle vit donc sur le composant
    # de rendu, et pas sur l'Actor — qui garde son rotation/scale MONDE comme
    # état de jeu, lisible et écrivable par un script dans tous les cas. Sans
    # cette case, l'actor tourne pour la logique, pas pour l'écran.
    affine_transform: bool = False
    # Transform affine LOCAL. Il se compose par-dessus le transform MONDE de
    # l'actor — rotation locale ajoutée à la rotation de l'actor, scale local
    # multiplié par le scale de l'actor. Sans `affine_transform`, aucun slot
    # n'est alloué et le sprite est émis en OAM normale : ces valeurs ne se
    # voient pas.
    scale_x: Raw = 1.0                 # affine OAM (1.0 = normal), local
    scale_y: Raw = 1.0
    rotation: Raw = 0                  # degrés 0–359 (OAM affine), local
    # Position du sprite RELATIVE à son actor, en pixels, dans le repère local de
    # l'actor : l'offset tourne/scale AVEC l'actor (hérarchie parent→enfant). Le
    # sprite n'a pas de position monde — la position monde reste Actor.x/y.
    # Raw : px (`int`), tiles ou variable — cf. core/models/field_value.py.
    offset_x: Raw = 0
    offset_y: Raw = 0
    # POINT DE PIVOT du sprite, en pixels, à partir du CENTRE du cadre : (0, 0) =
    # le centre. Rotation, échelle et flip s'exercent autour de lui, et il reste
    # fixe à l'écran pendant que le reste du sprite tourne. Distinct de l'offset
    # (qui déplace le cadre entier) : l'offset dit OÙ est le sprite, le pivot dit
    # AUTOUR DE QUOI il se transforme. Raw : px, tiles ou variable.
    pivot_x: Raw = 0
    pivot_y: Raw = 0

    def __post_init__(self):
        self.scale_x  = number_raw(self.scale_x, float)
        self.scale_y  = number_raw(self.scale_y, float)
        self.rotation = number_raw(self.rotation, int)
        self.offset_x = FieldValue.parse(self.offset_x).to_raw()
        self.offset_y = FieldValue.parse(self.offset_y).to_raw()
        self.pivot_x = FieldValue.parse(self.pivot_x).to_raw()
        self.pivot_y = FieldValue.parse(self.pivot_y).to_raw()


# Triggers de SoundFxComponent AUTRES que "manual" — tous DÉCLENCHÉS PAR LE
# MOTEUR, sans qu'aucun script n'existe sur l'actor (ROADMAP, 2026-08-24) :
# le dispatch est piloté par la DONNÉE du component, pas par la présence d'une
# fonction Lua compilée. "on_destroy" passe par une table indexée par tag
# (cf. `actor_destroy_with_sfx`, runtime), "on_spawn" est injecté au spawn de
# l'actor ; tout AUTRE trigger est un NOM de bouton ou d'action déclarée (la
# même liste que `input:pressed(nom)`, jamais une séquence — ROADMAP « Les
# inputs personnalisés », tranche finale, 2026-09-27, qui a remplacé les dix
# valeurs fixes `on_button_*` par ce nom libre).
SFX_AUTO_TRIGGERS: tuple[str, ...] = ("on_spawn", "on_destroy")


@dataclass
class SoundFxComponent:
    """
    Associe un Sfx à un actor.
    trigger="manual"     : ne joue rien automatiquement — appeler self:play_sfx() depuis un script.
    trigger="on_spawn"   : joue automatiquement au démarrage de l'actor, sans script.
    trigger="on_destroy" : joue juste avant que l'actor soit désactivé (self:destroy() ou
                            other:destroy() depuis N'IMPORTE QUEL script), sans script sur CET actor.
    trigger=<nom>         : un bouton ou une action déclarée (Project Settings → Input → Inputs,
                            jamais une séquence) — joue tant que cet actor est actif et que
                            l'accord vient d'être pressé (front montant), sans script. Pratique
                            pour un item de menu qui joue un son sans une ligne de Lua.
    """
    id: str = "sound_fx"
    active: bool = True
    sfx_name: Optional[str] = None      # référence Sfx.name
    trigger: str = "manual"             # "manual" | SFX_AUTO_TRIGGERS | un nom de bouton/action


@dataclass
class ScriptComponent:
    id: str = "script"
    active: bool = True
    script: Optional[str] = None        # chemin relatif vers le .lua
    exports_values: dict = field(default_factory=dict)  # valeurs overrides par instance


# Registre type-name -> classe, utilisé pour la (dé)sérialisation
# polymorphe et pour piloter le menu "+ Component" de l'UI.
COMPONENT_REGISTRY: dict = {
    "collision_box": CollisionBoxComponent,
    "sprite":        SpriteComponent,
    "sound_fx":      SoundFxComponent,
    "script":        ScriptComponent,
}


def component_type_name(comp) -> str:
    """Nom de type (clé COMPONENT_REGISTRY) d'une instance de composant."""
    for type_name, klass in COMPONENT_REGISTRY.items():
        if isinstance(comp, klass):
            return type_name
    raise ValueError(f"Unknown component type: {comp!r}")


def components_to_list(components: list) -> list[dict]:
    """Sérialise une liste de Component polymorphes (utilisé par Actor ET Prefab)."""
    return [
        {"component_type": component_type_name(c), **dataclasses.asdict(c)}
        for c in components
    ]


# Migration à la lecture (ROADMAP « Les inputs personnalisés », tranche
# finale, 2026-09-27) : `SoundFxComponent.trigger` visait un des dix
# `on_button_*` — il vise désormais un NOM (bouton ou action déclarée), la
# même liste que `input:pressed(nom)`. Un projet plus ancien ne perd rien.
_LEGACY_SFX_TRIGGERS: dict = {
    "on_button_a": "a", "on_button_b": "b", "on_button_l": "l", "on_button_r": "r",
    "on_button_start": "start", "on_button_select": "select",
    "on_button_up": "up", "on_button_down": "down",
    "on_button_left": "left", "on_button_right": "right",
}


def components_from_list(data: list) -> list:
    """Inverse de components_to_list."""
    components = []
    for cd in data:
        cd = dict(cd)
        type_name = cd.pop("component_type", None)
        klass = COMPONENT_REGISTRY.get(type_name)
        if not klass:
            continue
        valid = {f.name for f in fields(klass)}
        comp = klass(**{k: v for k, v in cd.items() if k in valid})
        if isinstance(comp, SoundFxComponent) and comp.trigger in _LEGACY_SFX_TRIGGERS:
            comp.trigger = _LEGACY_SFX_TRIGGERS[comp.trigger]
        components.append(comp)
    return components


# ── Les apparences d'un porteur (marche 3 de « La struct Actor allégée ») ──
# Un acteur, un prefab ou une partie de prefab affiche UN sprite, mais peut porter
# plusieurs `SpriteComponent` : chacun est une APPARENCE. `active` est le
# sélecteur — au plus un composant actif à la fois, activer l'un désactive
# l'autre. Ces trois fonctions sont la seule façon de lire « le » sprite d'un
# porteur : aucun site ne doit reprendre `get_component("sprite")`, qui rend
# le premier composant, actif ou non.

def sprite_components(owner) -> list:
    """Toutes les apparences d'un porteur, dans l'ordre de ses composants."""
    return [c for c in getattr(owner, "components", []) if isinstance(c, SpriteComponent)]


def center_on_frame(owner, sprite_comp, sprite) -> list:
    """Quand « Affine transform » est coché : pose l'acteur au CENTRE du cadre.

    Sur GBA native, un sprite affine pivote sur le centre de sa texture ; le cas
    courant est donc un acteur dont la position EST ce centre. Le sprite reçoit
    pour offset `(-largeur/2, -hauteur/2)` et les boîtes de collision restées à
    leur position d'origine `(0, 0)` reçoivent `(-w/2, -h/2)` : elles continuent
    d'entourer le sprite.

    N'écrase jamais un réglage de l'auteur (offset ou boîte déjà déplacés) ni une
    valeur liée à une variable. Retourne les composants modifiés."""
    changed = []
    if sprite is None or not sprite_comp:
        return changed
    if (FieldValue.parse(sprite_comp.offset_x).to_raw() == 0
            and FieldValue.parse(sprite_comp.offset_y).to_raw() == 0):
        sprite_comp.offset_x = -(sprite.frame_w // 2)
        sprite_comp.offset_y = -(sprite.frame_h // 2)
        changed.append(sprite_comp)
    for comp in getattr(owner, "components", []):
        if not isinstance(comp, CollisionBoxComponent):
            continue
        fx, fy = FieldValue.parse(comp.x), FieldValue.parse(comp.y)
        fw, fh = FieldValue.parse(comp.w), FieldValue.parse(comp.h)
        if (fx.to_raw(), fy.to_raw()) != (0, 0) or fw.is_ref or fh.is_ref:
            continue
        comp.x, comp.y = -(fw.px() // 2), -(fh.px() // 2)
        changed.append(comp)
    return changed


def displayed_sprite_component(owner):
    """L'apparence AFFICHÉE au départ : le composant sprite actif qui désigne un
    sprite, ou None (rien n'est affiché, même si des apparences existent)."""
    return next((c for c in sprite_components(owner) if c.active and c.sprite_name), None)


def competing_sprite_components(owner, comp) -> list:
    """Les apparences à DÉSACTIVER quand on active `comp` : celles qui sont actives.
    « Activer l'une désactive l'autre » — la règle vit ici, pas dans l'inspecteur."""
    return [c for c in sprite_components(owner) if c is not comp and c.active]


def affine_sprite_component(owner):
    """Le composant qui décide de l'affine de l'entrée OAM. Le slot de matrice
    appartient à l'ENTRÉE, pas à l'apparence : si un composant est affine,
    l'entrée l'est. À défaut, l'apparence affichée, puis la première."""
    comps = sprite_components(owner)
    return (next((c for c in comps if c.affine_transform), None)
            or displayed_sprite_component(owner)
            or (comps[0] if comps else None))


class ComponentOwnerMixin:
    """
    Mixin pour tout objet possédant une liste `components` de type ECS
    (Actor et Prefab). Fournit la manipulation des composants ; chaque
    classe garde son propre to_dict/from_dict (chemins/dossiers différents).
    """

    def get_component(self, comp_type: str):
        """Premier composant du type donné (ou None)."""
        klass = COMPONENT_REGISTRY[comp_type]
        return next((c for c in self.components if isinstance(c, klass)), None)

    def add_component(self, comp_type: str, **kwargs):
        klass = COMPONENT_REGISTRY[comp_type]
        comp = klass(**kwargs)
        # Garantir un id unique au sein de l'actor (ex: "collision", "collision_2", ...)
        existing_ids = {c.id for c in self.components}
        if comp.id in existing_ids:
            n = 2
            base = comp.id
            while f"{base}_{n}" in existing_ids:
                n += 1
            comp.id = f"{base}_{n}"
        self.components.append(comp)
        return comp
