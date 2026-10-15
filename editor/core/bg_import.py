"""core/bg_import.py — import & encodage d'un fond GBA (Mode 0, 4bpp).

Encode un PNG de fond en sa représentation matérielle GBA, stockée en métadonnées
(le PNG source n'est jamais modifié) — opération NON-DESTRUCTIVE pour un asset déjà
GBA-compatible (palette indexée préservée à l'identique) :
- jusqu'à 16 palettes de 16 couleurs (256), sélection par tuile ;
- un tileset de tuiles 8×8 UNIQUES (dédup + flips H/V) — c'est la dédup qui fait
  rentrer un grand niveau en VRAM ;
- une tilemap de SE (screen entries) : (tile_id, pal_bank, flip_h, flip_v) par case.

Une QUANTIFICATION des couleurs (réduction destructive) n'intervient qu'en repli,
quand la source n'est PAS déjà indexée/compatible (trop de couleurs) — cf.
`encode_background` et `reduce_colors`. Toutes les couleurs sont snappées en 5 bits
par canal (représentables en BGR555) dès l'extraction, donc la dédup couleur est
exacte vis-à-vis du hardware.
"""
from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Optional

from core.models.gba_color import (
    reduce_colors, nearest_rgb, rgb888_to_bgr555, bgr555_to_rgb888,
    COMPRESSION_METHODS,
)
from core.models.gba_color import RESERVED_SLOT_COLOR
from core.models.background import BackgroundCompression, BITMAP_SIZE
from core.bg_tile_merge import merge_tiles
from core.bg_palette_cluster import cluster_palettes

# Le format binaire lui-même (tuile <-> hex, miroirs, entrée de carte) vit
# dans son propre module : les modèles, la génération et le canvas en ont
# besoin autant que cet import-ci, et le laisser ici les faisait tous
# remonter jusqu'à la couche import de l'éditeur.
from core.models.tile_codec import (
    tile_to_hex, hex_to_tile, tile_to_hex8, hex_to_tile8,
    flip_h, flip_v, pack_se, unpack_se,
)

TILE_BUDGET = 512        # tuiles 4bpp par charblock (16 Ko)
TILE_BUDGET_8BPP = 256   # tuiles 8bpp par charblock (2× la taille → moitié moins)
GBA_SCREEN_W, GBA_SCREEN_H = BITMAP_SIZE


class BackgroundWorkCache:
    """Cache borné des étapes invariantes d'une compression interactive.

    Il appartient à un écran Background Editor (il n'est donc jamais sérialisé).
    Une modification de palettes ou de cible de tuiles réutilise l'image préparée
    et la liste des couleurs par tuile ; modifier seulement la cible réutilise
    aussi le regroupement de palettes et la déduplication. Une modification de la
    source, du canvas, de l'ajustement ou de la réduction globale produit
    naturellement une autre clé.
    Les workers Qt peuvent le consulter : les accès sont protégés, et les valeurs
    stockées ne sont ensuite lues que par les encodeurs.
    """

    def __init__(self, prepared_limit: int = 2, tiles_limit: int = 3):
        self._prepared_limit = prepared_limit
        self._tiles_limit = tiles_limit
        self._prepared = OrderedDict()
        self._tiles = OrderedDict()
        self._lock = RLock()

    @staticmethod
    def _source_key(source):
        if hasattr(source, "mode"):
            return None
        try:
            path = Path(source)
            stat = path.stat()
        except (OSError, TypeError, ValueError):
            return None
        return str(path.resolve()), stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _prep_key(prep: dict) -> tuple:
        adjust = prep.get("adjust")
        return (prep.get("canvas"), prep.get("pos"), prep.get("size"),
                prep.get("mirror"),
                (getattr(adjust, "hue", 0), getattr(adjust, "saturation", 0),
                 getattr(adjust, "brightness", 0), getattr(adjust, "contrast", 0)))

    @staticmethod
    def _put(cache: OrderedDict, key, value, limit: int) -> None:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def prepare(self, source, prep: dict):
        """Retourne ``(image, clé)`` ; ``clé`` est aussi celle du cache de tuiles."""
        source_key = self._source_key(source)
        if source_key is None:
            return prepare_source(source, **prep), None
        key = (source_key, self._prep_key(prep))
        with self._lock:
            image = self._prepared.get(key)
            if image is not None:
                self._prepared.move_to_end(key)
                return image, key
        image = prepare_source(source, **prep)
        with self._lock:
            # Un second worker a pu finir entre-temps : préférer sa valeur pour
            # que toutes les tâches partagent la même image immuable.
            existing = self._prepared.get(key)
            if existing is not None:
                self._prepared.move_to_end(key)
                return existing, key
            self._put(self._prepared, key, image, self._prepared_limit)
        return image, key

    def tile_data(self, key, variant: tuple):
        if key is None:
            return None
        full_key = (key, variant)
        with self._lock:
            data = self._tiles.get(full_key)
            if data is not None:
                self._tiles.move_to_end(full_key)
            return data

    def store_tile_data(self, key, variant: tuple, data: tuple) -> None:
        if key is None:
            return
        with self._lock:
            self._put(self._tiles, (key, variant), data, self._tiles_limit)


def open_image(source):
    """Ouvre le source PIL sans le convertir (préserve le mode 'P' indexé). Si un
    Image est déjà passé, le renvoie tel quel."""
    from PIL import Image
    return source if hasattr(source, "mode") else Image.open(source)


def prepare_source(source, canvas=None, pos=None, size=None, adjust=None, mirror=None):
    """Image PIL préparée pour l'encodage : l'image, mise à l'échelle (`size` = w, h) puis POSÉE dans un canvas
    (`canvas` = w, h ; `pos` = x, y du coin haut-gauche de l'image dans le canvas), PUIS mise en miroir
    (`mirror` = axe_x, axe_y, cf. `core.bg_mirror`), PUIS réglée (`adjust` =
    `BackgroundAdjust`, cf. `core.bg_adjust`). Le miroir précède la compression
    puisqu'il change les tuiles qu'elle trouvera. Rien de tout cela : la source est
    rendue telle quelle. Le fichier n'est jamais modifié — tout se
    passe en mémoire, c'est ce qui laisse revenir à l'original.

    Le canvas a SA taille : l'image peut le déborder (le surplus est rogné) ou le laisser en partie vide
    (transparent). Rien n'est jamais ajusté en douce — ce que l'auteur a posé est ce qui est encodé.

    Rééchantillonnage AUTOMATIQUE : plus proche voisin pour une source indexée (le
    mode 'P' et sa palette d'auteur survivent, un pixel art n'est pas lissé),
    Lanczos sinon (photo). Seule la partie VISIBLE de l'image est rééchantillonnée (`box`) : une photo posée
    en grand dans un petit canvas ne se redimensionne pas en entier."""
    from PIL import Image
    img = open_image(source)
    size = (max(1, int(size[0])), max(1, int(size[1]))) if size else img.size
    canvas = (max(1, int(canvas[0])), max(1, int(canvas[1]))) if canvas else size
    pos = (int(pos[0]), int(pos[1])) if pos else (0, 0)
    if size != img.size or canvas != size or pos != (0, 0):
        img = _place_in_canvas(img, size, canvas, pos)
    if mirror and any(axis is not None for axis in mirror[:2]):
        from core.bg_mirror import apply_mirror
        img = apply_mirror(img, mirror)
    if adjust is not None and not adjust.is_default():
        from core.bg_adjust import apply_adjust
        img = apply_adjust(img, adjust)
    return img


