"""codegen/bg_anim.py — fonds ANIMÉS posés sur un fond hôte, côté build.

Un `BackgroundAsset` de kind `animated` est une planche découpée en grille, posée
à une position d'un fond hôte (cf. `BackgroundAnimation`, dont le placement vit
chez l'HÔTE). Ce module traduit ce modèle d'authoring en ce que la ROM demande.

## L'animé se pose SUR le décor, il ne le remplace pas

Une case de tilemap ne porte qu'une tuile : poser un animé écraserait donc le
décor sur tout son rectangle englobant, et sa transparence percerait jusqu'au
fond d'écran. On fabrique à la place la **tuile fusionnée** — pixel de l'animé
là où il peint, pixel du décor là où il est transparent, transparence seulement
là où les deux le sont. Le décor derrière un arbre reste visible ; un arbre posé
sur un trou du décor laisse toujours voir le calque du dessous.

Deux conséquences à ne pas perdre de vue :

- **Les tuiles dépendent de ce qu'il y a dessous.** Deux copies ne partagent
  leurs tuiles que si le décor sous elles est identique — la déduplication le
  rattrape sans qu'on ait à le dire, mais une forêt sur un décor varié coûte
  vraiment plus cher qu'une forêt sur un fond uni.
- **La sous-palette est SYNTHÉTISÉE.** L'hôte et l'animé ont chacun la leur, une
  tuile fusionnée pioche dans les deux ; elle ne peut donc être ni l'une ni
  l'autre. Au-delà de 15 couleurs, le build BLOQUE (cf. `compose_placement`).

## Les deux modes

- `instance` : les entrées de carte du rectangle sont réécrites, toutes les
  images restent résidentes. Chaque copie a son compteur, donc sa propre cadence
  et son image de départ.
- `shared` : les pixels de la tuile sont réécrits, une seule image est résidente,
  et toute case qui l'utilise change avec elle — c'est la définition du procédé.

**Les tuiles de l'animé vivent dans le charblock de son HÔTE**, après les
siennes : une entrée de carte adresse les tuiles depuis la base du charblock,
pas depuis un asset. D'où `tile_base`. Un animé pèse donc sur le budget de tuiles
du calque hôte (cf. `layer_tile_count`, lu par le garde-fou de `pipeline` et par
l'allocateur de `main_gen`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.models.background import KIND_ANIMATED, ANIM_INSTANCE, ANIM_SHARED
from codegen.c_names import sym as c_sym
from core.models.tile_codec import unpack_se, pack_se, hex_to_tile, flip_h, flip_v

MAX_TILE_COLORS = 15    # 16 index par sous-palette, le 0 étant transparent


@dataclass
class PlacedAnim:
    """Un placement RÉSOLU, prêt à émettre : géométrie en tuiles déjà rognée aux
    bords de l'hôte, et cadence telle que l'auteur l'a réglée."""
    host_name: str
    anim_name: str
    col: int          # position dans la carte de l'hôte, en tuiles
    row: int
    cols: int         # taille VISIBLE (rognée) du rectangle, en tuiles
    rows: int
    src_col: int      # décalage dans l'image quand le rognage mord à gauche/en haut
    src_row: int
    frames: int
    speed: int        # ticks 60 Hz entre deux images
    loop: bool
    start_frame: int = 0   # image de départ de CETTE copie

    @property
    def cells(self) -> int:
        return self.cols * self.rows

    def start_state(self) -> tuple[int, int]:
        """(image de départ, ticks déjà écoulés dedans). Ramenée dans la planche :
        une image de départ hors bornes reboucle plutôt que d'afficher du vide."""
        return (max(0, self.start_frame) % max(1, self.frames), 0)


