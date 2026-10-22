"""BackgroundLayer / BackgroundAsset.
BackgroundImage = simple PNG dans assets/backgrounds/ (pas de JSON).
BackgroundAsset = sidecar d'import dans assets/backgrounds/{name}.json (à côté du PNG)."""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.tile_codec import pack_se, unpack_se
from core.models.palette import OWN_PAL_BANK
from core.models.sub_palette import SubPaletteAssetMixin, decode_palette_overrides
from core.models.gba_color import write_palettes, read_palettes
from core.models.project_json import write_grid, read_grid
from core.models import asset_extensions


# ── Types de fond ─────────────────────────────────────────────────
# Un DISCRIMINANT sur l'asset, pas trois classes. Les trois types sont la même
# chose sur le disque — un PNG et son sidecar de compression — et empruntent le
# même chemin complet : détection du mode à l'import, encodage 4bpp/8bpp/bitmap,
# grille de sous-palettes, validateur VRAM, réconciliation des PNG déposés à la
# main. Trois `Resource` distincts auraient recopié ce chemin trois fois pour ne
# faire varier que ce qu'on FAIT de l'image en aval.
#
# Ce qui change n'est donc pas la nature de l'asset mais son EMPLOI :
#   scene    — décor : posé en layer par une scène, repeint par tuile (inpainting).
#   ui       — interface : sert de fond à un `UIContainer`, soit en cadre étirable
#              (nine-slice), soit en image posée. Cf. `ui_role`.
#   animated — planche de frames : découpée en grille et jouée en boucle, puis
#              POSÉE sur un fond hôte (cf. `BackgroundAnimation`).
KIND_SCENE    = "scene"
KIND_UI       = "ui"
KIND_ANIMATED = "animated"

BG_KINDS = (KIND_SCENE, KIND_UI, KIND_ANIMATED)

BG_KIND_LABELS = {
    KIND_SCENE:    "Background",
    KIND_UI:       "UI background",
    KIND_ANIMATED: "Animated background",
}


COLOR_MAPPING_MODES = ("direct", "nearest", "luminance", "optimal", "ramp")


def _read_color_mapping(value) -> str:
    return value if value in COLOR_MAPPING_MODES else "direct"


def _color_mapping(source: list, target: list, mode: str) -> list[int]:
    """Association des 16 index d'une sous-palette 4bpp.

    L'index zéro reste transparent. Les distances sont calculées dans l'espace
    perceptuel OKLab : deux couleurs qui paraissent proches sont ainsi mieux
    associées qu'avec une simple distance RGB.
    """
    count = min(16, len(source), len(target))
    mapping = list(range(16))
    if mode == "direct" or count < 2:
        return mapping
    def oklab(word):
        # BGR555 GBA -> sRGB linéaire -> OKLab (Björn Ottosson).
        rgb = [((word >> shift) & 31) / 31 for shift in (0, 5, 10)]
        rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        r, g, b = rgb
        l = .4122214708 * r + .5363325363 * g + .0514459929 * b
        m = .2119034982 * r + .6806995451 * g + .1073969566 * b
        s = .0883024619 * r + .2817188376 * g + .6299787005 * b
        l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
        return (.2104542553 * l + .7936177850 * m - .0040720468 * s,
                1.9779984951 * l - 2.4285922050 * m + .4505937099 * s,
                .0259040371 * l + .7827717662 * m - .8086757660 * s)
    labs_source = [oklab(word) for word in source[:count]]
    labs_target = [oklab(word) for word in target[:count]]
    def hue(lab):
        return math.atan2(lab[2], lab[1])
    def cost(a, b):
        return sum((x - y) ** 2 for x, y in zip(labs_source[a], labs_target[b]))
    src, dst = list(range(1, count)), list(range(1, count))
    if mode == "luminance":
        src.sort(key=lambda i: labs_source[i][0]); dst.sort(key=lambda i: labs_target[i][0])
        for a, b in zip(src, dst): mapping[a] = b
        return mapping
    if mode == "ramp":
        # Une rampe colorée garde l'ordre teinte -> saturation -> valeur.
        src.sort(key=lambda i: (hue(labs_source[i]), math.hypot(labs_source[i][1], labs_source[i][2]), labs_source[i][0]))
        dst.sort(key=lambda i: (hue(labs_target[i]), math.hypot(labs_target[i][1], labs_target[i][2]), labs_target[i][0]))
        for a, b in zip(src, dst): mapping[a] = b
        return mapping
    if mode == "nearest":
        for a in src: mapping[a] = min(dst, key=lambda b: cost(a, b))
        return mapping
    # Appariement global Hongrois : une couleur cible est utilisée une seule
    # fois et la distance perceptuelle totale est minimale.
    n = len(src)
    u, v, p, way = [0.0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0, minv, used = i, 0, [float("inf")] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True; i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost(src[i0 - 1], dst[j - 1]) - u[i0] - v[j]
                    if cur < minv[j]: minv[j], way[j] = cur, j0
                    if minv[j] < delta: delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]: u[p[j]] += delta; v[j] -= delta
                else: minv[j] -= delta
            j0 = j1
            if p[j0] == 0: break
        while True:
            j1, p[j0], j0 = way[j0], p[way[j0]], way[j0]
            if j0 == 0: break
    for j in range(1, n + 1):
        mapping[src[p[j] - 1]] = dst[j - 1]
    return mapping

# ── Rôle d'un fond d'INTERFACE ────────────────────────────────────
# Les valeurs sont volontairement CELLES de `UIContainer.fill_kind` (FILL_NINE /
# FILL_BG, cf. core/models/ui_region.py) : l'inspecteur d'UI filtre son menu
# d'assets sur ce champ, et une seconde nomenclature obligerait à traduire
# dans les deux sens à chaque lecture.
UI_ROLE_NINE = "nine_slice"   # cadre étirable : coins fixes, bords/centre répétés
UI_ROLE_BG   = "background"   # image posée en haut-gauche, rognée bas/droite

UI_ROLES = (UI_ROLE_NINE, UI_ROLE_BG)

# ── Mode d'animation d'un fond ANIMÉ ──────────────────────────────
# Deux façons de faire bouger un décor, et l'auteur choisit sur ce qu'il VOIT :
#   instance — chaque copie posée a sa propre animation. Les entrées de carte du
#              rectangle sont réécrites ; toutes les frames restent résidentes.
#   shared   — toutes les copies bougent ensemble. Les pixels de la tuile sont
#              réécrits ; une seule frame est résidente, et TOUTE case qui
#              utilise la tuile change avec elle — c'est la définition du
#              procédé, pas un effet de bord.
#
# Nommés par leur effet observable et non par un cas d'usage : « cascade » et
# « objet unique » sont des exemples, et un libellé qui est un exemple laisse
# l'auteur chercher lequel des deux ressemble le plus à son tapis d'herbe.
#
# `instance` est le défaut : c'est l'attente quand on pose un objet à une
# position précise, et c'est ce que le pipeline sait déjà produire — la planche
# est encodée en un tileset dédupliqué dont chaque frame est un sous-rectangle.
# `shared` demande au contraire de DÉSACTIVER la déduplication pour l'asset.
ANIM_INSTANCE = "instance"
ANIM_SHARED   = "shared"

