"""
editor/scripting/api.py — Catalogue de l'API runtime GBA.

Chaque entrée décrit une fonction appelable depuis un script Lua,
avec sa signature Lua, sa traduction C, et le type de retour.

Le checker utilise ce catalogue pour valider les appels inconnus.
Le codegen l'utilise pour émettre le C correct (nom de fonction,
conversion des arguments string → constante entière, etc.).

Convention de nommage des clés :
  "actor:method"  →  méthode d'acteur (écrite `self:method`, `other:method`… ; 1er arg C = l'acteur)
  "module.func"   →  fonction de module (sfx.play, input.held…)
  "func"          →  fonction globale (send, broadcast)
"""

from dataclasses import dataclass, field
from typing import Optional

# Les deux fabricants d'identifiants C vivent ensemble, dans un module qui
# n'importe rien — ce catalogue les emploie, il ne les possède pas.
from codegen.c_names import c_ident, sym as c_sym


# ─── Types de paramètre ────────────────────────────────────────────
# Utilisés par le codegen pour savoir comment convertir l'arg Lua → C.
#
#   "int"   → entier littéral, passé directement
#   "str"   → string Lua → constante C (ANIM_*, SFX_*, KEY_*, TAG_*)
#             Le codegen fait la résolution via le contexte de build.
#   "bool"  → 0/1 entier
#   "actor" → référence à un acteur (nom Lua → pointeur C)

PARAM_INT          = "int"
PARAM_STR          = "str"
PARAM_STR_LITERAL  = "str_literal"   # string passée telle quelle entre guillemets C (pas de résolution de constante)
PARAM_BOOL         = "bool"
PARAM_ACTOR        = "actor"         # nom Lua → &g_actors[TAG_NAME]
# vec2/vec3 — valeur composée (cf. scripting/expr_types.py), pas une chaîne à
# résoudre : l'argument Lua est un vec2(x,y)/vec3(x,y,z) littéral, une variable
# du même type, ou une expression qui s'y réduit (a + b, get_position()…). Ces
# deux chaînes SONT le type de retour ("ret") d'une ApiFunc qui rend un vecteur
# — même vocabulaire des deux côtés, un seul à retenir.
PARAM_VEC2         = "vec2"
PARAM_VEC3         = "vec3"
PARAM_RECT         = "rect"

# ─── Types de RÉFÉRENCE — ce qu'un appel REND, et sur quoi on écrit « : » ──
# Une référence n'est ni une valeur composée (vec2) ni un nom résolu au build :
# c'est un SLOT pris dans un pool dimensionné par le matériel, rendu par l'appel
# qui l'a pris — la forme de `actor.spawn`, et celle de `sfx.play` depuis la
# v0.8.6. Le `ret` d'une ApiFunc porte ce type ; les méthodes qui s'écrivent
# dessus sont indexées `"<type>:<méthode>"` dans le catalogue, exactement comme
# les méthodes d'acteur le sont sous `"actor:"`.
REF_SFX = "sfx"                   # un effet EN TRAIN de jouer — un mm_sfxhand
REF_COLLISION_BOX = "collision_box"  # une boîte de collision d'un acteur — un rang, 0 = absente
REF_UI_ELEMENT = "ui_element"     # un élément d'interface — son index, connu au build
# Les natures d'élément (ROADMAP v0.16, étape c) : `interface:get("X")` rend le type RÉEL de
# l'élément, lu dans la mise en page au build. Ils HÉRITENT de `ui_element` — le cycle de vie
# (`show`/`hide`/`visible`) y vit une fois, pas quatre.
REF_LIST = "list"                 # un conteneur qui se PARCOURT — son index dans `g_ui_lists`
REF_IMAGE = "image"               # un sprite à état — son index dans `g_ui_images`
REF_TEXT_REGION = "text_region"   # une zone de texte — son index dans `g_ui_regions`
# Un ACTEUR : un `Actor*`. Ses méthodes sont indexées `actor:<méthode>`, ses propriétés
# `actor.<champ>` ; à l'écriture c'est `self:` (l'instance qui exécute le script), `other:`, une
# variable qui tient `actor:get(…)` — `self` n'est pas le type, c'est un récepteur implicite.
REF_ACTOR = "actor"
# Deux références NUMÉROTÉES OU NOMMÉES par le matériel, pas par un asset. Elles ne portent
# pas le nom du module qui les rend (`layer`, `window`) : un type `layer` donnerait à
# `layer.priority` deux lectures — la propriété du type, ou une fonction du module.
REF_LAYER = "background_layer"    # un fond tuilé — son numéro matériel (bg_slot)
REF_WINDOW_REGION = "window_region"  # une région du pochoir — son rang (WINR_*)


@dataclass(frozen=True)
class RefType:
    """La DÉCLARATION d'un type de référence — tout ce que le langage sait de lui
    en dehors de son catalogue.

    Ajouter un type se réduit à trois gestes, et à AUCUN cas spécial dans le
    checker ou le codegen (ROADMAP v0.16, critère 2 de l'amendement) :

    1. UNE ligne dans `REF_TYPE_TABLE` ci-dessous ;
    2. les entrées du catalogue : la fabrique (`ret=<type>`), les méthodes sous
       `"<type>:<méthode>"` et les propriétés sous `"<type>.<champ>"` ;
    3. les fonctions C qui les portent, déclarées DEUX fois (cf. ARCHITECTURE,
       « Deux listes de prototypes »).

    Tout le reste s'en DÉRIVE : le type C d'un `local` qui tient la référence
    (`codegen`), le refus d'une méthode ou d'un champ inconnu (`checker`), la
    variable des snippets (`api_snippets`), la portée du renommage (`refactor`).

    Seule une traduction C réellement atypique reste un cas de `_INVOKE_CUSTOM`
    (`ui_element:show` → `ui_element_show(h, 1)`), parce qu'elle change ce qui
    s'émet, pas ce que le type EST."""
    c_type:   str           # type C du `local` qui tient la référence
    variable: str           # nom de variable montré dans les snippets (`hb:overlaps(...)`)
    # Une phrase ajoutée à l'erreur « méthode/champ inconnu » : l'auteur qui
    # cherche une porte qui n'existe pas apprend laquelle existe.
    hint:     str = ""
    # HÉRITAGE : le type dont celui-ci reprend les membres (`list` → `ui_element`, d'où
    # `menu:hide()`). `to_base` est la fonction C qui convertit la référence en celle de
    # son parent — un `list` est un index de `g_ui_lists`, ses verbes de base veulent
    # l'index d'ÉLÉMENT : `ui_element_show(ui_list_element(menu), 0)`.
    base:     str = ""
    to_base:  str = ""
    # Ce que `interface:get(nom)` rend pour un élément de cette nature : le `kind` de la
    # mise en page (`core.models.ui_region.KIND_*`) et le préfixe de la constante C qui
    # l'indexe. Vide pour un type qui n'est pas un élément d'interface.
    ui_kind:  str = ""
    constant: str = ""
    # Le type de COLONNE d'une table de données qui stocke le handle de ce type (`region`,
    # `image` : le build y range l'index de la zone ou de l'image). Vide sinon.
    column:   str = ""


REF_TYPE_TABLE: dict[str, RefType] = {
    REF_SFX: RefType(c_type="mm_sfxhand", variable="pas"),
    REF_COLLISION_BOX: RefType(c_type="int", variable="hb"),
    # Le conteneur n'a aucune capacité propre : il EST le type de base.
    REF_UI_ELEMENT: RefType(
        c_type="int", variable="element", ui_kind="container", constant="UIELEM_",
        hint="La géométrie d'un élément est authorée : elle ne s'ouvre pas au "
             "runtime. Une liste, une image et une zone de texte ont leurs propres "
             "membres — le type de `interface:get(nom)` est celui de l'élément."),
    REF_LIST: RefType(
        c_type="int", variable="menu", base=REF_UI_ELEMENT, to_base="ui_list_element",
        ui_kind="list", constant="UILIST_"),
    REF_IMAGE: RefType(
        c_type="int", variable="icone", base=REF_UI_ELEMENT, to_base="ui_image_element",
        ui_kind="image", constant="IMAGE_", column="image"),
    REF_TEXT_REGION: RefType(
        c_type="int", variable="zone", base=REF_UI_ELEMENT, to_base="ui_region_element",
        ui_kind="text", constant="REGION_", column="region"),
    REF_LAYER: RefType(
        c_type="int", variable="fond",
        hint="Un fond est numéroté par le matériel, de 0 à 3 : `layer:get(n)`."),
    REF_ACTOR: RefType(
        c_type="Actor*", variable="self",
        hint="Un acteur s'appelle `self:méthode()` sur l'acteur qui exécute le script, ou sur un "
             "acteur tenu par une variable (`local boss = actor:get(\"Boss\")`)."),
    REF_WINDOW_REGION: RefType(

        c_type="int", variable="fenetre",
        hint="Une région se nomme : `window:get(\"Panneau\")`, \"object\" ou \"outside\"."),
}

# Les fonds RÉGULIERS (tuilés, à défilement) que chaque mode vidéo GBA offre — un fait du
# matériel, tenu ICI pour que le jour où `Scene.render_mode` sera offert à l'auteur, `layer:get`
# refuse déjà un numéro que la scène n'a pas. Les fonds affines (modes 1-2) et bitmap (3-5) ont
# d'autres registres et d'autres membres : ils auront leur propre type avec leur rendu.
#
# INTERNE : rien de ce que l'auteur lit — doc, indices, messages — ne parle de mode. Aujourd'hui
# seul le mode 0 est offert, donc toute scène a les quatre fonds.
LAYERS_BY_MODE: dict[int, tuple[int, ...]] = {
    0: (0, 1, 2, 3),
    1: (0, 1),
    2: (),
    3: (), 4: (), 5: (),
}

# Les numéros de fonds quand la scène n'est pas connue (hors build), et par défaut : le mode 0.
LAYER_NUMBERS: tuple[int, ...] = LAYERS_BY_MODE[0]




def ref_lineage(ref: str) -> list[str]:
    """`list` → `["list", "ui_element"]` : le type puis ses ancêtres, du plus proche au
    plus lointain. C'est l'ordre dans lequel un membre se cherche."""
    out: list[str] = []
    while ref and ref not in out:
        out.append(ref)
        decl = REF_TYPE_TABLE.get(ref)
        ref = decl.base if decl else ""
    return out


def ref_member(ref: str, name: str, sep: str):
    """(type qui DÉCLARE le membre, entrée) — `sep` = ":" pour une méthode, "." pour une
    propriété. Cherché sur le type puis sur ses ancêtres ; None si personne ne le porte."""
    table = RUNTIME_API if sep == ":" else RUNTIME_PROPS
    for owner in ref_lineage(ref):
        entry = table.get(f"{owner}{sep}{name}")
        if entry is not None:
            return owner, entry
    return None


def ref_upcast(ref: str, owner: str, receiver: str) -> str:
    """Le récepteur C tel que `owner` l'attend, quand le membre est hérité : chaque
    marche du chemin `ref` → `owner` applique la conversion `to_base` de son type."""
    for step in ref_lineage(ref):
        if step == owner:
            break
        receiver = f"{REF_TYPE_TABLE[step].to_base}({receiver})"
    return receiver

# Une VUE vivante sur la table : `"sfx" in REF_TYPES` reste vrai pour un type
# ajouté plus tard, sans seconde liste à tenir d'accord avec la première.
REF_TYPES = REF_TYPE_TABLE.keys()

# ─── Domaines de résolution pour les arguments "str" ──────────────
# Quand le codegen voit PARAM_STR il a besoin de savoir dans quel
# espace de noms chercher la constante C.
#
# Le `domain` d'un paramètre est aussi la déclaration « cet argument RÉFÉRENCE
# un élément nommé du projet » : c'est ce qui permet à scripting/refactor.py de
# suivre les renommages, sans liste de fonctions codée en dur. Tout nouvel
# argument qui cite un nom d'asset doit donc porter son domaine.
DOMAIN_ANIM   = "anim"    # ANIM_{actor}_{name}
DOMAIN_SPRITE_ID = "sprite_id"  # SPRITE_{actor}_{id} — l'id d'un composant sprite de l'acteur
DOMAIN_SFX    = "sfx"     # SFX_{name}
DOMAIN_MUSIC  = "music"   # MUSIC_{name}
DOMAIN_KEY    = "key"     # BTN_{name} — enum fixe du hardware, jamais renommé
# Nom d'axe passé à `input:get_axis()` — "horizontal"/"vertical" (toujours
# présents, jamais déclarés) ou un `InputAxis` du projet. Domaine distinct de
# DOMAIN_KEY : un axe n'est pas un bouton ni une action, il ne s'utilise
# jamais avec `held`/`pressed`/`released`/`buffered`.
DOMAIN_AXIS   = "axis"
# Nom d'une séquence déclarée (Project Settings → Input → Séquences), passé à
# `input:get_sequence()`. Espace de noms SÉPARÉ de DOMAIN_KEY (décision de
# l'auteur, 2026-09-27) : un accord se lit avec held/pressed/released/buffered,
# une séquence avec get_sequence — jamais l'inverse, et jamais partagé avec
# DOMAIN_SEQUENCE (qui, lui, nomme un `on_sequence_<nom>` de script).
DOMAIN_INPUT_SEQUENCE = "input_sequence"
# TAG_{name} — l'IDENTITÉ d'un acteur. L'espace de noms est celui des acteurs de
# la scène et des prefabs poolés, un `#define` par nom (cf. headers.py) : il est
# donc parfaitement énumérable, contrairement à ce que ce fichier a longtemps
# prétendu. La confusion venait de `BOXTAG_*`, lui bel et bien libre — il vient
# de `CollisionBoxComponent.tag`, que l'auteur écrit à la main.
DOMAIN_TAG    = "tag"
# BOXTAG_{name} — le champ « Tag » d'une boîte de collision. À l'opposé de
# DOMAIN_TAG, l'espace est LIBRE : l'auteur l'écrit à la main dans le
# CollisionBoxComponent, la liste du projet est `Project.collision_tags()`.
DOMAIN_BOX_TAG = "box_tag"
DOMAIN_SCENE  = "scene"   # SCENE_IDX_{name}
DOMAIN_CAMERA = "camera"  # CAM_{name}   — caméra du projet
# Les trois boîtes sonores (ROADMAP v0.8.7). Un domaine PAR BOÎTE, parce que
# chaque boîte a son propre espace de noms depuis qu'elles sont trois assets :
# « sable » dans une SoundBox et « sable » dans une JingleBox sont deux états
# différents, et l'appel dit lequel il vise. Un ÉTAT reste un fait qu'on pose
# (« le sol est du sable »), un DÉCLENCHEUR un événement qu'on émet.
DOMAIN_SOUND_BOX_STATE   = "sound_box_state"
DOMAIN_JINGLE_BOX_STATE  = "jingle_box_state"
DOMAIN_MUSIC_BOX_TRIGGER = "music_box_trigger"
DOMAIN_TEXT   = "text"    # TEXT_{key}  — clé de la table de textes du projet
# LANG_{code} — une langue DÉCLARÉE du projet (ROADMAP v0.9, phase 4).
# Espace de noms VIDE dans un projet monolingue : `lang.set`/`lang.get` n'ont
# alors aucun code valide, donc aucun appel ne compile — même mécanique que
# DOMAIN_SCENE sur un projet sans scène, jamais un cas spécial à écrire.
DOMAIN_LANG   = "lang"
DOMAIN_FONT   = "font"    # FONT_{name}
DOMAIN_PALETTE = "palette"  # PAL_{name} — palette du catalogue de couleurs
# État affiché par une image d'interface (`heart.state = "vide"`). Le SEUL domaine
# dont la validité dépend du RÉCEPTEUR : un état n'existe que dans un sprite, et
# c'est l'image qui dit lequel (`IMGST_{image}_{état}`). D'où un contrôle qui lit
# l'image sur le récepteur de la propriété plutôt que sur son seul littéral.
DOMAIN_IMAGE_STATE = "image_state"
DOMAIN_PREFAB = "prefab"  # nom de Prefab — actor:spawn()
# Domaines résolus par un _emit_* dédié du codegen (pas de constante C
# générique) : ils n'en restent pas moins des références nommées.
DOMAIN_ACTOR  = "actor"   # nom d'Actor de la scène — actor:get()
# N'IMPORTE QUEL élément d'une mise en page (texte, conteneur, liste, image) — le
# seul nom que cite `interface:get()`. Sa constante dépend de la NATURE de l'élément
# (`UIELEM_`, `UILIST_`, `IMAGE_`, `REGION_` : cf. `RefType.constant`), que le build
# lit dans la mise en page — le script n'a pas à la connaître.
DOMAIN_UI_ELEMENT = "ui_element"
DOMAIN_GLOBAL = "global"  # GlobalVar du projet — cité en LITTÉRAL par save.read
                           # (global.nom lui-même est un accès pointé, résolu
                           # hors domaine — cf. _check_global_scalar, chantier global/const)
# Pas de DOMAIN_CONST : const.get (seul site littéral qui le citait) a quitté
# RUNTIME_API au profit de l'accès pointé (`const.nom`, résolu par
# `_check_const_scalar`/`ExprIndex`, hors domaine — chantier global/const). Un domaine
# sans site serait un orphelin — `test_aucun_domaine_declare_nest_orphelin`.
# Nom de séquence — `sequence:start("intro")` désigne `function on_sequence_intro`.
# Le SEUL domaine dont l'espace de noms est le SCRIPT et non le projet : checker
# et codegen reçoivent l'AST, ils collectent les noms eux-mêmes. Conséquence à
# connaître : `refactor` le dérive du catalogue comme les autres, mais aucun
# renommage d'asset ne le déclenche — une séquence n'est pas un asset.
DOMAIN_SEQUENCE = "sequence"
# Énumérations MATÉRIELLES : ensemble fixe, connu au build, jamais renommé —
# même nature que DOMAIN_KEY, dont elles reprennent exactement le mécanisme.
# Elles ne citent pas un élément du projet : `refactor` n'a donc rien à y
# suivre, mais le checker et le codegen si (cf. HARDWARE_ENUMS plus bas).
DOMAIN_OBJ_MODE   = "obj_mode"    # mode OAM d'un sprite
DOMAIN_DIRECTION  = "direction"   # direction d'animation d'un acteur
DOMAIN_WIN_REGION = "win_region"  # région de window (WINR_*)
DOMAIN_BLEND_MODE = "blend_mode"  # mode de mélange (BLDCNT)
DOMAIN_BLEND_SIDE = "blend_side"  # dessus / dessous du mélange
DOMAIN_EASE       = "ease"        # courbe d'accélération de math.ease()