def _place_in_canvas(img, size, canvas, pos):
    """`img` mise à `size` puis posée en `pos` dans un canvas `canvas`. Indexé : le canvas reste 'P', même palette,
    le vide est l'index 0 (le transparent par convention). Sinon RGBA, le vide est transparent."""
    from PIL import Image
    indexed = is_indexed(img)
    # Zone du canvas que l'image recouvre, puis la part de la source qu'elle montre.
    x0, y0 = max(0, pos[0]), max(0, pos[1])
    x1, y1 = min(canvas[0], pos[0] + size[0]), min(canvas[1], pos[1] + size[1])
    if indexed:
        out = Image.new("P", canvas, 0)
        out.putpalette(img.getpalette() or [])
        if (x0, y0, x1, y1) != (0, 0, canvas[0], canvas[1]):
            out.info["transparency"] = _transparency_with_index_zero(img)    # il y a du vide à marquer
        elif "transparency" in img.info:
            out.info["transparency"] = img.info["transparency"]
    else:
        out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    if x1 <= x0 or y1 <= y0:
        return out
    sx, sy = img.width / size[0], img.height / size[1]
    box = ((x0 - pos[0]) * sx, (y0 - pos[1]) * sy, (x1 - pos[0]) * sx, (y1 - pos[1]) * sy)
    piece = img if indexed else img.convert("RGBA")
    if indexed and piece.mode != "P":
        piece = piece.convert("P")
    if (x1 - x0, y1 - y0) != img.size or box != (0, 0, img.width, img.height):
        filt = Image.NEAREST if indexed else Image.LANCZOS
        # On rogne D'ABORD : `resize(box=)` laisse le filtre lire les pixels au-delà de la boîte, et le rendu
        # différerait de « recadrer puis redimensionner », l'ancien geste que ce canvas remplace. Seule une boîte
        # non entière (échelle fractionnaire) garde un `box` relatif, au pixel près.
        left, top = int(box[0] // 1), int(box[1] // 1)
        right, bottom = -int(-box[2] // 1), -int(-box[3] // 1)
        piece = piece.crop((left, top, right, bottom))
        rel = (box[0] - left, box[1] - top, box[2] - left, box[3] - top)
        whole = (0, 0, right - left, bottom - top)
        piece = piece.resize((x1 - x0, y1 - y0), filt, box=None if rel == whole else rel)
    out.paste(piece, (x0, y0))
    return out


def _transparency_with_index_zero(img):
    """La table de transparence de `img` ('P'), index 0 rendu transparent : le vide du canvas est l'index 0."""
    raw = img.info.get("transparency")
    if raw is None:
        return 0
    if isinstance(raw, int):
        table = bytearray(b"\xff" * (raw + 1))
        table[raw] = 0
    else:
        table = bytearray(raw)
    if not table:
        return 0
    table[0] = 0
    return bytes(table)


def is_indexed(img) -> bool:
    """Vrai si le PNG porte sa propre palette (mode 'P'/'PA') — la palette est
    alors l'AUTORITÉ voulue par l'auteur, on ne la re-déduit pas."""
    return img.mode in ("P", "PA")


def count_source_colors(source, cap: int = 257) -> tuple[int, bool]:
    """Nombre de couleurs distinctes de l'image, plafonné à `cap`. Renvoie
    (n, capped). Deux régimes selon l'origine de la palette :
    - indexé : nombre d'entrées de palette réellement utilisées (l'autorité) ;
    - non-indexé : couleurs opaques distinctes après snap 5-bit (& 0xF8), donc un
      dégradé subtil qui s'effondre en BGR555 ne gonfle pas le compte à tort.
    Ne modifie pas le source."""
    img = open_image(source)
    if is_indexed(img):
        used = img.getcolors(maxcolors=cap)   # [(count, index), ...] ou None si > cap
        if used is None:
            return cap, True
        return len(used), False
    try:
        import numpy as np
    except Exception:
        # Repli sans numpy : getcolors sur RGB (sans snap → borne haute, suffisant).
        cols = img.convert("RGB").getcolors(maxcolors=cap)
        return (cap, True) if cols is None else (len(cols), False)
    arr = np.asarray(img.convert("RGBA"))
    if arr.size == 0:
        return 0, False
    opaque = (arr[..., :3] & 0xF8)[arr[..., 3] > 0]
    if opaque.size == 0:
        return 0, False
    packed = (opaque[:, 0].astype(np.uint32) << 16) \
        | (opaque[:, 1].astype(np.uint32) << 8) | opaque[:, 2]
    n = int(np.unique(packed).size)
    return (cap, True) if n > cap else (n, False)


def source_palette_info(source) -> tuple[bool, int, bool]:
    """(indexed, n_colors, capped) pour l'UI : le PNG porte-t-il sa propre palette
    (indexé), et combien de couleurs. n_colors=-1 si plafonné. Léger (aucune dédup
    de tuiles, contrairement à detect_import_mode). Ne modifie pas le source."""
    indexed = is_indexed(open_image(source))
    n, capped = count_source_colors(source)
    return indexed, (-1 if capped else n), capped


def _fits_4bpp_tiled(source) -> bool:
    """Vrai si le 4bpp tuilé représente l'image SANS perte : aucune tuile au-delà
    de 15 couleurs (l'index 0 est le transparent) et au plus 16 sous-palettes."""
    stats = analyze_tile_colors(source)
    return stats["tiles_over"] == 0 and stats["palettes_needed"] <= 16


def detect_import_mode(source, tile_budget: int = TILE_BUDGET) -> dict:
    """Décision d'import UNIFIÉE (le pivot = le PNG est-il indexé ?). Renvoie un
    dict de faits + un `token` pour l'UI. Ne modifie jamais le source.

    Deux axes ORTHOGONAUX :
    - profondeur (bpp) ← nombre de couleurs : ≤16 → 4 ; ≤256 → 8 ; >256 → 16 ;
    - layout (tiled/bitmap) ← répétition des tuiles (photo qui ne se tuile pas).

    Règles :
    - PNG indexé = palette autorité → jamais 16bpp (palette ≤256 par définition) ;
    - PNG non-indexé = palette déduite ; >256 couleurs = seul vrai cas 16bpp
      (aucune représentation indexée possible) ;
    - `warning` n'est posé QUE si la déduction force une perte (non-indexé
      hors-palette ou couleurs plafonnées), pas sur le cas courant.
    Clés : indexed, n_colors (-1 = plafonné), bpp (4/8/16), mode (tiled/bitmap),
    token (tiled4/tiled8/bitmap/bitmap16), warning (str|None)."""
    n, capped = count_source_colors(source, cap=257)
    indexed = is_indexed(open_image(source))

    if n <= 16:
        bpp = 4
    elif n <= 256:
        # Le 4bpp ne limite pas les couleurs de l'IMAGE mais celles de chaque
        # TUILE (15 + transparent) sur au plus 16 sous-palettes. Une image à 18
        # couleurs dont chaque tuile en utilise peu tient donc en 4bpp, sans
        # perte — et ne prend pas toute la PAL_BG_RAM comme le ferait le 8bpp.
        bpp = 4 if _fits_4bpp_tiled(source) else 8
    else:
        bpp = 16   # >256 couleurs : indexation impossible → couleur directe

    # Layout : le 16bpp est bitmap par nature (ni palette ni tuiles) ; sinon on
    # tranche photo vs pixel-art par l'unicité des tuiles (budget selon la bpp).
    if bpp == 16:
        mode = "bitmap"
    else:
        budget = TILE_BUDGET_8BPP if bpp == 8 else tile_budget
        mode = detect_bg_mode(source, tile_budget=budget)

    if bpp == 16:
        token = "bitmap16"
    elif mode == "bitmap":
        token = "bitmap"          # Mode 4 : bitmap paletté (≤256)
    else:
        token = "tiled8" if bpp == 8 else "tiled4"

    warning = None
    if not indexed and (bpp == 16 or capped):
        warning = "Non-indexed PNG with many colours (some loss possible)."

    return {
        "indexed": indexed,
        "n_colors": -1 if capped else n,
        "bpp": bpp,
        "mode": mode,
        "token": token,
        "warning": warning,
    }


def _snap5(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Snappe une couleur RGB888 sur la grille 5-bit/canal (représentable BGR555)."""
    return (r & 0xF8, g & 0xF8, b & 0xF8)


def _dedup_tile(idxgrid: tuple, lookup: dict, tileset: list) -> tuple[int, bool, bool]:
    """Renvoie (tile_id, flip_h, flip_v) : réutilise une tuile existante (ou son
    flip H/V/HV) si possible, sinon en crée une nouvelle."""
    if idxgrid in lookup:
        return lookup[idxgrid], False, False
    fh = flip_h(idxgrid)
    if fh in lookup:
        return lookup[fh], True, False
    fv = flip_v(idxgrid)
    if fv in lookup:
        return lookup[fv], False, True
    fhv = flip_h(fv)
    if fhv in lookup:
        return lookup[fhv], True, True
    tid = len(tileset)
    tileset.append(list(idxgrid))
    lookup[idxgrid] = tid
    return tid, False, False


def _open_padded(source):
    """Ouvre le source en RGBA, paddé à un multiple de 8. Retourne (img, w, h,
    tw, th) où (w,h) sont les dimensions D'ORIGINE (avant padding)."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    tw, th = (w + 7) // 8, (h + 7) // 8
    if w % 8 or h % 8:
        padded = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
        padded.paste(img, (0, 0))
        img = padded
    return img, w, h, tw, th


def _extract_tile_colors(img) -> tuple:
    """Grilles de pixels + jeu de couleurs opaques par tuile (couleurs snappées
    5-bit). `img` doit déjà être RGBA et paddé. Retourne (tw, th, tile_grids,
    tile_colors). Partagé entre compression et diagnostic (aucune divergence).

    La lecture PIL ``px[x, y]`` est étonnamment chère : une grande photo déclenche
    un appel Python par pixel, avant même le travail de compression. On lit donc
    le raster d'un coup et on le remet en tuiles avec NumPy. Les listes retournées
    restent volontairement identiques au contrat historique (tuples RGB ou
    ``None``, puis ``set`` de couleurs) : le packing, le clustering et les
    diagnostics n'ont pas à connaître cette optimisation.
    """
    w, h = img.size
    tw, th = w // 8, h // 8
    try:
        import numpy as np
    except ImportError:
        # NumPy est une dépendance de l'éditeur, mais garder ce repli rend le
        # coeur importable dans les installations minimales et préserve le
        # comportement précédent à l'identique.
        px = img.load()
        tile_grids, tile_colors = [], []
        for ty in range(th):
            for tx in range(tw):
                grid, colors = [], set()
                for y in range(8):
                    for x in range(8):
                        r, g, b, a = px[tx * 8 + x, ty * 8 + y]
                        if a == 0:
                            grid.append(None)
                        else:
                            c = _snap5(r, g, b)
                            grid.append(c)
                            colors.add(c)
                tile_grids.append(grid)
                tile_colors.append(colors)
        return tw, th, tile_grids, tile_colors

    rgba = np.asarray(img, dtype=np.uint8)
    # (hauteur, largeur, RGBA) -> (tuile en ordre de balayage, 64, RGBA).
    # Le transpose est essentiel : ``reshape`` seul prendrait huit lignes
    # consécutives au lieu des 8×8 pixels de la tuile suivante.
    tiles = (rgba.reshape(th, 8, tw, 8, 4)
             .transpose(0, 2, 1, 3, 4)
             .reshape(tw * th, 64, 4))
    visible = tiles[..., 3] != 0
    # Toutes les opérations coûteuses (lecture, découpage et snap 5 bits) sont
    # vectorisées. ``tolist`` ne sert ensuite qu'à rétablir des entiers Python
    # hashables, nécessaires aux dictionnaires du reste du pipeline.
    rgb = (tiles[..., :3] & np.uint8(0xF8)).tolist()
    alpha = visible.tolist()
    tile_grids = []
    tile_colors = []
    for pixels, opaque in zip(rgb, alpha):
        grid = [tuple(color) if is_opaque else None
                for color, is_opaque in zip(pixels, opaque)]
        tile_grids.append(grid)
        tile_colors.append({color for color in grid if color is not None})
    return tw, th, tile_grids, tile_colors


def _pack_palettes(tile_colors: list, editable: int, method: str) -> tuple:
    """Packing glouton (PRÉ-fusion) des palettes : chaque tuile (réduite à
    <=`editable` couleurs) rejoint une palette existante si l'union tient, sinon
    en ouvre une. Retourne (palettes, tile_pal, tile_cmap). Partagé entre
    compression et diagnostic."""
    palettes: list = []          # list[list[(r,g,b)]] (ordre = index 1..N)
    members: list = []           # le même contenu en ensembles : le test d'union ne reconstruit rien
    tile_pal: list = [0] * len(tile_colors)
    tile_cmap: list = [None] * len(tile_colors)   # réduction couleur par tuile si >15
    for i, colors in enumerate(tile_colors):
        cols = list(colors)
        if len(cols) > editable:
            cmap = reduce_colors(cols, {c: 1 for c in cols}, editable, method)
            cols = list(dict.fromkeys(cmap.values()))
            tile_cmap[i] = cmap
        cset = set(cols)
        best = None
        for pi, held in enumerate(members):
            # |palette ∪ tuile| <= editable, sans fabriquer l'union
            if len(cset - held) <= editable - len(held):
                best = pi
                break
        if best is None:
            palettes.append(list(cset))
            members.append(set(cset))
            best = len(palettes) - 1
        else:
            held = members[best]
            for c in cset:
                if c not in held:
                    palettes[best].append(c)
                    held.add(c)
        tile_pal[i] = best
    return palettes, tile_pal, tile_cmap


def analyze_background_source(source, max_colors: int = 16,
                             method: str = "median_cut") -> dict:
    """Diagnostic NON-DESTRUCTIF d'un PNG de fond — ce que la compression devra
    faire, SANS construire le tileset (chemin léger, pour valider un asset déjà
    importé). Le fichier n'est jamais modifié."""
    img, w, h, tw, th = _open_padded(source)
    editable = max_colors - 1
    _, _, _, tile_colors = _extract_tile_colors(img)
    palettes, _, tile_cmap = _pack_palettes(tile_colors, editable, method)
    return {
        "src_w": w, "src_h": h,
        "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
        "tiles_w": tw, "tiles_h": th,
        "max_tile_colors": max((len(c) for c in tile_colors), default=0),
        "tiles_reduced": sum(1 for cm in tile_cmap if cm),
        "pre_merge_palettes": len(palettes),
    }


def analyze_tile_colors(source) -> dict:
    """Ce que le 4bpp demanderait à cette image, MESURÉ sans rien encoder :
    couleurs par tuile, couleurs partagées d'une tuile à l'autre, palettes
    nécessaires. `source` est l'image PRÉPARÉE (cf. `prepare_source`) — c'est la
    taille qu'elle aura qui fait le nombre de tuiles.

    Même extraction et même packing que la compression (`_extract_tile_colors`,
    `_pack_palettes`) : le chiffre annoncé est celui que la compression trouvera.
    Une tuile de plus de 15 couleurs (l'index 0 est le transparent) ne tient dans
    aucune sous-palette telle quelle : elle serait RÉDUITE, donc avec perte. Les
    palettes comptées ici sont celles des tuiles qui tiennent, sans cette
    réduction — un minimum, jamais un optimiste.

    Clés : tiles, colors_min/avg/max, tiles_fit, tiles_over, buckets ((≤15,
    16–31, ≥32) en tuiles), distinct_sets, shared_tiles (tuiles dont le jeu de
    couleurs est aussi celui d'une autre), palettes_needed."""
    img, _w, _h, _tw, _th = _open_padded(source)
    _, _, _, tile_colors = _extract_tile_colors(img)
    counts = [len(c) for c in tile_colors]
    fitting = [c for c in tile_colors if len(c) <= 15]
    palettes, _, _ = _pack_palettes(fitting, 15, "median_cut")
    by_set: dict = {}
    for c in tile_colors:
        by_set[frozenset(c)] = by_set.get(frozenset(c), 0) + 1
    return {
        "tiles": len(counts),
        "colors_min": min(counts, default=0),
        "colors_avg": sum(counts) / len(counts) if counts else 0.0,
        "colors_max": max(counts, default=0),
        "tiles_fit": len(fitting),
        "tiles_over": len(counts) - len(fitting),
        "buckets": (len(fitting),
                    sum(1 for n in counts if 16 <= n <= 31),
                    sum(1 for n in counts if n >= 32)),
        "distinct_sets": len(by_set),
        "shared_tiles": sum(n for n in by_set.values() if n > 1),
        "palettes_needed": len(palettes),
    }


# ── Chemin « indexé direct » (partagé 4bpp / 8bpp / bitmap) ──────────────────
# Principe UNIFIÉ : dès qu'un PNG est indexé (mode 'P'/'PA'), sa palette déclarée
# (PLTE) est l'AUTORITÉ voulue par l'auteur — on la préserve TELLE QUELLE (ordre
# + entrées déclarées mais non peintes) et on indexe les pixels DIRECTEMENT par
# l'index natif (slot k = entrée native k), sans re-quantification : aucune
# couleur déclarée ne disparaît. Convention GBA/auteur : l'index 0 = transparent
# (backdrop). Vaut quelle que soit la profondeur, tant que la palette tient sous
# le plafond 256 (garanti par le mode 'P'). Sinon (PNG non indexé), on retombe
# sur les chemins déduits (quantification depuis les couleurs peintes).


def _native_palette_bgr555(pal_raw: list, n_slots: int) -> list:
    """Palette matérielle (BGR555) depuis la PLTE brute : slot 0 réservé/
    transparent, slots 1..n_slots-1 = entrées natives converties (0 si absente).
    Préserve l'ordre ET les entrées déclarées mais inutilisées."""
    pal = [RESERVED_SLOT_COLOR]
    for i in range(1, n_slots):
        base = i * 3
        if base + 2 < len(pal_raw):
            pal.append(rgb888_to_bgr555(pal_raw[base], pal_raw[base + 1], pal_raw[base + 2]))
        else:
            pal.append(0)
    return pal


def _indexed_direct_source(source):
    """(pimg 'P', alpha 'L', pal_raw PLTE, used) pour le chemin indexé direct, ou
    None si le PNG n'est pas indexé / sans palette. `alpha` résout uniformément la
    transparence réelle (tRNS / mode PA) via RGBA ; `used` = getcolors (comptage
    et index max). Le source n'est pas modifié."""
    src = open_image(source)
    if not is_indexed(src):
        return None
    pimg = src if src.mode == "P" else src.convert("P")
    pal_raw = pimg.getpalette() or []
    if not pal_raw:
        return None
    used = pimg.getcolors(maxcolors=257) or []    # [(count, index), ...]
    alpha = src.convert("RGBA").getchannel("A")
    return pimg, alpha, pal_raw, used


def _encode_background_indexed_4bpp(source) -> Optional[dict]:
    """Chemin direct 4bpp : PNG indexé dont les index utilisés tiennent dans UNE
    sous-palette (≤ 15), ou « PAR BANQUES » : index = banque × 16 + couleur, chaque tuile dans une seule
    banque (la convention des outils GBA, celle que `core.bg_bake` écrit). Dans les deux cas la palette
    déclarée et les banques sont gardées telles quelles. None si non indexé, ou si le PNG ne se lit pas
    exactement ainsi (une tuile à cheval sur deux banques, un index 16·b opaque : l'index 0 de chaque
    banque est le transparent) → repli sur le packing déduit de encode_background."""
    from PIL import Image
    prep = _indexed_direct_source(source)
    if prep is None:
        return None
    pimg, alpha, pal_raw, used = prep
    n_entries = len(pal_raw) // 3
    # Les banques DÉCLARÉES comptent (une palette ajoutée mais pas encore peinte survit au fichier) — sauf une PLTE
    # pleine de 256 entrées, qui n'est que le remplissage habituel des outils : là, seules les banques utilisées.
    declared = (n_entries + 15) // 16 if 16 < n_entries < 256 else 1
    n_banks = max(1, min(16, max(declared, (max((idx for _c, idx in used), default=0) >> 4) + 1)))
    palettes = [_native_palette_bgr555(pal_raw[b * 48:(b + 1) * 48], 16) for b in range(n_banks)]
    n_declared = min(16 * n_banks, n_entries)

    w, h = pimg.size
    tw, th = (w + 7) // 8, (h + 7) // 8
    if w % 8 or h % 8:                            # padding à un multiple de 8
        pad_p = Image.new("P", (tw * 8, th * 8), 0); pad_p.paste(pimg, (0, 0)); pimg = pad_p
        pad_a = Image.new("L", (tw * 8, th * 8), 0); pad_a.paste(alpha, (0, 0)); alpha = pad_a
    ipx = pimg.load()
    apx = alpha.load()

    tileset: list = []
    lookup: dict = {}
    tilemap: list = []
    tile_used: list = []                          # couleurs opaques distinctes/tuile (diag)
    for ty in range(th):
        for tx in range(tw):
            grid = []
            seen: set = set()
            banks: set = set()
            for y in range(8):
                for x in range(8):
                    px, py = tx * 8 + x, ty * 8 + y
                    idx = ipx[px, py] & 0xFF
                    if apx[px, py] == 0 or idx == 0:
                        grid.append(0)            # transparent (backdrop)
                        continue
                    if idx & 15 == 0:
                        return None               # index 0 d'une autre banque, mais opaque : pas une lecture par banques
                    grid.append(idx & 15)         # couleur dans la banque (identité en banque 0)
                    banks.add(idx >> 4)
                    seen.add(idx)
            if len(banks) > 1:
                return None                       # une tuile à cheval sur deux banques
            tid, fh, fv = _dedup_tile(tuple(grid), lookup, tileset)
            tilemap.append(pack_se(tid, next(iter(banks), 0), fh, fv))
            tile_used.append(len(seen))

    return {
        "palettes": palettes,                      # les banques de 16 de la PLTE native (une seule, en général)
        "tileset": [tile_to_hex(t) for t in tileset],
        "tilemap": tilemap,
        "tiles_w": tw,
        "tiles_h": th,
        # `quantize_method` reste un algo VALIDE (relu par reduce_colors sur
        # certains chemins) : le chemin direct est choisi d'après le PNG (indexé
        # ou non) à chaque compression, pas d'après ce champ. L'origine « indexé
        # direct » est tracée par `src_indexed` ci-dessous.
        "quantize_method": "median_cut",
        "bpp": 4,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "max_tile_colors": max(tile_used, default=0),
            "tiles_reduced": 0,                    # aucune réduction : indexation directe
            "pre_merge_palettes": n_banks,
            "final_palettes": n_banks,
            "unique_tiles": len(tileset),
            # Origine : renseignée ici pour que l'inspecteur affiche la taille de
            # la PALETTE DÉCLARÉE (et non les seules couleurs peintes). Lu en
            # priorité par BgPropertiesPanel._source_info.
            "src_indexed": True,
            "src_colors": n_declared,
        },
    }


def _encode_background_indexed_8bpp(source) -> Optional[dict]:
    """Chemin direct 8bpp tuilé : PNG indexé (≤ 256), palette native (256)
    préservée, tuiles en octets indexées directement. None si non indexé."""
    from PIL import Image
    prep = _indexed_direct_source(source)
    if prep is None:
        return None
    pimg, alpha, pal_raw, used = prep
    pal256 = _native_palette_bgr555(pal_raw, 256)
    n_declared = min(256, len(pal_raw) // 3)
    n_used = len(used)

    w, h = pimg.size
    tw, th = (w + 7) // 8, (h + 7) // 8
    if w % 8 or h % 8:
        pad_p = Image.new("P", (tw * 8, th * 8), 0); pad_p.paste(pimg, (0, 0)); pimg = pad_p
        pad_a = Image.new("L", (tw * 8, th * 8), 0); pad_a.paste(alpha, (0, 0)); alpha = pad_a
    ipx = pimg.load()
    apx = alpha.load()

    tileset: list = []
    lookup: dict = {}
    tilemap: list = []
    for ty in range(th):
        for tx in range(tw):
            grid = []
            for y in range(8):
                for x in range(8):
                    px, py = tx * 8 + x, ty * 8 + y
                    idx = ipx[px, py] & 0xFF
                    grid.append(0 if (apx[px, py] == 0 or idx == 0) else idx)
            tid, fh, fv = _dedup_tile(tuple(grid), lookup, tileset)
            tilemap.append(pack_se(tid, 0, fh, fv))

    return {
        "palettes": [pal256],                              # UNE palette de 256 (PLTE native)
        "tileset": [tile_to_hex8(t) for t in tileset],
        "tilemap": tilemap,
        "tiles_w": tw,
        "tiles_h": th,
        "quantize_method": "quantize_256",
        "bpp": 8,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "total_colors": n_used,
            "unique_tiles": len(tileset),
            "dither": False,
            "bpp": 8,
            "src_indexed": True,
            "src_colors": n_declared,
        },
    }


def _require_bitmap_canvas(w: int, h: int) -> None:
    """Un bitmap est au plus 240×160 : l'encodeur ne rétrécit JAMAIS en douce. `encode_by_mode` pose le canvas à cette
    taille (l'image déborde, le surplus est rogné) ; un appel direct avec une image plus grande est une erreur."""
    if w > GBA_SCREEN_W or h > GBA_SCREEN_H:
        raise ValueError(f"A bitmap background is at most {GBA_SCREEN_W}x{GBA_SCREEN_H}; "
                         f"the canvas is {w}x{h}.")


def _encode_background_indexed_bitmap(source) -> Optional[dict]:
    """Chemin direct bitmap (Mode 4) : PNG indexé (≤ 256), palette native (256)
    préservée, buffer indexé directement. Un canvas au-delà de 240×160 est une erreur (cf.
    `_require_bitmap_canvas`). None si non indexé."""
    from PIL import Image
    prep = _indexed_direct_source(source)
    if prep is None:
        return None
    pimg, alpha, pal_raw, used = prep
    pal256 = _native_palette_bgr555(pal_raw, 256)
    n_declared = min(256, len(pal_raw) // 3)
    n_used = len(used)

    w, h = pimg.size
    _require_bitmap_canvas(w, h)
    out_w, out_h = w, h
    ipx = pimg.load()
    apx = alpha.load()

    buf = bytearray(out_w * out_h)
    for y in range(out_h):
        row = y * out_w
        for x in range(out_w):
            idx = ipx[x, y] & 0xFF
            buf[row + x] = 0 if (apx[x, y] == 0 or idx == 0) else idx

    return {
        "mode": "bitmap",
        "palettes": [pal256],
        "bitmap": buf.hex(),
        "out_w": out_w, "out_h": out_h,
        "bpp": 8,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "out_w": out_w, "out_h": out_h,
            "total_colors": n_used,
            "dither": False,
            "mode": "bitmap",
            "src_indexed": True,
            "src_colors": n_declared,
        },
    }


def compose_animations(ba, project, compiled: dict) -> dict:
    """Compose les fonds ANIMÉS posés sur `ba` dans sa représentation rendue, à
    leur PREMIÈRE image.

    Pourquoi figés : un canvas de scène sert à placer des acteurs et des
    collisions, et un décor qui bouge sous la souris gêne ce travail. C'est
    l'inverse du canvas du Background Editor, où l'animation EST l'objet qu'on
    pose et où la voir jouer est la seule raison d'ouvrir un canvas.

    Le mode d'animation n'entre pas en jeu : `instance` et `shared` affichent la
    même première image, ils ne divergent qu'en mouvement.

    Composition locale : les tuiles et les palettes de l'animé sont concaténées
    à celles de l'hôte, sans rien demander à la scène. Les banques réelles sont
    allouées au build (cf. codegen/palette_alloc) — ici on ne cherche qu'à
    montrer les bonnes couleurs.
    """
    if project is None or not getattr(ba, "animations", None):
        return compiled
    if compiled.get("bpp", 4) != 4:
        # 8bpp : une seule palette de 256, la fusion par sous-palette n'a pas
        # de sens (et le build n'émet pas ces animés non plus).
        return compiled

    # Le MÊME calcul que le build (codegen/bg_anim) : l'aperçu doit montrer la
    # tuile fusionnée, pas une superposition approchée. Un aperçu qui composerait
    # autrement ferait mentir l'éditeur sur ce que la ROM produira.
    from codegen.bg_anim import resolve_blocks, host_placements, placement_geometry

    tiles = list(compiled["tileset"])
    pals = [list(x) for x in compiled["palettes"]]
    tm = list(compiled["tilemap"])
    tw = compiled["tiles_w"] or 1
    blocks, for_pl = resolve_blocks(project, ba)

    bank_of: dict = {}
    base_of: dict = {}
    for blk in blocks:
        key = tuple(blk.composed.palette)
        if key not in bank_of:
            if len(pals) >= 16:
                # Plus de banque libre : on montre le fond nu plutôt que des
                # couleurs fausses que rien n'expliquerait à l'écran. Le build,
                # lui, bloquera avec un message.
                continue
            bank_of[key] = len(pals)
            pals.append(list(blk.composed.palette))
        base_of[id(blk)] = len(tiles)
        tiles += blk.initial_tiles()

    for pl, src in host_placements(project, ba):
        blk = for_pl.get(id(pl))
        if blk is None or id(blk) not in base_of:
            continue
        bank = bank_of.get(tuple(blk.composed.palette))
        if bank is None:
            continue
        geom = placement_geometry(ba, src, pl)
        if geom is None:
            continue
        for r in range(geom.rows):
            for c in range(geom.cols):
                cell = r * geom.cols + c
                dst = (geom.row + r) * tw + (geom.col + c)
                # `shared` : une case = un emplacement dédié ; `instance` : la
                # carte pointe la tuile de l'image 0. Même adressage que le build.
                tid = cell if blk.shared else blk.composed.order[cell]
                if 0 <= dst < len(tm):
                    tm[dst] = pack_se(base_of[id(blk)] + tid, bank, False, False)

    out = dict(compiled)
    out.update({"tileset": tiles, "tilemap": tm, "palettes": pals})
    return out


def compiled_background(ba, source_path, project=None) -> Optional[dict]:
    """Représentation compressée (palette d'origine) d'un fond, pour un rendu
    éditeur (canvas de scène) : depuis le sidecar `ba` (BackgroundAsset) si déjà
    compressé, sinon compressée à la volée depuis le PNG (fallback legacy rare,
    asset pas encore reconcilié). None si indisponible.

    `project` fourni : les fonds animés posés sur `ba` sont composés à leur
    première image (cf. `compose_animations`). Sans lui, on rend le fond seul —
    un appelant qui n'a pas le projet ne peut pas résoudre les noms d'animés."""
    if ba and ba.tileset:
        # effective_tilemap() : baseline + overrides d'inpainting asset
        # (BackgroundInpainting), pour que le rendu montre le fond tel qu'édité
        # au niveau éditeur, partagé entre toutes les scènes.
        base = {"tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
                "tileset": ba.effective_tileset(), "tilemap": ba.effective_tilemap(),
                "palettes": ba.palettes, "bpp": getattr(ba, "bpp", 4)}
        return compose_animations(ba, project, base)
    if source_path and source_path.is_file():
        try:
            return encode_background(
                prepare_source(source_path, **ba.import_prep()) if ba else prepare_source(source_path),
                compression=ba.compression if ba else None)
        except (ValueError, OSError):
            return None
    return None


def _asks_for_reduction_4bpp(params: BackgroundCompression) -> bool:
    """Un réglage de compression 4bpp s'écarte-t-il du défaut ? (Le type de dithering n'en est pas un : il ne réduit rien.)"""
    base = BackgroundCompression()
    return (params.palettes_max, params.colors_per_palette, params.global_colors, params.tile_target) != (
        base.palettes_max, base.colors_per_palette, base.global_colors, base.tile_target)


def _asks_for_reduction_8bpp(params: BackgroundCompression) -> bool:
    base = BackgroundCompression()
    return (params.palette_colors, params.tile_target) != (base.palette_colors, base.tile_target)


def encode_background(source, method: str = "median_cut",
                        compression: Optional[BackgroundCompression] = None,
                        dither: bool = False,
                        work_cache: Optional[BackgroundWorkCache] = None,
                        cache_key=None) -> dict:
    """PNG -> représentation GBA (palettes BGR555 + tileset + tilemap). Ne modifie
    jamais le source. `compression` (cf. BackgroundCompression) fixe le nombre de
    sous-palettes, leurs couleurs, la réduction globale préalable et la cible de
    tuiles ; défauts = 16 sous-palettes de 15 couleurs (+ l'index 0 transparent).
    `dither` ne joue que sur la réduction globale (rien à diffuser sans elle).
    Le résultat inclut un sous-dict `diagnostics` (pression de compression : couleurs
    par tuile, palettes avant fusion, dimensions) pour le validateur de l'éditeur.

    PNG INDEXÉ tenant en 4bpp : la palette déclarée est préservée telle quelle
    (cf. `_encode_background_indexed_4bpp`) au lieu d'être re-déduite depuis les
    seules couleurs peintes."""
    params = compression or BackgroundCompression()
    # Le chemin « indexé direct » garde la palette d'auteur telle quelle — il ne réduit rien. Dès que l'auteur DEMANDE une
    # réduction (palettes, couleurs, réduction globale, cible de tuiles), on la lui doit : le packing déduit prend le relais.
    direct = None if _asks_for_reduction_4bpp(params) else _encode_background_indexed_4bpp(source)
    if direct is not None:
        return direct
    # Un fond passé du 8bpp ou du bitmap porte « quantize_256 » : c'est le nom du
    # quantifieur de PIL, pas une méthode de réduction par tuile. On retombe sur le
    # défaut plutôt que de refuser une image que l'auteur vient de basculer.
    if method not in {token for token, _name in COMPRESSION_METHODS}:
        method = "median_cut"
    max_palettes = params.palettes_max
    editable = params.colors_per_palette   # couleurs utiles (l'index 0 est le transparent)
    # Cette variante couvre TOUT ce qui change les pixels avant le découpage.
    # Les curseurs palettes/cible n'y figurent pas : ils reprennent donc les
    # tuiles déjà extraites au lieu de relire chaque pixel de la photo.
    tile_variant = ("tiled4", params.global_colors, dither, params.dither_kind)
    cached_tiles = work_cache.tile_data(cache_key, tile_variant) if work_cache else None
    if cached_tiles is None:
        img, w, h, tw, th = _open_padded(source)
        if params.global_colors:
            img = _reduce_globally(img, params.global_colors, dither, params.dither_kind)
        # 1. Grille de pixels + jeu de couleurs par tuile (couleurs snappées 5-bit).
        _, _, tile_grids, tile_colors = _extract_tile_colors(img)
        cached_tiles = (w, h, tw, th, tile_grids, tile_colors)
        if work_cache:
            work_cache.store_tile_data(cache_key, tile_variant, cached_tiles)
    w, h, tw, th, tile_grids, tile_colors = cached_tiles

    # 2–3. Le regroupement des palettes et la déduplication ne dépendent PAS de
    # la cible de tuiles. Conserver ce résultat évite de les refaire quand on
    # déplace uniquement ce curseur ; la fusion ci-dessous reste seule à courir.
    base_variant = tile_variant + (method, max_palettes, editable)
    cached_base = work_cache.tile_data(cache_key, base_variant) if work_cache else None
    if cached_base is None:
        # Répartition des tuiles entre sous-palettes. SANS PERTE d'abord : le
        # packing glouton exact, quand chaque tuile tient et que les palettes
        # suffisent. Sinon, une photo est regroupée par similarité.
        max_tile_colors = max((len(c) for c in tile_colors), default=0)
        tiles_reduced = sum(1 for c in tile_colors if len(c) > editable)
        palettes = None
        if max_tile_colors <= editable:
            packed, tile_pal, tile_cmap = _pack_palettes(tile_colors, editable, method)
            pre_merge_palettes = len(packed)
            if len(packed) <= max_palettes:
                palettes = packed
        if palettes is None:
            if max_tile_colors > editable:
                # Minimum pour tenir sans perte : palettes des tuiles qui tiennent.
                pre_merge_palettes = len(_pack_palettes(
                    [c for c in tile_colors if len(c) <= editable], editable, method)[0])
            palettes, tile_pal = cluster_palettes(tile_grids, max_palettes, editable, method)
            tile_cmap = [None] * len(tile_grids)

        # Indexation des pixels dans la palette de chaque tuile + dédup (flips).
        pal_lists = [list(pal) for pal in palettes]
        pal_index = [{c: k + 1 for k, c in enumerate(pal)} for pal in pal_lists]
        tileset: list = []
        lookup: dict = {}
        cells: list = []
        near: dict = {}     # (palette, couleur) -> index le plus proche, calculé une fois
        for i, grid in enumerate(tile_grids):
            pb = tile_pal[i]
            cmap = tile_cmap[i]
            pidx = pal_index[pb]
            pal = pal_lists[pb]
            idxgrid = []
            for c in grid:
                if c is None:
                    idxgrid.append(0)
                    continue
                cc = cmap[c] if cmap else c
                k = pidx.get(cc)
                if k is None:   # hors palette -> la couleur la plus proche de CETTE palette
                    k = near.get((pb, cc))
                    if k is None:
                        k = near[(pb, cc)] = pidx[nearest_rgb(cc, pal)] if pal else 0
                idxgrid.append(k)
            tid, fh, fv = _dedup_tile(tuple(idxgrid), lookup, tileset)
            cells.append((tid, pb, fh, fv))
        cached_base = (pal_lists, tileset, cells, max_tile_colors, tiles_reduced, pre_merge_palettes)
        if work_cache:
            work_cache.store_tile_data(cache_key, base_variant, cached_base)
    pal_lists, tileset, cells, max_tile_colors, tiles_reduced, pre_merge_palettes = cached_base

    # 4. Cible de tuiles : fusionne les moins employées (avec perte) — après la
    #    dédup exacte, qui elle est sans perte et passe toujours d'abord.
    tileset, cells, tiles_merged = merge_tiles(tileset, cells, pal_lists, params.tile_target)
    tilemap = [pack_se(*cell) for cell in cells]

    return {
        "palettes": [[RESERVED_SLOT_COLOR] + [rgb888_to_bgr555(*c) for c in pal]
                     for pal in pal_lists],
        "tileset": [tile_to_hex(t) for t in tileset],   # list[str] (64 hex nibbles)
        "tilemap": tilemap,                               # list[int] (screen entries GBA)
        "tiles_w": tw,
        "tiles_h": th,
        "quantize_method": method,
        "bpp": 4,
        # Diagnostics (validateur éditeur) — le source n'est jamais modifié.
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "max_tile_colors": max_tile_colors,   # couleurs opaques max dans une tuile
            "tiles_reduced": tiles_reduced,       # tuiles > 15 couleurs (réduites, perte)
            "pre_merge_palettes": pre_merge_palettes,  # palettes avant le cap à 16
            "final_palettes": len(pal_lists),     # palettes après fusion
            "unique_tiles": len(tileset),         # budget VRAM
            "tiles_merged": tiles_merged,         # tuiles retirées par la cible (perte)
        },
    }


def _bayer(n: int):
    """Matrice de Bayer n×n (n = 4 ou 8), centrée sur 0 : des seuils dans ]−0,5 ; 0,5[."""
    import numpy as np
    m = np.array([[0, 2], [3, 1]], dtype=np.float32)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n) - 0.5


