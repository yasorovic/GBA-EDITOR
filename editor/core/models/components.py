"""Components — briques attachables à un Actor (système type ECS).
Un Actor a une liste de composants ; plusieurs instances du même
type sont autorisées (ex: CollisionShape "ground_check" + "sword_hitbox").
Chaque composant a un `id` (label libre, unique au sein de l'actor)
et un flag `active` pour le désactiver sans le retirer."""

import dataclasses
import math
from dataclasses import dataclass, field, fields
from typing import Optional

from core.models.field_value import FieldValue, Raw, number_raw
from core.models.settings import INTERACTIVE_COLLISION_TAG
from core.models.unique_name import unique_name


COLLISION_RESPONSE_BLOCK = "block"
COLLISION_RESPONSE_SENSOR = "sensor"
COLLISION_RESPONSES: tuple[str, ...] = (
    COLLISION_RESPONSE_BLOCK,
    COLLISION_RESPONSE_SENSOR,
)
# Sens unique d'une forme de réponse `block` : la face qu'elle offre n'arrête un corps que s'il vient du côté de
# sa normale. `gravity` = l'opposé de la gravité de la scène (la plateforme classique, « le haut » sous gravité
# vers le bas) ; les quatre autres fixent la normale, indépendamment de la gravité.
ONE_WAY_OFF = "off"
ONE_WAY_GRAVITY = "gravity"
ONE_WAY_MODES: tuple[str, ...] = (ONE_WAY_OFF, ONE_WAY_GRAVITY, "up", "down", "left", "right")
PHYSICS_BODY_STATIC = "StaticBody"
PHYSICS_BODY_CHARACTER = "CharacterBody"
PHYSICS_BODY_KINEMATIC = "KinematicBody"
PHYSICS_BODY_RIGID = "RigidBody"
PHYSICS_BODY_MODES: tuple[str, ...] = (
    PHYSICS_BODY_STATIC,
    PHYSICS_BODY_CHARACTER,
    PHYSICS_BODY_KINEMATIC,
    PHYSICS_BODY_RIGID,
)
_LEGACY_PHYSICS_BODY_MODES: dict[str, str] = {
    "static": PHYSICS_BODY_STATIC,
    "character": PHYSICS_BODY_CHARACTER,
    "kinematic": PHYSICS_BODY_KINEMATIC,
    "rigid": PHYSICS_BODY_RIGID,
}