# Tous les domaines, DÉRIVÉS des constantes ci-dessus : déclarer un
# `DOMAIN_*` suffit à entrer dans le contrôle, il n'y a pas de seconde liste à
# penser à compléter.
#
# Deux consommateurs doivent savoir quoi faire de chaque domaine — le checker
# (le nom existe-t-il ?) et le codegen (quelle constante C émettre ?) — et
# aucun des deux ne le signalait quand la réponse manquait : le checker ne
# validait simplement rien, et le codegen retombait sur « émettre la chaîne
# telle quelle », donc du texte C là où le C attend un entier. Panne au `make`,
# sur la ligne générée, jamais sur la cause. C'est le même défaut que les deux
# listes de prototypes du moteur, et il se règle pareil : les deux tables sont
# comparées à celle-ci au build (`validator._check_api_domains`).
ALL_DOMAINS: frozenset[str] = frozenset(
    value for name, value in list(globals().items())
    if name.startswith("DOMAIN_") and isinstance(value, str)
)


@dataclass
class Param:
    name: str
    ptype: str                        # PARAM_*
    domain: Optional[str] = None      # DOMAIN_* (seulement si ptype == PARAM_STR)
    # Une chaîne qui ne résout PAS dans le domaine est-elle acceptable ?
    # Faux partout sauf `text.draw` : un nom de scène ou de sfx inconnu est une
    # faute, un texte peut s'écrire au vol dans le script (ROADMAP v0.3.2,
    # 2026-07-27). Déclaré ici plutôt que testé sur le nom de la fonction — la
    # même table pilote checker, codegen et refactor.
    literal_ok: bool = False


@dataclass
class ApiFunc:
    """Décrit une fonction de l'API runtime."""
    lua_name:  str                          # clé d'accès (ex: "actor:play_anim")
    c_func:    str                          # nom C généré (ex: "actor_play_anim")
    params:    list[Param] = field(default_factory=list)
    ret:       str = "void"                 # type de retour C ("void", "int", "bool")
    self_first: bool = False                # True → émettre (self, ...) en C
    variadic:   bool = False                # True → args restants après params passés tels quels
    # Arguments C constants, ajoutés APRÈS ceux du script : c'est ce qui fait
    # d'un verbe du cycle de vie (`:hide()`) le même appel C que son inverse
    # (`ui_element_show(h, 0)` / `(h, 1)`) sans un émetteur dédié par verbe.
    fixed_args: tuple = ()
    # Vrai quand le TYPE rendu dépend du NOM littéral en premier argument : `interface.get`
    # rend `list`, `image`… selon la nature de l'élément dans la mise en page. Le nom →
    # type se lit dans le contexte de build (`ref_kinds`) ; sans lui, `ret` fait foi.
    ret_by_name: bool = False
    doc:       str = ""


@dataclass
class ApiProp:
    """Décrit une PROPRIÉTÉ d'objet — un état intrinsèque lu et écrit par accès
    pointé (`self.position`, `camera.bound`) plutôt que par un appel get/set.

    La frontière est celle de la grammaire (ARCHITECTURE, « La grammaire de
    l'API » ; ROADMAP v0.7.4) : ce qui est un état de l'objet (`self.position`)
    se lit/s'écrit comme un champ ; ce qui est une ACTION (`self:play_anim`)
    reste un appel. Une propriété composite
    (PARAM_VEC2 / PARAM_RECT) est une valeur IMMUABLE : on lit `self.position.x`
    mais on écrit `self.position = vec2(x, y)` — jamais `self.position.x = 5`
    (le checker le refuse).

    Le `c_getter` rend une valeur composite (un Vec2/Rect) ou un scalaire, et
    `c_setter` en prend une. `scene.size` est la seule propriété sans fonction C
    : le codegen synthétise sa lecture depuis `g_scene_w/g_scene_h`
    (getter_expr), et elle est en lecture seule."""
    lua_name:   str                          # clé d'accès (ex: "actor.position")
    c_getter:   str                          # fonction C de lecture (ex: "actor_get_position")
    c_setter:   Optional[str] = None         # fonction C d'écriture (None → lecture seule)
    ptype:      str = PARAM_INT              # PARAM_INT / PARAM_VEC2 / PARAM_RECT
    self_first: bool = False                 # True → émettre (récepteur, ...) en C
    read_only:  bool = False
    getter_expr: Optional[str] = None        # lecture synthétique C (scène) au lieu d'un appel
    # DOMAIN_* d'énumération matérielle, quand la valeur de cette propriété est
    # un NOM et pas un nombre (`self.obj_mode = "window"`). Sans ce champ, une
    # propriété ne pouvait porter qu'un entier nu : convertir `blend.set_mode
    # ("alpha")` en propriété faisait donc RETOMBER ce réglage sur le `1` que la
    # section « Énumérations matérielles » ci-dessus existe pour supprimer.
    # Côté C rien ne change — la constante vaut toujours un entier. Ce qui
    # change, c'est ce que l'auteur écrit et ce que le checker sait vérifier :
    # l'écriture (`= "alpha"`) comme la comparaison (`== "alpha"`).
    domain:     Optional[str] = None
    # Fonctions C de la forme NOMMÉE, quand elle ne passe pas par les mêmes que
    # la forme ordinaire. Un seul cas : `self.direction` est un vec2 (pour le
    # calcul : `self.direction.x < 0`) dont les neuf valeurs ont AUSSI des noms
    # de boussole. Le C ne range qu'une donnée — `dir_x`/`dir_y` — mais les deux
    # vues n'y accèdent pas par la même porte : l'une prend/rend le vecteur,
    # l'autre l'index de boussole. Une énumération SCALAIRE (`blend.mode`) n'en
    # a pas besoin : sa constante EST l'entier que le getter ordinaire rend.
    c_getter_named: Optional[str] = None
    c_setter_named: Optional[str] = None
    doc:        str = ""


# ─── Énumérations matérielles — un nom, pas un nombre ─────────────
# Le catalogue distinguait deux familles d'arguments sans que rien ne l'explique
# à l'auteur : les éléments du PROJET se citaient par leur nom (`sfx:play("HIT")`,
# `scene:switch("ARENA")`), les énumérations du MATÉRIEL par un entier nu
# (`blend:set_layer("top", ...)`, `window.set("object", ...)`), leur sens vivant
# dans une phrase de documentation. Rien ne permettait de deviner laquelle
# s'appliquait.
#
# Or `DOMAIN_KEY` prouvait déjà que le mécanisme des noms convient à une
# énumération figée : `input:held("A")` se vérifie, se complète et se lit. Les
# tables ci-dessous étendent ce traitement aux cinq énumérations restantes.
#
# UNE table par énumération, {nom Lua: constante C}. Ses deux consommateurs en
# dérivent — le checker y valide le nom, le codegen y lit la constante à
# émettre. Pas de seconde liste à tenir d'accord, et le C généré reste lisible
# (`WINR_OBJ` plutôt que `2`).
#
# Un `domain` d'énumération se porte indifféremment sur un PARAMÈTRE (`Param`)
# ou sur une PROPRIÉTÉ (`ApiProp`) : `window.set_layer("MyPanel", ...)` et
# `self.obj_mode = "window"` passent par la même table. C'est ce qui empêche
# qu'un réglage retombe sur un entier nu le jour où il devient une propriété.
# DOMAIN_WIN_REGION fait exception (cf. plus bas) : ses noms rectangle sont
# propres au projet, la table ne peut donc pas être figée ici.

# nom Lua → (constante C, VALEUR). La valeur vit ICI, une seule fois : le
# `#define` correspondant est GÉNÉRÉ dans `runtime_api.h` (cf.
# codegen/runtime_codegen/api_prototypes.build_enum_defines), au lieu d'être
# redéclaré à la main dans `runtime_api_inline.h`. Même geste que les prototypes
# (le « 4e lecteur »), pour les constantes.
OBJ_MODES: dict[str, tuple[str, int]] = {
    "normal": ("OBJ_MODE_NORMAL", 0),   # sprite dessiné normalement
    "blend":  ("OBJ_MODE_BLEND",  1),   # semi-transparent (réservé au mélange)
    "window": ("OBJ_MODE_WINDOW", 2),   # masque : découpe la fenêtre-objet
}

# Les huit directions plus le neutre. Noms complets et non abrégés (« north »
# et non « n ») : la règle de nommage du projet vaut aussi pour les valeurs.
# L'ordre suit les tables de `actor_set_dir` du runtime (nord, puis sens horaire).
DIRECTIONS: dict[str, tuple[str, int]] = {
    "none":       ("DIR_NONE",       0),   # (0, 0), aucune direction
    "north":      ("DIR_NORTH",      1),
    "north_east": ("DIR_NORTH_EAST", 2),
    "east":       ("DIR_EAST",       3),
    "south_east": ("DIR_SOUTH_EAST", 4),
    "south":      ("DIR_SOUTH",      5),
    "south_west": ("DIR_SOUTH_WEST", 6),
    "west":       ("DIR_WEST",       7),
    "north_west": ("DIR_NORTH_WEST", 8),
}

# Les deux SEULS mots-clés fixes de DOMAIN_WIN_REGION (réglé le 2026-08-25,
# cf. ARCHITECTURE.md « Windows — le pochoir ») : ni géométrie ni rang
# disputé, jamais alloués. "win0"/"win1" ont disparu — un rectangle se nomme
# maintenant comme une caméra (`WindowSlot.name`), résolu par
# `window_region_constant`/`window_alloc.py`, pas par un enum statique.
WIN_REGIONS: dict[str, str] = {
    "object":  "WINR_OBJ",  # fenêtre-objet, découpée par les sprites
    "outside": "WINR_OUT",  # tout le reste
}

BLEND_MODES: dict[str, tuple[str, int]] = {
    "none":     ("BLD_MODE_NONE",     0),
    "alpha":    ("BLD_MODE_ALPHA",    1),   # dessus×EVA + dessous×EVB
    "brighten": ("BLD_MODE_BRIGHTEN", 2),   # vers le blanc
    "darken":   ("BLD_MODE_DARKEN",   3),   # vers le noir
}

BLEND_SIDES: dict[str, tuple[str, int]] = {
    "top":    ("BLD_SIDE_TOP",    0),   # la source du mélange
    "bottom": ("BLD_SIDE_BOTTOM", 1),   # ce sur quoi elle se mélange
}

EASE_KINDS: dict[str, tuple[str, int]] = {
    "in":     ("EASE_IN",     0),   # démarre lentement, accélère à l'arrivée
    "out":    ("EASE_OUT",    1),   # démarre vite, ralentit à l'arrivée
    "in_out": ("EASE_IN_OUT", 2),   # les deux, symétriques autour du milieu
}

# Les tables portant (constante, valeur), dans l'ordre — la SOURCE des `#define`
# générés (`build_enum_defines`). L'ordre = l'ordre d'émission.
_ENUM_TABLES: tuple[dict[str, tuple[str, int]], ...] = (
    OBJ_MODES, DIRECTIONS, BLEND_MODES, BLEND_SIDES, EASE_KINDS,
)

# Domaine → {nom Lua: constante}. VUE dérivée des tables ci-dessus (dont la
# valeur est retirée) : le checker (le nom est-il dans l'ensemble ?) et le codegen
# (quelle constante émettre ?) sont inchangés, ils n'ont jamais lu la valeur.
#
# DOMAIN_WIN_REGION n'y figure PAS : depuis le 2026-08-25 ce n'est plus un
# enum statique — "object"/"outside" restent fixes (WIN_REGIONS ci-dessus),
# mais un nom de `WindowSlot` est propre au PROJET. Validé par
# `CheckContext.window_names` (miroir de `camera_names`), résolu par
# `window_region_constant`, pas par `hardware_enum_constant`.
HARDWARE_ENUMS: dict[str, dict[str, str]] = {
    dom: {name: sym for name, (sym, _v) in table.items()}
    for dom, table in (
        (DOMAIN_OBJ_MODE,   OBJ_MODES),
        (DOMAIN_DIRECTION,  DIRECTIONS),
        (DOMAIN_BLEND_MODE, BLEND_MODES),
        (DOMAIN_BLEND_SIDE, BLEND_SIDES),
        (DOMAIN_EASE,       EASE_KINDS),
    )
}


def hardware_enum_defines() -> list[tuple[str, int]]:
    """(constante, valeur) de toutes les énums matérielles, dans l'ordre — pour
    générer leurs `#define`. Une constante n'apparaît qu'une fois ; l'ordre est
    celui des tables."""
    return [(sym, v) for table in _ENUM_TABLES for (sym, v) in table.values()]


def hardware_enum_constant(domain: str, name: str) -> str:
    """Nom Lua → constante C, pour une énumération matérielle.

    Rend la chaîne telle quelle si elle est inconnue : le checker a déjà émis
    l'erreur, et fabriquer une valeur ici la masquerait au profit d'un C qui ne
    compile pas — même règle que partout, la faute se voit sur sa cause."""
    return HARDWARE_ENUMS.get(domain, {}).get(name.lower(), name)


# ─── Constantes écran (résolues par le codegen en littéraux C) ────
# Accessibles en Lua comme screen.width, screen.center_x, etc.
SCREEN_CONSTANTS: dict[str, int] = {
    "width":    240,
    "height":   160,
    "center_x": 120,
    "center_y": 80,
}


# ─── Catalogue complet ─────────────────────────────────────────────