def _remap(rgb, palette_img, colors: int, kind: str = "floyd_steinberg"):
    """`rgb` repassé sur la palette de `palette_img`, l'erreur répartie selon `kind`. Diffusion : celle de PIL.
    Trame ordonnée : chaque pixel reçoit le seuil de sa case avant de prendre la couleur la plus proche — l'amplitude
    suit l'écart moyen des `colors` couleurs dans le cube RGB."""
    from PIL import Image
    if kind in ("bayer4", "bayer8"):
        import numpy as np
        n = 4 if kind == "bayer4" else 8
        arr = np.asarray(rgb.convert("RGB"), dtype=np.float32)
        h, w, _ = arr.shape
        threshold = np.tile(_bayer(n), (h // n + 1, w // n + 1))[:h, :w, None]
        spread = 255.0 / max(2.0, max(2, colors) ** (1 / 3))
        shifted = np.clip(arr + threshold * spread, 0, 255).astype(np.uint8)
        return Image.fromarray(shifted, "RGB").quantize(palette=palette_img, dither=Image.Dither.NONE)
    return rgb.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)


def _reduce_globally(img, colors: int, dither: bool, kind: str = "floyd_steinberg"):
    """RGBA → RGBA dont les pixels opaques n'emploient que `colors` couleurs.
    Fait AVANT le découpage en tuiles : deux tuiles voisines qui se ressemblent
    tombent alors sur les mêmes couleurs, donc sur les mêmes palettes. La
    transparence est rendue telle quelle."""
    from PIL import Image
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    q = rgb.quantize(colors=max(2, colors), method=Image.Quantize.MEDIANCUT)
    if dither:
        # `quantize(dither=…)` est ignoré tant qu'on ne fournit pas de palette :
        # on repasse l'image sur celle qu'on vient de calculer pour que la
        # diffusion d'erreur ait vraiment lieu.
        q = _remap(rgb, q, colors, kind)
    out = q.convert("RGB").convert("RGBA")
    out.putalpha(alpha)
    return out


# Quantifieurs de PIL offerts pour la palette unique (8bpp, bitmap). Le jeton est ce
# qui est stocké dans le sidecar ; « median_cut » est aussi le nom de la méthode 4bpp.
QUANTIZERS_8BPP = ("median_cut", "octree", "max_coverage")


def _quantize_rgb(rgb, colors: int, method: str, dither: bool, kind: str = "floyd_steinberg"):
    """Image PIL 'P' à `colors` couleurs. `quantize(dither=…)` est IGNORÉ tant qu'on
    ne lui donne pas de palette — le dithering des modes 8bpp et bitmap n'a donc
    jamais rien fait. On calcule la palette d'abord, puis on repasse l'image dessus
    pour que la diffusion d'erreur ait lieu."""
    from PIL import Image
    algo = {"median_cut": Image.Quantize.MEDIANCUT,
            "octree": Image.Quantize.FASTOCTREE,
            "max_coverage": Image.Quantize.MAXCOVERAGE}.get(method, Image.Quantize.MEDIANCUT)
    q = rgb.quantize(colors=max(2, colors), method=algo)
    if dither:
        q = _remap(rgb, q, colors, kind)
    return q


def encode_background_8bpp(source, dither: bool = False, method: str = "median_cut",
                           compression: Optional[BackgroundCompression] = None) -> dict:
    """PNG -> représentation GBA 8bpp : UNE palette de ≤256 couleurs, tuiles en
    octets (index 0-255), dédup (flips). Ne modifie jamais le source. Rapide : le
    quantifieur C de PIL fait le gros du travail (pas de packing multi-palettes).
    L'index 0 est réservé/transparent (pixels alpha 0).

    PNG INDEXÉ : la palette déclarée (≤256) est préservée telle quelle et les
    tuiles sont indexées directement (cf. `_encode_background_indexed_8bpp`),
    au lieu d'être re-quantifiées depuis les seules couleurs peintes.

    `compression` : `palette_colors` (taille de la palette, 255 par défaut — l'index
    0 reste au transparent) et `tile_target` (fusion des tuiles, cf. bg_tile_merge) ;
    `method` : un des `QUANTIZERS_8BPP`, sinon median-cut."""
    params = compression or BackgroundCompression()
    direct = None if _asks_for_reduction_8bpp(params) else _encode_background_indexed_8bpp(source)
    if direct is not None:
        return direct
    if method not in QUANTIZERS_8BPP:
        method = "median_cut"
    img, w, h, tw, th = _open_padded(source)
    alpha = img.getchannel("A").load()
    rgb = img.convert("RGB")
    q = _quantize_rgb(rgb, params.palette_colors, method, dither, params.dither_kind)
    qidx = q.load()
    pal_raw = q.getpalette() or []   # [r,g,b, ...]

    pal256 = [RESERVED_SLOT_COLOR]   # slot 0 réservé
    pal_rgb: list = []               # couleurs 1..N, pour la fusion de tuiles
    for i in range(255):
        base = i * 3
        if i < params.palette_colors and base + 2 < len(pal_raw):
            pal_rgb.append((pal_raw[base], pal_raw[base + 1], pal_raw[base + 2]))
            pal256.append(rgb888_to_bgr555(*pal_rgb[-1]))
        else:
            pal256.append(0)

    gc = rgb.getcolors(maxcolors=65536)
    total_colors = len(gc) if gc is not None else -1   # -1 = très nombreux

    tileset: list = []
    lookup: dict = {}
    cells: list = []
    for ty in range(th):
        for tx in range(tw):
            grid = []
            for y in range(8):
                for x in range(8):
                    px, py = tx * 8 + x, ty * 8 + y
                    if alpha[px, py] == 0:
                        grid.append(0)
                    else:
                        grid.append((qidx[px, py] + 1) & 0xFF)   # 1..255
            tid, fh, fv = _dedup_tile(tuple(grid), lookup, tileset)
            cells.append((tid, 0, fh, fv))

    # Cible de tuiles : après la dédup exacte, sans perte, qui passe toujours d'abord.
    tileset, cells, tiles_merged = merge_tiles(tileset, cells, [pal_rgb], params.tile_target)
    tilemap = [pack_se(*cell) for cell in cells]

    return {
        "palettes": [pal256],                              # UNE palette de 256
        "tileset": [tile_to_hex8(t) for t in tileset],    # list[str] (128 hex/tuile)
        "tilemap": tilemap,
        "tiles_w": tw,
        "tiles_h": th,
        "quantize_method": method,
        "bpp": 8,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "total_colors": total_colors,   # couleurs distinctes du source (-1 = >65536)
            "unique_tiles": len(tileset),
            "tiles_merged": tiles_merged,   # tuiles retirées par la cible (perte)
            "dither": dither,
            "bpp": 8,
        },
    }


