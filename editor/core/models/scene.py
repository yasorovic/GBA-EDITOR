"""Actor / Prefab / Scene — entités placées dans une scène + la scène elle-même."""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.palette import OWN_PAL_BANK
from core.models.components import (
    ComponentOwnerMixin, components_to_list, components_from_list, ScriptComponent,
    SpriteComponent, affine_sprite_component,
)
from core.models.background import BackgroundLayer, decode_tile_palette_overrides
from core.models.camera import Camera
from core.models.ui_region import InterfaceNode

# Les types de tuiles de collision et leur géométrie vivent dans leur propre
# module (feuille, il n'importe rien) : ils sont réclamés par l'outil de
# peinture, par le canvas qui les dessine et par le codegen qui les émet en C.
from core.models.collision_tiles import TILE_EMPTY, COLLISION_TILE_SIZE

# ── Slots BG valides par mode vidéo ───────────────────────────────
# SOURCE DE VÉRITÉ (cœur) du matériel : quels slots BG existent dans chaque mode
# DISPCNT. Mode 0 : 4 layers tuilés ; 1 : 3 ; 2 : 2 (les deux affines) ; 3-5 :
# bitmap, une seule surface sur BG2. L'UI en dérive son affichage (`MODE_INFO`)
# et le validateur les slots permis d'un nœud Interface — un seul endroit à tenir.
BG_SLOTS_BY_MODE: dict[int, tuple] = {
    0: (0, 1, 2, 3),
    1: (0, 1, 2),
    2: (2, 3),
    3: (2,),
    4: (2,),
    5: (2,),
}

# ── Mélange de couleurs (BLDCNT / BLDALPHA / BLDY) ────────────────
# **Le mode est GLOBAL à l'écran**, pas par layer : `BLDCNT` n'a qu'un champ
# mode (bits 6-7). Ce qui est par layer est son appartenance à l'ensemble du
# DESSUS (bits 0-5, ce qui est mélangé) ou du DESSOUS (bits 8-13, ce avec quoi,
# situé derrière selon les priorités). D'où le partage : le mode et les
# coefficients sur la Scene, le rôle sur le BackgroundLayer.
#
# Le mélange ne se produit QUE là où un pixel du dessus a effectivement un pixel
# du dessous derrière lui — c'est la cause n°1 des « alpha qui ne font rien »,
# et ce que le validateur doit dire.
BLEND_NONE     = 0   # aucun mélange — le défaut, et le comportement d'avant
BLEND_ALPHA    = 1   # dessus×EVA + dessous×EVB, saturé à 31 par canal
BLEND_BRIGHTEN = 2   # le dessus fond vers le BLANC, intensité EVY
BLEND_DARKEN   = 3   # le dessus fond vers le NOIR, intensité EVY
BLEND_MODES = (BLEND_NONE, BLEND_ALPHA, BLEND_BRIGHTEN, BLEND_DARKEN)

# Les modes 2 et 3 n'emploient QUE le dessus : désigner un dessous n'y change
# rien. L'inspecteur s'en sert pour griser le rôle « dessous » plutôt que de
# laisser composer un réglage sans effet.
BLEND_NEEDS_BOTTOM = (BLEND_ALPHA,)

BLEND_TOP    = "top"      # première cible — ce qui est mélangé
BLEND_BOTTOM = "bottom"   # seconde cible — ce avec quoi, situé DERRIÈRE
BLEND_ROLES  = ("", BLEND_TOP, BLEND_BOTTOM)

# Coefficients 0-16, bornes MATÉRIELLES (5 bits, valeurs >16 se comportent
# comme 16). 16 = « en entier », 0 = « rien ».
BLEND_EV_MAX = 16


def clamp_ev(v) -> int:
    try:
        return max(0, min(BLEND_EV_MAX, int(v)))
    except (TypeError, ValueError):
        return 0


def blend_role_of(layer) -> str:
    """Rôle d'un layer, normalisé — une valeur inconnue vaut « aucun »."""
    r = getattr(layer, "blend_role", "")
    return r if r in BLEND_ROLES else ""


# ── Vocabulaire des transitions de scène (v0.6.2) ─────────────────
# Un fondu joué en QUITTANT et en OUVRANT une scène (cf. `transition_of`). Ces
# noms servaient AUSSI à une authoring d'effet de blend au niveau scène, retirée
# depuis : le blending vit désormais PAR-CALQUE au runtime (`blend.*`/`layer.*`,
# BLDCNT n'a qu'un mode). Seuls les trois que la transition emploie subsistent.
EFFECT_NONE        = "none"
EFFECT_FADE_BLACK  = "fade_black"    # mode 3, tout l'écran
EFFECT_FADE_WHITE  = "fade_white"    # mode 2, tout l'écran

# Transitions de scène (v0.6.2) — le fondu joué en QUITTANT et en OUVRANT une
# scène. Volontairement le même vocabulaire que les effets ci-dessus : c'est le
# même effet matériel (BLDCNT mode 2/3 + BLDY sur tout l'écran), seul le moment
# où il est joué diffère. `TRANSITION_INHERIT` n'existe qu'au niveau de la
# scène — c'est l'absence de surcharge, donc le réglage du projet.
TRANSITION_INHERIT = ""              # la scène suit ProjectSettings
TRANSITION_KINDS = (EFFECT_NONE, EFFECT_FADE_BLACK, EFFECT_FADE_WHITE)