@dataclass
class CollisionShapeComponent:
    """
    Boîte de collision AABB attachée à un Actor.

    `solid` décide d'UNE chose et d'une seule : cette box est-elle arrêtée par la
    CARTE DE COLLISION de la scène (murs, pentes, plafonds) ?

        solid=True  → l'acteur est repoussé par les tuiles, se pose sur les
                      pentes, se cogne aux plafonds
        solid=False → la carte l'ignore : à un script de gérer les tuiles s'il
                      le veut, via `collision_shape.get_tile`

    Les collisions acteur-contre-acteur ne le consultent PAS : les callbacks
    ci-dessous se déclenchent au recouvrement, quelle que soit la valeur. La
    docstring a longtemps prétendu que `solid` « repoussait les autres actors
    solides » — aucune ligne du runtime ne l'a jamais fait, et la v0.6.3 l'a
    découvert en cherchant qui avait droit à la résolution.

    `response` est la réponse entre acteurs, indépendante de la carte : `"block"` repousse un
    Character mobile hors de cette boîte, `"sensor"` ne fait que produire les événements de contact.
    La matrice de collision décide dans les deux cas quels tags se rencontrent. L'ancien champ
    `blocks_actors` n'existe plus : un projet qui le porte encore le perd à la lecture (rupture assumée).

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
    response: str = COLLISION_RESPONSE_SENSOR   # "block" ou "sensor" (cf. docstring)
    tag: str = "body"       # ex: "body", "ground_check", "hitbox", "hurtbox"
    material_id: str = ""   # id d'un PhysicMaterialComponent du même acteur ; vide = matériau par défaut
    one_way: str = ONE_WAY_OFF   # face à sens unique (cf. ONE_WAY_MODES) ; sans effet si la réponse est `sensor`
    # Offset de la boîte depuis la POSITION DE L'ACTEUR, en pixels : le coin haut-gauche du sprite, ou le centre de son cadre
    # quand `affine_transform` est actif (l'acteur est alors centré sur le cadre). Ce n'est PAS le pivot du sprite : pour une boîte de
    # 8 px centrée sur un sprite de 16 px, x vaut 4 (et non -4).
    x: int = 0
    y: int = 0
    w: int = 16
    h: int = 16

    def __post_init__(self):
        if self.response not in COLLISION_RESPONSES:
            raise ValueError(f"unknown collision response {self.response!r}, expected one of {COLLISION_RESPONSES}")
        self.material_id = str(self.material_id or "")
        if self.one_way not in ONE_WAY_MODES:
            raise ValueError(f"unknown one_way mode {self.one_way!r}, expected one of {ONE_WAY_MODES}")


@dataclass
class PhysicMaterialComponent:
    """Le matériau d'un contact : rebond et frottement, indépendants de la géométrie.

    Une CollisionShapeComponent le désigne par son `id` (`material_id`) ; sans désignation,
    ou si le composant est introuvable, la forme prend le matériau par défaut (0, 0).
    Pour un contact, le rebond retenu est le plus élevé des deux formes et le frottement
    leur moyenne géométrique."""
    id: str = "physic_material"
    active: bool = True
    restitution: float = 0.0
    friction: float = 0.0

    def __post_init__(self):
        if not math.isfinite(self.restitution) or not 0.0 <= self.restitution <= 1.0:
            raise ValueError("physic material restitution must be between 0 and 1")
        if not math.isfinite(self.friction) or not 0.0 <= self.friction <= 1.0:
            raise ValueError("physic material friction must be between 0 and 1")


def shape_material(owner, shape: CollisionShapeComponent) -> PhysicMaterialComponent:
    """Le matériau d'une forme : celui qu'elle désigne s'il est présent et actif, sinon le défaut.
    La source unique, appelée par le build."""
    if shape.material_id:
        for c in getattr(owner, "components", []):
            if isinstance(c, PhysicMaterialComponent) and c.active and c.id == shape.material_id:
                return c
    return PhysicMaterialComponent()


@dataclass
class PhysicsBodyComponent:
    """Le comportement physique de l'acteur, indépendant de ses colliders.

    `CharacterBody` est conduit explicitement par son script, est arrêté sur la
    normale des contacts Block et ne reçoit aucune impulsion. `KinematicBody`
    applique sa vélocité à chaque frame, pousse les corps dynamiques et
    transporte ceux qui reposent dessus. `RigidBody` applique sa vélocité après
    la gravité de scène. Ces trois modes résolvent carte et `block`;
    `StaticBody` n'intègre aucun mouvement et ne reçoit aucune impulsion. La
    position de son Actor reste néanmoins écrivable : la modifier téléporte sa
    géométrie, sans lui donner une vitesse. Les acteurs hérités sans composant
    gardent le comportement CharacterBody quand ils possèdent une boîte
    `solid`. Pour un `RigidBody`, `mass` répartit les impulsions entre deux
    corps, `gravity_scale` module la gravité de scène et `can_sleep` autorise
    la règle de sommeil de la scène. Ces valeurs sont intégrées au code généré
    et n'ajoutent aucun champ à l'Actor runtime. `use_scene_gravity` (vrai par
    défaut) fait réagir un CharacterBody ou un KinematicBody à la gravité de
    scène, multipliée par `gravity_scale`; un RigidBody la reçoit toujours.
    `collider_id` relie le corps à
    sa CollisionShape physique. Une valeur vide conserve provisoirement la
    sélection historique des boîtes `solid`.
    """
    id: str = "physics_body"
    active: bool = True
    mode: str = PHYSICS_BODY_CHARACTER
    collider_id: str = ""
    mass: float = 1.0
    gravity_scale: float = 1.0
    can_sleep: bool = True
    use_scene_gravity: bool = True

    def __post_init__(self):
        self.mode = _LEGACY_PHYSICS_BODY_MODES.get(self.mode, self.mode)
        self.collider_id = str(self.collider_id or "")
        if self.mode not in PHYSICS_BODY_MODES:
            raise ValueError(f"unknown physics body mode {self.mode!r}, expected one of {PHYSICS_BODY_MODES}")
        if not math.isfinite(self.mass) or not 0.1 <= self.mass <= 100.0:
            raise ValueError("physics body mass must be between 0.1 and 100")
        if not math.isfinite(self.gravity_scale) or not -8.0 <= self.gravity_scale <= 8.0:
            raise ValueError("physics body gravity scale must be between -8 and 8")


@dataclass
class SpriteComponent:
    id: str = "sprite"
    active: bool = True
    sprite_name: Optional[str] = None   # référence SpriteAsset.name
    initial_state: str = "Idle"         # nom de l'AnimState joué au démarrage
    facing_auto: bool = True            # le regard (facing) suit la dernière direction non nulle
    # Réserve un des 32 slots de matrice affine OAM de la scène pour ce sprite,
    # même si rotation/scale valent
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
# MOTEUR, sans qu'aucun script n'existe sur l'actor :
# le dispatch est piloté par la DONNÉE du component, pas par la présence d'une
# fonction Lua compilée. "on_destroy" passe par une table indexée par tag
# (cf. `actor_destroy_with_sfx`, runtime), "on_spawn" est injecté au spawn de
# l'actor ; "on_interact" suit la cible retenue par Interactive ; tout AUTRE trigger est un NOM de bouton ou d'action déclarée (la
# même liste que `input:pressed(nom)`, jamais une séquence ; décision du
# 2026-09-27, qui a remplacé les dix
# valeurs fixes `on_button_*` par ce nom libre).
SFX_AUTO_TRIGGERS: tuple[str, ...] = ("on_spawn", "on_destroy", "on_interact")


@dataclass
class SoundFxComponent:
    """
    Associe un Sfx à un actor.
    trigger="manual"     : ne joue rien automatiquement — appeler self:play_sfx() depuis un script.
    trigger="on_spawn"   : joue automatiquement au démarrage de l'actor, sans script.
    trigger="on_interact": joue quand cet acteur est atteint par une interaction (Interactive requis).
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