def _render_bg_preview_8bpp(compiled: dict):
    """Rendu 8bpp : tuiles en octets, une seule palette de 256."""
    from PIL import Image
    tw, th = compiled["tiles_w"], compiled["tiles_h"]
    tiles = [hex_to_tile8(t) for t in compiled["tileset"]]
    pal = compiled["palettes"][0] if compiled["palettes"] else []
    rgb = [bgr555_to_rgb888(c) for c in pal]
    out = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
    px = out.load()
    for cell, se in enumerate(compiled["tilemap"]):
        tid, _pb, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(rgb):
                    continue
                r, g, b = rgb[idx]
                px[ox + x, oy + y] = (r, g, b, 255)
    return out


def render_bg_preview(compiled: dict):
    """Reconstruit l'image RGBA depuis la représentation compressée (aperçu éditeur)."""
    from PIL import Image
    if compiled.get("bpp", 4) == 8:
        return _render_bg_preview_8bpp(compiled)
    tw, th = compiled["tiles_w"], compiled["tiles_h"]
    tiles = [hex_to_tile(t) for t in compiled["tileset"]]
    palettes = compiled["palettes"]
    pal_rgb = [[bgr555_to_rgb888(c) for c in pal] for pal in palettes]
    out = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
    px = out.load()
    # Défensif (comme BgLayerRaster côté scène) : un tile_id ou un pal_bank hors
    # limites (données legacy/incohérentes, ou banque référencée absente après
    # édition de palettes) ne doit pas faire planter le rendu — on retombe sur la
    # tuile vide / la palette 0, et on ignore les index de couleur hors palette.
    for cell, se in enumerate(compiled["tilemap"]):
        tid, pb, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        rgb = pal_rgb[pb] if pb < len(pal_rgb) else (pal_rgb[0] if pal_rgb else [])
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(rgb):
                    continue
                r, g, b = rgb[idx]
                px[ox + x, oy + y] = (r, g, b, 255)
    return out