# `Scene.font_pal_banks` — banque de palette d'une police, PAR NOM, l'analogue
# de `Actor.pal_bank` pour un asset sans instance posée. Deux familles de valeur :
#   - absente / `OWN_PAL_BANK` : la police charge sa PROPRE palette dans une
#     banque allouée (comme un sprite, cf. `codegen.palette_alloc`) ;
#   - 0-15 : la police lit son encre dans cette palette de scène (override).
#
# La « banque du conteneur » N'EST PLUS une valeur à poser : un texte enfant d'un
# conteneur à fond PREND automatiquement la banque de ce conteneur (par zone, cf.
# `RegionFill.bank` runtime). `font_pal_banks` ne concerne donc que les usages
# LIBRES d'une police.
#
# La clé `""` désigne la police PAR DÉFAUT de la scène (stable quel que soit son
# nom, cible unique du sélecteur « UI colors ») ; toute autre clé est un nom de
# police. `font_pal_key()` fait la correspondance, `scene_font_pal_bank()` la
# lecture. Remplace l'ancien scalaire `ui_pal_bank`, migré à la lecture sur cette
# clé par défaut.


def font_pal_key(font_name: str, default_font_name: str) -> str:
    """Clé de `Scene.font_pal_banks` pour une police. La police PAR DÉFAUT de la
    scène passe par la clé `""` — stable quand son nom change, et cible unique du
    sélecteur « UI colors » ; une police nommée non-défaut passe par son nom. Une
    police héritée (`font_name` vide) EST la police par défaut, donc `""` aussi."""
    return "" if font_name == default_font_name else font_name


def scene_font_pal_bank(scene, font_name: str, default_font_name: str) -> int:
    """Banque de palette d'une police dans une scène : un override (slot 0-15),
    ou `OWN_PAL_BANK` par défaut (palette propre à allouer). Source unique lue
    par l'allocateur, le codegen et l'aperçu — jamais recalculée à côté. Un texte
    imbriqué dans un conteneur ignore ceci et prend la banque du conteneur."""
    banks = getattr(scene, "font_pal_banks", None) or {}
    return int(banks.get(font_pal_key(font_name, default_font_name), OWN_PAL_BANK))


def _font_pal_banks_from_dict(d: dict) -> dict:
    """Lit `font_pal_banks`, ou migre l'ancien scalaire `ui_pal_bank` sur la
    police par défaut (clé `""`). Seul un SLOT désigné (0-15) se migre : `-1`
    (automatique) comme l'ancien sentinel « banque du conteneur » (-2, désormais
    automatique par zone) n'ont rien à porter — absents de la map = OWN."""
    raw = d.get("font_pal_banks")
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    legacy = int(d.get("ui_pal_bank", OWN_PAL_BANK))
    return {"": legacy} if 0 <= legacy < 16 else {}


def _ui_nodes_from_dict(d: dict) -> list:
    """Lit les nœuds `Interface` d'une scène (v0.12) en tolérant les trois formes
    historiques. Un nom nu (v0.25) devient un nœud à migrer : `anchor=""` (la
    cible sera recopiée depuis l'asset à la première résolution) et `bg_slot`
    hérité de l'ancien `Scene.text_bg`, ce qui préserve deux scènes qui
    partageaient un layout avec deux `text_bg` différents."""
    raw = d.get("ui_layouts")
    if raw is None:
        raw = [d["ui_layout"]] if d.get("ui_layout") else []
    text_bg = int(d.get("text_bg", 1))
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(InterfaceNode.from_dict(item))
        elif isinstance(item, str):
            out.append(InterfaceNode(layout_name=item, anchor="", bg_slot=text_bg))
    return out


# Musique de la scène (v0.8.2) — TROIS valeurs, pas deux.
#
# `MUSIC_INHERIT` (le défaut) ne veut pas dire « silence » mais « ne touche à
# rien » : traverser une porte ne doit pas redémarrer le thème, et c'est aussi
# le cas le moins cher — aucun appel n'est émis. Le silence, lui, se DÉCLARE ;
# il ne s'obtient pas en laissant un champ vide.
#
# Contrairement aux transitions, il n'y a PAS de réglage de projet : « le
# morceau par défaut du jeu » n'a pas de sens, c'est la scène de démarrage qui
# le pose et l'héritage le propage tout seul.
MUSIC_INHERIT = ""
MUSIC_NONE    = "none"
# Le mode BLDCNT que chaque type demande — 0 = aucune transition. C'est ce que
# le codegen émet, le runtime ne connaissant que des modes de mélange.
TRANSITION_MODES = {EFFECT_NONE: BLEND_NONE,
                    EFFECT_FADE_BLACK: BLEND_DARKEN,
                    EFFECT_FADE_WHITE: BLEND_BRIGHTEN}


def transition_of(scene, settings) -> tuple[str, int]:
    """La transition EFFECTIVE d'une scène : la sienne, ou celle du projet.

    Source unique de la règle d'héritage — le codegen la résout au build (le
    runtime ne connaît pas la notion) et l'inspecteur s'en sert pour dire à
    l'auteur ce qu'il obtient réellement. La surcharge porte sur le COUPLE :
    une scène hérite des deux valeurs ou définit les deux, sans quoi « durée
    héritée, type surchargé » deviendrait un état à expliquer."""
    kind = getattr(scene, "transition_kind", TRANSITION_INHERIT) or TRANSITION_INHERIT
    if kind == TRANSITION_INHERIT:
        kind = getattr(settings, "transition_kind", EFFECT_NONE) or EFFECT_NONE
        frames = int(getattr(settings, "transition_frames", 16))
    else:
        frames = int(getattr(scene, "transition_frames", 16))
    if kind not in TRANSITION_KINDS:
        kind = EFFECT_NONE
    return kind, max(1, frames)


