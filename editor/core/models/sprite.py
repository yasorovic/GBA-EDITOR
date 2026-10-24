"""SpriteAsset — spritesheet + animations, réutilisable par les Actors.
Stocké dans project/sprites/{name}.json ; référencé par nom depuis Actor.sprite_name."""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.sub_palette import SubPaletteAssetMixin, decode_palette_overrides
from core.models.gba_color import write_colors, read_colors, write_palettes, read_palettes
from core.models import asset_extensions


@dataclass
class TilePlacement:
    """Une tuile 8×8 du spritesheet source placée à une position dans la frame.
    src_col/src_row : position de la tuile source (grille 8px du PNG).
    dst_col/dst_row : position dans la frame composée (grille 8px de la frame).
    flip_h/flip_v : miroir du contenu de la tuile (pas juste sa position) —
    la GBA n'a pas de flip matériel par tuile au sein d'un OBJ composé, donc
    une version retournée est physiquement générée dans le tileset au build.
    """
    src_col: int = 0
    src_row: int = 0
    dst_col: int = 0
    dst_row: int = 0
    flip_h:  bool = False
    flip_v:  bool = False


@dataclass
class AnimFrame:
    """Une frame = composition de tuiles 8×8 peintes depuis le spritesheet source."""
    tiles: list[TilePlacement] = field(default_factory=list)
    # Effet joué en ARRIVANT sur cette frame — un pas de course, un impact.
    # "" = rien.
    #
    # La donnée vit ICI et non dans l'écran Son : un pas appartient au cycle de
    # marche, partout où on le joue. Même règle qu'en v0.4.1, « le placement vit
    # chez l'hôte, la nature de l'animation vit chez l'animé ». L'écran Son en
    # est une seconde porte, pas le propriétaire.
    #
    # LIMITE ASSUMÉE DU MODÈLE : les frames sont dédupliquées au niveau
    # SÉQUENCE (cf. grit_conversion.sprite_unique_frames). Deux directions
    # identiques — une source et son miroir, une source et son omni — partagent
    # donc le même bloc, et l'effet se déclenche pour les deux. C'est ce qu'on
    # VEUT d'un miroir : le pas est le même à gauche et à droite. Deux états
    # qui se trouvent identiques produiront aussi les mêmes effets ; qui veut
    # les différencier renonce au mode miroir et décrit ses directions à la
    # main. Plus de réglages pour l'auteur, mais la limite est dite.
    # Le nom d'une ACTION de la SoundBox — « PlayerWalk » —, jamais un effet
    # concret : c'est l'état courant de la boîte qui dit vers quel échantillon
    # elle pointe. À ne pas confondre avec
    # `SoundFxComponent.sfx_name`, qui référence vraiment un Sfx.
    action_name: str = ""
    # Un Sfx joué DIRECTEMENT en arrivant sur cette frame — pas une action de
    # SoundBox indirecte, le nom d'un Sfx du projet (même espace que
    # `SoundFxComponent.sfx_name`). "" = rien. Cumulable avec `action_name` :
    # les deux sont des emplacements indépendants.
    #
    # NOM DÉLIBÉRÉMENT DIFFÉRENT de `sfx_name` : cette clé JSON est déjà prise
    # — `SpriteAsset.from_dict._parse_frame` la lit en ALIAS hérité de
    # `action_name` (l'ancien nom du champ, avant le renommage de la v0.8.7).
    # Réutiliser `sfx_name` ici aurait fait relire un vieux projet de travers.
    direct_sfx_name: str = ""
    # Le nom d'une fonction déclarée dans le script de l'ACTOR qui utilise ce
    # sprite — appelée en arrivant sur cette frame, comme un Animation Event.
    # Le sprite est un asset partagé : il ne sait pas quel actor l'anime, donc
    # ce nom n'est vérifié qu'au build, contre le script de CHAQUE actor qui
    # réfère ce sprite. "" = rien.
    event_name: str = ""

    def clone(self) -> "AnimFrame":
        """Copie indépendante (nouvelles TilePlacement) — utilisé par la
        timeline du Sprite Editor (copier/dupliquer une frame)."""
        return AnimFrame(tiles=[
            TilePlacement(t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
            for t in self.tiles
        ], action_name=self.action_name, direct_sfx_name=self.direct_sfx_name,
           event_name=self.event_name)


@dataclass
class StateDirection:
    """Une séquence de frames pour une direction donnée d'un AnimState.
    dir=0 : override / omnidirectionnel (affiché quelle que soit la direction).
    dir=1..8 : N, NE, E, SE, S, SW, W, NW.
    mirror_of : si défini, hérite les frames de la direction source + applique flip_h/flip_v.
    """
    dir:       int           = 0
    frames:    list[AnimFrame] = field(default_factory=lambda: [AnimFrame()])
    flip_h:    bool          = False
    flip_v:    bool          = False
    mirror_of: Optional[int] = None


@dataclass
class AnimState:
    name: str = "Idle"
    directions: list[StateDirection] = field(
        default_factory=lambda: [StateDirection()]
    )
    speed: int = 8        # ticks GBA (60fps) entre deux frames
    loop: bool = True


# ──────────────────────────────────────────────────────────────────
#  Miroir de directions — grille 3×3 du DirectionWidget (Sprite Editor)
#  dir id : 0=omni, 1=N, 2=NE, 3=E, 4=SE, 5=S, 6=SW, 7=W, 8=NW
# ──────────────────────────────────────────────────────────────────

# Paires source → miroir horizontal (E→W, NE→NW, SE→SW)
H_MIRROR_PAIRS = [(3, 7), (2, 8), (4, 6)]
# Paires source → miroir vertical (N→S, NE→SE, NW→SW)
V_MIRROR_PAIRS = [(1, 5), (2, 4), (8, 6)]


def resolve_direction_mirrors(active_dirs, h_mirror: bool, v_mirror: bool) -> dict:
    """Pour un ensemble de directions actives, retourne {dst: (src, flip_h, flip_v)}
    des directions dérivées par miroir depuis une direction source active.

    Un dst peut être atteint à la fois par une paire H et une paire V (ex.
    SW=6 : (4,6) en H, (8,6) en V) — dans ce cas src vient de la première
    liste qui matche (H avant V, ordre historique), et flip_h/flip_v sont
    déterminés indépendamment (un dst peut avoir les deux à True)."""
    mirrored: set = set()
    if h_mirror:
        for src, dst in H_MIRROR_PAIRS:
            if src in active_dirs:
                mirrored.add(dst)
    if v_mirror:
        for src, dst in V_MIRROR_PAIRS:
            if src in active_dirs:
                mirrored.add(dst)

    all_pairs = H_MIRROR_PAIRS + V_MIRROR_PAIRS
    result: dict = {}
    for d in mirrored:
        src = next((s for s, dst in all_pairs if dst == d), None)
        fh = any(dst == d for s, dst in H_MIRROR_PAIRS) and h_mirror
        fv = any(dst == d for s, dst in V_MIRROR_PAIRS) and v_mirror
        result[d] = (src, fh, fv)
    return result


# ──────────────────────────────────────────────────────────────────
#  Tailles de frame valides — contrainte hardware OAM (cf. SpriteAsset.oam_size)
# ──────────────────────────────────────────────────────────────────

# Les formats d'IMAGE que l'éditeur sait importer — sprites comme fonds, qui
# passent par le même grit. Déclaré ici pour la même raison que
# `FONT_FILE_EXTS` (models/font.py) et `SFX_FILE_EXTS` (models/audio.py) : le
# type d'asset dit lui-même ce qu'il accepte, et rien d'autre n'a le droit d'en
# tenir une seconde liste — c'est ce qui rendait les polices invisibles au
# ProjectWatcher, qui épelait la sienne.
#
# Un seul format, et c'est délibéré : `.bmp` était accepté ici sans qu'aucun écran, aucun document ni
# aucun test ne s'y réfère — une seconde entrée dans la chaîne d'encodage que
# personne n'empruntait, donc que rien ne vérifiait. Une liste d'un seul élément
# reste une LISTE : c'est elle que le watcher, la table de routage de window.py
# et les passes `reconcile_*` lisent, jamais la chaîne « .png ».
IMAGE_FILE_EXTS = {".png"}

VALID_FRAME_SIZES = {
    8:  [8, 16, 32],
    16: [8, 16, 32],
    32: [8, 16, 32, 64],
    64: [32, 64],
}


def valid_frame_heights(frame_w: int) -> list[int]:
    """Hauteurs de frame valides pour une largeur donnée (formes OAM GBA)."""
    return VALID_FRAME_SIZES.get(frame_w, [8])


@dataclass
class SpriteAsset(SubPaletteAssetMixin, Resource):
    """
    Spritesheet PNG + découpage en frames + états d'animation.
    Stocké dans project/sprites/{name}.json
    Référencé par nom depuis Actor.sprite_name.

    Pas de collision ici : la hitbox est portée par CollisionBoxComponent
    sur l'Actor, pas par le sprite (un même sprite peut être utilisé par
    des actors avec des hitbox différentes).
    """
    sidecar_extension = asset_extensions.SPRITE
    source_field = "asset"
    name: str = "sprite"
    asset: Optional[str] = None
    frame_w: int = 16
    frame_h: int = 16
    states: list[AnimState] = field(default_factory=lambda: [AnimState()])
    # Compression NON-DESTRUCTIVE du sprite : palette propre (couleurs BGR555
    # ordonnées, index 1..N ; index 0 transparent implicite) dérivée du PNG
    # source SANS le modifier, + l'algo qui l'a produite. Source de vérité de
    # l'indexation (preview + build) — cf. core/gba_color.own_palette_from_source.
    # [] = pas encore calculée (migration au chargement).
    own_palette: list = field(default_factory=list)   # list[int] BGR555
    quantize_method: str = "median_cut"
    # Modèle sous-palettes (aligné BackgroundAsset, cf. SubPaletteAssetMixin) = la
    # PAL_BANK du sprite. `palettes` = couleurs EFFECTIVES (forme banque hardware,
    # index 0 réservé), `source_palettes` = baseline PNG restaurable,
    # `palette_overrides` = {idx dérivé -> nom catalogue}. Pendant la transition,
    # `own_palette` reste peuplé (pont de compat build/preview/palette_alloc) =
    # sous-palette primaire sans l'index 0.
    palettes: list = field(default_factory=list)           # list[list[int]] BGR555
    source_palettes: list = field(default_factory=list)    # list[list[int]] BGR555
    palette_overrides: dict = field(default_factory=dict)  # dict[int, str]
    # Empreinte de l'image dont sont tirées les palettes ci-dessus — « ces
    # couleurs viennent de CETTE version du PNG ». Même rôle et mêmes raisons
    # que BackgroundAsset.source_stamp : une date de fichier ne dit pas de façon
    # fiable qu'une planche a été retouchée. Vide = origine inconnue (sprite
    # d'avant ce champ). Cf. core.resources.asset_reconciliation.resync_sprite_png.
    source_stamp: str = ""

    @property
    def tile_w(self) -> int:
        return max(1, self.frame_w // 8)

    @property
    def tile_h(self) -> int:
        return max(1, self.frame_h // 8)

    @property
    def tiles_per_frame(self) -> int:
        return self.tile_w * self.tile_h

    @property
    def oam_shape(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if fw == fh: return 0
        return 1 if fw > fh else 2

    @property
    def oam_size(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if self.oam_shape == 0:
            return {8: 0, 16: 1, 32: 2, 64: 3}.get(fw, 1)
        if self.oam_shape == 1:
            return {(16, 8): 0, (32, 8): 1, (32, 16): 2, (64, 32): 3}.get((fw, fh), 0)
        return {(8, 16): 0, (8, 32): 1, (16, 32): 2, (32, 64): 3}.get((fw, fh), 0)

    @property
    def oam_dims(self) -> tuple[int, int]:
        """Retourne (oam_w, oam_h) : taille OAM valide qui contient ce sprite."""
        sh, sz = self.oam_shape, self.oam_size
        if sh == 0:
            s = [8, 16, 32, 64][sz]
            return (s, s)
        if sh == 1:
            return [(16, 8), (32, 8), (32, 16), (64, 32)][sz]
        return [(8, 16), (8, 32), (16, 32), (32, 64)][sz]

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "asset":   self.asset,
            "frame_w": self.frame_w,
            "frame_h": self.frame_h,
            # Décrit l'image SOURCE, donc hors des blocs conditionnels de
            # palettes ci-dessous — elle vaut même sans encodage réussi.
            **({"source_stamp": self.source_stamp} if self.source_stamp else {}),
            # les couleurs s'écrivent en #RRGGBB — même donnée,
            # relisible par un humain dans un diff (cf. core/gba_color.py).
            **({"own_palette": write_colors(self.own_palette),
                "quantize_method": self.quantize_method} if self.own_palette else {}),
            **({"palettes": write_palettes(self.palettes)} if self.palettes else {}),
            **({"source_palettes": write_palettes(self.source_palettes)}
               if self.source_palettes else {}),
            **({"palette_overrides": {str(i): n for i, n in self.palette_overrides.items()}}
               if self.palette_overrides else {}),
            "states": [
                {
                    "name":  s.name,
                    "speed": s.speed,
                    "loop":  s.loop,
                    "directions": [
                        {
                            "dir":    sd.dir,
                            "frames": [
                                {
                                    "tiles": [
                                        {"src_col": t.src_col, "src_row": t.src_row,
                                         "dst_col": t.dst_col, "dst_row": t.dst_row,
                                         **({"flip_h": True} if t.flip_h else {}),
                                         **({"flip_v": True} if t.flip_v else {})}
                                        for t in f.tiles
                                    ],
                                    **({"action_name": f.action_name} if f.action_name else {}),
                                    **({"direct_sfx_name": f.direct_sfx_name} if f.direct_sfx_name else {}),
                                    **({"event_name": f.event_name} if f.event_name else {}),
                                }
                                for f in sd.frames
                            ],
                            **({"flip_h":    True} if sd.flip_h    else {}),
                            **({"flip_v":    True} if sd.flip_v    else {}),
                            **({"mirror_of": sd.mirror_of} if sd.mirror_of is not None else {}),
                        }
                        for sd in s.directions
                    ],
                }
                for s in self.states
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpriteAsset":
        frame_w = d.get("frame_w", 16)
        frame_h = d.get("frame_h", 16)
        tile_w  = max(1, frame_w // 8)
        tile_h  = max(1, frame_h // 8)

        def _parse_frame(f: dict) -> AnimFrame:
            if "tiles" in f:
                return AnimFrame(tiles=[
                    TilePlacement(
                        src_col=t.get("src_col", 0), src_row=t.get("src_row", 0),
                        dst_col=t.get("dst_col", 0), dst_row=t.get("dst_row", 0),
                        flip_h=t.get("flip_h", False), flip_v=t.get("flip_v", False),
                    )
                    for t in f["tiles"]
                ], action_name=f.get("action_name", f.get("sfx_name", "")),
                   # `direct_sfx_name`/`event_name` : pas de
                   # legacy à migrer, ce sont de nouveaux champs.
                   direct_sfx_name=f.get("direct_sfx_name", ""),
                   event_name=f.get("event_name", ""))
            # Migration ancien format {col, row} → bloc plein de tuiles 8×8
            old_col, old_row = f.get("col", 0), f.get("row", 0)
            return AnimFrame(tiles=[
                TilePlacement(
                    src_col=old_col * tile_w + tx, src_row=old_row * tile_h + ty,
                    dst_col=tx, dst_row=ty,
                )
                for ty in range(tile_h) for tx in range(tile_w)
            ])

        def _parse_state(s: dict) -> AnimState:
            if "directions" in s:
                directions = [
                    StateDirection(
                        dir       = sd.get("dir", 0),
                        frames    = [_parse_frame(f)
                                     for f in sd.get("frames", [{}])] or [AnimFrame()],
                        flip_h    = sd.get("flip_h", False),
                        flip_v    = sd.get("flip_v", False),
                        mirror_of = sd.get("mirror_of", None),
                    )
                    for sd in s["directions"]
                ] or [StateDirection()]
            else:
                directions = [StateDirection(
                    dir    = 0,
                    frames = [_parse_frame(f) for f in s.get("frames", [{}])] or [AnimFrame()],
                )]
            return AnimState(
                name       = s.get("name", "Idle"),
                directions = directions,
                speed      = s.get("speed", 8),
                loop       = s.get("loop", True),
            )

        states = [_parse_state(s) for s in d.get("states", [])] or [AnimState()]
        sprite = cls(
            name      = d.get("name", "sprite"),
            asset     = d.get("asset"),
            frame_w   = frame_w,
            frame_h   = frame_h,
            states    = states,
            own_palette     = read_colors(d.get("own_palette", [])),
            quantize_method = d.get("quantize_method", d.get("compress_method", "median_cut")),
            palettes          = read_palettes(d.get("palettes", [])),
            source_palettes   = read_palettes(d.get("source_palettes", [])),
            palette_overrides = decode_palette_overrides(d.get("palette_overrides")),
            source_stamp      = str(d.get("source_stamp", "")),
        )
        # Migration : un sprite sans `palettes` (antérieur au modèle sous-palettes)
        # dérive sa PAL_BANK de son `own_palette` (forme banque hardware : index 0
        # réservé + couleurs propres). Idempotent (persisté au save).
        if not sprite.palettes and sprite.own_palette:
            from core.models.gba_color import RESERVED_SLOT_COLOR
            bank = ([RESERVED_SLOT_COLOR] + list(sprite.own_palette))[:16]
            bank += [0] * (16 - len(bank))
            sprite.palettes = [bank]
            sprite.source_palettes = [list(bank)]
        return sprite