def encode_background_bitmap(source, dither: bool = False, compression: Optional[BackgroundCompression] = None,
                             method: str = "median_cut") -> dict:
    """PNG -> représentation GBA Mode 4 : bitmap plein écran ≤240×160, 8bpp (un
    index par pixel) + palette de 256. L'image est encodée telle qu'elle est : au-delà de 240×160 c'est une
    erreur (cf. `_require_bitmap_canvas`). Le source n'est jamais modifié.
    Rapide (quantifieur C de PIL). Convient aux photos (pas de tuiles → pas de
    limite de déduplication).

    PNG INDEXÉ : la palette déclarée (≤256) est préservée telle quelle et le
    buffer est indexé directement, sauf si l'auteur demande moins de couleurs —
    ce réglage implique nécessairement une nouvelle quantification."""
    params = compression or BackgroundCompression()
    direct = None if params.palette_colors != 255 else _encode_background_indexed_bitmap(source)
    if direct is not None:
        return direct
    if method not in QUANTIZERS_8BPP:
        method = "median_cut"
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    _require_bitmap_canvas(w, h)
    out_w, out_h = w, h
    alpha = img.getchannel("A").load()
    rgb = img.convert("RGB")
    q = _quantize_rgb(rgb, params.palette_colors, method, dither, params.dither_kind)
    qidx = q.load()
    pal_raw = q.getpalette() or []

    pal256 = [RESERVED_SLOT_COLOR]
    for i in range(255):
        base = i * 3
        if i < params.palette_colors and base + 2 < len(pal_raw):
            pal256.append(rgb888_to_bgr555(pal_raw[base], pal_raw[base + 1], pal_raw[base + 2]))
        else:
            pal256.append(0)

    buf = bytearray(out_w * out_h)
    for y in range(out_h):
        row = y * out_w
        for x in range(out_w):
            buf[row + x] = 0 if alpha[x, y] == 0 else ((qidx[x, y] + 1) & 0xFF)

    gc = rgb.getcolors(maxcolors=65536)
    total_colors = len(gc) if gc is not None else -1
    return {
        "mode": "bitmap",
        "palettes": [pal256],
        "bitmap": buf.hex(),
        "out_w": out_w, "out_h": out_h,
        "bpp": 8,
        "quantize_method": method,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "out_w": out_w, "out_h": out_h,
            "total_colors": total_colors,
            "palette_colors": params.palette_colors,
            "dither": dither,
            "mode": "bitmap",
        },
    }