def make_collision_map(width_px: int, height_px: int) -> list[list[int]]:
    """Crée une grille vide (TILE_EMPTY) aux dimensions de la scène en pixels."""
    cols = max(1, (width_px  + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    rows = max(1, (height_px + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    return [[TILE_EMPTY] * cols for _ in range(rows)]


def _components_with_affine_migrated(d: dict) -> list:
    """Décode `components` en reportant l'ancienne clé `affine_transform`.

    Elle vivait sur l'Actor / le Prefab jusqu'au 2026-08-25 ; elle vit désormais
    sur le SpriteComponent (cf. ARCHITECTURE.md « Le modèle affine »). Relue une
    fois à l'ouverture, elle n'est plus jamais réécrite — un projet enregistré
    depuis cette version ne la porte plus.

    Un actor sans SpriteComponent n'a jamais rien réservé (`_compute_affine_info`
    passait déjà son tour) : il n'y a rien à reporter."""
    components = components_from_list(d.get("components", []))
    if d.get("affine_transform"):
        for c in components:
            if isinstance(c, SpriteComponent):
                c.affine_transform = True
                break
    return components


# ──────────────────────────────────────────────────────────────────
#  Prefab — template réutilisable. Stocké dans project/prefab/{name}.json.
#  Jamais compilé ni placé directement dans une scène.
#  Instancier un Prefab = copie ponctuelle de ses Components dans un
#  nouvel Actor inline (aucun lien vivant après la création).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Prefab(Resource, ComponentOwnerMixin):
    name: str = "Prefab"
    # Un prefab EST son actor racine : components, palette, réservation
    # affine, notes — le MÊME `Actor` qu'un acteur de scène, celui que
    # ActorInspector.load() sait déjà éditer, pas une seconde définition à
    # tenir d'accord (cf. property de délégation ci-dessous). `Actor` est
    # défini plus bas dans ce fichier ; le default_factory ne le résout qu'à
    # la construction, pas à la définition de la classe.
    #
    # x/y/rotation/parent/etc de cet actor n'ont pas de sens pour un
    # template — jamais posé nulle part — et ne sont jamais sérialisés ici
    # (cf. to_dict) : c'est le TYPE qui est réutilisé, pas le sens de la pose.
    actor: "Actor" = field(default_factory=lambda: Actor(name="Prefab"))
    # (Le pool se déclare sur la SCÈNE — `Scene.prefab_pools`, ROADMAP v0.17 —
    # parce que combien d'exemplaires vivent en même temps est une propriété du
    # niveau, pas du template. L'ancien champ `Prefab.max_instances` a été retiré
    # en T7 : la compilation par scène l'a rendu inerte — plus aucun repli ne le
    # lisait — et le garder aurait laissé croire qu'il pilotait encore un pool.
    # `from_dict` ignore la clé si un vieux projet la porte encore.)
    # Le SOUS-ARBRE du template (ROADMAP v0.23) : un prefab est un arbre, pas
    # un objet plat — c'est ce que le `PackedScene` de Godot a de bon, et on
    # n'en prend que ceci. Une chenille à cinq anneaux ou un mini-boss segmenté
    # redevient spawnable.
    #
    # Une partie est un `Actor` : « une partie est ce qu'un acteur est déjà,
    # des composants et un transform local ». Réutiliser le type plutôt que
    # d'en écrire un second, c'est aussi réutiliser l'arbre, la profondeur, la
    # composition et le partage de slot affine déjà écrits pour les acteurs de
    # scène — un seul modèle à tenir d'accord au lieu de deux.
    #
    # `Actor.parent` d'une partie nomme une AUTRE PARTIE, ou vaut vide pour
    # descendre de la racine. Rien d'extérieur n'est nommable : c'est ce qui
    # garde la profondeur connue au build, donc le tri possible.
    #
    # Les parties ne sont PAS d'autres prefabs — un sous-arbre imbriquant des
    # templates ferait du dimensionnement de pool un problème de graphe.
    children: list = field(default_factory=list)   # list[Actor]

    def __post_init__(self):
        # Cohérence interne seulement (rien ne lit `actor.name` pour un
        # prefab — codegen/dispatcher lisent `prefab.name`, le champ Resource
        # ci-dessus, inchangé) : évite qu'un `prefab.actor` inspecté à la main
        # porte un nom qui ne corresponde à rien.
        self.actor.name = self.name

    # ── Délégation en LECTURE : le reste du code (codegen, dispatcher,
    # project_renames…) lit encore prefab.components / .pal_bank /
    # .affine_transform / .notes — une seule définition, sur l'actor racine,
    # jamais deux valeurs à resynchroniser à la main (c'était le bug : cf.
    # l'ancien `instantiate_actor_from_prefab` qui n'en recopiait que 4 sur 5).
    @property
    def components(self):
        return self.actor.components

    @property
    def pal_bank(self):
        return self.actor.pal_bank

    @property
    def affine_transform(self):
        """La réservation affine vit sur le SpriteComponent (ARCHITECTURE.md
        « Le modèle affine ») : un prefab sans sprite n'en a pas."""
        sc = affine_sprite_component(self.actor)
        return bool(sc and sc.affine_transform)

    @property
    def notes(self):
        return self.actor.notes

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "components":       components_to_list(self.actor.components),
            "pal_bank":         self.actor.pal_bank,
            # Absent tant que le prefab est plat — c'est à dire pour tous ceux
            # d'avant la v0.23.
            **({"children": [c.to_dict() for c in self.children]} if self.children else {}),
            "notes":            self.actor.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Prefab":
        name = d.get("name", "Prefab")
        actor = Actor(
            name             = name,
            components       = _components_with_affine_migrated(d),
            pal_bank         = d.get("pal_bank", OWN_PAL_BANK),
            notes            = d.get("notes", ""),
        )
        return cls(
            name          = name,
            actor         = actor,
            # `d.get("max_instances")` d'un vieux projet est simplement ignoré :
            # le champ n'existe plus (retiré en T7), le pool vit sur la scène.
            # `Actor` est défini plus bas dans ce fichier : la référence n'est
            # résolue qu'à l'appel, pas à la définition de la classe.
            children      = [Actor.from_dict(x) for x in (d.get("children") or [])],
        )


# ──────────────────────────────────────────────────────────────────
#  Actor — entité inline dans une scène.
#  Stocké directement dans le JSON de la scène (pas de fichier séparé).
#  Porte ses Components (sprite, collision, script…) ET son transform
#  de placement dans la scène (x, y, flip, priority…).
#  prefab_name est purement informatif : si l'actor a été créé depuis
#  un Prefab, il indique lequel — aucun lien vivant après la création.
# ──────────────────────────────────────────────────────────────────

@dataclass
class Actor(ComponentOwnerMixin):
    name: str = "Actor"
    prefab_name: Optional[str] = None
    active: bool = True
    components: list = field(default_factory=list)
    # Transform / placement dans la scène
    x: int = 112
    y: int = 72
    flip_h: bool = False
    flip_v: bool = False
    priority: int = 0
    pal_bank: int = OWN_PAL_BANK   # -1 = palette propre du sprite (défaut)
    visible: bool = True
    # Mode OAM (bits 10-11 d'attr0) : 0 = sprite normal, 2 = fenêtre-objet —
    # le sprite n'est plus dessiné, ses pixels opaques DÉCOUPENT la région
    # window.OBJ (forme libre, animable). Mode 1 (semi-transparent) suppose le
    # blending, pas encore câblé. Modifiable au runtime par self.obj_mode.
    obj_mode: int = 0
    # Transformation affine MONDE (cf. ARCHITECTURE.md « Le modèle affine »).
    # C'est de l'ÉTAT DE JEU : un script les lit, les écrit et les relit qu'il y
    # ait un sprite ou non. Ce qui décide si ça se VOIT est ailleurs — la case
    # `affine_transform` du SpriteComponent, qui réserve un des 32 slots de
    # matrice affine OAM. Sans elle, l'actor tourne pour la logique, pas pour
    # l'écran ; le SpriteComponent compose alors son propre scale/rotation/offset
    # locaux par-dessus ceux-ci, mais rien ne les affiche.
    rotation: int = 0            # degrés 0-359 — rotation monde de l'actor
    scale_x: float = 1.0         # scale monde de l'actor (1.0 = normal)
    scale_y: float = 1.0
    # Ancrage ÉCRAN : x/y ne sont plus des coordonnées de monde mais des pixels
    # d'écran, et l'émission OAM ne retranche pas la caméra — l'acteur ne
    # défile pas. C'est l'UI en sprite (score, cœurs, curseur) avec tout le
    # SpriteComponent existant : états, animations, éditeur de sprite.
    #
    # Résolu au BUILD, pas au runtime : aucun champ dans `g_actors`, aucun
    # setter Lua. Un acteur est de l'UI ou du monde pour toute sa vie, et le
    # défaut doit rester littéralement gratuit (le C émis est mot pour mot
    # celui d'avant pour un acteur de monde).
    screen_space: bool = False
    # Nom de l'acteur DE LA MÊME SCÈNE dans le repère duquel ma position est
    # exprimée (ROADMAP v0.23). Vide = aucun parent, ce qu'étaient tous les
    # acteurs avant cette version.
    #
    # Ce n'est PAS de l'héritage : « ma position est exprimée dans le repère de
    # celui-là », pas « je reprends sa définition ». L'héritage d'une définition
    # existe déjà dans ce logiciel et s'appelle un prefab ; laisser les deux sens
    # du même mot cohabiter coûterait plus cher que la fonctionnalité.
    #
    # x/y/rotation/scale gardent leur sens de POSE AUTHORÉE dans l'éditeur ;
    # au build, ils deviennent le transform LOCAL, et la position monde de
    # l'acteur est recomposée chaque frame depuis celle du parent (cf.
    # main_gen, `_parent_compose_lines`). La parenté est authorée et jamais
    # assignée au runtime : c'est ce qui rend le tri de profondeur possible au
    # build, donc l'ordre d'une frame lisible dans le C émis.
    parent: Optional[str] = None
    # Direction initiale discrète (-1|0|1 × -1|0|1) : oriente le sprite affiché
    # dans l'éditeur et initialise dir_x/dir_y de l'Actor au runtime. (0,0)=omni.
    dir_x: int = 0
    dir_y: int = 0
    notes: str = ""   # note libre utilisateur (éditeur uniquement, jamais compilée)

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "prefab_name": self.prefab_name,
            "active":      self.active,
            "components":  components_to_list(self.components),
            "x":           self.x,
            "y":           self.y,
            "flip_h":      self.flip_h,
            "flip_v":      self.flip_v,
            "priority":    self.priority,
            "pal_bank":    self.pal_bank,
            "visible":     self.visible,
            "obj_mode":    self.obj_mode,
            "rotation":    self.rotation,
            "scale_x":     self.scale_x,
            "scale_y":     self.scale_y,
            "screen_space": self.screen_space,
            # Écrit seulement s'il y a un parent : un acteur ordinaire — c'est
            # à dire tous ceux d'avant la v0.23 — ne gagne pas une clé.
            **({"parent": self.parent} if self.parent else {}),
            "dir_x":       self.dir_x,
            "dir_y":       self.dir_y,
            "notes":       self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Actor":
        return cls(
            name        = d.get("name", "Actor"),
            prefab_name = d.get("prefab_name"),
            active      = d.get("active", True),
            components  = _components_with_affine_migrated(d),
            x           = d.get("x", 112),
            y           = d.get("y", 72),
            flip_h      = d.get("flip_h", False),
            flip_v      = d.get("flip_v", False),
            priority    = d.get("priority", 0),
            pal_bank    = d.get("pal_bank", OWN_PAL_BANK),
            visible     = d.get("visible", True),
            obj_mode    = d.get("obj_mode", 0),
            rotation    = int(d.get("rotation", 0)),
            scale_x     = float(d.get("scale_x", 1.0)),
            scale_y     = float(d.get("scale_y", 1.0)),
            screen_space = d.get("screen_space", False),
            parent       = (d.get("parent") or None),
            dir_x       = d.get("dir_x", 0),
            dir_y       = d.get("dir_y", 0),
            notes       = d.get("notes", ""),
        )


def actor_descendant_names(actors: list, name: str) -> set:
    """Noms des acteurs qui descendent de `name` (lui exclu), calculés depuis
    `Actor.parent`. Source unique pour le garde-fou anti-cycle (inspecteur,
    drop dans l'arbre de scène) et pour faire suivre un sous-arbre entier
    quand son parent est déplacé dans le canvas (ROADMAP v0.23)."""
    children_of: dict = {}
    for a in actors:
        par = getattr(a, "parent", None)
        if par:
            children_of.setdefault(par, []).append(a.name)
    out, stack = set(), [name]
    while stack:
        for child in children_of.get(stack.pop(), []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def actor_prefab_linked(actor: "Actor", prefab: "Prefab") -> bool:
    """« Linké » (True) si `actor` reste sur le MÊME chemin de compilation que
    son prefab, « unlinké » (False) s'il en a dérivé — la distinction que le
    projet a choisie pour ce statut (ROADMAP, décision du 2026-08-21) : ce qui
    ne change pas ce qui se compile ne change pas la nature du prefab.

    Ce qui compte : les components eux-mêmes (type, ordre, id — ils décident
    quel C s'émet, cf. main_gen), et pour un ScriptComponent, le FICHIER .lua
    cité (c'est littéralement ce qui est compilé, cf. lua_compiler). Le reste
    — valeurs de champs, exports, offsets, `active`... — sont des PARAMÈTRES
    d'instance : les changer ne rend pas l'instance « unlinkée »."""
    a_comps, p_comps = actor.components, prefab.actor.components
    if len(a_comps) != len(p_comps):
        return False
    for ac, pc in zip(a_comps, p_comps):
        if type(ac) is not type(pc) or ac.id != pc.id:
            return False
        if isinstance(ac, ScriptComponent) and ac.script != pc.script:
            return False
    return True


# ──────────────────────────────────────────────────────────────────
#  Window — une région d'écran matérielle (WIN0 ou WIN1)
# ──────────────────────────────────────────────────────────────────

@dataclass
class WindowSlot:
    """Une window matérielle GBA authorée par la scène — une INTENTION nommée,
    pas un index matériel (révisé le 2026-08-25, cf. `codegen/window_alloc.py`
    et ARCHITECTURE.md « Windows — le pochoir »). Rectangle en pixels écran,
    clampé 240×160 par window_set() au runtime (même fonction que l'API Lua
    window.set() — un seul point d'écriture, même principe que la caméra).

    `is_obj=False` : un rectangle candidat à WIN0/WIN1 — `name` l'identifie
    (renommable, unique au PROJET, comme une caméra) ; l'allocateur décide
    seul lequel des deux rangs matériels il reçoit, un slot par scène qui en
    demande trop échoue au build (nommé), pas de repli silencieux possible.
    `is_obj=True` : la fenêtre-objet (forme donnée par les sprites en
    `obj_mode=2`, jamais disputée) — `name` n'a pas de sens, un seul slot OBJ
    par scène, toujours adressable par le mot-clé fixe "object".

    Défaut = tout traverse (visible=False, tous les layers_shown à True,
    obj_shown=True) : ajouter une window sans rien configurer ne doit RIEN
    cacher — l'utilisateur restreint ensuite, jamais l'inverse (neutralité
    de style, cf. ROADMAP v0.3.2)."""
    name: str = ""       # identité de l'intention — vide/ignoré si is_obj
    is_obj: bool = False  # fenêtre-objet (pas de géométrie propre, jamais allouée)
    x: int = 0
    y: int = 0
    w: int = 240
    h: int = 160
    visible: bool = False
    layers_shown: list = field(default_factory=lambda: [True, True, True, True])  # BG0-3
    obj_shown: bool = True


# ──────────────────────────────────────────────────────────────────
#  Scene — une scène complète
# ──────────────────────────────────────────────────────────────────

@dataclass
class Scene(Resource):
    name: str = "Scene"
    # Layers de fond de CETTE scène (inline dans le JSON) — chaque layer référence
    # un BackgroundAsset (sidecar de compression) par son nom d'image.
    background_layers: list = field(default_factory=list)  # list[BackgroundLayer]
    actors: list = field(default_factory=list)  # list[Actor], inline dans le JSON
    # ── Le budget d'acteurs de la scène (ROADMAP v0.17) ────────────
    # Les 128 entrées OAM du matériel, réparties entre ce que la scène POSE et
    # ce qu'elle SPAWNE. Deux champs qui partagent un plafond : monter l'un
    # descend l'autre, parce qu'il n'y a qu'un budget.
    #
    # `actor_slots` réserve des entrées pour les acteurs posés — il n'en compte
    # pas. L'auteur peut poser moins que ce qu'il réserve (le validateur
    # avertit s'il pose plus) ; c'est ce qui rend le champ réglable, donc les
    # deux champs solidaires.
    #
    # 0 = automatique : la réservation vaut le nombre d'acteurs réellement
    # posés. C'est le comportement d'avant ce champ, donc celui de toute scène
    # antérieure — le défaut ne s'invente rien.
    actor_slots: int = 0
    # Les pools de CETTE scène : nom de Prefab → nombre d'INSTANCES simultanées.
    # Le budget, lui, se paie en SLOTS — un prefab à sous-arbre coûte
    # instances × parties (v0.23). C'est `codegen/actor_budget.py` qui fait la
    # conversion, en un seul endroit.
    #
    # Remplace `Prefab.max_instances` : combien d'exemplaires vivent en même
    # temps est une propriété du NIVEAU, pas du template.
    prefab_pools: dict = field(default_factory=dict)  # dict[str, int]
    # Caméras POSSÉDÉES par cette scène (inline dans le JSON, comme `actors`) —
    # révisé le 2026-08-24 : une caméra n'est plus un asset de projet partagé
    # entre scènes (cf. models/camera.py, changelog-archive/v0.6.md).
    cameras: list = field(default_factory=list)  # list[Camera]
    # Caméra de DÉMARRAGE, par nom — résolue dans `cameras` ci-dessus. "" = la
    # caméra par défaut : fixe à (0,0), sans bornes ni suivi, sans entrée dans
    # `cameras`. L'auteur n'a donc rien à créer pour le cas simple, et la
    # liste ne se remplit pas d'une entrée par scène jamais réglée.
    camera: str = ""
    # Windows matérielles (WIN0/WIN1) authorées pour cette scène — max 2,
    # une par région (cf. WindowSlot). Liste vide = comportement identique à
    # aujourd'hui (aucune window active, tout s'affiche normalement).
    windows: list = field(default_factory=list)  # list[WindowSlot]
    scroll_h: bool = True  # défilement horizontal activé (mode "follow")
    scroll_v: bool = False # défilement vertical activé (mode "follow")
    # Mode vidéo GBA de la scène (0-5). 0 = 4 fonds tuilés réguliers (défaut) ;
    # 1/2 = tuilé + affine ; 3/4/5 = un fond bitmap plein écran (BG2). Pilote
    # l'inspecteur (zones background/palettes). cf. ui MODE_INFO.
    render_mode: int = 0
    # Transition jouée en QUITTANT cette scène et en l'OUVRANT — "" = celle du
    # projet. Chaque scène décrit sa propre disparition et sa propre apparition,
    # il n'y a donc jamais de conflit entre les deux scènes d'une bascule
    # (cf. ROADMAP v0.6.2). Résolu au build par transition_of().
    transition_kind: str = TRANSITION_INHERIT   # "" | none | fade_black | fade_white
    transition_frames: int = 16                 # durée d'UNE moitié, ignorée si héritée
    # Musique de la scène — MUSIC_INHERIT ("") = ne touche pas à ce qui joue,
    # MUSIC_NONE ("none") = silence explicite, sinon le nom d'une Music.
    # Redemander la piste DÉJÀ en cours ne la redémarre pas (le runtime tient
    # la piste courante) : nommer explicitement le thème dans douze salles se
    # comporte donc comme l'héritage, et non comme douze redémarrages.
    music: str = MUSIC_INHERIT
    script: str = ""       # chemin relatif vers le script Lua de la scène ("" = aucun)
    # Le slot BG de l'UI vit sur CHAQUE nœud (`InterfaceNode.bg_slot`), plus au
    # niveau scène : l'ancien `Scene.text_bg` a été retiré (v0.12). La lecture des
    # anciens fichiers seed encore `bg_slot` depuis la clé JSON `text_bg`
    # (cf. `_ui_nodes_from_dict`), mais elle n'est plus ni un champ ni réécrite.
    # Nœuds `Interface` de la scène (v0.12) : chacun un `InterfaceNode` qui
    # référence un `UILayout` par nom ET porte SA cible de rendu (ancrage, cible
    # BG/OBJ, acteur suivi, slot BG). Une scène peut en poser plusieurs (un HUD
    # fixe en BG et une bulle qui suit un acteur en OBJ sont deux nœuds). Vide =
    # aucune, le script place alors tout lui-même via text:draw(id, tx, ty).
    # cf. models/ui_region.py (InterfaceNode) et project.scene_ui_layouts.
    ui_layouts: list = field(default_factory=list)   # list[InterfaceNode]
    # Police chargée par `scene_init`, celle qu'obtient tout texte qui n'en
    # nomme pas (zone sans `font_name`, `text.draw` sans `text.set_font`).
    # Référencée par NOM comme tout asset.
    #
    # "" = la première police encodable du projet — le comportement historique
    # (`text_set_font(0)` en dur), et le seul défaut qui ne soit pas un choix :
    # une police par défaut livrée avec le moteur imposerait un style, ce que la
    # v0.3.2 refuse explicitement. Un nom introuvable retombe sur la même
    # première police, et le validateur le dit.
    font_name: str = ""
    # Banque de palette de CHAQUE police, par nom (cf. `font_pal_banks` en tête
    # de module). Absente = la police charge sa propre palette dans une banque
    # allouée (comme un sprite) ; un slot = elle lit son encre dans une palette
    # de scène. La clé `""` est la police par défaut. Remplace l'ancien scalaire
    # `ui_pal_bank`, migré à la lecture (`_font_pal_banks_from_dict`).
    font_pal_banks: dict = field(default_factory=dict)  # dict[str, int]
    collision_layer: int = 0  # index BG (0-3) portant la carte de collisions
    # Grille de collision en tiles 8×8 — list[row][col] de TILE_* constants
    collision_map: list = field(default_factory=list)
    # Palettes actives de cette scène — noms référençant project.obj_palettes/
    # bg_palettes (catalogue illimité). Ordre = index de banque hardware
    # (slot 0 = 1er élément). Actor/Prefab.pal_bank indexe dans CETTE liste,
    # pas directement le catalogue projet.
    active_obj_palettes: list = field(default_factory=list)  # list[str]
    active_bg_palettes:  list = field(default_factory=list)  # list[str]
    # Override de ProjectSettings.backdrop_color pour cette scène (BGR555) ;
    # None = hérite du défaut projet.
    backdrop_color: Optional[int] = None
    # ── Mélange de couleurs (cf. BLEND_* en tête de module) ───────
    # Le MODE est ici et pas sur les layers : le matériel n'en a qu'un pour tout
    # l'écran. Les layers ne portent que leur rôle (`BackgroundLayer.blend_role`).
    blend_mode: int = BLEND_NONE
    blend_eva: int = BLEND_EV_MAX   # poids du dessus (mode alpha)
    blend_evb: int = 0              # poids du dessous (mode alpha)
    blend_evy: int = BLEND_EV_MAX // 2   # intensité du fondu (modes 2 et 3)
    # Les sprites et le backdrop sont deux cibles comme les layers (BLDCNT bits
    # 4/5 et 12/13), mais ils n'ont pas de ligne dans la liste des layers : leur
    # rôle vit donc ici. Le backdrop en DESSOUS est le réglage qui fait marcher
    # un alpha au-dessus d'une zone vide — sans lui, rien derrière, donc rien à
    # mélanger.
    blend_obj_role: str = ""
    blend_backdrop_role: str = ""
    notes: str = ""   # note libre utilisateur (éditeur uniquement, jamais compilée)

    def __post_init__(self):
        # Invariant : `ui_layouts` tient toujours des `InterfaceNode`, quel que
        # soit le chemin de construction. Un nom nu (constructeur direct, code
        # hérité) est coercé en nœud À MIGRER (`anchor=""`, cible recopiée depuis
        # l'asset à la première résolution — cf. `Project.scene_ui_layouts`), au
        # `bg_slot` par défaut. La lecture d'un ancien FICHIER (`from_dict` →
        # `_ui_nodes_from_dict`) seed ce slot depuis l'ancienne clé `text_bg` ;
        # ce chemin-ci ne couvre que les constructions directes en mémoire.
        self.ui_layouts = [
            n if isinstance(n, InterfaceNode)
            else InterfaceNode(layout_name=str(n), anchor="")
            for n in self.ui_layouts
        ]

    # ── Mélange : lectures dérivées ───────────────────────────────
    def blend_layers(self, role: str) -> list:
        """Layers tenant `role` dans le mélange, dans l'ordre de la scène."""
        return [L for L in self.background_layers if blend_role_of(L) == role]

    def blend_has_target(self, role: str) -> bool:
        """Y a-t-il au moins une cible dans ce rôle — layer, sprites ou backdrop ?

        C'est la question que pose le validateur : un mode sans DESSUS ne fait
        rien du tout, et un alpha sans DESSOUS ne fait rien non plus."""
        if self.blend_layers(role):
            return True
        return role in (self.blend_obj_role, self.blend_backdrop_role)

    def ensure_collision_map(self, width_px: int = 240, height_px: int = 160):
        """Initialise ou redimensionne la collision_map si vide."""
        if not self.collision_map:
            self.collision_map = make_collision_map(width_px, height_px)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background_layers": [
                {"background_name": L.background_name, "bg_slot": L.bg_slot,
                 "scroll_speed": L.scroll_speed, "pal_bank": L.pal_bank,
                 **({"tile_palette_overrides": {f"{c},{r}": s
                                       for (c, r), s in L.tile_palette_overrides.items()}}
                    if L.tile_palette_overrides else {}),
                 **({"blend_role": L.blend_role} if L.blend_role else {}),
                 **({} if L.visible else {"visible": False})}
                for L in self.background_layers
            ],
            "actors": [a.to_dict() for a in self.actors],
            # Absents tant que la scène n'a rien réglé : une scène qui n'a
            # jamais ouvert la carte Actor budget ne gagne pas deux clés
            # inertes (même règle que transition_* et music ci-dessous).
            **({"actor_slots": self.actor_slots} if self.actor_slots else {}),
            **({"prefab_pools": {k: v for k, v in sorted(self.prefab_pools.items()) if v > 0}}
               if any(v > 0 for v in self.prefab_pools.values()) else {}),
            "cameras": [c.to_dict() for c in self.cameras],
            "camera": self.camera,
            "windows": [
                {"name": ws.name, "is_obj": ws.is_obj, "x": ws.x, "y": ws.y,
                 "w": ws.w, "h": ws.h, "visible": ws.visible,
                 "layers_shown": ws.layers_shown, "obj_shown": ws.obj_shown}
                for ws in self.windows
            ],
            "render_mode": self.render_mode,
            # Absentes du fichier tant que la scène hérite du projet : le défaut
            # ne s'écrit pas, sinon changer le réglage projet ne se verrait plus.
            **({"transition_kind": self.transition_kind,
                "transition_frames": self.transition_frames}
               if self.transition_kind else {}),
            # Même règle : absente du fichier tant que la scène hérite.
            **({"music": self.music} if self.music else {}),
            "scroll_h": self.scroll_h,
            "scroll_v": self.scroll_v,
            "script": self.script,
            "ui_layouts": [n.to_dict() for n in self.ui_layouts],
            "font_name": self.font_name,
            # Absent tant qu'aucune police n'est overridée : une scène en tout
            # automatique ne gagne pas la clé (même règle que blend/music).
            **({"font_pal_banks": {k: self.font_pal_banks[k]
                                   for k in sorted(self.font_pal_banks)}}
               if self.font_pal_banks else {}),
            "collision_layer": self.collision_layer,
            "collision_map": self.collision_map,
            "active_obj_palettes": self.active_obj_palettes,
            "active_bg_palettes": self.active_bg_palettes,
            "backdrop_color": self.backdrop_color,
            # Écrits seulement si un mélange est réglé : sans ça, tous les JSON
            # de scène du projet gagneraient cinq clés inertes.
            **({"blend_mode": self.blend_mode,
                "blend_eva": self.blend_eva, "blend_evb": self.blend_evb,
                "blend_evy": self.blend_evy,
                "blend_obj_role": self.blend_obj_role,
                "blend_backdrop_role": self.blend_backdrop_role}
               if self.blend_mode != BLEND_NONE else {}),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        bg_layers = [
            BackgroundLayer(
                background_name = L.get("background_name", ""),
                bg_slot      = L.get("bg_slot", i),
                scroll_speed = L.get("scroll_speed", 1.0),
                pal_bank     = L.get("pal_bank", OWN_PAL_BANK),
                tile_palette_overrides= decode_tile_palette_overrides(
                    L.get("tile_palette_overrides")),
                visible      = L.get("visible", True),
                blend_role   = (L.get("blend_role", "")
                                if L.get("blend_role", "") in BLEND_ROLES else ""),
            )
            for i, L in enumerate(d.get("background_layers", []))
        ]
        actors = [Actor.from_dict(a) for a in d.get("actors", [])]

        scene = cls(
            name=d.get("name", "Scene"),
            background_layers=bg_layers,
            actors=actors,
            actor_slots=int(d.get("actor_slots", 0) or 0),
            # Les valeurs nulles ne sont pas retenues : un pool à 0 est un pool
            # qui n'existe pas, et le garder ferait apparaître le prefab dans la
            # carte de budget d'une scène qui ne le spawne pas.
            prefab_pools={str(k): int(v) for k, v in (d.get("prefab_pools") or {}).items()
                          if int(v or 0) > 0},
            cameras=[Camera.from_dict(c) for c in d.get("cameras", [])],
            # Les anciens champs `cam_*` inline ne sont PAS relus : la maison
            # ne migre pas les formats (cf. core/project.py). Une scène
            # antérieure repart de la caméra par défaut, ce qui était de toute
            # façon le réglage de la quasi-totalité d'entre elles.
            camera=d.get("camera", ""),
            windows=[
                WindowSlot(
                    name=wd.get("name", ""),
                    # `is_obj` prend le relais de l'ancien `region` (region==2
                    # signifiait OBJ) : ni migré ni cassé, juste un défaut qui
                    # lit l'ancienne clé si la nouvelle est absente.
                    is_obj=wd.get("is_obj", int(wd.get("region", 0)) == 2),
                    x=wd.get("x", 0), y=wd.get("y", 0),
                    w=wd.get("w", 240), h=wd.get("h", 160),
                    visible=wd.get("visible", False),
                    layers_shown=wd.get("layers_shown", [True, True, True, True]),
                    obj_shown=wd.get("obj_shown", True),
                )
                for wd in d.get("windows", [])
            ],
            render_mode=int(d.get("render_mode", 0)),
            # Absente = la scène hérite du projet, ce qui est le cas de toute
            # scène antérieure à la v0.6.2.
            transition_kind=d.get("transition_kind", TRANSITION_INHERIT),
            transition_frames=int(d.get("transition_frames", 16)),
            # Absente = la scène hérite, ce qui est le cas de toute scène
            # antérieure à la v0.8.2.
            music=d.get("music", MUSIC_INHERIT),
            scroll_h=d.get("scroll_h", True),
            scroll_v=d.get("scroll_v", False),
            script=d.get("script", ""),
            # Nœuds `Interface` (v0.12) : chaque entrée est un `InterfaceNode`.
            # On lit TROIS formes ; on n'en écrit qu'une (des nœuds).
            #   • liste de nœuds (v0.12) → `InterfaceNode.from_dict` ;
            #   • liste de noms (v0.25)  → nœud nu, `anchor=""` (à migrer depuis
            #     l'asset) et `bg_slot = text_bg` de la scène (cf. scene_ui_layouts) ;
            #   • ancien `ui_layout` singulier → même traitement, emballé.
            ui_layouts=_ui_nodes_from_dict(d),
            font_name=d.get("font_name", ""),
            font_pal_banks=_font_pal_banks_from_dict(d),
            collision_layer=d.get("collision_layer", 0),
            collision_map=d.get("collision_map", []),
            active_obj_palettes=d.get("active_obj_palettes", []),
            active_bg_palettes=d.get("active_bg_palettes", []),
            backdrop_color=d.get("backdrop_color"),
            blend_mode=(int(d.get("blend_mode", BLEND_NONE))
                        if int(d.get("blend_mode", BLEND_NONE)) in BLEND_MODES
                        else BLEND_NONE),
            blend_eva=clamp_ev(d.get("blend_eva", BLEND_EV_MAX)),
            blend_evb=clamp_ev(d.get("blend_evb", 0)),
            blend_evy=clamp_ev(d.get("blend_evy", BLEND_EV_MAX // 2)),
            blend_obj_role=(d.get("blend_obj_role", "")
                            if d.get("blend_obj_role", "") in BLEND_ROLES else ""),
            blend_backdrop_role=(d.get("blend_backdrop_role", "")
                                 if d.get("blend_backdrop_role", "") in BLEND_ROLES else ""),
            notes=d.get("notes", ""),
        )
        scene.ensure_collision_map()
        return scene