ANIM_MODES = (ANIM_INSTANCE, ANIM_SHARED)

ANIM_MODE_LABELS = {
    ANIM_INSTANCE: "Per instance",
    ANIM_SHARED:   "Shared",
}


@dataclass
class BackgroundLayer:
    """Une couche de fond d'une scène : référence un BackgroundAsset (par nom) +
    slot GBA + vitesse de défilement."""
    background_name: str = ""  # nom du BackgroundAsset référencé (= stem du PNG) ;
                               # le fichier PNG vit sur BackgroundAsset.asset, pas ici
                               # (convention : cf. SpriteComponent.sprite_name)
    bg_slot:      int   = 0    # slot hardware GBA (0-3)
    scroll_speed: float = 1.0  # vitesse relative (1.0 = défilement normal)
    pal_bank:     int   = OWN_PAL_BANK  # slot (0-15) dans scene.active_bg_palettes,
                               # ou OWN_PAL_BANK (-1, défaut) = palette propre du PNG.
                               # Même mécanisme que Actor.pal_bank/Prefab.pal_bank,
                               # mais BG plutôt qu'OBJ ; chaque layer choisit sa
                               # propre banque, indépendamment des autres layers.
    # Overrides de palette PAR TUILE 8×8 (champ SE_PALBANK du hardware GBA) :
    # (col, row) -> slot (0-15) dans scene.active_bg_palettes. Absent = utilise
    # pal_bank (banque de base du layer). Peint depuis le canvas du Scene Manager.
    tile_palette_overrides: dict = field(default_factory=dict)  # dict[tuple[int,int], int]
    visible:      bool  = True   # visibilité VIEWPORT éditeur seule — le codegen
                               # l'ignore (le layer est toujours compilé).
    # Rôle de ce layer dans le mélange de couleurs de la scène — "" (aucun),
    # BLEND_TOP ou BLEND_BOTTOM (cf. models/scene.py).
    #
    # **Un layer ne porte PAS de mode.** `BLDCNT` n'a qu'un seul champ mode
    # (bits 6-7) pour tout l'écran : deux layers ne peuvent pas mélanger
    # différemment. Ce qui est par layer, c'est uniquement l'appartenance à
    # l'ensemble du DESSUS (bits 0-5) ou du DESSOUS (bits 8-13). Le mode et ses
    # coefficients vivent donc sur la scène — un champ « mode » ici promettrait
    # un réglage que le matériel ne sait pas tenir.
    blend_role:   str   = ""


def decode_tile_paint(raw) -> dict:
    """Relit `tile_paint` du JSON ({"col,row": [couleur, palette]}) ; tolère l'absence et les entrées mal formées."""
    out: dict = {}
    for key, value in (raw or {}).items():
        try:
            col, row = (int(v) for v in key.split(","))
            color, pal = int(value[0]), int(value[1])
        except (ValueError, TypeError, IndexError, AttributeError):
            continue
        if 0 <= color < 16 and 0 <= pal < 16:
            out[(col, row)] = (color, pal)
    return out


def decode_tile_palette_overrides(raw) -> dict:
    """Relit tile_palette_overrides du JSON ({"col,row": slot}) en dict[(col,row), slot].
    Tolère l'absence (None) et les clés mal formées (ignorées)."""
    out: dict[tuple[int, int], int] = {}
    if not raw:
        return out
    for key, slot in raw.items():
        try:
            c, r = key.split(",")
            out[(int(c), int(r))] = int(slot)
        except (ValueError, AttributeError):
            continue
    return out


def guess_frame_size(img_w: int, img_h: int) -> tuple[int, int]:
    """Découpe PROBABLE d'une planche d'animation, ou (0, 0) si rien d'évident.

    Une seule règle, celle qui couvre la planche que les gens dessinent : une
    BANDE de frames carrées, horizontale ou verticale. Le côté court donne alors
    la taille de la frame, et le long doit en être un multiple exact — sinon on
    ne devine rien plutôt que de deviner faux, et l'auteur pose ses deux nombres.

    Deviner à l'import et non à la lecture : la découpe est un CHAMP, que
    l'auteur corrige et qui ne doit pas se remettre à bouger derrière lui."""
    if img_w <= 0 or img_h <= 0 or img_w == img_h:
        return (0, 0)
    short, long_ = min(img_w, img_h), max(img_w, img_h)
    if long_ % short:
        return (0, 0)
    return (short, short)


def _read_kind(raw) -> str:
    """`kind` du JSON, ramené à une valeur connue. Un type inconnu (fichier
    d'une version plus récente, faute de frappe) se relit en DÉCOR plutôt qu'en
    erreur : le fond reste visible et réparable depuis l'éditeur."""
    return raw if raw in BG_KINDS else KIND_SCENE