def encode_by_mode(source, mode_token: str, method: str = "median_cut",
                    dither: bool = False, prep: Optional[dict] = None,
                    compression: Optional[BackgroundCompression] = None,
                    work_cache: Optional[BackgroundWorkCache] = None) -> dict:
    """Dispatch unique vers `encode_background`/`encode_background_8bpp`/
    `encode_background_bitmap` selon un token de mode ("tiled4"|"tiled8"|
    "bitmap"|"bitmap16" — vocabulaire de `detect_import_mode`). Partagé par
    l'import initial, la recompression depuis l'inspecteur (Background Editor)
    et `core.resources.asset_reconciliation.encode_background_asset`, pour qu'il n'existe qu'un
    seul endroit qui décide quel encodeur appeler.

    "bitmap16" = vrai 16bpp direct (détecté), pas encore implémenté : repli
    interim sur le Mode 4 paletté (quantif 256), cf. `detect_import_mode`.

    `prep` (`BackgroundAsset.import_prep()`) pose l'image dans le canvas avant
    d'encoder — le SEUL endroit où la préparation s'applique. Un bitmap a un canvas FIXE de 240×160, quoi qu'en
    dise `prep` : l'image garde sa taille et déborde, le surplus est rogné (jamais d'ajustement en douce).

    `work_cache`, réservé au flux interactif de l'éditeur, réutilise l'image
    préparée et les données par tuile lorsque leur clé est inchangée. Il ne
    modifie ni le PNG ni le résultat produit par cet appel."""
    bitmap = mode_token in ("bitmap", "bitmap16")
    if bitmap:
        prep = {**(prep or {}), "canvas": (GBA_SCREEN_W, GBA_SCREEN_H)}
    cache_key = None
    if prep:
        if work_cache:
            source, cache_key = work_cache.prepare(source, prep)
        else:
            source = prepare_source(source, **prep)
    if bitmap:
        return encode_background_bitmap(source, dither=dither, compression=compression, method=method)
    if mode_token == "tiled8":
        return encode_background_8bpp(source, dither=dither, method=method,
                                      compression=compression)
    return encode_background(source, method=method, compression=compression, dither=dither,
                             work_cache=work_cache, cache_key=cache_key)