# ── Interactive ───────────────────────────────────────────────────────
# `InteractiveComponent` est un système AUTOMATISÉ : il réutilise les blocs que le codegen émet déjà
# (gestes d'entrée, test de recouvrement par couple de tags) et délivre `on_interact(who)` au script de
# l'acteur. Deux sélecteurs indépendants, qui se croisent :
#   saisie      — le GESTE sur l'entrée interne `interact` (Project Settings → Input) ;
#   interaction — comment l'interacteur (l'acteur portant le tag d'acteur « Player ») atteint la zone.
INTERACT_INPUT_MODES: tuple[str, ...] = ("pressed", "hold", "released")
INTERACT_AREA_MODES: tuple[str, ...] = ("hover", "facing")
# Taille de la boîte implicite quand l'acteur n'a pas de sprite (et que l'auteur n'en impose pas).
INTERACTIVE_DEFAULT_BOX = 16
INTERACTIVE_DEFAULT_HOLD = 30


@dataclass
class InteractiveComponent:
    """Rend un acteur interactif : `on_interact(who)` est appelé sur son script quand l'interacteur
    fait le geste voulu sur la zone.

    input_mode  : "pressed" (front montant), "hold" (tenu `hold_frames` frames d'affilée dans la zone),
                  "released" (relâché ALORS QUE l'interacteur est encore dans la zone, sinon rien).
    interaction : "hover" (l'interacteur recouvre la zone) ou "facing" (sa box, projetée dans son regard
                  sur la portée réglée dans les settings et arrêtée par les murs, touche la zone).
    box_tag     : "" = le composant crée sa propre boîte (tag `Interactive`, réservé), sans que l'auteur
                  en dessine une ; sinon le tag d'une CollisionShapeComponent DÉJÀ présente sur l'acteur.
    box_w/box_h : taille de la boîte implicite, en pixels ; 0 = automatique (le cadre du sprite, sinon
                  16×16). Ignorés quand `box_tag` désigne une boîte existante."""
    id: str = "interactive"
    active: bool = True
    input_mode: str = "pressed"
    hold_frames: int = INTERACTIVE_DEFAULT_HOLD
    interaction: str = "hover"
    box_tag: str = ""
    box_w: int = 0
    box_h: int = 0

    def __post_init__(self):
        if self.input_mode not in INTERACT_INPUT_MODES:
            self.input_mode = "pressed"
        if self.interaction not in INTERACT_AREA_MODES:
            self.interaction = "hover"
        self.hold_frames = max(1, int(self.hold_frames or INTERACTIVE_DEFAULT_HOLD))
        self.box_w = max(0, int(self.box_w or 0))
        self.box_h = max(0, int(self.box_h or 0))