@dataclass
class ComposedAnim:
    """Le résultat de la fusion avec le décor, pour UN placement.

    `tiles` est dédupliqué ; `order` donne, pour chaque (image, case), l'index de
    sa tuile. Deux cases entièrement transparentes au-dessus du même décor
    partagent ainsi une tuile, ce qui rattrape l'essentiel du coût."""
    tiles: list          # tuiles hex UNIQUES
    order: list          # frames × cells -> index dans `tiles`
    palette: list        # 16 couleurs BGR555, index 0 transparent
    colors_used: int

    def frame_tiles(self, f: int, cells: int) -> list:
        """Tuiles de l'image `f`, dans l'ordre des cases (mode `shared`)."""
        return [self.tiles[i] for i in self.order[f * cells:(f + 1) * cells]]


def _is_emittable(ba) -> bool:
    """Un animé émissible : tuilé 4bpp, compressé, et découpé en au moins une
    image. Le bitmap (Mode 4) n'a pas de tuiles à poser dans une carte ; le 8bpp
    n'a pas de sous-palettes à synthétiser."""
    return bool(ba is not None
                and getattr(ba, "kind", "") == KIND_ANIMATED
                and getattr(ba, "mode", "tiled") == "tiled"
                and getattr(ba, "bpp", 4) == 4
                and getattr(ba, "tileset", None)
                and ba.frame_count() >= 1)


def is_shared(ba) -> bool:
    return getattr(ba, "animation_mode", ANIM_INSTANCE) == ANIM_SHARED