def render_bitmap_preview(compiled: dict):
    """Reconstruit l'image RGBA d'un fond bitmap (Mode 4) : buffer d'index + palette
    256. Trivial (pas de tuiles)."""
    from PIL import Image
    w, h = compiled["out_w"], compiled["out_h"]
    pal = compiled["palettes"][0] if compiled["palettes"] else []
    rgb = [bgr555_to_rgb888(c) for c in pal]
    buf = bytes.fromhex(compiled["bitmap"])
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = out.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            idx = buf[row + x] if row + x < len(buf) else 0
            if idx == 0 or idx >= len(rgb):
                continue
            r, g, b = rgb[idx]
            px[x, y] = (r, g, b, 255)
    return out


def detect_bg_mode(source, tile_budget: int = TILE_BUDGET) -> str:
    """'bitmap' si l'image ne rentrera pas en tuilé (tuiles 8×8 uniques estimées >
    budget — typiquement une photo), sinon 'tiled'. Estimation rapide via numpy
    (sans dédup de flips → borne haute suffisante pour trancher photo vs pixel-art)."""
    from PIL import Image
    try:
        import numpy as np
    except Exception:
        return "tiled"
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGB")
    w, h = img.size
    tw, th = w // 8, h // 8
    if tw == 0 or th == 0:
        return "tiled"
    a = (np.asarray(img)[:th * 8, :tw * 8, :3] & 0xF8)
    a = a.reshape(th, 8, tw, 8, 3).transpose(0, 2, 1, 3, 4).reshape(th * tw, 8 * 8 * 3)
    uniq = len(np.unique(a, axis=0))
    return "bitmap" if uniq > tile_budget else "tiled"
