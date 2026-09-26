"""BackgroundLayer / BackgroundAsset.
BackgroundImage = simple PNG dans assets/backgrounds/ (pas de JSON).
BackgroundAsset = sidecar d'import dans assets/backgrounds/{name}.json (à côté du PNG)."""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.tile_codec import pack_se, unpack_se
from core.models.palette import OWN_PAL_BANK
from core.models.sub_palette import SubPaletteAssetMixin, decode_palette_overrides
from core.models.gba_color import write_palettes, read_palettes
from core.models.project_json import write_grid, read_grid


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


def _read_ui_role(raw) -> str:
    return raw if raw in UI_ROLES else UI_ROLE_NINE


def _read_animation_mode(raw) -> str:
    """Même parti pris que `_read_kind` : un mode inconnu se relit au DÉFAUT
    plutôt qu'en erreur. Un fichier écrit par une version plus récente reste
    ouvrable, et l'auteur voit dans l'inspecteur ce que le build fera."""
    return raw if raw in ANIM_MODES else ANIM_INSTANCE


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
        )


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
    """Sidecar d'import d'UNE image de fond — assets/backgrounds/{stem}.json, à côté
    du PNG et keyé par son nom (comme SpriteAsset). Le PNG source n'est jamais modifié.
    C'est la SCÈNE qui possède ses layers (Scene.background_layers) et référence
    ce fond par nom — plus de composition multi-layer réutilisable ici."""
    name:   str  = "background"                     # = stem du PNG source
    asset:   str  = ""                              # PNG dans assets/backgrounds/ (convention .asset, cf. SpriteAsset)
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
    # Analogue à BackgroundLayer.tile_palette_overrides mais au niveau de l'asset.
    tile_palette_overrides: dict = field(default_factory=dict)  # dict[(col,row), pal_index]
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
    # Préparation de la source AVANT encodage — le PNG reste intact, c'est
    # l'image en mémoire qu'on recadre puis redimensionne (cf.
    # bg_import.prepare_source). `import_crop` = (x, y, w, h) en pixels du PNG ;
    # `import_size` = (w, h) de l'image préparée, appliqué APRÈS le recadrage.
    # None = pas de préparation (« Original »).
    import_crop: Optional[tuple] = None
    import_size: Optional[tuple] = None
    # Réglages de l'encodage tuilé 4bpp (cf. BackgroundCompression).
    compression: BackgroundCompression = field(default_factory=BackgroundCompression)
    # Origine des sous-palettes pour l'éditeur (modèle scène : grisé + override).
    # `source_palettes` = snapshot des palettes DÉRIVÉES du PNG à la compression
    # (baseline restaurable). Les indices < len(source_palettes) sont dérivés
    # (grisés/overridables) ; les suivants sont ajoutés depuis le catalogue
    # (éditables). `ba.palettes` reste les couleurs EFFECTIVES (rendu/build
    # inchangés) : une dérivée overridée a ses couleurs = celles du catalogue et
    # son index figure dans `palette_overrides` (idx -> nom de banque catalogue).
    source_palettes: list = field(default_factory=list)    # list[list[int]] BGR555
    palette_overrides: dict = field(default_factory=dict)  # dict[int, str]

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

    def image_name(self) -> str:
        return self.asset

    def import_prep(self) -> dict:
        """La préparation de la source, sous la forme que prend `bg_import` —
        les DEUX appelants qui encodent (worker de l'éditeur, chemin synchrone
        de la réconciliation) la lisent ici, pour ne jamais diverger."""
        return {"crop": self.import_crop, "size": self.import_size}

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

    def effective_tilemap(self) -> list[int]:
        """Tilemap avec les overrides d'inpainting asset appliqués (pal_bank par
        tuile). La baseline `tilemap` n'est jamais modifiée — c'est ce helper que
        consomment le canvas de scène, le canvas du Background Editor et le build,
        pour que l'inpainting soit partagé partout."""
        if not self.tile_palette_overrides:
            return list(self.tilemap)
        tw = self.tiles_w or 1
        out: list[int] = []
        for cell, se in enumerate(self.tilemap):
            tid, pb, fh, fv = unpack_se(se)
            ov = self.tile_palette_overrides.get((cell % tw, cell // tw))
            out.append(pack_se(tid, pb if ov is None else ov, fh, fv))
        return out

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
        # Hors des branches ci-dessous : l'empreinte décrit l'IMAGE SOURCE, pas
        # la forme de l'encodage — elle vaut autant en tuilé qu'en bitmap.
        if self.source_stamp:
            d["source_stamp"] = self.source_stamp
        if self.import_crop:
            d["import_crop"] = list(self.import_crop)
        if self.import_size:
            d["import_size"] = list(self.import_size)
        if not self.compression.is_default():
            d["compression"] = self.compression.to_dict()
        if self.tileset:
            # ROADMAP v0.24 : couleurs en #RRGGBB et tilemap rangée en RANGÉES,
            # pour que deux personnes qui retouchent deux zones d'un même fond
            # produisent deux diffs que git sait fusionner. La donnée ne change
            # pas — seule sa forme écrite (cf. core/project_json.py).
            d.update({
                "palettes": write_palettes(self.palettes), "tileset": self.tileset,
                "tilemap": write_grid(self.tilemap, self.tiles_w),
                "tiles_w": self.tiles_w,
                "tiles_h": self.tiles_h, "quantize_method": self.quantize_method,
            })
            if self.tile_palette_overrides:
                d["tile_palette_overrides"] = {
                    f"{c},{r}": s for (c, r), s in self.tile_palette_overrides.items()
                }
            if self.source_palettes:
                d["source_palettes"] = write_palettes(self.source_palettes)
            if self.palette_overrides:
                d["palette_overrides"] = {
                    str(i): n for i, n in self.palette_overrides.items()
                }
            if self.diagnostics:
                d["diagnostics"] = self.diagnostics
            if self.bpp != 4:
                d["bpp"] = self.bpp
            if self.dither:
                d["dither"] = True
        if self.mode == "bitmap" and self.bitmap:
            d.update({
                "mode": "bitmap", "bitmap": self.bitmap,
                "out_w": self.out_w, "out_h": self.out_h,
                "palettes": write_palettes(self.palettes),
            })
            if self.diagnostics:
                d["diagnostics"] = self.diagnostics
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BackgroundAsset":
        ba = cls(
            name=d.get("name", "background"),
            asset=d.get("asset", d.get("source", "")),   # rétro-compat: ancienne clé "source"
            palettes=read_palettes(d.get("palettes", [])),
            tileset=list(d.get("tileset", [])),
            tilemap=read_grid(d.get("tilemap", [])),
            tiles_w=d.get("tiles_w", 0), tiles_h=d.get("tiles_h", 0),
            quantize_method=d.get("quantize_method", d.get("compress_method", "median_cut")),
            tile_palette_overrides=decode_tile_palette_overrides(
                d.get("tile_palette_overrides")),
            diagnostics=dict(d.get("diagnostics") or {}),
            source_stamp=str(d.get("source_stamp", "")),
            import_crop=_read_ints(d.get("import_crop"), (0, 0, 1, 1)),
            import_size=_read_ints(d.get("import_size"), (1, 1)),
            compression=BackgroundCompression.from_dict(d.get("compression")),
            bpp=int(d.get("bpp", 4)),
            dither=bool(d.get("dither", False)),
            mode=d.get("mode", "tiled"),
            bitmap=d.get("bitmap", ""),
            out_w=int(d.get("out_w", 0)), out_h=int(d.get("out_h", 0)),
            source_palettes=read_palettes(d.get("source_palettes", [])),
            palette_overrides=decode_palette_overrides(d.get("palette_overrides")),
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
        return ba


# Stub rétrocompat (importé par d'anciens modules)
@dataclass
class Tileset(Resource):
    name: str = "tileset"
    asset: Optional[str] = None