RUNTIME_API: dict[str, ApiFunc] = {

    # ── Transform — position, rotation, échelle ──────────────────────
    # Ce sont des ÉTATS de l'actor : des PROPRIÉTÉS (self.position,
    # self.rotation, self.scale — cf. RUNTIME_PROPS), pas des appels get/set.
    # Le déplacement étalé (`self:move*`) reste un appel : une action, pas un
    # état stocké.
    "actor:move": ApiFunc(
        lua_name="actor:move", c_func="actor_move",
        params=[Param("dir", PARAM_VEC2), Param("speed", PARAM_INT)],
        self_first=True,
        doc="Avance ce frame d'au plus `speed` px dans la direction `dir` (un vec2) — normalisée, donc une diagonale n'avance pas plus vite qu'un axe.",
    ),
    "actor:move_to": ApiFunc(
        lua_name="actor:move_to", c_func="actor_move_to",
        params=[Param("target", PARAM_VEC2), Param("speed", PARAM_INT)],
        self_first=True,
        doc="Avance ce frame d'au plus `speed` px vers la position `target` (un vec2) ; s'arrête pile dessus sans dépasser.",
    ),

    # ── Physics — vélocité stockée sur l'actor ────────────────────────
    # La vélocité est un état : la propriété `self.velocity` (cf. RUNTIME_PROPS).
    # Seul l'ACCUMUL reste un appel — add_velocity est une action, pas une
    # affectation d'état.
    "actor:add_velocity": ApiFunc(
        lua_name="actor:add_velocity", c_func="actor_add_velocity",
        params=[Param("dv", PARAM_VEC2)],
        self_first=True,
        doc="Ajoute `dv` (un vec2, en Q8 — 256 = 1 px/frame) à la vélocité courante. "
            "Utile pour l'accélération ou la gravité, frame après frame.",
    ),
    # Le pendant manquant de self.velocity depuis que sa réponse à « comment
    # l'auteur exprime une vélocité fractionnaire » (ROADMAP v0.19,
    # 2026-08-20) est « self.velocity devient Q8 » : sans cet appel, un
    # sous-pixel accumulé n'a nulle part où s'appliquer — self.position ne
    # rend et n'accepte que des pixels entiers, donc `self.position =
    # self.position + self.velocity` n'a plus de sens dimensionnel. C'est lui
    # qui possède l'accumulateur (littéralement s->x/s->y en Q8), pas un
    # nouveau champ caché sur l'Actor.
    "actor:apply_velocity": ApiFunc(
        lua_name="actor:apply_velocity", c_func="actor_apply_velocity",
        params=[], self_first=True,
        doc="Ajoute la vélocité courante (self.velocity) à la position, en gardant le "
            "sous-pixel d'une frame à l'autre — remplace `self.position = self.position "
            "+ self.velocity`, qui mélangeait deux échelles depuis que self.velocity est "
            "en Q8. self.position continue de ne rendre que des pixels entiers.",
    ),

    # self.grounded (lecture seule) : cf. RUNTIME_PROPS — « y a-t-il un sol
    # sous les pieds » est une requête pure sans argument, donc de l'état.

    # ── Animation ─────────────────────────────────────────────────
    "actor:play_anim": ApiFunc(
        lua_name="actor:play_anim", c_func="actor_play_anim",
        params=[Param("name", PARAM_STR, DOMAIN_ANIM)],
        self_first=True,
        doc="Démarre l'animation nommée (définie dans le SpriteAsset).",
    ),
    # Apparences (marche 3 de « La struct Actor allégée ») : un acteur affiche UN
    # sprite parmi plusieurs composants sprite ; activer l'un désactive l'autre.
    # Comme play_anim, c'est un GESTE — l'animation repart de l'état 0, frame 0, et
    # les tailles/la palette du sprite d'arrivée sont reposées — donc une méthode.
    "actor:activate_sprite": ApiFunc(
        lua_name="actor:activate_sprite", c_func="actor_set_appearance",
        params=[Param("id", PARAM_STR, DOMAIN_SPRITE_ID)],
        self_first=True,
        doc="Active le composant sprite dont l'id est donné (case « Active » de "
            "l'inspecteur) et désactive celui qui l'était : c'est son sprite qui "
            "s'affiche désormais. L'animation repart de son premier état. "
            "Ex: self:activate_sprite(\"blesse\"). Sans effet sur un acteur qui "
            "n'a qu'une apparence.",
    ),
    # self.frame / self.flip_h / self.flip_v / self.pal / self.obj_mode : cf.
    # RUNTIME_PROPS — l'état de l'acteur se lit/s'écrit en propriétés, pas en
    # appels set_*.

    # ── Juiciness — effets de feedback sur le sprite ─────────────────
    # Neuf helpers "prêts à l'emploi", mais qui ne composent QUE ce qui
    # précède (self.sprite_scale/sprite_offset/sprite_rotation/pal/visible,
    # math.ease/lerp/rand) — rien qu'un script ne pourrait écrire à la main.
    # `t`/`duration` sont en frames et fournis par l'appelant : sur GBA un
    # script ne peut pas "attendre" (pas de coroutine, cf. ARCHITECTURE.md),
    # donc c'est lui qui fait avancer `t` d'une frame à l'autre — dans une
    # variable de tête du script, ou dans une GlobalVar quand plusieurs
    # scripts la regardent. Au-delà de `duration`, l'effet retombe à son état
    # neutre (scale 100, offset 0, rotation 0, pal 0, visible) tout seul.
    # squash/stretch/bounce/shake/pulse/pop/wobble écrivent sprite_scale,
    # sprite_offset ou sprite_rotation : comme ces propriétés, ils demandent
    # "Affine transform" coché sur le SpriteComponent, sinon rien ne s'affiche
    # (aucune erreur — même contrat que self.sprite_scale). flash/blink
    # (pal/visible) n'ont pas cette contrainte.
    "actor:squash": ApiFunc(
        lua_name="actor:squash", c_func="actor_squash",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Aplatit le sprite (large et bas) puis revient à 100% en `duration` frames. "
            "`amount` = intensité en points de %. Ex: impact au sol → self:squash(t, 8, 30).",
    ),
    "actor:stretch": ApiFunc(
        lua_name="actor:stretch", c_func="actor_stretch",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Étire le sprite (fin et haut) puis revient à 100% en `duration` frames. "
            "`amount` = intensité en points de %. Ex: départ d'un saut → self:stretch(t, 6, 25).",
    ),
    "actor:bounce": ApiFunc(
        lua_name="actor:bounce", c_func="actor_bounce",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Décale le sprite vers le haut puis le laisse retomber (self.sprite_offset.y), "
            "`amount` px d'amplitude sur `duration` frames.",
    ),
    "actor:shake": ApiFunc(
        lua_name="actor:shake", c_func="actor_shake",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Fait trembler le sprite (self.sprite_offset aléatoire), `amount` px max, "
            "retombant à zéro sur `duration` frames. Écrase tout self.sprite_offset déjà posé.",
    ),
    "actor:flash": ApiFunc(
        lua_name="actor:flash", c_func="actor_flash",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("pal", PARAM_INT)],
        self_first=True,
        doc="Bascule sur la banque palette `pal` (self.pal) tant que t < duration, "
            "puis revient à la banque 0. Ex: dégât → self:flash(t, 4, WHITE_FLASH_BANK).",
    ),
    "actor:blink": ApiFunc(
        lua_name="actor:blink", c_func="actor_blink",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("interval", PARAM_INT)],
        self_first=True,
        doc="Bascule self.visible on/off toutes les `interval` frames tant que t < duration, "
            "puis reste visible. Ex: invincibilité → self:blink(t, 90, 4).",
    ),
    "actor:pulse": ApiFunc(
        lua_name="actor:pulse", c_func="actor_pulse",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Grossit puis revient à 100% (self.sprite_scale), `amount` points de % "
            "d'amplitude sur `duration` frames. Ex: objet ramassable → self:pulse(t, 30, 15).",
    ),
    "actor:pop": ApiFunc(
        lua_name="actor:pop", c_func="actor_pop",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Apparition : grossit de 0% jusqu'à 100+`amount`% puis se stabilise à 100%. "
            "Ex: spawn d'un power-up → self:pop(t, 15, 20).",
    ),
    "actor:wobble": ApiFunc(
        lua_name="actor:wobble", c_func="actor_wobble",
        params=[Param("t", PARAM_INT), Param("duration", PARAM_INT), Param("amount", PARAM_INT)],
        self_first=True,
        doc="Oscille en rotation autour de 0° (self.sprite_rotation), `amount` degrés max, "
            "amplitude retombant à zéro sur `duration` frames.",
    ),

    # La direction s'écrivait de trois façons pour un seul état (`dir_x`/`dir_y`)
    # : un vec2, une boussole nommée, et un entier 0-8 en lecture. Il n'en reste
    # qu'UNE — la propriété `self.direction` (cf. RUNTIME_PROPS), qui accepte le
    # vecteur COMME le nom de boussole et se compare aux deux. `self.auto_dir`
    # est l'état voisin : le calcul automatique depuis la vélocité.
    "actor:destroy": ApiFunc(
        lua_name="actor:destroy", c_func="_destroy",  # résolu par codegen
        params=[], self_first=True,
        doc="Détruit l'actor : appelle on_destroy() puis le désactive (plus d'update, plus de rendu).",
    ),
    # self.tag (lecture seule) et self.pal : cf. RUNTIME_PROPS.

    # ── Cycle de vie : les cinq verbes (ROADMAP v0.16, critère 3) ────
    # La SEULE porte d'écriture de « visible » et « actif » ; l'état se lit par
    # `self.visible` / `self.active`, en lecture seule. `destroy` est plus haut.
    "actor:show": ApiFunc(
        lua_name="actor:show", c_func="actor_set_visible",
        params=[], self_first=True, fixed_args=(1,),
        doc="Affiche le sprite de l'actor. Ex: self:show()",
    ),
    "actor:hide": ApiFunc(
        lua_name="actor:hide", c_func="actor_set_visible",
        params=[], self_first=True, fixed_args=(0,),
        doc="Cache le sprite de l'actor ; il continue d'exister, d'être mis à "
            "jour et de heurter. Ex: self:hide()",
    ),
    "actor:activate": ApiFunc(
        lua_name="actor:activate", c_func="actor_set_active",
        params=[], self_first=True, fixed_args=(1,),
        doc="Réactive l'actor : update, collisions et rendu reprennent. Ex: other:activate()",
    ),
    "actor:deactivate": ApiFunc(
        lua_name="actor:deactivate", c_func="actor_set_active",
        params=[], self_first=True, fixed_args=(0,),
        doc="Désactive l'actor : plus d'update, de collisions ni de rendu, mais il "
            "existe toujours (contrairement à destroy) et peut être réactivé. "
            "Ex: self:deactivate()",
    ),

    # ── Boîtes de collision — une référence typée ───────────────────
    # Ce que l'inspecteur du CollisionBoxComponent règle (actif, solide, décalage,
    # taille) est vivant au runtime : la résolution contre la carte et le test de
    # chevauchement lisent ces mêmes champs à chaque frame. La boîte est un objet
    # à part entière : on la demande à l'acteur par son tag, on la tient dans une
    # variable, et ses champs sont des PROPRIÉTÉS (cf. RUNTIME_PROPS, clés
    # `collision_box.*`), ses actions des MÉTHODES (`collision_box:*`). Le tag est
    # la clé : le lire n'a de sens que pour comparer.
    "actor:collision_box": ApiFunc(
        lua_name="actor:collision_box", c_func="actor_get_box",
        params=[Param("tag", PARAM_STR, DOMAIN_BOX_TAG)],
        ret=REF_COLLISION_BOX, self_first=True,
        doc='La boîte de collision de cet actor portant ce tag. Rend nil si '
            'l\'actor n\'en a pas — `if hb then` le teste. Ex: '
            'local hb = self:collision_box("hitbox")',
    ),
    f"{REF_COLLISION_BOX}:overlaps": ApiFunc(
        lua_name="collision_box:overlaps", c_func="collision_box_overlaps_actor",
        params=[Param("other", PARAM_ACTOR)], ret="bool", self_first=True,
        doc="Cette boîte chevauche-t-elle `other` ? `other` est un actor (n'importe "
            "laquelle de ses boîtes actives) ou une autre boîte (celle-là "
            "seulement). Une boîte inactive ne chevauche personne. "
            "Ex: if hb:overlaps(other) then ... end",
    ),
    f"{REF_COLLISION_BOX}:activate": ApiFunc(
        lua_name="collision_box:activate", c_func="collision_box_set_active",
        params=[], self_first=True, fixed_args=(1,),
        doc="Remet la boîte en jeu : elle heurte de nouveau la carte et les autres "
            "boîtes. Ex: hb:activate()",
    ),
    f"{REF_COLLISION_BOX}:deactivate": ApiFunc(
        lua_name="collision_box:deactivate", c_func="collision_box_set_active",
        params=[], self_first=True, fixed_args=(0,),
        doc="Retire la boîte du jeu : elle ne heurte plus rien, sans être "
            "détruite. Ex: hb:deactivate()",
    ),
    "actor:play_sfx": ApiFunc(
        lua_name="actor:play_sfx", c_func="_play_sfx",  # résolu par codegen (SoundFxComponent de l'actor)
        params=[], self_first=True,
        doc="Joue le Sfx configuré dans le SoundFX component de cet actor.",
    ),

    # ── Actors ─────────────────────────────────────────────────────
    "actor.spawn": ApiFunc(
        lua_name="actor.spawn", c_func="_spawn",     # résolu par codegen
        params=[Param("prefab", PARAM_STR, DOMAIN_PREFAB), Param("position", PARAM_VEC2)],
        # 3e argument FACULTATIF : une table { export = valeur } réglant l'instance
        # née (chantier « Les exports de script », tranche poolé). variadic pour
        # que le checker l'accepte ; sa validation dédiée vit dans _check_spawn_table.
        variadic=True,
        ret="actor",   # rend l'instance née, ou nil si le pool est plein (ROADMAP v0.17 T6)
        doc='Instancie un prefab poolé à `position` (un vec2) et rend l\'instance née, ou nil si le pool est plein. Une table facultative règle ses exports : actor:spawn("Bullet", pos, { speed = 8, team = "RED" }) ; les clés absentes gardent la valeur du prefab. Ex: local b = actor:spawn("Bullet", vec2(116, 76)); if b then b:set_velocity(0, -2) end.',
    ),
    "actor.get": ApiFunc(
        lua_name="actor.get", c_func="_get_actor",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_ACTOR)],
        ret="actor",
        doc='Un acteur de la scène, par NOM (littéral, résolu à la compilation : actor:get("PADDLE_AUTO"):move_to(vec2(120,80),2)) ou par INDEX dynamique 1-based (actor:get(i), de 1 à actor:count(), dans l\'ordre de la scène). Rend nil si absent ou détruit — à tester. Pour lire une position, passe par un local : local p = actor:get(i) ; puis p.position.x.',
    ),
    "actor.count": ApiFunc(
        lua_name="actor.count", c_func="_actor_count",   # résolu par codegen
        params=[], ret="int",
        doc="Nombre d'acteurs POSÉS de la scène active — la borne de actor:get(i). Ex: for i=1,actor:count() do local a=actor:get(i) ... end.",
    ),

    # ── Éléments d'interface, typés (ROADMAP v0.16, étape c) ─────────
    # `interface:get("Nom")` rend une référence du TYPE RÉEL de l'élément, lu dans la
    # mise en page au build : `list`, `image`, `text_region`, ou `ui_element` pour un
    # conteneur. Les membres d'un élément vivent sur SON type — `menu.index`,
    # `heart.state`, `box:draw(...)` — et le cycle de vie (`show`/`hide`/`visible`) sur
    # `ui_element`, dont les autres héritent. Plus aucune fonction de module ne prend
    # un nom d'élément en premier argument : c'était `list.index("menu")`,
    # `interface.image_set("heart", …)`, `interface.draw_text("box", …)`.
    #
    # Cacher un conteneur cache tout son sous-arbre SANS toucher ses enfants : la
    # visibilité effective remonte la chaîne des parents au runtime, elle ne
    # se propage jamais à l'écriture (cf. models/ui_region.UILayout.is_visible,
    # même règle côté éditeur).
    "interface.get": ApiFunc(
        lua_name="interface.get", c_func="_ui_get",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_UI_ELEMENT)],
        ret=REF_UI_ELEMENT, ret_by_name=True,
        doc='Un élément d\'interface par son nom, du type de sa nature dans la mise '
            'en page (liste, image, zone de texte…). Résolu à la compilation, zéro '
            'overhead runtime. Ex: interface:get("alerte"):show().',
    ),
    # Cycle de vie : `show`/`hide` sont deux valeurs du MÊME appel C (`fixed_args`).
    # `visible` (lecture seule, cf. RUNTIME_PROPS) est le seul moyen de lire l'état.
    f"{REF_UI_ELEMENT}:show": ApiFunc(
        lua_name=f"{REF_UI_ELEMENT}:show", c_func="ui_element_show",
        params=[], self_first=True, fixed_args=(1,),
        doc='Affiche l\'élément (et implicitement ses enfants, sauf s\'ils sont '
            'cachés individuellement). Ex: interface:get("alerte"):show()',
    ),
    f"{REF_UI_ELEMENT}:hide": ApiFunc(
        lua_name=f"{REF_UI_ELEMENT}:hide", c_func="ui_element_show",
        params=[], self_first=True, fixed_args=(0,),
        doc='Cache l\'élément et tout son sous-arbre. Ex: interface:get("alerte"):hide()',
    ),
    # Une LISTE : la navigation d'un menu (ROADMAP v0.22). Le moteur suit un index ; il
    # ne dessine rien. Les rangées sont les zones de texte du panneau, et c'est le script
    # qui écrit leur contenu (`menu:row(1):draw(...)`). Un item est une LIGNE DE DONNÉE,
    # pas un objet d'interface : c'est ce qui évite un widget par genre de menu. Son
    # nombre, son index, son premier item affiché et sa main sont des PROPRIÉTÉS
    # (cf. RUNTIME_PROPS, `list.*`) ; `activate`/`deactivate` sont les verbes communs.
    f"{REF_LIST}:row": ApiFunc(
        lua_name=f"{REF_LIST}:row", c_func="ui_list_row",
        params=[Param("r", PARAM_INT)], ret=REF_TEXT_REGION, self_first=True,
        doc="La zone de texte qui porte la rangée r (1 = la première visible), où "
            "écrire l'item : menu:row(1):draw(\"Potion\"). Hors bornes, la référence "
            "vaut -1 et n'écrit rien.",
    ),
    f"{REF_LIST}:activate": ApiFunc(
        lua_name=f"{REF_LIST}:activate", c_func="ui_list_set_active",
        params=[], self_first=True, fixed_args=(1,),
        doc="Donne la croix directionnelle à cette liste. C'est ce qui permet un menu "
            "et son sous-menu à l'écran en même temps : sans ça, les deux bougent au "
            "même appui. Ex: menu:activate()",
    ),
    f"{REF_LIST}:deactivate": ApiFunc(
        lua_name=f"{REF_LIST}:deactivate", c_func="ui_list_set_active",
        params=[], self_first=True, fixed_args=(0,),
        doc="Retire la main à cette liste : elle reste à l'écran et garde son item "
            "courant, seule la SÉLECTION est coupée. La cacher (:hide()) est autre "
            "chose — elle disparaît. Ex: menu:deactivate()",
    ),
    # Une IMAGE : un sprite à état posé sur la mise en page. L'élément est AUTHORÉ dans le
    # canvas (position, sprite, état de départ) et le script ne fait que changer d'état
    # ou décaler — ce qui rouvrirait la géométrie au runtime reste fermé (cf.
    # models/ui_region.py, « Pas de FieldValue »). `state` et `offset` sont des
    # propriétés (cf. RUNTIME_PROPS, `image.*`).
    f"{REF_IMAGE}:play": ApiFunc(
        lua_name=f"{REF_IMAGE}:play", c_func="ui_image_play",
        params=[], self_first=True, fixed_args=(1,),
        doc="Lance le défilement des frames de l'état affiché. Ex: heart:play()",
    ),
    f"{REF_IMAGE}:pause": ApiFunc(
        lua_name=f"{REF_IMAGE}:pause", c_func="ui_image_play",
        params=[], self_first=True, fixed_args=(0,),
        doc="Fige l'image sur la première frame de son état. Ex: cursor:pause()",
    ),
    # Une ZONE DE TEXTE : c'est ELLE qui écrit, pas un module. La cible (BG ou sprites) ne
    # remonte pas jusqu'ici : c'est une conséquence de l'ancrage du nœud Interface, pas un
    # choix d'appel. `draw` se traduit par un émetteur (le littéral pose ses `$locale`).
    f"{REF_TEXT_REGION}:draw": ApiFunc(
        lua_name=f"{REF_TEXT_REGION}:draw", c_func="text_draw_in",
        params=[Param("id", PARAM_STR, DOMAIN_TEXT, literal_ok=True)], self_first=True,
        doc='Affiche un texte dans cette zone. Une clé est traduisible ; un littéral '
            'peut lire une locale avec `$nom` et tronquer avec `!1` à `!9`. '
            'Ex: interface:get("boite_bas"):draw("PV : $hp!3")',
    ),
    f"{REF_TEXT_REGION}:clear": ApiFunc(
        lua_name=f"{REF_TEXT_REGION}:clear", c_func="text_clear_in",
        params=[], self_first=True,
        doc='Vide cette zone de texte. Ex: interface:get("boite_bas"):clear()',
    ),
    # Un texte à tempo (`[speed=4]`, `[pause=30]`) introduit un ÉTAT par zone : il ne
    # s'affiche plus, il se lit (`reading`, cf. RUNTIME_PROPS). `skip` révèle tout d'un
    # coup — le bouton « passer » —, et sans les deux un script n'aurait aucun moyen de
    # savoir quand enchaîner.
    f"{REF_TEXT_REGION}:skip": ApiFunc(
        lua_name=f"{REF_TEXT_REGION}:skip", c_func="text_skip",
        params=[], self_first=True,
        doc='Révèle tout le texte d\'un coup. Ex: if input:pressed("A") then box:skip() end',
    ),

    # ── Input ──────────────────────────────────────────────────────
    # `held`/`pressed` gardent leur nom (ROADMAP « Les inputs personnalisés »,
    # décision verrouillée) ; `n` optionnel sur `held` est vérifié à part
    # (`checker._check_input_call`) — `variadic` n'existe que pour ça, ce
    # n'est pas une vraie fonction à arité libre. Les quatre ne lisent qu'un
    # ACCORD (bouton ou InputBinding) — jamais une séquence, qui a son propre
    # nom d'appel (`get_sequence`, décision de l'auteur du 2026-09-27).
    "input.held": ApiFunc(
        lua_name="input.held", c_func="input_held",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY)], variadic=True,
        ret="bool",
        doc="Vrai si l'accord est tenu ce frame. Avec un 2e argument (frames), "
            "vrai depuis AU MOINS ce nombre de frames consécutives (appui long).",
    ),
    "input.pressed": ApiFunc(
        lua_name="input.pressed", c_func="input_pressed",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY)],
        ret="bool",
        doc="Vrai si l'accord vient de se compléter (front montant).",
    ),
    "input.released": ApiFunc(
        lua_name="input.released", c_func="input_released",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY)],
        ret="bool",
        doc="Vrai si l'accord était complet au frame précédent et ne l'est "
            "plus (saut à hauteur variable).",
    ),
    "input.buffered": ApiFunc(
        lua_name="input.buffered", c_func="input_buffered",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY), Param("frames", PARAM_INT)],
        ret="bool",
        doc="Vrai si l'accord vient d'être pressé dans les `frames` derniers "
            "frames (tampon de saut) ET que cet appui n'a pas déjà été "
            "consommé. Répondre vrai CONSOMME l'appui. `frames` doit être un "
            "nombre écrit en clair (comme wait()) : il fixe la profondeur de "
            "l'anneau au build. Piège : évaluée avant un `and` qui la suit — "
            "écrire `if au_sol and input:buffered(...)`, jamais l'inverse, "
            "pour ne la consommer qu'au bon moment.",
    ),
    "input.get_sequence": ApiFunc(
        lua_name="input.get_sequence", c_func="input_seq_pressed",
        params=[Param("nom", PARAM_STR, DOMAIN_INPUT_SEQUENCE)],
        ret="bool",
        doc="Vrai le frame où la séquence déclarée (Project Settings → Input "
            "→ Séquences) vient de se compléter : son DERNIER pas vient de "
            "se compléter, les précédents s'étant trouvés en amont, dans "
            "l'ordre, dans la fenêtre de la séquence.",
    ),
    "input.get_axis": ApiFunc(
        lua_name="input.get_axis", c_func="input_get_axis",
        params=[Param("x", PARAM_STR, DOMAIN_AXIS)], variadic=True,
        ret="int",
        doc='Position de l\'axe `x` : -1, 0 ou 1. Avec un 2e argument (y), rend '
            'un vec2 des deux axes — la forme 2D. "horizontal"/"vertical" sont '
            "toujours définis (la croix) ; un axe déclaré s'y ajoute.",
    ),
    # ── Audio ──────────────────────────────────────────────────────
    "sfx.play": ApiFunc(
        lua_name="sfx.play", c_func="sfx_play",
        params=[Param("name", PARAM_STR, DOMAIN_SFX)],
        ret=REF_SFX,
        doc="Joue un effet sonore one-shot. L'appel REND l'effet qui vient de "
            "démarrer : `sfx:play(\"Bip\")` seul reste le cas courant, "
            "`local pas = sfx:play(\"Pas\")` le suit ensuite. La référence "
            "vaut 0 quand maxmod n'en a pas donné — plus aucun canal libre "
            "(l'effet ne sonne pas), ou les 16 références déjà prises (il "
            "sonne quand même).",
    ),
    # Les cinq méthodes de la référence. Elles ne valent que sur ce qu'un
    # `sfx.play` a rendu : la clé porte le TYPE, pas le nom d'une variable.
    # Une référence périmée — le son est fini — ne fait rien : maxmod range un
    # compteur dans le handle et le relit à chaque appel (mesuré, v0.8.6).
    f"{REF_SFX}:stop": ApiFunc(
        lua_name="sfx:stop", c_func="sfx_stop",
        params=[], self_first=True,
        doc="Coupe cet effet. Sans effet s'il est déjà terminé.",
    ),
    f"{REF_SFX}:playing": ApiFunc(
        lua_name="sfx:playing", c_func="sfx_is_playing",
        params=[], ret="int", self_first=True,
        doc="Vrai tant que cet effet sonne.",
    ),
    f"{REF_SFX}:set_volume": ApiFunc(
        lua_name="sfx:set_volume", c_func="sfx_set_volume",
        params=[Param("percent", PARAM_INT)], self_first=True,
        doc="Règle le volume de CET effet, en pourcentage (100 = le niveau de "
            "la ressource). Sans rapport avec `sound_box.set_volume`, qui règle "
            "la catégorie entière.",
    ),
    f"{REF_SFX}:set_pitch": ApiFunc(
        lua_name="sfx:set_pitch", c_func="sfx_set_pitch",
        params=[Param("percent", PARAM_INT)], self_first=True,
        doc="Règle la hauteur de CET effet, en pourcentage de sa hauteur "
            "d'origine — 200 = une octave au-dessus, 50 = une octave en "
            "dessous. La valeur est absolue : la même donne la même hauteur, "
            "quel que soit le nombre d'appels.",
    ),
    f"{REF_SFX}:set_panning": ApiFunc(
        lua_name="sfx:set_panning", c_func="sfx_set_panning",
        params=[Param("panning", PARAM_INT)], self_first=True,
        doc="Place cet effet dans le champ stéréo : −100 à gauche, 0 au "
            "centre, +100 à droite.",
    ),
    "music.play": ApiFunc(
        lua_name="music.play", c_func="music_play",
        params=[Param("name", PARAM_STR, DOMAIN_MUSIC)],
        doc="Démarre une piste musicale (en boucle).",
    ),
    "music.stop": ApiFunc(
        lua_name="music.stop", c_func="music_stop",
        params=[],
        doc="Arrête la musique.",
    ),
    # Pas de référence côté musique : il n'y a qu'un module à la fois sur cette
    # console, donc rien à tenir — l'appel désigne le seul qui puisse jouer.
    "music.pause": ApiFunc(
        lua_name="music.pause", c_func="music_pause",
        params=[],
        doc="Suspend la musique là où elle en est. `music:resume()` la reprend "
            "au même endroit.",
    ),
    "music.resume": ApiFunc(
        lua_name="music.resume", c_func="music_resume",
        params=[],
        doc="Reprend la musique suspendue.",
    ),
    "music.is_playing": ApiFunc(
        lua_name="music.is_playing", c_func="music_is_playing",
        params=[], ret="int",
        doc="Vrai tant qu'un module joue. Faux après `music:stop()`, vrai "
            "pendant une pause.",
    ),
    "music.set_volume": ApiFunc(
        lua_name="music.set_volume", c_func="music_set_volume",
        params=[Param("percent", PARAM_INT)],
        doc="Règle le volume de la musique, en pourcentage. C'est le SEUL "
            "niveau de la couche module : le matériel n'a qu'un scaler, et "
            "aucune boîte n'en ajoute un deuxième.",
    ),
    # Le jingle : la seule superposition que la console autorise. Il ne boucle
    # pas, prend jusqu'à 4 des 8 canaux, et il n'y en a qu'un à la fois — trois
    # faits matériels, énoncés dans la doc plutôt que corrigés en douce.
    "sound_box.set_state": ApiFunc(
        lua_name="sound_box.set_state", c_func="sound_box_set_state",
        params=[Param("state", PARAM_STR, DOMAIN_SOUND_BOX_STATE)],
        doc="Change l'état de la SoundBox — « le sol est du sable », « on est "
            "en vol ». Les actions posées sur les frames d'animation se "
            "résolvent alors vers les échantillons de ce nouvel état : le même "
            "cycle de marche sonne le sable ou les cailloux sans être authoré "
            "deux fois.",
    ),
    "jingle_box.set_state": ApiFunc(
        lua_name="jingle_box.set_state", c_func="jingle_box_set_state",
        params=[Param("state", PARAM_STR, DOMAIN_JINGLE_BOX_STATE)],
        doc="Change l'état de la JingleBox : vers quel module chaque "
            "action de jingle pointe désormais.",
    ),
    "sound_box.set_volume": ApiFunc(
        lua_name="sound_box.set_volume", c_func="sfx_set_effects_volume",
        params=[Param("percent", PARAM_INT)],
        doc="Règle le volume de TOUS les effets, en pourcentage. C'est un "
            "réglage de mixage : il multiplie le volume propre de chaque "
            "effet, il ne le remplace pas.",
    ),
    "jingle_box.set_volume": ApiFunc(
        lua_name="jingle_box.set_volume", c_func="music_jingle_volume",
        params=[Param("percent", PARAM_INT)],
        doc="Règle le volume de la couche jingle, en pourcentage. Avec "
            "`music.set_volume`, c'est la moitié du duck : la musique "
            "s'efface pendant la fanfare, puis remonte.",
    ),
    "music_box.trigger": ApiFunc(
        lua_name="music_box.trigger", c_func="music_box_trigger",
        params=[Param("trigger", PARAM_STR, DOMAIN_MUSIC_BOX_TRIGGER)],
        doc="Émet un déclencheur de la MusicBox. C'est la BOÎTE qui décide "
            "vers quel état il mène et par quelle transition — le script dit "
            "seulement qu'il s'est passé quelque chose.",
    ),
    "music.jingle": ApiFunc(
        lua_name="music.jingle", c_func="music_jingle",
        params=[Param("name", PARAM_STR, DOMAIN_MUSIC)],
        doc="Joue un module PAR-DESSUS la musique en cours, sans l'arrêter — "
            "une fanfare de victoire, un carillon. Il ne boucle jamais et se "
            "termine seul. Un seul à la fois, et il prend jusqu'à 4 des 8 "
            "canaux du projet. C'est la seule façon de faire sonner deux "
            "musiques ensemble sur cette console.",
    ),
    "music.jingle_playing": ApiFunc(
        lua_name="music.jingle_playing", c_func="music_jingle_playing",
        params=[], ret="int",
        doc="Vrai tant qu'un jingle sonne.",
    ),

    # Les DEUX transitions du matériel. Il n'y en a pas de troisième : maxmod
    # n'a qu'une couche de module qui boucle, donc aucun fondu enchaîné n'est
    # possible sur cette console (cf. ROADMAP v0.8.3).
    "music.fade_to": ApiFunc(
        lua_name="music.fade_to", c_func="music_fade_to",
        params=[Param("name", PARAM_STR, DOMAIN_MUSIC),
                Param("frames", PARAM_INT)],
        doc="Passe à une autre piste par un fondu traversant : le volume tombe "
            "à zéro, la piste change, le volume remonte. Marche entre deux "
            "morceaux quelconques, au prix d'un creux audible. `frames` est la "
            "durée totale des deux moitiés.",
    ),
    "music.cut_to": ApiFunc(
        lua_name="music.cut_to", c_func="music_cut_to",
        params=[Param("name", PARAM_STR, DOMAIN_MUSIC)],
        doc="Passe à une autre piste SANS creux, à la fin du motif en cours, "
            "en reprenant à la même position. C'est ce qui enchaîne deux "
            "variantes d'un même morceau — la batterie qui entre, le thème qui "
            "s'intensifie. Les deux pistes doivent avoir la même structure ; le "
            "validateur le vérifie.",
    ),

    # ── Scènes ─────────────────────────────────────────────────────
    "scene.switch": ApiFunc(
        lua_name="scene.switch", c_func="scene_switch",
        params=[Param("name", PARAM_STR, DOMAIN_SCENE)],
        doc="Passe à une autre scène au début de la prochaine frame.",
    ),

    # ── Langue (ROADMAP v0.9, phase 4) ───────────────────────────────
    # Rien de plus que ces deux appels : la police EFFECTIVE (`g_lang_font`,
    # phase 3.2) et le sous-ensemble de glyphes ÉMIS (union de toutes les
    # langues, phase 3.3) sont déjà prêts pour n'importe laquelle — changer
    # `g_lang` n'a donc RIEN d'autre à faire lui-même. Rendre le changement
    # VISIBLE, en revanche, retraverse la scène courante comme un vrai
    # changement de scène (mêmes zones réécrites, même transition si le
    # projet en a une) — `lang_set` le déclenche, pas le script.
    "lang.set": ApiFunc(
        lua_name="lang.set", c_func="lang_set",
        params=[Param("code", PARAM_STR, DOMAIN_LANG)],
        doc="Change la langue active et recharge la scène courante pour "
            "l'appliquer (comme un scene.switch vers elle-même — acteurs et "
            "état de scène repartent à zéro). Ex: lang:set(\"fr\").",
    ),
    "lang.get": ApiFunc(
        lua_name="lang.get", c_func="lang_get",
        params=[], ret="int",
        doc="La langue active — un index (0 = la source), comparable à "
            "LANG_<CODE>. Ex: if lang:get() == LANG_FR then ... end.",
    ),

    # ── Variables (globals + constantes) ──────────────────────────
    # Deux registres distincts (project.globals / project.constants, cf.
    # core/project_variables.py — un nom PEUT être partagé entre les deux,
    # leurs préfixes C ne collisionnent pas), regroupés ici sous un même
    # en-tête parce qu'ils répondent à la même question côté script : « lire
    # une valeur nommée du projet ». Rester deux modules Lua (`global.*` /
    # `const.*`) plutôt qu'un seul évite justement l'ambiguïté d'un nom
    # partagé — voir la discussion en tête de ce fichier avant d'y toucher.
    #
    # Pas d'entrée de catalogue ici : `global.nom` / `const.nom` ne sont pas
    # des APPELS mais un accès POINTÉ, comme `self.position` (RUNTIME_PROPS)
    # ou `data.Objets` — sauf que le membre est un nom de PROJET, pas un nom
    # de langage fixe, donc ni l'un ni l'autre catalogue ne convient. Le
    # checker (`_check_global_scalar`/`_check_const_scalar`/
    # `_check_global_indexed`) et le codegen (`_expr`, branche `ExprIndex`)
    # les résolvent directement contre `project.globals`/`.constants` — un
    # accès direct en C (g_nom / CONST_NOM), jamais un appel de fonction.
    # Lecture seule côté constante : `const.nom = …` est refusé par le
    # checker (`_check_const_write`). Un tableau (ROADMAP v0.20) s'indexe :
    # `global.nom[i]`, lecture ET écriture, borné par `_check_global_indexed`.

    # ── Tableaux ───────────────────────────────────────────────────
    # `array` n'est pas un appel : c'est la DÉCLARATION d'un tableau, lue par le
    # codegen à l'endroit du `local` (cf. parser.array_dims). Elle figure quand
    # même au catalogue, parce que c'est lui qui remplit la sidebar et la
    # référence de l'écran de script : une forme absente d'ici est une forme que
    # personne ne découvre.
    "array": ApiFunc(
        lua_name="array", c_func="_array",   # résolu par codegen (déclaration)
        params=[Param("taille", PARAM_INT)],
        variadic=True,
        ret="int",
        doc="Déclare un tableau d'entiers rempli de zéros : local sac = array(8). "
            "Deux tailles pour une grille — array(20, 12) se lit grille[1..20][1..12]. "
            "La taille est fixée au build ; les tableaux sont indexés à partir de 1, "
            "et #sac vaut leur taille.",
    ),

    # ── Diagnostic (ROADMAP v0.14) ───────────────────────────────────
    # Ni int ni string : chaque argument peut être l'un ou l'autre, ce
    # qu'aucun PARAM_* existant ne décrit — d'où params=[] plutôt qu'un type
    # inventé qui mentirait sur la moitié des appels. Résolu par codegen, pas
    # par `_emit_api_call` : la ligne devient une SÉQUENCE d'appels C
    # (debug_write_str/debug_write_int, un par argument, puis debug_flush),
    # jamais un unique appel variadique — le moteur n'émet pas de printf.
    # Disparaît des builds release (cf. runtime/include/gba_debug.h) : un
    # projet qui n'active jamais le build debug ne paie rien.
    "debug.log": ApiFunc(
        lua_name="debug.log", c_func="_debug_log",   # résolu par codegen
        params=[], variadic=True,
        doc='Écrit une ligne dans le journal mGBA — jamais à l\'écran du jeu. '
            'Concatène ses arguments, chacun déjà une chaîne ou un entier : '
            'debug:log("hp=", hp, " x=", x). Sans effet, et retiré de la ROM, '
            'hors build debug (réglage du projet).',
    ),

    # ── Affichage texte : voir `text.*` (cf. REMOVED_API) ─────────
    # `display.print` / `display.clear` (libtonc TTE) ont été RETIRÉS. Leur
    # chaîne de format vivait dans le script, donc hors de la table de textes :
    # intraduisible, alors que la table existe pour ça. Et la police de TTE
    # occupait les mêmes tuiles que la nôtre, les deux s'écrasant.
    #
    # Migration : un libellé devient une entrée de table (`text.draw`), une
    # valeur devient `text.draw_num`. Les noms retirés sont listés dans
    # REMOVED_API pour que le checker guide au lieu de dire « inconnu ».

    # ── Caméra ────────────────────────────────────────────────────
    # La position et les bornes sont des ÉTATS de la caméra : des PROPRIÉTÉS
    # (camera.position, camera.bound — cf. RUNTIME_PROPS). Ne restent des
    # appels que les ACTIONS : suivre, basculer, secouer.
    "camera.follow": ApiFunc(
        lua_name="camera.follow", c_func="camera_follow",
        params=[
            Param("target",   PARAM_VEC2),
            Param("margin_x", PARAM_INT),
            Param("margin_y", PARAM_INT),
        ],
        doc="Suit `target` (un vec2) avec une zone morte. Ex: camera:follow(camera.position, 40, 20)",
    ),
    "camera.switch": ApiFunc(
        lua_name="camera.switch", c_func="camera_switch",
        params=[Param("name", PARAM_STR, DOMAIN_CAMERA)],
        doc="Active une autre caméra du projet — son cadrage et ses bornes sont posés "
            "immédiatement. Une seule caméra est active à la fois.",
    ),
    # ── Séquences ────────────────────────────────────────────────
    # Un seul entier porte l'état d'une séquence : 0 = arrêtée, 1..N = l'étape
    # en cours. Les trois portes ne sont donc qu'une écriture, une écriture et
    # un test — aucune fonction C derrière (cf. codegen._emit_sequence_*), d'où
    # `c_func` vide. Elles figurent au catalogue parce que c'est lui qui porte
    # la documentation, la validation d'arguments et la sidebar.
    "sequence.start": ApiFunc(
        lua_name="sequence.start", c_func="",
        params=[Param("name", PARAM_STR, DOMAIN_SEQUENCE)],
        doc="Démarre (ou redémarre depuis le début) la séquence `on_sequence_<name>` "
            "de ce script. Ex: sequence:start(\"intro\")",
    ),
    "sequence.stop": ApiFunc(
        lua_name="sequence.stop", c_func="",
        params=[Param("name", PARAM_STR, DOMAIN_SEQUENCE)],
        doc="Arrête la séquence en cours de route. Elle ne reprend pas où elle en "
            "était : un `sequence.start` la relance depuis le début.",
    ),
    "sequence.running": ApiFunc(
        lua_name="sequence.running", c_func="",
        params=[Param("name", PARAM_STR, DOMAIN_SEQUENCE)], ret="bool",
        doc="Vrai tant que la séquence n'a pas atteint sa dernière ligne. "
            "Ex: if not sequence:running(\"intro\") then … end",
    ),

    "camera.shake": ApiFunc(
        lua_name="camera.shake", c_func="camera_shake",
        params=[Param("amplitude", PARAM_INT), Param("frames", PARAM_INT)],
        doc="Secoue la caméra : amplitude en pixels, retombant à zéro sur la durée. "
            "Ex: camera:shake(4, 20)",
    ),

    # ── Maths ────────────────────────────────────────────────────
    "math.abs": ApiFunc(
        lua_name="math.abs", c_func="math_abs",
        params=[Param("x", PARAM_INT)], ret="int",
        doc="Valeur absolue entière.",
    ),
    "math.clamp": ApiFunc(
        lua_name="math.clamp", c_func="math_clamp",
        params=[Param("x", PARAM_INT), Param("lo", PARAM_INT), Param("hi", PARAM_INT)],
        ret="int",
        doc="Bloque x entre lo et hi.",
    ),
    "math.rand": ApiFunc(
        lua_name="math.rand", c_func="math_rand",
        params=[Param("lo", PARAM_INT), Param("hi", PARAM_INT)],
        ret="int",
        doc="Entier aléatoire entre lo et hi inclus. Ex: math.rand(1, 3) → 1, 2 ou 3.",
    ),
    "math.sign": ApiFunc(
        lua_name="math.sign", c_func="math_sign",
        params=[Param("x", PARAM_INT)], ret="int",
        doc="Signe de x : retourne -1, 0 ou 1.",
    ),
    "math.min": ApiFunc(
        lua_name="math.min", c_func="math_min",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT)], ret="int",
        doc="Minimum de deux entiers.",
    ),
    "math.max": ApiFunc(
        lua_name="math.max", c_func="math_max",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT)], ret="int",
        doc="Maximum de deux entiers.",
    ),
    "math.lerp": ApiFunc(
        lua_name="math.lerp", c_func="math_lerp",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT), Param("num", PARAM_INT), Param("den", PARAM_INT)],
        ret="int",
        doc="Interpole linéairement entre a et b à la fraction num/den. "
            "Ex: math.lerp(0, 100, frame, 30) glisse de 0 à 100 sur 30 frames.",
    ),
    "math.ease": ApiFunc(
        lua_name="math.ease", c_func="math_ease",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT), Param("num", PARAM_INT), Param("den", PARAM_INT),
                Param("kind", PARAM_STR, DOMAIN_EASE)],
        ret="int",
        doc='Comme math.lerp, mais en courbant la fraction avant de l\'appliquer. '
            '"in" démarre lentement et accélère, "out" démarre vite et ralentit, '
            '"in_out" combine les deux. Ex: math.ease(0, 100, frame, 30, "out").',
    ),
    "math.sin": ApiFunc(
        lua_name="math.sin", c_func="math_sin",
        params=[Param("deg", PARAM_INT)], ret="int",
        doc="Sinus de deg (degrés), en fixe Q8 (×256 : -256 à 256, pas de virgule "
            "flottante sur GBA) — la même échelle que la matrice affine du sprite. "
            "Ex: dx = amount * math.sin(deg) / 256.",
    ),
    "math.cos": ApiFunc(
        lua_name="math.cos", c_func="math_cos",
        params=[Param("deg", PARAM_INT)], ret="int",
        doc="Cosinus de deg (degrés), en fixe Q8 (×256), même échelle que math.sin.",
    ),
    "math.sqrt": ApiFunc(
        lua_name="math.sqrt", c_func="math_sqrt",
        params=[Param("x", PARAM_INT)], ret="int",
        doc="Racine carrée entière (tronquée). x négatif ou nul → 0.",
    ),
    "math.atan2": ApiFunc(
        lua_name="math.atan2", c_func="math_atan2",
        params=[Param("y", PARAM_INT), Param("x", PARAM_INT)], ret="int",
        doc="Angle en degrés (0-359) du vecteur (x, y) — même convention d'axes que "
            "self.rotation, donc self.rotation = math.atan2(vel.y, vel.x) oriente "
            "l'actor dans le sens de sa vélocité.",
    ),

    # ── Scène ──────────────────────────────────────────────────────
    # scene.frame (int, lecture seule) et scene.size (rect) : cf. RUNTIME_PROPS
    # — la scène expose son état en propriétés.

    # ── Tile ───────────────────────────────────────────────────────
    f"{REF_COLLISION_BOX}:get_collision_tile": ApiFunc(
        lua_name="collision_box:get_collision_tile", c_func="collision_box_get_collision_tile",
        params=[Param("x", PARAM_INT), Param("y", PARAM_INT)], ret="int", self_first=True,
        doc="Type de tile de la carte de collision à la position monde (x, y) en "
            "pixels. 0 = vide (ou hors carte). Le point est absolu : il ne dépend "
            "pas de cette boîte, qui sert seulement de porte d'entrée (le verbe "
            "`get` est juste : le tile n'est pas un champ de la boîte, c'est une "
            "question posée à la carte). Utile pour des déclencheurs non solides "
            "(pièces, zones de spawn, poison). "
            "Ex: local t = hb:get_collision_tile(hb.bounds.x, hb.bounds.y + hb.bounds.h)",
    ),

    # ── Fonds (layers) — une référence NUMÉROTÉE par le matériel ───────
    # `layer:get(n)` rend le fond `n`, le même numéro que le bg_slot de l'inspecteur de
    # scène (`LAYER_NUMBERS`). Le numéro se résout au build — aucun slot, aucun test de
    # `nil` — et un numéro écrit en clair hors de 0-3 est refusé. Toute la

    # famille passe par le fond : son état (`visible`, `priority`, `scroll`, `map`) est une
    # PROPRIÉTÉ, ses actions des MÉTHODES, et les tuiles de sa carte en sont aussi
    # (`layer:get(0):set_tile(...)` — plus de module `tilemap`).
    # Priorité 0 = dessiné devant (convention alignée sur bg_slot).
    "layer.get": ApiFunc(
        lua_name="layer.get", c_func="_layer_get",   # résolu par codegen
        params=[Param("n", PARAM_INT)], ret=REF_LAYER,
        doc="Le fond `n` de la scène, de 0 à 3 (le numéro de l'inspecteur de scène). Résolu à "
            "la compilation ; un numéro écrit en clair hors de 0-3 est refusé. "
            "Ex: layer:get(2):hide()",

    ),
    f"{REF_LAYER}:show": ApiFunc(
        lua_name=f"{REF_LAYER}:show", c_func="layer_show",
        params=[], self_first=True, fixed_args=(1,),
        doc="Affiche le fond. Ex: layer:get(2):show()",
    ),
    f"{REF_LAYER}:hide": ApiFunc(
        lua_name=f"{REF_LAYER}:hide", c_func="layer_show",
        params=[], self_first=True, fixed_args=(0,),
        doc="Cache le fond. Ex: layer:get(2):hide()",
    ),
    f"{REF_LAYER}:scroll_by": ApiFunc(
        lua_name=f"{REF_LAYER}:scroll_by", c_func="layer_scroll_by",
        params=[Param("dx", PARAM_INT), Param("dy", PARAM_INT)], self_first=True,
        doc="Ajoute (dx, dy) au décalage propre du fond. Ex: nuages qui dérivent seuls.",
    ),
    # tx/ty en TUILES dans la map du fond (pas en pixels monde) ; les coordonnées
    # wrappent comme le hardware.
    f"{REF_LAYER}:set_tile": ApiFunc(
        lua_name=f"{REF_LAYER}:set_tile", c_func="tilemap_set",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT), Param("tile", PARAM_INT)],
        self_first=True,
        doc="Pose la tuile d'index `tile` en (tx, ty) sur le fond. Conserve le flip et la palette de la case.",
    ),
    f"{REF_LAYER}:get_tile": ApiFunc(
        lua_name=f"{REF_LAYER}:get_tile", c_func="tilemap_get",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT)], ret="int", self_first=True,
        doc="Index de tuile actuellement en (tx, ty) sur le fond.",
    ),
    f"{REF_LAYER}:set_tile_palette": ApiFunc(
        lua_name=f"{REF_LAYER}:set_tile_palette", c_func="tilemap_set_palette",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT), Param("bank", PARAM_INT)],
        self_first=True,
        doc="Repeint la case (tx, ty) avec la banque de palette `bank` (0-15) — l'inpainting, au runtime.",
    ),
    f"{REF_LAYER}:set_tile_flip": ApiFunc(
        lua_name=f"{REF_LAYER}:set_tile_flip", c_func="tilemap_set_flip",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("h", PARAM_BOOL), Param("v", PARAM_BOOL)], self_first=True,
        doc="Retourne la case (tx, ty) horizontalement et/ou verticalement.",
    ),
    f"{REF_LAYER}:fill": ApiFunc(
        lua_name=f"{REF_LAYER}:fill", c_func="tilemap_fill",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT), Param("tile", PARAM_INT)],
        self_first=True,
        doc="Remplit un rectangle de w×h tuiles à partir de (tx, ty) avec la tuile `tile`.",
    ),

    # ── Texte ──────────────────────────────────────────────────────
    # Le texte se pose sur LE layer d'UI de la scène (Scene.text_bg) : les
    # glyphes vivent dans le charblock de ce layer. Pas de paramètre `layer`,
    # il serait mensonger. tx/ty en tuiles.
    #
    # GRAMMAIRE : position ou conteneur D'ABORD, contenu ENSUITE. Tenue par
    # toute la famille, y compris les primitives datées ci-dessous — une
    # grammaire mixte pendant l'intérim coûterait plus cher que de les aligner.
    # Le contenu finit la liste parce que c'est lui qui grandira (valeurs
    # interpolées) ; la géométrie, elle, ne bougera plus.
    #
    # L'ordre est celui du C : `zip(api.params, lua_args)` dans
    # `codegen._emit_api_call` est positionnel, donc réordonner ici réordonne
    # l'appel émis. Les signatures de `gba_engine.h` suivent, plutôt qu'une
    # permutation invisible entre Lua et C qu'il faudrait ensuite se rappeler.
    "text.draw": ApiFunc(
        lua_name="text.draw", c_func="text_draw",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("id", PARAM_STR, DOMAIN_TEXT, literal_ok=True)],
        doc='Affiche un texte du projet à (tx, ty), en tuiles — une clé de la '
            'table, ou un littéral écrit sur place (qui ne se traduira pas). '
            'Dans un littéral, `$nom` lit une locale visible, ou une globale '
            'si aucune locale ne la masque ; `$nom!3` tronque l’affichage à '
            'trois caractères (maximum `!9`). Ex: text:draw(2, 16, "PV : $hp!3")',
    ),
    "text.clear": ApiFunc(
        lua_name="text.clear", c_func="text_clear",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT)],
        doc="Efface un rectangle de w×h tuiles sur le layer d'UI.",
    ),
    "text.length": ApiFunc(
        lua_name="text.length", c_func="text_length",
        params=[Param("id", PARAM_STR, DOMAIN_TEXT)], ret="int",
        doc="Nombre de caractères d'un texte — la borne de la machine à écrire.",
    ),
    "text.set_font": ApiFunc(
        lua_name="text.set_font", c_func="text_set_font",
        params=[Param("f", PARAM_STR, DOMAIN_FONT)],
        doc='Charge une police en mémoire vidéo. Une seule à la fois. Ex: text:set_font("Pixelia")',
    ),


    # ── Window ─────────────────────────────────────────────────────
    # Une window ne dessine rien : c'est un pochoir. Elle dit, par région
    # de l'écran, qui a le droit de s'afficher. L'apparence vient de ce
    # qu'on met dedans (tilemap, sprites) — jamais de la window elle-même.
    # Une région se NOMME (comme une caméra) : "object"/"outside" sont fixes,
    # tout le reste est un WindowSlot du projet, dont le rang matériel est
    # décidé par l'allocateur (réglé le 2026-08-25, plus de "win0"/"win1"
    # ni d'index brut — cf. ARCHITECTURE.md « Windows — le pochoir »).
    # `window:get(nom)` rend la région ; son état est `visible` (cf. RUNTIME_PROPS), ses
    # réglages des méthodes.
    "window.get": ApiFunc(
        lua_name="window.get", c_func="_window_get",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_WIN_REGION)], ret=REF_WINDOW_REGION,
        doc='Une région du pochoir : un nom de WindowSlot, "object" (la fenêtre-objet) ou '
            '"outside". Résolu à la compilation. Ex: window:get("Panneau"):show()',
    ),
    f"{REF_WINDOW_REGION}:show": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:show", c_func="window_show",
        params=[], self_first=True, fixed_args=(1,),
        doc="Active la window : un WindowSlot, ou la fenêtre-objet. Ex: window:get(\"Panneau\"):show()",
    ),
    f"{REF_WINDOW_REGION}:hide": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:hide", c_func="window_show",
        params=[], self_first=True, fixed_args=(0,),
        doc="Désactive la window. Ex: window:get(\"Panneau\"):hide()",
    ),
    f"{REF_WINDOW_REGION}:set": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:set", c_func="window_set",
        params=[Param("x", PARAM_INT), Param("y", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT)], self_first=True,
        doc="Rectangle en pixels écran d'un WindowSlot. Clampé à 240×160.",
    ),
    f"{REF_WINDOW_REGION}:set_layer": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:set_layer", c_func="window_set_layer",
        params=[Param("bg", PARAM_INT), Param("on", PARAM_BOOL)], self_first=True,
        doc="Autorise ou non le fond `bg` dans la région (un WindowSlot, la fenêtre-objet ou l'extérieur).",
    ),
    f"{REF_WINDOW_REGION}:get_layer": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:get_layer", c_func="window_get_layer",
        params=[Param("bg", PARAM_INT)], ret="int", self_first=True,
        doc="1 si le fond `bg` est autorisé dans la région, 0 sinon.",
    ),
    f"{REF_WINDOW_REGION}:set_obj": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:set_obj", c_func="window_set_obj",
        params=[Param("on", PARAM_BOOL)], self_first=True,
        doc="Autorise ou non les sprites dans la région.",
    ),
    f"{REF_WINDOW_REGION}:set_blend": ApiFunc(
        lua_name=f"{REF_WINDOW_REGION}:set_blend", c_func="window_set_blend",
        params=[Param("on", PARAM_BOOL)], self_first=True,
        doc="Autorise ou non le blending dans la région. Assombrir le monde SAUF un panneau = blending activé dans la région 3, coupé dans la 0.",
    ),

    # ── Blend ──────────────────────────────────────────────────────
    # Deux jeux de cibles : le dessus (side 0, ce qui est mélangé) et le
    # dessous (side 1, ce avec quoi — situé derrière selon les priorités).
    # window.set_blend() décide ensuite des RÉGIONS où tout ceci s'applique.
    # ── Palettes au runtime ────────────────────────────────────────
    # Remplacer les seize couleurs d'une banque matérielle. C'est l'ÉCHANGE, pas
    # le cycle : faire tourner les couleurs d'une palette a été écarté (une lave
    # dessinée puis exportée en planche a des index différents d'une image à
    # l'autre — elle emprunte le chemin ordinaire des fonds animés).
    #
    # Deux fonctions et non un paramètre de cible : les deux pools sont
    # PHYSIQUEMENT distincts sur GBA (PAL_BG_RAM / PAL_OBJ_RAM), la scène les
    # sélectionne déjà séparément, et une cible en argument laisserait croire
    # qu'une même banque existe des deux côtés.
    "palette.set_bg": ApiFunc(
        lua_name="palette.set_bg", c_func="palette_set_bg",
        params=[Param("bank", PARAM_INT), Param("p", PARAM_STR, DOMAIN_PALETTE)],
        doc='Remplace les couleurs de la banque de FOND `bank` (0-15). '
            'Ex: palette:set_bg(0, "Nuit")',
    ),
    "palette.set_obj": ApiFunc(
        lua_name="palette.set_obj", c_func="palette_set_obj",
        params=[Param("bank", PARAM_INT), Param("p", PARAM_STR, DOMAIN_PALETTE)],
        doc='Remplace les couleurs de la banque de SPRITES `bank` (0-15). '
            'Ex: palette:set_obj(1, "Nuit")',
    ),

    # ── Sauvegarde (SRAM) ──────────────────────────────────────────
    # save.write/save.load écrivent ou relisent TOUTES les variables globales
    # MARQUÉES persistantes dans l'éditeur. Aucun nom de variable en argument :
    # ce qui est sauvé est une propriété du projet, pas de l'appel — sinon deux
    # endroits du jeu pourraient sauver deux ensembles différents et la
    # dernière écriture gagnerait en silence. save.read, plus bas, ne relève
    # pas de cette règle : elle ne touche à AUCUNE globale de la partie en
    # cours, donc pas de second ensemble en jeu à confondre avec le premier.
    #
    # L'écriture est toujours explicite : le moment où l'on peut sauver est une
    # règle de game design, pas quelque chose que le moteur décide.
    "save.write": ApiFunc(
        lua_name="save.write", c_func="save_write",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Écrit les variables persistantes dans l'emplacement `slot` "
            "(0 = le premier). Rend 0 si l'emplacement n'existe pas.",
    ),
    "save.load": ApiFunc(
        lua_name="save.load", c_func="save_read",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Relit l'emplacement `slot` et REMPLACE TOUTES les variables "
            "persistantes de la partie en cours. Rend 0 si l'emplacement est "
            "vide ou illisible — les variables ne sont alors PAS touchées. "
            "Pour lire une seule valeur sans charger la partie, cf. save.read.",
    ),
    # Une lecture SANS effet de bord : contrairement à save.load, elle ne
    # touche à aucune globale de la partie en cours. C'est ce qui manquait
    # pour peindre un écran de sélection de partie (chapitre, temps de jeu,
    # nom) sans écraser une partie déjà en cours pour aller regarder les
    # autres emplacements (ROADMAP v0.22). Même nom que `global_read` en C,
    # pour le même sens : rendre une valeur par référence, rien d'autre.
    "save.read": ApiFunc(
        lua_name="save.read", c_func="_save_read",   # résolu par codegen
        params=[Param("slot", PARAM_INT), Param("name", PARAM_STR, DOMAIN_GLOBAL)],
        ret="int",
        doc="Rend la valeur de la variable persistante `name` dans "
            "l'emplacement `slot`, SANS toucher à la partie en cours. Rend son "
            "défaut si l'emplacement est vide, illisible, ou si le fichier ne "
            "contient pas cette variable (jeu plus récent que la sauvegarde). "
            "`name` doit être une variable cochée « persist ». "
            "Ex: save:read(0, \"chapitre\")",
    ),
    "save.exists": ApiFunc(
        lua_name="save.exists", c_func="save_exists",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Vrai si l'emplacement `slot` contient une sauvegarde relisible. "
            "De quoi griser une entrée « Continuer ».",
    ),
    "save.erase": ApiFunc(
        lua_name="save.erase", c_func="save_erase",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Vide l'emplacement `slot` : save.exists y répond faux ensuite.",
    ),

    # blend.mode (int 0-3) : cf. RUNTIME_PROPS — l'état du mélange est une
    # propriété. set_layer/set_obj/set_alpha/set_fade restent des actions.
    "blend.set_layer": ApiFunc(
        lua_name="blend.set_layer", c_func="blend_set_layer",
        params=[Param("side", PARAM_STR, DOMAIN_BLEND_SIDE), Param("bg", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) le layer de fond `bg` comme cible du mélange, côté \"top\" (la source) ou \"bottom\" (ce sur quoi elle se mélange).",
    ),
    "blend.set_obj": ApiFunc(
        lua_name="blend.set_obj", c_func="blend_set_obj",
        params=[Param("side", PARAM_STR, DOMAIN_BLEND_SIDE), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) les sprites comme cible du mélange, côté \"top\" ou \"bottom\".",
    ),
    "blend.set_backdrop": ApiFunc(
        lua_name="blend.set_backdrop", c_func="blend_set_backdrop",
        params=[Param("side", PARAM_STR, DOMAIN_BLEND_SIDE), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) la couleur de fond de la scène comme cible. Souvent le dessous manquant quand rien n'est dessiné derrière.",
    ),
    "blend.set_alpha": ApiFunc(
        lua_name="blend.set_alpha", c_func="blend_set_alpha",
        params=[Param("eva", PARAM_INT), Param("evb", PARAM_INT)],
        doc="Dosage du mode 1, en seizièmes (0-16) : eva pour le dessus, evb pour le dessous. Ex: blend:set_alpha(8, 8) = moitié-moitié.",
    ),
    "blend.set_fade": ApiFunc(
        lua_name="blend.set_fade", c_func="blend_set_fade",
        params=[Param("evy", PARAM_INT)],
        doc="Intensité des modes 2 et 3, en seizièmes (0 = rien, 16 = blanc ou noir complet). Un fondu = incrémenter evy frame après frame.",
    ),

}