def _read_ints(raw, minimums: tuple) -> Optional[tuple]:
    """Entiers dont chacun atteint son minimum (`minimums` fixe aussi la
    longueur), ou None. Une préparation illisible (mauvaise longueur, valeur
    trop petite, texte) se relit comme « pas de préparation » : l'image
    d'origine reste utilisable, c'est le repli le moins surprenant."""
    try:
        vals = tuple(int(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if len(vals) != len(minimums) or any(v < lo for v, lo in zip(vals, minimums)):
        return None
    return vals


def _read_cells(cells: list) -> list:
    """Les entrées d'une tilemap, ou rien si l'une n'est pas un entier : une grille abîmée se relit comme
    « pas encore encodée » plutôt que de faire planter le build sur une opération binaire."""
    return cells if all(type(c) is int for c in cells) else []


_POS_LIMIT = 1 << 20   # une position se lit signée : seul ce plancher la distingue d'un sidecar corrompu

# Le canvas FIXE d'un fond bitmap (Mode 4, plein écran). Une seule définition : l'encodeur (core.bg_import) et le
# modèle la lisent ici.
BITMAP_SIZE = (240, 160)


def _read_axis(raw) -> Optional[int]:
    """Axe de miroir en pixels (≥ 1), ou None : une valeur illisible se relit comme « pas de miroir »."""
    try:
        axis = int(raw)
    except (TypeError, ValueError):
        return None
    return axis if axis >= 1 else None


def _read_ui_role(raw) -> str:
    return raw if raw in UI_ROLES else UI_ROLE_NINE


def _read_animation_mode(raw) -> str:
    """Même parti pris que `_read_kind` : un mode inconnu se relit au DÉFAUT
    plutôt qu'en erreur. Un fichier écrit par une version plus récente reste
    ouvrable, et l'auteur voit dans l'inspecteur ce que le build fera."""
    return raw if raw in ANIM_MODES else ANIM_INSTANCE


# Les façons de répartir l'erreur de la réduction de couleurs : diffusion (Floyd–Steinberg), ou trames ordonnées
# (Bayer 4×4 / 8×8) — régulières, donc plus propres une fois tuilées. Le jeton est ce qui s'écrit dans le sidecar.
DITHER_KINDS = ("floyd_steinberg", "bayer4", "bayer8")


@dataclass
class BackgroundCompression:
    """Réglages de l'encodage TUILÉ 4bpp d'un fond — ce avec quoi l'auteur « joue »
    pour faire tenir une image riche. Les valeurs par défaut sont le comportement
    d'avant ces réglages : un fond qui n'y touche pas s'encode à l'identique, et
    n'écrit rien dans son sidecar.

    `palettes_max`        sous-palettes autorisées (1–16, le matériel en offre 16) ;
    `colors_per_palette`  couleurs utiles par sous-palette (2–15 : l'index 0 est le
                          transparent) ;
    `global_colors`       réduire d'abord TOUTE l'image à ce nombre de couleurs
                          (0 = non) — c'est ce qui rend les tuiles voisines
                          compatibles entre elles avant le découpage ;
    `tile_target`         nombre de tuiles uniques visé (0 = pas de fusion) : les
                          tuiles sont regroupées par plus faible perte, chaque
                          groupe garde sa tuile la plus centrale. Avec perte ;
    `palette_colors`      8bpp : couleurs de l'UNIQUE palette (2–255, l'index 0 est
                          le transparent). `tile_target` vaut aussi en 8bpp.
    Les quatre premiers ne règlent que le 4bpp, le dernier que le 8bpp."""
    palettes_max: int = 16
    colors_per_palette: int = 15
    global_colors: int = 0
    tile_target: int = 0
    palette_colors: int = 255
    dither_kind: str = "floyd_steinberg"   # n'agit que si le dithering est coché

    def is_default(self) -> bool:
        return self == BackgroundCompression()

    def to_dict(self) -> dict:
        """Seulement ce qui s'écarte du défaut — le sidecar reste minimal."""
        base = BackgroundCompression()
        return {k: v for k, v in self.__dict__.items() if v != getattr(base, k)}

    @classmethod
    def from_dict(cls, d) -> "BackgroundCompression":
        """Valeurs ramenées dans leur plage : un fichier écrit à la main ou par une
        autre version ne doit pas pouvoir demander zéro palette."""
        d = d if isinstance(d, dict) else {}

        def _int(key: str, lo: int, hi: int, default: int) -> int:
            try:
                return max(lo, min(hi, int(d.get(key, default))))
            except (TypeError, ValueError):
                return default

        return cls(
            palettes_max=_int("palettes_max", 1, 16, 16),
            colors_per_palette=_int("colors_per_palette", 2, 15, 15),
            global_colors=_int("global_colors", 0, 256, 0),
            tile_target=_int("tile_target", 0, 1024, 0),
            palette_colors=_int("palette_colors", 2, 255, 255),
            dither_kind=d.get("dither_kind") if d.get("dither_kind") in DITHER_KINDS else "floyd_steinberg",
        )


@dataclass
class BackgroundAdjust:
    """Réglages de l'IMAGE avant la compression : teinte, saturation, luminosité, contraste. Ils dirigent ce que
    la compression reçoit — d'où leur place AVANT elle. Neutres à 0 : un fond qui n'y touche pas s'encode à
    l'identique et n'écrit rien dans son sidecar. Le PNG source n'est jamais modifié.

    `hue`  −180…180 degrés ; `saturation`, `brightness`, `contrast`  −100…100 (pourcentage autour du neutre)."""
    hue: int = 0
    saturation: int = 0
    brightness: int = 0
    contrast: int = 0

    def is_default(self) -> bool:
        return self == BackgroundAdjust()

    def to_dict(self) -> dict:
        base = BackgroundAdjust()
        return {k: v for k, v in self.__dict__.items() if v != getattr(base, k)}

    @classmethod
    def from_dict(cls, d) -> "BackgroundAdjust":
        d = d if isinstance(d, dict) else {}

        def _int(key: str, lo: int, hi: int) -> int:
            try:
                return max(lo, min(hi, int(d.get(key, 0))))
            except (TypeError, ValueError):
                return 0

        return cls(hue=_int("hue", -180, 180), saturation=_int("saturation", -100, 100),
                   brightness=_int("brightness", -100, 100), contrast=_int("contrast", -100, 100))


@dataclass
class BackgroundAnimation:
    """Un fond ANIMÉ posé à une position d'un fond hôte.

    **Le placement vit chez l'hôte, pas chez l'animé.** Une cascade dessinée une
    fois se pose dans trois décors : stocker les positions dans l'animé
    obligerait à y citer les fonds qui l'emploient, c'est-à-dire à inverser le
    sens de la référence (`<asset>_name` va toujours du consommateur vers
    l'asset). L'hôte porte donc sa liste, exactement comme une scène porte ses
    `background_layers` plutôt que le fond ses scènes.

    Position en PIXELS de l'image hôte, comme tout le reste de l'éditeur ; le
    calage sur la grille 8×8 est un geste du canvas, pas un format de stockage
    (même parti pris que `UIRegion`)."""
    animated_name: str = ""   # nom d'un BackgroundAsset de kind `animated`
    x: int = 0
    y: int = 0
    # Ce qui distingue CETTE copie des autres copies de la même planche. Le reste
    # — découpe, boucle, mode — appartient à l'animé : une cascade est une
    # cascade partout où on la pose.
    #
    # Les deux n'ont de sens qu'en mode `instance`, où chaque copie a son propre
    # compteur (c'est même sa raison d'être). En `shared` toutes les copies
    # partagent un unique compteur ; l'éditeur ne propose donc pas ces champs.
    start_frame: int = 0
    # SURCHARGE de la cadence de l'animé, en ticks 60 Hz. 0 = celle de l'animé —
    # même convention que `UIContainer.fill_speed` vis-à-vis du sprite qu'il pave.
    # Deux copies à des vitesses différentes se désynchronisent durablement, là
    # où deux images de départ distinctes gardent le même rythme.
    speed: int = 0

    def to_dict(self) -> dict:
        d = {"animated_name": self.animated_name, "x": self.x, "y": self.y}
        if self.start_frame:
            d["start_frame"] = self.start_frame
        if self.speed:
            d["speed"] = self.speed
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BackgroundAnimation":
        return cls(animated_name=str(d.get("animated_name", "")),
                   x=int(d.get("x", 0) or 0), y=int(d.get("y", 0) or 0),
                   start_frame=max(0, int(d.get("start_frame", 0) or 0)),
                   speed=max(0, int(d.get("speed", 0) or 0)))

    def effective_speed(self, ba) -> int:
        """Cadence réellement appliquée : la surcharge, ou celle de l'animé.
        Point d'accès unique — l'aperçu du canvas et le build doivent lire la
        même, sinon l'éditeur ment sur ce que la ROM fera."""
        return max(1, self.speed or int(getattr(ba, "speed", 8) or 8))


@dataclass
class BackgroundAsset(SubPaletteAssetMixin, Resource):
    """Asset d'UNE image de fond — `<nom>.background`, rangé où l'auteur veut sous assets/ ; il POINTE
    son PNG par un chemin relatif au projet (comme SpriteAsset). Le PNG source n'est jamais modifié.
    C'est la SCÈNE qui possède ses layers (Scene.background_layers) et référence
    ce fond par nom — plus de composition multi-layer réutilisable ici."""
    sidecar_extension = asset_extensions.BACKGROUND
    name:   str  = "background"
    asset:   str  = ""                              # chemin du PNG relatif au projet (cf. SpriteAsset)
    palettes: list = field(default_factory=list)    # list[list[int]] BGR555 (≤16×≤16)
    tileset:  list = field(default_factory=list)    # list[str] (64 nibbles hex/tuile)
    tilemap:  list = field(default_factory=list)    # list[int] (screen entries GBA)
    tiles_w:  int = 0
    tiles_h:  int = 0
    quantize_method: str = "median_cut"
    # Mode couleur GBA du fond : 4 (jusqu'à 16 sous-palettes de 16, pal_bank par
    # tuile — défaut) ou 8 (une seule palette de 256 couleurs, tuiles en octets,
    # pas d'inpainting). Auto-détecté à l'import (> 256 couleurs -> 8bpp).
    bpp: int = 4
    dither: bool = False   # 8bpp uniquement : dithering du quantifieur (OFF par défaut)
    # Type de fond : "tiled" (Mode 0, tuilé — défaut, cf. bpp) ou "bitmap" (Mode 4,
    # plein écran 240×160, 256 couleurs, SANS tuiles — pour les photos/écrans-titre).
    mode: str = "tiled"
    bitmap: str = ""       # mode bitmap : index 8bpp du buffer (hex, out_w*out_h octets)
    out_w: int = 0         # dimensions du bitmap après ajustement à ≤240×160
    out_h: int = 0
    # BackgroundInpainting (niveau ÉDITEUR, partagé entre scènes) : réassigne la
    # palette (pal_bank local, index dans `palettes`) d'une tuile 8×8. La baseline
    # `tilemap` reste intacte ; `effective_tilemap()` applique ces overrides.
    # Analogue à BackgroundLayer.tile_palette_overrides mais au niveau de l'asset. Comme la peinture, un repeint ne cible
    # qu'une palette AJOUTÉE (une référence au catalogue, que l'encodage ne touche pas) et la désigne par sa POSITION dans
    # `added_palettes` — pas par un numéro de banque, qu'un encodage peut déplacer (cf. `repaint_bank`).
    tile_palette_overrides: dict = field(default_factory=dict)  # dict[(col,row), position dans added_palettes]
    # Comment les index d'une tuile repeinte sont associés à sa nouvelle palette.
    # "direct" préserve le comportement historique (i -> i).
    color_mapping: str = "direct"
    # Peinture de CASES (niveau éditeur) : un CALQUE par-dessus l'image. Une case peinte montre une tuile pleine de
    # la couleur `color` (index dans la sous-palette `pal`) ; `color` 0 la rend transparente. Effacer une case la
    # retire du dict et rend la tuile initiale. Ni `tileset` ni `tilemap` ne sont touchés : une recompression de
    # l'image garde donc la peinture. `effective_tileset()` / `effective_tilemap()` la composent.
    # `pal` = la POSITION de la palette dans `added_palettes` (pas un numéro de banque : le numéro se calcule, cf.
    # `painted_cells`) — un encodage qui change le nombre de palettes dérivées ne déplace donc pas la peinture.
    tile_paint: dict = field(default_factory=dict)  # dict[(col,row), (color, position dans added_palettes)]
    # Diagnostics de compression (validateur éditeur, non-bloquant) — calculés à
    # la compression, cf. bg_import.encode_background. Le PNG reste intact.
    diagnostics: dict = field(default_factory=dict)
    # Empreinte de l'image dont sont tirés `tileset`/`palettes` ci-dessus —
    # « ces tuiles viennent de CETTE version du PNG ». Permet de voir qu'une
    # image a été retouchée hors de l'éditeur, ce qu'une date de fichier ne dit
    # pas de façon fiable : le sidecar est réécrit à chaque sauvegarde, donc
    # presque toujours plus récent que le PNG, et certains outils de dessin
    # reposent l'ancienne date en enregistrant. Vide = origine inconnue (asset
    # d'avant ce champ). Cf. core.resources.asset_reconciliation.resync_background_png.
    source_stamp: str = ""
    # Empreinte des RÉGLAGES qui ont produit `tileset`/`palettes`/`bitmap` (cf. `encode_settings_fingerprint`) : « ce
    # résultat vient de CES réglages ». Quand les réglages d'aujourd'hui en ont une autre, le résultat est périmé
    # (cf. `encoding_is_current`). Vide = origine inconnue (asset d'avant ce champ) : traité comme à jour.
    encoded_for: str = ""
    # Plan de travail — le PNG reste intact, c'est l'image en mémoire qu'on pose dans un canvas (cf.
    # bg_import.prepare_source). `canvas_size` = (w, h) du canvas, valeur DISTINCTE de la taille de l'image : ce
    # que l'encodeur reçoit. `image_size` = (w, h) de l'image une fois mise à l'échelle ; `image_pos` = (x, y) de son
    # coin haut-gauche dans le canvas, qui peut déborder (le surplus est rogné) ou laisser du vide (transparent).
    # None partout = « Original » : canvas = image = fichier, posée en (0, 0).
    canvas_size: Optional[tuple] = None
    image_pos: Optional[tuple] = None
    image_size: Optional[tuple] = None
    # Miroir du canvas, APRÈS la pose de l'image : position
    # de l'axe en pixels du canvas (None = pas de miroir sur cet axe).
    # `mirror_x` est une barre verticale (le côté gauche se reflète à droite),
    # `mirror_y` une barre horizontale (le haut se reflète en bas). Il précède la
    # compression, puisqu'il change les tuiles que celle-ci trouvera.
    mirror_x: Optional[int] = None
    mirror_y: Optional[int] = None
    # Côté GARDÉ : par défaut le gauche / le haut ; `True` garde le droit / le bas (le gauche / haut en est le reflet).
    mirror_flip_x: bool = False
    mirror_flip_y: bool = False
    # Réglages de l'encodage tuilé 4bpp (cf. BackgroundCompression).
    compression: BackgroundCompression = field(default_factory=BackgroundCompression)
    adjust: BackgroundAdjust = field(default_factory=BackgroundAdjust)   # teinte, saturation… avant la compression
    # Origine des sous-palettes pour l'éditeur (modèle scène : grisé + override).
    # `source_palettes` = snapshot des palettes DÉRIVÉES du PNG à la compression
    # (baseline restaurable). Les indices < len(source_palettes) sont dérivés
    # (grisés/overridables) ; les suivants sont ajoutés depuis le catalogue
    # (éditables). `ba.palettes` reste les couleurs EFFECTIVES (rendu/build
    # inchangés) : une dérivée overridée a ses couleurs = celles du catalogue et
    # son index figure dans `palette_overrides` (idx -> nom de banque catalogue).
    source_palettes: list = field(default_factory=list)    # list[list[int]] BGR555
    palette_overrides: dict = field(default_factory=dict)  # dict[int, str]  — un RÉGLAGE (cf. `settings`)
    # Les palettes AJOUTÉES (« + ») : des RÉFÉRENCES au catalogue de palettes, par nom — jamais des copies. Un RÉGLAGE :
    # l'encodage ne les voit pas, donc ne peut ni les perdre ni les changer. Leurs couleurs, comme celles d'un override,
    # viennent du catalogue ; `palettes` n'en garde que le cache résolu (cf. `resolve_palettes`). Une tuile peinte
    # (`tile_paint`) en désigne une par sa POSITION dans cette liste.
    added_palettes: list = field(default_factory=list)     # list[str] noms de banques du catalogue

    # ── Emploi de l'image (cf. BG_KINDS en tête de module) ─────────
    kind: str = KIND_SCENE

    # ── kind == ui : fond d'interface ─────────────────────────────
    # `ui_role` dit COMMENT le `UIContainer` étale l'image ; les marges ne comptent
    # qu'en nine-slice. En pixels, comme la géométrie d'UI — mais le build les
    # ramène à la TUILE (une tilemap ne coupe pas un cadre à 3 px, cf.
    # main_gen.scene_ui_fills), d'où le défaut à 8 : une marge d'une tuile est
    # la plus petite qui survive au passage.
    ui_role: str = UI_ROLE_NINE
    slice_left:   int = 8
    slice_right:  int = 8
    slice_top:    int = 8
    slice_bottom: int = 8

    # ── kind == animated : planche de frames ──────────────────────
    # Découpe en GRILLE (frame_w × frame_h balayée de gauche à droite puis de
    # haut en bas), et non « nombre de frames + sens » : une grille couvre la
    # bande horizontale (une seule rangée) comme la planche carrée, alors qu'un
    # compteur ne dit rien de la disposition. 0 = pas encore découpé, l'image
    # entière valant une frame — un fond animé sans découpe reste affichable.
    frame_w: int = 0
    frame_h: int = 0
    # Ticks GBA (60 Hz) entre deux frames — MÊME unité que `AnimState.speed`,
    # pour qu'une vitesse se lise pareil qu'on anime un sprite ou un décor.
    speed: int = 8
    loop: bool = True
    # Comment l'animation est jouée (cf. ANIM_MODES en tête de module). Vit sur
    # l'ANIMÉ et non sur le placement : une cascade est une cascade partout où
    # on la pose, et un mode par placement forcerait deux encodages du même
    # asset dans une même scène. Symétrique de la règle de placement — la
    # position vit chez l'hôte, la nature de l'animation chez l'animé.
    animation_mode: str = ANIM_INSTANCE

    # ── Fonds animés POSÉS sur celui-ci (cf. BackgroundAnimation) ─
    # N'a de sens que sur un hôte ; un animé peut en porter (une planche reste
    # une image), mais rien dans l'éditeur ne le propose.
    animations: list = field(default_factory=list)   # list[BackgroundAnimation]

    # ── Le résultat est-il à jour ? ───────────────────────────────
    def encode_settings_fingerprint(self) -> str:
        """Empreinte des réglages qui DÉTERMINENT l'encodage : layout, profondeur, dithering, méthode, canvas (EFFECTIF : un
        bitmap a toujours 240×160), pose et taille de l'image, miroir, ajustements, compression. Les palettes citées, la
        peinture et les repeints n'y sont pas : ils se posent par-dessus le résultat sans le changer. Stable d'une
        session à l'autre (JSON trié, SHA-1), courte."""
        canvas = BITMAP_SIZE if self.mode == "bitmap" else self.canvas_size
        settings = {
            "mode": self.mode, "bpp": self.bpp, "dither": self.dither, "method": self.quantize_method,
            "canvas": canvas, "pos": self.image_pos, "size": self.image_size,
            "mirror": [self.mirror_x, self.mirror_y, self.mirror_flip_x, self.mirror_flip_y],
            "compression": self.compression.to_dict(), "adjust": self.adjust.to_dict(),
        }
        blob = json.dumps(settings, sort_keys=True, default=list)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]

    def encoding_is_current(self, source_stamp: Optional[str] = None) -> bool:
        """Le résultat (`tileset` / `bitmap`) correspond-il aux réglages d'aujourd'hui — et, si on donne l'empreinte
        ACTUELLE du fichier source, à la version du PNG dont il est tiré ? Faux sans résultat. Un asset d'avant `encoded_for`
        est tenu pour à jour : on ne réencode pas tout un projet existant à l'ouverture."""
        if not (self.tileset or self.bitmap):
            return False
        if self.encoded_for and self.encoded_for != self.encode_settings_fingerprint():
            return False
        if source_stamp is not None and self.source_stamp and source_stamp != self.source_stamp:
            return False
        return True

    def choose_layout(self, token: str) -> None:
        """Le layout VOULU, comme RÉGLAGE : « tiled4 » | « tiled8 » | « bitmap » | « bitmap16 » (le vocabulaire de
        `bg_import.detect_import_mode`). C'est le geste de l'auteur — ou de l'import, qui décide à sa place —, jamais
        un effet de l'encodage : `apply_bg_encoding` range un résultat, il ne touche pas aux réglages.

        Un bitmap est un tampon plein écran : son canvas vaut 240×160, ENREGISTRÉ pour que repasser en tuilé garde la
        taille connue, et il n'a pas de tuiles à repeindre."""
        if token.startswith("bitmap"):
            self.mode, self.bpp = "bitmap", 8
            self.canvas_size = BITMAP_SIZE
            self.tile_palette_overrides = {}
            self.tile_paint = {}
        else:
            self.mode, self.bpp = "tiled", 8 if token == "tiled8" else 4

    def import_prep(self) -> dict:
        """La préparation de la source, sous la forme que prend `bg_import` —
        les DEUX appelants qui encodent (worker de l'éditeur, chemin synchrone
        de la réconciliation) la lisent ici, pour ne jamais diverger."""
        return {"canvas": self.canvas_size, "pos": self.image_pos, "size": self.image_size, "adjust": self.adjust,
                "mirror": (self.mirror_x, self.mirror_y, self.mirror_flip_x, self.mirror_flip_y)}

    # ── Type ──────────────────────────────────────────────────────
    @property
    def is_ui(self) -> bool:
        return self.kind == KIND_UI

    @property
    def is_animated(self) -> bool:
        return self.kind == KIND_ANIMATED

    def kind_label(self) -> str:
        return BG_KIND_LABELS.get(self.kind, BG_KIND_LABELS[KIND_SCENE])

    # ── Géométrie de l'image compressée ───────────────────────────
    def pixel_size(self) -> tuple[int, int]:
        """(w, h) en pixels de la représentation GBA — tuiles×8 en tuilé, le
        buffer ajusté en bitmap. 0×0 tant que rien n'est compressé."""
        if self.mode == "bitmap":
            return (self.out_w, self.out_h)
        return (self.tiles_w * 8, self.tiles_h * 8)

    # ── kind == ui ────────────────────────────────────────────────
    def slice_margins(self) -> tuple[int, int, int, int]:
        """(left, right, top, bottom) en pixels. Un point d'accès unique plutôt
        que quatre `getattr` chez chaque consommateur (canvas de scène, codegen
        des fonds d'UI) — c'est ce qui avait fini par diverger du temps où les
        marges vivaient dans un asset `NineSlice` séparé."""
        return (self.slice_left, self.slice_right, self.slice_top, self.slice_bottom)

    def slice_margins_tiles(self) -> tuple[int, int, int, int]:
        """Les mêmes marges en TUILES, telles que le build les verra. Affichées
        par l'éditeur : une marge de 4 px vaut 0 tuile à l'arrivée, et le seul
        endroit où l'auteur peut s'en apercevoir est là où il la règle."""
        return tuple(m // 8 for m in self.slice_margins())  # type: ignore[return-value]

    # ── kind == animated ──────────────────────────────────────────
    def frame_size(self) -> tuple[int, int]:
        """(w, h) RÉSOLUE d'une frame : la découpe déclarée, ou l'image entière
        si elle ne l'est pas encore. Jamais 0 — les appelants divisent par."""
        iw, ih = self.pixel_size()
        return (self.frame_w or iw or 1, self.frame_h or ih or 1)

    def frame_grid(self) -> tuple[int, int]:
        """(colonnes, rangées) de la planche. Tronqué : une frame partielle en
        bord d'image n'en est pas une, elle sortirait rognée à l'écran."""
        iw, ih = self.pixel_size()
        fw, fh = self.frame_size()
        return (max(0, iw // fw), max(0, ih // fh))

    def frame_count(self) -> int:
        cols, rows = self.frame_grid()
        return cols * rows

    def frame_rect(self, index: int) -> tuple[int, int, int, int]:
        """(x, y, w, h) en pixels de la frame `index` dans la planche. Balayage
        de gauche à droite puis de haut en bas. Rect vide si hors planche."""
        cols, rows = self.frame_grid()
        fw, fh = self.frame_size()
        if cols <= 0 or not (0 <= index < cols * rows):
            return (0, 0, 0, 0)
        return ((index % cols) * fw, (index // cols) * fh, fw, fh)

    def frame_grid_is_exact(self) -> bool:
        """La découpe tombe-t-elle juste sur l'image ? Faux = des pixels de la
        planche n'appartiennent à aucune frame (bande morte à droite/en bas)."""
        iw, ih = self.pixel_size()
        fw, fh = self.frame_size()
        return bool(iw and ih) and iw % fw == 0 and ih % fh == 0

    def duration_frames(self) -> int:
        """Durée d'un cycle en ticks 60 Hz — ce que l'auteur lit comme « une
        seconde », pas comme « 8 »."""
        return max(1, self.speed) * max(1, self.frame_count())

    # ── Fonds animés posés ────────────────────────────────────────
    def animation_at(self, x: int, y: int, sizes) -> Optional["BackgroundAnimation"]:
        """Placement dont la frame couvre le pixel (x, y), le DERNIER posé
        d'abord (il est au-dessus). `sizes` = callable nom→(w, h) : le modèle ne
        résout pas les noms d'asset, c'est le projet qui les connaît."""
        for pl in reversed(self.animations):
            w, h = sizes(pl.animated_name) or (0, 0)
            if w and h and pl.x <= x < pl.x + w and pl.y <= y < pl.y + h:
                return pl
        return None

    # ── Palettes : dérivées du PNG, overrides, ajoutées par référence ─────
    def added_bank(self, position: int) -> int:
        """Le numéro de banque (index dans `palettes`) de la palette ajoutée à cette POSITION : les dérivées d'abord."""
        return self.derived_count() + position

    def added_position(self, bank: int) -> int:
        """La position dans `added_palettes` de la banque `bank`, ou -1 si c'est une palette dérivée du PNG."""
        position = bank - self.derived_count()
        return position if 0 <= position < len(self.added_palettes) else -1

    def added_palette_colors(self) -> list:
        """Les couleurs en cache des palettes ajoutées, dans l'ordre de `added_palettes` — à lire AVANT qu'un
        encodage remplace `palettes`, pour que `resolve_palettes` retombe dessus si une banque a quitté le catalogue."""
        return [list(p) for p in self.palettes[self.derived_count():][:len(self.added_palettes)]]

    def add_palette_ref(self, name: str, colors: list) -> int:
        """« + » : ajoute la banque `name` du catalogue. Retourne son numéro de banque, ou -1 si les 16 sont prises."""
        if len(self.palettes) >= 16:
            return -1
        self.added_palettes.append(name)
        self.palettes.append((list(colors) + [0] * 16)[:16])
        return len(self.palettes) - 1

    def replace_added_palette(self, bank: int, name: str, colors: list) -> bool:
        """Remplace la palette ajoutée `bank` par la banque `name` : la peinture suit, c'est la même position."""
        position = self.added_position(bank)
        if position < 0:
            return False
        self.added_palettes[position] = name
        self.palettes[bank] = (list(colors) + [0] * 16)[:16]
        return True

    def remove_palette(self, idx: int) -> None:
        """Retire la palette `idx`. Une palette AJOUTÉE emporte sa référence et sa peinture : un trait ne retombe pas sur
        une autre palette, il disparaît ; les positions suivantes avancent d'un cran."""
        position = self.added_position(idx)
        # Le mixin remappe des numéros de banque ; la peinture et les repeints se rangent par POSITION.
        paint, self.tile_paint = self.tile_paint, {}
        repaint, self.tile_palette_overrides = self.tile_palette_overrides, {}
        super().remove_palette(idx)
        if position >= 0:
            self.added_palettes.pop(position)
            paint = {cell: (color, pal - 1 if pal > position else pal)
                     for cell, (color, pal) in paint.items() if pal != position}
            repaint = {cell: pal - 1 if pal > position else pal for cell, pal in repaint.items() if pal != position}
        self.tile_paint, self.tile_palette_overrides = paint, repaint

    def repaint_bank(self, cell: tuple) -> Optional[int]:
        """Le numéro de banque du repeint de cette case (les dérivées d'abord, puis la position dans `added_palettes`),
        ou None si la case n'est pas repeinte ou que sa palette n'existe plus. Tout ce qui rend ou construit lit ce
        numéro, jamais la position stockée."""
        position = self.tile_palette_overrides.get(cell)
        if position is None or not 0 <= position < len(self.added_palettes):
            return None
        return self.added_bank(position)

    def resolve_palettes(self, lookup=None, kept: Optional[list] = None) -> list:
        """Recompose `palettes` — ce que lisent le rendu et le build — depuis les RÉGLAGES : les palettes dérivées du PNG
        (`source_palettes`), chacune remplacée par sa banque quand elle est overridée, puis les palettes ajoutées.

        `lookup(nom)` rend les couleurs d'une banque du catalogue, ou None si elle n'existe pas. Une banque disparue ne
        casse rien : une ajoutée garde `kept` (ses couleurs en cache), un override garde la couleur du PNG ; le validateur
        le dit. Un override dont la palette dérivée n'existe plus (un nouvel encodage en a moins) est levé : ses indices
        sont rendus. Un fond 8bpp ou bitmap n'a qu'une palette de 256 couleurs : ni ajoutées ni overrides n'y ont de sens."""
        from core.models.gba_color import RESERVED_SLOT_COLOR
        derived = [list(p) for p in self.source_palettes]
        if self.mode == "bitmap" or self.bpp == 8:
            self.palettes = derived
            return []
        dropped = [idx for idx in self.palette_overrides if idx >= len(derived)]
        for idx in dropped:
            del self.palette_overrides[idx]
        for idx, name in self.palette_overrides.items():
            colors = lookup(name) if lookup else None
            if colors is not None:
                derived[idx] = (list(colors) + [0] * 16)[:16]
        added = []
        kept = kept or []
        for position, name in enumerate(self.added_palettes):
            colors = lookup(name) if lookup else None
            if colors is None and position < len(kept):
                colors = kept[position]
            added.append((list(colors) + [0] * 16)[:16] if colors is not None
                         else [RESERVED_SLOT_COLOR] + [0] * 15)
        self.palettes = derived + added
        return dropped

    def painted_cells(self) -> dict:
        """Les cases peintes qui comptent : dans la grille, et seulement en tuilé 4bpp (la peinture
        pose des tuiles pleines d'UNE sous-palette — rien d'équivalent en 8bpp ni en bitmap). La palette de chaque
        trait est rendue en NUMÉRO DE BANQUE (les dérivées d'abord, puis la position dans `added_palettes`) : tout ce
        qui rend ou construit lit ce numéro, jamais la position stockée."""
        if not self.tile_paint or self.mode != "tiled" or self.bpp != 4:
            return {}
        return {cell: (color, self.added_bank(pal)) for cell, (color, pal) in self.tile_paint.items()
                if 0 <= cell[0] < self.tiles_w and 0 <= cell[1] < self.tiles_h and pal < len(self.added_palettes)}

    @staticmethod
    def solid_tile(color: int) -> str:
        return f"{color:x}" * 64

    def effective_tileset(self) -> list:
        """Le tileset tel qu'il part à l'écran et dans la ROM : celui de l'image, puis une tuile pleine par
        couleur peinte (réutilisée si l'image en a déjà une identique). Les ids de la baseline ne bougent pas."""
        tiles, _remapped = self._remapped_tile_variants()
        for color in sorted({c for c, _pal in self.painted_cells().values()}):
            if self.solid_tile(color) not in tiles:
                tiles.append(self.solid_tile(color))
        return tiles

    def effective_tilemap(self) -> list[int]:
        """Tilemap avec les overrides d'inpainting asset appliqués (pal_bank par
        tuile). La baseline `tilemap` n'est jamais modifiée — c'est ce helper que
        consomment le canvas de scène, le canvas du Background Editor et le build,
        pour que l'inpainting soit partagé partout."""
        painted = self.painted_cells()
        if not self.tile_palette_overrides and not painted:
            return list(self.tilemap)
        tw = self.tiles_w or 1
        tiles, remapped = self._remapped_tile_variants()
        if painted:
            for color in sorted({c for c, _pal in painted.values()}):
                if self.solid_tile(color) not in tiles:
                    tiles.append(self.solid_tile(color))
        out: list[int] = []
        for cell, se in enumerate(self.tilemap):
            key = (cell % tw, cell // tw)
            if key in painted:
                color, pal = painted[key]
                out.append(pack_se(tiles.index(self.solid_tile(color)), pal, False, False))
                continue
            tid, pb, fh, fv = unpack_se(se)
            ov = self.repaint_bank(key)
            if key in remapped:
                tid = remapped[key]
            out.append(pack_se(tid, pb if ov is None else ov, fh, fv))
        return out

    def _remapped_tile_variants(self) -> tuple[list, dict]:
        """Tileset de rendu et ID de variante par case repeinte.

        Les tuiles codées restent intactes : les variantes ne vivent que dans
        cette vue effective, exactement comme les tuiles pleines de Paint.
        """
        variants = list(self.tileset)
        if self.color_mapping == "direct" or not self.tile_palette_overrides or self.bpp != 4:
            return variants, {}
        out, mapping_cache = {}, {}
        tw = self.tiles_w or 1
        for cell, se in enumerate(self.tilemap):
            key = (cell % tw, cell // tw)
            target = self.repaint_bank(key)
            if target is None:
                continue
            tid, source, _fh, _fv = unpack_se(se)
            if not (tid < len(self.tileset) and source < len(self.palettes) and target < len(self.palettes)):
                continue
            cache_key = (source, target, self.color_mapping)
            mapping = mapping_cache.get(cache_key)
            if mapping is None:
                mapping = _color_mapping(self.palettes[source], self.palettes[target], self.color_mapping)
                mapping_cache[cache_key] = mapping
            variant = "".join(format(mapping[int(v, 16)], "x") for v in self.tileset[tid])
            if variant not in variants:
                variants.append(variant)
            out[key] = variants.index(variant)
        return variants, out

    def to_dict(self) -> dict:
        d = {"name": self.name}
        # Le kind sort AVANT le bloc de compression et sans condition sur celui-ci :
        # un fond dont le PNG est devenu illisible garde son type, sans quoi il
        # se relirait en décor et quitterait la section où l'auteur l'a rangé.
        if self.kind != KIND_SCENE:
            d["kind"] = self.kind
        if self.kind == KIND_UI:
            d.update({"ui_role": self.ui_role,
                      "slice_left": self.slice_left, "slice_right": self.slice_right,
                      "slice_top": self.slice_top, "slice_bottom": self.slice_bottom})
        if self.kind == KIND_ANIMATED:
            d.update({"frame_w": self.frame_w, "frame_h": self.frame_h,
                      "speed": self.speed, "loop": self.loop,
                      "animation_mode": self.animation_mode})
        if self.animations:
            d["animations"] = [a.to_dict() for a in self.animations]
        if self.asset:
            d["asset"] = self.asset
        # Deux blocs, deux responsabilités. `settings` : ce que l'auteur a décidé (et ses retouches de tuiles) — la vérité,
        # avec le PNG. `encoded` : ce que l'encodage en a tiré — une fonction des réglages et de la source, que le build lit
        # et qu'un nouvel encodage remplace en entier. Rien dans `encoded` ne s'écrit de la main de l'auteur.
        settings = self._settings_dict()
        encoded = self._encoded_dict()
        if settings:
            d["settings"] = settings
        if encoded:
            d["encoded"] = encoded
        return d

    def _settings_dict(self) -> dict:
        """Les RÉGLAGES du fond : layout, préparation de la source (canvas, pose, miroir, ajustements), compression, et
        les retouches de tuiles de l'auteur (clés par case de la grille encodée)."""
        s = {}
        if self.mode != "tiled":
            s["mode"] = self.mode
        if self.bpp != 4:
            s["bpp"] = self.bpp
        if self.dither:
            s["dither"] = True
        if self.quantize_method != "median_cut":
            s["quantize_method"] = self.quantize_method
        if self.canvas_size:
            s["canvas_size"] = list(self.canvas_size)
        if self.image_pos:
            s["image_pos"] = list(self.image_pos)
        if self.image_size:
            s["image_size"] = list(self.image_size)
        if self.mirror_x is not None:
            s["mirror_x"] = self.mirror_x
        if self.mirror_y is not None:
            s["mirror_y"] = self.mirror_y
        if self.mirror_flip_x:
            s["mirror_flip_x"] = True
        if self.mirror_flip_y:
            s["mirror_flip_y"] = True
        if not self.compression.is_default():
            s["compression"] = self.compression.to_dict()
        if not self.adjust.is_default():
            s["adjust"] = self.adjust.to_dict()
        if self.tile_palette_overrides:
            # Une clé À PART de l'ancienne `tile_palette_overrides` (des numéros de banque) : le sens des valeurs a changé.
            s["tile_repaint"] = {
                f"{c},{r}": v for (c, r), v in self.tile_palette_overrides.items()
            }
        if self.color_mapping != "direct":
            s["color_mapping"] = self.color_mapping
        if self.added_palettes:
            s["added_palettes"] = list(self.added_palettes)
        if self.palette_overrides:
            s["palette_overrides"] = {str(i): n for i, n in self.palette_overrides.items()}
        if self.tile_paint:
            s["tile_paint"] = {
                f"{c},{r}": [color, pal] for (c, r), (color, pal) in self.tile_paint.items()
            }
        return s

    def _encoded_dict(self) -> dict:
        """Le RÉSULTAT de l'encodage : ce que le build lit. `source_stamp` dit de quelle version du PNG il vient (il vaut
        autant en tuilé qu'en bitmap). `palettes` y est le CACHE résolu — les dérivées du PNG, leurs overrides, puis les
        ajoutées, dont les couleurs viennent du catalogue (cf. `resolve_palettes`) : un nouvel encodage le refait."""
        e = {}
        if self.source_stamp:
            e["source_stamp"] = self.source_stamp
        if self.encoded_for:
            e["encoded_for"] = self.encoded_for
        if self.tileset:
            # couleurs en #RRGGBB et tilemap rangée en RANGÉES,
            # pour que deux personnes qui retouchent deux zones d'un même fond
            # produisent deux diffs que git sait fusionner. La donnée ne change
            # pas — seule sa forme écrite (cf. core/project_json.py).
            e.update({
                "palettes": write_palettes(self.palettes), "tileset": self.tileset,
                "tilemap": write_grid(self.tilemap, self.tiles_w),
                "tiles_w": self.tiles_w, "tiles_h": self.tiles_h,
            })
            if self.source_palettes:
                e["source_palettes"] = write_palettes(self.source_palettes)
            if self.diagnostics:
                e["diagnostics"] = self.diagnostics
        if self.mode == "bitmap" and self.bitmap:
            e.update({"bitmap": self.bitmap, "out_w": self.out_w, "out_h": self.out_h,
                      "palettes": write_palettes(self.palettes)})
            if self.diagnostics:
                e["diagnostics"] = self.diagnostics
        return e

    @classmethod
    def from_dict(cls, d: dict) -> "BackgroundAsset":
        # Lecture TOLÉRANTE : un sidecar d'avant les deux blocs porte tout à plat, et se lit tel quel ; il est réécrit en
        # `settings` / `encoded` à la prochaine sauvegarde. Les blocs priment sur le plat.
        d = {**d, **(d.get("encoded") or {}), **(d.get("settings") or {})}
        ba = cls(
            name=d.get("name", "background"),
            asset=d.get("asset", d.get("source", "")),   # rétro-compat: ancienne clé "source"
            palettes=read_palettes(d.get("palettes", [])),
            tileset=list(d.get("tileset", [])),
            tilemap=_read_cells(read_grid(d.get("tilemap", []))),
            tiles_w=int(d.get("tiles_w", 0) or 0), tiles_h=int(d.get("tiles_h", 0) or 0),
            quantize_method=d.get("quantize_method", d.get("compress_method", "median_cut")),
            tile_palette_overrides=decode_tile_palette_overrides(d.get("tile_repaint")),
            color_mapping=_read_color_mapping(d.get("color_mapping", d.get("inpaint_mode"))),   # rétro-compat: ancienne clé "inpaint_mode"
            tile_paint=decode_tile_paint(d.get("tile_paint")),
            diagnostics=dict(d.get("diagnostics") or {}),
            source_stamp=str(d.get("source_stamp", "")),
            encoded_for=str(d.get("encoded_for", "")),
            canvas_size=_read_ints(d.get("canvas_size"), (1, 1)),
            image_pos=_read_ints(d.get("image_pos"), (-_POS_LIMIT, -_POS_LIMIT)),
            image_size=_read_ints(d.get("image_size"), (1, 1)),
            mirror_x=_read_axis(d.get("mirror_x")),
            mirror_y=_read_axis(d.get("mirror_y")),
            mirror_flip_x=bool(d.get("mirror_flip_x", False)),
            mirror_flip_y=bool(d.get("mirror_flip_y", False)),
            compression=BackgroundCompression.from_dict(d.get("compression")),
            adjust=BackgroundAdjust.from_dict(d.get("adjust")),
            bpp=int(d.get("bpp", 4)),
            dither=bool(d.get("dither", False)),
            mode=d.get("mode", "tiled"),
            bitmap=d.get("bitmap", ""),
            out_w=int(d.get("out_w", 0)), out_h=int(d.get("out_h", 0)),
            source_palettes=read_palettes(d.get("source_palettes", [])),
            palette_overrides=decode_palette_overrides(d.get("palette_overrides")),
            added_palettes=[str(n) for n in (d.get("added_palettes") or [])],
            kind=_read_kind(d.get("kind")),
            ui_role=_read_ui_role(d.get("ui_role")),
            slice_left=int(d.get("slice_left", 8) or 0),
            slice_right=int(d.get("slice_right", 8) or 0),
            slice_top=int(d.get("slice_top", 8) or 0),
            slice_bottom=int(d.get("slice_bottom", 8) or 0),
            frame_w=max(0, int(d.get("frame_w", 0) or 0)),
            frame_h=max(0, int(d.get("frame_h", 0) or 0)),
            speed=max(1, int(d.get("speed", 8) or 8)),
            loop=bool(d.get("loop", True)),
            animation_mode=_read_animation_mode(d.get("animation_mode")),
            animations=[BackgroundAnimation.from_dict(a)
                        for a in (d.get("animations") or [])],
        )
        # Migration : un fond tuilé sans `source_palettes` (antérieur à l'origine
        # des palettes) prend ses palettes courantes comme baseline dérivée —
        # toutes deviennent grisées/overridables. Idempotent (persisté au save).
        if ba.tileset and not ba.source_palettes and ba.palettes:
            ba.source_palettes = [list(p) for p in ba.palettes]
        # Lecture tolérante : un sidecar d'avant `tile_repaint` porte ses repeints sous l'ancienne clé, en NUMÉROS DE BANQUE.
        # Ceux qui visaient une palette ajoutée passent en position ; ceux qui visaient une palette dérivée du PNG ne
        # peuvent plus exister (on ne repeint qu'avec une palette ajoutée) et sont abandonnés.
        legacy = decode_tile_palette_overrides(d.get("tile_palette_overrides"))
        if legacy and not ba.tile_palette_overrides:
            derived = len(ba.source_palettes)
            ba.tile_palette_overrides = {cell: bank - derived for cell, bank in legacy.items() if bank >= derived}
        return ba


# Stub rétrocompat (importé par d'anciens modules)
@dataclass
class Tileset(Resource):
    name: str = "tileset"
    asset: Optional[str] = None