def interactive_box_size(comp, frame_w: int = 0, frame_h: int = 0) -> tuple[int, int]:
    """La taille de la boîte implicite d'un composant Interactive, en pixels : la valeur de l'auteur
    si elle est posée, sinon le cadre du sprite, sinon 16×16.

    UNE fonction pour le canvas et le codegen : le canvas dessine ce que le build émet, jamais un
    repli à part."""
    w = comp.box_w or frame_w or INTERACTIVE_DEFAULT_BOX
    h = comp.box_h or frame_h or INTERACTIVE_DEFAULT_BOX
    return int(w), int(h)


MAX_COLLISION_SHAPES = 4      # `MAX_BOXES`, actor_types_static.h


def effective_collision_shapes(owner, frame_w: int = 0, frame_h: int = 0, centered: bool = False) -> list:
    """Les boîtes que le build pose sur un porteur : ses CollisionShapeComponent (au plus MAX_BOXES),
    PUIS la boîte propre de son composant Interactive actif quand celui-ci n'en désigne pas une
    existante — tag réservé `Interactive`, taille de `interactive_box_size`, solide et bloquante pour
    les acteurs en mode `facing` (un obstacle), ni l'un ni l'autre en mode `hover`.

    La source UNIQUE des boîtes d'un porteur : le codegen l'appelle, et le canvas devra l'appeler
    pour dessiner ce que le build émet. `centered` : le sprite est affine, l'acteur est centré sur
    son cadre (cf. `center_on_frame`) et la boîte propre l'est donc aussi."""
    boxes = [c for c in getattr(owner, "components", [])
             if isinstance(c, CollisionShapeComponent)][:MAX_COLLISION_SHAPES]
    comp = next((c for c in getattr(owner, "components", [])
                 if isinstance(c, InteractiveComponent) and c.active), None)
    if comp is not None and not comp.box_tag and len(boxes) < MAX_COLLISION_SHAPES:
        w, h = interactive_box_size(comp, frame_w, frame_h)
        # En mode `facing`, l'objet est un OBSTACLE contre lequel on s'arrête pour le viser (un coffre, un
        # panneau) : sa boîte propre bloque les acteurs. En mode `hover`, on doit pouvoir la recouvrir
        # (une plaque) : elle ne bloque pas.
        obstacle = comp.interaction == "facing"
        boxes.append(CollisionShapeComponent(
            id="interactive", solid=obstacle,
            response=COLLISION_RESPONSE_BLOCK if obstacle else COLLISION_RESPONSE_SENSOR, tag=INTERACTIVE_COLLISION_TAG,
            x=-(w // 2) if centered else 0, y=-(h // 2) if centered else 0, w=w, h=h))
    return boxes


def owner_effective_boxes(owner, sprite) -> list:
    """`effective_collision_shapes` d'un porteur dont le sprite affiché est `sprite` (ou None) : le
    cadre du sprite donne la taille de la boîte propre, et un sprite affine la centre. L'appel unique
    du build ET du canvas."""
    comp = affine_sprite_component(owner)
    return effective_collision_shapes(
        owner,
        sprite.frame_w if sprite else 0,
        sprite.frame_h if sprite else 0,
        centered=bool(comp is not None and comp.affine_transform))


def interactive_box_index(boxes: list, comp) -> int:
    """Le rang, dans `boxes` (cf. `effective_collision_shapes`), de la zone du composant : la boîte
    propre, ou la première boîte portant le tag désigné. -1 si elle n'y est pas."""
    tag = comp.box_tag or INTERACTIVE_COLLISION_TAG
    return next((i for i, b in enumerate(boxes) if (b.tag or "body") == tag), -1)


@dataclass
class TriggerComponent:
    """Fait d'une Area un DÉCLENCHEUR : ses contacts avec les acteurs préviennent leurs scripts, qui reçoivent
    `on_area_enter(area, my_box)`, `on_area_collide(area, my_box)` et `on_area_exit(area, my_box)` (`self` est
    l'acteur qui touche l'Area, `my_box` sa boîte en contact).

    Une Area sans ce composant ne teste aucun contact : elle ne coûte rien par frame, ce qui laisse la place aux
    effets qui n'ont pas besoin d'événements. Quels acteurs la touchent se décide par la matrice des tags du projet
    (le tag de la forme de l'Area contre ceux de leurs boîtes), comme entre deux acteurs. `active` désactive le
    déclencheur sans le retirer."""
    id: str = "trigger"
    active: bool = True


@dataclass
class GravityOverrideComponent:
    """Remplace, dans le volume de l'Area, la gravité de la scène : les corps qui la suivent (tout `RigidBody`, et les
    `CharacterBody` / `KinematicBody` dont `use_scene_gravity` est vrai) reçoivent cette gravité, toujours multipliée par leur
    `gravity_scale`, tant que leur boîte de physique recouvre l'Area. Unités : pixels par frame². Quand plusieurs zones se
    recouvrent, la dernière de la scène l'emporte (les gravités ne s'additionnent pas)."""
    id: str = "gravity_override"
    active: bool = True
    gravity_x: float = 0.0
    gravity_y: float = 0.1

    def __post_init__(self):
        for name in ("gravity_x", "gravity_y"):
            if not math.isfinite(getattr(self, name)) or not -8.0 <= getattr(self, name) <= 8.0:
                raise ValueError(f"gravity override {name} must be between -8 and 8")


@dataclass
class ForceFieldComponent:
    """Un champ de force dans le volume de l'Area (vent, courant, eau), appliqué avant la gravité du pas physique aux corps
    `KinematicBody` et `RigidBody` dont la boîte de physique recouvre l'Area ; les `CharacterBody` seulement avec
    `affects_characters`.

    `force_x` / `force_y` : accélération constante (pixels par frame²). `turbulence` : amplitude d'une secousse aléatoire
    ajoutée à chaque frame sur les deux axes (générateur congruentiel linéaire, donc déterministe). `buoyancy` : fraction de
    la gravité annulée quand le CENTRE de la boîte du corps est dans la zone (1.0 = flottaison neutre, plus = le corps
    remonte). `drag` : fraction de la vitesse perdue à chaque frame (viscosité, 0 = l'air libre)."""
    id: str = "force_field"
    active: bool = True
    force_x: float = 0.0
    force_y: float = 0.0
    turbulence: float = 0.0
    buoyancy: float = 0.0
    drag: float = 0.0
    affects_characters: bool = False

    def __post_init__(self):
        bounds = {"force_x": (-8.0, 8.0), "force_y": (-8.0, 8.0), "turbulence": (0.0, 8.0),
                  "buoyancy": (0.0, 4.0), "drag": (0.0, 1.0)}
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"force field {name} must be between {low:g} and {high:g}")


@dataclass
class AudioEmitterComponent:
    """Fait d'une Area un ÉMETTEUR sonore : un effet (`Sfx`) joué en continu tant que l'écouteur est dans la zone audible.

    L'écouteur est le centre de la caméra. La zone audible est la forme de l'Area plus une marge de `falloff` pixels : plein
    volume dans la forme, puis décroissance linéaire jusqu'à zéro à `falloff` pixels du rectangle (distance sans racine
    carrée). Hors de la zone audible l'émetteur est coupé et ne tient plus de canal. `volume` : pourcentage du volume de
    l'effet. `panning` : placer le son à gauche ou à droite selon la position de l'Area par rapport à l'écouteur.

    La boucle se fait par relance : quand l'effet est fini et que l'écouteur est toujours dans la zone, il repart à la frame
    suivante (au plus une frame de silence). Un effet n'a pas de boucle d'échantillon."""
    id: str = "audio_emitter"
    active: bool = True
    sfx_name: Optional[str] = None
    volume: int = 100
    falloff: int = 64
    panning: bool = False

    def __post_init__(self):
        if not 0 <= int(self.volume) <= 100:
            raise ValueError("audio emitter volume must be between 0 and 100")
        if not 0 <= int(self.falloff) <= 255:
            raise ValueError("audio emitter falloff must be between 0 and 255")


@dataclass
class ScriptComponent:
    id: str = "script"
    active: bool = True
    script: Optional[str] = None        # chemin relatif vers le .lua
    exports_values: dict = field(default_factory=dict)  # valeurs overrides par instance


# Registre type-name -> classe, utilisé pour la (dé)sérialisation
# polymorphe et pour piloter le menu "+ Component" de l'UI.
COMPONENT_REGISTRY: dict = {
    "collision_shape": CollisionShapeComponent,
    "physic_material": PhysicMaterialComponent,
    "physics_body":  PhysicsBodyComponent,
    "sprite":        SpriteComponent,
    "sound_fx":      SoundFxComponent,
    "interactive":   InteractiveComponent,
    "trigger":       TriggerComponent,
    "gravity_override": GravityOverrideComponent,
    "force_field":   ForceFieldComponent,
    "audio_emitter": AudioEmitterComponent,
    "script":        ScriptComponent,
}


# Un seul composant de ces types par acteur : le script et le moteur les adressent par leur
# type (`self:physics_body()`), jamais par un id. L'inspecteur n'en montre donc pas.
SINGLETON_COMPONENTS = frozenset({"physics_body", "interactive", "trigger", "gravity_override", "force_field", "audio_emitter", "script"})


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


# Migration à la lecture : `SoundFxComponent.trigger` visait un des dix
# `on_button_*` — il vise désormais un NOM (bouton ou action déclarée), la
# même liste que `input:pressed(nom)`. Un projet plus ancien ne perd rien.
_LEGACY_SFX_TRIGGERS: dict = {
    "on_button_a": "a", "on_button_b": "b", "on_button_l": "l", "on_button_r": "r",
    "on_button_start": "start", "on_button_select": "select",
    "on_button_up": "up", "on_button_down": "down",
    "on_button_left": "left", "on_button_right": "right",
}


# Migration à la lecture : `CollisionBoxComponent` (clé "collision_box") est devenu
# CollisionShapeComponent, et son rebond/frottement un PhysicMaterialComponent à part.
_LEGACY_COLLISION_SHAPE_TYPE = "collision_box"


def _legacy_shape_material(cd: dict) -> Optional[PhysicMaterialComponent]:
    """Le matériau d'une ancienne boîte qui portait un rebond ou un frottement non nul, sinon None.
    Retire ces deux champs de `cd`."""
    restitution, friction = cd.pop("restitution", 0.0), cd.pop("friction", 0.0)
    if not (restitution or friction):
        return None
    return PhysicMaterialComponent(id=f"{cd.get('id', 'collision')}_material",
                                   restitution=restitution, friction=friction)


def components_from_list(data: list) -> list:
    """Inverse de components_to_list."""
    components = []
    for cd in data:
        cd = dict(cd)
        type_name = cd.pop("component_type", None)
        if type_name == _LEGACY_COLLISION_SHAPE_TYPE:
            type_name = "collision_shape"
            material = _legacy_shape_material(cd)
            if material is not None:
                cd["material_id"] = material.id
                components.append(material)
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
        if not isinstance(comp, CollisionShapeComponent):
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
        comp.id = unique_name(comp.id, existing_ids)
        self.components.append(comp)
        return comp