# ─── Propriétés (RUNTIME_PROPS) ────────────────────────────────────
# L'autre versant de l'API : ce qui est un ÉTAT d'objet se lit/s'écrit par accès
# pointé (`self.position`, `camera.bound`) au lieu d'un appel get/set. La
# frontière est celle de la grammaire (ROADMAP v0.7.4) :
#   - position, vélocité, rotation, échelle d'un actor → self.*
#   - position et zone scrollable de la caméra → camera.*
#   - taille du monde de la scène → scene.size (lecture seule, .w/.h)
# Les propriétés d'actor s'accèdent sur n'importe quel Actor* nommé (self,
# other, ou une variable d'actor) — c'est `expr_types.resolve_prop` qui le gère.
#
# Une propriété composite (PARAM_VEC2 / PARAM_RECT) est une valeur IMMUABLE :
# `self.position.x` se lit, `self.position = vec2(x, y)` s'écrit, mais
# `self.position.x = 5` est refusé par le checker.

RUNTIME_PROPS: dict[str, ApiProp] = {

    # ── Actor — transform ──────────────────────────────────────────
    "actor.position": ApiProp(
        lua_name="actor.position", c_getter="actor_get_position",
        c_setter="actor_set_position", ptype=PARAM_VEC2, self_first=True,
        doc="Position monde de l'actor (un vec2, .x/.y), en PIXELS entiers — "
            "toujours, même sur un actor qui accumule du sous-pixel via "
            "self:apply_velocity(). self.position = vec2(x, y) la téléporte "
            "instantanément et efface le sous-pixel accumulé.",
    ),
    "actor.rotation": ApiProp(
        lua_name="actor.rotation", c_getter="actor_get_rotation",
        c_setter="actor_set_rotation", ptype=PARAM_INT, self_first=True,
        doc='Rotation MONDE de cet actor en degrés (0-359), héritée par son sprite. '
            "Se lit et s'écrit toujours ; ne s'AFFICHE que si le SpriteComponent a "
            '"Affine transform" coché (il réserve un des 32 slots affines du GBA). '
            "Le sprite a sa propre rotation locale : self.sprite_rotation (somme des "
            "deux à l'écran).",
    ),
    "actor.scale": ApiProp(
        lua_name="actor.scale", c_getter="actor_get_scale",
        c_setter="actor_set_scale", ptype=PARAM_VEC2, self_first=True,
        doc="Échelle MONDE de cet actor en pourcent (100 = normal, 50 = moitié) — un vec2 "
            "(.x, .y), héritée par son sprite. Se lit et s'écrit toujours ; ne s'AFFICHE "
            "que si le SpriteComponent a \"Affine transform\" coché. Le sprite a son "
            "propre scale local : self.sprite_scale (produit des deux à l'écran).",
    ),

    # ── Actor — transform LOCAL du sprite ─────────────────────────
    # Le sprite n'a pas de position monde : sa position, son échelle et sa rotation
    # sont RELATIVES à son actor, dans le repère local de l'actor (l'offset tourne/
    # scale avec lui). Ne s'affichent que si le SpriteComponent a "Affine transform"
    # coché — sans slot de matrice, aucune de ces valeurs n'atteint l'écran.
    "actor.sprite_rotation": ApiProp(
        lua_name="actor.sprite_rotation", c_getter="actor_get_sprite_rotation",
        c_setter="actor_set_sprite_rotation", ptype=PARAM_INT, self_first=True,
        doc="Rotation LOCAL du sprite en degrés (0-359), composée PAR-DESSUS la rotation "
            "monde de l'actor (la somme des deux s'affiche). Ne s'affiche que si ce "
            "sprite a \"Affine transform\" coché.",
    ),
    "actor.sprite_scale": ApiProp(
        lua_name="actor.sprite_scale", c_getter="actor_get_sprite_scale",
        c_setter="actor_set_sprite_scale", ptype=PARAM_VEC2, self_first=True,
        doc="Échelle LOCALE du sprite en pourcent (100 = normal) — un vec2 (.x, .y), "
            "MULTIPLIÉE par le scale monde de l'actor. Ne s'affiche que si ce sprite a "
            "\"Affine transform\" coché.",
    ),
    "actor.sprite_offset": ApiProp(
        lua_name="actor.sprite_offset", c_getter="actor_get_sprite_offset",
        c_setter="actor_set_sprite_offset", ptype=PARAM_VEC2, self_first=True,
        doc="Offset du sprite par rapport à son actor, en pixels, dans le repère LOCAL de "
            "l'actor : il tourne et scale avec lui (hérarchie parent→enfant). Le sprite "
            "n'a pas de position monde — la position monde, c'est self.position. "
            "Ne s'applique que si ce sprite a \"Affine transform\" coché.",
    ),

    # ── Actor — physique ───────────────────────────────────────────
    # ROADMAP v0.19 (2026-08-20) : unité Q8 (256 = 1 px), pas des pixels — la
    # rupture assumée qui rend le sous-pixel utilisable sans un second nom
    # (self.velocity_q8) à côté de self.velocity. 128 = un demi-pixel/frame,
    # 256 = un pixel/frame, 384 = un pixel et demi/frame. self.position, elle,
    # reste en pixels (décision verrouillée, inchangée).
    "actor.velocity": ApiProp(
        lua_name="actor.velocity", c_getter="actor_get_velocity",
        c_setter="actor_set_velocity", ptype=PARAM_VEC2, self_first=True,
        doc="Vélocité de l'actor (un vec2, .x/.y), en Q8 : 256 = 1 pixel/frame, "
            "128 = un demi-pixel/frame. Ne déplace pas seule — self:apply_velocity() "
            "l'ajoute à la position, en conservant le sous-pixel d'une frame à l'autre "
            "(self.position, elle, ne rend que des pixels entiers).",
    ),

    # ── Actor — état général ───────────────────────────────────────
    # `visible` et `active` se LISENT ici ; ils s'écrivent par les verbes
    # `:show()` / `:hide()` / `:activate()` / `:deactivate()` — une seule porte
    # d'écriture (ROADMAP v0.16, critère 3).
    "actor.visible": ApiProp(
        lua_name="actor.visible", c_getter="actor_get_visible",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Le sprite est-il affiché ? Lecture seule : self:show() / self:hide() "
            "l'écrivent.",
    ),
    "actor.active": ApiProp(
        lua_name="actor.active", c_getter="actor_get_active",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="L'actor est-il actif (update, collisions et rendu en marche) ? "
            "Lecture seule : self:activate() / self:deactivate() l'écrivent.",
    ),
    # Se compare par le NOM de l'acteur ou du prefab — sans quoi la propriété
    # rendait un entier opaque qu'aucune écriture Lua ne permettait de nommer :
    # « utile pour identifier other », disait sa doc, sans dire comment.
    "actor.tag": ApiProp(
        lua_name="actor.tag", c_getter="actor_get_tag", ptype=PARAM_INT,
        self_first=True, read_only=True, domain=DOMAIN_TAG,
        doc='Identité de cet actor (lecture seule) : le nom de son acteur de '
            'scène ou de son prefab. C\'est ce qui permet de reconnaître qui '
            'l\'on touche. Ex: if other.tag == "Ball" then self:destroy() end',
    ),

    # ── Actor — animation ──────────────────────────────────────────
    # Lecture seule, comparable par son nom — symétrique de self:play_anim qui
    # l'écrit par son nom. Pas de self.anim = "Walk" : changer d'état est un
    # GESTE (il remet frame/timer à zéro), pas une propriété qu'on assigne.
    "actor.anim": ApiProp(
        lua_name="actor.anim", c_getter="actor_get_anim", ptype=PARAM_INT,
        self_first=True, read_only=True, domain=DOMAIN_ANIM,
        doc='État d\'animation courant (lecture seule), comparable par son nom. '
            'Ex: if self.anim == "Walk" then ... end. Pour le changer, '
            'self:play_anim(name).',
    ),
    "actor.active_sprite": ApiProp(
        lua_name="actor.active_sprite", c_getter="actor_get_appearance", ptype=PARAM_INT,
        self_first=True, read_only=True, domain=DOMAIN_SPRITE_ID,
        doc="Id du composant sprite actif (lecture seule), comparable par son nom. "
            "Ex: if self.active_sprite == \"blesse\" then ... end. Pour le changer, "
            "self:activate_sprite(id).",
    ),
    "actor.anim_speed": ApiProp(
        lua_name="actor.anim_speed", c_getter="actor_get_anim_speed",
        c_setter="actor_set_anim_speed", ptype=PARAM_INT, self_first=True,
        doc="Surcharge la vitesse (ticks GBA entre deux frames) de "
            "l'animation en cours. 0 = la vitesse réglée pour cet état dans "
            "le Sprite Editor, qui reste la source de vérité. Ne se remet "
            "pas à 0 tout seul : un effet temporaire (temps ralenti) se "
            "referme explicitement par le script qui l'a ouvert.",
    ),
    "actor.anim_length": ApiProp(
        lua_name="actor.anim_length", c_getter="actor_get_anim_length",
        ptype=PARAM_INT, self_first=True, read_only=True,
        doc="Nombre de frames de la direction actuellement jouée de l'état "
            "d'animation courant. Lecture seule.",
    ),
    "actor.anim_loop": ApiProp(
        lua_name="actor.anim_loop", c_getter="actor_get_anim_loop",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Vrai si l'état d'animation courant boucle (réglage « Loop » du "
            "Sprite Editor pour cet état). Lecture seule.",
    ),
    "actor.anim_finished": ApiProp(
        lua_name="actor.anim_finished", c_getter="actor_get_anim_finished",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Vrai si l'état d'animation courant NE boucle PAS et a atteint "
            "sa dernière frame (self.anim_length). Reste vrai tant qu'on ne "
            "change pas d'état (self:play_anim) — comme self.grounded reste "
            "vrai tant qu'on ne quitte pas le sol. Toujours faux pour un "
            "état qui boucle. Lecture seule.",
    ),
    "actor.frame_w": ApiProp(
        lua_name="actor.frame_w", c_getter="actor_get_frame_w",
        ptype=PARAM_INT, self_first=True, read_only=True,
        doc="Largeur d'une frame du sprite, en pixels (réglage du Sprite "
            "Editor). Lecture seule — la taille de frame est fixée au build.",
    ),
    "actor.frame_h": ApiProp(
        lua_name="actor.frame_h", c_getter="actor_get_frame_h",
        ptype=PARAM_INT, self_first=True, read_only=True,
        doc="Hauteur d'une frame du sprite, en pixels (réglage du Sprite "
            "Editor). Lecture seule — la taille de frame est fixée au build.",
    ),
    "actor.frame": ApiProp(
        lua_name="actor.frame", c_getter="actor_get_frame",
        c_setter="actor_set_frame", ptype=PARAM_INT, self_first=True,
        doc="Frame courante de l'animation. self.frame = 0 la remet au début.",
    ),
    "actor.flip_h": ApiProp(
        lua_name="actor.flip_h", c_getter="actor_get_flip_h",
        c_setter="actor_set_flip_h", ptype=PARAM_BOOL, self_first=True,
        doc="Sprite retourné horizontalement (true) ou normal (false). "
            "self.flip_h = self.direction.x < 0 suit le regard.",
    ),
    "actor.flip_v": ApiProp(
        lua_name="actor.flip_v", c_getter="actor_get_flip_v",
        c_setter="actor_set_flip_v", ptype=PARAM_BOOL, self_first=True,
        doc="Sprite retourné verticalement (true) ou normal (false).",
    ),
    "actor.pal": ApiProp(
        lua_name="actor.pal", c_getter="actor_get_pal",
        c_setter="actor_set_pal", ptype=PARAM_INT, self_first=True,
        doc="Palette bank OAM courante (0-15). Flash de dégâts, invincibilité…",
    ),
    "actor.obj_mode": ApiProp(
        lua_name="actor.obj_mode", c_getter="actor_get_obj_mode",
        c_setter="actor_set_obj_mode", ptype=PARAM_INT, self_first=True,
        domain=DOMAIN_OBJ_MODE,
        doc='Mode OAM, par son nom : "normal", "blend" (semi-transparent, '
            'réservé au mélange) ou "window" (masque : découpe la '
            'fenêtre-objet). Ex: self.obj_mode = "window"',
    ),
    "actor.priority": ApiProp(
        lua_name="actor.priority", c_getter="actor_get_priority",
        c_setter="actor_set_priority", ptype=PARAM_INT, self_first=True,
        doc="Ordre d'affichage face aux BG layers (0-3) : 0 = devant tous "
            "les backgrounds, 3 = derrière tous. Même registre OAM que "
            "self.pal/self.obj_mode.",
    ),

    # ── Actor — direction ──────────────────────────────────────────
    # UN état, deux écritures — et c'est la même propriété. Le vecteur sert au
    # CALCUL (`self.direction.x < 0` suit le regard), le nom de boussole sert à
    # POSER une direction sans avoir à se rappeler quel axe monte. Les deux
    # atteignent `dir_x`/`dir_y` ; seule la porte C diffère (cf. ApiProp).
    "actor.direction": ApiProp(
        lua_name="actor.direction", c_getter="actor_get_direction",
        c_setter="actor_set_direction", ptype=PARAM_VEC2, self_first=True,
        domain=DOMAIN_DIRECTION,
        c_getter_named="actor_get_dir", c_setter_named="actor_set_dir",
        doc='Direction d\'animation discrète. Se lit en vec2 dont chaque '
            'composante vaut -1, 0 ou 1 (.x = gauche/droite, .y = haut/bas), et '
            's\'écrit des deux façons : self.direction = vec2(1, -1) ou '
            'self.direction = "north_east". Se compare aussi par son nom : '
            'if self.direction == "west". Écrire le vecteur ENTIER — jamais '
            'self.direction.x seul.',
    ),
    "actor.auto_dir": ApiProp(
        lua_name="actor.auto_dir", c_getter="actor_get_auto_dir",
        c_setter="actor_set_auto_dir", ptype=PARAM_BOOL, self_first=True,
        doc="Calcule (true) ou non (false) la direction automatiquement depuis "
            "la vélocité. À false, self.direction est ce que le script en fait.",
    ),

    # ── Actor — collision ──────────────────────────────────────────
    "actor.grounded": ApiProp(
        lua_name="actor.grounded", c_getter="actor_on_ground", ptype=PARAM_BOOL,
        self_first=True, read_only=True,
        doc="Vrai si une box solide reposait sur le sol à la fin de la frame "
            "précédente — pentes comprises. Demande une carte de collision dans "
            "la scène. Lecture seule.",
    ),
    "actor.box_count": ApiProp(
        lua_name="actor.box_count", c_getter="actor_get_box_count", ptype=PARAM_INT,
        self_first=True, read_only=True,
        doc="Nombre de boîtes de collision de cet actor, actives ou non (fixé au "
            "build, lecture seule). Les boîtes elles-mêmes se demandent par leur "
            "tag : self:collision_box(\"hitbox\").",
    ),

    # ── La boîte de collision (référence `collision_box`) ──────────
    # Clés `collision_box.<champ>` : le récepteur est une VARIABLE qui tient la
    # référence (`hb.solid`), pas un module. `expr_types.resolve_prop` les
    # résout d'après le type que porte le `local`.
    "collision_box.tag": ApiProp(
        lua_name="collision_box.tag", c_getter="collision_box_get_tag",
        ptype=PARAM_INT, self_first=True, read_only=True, domain=DOMAIN_BOX_TAG,
        doc='Le tag de cette boîte — la clé qui l\'a désignée. Lecture seule ; '
            'sert à comparer : hb.tag == "hitbox".',
    ),
    "collision_box.active": ApiProp(
        lua_name="collision_box.active", c_getter="collision_box_get_active",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="La boîte est-elle en jeu ? Inactive, elle ne heurte ni la carte ni les "
            "autres boîtes. Lecture seule : hb:activate() / hb:deactivate() "
            "l'écrivent. C'est la case « Active » de l'inspecteur, qui n'en "
            "fixe que l'état de départ.",
    ),
    # ── Une LISTE ────────────────────────────────────────────────
    f"{REF_LIST}.count": ApiProp(
        lua_name=f"{REF_LIST}.count", c_getter="ui_list_count",
        c_setter="ui_list_set_count", ptype=PARAM_INT, self_first=True,
        doc="Combien d'items cette liste parcourt. Vaut le nombre de rangées authorées "
            "par défaut — un menu statique navigue donc sans rien poser. À écrire quand "
            "les items dépassent les rangées visibles (un inventaire qui défile) : "
            "#mon_tableau, le nombre de lignes d'une table de données, ou un compte "
            "tenu à la main. Ex: menu.count = #sac",
    ),
    f"{REF_LIST}.index": ApiProp(
        lua_name=f"{REF_LIST}.index", c_getter="ui_list_index",
        c_setter="ui_list_set_index", ptype=PARAM_INT, self_first=True,
        doc="L'item sélectionné, à partir de 1 (0 si la liste est vide). Écrire place "
            "le curseur sur cet item ; la fenêtre se recale pour qu'il soit visible. "
            "Ex: menu.index = 2",
    ),
    f"{REF_LIST}.first": ApiProp(
        lua_name=f"{REF_LIST}.first", c_getter="ui_list_first",
        ptype=PARAM_INT, self_first=True, read_only=True,
        doc="Le premier item AFFICHÉ, à partir de 1 — la position de la fenêtre. "
            "L'item de la rangée r est first + r - 1. Lecture seule.",
    ),
    f"{REF_LIST}.active": ApiProp(
        lua_name=f"{REF_LIST}.active", c_getter="ui_list_active",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Cette liste prend-elle la croix directionnelle ? C'est la SÉLECTION, pas "
            "l'affichage. Lecture seule : menu:activate() / menu:deactivate() l'écrivent.",
    ),
    # ── Une IMAGE ────────────────────────────────────────────────
    # L'état se pose par son NOM dans le sprite de CETTE image (`IMGST_{image}_{état}`) :
    # deux images de sprites différents citent légitimement des états différents. Le
    # checker et le codegen lisent donc l'image sur le RÉCEPTEUR — un littéral
    # `interface:get("Cœur")` ou un `local` qui en tient un.
    f"{REF_IMAGE}.state": ApiProp(
        lua_name=f"{REF_IMAGE}.state", c_getter="ui_image_state",
        c_setter="ui_image_set_state", ptype=PARAM_INT, self_first=True,
        domain=DOMAIN_IMAGE_STATE,
        doc='L\'état affiché, par son nom dans le sprite de l\'image : heart.state = "vide", '
            'if heart.state == "vide". L\'image doit être connue au build.',
    ),
    f"{REF_IMAGE}.offset": ApiProp(
        lua_name=f"{REF_IMAGE}.offset", c_getter="ui_image_offset",
        c_setter="ui_image_set_offset", ptype=PARAM_VEC2, self_first=True,
        doc="Le décalage de l'image, en pixels, RELATIVEMENT à la position posée dans le "
            "canvas — (0, 0) l'y ramène. En cible BG l'origine se cale sur la grille de "
            "8 px ; pour un déplacement au pixel, l'ancrage du conteneur racine doit "
            "donner la cible OBJ. Ex: cursor.offset = vec2(0, 16 * menu.index)",
    ),
    # ── Une ZONE DE TEXTE ────────────────────────────────────────
    f"{REF_TEXT_REGION}.reading": ApiProp(
        lua_name=f"{REF_TEXT_REGION}.reading", c_getter="text_reading",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Vrai tant que le texte s'écrit dans cette zone (machine à écrire). "
            "Lecture seule. Ex: if not box.reading then scene.goto(\"SUITE\") end",
    ),
    # ── Un FOND (layer) ──────────────────────────────────────────
    # `visible` se lit ici ; `:show()` / `:hide()` l'écrivent.
    f"{REF_LAYER}.visible": ApiProp(
        lua_name=f"{REF_LAYER}.visible", c_getter="layer_is_visible",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Le fond est-il affiché ? Lecture seule : :show() / :hide() l'écrivent.",
    ),
    f"{REF_LAYER}.priority": ApiProp(
        lua_name=f"{REF_LAYER}.priority", c_getter="layer_get_priority",
        c_setter="layer_set_priority", ptype=PARAM_INT, self_first=True,
        doc="Ordre d'affichage du fond (0 = devant, 3 = derrière), sprites compris. "
            "Ex: layer:get(1).priority = 0",
    ),
    # Le moteur tient le décalage en deux entiers ; `Vec2` n'existe que côté scripts : la
    # conversion vit dans la façade `runtime_api_inline.h`.
    f"{REF_LAYER}.scroll": ApiProp(
        lua_name=f"{REF_LAYER}.scroll", c_getter="layer_get_scroll",
        c_setter="layer_set_scroll_to", ptype=PARAM_VEC2, self_first=True,
        doc="Décalage PROPRE du fond, en pixels, ajouté au scroll caméra (un vec2). "
            "Ex: layer:get(0).scroll = vec2(0, 8)",
    ),
    f"{REF_LAYER}.scroll_speed": ApiProp(
        lua_name=f"{REF_LAYER}.scroll_speed", c_getter="layer_get_scroll_speed",
        c_setter="layer_set_scroll_speed", ptype=PARAM_INT, self_first=True,
        doc="Vitesse de parallax du fond, en pourcent de celle de la caméra (100 = le fond suit "
            "la caméra, 50 = il défile deux fois plus lentement, 0 = il reste fixe). Le réglage "
            "« Scroll speed » de l'inspecteur n'en fixe que la valeur de départ. "
            "Ex: layer:get(1).scroll_speed = 50",
    ),
    f"{REF_LAYER}.pal_bank": ApiProp(
        lua_name=f"{REF_LAYER}.pal_bank", c_getter="layer_get_pal_bank",
        ptype=PARAM_INT, self_first=True, read_only=True,
        doc="Banque de palette de BASE du fond (0-15) : celle que sa carte cite, y compris quand "
            "l'inspecteur laisse « palette propre » (le build l'a alors placée). Lecture seule : "
            "la banque est gravée dans chaque case de la carte. Sert à recolorer le fond : "
            "palette:set_bg(layer:get(1).pal_bank, \"Nuit\"). Un fond aux tuiles peintes de "
            "banques différentes rend sa banque de base, pas toutes celles en usage.",
    ),
    f"{REF_LAYER}.map": ApiProp(
        lua_name=f"{REF_LAYER}.map", c_getter="layer_get_map",
        c_setter="layer_set_map", ptype=PARAM_INT, self_first=True,
        doc="Avancé — le screenblock (0-31) affiché par le fond. Écrire bascule d'un coup "
            "sur une carte préparée, sans tearing.",
    ),
    # ── Une REGION de window ─────────────────────────────────────
    f"{REF_WINDOW_REGION}.visible": ApiProp(
        lua_name=f"{REF_WINDOW_REGION}.visible", c_getter="window_is_visible",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="La window est-elle active ? Lecture seule : :show() / :hide() l'écrivent.",
    ),
    f"{REF_UI_ELEMENT}.visible": ApiProp(
        lua_name=f"{REF_UI_ELEMENT}.visible", c_getter="ui_element_is_visible",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="L'élément est-il affiché ? Tient compte de ses parents : un enfant "
            "d'un conteneur caché ne l'est pas. Lecture seule : :show() / :hide() "
            "l'écrivent.",
    ),
    "collision_box.is_grounded": ApiProp(
        lua_name="collision_box.is_grounded", c_getter="collision_box_get_grounded",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Cette boîte reposait-elle sur le sol à la fin de la frame précédente "
            "(pentes comprises) ? Vaut toujours faux pour une boîte non solide : "
            "la carte de collision l'ignore. `self.grounded` en est le OU sur "
            "toutes les boîtes de l'acteur. Lecture seule."),
    "collision_box.solid": ApiProp(
        lua_name="collision_box.solid", c_getter="collision_box_get_solid",
        c_setter="collision_box_set_solid", ptype=PARAM_BOOL, self_first=True,
        doc="Arrêtée par la carte de collision (true) ou simple déclencheur "
            "(false). Ex: hb.solid = false pour traverser les murs.",
    ),
    "collision_box.offset": ApiProp(
        lua_name="collision_box.offset", c_getter="collision_box_get_offset",
        c_setter="collision_box_set_offset", ptype=PARAM_VEC2, self_first=True,
        doc="Décalage de la boîte par rapport au pivot du sprite, en pixels "
            "(−128 à 127, borné). Valeur immuable : hb.offset = vec2(8, -4).",
    ),
    "collision_box.size": ApiProp(
        lua_name="collision_box.size", c_getter="collision_box_get_size",
        c_setter="collision_box_set_size", ptype=PARAM_VEC2, self_first=True,
        doc="Largeur et hauteur de la boîte, en pixels (0 à 255, borné). Une "
            "hitbox qui grandit : hb.size = vec2(12 + t, 8).",
    ),
    "collision_box.bounds": ApiProp(
        lua_name="collision_box.bounds", c_getter="collision_box_get_bounds",
        ptype=PARAM_RECT, self_first=True, read_only=True,
        doc="Le rectangle de la boîte en coordonnées MONDE (position de l'actor + "
            "décalage + taille), en pixels. Lecture seule : c'est ce que la "
            "détection compare, et ce qu'on passe à collision_box.get_tile.",
    ),

    # ── Actor — réglages d'inspecteur fixés au build (lecture seule) ─
    # Ce que l'inspecteur règle mais que le runtime ne SAIT pas changer : le C
    # émis diffère selon la valeur, ou elle réserve du matériel. Ils se lisent
    # pour qu'un script s'adapte, sans dupliquer la valeur dans une variable.
    "actor.screen_space": ApiProp(
        lua_name="actor.screen_space", c_getter="actor_get_screen_space",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Vrai si la position de cet actor est en pixels d'ÉCRAN (interface en "
            "sprite : la caméra ne la déplace pas) plutôt qu'en pixels du monde. "
            "Lecture seule — fixé à l'éditeur (case « Screen space »).",
    ),
    "actor.affine": ApiProp(
        lua_name="actor.affine", c_getter="actor_get_affine",
        ptype=PARAM_BOOL, self_first=True, read_only=True,
        doc="Vrai si le sprite de cet actor a un slot de matrice affine (case "
            "« Affine transform » du SpriteComponent) — donc si sa rotation et "
            "son échelle se VOIENT. Lecture seule : le slot est réservé au build.",
    ),

    # ── Caméra ─────────────────────────────────────────────────────
    "camera.position": ApiProp(
        lua_name="camera.position", c_getter="camera_get_position",
        c_setter="camera_set_position", ptype=PARAM_VEC2,
        doc="Position courante de la caméra (un vec2, .x/.y). "
            "camera.position = vec2(x, y) la place exactement.",
    ),
    "camera.margin": ApiProp(
        lua_name="camera.margin", c_getter="camera_get_margin",
        c_setter="camera_set_margin", ptype=PARAM_VEC2,
        doc="Zone morte du suivi de la caméra active, en pixels (un vec2 : .x = horizontale, "
            ".y = verticale) : la cible peut s'éloigner de cette distance du bord de l'écran avant "
            "que la caméra ne bouge. 0 = recentrage permanent. Le réglage « Margin » de "
            "l'inspecteur n'en fixe que la valeur à l'activation. Ex: camera.margin = vec2(60, 30)",
    ),
    "camera.frame": ApiProp(
        lua_name="camera.frame", c_getter="camera_get_frame",
        c_setter="camera_set_frame", ptype=PARAM_VEC2,
        doc="Taille du rendu à l'écran, en pixels (un vec2 : .x = largeur, .y = hauteur ; 240×160 "
            "= plein écran). Plus petit, la caméra ne rend que dans ce cadre, ancré en haut à "
            "gauche. Borné à l'écran. Ex: camera.frame = vec2(240, 120)",
    ),
    "camera.name": ApiProp(
        lua_name="camera.name", c_getter="camera_get_active", ptype=PARAM_INT,
        read_only=True, domain=DOMAIN_CAMERA,
        doc='Nom de la caméra active (lecture seule), comparable par son nom. '
            'Ex: if camera.name == "Boss" then ... end. Pour en changer, camera:switch(nom).',
    ),
    "camera.bound": ApiProp(
        lua_name="camera.bound", c_getter="camera_get_bounds",
        c_setter="camera_set_bounds", ptype=PARAM_RECT,
        doc="Zone scrollable du monde, un rect (.x/.y = origine, .w/.h = taille en px ; "
            "0 = axe illimité). camera.bound = rect(x, y, w, h) débloque une zone au runtime.",
    ),

    # ── Blend ──────────────────────────────────────────────────────
    "blend.mode": ApiProp(
        lua_name="blend.mode", c_getter="blend_get_mode",
        c_setter="blend_set_mode", ptype=PARAM_INT,
        domain=DOMAIN_BLEND_MODE,
        doc='Mode de mélange courant, par son nom : "none", "alpha" '
            '(dessus×EVA + dessous×EVB), "brighten" (vers le blanc) ou '
            '"darken" (vers le noir). Ex: blend.mode = "alpha"',
    ),

    # ── Scène ──────────────────────────────────────────────────────
    "scene.frame": ApiProp(
        lua_name="scene.frame", c_getter="scene_frame",
        ptype=PARAM_INT, read_only=True,
        doc="Compteur de frames global depuis le début de la scène. Lecture "
            "seule — utile pour des timers sans variable locale.",
    ),
    "scene.scroll_h": ApiProp(
        lua_name="scene.scroll_h", c_getter="", ptype=PARAM_BOOL, read_only=True,
        getter_expr="g_scene_scroll_h",
        doc="La scène défile-t-elle horizontalement (case « Scroll H » de l'inspecteur de scène) ? "
            "Lecture seule — le suivi de la caméra en a fait un choix de build.",
    ),
    "scene.scroll_v": ApiProp(
        lua_name="scene.scroll_v", c_getter="", ptype=PARAM_BOOL, read_only=True,
        getter_expr="g_scene_scroll_v",
        doc="La scène défile-t-elle verticalement (case « Scroll V » de l'inspecteur de scène) ? "
            "Lecture seule — le suivi de la caméra en a fait un choix de build.",
    ),
    "scene.collision_layer": ApiProp(
        lua_name="scene.collision_layer", c_getter="", ptype=PARAM_INT, read_only=True,
        getter_expr="g_scene_collision_layer",
        doc="Numéro du fond (0-3) qui porte la carte de collision de la scène — le bouton radio "
            "« collision layer » de l'inspecteur. Lecture seule : la carte est choisie au build. "
            "Ex: layer:get(scene.collision_layer):hide()",
    ),
    "scene.size": ApiProp(
        lua_name="scene.size", c_getter="", ptype=PARAM_RECT, read_only=True,
        getter_expr="(Rect){0, 0, g_scene_w, g_scene_h}",
        doc="Taille du monde de la scène (un rect : .x/.y = 0, .w/.h = canvas en px). "
            "Lecture seule.",
    ),
}


# ─── API retirée ──────────────────────────────────────────────────
# Le checker laisse passer un appel inconnu : ce peut être un helper défini
# par l'utilisateur. Une fonction RETIRÉE mériterait, elle, un message de
# migration plutôt qu'un simple « inconnu ».
#
# {clé retirée: message de migration}. VIDE avant la 1.0 : tant que l'API
# bouge encore, une suppression est un RETRAIT SEC — l'ancien nom devient
# « inconnu », sans guide (ROADMAP v0.16). Le guidage de migration redevient
# un engagement le jour où la 1.0 fige l'API : c'est là qu'une entrée par
# suppression retrouvera son sens, sur une surface qu'on promet stable.

REMOVED_API: dict[str, str] = {}


# Les dix `on_button_*` sont un cas à part : ce ne sont pas des appels d'API
# mais des noms de fonction de PREMIER NIVEAU (des handlers), qui ne passent
# jamais par `REMOVED_API` (celui-ci ne couvre que les appels `récepteur:méthode`
# ou `module.fonction`). Retrait sec ailleurs, mais l'auteur a explicitement
# demandé un message ici (ROADMAP « Les inputs personnalisés », tranche
# finale, 2026-09-27) : aucun `.lua`/doc/démo du dépôt ne les utilisait déjà,
# donc un guide ne coûte rien et évite la confusion avec `input:pressed`.
REMOVED_EVENTS: dict[str, str] = {
    name: (f"L'événement '{name}' n'existe plus : écrivez "
          f"if input:pressed(\"{btn}\") then ... end dans on_update.")
    for name, btn in (
        ("on_button_a", "a"), ("on_button_b", "b"),
        ("on_button_l", "l"), ("on_button_r", "r"),
        ("on_button_start", "start"), ("on_button_select", "select"),
        ("on_button_up", "up"), ("on_button_down", "down"),
        ("on_button_left", "left"), ("on_button_right", "right"),
    )
}


# ─── Registre des événements ──────────────────────────────────────
# Source unique de vérité pour tous les events Lua/C.
# Clés par event :
#   icon    — icône affichée dans le script editor sidebar
#   stub    — template Lua inséré au clic
#   desc    — description courte (tooltip)
#   params  — liste de {name, type, description} (args Lua)
#   c_sig   — signature C générée par build.py / codegen
#
# Pour ajouter un event : une seule entrée ici suffit.

EVENT_REGISTRY: dict[str, dict] = {
    "on_start": {
        "icon": "▶",
        "icon_key": "ev_start",
        "stub": "function on_start()\n    \nend\n",
        "desc": "Appelé une fois au démarrage de la scène.",
        "params": [],
        "c_sig": "void {prefix}_on_start(Actor* self)",
    },
    "on_update": {
        "icon": "↺",
        "icon_key": "ev_update",
        "stub": "function on_update()\n    \nend\n",
        "desc": "Appelé chaque frame (60 fps). Logique principale.",
        "params": [],
        "c_sig": "void {prefix}_on_update(Actor* self)",
    },
    "on_late_update": {
        "icon": "↻",
        "icon_key": "ev_late_update",
        "stub": "function on_late_update()\n    \nend\n",
        "desc": "Appelé après physique et collisions. Idéal pour la caméra et le HUD.",
        "params": [],
        "c_sig": "void {prefix}_on_late_update(Actor* self)",
    },
    "on_collide": {
        "icon": "⬡",
        "icon_key": "ev_collide",
        "stub": "function on_collide(other, my_box, other_box)\n    \nend\n",
        "desc": "Appelé chaque frame où cet actor touche un autre.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor en contact"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_collision_enter": {
        "icon": "→",
        "icon_key": "ev_collision_enter",
        "stub": "function on_collision_enter(other, my_box, other_box)\n    \nend\n",
        "desc": "Premier frame de contact avec un autre actor.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor entrant en contact"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_tile_collide": {
        "icon": "▦",
        "icon_key": "ev_tile_collide",
        "stub": "function on_tile_collide(normal_x, normal_y)\n    \nend\n",
        "desc": "Appelé quand cet actor heurte une tile solide de la collision map.",
        "params": [
            {"name": "normal_x", "type": "int", "description": "-1/0/1 : direction horizontale du choc"},
            {"name": "normal_y", "type": "int", "description": "-1/0/1 : direction verticale du choc"},
        ],
        "c_sig": "void {prefix}_on_tile_collide(Actor* self, int normal_x, int normal_y)",
    },
    "on_collision_exit": {
        "icon": "←",
        "icon_key": "ev_collision_exit",
        "stub": "function on_collision_exit(other, my_box, other_box)\n    \nend\n",
        "desc": "Premier frame sans contact après une collision.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor qui s'est éloigné"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_destroy": {
        "icon": "✕",
        "icon_key": "ev_destroy",
        "stub": "function on_destroy()\n    \nend\n",
        "desc": "Appelé juste avant que l'actor soit désactivé par destroy().",
        "params": [],
        "c_sig": "void {prefix}_on_destroy(Actor* self)",
    },
}

# Aliases dérivés — ne plus éditer, générés depuis EVENT_REGISTRY
KNOWN_EVENTS: list[str] = list(EVENT_REGISTRY.keys())
EVENT_C_SIGNATURES: dict[str, str] = {k: v["c_sig"] for k, v in EVENT_REGISTRY.items()}


# ─── Les modules, dérivés du catalogue ────────────────────────────
# `math`, `text`, `layer`… : le préfixe d'une clé pointée. Dérivés et non
# listés, comme KNOWN_EVENTS ci-dessus — un module naît de sa première
# fonction, il n'a rien à déclarer. Sert au checker pour distinguer « ce module
# n'existe pas » de « ce module n'a pas cette fonction-là », distinction qui
# vaut surtout pour `math` : le nom est celui de Lua, le contenu non.

# `self` en est exclu : ce n'est pas un module mais un RÉCEPTEUR — ses champs
# sont des propriétés (`self.position`) et ses fonctions des méthodes, appelées
# avec deux points (`self:play_anim`). Le confondre ferait dire « le module self
# n'a pas de … » à quelqu'un qui a juste écrit un point de trop.
API_MODULES: frozenset[str] = frozenset(
    key.split(".", 1)[0] for key in (*RUNTIME_API, *RUNTIME_PROPS) if "." in key
) - {"self"}


# ─── L'appel d'un module : « : », sauf pour une bibliothèque ──────────
# Un module du moteur est un récepteur SINGLETON : son état s'écrit `module.propriété`
# (`camera.bound`, `scene.frame`), son action `module:action(…)` (`music:play("Combat")`,
# `input:pressed("A")`, `save:write(0)`, `text:draw(…)`, `layer:get(0)`), exactement comme
# `menu.index` et `menu:hide()` sur une instance. Le module et le type ne se distinguent que
# par leur durée de vie, jamais par une ponctuation à mémoriser (ROADMAP v0.16).
#
# Une seule EXCEPTION, nommée : une bibliothèque sans état ni identité runtime garde
# l'appel pointé — `math.abs(x)` —, parce que `math` n'est pas un récepteur du moteur.
# Les clés du catalogue restent `module.fonction` : seule l'ÉCRITURE change.
STATELESS_MODULES: frozenset[str] = frozenset({"math"})

# Les modules qui portent des fonctions et s'appellent donc avec « : ».
MODULE_CALLS: frozenset[str] = frozenset(
    key.split(".", 1)[0] for key in RUNTIME_API if "." in key
) - STATELESS_MODULES


def module_call_form(key: str) -> str:
    """`input.pressed` → `input:pressed` : la clé du catalogue, dans la forme que l'auteur
    ÉCRIT. Une clé qui n'est pas la fonction d'un module (`math.abs`, `self:move`,
    `sfx:stop`) se rend inchangée."""
    if key.startswith("actor:") and key in RUNTIME_API:
        return "self:" + key[len("actor:"):]         # un acteur s'écrit `self:` (ou `other:`…)
    module, dot, name = key.partition(".")
    return f"{module}:{name}" if dot and key in RUNTIME_API and module in MODULE_CALLS else key


def canonical_key(shown: str) -> str:
    """L'inverse de `module_call_form` : `input:pressed` → `input.pressed`. Un nom qui est
    déjà une clé du catalogue (`sfx:stop`, méthode d'un type) se rend inchangé — `sfx` est à
    la fois un module (`sfx:play`) et un type (`pas:stop`), et le catalogue dit lequel."""
    if shown in RUNTIME_API or shown in RUNTIME_PROPS:
        return shown
    # `self:move_to` / `self.position` : l'acteur qui exécute le script, dont le catalogue dit `actor`.
    if shown.startswith("self:") and f"actor:{shown[5:]}" in RUNTIME_API:
        return f"actor:{shown[5:]}"
    if shown.startswith("self.") and f"actor.{shown[5:]}" in RUNTIME_PROPS:
        return f"actor.{shown[5:]}"
    module, colon, name = shown.partition(":")

    dotted = f"{module}.{name}"
    return dotted if colon and dotted in RUNTIME_API else shown


_CALL_KEY_IN_TEXT = None


def modernize_message(message: str) -> str:
    """Réécrit dans un message les clés de fonctions de module en leur forme écrite :
    « sfx:play('Bip') : … » devient « sfx:play('Bip') : … ». Les diagnostics parlent au
    script tel que l'auteur l'a écrit, pas à la clé interne du catalogue."""
    global _CALL_KEY_IN_TEXT
    if _CALL_KEY_IN_TEXT is None:
        import re
        modules = "|".join(sorted(MODULE_CALLS))
        _CALL_KEY_IN_TEXT = re.compile(rf"(?<![\w.:])({modules})\.(\w+)(?=\()")
    return _CALL_KEY_IN_TEXT.sub(
        lambda m: module_call_form(f"{m.group(1)}.{m.group(2)}"), message)


def module_members(module: str) -> list[str]:

    """Ce que ce module offre — fonctions et propriétés confondues, puisque
    c'est ce que l'auteur cherche."""
    prefix = f"{module}."
    # Les propriétés d'un TYPE (`actor.position`) ne sont pas celles du MODULE du même nom
    # (`actor:get`) : elles ne se lisent que sur une référence de ce type.
    props = () if module in REF_TYPES else RUNTIME_PROPS
    return sorted(key[len(prefix):]
                  for key in (*RUNTIME_API, *props)
                  if key.startswith(prefix))



# ─── Résolution des constantes "str" ──────────────────────────────
# Helpers utilisés par le codegen pour convertir "nom_lua" → "NOM_C"

def anim_constant(actor_sym: str, anim_name: str) -> str:
    """'walk' pour Hero → 'ANIM_HERO_WALK'"""
    return f"ANIM_{actor_sym.upper()}_{c_ident(anim_name)}"


def sprite_id_constant(actor_sym: str, sprite_id: str) -> str:
    """'blesse' pour Hero → 'SPRITE_HERO_BLESSE'"""
    return f"SPRITE_{actor_sym.upper()}_{c_ident(sprite_id)}"


def sfx_constant(sfx_name: str) -> str:
    return f"SFX_{c_ident(sfx_name)}"


def music_constant(music_name: str) -> str:
    return f"MUSIC_{c_ident(music_name)}"


def key_constant(key_name: str) -> str:
    """'a' → 'BTN_A', 'left' → 'BTN_LEFT'"""
    return f"BTN_{c_ident(key_name)}"


def tag_constant(actor_name: str) -> str:
    """'enemy' → 'TAG_ENEMY'"""
    return f"TAG_{c_ident(actor_name)}"


def box_tag_constant(tag: str) -> str:
    """'hitbox' → 'BOXTAG_HITBOX' — EXACTEMENT la dérivation du `#define` émis par
    codegen/runtime_codegen/headers.py (`sym(tag).upper()`) : `c_ident` diffère
    de `sym` sur un tag qui commence par un chiffre."""
    return f"BOXTAG_{c_sym(tag).upper()}"


def scene_constant(scene_name: str) -> str:
    """'Victory' → 'SCENE_IDX_VICTORY'"""
    return f"SCENE_IDX_{c_ident(scene_name)}"


def camera_constant(camera_name: str) -> str:
    """'Boss' → 'CAM_BOSS'"""
    return f"CAM_{c_ident(camera_name)}"


def lang_constant(code: str) -> str:
    """'fr' → 'LANG_FR' — même index que `g_texts[lang]`/`g_lang_font[lang]`
    (source en 0, puis `settings.languages` dans l'ordre déclaré)."""
    return f"LANG_{c_ident(code)}"


def window_region_constant(name: str) -> str:
    """"object"/"outside" → les deux mots-clés fixes (jamais disputés, cf.
    ARCHITECTURE.md « Windows — le pochoir »). Tout autre nom → le nom d'un
    `WindowSlot` du projet, dérivé comme `camera_constant` ('MyPanel' →
    'WIN_MYPANEL') : le rang matériel réel est décidé par l'allocateur
    (`codegen/window_alloc.py`), le `#define` correspondant est émis par
    `headers.py` — jamais un index brut ici."""
    low = name.lower()
    if low in ("object", "outside"):
        return WIN_REGIONS[low]
    return f"WIN_{c_ident(name)}"


def text_constant(text_key: str) -> str:
    """'village_garde_01' → 'TEXT_VILLAGE_GARDE_01'"""
    return f"TEXT_{c_ident(text_key)}"


# Primitives qui acceptent un littéral à la place d'une clé — DÉDUIT du
# catalogue, jamais listé à la main : marquer un `Param.literal_ok` suffit à
# faire suivre le checker, le codegen et la collecte de littéraux.
LITERAL_TEXT_CALLS: frozenset = frozenset(
    k for k, f in RUNTIME_API.items()
    for prm in f.params if prm.domain == DOMAIN_TEXT and prm.literal_ok
)


def anon_text_key(literal: str) -> str:
    """Clé de l'entrée ANONYME que fabrique un littéral passé à `text.draw*`.

    Dérivée du CONTENU : la même phrase écrite dans deux scripts partage une
    seule entrée, et la clé ne bouge pas d'un build à l'autre. Un compteur, lui,
    se décalerait au premier littéral ajouté plus haut, décalant des index C
    sans que rien n'ait changé côté auteur.

    Le préfixe la range hors du chemin de l'utilisateur. Si une vraie clé
    s'appelait pareil, c'est elle qui gagnerait — la résolution essaie la table
    d'abord — donc le pire cas reste un texte affiché à la place d'un autre,
    jamais une table incohérente."""
    import hashlib
    return "_lit_" + hashlib.sha1(literal.encode("utf-8")).hexdigest()[:8]


def font_constant(font_name: str) -> str:
    """'Pixelia' → 'FONT_PIXELIA'"""
    return f"FONT_{c_ident(font_name)}"


def palette_constant(palette_name: str) -> str:
    """'Nuit' → 'PAL_NUIT'"""
    return f"PAL_{c_ident(palette_name)}"


def region_constant(region_name: str) -> str:
    """'boite_bas' → 'REGION_BOITE_BAS'"""
    return f"REGION_{c_ident(region_name)}"


def image_constant(image_name: str) -> str:
    """'coeur_2' → 'IMAGE_COEUR_2' — index dans `g_ui_images`."""
    return f"IMAGE_{c_ident(image_name)}"


def ui_list_constant(list_name: str) -> str:
    """'Inventaire' → 'UILIST_INVENTAIRE' — index dans `g_ui_lists`. Ce n'est
    PAS l'index d'élément : une liste a sa propre table, et son rang y est
    celui des panneaux-listes, pas celui de tous les éléments."""
    return f"UILIST_{c_ident(list_name)}"


def ref_constant(ref: str, name: str) -> str:
    """('list', 'Menu') → 'UILIST_MENU' : la constante C que `interface:get(nom)` émet pour
    un élément de ce TYPE. Le préfixe se déclare avec le type (`RefType.constant`) — les
    quatre fonctions ci-dessous n'en sont que les cas nommés, pour les `#define`."""
    return f"{REF_TYPE_TABLE[ref].constant}{c_ident(name)}"


def ui_element_constant(element_name: str) -> str:
    """'alerte' → 'UIELEM_ALERTE' — index dans la table de visibilité plate,
    qui couvre TOUS les éléments d'une mise en page (texte, conteneur, image),
    contrairement à REGION_*/IMAGE_* qui n'indexent que ce qui dessine."""
    return f"UIELEM_{c_ident(element_name)}"


def image_state_constant(image_name: str, state_name: str) -> str:
    """('coeur_2', 'vide') → 'IMGST_COEUR_2_VIDE'.

    Indexé par IMAGE et non par sprite : c'est l'image que le script nomme, et
    deux images du même sprite doivent pouvoir citer le même état sans que
    l'auteur ait à savoir quel asset est derrière. Le build émet une constante
    par (image, état de son sprite) — quelques `#define`, contre une résolution
    de chaîne au runtime que le moteur ne fait pas."""
    return f"IMGST_{c_ident(image_name)}_{c_ident(state_name)}"


# ─── Événements de scène ───────────────────────────────────────────
# Distinct des events d'acteur : pas de paramètre `self`.

KNOWN_SCENE_EVENTS: list[str] = [
    "on_start",
    "on_update",
    "on_late_update",
]

# Points d'entrée d'une CAMÉRA — les mêmes, moins `on_late_update` : le moteur
# n'exécute le script d'une caméra qu'à un seul moment de la frame (juste après
# le suivi déclaratif, cf. ROADMAP v0.6.1). Deux hooks s'y enchaîneraient sans
# que rien ne les sépare, donc l'un d'eux serait un mensonge.
KNOWN_CAMERA_EVENTS: list[str] = [
    "on_start",
    "on_update",
]

# Les événements ADMIS par famille de propriétaire. Un script n'a pas de type : c'est
# ce à quoi il est attaché qui décide de ce qu'il peut écrire. Un acteur et un prefab
# partagent la famille (mêmes événements, même `self`).
KNOWN_EVENTS_BY_KIND: dict[str, list[str]] = {
    "actor":  KNOWN_EVENTS,
    "prefab": KNOWN_EVENTS,
    "scene":  KNOWN_SCENE_EVENTS,
    "camera": KNOWN_CAMERA_EVENTS,
}

# Un événement de N'IMPORTE quelle famille : ce qui n'en est pas un est une fonction privée.
ALL_KNOWN_EVENTS: frozenset[str] = frozenset(
    ev for events in KNOWN_EVENTS_BY_KIND.values() for ev in events)

# Les familles qui ont un `self` : l'instance à laquelle le script est attaché.
OWNER_KINDS_WITH_SELF: frozenset[str] = frozenset({"actor", "prefab"})

def scene_event_sig(scene_sym: str, event: str, kind: str = "scene") -> str:
    """Signature C namespacée pour un hook sans `self`.

    `kind` nomme la famille de propriétaire : une CAMÉRA a exactement les mêmes
    points d'entrée qu'une scène (cf. ROADMAP v0.6.1) et emprunte donc toute
    cette machinerie — seul le mot dans le symbole change, pour qu'un
    `camera_Boss_camera_on_update` ne prétende pas être une scène."""
    return f"void {scene_sym}_{kind}_{event}(void)"


# (Une table `SCENE_EVENT_C_SIGNATURES` doublait `scene_event_sig` avec les
#  mêmes trois signatures en dur ; personne ne la lisait, et elle aurait figé le
#  mot « scene » que la caméra vient de rendre variable. Retirée.)