def frame_cell_grid(anim_ba) -> tuple[int, int]:
    """(colonnes, rangées) de tuiles d'UNE image, avant rognage."""
    fw, fh = anim_ba.frame_size()
    return (fw // 8, fh // 8)


def host_placements(p, host_ba, on_skip=None) -> list:
    """(placement, animé) retenus pour cet hôte, dans l'ordre de pose.

    `on_skip(nom, raison)` est appelé pour chaque placement écarté — le build en
    fait une ligne de log. Un placement muet serait le pire des cas : l'auteur
    voit son animé sur le canvas et pas dans la ROM, sans rien pour le relier."""
    out = []
    for pl in getattr(host_ba, "animations", None) or []:
        name = getattr(pl, "animated_name", "")
        if not name:
            continue
        ba = p.get_background(name)
        if not _is_emittable(ba):
            if on_skip:
                on_skip(name, "not an animated sheet encoded as tiled 4bpp")
            continue
        out.append((pl, ba))
    return out


def compose_placement(host_ba, anim_ba, geom: PlacedAnim) -> tuple:
    """(ComposedAnim, erreur) — la seconde non vide si la fusion est impossible.

    Refuser plutôt qu'approximer : ramener les couleurs du décor vers la palette
    de l'animé marcherait toujours et ferait changer les couleurs du décor sans
    un mot. C'est la dégradation silencieuse que la v0.2 a écartée.

    Les miroirs sont résolus dans les pixels — la tuile fusionnée est neuve, elle
    n'a aucune raison d'hériter des bits de miroir de ses deux sources."""
    def _grid(tiles, tilemap, tw, cell):
        if not 0 <= cell < len(tilemap):
            return tuple([0] * 64), 0
        tid, pb, fh, fv = unpack_se(tilemap[cell])
        g = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            g = flip_h(g)
        if fv:
            g = flip_v(g)
        return g, pb

    htiles = [hex_to_tile(t) for t in host_ba.tileset]
    atiles = [hex_to_tile(t) for t in anim_ba.tileset]
    hmap, amap = host_ba.effective_tilemap(), anim_ba.effective_tilemap()
    htw, atw = host_ba.tiles_w or 1, anim_ba.tiles_w or 1

    # 1ʳᵉ passe : les couleurs réellement employées, sur TOUT le placement et
    # toutes les images — la palette ne change pas en cours de lecture, une
    # couleur qui n'apparaît qu'à la 4ᵉ image doit y être.
    order_cols: list = []
    seen_cols: set = set()
    cells_rgb: list = []
    for f in range(geom.frames):
        fx, fy, _w, _h = anim_ba.frame_rect(f)
        for r in range(geom.rows):
            for c in range(geom.cols):
                ag, apb = _grid(atiles, amap, atw,
                                (fy // 8 + geom.src_row + r) * atw
                                + (fx // 8 + geom.src_col + c))
                hg, hpb = _grid(htiles, hmap, htw,
                                (geom.row + r) * htw + (geom.col + c))
                apal = anim_ba.palettes[apb] if apb < len(anim_ba.palettes) else []
                hpal = host_ba.palettes[hpb] if hpb < len(host_ba.palettes) else []
                cell = []
                for i in range(64):
                    if ag[i] and ag[i] < len(apal):
                        col = apal[ag[i]]      # l'animé peint
                    elif hg[i] and hg[i] < len(hpal):
                        col = hpal[hg[i]]      # il est transparent : le décor reste
                    else:
                        cell.append(0)         # transparent des DEUX côtés
                        continue
                    if col not in seen_cols:
                        seen_cols.add(col)
                        order_cols.append(col)
                    cell.append(col)
                cells_rgb.append(cell)

    if len(order_cols) > MAX_TILE_COLORS:
        return None, (f"{len(order_cols)} distinct colours once merged with the scenery (maximum "
                      f"{MAX_TILE_COLORS} per sub-palette)")

    # 2ᵈᵉ passe : réindexation sur la palette synthétisée + déduplication.
    idx = {col: i + 1 for i, col in enumerate(order_cols)}
    tiles: list = []
    pos: dict = {}
    order: list = []
    for cell in cells_rgb:
        hexed = "".join(f"{(idx[v] if v else 0):x}" for v in cell)
        if hexed not in pos:
            pos[hexed] = len(tiles)
            tiles.append(hexed)
        order.append(pos[hexed])
    pal = [0] + order_cols
    return ComposedAnim(tiles=tiles, order=order,
                        palette=pal + [0] * (16 - len(pal)),
                        colors_used=len(order_cols)), ""


def placement_geometry(host_ba, anim_ba, pl) -> Optional[PlacedAnim]:
    """Géométrie en TUILES d'un placement, rognée à la carte de l'hôte, ou None
    s'il n'en reste rien de visible.

    La position est stockée en pixels (le calage sur la grille 8×8 est un geste
    du canvas, pas un format) : on la ramène ici à la tuile inférieure, seule
    unité qu'une carte sache adresser."""
    cols, rows = frame_cell_grid(anim_ba)
    if cols <= 0 or rows <= 0:
        return None
    col, row = int(pl.x) // 8, int(pl.y) // 8

    src_col, src_row = max(0, -col), max(0, -row)
    vis_col, vis_row = max(0, col), max(0, row)
    vis_cols = min(col + cols, host_ba.tiles_w) - vis_col
    vis_rows = min(row + rows, host_ba.tiles_h) - vis_row
    if vis_cols <= 0 or vis_rows <= 0:
        return None

    return PlacedAnim(
        host_name=host_ba.name, anim_name=anim_ba.name,
        col=vis_col, row=vis_row, cols=vis_cols, rows=vis_rows,
        src_col=src_col, src_row=src_row,
        frames=anim_ba.frame_count(),
        # Cadence PROPRE À LA COPIE (surcharge, ou celle de l'animé) : deux
        # copies à des vitesses différentes sont deux animations distinctes.
        speed=pl.effective_speed(anim_ba),
        loop=bool(anim_ba.loop),
        start_frame=max(0, int(getattr(pl, "start_frame", 0) or 0)),
    )


@dataclass
class AnimBlock:
    """Un bloc de tuiles réservé dans le charblock de l'hôte, et la sous-palette
    qui va avec. Partagé par tous les placements dont la fusion donne exactement
    le même résultat — même animé, même décor dessous."""
    key: tuple
    composed: ComposedAnim
    shared: bool
    cells: int          # cases du rectangle rogné (taille du bloc en `shared`)
    tile_base: int = 0

    @property
    def size(self) -> int:
        """Tuiles réservées, et les deux modes n'en réservent pas le même nombre :

        - `instance` : le bloc DÉDUPLIQUÉ de toutes les images, puisqu'elles
          résident toutes et que la carte se contente de pointer l'une d'elles ;
        - `shared` : une case = un emplacement DÉDIÉ, sans déduplication. Une case
          dont on réécrit les pixels ne peut pas partager sa tuile avec une autre
          — ce serait faire changer sa voisine en même temps."""
        return self.cells if self.shared else len(self.composed.tiles)

    def initial_tiles(self) -> list:
        """Contenu du bloc au chargement : la 1ʳᵉ image en `shared` (le reste
        arrive par recopie), le bloc entier en `instance`."""
        return (self.composed.frame_tiles(0, self.cells) if self.shared
                else self.composed.tiles)


def resolve_blocks(p, host_ba, on_error=None) -> tuple:
    """(blocs dans l'ordre d'allocation, {id(placement): bloc}).

    Point de calcul UNIQUE : la taille du charblock, l'allocation des palettes,
    l'émission et les descripteurs le relisent tous, et diverger ferait pointer
    une carte sur des tuiles qui ne sont pas là."""
    blocks: list = []
    by_key: dict = {}
    for_pl: dict = {}
    for pl, ba in host_placements(p, host_ba):
        geom = placement_geometry(host_ba, ba, pl)
        if geom is None:
            continue
        composed, err = compose_placement(host_ba, ba, geom)
        if composed is None:
            if on_error:
                on_error(ba.name, geom, err)
            continue
        # Deux copies identiques (même animé, même décor dessous, même rognage)
        # donnent exactement les mêmes tuiles : un seul bloc les sert.
        key = (ba.name, is_shared(ba), tuple(composed.tiles),
               tuple(composed.order), tuple(composed.palette))
        blk = by_key.get(key)
        if blk is None:
            blk = AnimBlock(key=key, composed=composed, shared=is_shared(ba),
                            cells=geom.cells)
            by_key[key] = blk
            blocks.append(blk)
        for_pl[id(pl)] = blk
    base = len(getattr(host_ba, "tileset", None) or [])
    for blk in blocks:
        blk.tile_base = base
        base += blk.size
    return blocks, for_pl


def host_blocks(p, host_ba, on_error=None) -> list:
    return resolve_blocks(p, host_ba, on_error)[0]


def merged_tileset(p, host_ba) -> list:
    """Tileset du CHARBLOCK : celui de l'hôte, puis un bloc par fusion distincte.
    Les tuiles de l'hôte d'abord — ainsi sa propre carte, émise sans décalage,
    reste valable telle quelle."""
    tiles = list(getattr(host_ba, "tileset", None) or [])
    for blk in host_blocks(p, host_ba):
        tiles += blk.initial_tiles()
    return tiles


def layer_tile_count(p, host_ba) -> int:
    """Tuiles réellement chargées dans le charblock du calque : les siennes plus
    celles des fusions. C'est CE nombre que le budget doit voir — compter le seul
    hôte laisserait l'animé déborder sur le voisin sans erreur à l'exécution."""
    return len(merged_tileset(p, host_ba))


def host_palettes(p, host_ba) -> list:
    """Sous-palettes synthétisées par les fusions de cet hôte, dédupliquées."""
    out, seen = [], set()
    for blk in host_blocks(p, host_ba):
        key = tuple(blk.composed.palette)
        if key not in seen:
            seen.add(key)
            out.append(list(blk.composed.palette))
    return out


def scene_anim_sym(scene) -> str:
    """Symbole du fichier C qui porte les tables d'images de cette scène."""
    return c_sym(f"{scene.name}_bganim")


def anim_table_sym(scene, index: int) -> str:
    """Symbole d'une table d'entrées de carte (mode `instance`)."""
    return f"{scene_anim_sym(scene)}_{index}"


def shared_anim_sym(scene) -> str:
    return c_sym(f"{scene.name}_bgtileanim")


def shared_table_sym(scene, index: int) -> str:
    return f"{shared_anim_sym(scene)}_{index}"


def scene_animations(p, scene, on_skip=None, on_error=None) -> list:
    """Tous les placements émissibles de la scène, calque par calque."""
    out = []
    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        host = p.get_background(layer.background_name)
        if host is None or not getattr(host, "tileset", None):
            continue
        _blocks, for_pl = resolve_blocks(p, host, on_error)
        for pl, ba in host_placements(p, host, on_skip):
            geom = placement_geometry(host, ba, pl)
            blk = for_pl.get(id(pl))
            if geom is None or blk is None:
                if on_skip and geom is None:
                    on_skip(ba.name, "placed outside the host background")
                continue
            out.append({"layer": layer, "host": host, "anim": ba, "geom": geom,
                        "block": blk, "shared": blk.shared})
    # Index de table par mode, attribué à la première apparition — stable, et
    # identique des deux côtés (pipeline émet, main_gen déclare).
    seen: dict = {}
    for a in out:
        k = (a["shared"], a["block"].key)
        if k not in seen:
            seen[k] = sum(1 for kk in seen if kk[0] == a["shared"])
        a["table_index"] = seen[k]
    return out


def scene_anim_tables(p, scene, shared: bool) -> list:
    """Un placement représentatif par table d'un mode, dans l'ordre des index."""
    out: list = []
    for a in scene_animations(p, scene):
        if bool(a["shared"]) == shared and a["table_index"] == len(out):
            out.append(a)
    return out


def frame_table(a: dict, pal_bank: int) -> list:
    """Entrées de carte de TOUTES les images (mode `instance`), à la suite :
    image 0 puis 1, chacune balayée par rangées. Tuile décalée du `tile_base` du
    bloc, banque = celle allouée à la sous-palette synthétisée, miroirs nuls (ils
    sont résolus dans les pixels de la tuile fusionnée)."""
    blk, geom = a["block"], a["geom"]
    base = blk.tile_base
    return [pack_se(base + t, pal_bank, 0, 0) for t in blk.composed.order]


def shared_frame_tiles(a: dict) -> list:
    """Pixels de toutes les images (mode `shared`), image par image puis case par
    case. Une case garde son emplacement, c'est son CONTENU qui change."""
    blk, geom = a["block"], a["geom"]
    return [t for f in range(geom.frames)
            for t in blk.composed.frame_tiles(f, geom.cells)]


def bake_shared_map(p, host_ba, tilemap: list, pal_offsets: dict) -> list:
    """Carte de l'hôte avec les rectangles des animés `shared` déjà pointés sur
    leur bloc réservé.

    En `shared` la carte ne change JAMAIS : ses entrées sont cuites dans la ROM,
    et le runtime n'a plus que des pixels à recopier. Elles vivent dans la carte
    de l'hôte et non dans une passe d'init parce que le placement est une
    propriété de l'hôte — toute scène qui affiche ce fond affiche ses animés."""
    out = list(tilemap)
    tw = host_ba.tiles_w or 1
    _blocks, for_pl = resolve_blocks(p, host_ba)
    for pl, ba in host_placements(p, host_ba):
        blk = for_pl.get(id(pl))
        if blk is None or not blk.shared:
            continue
        geom = placement_geometry(host_ba, ba, pl)
        if geom is None:
            continue
        bank = pal_offsets.get(tuple(blk.composed.palette), 0)
        for r in range(geom.rows):
            for c in range(geom.cols):
                cell = r * geom.cols + c
                dst = (geom.row + r) * tw + (geom.col + c)
                if 0 <= dst < len(out):
                    # Une case = son emplacement dédié, invariable : c'est le
                    # CONTENU de cet emplacement que le runtime réécrit.
                    out[dst] = pack_se(blk.tile_base + cell, bank, 0, 0)
    return out
